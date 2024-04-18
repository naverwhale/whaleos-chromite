# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Spider to get all ebuilds and its package info."""

from chromite.contrib.portage_explorer import spiderlib
from chromite.lib import constants
from chromite.lib import portage_util
from chromite.lib.parser import package_info


def execute(output: spiderlib.SpiderOutput):
    """Get all the ebuilds' src_path, version/revision, and package info.

    Find all ebuilds within all the overlays and parse it using the package_info
    module to find the category, PN, version, and revision for the ebuild.

    Args:
        output: SpiderOutput representing the final output from all the spiders.
    """
    for overlay in output.overlays:
        overlay_ebuilds = []
        overlay_path = constants.SOURCE_ROOT / overlay.path
        for ebuild in portage_util.FindEbuildsForOverlays([overlay_path]):
            ebuild_src_path = ebuild.relative_to(overlay_path)
            ebuild_category = ebuild_src_path.parents[1]
            ebuild_pf = ebuild_src_path.stem
            package = package_info.parse(str(ebuild_category / ebuild_pf))
            spider_ebuild = spiderlib.Ebuild(
                ebuild.relative_to(constants.SOURCE_ROOT), package
            )
            overlay_ebuilds.append(spider_ebuild)
        overlay_ebuilds.sort(key=lambda ebuild: ebuild.package.cpf)
        overlay.ebuilds = overlay_ebuilds
