# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for the get_profiles_spider."""

from chromite.contrib.portage_explorer import get_profiles_spider
from chromite.contrib.portage_explorer import spider_testables
from chromite.contrib.portage_explorer import spiderlib


def test_execute(monkeypatch, tmp_path):
    """Test the get_profiles_spider's execute function.

    Ensure the get_profiles_spider is getting all the right profiles and
    connecting the profiles to the correct overlays and boards.
    """
    overlay_zork = spider_testables.create_overlays(tmp_path, "zork")[1]
    test_brya, overlay_brya = spider_testables.create_overlays(tmp_path, "brya")
    test_elm, overlay_elm = spider_testables.create_overlays(tmp_path, "elm")
    test_brya_private, overlay_brya_private = spider_testables.create_overlays(
        tmp_path, "brya-private"
    )
    test_elm_private, overlay_elm_private = spider_testables.create_overlays(
        tmp_path, "elm-private"
    )
    brya_profiles = spider_testables.create_profiles(
        tmp_path, test_brya, ["base", "foo"]
    )[1]
    elm_profiles = spider_testables.create_profiles(
        tmp_path, test_elm, ["base"]
    )[1]
    brya_private_profiles = spider_testables.create_profiles(
        tmp_path, test_brya_private, ["bar"]
    )[1]
    elm_private_profiles = spider_testables.create_profiles(
        tmp_path, test_elm_private, ["base"]
    )[1]
    build_target_brya = spiderlib.BuildTarget("brya")
    build_target_elm = spiderlib.BuildTarget("elm")
    test_output = spiderlib.SpiderOutput(
        [
            build_target_brya,
            build_target_elm,
        ],
        [
            overlay_zork,
            overlay_brya,
            overlay_elm,
            overlay_brya_private,
            overlay_elm_private,
        ],
    )
    monkeypatch.setattr("chromite.lib.constants.SOURCE_ROOT", tmp_path)
    get_profiles_spider.execute(test_output)
    assert test_output.build_targets[0].profile == brya_profiles["base"]
    assert test_output.build_targets[1].profile == elm_private_profiles["base"]
    assert test_output.overlays[0].profiles == []
    assert test_output.overlays[1].profiles == [
        brya_profiles["base"],
        brya_profiles["foo"],
    ]
    assert test_output.overlays[2].profiles == [elm_profiles["base"]]
    assert test_output.overlays[3].profiles == [brya_private_profiles["bar"]]
    assert test_output.overlays[4].profiles == [elm_private_profiles["base"]]
