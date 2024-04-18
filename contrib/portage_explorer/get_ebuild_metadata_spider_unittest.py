# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for the get_ebuild_metadata_spider."""

from chromite.contrib.portage_explorer import get_ebuild_metadata_spider
from chromite.contrib.portage_explorer import spider_testables
from chromite.contrib.portage_explorer import spiderlib


def test_execute(monkeypatch, tmp_path):
    """Test the get_ebuild_metadata_spider's execute function.

    Ensure that we are getting all the metadata that we're looking for and
    filling out the spiderlib.Ebuild correctly. Ensure that the use flags and
    inherited eclasses are sorted as well.
    """
    test_elm, overlay_elm = spider_testables.create_overlays(tmp_path, "elm")
    test_brya, overlay_brya = spider_testables.create_overlays(tmp_path, "brya")
    brya_eclasses, _eclass_inherit = spider_testables.create_eclasses(
        tmp_path,
        test_brya,
        [
            "eclass",
            "ssalce",
        ],
    )
    overlay_brya.eclasses = brya_eclasses
    name_metadata = spiderlib.TestEbuild(
        7,
        "Description of category/name-1",
        "http://home.com",
        "Google",
        "0/0",
        "name-1.tar.gz",
        "mirror",
        "category/name",
        "category/name yrogetac/foo",
        "yrogetac/foo",
        "use ? (category/name)",
        "use +flag -foo ",
        "ssalce\trandomstuff\teclass ",
    )
    eman_metadata = spiderlib.TestEbuild(8, bdepend="category/name")
    (
        _package_files,
        elm_ebuilds,
        elm_ebuilds_metadata,
    ) = spider_testables.create_ebuilds(
        tmp_path,
        test_elm,
        {
            "category/eman-1.2.3": eman_metadata,
            "category/name-1": name_metadata,
        },
    )
    elm_ebuilds_metadata[1].rdepend = "category/name yrogetac/foo"
    overlay_elm.ebuilds.append(elm_ebuilds[0])
    overlay_elm.ebuilds.append(elm_ebuilds[1])
    test_output = spiderlib.SpiderOutput([], [overlay_brya, overlay_elm])
    monkeypatch.setattr("chromite.lib.constants.SOURCE_ROOT", tmp_path)
    get_ebuild_metadata_spider.execute(test_output)
    assert test_output.build_targets == []
    assert test_output.overlays[0].profiles == []
    assert test_output.overlays[0].eclasses == brya_eclasses
    assert test_output.overlays[0].ebuilds == []
    assert test_output.overlays[1].ebuilds == elm_ebuilds_metadata
