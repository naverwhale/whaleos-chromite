# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Package related functionality."""

import logging

from chromite.api import faux
from chromite.api import validate
from chromite.api.controller import controller_util
from chromite.api.gen.chromite.api import binhost_pb2
from chromite.api.gen.chromite.api import packages_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import portage_util
from chromite.lib.parser import package_info
from chromite.lib.uprev_lib import GitRef
from chromite.service import packages


_OVERLAY_TYPE_TO_NAME = {
    binhost_pb2.OVERLAYTYPE_PUBLIC: constants.PUBLIC_OVERLAYS,
    binhost_pb2.OVERLAYTYPE_PRIVATE: constants.PRIVATE_OVERLAYS,
    binhost_pb2.OVERLAYTYPE_BOTH: constants.BOTH_OVERLAYS,
}


def _UprevResponse(_input_proto, output_proto, _config):
    """Add fake paths to a successful uprev response."""
    output_proto.modified_ebuilds.add().path = "/fake/path1"
    output_proto.modified_ebuilds.add().path = "/fake/path2"


@faux.success(_UprevResponse)
@faux.empty_error
@validate.require("overlay_type")
@validate.is_in("overlay_type", _OVERLAY_TYPE_TO_NAME)
@validate.validation_complete
def Uprev(input_proto, output_proto, _config):
    """Uprev all cros workon ebuilds that have changes."""
    build_targets = controller_util.ParseBuildTargets(input_proto.build_targets)
    overlay_type = _OVERLAY_TYPE_TO_NAME[input_proto.overlay_type]
    chroot = controller_util.ParseChroot(input_proto.chroot)
    output_dir = input_proto.output_dir or None

    try:
        modified_ebuilds, revved_packages = packages.uprev_build_targets(
            build_targets, overlay_type, chroot, output_dir
        )
    except packages.Error as e:
        # Handle module errors nicely, let everything else bubble up.
        cros_build_lib.Die(e)

    for path in modified_ebuilds:
        output_proto.modified_ebuilds.add().path = path

    for package in revved_packages:
        pkg_info = package_info.parse(package)
        pkg_proto = output_proto.packages.add()
        controller_util.serialize_package_info(pkg_info, pkg_proto)


def _UprevVersionedPackageResponse(_input_proto, output_proto, _config):
    """Add fake paths to a successful uprev versioned package response."""
    uprev_response = output_proto.responses.add()
    uprev_response.modified_ebuilds.add().path = "/uprev/response/path"


@faux.success(_UprevVersionedPackageResponse)
@faux.empty_error
@validate.require("versions")
@validate.require("package_info.package_name", "package_info.category")
@validate.validation_complete
def UprevVersionedPackage(input_proto, output_proto, _config):
    """Uprev a versioned package.

    See go/pupr-generator for details about this endpoint.
    """
    chroot = controller_util.ParseChroot(input_proto.chroot)
    build_targets = controller_util.ParseBuildTargets(input_proto.build_targets)
    package = controller_util.deserialize_package_info(input_proto.package_info)
    refs = []
    for ref in input_proto.versions:
        refs.append(
            GitRef(path=ref.repository, ref=ref.ref, revision=ref.revision)
        )

    try:
        result = packages.uprev_versioned_package(
            package, build_targets, refs, chroot
        )
    except packages.Error as e:
        # Handle module errors nicely, let everything else bubble up.
        cros_build_lib.Die(e)

    for modified in result.modified:
        uprev_response = output_proto.responses.add()
        uprev_response.version = modified.new_version
        for path in modified.files:
            uprev_response.modified_ebuilds.add().path = path


@faux.success(_UprevVersionedPackageResponse)
@faux.empty_error
@validate.validation_complete
def RevBumpChrome(_input_proto, output_proto, _config):
    result = packages.revbump_chrome()

    for modified in result.modified:
        uprev_response = output_proto.responses.add()
        uprev_response.version = modified.new_version
        for path in modified.files:
            uprev_response.modified_ebuilds.add().path = path


def _GetBestVisibleResponse(_input_proto, output_proto, _config):
    """Add fake paths to a successful GetBestVisible response."""
    pkg_info_msg = common_pb2.PackageInfo(
        category="category",
        package_name="name",
        version="1.01",
    )
    output_proto.package_info.CopyFrom(pkg_info_msg)


@faux.success(_GetBestVisibleResponse)
@faux.empty_error
@validate.require("atom")
@validate.validation_complete
def GetBestVisible(input_proto, output_proto, _config):
    """Returns the best visible PackageInfo for the indicated atom."""
    build_target = None
    if input_proto.build_target.name:
        build_target = controller_util.ParseBuildTarget(
            input_proto.build_target
        )

    best = packages.get_best_visible(
        input_proto.atom, build_target=build_target
    )
    controller_util.serialize_package_info(best, output_proto.package_info)


def _ChromeVersionResponse(_input_proto, output_proto, _config):
    """Add a fake chrome version to a successful response."""
    output_proto.version = "78.0.3900.0"


@faux.success(_ChromeVersionResponse)
@faux.empty_error
@validate.require("build_target.name")
@validate.validation_complete
def GetChromeVersion(input_proto, output_proto, _config):
    """Returns the chrome version."""
    build_target = controller_util.ParseBuildTarget(input_proto.build_target)
    chrome_version = packages.determine_package_version(
        constants.CHROME_CP, build_target
    )
    if chrome_version:
        output_proto.version = chrome_version


def _GetTargetVersionsResponse(_input_proto, output_proto, _config):
    """Add fake target version fields to a successful response."""
    output_proto.android_version = "5812377"
    output_proto.android_branch_version = "git_nyc-mr1-arc"
    output_proto.android_target_version = "cheets"
    output_proto.chrome_version = "78.0.3900.0"
    output_proto.platform_version = "12438.0.0"
    output_proto.milestone_version = "78"
    output_proto.full_version = "R78-12438.0.0"
    output_proto.lacros_version = "111.0.5550.0"


@faux.success(_GetTargetVersionsResponse)
@faux.empty_error
@validate.require("build_target.name")
@validate.require_each("packages", ["category", "package_name"])
@validate.validation_complete
def GetTargetVersions(input_proto, output_proto, _config):
    """Returns the target versions."""
    build_target = controller_util.ParseBuildTarget(input_proto.build_target)
    package_list = [
        controller_util.deserialize_package_info(x)
        for x in input_proto.packages
    ]
    target_versions = packages.get_target_versions(build_target, package_list)

    output_proto.android_version = target_versions.android_version or ""
    output_proto.android_branch_version = target_versions.android_branch or ""
    output_proto.android_target_version = target_versions.android_target or ""
    output_proto.chrome_version = target_versions.chrome_version or ""
    output_proto.platform_version = target_versions.platform_version or ""
    output_proto.milestone_version = target_versions.milestone_version or ""
    output_proto.full_version = target_versions.full_version or ""
    output_proto.lacros_version = target_versions.lacros_version or ""


def _GetBuilderMetadataResponse(input_proto, output_proto, _config):
    """Add fake metadata fields to a successful response."""
    # Populate only a few fields to validate faux testing.
    build_target_metadata = output_proto.build_target_metadata.add()
    build_target_metadata.build_target = input_proto.build_target.name
    build_target_metadata.android_container_branch = "git_pi-arc"
    model_metadata = output_proto.model_metadata.add()
    model_metadata.model_name = "astronaut"
    model_metadata.ec_firmware_version = "coral_v1.1.1234-56789f"


@faux.success(_GetBuilderMetadataResponse)
@faux.empty_error
@validate.require("build_target.name")
@validate.validation_complete
def GetBuilderMetadata(input_proto, output_proto, _config):
    """Returns the target builder metadata."""
    build_target = controller_util.ParseBuildTarget(input_proto.build_target)
    build_target_metadata = output_proto.build_target_metadata.add()
    build_target_metadata.build_target = build_target.name
    # Android version.
    android_version = packages.determine_android_version(build_target.name)
    logging.info("Found android version: %s", android_version)
    if android_version:
        build_target_metadata.android_container_version = android_version
    # Android branch version.
    android_branch_version = packages.determine_android_branch(
        build_target.name
    )
    logging.info("Found android branch version: %s", android_branch_version)
    if android_branch_version:
        build_target_metadata.android_container_branch = android_branch_version
    # Android target version.
    android_target_version = packages.determine_android_target(
        build_target.name
    )
    logging.info("Found android target version: %s", android_target_version)
    if android_target_version:
        build_target_metadata.android_container_target = android_target_version

    build_target_metadata.arc_use_set = "arc" in portage_util.GetBoardUseFlags(
        build_target.name
    )

    fw_versions = packages.determine_firmware_versions(build_target)
    build_target_metadata.main_firmware_version = (
        fw_versions.main_fw_version or ""
    )
    build_target_metadata.ec_firmware_version = fw_versions.ec_fw_version or ""

    build_target_metadata.kernel_version = (
        packages.determine_kernel_version(build_target) or ""
    )
    fingerprints = packages.find_fingerprints(build_target)
    build_target_metadata.fingerprints.extend(fingerprints)

    models = packages.get_models(build_target)
    if models:
        all_fw_versions = packages.get_all_firmware_versions(build_target)
        for model in models:
            if model in all_fw_versions:
                fw_versions = all_fw_versions[model]
                ec = fw_versions.ec_rw or fw_versions.ec
                main_ro = fw_versions.main
                main_rw = fw_versions.main_rw or main_ro
                # Get the firmware key-id for the current board and model.
                key_id = packages.get_key_id(build_target, model)
                model_metadata = output_proto.model_metadata.add()
                model_metadata.model_name = model
                model_metadata.ec_firmware_version = ec or ""
                model_metadata.firmware_key_id = key_id
                model_metadata.main_readonly_firmware_version = main_ro or ""
                model_metadata.main_readwrite_firmware_version = main_rw or ""


def _HasPrebuiltSuccess(_input_proto, output_proto, _config):
    """The mock success case for HasChromePrebuilt."""
    output_proto.has_prebuilt = True


@faux.success(_HasPrebuiltSuccess)
@faux.empty_error
@validate.require("build_target.name")
@validate.validation_complete
def HasChromePrebuilt(input_proto, output_proto, _config):
    """Checks if the most recent version of Chrome has a prebuilt."""
    build_target = controller_util.ParseBuildTarget(input_proto.build_target)
    useflags = "chrome_internal" if input_proto.chrome else None
    exists = packages.has_prebuilt(
        constants.CHROME_CP, build_target=build_target, useflags=useflags
    )

    output_proto.has_prebuilt = exists


@faux.success(_HasPrebuiltSuccess)
@faux.empty_error
@validate.require(
    "build_target.name", "package_info.category", "package_info.package_name"
)
@validate.validation_complete
def HasPrebuilt(input_proto, output_proto, _config):
    """Checks if the most recent version of Chrome has a prebuilt."""
    build_target = controller_util.ParseBuildTarget(input_proto.build_target)
    package = controller_util.deserialize_package_info(input_proto.package_info)
    useflags = "chrome_internal" if input_proto.chrome else None
    exists = packages.has_prebuilt(
        package.atom, build_target=build_target, useflags=useflags
    )

    output_proto.has_prebuilt = exists


def _BuildsChromeSuccess(_input_proto, output_proto, _config):
    """Mock success case for BuildsChrome."""
    output_proto.builds_chrome = True


@faux.success(_BuildsChromeSuccess)
@faux.empty_error
@validate.require("build_target.name")
@validate.require_each("packages", ["category", "package_name"])
@validate.validation_complete
def BuildsChrome(input_proto, output_proto, _config):
    """Check if the board builds chrome."""
    build_target = controller_util.ParseBuildTarget(input_proto.build_target)
    pkgs = [
        controller_util.deserialize_package_info(x)
        for x in input_proto.packages
    ]
    builds_chrome = packages.builds(constants.CHROME_CP, build_target, pkgs)
    output_proto.builds_chrome = builds_chrome


def _NeedsChromeSourceSuccess(_input_proto, output_proto, _config):
    """Mock success case for NeedsChromeSource."""
    output_proto.needs_chrome_source = True
    output_proto.builds_chrome = True

    output_proto.reasons.append(
        packages_pb2.NeedsChromeSourceResponse.NO_PREBUILT
    )
    pkg_info_msg = output_proto.packages.add()
    pkg_info_msg.category = constants.CHROME_CN
    pkg_info_msg.package_name = constants.CHROME_PN

    output_proto.reasons.append(
        packages_pb2.NeedsChromeSourceResponse.FOLLOWER_LACKS_PREBUILT
    )
    for pkg in constants.OTHER_CHROME_PACKAGES:
        pkg_info_msg = output_proto.packages.add()
        pkg_info = package_info.parse(pkg)
        controller_util.serialize_package_info(pkg_info, pkg_info_msg)


@faux.success(_NeedsChromeSourceSuccess)
@faux.empty_error
@validate.require("install_request.sysroot.build_target.name")
@validate.exists("install_request.sysroot.path")
@validate.validation_complete
def NeedsChromeSource(input_proto, output_proto, _config):
    """Check if the build will need the chrome source."""
    # Input parsing.
    build_target = controller_util.ParseBuildTarget(
        input_proto.install_request.sysroot.build_target
    )
    compile_source = (
        input_proto.install_request.flags.compile_source
        or input_proto.install_request.flags.toolchain_changed
        or input_proto.install_request.flags.bazel
    )
    pkgs = [
        controller_util.deserialize_package_info(pi)
        for pi in input_proto.install_request.packages
    ]
    use_flags = [f.flag for f in input_proto.install_request.use_flags]

    result = packages.needs_chrome_source(
        build_target,
        compile_source=compile_source,
        packages=pkgs,
        useflags=use_flags,
    )

    # Record everything in the response.
    output_proto.needs_chrome_source = result.needs_chrome_source
    output_proto.builds_chrome = result.builds_chrome

    # Compile source reason.
    if compile_source:
        output_proto.reasons.append(
            packages_pb2.NeedsChromeSourceResponse.COMPILE_SOURCE
        )

    # Local uprev reason.
    if result.local_uprev:
        output_proto.reasons.append(
            packages_pb2.NeedsChromeSourceResponse.LOCAL_UPREV
        )

    # No chrome prebuilt reason.
    if result.missing_chrome_prebuilt:
        output_proto.reasons.append(
            packages_pb2.NeedsChromeSourceResponse.NO_PREBUILT
        )

    # Follower package(s) lack prebuilt reason.
    if result.missing_follower_prebuilt:
        output_proto.reasons.append(
            packages_pb2.NeedsChromeSourceResponse.FOLLOWER_LACKS_PREBUILT
        )

    for pkg in result.packages:
        pkg_info = output_proto.packages.add()
        controller_util.serialize_package_info(pkg, pkg_info)


def _GetAndroidMetadataResponse(_input_proto, output_proto, _config):
    """Mock Android metadata on successful run."""
    output_proto.android_package = "android-vm-rvc"
    output_proto.android_branch = "git_rvc-arc"
    output_proto.android_version = "7123456"


@faux.success(_GetAndroidMetadataResponse)
@faux.empty_error
@validate.require("build_target.name")
@validate.validation_complete
def GetAndroidMetadata(input_proto, output_proto, _config):
    """Returns Android-related metadata."""
    build_target = controller_util.ParseBuildTarget(input_proto.build_target)
    # This returns a full CPVR string, e.g.
    # 'chromeos-base/android-vm-rvc-7336577-r1'
    android_full_package = packages.determine_android_package(build_target.name)
    if android_full_package:
        logging.info("Found Android package: %s", android_full_package)
        info = package_info.parse(android_full_package)
        output_proto.android_package = info.package

        android_branch = packages.determine_android_branch(
            build_target.name, package=android_full_package
        )
        logging.info("Found Android branch: %s", android_branch)
        output_proto.android_branch = android_branch

        android_version = packages.determine_android_version(
            build_target.name, package=android_full_package
        )
        logging.info("Found Android version: %s", android_version)
        output_proto.android_version = android_version
