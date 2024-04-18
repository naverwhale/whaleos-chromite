# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for the binhost.py service."""

import os
from pathlib import Path
import time

import pytest

from chromite.lib import binpkg
from chromite.lib import build_target_lib
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import git
from chromite.lib import osutils
from chromite.lib import parallel_unittest
from chromite.lib import portage_util
from chromite.lib import repo_util
from chromite.lib import sysroot_lib
from chromite.service import binhost
from chromite.utils import gs_urls_util


class GetPrebuiltAclArgsTest(cros_test_lib.MockTempDirTestCase):
    """GetPrebuiltAclArgs tests."""

    _ACL_FILE = """
# Comment
-g group1:READ

# Another Comment
-u user:FULL_CONTROL # EOL Comment



# Comment # Comment
-g group2:READ
"""

    def setUp(self):
        self.build_target = build_target_lib.BuildTarget("board")
        self.acl_file = os.path.join(self.tempdir, "googlestorage_acl.txt")
        osutils.WriteFile(self.acl_file, self._ACL_FILE)

    def testParse(self):
        """Test parsing a valid file."""
        self.PatchObject(
            portage_util, "FindOverlayFile", return_value=self.acl_file
        )

        expected_acls = [
            ["-g", "group1:READ"],
            ["-u", "user:FULL_CONTROL"],
            ["-g", "group2:READ"],
        ]

        acls = binhost.GetPrebuiltAclArgs(self.build_target)

        self.assertCountEqual(expected_acls, acls)

    def testNoFile(self):
        """Test no file handling."""
        self.PatchObject(portage_util, "FindOverlayFile", return_value=None)

        with self.assertRaises(binhost.NoAclFileFound):
            binhost.GetPrebuiltAclArgs(self.build_target)


class SetBinhostTest(cros_test_lib.MockTempDirTestCase):
    """Unittests for SetBinhost."""

    def setUp(self):
        self.PatchObject(constants, "SOURCE_ROOT", new=self.tempdir)

        self.public_conf_dir = os.path.join(
            self.tempdir, constants.PUBLIC_BINHOST_CONF_DIR, "target"
        )
        osutils.SafeMakedirs(self.public_conf_dir)

        self.private_conf_dir = os.path.join(
            self.tempdir, constants.PRIVATE_BINHOST_CONF_DIR, "target"
        )
        osutils.SafeMakedirs(self.private_conf_dir)

    def tearDown(self):
        osutils.EmptyDir(self.tempdir)

    def testSetBinhostPublic(self):
        """SetBinhost returns correct public path and updates conf file."""
        actual = binhost.SetBinhost(
            "coral", "BINHOST_KEY", "gs://prebuilts", private=False
        )
        expected = os.path.join(self.public_conf_dir, "coral-BINHOST_KEY.conf")
        self.assertEqual(actual, expected)
        self.assertEqual(
            osutils.ReadFile(actual), 'BINHOST_KEY="gs://prebuilts"'
        )

    def testSetBinhostPrivate(self):
        """SetBinhost returns correct private path and updates conf file."""
        actual = binhost.SetBinhost("coral", "BINHOST_KEY", "gs://prebuilts")
        expected = os.path.join(self.private_conf_dir, "coral-BINHOST_KEY.conf")
        self.assertEqual(actual, expected)
        self.assertEqual(
            osutils.ReadFile(actual), 'BINHOST_KEY="gs://prebuilts"'
        )

    def testSetBinhostEmptyConf(self):
        """SetBinhost rejects existing but empty conf files."""
        conf_path = os.path.join(
            self.private_conf_dir, "multi-BINHOST_KEY.conf"
        )
        osutils.WriteFile(conf_path, " ")
        with self.assertRaises(ValueError):
            binhost.SetBinhost("multi", "BINHOST_KEY", "gs://blah")

    def testSetBinhostMultilineConf(self):
        """SetBinhost rejects existing multiline conf files."""
        conf_path = os.path.join(
            self.private_conf_dir, "multi-BINHOST_KEY.conf"
        )
        osutils.WriteFile(conf_path, "\n".join(['A="foo"', 'B="bar"']))
        with self.assertRaises(ValueError):
            binhost.SetBinhost("multi", "BINHOST_KEY", "gs://blah")

    def testSetBinhhostBadConfLine(self):
        """SetBinhost rejects existing conf files with malformed lines."""
        conf_path = os.path.join(self.private_conf_dir, "bad-BINHOST_KEY.conf")
        osutils.WriteFile(conf_path, "bad line")
        with self.assertRaises(ValueError):
            binhost.SetBinhost("bad", "BINHOST_KEY", "gs://blah")

    def testSetBinhostMismatchedKey(self):
        """SetBinhost rejects existing conf files with a mismatched key."""
        conf_path = os.path.join(self.private_conf_dir, "bad-key-GOOD_KEY.conf")
        osutils.WriteFile(conf_path, 'BAD_KEY="https://foo.bar"')
        with self.assertRaises(KeyError):
            binhost.SetBinhost("bad-key", "GOOD_KEY", "gs://blah")

    def testSetBinhostMaxURIsIncrease(self):
        """SetBinhost appends uri in BINHOST conf file."""
        binhost.SetBinhost("coral", "BINHOST_KEY", "gs://prebuilts", max_uris=1)
        actual = binhost.SetBinhost(
            "coral", "BINHOST_KEY", "gs://prebuilts2", max_uris=2
        )
        self.assertEqual(
            osutils.ReadFile(actual),
            'BINHOST_KEY="gs://prebuilts gs://prebuilts2"',
        )

    def testSetBinhostMaxURIsRemoveOldest(self):
        """Setbinhost appends only maximum # uris and removes in FIFO order."""
        binhost.SetBinhost(
            "coral", "BINHOST_KEY", "gs://prebuilts1", max_uris=1
        )
        binhost.SetBinhost(
            "coral", "BINHOST_KEY", "gs://prebuilts2", max_uris=3
        )
        binhost.SetBinhost(
            "coral", "BINHOST_KEY", "gs://prebuilts3", max_uris=3
        )
        actual = binhost.SetBinhost(
            "coral", "BINHOST_KEY", "gs://prebuilts4", max_uris=3
        )
        self.assertEqual(
            osutils.ReadFile(actual),
            'BINHOST_KEY="gs://prebuilts2 gs://prebuilts3 gs://prebuilts4"',
        )

        actual = binhost.SetBinhost(
            "coral", "BINHOST_KEY", "gs://prebuilts5", max_uris=1
        )
        self.assertEqual(
            osutils.ReadFile(actual), 'BINHOST_KEY="gs://prebuilts5"'
        )

    def testSetBinhostInvalidMaxUris(self):
        """SetBinhost rejects invalid max_uris"""
        with self.assertRaises(binhost.InvalidMaxUris):
            binhost.SetBinhost(
                "coral", "BINHOST_KEY", "gs://prebuilts", max_uris=0
            )
        with self.assertRaises(binhost.InvalidMaxUris):
            binhost.SetBinhost(
                "coral", "BINHOST_KEY", "gs://prebuilts", max_uris=-1
            )
        with self.assertRaises(binhost.InvalidMaxUris):
            binhost.SetBinhost(
                "coral", "BINHOST_KEY", "gs://prebuilts", max_uris=None
            )


class GetBinhostConfPathTest(cros_test_lib.MockTempDirTestCase):
    """Unittests for GetBinhostConfPath."""

    def setUp(self):
        self.PatchObject(constants, "SOURCE_ROOT", new=self.tempdir)

        self.public_conf_dir = (
            Path(self.tempdir) / constants.PUBLIC_BINHOST_CONF_DIR / "target"
        )
        self.private_conf_dir = (
            Path(self.tempdir) / constants.PRIVATE_BINHOST_CONF_DIR / "target"
        )

    def testGetBinhostConfPathPublic(self):
        """GetBinhostConfPath returns correct public conf path."""
        expected = self.public_conf_dir / "coral-BINHOST_KEY.conf"
        actual = binhost.GetBinhostConfPath("coral", "BINHOST_KEY", False)
        self.assertEqual(actual, expected)

    def testGetBinhostConfPathPrivate(self):
        """GetBinhostConfPath returns correct private conf path."""
        expected = self.private_conf_dir / "coral-BINHOST_KEY.conf"
        actual = binhost.GetBinhostConfPath("coral", "BINHOST_KEY", True)
        self.assertEqual(actual, expected)


class GetPrebuiltsRootTest(cros_test_lib.MockTempDirTestCase):
    """Unittests for GetPrebuiltsRoot."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        self.PatchObject(constants, "SOURCE_ROOT", new=self.tempdir)
        self.sysroot_path = "/build/foo"

        self.chroot = chroot_lib.Chroot(
            path=self.tempdir / "chroot",
            out_path=self.tempdir / "out",
        )
        self.sysroot = sysroot_lib.Sysroot(self.sysroot_path)
        self.build_target = build_target_lib.BuildTarget("foo")

        self.root = self.chroot.full_path(self.sysroot.JoinPath("packages"))
        osutils.SafeMakedirs(self.root)

    def testGetPrebuiltsRoot(self):
        """GetPrebuiltsRoot returns correct root for given build target."""
        actual = binhost.GetPrebuiltsRoot(
            self.chroot, self.sysroot, self.build_target
        )
        self.assertEqual(actual, self.root)

    def testGetPrebuiltsBadTarget(self):
        """GetPrebuiltsRoot dies on missing root (target probably not built.)"""
        with self.assertRaises(binhost.EmptyPrebuiltsRoot):
            binhost.GetPrebuiltsRoot(
                self.chroot,
                sysroot_lib.Sysroot("/build/bar"),
                build_target_lib.BuildTarget("bar"),
            )


class GetPrebuiltsFilesTest(cros_test_lib.MockTempDirTestCase):
    """Unittests for GetPrebuiltsFiles."""

    def setUp(self):
        self.PatchObject(constants, "SOURCE_ROOT", new=str(self.tempdir))
        self.root = self.tempdir / "chroot/build/target/packages"
        osutils.SafeMakedirs(self.root)

    def testGetPrebuiltsFiles(self):
        """GetPrebuiltsFiles returns all archives for all packages."""
        packages_content = """\
ARCH: amd64
URI: gs://foo_prebuilts

CPV: package/prebuilt_a

CPV: package/prebuilt_b
    """
        osutils.WriteFile(os.path.join(self.root, "Packages"), packages_content)
        osutils.WriteFile(
            os.path.join(self.root, "package/prebuilt_a.tbz2"),
            "a",
            makedirs=True,
        )
        osutils.WriteFile(
            os.path.join(self.root, "package/prebuilt_b.tbz2"), "b"
        )

        actual = binhost.GetPrebuiltsFiles(self.root)
        expected = ["package/prebuilt_a.tbz2", "package/prebuilt_b.tbz2"]
        self.assertEqual(actual, expected)

    def testGetPrebuiltsFilesWithDebugSymbols(self):
        """GetPrebuiltsFiles returns debug symbols archive if set in index."""
        packages_content = """\
ARCH: amd64
URI: gs://foo_prebuilts

CPV: package/prebuilt
DEBUG_SYMBOLS: yes
    """
        osutils.WriteFile(os.path.join(self.root, "Packages"), packages_content)
        osutils.WriteFile(
            os.path.join(self.root, "package/prebuilt.tbz2"),
            "foo",
            makedirs=True,
        )
        osutils.WriteFile(
            os.path.join(self.root, "package/prebuilt.debug.tbz2"),
            "debug",
            makedirs=True,
        )

        actual = binhost.GetPrebuiltsFiles(self.root)
        expected = ["package/prebuilt.tbz2", "package/prebuilt.debug.tbz2"]
        self.assertEqual(actual, expected)

    def testGetPrebuiltsFilesBadFile(self):
        """GetPrebuiltsFiles dies if archive file does not exist."""
        packages_content = """\
ARCH: amd64
URI: gs://foo_prebuilts

CPV: package/prebuilt
    """
        osutils.WriteFile(os.path.join(self.root, "Packages"), packages_content)

        with self.assertRaises(LookupError):
            binhost.GetPrebuiltsFiles(self.root)

    def testPrebuiltsDeduplication(self):
        """GetPrebuiltsFiles returns all archives for all packages."""
        now = int(time.time())
        # As of time of writing it checks for no older than 2 weeks. We just
        # need to be newer than that, but older than the new time, so just knock
        # off a few seconds.
        old_time = now - 5

        packages_content = f"""\
ARCH: amd64
URI: gs://foo_prebuilts

CPV: category/package_a
SHA1: 02b0a68a347e39c6d7be3c987022c134e4ba75e5
MTIME: {now}
PATH: category/package_a.tbz2

CPV: category/package_b
"""

        old_packages_content = f"""\
ARCH: amd64
URI: gs://foo_prebuilts

CPV: category/package_a
SHA1: 02b0a68a347e39c6d7be3c987022c134e4ba75e5
MTIME: {old_time}
PATH: old_binhost/category/package_a.tbz2
"""

        old_binhost = self.tempdir / "old_packages"
        old_package_index = old_binhost / "Packages"
        osutils.WriteFile(
            old_package_index, old_packages_content, makedirs=True
        )
        osutils.WriteFile(self.root / "Packages", packages_content)
        osutils.WriteFile(
            self.root / "category/package_a.tbz2",
            "a",
            makedirs=True,
        )
        osutils.WriteFile(
            self.root / "category/package_b.tbz2",
            "b",
            makedirs=True,
        )

        actual = binhost.GetPrebuiltsFiles(self.root, [old_package_index])
        # package_a should be deduped, so only package_b is left.
        expected = ["category/package_b.tbz2"]
        self.assertEqual(expected, actual)

        # Verify the deduplication was persisted to the index.
        pkg_index = binpkg.PackageIndex()
        pkg_index.ReadFilePath(self.root / "Packages")
        self.assertEqual(
            pkg_index.packages[0]["PATH"], "old_binhost/category/package_a.tbz2"
        )


class UpdatePackageIndexTest(cros_test_lib.MockTempDirTestCase):
    """Unittests for UpdatePackageIndex."""

    def setUp(self):
        self.PatchObject(constants, "SOURCE_ROOT", new=self.tempdir)
        self.root = os.path.join(self.tempdir, "chroot/build/target/packages")
        osutils.SafeMakedirs(self.root)

    def testAbsoluteUploadPath(self):
        """Test UpdatePackageIndex raises an error for absolute paths."""
        with self.assertRaises(AssertionError):
            binhost.UpdatePackageIndex(
                self.root, "gs://chromeos-prebuilt", "/target"
            )

    def testUpdatePackageIndex(self):
        """UpdatePackageIndex writes updated file to disk."""
        packages_content = """\
ARCH: amd64
TTL: 0

CPV: package/prebuilt
    """
        osutils.WriteFile(os.path.join(self.root, "Packages"), packages_content)

        binhost.UpdatePackageIndex(
            self.root, "gs://chromeos-prebuilt", "target/"
        )

        actual = binpkg.GrabLocalPackageIndex(self.root)
        self.assertEqual(actual.header["URI"], "gs://chromeos-prebuilt")
        self.assertEqual(int(actual.header["TTL"]), 60 * 60 * 24 * 365)
        self.assertEqual(
            actual.packages,
            [
                {
                    "CPV": "package/prebuilt",
                    "PATH": "target/package/prebuilt.tbz2",
                }
            ],
        )


class RegenBuildCacheTest(cros_test_lib.MockTempDirTestCase):
    """Unittests for RegenBuildCache."""

    def testCallsRegenPortageCache(self):
        """Test that overlays=None works."""
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        chroot = chroot_lib.Chroot(
            path=self.tempdir / "chroot", out_path=self.tempdir / "out"
        )
        osutils.SafeMakedirs(chroot.tmp)
        overlays_found = [chroot.full_path("/path/to")]
        for o in overlays_found:
            osutils.SafeMakedirs(o)
        self.PatchObject(
            portage_util, "FindOverlays", return_value=overlays_found
        )

        with parallel_unittest.ParallelMock():
            binhost.RegenBuildCache(chroot, constants.PUBLIC_OVERLAYS)


class ReadDevInstallPackageFileTest(cros_test_lib.MockTempDirTestCase):
    """Unittests for ReadDevInstallPackageFile."""

    def setUp(self):
        self.root = os.path.join(
            self.tempdir, "chroot/build/target/build/dev-install/"
        )
        self.packages_file = os.path.join(self.root, "package.installable")
        osutils.SafeMakedirs(self.root)
        package_file_content = """\
x11-apps/intel-gpu-tools-1.22
x11-libs/gdk-pixbuf-2.36.12-r1
x11-misc/read-edid-1.4.2
virtual/acl-0-r1
"""
        osutils.WriteFile(self.packages_file, package_file_content)

    def testReadDevInstallPackageFile(self):
        """Test that parsing valid file works."""
        packages = binhost.ReadDevInstallPackageFile(self.packages_file)
        expected_packages = [
            "x11-apps/intel-gpu-tools-1.22",
            "x11-libs/gdk-pixbuf-2.36.12-r1",
            "x11-misc/read-edid-1.4.2",
            "virtual/acl-0-r1",
        ]
        self.assertEqual(packages, expected_packages)


class CreateDevInstallPackageFileTest(cros_test_lib.MockTempDirTestCase):
    """Unittests for CreateDevInstallPackageFile."""

    def setUp(self):
        self.PatchObject(constants, "SOURCE_ROOT", new=self.tempdir)
        self.root = os.path.join(self.tempdir, "chroot/build/target/packages")
        osutils.SafeMakedirs(self.root)
        self.devinstall_package_list = ["virtual/python-enum34-1"]
        self.devinstall_packages_filename = os.path.join(
            self.root, "package.installable"
        )
        packages_content = """\
ARCH: amd64
TTL: 0

CPV: package/prebuilt

CPV: virtual/python-enum34-1

    """
        osutils.WriteFile(os.path.join(self.root, "Packages"), packages_content)

        devinstall_packages_content = """\
virtual/python-enum34-1
    """
        osutils.WriteFile(
            self.devinstall_packages_filename, devinstall_packages_content
        )
        self.upload_dir = os.path.join(self.root, "upload_dir")
        osutils.SafeMakedirs(self.upload_dir)
        self.upload_packages_file = os.path.join(self.upload_dir, "Packages")

    def testCreateFilteredPackageIndex(self):
        """CreateDevInstallPackageFile writes updated file to disk."""
        binhost.CreateFilteredPackageIndex(
            self.root,
            self.devinstall_package_list,
            self.upload_packages_file,
            "gs://chromeos-prebuilt",
            "target/",
        )

        # We need to verify that a file was created at
        # self.devinstall_package_list
        actual = binpkg.GrabLocalPackageIndex(self.upload_dir)
        self.assertEqual(actual.header["URI"], "gs://chromeos-prebuilt")
        self.assertEqual(int(actual.header["TTL"]), 60 * 60 * 24 * 365)
        self.assertEqual(
            actual.packages,
            [
                {
                    "CPV": "virtual/python-enum34-1",
                    "PATH": "target/virtual/python-enum34-1.tbz2",
                }
            ],
        )


class CreateChromePackageIndexTest(cros_test_lib.MockTempDirTestCase):
    """Unittests for CreateChromePackageIndex."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        self.chroot = chroot_lib.Chroot(
            path=self.tempdir / "chroot",
            out_path=self.tempdir / "out",
        )
        self.sysroot_path = Path("/build/foo")
        self.pkgs_dir = self.sysroot_path / "packages"
        self.sysroot = sysroot_lib.Sysroot(self.sysroot_path)

        packages_content = """\
ARCH: amd64
TTL: 0

CPV: package/exclude-1

CPV: chromeos-base/chromeos-chrome-100.0.0-r1

CPV: chromeos-base/chromeos-lacros-100.0.0-r1

CPV: chromeos-base/chrome-icu-100.0.0-r1

CPV: package/exclude-2
    """
        package_index_file_path = self.chroot.full_path(
            self.pkgs_dir / "Packages"
        )
        osutils.Touch(package_index_file_path, makedirs=True)
        osutils.WriteFile(package_index_file_path, packages_content)

        self.upload_dir = Path(self.chroot.tmp) / "upload_dir"
        osutils.SafeMakedirs(self.upload_dir)
        self.upload_packages_file = self.upload_dir / "Packages"

        self.PatchObject(os.path, "exists", return_value=True)
        self.fake_packages = [
            portage_util.InstalledPackage(
                None, "", category="package", pf="exclude-1"
            ),
            portage_util.InstalledPackage(
                None,
                "",
                category=constants.CHROME_CN,
                pf="chromeos-chrome-100.0.0-r1",
            ),
            portage_util.InstalledPackage(
                None,
                "",
                category=constants.CHROME_CN,
                pf="chromeos-lacros-100.0.0-r1",
            ),
            portage_util.InstalledPackage(
                None,
                "",
                category=constants.CHROME_CN,
                pf="chrome-icu-100.0.0-r1",
            ),
            portage_util.InstalledPackage(
                None, "", category="package", pf="exclude-2"
            ),
        ]
        self.PatchObject(
            portage_util.PortageDB,
            "InstalledPackages",
            return_value=self.fake_packages,
        )

    def testCreateChromePackageIndex(self):
        """CreateChromePackageIndex writes updated file to disk."""
        actual_packages = binhost.CreateChromePackageIndex(
            self.chroot,
            self.sysroot,
            self.upload_packages_file,
            "gs://chromeos-prebuilt",
            "target/",
        )
        actual_packages_content = osutils.ReadFile(
            self.upload_packages_file
        ).splitlines()

        self.assertEqual(
            [
                "chromeos-base/chromeos-chrome-100.0.0-r1.tbz2",
                "chromeos-base/chromeos-lacros-100.0.0-r1.tbz2",
                "chromeos-base/chrome-icu-100.0.0-r1.tbz2",
            ],
            actual_packages,
        )
        self.assertIn(
            "CPV: chromeos-base/chromeos-chrome-100.0.0-r1",
            actual_packages_content,
        )
        self.assertIn(
            "PATH: target/chromeos-base/chromeos-chrome-100.0.0-r1.tbz2",
            actual_packages_content,
        )
        self.assertIn(
            "CPV: chromeos-base/chromeos-lacros-100.0.0-r1",
            actual_packages_content,
        )
        self.assertIn(
            "PATH: target/chromeos-base/chromeos-lacros-100.0.0-r1.tbz2",
            actual_packages_content,
        )
        self.assertIn(
            "CPV: chromeos-base/chrome-icu-100.0.0-r1", actual_packages_content
        )
        self.assertIn(
            "PATH: target/chromeos-base/chrome-icu-100.0.0-r1.tbz2",
            actual_packages_content,
        )
        self.assertNotIn("CPV: package/exclude-1", actual_packages_content)
        self.assertNotIn("CPV: package/exclude-2", actual_packages_content)


class LookupBinhostsTest(
    cros_test_lib.MockTempDirTestCase, cros_test_lib.LoggingTestCase
):
    """Unittests for lookup_binhosts."""

    def setUp(self):
        self.find_repo_mock = self.PatchObject(repo_util.Repository, "MustFind")
        self.has_remote_mock = (
            self.find_repo_mock.return_value.Manifest.return_value.HasRemote
        )
        self.git_log_mock = self.PatchObject(git, "Log")
        self.source_root_mock = self.PatchObject(
            constants, "SOURCE_ROOT", new=self.tempdir
        )

    def testInternalSuccess(self):
        """Test basic internal success case."""
        self.has_remote_mock.side_effect = (False, True)
        self.git_log_mock.side_effect = (
            "",
            "internal-snapshot-sha1\ninternal-snapshot-sha2",
        )

        result = binhost.lookup_binhosts()

        self.git_log_mock.assert_called_with(
            os.path.join(self.tempdir, "manifest-internal"),
            format="format:%H",
            max_count=10,
            rev="cros-internal/snapshot",
        )
        self.assertEqual(
            ["internal-snapshot-sha1", "internal-snapshot-sha2"],
            result.internal,
        )
        self.assertEqual([], result.external)

    def testExternalSuccess(self):
        """Test basic external success case."""
        self.has_remote_mock.side_effect = (True, False)
        self.git_log_mock.side_effect = (
            "external-snapshot-sha1\nexternal-snapshot-sha2",
            "",
        )

        result = binhost.lookup_binhosts()

        self.git_log_mock.assert_called_with(
            os.path.join(self.tempdir, "manifest"),
            format="format:%H",
            max_count=10,
            rev="cros/snapshot",
        )
        self.assertEqual(
            ["external-snapshot-sha1", "external-snapshot-sha2"],
            result.external,
        )
        self.assertEqual([], result.internal)

    def testGetSnapshotShasRepoError(self):
        """Test repo error when getting snapshot SHAs."""
        with cros_test_lib.LoggingCapturer() as logs:
            self.find_repo_mock.side_effect = repo_util.NotInRepoError()

            result = binhost.lookup_binhosts()

            self.AssertLogsContain(logs, "Unable to determine a repo directory")
            self.assertEqual([], result.external)
            self.assertEqual([], result.internal)

    def testGetSnapshotShasGitError(self):
        """Test git error when getting snapshot SHAs."""
        with cros_test_lib.LoggingCapturer() as logs:
            self.git_log_mock.side_effect = cros_build_lib.RunCommandError(
                "Run Command Error."
            )

            result = binhost.lookup_binhosts()

            self.AssertLogsContain(logs, "Run Command Error.")
            self.assertEqual([], result.external)
            self.assertEqual([], result.internal)


@pytest.mark.parametrize(
    "uri,expected",
    [
        ("gs://garbage", f"{gs_urls_util.PUBLIC_BASE_HTTPS_URL}garbage"),
        (
            "gs://chromeos-dev-installer",
            f"{gs_urls_util.PUBLIC_BASE_HTTPS_URL}chromeos-dev-installer",
        ),
        ("https://google.com", "https://google.com"),
        (
            f"{gs_urls_util.PUBLIC_BASE_HTTPS_URL}chromeos-dev-installer",
            f"{gs_urls_util.PUBLIC_BASE_HTTPS_URL}chromeos-dev-installer",
        ),
    ],
)
def test_convert_gs_upload_uri(uri, expected):
    """Ensure we're converting gs:// URIs to https:// in an expected way."""
    assert binhost.ConvertGsUploadUri(uri) == expected
