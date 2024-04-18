# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Build metadata operations."""

from chromite.api import faux
from chromite.api import validate
from chromite.api.controller import controller_util
from chromite.api.gen.chromiumos.build.api import portage_pb2
from chromite.api.gen.chromiumos.build.api import system_image_pb2
from chromite.lib import portage_util
from chromite.lib.parser import package_info
from chromite.service import packages


def _SystemImageMetadataResponse(_input_proto, output_proto, _config):
    response = system_image_pb2.SystemImage()
    portage_build_target = portage_pb2.Portage.BuildTarget(
        overlay_name="overlay-build-target",
        profile_name="base",
        use_flags=["use", "flag"],
        features=["feature"],
    )

    BuildMetadata = system_image_pb2.SystemImage.BuildMetadata
    package_summary = BuildMetadata.PackageSummary(
        arc=BuildMetadata.Arc(version="1.2.3", branch="mock"),
        chrome=BuildMetadata.AshChrome(version="1.2.3.4"),
        chipset=BuildMetadata.Chipset(overlay="mock"),
        kernel=BuildMetadata.Kernel(version="1.2"),
        toolchain=BuildMetadata.Toolchain(version=None),
    )

    output_proto.metadata.build_target = portage_build_target
    output_proto.metadata.package_summary = package_summary
    for cpvr in ["cat/pkg-1.2.3-r4", "foo/bar-5.6.7-r8"]:
        pkg = package_info.parse(cpvr)
        msg = output_proto.metadata.packages.add()
        controller_util.serialize_package_info(pkg, msg)

    return response


@faux.success(_SystemImageMetadataResponse)
@faux.empty_error
@validate.exists("sysroot.path")
@validate.require("sysroot.build_target.name")
@validate.validation_complete
def SystemImageMetadata(input_proto, output_proto, _config):
    sysroot = controller_util.ParseSysroot(input_proto.sysroot)
    build_target = controller_util.ParseBuildTarget(
        input_proto.sysroot.build_target
    )

    portage_build_target = portage_pb2.Portage.BuildTarget(
        overlay_name=getattr(sysroot.build_target_overlay, "name", ""),
        profile_name=sysroot.profile_name,
        use_flags=sysroot.use_flags,
        features=sysroot.features,
    )

    target_versions = packages.get_target_versions(build_target)
    BuildMetadata = system_image_pb2.SystemImage.BuildMetadata
    package_summary = BuildMetadata.PackageSummary(
        arc=BuildMetadata.Arc(
            version=target_versions.android_version,
            branch=target_versions.android_branch,
        ),
        chrome=BuildMetadata.AshChrome(version=target_versions.chrome_version),
        chipset=BuildMetadata.Chipset(overlay=sysroot.chipset or ""),
        kernel=BuildMetadata.Kernel(
            version=packages.determine_kernel_version(build_target) or ""
        ),
    )

    # pylint: disable=line-too-long
    output_proto.system_image.metadata.build_target.portage_build_target.CopyFrom(
        portage_build_target
    )
    # pylint: enable=line-too-long
    output_proto.system_image.metadata.package_summary.CopyFrom(package_summary)

    portage_db = portage_util.PortageDB(sysroot.path)
    for pkg in portage_db.InstalledPackages():
        msg = output_proto.system_image.metadata.packages.add()
        controller_util.serialize_package_info(pkg.package_info, msg)
