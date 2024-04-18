# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Holds helper functions to run fuzzers on hardware devices."""

import contextlib
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from chromite.lib import build_target_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import portage_util
from chromite.lib import remote_access


_CROS_GENERATE_SYSROOT = constants.CHROMITE_BIN_DIR / "cros_generate_sysroot"

# TODO(b/255365294): remove duplicate cros_fuzz and
# on device code.
_MAX_TOTAL_TIME_OPTION_NAME = "max_total_time"
_MAX_TOTAL_TIME_DEFAULT_VALUE = 30


class Error(Exception):
    """Base on_device_fuzz error class."""


class SetupError(Error):
    """Error for when setup commands fail."""


def create_sysroot_tarball(
    packages: Iterable[str],
    board: str,
    output_path: Path,
    board_build_dir: Optional[Path] = None,
) -> Path:
    """Create a sysroot tarball to install on device.

    Args:
        packages: Packages we want to include in the sysroot.
            Does not implicitly check for virtual/implicit-system.
        board: Board to build sysroot tarball for.
        output_path: Output path for the tarball. Should
            be a file path, not a directory.
        board_build_dir: Path to the board build dir
            to check for installed packages. Defaults to
            "/build/<board>".

    Returns:
        The output_path of the tarball.

    Raises:
        SetupError if the setup fails.
    """
    if not board_build_dir:
        board_build_dir = build_target_lib.get_default_sysroot_path(board)
    sysroot_tarball_setup_checks(packages, board_build_dir)
    package_str = " ".join(packages)
    sdk_cmd = [
        _CROS_GENERATE_SYSROOT,
        f"--out-file={output_path.name}",
        f"--out-dir={output_path.parent}",
        f"--board={board}",
        f"--package={package_str}",
    ]
    try:
        cros_build_lib.run(sdk_cmd, check=True, env={"USE": "asan fuzzer"})
    except cros_build_lib.RunCommandError as e:
        raise SetupError from e
    return output_path


def sysroot_tarball_setup_checks(
    packages: Iterable[str], board_build_dir: Path
):
    """Check that we can bundle the necessary packages for a sysroot.

    Args:
        packages: Packages we want to include in the sysroot.
            Does not implicitly check for virtual/implicit-system.
        board_build_dir: Path to the board build dir to check for
            installed packages.

    Raises:
        SetupError if the check fails. Otherwise returns None.
    """
    not_installed = _check_necessary_installed(packages, board_build_dir)
    if not_installed:
        logging.error(
            "Not all necessary packages are installed in %s:\n%s",
            board_build_dir,
            not_installed,
        )
        raise SetupError("Not all necessary packages installed.")


def _check_necessary_installed(
    atoms: Iterable[str], board_build_dir: Path
) -> List[Tuple[str, str]]:
    """Helper for checking the packages are installed."""
    match_gen = (
        (x, portage_util.PortageqMatch(x, sysroot=board_build_dir))
        for x in atoms
    )
    db = portage_util.PortageDB(board_build_dir)
    not_installed = []
    for atom, package_info in match_gen:
        if not package_info:
            not_installed.append((atom, None))
            continue
        if not db.GetInstalledPackage(package_info.category, package_info.pvr):
            not_installed.append((atom, package_info.cpvr))
    return not_installed


def create_dut_sysroot(
    device: remote_access.ChromiumOSDevice,
    sysroot_tarball: Path,
    sysroot_device_path: Path,
):
    """Create a sysroot on a device using a sysroot tarball.

    Args:
        device: Device to create the sysroot on.
        sysroot_tarball: Path on the build system to the sysroot tarball
            to unpack.
        sysroot_device_path: Path ON DEVICE for the sysroot to be located.
            Should be on an executable partition, like in /usr/local.
            Will be created if it does not exist. Should be absolute.
    """
    device.mkdir(sysroot_device_path)
    dest = sysroot_device_path.parent
    device.CopyToDevice(src=str(sysroot_tarball), dest=str(dest), mode="scp")
    untar_cmd = [
        "tar",
        "-xf",
        str(dest / sysroot_tarball.name),
        "-C",
        str(sysroot_device_path),
    ]
    device.run(untar_cmd)


def add_default_fuzz_time(libfuzzer_options: Dict[str, Any]) -> Dict[str, Any]:
    """Add default maximum fuzz time to the libfuzzer options if not set."""
    return {
        _MAX_TOTAL_TIME_OPTION_NAME: _MAX_TOTAL_TIME_DEFAULT_VALUE,
        **libfuzzer_options,
    }


def _setup_envs(cmd: List[str]) -> List[str]:
    """Set environment variables for ASAN, MSAN, UBSAN for chroot cmds."""
    # We have to prepend these environment variables because they are
    # run as a string in the chroot.
    sanitizers = ("ASAN", "MSAN", "UBSAN")
    options_dict = {"log_path": "stderr", "detect_odr_violation": "0"}
    sanitizer_options = ":".join(f"{k}={v}" for k, v in options_dict.items())
    sanitizer_vars = [
        f"{san}_OPTIONS={sanitizer_options}" for san in sanitizers
    ]
    return cmd + sanitizer_vars


@contextlib.contextmanager
def _sysroot_mount_context(
    device: remote_access.ChromiumOSDevice, sysroot_device_path: Path
):
    """Mount necessary system directories into the device sysroot.

    System directories are lazily unmounted from the chroot when exiting
    this context.

    Args:
        device: Device which to run fuzzers on.
        sysroot_device_path: Location on device where the sysroot is located.
            Cannot be the root dir.
    """
    if sysroot_device_path == Path("/"):
        raise ValueError("sysroot_device_path should never be the root dir")

    def _mount(flags, dirname: str):
        mount_target = str(sysroot_device_path / dirname)
        device.mkdir(mount_target)
        device.run(["mount"] + flags + [f"/{dirname}", mount_target])

    def _umount(dirname: str):
        mount_target = str(sysroot_device_path / dirname)
        # Lazily umount, because the mounts may be busy.
        device.run(["umount", "-l", mount_target])

    _mount(["-t", "proc"], "proc")
    _mount(["--rbind"], "dev")
    try:
        yield
    finally:
        _umount("dev")
        _umount("proc")


def run_fuzzer_executable(
    device: remote_access.ChromiumOSDevice,
    sysroot_device_path: Path,
    sysroot_fuzzer_path: Path,
    libfuzzer_options: Optional[Dict[str, Any]] = None,
):
    """Run a fuzzer on a device with an already set-up sysroot.

    Args:
        device: Device to run fuzzer on.
        sysroot_device_path: Location of sysroot on the device.
        sysroot_fuzzer_path: Location of the fuzzer, from within the sysroot
            on device. Usually something like
            Path("/usr/libexec/fuzzers/my_fuzzer").
        libfuzzer_options: Key-value pairs to pass to the fuzzer invocation.

    Raises:
        FileNotFoundError: When the fuzzer on device does not exist.
    """
    if not libfuzzer_options:
        libfuzzer_options = {}
    libfuzzer_options_timed = add_default_fuzz_time(libfuzzer_options)
    # We need the following command set up so we can pass arguments and
    # environment variables.
    libfuzzer_cmd = ["/usr/bin/env"]
    libfuzzer_cmd = _setup_envs(libfuzzer_cmd)
    libfuzzer_cmd.append(str(sysroot_fuzzer_path))
    libfuzzer_cmd += (f"-{k}={v}" for k, v in libfuzzer_options_timed.items())

    chroot_run_cmd = ["chroot", str(sysroot_device_path)] + libfuzzer_cmd
    outside_dut_sysroot_fuzzer = (
        sysroot_device_path / sysroot_fuzzer_path.relative_to("/")
    )
    if not device.IfFileExists(outside_dut_sysroot_fuzzer):
        logging.error(
            "Could not find fuzzer on device at" " %s. Maybe not installed?",
            outside_dut_sysroot_fuzzer,
        )
        raise FileNotFoundError(f"Fuzzer {sysroot_fuzzer_path} not found")
    with _sysroot_mount_context(device, sysroot_device_path):
        logging.info(
            "Running %s now on device...",
            sysroot_fuzzer_path,
        )
        # We can't capture output here because fuzzers run indefinitely.
        # In theory we could have a process that we poll every so often,
        # and then buffer the output, but not capturing the process
        # output seems to also do exactly what we need anyways.
        device.run(chroot_run_cmd, capture_output=False)
