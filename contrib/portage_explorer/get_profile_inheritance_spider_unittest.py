# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for the get_profile_inheritance_spider."""

from chromite.contrib.portage_explorer import get_profile_inheritance_spider
from chromite.contrib.portage_explorer import spider_testables
from chromite.contrib.portage_explorer import spiderlib


def test_execute(monkeypatch, tmp_path):
    """Test the get_profile_inheritance_spider's execute function.

    Ensure the profiles have the right parents in the right order.
    """
    test_elm, overlay_elm = spider_testables.create_overlays(tmp_path, "elm")
    test_elm_private, overlay_elm_private = spider_testables.create_overlays(
        tmp_path, "elm-private"
    )
    (
        test_elm_private_profiles,
        elm_private_profiles,
        elm_private_profiles_parents,
    ) = spider_testables.create_profiles(
        tmp_path, test_elm_private, ["base", "foo", "bar"]
    )
    (
        test_elm_profiles,
        elm_profiles,
        elm_profiles_parents,
    ) = spider_testables.create_profiles(
        tmp_path,
        test_elm,
        ["base"],
        {
            "base": [
                test_elm_private_profiles["foo"],
                test_elm_private_profiles["base"],
            ]
        },
    )
    with (test_elm_profiles["base"].full_path / "parent").open(
        "a", encoding="utf-8"
    ) as parent_file:
        parent_file.write(
            "elm-private:bar # elm-private:baz\n# elm-private:baz\n "
        )
    elm_profiles_parents["base"].parent_profiles.append("elm-private:bar")
    overlay_elm_private.profiles = [
        elm_private_profiles["base"],
        elm_private_profiles["foo"],
        elm_private_profiles["bar"],
    ]
    overlay_elm.profiles = [
        elm_profiles["base"],
    ]
    test_output = spiderlib.SpiderOutput(
        [],
        [
            overlay_elm,
            overlay_elm_private,
        ],
    )
    monkeypatch.setattr("chromite.lib.constants.SOURCE_ROOT", tmp_path)
    get_profile_inheritance_spider.execute(test_output)
    assert test_output.build_targets == []
    assert test_output.overlays[0].profiles == [
        elm_profiles_parents["base"],
    ]
    assert test_output.overlays[1].profiles == [
        elm_private_profiles_parents["base"],
        elm_private_profiles_parents["foo"],
        elm_private_profiles_parents["bar"],
    ]
