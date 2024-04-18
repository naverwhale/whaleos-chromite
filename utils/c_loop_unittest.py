# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the c_loop module."""

import errno

import pytest

from chromite.utils import c_loop


def test_non_block():
    """Test the code against a non-block device."""
    with pytest.raises(OSError) as e:
        c_loop.detach("/dev/null")
    assert e.value.errno == errno.ENOTTY
