# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for managing the toolchains in the chroot."""

import logging
import os
from pathlib import Path
import subprocess
from typing import List, Optional, TYPE_CHECKING, Union

from chromite.lib import build_target_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import toolchain_list
from chromite.utils import gs_urls_util
from chromite.utils import key_value_store


if TYPE_CHECKING:
    from chromite.lib.parser import package_info

if cros_build_lib.IsInsideChroot():
    # Only import portage after we've checked that we're inside the chroot.
    # Outside may not have portage, in which case the above may not happen.
    # We'll check in main() if the operation needs portage.
    # pylint: disable=import-error
    import portage


class Error(Exception):
    """Base exception class for this module."""


class UnknownToolchainError(Error):
    """Missing a required package."""


class ToolchainInstallError(Error, cros_build_lib.RunCommandError):
    """An error when installing a toolchain."""

    def __init__(
        self,
        msg: str,
        result: cros_build_lib.CompletedProcess,
        exception: Optional[Exception] = None,
        tc_info: Optional[List["package_info.PackageInfo"]] = None,
    ):
        """ToolchainInstallError init.

        Args:
            msg: Error message.
            result: The command result.
            exception: The original exception.
            tc_info: A list of the failed packages' package_info.PackageInfo.
        """
        super().__init__(msg, result, exception)
        self.failed_toolchain_info = tc_info


def GetHostTuple():
    """Returns compiler tuple for the host system."""
    return portage.settings["CHOST"]


# Tree interface functions. They help with retrieving data about the current
# state of the tree:
def GetAllTargets():
    """Get the complete list of targets.

    Returns:
        The list of cross targets for the current tree
    """
    overlays = portage_util.FindOverlays(constants.BOTH_OVERLAYS)
    toolchains = toolchain_list.ToolchainList(overlays=overlays)
    targets = toolchains.GetMergedToolchainSettings()

    # Remove the host target as that is not a cross-target. Replace with 'host'.
    del targets[GetHostTuple()]
    return targets


def get_toolchains_for_build_target(
    build_target: build_target_lib.BuildTarget,
    source_root=constants.SOURCE_ROOT,
):
    """Get a dictionary mapping toolchain targets to their options for a board.

    Args:
        build_target: BuildTarget of interest.
        source_root: If provided, use an alternative SOURCE_ROOT (useful for
            testing).

    Returns:
        The list of toolchain tuples for the given board
    """
    overlays = build_target.find_overlays(source_root=source_root)
    toolchains = toolchain_list.ToolchainList(overlays=overlays)
    targets = toolchains.GetMergedToolchainSettings()
    if build_target.is_host():
        targets = FilterToolchains(targets, "sdk", True)
    return targets


def GetToolchainTupleForBoard(board, buildroot=constants.SOURCE_ROOT):
    """Gets a tuple for the default and non-default toolchains for a board.

    Args:
        board: board name in question (e.g. 'daisy').
        buildroot: path to buildroot.

    Returns:
        The tuples of toolchain targets ordered default, non-default for the
        board.
    """
    # TODO: This function should take a BuildTarget instead of a raw board name.
    build_target = build_target_lib.BuildTarget(board)
    toolchains = get_toolchains_for_build_target(
        build_target, source_root=buildroot
    )
    return list(FilterToolchains(toolchains, "default", True)) + list(
        FilterToolchains(toolchains, "default", False)
    )


def FilterToolchains(targets, key, value):
    """Filter out targets based on their attributes.

    Args:
        targets: dict of toolchains
        key: metadata to examine
        value: expected value for metadata

    Returns:
        dict where all targets whose metadata |key| does not match |value|
        have been deleted
    """
    return dict((k, v) for k, v in targets.items() if v[key] == value)


def GetSdkURL(for_gsutil=False, suburl=""):
    """Construct a Google Storage URL for accessing SDK related archives

    Args:
        for_gsutil: Do you want a URL for passing to `gsutil`?
        suburl: A url fragment to tack onto the end

    Returns:
        The fully constructed URL
    """
    return gs_urls_util.GetGsURL(
        constants.SDK_GS_BUCKET, for_gsutil=for_gsutil, suburl=suburl
    )


def GetArchForTarget(target):
    """Returns the arch used by the given toolchain.

    Args:
        target: a toolchain.
    """
    ret = cros_build_lib.dbg_run(
        ["crossdev", "--show-target-cfg", target],
        capture_output=True,
        encoding="utf-8",
    )
    return key_value_store.LoadData(ret.stdout).get("arch")


def InstallToolchain(sysroot, toolchain=None, force=False, configure=True):
    """Simplified entry point for the toolchain installation process."""
    if not cros_build_lib.IsInsideChroot():
        # Build the command to run inside the chroot instead.
        cmd = [
            constants.CHROMITE_BIN_DIR / "install_toolchain",
            "--sysroot",
            sysroot.path,
        ]
        if toolchain:
            cmd.append("--toolchain")
            cmd.append(toolchain)
        if force:
            cmd.append("--force")
        if not configure:
            cmd.append("--noconfigure")
        cros_build_lib.run(cmd, enter_chroot=True)
    else:
        envvars = portage_util.PortageqEnvvars(["CHOST", "PKGDIR"])
        installer = ToolchainInstaller(
            force, configure, envvars["CHOST"], envvars["PKGDIR"]
        )
        installer.Install(sysroot, board_chost=toolchain)


class ToolchainInstaller:
    """Sysroot toolchain installer.

    This class installs the toolchain into the given sysroots.
    """

    def __init__(self, force: bool, configure: bool, cbuild: str, pkgdir: str):
        """ToolchainInstaller configuration.

        |force| and |configure| alter the installer's behavior (details below).
        |chost| and |pkgdir| are values fetched from the chroot that determine
        which packages to install and how to fetch them.

        See:
            https://wiki.gentoo.org/wiki/CHOST

        Args:
            force: Whether to force the installation if already up to date.
            configure: Whether to write out the config files in the sysroot
                when complete.
            cbuild: The CHOST value of the chroot SDK itself.
            pkgdir: The PKGDIR value of the chroot; the path at which package
                archives are stored.
        """
        self.force = force
        self.configure = configure
        self.cbuild = cbuild
        self.pkgdir = pkgdir

    def Install(self, sysroot, board_chost=None):
        """Toolchain installation process.

        Install most recent glibc version in the sysroot.
        If the configure option passed to __init__ is True; the gcc and go
        packages are listed in the sysroot's package.provided, and the glibc
        version is stored in sysroot's LIBC_VERSION cached field. Otherwise, all
        are left untouched.

        Note: Must be run inside the chroot. Not currently asserted because
        InstallToolchain is the preferred entry point.

        Args:
            sysroot: sysroot_lib.Sysroot - Must be a valid sysroot,
                e.g. use setup_board to initialize one.
            board_chost: str|None - The CHOST value to use for the board. If not
                explicitly provided as an argument, must be set in the sysroot's
                CHOST standard field.
        """
        # Determine the toolchain we'll be installing; e.g. i686-pc-linux-gnu,
        # armv7a-softfloat-linux-gnueabi.
        # Run `qlist -Iv cross-` inside the chroot for more examples.
        chost = board_chost or sysroot.GetStandardField("CHOST")
        if not chost:
            raise ValueError(
                "Toolchain not provided or specified in the sysroot."
            )

        tc_info = ToolchainInfo(chost, self.cbuild)

        if not self._NeedsInstalled(sysroot, tc_info):
            # Up to date and not forced; nothing to do.
            logging.info("Cross-compiler already up to date. Nothing to do.")
            return

        # Verify we can install the required packages.
        if not tc_info.gcc_version or not tc_info.libc_version:
            raise UnknownToolchainError(
                "Cannot find toolchain to install into board " "root."
            )

        logging.info("Installing toolchain to the board root: %s", sysroot.path)
        self._InstallLibc(sysroot, tc_info)

        self._WriteConfigs(sysroot, tc_info)
        self._UpdateProvided(sysroot, tc_info)

    def _InstallLibc(
        self, sysroot: "sysroot_lib.Sysroot", tc_info: "ToolchainInfo"
    ):
        """Install the libc package to the sysroot.

        Args:
            sysroot: The sysroot where it's being installed.
            tc_info: The toolchain being installed.
        """
        if not tc_info.IsCrossCompiler():
            # Host and target toolchains match, install standard packages.
            cmd = [
                "emerge",
                "--oneshot",
                "--nodeps",
                "-k",
                "--root",
                sysroot.path,
                "=%s" % tc_info.libc_cpf,
            ]
            try:
                cros_build_lib.sudo_run(cmd)
            except cros_build_lib.RunCommandError as e:
                raise ToolchainInstallError(
                    str(e),
                    e.result,
                    exception=e,
                    tc_info=[tc_info.libc_pkg_info],
                )
        else:
            # They do not match, install appropriate cross-toolchain variant
            # package. See ToolchainInfo for alternate package name build outs.
            libc_path = os.path.join(self.pkgdir, "%s.tbz2" % tc_info.libc_cpf)

            if not os.path.exists(libc_path):
                # Install libc in chroot if it hasn't already been installed.
                cmd = ["emerge", "--nodeps", "-gf", "=%s" % tc_info.libc_cpf]
                cros_build_lib.sudo_run(cmd)

            try:
                self._ExtractLibc(sysroot, tc_info.target, libc_path)
            except ToolchainInstallError as e:
                e.failed_toolchain_info = [tc_info.libc_pkg_info]
                raise e

    def _ExtractLibc(
        self, sysroot: "sysroot_lib.Sysroot", board_chost: str, libc_path: str
    ):
        """Extract the libc archive to the sysroot.

        Args:
            sysroot: The sysroot where it's being installed.
            board_chost: The board's CHOST value.
            libc_path: The location of the libc archive.
        """
        compression = cros_build_lib.CompressionDetectType(libc_path)
        compressor = cros_build_lib.FindCompressor(compression)
        compressor_algo = Path(compressor).name
        if compressor_algo == "pbzip2":
            compressor = "%s --ignore-trailing-garbage=1" % compressor
        elif compressor_algo.startswith("zstd"):
            compressor += " -f"

        with osutils.TempDir(sudo_rm=True) as tempdir:
            # Extract to the temporary directory.
            cmd = ["tar", "-I", compressor, "-xpf", libc_path, "-C", tempdir]
            result = cros_build_lib.sudo_run(
                cmd,
                check=False,
                stdout=True,
                stderr=subprocess.STDOUT,
            )
            if result.returncode:
                logging.error("failed to extract libc:\n%s", result.stdout)
                raise ToolchainInstallError(
                    f"Error extracting libc: {result.stdout}", result
                )

            # Sync the files to the sysroot to install. Trailing / on source to
            # sync contents instead of the directory itself.
            source = os.path.join(tempdir, "usr", board_chost)
            cmd = [
                "rsync",
                "--archive",
                "--hard-links",
                f"{source}/",
                f"{sysroot.path}/",
            ]
            result = cros_build_lib.sudo_run(
                cmd,
                check=False,
                stdout=True,
                stderr=subprocess.STDOUT,
            )
            if result.returncode:
                logging.error("failed to install libc:\n%s", result.stdout)
                raise ToolchainInstallError(
                    f"Error installing libc: {result.stdout}", result
                )

            # Make the debug directory.
            debug_dir = os.path.join(sysroot.path, "usr/lib/debug")
            osutils.SafeMakedirs(debug_dir, sudo=True)
            # Sync the debug files to the debug directory.
            source = os.path.join(tempdir, "usr/lib/debug/usr", board_chost)
            cmd = [
                "rsync",
                "--archive",
                "--hard-links",
                f"{source}/",
                f"{debug_dir}/",
            ]
            result = cros_build_lib.sudo_run(
                cmd,
                check=False,
                stdout=True,
                stderr=subprocess.STDOUT,
            )
            if result.returncode:
                logging.error(
                    "failed to copy lib debug info:\n%s", result.stdout
                )
                raise ToolchainInstallError(
                    f"Error copying libc debug info: {result.stdout}", result
                )

    def _NeedsInstalled(self, sysroot, tc_info):
        """Check if the toolchain installation needs to be run."""
        return self.force or not tc_info.LibcVersionsMatch(sysroot)

    def _WriteConfigs(self, sysroot, tc_info):
        """Write out config updates."""
        if self.configure:
            sysroot.SetCachedField("LIBC_VERSION", tc_info.libc_version)
            sysroot.SetCachedField("LIBCXX_VERSION", tc_info.libcxx_version)
            sysroot.SetCachedField("LIBGCC_VERSION", tc_info.libgcc_version)

    def _UpdateProvided(self, sysroot, tc_info):
        """Write the package.provided file."""
        if self.configure:
            content = "\n".join(tc_info.sdk_cpfs)
            pkg_provided = os.path.join(
                sysroot.path, "etc/portage/profile/package.provided"
            )
            osutils.WriteFile(pkg_provided, content, makedirs=True, sudo=True)


class ToolchainInfo:
    """Class to manage some of the toolchain related information."""

    # Package reference names.
    _PKG_GCC = "gcc"
    _PKG_LIBC = "glibc"
    _PKG_LIBCXX = "libcxx"
    _PKG_LIBGCC = "llvm-libunwind"
    _PKG_LIBXCRYPT = "libxcrypt"
    _PKG_GO = "go"
    _PKG_RPCSVC = "rpcsvc"

    # Standard group/package names.
    _PACKAGES = {
        _PKG_GCC: "sys-devel/gcc",
        _PKG_LIBC: "sys-libs/glibc",
        _PKG_LIBCXX: "sys-libs/libcxx",
        _PKG_LIBGCC: "sys-libs/llvm-libunwind",
        _PKG_LIBXCRYPT: "sys-libs/libxcrypt",
        _PKG_GO: "dev-lang/go",
        _PKG_RPCSVC: "net-libs/rpcsvc-proto",
    }

    def __init__(self, target: str, cbuild: str):
        """ToolchainInfo init.

        Args:
            target: The target cross-compiler tuple, i.e. the board's CHOST.
            cbuild: The CHOST value of the chroot SDK itself.
        """
        self.target = target
        self.cbuild = cbuild
        self._pkgs = {}

    @property
    def libc_version(self) -> str:
        return self._GetVersion(self._PKG_LIBC)

    @property
    def libc_cpf(self) -> str:
        return self._GetCPF(self._PKG_LIBC)

    @property
    def libc_pkg_info(self) -> "package_info.PackageInfo":
        return self._get_pkg(self._PKG_LIBC)

    @property
    def libcxx_version(self) -> str:
        return self._GetVersion(self._PKG_LIBCXX)

    @property
    def libcxx_cpf(self) -> str:
        return self._GetCPF(self._PKG_LIBCXX)

    @property
    def libcxx_pkg_info(self) -> "package_info.PackageInfo":
        return self._get_pkg(self._PKG_LIBCXX)

    @property
    def libgcc_version(self) -> str:
        return self._GetVersion(self._PKG_LIBGCC)

    @property
    def libgcc_cpf(self) -> str:
        return self._GetCPF(self._PKG_LIBGCC)

    @property
    def libgcc_pkg_info(self) -> "package_info.PackageInfo":
        return self._get_pkg(self._PKG_LIBGCC)

    @property
    def gcc_version(self) -> str:
        return self._GetVersion(self._PKG_GCC)

    @property
    def gcc_cpf(self) -> str:
        return self._GetCPF(self._PKG_GCC)

    @property
    def go_version(self):
        return self._GetVersion(self._PKG_GO)

    @property
    def go_cpf(self):
        return self._GetCPF(self._PKG_GO)

    @property
    def rpcsvc_proto_version(self):
        return self._GetVersion(self._PKG_RPCSVC)

    @property
    def rpcsvc_proto_cpf(self):
        return self._GetCPF(self._PKG_RPCSVC)

    @property
    def sdk_cpfs(self):
        """Get the standard CPFs, i.e. the host, not necessarily the target."""
        cpfs = [
            "%s-%s" % (self._PACKAGES[self._PKG_GCC], self.gcc_version),
            "%s-%s" % (self._PACKAGES[self._PKG_LIBC], self.libc_version),
        ]
        if self.go_version:
            cpfs.append(
                "%s-%s" % (self._PACKAGES[self._PKG_GO], self.go_version)
            )

        if self.rpcsvc_proto_version:
            cpfs.append(
                "%s-%s"
                % (self._PACKAGES[self._PKG_RPCSVC], self.rpcsvc_proto_version)
            )

        return cpfs

    def _get_pkg(self, pkg: str) -> Union["package_info.PackageInfo", None]:
        """Return PackageInfo object for the package."""
        if pkg not in self._pkgs:
            self._pkgs[pkg] = portage_util.PortageqMatch(self._GetCP(pkg))

        return self._pkgs[pkg]

    def _GetVersion(self, pkg):
        """Get version for the package."""
        return getattr(self._get_pkg(pkg), "vr", None)

    def _GetCP(self, pkg):
        """Returns the appropriate 'category/package' for the toolchain."""
        return (
            self._PACKAGES[pkg]
            if not self.IsCrossCompiler()
            else "cross-%(t)s/%(pkg)s" % {"t": self.target, "pkg": pkg}
        )

    def _GetCPF(self, pkg):
        """Get the full 'category/package-version-revision'."""
        return getattr(self._get_pkg(pkg), "cpvr", None)

    def LibcVersionsMatch(self, sysroot: "sysroot_lib.Sysroot"):
        """Check if the two libc package versions match.

        Args:
            sysroot: The sysroot whose libc version is checked.

        Returns:
            bool - True iff same version installed in sdk and sysroot.
        """
        board_version = sysroot.GetCachedField("LIBC_VERSION")
        toolchain_version = self.libc_version

        return board_version == toolchain_version and (
            board_version or toolchain_version
        )

    def IsCrossCompiler(self):
        """Whether the sdk and board chost values match."""
        return self.cbuild != self.target
