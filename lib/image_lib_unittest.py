# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the image_lib module."""

import collections
import gc
import glob
import os
from pathlib import Path
import stat
from unittest import mock

from chromite.lib import chromeos_version
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import git
from chromite.lib import image_lib
from chromite.lib import install_mask
from chromite.lib import osutils
from chromite.lib import partial_mock
from chromite.lib import portage_util
from chromite.lib import retry_util
from chromite.utils import c_loop
from chromite.utils import os_util


# pylint: disable=protected-access


class FakeException(Exception):
    """Fake exception used for testing exception handling."""


FAKE_PATH = "/imaginary/file"
LOOP_DEV = "/dev/loop9999"
LOOP_PART_COUNT = 12
LOOP_PARTITION_INFO = [
    image_lib.PartitionInfo(1, 2928640, 28672, "", "STATE"),
    image_lib.PartitionInfo(2, 20480, 32768, "", "KERN-A"),
    image_lib.PartitionInfo(3, 286720, 2641920, "", "ROOT-A"),
    image_lib.PartitionInfo(4, 53248, 32768, "", "KERN-B"),
    image_lib.PartitionInfo(5, 282624, 4096, "", "ROOT-B"),
    image_lib.PartitionInfo(6, 16448, 1, "", "KERN-C"),
    image_lib.PartitionInfo(7, 16449, 1, "", "ROOT-C"),
    image_lib.PartitionInfo(8, 86016, 32768, "", "OEM"),
    image_lib.PartitionInfo(9, 16450, 1, "", "reserved"),
    image_lib.PartitionInfo(10, 16451, 1, "", "reserved"),
    image_lib.PartitionInfo(11, 64, 16384, "", "RWFW"),
    image_lib.PartitionInfo(12, 249856, 32768, "", "EFI-SYSTEM"),
]
LOOP_PARTS_DICT = {
    p.number: "%sp%d" % (LOOP_DEV, p.number) for p in LOOP_PARTITION_INFO
}
LOOP_PARTS_LIST = LOOP_PARTS_DICT.values()
FAKE_DATE_STRING = "2022_07_20_203326"


class LoopbackPartitionsMock(image_lib.LoopbackPartitions):
    """Mocked loopback partition class to use in unit tests."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enable_rw_called = set()
        self.disable_rw_called = set()

    def _InitGpt(self):
        """Initialize the GPT info."""
        self._gpt_table = LOOP_PARTITION_INFO

    def Attach(self):
        """Initialize the loopback device."""
        self.dev = LOOP_DEV
        if not self.destination:
            self.destination = osutils.TempDir()
        self.parts = {
            p.number: "%sp%s" % (self.dev, p.number) for p in self._gpt_table
        }

    def EnableRwMount(self, part_id, offset=0):
        """Stub out enable rw mount."""
        self.enable_rw_called.add((part_id, offset))

    def DisableRwMount(self, part_id, offset=0):
        """Stub out disable rw mount."""
        self.disable_rw_called.add((part_id, offset))

    def _Mount(self, part, mount_opts):
        """Stub out mount operations."""
        dest_number, _ = self._GetMountPointAndSymlink(part)
        # Don't actually even try to mount it.
        self._mounted.add(part)
        return dest_number

    def _Unmount(self, part):
        """Stub out unmount operations."""
        self._mounted.remove(part)

    def close(self):
        pass


class LoopbackPartitionsTest(cros_test_lib.MockTempDirTestCase):
    """Test the loopback partitions class"""

    def setUp(self):
        self.rc_mock = cros_test_lib.RunCommandMock()
        self.StartPatcher(self.rc_mock)
        self.rc_mock.SetDefaultCmdResult()
        self.rc_mock.AddCmdResult(partial_mock.In("--show"), stdout=LOOP_DEV)

        self.PatchObject(
            image_lib,
            "GetImageDiskPartitionInfo",
            return_value=LOOP_PARTITION_INFO,
        )
        self.PatchObject(glob, "glob", return_value=LOOP_PARTS_LIST)
        self.mount_mock = self.PatchObject(osutils, "MountDir")
        self.umount_mock = self.PatchObject(osutils, "UmountDir")
        self.retry_mock = self.PatchObject(retry_util, "RetryException")
        self.addpart_mock = self.PatchObject(
            image_lib.LoopbackPartitions, "_AddPartitions"
        )
        self.delpart_mock = self.PatchObject(
            image_lib.LoopbackPartitions, "_DeletePartitions"
        )
        self.detach_mock = self.PatchObject(c_loop, "detach")

        def fake_which(val, *_arg, **_kwargs):
            return val

        self.PatchObject(osutils, "Which", side_effect=fake_which)

        # Patch osutils.IsRootUser() to pretend running as root so we attempt to
        # do all the setup directly instead of falling back to our sudo helper.
        self.PatchObject(os_util, "is_root_user", return_value=True)

    def testContextManager(self):
        """Test using the loopback class as a context manager."""
        with image_lib.LoopbackPartitions(FAKE_PATH) as lb:
            self.rc_mock.assertCommandContains(
                ["losetup", "--show", "-f", FAKE_PATH]
            )
            self.delpart_mock.assert_called_once()
            self.delpart_mock.reset_mock()
            self.addpart_mock.assert_called_once()
            self.detach_mock.assert_not_called()
            self.assertEqual(lb.parts, LOOP_PARTS_DICT)
            self.assertEqual(lb._gpt_table, LOOP_PARTITION_INFO)
        self.delpart_mock.assert_called_once()
        self.detach_mock.assert_called_once()

    def testContextManagerWithMounts(self):
        """Test using the loopback class as a context manager with mounts."""
        syml = self.PatchObject(osutils, "SafeSymlink")
        part_ids = (1, "ROOT-A")
        with image_lib.LoopbackPartitions(
            FAKE_PATH, part_ids=part_ids, mount_opts=("ro",)
        ) as lb:
            expected_mounts = set()
            expected_calls = []
            for part_id in part_ids:
                for part in LOOP_PARTITION_INFO:
                    if part_id in (part.name, part.number):
                        expected_mounts.add(part)
                        expected_calls.append(
                            mock.call(
                                "dir-%d" % part.number,
                                os.path.join(
                                    lb.destination, "dir-%s" % part.name
                                ),
                            )
                        )
                        break
            self.rc_mock.assertCommandContains(
                ["losetup", "--show", "-f", FAKE_PATH]
            )
            self.delpart_mock.assert_called_once()
            self.delpart_mock.reset_mock()
            self.addpart_mock.assert_called_once()
            self.detach_mock.assert_not_called()
            self.assertEqual(lb.parts, LOOP_PARTS_DICT)
            self.assertEqual(lb._gpt_table, LOOP_PARTITION_INFO)
            self.assertEqual(expected_calls, syml.call_args_list)
            self.assertEqual(expected_mounts, lb._mounted)
        self.delpart_mock.assert_called_once()
        self.detach_mock.assert_called_once()

    def testManual(self):
        """Test using the loopback class closed manually."""
        lb = image_lib.LoopbackPartitions(FAKE_PATH)
        lb.Attach()
        self.rc_mock.assertCommandContains(
            ["losetup", "--show", "-f", FAKE_PATH]
        )
        self.delpart_mock.assert_called_once()
        self.delpart_mock.reset_mock()
        self.addpart_mock.assert_called_once()
        self.detach_mock.assert_not_called()
        self.assertEqual(lb.parts, LOOP_PARTS_DICT)
        self.assertEqual(lb._gpt_table, LOOP_PARTITION_INFO)
        lb.close()
        self.delpart_mock.assert_called_once()
        self.detach_mock.assert_called_once()

    def gcFunc(self):
        """Isolates a local variable so it'll be garbage collected."""
        lb = image_lib.LoopbackPartitions(FAKE_PATH)
        lb.Attach()
        self.rc_mock.assertCommandContains(
            ["losetup", "--show", "-f", FAKE_PATH]
        )
        self.delpart_mock.assert_called_once()
        self.delpart_mock.reset_mock()
        self.addpart_mock.assert_called_once()
        self.detach_mock.assert_not_called()
        self.assertEqual(lb.parts, LOOP_PARTS_DICT)
        self.assertEqual(lb._gpt_table, LOOP_PARTITION_INFO)

    def testGarbageCollected(self):
        """Test using the loopback class closed by garbage collection."""
        self.gcFunc()
        # Force garbage collection in case python didn't already clean up the
        # loopback object.
        gc.collect()
        self.delpart_mock.assert_called_once()
        self.detach_mock.assert_called_once()

    def testMountUnmount(self):
        """Test Mount() and Unmount() entry points."""
        lb = image_lib.LoopbackPartitions(FAKE_PATH, destination=self.tempdir)
        lb.Attach()
        # Mount four partitions.
        lb.Mount((1, 3, "ROOT-B", "ROOT-C"))
        for p in (1, 3, 5, 7):
            self.mount_mock.assert_any_call(
                "%sp%d" % (LOOP_DEV, p),
                "%s/dir-%d" % (self.tempdir, p),
                makedirs=True,
                skip_mtab=False,
                sudo=True,
                mount_opts=("ro",),
            )
            linkname = "%s/dir-%s" % (
                self.tempdir,
                LOOP_PARTITION_INFO[p - 1].name,
            )
            self.assertTrue(stat.S_ISLNK(os.lstat(linkname).st_mode))
        self.assertEqual(4, self.mount_mock.call_count)
        self.umount_mock.assert_not_called()

        # Check that Mounted provides the right info.
        mounts = lb.Mounted()
        self.assertDictEqual(
            mounts,
            {
                "STATE": f"{self.tempdir}/dir-1",
                "ROOT-A": f"{self.tempdir}/dir-3",
                "ROOT-B": f"{self.tempdir}/dir-5",
                "ROOT-C": f"{self.tempdir}/dir-7",
            },
        )

        # Unmount half of them, confirm that they were unmounted.
        lb.Unmount((1, "ROOT-B"))
        for p in (1, 5):
            self.umount_mock.assert_any_call(
                "%s/dir-%d" % (self.tempdir, p), cleanup=False
            )
        self.assertEqual(2, self.umount_mock.call_count)
        self.umount_mock.reset_mock()

        # Check that Mounted has been updated
        mounts = lb.Mounted()
        self.assertDictEqual(
            mounts,
            {
                "ROOT-A": f"{self.tempdir}/dir-3",
                "ROOT-C": f"{self.tempdir}/dir-7",
            },
        )

        # Close the object, so that we unmount the other half of them.
        lb.close()
        for p in (3, 7):
            self.umount_mock.assert_any_call(
                "%s/dir-%d" % (self.tempdir, p), cleanup=False
            )
        self.assertEqual(2, self.umount_mock.call_count)

        # Verify that the directories were cleaned up.
        for p in (1, 3):
            self.retry_mock.assert_any_call(
                cros_build_lib.RunCommandError,
                60,
                osutils.RmDir,
                "%s/dir-%d" % (self.tempdir, p),
                sudo=True,
                sleep=1,
            )

    def testMountingMountedPartReturnsName(self):
        """Verify Mount returns the directory name even when already mounted."""
        lb = image_lib.LoopbackPartitions(FAKE_PATH, destination=self.tempdir)
        lb.Attach()
        dirname = "%s/dir-%d" % (self.tempdir, lb._gpt_table[0].number)
        # First make sure we get the directory name when we actually mount.
        self.assertEqual(dirname, lb._Mount(lb._gpt_table[0], ("ro",)))
        # Then make sure we get it when we call it again.
        self.assertEqual(dirname, lb._Mount(lb._gpt_table[0], ("ro",)))
        lb.close()

    def testRemountCallsMount(self):
        """Verify Mount returns the directory name even when already mounted."""
        lb = image_lib.LoopbackPartitions(FAKE_PATH, destination=self.tempdir)
        lb.Attach()
        devname = "%sp%d" % (LOOP_DEV, lb._gpt_table[0].number)
        dirname = "%s/dir-%d" % (self.tempdir, lb._gpt_table[0].number)
        # First make sure we get the directory name when we actually mount.
        self.assertEqual(dirname, lb._Mount(lb._gpt_table[0], ("ro",)))
        self.mount_mock.assert_called_once_with(
            devname,
            dirname,
            makedirs=True,
            skip_mtab=False,
            sudo=True,
            mount_opts=("ro",),
        )
        # Then make sure we get it when we call it again.
        self.assertEqual(
            dirname, lb._Mount(lb._gpt_table[0], ("remount", "rw"))
        )
        self.assertEqual(
            mock.call(
                devname,
                dirname,
                makedirs=True,
                skip_mtab=False,
                sudo=True,
                mount_opts=("remount", "rw"),
            ),
            self.mount_mock.call_args,
        )
        lb.close()

    def testGetPartitionDevName(self):
        """Test GetPartitionDevName()."""
        lb = image_lib.LoopbackPartitions(FAKE_PATH)
        lb.Attach()
        for part in LOOP_PARTITION_INFO:
            self.assertEqual(
                "%sp%d" % (LOOP_DEV, part.number),
                lb.GetPartitionDevName(part.number),
            )
            if part.name != "reserved":
                self.assertEqual(
                    "%sp%d" % (LOOP_DEV, part.number),
                    lb.GetPartitionDevName(part.name),
                )
        lb.close()

    def test_GetMountPointAndSymlink(self):
        """Test _GetMountPointAndSymlink()."""
        lb = image_lib.LoopbackPartitions(FAKE_PATH, destination=self.tempdir)
        lb.Attach()
        for part in LOOP_PARTITION_INFO:
            expected = [
                os.path.join(lb.destination, "dir-%s" % n)
                for n in (part.number, part.name)
            ]
            self.assertEqual(expected, list(lb._GetMountPointAndSymlink(part)))
        lb.close()

    def testIsExt2OnVarious(self):
        """Test _IsExt2 works with the various partition types."""
        # STATE, ROOT-A, and OEM generally have ext2 filesystems.
        FS_PARTITIONS = (1, 3, 8)

        def ext_mock(path, offset=0):  # pylint: disable=unused-argument
            for num in FS_PARTITIONS:
                if path.endswith(f"p{num}"):
                    return True
            return False

        self.PatchObject(image_lib, "IsExt2Image", side_effect=ext_mock)

        lb = image_lib.LoopbackPartitions(FAKE_PATH, destination=self.tempdir)
        lb.Attach()
        # We expect that only the partitions in FS_PARTITIONS are ext2.
        self.assertEqual(
            [part.number in FS_PARTITIONS for part in LOOP_PARTITION_INFO],
            [lb._IsExt2(part.name) for part in LOOP_PARTITION_INFO],
        )
        lb.close()


class LsbUtilsTest(cros_test_lib.RunCommandTempDirTestCase):
    """Tests the various LSB utilities."""

    def setUp(self):
        # Patch osutils.IsRootUser() to pretend running as root, so
        # reading/writing the lsb-release file doesn't require escalated
        # privileges and the test can clean itself up correctly.
        self.PatchObject(os_util, "is_root_user", return_value=True)

    def testWriteLsbRelease(self):
        """Tests writing out the lsb_release file using WriteLsbRelease(..)."""
        fields = collections.OrderedDict(
            (
                ("x", "1"),
                ("y", "2"),
                ("foo", "bar"),
            )
        )
        image_lib.WriteLsbRelease(self.tempdir, fields)
        lsb_release_file = os.path.join(self.tempdir, "etc", "lsb-release")
        expected_content = "x=1\ny=2\nfoo=bar\n"
        self.assertFileContents(lsb_release_file, expected_content)
        self.rc.assertCommandCalled(
            [
                "setfattr",
                "-n",
                "security.selinux",
                "-v",
                "u:object_r:cros_conf_file:s0",
                os.path.join(self.tempdir, "etc/lsb-release"),
            ]
        )

    def testOverwriteLsbRelease(self):
        """Tests overwriting the lsb_release file using WriteLsbRelease(..)."""
        lsb_release_file = os.path.join(self.tempdir, "etc", "lsb-release")

        image_lib.WriteLsbRelease(
            self.tempdir,
            collections.OrderedDict(
                (
                    ("x", "1"),
                    ("y", "2"),
                    ("foo", "bar"),
                )
            ),
        )

        # Test that WriteLsbRelease(..) correctly handles an existing file.
        fields = collections.OrderedDict(
            (
                ("newkey1", "value1"),
                ("newkey2", "value2"),
                ("a", "3"),
                ("b", "4"),
            )
        )
        image_lib.WriteLsbRelease(self.tempdir, fields)
        expected_content = (
            "x=1\ny=2\nfoo=bar\nnewkey1=value1\nnewkey2=value2\na=3\nb=4\n"
        )
        self.assertFileContents(lsb_release_file, expected_content)
        self.rc.assertCommandCalled(
            [
                "setfattr",
                "-n",
                "security.selinux",
                "-v",
                "u:object_r:cros_conf_file:s0",
                os.path.join(self.tempdir, "etc/lsb-release"),
            ]
        )


class BuildImagePathTest(cros_test_lib.MockTempDirTestCase):
    """BuildImagePath tests."""

    def setUp(self):
        self.board = "board"
        self.board_dir = os.path.join(self.tempdir, self.board)

        D = cros_test_lib.Directory
        filesystem = (
            D(self.board, ("recovery_image.bin", "other_image.bin")),
            "full_path_image.bin",
        )
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, filesystem)

        self.full_path = os.path.join(self.tempdir, "full_path_image.bin")

    def testBuildImagePath(self):
        """BuildImagePath tests."""
        self.PatchObject(
            image_lib,
            "GetLatestImageLink",
            return_value=os.path.join(self.tempdir, self.board),
        )

        # Board and full image path provided.
        result = image_lib.BuildImagePath(self.board, self.full_path)
        self.assertEqual(self.full_path, result)

        # Only full image path provided.
        result = image_lib.BuildImagePath(None, self.full_path)
        self.assertEqual(self.full_path, result)

        # Full image path provided that does not exist.
        with self.assertRaises(image_lib.ImageDoesNotExistError):
            image_lib.BuildImagePath(self.board, "/does/not/exist")
        with self.assertRaises(image_lib.ImageDoesNotExistError):
            image_lib.BuildImagePath(None, "/does/not/exist")

        # Default image is used.
        result = image_lib.BuildImagePath(self.board, None)
        self.assertEqual(
            os.path.join(self.board_dir, "recovery_image.bin"), result
        )

        # Image basename provided.
        result = image_lib.BuildImagePath(self.board, "other_image.bin")
        self.assertEqual(
            os.path.join(self.board_dir, "other_image.bin"), result
        )

        # Image basename provided that does not exist.
        with self.assertRaises(image_lib.ImageDoesNotExistError):
            image_lib.BuildImagePath(self.board, "does_not_exist.bin")

        default_mock = self.PatchObject(cros_build_lib, "GetDefaultBoard")

        # Nothing provided, and no default.
        default_mock.return_value = None
        with self.assertRaises(image_lib.ImageDoesNotExistError):
            image_lib.BuildImagePath(None, None)

        # Nothing provided, with default.
        default_mock.return_value = "board"
        result = image_lib.BuildImagePath(None, None)
        self.assertEqual(
            os.path.join(self.board_dir, "recovery_image.bin"), result
        )


class SecurityTestConfigTest(cros_test_lib.RunCommandTempDirTestCase):
    """SecurityTestConfig class tests."""

    # pylint: disable=protected-access

    def setUp(self):
        self.image = "/path/to/image.bin"
        self.baselines = "/path/to/baselines"
        self.vboot_hash = "abc123"
        self.config = image_lib.SecurityTestConfig(
            self.image, self.baselines, self.vboot_hash, self.tempdir
        )

    def testVbootCheckout(self):
        """Test normal flow - clone and checkout."""
        clone_patch = self.PatchObject(git, "Clone")
        self.config._VbootCheckout()
        clone_patch.assert_called_once()
        self.assertCommandContains(["git", "checkout", self.vboot_hash])

        # Make sure it doesn't try to clone & checkout again after already
        # having done so successfully.
        clone_patch = self.PatchObject(git, "Clone")
        self.config._VbootCheckout()
        clone_patch.assert_not_called()

    def testVbootCheckoutError(self):
        """Test exceptions in a git command."""
        rce = cros_build_lib.RunCommandError("error")
        self.PatchObject(git, "Clone", side_effect=rce)
        with self.assertRaises(image_lib.VbootCheckoutError):
            self.config._VbootCheckout()

    def testVbootCheckoutNoDirectory(self):
        """Test the error handling when the directory does not exist."""
        # Test directory that does not exist.
        self.config.directory = "/DOES/NOT/EXIST"
        with self.assertRaises(image_lib.SecurityConfigDirectoryError):
            self.config._VbootCheckout()

    def testRunCheck(self):
        """RunCheck tests."""
        # No config argument when running check.
        self.config.RunCheck("check1", False)
        check1 = os.path.join(self.config._checks_dir, "ensure_check1.sh")
        config1 = os.path.join(self.baselines, "ensure_check1.config")
        self.assertCommandContains([check1, self.image])
        self.assertCommandContains([config1], expected=False)

        # Include config argument when running check.
        self.config.RunCheck("check2", True)
        check2 = os.path.join(self.config._checks_dir, "ensure_check2.sh")
        config2 = os.path.join(self.baselines, "ensure_check2.config")
        self.assertCommandContains([check2, self.image, config2])


class GetImageDiskPartitionInfoTests(cros_test_lib.RunCommandTestCase):
    """Tests the GetImageDiskPartitionInfo function."""

    SAMPLE_PARTED = """/foo/chromiumos_qemu_image.bin:\
2271240192B:file:512:512:gpt::;
11:32768B:8421375B:8388608B::RWFW:;
6:8421376B:8421887B:512B::KERN-C:;
7:8421888B:8422399B:512B::ROOT-C:;
9:8422400B:8422911B:512B::reserved:;
10:8422912B:8423423B:512B::reserved:;
2:10485760B:27262975B:16777216B::KERN-A:;
4:27262976B:44040191B:16777216B::KERN-B:;
8:44040192B:60817407B:16777216B:ext4:OEM:msftdata;
12:127926272B:161480703B:33554432B:fat16:EFI-SYSTEM:boot, esp;
5:161480704B:163577855B:2097152B::ROOT-B:;
3:163577856B:2260729855B:2097152000B:ext2:ROOT-A:;
1:2260729856B:2271215615B:10485760B:ext2:STATE:msftdata;
"""

    SAMPLE_CGPT = """\
       start        size    part  contents
           0           1          PMBR (Boot GUID: 88FB7EB8-2B3F-B943-B933-\
EEC571FFB6E1)
           1           1          Pri GPT header
           2          32          Pri GPT table
     1921024     2097152       1  Label: "STATE"
                                  Type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
                                  UUID: EEBD83BE-397E-BD44-878B-0DDDD5A5C510
                                  Attr: [0]
       20480       32768       2  Label: "KERN-A"
                                  Type: FE3A2A5D-4F32-41A7-B725-ACCC3285A309
                                  UUID: 7007C2F3-08E5-AB40-A4BC-FF5B01F5460D
                                  Attr: [101]
     1101824      819200       3  Label: "ROOT-A"
                                  Type: 3CB8E202-3B7E-47DD-8A3C-7FF2A13CFCEC
                                  UUID: F4C5C3AD-027F-894B-80CD-3DEC57932948
                                  Attr: [0]
       53248       32768       4  Label: "KERN-B"
                                  Type: FE3A2A5D-4F32-41A7-B725-ACCC3285A309
                                  UUID: C85FB478-404C-8741-ADB8-11312A35880D
                                  Attr: [0]
      282624      819200       5  Label: "ROOT-B"
                                  Type: 3CB8E202-3B7E-47DD-8A3C-7FF2A13CFCEC
                                  UUID: A99F4231-1EC3-C542-AC0C-DF3729F5DB07
                                  Attr: [0]
       16448           1       6  Label: "KERN-C"
                                  Type: FE3A2A5D-4F32-41A7-B725-ACCC3285A309
                                  UUID: 81F0E336-FAC9-174D-A08C-864FE627B637
                                  Attr: [0]
       16449           1       7  Label: "ROOT-C"
                                  Type: 3CB8E202-3B7E-47DD-8A3C-7FF2A13CFCEC
                                  UUID: 9E127FCA-30C1-044E-A5F2-DF74E6932692
                                  Attr: [0]
       86016       32768       8  Label: "OEM"
                                  Type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
                                  UUID: 72986347-A37C-684F-9A19-4DBAF41C55A9
                                  Attr: [0]
       16450           1       9  Label: "reserved"
                                  Type: 2E0A753D-9E48-43B0-8337-B15192CB1B5E
                                  UUID: BA85A0A7-1850-964D-8EF8-6707AC106C3A
                                  Attr: [0]
       16451           1      10  Label: "reserved"
                                  Type: 2E0A753D-9E48-43B0-8337-B15192CB1B5E
                                  UUID: 16C9EC9B-50FA-DD46-98DC-F781360817B4
                                  Attr: [0]
          64       16384      11  Label: "RWFW"
                                  Type: CAB6E88E-ABF3-4102-A07A-D4BB9BE3C1D3
                                  UUID: BE8AECB9-4F78-7C44-8F23-5A9273B7EC8F
                                  Attr: [0]
      249856       32768      12  Label: "EFI-SYSTEM"
                                  Type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
                                  UUID: 88FB7EB8-2B3F-B943-B933-EEC571FFB6E1
                                  Attr: [0]
     4050847          32          Sec GPT table
     4050879           1          Sec GPT header
"""

    def testCgpt(self):
        """Tests that we can list all partitions with `cgpt` correctly."""
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)
        self.rc.AddCmdResult(partial_mock.Ignore(), stdout=self.SAMPLE_CGPT)
        partitions = image_lib.GetImageDiskPartitionInfo("...")
        part_dict = {p.name: p for p in partitions}
        self.assertEqual(part_dict["STATE"].start, 983564288)
        self.assertEqual(part_dict["STATE"].size, 1073741824)
        self.assertEqual(part_dict["STATE"].number, 1)
        self.assertEqual(part_dict["STATE"].name, "STATE")
        self.assertEqual(part_dict["EFI-SYSTEM"].start, 249856 * 512)
        self.assertEqual(part_dict["EFI-SYSTEM"].size, 32768 * 512)
        self.assertEqual(part_dict["EFI-SYSTEM"].number, 12)
        self.assertEqual(part_dict["EFI-SYSTEM"].name, "EFI-SYSTEM")
        self.assertEqual(12, len(partitions))

    def testNormalPath(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)
        self.rc.AddCmdResult(partial_mock.Ignore(), stdout=self.SAMPLE_PARTED)
        partitions = image_lib.GetImageDiskPartitionInfo("_ignored")
        part_dict = {p.name: p for p in partitions}
        self.assertEqual(12, len(partitions))
        self.assertEqual(1, part_dict["STATE"].number)
        self.assertEqual(2097152000, part_dict["ROOT-A"].size)

    def testKeyedByNumber(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)
        self.rc.AddCmdResult(partial_mock.Ignore(), stdout=self.SAMPLE_PARTED)
        partitions = image_lib.GetImageDiskPartitionInfo("_ignored")
        part_dict = {p.number: p for p in partitions}
        self.assertEqual(12, len(part_dict))
        self.assertEqual("STATE", part_dict[1].name)
        self.assertEqual(2097152000, part_dict[3].size)
        self.assertEqual("reserved", part_dict[9].name)
        self.assertEqual("reserved", part_dict[10].name)

    def testChangeUnitInsideChroot(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)
        self.rc.AddCmdResult(partial_mock.Ignore(), stdout=self.SAMPLE_CGPT)
        partitions = image_lib.GetImageDiskPartitionInfo("_ignored")
        part_dict = {p.name: p for p in partitions}
        self.assertEqual(part_dict["STATE"].start, 983564288)
        self.assertEqual(part_dict["STATE"].size, 1073741824)


class GetImagesToBuildTests(cros_test_lib.MockTestCase):
    """Tests the GetImagesToBuild function."""

    def testExpectedInput(self):
        """Pass in all expected image types and check expected image names."""
        # TODO(b/236161656): Fix.
        # pylint: disable-next=consider-using-dict-items
        for k in constants.IMAGE_TYPE_TO_NAME:
            image = image_lib.GetImagesToBuild([k])
            self.assertEqual(len(image), 1)
            self.assertTrue(constants.IMAGE_TYPE_TO_NAME[k] in image)

    def testInvalidInput(self):
        """Pass in an invalid image type and check for ValueError."""
        with self.assertRaises(ValueError):
            image_lib.GetImagesToBuild([constants.IMAGE_TYPE_DEV, "invalid"])

    def testInvalidImageCombination(self):
        """Verify an invalid image type combination raises a ValueError."""
        with self.assertRaises(ValueError):
            image_lib.GetImagesToBuild(
                [constants.IMAGE_TYPE_DEV, constants.FACTORY_IMAGE_BIN]
            )


class GetBuildImageEnvvarTests(cros_test_lib.MockTestCase):
    """Tests the GetBuildImageEnvvars function."""

    def setUp(self):
        self.use_flag_mock = self.PatchObject(
            portage_util, "GetBoardUseFlags", return_value=[]
        )

    def testStandardImage(self):
        """Test with standard base/dev/test image name."""
        expected_envvar = {
            "INSTALL_MASK": (
                "\n".join(install_mask.DEFAULT)
                + "\n"
                + "\n".join(install_mask.SYSTEMD)
            ),
            "PRISTINE_IMAGE_NAME": constants.BASE_IMAGE_BIN,
            "BASE_PACKAGE": "virtual/target-os",
        }
        image_to_test = [
            constants.BASE_IMAGE_BIN,
            constants.DEV_IMAGE_BIN,
            constants.TEST_IMAGE_BIN,
        ]
        for image in image_to_test:
            envar = image_lib.GetBuildImageEnvvars(set([image]), "test_board")
            self.assertDictEqual(envar, expected_envvar)

        # Validate scenario with systemd in USE flag
        self.use_flag_mock.return_value = ["cros_debug", "systemd"]
        expected_envvar["INSTALL_MASK"] = "\n".join(install_mask.DEFAULT)
        for image in image_to_test:
            envar = image_lib.GetBuildImageEnvvars(set([image]), "test_board")
            self.assertDictEqual(envar, expected_envvar)

    def testFactoryImage(self):
        """Test with factory image name."""
        expected_envvar = {
            "INSTALL_MASK": (
                "\n".join(install_mask.FACTORY_SHIM)
                + "\n"
                + "\n".join(install_mask.SYSTEMD)
            ),
            "USE": image_lib._FACTORY_SHIM_USE_FLAGS,
            "PRISTINE_IMAGE_NAME": constants.FACTORY_IMAGE_BIN,
            "BASE_PACKAGE": "virtual/target-os-factory-shim",
        }
        envar = image_lib.GetBuildImageEnvvars(
            set([constants.FACTORY_IMAGE_BIN]), "betty"
        )
        self.assertDictEqual(envar, expected_envvar)

        # Validate scenario with systemd in USE flag
        self.use_flag_mock.return_value = ["cros_debug", "systemd"]
        expected_envvar["INSTALL_MASK"] = "\n".join(install_mask.FACTORY_SHIM)
        envar.clear()
        envar = image_lib.GetBuildImageEnvvars(
            set([constants.FACTORY_IMAGE_BIN]), "betty"
        )
        print(envar)
        self.assertDictEqual(envar, expected_envvar)

        # Validate if extra environment variable is passed
        extra_env = {
            "USE": "test test1",
            "ENV": "TEST_VALUE",
        }
        expected_envvar["USE"] = extra_env["USE"] + " " + expected_envvar["USE"]
        expected_envvar["ENV"] = extra_env["ENV"]
        envar.clear()
        envar = image_lib.GetBuildImageEnvvars(
            set([constants.FACTORY_IMAGE_BIN]), "betty", env_var_init=extra_env
        )
        self.assertDictEqual(envar, expected_envvar)

    def testChromeOSVersion(self):
        """Test ChromeOS version environment variable."""
        version_info = chromeos_version.VersionInfo(
            version_string="1.2.3", chrome_branch="4"
        )
        envar = image_lib.GetBuildImageEnvvars(
            set([constants.BASE_IMAGE_BIN]), "betty", version_info=version_info
        )

        self.assertEqual(envar["CHROME_BRANCH"], "4")
        self.assertEqual(envar["CHROMEOS_BUILD"], "1")
        self.assertEqual(envar["CHROMEOS_BRANCH"], "2")
        self.assertEqual(envar["CHROMEOS_PATCH"], "3")
        self.assertEqual(envar["CHROMEOS_VERSION_STRING"], "1.2.3")

    def testBuildAndOutputDir(self):
        """Test BUILD_DIR and OUTPUT_DIR environment variable."""
        build_dir = "build/dir"
        output_dir = Path("ouput/dir")
        envar = image_lib.GetBuildImageEnvvars(
            set([constants.BASE_IMAGE_BIN]),
            "betty",
            build_dir=build_dir,
            output_dir=output_dir,
        )

        self.assertEqual(envar["BUILD_DIR"], build_dir)
        self.assertEqual(envar["OUTPUT_DIR"], str(output_dir))


class CreateBuildDirTests(cros_test_lib.MockTempDirTestCase):
    """Test CreateBuildDir."""

    def setUp(self):
        self.PatchObject(
            chromeos_version.VersionInfo,
            "_GetDateTime",
            return_value=FAKE_DATE_STRING,
        )
        self.build_top_dir = self.tempdir / "build"
        self.output_top_dir = self.tempdir / "output"
        self.testBoard = "TestBoard"
        self.version_info = chromeos_version.VersionInfo(
            version_string="1.2.3", chrome_branch="4"
        )
        self.attempt = 5
        self.result_build_dir = self.build_top_dir / self.testBoard
        self.result_output_dir = self.output_top_dir / self.testBoard
        self.image_dir = (
            f"R{self.version_info.chrome_branch}-"
            + f"{self.version_info.VersionString()}"
        )
        self.image_dir_attempt = self.image_dir + f"-a{self.attempt}"
        self.image_dir_date = (
            f"R{self.version_info.chrome_branch}-"
            + f"{self.version_info.VersionStringWithDateTime()}"
        )
        self.image_dir_date_attempt = f"{self.image_dir_date}-a{self.attempt}"
        self.symlink = "latest"

    def testChromeBranchVersion(self):
        """Test with chrome_branch and version string."""
        build_dir, output_dir, symlink_dir = image_lib.CreateBuildDir(
            self.build_top_dir,
            self.output_top_dir,
            self.version_info.chrome_branch,
            self.version_info.VersionString(),
            self.testBoard,
            self.symlink,
        )

        self.assertExists(build_dir)
        self.assertExists(output_dir)
        self.assertEqual(build_dir, self.result_build_dir / self.image_dir)
        self.assertExists(output_dir, self.result_output_dir / self.image_dir)
        self.assertTrue(symlink_dir.is_symlink())
        self.assertEqual(self.image_dir, os.readlink(symlink_dir))

        # Now test the case where the build directory already exists.
        build_dir, output_dir, symlink_dir = image_lib.CreateBuildDir(
            self.build_top_dir,
            self.output_top_dir,
            self.version_info.chrome_branch,
            self.version_info.VersionString(),
            self.testBoard,
            self.symlink,
            replace=True,
        )

        self.assertExists(build_dir)
        self.assertExists(output_dir)
        self.assertEqual(build_dir, self.result_build_dir / self.image_dir)
        self.assertExists(output_dir, self.result_output_dir / self.image_dir)
        self.assertTrue(symlink_dir.is_symlink())
        self.assertEqual(self.image_dir, os.readlink(symlink_dir))

        # Now test the case where the build directory already exists with
        # replace as false.
        with self.assertRaises(FileExistsError):
            build_dir, output_dir, symlink_dir = image_lib.CreateBuildDir(
                self.build_top_dir,
                self.output_top_dir,
                self.version_info.chrome_branch,
                self.version_info.VersionString(),
                self.testBoard,
                self.symlink,
            )

    def testChromeBranchVersionDate(self):
        """Test with chrome_branch and version string with date."""
        build_dir, output_dir, symlink_dir = image_lib.CreateBuildDir(
            self.build_top_dir,
            self.output_top_dir,
            self.version_info.chrome_branch,
            self.version_info.VersionStringWithDateTime(),
            self.testBoard,
            self.symlink,
        )

        self.assertExists(build_dir)
        self.assertExists(output_dir)
        self.assertEqual(build_dir, self.result_build_dir / self.image_dir_date)
        self.assertExists(
            output_dir, self.result_output_dir / self.image_dir_date
        )
        self.assertTrue(symlink_dir.is_symlink())
        self.assertEqual(self.image_dir_date, os.readlink(symlink_dir))

    def testBuildAttempt(self):
        """Test with chrome_branch, version string and build attempt."""
        build_dir, output_dir, symlink_dir = image_lib.CreateBuildDir(
            self.build_top_dir,
            self.output_top_dir,
            self.version_info.chrome_branch,
            self.version_info.VersionString(),
            self.testBoard,
            self.symlink,
            build_attempt=self.attempt,
        )

        self.assertExists(build_dir)
        self.assertExists(output_dir)
        self.assertEqual(
            build_dir, self.result_build_dir / self.image_dir_attempt
        )
        self.assertExists(
            output_dir, self.result_output_dir / self.image_dir_attempt
        )
        self.assertTrue(symlink_dir.is_symlink())
        self.assertEqual(self.image_dir_attempt, os.readlink(symlink_dir))

    def testBuildAttemptDate(self):
        """Test with chrome_branch, version string, date, and build attempt."""
        build_dir, output_dir, symlink_dir = image_lib.CreateBuildDir(
            self.build_top_dir,
            self.output_top_dir,
            self.version_info.chrome_branch,
            self.version_info.VersionStringWithDateTime(),
            self.testBoard,
            self.symlink,
            build_attempt=self.attempt,
        )

        self.assertExists(build_dir)
        self.assertExists(output_dir)
        self.assertEqual(
            build_dir, self.result_build_dir / self.image_dir_date_attempt
        )
        self.assertExists(
            output_dir, self.result_output_dir / self.image_dir_date_attempt
        )
        self.assertTrue(symlink_dir.is_symlink())
        self.assertEqual(self.image_dir_date_attempt, os.readlink(symlink_dir))

    def testOutputSuffix(self):
        """Test with output suffix."""
        output_suffix = "test-suffix"
        build_dir, output_dir, symlink_dir = image_lib.CreateBuildDir(
            self.build_top_dir,
            self.output_top_dir,
            self.version_info.chrome_branch,
            self.version_info.VersionString(),
            self.testBoard,
            self.symlink,
            build_attempt=self.attempt,
            output_suffix=output_suffix,
        )

        self.assertExists(build_dir)
        self.assertExists(output_dir)
        self.assertEqual(
            build_dir,
            self.result_build_dir
            / (self.image_dir_attempt + "-" + output_suffix),
        )
        self.assertExists(
            output_dir,
            self.result_output_dir
            / (self.image_dir_attempt + "-" + output_suffix),
        )
        self.assertTrue(symlink_dir.is_symlink())
        self.assertEqual(
            self.image_dir_attempt + "-" + output_suffix,
            os.readlink(symlink_dir),
        )

        # Test the case without build_attempt.
        build_dir, output_dir, symlink_dir = image_lib.CreateBuildDir(
            self.build_top_dir,
            self.output_top_dir,
            self.version_info.chrome_branch,
            self.version_info.VersionString(),
            self.testBoard,
            self.symlink,
            output_suffix=output_suffix,
        )

        self.assertExists(build_dir)
        self.assertExists(output_dir)
        self.assertEqual(
            build_dir,
            self.result_build_dir / (self.image_dir + "-" + output_suffix),
        )
        self.assertExists(
            output_dir,
            self.result_output_dir / (self.image_dir + "-" + output_suffix),
        )
        self.assertTrue(symlink_dir.is_symlink())
        self.assertEqual(
            self.image_dir + "-" + output_suffix, os.readlink(symlink_dir)
        )

    def testOutputSuffixWithDate(self):
        """Test with output suffix with date."""
        output_suffix = "test-suffix"
        build_dir, output_dir, symlink_dir = image_lib.CreateBuildDir(
            self.build_top_dir,
            self.output_top_dir,
            self.version_info.chrome_branch,
            self.version_info.VersionStringWithDateTime(),
            self.testBoard,
            self.symlink,
            build_attempt=self.attempt,
            output_suffix=output_suffix,
        )

        self.assertExists(build_dir)
        self.assertExists(output_dir)
        self.assertEqual(
            build_dir,
            self.result_build_dir
            / f"{self.image_dir_date_attempt}-{output_suffix}",
        )
        self.assertExists(
            output_dir,
            self.result_output_dir
            / f"{self.image_dir_date_attempt}-{output_suffix}",
        )
        self.assertTrue(symlink_dir.is_symlink())
        self.assertEqual(
            f"{self.image_dir_date_attempt}-{output_suffix}",
            os.readlink(symlink_dir),
        )

        # Test the case without build_attempt.
        build_dir, output_dir, symlink_dir = image_lib.CreateBuildDir(
            self.build_top_dir,
            self.output_top_dir,
            self.version_info.chrome_branch,
            self.version_info.VersionStringWithDateTime(),
            self.testBoard,
            self.symlink,
            output_suffix=output_suffix,
        )

        self.assertExists(build_dir)
        self.assertExists(output_dir)
        self.assertEqual(
            build_dir,
            self.result_build_dir / f"{self.image_dir_date}-{output_suffix}",
        )
        self.assertExists(
            output_dir,
            self.result_output_dir / f"{self.image_dir_date}-{output_suffix}",
        )
        self.assertTrue(symlink_dir.is_symlink())
        self.assertEqual(
            f"{self.image_dir_date}-{output_suffix}", os.readlink(symlink_dir)
        )


class UtilsTests(cros_test_lib.TempDirTestCase):
    """Test simple util funcs."""

    def testIsSquashfsImageFails(self):
        """Test SquashFS identification on non-images."""
        image = self.tempdir / "img.squashfs"
        osutils.AllocateFile(image, 1024 * 1024)
        self.assertFalse(image_lib.IsSquashfsImage(image))

    def testIsSquashfsImage(self):
        """Tests we correctly identify a SquashFS image."""
        image = self.tempdir / "img.squashfs"
        root = self.tempdir / "root"
        root.mkdir()
        cros_build_lib.run(
            ["mksquashfs", root.name, image.name], cwd=self.tempdir
        )
        self.assertTrue(image_lib.IsSquashfsImage(image))

    def testIsExt4Image(self):
        """Tests we correctly identify an Ext4 image."""
        for ver in (2, 3, 4):
            image = self.tempdir / f"rootfs.ext{ver}"
            # 2 MiB is big enough for ext3/ext4 specific features.
            osutils.AllocateFile(image, 2 * 1024 * 1024)

            # Tests failure to identify.
            self.assertFalse(image_lib.IsExt2Image(image))

            # Make a real ext2/ext3/ext4 images.
            cros_build_lib.run(
                [f"mkfs.ext{ver}", image],
                extra_env={"PATH": "/sbin:/usr/sbin:%s" % os.environ["PATH"]},
            )
            self.assertTrue(image_lib.IsExt2Image(image))
