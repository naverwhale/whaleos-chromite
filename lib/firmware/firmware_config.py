# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""AP Firmware Config related functionality.

This module holds the firmware config objects, provides functionality to read
the config from ap_firmware_config modules, and export it into JSON.
"""

from typing import List, NamedTuple, Optional

from chromite.lib.firmware import ap_firmware_config
from chromite.lib.firmware import servo_lib


_CONFIG_BUILD_WORKON_PACKAGES = "BUILD_WORKON_PACKAGES"
_CONFIG_BUILD_PACKAGES = "BUILD_PACKAGES"


class FirmwareConfig(NamedTuple):
    """Stores firmware config for a specific board and a specific servo/ssh.

    Attributes:
        dut_control_on:  2d array formatted like
            [["cmd1", "arg1", "arg2"], ["cmd2", "arg3", "arg4"]]
            with commands that need to be ran before flashing,
            where cmd1 will be run before cmd2.
        dut_control_off: 2d array formatted like
            [["cmd1", "arg1", "arg2"], ["cmd2", "arg3", "arg4"]]
            with commands that need to be ran after flashing,
            where cmd1 will be run before cmd2.
        programmer: programmer argument (-p) for flashrom and futility.
        force_flashrom: force use of flashrom instead of futility.
        flash_extra_flags_futility: extra flags to flash with futility.
        flash_extra_flags_flashrom: extra flags to flash with flashrom.
        workon_packages: packages to cros-workon before building.
        build_packages: packages to build.
    """

    dut_control_on: List[List[str]]
    dut_control_off: List[List[str]]
    programmer: str
    force_flashrom: bool
    flash_extra_flags_futility: List[str]
    flash_extra_flags_flashrom: List[str]
    workon_packages: List[str]
    build_packages: List[str]


def get_config(
    build_target_name: str, servo: Optional[servo_lib.Servo]
) -> FirmwareConfig:
    """Return config for a given build target and servo/ssh.

    Args:
        build_target_name: Name of the build target, e.g. 'dedede'.
        servo: servo: The servo connected to the target DUT. None for SSH.
    """
    module = ap_firmware_config.get(build_target_name, fallback=True)

    workon_packages = getattr(module, _CONFIG_BUILD_WORKON_PACKAGES, None)
    build_packages = getattr(
        module, _CONFIG_BUILD_PACKAGES, ["chromeos-bootimage"]
    )

    if servo:
        dut_control_on, dut_control_off, programmer = module.get_config(servo)
        force_flashrom = getattr(module, "DEPLOY_SERVO_FORCE_FLASHROM", False)
        # Some servo variables are set to a different value by other programs.
        # Reset them to the default and then append with variables from the
        # config to avoid overriding config.
        reset_dut_control_on = [["ec_uart_timeout:10"]]
        dut_control_on = reset_dut_control_on + dut_control_on
    else:
        dut_control_on = []
        dut_control_off = []
        programmer = "internal"
        force_flashrom = getattr(module, "DEPLOY_SSH_FORCE_FLASHROM", False)

    flash_extra_flags_futility = []
    flash_extra_flags_flashrom = []
    if hasattr(module, "is_fast_required") and servo:
        if module.is_fast_required(True, servo):
            flash_extra_flags_futility += ["--fast"]
        if module.is_fast_required(False, servo):
            flash_extra_flags_flashrom += ["-n"]
    if hasattr(module, "deploy_extra_flags_futility"):
        flash_extra_flags_futility += module.deploy_extra_flags_futility(servo)
    if hasattr(module, "deploy_extra_flags_flashrom"):
        flash_extra_flags_flashrom += module.deploy_extra_flags_flashrom(servo)

    return FirmwareConfig(
        dut_control_on,
        dut_control_off,
        programmer,
        force_flashrom,
        flash_extra_flags_futility,
        flash_extra_flags_flashrom,
        workon_packages,
        build_packages,
    )
