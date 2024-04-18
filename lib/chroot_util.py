# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for updating and building in the chroot environment."""

import logging
import os

from chromite.third_party.opentelemetry import trace

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_sdk_lib
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.lib import sysroot_lib


tracer = trace.get_tracer(__name__)


if cros_build_lib.IsInsideChroot():
    # These import libraries outside chromite. See brbug.com/472.
    from chromite.scripts import cros_list_modified_packages as workon
    from chromite.scripts import cros_setup_toolchains as toolchain


_HOST_PKGS = (
    "virtual/target-sdk",
    "world",
)

_DEFAULT_MAKE_CONF_USER = """
# This file is useful for doing global (chroot and all board) changes.
# Tweak emerge settings, ebuild env, etc...
#
# Make sure to append variables unless you really want to clobber all
# existing settings.  e.g. You most likely want:
#   FEATURES="${FEATURES} ..."
#   USE="${USE} foo"
# and *not*:
#   USE="foo"
#
# This also is a good place to setup ACCEPT_LICENSE.
"""


def _GetToolchainPackages():
    """Get a list of host toolchain packages."""
    # Load crossdev cache first for faster performance.
    toolchain.Crossdev.Load(False)
    packages = toolchain.GetTargetPackages("host")
    return [toolchain.GetPortagePackage("host", x) for x in packages]


def GetEmergeCommand(sysroot=None):
    """Returns the emerge command to use for |sysroot| (host if None)."""
    cmd = [constants.CHROMITE_BIN_DIR / "parallel_emerge"]
    if sysroot and sysroot != "/":
        cmd += ["--sysroot=%s" % sysroot]
    return cmd


@tracer.start_as_current_span("chroot_util.Emerge")
def Emerge(
    packages,
    sysroot,
    with_deps=True,
    rebuild_deps=True,
    use_binary=True,
    jobs=None,
    debug_output=False,
):
    """Emerge the specified |packages|.

    Args:
        packages: List of packages to emerge.
        sysroot: Path to the sysroot in which to emerge.
        with_deps: Whether to include dependencies.
        rebuild_deps: Whether to rebuild dependencies.
        use_binary: Whether to use binary packages.
        jobs: Number of jobs to run in parallel.
        debug_output: Emit debug level output.

    Raises:
        cros_build_lib.RunCommandError: If emerge returns an error.
    """
    cros_build_lib.AssertInsideChroot()

    span = trace.get_current_span()
    span.set_attributes(
        {
            "sysroot": sysroot,
            "packages": packages,
            "with_deps": with_deps,
            "rebuild_deps": rebuild_deps,
            "use_binary": use_binary,
            "jobs": jobs,
        }
    )

    if not packages:
        raise ValueError("No packages provided")

    cmd = GetEmergeCommand(sysroot)
    cmd.append("-uNv")

    modified_packages = workon.ListModifiedWorkonPackages(
        sysroot_lib.Sysroot(sysroot)
    )
    if modified_packages is not None:
        mod_pkg_list = " ".join(modified_packages)
        cmd += [
            "--reinstall-atoms=" + mod_pkg_list,
            "--usepkg-exclude=" + mod_pkg_list,
        ]

    cmd.append("--deep" if with_deps else "--nodeps")
    if use_binary:
        cmd += ["-g", "--with-bdeps=y"]
        if sysroot == "/":
            # Only update toolchains in the chroot when binpkgs are available.
            # The toolchain rollout process only takes place when the chromiumos
            # sdk builder finishes a successful build and pushes out binpkgs.
            cmd += ["--useoldpkg-atoms=%s" % " ".join(_GetToolchainPackages())]

    if rebuild_deps:
        cmd.append("--rebuild-if-unbuilt")
    if jobs:
        cmd.append("--jobs=%d" % jobs)
    if debug_output:
        cmd.append("--show-output")

    # We might build chrome, in which case we need to pass 'CHROME_ORIGIN'.
    cros_build_lib.sudo_run(cmd + packages, preserve_env=True)


def UpdateChroot(board=None, update_host_packages=True):
    """Update the chroot."""
    # Run chroot update hooks.
    logging.notice("Updating the chroot. This may take several minutes.")
    cros_sdk_lib.RunChrootVersionHooks()

    # Update toolchains.
    cmd = [constants.CHROMITE_BIN_DIR / "cros_setup_toolchains"]
    if board:
        cmd += ["--targets=boards", "--include-boards=%s" % board]
    cros_build_lib.sudo_run(cmd, debug_level=logging.DEBUG)

    # Update the host before updating the board.
    if update_host_packages:
        Emerge(list(_HOST_PKGS), "/", rebuild_deps=False)

    # Automatically discard all CONFIG_PROTECT'ed files. Those that are
    # protected should not be overwritten until the variable is changed.
    # Autodiscard is option "-9" followed by the "YES" confirmation.
    cros_build_lib.sudo_run(
        ["etc-update"], input="-9\nYES\n", debug_level=logging.DEBUG
    )


@tracer.start_as_current_span("chroot_util.RunUnittests")
def RunUnittests(
    sysroot,
    packages,
    extra_env=None,
    keep_going=False,
    verbose=False,
    retries=None,
    jobs=None,
):
    """Runs the unit tests for |packages|.

    Args:
        sysroot: Path to the sysroot to build the tests in.
        packages: List of packages to test.
        extra_env: Python dictionary containing the extra environment variable
            to pass to the build command.
        keep_going: Tolerate package failure from parallel_emerge.
        verbose: If True, show the output from emerge, even when the tests
            succeed.
        retries: Number of time we should retry a failed packages. If None, use
            parallel_emerge's default.
        jobs: Max number of parallel jobs. (optional)

    Raises:
        RunCommandError if the unit tests failed.
    """
    span = trace.get_current_span()
    span.set_attributes(
        {
            "sysroot": sysroot,
            "packages": packages,
            "keep_going": keep_going,
            "retries": retries,
            "jobs": jobs,
        }
    )

    env = extra_env.copy() if extra_env else {}

    if "FEATURES" in env:
        env["FEATURES"] += " test"
    else:
        env["FEATURES"] = "test"

    env["PKGDIR"] = os.path.join(sysroot, constants.UNITTEST_PKG_PATH)

    command = [
        constants.CHROMITE_BIN_DIR / "parallel_emerge",
        "--sysroot=%s" % sysroot,
    ]

    if keep_going:
        command += ["--keep-going=y"]

    if verbose:
        command += ["--show-output"]
        command += ["--verbose"]

    if retries is not None:
        command += ["--retries=%s" % retries]

    if jobs is not None:
        command += ["--jobs=%s" % jobs]

    command += list(packages)

    cros_build_lib.sudo_run(command, extra_env=env)


def CreateMakeConfUser():
    """Create default make.conf.user file in the chroot if it does not exist."""
    path = "/etc/make.conf.user"
    if not cros_build_lib.IsInsideChroot():
        path = path_util.FromChrootPath(path)

    if not os.path.exists(path):
        osutils.WriteFile(path, _DEFAULT_MAKE_CONF_USER, sudo=True)
