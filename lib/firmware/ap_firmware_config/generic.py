# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO: Name the build target.

"""{Build Target} configs."""

from typing import List, Optional

from chromite.lib.firmware import servo_lib


# BUILD CONFIGS.
# You probably don't need to fill those in.
# BUILD_WORKON_PACKAGES is the list packages that will be `cros_workon`ed.
# TODO(b/197680341): deprecate in favor of --workon-all.
# BUILD_WORKON_PACKAGES = (
#    '',
# )
# All packages that need to be built.
# BUILD_PACKAGES = BUILD_WORKON_PACKAGES + (
#    '',
# )
# End BUILD CONFIGS.

# FLASH CONFIGS.

# futility will be used by default for flashing.
# TODO: If flashrom is required, set the constant to True with explanation.
# DEPLOY_SSH_FORCE_FLASHROM = False
# DEPLOY_SERVO_FORCE_FLASHROM = False


def deploy_extra_flags_futility(servo: Optional[servo_lib.Servo]) -> List[str]:
    """Returns extra flags for flashing with futility.

    Args:
        servo: The servo connected to the target DUT. Return flags for ssh if
            None.

    Returns:
        extra_flags: List of extra flags.
    """
    if not servo:
        # extra flags for flashing with futility directly over ssh
        return []
    if servo.is_ccd:
        # when flashing over CCD, skip verify step
        return ["--fast"]
    return []


def deploy_extra_flags_flashrom(servo: Optional[servo_lib.Servo]) -> List[str]:
    """Returns extra flags for flashing with flashrom.

    Args:
        servo: The servo connected to the target DUT. Return flags for ssh if
            None.

    Returns:
        extra_flags: List of extra flags.
    """
    if not servo:
        # extra flags for flashing with flashrom directly over ssh
        return []
    if servo.is_ccd:
        # when flashing over CCD, skip verify step
        return ["-n"]
    return []


def get_config(servo: servo_lib.Servo) -> servo_lib.ServoConfig:
    """Get DUT controls and programmer argument to flash a build target.

    Each board needs specific config including the voltage for Vref, to turn
    on and turn off the SPI flash. get_config() returns servo_lib.ServoConfig
    with settings to flash a servo for a particular build target.
    The voltage for this board needs to be set to 1.8 V.

    Args:
        servo: The servo connected to the target DUT.

    Returns:
        servo_lib.ServoConfig:
            dut_control_{on, off}=2d arrays formatted like
                [["cmd1", "arg1", "arg2"], ["cmd2", "arg3", "arg4"]]
                where cmd1 will be run before cmd2.
            programmer=programmer argument (-p) for flashrom and futility.
    """
    # TODO: Use `futility --servo`.  Stop using dut-control here.  Stop
    # specifying --programmer.  Let futility handle those things.
    if servo.is_v2:
        dut_control_on = [["cpu_fw_spi:on"]]
        dut_control_off = [["cpu_fw_spi:off"]]
        programmer = "ft2232_spi:type=google-servo-v2,serial=%s" % (
            servo.serial,
        )
    elif servo.is_micro or servo.is_c2d2:
        dut_control_on = [["cpu_fw_spi:on"]]
        dut_control_off = [["cpu_fw_spi:off"]]
        programmer = "raiden_debug_spi:serial=%s" % (servo.serial,)
    elif servo.is_ccd:
        dut_control_on = [["ccd_cpu_fw_spi:on"]]
        dut_control_off = [["ccd_cpu_fw_spi:off"]]
        programmer = "raiden_debug_spi:target=AP,custom_rst=true,serial=%s" % (
            servo.serial,
        )
    else:
        raise servo_lib.UnsupportedServoVersionError(
            "%s not supported" % (servo.version,)
        )

    return servo_lib.ServoConfig(dut_control_on, dut_control_off, programmer)


# End FLASH CONFIGS.
