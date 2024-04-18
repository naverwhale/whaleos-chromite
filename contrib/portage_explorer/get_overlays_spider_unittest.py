# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for the get_overlays_spider."""

from pathlib import Path
from unittest import mock

from chromite.contrib.portage_explorer import get_overlays_spider
from chromite.contrib.portage_explorer import spiderlib


def test_execute():
    """Test the get_overlays_spider's execute function.

    The execute function should get all the overlays, get the correct path for
    each overlay starting from 'src/' and get the correct overlay name. The
    overlays should follow alphabetical order of the src paths.
    """
    with mock.patch(
        "chromite.lib.portage_util.FindOverlays",
        return_value=[
            "/mnt/host/source/src/overlays/overlay-elm",
            "/mnt/host/source/src/private-overlays/overlay-elm-private",
            "/mnt/host/source/src/overlays/baseboard-brya",
            "/mnt/host/source/src/private-overlays/chipset-picasso-private",
            "/mnt/host/source/src/third_party/portage-stable",
        ],
    ), mock.patch(
        "chromite.lib.portage_util.GetOverlayName",
        side_effect=[
            "baseboard-brya",
            "elm",
            "chipset-picasso-private",
            "elm-private",
            "portage-stable",
        ],
    ):
        test_output = spiderlib.SpiderOutput()
        get_overlays_spider.execute(test_output)
        assert test_output.overlays == [
            spiderlib.Overlay(
                Path("src/overlays/baseboard-brya"), "baseboard-brya"
            ),
            spiderlib.Overlay(Path("src/overlays/overlay-elm"), "elm"),
            spiderlib.Overlay(
                Path("src/private-overlays/chipset-picasso-private"),
                "chipset-picasso-private",
            ),
            spiderlib.Overlay(
                Path("src/private-overlays/overlay-elm-private"), "elm-private"
            ),
            spiderlib.Overlay(
                Path("src/third_party/portage-stable"), "portage-stable"
            ),
        ]
