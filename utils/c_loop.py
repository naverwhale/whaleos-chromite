# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Interface to loopdev ioctls.

See /usr/include/linux/loop.h header for more info.
"""

import enum
import fcntl
import os
from typing import Union


class Command(enum.IntEnum):
    """Ioctl loopdev commands."""

    # /dev/loop# commands.
    SET_FD = 0x4C00
    CLR_FD = 0x4C01
    SET_STATUS = 0x4C02
    GET_STATUS = 0x4C03
    SET_STATUS64 = 0x4C04
    GET_STATUS64 = 0x4C05
    CHANGE_FD = 0x4C06
    SET_CAPACITY = 0x4C07
    SET_DIRECT_IO = 0x4C08
    SET_BLOCK_SIZE = 0x4C09
    CONFIGURE = 0x4C0A

    # /dev/loop-control commands.
    CTL_ADD = 0x4C80
    CTL_REMOVE = 0x4C81
    CTL_GET_FREE = 0x4C82


def detach(path: Union[str, os.PathLike]) -> None:
    """Detach the loopdev |path|."""
    with open(path, "wb") as f:
        fcntl.ioctl(f.fileno(), Command.CLR_FD)
