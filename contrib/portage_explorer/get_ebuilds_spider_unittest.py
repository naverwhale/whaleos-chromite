# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for the get_ebuilds_spider."""

from chromite.contrib.portage_explorer import get_ebuilds_spider
from chromite.contrib.portage_explorer import spider_testables
from chromite.contrib.portage_explorer import spiderlib


def test_execute(monkeypatch, tmp_path):
    """Test the get_ebuilds_spider's execute function.

    Ensure that we are getting all the correct ebuilds and that each ebuild has
    the right src path, category, PN, version, and revision.
    """
    test_elm, overlay_elm = spider_testables.create_overlays(tmp_path, "elm")
    (
        _test_ebuilds,
        spider_ebuilds,
        _spider_ebuilds_metadata,
    ) = spider_testables.create_ebuilds(
        tmp_path,
        test_elm,
        {
            "category/name-1": spiderlib.TestEbuild(),
            "category/name-1-r4": spiderlib.TestEbuild(),
            "category/eman-1.2.3-r3": spiderlib.TestEbuild(),
            "yrogetac/foo-5.4_alpha0": spiderlib.TestEbuild(),
        },
    )
    test_output = spiderlib.SpiderOutput([], [overlay_elm])
    monkeypatch.setattr("chromite.lib.constants.SOURCE_ROOT", tmp_path)
    get_ebuilds_spider.execute(test_output)
    assert test_output.build_targets == []
    assert test_output.overlays[0].profiles == []
    assert test_output.overlays[0].ebuilds == spider_ebuilds
