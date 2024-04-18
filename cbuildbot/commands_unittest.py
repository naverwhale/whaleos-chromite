# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for commands."""

import base64
import hashlib
import json
import os
import struct
from unittest import mock

from chromite.cbuildbot import commands
from chromite.lib import build_target_lib
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import failures_lib
from chromite.lib import osutils
from chromite.lib import partial_mock
from chromite.lib import path_util
from chromite.lib import portage_util
from chromite.lib import sysroot_lib
from chromite.lib.parser import package_info
from chromite.scripts import pushimage
from chromite.service import artifacts as artifacts_service


class RunBuildScriptTest(cros_test_lib.RunCommandTempDirTestCase):
    """Test RunBuildScript in a variety of cases."""

    def _assertRunBuildScript(
        self, in_chroot=False, error=None, raises=None, **kwargs
    ):
        """Test the RunBuildScript function.

        Args:
            in_chroot: Whether to enter the chroot or not.
            error: error result message to simulate.
            raises: If the command should fail, the exception to be raised.
            **kwargs: Extra kwargs passed to RunBuildScript.
        """

        # Write specified error message to status file.
        def WriteError(_cmd, extra_env=None, **_kwargs):
            if extra_env is not None and error is not None:
                status_file = extra_env[
                    constants.PARALLEL_EMERGE_STATUS_FILE_ENVVAR
                ]
                osutils.WriteFile(status_file, error)

        buildroot = self.tempdir
        osutils.SafeMakedirs(os.path.join(buildroot, ".repo"))
        if error is not None:
            osutils.SafeMakedirs(os.path.join(buildroot, "chroot", "tmp"))

        # Run the command, throwing an exception if it fails.
        cmd = ["example", "command"]
        sudo_cmd = ["sudo", "--"] + cmd
        returncode = 1 if raises else 0
        self.rc.AddCmdResult(cmd, returncode=returncode, side_effect=WriteError)
        self.rc.AddCmdResult(
            sudo_cmd, returncode=returncode, side_effect=WriteError
        )

        self.PatchObject(
            path_util, "ToChrootPath", side_effect=lambda x, **kwargs: x
        )

        with cros_test_lib.LoggingCapturer():
            # If the script failed, the exception should be raised and printed.
            if raises:
                self.assertRaises(
                    raises,
                    commands.RunBuildScript,
                    buildroot,
                    cmd,
                    enter_chroot=in_chroot,
                    **kwargs,
                )
            else:
                commands.RunBuildScript(
                    buildroot, cmd, enter_chroot=in_chroot, **kwargs
                )

    def testSuccessOutsideChroot(self):
        """Test executing a command outside the chroot."""
        self._assertRunBuildScript()

    def testSuccessInsideChrootWithoutTempdir(self):
        """Test executing a command inside a chroot without a tmp dir."""
        self._assertRunBuildScript(in_chroot=True)

    def testSuccessInsideChrootWithTempdir(self):
        """Test executing a command inside a chroot with a tmp dir."""
        self._assertRunBuildScript(in_chroot=True, error="")

    def testFailureOutsideChroot(self):
        """Test a command failure outside the chroot."""
        self._assertRunBuildScript(raises=failures_lib.BuildScriptFailure)

    def testFailureInsideChrootWithoutTempdir(self):
        """Test a command failure inside the chroot without a temp directory."""
        self._assertRunBuildScript(
            in_chroot=True, raises=failures_lib.BuildScriptFailure
        )

    def testFailureInsideChrootWithTempdir(self):
        """Test a command failure inside the chroot with a temp directory."""
        self._assertRunBuildScript(
            in_chroot=True, error="", raises=failures_lib.BuildScriptFailure
        )

    def testPackageBuildFailure(self):
        """Test detecting a package build failure."""
        self._assertRunBuildScript(
            in_chroot=True,
            error=constants.CHROME_CP,
            raises=failures_lib.PackageBuildFailure,
        )

    def testSuccessWithSudo(self):
        """Test a command run with sudo."""
        self._assertRunBuildScript(in_chroot=False, sudo=True)
        self._assertRunBuildScript(in_chroot=True, sudo=True)


class ChromeSDKTest(cros_test_lib.RunCommandTempDirTestCase):
    """Basic tests for ChromeSDK commands with run mocked out."""

    BOARD = "daisy_foo"
    EXTRA_ARGS = ("--monkey", "banana")
    EXTRA_ARGS2 = ("--donkey", "kong")
    CHROME_SRC = "chrome_src"
    CMD = ["bar", "baz"]
    CWD = "fooey"

    def setUp(self):
        self.inst = commands.ChromeSDK(self.CWD, self.BOARD)

    def testRunCommand(self):
        """Test that running a command is possible."""
        self.inst.Run(self.CMD)
        self.assertCommandContains([self.BOARD] + self.CMD, cwd=self.CWD)

    def testRunCommandWithRunArgs(self):
        """Test run_args optional argument for run kwargs."""
        self.inst.Run(self.CMD, run_args={"log_output": True})
        self.assertCommandContains(
            [self.BOARD] + self.CMD, cwd=self.CWD, log_output=True
        )

    def testRunCommandKwargs(self):
        """Exercise optional arguments."""
        custom_inst = commands.ChromeSDK(
            self.CWD,
            self.BOARD,
            extra_args=list(self.EXTRA_ARGS),
            chrome_src=self.CHROME_SRC,
            debug_log=True,
        )
        custom_inst.Run(self.CMD, list(self.EXTRA_ARGS2))
        self.assertCommandContains(
            ["debug", self.BOARD]
            + list(self.EXTRA_ARGS)
            + list(self.EXTRA_ARGS2)
            + self.CMD,
            cwd=self.CWD,
        )

    def MockGetDefaultTarget(self):
        self.rc.AddCmdResult(
            partial_mock.In("qlist-%s" % self.BOARD),
            stdout="%s" % constants.CHROME_CP,
        )

    def testNinjaWithRunArgs(self):
        """Test that running ninja with run_args.

        run_args is an optional argument for run kwargs.
        """
        self.MockGetDefaultTarget()
        self.inst.Ninja(run_args={"log_output": True})
        self.assertCommandContains(
            [
                "autoninja",
                "-C",
                "out_%s/Release" % self.BOARD,
                "chromiumos_preflight",
            ],
            cwd=self.CWD,
            log_output=True,
        )

    def testNinjaOptions(self):
        """Test that running ninja with non-default options."""
        self.MockGetDefaultTarget()
        custom_inst = commands.ChromeSDK(self.CWD, self.BOARD, goma=True)
        custom_inst.Ninja(debug=True)
        self.assertCommandContains(
            [
                "autoninja",
                "-j",
                "80",
                "-C",
                "out_%s/Debug" % self.BOARD,
                "chromiumos_preflight",
            ]
        )


class CBuildBotTest(cros_test_lib.RunCommandTempDirTestCase):
    """Test general cbuildbot command methods."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        self._board = "test-board"
        self._buildroot = self.tempdir
        self._path_resolver = path_util.ChrootPathResolver(
            source_path=self._buildroot
        )
        os.makedirs(os.path.join(self._buildroot, ".repo"))

        self._dropfile = os.path.join(
            self._buildroot, "src", "scripts", "cbuildbot_package.list"
        )

        self.target_image = os.path.join(
            self.tempdir,
            "link/R37-5952.0.2014_06_12_2302-a1/chromiumos_test_image.bin",
        )

    def testUprevPackagesMin(self):
        """See if we can generate minimal cros_mark_as_stable commandline."""
        commands.UprevPackages(
            self._buildroot, [self._board], constants.PUBLIC_OVERLAYS
        )
        self.assertCommandContains(
            [
                "commit",
                "--all",
                "--boards=%s" % self._board,
                "--drop_file=%s" % self._dropfile,
                "--buildroot",
                self._buildroot,
                "--overlay-type",
                "public",
            ]
        )

    def testUprevPackagesMax(self):
        """See if we can generate the max cros_mark_as_stable commandline."""
        commands.UprevPackages(
            self._buildroot,
            [self._board],
            overlay_type=constants.PUBLIC_OVERLAYS,
            workspace="/workspace",
        )
        self.assertCommandContains(
            [
                "commit",
                "--all",
                "--boards=%s" % self._board,
                "--drop_file=%s" % self._dropfile,
                "--buildroot",
                "/workspace",
                "--overlay-type",
                "public",
            ]
        )

    def testUprevPushMin(self):
        """See if we can generate minimal cros_mark_as_stable commandline."""
        commands.UprevPush(
            self._buildroot, overlay_type=constants.PUBLIC_OVERLAYS
        )
        self.assertCommandContains(
            [
                "push",
                "--buildroot",
                self._buildroot,
                "--overlay-type",
                "public",
                "--dryrun",
            ]
        )

    def testUprevPushMax(self):
        """See if we can generate the max cros_mark_as_stable commandline."""
        commands.UprevPush(
            self._buildroot,
            dryrun=False,
            overlay_type=constants.PUBLIC_OVERLAYS,
            workspace="/workspace",
        )
        self.assertCommandContains(
            [
                "push",
                "--buildroot",
                "/workspace",
                "--overlay-type",
                "public",
            ]
        )

    def testVerifyBinpkgMissing(self):
        """Test case where binpkg is missing."""
        self.rc.AddCmdResult(
            partial_mock.ListRegex(r"emerge"),
            stdout="\n[ebuild] %s" % constants.CHROME_CP,
        )
        self.assertRaises(
            commands.MissingBinpkg,
            commands.VerifyBinpkg,
            self._buildroot,
            self._board,
            constants.CHROME_CP,
            packages=(),
        )

    def testVerifyBinpkgPresent(self):
        """Test case where binpkg is present."""
        self.rc.AddCmdResult(
            partial_mock.ListRegex(r"emerge"),
            stdout="\n[binary] %s" % constants.CHROME_CP,
        )
        commands.VerifyBinpkg(
            self._buildroot, self._board, constants.CHROME_CP, packages=()
        )

    def testVerifyChromeNotInstalled(self):
        """Test case where Chrome is not installed at all."""
        commands.VerifyBinpkg(
            self._buildroot, self._board, constants.CHROME_CP, packages=()
        )

    def testBuild(self, default=False, **kwargs):
        """Base case where Build is called with minimal options."""
        kwargs.setdefault("build_autotest", default)
        kwargs.setdefault("usepkg", default)
        kwargs.setdefault("skip_chroot_upgrade", default)

        commands.Build(
            buildroot=self._buildroot, board="amd64-generic", **kwargs
        )
        self.assertCommandContains(
            [
                self._path_resolver.ToChroot(
                    self._buildroot
                    / constants.CHROMITE_BIN_SUBDIR
                    / "build_packages"
                )
            ]
        )

    def testBuildLegacy(self, default=False, **kwargs):
        """Base case where legacy Build is called with minimal options."""
        kwargs.setdefault("build_autotest", default)
        kwargs.setdefault("usepkg", default)
        kwargs.setdefault("skip_chroot_upgrade", default)

        commands.LegacyBuild(
            buildroot=self._buildroot, board="amd64-generic", **kwargs
        )
        self.assertCommandContains(["./build_packages"])

    def testGetFirmwareVersions(self):
        # pylint: disable=line-too-long
        self.rc.SetDefaultCmdResult(
            stdout="""

flashrom(8): a8f99c2e61e7dc09c4b25ef5a76ef692 */build/kevin/usr/sbin/flashrom
             ELF 32-bit LSB executable, ARM, EABI5 version 1 (SYSV), statically linked, for GNU/Linux 2.d
             0.9.4  : 860875a : Apr 10 2017 23:54:29 UTC

BIOS image:   6b5b855a0b8fd1657546d1402c15b206 *chromeos-firmware-kevin-0.0.1/.dist/kevin_fw_8785.178.0.n
BIOS version: Google_Kevin.8785.178.0
EC image:     1ebfa9518e6cac0558a80b7ab2f5b489 *chromeos-firmware-kevin-0.0.1/.dist/kevin_ec_8785.178.0.n
EC version:kevin_v1.10.184-459421c

Package Content:
a8f99c2e61e7dc09c4b25ef5a76ef692 *./flashrom
3c3a99346d1ca1273cbcd86c104851ff *./shflags
457a8dc8546764affc9700f8da328d23 *./dump_fmap
c392980ddb542639edf44a965a59361a *./updater5.sh
490c95d6123c208d20d84d7c16857c7c *./crosfw.sh
6b5b855a0b8fd1657546d1402c15b206 *./bios.bin
7b5bef0d2da90c23ff2e157250edf0fa *./crosutil.sh
d78722e4f1a0dc2d8c3d6b0bc7010ae3 *./crossystem
457a8dc8546764affc9700f8da328d23 *./gbb_utility
1ebfa9518e6cac0558a80b7ab2f5b489 *./ec.bin
c98ca54db130886142ad582a58e90ddc *./common.sh
5ba978bdec0f696f47f0f0de90936880 *./mosys
312e8ee6122057f2a246d7bcf1572f49 *./vpd
"""
        )
        build_sbin = self._path_resolver.FromChroot(
            os.path.join(
                os.path.sep,
                "build",
                self._board,
                "usr",
                "sbin",
            )
        )
        osutils.Touch(
            os.path.join(build_sbin, "chromeos-firmwareupdate"), makedirs=True
        )
        result = commands.GetFirmwareVersions(self._buildroot, self._board)
        versions = commands.FirmwareVersions(
            None,
            "Google_Kevin.8785.178.0",
            None,
            "kevin_v1.10.184-459421c",
            None,
        )
        self.assertEqual(result, versions)

    def testGetFirmwareVersionsMixedImage(self):
        """Test that can extract the right version from a mixed RO+RW bundle."""
        # pylint: disable=line-too-long
        self.rc.SetDefaultCmdResult(
            stdout="""

flashrom(8): 29c9ec509aaa9c1f575cca883d90980c */build/caroline/usr/sbin/flashrom
             ELF 64-bit LSB executable, x86-64, version 1 (SYSV), statically linked, for GNU/Linux 2.6.32, BuildID[sha1]=eb6af9bb9e14e380676ad9607760c54addec4a3a, stripped
             0.9.4  : 1bb61e1 : Feb 07 2017 18:29:17 UTC

BIOS image:   9f78f612c24ee7ec4ca4d2747b01d8b9 *chromeos-firmware-caroline-0.0.1/.dist/Caroline.7820.263.0.tbz2/image.bin
BIOS version: Google_Caroline.7820.263.0
BIOS (RW) image:   2cb5021b986fe024f20d242e1885e1e7 *chromeos-firmware-caroline-0.0.1/.dist/Caroline.7820.286.0.tbz2/image.bin
BIOS (RW) version: Google_Caroline.7820.286.0
EC image:     18569de94ea66ba0cad360c3b7d8e205 *chromeos-firmware-caroline-0.0.1/.dist/Caroline_EC.7820.263.0.tbz2/ec.bin
EC version:   caroline_v1.9.357-ac5c7b4
EC (RW) version:   caroline_v1.9.370-e8b9bd2
PD image:     0ba8d6a0fa82c42fa42a98096e2b1480 *chromeos-firmware-caroline-0.0.1/.dist/Caroline_PD.7820.263.0.tbz2/ec.bin
PD version:   caroline_pd_v1.9.357-ac5c7b4
PD (RW) version:   caroline_pd_v1.9.370-e8b9bd2
Extra files from folder: /mnt/host/source/src/private-overlays/overlay-caroline-private/chromeos-base/chromeos-firmware-caroline/files/extra
Extra file: /build/caroline//bin/xxd

Package Content:
dc9b08c5b17a7d51f9acdf5d3e12ebb7 *./updater4.sh
29c9ec509aaa9c1f575cca883d90980c *./flashrom
3c3a99346d1ca1273cbcd86c104851ff *./shflags
d962372228f82700d179d53a509f9735 *./dump_fmap
490c95d6123c208d20d84d7c16857c7c *./crosfw.sh
deb421e949ffaa23102ef3cee640be2d *./bios.bin
b0ca480cb2981b346f493ebc93a52e8a *./crosutil.sh
fba6434300d36f7b013883b6a3d04b57 *./pd.bin
03496184aef3ec6d5954528a5f15d8af *./crossystem
d962372228f82700d179d53a509f9735 *./gbb_utility
6ddd288ce20e28b90ef0b21613637b60 *./ec.bin
7ca17c9b563383296ee9e2c353fdb766 *./updater_custom.sh
c2728ed24809ec845c53398a15255f49 *./xxd
c98ca54db130886142ad582a58e90ddc *./common.sh
a3326e34e8c9f221cc2dcd2489284e30 *./mosys
ae8cf9fca3165a1c1f12decfd910c4fe *./vpd
"""
        )
        build_sbin = self._path_resolver.FromChroot(
            os.path.join(
                os.path.sep,
                "build",
                self._board,
                "usr",
                "sbin",
            )
        )
        osutils.Touch(
            os.path.join(build_sbin, "chromeos-firmwareupdate"), makedirs=True
        )
        result = commands.GetFirmwareVersions(self._buildroot, self._board)
        versions = commands.FirmwareVersions(
            None,
            "Google_Caroline.7820.263.0",
            "Google_Caroline.7820.286.0",
            "caroline_v1.9.357-ac5c7b4",
            "caroline_v1.9.370-e8b9bd2",
        )
        self.assertEqual(result, versions)

    def testGetAllFirmwareVersions(self):
        """Verify that all model firmware versions can be extracted"""
        # pylint: disable=line-too-long
        self.rc.SetDefaultCmdResult(
            stdout="""

flashrom(8): 68935ee2fcfcffa47af81b966269cd2b */build/reef/usr/sbin/flashrom
             ELF 64-bit LSB executable, x86-64, version 1 (SYSV), statically linked, for GNU/Linux 2.6.32, BuildID[sha1]=e102cc98d45300b50088999d53775acbeff407dc, stripped
             0.9.9  : bbb2d6a : Jul 28 2017 15:12:34 UTC

Model:        reef
BIOS image:   1b535280fe688ac284d95276492b06f6 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/reef/image.bin
BIOS version: Google_Reef.9042.87.1
BIOS (RW) image:   0ef265eb8f2d228c09f75b011adbdcbb */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/reef/image.binrw
BIOS (RW) version: Google_Reef.9042.110.0
EC image:     2e8b4b5fa73cc5dbca4496de97a917a9 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/reef/ec.bin
EC version:   reef_v1.1.5900-ab1ee51
EC (RW) version: reef_v1.1.5909-bd1f0c9

Model:        pyro
BIOS image:   9e62447ebf22a724a4a835018ab6234e */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/pyro/image.bin
BIOS version: Google_Pyro.9042.87.1
BIOS (RW) image:   1897457303c85de99f3e98b2eaa0eccc */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/pyro/image.binrw
BIOS (RW) version: Google_Pyro.9042.110.0
EC image:     44b93ed591733519e752e05aa0529eb5 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/pyro/ec.bin
EC version:   pyro_v1.1.5900-ab1ee51
EC (RW) version: pyro_v1.1.5909-bd1f0c9

Model:        snappy
BIOS image:   3ab63ff080596bd7de4e7619f003bb64 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/snappy/image.bin
BIOS version: Google_Snappy.9042.110.0
EC image:     c4db159e84428391d2ee25368c5fe5b6 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/snappy/ec.bin
EC version:   snappy_v1.1.5909-bd1f0c9

Model:        sand
BIOS image:   387da034a4f0a3f53e278ebfdcc2a412 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/sand/image.bin
BIOS version: Google_Sand.9042.110.0
EC image:     411562e0589dacec131f5fdfbe95a561 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/sand/ec.bin
EC version:   sand_v1.1.5909-bd1f0c9

Model:        electro
BIOS image:   1b535280fe688ac284d95276492b06f6 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/reef/image.bin
BIOS version: Google_Reef.9042.87.1
BIOS (RW) image:   0ef265eb8f2d228c09f75b011adbdcbb */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/reef/image.binrw
BIOS (RW) version: Google_Reef.9042.110.0
EC image:     2e8b4b5fa73cc5dbca4496de97a917a9 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/reef/ec.bin
EC version:   reef_v1.1.5900-ab1ee51
EC (RW) version: reef_v1.1.5909-bd1f0c9

Package Content:
612e7bb6ed1fb0a05abf2ebdc834c18b *./updater4.sh
0eafbee07282315829d0f42135ec7c0c *./gbb_utility
6074e3ca424cb30a67c378c1d9681f9c *./mosys
68935ee2fcfcffa47af81b966269cd2b *./flashrom
0eafbee07282315829d0f42135ec7c0c *./dump_fmap
490c95d6123c208d20d84d7c16857c7c *./crosfw.sh
60899148600b8673ddb711faa55aee40 *./common.sh
3c3a99346d1ca1273cbcd86c104851ff *./shflags
de7ce035e1f82a89f8909d888ee402c0 *./crosutil.sh
f9334372bdb9036ba09a6fd9bf30e7a2 *./crossystem
22257a8d5f0adc1f50a1916c3a4a35dd *./models/reef/ec.bin
faf12dbb7cdaf21ce153bdffb67841fd *./models/reef/bios.bin
c9bbb417b7921b85a7ed999ee42f550e *./models/reef/setvars.sh
29823d46f1ec1491ecacd7b830fd2686 *./models/pyro/ec.bin
2320463aba8b22eb5ea836f094d281b3 *./models/pyro/bios.bin
81614833ad77c9cd093360ba7bea76b8 *./models/pyro/setvars.sh
411562e0589dacec131f5fdfbe95a561 *./models/sand/ec.bin
387da034a4f0a3f53e278ebfdcc2a412 *./models/sand/bios.bin
fcd8cb0ac0e2ed6be220aaae435d43ff *./models/sand/setvars.sh
c4db159e84428391d2ee25368c5fe5b6 *./models/snappy/ec.bin
3ab63ff080596bd7de4e7619f003bb64 *./models/snappy/bios.bin
fe5d699f2e9e4a7de031497953313dbd *./models/snappy/setvars.sh
79aabd7cd8a215a54234c53d7bb2e6fb *./vpd
"""
        )
        build_sbin = self._path_resolver.FromChroot(
            os.path.join(
                os.path.sep,
                "build",
                self._board,
                "usr",
                "sbin",
            )
        )
        osutils.Touch(
            os.path.join(build_sbin, "chromeos-firmwareupdate"), makedirs=True
        )
        result = commands.GetAllFirmwareVersions(self._buildroot, self._board)
        self.assertEqual(len(result), 5)
        self.assertEqual(
            result["reef"],
            commands.FirmwareVersions(
                "reef",
                "Google_Reef.9042.87.1",
                "Google_Reef.9042.110.0",
                "reef_v1.1.5900-ab1ee51",
                "reef_v1.1.5909-bd1f0c9",
            ),
        )
        self.assertEqual(
            result["pyro"],
            commands.FirmwareVersions(
                "pyro",
                "Google_Pyro.9042.87.1",
                "Google_Pyro.9042.110.0",
                "pyro_v1.1.5900-ab1ee51",
                "pyro_v1.1.5909-bd1f0c9",
            ),
        )
        self.assertEqual(
            result["snappy"],
            commands.FirmwareVersions(
                "snappy",
                "Google_Snappy.9042.110.0",
                None,
                "snappy_v1.1.5909-bd1f0c9",
                None,
            ),
        )
        self.assertEqual(
            result["sand"],
            commands.FirmwareVersions(
                "sand",
                "Google_Sand.9042.110.0",
                None,
                "sand_v1.1.5909-bd1f0c9",
                None,
            ),
        )
        self.assertEqual(
            result["electro"],
            commands.FirmwareVersions(
                "electro",
                "Google_Reef.9042.87.1",
                "Google_Reef.9042.110.0",
                "reef_v1.1.5900-ab1ee51",
                "reef_v1.1.5909-bd1f0c9",
            ),
        )

    def testGetModels(self):
        self.rc.SetDefaultCmdResult(stdout="pyro\nreef\nsnappy\n")
        build_bin = os.path.join(
            self._buildroot, constants.DEFAULT_CHROOT_DIR, "usr", "bin"
        )
        osutils.Touch(
            os.path.join(build_bin, "cros_config_host"), makedirs=True
        )
        result = commands.GetModels(self._buildroot, self._board)
        self.assertEqual(result, ["pyro", "reef", "snappy"])

    def testBuildMaximum(self):
        """Base case: Build is called with all options (except extra_env)."""
        self.testBuild(default=True)

    def testBuildWithEnv(self):
        """Case where Build is called with a custom environment."""
        extra_env = {"A": "Av", "B": "Bv"}
        self.testBuild(extra_env=extra_env)
        self.assertCommandContains(
            [
                self._path_resolver.ToChroot(
                    self._buildroot
                    / constants.CHROMITE_BIN_SUBDIR
                    / "build_packages"
                )
            ],
            extra_env=extra_env,
        )

    def testGenerateBreakpadSymbols(self):
        """Test GenerateBreakpadSymbols Command."""
        commands.GenerateBreakpadSymbols(self.tempdir, self._board, False)
        self.assertCommandContains(["--board=%s" % self._board])

    def testGenerateAndroidBreakpadSymbols(self):
        """Test GenerateAndroidBreakpadSymbols Command."""
        with mock.patch.object(
            path_util, "ToChrootPath", side_effect=lambda s, **kwargs: s
        ):
            commands.GenerateAndroidBreakpadSymbols(
                "/buildroot", "MyBoard", "symbols.zip"
            )
        self.assertCommandContains(
            [
                (
                    "/buildroot/chromite/bin/"
                    "cros_generate_android_breakpad_symbols"
                ),
                "--symbols_file=symbols.zip",
                "--breakpad_dir=/build/MyBoard/usr/lib/debug/breakpad",
            ]
        )

    def testUploadSymbolsMinimal(self):
        """Test uploading symbols for official builds"""
        commands.UploadSymbols("/buildroot", "MyBoard")
        self.assertCommandContains(
            [
                "/buildroot/chromite/bin/upload_symbols",
                "--yes",
                "--root",
                "/buildroot/chroot",
                "--board",
                "MyBoard",
            ]
        )

    def testUploadSymbolsMinimalNoneChromeOS(self):
        """Test uploading symbols for official builds"""
        commands.UploadSymbols(
            "/buildroot", breakpad_root="/breakpad", product_name="CoolProduct"
        )
        self.assertCommandContains(
            [
                "/buildroot/chromite/bin/upload_symbols",
                "--yes",
                "--breakpad_root",
                "/breakpad",
                "--product_name",
                "CoolProduct",
            ]
        )

    def testUploadSymbolsMaximal(self):
        """Test uploading symbols for official builds"""
        commands.UploadSymbols(
            "/buildroot",
            "MyBoard",
            official=True,
            cnt=55,
            failed_list="/failed_list.txt",
            breakpad_root="/breakpad",
            product_name="CoolProduct",
        )
        self.assertCommandContains(
            [
                "/buildroot/chromite/bin/upload_symbols",
                "--yes",
                "--root",
                "/buildroot/chroot",
                "--board",
                "MyBoard",
                "--official_build",
                "--upload-limit",
                "55",
                "--failed-list",
                "/failed_list.txt",
                "--breakpad_root",
                "/breakpad",
                "--product_name",
                "CoolProduct",
            ]
        )

    def testPushImages(self):
        """Test PushImages Command."""
        m = self.PatchObject(pushimage, "PushImage")
        commands.PushImages(self._board, "gs://foo/R34-1234.0.0", False, None)
        self.assertEqual(m.call_count, 1)

    def testBuildImage(self):
        """Test Basic BuildImage Command."""
        commands.BuildImage(self._buildroot, self._board, None)
        self.assertCommandContains(["./build_image"])

    def testCompleteBuildImage(self):
        """Test Complete BuildImage Command."""
        images_to_build = ["bob", "carol", "ted", "alice"]
        commands.BuildImage(
            self._buildroot,
            self._board,
            images_to_build,
            rootfs_verification=False,
            extra_env={"LOVE": "free"},
            version="1969",
        )
        self.assertCommandContains(["./build_image"])


class GenerateDebugTarballTests(cros_test_lib.MockTempDirTestCase):
    """Tests related to building tarball artifacts."""

    def tearDown(self):
        if cros_build_lib.IsOutsideChroot():
            board_path = os.path.join(os.path.sep, "build", self._board)
            cros_build_lib.sudo_run(
                ["rm", "-rf", board_path], enter_chroot=True
            )

    def setUp(self):
        self._board = "test-board"
        self._buildroot = os.path.join(self.tempdir, "buildroot")
        self._sysroot = self.tempdir / "build" / self._board
        self._debug_base = os.path.join(self._sysroot, "usr", "lib")

        self._files = [
            "debug/s1",
            "debug/breakpad/b1",
            "debug/tests/t1",
            "debug/stuff/nested/deep",
            "debug/usr/local/build/autotest/a1",
        ]

        self._tarball_dir = self.tempdir

        self.PatchObject(
            build_target_lib,
            "get_default_sysroot_path",
            return_value=self._sysroot,
        )
        if cros_build_lib.IsInsideChroot():
            cros_test_lib.CreateOnDiskHierarchy(self._debug_base, self._files)

    def testGenerateDebugTarballGdb(self):
        """Test the simplest case."""

        # It's non-trivially difficult to make this unit test actually work
        # outside the chroot and the Cbuildbot code will go away in early 2023Q4
        # so just don't try to test if we're outside the chroot.
        if not cros_build_lib.IsInsideChroot():
            return

        commands.GenerateDebugTarball(
            self._buildroot, self._board, self._tarball_dir, gdb_symbols=True
        )

        cros_test_lib.VerifyTarball(
            os.path.join(self._tarball_dir, "debug.tgz"),
            [
                "debug/",
                "debug/s1",
                "debug/breakpad/",
                "debug/breakpad/b1",
                "debug/stuff/",
                "debug/stuff/nested/",
                "debug/stuff/nested/deep",
                "debug/usr/",
                "debug/usr/local/",
                "debug/usr/local/build/",
            ],
        )

    def testGenerateDebugTarballNoGdb(self):
        """Test the simplest case."""

        # It's non-trivially difficult to make this unit test actually work
        # outside the chroot and the Cbuildbot code will go away in early 2023Q4
        # so just don't try to test if we're outside the chroot.
        if not cros_build_lib.IsInsideChroot():
            return

        commands.GenerateDebugTarball(
            self._buildroot, self._board, self._tarball_dir, gdb_symbols=False
        )

        cros_test_lib.VerifyTarball(
            os.path.join(self._tarball_dir, "debug.tgz"),
            [
                "debug/breakpad/",
                "debug/breakpad/b1",
            ],
        )


class BuildTarballTests(cros_test_lib.RunCommandTempDirTestCase):
    """Tests related to building tarball artifacts."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        self._buildroot = os.path.join(self.tempdir, "buildroot")
        self._path_resolver = path_util.ChrootPathResolver(
            source_path=self._buildroot
        )
        os.makedirs(self._buildroot)
        self._board = "test-board"
        self._cwd = os.path.abspath(
            self._path_resolver.FromChroot(
                os.path.join(
                    "/build",
                    self._board,
                    constants.AUTOTEST_BUILD_PATH,
                    "..",
                )
            )
        )
        self._sysroot_build = self._path_resolver.FromChroot(
            os.path.join("/build", self._board, "build")
        )
        self._tarball_dir = self.tempdir

    def testBuildAutotestPackagesTarball(self):
        """Tests that generating the autotest packages tarball is correct."""
        with mock.patch.object(commands, "BuildTarball") as m:
            commands.BuildAutotestPackagesTarball(
                self._buildroot, self._cwd, self._tarball_dir
            )
            m.assert_called_once_with(
                self._buildroot,
                ["autotest/packages"],
                os.path.join(self._tarball_dir, "autotest_packages.tar"),
                cwd=self._cwd,
                compressed=False,
            )

    def testBuildAutotestControlFilesTarball(self):
        """Tests generating the autotest control files tarball is correct."""
        control_file_list = [
            "autotest/client/site_tests/testA/control",
            "autotest/server/site_tests/testB/control",
        ]
        with mock.patch.object(commands, "FindFilesWithPattern") as find_mock:
            find_mock.return_value = control_file_list
            with mock.patch.object(commands, "BuildTarball") as tar_mock:
                commands.BuildAutotestControlFilesTarball(
                    self._buildroot, self._cwd, self._tarball_dir
                )
                tar_mock.assert_called_once_with(
                    self._buildroot,
                    control_file_list,
                    os.path.join(self._tarball_dir, "control_files.tar"),
                    cwd=self._cwd,
                    compressed=False,
                )

    def testBuildAutotestServerPackageTarball(self):
        """Tests generating the autotest server package tarball is correct."""
        control_file_list = [
            "autotest/server/site_tests/testA/control",
            "autotest/server/site_tests/testB/control",
        ]
        # Pass a copy of the file list so the code under test can't mutate it.
        self.PatchObject(
            commands,
            "FindFilesWithPattern",
            return_value=list(control_file_list),
        )
        tar_mock = self.PatchObject(commands, "BuildTarball")

        expected_files = list(control_file_list)

        # Touch Tast paths so they'll be included in the tar command. Skip
        # creating the last file so we can verify that it's omitted from the tar
        # command.
        for p in commands.TAST_SSP_CHROOT_FILES[:-1]:
            path = path_util.FromChrootPath(
                p,
                source_path=self._buildroot,
            )
            if not os.path.exists(os.path.dirname(path)):
                os.makedirs(os.path.dirname(path))
            # TODO(b/236161656): Fix.
            # pylint: disable-next=consider-using-with
            open(path, "ab").close()
            expected_files.append(path)

        commands.BuildAutotestServerPackageTarball(
            self._buildroot, self._cwd, self._tarball_dir
        )

        tar_mock.assert_called_once_with(
            self._buildroot,
            expected_files,
            os.path.join(self._tarball_dir, commands.AUTOTEST_SERVER_PACKAGE),
            cwd=self._cwd,
            extra_args=mock.ANY,
            check=False,
        )

    def testBuildTastTarball(self):
        """Tests that generating the Tast private bundles tarball is correct."""
        expected_tarball = os.path.join(
            self._tarball_dir, "tast_bundles.tar.bz2"
        )

        for d in ("libexec/tast", "share/tast"):
            os.makedirs(os.path.join(self._cwd, d))

        chroot = chroot_lib.Chroot(
            os.path.join(self._buildroot, "chroot"),
            out_path=self._buildroot / constants.DEFAULT_OUT_DIR,
        )
        sysroot = sysroot_lib.Sysroot(os.path.join("/build", self._board))
        patch = self.PatchObject(
            artifacts_service, "BundleTastFiles", return_value=expected_tarball
        )

        tarball = commands.BuildTastBundleTarball(
            self._buildroot, self._sysroot_build, self._tarball_dir
        )
        self.assertEqual(expected_tarball, tarball)
        patch.assert_called_once_with(chroot, sysroot, self._tarball_dir)

    def testBuildTastTarballNoBundle(self):
        """Tests the case when Tast private bundles tarball is not generated."""
        self.PatchObject(
            artifacts_service, "BundleTastFiles", return_value=None
        )
        tarball = commands.BuildTastBundleTarball(
            self._buildroot, self._sysroot_build, self._tarball_dir
        )
        self.assertIsNone(tarball)

    def testBuildStrippedPackagesArchive(self):
        """Test generation of stripped package tarball using globs."""
        package_globs = ["chromeos-base/chromeos-chrome", "sys-kernel/*kernel*"]
        self.PatchObject(
            portage_util,
            "FindPackageNameMatches",
            side_effect=[
                [package_info.SplitCPV("chromeos-base/chrome-1-r0")],
                [
                    package_info.SplitCPV("sys-kernel/kernel-1-r0"),
                    package_info.SplitCPV("sys-kernel/kernel-2-r0"),
                ],
            ],
        )
        # Drop "stripped packages".
        sysroot = self._path_resolver.FromChroot(
            os.path.join("/build", "test-board")
        )
        pkg_dir = os.path.join(sysroot, "stripped-packages")
        osutils.Touch(
            os.path.join(pkg_dir, "chromeos-base", "chrome-1-r0.tbz2"),
            makedirs=True,
        )
        sys_kernel = os.path.join(pkg_dir, "sys-kernel")
        osutils.Touch(
            os.path.join(sys_kernel, "kernel-1-r0.tbz2"), makedirs=True
        )
        osutils.Touch(
            os.path.join(sys_kernel, "kernel-1-r01.tbz2"), makedirs=True
        )
        osutils.Touch(
            os.path.join(sys_kernel, "kernel-2-r0.tbz1"), makedirs=True
        )
        osutils.Touch(
            os.path.join(sys_kernel, "kernel-2-r0.tbz2"), makedirs=True
        )
        stripped_files_list = [
            os.path.join(
                "stripped-packages", "chromeos-base", "chrome-1-r0.tbz2"
            ),
            os.path.join("stripped-packages", "sys-kernel", "kernel-1-r0.tbz2"),
            os.path.join("stripped-packages", "sys-kernel", "kernel-2-r0.tbz2"),
        ]

        tar_mock = self.PatchObject(commands, "BuildTarball")
        commands.BuildStrippedPackagesTarball(
            self._buildroot, "test-board", package_globs, self.tempdir
        )
        tar_mock.assert_called_once_with(
            self._buildroot,
            stripped_files_list,
            os.path.join(self.tempdir, "stripped-packages.tar"),
            cwd=sysroot,
            compressed=False,
        )


class UnmockedTests(cros_test_lib.MockTempDirTestCase):
    """Test cases which really run tests, instead of using mocks.

    ...except that we mock IsInsideChroot, for consistent behavior and to test
    the real flow, where chromite code runs outside the SDK.
    """

    _TEST_BOARD = "board"

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

    def testBuildFirmwareArchive(self):
        """Verifies the archiver creates a tarfile with the expected files."""
        # Set of files to tar up
        fw_files = (
            "dts/emeraldlake2.dts",
            "image-link.rw.bin",
            "nv_image-link.bin",
            "pci8086,0166.rom",
            "seabios.cbfs",
            "u-boot.elf",
            "u-boot_netboot.bin",
            "updater-link.rw.sh",
            "x86-memtest",
        )
        board = "link"
        fw_test_root = os.path.join(self.tempdir, os.path.basename(__file__))
        fw_files_root = path_util.FromChrootPath(
            "/build/%s/firmware" % board,
            source_path=fw_test_root,
        )

        # Generate the fw_files in fw_files_root.
        cros_test_lib.CreateOnDiskHierarchy(fw_files_root, fw_files)

        # Create an archive from the specified test directory.
        returned_archive_name = commands.BuildFirmwareArchive(
            fw_test_root, board, fw_test_root
        )
        # Verify we get a valid tarball returned whose name uses the default
        # name.
        self.assertTrue(returned_archive_name is not None)
        self.assertEqual(returned_archive_name, constants.FIRMWARE_ARCHIVE_NAME)

        # Create an archive and specify that archive filename.
        archive_name = "alternative_archive.tar.bz2"
        returned_archive_name = commands.BuildFirmwareArchive(
            fw_test_root, board, fw_test_root, archive_name
        )
        # Verify that we get back an archive file using the specified name.
        self.assertEqual(archive_name, returned_archive_name)

    def testBuildFpmcuUnittestsArchive(self):
        """Verifies that a tarball with the right name is created."""
        unittest_files = (
            "bloonchipper/test_rsa.bin",
            "dartmonkey/test_utils.bin",
        )
        unittest_files_root = path_util.FromChrootPath(
            f"/build/{self._TEST_BOARD}/firmware/chromeos-fpmcu-unittests",
            source_path=self.tempdir,
        )
        cros_test_lib.CreateOnDiskHierarchy(unittest_files_root, unittest_files)

        returned_archive_name = commands.BuildFpmcuUnittestsArchive(
            self.tempdir, self._TEST_BOARD, self.tempdir
        )
        self.assertEqual(
            returned_archive_name,
            os.path.join(self.tempdir, constants.FPMCU_UNITTESTS_ARCHIVE_NAME),
        )

    def findFilesWithPatternExpectedResults(self, root, files):
        """Generate the expected results for testFindFilesWithPattern"""
        return [os.path.join(root, f) for f in files]

    def testFindFilesWithPattern(self):
        """Verifies FindFilesWithPattern searches and excludes files properly"""
        search_files = (
            "file1",
            "test1",
            "file2",
            "dir1/file1",
            "dir1/test1",
            "dir2/file2",
        )
        search_files_root = os.path.join(
            self.tempdir, "FindFilesWithPatternTest"
        )
        cros_test_lib.CreateOnDiskHierarchy(search_files_root, search_files)
        find_all = commands.FindFilesWithPattern("*", target=search_files_root)
        expected_find_all = self.findFilesWithPatternExpectedResults(
            search_files_root, search_files
        )
        self.assertEqual(set(find_all), set(expected_find_all))
        find_test_files = commands.FindFilesWithPattern(
            "test*", target=search_files_root
        )
        find_test_expected = self.findFilesWithPatternExpectedResults(
            search_files_root, ["test1", "dir1/test1"]
        )
        self.assertEqual(set(find_test_files), set(find_test_expected))
        find_exclude = commands.FindFilesWithPattern(
            "*",
            target=search_files_root,
            exclude_dirs=(os.path.join(search_files_root, "dir1"),),
        )
        find_exclude_expected = self.findFilesWithPatternExpectedResults(
            search_files_root, ["file1", "test1", "file2", "dir2/file2"]
        )
        self.assertEqual(set(find_exclude), set(find_exclude_expected))

    def testGenerateUploadJSON(self):
        """Verifies GenerateUploadJSON"""
        archive = os.path.join(self.tempdir, "archive")
        osutils.SafeMakedirs(archive)

        # Text file.
        text_str = "Happiness equals reality minus expectations.\n"
        osutils.WriteFile(os.path.join(archive, "file1.txt"), text_str)

        # JSON file.
        json_str = json.dumps(
            [
                {
                    "Salt": "Pepper",
                    "Pots": "Pans",
                    "Cloak": "Dagger",
                    "Shoes": "Socks",
                }
            ]
        )
        osutils.WriteFile(os.path.join(archive, "file2.json"), json_str)

        # Binary file.
        bin_blob = struct.pack("6B", 228, 39, 123, 87, 2, 168)
        with open(os.path.join(archive, "file3.bin"), "wb") as f:
            f.write(bin_blob)

        # Directory.
        osutils.SafeMakedirs(os.path.join(archive, "dir"))

        # List of files in archive.
        uploaded = os.path.join(self.tempdir, "uploaded")
        osutils.WriteFile(uploaded, "file1.txt\nfile2.json\nfile3.bin\ndir\n")

        upload_file = os.path.join(self.tempdir, "upload.json")
        commands.GenerateUploadJSON(upload_file, archive, uploaded)
        parsed = json.loads(osutils.ReadFile(upload_file))

        # Directory should be ignored.
        test_content = {
            "file1.txt": text_str.encode("utf-8"),
            "file2.json": json_str.encode("utf-8"),
            "file3.bin": bin_blob,
        }

        self.assertEqual(set(parsed.keys()), set(test_content.keys()))

        # Verify the math.
        for filename, content in test_content.items():
            entry = parsed[filename]
            size = len(content)
            sha1 = base64.b64encode(hashlib.sha1(content).digest()).decode(
                "utf-8"
            )
            sha256 = base64.b64encode(hashlib.sha256(content).digest()).decode(
                "utf-8"
            )

            self.assertEqual(entry["size"], size)
            self.assertEqual(entry["sha1"], sha1)
            self.assertEqual(entry["sha256"], sha256)

    def testGenerateHtmlIndexTuple(self):
        """Verifies GenerateHtmlIndex gives us something sane (input: tuple)"""
        index = os.path.join(self.tempdir, "index.html")
        files = (
            "file1",
            "monkey tree",
            "flying phone",
        )
        commands.GenerateHtmlIndex(index, files)
        html = osutils.ReadFile(index)
        for f in files:
            self.assertIn(">%s</a>" % f, html)

    def testGenerateHtmlIndexTupleDupe(self):
        """Verifies GenerateHtmlIndex gives something unique (input: tuple)"""
        index = os.path.join(self.tempdir, "index.html")
        files = (
            "file1",
            "file1",
            "file1",
        )
        commands.GenerateHtmlIndex(index, files)
        html = osutils.ReadFile(index)
        self.assertEqual(html.count(">file1</a>"), 1)

    def testGenerateHtmlIndexTuplePretty(self):
        """Verifies GenerateHtmlIndex gives something pretty (input: tuple)"""
        index = os.path.join(self.tempdir, "index.html")
        files = (
            "..|up",
            "f.txt|MY FILE",
            "m.log|MONKEY",
            "b.bin|Yander",
        )
        commands.GenerateHtmlIndex(index, files)
        html = osutils.ReadFile(index)
        for f in files:
            a = f.split("|")
            self.assertIn('href="%s"' % a[0], html)
            self.assertIn(">%s</a>" % a[1], html)

    def testGenerateHtmlIndexDir(self):
        """Verifies GenerateHtmlIndex gives us something sane (input: dir)"""
        index = os.path.join(self.tempdir, "index.html")
        files = (
            "a",
            "b b b",
            "c",
            "dalsdkjfasdlkf",
        )
        simple_dir = os.path.join(self.tempdir, "dir")
        for f in files:
            osutils.Touch(os.path.join(simple_dir, f), makedirs=True)
        commands.GenerateHtmlIndex(index, files)
        html = osutils.ReadFile(index)
        for f in files:
            self.assertIn(">%s</a>" % f, html)

    def testGenerateHtmlIndexFile(self):
        """Verifies GenerateHtmlIndex gives us something sane (input: file)"""
        index = os.path.join(self.tempdir, "index.html")
        files = (
            "a.tgz",
            "b b b.txt",
            "c",
            "dalsdkjfasdlkf",
        )
        filelist = os.path.join(self.tempdir, "listing")
        osutils.WriteFile(filelist, "\n".join(files))
        commands.GenerateHtmlIndex(index, filelist)
        html = osutils.ReadFile(index)
        for f in files:
            self.assertIn(">%s</a>" % f, html)

    def testArchiveGeneration(self):
        """Verifies BuildStandaloneImageArchive produces correct archives"""
        image_dir = os.path.join(self.tempdir, "inputs")
        archive_dir = os.path.join(self.tempdir, "outputs")
        files = (
            "a.bin",
            "aa",
            "b b b",
            "c",
            "dalsdkjfasdlkf",
        )
        dlc_dir = "dlc"
        osutils.SafeMakedirs(image_dir)
        osutils.SafeMakedirs(archive_dir)
        for f in files:
            osutils.Touch(os.path.join(image_dir, f))
        osutils.SafeMakedirs(os.path.join(image_dir, dlc_dir))

        # Check specifying tar functionality.
        artifact = {
            "paths": ["a.bin"],
            "output": "a.tar.gz",
            "archive": "tar",
            "compress": "gz",
        }
        path = commands.BuildStandaloneArchive(archive_dir, image_dir, artifact)
        self.assertEqual(path, ["a.tar.gz"])
        cros_test_lib.VerifyTarball(
            os.path.join(archive_dir, path[0]), ["a.bin"]
        )

        # Check multiple input files.
        artifact = {
            "paths": ["a.bin", "aa"],
            "output": "aa.tar.gz",
            "archive": "tar",
            "compress": "gz",
        }
        path = commands.BuildStandaloneArchive(archive_dir, image_dir, artifact)
        self.assertEqual(path, ["aa.tar.gz"])
        cros_test_lib.VerifyTarball(
            os.path.join(archive_dir, path[0]), ["a.bin", "aa"]
        )

        # Check zip functionality.
        artifact = {"paths": ["a.bin"], "archive": "zip"}
        path = commands.BuildStandaloneArchive(archive_dir, image_dir, artifact)
        self.assertEqual(path, ["a.zip"])
        self.assertExists(os.path.join(archive_dir, path[0]))

        # Check directory copy functionality.
        artifact = {"paths": ["dlc"], "output": "dlc"}
        path = commands.BuildStandaloneArchive(archive_dir, image_dir, artifact)
        self.assertEqual(path, ["dlc"])
        self.assertExists(os.path.join(archive_dir, path[0]))

    def testBuildEbuildLogsTarballPositive(self):
        """Verifies that the ebuild logs archiver builds correct logs"""
        # Names of log files typically found in a build directory.
        log_files = (
            "",
            "x11-libs:libdrm-2.4.81-r24:20170816-175008.log",
            "x11-libs:libpciaccess-0.12.902-r2:20170816-174849.log",
            "x11-libs:libva-1.7.1-r2:20170816-175019.log",
            "x11-libs:libva-intel-driver-1.7.1-r4:20170816-175029.log",
            "x11-libs:libxkbcommon-0.4.3-r2:20170816-174908.log",
            "x11-libs:pango-1.32.5-r1:20170816-174954.log",
            "x11-libs:pixman-0.32.4:20170816-174832.log",
            "x11-misc:xkeyboard-config-2.15-r3:20170816-174908.log",
            "x11-proto:kbproto-1.0.5:20170816-174849.log",
            "x11-proto:xproto-7.0.31:20170816-174849.log",
        )
        tarred_files = [os.path.join("logs", x) for x in log_files]
        log_files_root = path_util.FromChrootPath(
            f"/build/{self._TEST_BOARD}/tmp/portage/logs",
            source_path=self.tempdir,
        )
        # Generate a representative set of log files produced by a typical
        # build.
        cros_test_lib.CreateOnDiskHierarchy(log_files_root, log_files)
        # Create an archive from the simulated logs directory
        tarball = os.path.join(
            self.tempdir,
            commands.BuildEbuildLogsTarball(
                self.tempdir, self._TEST_BOARD, self.tempdir
            ),
        )
        # Verify the tarball contents.
        cros_test_lib.VerifyTarball(tarball, tarred_files)

    def testBuildEbuildLogsTarballNegative(self):
        """Verifies that the Ebuild logs archiver handles wrong inputs"""
        # Names of log files typically found in a build directory.
        log_files = (
            "",
            "x11-libs:libdrm-2.4.81-r24:20170816-175008.log",
            "x11-libs:libpciaccess-0.12.902-r2:20170816-174849.log",
            "x11-libs:libva-1.7.1-r2:20170816-175019.log",
            "x11-libs:libva-intel-driver-1.7.1-r4:20170816-175029.log",
            "x11-libs:libxkbcommon-0.4.3-r2:20170816-174908.log",
            "x11-libs:pango-1.32.5-r1:20170816-174954.log",
            "x11-libs:pixman-0.32.4:20170816-174832.log",
            "x11-misc:xkeyboard-config-2.15-r3:20170816-174908.log",
            "x11-proto:kbproto-1.0.5:20170816-174849.log",
            "x11-proto:xproto-7.0.31:20170816-174849.log",
        )

        # Create a malformed directory name.
        log_files_root = path_util.FromChrootPath(
            f"{self._TEST_BOARD}/tmp/portage/wrong_dir_name",
            source_path=self.tempdir,
        )
        # Generate a representative set of log files produced by a typical
        # build.
        cros_test_lib.CreateOnDiskHierarchy(log_files_root, log_files)

        # Create an archive from the simulated logs directory
        wrong_board = "wrongboard"
        tarball_rel_path = commands.BuildEbuildLogsTarball(
            self.tempdir, wrong_board, self.tempdir
        )
        self.assertEqual(tarball_rel_path, None)
        tarball_rel_path = commands.BuildEbuildLogsTarball(
            self.tempdir, self._TEST_BOARD, self.tempdir
        )
        self.assertEqual(tarball_rel_path, None)
