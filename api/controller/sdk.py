# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""SDK chroot operations."""

import os
from pathlib import Path
from typing import Dict, TYPE_CHECKING, Union

from chromite.api import controller
from chromite.api import faux
from chromite.api import validate
from chromite.api.controller import controller_util
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import cros_build_lib
from chromite.lib import path_util
from chromite.lib import sysroot_lib
from chromite.service import sdk


if TYPE_CHECKING:
    from chromite.api import api_config
    from chromite.api.gen.chromite.api import sdk_pb2


def _ChrootVersionResponse(_input_proto, output_proto, _config):
    """Add a fake chroot version to a successful response."""
    output_proto.version.version = 168


def _BinhostCLs(_input_proto, output_proto, _config):
    """Add fake CL identifiers to a successful response."""
    output_proto.cls = [
        "fakecl:1",
        "fakecl:2",
    ]


def _BuildSdkTarballResponse(_input_proto, output_proto, _config):
    """Populate a fake BuildSdkTarballResponse."""
    output_proto.sdk_tarball_path.path = "/fake/sdk/tarball.tar.gz"
    output_proto.sdk_tarball_path.location = common_pb2.Path.OUTSIDE


@faux.success(_BuildSdkTarballResponse)
@validate.require("chroot")
@validate.require("sdk_version")
@validate.validation_complete
def BuildSdkTarball(
    input_proto: "sdk_pb2.BuildSdkTarballRequest",
    output_proto: "sdk_pb2.BuildSdkTarballResponse",
    _config: "api_config.ApiConfig",
) -> None:
    chroot = controller_util.ParseChroot(input_proto.chroot)
    tarball_path = sdk.BuildSdkTarball(
        chroot=chroot,
        sdk_version=input_proto.sdk_version,
    )
    output_proto.sdk_tarball_path.path = str(tarball_path)
    output_proto.sdk_tarball_path.location = common_pb2.Path.OUTSIDE


def _CreateManifestFromSdkResponse(_input_proto, output_proto, _config):
    """Populate a fake CreateManifestFromSdkResponse."""
    output_proto.manifest_path.path = "/fake/sdk/tarball.tar.gz.Manifest"
    output_proto.manifest_path.location = common_pb2.Path.Location.INSIDE


@faux.success(_CreateManifestFromSdkResponse)
@validate.require("chroot")
@validate.require("sdk_path")
@validate.require("dest_dir")
@validate.validation_complete
def CreateManifestFromSdk(
    input_proto: "sdk_pb2.CreateManifestFromSdkRequest",
    output_proto: "sdk_pb2.CreateManifestFromSdkResponse",
    _config: "api_config.ApiConfig",
) -> None:
    """Create a manifest file showing the ebuilds in an SDK."""

    def _assert_path_is_absolute(path: str, name: str):
        """Raise an exception if the given path is not absolute."""
        if not os.path.isabs(path):
            cros_build_lib.Die(f"The {name} must be absolute; got {path}")

    _assert_path_is_absolute(input_proto.chroot.path, "chroot path")
    _assert_path_is_absolute(input_proto.sdk_path.path, "SDK path")
    _assert_path_is_absolute(input_proto.dest_dir.path, "destination directory")

    sdk_path = controller_util.pb2_path_to_pathlib_path(
        input_proto.sdk_path, input_proto.chroot
    )
    dest_dir = controller_util.pb2_path_to_pathlib_path(
        input_proto.dest_dir, input_proto.chroot
    )

    manifest_path = sdk.CreateManifestFromSdk(sdk_path, dest_dir)
    output_proto.manifest_path.path = str(manifest_path)
    output_proto.manifest_path.location = common_pb2.Path.Location.OUTSIDE


@faux.success(_ChrootVersionResponse)
@faux.empty_error
def Create(
    input_proto: "sdk_pb2.CreateRequest",
    output_proto: "sdk_pb2.CreateResponse",
    config: "api_config.ApiConfig",
) -> Union[int, None]:
    """Chroot creation, includes support for replacing an existing chroot.

    Args:
        input_proto: The input proto.
        output_proto: The output proto.
        config: The API call config.

    Returns:
        An error code, None otherwise.
    """
    replace = not input_proto.flags.no_replace
    bootstrap = input_proto.flags.bootstrap
    chroot = controller_util.ParseChroot(input_proto.chroot)

    sdk_version = input_proto.sdk_version
    skip_chroot_upgrade = input_proto.skip_chroot_upgrade
    ccache_disable = input_proto.ccache_disable

    if config.validate_only:
        return controller.RETURN_CODE_VALID_INPUT

    args = sdk.CreateArguments(
        replace=replace,
        bootstrap=bootstrap,
        chroot=chroot,
        sdk_version=sdk_version,
        skip_chroot_upgrade=skip_chroot_upgrade,
        ccache_disable=ccache_disable,
    )

    version = sdk.Create(args)

    if version:
        output_proto.version.version = version
    else:
        # This should be very rare, if ever used, but worth noting.
        cros_build_lib.Die(
            "No chroot version could be found. There was likely an"
            "error creating the chroot that was not detected."
        )


@faux.success(_ChrootVersionResponse)
@faux.empty_error
@validate.require_each("toolchain_targets", ["name"])
@validate.validation_complete
def Update(
    input_proto: "sdk_pb2.UpdateRequest",
    output_proto: "sdk_pb2.UpdateResponse",
    _config: "api_config.ApiConfig",
):
    """Update the chroot.

    Args:
        input_proto: The input proto.
        output_proto: The output proto.
        _config: The API call config.
    """
    build_source = input_proto.flags.build_source
    targets = [target.name for target in input_proto.toolchain_targets]
    toolchain_changed = input_proto.flags.toolchain_changed

    args = sdk.UpdateArguments(
        build_source=build_source,
        toolchain_targets=targets,
        toolchain_changed=toolchain_changed,
    )

    result = sdk.Update(args)
    if result.success:
        output_proto.version.version = result.version
    elif result.failed_pkgs:
        sysroot = sysroot_lib.Sysroot("/")
        controller_util.retrieve_package_log_paths(
            result.failed_pkgs, output_proto, sysroot
        )
        return controller.RETURN_CODE_UNSUCCESSFUL_RESPONSE_AVAILABLE
    else:
        return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY


@faux.all_empty
@validate.require("binhost_gs_bucket")
@validate.require("toolchain_tarball_template")
@validate.validation_complete
def Uprev(input_proto, output_proto, _config):
    """Update SDK version file and prebuilt files to point to the latest SDK.

    Files will be changed locally, but not committed.
    """
    # If the UprevRequest did not specify a target version,
    # check the remote SDK version file on Google Cloud Storage for the latest
    # uprev target.
    target_version = (
        input_proto.version or sdk.get_latest_uprev_target_version()
    )

    # The main uprev logic occurs in service/sdk.py.
    modified_files = sdk.uprev_sdk_and_prebuilts(
        binhost_gs_bucket=input_proto.binhost_gs_bucket,
        sdk_version=target_version,
        toolchain_tarball_template=input_proto.toolchain_tarball_template,
    )

    # Populate the UprevResponse object with the modified files.
    for modified_file in modified_files:
        proto_path = output_proto.modified_files.add()
        proto_path.path = str(modified_file)
        proto_path.location = common_pb2.Path.OUTSIDE
    output_proto.version = target_version


@faux.all_empty
@validate.validation_complete
def Delete(input_proto, _output_proto, _config):
    """Delete a chroot."""
    chroot = controller_util.ParseChroot(input_proto.chroot)
    sdk.Delete(chroot, force=True)


@faux.all_empty
@validate.validation_complete
def Unmount(_input_proto, _output_proto, _config):
    """Unmount a chroot"""
    # Deprecated. Do nothing.


@faux.all_empty
@validate.require("path.path")
@validate.validation_complete
def UnmountPath(input_proto, _output_proto, _config):
    """Unmount a path"""
    sdk.UnmountPath(input_proto.path.path)


@faux.all_empty
@validate.validation_complete
def Clean(input_proto, _output_proto, _config):
    """Clean unneeded files from a chroot."""
    chroot = controller_util.ParseChroot(input_proto.chroot)

    # Default (flagless) call sets 'safe' and 'sysroots'.
    if not (
        input_proto.safe
        or input_proto.images
        or input_proto.sysroots
        or input_proto.tmp
        or input_proto.cache
        or input_proto.logs
        or input_proto.workdirs
        or input_proto.incrementals
    ):
        sdk.Clean(chroot, safe=True, sysroots=True)
    else:
        sdk.Clean(
            chroot,
            safe=input_proto.safe,
            images=input_proto.images,
            sysroots=input_proto.sysroots,
            tmp=input_proto.tmp,
            cache=input_proto.cache,
            logs=input_proto.logs,
            workdirs=input_proto.workdirs,
            incrementals=input_proto.incrementals,
        )


@faux.all_empty
@validate.validation_complete
def BuildPrebuilts(input_proto, output_proto, _config):
    """Build the binary packages that comprise the Chromium OS SDK."""
    chroot = controller_util.ParseChroot(input_proto.chroot)
    host_path, target_path = sdk.BuildPrebuilts(
        chroot,
        board=input_proto.build_target.name,
    )
    # Convert paths to OUTSIDE, rather than using the ResultPath, to avoid
    # unnecessary copying of several-gigabyte directories, and because
    # ResultPath doesn't support returning multiple directories.
    chroot_path_resolver = path_util.ChrootPathResolver(
        chroot_path=Path(input_proto.chroot.path),
        out_path=Path(input_proto.chroot.out_path),
    )
    output_proto.host_prebuilts_path.path = str(
        chroot_path_resolver.FromChroot(host_path),
    )
    output_proto.host_prebuilts_path.location = common_pb2.Path.OUTSIDE
    output_proto.target_prebuilts_path.path = str(
        chroot_path_resolver.FromChroot(target_path),
    )
    output_proto.target_prebuilts_path.location = common_pb2.Path.OUTSIDE


@faux.success(_BinhostCLs)
@faux.empty_error
@validate.require(
    "prepend_version", "version", "upload_location", "sdk_tarball_template"
)
@validate.validation_complete
def CreateBinhostCLs(
    input_proto: "sdk_pb2.CreateBinhostCLsRequest",
    output_proto: "sdk_pb2.CreateBinhostCLsResponse",
    _config: "api_config.ApiConfig",
) -> None:
    """Create CLs to update the binhost to point at uploaded prebuilts."""
    output_proto.cls.extend(
        sdk.CreateBinhostCLs(
            input_proto.prepend_version,
            input_proto.version,
            input_proto.upload_location,
            input_proto.sdk_tarball_template,
        )
    )


@faux.all_empty
@validate.require("prepend_version", "version", "upload_location")
@validate.validation_complete
def UploadPrebuiltPackages(input_proto, _output_proto, _config):
    """Upload prebuilt packages."""
    sdk.UploadPrebuiltPackages(
        controller_util.ParseChroot(input_proto.chroot),
        input_proto.prepend_version,
        input_proto.version,
        input_proto.upload_location,
    )


@faux.all_empty
@validate.validation_complete
def BuildSdkToolchain(input_proto, output_proto, _config):
    """Build cross-compiler packages for the SDK."""
    extra_env: Dict[str, str] = {}
    if input_proto.use_flags:
        extra_env["USE"] = " ".join(use.flag for use in input_proto.use_flags)
    generated_files = sdk.BuildSdkToolchain(extra_env=extra_env)
    output_proto.generated_files.extend(generated_files)
