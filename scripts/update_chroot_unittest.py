# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for update_chroot."""

from chromite.scripts import update_chroot


def test_main(run_mock):  # pylint: disable=unused-argument
    """Smoke test."""
    result = update_chroot.main([])
    assert result == 0
