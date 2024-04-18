# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Spider to get metadata about every ebuild."""

from chromite.contrib.portage_explorer import spiderlib
from chromite.lib import constants
from chromite.utils import key_value_store


def execute(output: spiderlib.SpiderOutput):
    """Get all the ebuild metadata for all the ebuilds.

    Get the EAPI, DESCRIPTION, HOMEPAGE, LICENSE, SLOT, SRC_URI, RESTRICT,
    DEPEND, RDEPEND, BDEPEND, PDEPEND, IUSE, and the eclasses inherited for
    every ebuild by reading its md5-cache if it has one.

    Args:
        output: SpiderOutput representing the final output from all the spiders.
    """
    for overlay in output.overlays:
        for ebuild in overlay.ebuilds:
            md5_cache_path = (
                constants.SOURCE_ROOT
                / overlay.path
                / "metadata"
                / "md5-cache"
                / ebuild.package.category
                / ebuild.package.pvr
            )
            if not md5_cache_path.exists():
                continue
            store_data = key_value_store.LoadData(
                md5_cache_path.read_text(encoding="utf-8")
            )
            ebuild.eapi = int(store_data.get("EAPI", 0))
            ebuild.description = store_data.get("DESCRIPTION", "")
            ebuild.homepage = store_data.get("HOMEPAGE", "")
            ebuild.license_ = store_data.get("LICENSE", "")
            ebuild.slot = store_data.get("SLOT", "")
            ebuild.src_uri = store_data.get("SRC_URI", "")
            ebuild.restrict = store_data.get("RESTRICT", "")
            ebuild.depend = store_data.get("DEPEND", "")
            ebuild.rdepend = store_data.get("RDEPEND", "")
            ebuild.bdepend = store_data.get("BDEPEND", "")
            ebuild.pdepend = store_data.get("PDEPEND", "")
            use_flags = store_data.get("IUSE", "").split()
            for flag in use_flags:
                ebuild.add_use_flag(flag)
            ebuild.use_flags.sort(key=lambda ebuild_use: ebuild_use.name)
            _eclasses_ = store_data.get("_eclasses_", "").split()
            hold_eclasses = sorted(_eclasses_[::2])
            ebuild.eclass_inherits = hold_eclasses
