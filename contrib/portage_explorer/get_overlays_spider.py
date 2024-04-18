# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Spider to get all the overlays."""

from pathlib import Path

from chromite.contrib.portage_explorer import spiderlib
from chromite.lib import constants
from chromite.lib import portage_util


def execute(output: spiderlib.SpiderOutput):
    """Get all overlay source paths and names.

    Get all the overlay paths and names. Parse the overlays for the path
    starting from src/ and get the overlay name from the path. Add all of these
    to the overlays list in output argument.

    Args:
        output: SpiderOutput representing the final output from all the spiders.
    """
    overlay_paths = sorted(portage_util.FindOverlays(constants.BOTH_OVERLAYS))
    for path in overlay_paths:
        src_path = Path(path).relative_to(constants.SOURCE_ROOT)
        overlay_name = portage_util.GetOverlayName(path)
        output.overlays.append(spiderlib.Overlay(src_path, overlay_name))
