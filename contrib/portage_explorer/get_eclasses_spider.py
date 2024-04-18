# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Spider to get all eclasses."""

from chromite.contrib.portage_explorer import spiderlib
from chromite.lib import constants


def execute(output: spiderlib.SpiderOutput):
    """Get all eclasses sorted by eclass name.

    Args:
        output: SpiderOutput representing the final output from all the spiders.
    """
    for overlay in output.overlays:
        eclass_folder = constants.SOURCE_ROOT / overlay.path / "eclass"
        eclasses = []
        for eclass in eclass_folder.glob("*.eclass"):
            eclass_name = eclass.stem
            eclass_path = overlay.path / "eclass" / eclass.name
            eclasses.append(spiderlib.Eclass(eclass_path, eclass_name))
        eclasses.sort(key=lambda eclass: eclass.name)
        overlay.eclasses = eclasses
