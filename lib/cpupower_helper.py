# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""CPU Power related helpers."""

import contextlib
import errno
import logging
from pathlib import Path
from typing import Iterator, Optional

from chromite.lib import chromite_config
from chromite.lib import cros_build_lib
from chromite.lib import osutils


_AUTO_SET_GOV_CONTENT = (
    "# Delete this file to turn off automatic performance governor switch.\n"
)

_CPU_PATH = Path("/sys/devices/system/cpu")

# cpupower command with default options used to set scaling governor for CPUs
_CPUPOWER_CMD = ["cpupower", "-c", "all", "frequency-set", "-g"]


def _FetchActiveCpuGovernor() -> Optional[str]:
    """Scans and returns the active governor if all cpus use it.

    Returns:
        The active governor or None if there is no single active governor.
    """
    cpufreq = _CPU_PATH / "cpufreq"

    governors = set()
    offline_cpus = False
    for x in cpufreq.glob("policy*/scaling_governor"):
        try:
            governors.add(x.read_text(encoding="utf-8"))
        except OSError as e:
            if e.errno == errno.EBUSY:
                offline_cpus = True
                continue
    if offline_cpus:
        logging.warning(
            "Some CPUs are offline. Rebooting should bring them online."
        )
    if len(governors) != 1:
        logging.warning(
            "Too many active CPU governors; refusing to use 'performance'."
        )
        return None
    return next(iter(governors))


def _AutoSetGovStickyConfigUpdate(perf_governor: bool, sticky: bool) -> None:
    """Create/remove config file based on performance governor sticky request.

    Args:
        perf_governor: If true, switch the CPU governors to performance.
        sticky: If true, cache the switch request for subsequent runs.
    """
    if not sticky:
        return

    if not perf_governor:
        logging.info("Future runs will respect --autosetgov")
        osutils.SafeUnlink(chromite_config.AUTO_SET_GOV_CONFIG, sudo=True)
    elif not chromite_config.AUTO_SET_GOV_CONFIG.exists():
        logging.info("Future runs will *always* use --autosetgov")
        chromite_config.initialize()
        chromite_config.AUTO_SET_GOV_CONFIG.write_text(
            _AUTO_SET_GOV_CONTENT, encoding="utf-8"
        )


@contextlib.contextmanager
def ModifyCpuGovernor(perf_governor: bool, sticky: bool) -> Iterator[None]:
    """A context manager to switch the CPU governor policy to performance.

    This context manager will switch the CPU governors to the 'performance'
    governor and will revert the policy to the default governor when it exits.
    When the sticky option is selected, the governor will be automatically
    switched to performance for the subsequent runs. To clear this automatic
    switching, user must pass the perf_governor arg as false with sticky
    argument set to true.

    Args:
        perf_governor: If true, switch the CPU governors to performance.
        sticky: If true, cache the switch request for subsequent runs.

    Yields:
        Iterator.
    """

    _AutoSetGovStickyConfigUpdate(perf_governor, sticky)

    old_governor = None
    new_governor = None
    # If the config path is present we switch CPUs to performance governor.
    if chromite_config.AUTO_SET_GOV_CONFIG.exists():
        perf_governor = True
    if perf_governor:
        new_governor = "performance"
    # Check if performance governor is supported by the CPU.
    governor_path = (
        _CPU_PATH / "cpu0" / "cpufreq" / "scaling_available_governors"
    )
    try:
        governors = governor_path.read_text(encoding="utf-8").split()
    except FileNotFoundError as e:
        logging.debug("Error reading CPU scaling governor file: %s", e)
        governors = []

    try:
        if "performance" in governors:
            old_governor = _FetchActiveCpuGovernor()

            # Switch the CPU governors to performance if they have the same
            # active governor and if the active governor is not performance.
            if new_governor and old_governor and new_governor != old_governor:
                logging.info(
                    "Temporarily setting CPU governors to %s", new_governor
                )
                perf_cmd = _CPUPOWER_CMD + [new_governor]
                try:
                    cros_build_lib.sudo_run(
                        perf_cmd, print_cmd=False, capture_output=True
                    )
                except cros_build_lib.RunCommandError as e:
                    logging.warning("Error switching CPU governors: %s", e)
            elif old_governor == "powersave":
                logging.warning(
                    "Current CPU governor set to 'powersave' which can "
                    "slow down builds."
                )
                logging.warning(
                    "Use --autosetgov to automatically (and "
                    "temporarily) switch to 'performance'."
                )

        yield
    finally:
        if new_governor and old_governor and new_governor != old_governor:
            logging.info("Restoring CPU governors to %s", old_governor)
            restore_cmd = _CPUPOWER_CMD + [old_governor]
            try:
                cros_build_lib.sudo_run(
                    restore_cmd, print_cmd=False, capture_output=True
                )
            except cros_build_lib.RunCommandError as e:
                logging.warning("Error restoring CPU governors: %s", e)
