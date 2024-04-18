# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Interface to BLKPG ioctls.

This isn't well documented beyond /usr/include/linux/blkpg.h header.
"""

import ctypes
import fcntl


# From linux/blkpg.h.
# _IO(0x12,105)
BLKPG = 0x1269

BLKPG_ADD_PARTITION = 1
BLKPG_DEL_PARTITION = 2
BLKPG_RESIZE_PARTITION = 3


# struct blkpg_partition {
#     long long start;     /* starting offset in bytes */
#     long long length;    /* length in bytes */
#     int pno;             /* partition number */
#     char devname[64];    /* unused / ignored */
#     char volname[64];    /* unused / ignore */
# }
class BlkpgPartition(ctypes.Structure):
    """struct blkpg_partition."""

    _fields_ = [
        ("start", ctypes.c_longlong),
        ("length", ctypes.c_longlong),
        ("pno", ctypes.c_int),
        ("devname", ctypes.c_char * 64),
        ("volname", ctypes.c_char * 64),
    ]


# struct blkpg_ioctl_arg {
#     int op;
#     int flags;
#     int datalen;
#     void *data;
# }
class BlkpgArg(ctypes.Structure):
    """struct blkpg_ioctl_arg."""

    _fields_ = [
        ("op", ctypes.c_int),
        ("flags", ctypes.c_int),
        ("datalen", ctypes.c_int),
        ("data", ctypes.c_void_p),
    ]


def add_partition(fd: int, part_id: int, start: int, length: int) -> None:
    """Add the |part_id| partition via |fd|."""
    blkpg_part = BlkpgPartition(start, length, part_id, b"", b"")
    blkpg_arg = BlkpgArg(
        BLKPG_ADD_PARTITION,
        0,
        ctypes.sizeof(blkpg_part),
        ctypes.cast(ctypes.byref(blkpg_part), ctypes.c_void_p),
    )
    fcntl.ioctl(fd, BLKPG, blkpg_arg)


def delete_partition(fd: int, part_id: int) -> None:
    """Delete the |part_id| partition via |fd|."""
    blkpg_part = BlkpgPartition(0, 0, part_id, b"", b"")
    blkpg_arg = BlkpgArg(
        BLKPG_DEL_PARTITION,
        0,
        ctypes.sizeof(blkpg_part),
        ctypes.cast(ctypes.byref(blkpg_part), ctypes.c_void_p),
    )
    fcntl.ioctl(fd, BLKPG, blkpg_arg)
