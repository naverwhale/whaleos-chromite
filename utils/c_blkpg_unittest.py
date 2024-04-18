# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the c_blkpg module."""

import errno
import os

import pytest

from chromite.lib import osutils
from chromite.utils import c_blkpg


def test_non_block():
    """Test the code against a non-block device."""
    with osutils.OpenContext(".", flags=os.O_RDONLY) as fd:
        with pytest.raises(OSError) as e:
            c_blkpg.add_partition(fd, 0, 0, 0)
        assert e.value.errno == errno.ENOTTY

        with pytest.raises(OSError) as e:
            c_blkpg.delete_partition(fd, 0)
        assert e.value.errno == errno.ENOTTY
