# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module containing the various individual commands a builder can run."""

import collections
import contextlib
import datetime
import fnmatch
import glob
import json
import logging
import multiprocessing
import os
import re
import shutil
import sys
import tempfile
from typing import Dict

from chromite.cbuildbot import cbuildbot_alerts
from chromite.lib import build_target_lib
from chromite.lib import chromeos_version
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import failures_lib
from chromite.lib import gs
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.lib import portage_util
from chromite.lib import retry_util
from chromite.lib import sysroot_lib
from chromite.lib import timeout_util
from chromite.lib.paygen import filelib
from chromite.scripts import pushimage
from chromite.service import artifacts as artifacts_service
from chromite.utils import pformat


_PACKAGE_FILE = "%(buildroot)s/src/scripts/cbuildbot_package.list"
_FACTORY_SHIM = "factory_shim"
FACTORY_PACKAGE_CHROOT_PATH = "/build/%(board)s/usr/local/factory"
# Filename for tarball containing factory project specific files.
FACTORY_PROJECT_PACKAGE = "factory_project_toolkits.tar.gz"
LOCAL_BUILD_FLAGS = ["--nousepkg"]
UPLOADED_LIST_FILENAME = "UPLOADED"

# Filename for tarball containing Autotest server files needed for Server-Side
# Packaging.
AUTOTEST_SERVER_PACKAGE = "autotest_server_package.tar.bz2"

# Directory within AUTOTEST_SERVER_PACKAGE where Tast files needed to run with
# Server-Side Packaging are stored.
_TAST_SSP_SUBDIR = "tast"

# Tast files and directories to include in AUTOTEST_SERVER_PACKAGE relative to
# the build root. Public so it can be used by commands_unittest.py.
TAST_SSP_CHROOT_FILES = [
    "chroot/etc/tast/vars",  # Secret variables tast interprets.
    "chroot/usr/bin/remote_test_runner",  # Runs remote tests.
    "chroot/usr/bin/tast",  # Main Tast executable.
    "chroot/usr/libexec/tast/bundles",  # Dir containing test bundles.
    "chroot/usr/share/tast/data",  # Dir containing test data.
    "src/platform/tast/tools/run_tast.sh",  # Helper script to run SSP tast.
]

# =========================== Command Helpers =================================


def RunBuildScript(buildroot, cmd, chromite_cmd=False, **kwargs):
    """Run a build script, wrapping exceptions as needed.

    This wraps run(cmd, cwd=buildroot, **kwargs), adding extra logic to help
    determine the cause of command failures.
      - If a package fails to build, a PackageBuildFailure exception is thrown,
        which lists exactly which packages failed to build.
      - If the command fails for a different reason, a BuildScriptFailure
        exception is thrown.

    We detect what packages failed to build by creating a temporary status file,
    and passing that status file to parallel_emerge via the
    PARALLEL_EMERGE_STATUS_FILE variable.

    Args:
        buildroot: The root of the build directory.
        cmd: The command to run.
        chromite_cmd: Whether the command should be evaluated relative to the
            chromite/bin subdir of the |buildroot|.
        **kwargs: Optional args passed to run; see cros_build_lib.run for
            specifics. In addition, if 'sudo' kwarg is True, sudo_run will be
            used.
    """
    assert not kwargs.get("shell", False), "Cannot execute shell commands"
    kwargs.setdefault("cwd", buildroot)
    enter_chroot = kwargs.get("enter_chroot", False)
    sudo = kwargs.pop("sudo", False)

    if chromite_cmd:
        cmd = cmd[:]
        cmd[0] = str(buildroot / constants.CHROMITE_BIN_SUBDIR / cmd[0])
        if enter_chroot:
            cmd[0] = path_util.ToChrootPath(cmd[0], source_path=buildroot)

    # If we are entering the chroot, create status file for tracking what
    # packages failed to build.
    chroot_tmp = path_util.FromChrootPath("/tmp", source_path=buildroot)
    status_file = None
    with contextlib.ExitStack() as stack:
        if enter_chroot and os.path.exists(chroot_tmp):
            kwargs["extra_env"] = (kwargs.get("extra_env") or {}).copy()
            status_file = stack.enter_context(
                tempfile.NamedTemporaryFile(
                    dir=chroot_tmp,
                    mode="w+",
                    encoding="utf-8",
                )
            )
            kwargs["extra_env"][
                constants.PARALLEL_EMERGE_STATUS_FILE_ENVVAR
            ] = path_util.ToChrootPath(status_file.name, source_path=buildroot)
        runcmd = cros_build_lib.run
        if sudo:
            runcmd = cros_build_lib.sudo_run
        try:
            return runcmd(cmd, **kwargs)
        except cros_build_lib.RunCommandError as ex:
            # Print the original exception.
            logging.error("\n%s", ex)

            # Check whether a specific package failed. If so, wrap the exception
            # appropriately. These failures are usually caused by a recent CL,
            # so we don't ever treat these failures as flaky.
            if status_file is not None:
                status_file.seek(0)
                failed_packages = status_file.read().split()
                if failed_packages:
                    raise failures_lib.PackageBuildFailure(
                        ex, cmd[0], failed_packages
                    )

            # Looks like a generic failure. Raise a BuildScriptFailure.
            raise failures_lib.BuildScriptFailure(ex, cmd[0])


def ValidateClobber(buildroot):
    """Do due diligence if user wants to clobber buildroot.

    Args:
        buildroot: buildroot that's potentially clobbered.

    Returns:
        True if the clobber is ok.
    """
    cwd = os.path.dirname(os.path.realpath(__file__))
    if cwd.startswith(buildroot):
        cros_build_lib.Die("You are trying to clobber this chromite checkout!")

    if buildroot == "/":
        cros_build_lib.Die("Refusing to clobber your system!")

    if os.path.exists(buildroot):
        return cros_build_lib.BooleanPrompt(default=False)
    return True


# =========================== Main Commands ===================================


def WipeOldOutput(buildroot):
    """Wipes out build output directory.

    Args:
        buildroot: Root directory where build occurs.
        board: Delete image directories for this board name.
    """
    image_dir = os.path.join(buildroot, "src", "build", "images")
    osutils.RmDir(image_dir, ignore_missing=True, sudo=True)


def MakeChroot(
    buildroot,
    replace,
    use_sdk,
    chrome_root=None,
    extra_env=None,
    cache_dir=None,
):
    """Wrapper around make_chroot."""
    cmd = ["cros_sdk", "--buildbot-log-version"]
    if use_sdk:
        cmd.append("--create")
    else:
        cmd.append("--bootstrap")

    if replace:
        cmd.append("--replace")

    if chrome_root:
        cmd.append("--chrome_root=%s" % chrome_root)

    if cache_dir:
        cmd += ["--cache-dir", cache_dir]

    RunBuildScript(buildroot, cmd, chromite_cmd=True, extra_env=extra_env)


def UpdateChroot(
    buildroot, usepkg, toolchain_boards=None, extra_env=None, chroot_args=None
):
    """Wrapper around update_chroot.

    Args:
        buildroot: The buildroot of the current build.
        usepkg: Whether to use binary packages when setting up the toolchain.
        toolchain_boards: List of boards to always include.
        extra_env: A dictionary of environmental variables to set during
            generation.
        chroot_args: The args to the chroot.
    """
    cmd = ["./update_chroot"]

    if not usepkg:
        cmd.extend(["--nousepkg"])

    if toolchain_boards:
        cmd.extend(["--toolchain_boards", ",".join(toolchain_boards)])

    # workaround https://crbug.com/225509
    # Building with FEATURES=separatedebug will create a dedicated tarball with
    # the debug files, and the debug files won't be in the glibc.tbz2, which is
    # where the build scripts expect them.
    extra_env_local = extra_env.copy()
    extra_env_local.setdefault("FEATURES", "")
    extra_env_local["FEATURES"] += " -separatedebug splitdebug"

    RunBuildScript(
        buildroot,
        cmd,
        enter_chroot=True,
        chroot_args=chroot_args,
        extra_env=extra_env_local,
    )


def SetupBoard(
    buildroot,
    board,
    usepkg,
    extra_env=None,
    force=False,
    profile=None,
    chroot_upgrade=True,
    chroot_args=None,
):
    """Wrapper around setup_board.

    Args:
        buildroot: The buildroot of the current build.
        board: The board to set up.
        usepkg: Whether to use binary packages when setting up the board.
        extra_env: A dictionary of environmental variables to set during
            generation.
        force: Whether to remove the board prior to setting it up.
        profile: The profile to use with this board.
        chroot_upgrade: Whether to update the chroot. If the chroot is already
            up to date, you can specify chroot_upgrade=False.
        chroot_args: The args to the chroot.
    """
    cmd = ["setup_board", "--board=%s" % board, "--accept-licenses=@CHROMEOS"]

    # This isn't the greatest thing, but emerge's dependency calculation
    # isn't the speediest thing, so let callers skip this step when they
    # know the system is up-to-date already.
    if not chroot_upgrade:
        cmd.append("--skip-chroot-upgrade")

    if profile:
        cmd.append("--profile=%s" % profile)

    if not usepkg:
        # TODO(crbug.com/922144): Uses the underscore variant of an argument,
        # will require updating tests when the arguments are cleaned up.
        cmd.extend(LOCAL_BUILD_FLAGS)

    if force:
        cmd.append("--force")

    RunBuildScript(
        buildroot,
        cmd,
        chromite_cmd=True,
        extra_env=extra_env,
        enter_chroot=True,
        chroot_args=chroot_args,
    )


def LegacySetupBoard(
    buildroot,
    board,
    usepkg,
    extra_env=None,
    force=False,
    profile=None,
    chroot_upgrade=True,
    chroot_args=None,
):
    """Wrapper around setup_board for the workspace stage only.

    This wrapper supports the old version of setup_board, and is only meant to
    be used for the workspace builders so they can support old firmware/factory
    branches.

    This function should not need to be changed until it's deleted.

    Args:
        buildroot: The buildroot of the current build.
        board: The board to set up.
        usepkg: Whether to use binary packages when setting up the board.
        extra_env: A dictionary of environmental variables to set during
            generation.
        force: Whether to remove the board prior to setting it up.
        profile: The profile to use with this board.
        chroot_upgrade: Whether to update the chroot. If the chroot is already
            up to date, you can specify chroot_upgrade=False.
        chroot_args: The args to the chroot.
    """
    cmd = ["./setup_board", "--board=%s" % board, "--accept_licenses=@CHROMEOS"]

    # This isn't the greatest thing, but emerge's dependency calculation
    # isn't the speediest thing, so let callers skip this step when they
    # know the system is up-to-date already.
    if not chroot_upgrade:
        cmd.append("--skip_chroot_upgrade")

    if profile:
        cmd.append("--profile=%s" % profile)

    if not usepkg:
        cmd.extend(LOCAL_BUILD_FLAGS)

    if force:
        cmd.append("--force")

    RunBuildScript(
        buildroot,
        cmd,
        extra_env=extra_env,
        enter_chroot=True,
        chroot_args=chroot_args,
    )


def SetupToolchains(
    buildroot,
    usepkg=True,
    create_packages=False,
    targets=None,
    sysroot=None,
    boards=None,
    output_dir=None,
    **kwargs,
):
    """Install or update toolchains.

    See cros_setup_toolchains for more documentation about the arguments other
    than buildroot.

    Args:
        buildroot: str - The buildroot of the current build.
        usepkg: bool - Whether to use prebuilt packages.
        create_packages: bool - Whether to build redistributable packages.
        targets: str - Type of target for the toolchain install, e.g. 'boards'.
        sysroot: str - The sysroot in which to install the toolchains.
        boards: str|list - The board(s) whose toolchain should be installed.
        output_dir: str - The output directory.
    """
    kwargs.setdefault("chromite_cmd", True)
    kwargs.setdefault("enter_chroot", True)
    kwargs.setdefault("sudo", True)

    cmd = ["cros_setup_toolchains"]
    if not usepkg:
        cmd.append("--nousepkg")
    if create_packages:
        cmd.append("--create-packages")
    if targets:
        cmd += ["--targets", targets]
    if sysroot:
        cmd += ["--sysroot", sysroot]
    if boards:
        boards_str = boards if isinstance(boards, str) else ",".join(boards)
        cmd += ["--include-boards", boards_str]
    if output_dir:
        cmd += ["--output-dir", output_dir]

    RunBuildScript(buildroot, cmd, **kwargs)


class MissingBinpkg(failures_lib.StepFailure):
    """Error class for when we are missing an essential binpkg."""


def VerifyBinpkg(buildroot, board, pkg, packages, extra_env=None):
    """Verify that an appropriate binary package exists for |pkg|.

    Using the depgraph from |packages|, check to see if |pkg| would be pulled in
    as a binary or from source.  If |pkg| isn't installed at all, then ignore
    it.

    Args:
        buildroot: The buildroot of the current build.
        board: The board to set up.
        pkg: The package to look for.
        packages: The list of packages that get installed on |board|.
        extra_env: A dictionary of environmental variables to set.

    Raises:
        If the package is found and is built from source, raise MissingBinpkg.
        If the package is not found, or it is installed from a binpkg, do
        nothing.
    """
    cmd = [
        "emerge-%s" % board,
        "-pegNuvq",
        "--with-bdeps=y",
        "--color=n",
    ] + list(packages)
    result = RunBuildScript(
        buildroot,
        cmd,
        capture_output=True,
        encoding="utf-8",
        enter_chroot=True,
        extra_env=extra_env,
    )
    pattern = r"^\[(ebuild|binary).*%s" % re.escape(pkg)
    m = re.search(pattern, result.stdout, re.MULTILINE)
    if m and m.group(1) == "ebuild":
        logging.info("(output):\n%s", result.stdout)
        msg = "Cannot find prebuilts for %s on %s" % (pkg, board)
        raise MissingBinpkg(msg)


# pylint: disable=unused-argument
def Build(
    buildroot,
    board,
    build_autotest,
    usepkg,
    packages=(),
    skip_chroot_upgrade=True,
    extra_env=None,
    chrome_root=None,
    noretry=False,
    chroot_args=None,
    run_goma=False,
    disable_revdep_logic=False,
):
    """Wrapper around build_packages.

    Args:
        buildroot: The buildroot of the current build.
        board: The board to set up.
        build_autotest: Whether to build autotest-related packages.
        usepkg: Whether to use binary packages.
        packages: Tuple of specific packages we want to build. If empty,
            build_packages will calculate a list of packages automatically.
        skip_chroot_upgrade: Whether to skip the chroot update. If the chroot is
            not yet up to date, you should specify skip_chroot_upgrade=False.
        extra_env: A dictionary of environmental variables to set during
            generation.
        chrome_root: The directory where chrome is stored.
        noretry: Deprecated.
        chroot_args: The args to the chroot.
        run_goma: Set `build_package --run-goma` option, which starts and stops
            goma server in chroot while building packages.
        disable_revdep_logic: Pass --nowithrevdeps to build_packages, disabling
            the reverse dependency calculation step.
    """
    cmd = [
        "build_packages",
        "--board=%s" % board,
        "--accept-licenses=@CHROMEOS",
        "--withdebugsymbols",
    ]

    if not build_autotest:
        cmd.append("--no-withautotest")

    if skip_chroot_upgrade:
        cmd.append("--skip-chroot-upgrade")

    if not usepkg:
        cmd.append("--no-usepkg")

    if disable_revdep_logic:
        cmd.append("--no-withrevdeps")

    if run_goma:
        cmd.append("--run-goma")

    if not chroot_args:
        chroot_args = []

    if chrome_root:
        chroot_args.append("--chrome_root=%s" % chrome_root)

    cmd.extend(packages)
    RunBuildScript(
        buildroot,
        cmd,
        chromite_cmd=True,
        extra_env=extra_env,
        chroot_args=chroot_args,
        enter_chroot=True,
    )


def LegacyBuild(
    buildroot,
    board,
    build_autotest,
    usepkg,
    packages=(),
    skip_chroot_upgrade=True,
    extra_env=None,
    chrome_root=None,
    noretry=False,
    chroot_args=None,
    run_goma=False,
    disable_revdep_logic=False,
):
    """Wrapper around legacy build_packages.

    This wrapper supports the old version of build_packages to support old
    firmware/factory branches. Do not change this function until it's deleted.

    Args:
        buildroot: The buildroot of the current build.
        board: The board to set up.
        build_autotest: Whether to build autotest-related packages.
        usepkg: Whether to use binary packages.
        packages: Tuple of specific packages we want to build. If empty,
            build_packages will calculate a list of packages automatically.
        skip_chroot_upgrade: Whether to skip the chroot update. If the chroot is
            not yet up to date, you should specify skip_chroot_upgrade=False.
        extra_env: A dictionary of environmental variables to set during
            generation.
        chrome_root: The directory where chrome is stored.
        noretry: Do not retry package failures.
        chroot_args: The args to the chroot.
        run_goma: Set ./build_package --run_goma option, which starts and stops
            goma server in chroot while building packages.
        disable_revdep_logic: Pass --nowithrevdeps to build_packages, disabling
            the reverse dependency calculation step.
    """
    cmd = [
        "./build_packages",
        "--board=%s" % board,
        "--accept_licenses=@CHROMEOS",
        "--withdebugsymbols",
    ]

    if not build_autotest:
        cmd.append("--nowithautotest")

    if skip_chroot_upgrade:
        cmd.append("--skip_chroot_upgrade")

    if not usepkg:
        cmd.extend(LOCAL_BUILD_FLAGS)

    if noretry:
        cmd.append("--nobuildretry")

    if disable_revdep_logic:
        cmd.append("--nowithrevdeps")

    if run_goma:
        cmd.append("--run_goma")

    if not chroot_args:
        chroot_args = []

    if chrome_root:
        chroot_args.append("--chrome_root=%s" % chrome_root)

    cmd.extend(packages)
    RunBuildScript(
        buildroot,
        cmd,
        extra_env=extra_env,
        chroot_args=chroot_args,
        enter_chroot=True,
    )


FirmwareVersions = collections.namedtuple(
    "FirmwareVersions", ["model", "main", "main_rw", "ec", "ec_rw"]
)


def GetFirmwareVersionCmdResult(buildroot, board):
    """Gets the raw result output of the firmware updater version command.

    Args:
        buildroot: The buildroot of the current build.
        board: The board the firmware is for.

    Returns:
        Command execution result.
    """
    updater = os.path.join(
        build_target_lib.get_default_sysroot_path(board),
        "usr",
        "sbin",
        "chromeos-firmwareupdate",
    )
    if not os.path.isfile(
        path_util.FromChrootPath(updater, source_path=buildroot)
    ):
        return ""

    return cros_build_lib.run(
        [updater, "-V"],
        enter_chroot=True,
        capture_output=True,
        log_output=True,
        encoding="utf-8",
        cwd=buildroot,
    ).stdout


def FindFirmwareVersions(cmd_output):
    """Finds firmware version output via regex matches against the cmd_output.

    Args:
        cmd_output: The raw output to search against.

    Returns:
        FirmwareVersions namedtuple with results.
        Each element will either be set to the string output by the firmware
        updater shellball, or None if there is no match.
    """

    # Sometimes a firmware bundle includes a special combination of RO+RW
    # firmware.  In this case, the RW firmware version is indicated with a "(RW)
    # version" field.  In other cases, the "(RW) version" field is not present.
    # Therefore, search for the "(RW)" fields first and if they aren't present,
    # fallback to the other format. e.g. just "BIOS version:".
    # TODO(aaboagye): Use JSON once the firmware updater supports it.
    main = None
    main_rw = None
    ec = None
    ec_rw = None
    model = None

    match = re.search(r"BIOS version:\s*(?P<version>.*)", cmd_output)
    if match:
        main = match.group("version")

    match = re.search(r"BIOS \(RW\) version:\s*(?P<version>.*)", cmd_output)
    if match:
        main_rw = match.group("version")

    match = re.search(r"EC version:\s*(?P<version>.*)", cmd_output)
    if match:
        ec = match.group("version")

    match = re.search(r"EC \(RW\) version:\s*(?P<version>.*)", cmd_output)
    if match:
        ec_rw = match.group("version")

    match = re.search(r"Model:\s*(?P<model>.*)", cmd_output)
    if match:
        model = match.group("model")

    return FirmwareVersions(model, main, main_rw, ec, ec_rw)


def GetAllFirmwareVersions(buildroot, board):
    """Extract firmware version for all models present.

    Args:
        buildroot: The buildroot of the current build.
        board: The board the firmware is for.

    Returns:
        A dict of FirmwareVersions namedtuple instances by model.
        Each element will be populated based on whether it was present in the
        command output.
    """
    result = {}
    cmd_result = GetFirmwareVersionCmdResult(buildroot, board)

    # There is a blank line between the version info for each model.
    firmware_version_payloads = cmd_result.split("\n\n")
    for firmware_version_payload in firmware_version_payloads:
        if "BIOS" in firmware_version_payload:
            firmware_version = FindFirmwareVersions(firmware_version_payload)
            result[firmware_version.model] = firmware_version
    return result


def GetFirmwareVersions(buildroot, board):
    """Extract version information from the firmware updater, if one exists.

    Args:
        buildroot: The buildroot of the current build.
        board: The board the firmware is for.

    Returns:
        A FirmwareVersions namedtuple instance.
        Each element will either be set to the string output by the firmware
        updater shellball, or None if there is no firmware updater.
    """
    cmd_result = GetFirmwareVersionCmdResult(buildroot, board)
    if cmd_result:
        return FindFirmwareVersions(cmd_result)
    else:
        return FirmwareVersions(None, None, None, None, None)


def RunCrosConfigHost(buildroot, board, args, log_output=True):
    """Run the cros_config_host tool in the buildroot

    Args:
        buildroot: The buildroot of the current build.
        board: The board the build is for.
        args: List of arguments to pass.
        log_output: Whether to log the output of the cros_config_host.

    Returns:
        Output of the tool
    """
    tool = os.path.join(
        buildroot,
        constants.DEFAULT_CHROOT_DIR,
        "usr",
        "bin",
        "cros_config_host",
    )
    if not os.path.isfile(tool):
        return None
    tool = path_util.ToChrootPath(tool)

    config_fname = os.path.join(
        build_target_lib.get_default_sysroot_path(board),
        "usr",
        "share",
        "chromeos-config",
        "yaml",
        "config.yaml",
    )
    result = cros_build_lib.run(
        [tool, "-c", config_fname] + args,
        enter_chroot=True,
        capture_output=True,
        encoding="utf-8",
        log_output=log_output,
        cwd=buildroot,
        check=False,
    )
    if result.returncode:
        # Show the output for debugging purposes.
        if "No such file or directory" not in result.stderr:
            print(
                "cros_config_host failed: %s\n" % result.stderr, file=sys.stderr
            )
        return None
    return result.stdout.strip().splitlines()


def GetModels(buildroot, board, log_output=True):
    """Obtain a list of models supported by a unified board

    This ignored whitelabel models since GoldenEye has no specific support for
    these at present.

    Args:
        buildroot: The buildroot of the current build.
        board: The board the build is for.
        log_output: Whether to log the output of the cros_config_host
            invocation.

    Returns:
        A list of models supported by this board, if it is a unified build;
        None, if it is not a unified build.
    """
    return RunCrosConfigHost(
        buildroot, board, ["list-models"], log_output=log_output
    )


def BuildImage(
    buildroot,
    board,
    images_to_build,
    version=None,
    builder_path=None,
    rootfs_verification=True,
    extra_env=None,
    chroot_args=None,
):
    """Run the script which builds images.

    Args:
        buildroot: The buildroot of the current build.
        board: The board of the image.
        images_to_build: The images to be built.
        version: The version of image.
        builder_path: The path of the builder to build the image.
        rootfs_verification: Whether to enable the rootfs verification.
        extra_env: A dictionary of environmental variables to set during
            generation.
        chroot_args: The args to the chroot.
    """

    # Default to base if images_to_build is passed empty.
    if not images_to_build:
        images_to_build = ["base"]

    version_str = "--version=%s" % (version or "")

    builder_path_str = "--builder_path=%s" % (builder_path or "")

    cmd = [
        "./build_image",
        "--board=%s" % board,
        "--replace",
        version_str,
        builder_path_str,
    ]

    if not rootfs_verification:
        cmd += ["--noenable_rootfs_verification"]

    cmd += images_to_build

    RunBuildScript(
        buildroot,
        cmd,
        enter_chroot=True,
        extra_env=extra_env,
        chroot_args=chroot_args,
    )


def RunUnitTests(
    buildroot,
    board,
    extra_env=None,
    build_stage=True,
    chroot_args=None,
):
    cmd = ["cros_run_unit_tests", "--board=%s" % board, "--jobs=10"]

    if not build_stage:
        cmd += ["--assume-empty-sysroot"]

    RunBuildScript(
        buildroot,
        cmd,
        chromite_cmd=True,
        enter_chroot=True,
        extra_env=extra_env or {},
        chroot_args=chroot_args,
    )


@failures_lib.SetFailureType(failures_lib.BuilderFailure)
def ArchiveFile(file_to_archive, archive_dir):
    """Archives the specified file.

    Args:
        file_to_archive: Full path to file to archive.
        archive_dir: Local directory for archiving.

    Returns:
        The base name of the archived file.
    """
    filename = os.path.basename(file_to_archive)
    if archive_dir:
        archived_file = os.path.join(archive_dir, filename)
        shutil.copy(file_to_archive, archived_file)
        os.chmod(archived_file, 0o644)

    return filename


def UprevPackages(buildroot, boards, overlay_type, workspace=None):
    """Uprevs non-browser chromium os packages that have changed.

    Args:
        buildroot: Root directory where build occurs.
        boards: List of boards to uprev.
        overlay_type: A value from constants.VALID_OVERLAYS.
        workspace: Alternative buildroot directory to uprev.
    """
    assert overlay_type

    drop_file = _PACKAGE_FILE % {"buildroot": buildroot}
    cmd = [
        "cros_mark_as_stable",
        "commit",
        "--all",
        "--boards=%s" % ":".join(boards),
        "--drop_file=%s" % drop_file,
        "--buildroot",
        workspace or buildroot,
        "--overlay-type",
        overlay_type,
    ]

    RunBuildScript(buildroot, cmd, chromite_cmd=True)


def UprevPush(buildroot, overlay_type, dryrun=True, workspace=None):
    """Pushes uprev changes to the main line.

    Args:
        buildroot: Root directory where build occurs.
        dryrun: If True, do not actually push.
        overlay_type: A value from constants.VALID_OVERLAYS.
        workspace: Alternative buildroot directory to uprev.
    """
    assert overlay_type

    cmd = [
        "cros_mark_as_stable",
        "push",
        "--buildroot",
        workspace or buildroot,
        "--overlay-type",
        overlay_type,
    ]
    if dryrun:
        cmd.append("--dryrun")
    RunBuildScript(buildroot, cmd, chromite_cmd=True)


def ExtractBuildDepsGraph(buildroot, board):
    """Extract the build deps graph for |board| using build_api proto service.

    Args:
        buildroot: The root directory where the build occurs.
        board: Board type that was built on this machine.
    """
    input_proto = {
        "build_target": {
            "name": board,
        },
    }
    json_output = CallBuildApiWithInputProto(
        buildroot,
        "chromite.api.DependencyService/GetBuildDependencyGraph",
        input_proto,
    )
    return json_output["depGraph"]


def GenerateBuildConfigs(board, config_useflags):
    """Generate build configs..

    Args:
        board: Board type that was built on this machine.
        config_useflags: A list of useflags for this build set by the cbuildbot
            configs.

    Returns:
        A jsonizable object which is the combination of config.yaml (for
        unibuild) and use flags.
    """
    config_chroot_path = os.path.join(
        build_target_lib.get_default_sysroot_path(board),
        "usr",
        "share",
        "chromeos-config",
        "yaml",
        "config.yaml",
    )

    config_fname = path_util.FromChrootPath(config_chroot_path)

    results = {}
    if os.path.exists(config_fname):
        with open(config_fname, "rb") as f:
            results = json.load(f)
    else:
        logging.warning("Cannot find config.yaml file in %s", config_fname)

    results["board"] = board
    results["useflags"] = portage_util.PortageqEnvvar(
        variable="USE", board=board, allow_undefined=False
    )

    if config_useflags:
        results["config_useflags"] = config_useflags

    return results


def GenerateBreakpadSymbols(
    buildroot, board, debug, extra_env=None, chroot_args=None
):
    """Generate breakpad symbols.

    Args:
        buildroot: The root directory where the build occurs.
        board: Board type that was built on this machine.
        debug: Include extra debugging output.
        extra_env: A dictionary of environmental variables to set during
            generation.
        chroot_args: The args to the chroot.
    """
    # We don't care about firmware symbols.
    # See https://crbug.com/213670.
    exclude_dirs = ["firmware"]

    cmd = [
        "cros_generate_breakpad_symbols",
        "--board=%s" % board,
        "--jobs",
        str(max([1, multiprocessing.cpu_count() // 2])),
    ]
    cmd += ["--exclude-dir=%s" % x for x in exclude_dirs]
    if debug:
        cmd += ["--debug"]
    RunBuildScript(
        buildroot,
        cmd,
        enter_chroot=True,
        chromite_cmd=True,
        chroot_args=chroot_args,
        extra_env=extra_env,
    )


def GenerateAndroidBreakpadSymbols(
    buildroot, board, symbols_file, extra_env=None, chroot_args=None
):
    """Generate breakpad symbols of Android binaries.

    Args:
        buildroot: The root directory where the build occurs.
        board: Board type that was built on this machine.
        symbols_file: Path to a symbol archive file.
        extra_env: A dictionary of environmental variables to set during
            generation.
        chroot_args: The args to the chroot.
    """
    board_path = build_target_lib.get_default_sysroot_path(board)
    breakpad_dir = os.path.join(board_path, "usr", "lib", "debug", "breakpad")
    cmd = [
        "cros_generate_android_breakpad_symbols",
        "--symbols_file=%s" % path_util.ToChrootPath(symbols_file),
        "--breakpad_dir=%s" % breakpad_dir,
    ]
    RunBuildScript(
        buildroot,
        cmd,
        enter_chroot=True,
        chromite_cmd=True,
        chroot_args=chroot_args,
        extra_env=extra_env,
    )


def GenerateDebugTarball(
    buildroot,
    board,
    archive_path,
    gdb_symbols,
    archive_name="debug.tgz",
    chroot_compression=True,
):
    """Generates a debug tarball in the archive_dir, in or out of the chroot.

    Generates a debug tarball in the archive_dir. Invokes the appropriate
    algorithm based on whether we're inside or outside of the chroot.

    Args:
        buildroot: The root directory where the build occurs.
        board: Board type that was built on this machine
        archive_path: Directory where tarball should be stored.
        gdb_symbols: Include *.debug files for debugging core files with gdb.
        archive_name: Name of the tarball to generate.
        chroot_compression: Whether to use compression tools in the chroot if
            they're available.

    Returns:
        The filename of the created debug tarball.
    """
    func = (
        GenerateDebugTarballInsideChroot
        if cros_build_lib.IsInsideChroot()
        else GenerateDebugTarballOutsideChroot
    )

    return func(
        buildroot,
        board,
        archive_path,
        gdb_symbols,
        archive_name,
        chroot_compression,
    )


def GenerateDebugTarballInsideChroot(
    buildroot,
    board,
    archive_path,
    gdb_symbols,
    archive_name="debug.tgz",
    chroot_compression=True,
):
    """Generates a debug tarball in the archive_dir, from inside the chroot.

    Args:
        buildroot: The root directory where the build occurs.
        board: Board type that was built on this machine
        archive_path: Directory where tarball should be stored.
        gdb_symbols: Include *.debug files for debugging core files with gdb.
        archive_name: Name of the tarball to generate.
        chroot_compression: Whether to use compression tools in the chroot if
            they're available.

    Returns:
        The filename of the created debug tarball.
    """
    cros_build_lib.AssertInsideChroot()

    # Generate debug tarball. This needs to run as root because some of the
    # symbols are only readable by root.
    board_dir = path_util.FromChrootPath(
        os.path.join(
            build_target_lib.get_default_sysroot_path(board), "usr", "lib"
        ),
        source_path=buildroot,
    )
    debug_tarball = os.path.join(archive_path, archive_name)
    extra_args = None
    inputs = None

    if gdb_symbols:
        extra_args = [
            "--exclude",
            os.path.join("debug", constants.AUTOTEST_BUILD_PATH),
            "--exclude",
            "debug/tests",
        ]
        inputs = ["debug"]
    else:
        inputs = ["debug/breakpad"]

    compression_chroot = None
    if chroot_compression:
        compression_chroot = os.path.join(buildroot, "chroot")

    compression = cros_build_lib.CompressionExtToType(debug_tarball)
    cros_build_lib.CreateTarball(
        debug_tarball,
        board_dir,
        sudo=True,
        compression=compression,
        chroot=compression_chroot,
        inputs=inputs,
        extra_args=extra_args,
    )

    # Fix permissions and ownership on debug tarball.
    cros_build_lib.sudo_run(["chown", str(os.getuid()), debug_tarball])
    os.chmod(debug_tarball, 0o644)

    return os.path.basename(debug_tarball)


def GenerateDebugTarballOutsideChroot(
    buildroot,
    board,
    archive_path,
    gdb_symbols,
    archive_name="debug.tgz",
    chroot_compression=True,
):
    """Generates a debug tarball in the archive_dir, from outside the chroot.

    Args:
        buildroot: The root directory where the build occurs.
        board: Board type that was built on this machine
        archive_path: Directory where tarball should be stored.
        gdb_symbols: Include *.debug files for debugging core files with gdb.
        archive_name: Name of the tarball to generate.
        chroot_compression: Whether to use compression tools in the chroot if
            they're available.

    Returns:
        The filename of the created debug tarball.
    """
    cros_build_lib.AssertOutsideChroot()

    # Originally this called cros_build_lib.CreateTarball(), but ToT changes to
    # paths within the chroot meant we stopped being able to execute outside the
    # chroot. Since cbuildbot code is going away shortly anyway, we've done a
    # quick-fix to call tar directly rather than updating
    # cros_build_lib.CreateTarball() to support `enter_chroot`.

    # Generate debug tarball. This needs to run as root because some of the
    # symbols are only readable by root.
    board_dir = os.path.join(os.path.sep, "build", board, "usr", "lib")
    debug_tarball = os.path.join(archive_path, archive_name)
    extra_args = []
    inputs = []

    if gdb_symbols:
        extra_args = [
            "--exclude",
            os.path.join("debug", constants.AUTOTEST_BUILD_PATH),
            "--exclude",
            "debug/tests",
        ]
        inputs = ["debug"]
    else:
        inputs = ["debug/breakpad"]

    # Find the compression utility to use, and get its inside-chroot path.
    compression_chroot = None
    if chroot_compression:
        compression_chroot = os.path.join(buildroot, "chroot")

    compression = cros_build_lib.CompressionExtToType(debug_tarball)
    compressor = cros_build_lib.FindCompressor(
        compression, chroot=compression_chroot
    )
    if compressor.startswith("/bin/"):
        compressor = "/usr" + compressor
    try:
        compressor = path_util.ToChrootPath(compressor)
    except ValueError as e:
        if not e.args[0].startswith("Path is not reachable from the chroot"):
            raise

    # Invoke tar inside the chroot, creating a file in the chroot's `/tmp` dir
    # that we'll be able to access from outside the chroot.
    chroot_temp_debug_tarball = os.path.join("/tmp", archive_name)

    RunBuildScript(
        buildroot,
        [
            "tar",
            f"--directory={board_dir}",
            *extra_args,
            "--sparse",
            "--hole-detection=raw",
            "--use-compress-program",
            compressor,
            "-c",
            "-f",
            chroot_temp_debug_tarball,
            *inputs,
        ],
        enter_chroot=True,
        sudo=True,
    )

    # 15483.0.0 is when crrev/c/4522313 landed, and so is the version where we
    # can rely on out/tmp being available outside the chroot. The content from
    # that CL landed and was reverted a few times previously, so if we ever get
    # a Cbuildbot-based branch that got made while we were landing and
    # reverting before that CL, we may need to get more granular, but since
    # CBuildbot is disappearing shortly, this should be enough for our needs.
    first_version_with_outdir = "15483.0.0"
    dir_containing_tmp = (
        "out"
        if IsBuildRootAfterLimit(buildroot, first_version_with_outdir)
        else "chroot"
    )
    temp_debug_tarball = (
        os.path.join(buildroot, dir_containing_tmp) + chroot_temp_debug_tarball
    )
    if temp_debug_tarball != debug_tarball:
        # Move the tarball out of the `/tmp` dir to the archive location.
        # shutil.move() doesn't handle moving across mounts, so copy/delete.
        shutil.copy(temp_debug_tarball, debug_tarball)
        osutils.SafeUnlink(temp_debug_tarball, sudo=True)

    # Fix permissions and ownership on debug tarball.
    cros_build_lib.sudo_run(["chown", str(os.getuid()), debug_tarball])
    os.chmod(debug_tarball, 0o644)

    return os.path.basename(debug_tarball)


def GenerateUploadJSON(filepath, archive_path, uploaded):
    """Generate upload.json file given a set of filenames.

    The JSON is a dictionary keyed by filename, with entries for size, and
    hashes.

    Args:
        filepath: complete output filepath as string.
        archive_path: location of files.
        uploaded: file with list of uploaded filepaths, relative to
            archive_path.
    """
    utcnow = datetime.datetime.utcnow
    start = utcnow()

    result = {}
    files = osutils.ReadFile(uploaded).splitlines()
    for f in files:
        path = os.path.join(archive_path, f)
        # Ignore directories.
        if os.path.isdir(path):
            continue
        size = os.path.getsize(path)
        sha1, sha256 = filelib.ShaSums(path)
        result[f] = {"size": size, "sha1": sha1, "sha256": sha256}
    osutils.WriteFile(filepath, pformat.json(result))
    logging.info("GenerateUploadJSON completed in %s.", utcnow() - start)


def GenerateHtmlIndex(index, files, title="Index", url_base=None):
    """Generate a simple index.html file given a set of filenames

    Args:
        index: The file to write the html index to.
        files: The list of files to create the index of.  If a string, then it
            may be a path to a file (with one file per line), or a directory
            (which will be listed).
        title: Title string for the HTML file.
        url_base: The URL to prefix to all elements (otherwise they'll be
            relative).
    """

    def GenLink(target, name=None):
        if name == "":
            return ""
        return '<li><a href="%s%s">%s</a></li>' % (
            url_base,
            target,
            name if name else target,
        )

    if isinstance(files, str):
        if os.path.isdir(files):
            files = os.listdir(files)
        else:
            files = osutils.ReadFile(files).splitlines()
    url_base = url_base + "/" if url_base else ""

    # Head + open list.
    html = "<html>"
    html += "<head><title>%s</title></head>" % title
    html += "<body><h2>%s</h2><ul>" % title

    # List members.
    dot = (".",)
    dot_dot = ("..",)
    links = []
    for a in sorted(set(files)):
        a = a.split("|")
        if a[0] == ".":
            dot = a
        elif a[0] == "..":
            dot_dot = a
        else:
            links.append(GenLink(*a))
    links.insert(0, GenLink(*dot_dot))
    links.insert(0, GenLink(*dot))
    html += "\n".join(links)

    # Close list and file.
    html += "</ul></body></html>"

    osutils.WriteFile(index, html)


@failures_lib.SetFailureType(failures_lib.GSUploadFailure)
def _UploadPathToGS(local_path, upload_urls, debug, timeout, acl=None):
    """Upload |local_path| to Google Storage.

    Args:
        local_path: Local path to upload.
        upload_urls: Iterable of GS locations to upload to.
        debug: Whether we are in debug mode.
        filename: Filename of the file to upload.
        timeout: Timeout in seconds.
        acl: Canned gsutil acl to use.
    """
    gs_context = gs.GSContext(acl=acl, dry_run=debug)
    for upload_url in upload_urls:
        with timeout_util.Timeout(timeout):
            gs_context.CopyInto(
                local_path, upload_url, parallel=True, recursive=True
            )


@failures_lib.SetFailureType(failures_lib.InfrastructureFailure)
def UploadArchivedFile(
    archive_dir,
    upload_urls,
    filename,
    debug,
    update_list=False,
    timeout=2 * 60 * 60,
    acl=None,
):
    """Uploads |filename| in |archive_dir| to Google Storage.

    Args:
        archive_dir: Path to the archive directory.
        upload_urls: Iterable of GS locations to upload to.
        debug: Whether we are in debug mode.
        filename: Name of the file to upload.
        update_list: Flag to update the list of uploaded files.
        timeout: Timeout in seconds.
        acl: Canned gsutil acl to use.
    """
    # Upload the file.
    file_path = os.path.join(archive_dir, filename)
    _UploadPathToGS(file_path, upload_urls, debug, timeout, acl=acl)

    if update_list:
        # Append |filename| to the local list of uploaded files and archive
        # the list to Google Storage. As long as the |filename| string is
        # less than PIPE_BUF (> 512 bytes), the append is atomic.
        uploaded_file_path = os.path.join(archive_dir, UPLOADED_LIST_FILENAME)
        osutils.WriteFile(uploaded_file_path, filename + "\n", mode="a")
        _UploadPathToGS(uploaded_file_path, upload_urls, debug, timeout)


def UploadSymbols(
    buildroot,
    board=None,
    official=False,
    cnt=None,
    failed_list=None,
    breakpad_root=None,
    product_name=None,
    extra_env=None,
    chroot_args=None,
):
    """Upload debug symbols for this build."""
    cmd = ["upload_symbols", "--yes", "--dedupe"]

    if board is not None:
        # Board requires both root and board to be set to be useful.
        cmd += [
            "--root",
            os.path.join(buildroot, constants.DEFAULT_CHROOT_DIR),
            "--board",
            board,
        ]
    if official:
        cmd.append("--official_build")
    if cnt is not None:
        cmd += ["--upload-limit", str(cnt)]
    if failed_list is not None:
        cmd += ["--failed-list", str(failed_list)]
    if breakpad_root is not None:
        cmd += ["--breakpad_root", breakpad_root]
    if product_name is not None:
        cmd += ["--product_name", product_name]

    # We don't want to import upload_symbols directly because it uses the
    # swarming module which itself imports a _lot_ of stuff.  It has also
    # been known to hang.  We want to keep cbuildbot isolated & robust.
    RunBuildScript(
        buildroot,
        cmd,
        chromite_cmd=True,
        chroot_args=chroot_args,
        extra_env=extra_env,
    )


def PushImages(
    board, archive_url, dryrun, profile, sign_types=(), buildroot=None
):
    """Push the generated image to the release bucket for signing."""
    # Log the equivalent command for debugging purposes.
    log_cmd = ["pushimage", "--board=%s" % board]

    if dryrun:
        log_cmd.append("-n")

    if profile:
        log_cmd.append("--profile=%s" % profile)

    if sign_types:
        log_cmd.append("--sign-types")
        log_cmd.extend(sign_types)

    if buildroot:
        log_cmd.append("--buildroot=%s" % buildroot)

    log_cmd.append(archive_url)
    logging.info("Running: %s", cros_build_lib.CmdToStr(log_cmd))

    try:
        return pushimage.PushImage(
            archive_url,
            board,
            profile=profile,
            sign_types=sign_types,
            dryrun=dryrun,
            buildroot=buildroot,
        )
    except pushimage.PushError as e:
        cbuildbot_alerts.PrintBuildbotStepFailure()
        return e.args[1]


def BuildFactoryInstallImage(buildroot, board, extra_env):
    """Build a factory install image.

    Args:
        buildroot: Root directory where build occurs.
        board: Board type that was built on this machine
        extra_env: Flags to be added to the environment for the new process.

    Returns:
        The basename of the symlink created for the image.
    """

    # We use build_attempt=3 here to ensure that this image uses a different
    # output directory from our regular image and the factory test image.
    alias = _FACTORY_SHIM
    cmd = [
        "./build_image",
        "--board=%s" % board,
        "--replace",
        "--noeclean",
        "--symlink=%s" % alias,
        "--build_attempt=3",
        "factory_install",
    ]
    RunBuildScript(
        buildroot,
        cmd,
        extra_env=extra_env,
        capture_output=True,
        enter_chroot=True,
    )
    return alias


def MakeNetboot(buildroot, board, image_dir):
    """Build a netboot image.

    Args:
        buildroot: Root directory where build occurs.
        board: Board type that was built on this machine.
        image_dir: Directory containing factory install shim.
    """
    cmd = [
        "./make_netboot.sh",
        "--board=%s" % board,
        "--image_dir=%s" % path_util.ToChrootPath(image_dir),
    ]
    RunBuildScript(buildroot, cmd, capture_output=True, enter_chroot=True)


def BuildRecoveryImage(buildroot, board, image_dir, extra_env):
    """Build a recovery image.

    Args:
        buildroot: Root directory where build occurs.
        board: Board type that was built on this machine.
        image_dir: Directory containing base image.
        extra_env: Flags to be added to the environment for the new process.
    """
    base_image = os.path.join(image_dir, constants.BASE_IMAGE_BIN)
    # mod_image_for_recovery leaves behind some artifacts in the source
    # directory that we don't care about. So, use a tempdir as the working
    # directory. This tempdir needs to be at a chroot accessible path.
    with osutils.TempDir(base_dir=image_dir) as tempdir:
        tempdir_base_image = os.path.join(tempdir, constants.BASE_IMAGE_BIN)
        tempdir_recovery_image = os.path.join(
            tempdir, constants.RECOVERY_IMAGE_BIN
        )

        # Copy the base image. Symlinking isn't enough because image building
        # scripts follow symlinks by design.
        shutil.copyfile(base_image, tempdir_base_image)
        cmd = [
            "./mod_image_for_recovery.sh",
            "--board=%s" % board,
            "--image=%s" % path_util.ToChrootPath(tempdir_base_image),
        ]
        RunBuildScript(
            buildroot,
            cmd,
            extra_env=extra_env,
            capture_output=True,
            enter_chroot=True,
        )
        shutil.move(tempdir_recovery_image, image_dir)


def BuildTarball(
    buildroot, input_list, tarball_path, cwd=None, compressed=True, **kwargs
):
    """Tars and zips files and directories from input_list to tarball_path.

    Args:
        buildroot: Root directory where build occurs.
        input_list: A list of files and directories to be archived.
        tarball_path: Path of output tar archive file.
        cwd: Current working directory when tar command is executed.
        compressed: Whether or not the tarball should be compressed with pbzip2.
        **kwargs: Keyword arguments to pass to CreateTarball.

    Returns:
        Return value of cros_build_lib.CreateTarball.
    """
    compressor = cros_build_lib.CompressionType.NONE
    chroot = None
    if compressed:
        compressor = cros_build_lib.CompressionType.BZIP2
        chroot = os.path.join(buildroot, "chroot")
    return cros_build_lib.CreateTarball(
        tarball_path,
        cwd,
        compression=compressor,
        chroot=chroot,
        inputs=input_list,
        **kwargs,
    )


def FindFilesWithPattern(pattern, target="./", cwd=os.curdir, exclude_dirs=()):
    """Search the root directory recursively for matching filenames.

    Args:
        pattern: the pattern used to match the filenames.
        target: the target directory to search.
        cwd: current working directory.
        exclude_dirs: Directories to not include when searching.

    Returns:
        A list of paths of the matched files.
    """
    # Backup the current working directory before changing it
    old_cwd = os.getcwd()
    os.chdir(cwd)

    matches = []
    for root, _, filenames in os.walk(target):
        if not any(root.startswith(e) for e in exclude_dirs):
            for filename in fnmatch.filter(filenames, pattern):
                matches.append(os.path.join(root, filename))

    # Restore the working directory
    os.chdir(old_cwd)

    return matches


def BuildAutotestControlFilesTarball(buildroot, cwd, tarball_dir):
    """Tar up the autotest control files.

    Args:
        buildroot: Root directory where build occurs.
        cwd: Current working directory.
        tarball_dir: Location for storing autotest tarball.

    Returns:
        Path of the partial autotest control files tarball.
    """
    # Find the control files in autotest/
    control_files = FindFilesWithPattern(
        "control*",
        target="autotest",
        cwd=cwd,
        exclude_dirs=["autotest/test_suites"],
    )
    control_files_tarball = os.path.join(tarball_dir, "control_files.tar")
    BuildTarball(
        buildroot,
        control_files,
        control_files_tarball,
        cwd=cwd,
        compressed=False,
    )
    return control_files_tarball


def BuildAutotestPackagesTarball(buildroot, cwd, tarball_dir):
    """Tar up the autotest packages.

    Args:
        buildroot: Root directory where build occurs.
        cwd: Current working directory.
        tarball_dir: Location for storing autotest tarball.

    Returns:
        Path of the partial autotest packages tarball.
    """
    input_list = ["autotest/packages"]
    packages_tarball = os.path.join(tarball_dir, "autotest_packages.tar")
    BuildTarball(
        buildroot, input_list, packages_tarball, cwd=cwd, compressed=False
    )
    return packages_tarball


def BuildAutotestTestSuitesTarball(buildroot, cwd, tarball_dir):
    """Tar up the autotest test suite control files.

    Args:
        buildroot: Root directory where build occurs.
        cwd: Current working directory.
        tarball_dir: Location for storing autotest tarball.

    Returns:
        Path of the autotest test suites tarball.
    """
    test_suites_tarball = os.path.join(tarball_dir, "test_suites.tar.bz2")
    BuildTarball(
        buildroot, ["autotest/test_suites"], test_suites_tarball, cwd=cwd
    )
    return test_suites_tarball


def BuildAutotestServerPackageTarball(buildroot, cwd, tarball_dir):
    """Tar up the autotest files required by the server package.

    Args:
        buildroot: Root directory where build occurs.
        cwd: Current working directory.
        tarball_dir: Location for storing autotest tarballs.

    Returns:
        The path of the autotest server package tarball.
    """
    # Find all files in autotest excluding certain directories.
    autotest_files = FindFilesWithPattern(
        "*",
        target="autotest",
        cwd=cwd,
        exclude_dirs=(
            "autotest/packages",
            "autotest/client/deps/",
            "autotest/client/tests",
            "autotest/client/site_tests",
        ),
    )

    tast_files, transforms = _GetTastServerFilesAndTarTransforms(buildroot)

    tarball = os.path.join(tarball_dir, AUTOTEST_SERVER_PACKAGE)
    BuildTarball(
        buildroot,
        autotest_files + tast_files,
        tarball,
        cwd=cwd,
        extra_args=transforms,
        check=False,
    )
    return tarball


def _GetTastServerFilesAndTarTransforms(buildroot):
    """Returns Tast server files and corresponding tar transform flags.

    The returned paths should be included in AUTOTEST_SERVER_PACKAGE. The
    --transform arguments should be passed to GNU tar to convert the paths to
    appropriate destinations in the tarball.

    Args:
        buildroot: Absolute path to root build directory.

    Returns:
        (files, transforms), where files is a list of absolute paths to Tast
        server files/directories and transforms is a list of --transform
        arguments to pass to GNU tar when archiving those files.
    """
    files = []
    transforms = []

    for p in TAST_SSP_CHROOT_FILES:
        path = path_util.FromChrootPath(
            p,
            source_path=buildroot,
        )
        if os.path.exists(path):
            files.append(path)
            dest = os.path.join(_TAST_SSP_SUBDIR, os.path.basename(path))
            transforms.append(
                "--transform=s|^%s|%s|" % (os.path.relpath(path, "/"), dest)
            )

    return files, transforms


def BuildAutotestTarballsForHWTest(buildroot, cwd, tarball_dir):
    """Generate the "usual" autotest tarballs required for running HWTests.

    These tarballs are created in multiple places wherever they need to be
    staged for running HWTests.

    Args:
        buildroot: Root directory where build occurs.
        cwd: Current working directory.
        tarball_dir: Location for storing autotest tarballs.

    Returns:
        A list of paths of the generated tarballs.

    TODO(crbug.com/924655): Has been ported to a build API endpoint. Remove this
    function and any unused child functions when the stages have been updated to
    use the API call.
    """
    return [
        BuildAutotestControlFilesTarball(buildroot, cwd, tarball_dir),
        BuildAutotestPackagesTarball(buildroot, cwd, tarball_dir),
        BuildAutotestTestSuitesTarball(buildroot, cwd, tarball_dir),
        BuildAutotestServerPackageTarball(buildroot, cwd, tarball_dir),
    ]


def BuildTastBundleTarball(buildroot, cwd, tarball_dir):
    """Tar up the Tast private test bundles.

    Args:
        buildroot: Root directory where build occurs.
        cwd: Current working directory pointing /build/$board/build.
        tarball_dir: Location for storing the tarball.

    Returns:
        Path of the generated tarball, or None if there is no private test
        bundles.
    """
    chroot = chroot_lib.Chroot(
        path=os.path.join(buildroot, "chroot"),
        out_path=buildroot / constants.DEFAULT_OUT_DIR,
    )
    sysroot_path = chroot.chroot_path(os.path.normpath(os.path.join(cwd, "..")))
    sysroot = sysroot_lib.Sysroot(sysroot_path)

    return artifacts_service.BundleTastFiles(chroot, sysroot, tarball_dir)


def BuildImageZip(archive_dir, image_dir):
    """Build image.zip in archive_dir from contents of image_dir.

    Exclude the dev image from the zipfile.

    Args:
        archive_dir: Directory to store image.zip.
        image_dir: Directory to zip up.

    Returns:
        The basename of the zipfile.
    """
    filename = "image.zip"
    zipfile = os.path.join(archive_dir, filename)
    cros_build_lib.run(
        ["zip", zipfile, "-r", "."], cwd=image_dir, capture_output=True
    )
    return filename


def BuildStandaloneArchive(archive_dir, image_dir, artifact_info):
    """Create a compressed archive from the specified image information.

    The artifact info is derived from a JSON file in the board overlay. It
    should be in the following format:
    {
    "artifacts": [
      { artifact },
      { artifact },
      ...
    ]
    }
    Each artifact can contain the following keys:
    input - Required. A list of paths and globs that expands to
        the list of files to archive.
    output - the name of the archive to be created. If omitted,
        it will default to the first filename, stripped of
        extensions, plus the appropriate .tar.gz or other suffix.
    archive - "tar" or "zip". If omitted, files will be uploaded
        directly, without being archived together.
    compress - a value cros_build_lib.CompressionStrToType knows about. Only
        useful for tar. If omitted, an uncompressed tar will be created.

    Args:
        archive_dir: Directory to store image zip.
        image_dir: Base path for all inputs.
        artifact_info: Extended archive configuration dictionary containing: -
            paths - required, list of files to archive. - output archive &
            compress entries from the JSON file.

    Returns:
        The base name of the archive.

    Raises:
        A ValueError if the compression or archive values are unknown.
        A KeyError is a required field is missing from artifact_info.
    """
    if "archive" not in artifact_info:
        # Copy the file in 'paths' as is to the archive directory.
        if len(artifact_info["paths"]) > 1:
            raise ValueError(
                "default archive type does not support multiple inputs"
            )
        src_path = os.path.join(image_dir, artifact_info["paths"][0])
        tgt_path = os.path.join(archive_dir, artifact_info["paths"][0])
        if not os.path.exists(tgt_path):
            # The image may have already been copied into place. If so,
            # overwriting it can affect parallel processes.
            if os.path.isdir(src_path):
                shutil.copytree(src_path, tgt_path)
            else:
                shutil.copy(src_path, tgt_path)
        return artifact_info["paths"]

    inputs = artifact_info["paths"]
    archive = artifact_info["archive"]
    compress = artifact_info.get("compress")
    compress_type = cros_build_lib.CompressionStrToType(compress)
    if compress_type is None:
        raise ValueError("unknown compression type: %s" % compress)

    # If the output is fixed, use that. Otherwise, construct it
    # from the name of the first archived file, stripping extensions.
    filename = artifact_info.get(
        "output", "%s.%s" % (os.path.splitext(inputs[0])[0], archive)
    )
    if archive == "tar":
        # Add the .compress extension if we don't have a fixed name.
        if "output" not in artifact_info and compress:
            filename = "%s.%s" % (filename, compress)
        extra_env = {"XZ_OPT": "-1"}
        cros_build_lib.CreateTarball(
            os.path.join(archive_dir, filename),
            image_dir,
            inputs=inputs,
            compression=compress_type,
            extra_env=extra_env,
        )
    elif archive == "zip":
        cros_build_lib.run(
            ["zip", os.path.join(archive_dir, filename), "-r"] + inputs,
            cwd=image_dir,
            capture_output=True,
        )
    else:
        raise ValueError("unknown archive type: %s" % archive)

    return [filename]


def BuildStrippedPackagesTarball(buildroot, board, package_globs, archive_dir):
    """Builds a tarball containing stripped packages.

    Args:
        buildroot: Root directory where build occurs.
        board: The board for which packages should be tarred up.
        package_globs: List of package search patterns. Each pattern is used to
            search for packages via `equery list`.
        archive_dir: The directory to drop the tarball in.

    Returns:
        The file name of the output tarball, None if no package found.
    """
    chroot = chroot_lib.Chroot(
        path=os.path.join(buildroot, "chroot"),
        out_path=buildroot / constants.DEFAULT_OUT_DIR,
    )
    board_path = chroot.full_path(os.path.join("/build", board))
    stripped_pkg_dir = os.path.join(board_path, "stripped-packages")
    tarball_paths = []
    strip_package_path = chroot.chroot_path(
        constants.CHROMITE_SCRIPTS_DIR / "strip_package"
    )
    for pattern in package_globs:
        packages = portage_util.FindPackageNameMatches(
            pattern, board, chroot=chroot
        )
        for cpv in packages:
            cmd = [strip_package_path, "--board", board, cpv.cpf]
            cros_build_lib.run(cmd, cwd=buildroot, enter_chroot=True)
            # Find the stripped package.
            files = glob.glob(os.path.join(stripped_pkg_dir, cpv.cpf) + ".*")
            if not files:
                raise AssertionError(
                    "Silent failure to strip binary %s? "
                    "Failed to find stripped files at %s."
                    % (cpv.cpf, os.path.join(stripped_pkg_dir, cpv.cpf))
                )
            if len(files) > 1:
                cbuildbot_alerts.PrintBuildbotStepWarnings()
                logging.warning(
                    "Expected one stripped package for %s, found %d",
                    cpv.cpf,
                    len(files),
                )

            tarball = sorted(files)[-1]
            tarball_paths.append(os.path.relpath(tarball, board_path))

    if not tarball_paths:
        # tar barfs on an empty list of files, so skip tarring completely.
        return None

    tarball_output = os.path.join(archive_dir, "stripped-packages.tar")
    BuildTarball(
        buildroot,
        tarball_paths,
        tarball_output,
        compressed=False,
        cwd=board_path,
    )
    return os.path.basename(tarball_output)


def BuildEbuildLogsTarball(buildroot, board, archive_dir):
    """Builds a tarball containing ebuild logs.

    Args:
        buildroot: Root directory where build occurs.
        board: The board for which packages should be tarred up.
        archive_dir: The directory to drop the tarball in.

    Returns:
        The file name of the output tarball, None if no package found.
    """
    sysroot = sysroot_lib.Sysroot(os.path.join("build", board))
    chroot = chroot_lib.Chroot(
        path=os.path.join(buildroot, "chroot"),
        out_path=buildroot / constants.DEFAULT_OUT_DIR,
    )
    return artifacts_service.BundleEBuildLogsTarball(
        chroot, sysroot, archive_dir
    )


def BuildFirmwareArchive(
    buildroot, board, archive_dir, archive_name=constants.FIRMWARE_ARCHIVE_NAME
):
    """Build firmware_from_source.tar.bz2 in archive_dir from build root.

    Args:
        buildroot: Root directory where build occurs.
        board: Board name of build target.
        archive_dir: Directory to store output file.
        archive_name: Name of file to create in archive_dir.

    Returns:
        The basename of the archived file, or None if the target board does
        not have firmware from source.
    """
    sysroot = sysroot_lib.Sysroot(os.path.join("build", board))
    chroot = chroot_lib.Chroot(
        path=os.path.join(buildroot, "chroot"),
        out_path=buildroot / constants.DEFAULT_OUT_DIR,
    )

    archive_file = artifacts_service.BuildFirmwareArchive(
        chroot, sysroot, archive_dir
    )
    if archive_file is None:
        return None
    else:
        shutil.move(archive_file, os.path.join(archive_dir, archive_name))
        return archive_name


def BuildFpmcuUnittestsArchive(buildroot, board, tarball_dir):
    """Build fpmcu_unittests.tar.bz2 for fingerprint MCU on-device testing.

    Args:
        buildroot: Root directory where build occurs.
        board: Board name of build target.
        tarball_dir: Directory to store output file.

    Returns:
        The path of the archived file, or None if the target board does
        not have fingerprint MCU unittest binaries.
    """
    sysroot = sysroot_lib.Sysroot(os.path.join("build", board))
    chroot = chroot_lib.Chroot(
        path=os.path.join(buildroot, "chroot"),
        out_path=buildroot / constants.DEFAULT_OUT_DIR,
    )

    return artifacts_service.BundleFpmcuUnittests(chroot, sysroot, tarball_dir)


def CallBuildApiWithInputProto(
    buildroot: str, build_api_command: str, input_proto: Dict
):
    """Call BuildApi with the input_proto and buildroot.

    Args:
        buildroot: Root directory where build occurs.
        build_api_command: Service (command) to execute.
        input_proto: The input proto as a dict.

    Returns:
        The json-encoded output proto.
    """
    cmd = ["build_api", build_api_command]
    with osutils.TempDir() as tmpdir:
        input_proto_file = os.path.join(tmpdir, "input.json")
        output_proto_file = os.path.join(tmpdir, "output.json")
        pformat.json(input_proto, fp=input_proto_file)
        cmd += [
            "--input-json",
            input_proto_file,
            "--output-json",
            output_proto_file,
        ]
        RunBuildScript(buildroot, cmd, chromite_cmd=True, stdout=True)
        return json.loads(osutils.ReadFile(output_proto_file))


def BuildFactoryZip(
    buildroot, board, archive_dir, factory_shim_dir, version=None
):
    """Build factory_image.zip in archive_dir.

    Args:
        buildroot: Root directory where build occurs.
        board: Board name of build target.
        archive_dir: Directory to store factory_image.zip.
        factory_shim_dir: Directory containing factory shim.
        version: The version string to be included in the factory image.zip.

    Returns:
        The basename of the zipfile.
    """
    filename = "factory_image.zip"

    zipfile = os.path.join(archive_dir, filename)
    cmd = ["zip", "-r", zipfile]

    # Rules for archive: { folder: pattern }
    rules = {
        factory_shim_dir: [
            "*factory_install*.bin",
            "*partition*",
            os.path.join("netboot", "*"),
        ],
    }

    for folder, patterns in rules.items():
        if not folder or not os.path.exists(folder):
            continue
        dirname = os.path.dirname(folder)
        basename = os.path.basename(folder)
        pattern_options = []
        for pattern in patterns:
            pattern_options.extend(
                ["--include", os.path.join(basename, pattern)]
            )
        # factory_shim_dir may be a symlink. We can not use '-y' here.
        cros_build_lib.run(
            cmd + [basename] + pattern_options, cwd=dirname, capture_output=True
        )

    # Everything in /usr/local/factory/bundle gets overlaid into the
    # bundle.
    bundle_src_dir = os.path.join(
        path_util.FromChrootPath(
            FACTORY_PACKAGE_CHROOT_PATH % {"board": board},
            source_path=buildroot,
        ),
        "bundle",
    )
    if os.path.exists(bundle_src_dir):
        cros_build_lib.run(
            cmd + ["-y", "."], cwd=bundle_src_dir, capture_output=True
        )

    # Add a version file in the zip file.
    if version is not None:
        version_filename = "BUILD_VERSION"
        # Creates a staging temporary folder.
        with osutils.TempDir(prefix="cbuildbot_factory") as temp_dir:
            version_file = os.path.join(temp_dir, version_filename)
            osutils.WriteFile(version_file, version)
            cros_build_lib.run(
                cmd + [version_filename], cwd=temp_dir, capture_output=True
            )

    return filename


def GeneratePayloads(
    buildroot,
    target_image_path,
    archive_dir,
    full=False,
    delta=False,
    stateful=False,
    dlc=False,
):
    """Generates the payloads for hw testing.

    Args:
        buildroot: Path to the build root directory.
        target_image_path: The path to the image to generate payloads to.
        archive_dir: Where to store payloads we generated.
        full: Generate full payloads.
        delta: Generate delta payloads.
        stateful: Generate stateful payload.
        dlc: Generate sample-dlc payloads.
    """
    artifacts_service.GenerateTestPayloads(
        chroot_lib.Chroot(
            path=os.path.join(buildroot, "chroot"),
            out_path=buildroot / constants.DEFAULT_OUT_DIR,
        ),
        target_image_path,
        archive_dir,
        full=full,
        delta=delta,
        stateful=stateful,
        dlc=dlc,
    )
    artifacts_service.GenerateQuickProvisionPayloads(
        target_image_path, archive_dir
    )


def SyncChrome(
    build_root,
    chrome_root,
    useflags,
    tag=None,
    revision=None,
    git_cache_dir=None,
    workspace=None,
):
    """Sync chrome.

    Args:
        build_root: The root of the chromium os checkout.
        chrome_root: The directory where chrome is stored.
        useflags: Array of use flags.
        tag: If supplied, the Chrome tag to sync.
        revision: If supplied, the Chrome revision to sync.
        git_cache_dir: Directory to use for git-cache.
        workspace: Alternative buildroot directory to sync.
    """
    sync_chrome = os.path.join(build_root, "chromite", "bin", "sync_chrome")
    internal = constants.USE_CHROME_INTERNAL in useflags
    # --reset tells sync_chrome to blow away local changes and to feel
    # free to delete any directories that get in the way of syncing. This
    # is needed for unattended operation.
    cmd = [sync_chrome, "--reset"]
    if internal:
        cmd += ["--internal"]
    if tag:
        cmd += ["--tag", tag]
    if revision:
        cmd += ["--revision", revision]
    if git_cache_dir:
        cmd += ["--git_cache_dir", git_cache_dir]
    cmd += [chrome_root]
    retry_util.RunCommandWithRetries(
        constants.SYNC_RETRIES, cmd, cwd=workspace or build_root
    )


class ChromeSDK:
    """Wrapper for the 'cros chrome-sdk' command."""

    DEFAULT_GOMA_JOBS = "80"

    def __init__(
        self,
        cwd,
        board,
        extra_args=None,
        chrome_src=None,
        goma=False,
        debug_log=True,
        cache_dir=None,
        target_tc=None,
        toolchain_url=None,
    ):
        """Initialization.

        Args:
            cwd: Where to invoke 'cros chrome-sdk'.
            board: The board to run chrome-sdk for.
            extra_args: Extra args to pass in on the command line.
            chrome_src: Path to pass in with --chrome-src.
            goma: If True, run using goma.
            debug_log: If set, run with debug log-level.
            cache_dir: Specify non-default cache directory.
            target_tc: Override target toolchain.
            toolchain_url: Override toolchain url pattern.
        """
        self.cwd = cwd
        self.board = board
        self.extra_args = extra_args or []
        if chrome_src:
            self.extra_args += ["--chrome-src", chrome_src]
        self.goma = goma
        if not self.goma:
            self.extra_args.append("--nogoma")
        self.debug_log = debug_log
        self.cache_dir = cache_dir
        self.target_tc = target_tc
        self.toolchain_url = toolchain_url

    def Run(self, cmd, extra_args=None, run_args=None):
        """Run a command inside the chrome-sdk context.

        Args:
            cmd: Command (list) to run inside 'cros chrome-sdk'.
            extra_args: Extra arguments for 'cros chorme-sdk'.
            run_args: If set (dict), pass to run as kwargs.

        Returns:
            A CompletedProcess object.
        """
        if run_args is None:
            run_args = {}
        cros_cmd = ["cros"]
        if self.debug_log:
            cros_cmd += ["--log-level", "debug"]
        if self.cache_dir:
            cros_cmd += ["--cache-dir", self.cache_dir]
        if self.target_tc:
            self.extra_args += ["--target-tc", self.target_tc]
        if self.toolchain_url:
            self.extra_args += ["--toolchain-url", self.toolchain_url]
        cros_cmd += ["chrome-sdk", "--board", self.board] + self.extra_args
        cros_cmd += (extra_args or []) + ["--"] + cmd
        return cros_build_lib.run(cros_cmd, cwd=self.cwd, **run_args)

    def Ninja(self, debug=False, run_args=None):
        """Run 'ninja' inside a chrome-sdk context.

        Args:
            debug: Whether to do a Debug build (defaults to Release).
            run_args: If set (dict), pass to run as kwargs.

        Returns:
            A CompletedProcess object.
        """
        return self.Run(self.GetNinjaCommand(debug=debug), run_args=run_args)

    def GetNinjaCommand(self, debug=False):
        """Returns a command line to run "ninja".

        Args:
            debug: Whether to do a Debug build (defaults to Release).

        Returns:
            Command line to run "ninja".
        """
        cmd = ["autoninja"]
        if self.goma:
            cmd += ["-j", self.DEFAULT_GOMA_JOBS]
        cmd += [
            "-C",
            self._GetOutDirectory(debug=debug),
            "chromiumos_preflight",
        ]
        return cmd

    def VMTest(self, image_path, debug=False):
        """Run cros_run_test in a VM.

        Only run tests for boards where we build a VM.

        Args:
            image_path: VM image path.
            debug: True if this is a debug build.

        Returns:
            A CompletedProcess object.
        """
        return self.Run(
            [
                "cros_run_test",
                "--copy-on-write",
                "--deploy",
                "--board=%s" % self.board,
                "--image-path=%s" % image_path,
                "--build-dir=%s" % self._GetOutDirectory(debug=debug),
            ]
        )

    def _GetOutDirectory(self, debug=False):
        """Returns the path to the output directory.

        Args:
            debug: Whether to do a Debug build (defaults to Release).

        Returns:
            Path to the output directory.
        """
        flavor = "Debug" if debug else "Release"
        return "out_%s/%s" % (self.board, flavor)

    def GetNinjaLogPath(self, debug=False):
        """Returns the path to the .ninja_log file.

        Args:
            debug: Whether to do a Debug build (defaults to Release).

        Returns:
            Path to the .ninja_log file.
        """
        return os.path.join(self._GetOutDirectory(debug=debug), ".ninja_log")


class ApiMismatchError(Exception):
    """Raised by GetTargetChromiteApiVersion."""


class NoChromiteError(Exception):
    """Raised when an expected chromite installation was missing."""


def GetTargetChromiteApiVersion(buildroot, validate_version=True):
    """Get the re-exec API version of the target chromite.

    Args:
        buildroot: The directory containing the chromite to check.
        validate_version: If set to true, checks the target chromite for
            compatibility, and raises an ApiMismatchError when there is an
            incompatibility.

    Returns:
        The version number in (major, minor) tuple.

    Raises:
        May raise an ApiMismatchError if validate_version is set.
    """
    try:
        api = cros_build_lib.run(
            [constants.PATH_TO_CBUILDBOT, "--reexec-api-version"],
            cwd=buildroot,
            check=False,
            encoding="utf-8",
            capture_output=True,
        )
    except cros_build_lib.RunCommandError:
        # Although check=False was used, this exception will still be raised
        # if the executible did not exist.
        full_cbuildbot_path = os.path.join(
            buildroot, constants.PATH_TO_CBUILDBOT
        )
        if not os.path.exists(full_cbuildbot_path):
            raise NoChromiteError(
                "No cbuildbot found in buildroot %s, expected to find %s. "
                % (buildroot, full_cbuildbot_path)
            )
        raise

    # If the command failed, then we're targeting a cbuildbot that lacks the
    # option; assume 0:0 (ie, initial state).
    major = minor = 0
    if api.returncode == 0:
        major, minor = (int(x) for x in api.stdout.strip().split(".", 1))

    if validate_version and major != constants.REEXEC_API_MAJOR:
        raise ApiMismatchError(
            "The targeted version of chromite in buildroot %s requires "
            "api version %i, but we are api version %i.  We cannot proceed."
            % (buildroot, major, constants.REEXEC_API_MAJOR)
        )

    return major, minor


def GetBuildrootVersionInfo(build_root: str) -> chromeos_version.VersionInfo:
    """Fetch the ChromeOS version info for a checkout.

    Only valid after the build_root has been synced.

    Args:
        build_root: Absolute path to the root of the checkout in question.

    Returns:
        VersionInfo object based on the checkout at build_root.
    """
    return chromeos_version.VersionInfo.from_repo(build_root)


def IsBuildRootAfterLimit(build_root: str, limit: str) -> bool:
    """Check whether the build_root version is newer than the given version.

    Only valid after the build_root has been synced.

    Args:
        build_root: Absolute path to the root of the checkout in question.
        limit: String version of the format '123.0.0'.

    Returns:
        True if the build_root has a newer version than `limit`.
    """
    version_info = GetBuildrootVersionInfo(build_root)
    return version_info > chromeos_version.VersionInfo(limit)
