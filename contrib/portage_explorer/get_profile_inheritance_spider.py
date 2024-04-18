# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Spider to get the parent profiles a profile inherits from."""

from chromite.contrib.portage_explorer import spiderlib
from chromite.lib import constants


def execute(output: spiderlib.SpiderOutput):
    """Get the parent profiles from the parent file for each profile.

    Read the parent file for each profile, the profile inherits from each of the
    profiles listed there. Keep the order of the profiles as found since the
    profiles inherit in that order.

    Args:
        output: SpiderOutput representing the final output from all the spiders.
    """
    for overlay in output.overlays:
        for profile in overlay.profiles:
            parent_file = constants.SOURCE_ROOT / profile.path / "parent"
            if parent_file.exists():
                for line in parent_file.open(encoding="utf-8"):
                    line = line.split("#")[0].strip()
                    if line:
                        profile.parent_profiles.append(line)
