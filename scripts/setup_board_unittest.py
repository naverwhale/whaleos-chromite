# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for setup_board."""

from unittest import mock

import pytest

from chromite.scripts import setup_board


@mock.patch("chromite.service.sysroot.SetupBoard", return_value=None)
def test_main(_, tmp_path):
    """Smoke test."""
    # Missing --board fails.
    with pytest.raises(SystemExit):
        setup_board.main([])

    # Point to an empty root just in case we try to touch something.
    setup_board.main(
        ["-b", "amd64-generic", "--board-root", str(tmp_path / "empty")]
    )
