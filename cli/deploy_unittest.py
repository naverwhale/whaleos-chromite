# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for the deploy module."""

import json
import multiprocessing
import os
import sys
from unittest import mock

from chromite.cli import command
from chromite.cli import deploy
from chromite.lib import build_target_lib
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import dlc_lib
from chromite.lib import osutils
from chromite.lib import remote_access
from chromite.lib import sysroot_lib
from chromite.lib import unittest_lib
from chromite.lib.parser import package_info
from chromite.utils import os_util


pytestmark = [cros_test_lib.pytestmark_inside_only]


if cros_build_lib.IsInsideChroot():
    import portage  # pylint: disable=import-error


# pylint: disable=protected-access


# Example DLC LoadPin digests to test with.
LOADPIN_TRUSTED_VERITY_ROOT_DIGESTS = """# LOADPIN_TRUSTED_VERITY_ROOT_DIGESTS
75a799de83eee0ef0f028ea94643d1b2021261e77b8f76fee1d5749847fef431
"""

# An example LoadPin digest.
DLC_LOADPIN_DIGEST = (
    "feeddeadc0de0000000000000000000000000000000000000000000000000000"
)


class ChromiumOSDeviceFake:
    """Fake for device."""

    def __init__(self):
        self.board = "board"
        self.hostname = None
        self.username = None
        self.port = None
        self.lsb_release = None
        self.cmds = []
        self.work_dir = "/testdir/"
        self.selinux_available = False
        self.copy_store = None
        self.cat_file_output = ""
        self.cmd_disallowed = []

    def MountRootfsReadWrite(self):
        return True

    def IsSELinuxAvailable(self):
        return self.selinux_available

    def IsSELinuxEnforced(self):
        return True

    def mkdir(self, _path):
        return None

    def run(self, cmd, **_kwargs):
        if cmd in self.cmd_disallowed:
            raise cros_build_lib.RunCommandError("Command disallowed")
        else:
            self.cmds.append(cmd)

    def CopyToDevice(self, _src, _dest, _mode="rsync", **_kwargs):
        if os.path.exists(_src):
            self.copy_store = osutils.ReadFile(_src)
        return True

    def CatFile(self, _src):
        return self.cat_file_output


class ChromiumOSDeviceHandlerFake:
    """Fake for chromite.lib.remote_access.ChomiumOSDeviceHandler."""

    class RemoteAccessFake:
        """Fake for chromite.lib.remote_access.RemoteAccess."""

        def __init__(self):
            self.remote_sh_output = None

        def RemoteSh(self, *_args, **_kwargs):
            return cros_build_lib.CompletedProcess(stdout=self.remote_sh_output)

    def __init__(self, *_args, **_kwargs):
        self._agent = self.RemoteAccessFake()
        self.device = ChromiumOSDeviceFake()

    @property
    def agent(self):
        return self._agent

    def __exit__(self, _type, _value, _traceback):
        pass

    def __enter__(self):
        return self.device


class BrilloDeployOperationFake(deploy.BrilloDeployOperation):
    """Fake for deploy.BrilloDeployOperation."""

    def __init__(self, emerge, queue):
        super().__init__(emerge)
        self._queue = queue

    def ParseOutput(self, output=None):
        super().ParseOutput(output)
        self._queue.put("advance")


class DbApiFake:
    """Fake for Portage dbapi."""

    def __init__(self, pkgs):
        self.pkg_db = {}
        for cpv, slot, rdeps_raw, build_time, use in pkgs:
            self.pkg_db[cpv] = {
                "SLOT": slot,
                "RDEPEND": rdeps_raw,
                "BUILD_TIME": build_time,
                "USE": use,
            }

    def cpv_all(self):
        return list(self.pkg_db)

    def aux_get(self, cpv, keys):
        pkg_info = self.pkg_db[cpv]
        return [pkg_info[key] for key in keys]


class PackageScannerFake:
    """Fake for PackageScanner."""

    def __init__(self, packages, pkgs_attrs, packages_cpvs=None):
        self.pkgs = packages
        self.cpvs = packages_cpvs or packages
        self.listed = []
        self.num_updates = 0
        self.pkgs_attrs = pkgs_attrs
        self.warnings_shown = False

    def Run(self, _device, _root, _packages, _update, _deep, _deep_rev):
        return (
            self.cpvs,
            self.listed,
            self.num_updates,
            self.pkgs_attrs,
            self.warnings_shown,
        )


class PortageTreeFake:
    """Fake for Portage tree."""

    def __init__(self, dbapi):
        self.dbapi = dbapi


class TestInstallPackageScanner(cros_test_lib.MockOutputTestCase):
    """Test the update package scanner."""

    _BOARD = "foo_board"
    _BUILD_ROOT = "/build/%s" % _BOARD
    _VARTREE = [
        (
            "foo/app1-1.2.3-r4",
            "0",
            "foo/app2 !foo/app3",
            "1413309336",
            "cros-debug",
        ),
        ("foo/app2-4.5.6-r7", "0", "", "1413309336", "cros-debug"),
        (
            "foo/app4-2.0.0-r1",
            "0",
            "foo/app1 foo/app5",
            "1413309336",
            "cros-debug",
        ),
        ("foo/app5-3.0.7-r3", "0", "", "1413309336", "cros-debug"),
    ]

    def setUp(self):
        """Patch imported modules."""
        self.PatchObject(cros_build_lib, "GetChoice", return_value=0)
        self.device = ChromiumOSDeviceHandlerFake()
        self.scanner = deploy._InstallPackageScanner(self._BUILD_ROOT)
        self.PatchObject(deploy, "_GetDLCInfo", return_value=(None, None))
        self.PatchObject(
            deploy, "_ConfirmUpdateDespiteWarnings", return_value=True
        )

    def SetupVartree(self, vartree_pkgs):
        self.PatchObject(
            self.scanner,
            "_get_portage_interpreter",
            return_value="FAKE_PYTHON",
        )
        self.device.agent.remote_sh_output = json.dumps(vartree_pkgs)

    def SetupBintree(self, bintree_pkgs):
        bintree = PortageTreeFake(DbApiFake(bintree_pkgs))
        build_root = os.path.join(self._BUILD_ROOT, "")
        portage_db = {build_root: {"bintree": bintree}}
        self.PatchObject(portage, "create_trees", return_value=portage_db)

    def ValidatePkgs(self, actual, expected, constraints=None):
        # Containing exactly the same packages.
        self.assertEqual(sorted(expected), sorted(actual))
        # Packages appear in the right order.
        if constraints is not None:
            for needs, needed in constraints:
                self.assertGreater(actual.index(needs), actual.index(needed))

    def testRunUpdatedVersion(self):
        self.SetupVartree(self._VARTREE)
        app1 = "foo/app1-1.2.5-r4"
        self.SetupBintree(
            [
                (app1, "0", "foo/app2 !foo/app3", "1413309336", "cros-debug"),
                ("foo/app2-4.5.6-r7", "0", "", "1413309336", "cros-debug"),
            ]
        )
        installs, listed, num_updates, _, _ = self.scanner.Run(
            self.device, "/", ["app1"], True, True, True
        )
        self.ValidatePkgs(installs, [app1])
        self.ValidatePkgs(listed, [app1])
        self.assertEqual(num_updates, 1)

    def testRunUpdatedVersionWithUseMismatch(self):
        self.SetupVartree(self._VARTREE)
        app1 = "foo/app1-1.2.5-r4"
        # Setup the bintree with packages that don't have USE=cros-debug.
        self.SetupBintree(
            [
                (app1, "0", "foo/app2 !foo/app3", "1413309336", ""),
                ("foo/app2-4.5.6-r7", "0", "", "1413309336", ""),
            ]
        )
        with self.assertLogs(level="WARN") as cm:
            installs, listed, num_updates, _, _ = self.scanner.Run(
                self.device, "/", ["app1"], True, True, True
            )
            self.ValidatePkgs(installs, [app1])
            self.ValidatePkgs(listed, [app1])
            self.assertEqual(num_updates, 1)
            testline = "USE flags for package foo/app1 do not match"
            matching_logs = [
                logline for logline in cm.output if testline in logline
            ]
            self.assertTrue(
                matching_logs, "Failed to detect USE flag mismatch."
            )

    def testRunUpdatedBuildTime(self):
        self.SetupVartree(self._VARTREE)
        app1 = "foo/app1-1.2.3-r4"
        self.SetupBintree(
            [
                (app1, "0", "foo/app2 !foo/app3", "1413309350", "cros-debug"),
                ("foo/app2-4.5.6-r7", "0", "", "1413309336", "cros-debug"),
            ]
        )
        installs, listed, num_updates, _, _ = self.scanner.Run(
            self.device, "/", ["app1"], True, True, True
        )
        self.ValidatePkgs(installs, [app1])
        self.ValidatePkgs(listed, [app1])
        self.assertEqual(num_updates, 1)

    def testRunExistingDepUpdated(self):
        self.SetupVartree(self._VARTREE)
        app1 = "foo/app1-1.2.5-r2"
        app2 = "foo/app2-4.5.8-r3"
        self.SetupBintree(
            [
                (app1, "0", "foo/app2 !foo/app3", "1413309350", "cros-debug"),
                (app2, "0", "", "1413309350", "cros-debug"),
            ]
        )
        installs, listed, num_updates, _, _ = self.scanner.Run(
            self.device, "/", ["app1"], True, True, True
        )
        self.ValidatePkgs(installs, [app1, app2], constraints=[(app1, app2)])
        self.ValidatePkgs(listed, [app1])
        self.assertEqual(num_updates, 2)

    def testRunMissingDepUpdated(self):
        self.SetupVartree(self._VARTREE)
        app1 = "foo/app1-1.2.5-r2"
        app6 = "foo/app6-1.0.0-r1"
        self.SetupBintree(
            [
                (
                    app1,
                    "0",
                    "foo/app2 !foo/app3 foo/app6",
                    "1413309350",
                    "cros-debug",
                ),
                ("foo/app2-4.5.6-r7", "0", "", "1413309336", "cros-debug"),
                (app6, "0", "", "1413309350", "cros-debug"),
            ]
        )
        installs, listed, num_updates, _, _ = self.scanner.Run(
            self.device, "/", ["app1"], True, True, True
        )
        self.ValidatePkgs(installs, [app1, app6], constraints=[(app1, app6)])
        self.ValidatePkgs(listed, [app1])
        self.assertEqual(num_updates, 1)

    def testRunExistingRevDepUpdated(self):
        self.SetupVartree(self._VARTREE)
        app1 = "foo/app1-1.2.5-r2"
        app4 = "foo/app4-2.0.1-r3"
        self.SetupBintree(
            [
                (app1, "0", "foo/app2 !foo/app3", "1413309350", "cros-debug"),
                (app4, "0", "foo/app1 foo/app5", "1413309350", "cros-debug"),
                ("foo/app5-3.0.7-r3", "0", "", "1413309336", "cros-debug"),
            ]
        )
        installs, listed, num_updates, _, _ = self.scanner.Run(
            self.device, "/", ["app1"], True, True, True
        )
        self.ValidatePkgs(installs, [app1, app4], constraints=[(app4, app1)])
        self.ValidatePkgs(listed, [app1])
        self.assertEqual(num_updates, 2)

    def testRunMissingRevDepNotUpdated(self):
        self.SetupVartree(self._VARTREE)
        app1 = "foo/app1-1.2.5-r2"
        app6 = "foo/app6-1.0.0-r1"
        self.SetupBintree(
            [
                (app1, "0", "foo/app2 !foo/app3", "1413309350", "cros-debug"),
                (app6, "0", "foo/app1", "1413309350", "cros-debug"),
            ]
        )
        installs, listed, num_updates, _, _ = self.scanner.Run(
            self.device, "/", ["app1"], True, True, True
        )
        self.ValidatePkgs(installs, [app1])
        self.ValidatePkgs(listed, [app1])
        self.assertEqual(num_updates, 1)

    def testRunTransitiveDepsUpdated(self):
        self.SetupVartree(self._VARTREE)
        app1 = "foo/app1-1.2.5-r2"
        app2 = "foo/app2-4.5.8-r3"
        app4 = "foo/app4-2.0.0-r1"
        app5 = "foo/app5-3.0.8-r2"
        self.SetupBintree(
            [
                (app1, "0", "foo/app2 !foo/app3", "1413309350", "cros-debug"),
                (app2, "0", "", "1413309350", "cros-debug"),
                (app4, "0", "foo/app1 foo/app5", "1413309350", "cros-debug"),
                (app5, "0", "", "1413309350", "cros-debug"),
            ]
        )
        installs, listed, num_updates, _, _ = self.scanner.Run(
            self.device, "/", ["app1"], True, True, True
        )
        self.ValidatePkgs(
            installs,
            [app1, app2, app4, app5],
            constraints=[(app1, app2), (app4, app1), (app4, app5)],
        )
        self.ValidatePkgs(listed, [app1])
        self.assertEqual(num_updates, 4)

    def testRunDisjunctiveDepsExistingUpdated(self):
        self.SetupVartree(self._VARTREE)
        app1 = "foo/app1-1.2.5-r2"
        self.SetupBintree(
            [
                (
                    app1,
                    "0",
                    "|| ( foo/app6 foo/app2 ) !foo/app3",
                    "1413309350",
                    "cros-debug",
                ),
                ("foo/app2-4.5.6-r7", "0", "", "1413309336", "cros-debug"),
            ]
        )
        installs, listed, num_updates, _, _ = self.scanner.Run(
            self.device, "/", ["app1"], True, True, True
        )
        self.ValidatePkgs(installs, [app1])
        self.ValidatePkgs(listed, [app1])
        self.assertEqual(num_updates, 1)

    def testRunDisjunctiveDepsDefaultUpdated(self):
        self.SetupVartree(self._VARTREE)
        app1 = "foo/app1-1.2.5-r2"
        app7 = "foo/app7-1.0.0-r1"
        self.SetupBintree(
            [
                (
                    app1,
                    "0",
                    "|| ( foo/app6 foo/app7 ) !foo/app3",
                    "1413309350",
                    "cros-debug",
                ),
                (app7, "0", "", "1413309350", "cros-debug"),
            ]
        )
        installs, listed, num_updates, _, _ = self.scanner.Run(
            self.device, "/", ["app1"], True, True, True
        )
        self.ValidatePkgs(installs, [app1, app7], constraints=[(app1, app7)])
        self.ValidatePkgs(listed, [app1])
        self.assertEqual(num_updates, 1)

    def test_get_portage_interpreter(self):
        """Test getting the portage interpreter from the device."""
        self.device.agent.remote_sh_output = """\
/usr/lib/python-exec/python3.6/emerge
/usr/lib/python-exec/python3.8/emerge
/usr/lib/python-exec/python3.11/emerge
"""
        self.assertEqual(
            self.scanner._get_portage_interpreter(self.device),
            "python3.11",
        )


class TestDeploy(
    cros_test_lib.ProgressBarTestCase, cros_test_lib.MockTempDirTestCase
):
    """Test deploy.Deploy."""

    @staticmethod
    def FakeGetPackagesByCPV(cpvs, _strip, _sysroot):
        return ["/path/to/%s.tbz2" % cpv.pv for cpv in cpvs]

    def setUp(self):
        # Fake being root to avoid running filesystem commands with sudo_run.
        self.PatchObject(os_util, "is_root_user", return_value=True)
        self._sysroot = os.path.join(self.tempdir, "sysroot")
        osutils.SafeMakedirs(self._sysroot)
        self.device = ChromiumOSDeviceHandlerFake()
        self.PatchObject(
            remote_access, "ChromiumOSDeviceHandler", return_value=self.device
        )
        self.PatchObject(cros_build_lib, "GetBoard", return_value=None)
        self.PatchObject(
            build_target_lib,
            "get_default_sysroot_path",
            return_value=self._sysroot,
        )
        self.package_scanner = self.PatchObject(
            deploy, "_InstallPackageScanner"
        )
        self.get_packages_paths = self.PatchObject(
            deploy, "_GetPackagesByCPV", side_effect=self.FakeGetPackagesByCPV
        )
        self.emerge = self.PatchObject(deploy, "_Emerge", return_value=None)
        self.unmerge = self.PatchObject(deploy, "_Unmerge", return_value=None)
        self.PatchObject(deploy, "_GetDLCInfo", return_value=(None, None))
        # Avoid running the portageq command.
        sysroot_lib.Sysroot(self._sysroot).WriteConfig(
            'ARCH="amd64"\nPORTDIR_OVERLAY="%s"' % "/nothing/here"
        )
        # make.conf needs to exist to correctly read back config.
        unittest_lib.create_stub_make_conf(self._sysroot)

    def testDeployEmerge(self):
        """Test that deploy._Emerge is called for each package."""

        _BINPKG = "/path/to/bar-1.2.5.tbz2"

        def FakeIsFile(fname):
            return fname == _BINPKG

        packages = ["some/foo-1.2.3", _BINPKG, "some/foobar-2.0"]
        cpvs = ["some/foo-1.2.3", "to/bar-1.2.5", "some/foobar-2.0"]
        self.package_scanner.return_value = PackageScannerFake(
            packages,
            {"some/foo-1.2.3": {}, _BINPKG: {}, "some/foobar-2.0": {}},
            cpvs,
        )
        self.PatchObject(os.path, "isfile", side_effect=FakeIsFile)

        deploy.Deploy(None, ["package"], force=True, clean_binpkg=False)

        # Check that package names were correctly resolved into binary packages.
        self.get_packages_paths.assert_called_once_with(
            [package_info.SplitCPV(p) for p in cpvs], True, self._sysroot
        )
        # Check that deploy._Emerge is called the right number of times.
        self.emerge.assert_called_once_with(
            mock.ANY,
            [
                "/path/to/foo-1.2.3.tbz2",
                "/path/to/bar-1.2.5.tbz2",
                "/path/to/foobar-2.0.tbz2",
            ],
            "/",
            extra_args=None,
        )
        self.assertEqual(self.unmerge.call_count, 0)

    def testDeployEmergeDLC(self):
        """Test that deploy._Emerge installs images for DLC packages."""
        packages = ["some/foodlc-1.0", "some/bardlc-2.0"]
        cpvs = ["some/foodlc-1.0", "some/bardlc-2.0"]
        self.package_scanner.return_value = PackageScannerFake(
            packages, {"some/foodlc-1.0": {}, "some/bardlc-2.0": {}}, cpvs
        )
        dlc_id = "foo_id"
        self.PatchObject(
            deploy, "_GetDLCInfo", return_value=(dlc_id, "foo_package")
        )

        deploy.Deploy(None, ["package"], force=True, clean_binpkg=False)
        # Check that dlcservice is restarted (DLC modules are deployed).
        self.assertTrue(
            ["dlcservice_util", "--deploy", f"--id={dlc_id}"]
            in self.device.device.cmds
        )
        self.assertTrue(["restart", "dlcservice"] in self.device.device.cmds)

    def testDeployEmergeDLCFallback(self):
        """Test that deploy._Emerge installs images for DLC packages."""
        packages = ["some/foodlc-1.0", "some/bardlc-2.0"]
        cpvs = ["some/foodlc-1.0", "some/bardlc-2.0"]
        self.package_scanner.return_value = PackageScannerFake(
            packages, {"some/foodlc-1.0": {}, "some/bardlc-2.0": {}}, cpvs
        )
        dlc_id = "foo_id"
        self.PatchObject(
            deploy, "_GetDLCInfo", return_value=(dlc_id, "foo_package")
        )
        deploy_cmd = ["dlcservice_util", "--deploy", f"--id={dlc_id}"]
        # Fails to run the dlcservice_util command to trigger fallback.
        self.device.device.cmd_disallowed.append(deploy_cmd)

        deploy.Deploy(None, ["package"], force=True, clean_binpkg=False)
        # Check that dlcservice is restarted (DLC modules are deployed).
        self.assertFalse(deploy_cmd in self.device.device.cmds)
        self.assertTrue(["restart", "dlcservice"] in self.device.device.cmds)

    def testDeployDLCLoadPinMissingDeviceDigests(self):
        """Test that _DeployDLCLoadPin works with missing device digests."""
        osutils.WriteFile(
            self.tempdir
            / dlc_lib.DLC_META_DIR
            / dlc_lib.DLC_LOADPIN_TRUSTED_VERITY_DIGESTS,
            LOADPIN_TRUSTED_VERITY_ROOT_DIGESTS,
            makedirs=True,
        )
        with self.device as d:
            deploy._DeployDLCLoadPin(self.tempdir, d)
        self.assertEqual(
            d.copy_store.splitlines()[0], dlc_lib.DLC_LOADPIN_FILE_HEADER
        )
        self.assertFalse(DLC_LOADPIN_DIGEST in d.copy_store.splitlines())
        self.assertTrue(
            "75a799de83eee0ef0f028ea94643d1b2021261e77b8f76fee1d5749847fef431"
            in d.copy_store.splitlines()
        )

    def testDeployDLCLoadPinFeedNewDigests(self):
        """Test that _DeployDLCLoadPin works with digest format file."""
        osutils.WriteFile(
            self.tempdir
            / dlc_lib.DLC_META_DIR
            / dlc_lib.DLC_LOADPIN_TRUSTED_VERITY_DIGESTS,
            LOADPIN_TRUSTED_VERITY_ROOT_DIGESTS,
            makedirs=True,
        )
        with self.device as d:
            d.cat_file_output = DLC_LOADPIN_DIGEST
            deploy._DeployDLCLoadPin(self.tempdir, d)
        self.assertEqual(
            d.copy_store.splitlines()[0], dlc_lib.DLC_LOADPIN_FILE_HEADER
        )
        self.assertTrue(DLC_LOADPIN_DIGEST in d.copy_store.splitlines())
        self.assertTrue(
            "75a799de83eee0ef0f028ea94643d1b2021261e77b8f76fee1d5749847fef431"
            in d.copy_store.splitlines()
        )

    def testDeployEmergeSELinux(self):
        """Test deploy progress when the device has SELinux"""

        _BINPKG = "/path/to/bar-1.2.5.tbz2"

        def FakeIsFile(fname):
            return fname == _BINPKG

        def GetRestoreconCommand(pkgfile):
            remote_path = os.path.join("/testdir/packages/to/", pkgfile)
            return [
                [
                    "cd",
                    "/",
                    "&&",
                    "tar",
                    "tf",
                    remote_path,
                    "|",
                    "restorecon",
                    "-i",
                    "-f",
                    "-",
                ]
            ]

        self.device.device.selinux_available = True
        packages = ["some/foo-1.2.3", _BINPKG, "some/foobar-2.0"]
        cpvs = ["some/foo-1.2.3", "to/bar-1.2.5", "some/foobar-2.0"]
        self.package_scanner.return_value = PackageScannerFake(
            packages,
            {"some/foo-1.2.3": {}, _BINPKG: {}, "some/foobar-2.0": {}},
            cpvs,
        )
        self.PatchObject(os.path, "isfile", side_effect=FakeIsFile)

        deploy.Deploy(None, ["package"], force=True, clean_binpkg=False)

        # Check that package names were correctly resolved into binary packages.
        self.get_packages_paths.assert_called_once_with(
            [package_info.SplitCPV(p) for p in cpvs], True, self._sysroot
        )
        # Check that deploy._Emerge is called the right number of times.
        self.assertEqual(self.emerge.call_count, 1)
        self.assertEqual(self.unmerge.call_count, 0)

        self.assertEqual(
            self.device.device.cmds,
            [["setenforce", "0"]]
            + GetRestoreconCommand("foo-1.2.3.tbz2")
            + GetRestoreconCommand("bar-1.2.5.tbz2")
            + GetRestoreconCommand("foobar-2.0.tbz2")
            + [["setenforce", "1"]],
        )

    def testDeployUnmerge(self):
        """Test that deploy._Unmerge is called for each package."""
        packages = ["foo", "bar", "foobar", "foodlc"]
        self.package_scanner.return_value = PackageScannerFake(
            packages,
            {
                "foo": {},
                "bar": {},
                "foobar": {},
                "foodlc": {
                    deploy._DLC_ID: "foodlc",
                    deploy._DLC_PACKAGE: "foopackage",
                },
            },
        )

        deploy.Deploy(
            None, ["package"], force=True, clean_binpkg=False, emerge=False
        )

        # Check that deploy._Unmerge is called the right number of times.
        self.assertEqual(self.emerge.call_count, 0)
        self.unmerge.assert_called_once_with(mock.ANY, packages, "/")

        self.assertEqual(
            self.device.device.cmds,
            [
                ["dlcservice_util", "--uninstall", "--id=foodlc"],
                ["restart", "dlcservice"],
            ],
        )

    def testDeployMergeWithProgressBar(self):
        """Test that BrilloDeployOperation.Run() is called for merge."""
        packages = ["foo", "bar", "foobar"]
        self.package_scanner.return_value = PackageScannerFake(
            packages, {"foo": {}, "bar": {}, "foobar": {}}
        )

        run = self.PatchObject(
            deploy.BrilloDeployOperation, "Run", return_value=None
        )

        self.PatchObject(command, "UseProgressBar", return_value=True)
        deploy.Deploy(None, ["package"], force=True, clean_binpkg=False)

        # Check that BrilloDeployOperation.Run was called.
        self.assertTrue(run.called)

    def testDeployUnmergeWithProgressBar(self):
        """Test that BrilloDeployOperation.Run() is called for unmerge."""
        packages = ["foo", "bar", "foobar"]
        self.package_scanner.return_value = PackageScannerFake(
            packages, {"foo": {}, "bar": {}, "foobar": {}}
        )

        run = self.PatchObject(
            deploy.BrilloDeployOperation, "Run", return_value=None
        )

        self.PatchObject(command, "UseProgressBar", return_value=True)
        deploy.Deploy(
            None, ["package"], force=True, clean_binpkg=False, emerge=False
        )

        # Check that BrilloDeployOperation.Run was called.
        self.assertTrue(run.called)

    def testBrilloDeployMergeOperation(self):
        """Test that BrilloDeployOperation works for merge."""

        def func(queue):
            for event in op.MERGE_EVENTS:
                queue.get()
                print(event)
                sys.stdout.flush()

        queue = multiprocessing.Queue()
        # Emerge one package.
        op = BrilloDeployOperationFake(True, queue)

        with self.OutputCapturer():
            op.Run(func, queue)

        # Check that the progress bar prints correctly.
        self.AssertProgressBarAllEvents(len(op.MERGE_EVENTS))

    def testBrilloDeployUnmergeOperation(self):
        """Test that BrilloDeployOperation works for unmerge."""

        def func(queue):
            for event in op.UNMERGE_EVENTS:
                queue.get()
                print(event)
                sys.stdout.flush()

        queue = multiprocessing.Queue()
        # Unmerge one package.
        op = BrilloDeployOperationFake(False, queue)

        with self.OutputCapturer():
            op.Run(func, queue)

        # Check that the progress bar prints correctly.
        self.AssertProgressBarAllEvents(len(op.UNMERGE_EVENTS))
