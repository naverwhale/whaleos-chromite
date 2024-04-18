# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit test for get_boards_spider."""

from unittest import mock

from chromite.contrib.portage_explorer import get_boards_spider
from chromite.contrib.portage_explorer import spiderlib


def test_get_board_name():
    """Test that get_board_name returns the correct board name."""
    assert get_boards_spider.get_board_name("overlay-brya") == "brya"
    assert get_boards_spider.get_board_name("overlay-elm-private") == "elm"
    assert get_boards_spider.get_board_name("chromeos-overlay-oak") == ""
    assert get_boards_spider.get_board_name("baseboard-asuka") == ""


def test_execute():
    """Test that execute returns the correct board names and details."""
    with mock.patch(
        "chromite.lib.portage_util.FindOverlays",
        return_value=[
            "/mnt/host/source/src/overlays/overlay-elm",
            "/mnt/host/source/src/private-overlays/overlay-elm-private",
            "/mnt/host/source/src/private-overlays/chipset-tgl-private",
            "/mnt/host/source/src/private-overlays/overlay-soraka-private",
            "/mnt/host/source/src/overlays/overlay-asuka",
        ],
    ):
        test_output = spiderlib.SpiderOutput()
        get_boards_spider.execute(test_output)
        assert test_output.build_targets == [
            spiderlib.BuildTarget("asuka"),
            spiderlib.BuildTarget("elm"),
            spiderlib.BuildTarget("soraka"),
        ]
