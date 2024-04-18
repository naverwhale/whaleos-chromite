# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for the get_eclasses_spider."""

from chromite.contrib.portage_explorer import get_eclasses_spider
from chromite.contrib.portage_explorer import spider_testables
from chromite.contrib.portage_explorer import spiderlib


def test_execute(monkeypatch, tmp_path):
    """Test the execute function for the get_eclasses_spider.

    Ensure the get_eclasses_spider gets all the eclasses in the overlay's eclass
    directory and sorts them.
    """
    test_elm, overlay_elm = spider_testables.create_overlays(tmp_path, "elm")
    _test_brya, overlay_brya = spider_testables.create_overlays(
        tmp_path, "brya"
    )
    eclasses, _eclass_inherit = spider_testables.create_eclasses(
        tmp_path,
        test_elm,
        ["eclass", "ssalce", "abcd"],
    )
    monkeypatch.setattr("chromite.lib.constants.SOURCE_ROOT", tmp_path)
    test_output = spiderlib.SpiderOutput([], [overlay_brya, overlay_elm])
    get_eclasses_spider.execute(test_output)
    assert test_output.build_targets == []
    assert test_output.overlays[0].eclasses == []
    assert test_output.overlays[1].profiles == []
    assert test_output.overlays[1].ebuilds == []
    assert test_output.overlays[1].eclasses == eclasses
