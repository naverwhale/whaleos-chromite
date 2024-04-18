# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Portage Explorer Spider Controller.

Handles the endpoint for running all the spiders and generating the protobuf.
"""

from chromite.api import faux
from chromite.api import validate
from chromite.contrib import portage_explorer


def _RunSpiders(_input_proto, output_proto, _config_proto):
    """Mock success output for the RunSpiders endpoint."""
    mock_build_target = output_proto.build_targets.add()
    mock_build_target.name = "board"
    mock_build_target.profile_id.id = "profile:base"
    mock_overlay = output_proto.overlays.add()
    mock_overlay.path = "src/overlays/overlay-board"
    mock_overlay.name = "board"
    mock_profile = mock_overlay.profiles.add()
    mock_profile.id = "profile:base"
    mock_profile.path = "src/overlays/overlay-board/profile/base"
    mock_profile.name = "base"
    mock_profile_use = mock_profile.use_flags.add()
    mock_profile_use.name = "-use_flag"
    mock_profile_use.enabled = False
    mock_profile_parent = mock_profile.parent_profiles.add()
    mock_profile_parent.id = "parent:base"
    mock_eclass = mock_overlay.eclasses.add()
    mock_eclass.path = "src/overlays/overlay-board/eclass/eclass.eclass"
    mock_eclass.name = "eclass"
    mock_ebuild = mock_overlay.ebuilds.add()
    mock_ebuild.path = (
        "src/overlays/overlay-board/category/name/name-1-r4.ebuild"
    )
    mock_ebuild.package_info.category = "category"
    mock_ebuild.package_info.package_name = "name"
    mock_ebuild.version = "1.1"
    mock_ebuild.revision = 4
    mock_ebuild.eapi = 7
    mock_ebuild.description = "Description of ebuild."
    mock_ebuild.homepage = "http://homepage.com"
    mock_ebuild.license = "Google"
    mock_ebuild.slot = "0/0"
    mock_ebuild.src_uri = "name-1.1.tar.gz"
    mock_ebuild.restrict = "mirror"
    mock_ebuild.depend = "diff_category/diff_name"
    mock_ebuild.rdepend = "diff_category/diff_name"
    mock_ebuild.bdepend = "diff_category/diff_name"
    mock_ebuild.pdepend = "diff_category/diff_name"
    mock_ebuild_use = mock_ebuild.use_flags.add()
    mock_ebuild_use.name = "+use_flag"
    mock_ebuild_use.default_enabled = True
    mock_ebuild.eclass_inherits.extend(["boo", "far"])


@faux.success(_RunSpiders)
@faux.empty_error
@validate.validation_complete
def RunSpiders(_input_proto, output_proto, _config_proto):
    """Run all the spiders from portage_explorer and enter data into proto."""
    spider_output = portage_explorer.execute()
    for build_target in spider_output.build_targets:
        proto_build_target = output_proto.build_targets.add()
        proto_build_target.name = build_target.name
        proto_build_target.profile_id.id = build_target.profile.id_
    for overlay in spider_output.overlays:
        proto_overlay = output_proto.overlays.add()
        proto_overlay.path = str(overlay.path)
        proto_overlay.name = overlay.name
        for profile in overlay.profiles:
            proto_profile = proto_overlay.profiles.add()
            proto_profile.id = profile.id_
            proto_profile.path = str(profile.path)
            proto_profile.name = profile.name
            for flag in profile.use_flags:
                proto_use = proto_profile.use_flags.add()
                proto_use.name = flag.name
                proto_use.enabled = flag.enabled.value
            for parent in profile.parent_profiles:
                proto_parent = proto_profile.parent_profiles.add()
                proto_parent.id = parent
        for ebuild in overlay.ebuilds:
            proto_ebuild = proto_overlay.ebuilds.add()
            proto_ebuild.path = str(ebuild.path)
            proto_ebuild.package_info.category = ebuild.package.category
            proto_ebuild.package_info.package_name = ebuild.package.package
            proto_ebuild.version = ebuild.package.version
            proto_ebuild.revision = ebuild.package.revision
            proto_ebuild.eapi = ebuild.eapi
            proto_ebuild.description = ebuild.description
            proto_ebuild.homepage = ebuild.homepage
            proto_ebuild.license = ebuild.license_
            proto_ebuild.slot = ebuild.slot
            proto_ebuild.src_uri = ebuild.src_uri
            proto_ebuild.restrict = ebuild.restrict
            proto_ebuild.depend = ebuild.depend
            proto_ebuild.rdepend = ebuild.rdepend
            proto_ebuild.bdepend = ebuild.bdepend
            proto_ebuild.pdepend = ebuild.pdepend
            for flag in ebuild.use_flags:
                proto_use = proto_ebuild.use_flags.add()
                proto_use.name = flag.name
                proto_use.default_enabled = flag.default_enabled.value
            proto_ebuild.eclass_inherits.extend(ebuild.eclass_inherits)
        for eclass in overlay.eclasses:
            proto_eclass = proto_overlay.eclasses.add()
            proto_eclass.path = str(eclass.path)
            proto_eclass.name = eclass.name
