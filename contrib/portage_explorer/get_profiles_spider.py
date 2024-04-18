# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Spider to get all profiles and connect them to the correct board/overlay."""

from chromite.contrib.portage_explorer import get_boards_spider
from chromite.contrib.portage_explorer import spiderlib
from chromite.lib import constants


def execute(output: spiderlib.SpiderOutput):
    """Get all profiles and add to respective overlay and board.

    Read all overlays' profiles folder and record the profile's id
    (overlay_name:profile_name), src path, and name. Connect the profiles to
    overlays and boards. Connect a profile to a board's private overlay's base
    profile if it exists, else the public overlay's base profile.

    Args:
        output: SpiderOutput representing the final output from all the spiders.
    """
    board_profiles = {}
    for overlay in output.overlays:
        overlay_profiles_path = (
            constants.SOURCE_ROOT / overlay.path / "profiles"
        )
        for profile_path in overlay_profiles_path.glob("*/"):
            if profile_path.is_dir():
                profile_name = profile_path.name
                profile_id = f"{overlay.name}:{profile_name}"
                profile_src_path = overlay.path / "profiles" / profile_name
                profile = spiderlib.Profile(
                    profile_id, profile_src_path, profile_name
                )
                overlay.profiles.append(profile)
                board_name = get_boards_spider.get_board_name(str(overlay.path))
                if "private" in overlay.name and profile_name == "base":
                    board_profiles[board_name] = profile
                elif (
                    board_name not in board_profiles and profile_name == "base"
                ):
                    board_profiles[board_name] = profile
            overlay.profiles = sorted(
                overlay.profiles, key=lambda profile: profile.name
            )
    for build_target in output.build_targets:
        build_target.profile = board_profiles[build_target.name]
