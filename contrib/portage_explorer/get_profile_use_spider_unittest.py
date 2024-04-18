# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for the get_profile_use_spider."""

from chromite.contrib.portage_explorer import get_profile_use_spider
from chromite.contrib.portage_explorer import spider_testables
from chromite.contrib.portage_explorer import spiderlib


def test_execute(monkeypatch, tmp_path):
    """Test the get_profile_use_spider's execute function.

    Ensure that we are only getting the use flags when sourcing a profile's
    make.defaults file, setting the enabled/disabled property correctly, and
    sorting the use flags.
    """
    test_elm, overlay_elm = spider_testables.create_overlays(tmp_path, "elm")
    (
        test_elm_profiles,
        overlay_elm_profiles,
        overlay_elm_profiles_use,
    ) = spider_testables.create_profiles(
        tmp_path,
        test_elm,
        ["base", "foo"],
        make_defaults={"base": {"USE": "use -flag", "OTHER_KEY": "foo bar"}},
    )
    make_defaults_file = test_elm_profiles["base"].full_path / "make.defaults"
    with make_defaults_file.open("a", encoding="utf-8") as make_defaults_opened:
        make_defaults_opened.write(
            'USE="${USE} -use abc" # USE="${USE} not_flag"'
        )
    overlay_elm_profiles_use["base"].use_flags.insert(
        0, spiderlib.ProfileUse("abc", spiderlib.UseState.ENABLED)
    )
    overlay_elm_profiles_use["base"].set_enabled("use", False)
    overlay_elm.profiles = [
        overlay_elm_profiles["base"],
        overlay_elm_profiles["foo"],
    ]
    test_output = spiderlib.SpiderOutput(
        [],
        [
            overlay_elm,
        ],
    )
    monkeypatch.setattr("chromite.lib.constants.SOURCE_ROOT", tmp_path)
    get_profile_use_spider.execute(test_output)
    assert test_output.build_targets == []
    assert test_output.overlays[0].profiles == [
        overlay_elm_profiles_use["base"],
        overlay_elm_profiles_use["foo"],
    ]
