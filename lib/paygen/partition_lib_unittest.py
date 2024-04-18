# Copyright 2018 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the partition_lib module."""

import os

from chromite.lib import cgpt
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import image_lib
from chromite.lib import osutils
from chromite.lib.paygen import partition_lib


class PartitionLibTest(cros_test_lib.MockTempDirTestCase):
    """Test partition_lib functions with no mocks by default."""

    def testTruncate(self):
        """Test truncating on extraction."""
        root = self.tempdir / "root.bin"

        # Create a small fs first.
        osutils.AllocateFile(root, 1024 * 1024)
        cros_build_lib.run(
            ["mke2fs", root],
            extra_env={"PATH": "/sbin:/usr/sbin:%s" % os.environ["PATH"]},
        )

        # Then enlarge it.
        os.truncate(root, 10 * 1024 * 1024)

        self.PatchObject(partition_lib, "ExtractPartition")

        partition_lib.ExtractRoot(None, root, truncate=False)
        self.assertEqual(root.stat().st_size, 10 * 1024 * 1024)

        partition_lib.ExtractRoot(None, root)
        self.assertEqual(root.stat().st_size, 1024 * 1024)

    def testExt2FileSystemSize(self):
        """Test getting filesystem size on a simple output."""
        root = self.tempdir / "root.bin"
        osutils.AllocateFile(root, 1024 * 1024)
        cros_build_lib.run(
            ["mke2fs", root],
            extra_env={"PATH": "/sbin:/usr/sbin:%s" % os.environ["PATH"]},
        )
        self.assertEqual(partition_lib.Ext2FileSystemSize(root), 1024 * 1024)


class PartitionLibMockTest(cros_test_lib.RunCommandTempDirTestCase):
    """Test partition_lib functions with run() mocked."""

    def testExtractPartition(self):
        """Tests extraction on a simple image."""
        part_a_bin = "0123"
        part_b_bin = "4567"
        image_bin = part_a_bin + part_b_bin

        image = os.path.join(self.tempdir, "image.bin")
        osutils.WriteFile(image, image_bin)
        part_a = os.path.join(self.tempdir, "a.bin")

        fake_partitions = (
            image_lib.PartitionInfo(1, 0, 4, "fs", "PART-A"),
            image_lib.PartitionInfo(2, 4, 4, "fs", "PART-B"),
        )
        self.PatchObject(
            image_lib, "GetImageDiskPartitionInfo", return_value=fake_partitions
        )

        partition_lib.ExtractPartition(image, "PART-A", part_a)
        self.assertEqual(osutils.ReadFile(part_a), part_a_bin)

    def testIsGptImage(self):
        """Tests we correctly identify an Gpt image."""
        # Tests correct arguments are passed and Gpt image is correctly
        # identified.
        image = "/foo/image"
        part_info_mock = self.PatchObject(
            image_lib, "GetImageDiskPartitionInfo"
        )
        self.assertTrue(partition_lib.IsGptImage(image))
        part_info_mock.assert_called_once_with(image)

        # Tests failure to identify.
        part_info_mock.side_effect = cros_build_lib.RunCommandError("error")
        part_info_mock.return_value = []
        self.assertFalse(partition_lib.IsGptImage(image))

    def testLookupImageType(self):
        """Tests we correctly identify different image types."""
        image = "/foo/image"
        is_gpt = self.PatchObject(partition_lib, "IsGptImage")
        is_squashfs = self.PatchObject(image_lib, "IsSquashfsImage")
        is_ext2 = self.PatchObject(image_lib, "IsExt2Image")

        is_gpt.return_value = True
        self.assertEqual(
            partition_lib.LookupImageType(image), partition_lib.CROS_IMAGE
        )

        is_gpt.return_value = False
        is_squashfs.return_value = True
        self.assertEqual(
            partition_lib.LookupImageType(image), partition_lib.DLC_IMAGE
        )

        is_squashfs.return_value = False
        is_ext2.return_value = True
        self.assertEqual(
            partition_lib.LookupImageType(image), partition_lib.DLC_IMAGE
        )

        is_ext2.return_value = False
        self.assertIsNone(partition_lib.LookupImageType(image))

    def testHasMiniOSPartitions(self):
        """Tests we correctly identify miniOS supported images."""
        image = "/foo/image"

        self.PatchObject(cgpt.Disk, "FromImage", return_value=cgpt.Disk(""))
        self.PatchObject(
            cgpt.Disk, "GetPartitionByTypeGuid", side_effect=KeyError()
        )
        self.assertFalse(partition_lib.HasMiniOSPartitions(image))

        self.PatchObject(cgpt.Disk, "GetPartitionByTypeGuid", return_value=[])
        self.assertFalse(partition_lib.HasMiniOSPartitions(image))

        self.PatchObject(
            cgpt.Disk, "GetPartitionByTypeGuid", return_value=[None, None]
        )
        self.assertTrue(partition_lib.HasMiniOSPartitions(image))
