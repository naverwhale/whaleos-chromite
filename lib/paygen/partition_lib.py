# Copyright 2018 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Library for handling Chrome OS partition."""

import logging
import os
import tempfile
from typing import Optional

from chromite.lib import cgpt
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import image_lib
from chromite.lib import osutils
from chromite.lib.paygen import filelib


DLC_IMAGE = "dlc"
CROS_IMAGE = "cros"


def ExtractPartition(filename: str, partition: str, out_part: str) -> None:
    """Extract partition from an image file.

    Args:
        filename: The image file.
        partition: The partition name. e.g. ROOT or KERNEL.
        out_part: The output partition file.
    """
    parts = image_lib.GetImageDiskPartitionInfo(filename)
    part_info = [p for p in parts if p.name == partition][0]

    offset = int(part_info.start)
    length = int(part_info.size)

    filelib.CopyFileSegment(
        filename, "rb", length, out_part, "wb", in_seek=offset
    )


def Ext2FileSystemSize(ext2_file: str) -> int:
    """Return the size of an ext2 filesystem in bytes.

    Args:
        ext2_file: The path to the ext2 file.
    """
    # dumpe2fs is normally installed in /sbin but doesn't require root.
    dump = cros_build_lib.dbg_run(
        ["/sbin/dumpe2fs", "-h", ext2_file],
        capture_output=True,
        encoding="utf-8",
    ).stdout
    fs_blocks = 0
    fs_blocksize = 0
    for line in dump.split("\n"):
        if not line:
            continue
        label, data = line.split(":")[:2]
        if label == "Block count":
            fs_blocks = int(data)
        elif label == "Block size":
            fs_blocksize = int(data)

    return fs_blocks * fs_blocksize


def PatchKernel(image: str, kern_file: str) -> None:
    """Patch a kernel with vblock from a stateful partition.

    Args:
        image: The stateful partition image.
        kern_file: The kernel file.
    """

    with tempfile.NamedTemporaryFile(
        prefix="stateful"
    ) as state_out, tempfile.NamedTemporaryFile(
        prefix="vmlinuz_hd.vblock"
    ) as vblock:
        ExtractPartition(image, constants.PART_STATE, state_out)
        cros_build_lib.run(
            ["e2cp", "%s:/vmlinuz_hd.vblock" % state_out, vblock]
        )
        filelib.CopyFileSegment(
            vblock, "rb", os.path.getsize(vblock), kern_file, "r+b"
        )


def ExtractKernel(image: str, kern_out: str) -> None:
    """Extract the kernel from the given image.

    Args:
        image: The image containing the kernel partition.
        kern_out: The output kernel file.
    """
    ExtractPartition(image, constants.PART_KERN_B, kern_out)
    if not any(osutils.ReadFile(kern_out, "rb", size=65536)):
        logging.warning("%s: Kernel B is empty, patching kernel A.", image)
        ExtractPartition(image, constants.PART_KERN_A, kern_out)
        PatchKernel(image, kern_out)


def ExtractRoot(image: str, root_out: str, truncate: bool = True) -> None:
    """Extract the rootfs partition from a gpt image.

    Args:
        image: The input image file.
        root_out: The output root partition file.
        truncate: If true, truncate the partition to the file system size.

    Raises:
        IOError: If unable to truncate the rootfs.
    """
    ExtractPartition(image, constants.PART_ROOT_A, root_out)

    if not truncate:
        return

    # We only update the filesystem part of the partition, which is stored in
    # the gpt script. So we need to truncated it to the file system size if
    # asked for. Currently, we only support truncating ext filesystems.
    if not image_lib.IsExt2Image(root_out):
        logging.warning("Not truncating rootfs due to unsupported filesystem.")
        return

    root_out_size = Ext2FileSystemSize(root_out)
    if root_out_size:
        os.truncate(root_out, root_out_size)
        logging.info("Truncated root to %d bytes.", root_out_size)
    else:
        raise IOError("Error truncating the rootfs to filesystem size.")


def ExtractMiniOS(image: str, minios_out: str, part_a: bool = True) -> None:
    """Extract the minios partition from a gpt image.

    Args:
        image: The input image file.
        minios_out: The output minios partition file.
        part_a: True to extract A partition.
    """
    ExtractPartition(
        image,
        constants.PART_MINIOS_A if part_a else constants.PART_MINIOS_B,
        minios_out,
    )


def IsGptImage(image: str) -> bool:
    """Return true if the image is a GPT image.

    Args:
        image: The path to the image.
    """
    try:
        return bool(image_lib.GetImageDiskPartitionInfo(image))
    except cros_build_lib.RunCommandError:
        return False


def LookupImageType(image: str) -> Optional[str]:
    """Return the image type given the path to an image.

    Args:
        image: The path to a GPT or Squashfs Image.

    Returns:
        The type of the image. None if it cannot detect the image type.
    """
    if IsGptImage(image):
        return CROS_IMAGE
    elif image_lib.IsExt2Image(image) or image_lib.IsSquashfsImage(image):
        return DLC_IMAGE

    return None


def HasMiniOSPartitions(image: str) -> bool:
    """Return true if the image has miniOS partitions.

    Args:
        image: The path to the GPT image.

    Returns:
        True if the image has miniOS partitions.
    """
    disk = cgpt.Disk.FromImage(image)
    try:
        parts = disk.GetPartitionByTypeGuid(cgpt.MINIOS_TYPE_GUID)
    except KeyError:
        return False
    if len(parts) != 2:
        logging.error(
            "MiniOS should have two partitions, only found: %s",
            len(parts),
        )
        return False
    return True
