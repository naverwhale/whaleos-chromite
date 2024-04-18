# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implements ArtifactService."""

import logging
import os
from typing import Any, NamedTuple, Optional, TYPE_CHECKING

from chromite.api import controller
from chromite.api import faux
from chromite.api import validate
from chromite.api.controller import controller_util
from chromite.api.controller import image as image_controller
from chromite.api.controller import sysroot as sysroot_controller
from chromite.api.controller import test as test_controller
from chromite.api.gen.chromite.api import artifacts_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import sysroot_lib
from chromite.service import artifacts
from chromite.service import test


if TYPE_CHECKING:
    from chromite.api import api_config


class RegisteredGet(NamedTuple):
    """A registered function for calling Get on an artifact type."""

    output_proto: artifacts_pb2.GetResponse
    artifact_dict: Any


def ExampleGetResponse(_input_proto, _output_proto, _config) -> Optional[int]:
    """Give an example GetResponse with a minimal coverage set."""
    _output_proto = artifacts_pb2.GetResponse(
        artifacts=common_pb2.UploadedArtifactsByService(
            image=image_controller.ExampleGetResponse(),
            sysroot=sysroot_controller.ExampleGetResponse(),
        )
    )
    return controller.RETURN_CODE_SUCCESS


@faux.empty_error
@faux.success(ExampleGetResponse)
@validate.exists("result_path.path.path")
@validate.validation_complete
def Get(
    input_proto: artifacts_pb2.GetRequest,
    output_proto: artifacts_pb2.GetResponse,
    _config: "api_config.ApiConfig",
) -> Optional[int]:
    """Get all artifacts.

    Get all artifacts for the build.

    Note: As the individual artifact_type bundlers are added here, they *must*
    stop uploading it via the individual bundler function.
    """
    output_dir = input_proto.result_path.path.path

    sysroot = controller_util.ParseSysroot(input_proto.sysroot)
    # This endpoint does not currently support any artifacts that are built
    # without a sysroot being present.
    if not sysroot.path:
        return controller.RETURN_CODE_SUCCESS

    chroot = controller_util.ParseChroot(input_proto.chroot)
    build_target = controller_util.ParseBuildTarget(
        input_proto.sysroot.build_target
    )

    # A list of RegisteredGet tuples (input proto, output proto, get results).
    get_res_list = [
        RegisteredGet(
            output_proto.artifacts.image,
            image_controller.GetArtifacts(
                input_proto.artifact_info.image,
                chroot,
                sysroot,
                build_target,
                output_dir,
            ),
        ),
        RegisteredGet(
            output_proto.artifacts.sysroot,
            sysroot_controller.GetArtifacts(
                input_proto.artifact_info.sysroot,
                chroot,
                sysroot,
                build_target,
                output_dir,
            ),
        ),
        RegisteredGet(
            output_proto.artifacts.test,
            test_controller.GetArtifacts(
                input_proto.artifact_info.test,
                chroot,
                sysroot,
                build_target,
                output_dir,
            ),
        ),
    ]

    for get_res in get_res_list:
        for artifact_dict in get_res.artifact_dict:
            kwargs = {}
            # TODO(b/255838545): Remove the kwargs funkness when these fields
            # have been added for all services.
            if "failed" in artifact_dict:
                kwargs["failed"] = artifact_dict.get("failed", False)
                kwargs["failure_reason"] = artifact_dict.get("failure_reason")
            get_res.output_proto.artifacts.add(
                artifact_type=artifact_dict["type"],
                paths=[
                    common_pb2.Path(
                        path=x, location=common_pb2.Path.Location.OUTSIDE
                    )
                    for x in artifact_dict.get("paths", [])
                ],
                **kwargs,
            )
    return controller.RETURN_CODE_SUCCESS


def _BuildSetupResponse(_input_proto, output_proto, _config) -> None:
    """Just return POINTLESS for now."""
    # All the artifact types we support claim that the build is POINTLESS.
    output_proto.build_relevance = artifacts_pb2.BuildSetupResponse.POINTLESS


@faux.success(_BuildSetupResponse)
@faux.empty_error
@validate.validation_complete
def BuildSetup(
    _input_proto: artifacts_pb2.GetRequest,
    output_proto: artifacts_pb2.GetResponse,
    _config: "api_config.ApiConfig",
) -> Optional[int]:
    """Setup anything needed for building artifacts

    If any artifact types require steps prior to building the package, they go
    here.  For example, see ToolchainService/PrepareForBuild.

    Note: crbug/1034529 introduces this method as a noop.  As the individual
    artifact_type bundlers are added here, they *must* stop uploading it via the
    individual bundler function.
    """
    # If any artifact_type says "NEEDED", the return is NEEDED.
    # Otherwise, if any artifact_type says "UNKNOWN", the return is UNKNOWN.
    # Otherwise, the return is POINTLESS.
    output_proto.build_relevance = artifacts_pb2.BuildSetupResponse.POINTLESS
    return controller.RETURN_CODE_SUCCESS


def _GetImageDir(build_root: str, target: str) -> Optional[str]:
    """Return path containing images for the given build target.

    TODO(saklein) Expand image_lib.GetLatestImageLink to support this use case.

    Args:
        build_root: Path to checkout where build occurs.
        target: Name of the build target.

    Returns:
        Path to the latest directory containing target images or None.
    """
    image_dir = os.path.join(build_root, "src/build/images", target, "latest")
    if not os.path.exists(image_dir):
        logging.warning(
            "Expected to find image output for target %s at %s, but "
            "path does not exist",
            target,
            image_dir,
        )
        return None

    return image_dir


def _BundleImageArchivesResponse(input_proto, output_proto, _config) -> None:
    """Add artifact paths to a successful response."""
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(
                input_proto.result_path.path.path, "path0.tar.xz"
            ),
            location=common_pb2.Path.OUTSIDE,
        )
    )
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(
                input_proto.result_path.path.path, "path1.tar.xz"
            ),
            location=common_pb2.Path.OUTSIDE,
        )
    )


@faux.success(_BundleImageArchivesResponse)
@faux.empty_error
@validate.require("sysroot.build_target.name", "sysroot.path")
@validate.exists("result_path.path.path")
@validate.validation_complete
def BundleImageArchives(
    input_proto: artifacts_pb2.BundleRequest,
    output_proto: artifacts_pb2.BundleResponse,
    _config: "api_config.ApiConfig",
) -> Optional[int]:
    """Create a .tar.xz archive for each image that has been created."""
    build_target = controller_util.ParseBuildTarget(
        input_proto.sysroot.build_target
    )
    chroot = controller_util.ParseChroot(input_proto.chroot)
    sysroot = controller_util.ParseSysroot(input_proto.sysroot)
    output_dir = input_proto.result_path.path.path
    image_dir = _GetImageDir(constants.SOURCE_ROOT, build_target.name)
    if image_dir is None:
        return

    if not sysroot.Exists(chroot=chroot):
        logging.warning("Sysroot does not exist: %s", sysroot.path)

    archives = artifacts.ArchiveImages(chroot, sysroot, image_dir, output_dir)

    for archive in archives:
        output_proto.artifacts.add(
            artifact_path=common_pb2.Path(
                path=os.path.join(output_dir, archive),
                location=common_pb2.Path.OUTSIDE,
            )
        )


def _BundleImageZipResponse(input_proto, output_proto, _config) -> None:
    """Add artifact zip files to a successful response."""
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(input_proto.result_path.path.path, "image.zip"),
            location=common_pb2.Path.OUTSIDE,
        )
    )


@faux.success(_BundleImageZipResponse)
@faux.empty_error
@validate.require("build_target.name", "result_path.path.path")
@validate.exists("result_path.path.path")
@validate.validation_complete
def BundleImageZip(
    input_proto: artifacts_pb2.BundleRequest,
    output_proto: artifacts_pb2.BundleResponse,
    _config: "api_config.ApiConfig",
) -> Optional[int]:
    """Bundle image.zip."""
    target = input_proto.build_target.name
    output_dir = input_proto.result_path.path.path
    image_dir = _GetImageDir(constants.SOURCE_ROOT, target)
    if image_dir is None:
        logging.warning("Image build directory not found.")
        return None

    archive = artifacts.BundleImageZip(output_dir, image_dir)
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(output_dir, archive),
            location=common_pb2.Path.OUTSIDE,
        )
    )


def _BundleTestUpdatePayloadsResponse(
    input_proto, output_proto, _config
) -> None:
    """Add test payload files to a successful response."""
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(
                input_proto.result_path.path.path, "payload1.bin"
            ),
            location=common_pb2.Path.OUTSIDE,
        )
    )
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(
                input_proto.result_path.path.path, "payload1.json"
            ),
            location=common_pb2.Path.OUTSIDE,
        )
    )
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(
                input_proto.result_path.path.path, "payload1.log"
            ),
            location=common_pb2.Path.OUTSIDE,
        )
    )


@faux.success(_BundleTestUpdatePayloadsResponse)
@faux.empty_error
@validate.require("build_target.name")
@validate.validation_complete
def BundleTestUpdatePayloads(
    input_proto: artifacts_pb2.BundleRequest,
    output_proto: artifacts_pb2.BundleResponse,
    _config: "api_config.ApiConfig",
) -> Optional[int]:
    """Generate minimal update payloads for the build target for testing."""
    target = input_proto.build_target.name
    chroot = controller_util.ParseChroot(input_proto.chroot)
    build_root = constants.SOURCE_ROOT
    # Leave artifact output intact, for the router layer to copy it out of the
    # chroot. This may leave stray files leftover, but builders should clean
    # these up.
    output_dir = chroot.tempdir(delete=False)

    # Use the first available image to create the update payload.
    img_dir = _GetImageDir(build_root, target)
    if img_dir is None:
        return None

    img_types = [
        constants.IMAGE_TYPE_TEST,
        constants.IMAGE_TYPE_DEV,
        constants.IMAGE_TYPE_BASE,
    ]
    img_names = [constants.IMAGE_TYPE_TO_NAME[t] for t in img_types]
    img_paths = [os.path.join(img_dir, x) for x in img_names]
    valid_images = [x for x in img_paths if os.path.exists(x)]

    if not valid_images:
        cros_build_lib.Die(
            'Expected to find an image of type among %r for target "%s" '
            "at path %s.",
            img_types,
            target,
            img_dir,
        )
    image = valid_images[0]

    payloads = artifacts.BundleTestUpdatePayloads(
        chroot, image, str(output_dir)
    )
    for payload in payloads:
        output_proto.artifacts.add(
            artifact_path=common_pb2.Path(
                path=payload, location=common_pb2.Path.INSIDE
            ),
        )


def _BundleAutotestFilesResponse(input_proto, output_proto, _config) -> None:
    """Add test autotest files to a successful response."""
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(
                input_proto.result_path.path.path, "autotest-a.tar.gz"
            ),
            location=common_pb2.Path.OUTSIDE,
        )
    )


@faux.success(_BundleAutotestFilesResponse)
@faux.empty_error
@validate.require("sysroot.path")
@validate.exists("result_path.path.path")
@validate.validation_complete
def BundleAutotestFiles(
    input_proto: artifacts_pb2.BundleRequest,
    output_proto: artifacts_pb2.BundleResponse,
    _config: "api_config.ApiConfig",
) -> Optional[int]:
    """Tar the autotest files for a build target."""
    output_dir = input_proto.result_path.path.path
    chroot = controller_util.ParseChroot(input_proto.chroot)
    sysroot = controller_util.ParseSysroot(input_proto.sysroot)

    if not sysroot.Exists(chroot=chroot):
        logging.warning("Sysroot does not exist: %s", sysroot.path)
        return

    try:
        # Note that this returns the full path to *multiple* tarballs.
        archives = artifacts.BundleAutotestFiles(chroot, sysroot, output_dir)
    except artifacts.Error as e:
        logging.warning(e)
        return

    for archive in archives.values():
        output_proto.artifacts.add(
            artifact_path=common_pb2.Path(
                path=archive, location=common_pb2.Path.OUTSIDE
            )
        )


def _BundleTastFilesResponse(input_proto, output_proto, _config) -> None:
    """Add test tast files to a successful response."""
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(
                input_proto.result_path.path.path, "tast_bundles.tar.gz"
            ),
            location=common_pb2.Path.OUTSIDE,
        )
    )


@faux.success(_BundleTastFilesResponse)
@faux.empty_error
@validate.require("sysroot.path")
@validate.exists("result_path.path.path")
@validate.validation_complete
def BundleTastFiles(
    input_proto: artifacts_pb2.BundleRequest,
    output_proto: artifacts_pb2.BundleResponse,
    _config: "api_config.ApiConfig",
) -> Optional[int]:
    """Tar the tast files for a build target."""
    output_dir = input_proto.result_path.path.path
    chroot = controller_util.ParseChroot(input_proto.chroot)
    sysroot = controller_util.ParseSysroot(input_proto.sysroot)

    if not sysroot.Exists(chroot=chroot):
        logging.warning("Sysroot does not exist: %s", sysroot.path)
        return

    archive = artifacts.BundleTastFiles(chroot, sysroot, output_dir)

    if not archive:
        logging.warning("Found no tast files for %s.", sysroot.path)
        return

    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=archive, location=common_pb2.Path.OUTSIDE
        )
    )


def BundlePinnedGuestImages(_input_proto, _output_proto, _config):
    # TODO(crbug/1034529): Remove this endpoint
    pass


def FetchPinnedGuestImageUris(_input_proto, _output_proto, _config):
    # TODO(crbug/1034529): Remove this endpoint
    pass


def _FetchMetadataResponse(
    _input_proto, output_proto, _config
) -> Optional[int]:
    """Populate the output_proto with sample data."""
    for fp in ("/metadata/foo.txt", "/metadata/bar.jsonproto"):
        output_proto.filepaths.add(
            path=common_pb2.Path(path=fp, location=common_pb2.Path.OUTSIDE)
        )
    return controller.RETURN_CODE_SUCCESS


@faux.success(_FetchMetadataResponse)
@faux.empty_error
@validate.exists("chroot.path")
@validate.require("sysroot.path")
@validate.validation_complete
def FetchMetadata(
    input_proto: artifacts_pb2.FetchMetadataRequest,
    output_proto: artifacts_pb2.FetchMetadataResponse,
    _config: "api_config.ApiConfig",
) -> Optional[int]:
    """FetchMetadata returns the paths to all build/test metadata files.

    This implements ArtifactsService.FetchMetadata.
    """
    chroot = controller_util.ParseChroot(input_proto.chroot)
    sysroot = controller_util.ParseSysroot(input_proto.sysroot)
    for path in test.FindAllMetadataFiles(chroot, sysroot):
        output_proto.filepaths.add(
            path=common_pb2.Path(path=path, location=common_pb2.Path.OUTSIDE)
        )
    return controller.RETURN_CODE_SUCCESS


def _BundleFirmwareResponse(input_proto, output_proto, _config):
    """Add test firmware image files to a successful response."""
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(
                input_proto.result_path.path.path, "firmware.tar.gz"
            ),
            location=common_pb2.Path.OUTSIDE,
        )
    )


@faux.success(_BundleFirmwareResponse)
@faux.empty_error
@validate.require("sysroot.path")
@validate.exists("result_path.path.path")
@validate.validation_complete
def BundleFirmware(
    input_proto: artifacts_pb2.BundleRequest,
    output_proto: artifacts_pb2.BundleResponse,
    _config: "api_config.ApiConfig",
) -> Optional[int]:
    """Tar the firmware images for a build target."""
    output_dir = input_proto.result_path.path.path
    chroot = controller_util.ParseChroot(input_proto.chroot)
    sysroot = controller_util.ParseSysroot(input_proto.sysroot)

    if not chroot.exists():
        logging.warning("Chroot does not exist: %s", chroot.path)
        return
    elif not sysroot.Exists(chroot=chroot):
        logging.warning("Sysroot does not exist: %s", sysroot.path)
        return

    archive = artifacts.BuildFirmwareArchive(chroot, sysroot, output_dir)

    if not archive:
        logging.warning(
            "Could not create firmware archive. No firmware found for %s.",
            sysroot.path,
        )
        return

    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=archive, location=common_pb2.Path.OUTSIDE
        )
    )


def _BundleFpmcuUnittestsResponse(input_proto, output_proto, _config) -> None:
    """Add fingerprint MCU unittest binaries to a successful response."""
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(
                input_proto.result_path.path.path, "fpmcu_unittests.tar.gz"
            ),
            location=common_pb2.Path.OUTSIDE,
        )
    )


@faux.success(_BundleFpmcuUnittestsResponse)
@faux.empty_error
@validate.require("sysroot.path")
@validate.exists("result_path.path.path")
@validate.validation_complete
def BundleFpmcuUnittests(
    input_proto: artifacts_pb2.BundleRequest,
    output_proto: artifacts_pb2.BundleResponse,
    _config: "api_config.ApiConfig",
) -> Optional[int]:
    """Tar the fingerprint MCU unittest binaries for a build target."""
    output_dir = input_proto.result_path.path.path
    chroot = controller_util.ParseChroot(input_proto.chroot)
    sysroot = controller_util.ParseSysroot(input_proto.sysroot)

    if not chroot.exists():
        logging.warning("Chroot does not exist: %s", chroot.path)
        return
    elif not sysroot.Exists(chroot=chroot):
        logging.warning("Sysroot does not exist: %s", sysroot.path)
        return

    archive = artifacts.BundleFpmcuUnittests(chroot, sysroot, output_dir)

    if not archive:
        logging.warning("No fpmcu unittests found for %s.", sysroot.path)
        return

    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=archive, location=common_pb2.Path.OUTSIDE
        )
    )


def _BundleEbuildLogsResponse(input_proto, output_proto, _config) -> None:
    """Add test log files to a successful response."""
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(
                input_proto.result_path.path.path, "ebuild-logs.tar.gz"
            ),
            location=common_pb2.Path.OUTSIDE,
        )
    )


@faux.success(_BundleEbuildLogsResponse)
@faux.empty_error
@validate.require("sysroot.path")
@validate.exists("result_path.path.path")
@validate.validation_complete
def BundleEbuildLogs(
    input_proto: artifacts_pb2.BundleRequest,
    output_proto: artifacts_pb2.BundleResponse,
    _config: "api_config.ApiConfig",
) -> Optional[int]:
    """Tar the ebuild logs for a build target."""
    output_dir = input_proto.result_path.path.path
    chroot = controller_util.ParseChroot(input_proto.chroot)
    sysroot = controller_util.ParseSysroot(input_proto.sysroot)

    if not sysroot.Exists(chroot=chroot):
        logging.warning("Sysroot does not exist: %s", sysroot.path)
        return

    archive = artifacts.BundleEBuildLogsTarball(chroot, sysroot, output_dir)

    if not archive:
        logging.warning(
            "Could not create ebuild logs archive. No logs found for %s.",
            sysroot.path,
        )
        return

    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(output_dir, archive),
            location=common_pb2.Path.OUTSIDE,
        )
    )


def _BundleChromeOSConfigResponse(input_proto, output_proto, _config) -> None:
    """Add test config files to a successful response."""
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(input_proto.result_path.path.path, "config.yaml"),
            location=common_pb2.Path.OUTSIDE,
        )
    )


@faux.success(_BundleChromeOSConfigResponse)
@faux.empty_error
@validate.require("sysroot.path")
@validate.exists("result_path.path.path")
@validate.validation_complete
def BundleChromeOSConfig(
    input_proto: artifacts_pb2.BundleRequest,
    output_proto: artifacts_pb2.BundleResponse,
    _config: "api_config.ApiConfig",
) -> Optional[int]:
    """Output the ChromeOS Config payload for a build target."""
    output_dir = input_proto.result_path.path.path
    chroot = controller_util.ParseChroot(input_proto.chroot)
    sysroot = controller_util.ParseSysroot(input_proto.sysroot)

    chromeos_config = artifacts.BundleChromeOSConfig(
        chroot, sysroot, output_dir
    )

    if not chromeos_config:
        logging.warning(
            "Could not create ChromeOS Config for %s.", sysroot.path
        )
        return

    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(output_dir, chromeos_config),
            location=common_pb2.Path.OUTSIDE,
        )
    )


def _BundleSimpleChromeArtifactsResponse(
    input_proto, output_proto, _config
) -> None:
    """Add test simple chrome files to a successful response."""
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(
                input_proto.result_path.path.path, "simple_chrome.txt"
            ),
            location=common_pb2.Path.OUTSIDE,
        )
    )


@faux.success(_BundleSimpleChromeArtifactsResponse)
@faux.empty_error
@validate.require(
    "result_path.path.path", "sysroot.build_target.name", "sysroot.path"
)
@validate.exists("result_path.path.path")
@validate.validation_complete
def BundleSimpleChromeArtifacts(
    input_proto, output_proto, _config
) -> Optional[int]:
    """Create the simple chrome artifacts."""
    sysroot_path = input_proto.sysroot.path
    output_dir = input_proto.result_path.path.path

    # Build out the argument instances.
    build_target = controller_util.ParseBuildTarget(
        input_proto.sysroot.build_target
    )
    chroot = controller_util.ParseChroot(input_proto.chroot)
    # Sysroot.path needs to be the fully qualified path, including the chroot.
    full_sysroot_path = chroot.full_path(sysroot_path)
    sysroot = sysroot_lib.Sysroot(full_sysroot_path)

    # Check that the sysroot exists before we go on.
    if not sysroot.Exists():
        logging.warning("The sysroot does not exist.")
        return

    try:
        results = artifacts.BundleSimpleChromeArtifacts(
            chroot, sysroot, build_target, output_dir
        )
    except artifacts.Error as e:
        logging.warning(
            "Error %s raised in BundleSimpleChromeArtifacts: %s", type(e), e
        )
        return

    for file_name in results:
        output_proto.artifacts.add(
            artifact_path=common_pb2.Path(
                path=file_name, location=common_pb2.Path.OUTSIDE
            )
        )


def _BundleVmFilesResponse(input_proto, output_proto, _config) -> None:
    """Add test vm files to a successful response."""
    output_proto.artifacts.add().path = os.path.join(
        input_proto.output_dir, "f1.tar"
    )


@faux.success(_BundleVmFilesResponse)
@faux.empty_error
@validate.require("chroot.path", "test_results_dir", "output_dir")
@validate.exists("output_dir")
@validate.validation_complete
def BundleVmFiles(
    input_proto: artifacts_pb2.BundleVmFilesRequest,
    output_proto: artifacts_pb2.BundleResponse,
    _config: "api_config.ApiConfig",
) -> None:
    """Tar VM disk and memory files."""
    chroot = controller_util.ParseChroot(input_proto.chroot)
    test_results_dir = input_proto.test_results_dir
    output_dir = input_proto.output_dir

    archives = artifacts.BundleVmFiles(chroot, test_results_dir, output_dir)
    for archive in archives:
        output_proto.artifacts.add().path = archive


def _BundleGceTarballResponse(input_proto, output_proto, _config) -> None:
    """Add artifact tarball to a successful response."""
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=os.path.join(
                input_proto.result_path.path.path, constants.TEST_IMAGE_GCE_TAR
            ),
            location=common_pb2.Path.OUTSIDE,
        )
    )


@faux.success(_BundleGceTarballResponse)
@faux.empty_error
@validate.require("build_target.name", "result_path.path.path")
@validate.exists("result_path.path.path")
@validate.validation_complete
def BundleGceTarball(
    input_proto: artifacts_pb2.BundleRequest,
    output_proto: artifacts_pb2.BundleResponse,
    _config: "api_config.ApiConfig",
) -> Optional[int]:
    """Bundle the test image into a tarball suitable for importing into GCE."""
    target = input_proto.build_target.name
    output_dir = input_proto.result_path.path.path
    image_dir = _GetImageDir(constants.SOURCE_ROOT, target)
    if image_dir is None:
        return None

    tarball = artifacts.BundleGceTarball(output_dir, image_dir)
    output_proto.artifacts.add(
        artifact_path=common_pb2.Path(
            path=tarball, location=common_pb2.Path.OUTSIDE
        )
    )
