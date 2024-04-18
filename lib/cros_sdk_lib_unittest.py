# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the cros_sdk_lib module."""

import errno
import os
from pathlib import Path
import stat
from unittest import mock

import pytest

from chromite.lib import chroot_lib
from chromite.lib import cros_build_lib
from chromite.lib import cros_sdk_lib
from chromite.lib import cros_test_lib
from chromite.lib import locking
from chromite.lib import osutils


# pylint: disable=protected-access


class VersionHookTestCase(cros_test_lib.TempDirTestCase):
    """Class to set up tests that use the version hooks."""

    def setUp(self):
        # Build set of expected scripts.
        self.ExpectRootOwnedFiles()
        D = cros_test_lib.Directory
        filesystem = (
            D(
                "hooks",
                (
                    "8_invalid_gap",
                    "10_run_success",
                    "11_run_success",
                    "12_run_success",
                ),
            ),
            "version_file",
        )
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, filesystem)

        self.chroot_path = os.path.join(self.tempdir, "chroot")
        self.version_file = os.path.join(
            self.chroot_path, cros_sdk_lib.CHROOT_VERSION_FILE.lstrip(os.sep)
        )
        osutils.WriteFile(self.version_file, "0", makedirs=True, sudo=True)
        self.hooks_dir = os.path.join(self.tempdir, "hooks")

        self.earliest_version = 8
        self.latest_version = 12
        self.deprecated_versions = (6, 7, 8)
        self.invalid_versions = (13,)
        self.success_versions = (9, 10, 11, 12)


class TestGetFileSystemDebug(cros_test_lib.RunCommandTestCase):
    """Tests GetFileSystemDebug functionality."""

    def testNoPs(self):
        """Verify with run_ps=False."""
        self.rc.AddCmdResult(
            ["sudo", "--", "fuser", "/some/path"], stdout="fuser_output"
        )
        self.rc.AddCmdResult(
            ["sudo", "--", "lsof", "/some/path"], stdout="lsof_output"
        )
        file_system_debug_tuple = cros_sdk_lib.GetFileSystemDebug(
            "/some/path", run_ps=False
        )
        self.assertEqual(file_system_debug_tuple.fuser, "fuser_output")
        self.assertEqual(file_system_debug_tuple.lsof, "lsof_output")
        self.assertIsNone(file_system_debug_tuple.ps)

    def testWithPs(self):
        """Verify with run_ps=False."""
        self.rc.AddCmdResult(
            ["sudo", "--", "fuser", "/some/path"], stdout="fuser_output"
        )
        self.rc.AddCmdResult(
            ["sudo", "--", "lsof", "/some/path"], stdout="lsof_output"
        )
        self.rc.AddCmdResult(["ps", "auxf"], stdout="ps_output")
        file_system_debug_tuple = cros_sdk_lib.GetFileSystemDebug(
            "/some/path", run_ps=True
        )
        self.assertEqual(file_system_debug_tuple.fuser, "fuser_output")
        self.assertEqual(file_system_debug_tuple.lsof, "lsof_output")
        self.assertEqual(file_system_debug_tuple.ps, "ps_output")


class TestMigrateStatePaths(cros_test_lib.MockTempDirTestCase):
    """Tests MigrateStatePaths functionality."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        chroot_path = self.tempdir / "chroot"
        out_path = self.tempdir / "out"
        self.chroot = chroot_lib.Chroot(path=chroot_path, out_path=out_path)
        osutils.SafeMakedirsNonRoot(self.chroot.path)
        osutils.SafeMakedirsNonRoot(self.chroot.out_path)
        self.lock = locking.FileLock(
            chroot_path / ".chroot_lock", "chroot lock"
        )

        self.state_path_map = (
            (Path(self.chroot.path) / "tmp", self.chroot.out_path / "tmp"),
            (Path(self.chroot.path) / "home", self.chroot.out_path / "home"),
            (Path(self.chroot.path) / "build", self.chroot.out_path / "build"),
            (
                Path(self.chroot.path) / "usr" / "local" / "bin",
                self.chroot.out_path / "sdk" / "bin",
            ),
            (
                Path(self.chroot.path) / "var" / "cache",
                self.chroot.out_path / "sdk" / "cache",
            ),
            (
                Path(self.chroot.path) / "var" / "log",
                self.chroot.out_path / "sdk" / "logs",
            ),
        )

    def _crossdevice_rename(self, src, dst):
        raise OSError(errno.EXDEV, "fake cross-device rename failure")

    def testOldPathsExist(self):
        for src, dst in self.state_path_map:
            osutils.SafeMakedirsNonRoot(src / "foo")

        cros_sdk_lib.MigrateStatePaths(self.chroot, self.lock)

        for src, dst in self.state_path_map:
            self.assertNotExists(src / "foo")
            self.assertExists(src / "README")
            self.assertExists(dst / "foo")

    def testOnlyReadmeExists(self):
        for src, dst in self.state_path_map:
            osutils.SafeMakedirsNonRoot(src)
            osutils.Touch(src / "README")

        cros_sdk_lib.MigrateStatePaths(self.chroot, self.lock)

        for src, dst in self.state_path_map:
            self.assertExists(src / "README")
            self.assertNotExists(dst / "README")

    def testBothPathsExist(self):
        for src, dst in self.state_path_map:
            osutils.SafeMakedirsNonRoot(src / "foo")
            osutils.Touch(src / "foo" / "bar")
            osutils.SafeMakedirsNonRoot(dst / "foo")
            osutils.Touch(dst / "foo" / "baz")

        cros_sdk_lib.MigrateStatePaths(self.chroot, self.lock)

        for src, dst in self.state_path_map:
            self.assertNotExists(src / "foo")
            self.assertExists(dst / "foo")
            self.assertExists(dst / "foo" / "bar")
            self.assertExists(dst / "foo" / "baz")

    def testCrossDevice(self):
        """Verify we can migrate state across filesystem boundaries.

        Check for retention of ownership, mode too, since we
        need to exercise different logic when os.rename()
        doesn't work.
        """
        # Mock os.rename() to fail, so we fall back to copying/rsyncing.
        self.PatchObject(os, "rename", side_effect=self._crossdevice_rename)

        for src, dst in self.state_path_map:
            osutils.SafeMakedirsNonRoot(src / "foo")
            (src / "foo" / "bar").touch()
            (src / "foo" / "baz").touch(mode=0o400)
            osutils.Chown(src / "foo" / "baz", user="root", group="root")
            self.assertEqual(
                stat.S_IMODE((src / "foo" / "baz").stat().st_mode), 0o400
            )

            cros_sdk_lib.MigrateStatePaths(self.chroot, self.lock)

            self.assertNotExists(src / "foo")
            self.assertExists(dst / "foo")
            self.assertExists(dst / "foo" / "bar")
            self.assertExists(dst / "foo" / "baz")
            st = (dst / "foo" / "baz").stat()
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o400)
            self.assertEqual(st.st_uid, 0)
            self.assertEqual(st.st_gid, 0)


class TestMountChrootPaths(cros_test_lib.MockTempDirTestCase):
    """Tests MountChrootPaths functionality."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        chroot_path = self.tempdir / "chroot"
        out_path = self.tempdir / "out"
        self.chroot = chroot_lib.Chroot(path=chroot_path, out_path=out_path)
        osutils.SafeMakedirsNonRoot(self.chroot.path)
        osutils.SafeMakedirsNonRoot(self.chroot.out_path)

        osutils.WriteFile(
            chroot_path / "etc" / "passwd", "passwd contents", makedirs=True
        )
        osutils.WriteFile(
            chroot_path / "etc" / "group", "group contents", makedirs=True
        )
        osutils.WriteFile(
            chroot_path / "etc" / "shadow", "shadow contents", makedirs=True
        )

        self.mount_mock = self.PatchObject(osutils, "Mount")

    def testMounts(self):
        cros_sdk_lib.MountChrootPaths(self.chroot)

        self.mount_mock.assert_has_calls(
            [
                mock.call(
                    Path(self.chroot.path),
                    Path(self.chroot.path),
                    None,
                    osutils.MS_BIND | osutils.MS_REC,
                ),
                mock.call(
                    self.chroot.out_path / "tmp",
                    Path(self.chroot.path) / "tmp",
                    None,
                    osutils.MS_BIND | osutils.MS_REC,
                ),
                mock.call(
                    self.chroot.out_path / "home",
                    Path(self.chroot.path) / "home",
                    None,
                    osutils.MS_BIND | osutils.MS_REC,
                ),
                mock.call(
                    self.chroot.out_path / "build",
                    Path(self.chroot.path) / "build",
                    None,
                    osutils.MS_BIND | osutils.MS_REC,
                ),
                mock.call(
                    self.chroot.out_path / "sdk" / "bin",
                    Path(self.chroot.path) / "usr" / "local" / "bin",
                    None,
                    osutils.MS_BIND | osutils.MS_REC,
                ),
                mock.call(
                    self.chroot.out_path / "sdk" / "cache",
                    Path(self.chroot.path) / "var" / "cache",
                    None,
                    osutils.MS_BIND | osutils.MS_REC,
                ),
                mock.call(
                    self.chroot.out_path / "sdk" / "run",
                    Path(self.chroot.path) / "run",
                    None,
                    osutils.MS_BIND | osutils.MS_REC,
                ),
                mock.call(
                    self.chroot.out_path / "sdk" / "logs",
                    Path(self.chroot.path) / "var" / "log",
                    None,
                    osutils.MS_BIND | osutils.MS_REC,
                ),
                mock.call(
                    self.chroot.out_path / "sdk" / "tmp",
                    Path(self.chroot.path) / "var" / "tmp",
                    None,
                    osutils.MS_BIND | osutils.MS_REC,
                ),
                mock.call(
                    "proc", Path(self.chroot.path) / "proc", "proc", mock.ANY
                ),
                mock.call(
                    "sysfs", Path(self.chroot.path) / "sys", "sysfs", mock.ANY
                ),
                mock.call(
                    "/dev",
                    Path(self.chroot.path) / "dev",
                    None,
                    osutils.MS_BIND | osutils.MS_REC,
                ),
                mock.call(
                    self.chroot.out_path / "sdk" / "passwd",
                    Path(self.chroot.path) / "etc" / "passwd",
                    None,
                    osutils.MS_BIND,
                ),
                mock.call(
                    self.chroot.out_path / "sdk" / "group",
                    Path(self.chroot.path) / "etc" / "group",
                    None,
                    osutils.MS_BIND,
                ),
                mock.call(
                    self.chroot.out_path / "sdk" / "shadow",
                    Path(self.chroot.path) / "etc" / "shadow",
                    None,
                    osutils.MS_BIND,
                ),
            ],
            any_order=True,
        )

    def testPasswdExists(self):
        """If out/ already has passwd contents, we should still mount OK."""
        osutils.WriteFile(
            self.chroot.out_path / "sdk" / "passwd",
            "preexisting passwd",
            makedirs=True,
        )

        cros_sdk_lib.MountChrootPaths(self.chroot)

        self.assertEqual(
            "preexisting passwd",
            osutils.ReadFile(self.chroot.out_path / "sdk" / "passwd"),
        )

        self.mount_mock.assert_has_calls(
            [
                mock.call(
                    self.chroot.out_path / "sdk" / "passwd",
                    Path(self.chroot.path) / "etc" / "passwd",
                    None,
                    osutils.MS_BIND,
                ),
                mock.call(
                    self.chroot.out_path / "sdk" / "group",
                    Path(self.chroot.path) / "etc" / "group",
                    None,
                    osutils.MS_BIND,
                ),
                mock.call(
                    self.chroot.out_path / "sdk" / "shadow",
                    Path(self.chroot.path) / "etc" / "shadow",
                    None,
                    osutils.MS_BIND,
                ),
            ],
            any_order=True,
        )

    def testTmpPermissions(self):
        cros_sdk_lib.MountChrootPaths(self.chroot)

        self.assertEqual(
            0o1777, stat.S_IMODE(os.stat(self.chroot.out_path / "tmp").st_mode)
        )


class TestGetChrootVersion(cros_test_lib.MockTestCase):
    """Tests GetChrootVersion functionality."""

    def testNoChroot(self):
        """Verify we don't blow up when there is no chroot yet."""
        self.PatchObject(
            cros_sdk_lib.ChrootUpdater, "GetVersion", side_effect=IOError()
        )
        self.assertIsNone(cros_sdk_lib.GetChrootVersion("/.$om3/place/nowhere"))


class TestChrootVersionValid(VersionHookTestCase):
    """Test valid chroot version method."""

    def testLowerVersionValid(self):
        """Lower versions are considered valid."""
        osutils.WriteFile(
            self.version_file, str(self.latest_version - 1), sudo=True
        )
        self.assertTrue(
            cros_sdk_lib.IsChrootVersionValid(self.chroot_path, self.hooks_dir)
        )

    def testLatestVersionValid(self):
        """Test latest version."""
        osutils.WriteFile(
            self.version_file, str(self.latest_version), sudo=True
        )
        self.assertTrue(
            cros_sdk_lib.IsChrootVersionValid(self.chroot_path, self.hooks_dir)
        )

    def testInvalidVersion(self):
        """Test version higher than latest."""
        osutils.WriteFile(
            self.version_file, str(self.latest_version + 1), sudo=True
        )
        self.assertFalse(
            cros_sdk_lib.IsChrootVersionValid(self.chroot_path, self.hooks_dir)
        )


class TestLatestChrootVersion(VersionHookTestCase):
    """LatestChrootVersion tests."""

    def testLatest(self):
        """Test latest version."""
        self.assertEqual(
            self.latest_version,
            cros_sdk_lib.LatestChrootVersion(self.hooks_dir),
        )


class TestEarliestChrootVersion(VersionHookTestCase):
    """EarliestChrootVersion tests."""

    def testEarliest(self):
        """Test earliest version."""
        self.assertEqual(
            self.earliest_version,
            cros_sdk_lib.EarliestChrootVersion(self.hooks_dir),
        )


class TestIsChrootReady(cros_test_lib.MockTestCase):
    """Tests IsChrootReady functionality."""

    def setUp(self):
        self.version_mock = self.PatchObject(cros_sdk_lib, "GetChrootVersion")

    def testMissing(self):
        """Check behavior w/out a chroot."""
        self.version_mock.return_value = None
        self.assertFalse(cros_sdk_lib.IsChrootReady("/"))

    def testNotSetup(self):
        """Check behavior w/an existing uninitialized chroot."""
        self.version_mock.return_value = 0
        self.assertFalse(cros_sdk_lib.IsChrootReady("/"))

    def testUpToDate(self):
        """Check behavior w/a valid chroot."""
        self.version_mock.return_value = 123
        self.assertTrue(cros_sdk_lib.IsChrootReady("/"))


class TestCleanupChrootMount(cros_test_lib.MockTempDirTestCase):
    """Tests the CleanupChrootMount function."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        self.chroot = chroot_lib.Chroot(
            path=self.tempdir / "chroot",
            out_path=self.tempdir / "out",
        )
        osutils.SafeMakedirsNonRoot(self.chroot.path)
        osutils.SafeMakedirsNonRoot(self.chroot.out_path)

    def testCleanup(self):
        m = self.PatchObject(osutils, "UmountTree")

        cros_sdk_lib.CleanupChrootMount(self.chroot, None)

        m.assert_called_with(self.chroot.path)

    def testCleanupByBuildroot(self):
        m = self.PatchObject(osutils, "UmountTree")

        cros_sdk_lib.CleanupChrootMount(None, self.tempdir)

        m.assert_called_with(self.chroot.path)

    def testCleanupWithDelete(self):
        m = self.PatchObject(osutils, "UmountTree")
        m2 = self.PatchObject(osutils, "RmDir")

        cros_sdk_lib.CleanupChrootMount(self.chroot, None, delete=True)

        m.assert_called_with(self.chroot.path)
        m2.assert_any_call(self.chroot.path, ignore_missing=True, sudo=True)
        m2.assert_any_call(self.chroot.out_path, ignore_missing=True, sudo=True)

    def testCleanupNoDeleteOut(self):
        m = self.PatchObject(osutils, "UmountTree")
        m2 = self.PatchObject(osutils, "RmDir")

        cros_sdk_lib.CleanupChrootMount(
            self.chroot, None, delete=True, delete_out=False
        )

        m.assert_called_with(self.chroot.path)
        m2.assert_called_with(self.chroot.path, ignore_missing=True, sudo=True)


class ChrootUpdaterTest(cros_test_lib.MockTestCase, VersionHookTestCase):
    """ChrootUpdater tests."""

    def setUp(self):
        self.chroot = cros_sdk_lib.ChrootUpdater(
            version_file=self.version_file, hooks_dir=self.hooks_dir
        )

    def testVersion(self):
        """Test the version property logic."""
        # Testing default value.
        self.assertEqual(0, self.chroot.GetVersion())

        # Test setting the version.
        self.chroot.SetVersion(5)
        self.assertEqual(5, self.chroot.GetVersion())
        self.assertEqual("5", osutils.ReadFile(self.version_file))

        # The current behavior is that outside processes writing to the file
        # does not affect our view after we've already read it. This shouldn't
        # generally be a problem since run_chroot_version_hooks should be the
        # only process writing to it.
        osutils.WriteFile(self.version_file, "10", sudo=True)
        self.assertEqual(5, self.chroot.GetVersion())

    def testInvalidVersion(self):
        """Test invalid version file contents."""
        osutils.WriteFile(self.version_file, "invalid", sudo=True)
        with self.assertRaises(cros_sdk_lib.InvalidChrootVersionError):
            self.chroot.GetVersion()

    def testMissingFileVersion(self):
        """Test missing version file."""
        osutils.SafeUnlink(self.version_file, sudo=True)
        with self.assertRaises(cros_sdk_lib.UninitializedChrootError):
            self.chroot.GetVersion()

    def testLatestVersion(self):
        """Test the latest_version property/_LatestScriptsVersion method."""
        self.assertEqual(self.latest_version, self.chroot.latest_version)

    def testGetChrootUpdates(self):
        """Test GetChrootUpdates."""
        # Test the deprecated error conditions.
        for version in self.deprecated_versions:
            self.chroot.SetVersion(version)
            with self.assertRaises(cros_sdk_lib.ChrootDeprecatedError):
                self.chroot.GetChrootUpdates()

    def testMultipleUpdateFiles(self):
        """Test handling of multiple files existing for a single version."""
        # When the version would be run.
        osutils.WriteFile(os.path.join(self.hooks_dir, "10_duplicate"), "")

        self.chroot.SetVersion(9)
        with self.assertRaises(cros_sdk_lib.VersionHasMultipleHooksError):
            self.chroot.GetChrootUpdates()

        # When the version would not be run.
        self.chroot.SetVersion(11)
        with self.assertRaises(cros_sdk_lib.VersionHasMultipleHooksError):
            self.chroot.GetChrootUpdates()

    def testApplyUpdates(self):
        """Test ApplyUpdates."""
        rc_mock = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc_mock.SetDefaultCmdResult()
        for version in self.success_versions:
            self.chroot.SetVersion(version)
            self.chroot.ApplyUpdates()
            self.assertEqual(self.latest_version, self.chroot.GetVersion())

    def testApplyInvalidUpdates(self):
        """Test the invalid version conditions for ApplyUpdates."""
        for version in self.invalid_versions:
            self.chroot.SetVersion(version)
            with self.assertRaises(cros_sdk_lib.InvalidChrootVersionError):
                self.chroot.ApplyUpdates()

    def testIsInitialized(self):
        """Test IsInitialized conditions."""
        self.chroot.SetVersion(0)
        self.assertFalse(self.chroot.IsInitialized())

        self.chroot.SetVersion(1)
        self.assertTrue(self.chroot.IsInitialized())

        # Test handling each of the errors thrown by GetVersion.
        self.PatchObject(
            self.chroot,
            "GetVersion",
            side_effect=cros_sdk_lib.InvalidChrootVersionError(),
        )
        self.assertFalse(self.chroot.IsInitialized())

        self.PatchObject(self.chroot, "GetVersion", side_effect=IOError())
        self.assertFalse(self.chroot.IsInitialized())

        self.PatchObject(
            self.chroot,
            "GetVersion",
            side_effect=cros_sdk_lib.UninitializedChrootError(),
        )
        self.assertFalse(self.chroot.IsInitialized())


class ChrootCreatorTests(cros_test_lib.MockTempDirTestCase):
    """ChrootCreator tests."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        self.chroot = chroot_lib.Chroot(
            path=self.tempdir / "chroot",
            out_path=self.tempdir / "out",
            cache_dir=str(self.tempdir / "cache_dir"),
        )
        self.sdk_tarball = self.tempdir / "chroot.tar"

        # We can't really verify these in any useful way atm.
        self.mount_mock = self.PatchObject(osutils, "Mount")

        self.creater = cros_sdk_lib.ChrootCreator(self.chroot, self.sdk_tarball)

        # Create a minimal tarball to extract during testing.
        tar_dir = self.tempdir / "tar_dir"
        D = cros_test_lib.Directory
        cros_test_lib.CreateOnDiskHierarchy(
            tar_dir,
            (
                D(
                    "etc",
                    (
                        D("env.d", ()),
                        "passwd",
                        "group",
                        "shadow",
                        D("skel", (D(".ssh", ("foo",)),)),
                    ),
                ),
                D(
                    "var",
                    (
                        D(
                            "cache",
                            (D("edb", ("counter",)),),
                        ),
                        D("log", (D("portage", ()),)),
                    ),
                ),
            ),
        )
        (tar_dir / "etc/passwd").write_text(
            "root:x:0:0:Root:/root:/bin/bash\n", encoding="utf-8"
        )
        (tar_dir / "etc/group").write_text(
            "root::0\nusers::100\n", encoding="utf-8"
        )
        (tar_dir / "etc/shadow").write_text(
            "root:*:10770:0:::::\n", encoding="utf-8"
        )

        osutils.Touch(tar_dir / self.creater.DEFAULT_TZ, makedirs=True)
        cros_build_lib.CreateTarball(self.sdk_tarball, tar_dir)

    def testMakeChroot(self):
        """Verify make_chroot invocation."""
        with cros_test_lib.RunCommandMock() as rc_mock:
            rc_mock.SetDefaultCmdResult()
            # pylint: disable=protected-access
            self.creater._make_chroot()
            rc_mock.assertCommandContains(
                [
                    "--chroot",
                    str(self.chroot.path),
                    "--cache_dir",
                    str(self.chroot.cache_dir),
                ]
            )

    def testRun(self):
        """Verify run works."""
        TEST_USER = "a-test-user"
        TEST_UID = 20100908
        TEST_GROUP = "a-test-group"
        TEST_GID = 9082010
        self.PatchObject(cros_sdk_lib.ChrootCreator, "_make_chroot")
        # The files won't be root owned, but they won't be user owned.
        self.ExpectRootOwnedFiles()

        self.creater.run(
            user=TEST_USER, uid=TEST_UID, group=TEST_GROUP, gid=TEST_GID
        )

        # Check various root files.
        self.assertExists(Path(self.chroot.path) / "etc" / "localtime")

        # Check user home files.
        user_file = (
            self.chroot.out_path / "home" / "a-test-user" / ".ssh" / "foo"
        )

        self.assertExists(user_file)
        st = user_file.stat()
        self.assertEqual(st.st_uid, TEST_UID)
        self.assertEqual(st.st_gid, TEST_GID)

        # Check the user/group accounts.
        db = (Path(self.chroot.path) / "etc" / "passwd").read_text(
            encoding="utf-8"
        )
        self.assertStartsWith(db, f"{TEST_USER}:x:{TEST_UID}:{TEST_GID}:")
        # Make sure Python None didn't leak in.
        self.assertNotIn("None", db)
        db = (Path(self.chroot.path) / "etc" / "group").read_text(
            encoding="utf-8"
        )
        self.assertStartsWith(db, f"{TEST_GROUP}:x:{TEST_GID}:{TEST_USER}")
        # Make sure Python None didn't leak in.
        self.assertNotIn("None", db)

        # Check various /etc paths.
        etc = Path(self.chroot.path) / "etc"
        self.assertExists(etc / "mtab")
        self.assertExists(etc / "hosts")
        self.assertExists(etc / "resolv.conf")
        self.assertIn(
            f'PORTAGE_USERNAME="{TEST_USER}"',
            (etc / "env.d" / "99chromiumos").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            "/mnt/host/source/chromite/sdk/etc/bash_completion.d/cros",
            os.readlink(etc / "bash_completion.d" / "cros"),
        )
        self.assertExists(etc / "shadow")

        # Check /mnt/host directories.
        self.assertTrue(
            (Path(self.chroot.path) / "mnt" / "host" / "source").is_dir()
        )
        self.assertTrue(
            (Path(self.chroot.path) / "mnt" / "host" / "out").is_dir()
        )
        self.assertTrue(self.chroot.out_path.is_dir())
        edb_dep_path = Path(
            self.chroot.full_path(Path("/") / "var" / "cache" / "edb" / "dep")
        )
        self.assertTrue(edb_dep_path.is_dir())
        self.assertEqual(edb_dep_path.stat().st_uid, 250)
        self.assertEqual(edb_dep_path.stat().st_gid, 250)

        # Check chroot/var/ directories.
        var = Path(self.chroot.path) / "var"
        # Mount points exist in chroot.
        self.assertTrue((var / "cache").is_dir())
        self.assertTrue((var / "log").is_dir())
        # Sub-directory contents get copied over to out/.
        self.assertTrue(
            (self.chroot.out_path / "sdk" / "logs" / "portage").is_dir()
        )
        self.assertExists(
            self.chroot.out_path / "sdk" / "cache" / "edb" / "counter"
        )

    def testExistingCompatGroup(self):
        """Verify running with an existing, but matching, group works."""
        TEST_USER = "a-test-user"
        TEST_UID = 20100908
        TEST_GROUP = "users"
        TEST_GID = 100
        self.PatchObject(cros_sdk_lib.ChrootCreator, "_make_chroot")
        # The files won't be root owned, but they won't be user owned.
        self.ExpectRootOwnedFiles()

        self.creater.run(
            user=TEST_USER, uid=TEST_UID, group=TEST_GROUP, gid=TEST_GID
        )


class ChrootEnterorTests(cros_test_lib.MockTempDirTestCase):
    """ChrootEnteror tests."""

    def setUp(self):
        chroot_path = self.tempdir / "chroot"
        self.chroot = chroot_lib.Chroot(
            path=chroot_path, cache_dir=self.tempdir / "cache_dir"
        )

        sudo = chroot_path / "usr" / "bin" / "sudo"
        osutils.Touch(sudo, makedirs=True, mode=0o7755)

        # We can't really verify these in any useful way atm.
        self.mount_mock = self.PatchObject(osutils, "Mount")

        self.enteror = cros_sdk_lib.ChrootEnteror(self.chroot, read_only=False)

        self.sysctl_vm_max_map_count = self.tempdir / "vm_max_map_count"
        self.PatchObject(
            cros_sdk_lib.ChrootEnteror,
            "_SYSCTL_VM_MAX_MAP_COUNT",
            self.sysctl_vm_max_map_count,
        )

    def testRun(self):
        """Verify run works."""
        with self.PatchObject(cros_build_lib, "dbg_run"):
            self.enteror.run()

    def testHelperRun(self):
        """Verify helper run API works."""
        with self.PatchObject(cros_build_lib, "dbg_run"):
            cros_sdk_lib.EnterChroot(self.chroot)

    def test_setup_vm_max_map_count(self):
        """Verify _setup_vm_max_map_count works."""
        self.sysctl_vm_max_map_count.write_text("1024", encoding="utf-8")
        self.enteror._setup_vm_max_map_count()
        self.assertEqual(
            int(self.sysctl_vm_max_map_count.read_text(encoding="utf-8")),
            self.enteror._RLIMIT_NOFILE_MIN,
        )


@pytest.fixture(name="chroot_version_file")
def _with_chroot_version_file(monkeypatch, tmp_path: Path):
    """Set CHROOT_VERSION_FILE to the returned temp path.

    The chroot version file is not created, callers expected to write the
    file if that's the desired behavior.
    """
    chroot_version_file = tmp_path / "chroot_version_file"
    monkeypatch.setattr(
        cros_sdk_lib, "CHROOT_VERSION_FILE", str(chroot_version_file)
    )

    yield chroot_version_file


def test_inside_chroot_checks_inside_chroot(chroot_version_file: Path):
    """Test {is|assert}_inside_chroot inside the chroot."""
    chroot_version_file.write_text("123", encoding="utf-8")

    assert cros_sdk_lib.is_inside_chroot()
    cros_sdk_lib.assert_inside_chroot()


def test_outside_chroot_checks_inside_chroot(chroot_version_file: Path):
    """Test {is|assert}_outside_chroot inside the chroot."""
    chroot_version_file.write_text("123", encoding="utf-8")

    assert not cros_sdk_lib.is_outside_chroot()
    with pytest.raises(AssertionError):
        cros_sdk_lib.assert_outside_chroot()


def test_inside_chroot_checks_outside_chroot(chroot_version_file: Path):
    """Test {is|assert}_inside_chroot outside the chroot."""
    assert not chroot_version_file.exists()

    assert not cros_sdk_lib.is_inside_chroot()
    with pytest.raises(AssertionError):
        cros_sdk_lib.assert_inside_chroot()


def test_outside_chroot_checks_outside_chroot(chroot_version_file: Path):
    """Test {is|assert}_outside_chroot outside the chroot."""
    assert not chroot_version_file.exists()

    assert cros_sdk_lib.is_outside_chroot()
    cros_sdk_lib.assert_outside_chroot()


def test_require_inside_decorator_inside_chroot(chroot_version_file: Path):
    """Test require_inside_chroot decorator inside the chroot."""
    chroot_version_file.write_text("123", encoding="utf-8")

    @cros_sdk_lib.require_inside_chroot("Runs")
    def inside():
        pass

    inside()


def test_require_outside_decorator_inside_chroot(chroot_version_file: Path):
    """Test require_outside_chroot decorator inside the chroot."""
    chroot_version_file.write_text("123", encoding="utf-8")

    @cros_sdk_lib.require_outside_chroot("Raises assertion")
    def outside():
        pass

    with pytest.raises(AssertionError):
        outside()


def test_require_inside_decorator_outside_chroot(chroot_version_file: Path):
    """Test require_inside_chroot decorator outside the chroot."""
    assert not chroot_version_file.exists()

    @cros_sdk_lib.require_inside_chroot("Raises assertion")
    def inside():
        pass

    with pytest.raises(AssertionError):
        inside()


def test_require_outside_decorator_outside_chroot(chroot_version_file: Path):
    """Test require_outside_chroot decorator inside the chroot."""
    assert not chroot_version_file.exists()

    @cros_sdk_lib.require_outside_chroot("Runs")
    def outside():
        pass

    outside()


class ChrootWritableTests(cros_test_lib.MockTempDirTestCase):
    """Tests for ChrootReadWrite and ChrootReadOnly context managers."""

    def fake_mount(self, _source, target, _fstype, flags, _data=""):
        if target in self.ro_map:
            ro = flags & osutils.MS_RDONLY != 0
            self.ro_map[target] = ro

    def fake_is_mounted(self, target):
        return target in self.ro_map

    def fake_is_mounted_readonly(self, target):
        return self.ro_map.get(target, False)

    def fake_run_mount(self, *args, **_kwargs):
        mount_options = args[0][4]
        mount_point = args[0][5]
        ro = "rw" not in mount_options.split(",")
        self.ro_map[mount_point] = ro

    def setUp(self):
        self.ro_map = {}

        self.mount_mock = self.PatchObject(
            osutils, "Mount", side_effect=self.fake_mount
        )
        self.is_mounted_mock = self.PatchObject(
            osutils, "IsMounted", side_effect=self.fake_is_mounted
        )
        self.read_only_mock = self.PatchObject(
            osutils,
            "IsMountedReadOnly",
            side_effect=self.fake_is_mounted_readonly,
        )
        self.rc_mock = self.StartPatcher(cros_test_lib.RunCommandMock())
        self.rc_mock.AddCmdResult(
            ["sudo", "--", "mount", "-o", mock.ANY, mock.ANY],
            side_effect=self.fake_run_mount,
        )

    def testReadWrite_BadMount(self):
        """Test with a path that's not mounted."""
        assert not osutils.IsMounted("/some/path")

        with pytest.raises(AssertionError):
            with cros_sdk_lib.ChrootReadWrite("/some/path"):
                pass

        self.mount_mock.assert_not_called()

    def testReadWrite_RenamedMount(self):
        """Test with a path that's modified within the context manager."""
        self.ro_map["/path/to/chroot"] = True
        self.PatchObject(cros_sdk_lib, "IsChrootReady", return_value=True)
        assert osutils.IsMounted("/path/to/chroot")
        assert osutils.IsMountedReadOnly("/path/to/chroot")
        assert not osutils.IsMounted("/")

        with cros_sdk_lib.ChrootReadWrite("/path/to/chroot"):
            assert not osutils.IsMountedReadOnly("/path/to/chroot")

            # Imitate a pivot_root.
            self.ro_map.pop("/path/to/chroot")
            self.ro_map["/"] = False

            assert not osutils.IsMounted("/path/to/chroot")
            assert osutils.IsMounted("/")
            assert not osutils.IsMountedReadOnly("/")

        assert self.mount_mock.call_count == 1
        # We lost track of the changed root mount, but that's the best we can
        # do. We only expect this to happen for the outermost chroot entry, so
        # this leakage should be short-lived (until we tear down the mount
        # namespace).
        assert osutils.IsMounted("/")
        assert not osutils.IsMountedReadOnly("/")

    def testReadWrite_WritableRoot(self):
        """Read-write context when root is already writable."""
        self.ro_map["/"] = False
        assert osutils.IsMounted("/")
        assert not osutils.IsMountedReadOnly("/")

        with cros_sdk_lib.ChrootReadWrite():
            assert not osutils.IsMountedReadOnly("/")

        assert not osutils.IsMountedReadOnly("/")
        self.mount_mock.assert_not_called()

    def testReadWrite_ReadonlyRoot(self):
        """Read-write context when root is read-only."""
        self.ro_map["/"] = True
        assert osutils.IsMounted("/")
        assert osutils.IsMountedReadOnly("/")

        with cros_sdk_lib.ChrootReadWrite():
            assert not osutils.IsMountedReadOnly("/")

        assert osutils.IsMountedReadOnly("/")
        assert self.mount_mock.call_args_list == [
            mock.call(None, "/", None, osutils.MS_REMOUNT | osutils.MS_BIND),
            mock.call(
                None,
                "/",
                None,
                osutils.MS_REMOUNT | osutils.MS_BIND | osutils.MS_RDONLY,
            ),
        ]

    def testReadWrite_Stacked(self):
        """Stacked read/write on a writable root."""
        self.ro_map["/"] = False
        assert osutils.IsMounted("/")
        assert not osutils.IsMountedReadOnly("/")

        with cros_sdk_lib.ChrootReadWrite():
            with cros_sdk_lib.ChrootReadWrite():
                assert not osutils.IsMountedReadOnly("/")
            assert not osutils.IsMountedReadOnly("/")

        assert not osutils.IsMountedReadOnly("/")
        self.mount_mock.assert_not_called()

    def testReadWrite_StackedReadOnly(self):
        """Stacked read/write on a read-only root."""
        self.ro_map["/"] = True
        assert osutils.IsMounted("/")
        assert osutils.IsMountedReadOnly("/")

        with cros_sdk_lib.ChrootReadWrite():
            with cros_sdk_lib.ChrootReadWrite():
                assert not osutils.IsMountedReadOnly("/")
            assert not osutils.IsMountedReadOnly("/")

        assert osutils.IsMountedReadOnly("/")
        assert self.mount_mock.call_count == 2

    def testReadOnly_BadMount(self):
        """Test with a path that's not mounted."""
        assert not osutils.IsMounted("/some/path")

        with pytest.raises(AssertionError):
            with cros_sdk_lib.ChrootReadOnly("/some/path"):
                pass

        self.mount_mock.assert_not_called()

    def testReadOnly_ReadOnlyRoot(self):
        """Read-only context when root is already read-only."""
        self.ro_map["/"] = True
        assert osutils.IsMounted("/")
        assert osutils.IsMountedReadOnly("/")

        with cros_sdk_lib.ChrootReadOnly():
            assert osutils.IsMountedReadOnly("/")

        assert osutils.IsMountedReadOnly("/")
        self.mount_mock.assert_not_called()

    def testReadOnly_WritableRoot(self):
        """Read-only context when root is read/write."""
        self.ro_map["/"] = False
        assert osutils.IsMounted("/")
        assert not osutils.IsMountedReadOnly("/")

        with cros_sdk_lib.ChrootReadOnly():
            assert osutils.IsMountedReadOnly("/")

        assert not osutils.IsMountedReadOnly("/")
        assert self.mount_mock.call_args_list == [
            mock.call(
                None,
                "/",
                None,
                osutils.MS_REMOUNT | osutils.MS_BIND | osutils.MS_RDONLY,
            ),
            mock.call(
                None,
                "/",
                None,
                osutils.MS_REMOUNT | osutils.MS_BIND,
            ),
        ]

    def testReadOnly_Stacked(self):
        """Stacked read-only on a read-only root."""
        self.ro_map["/"] = True
        assert osutils.IsMounted("/")
        assert osutils.IsMountedReadOnly("/")

        with cros_sdk_lib.ChrootReadOnly():
            with cros_sdk_lib.ChrootReadOnly():
                assert osutils.IsMountedReadOnly("/")
            assert osutils.IsMountedReadOnly("/")

        assert osutils.IsMountedReadOnly("/")
        self.mount_mock.assert_not_called()

    def testReadOnly_StackedWritable(self):
        """Stacked read-only on a writable root."""
        self.ro_map["/"] = False
        assert osutils.IsMounted("/")
        assert not osutils.IsMountedReadOnly("/")

        with cros_sdk_lib.ChrootReadOnly():
            with cros_sdk_lib.ChrootReadOnly():
                assert osutils.IsMountedReadOnly("/")
            assert osutils.IsMountedReadOnly("/")

        assert not osutils.IsMountedReadOnly("/")
        assert self.mount_mock.call_count == 2

    def testStacked_WriteRead(self):
        """Stacked writable and read-only."""
        self.ro_map["/"] = True
        assert osutils.IsMounted("/")
        assert osutils.IsMountedReadOnly("/")

        with cros_sdk_lib.ChrootReadWrite():
            assert not osutils.IsMountedReadOnly("/")
            with cros_sdk_lib.ChrootReadOnly():
                assert osutils.IsMountedReadOnly("/")
            assert not osutils.IsMountedReadOnly("/")

        assert osutils.IsMountedReadOnly("/")
        assert self.mount_mock.call_count == 4

    def testStacked_ReadWrite(self):
        """Stacked read-only and writable."""
        self.ro_map["/"] = False
        assert osutils.IsMounted("/")
        assert not osutils.IsMountedReadOnly("/")

        with cros_sdk_lib.ChrootReadOnly():
            assert osutils.IsMountedReadOnly("/")
            with cros_sdk_lib.ChrootReadWrite():
                assert not osutils.IsMountedReadOnly("/")
            assert osutils.IsMountedReadOnly("/")

        assert not osutils.IsMountedReadOnly("/")
        assert self.mount_mock.call_count == 4

    def testNonRoot(self):
        """Test the non-root flow."""

        def non_root_mount(self, *args):
            raise PermissionError("Fake Mount permission failure")

        self.PatchObject(osutils, "Mount", side_effect=non_root_mount)

        self.ro_map["/"] = True
        assert osutils.IsMounted("/")
        assert osutils.IsMountedReadOnly("/")

        with cros_sdk_lib.ChrootReadOnly():
            assert osutils.IsMountedReadOnly("/")

        with cros_sdk_lib.ChrootReadWrite():
            assert not osutils.IsMountedReadOnly("/")

        self.rc_mock.assertCommandContains(
            ["sudo", "--", "mount", "-o", "remount,bind,rw", "/"],
        )
        self.rc_mock.assertCommandContains(
            ["sudo", "--", "mount", "-o", "remount,bind,ro", "/"],
        )
        assert self.rc_mock.call_count == 2
        assert osutils.IsMountedReadOnly("/")
