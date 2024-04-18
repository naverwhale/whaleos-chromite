# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""DLC API Service."""

from typing import List, Optional, TYPE_CHECKING

from chromite.api import controller
from chromite.api import faux
from chromite.api import validate
from chromite.api.controller import controller_util
from chromite.service import image


if TYPE_CHECKING:
    from chromite.api import api_config
    from chromite.api.gen.chromite.api import dlc_pb2


def _GenerateDlcArtifactsResponse(_input_proto, output_proto, _config):
    """Set output_proto success field on a successful SignerTest response."""
    artifact = output_proto.dlc_artifacts.add()
    artifact.image_hash = (
        "88d54cb6b5bba15a71ffda3ca75446eb453bf7fe393e3595d3bc52beb3b61711"
    )
    artifact.image_name = "dlc.img"
    artifact.gs_uri_path = "gs://some/uri/prefix/for/dlc-1"
    artifact.id = "dlc-1"
    return controller.RETURN_CODE_SUCCESS


@faux.success(_GenerateDlcArtifactsResponse)
@faux.empty_error
@validate.require("sysroot")
@validate.validation_complete
def GenerateDlcArtifactsList(
    input_proto: "dlc_pb2.GenerateDlcArtifactsListRequest",
    output_proto: "dlc_pb2.GenerateDlcArtifactsListResponse",
    _config: "api_config.ApiConfig",
) -> Optional[int]:
    """Generate DLC Artifacts List.

    Args:
        input_proto: the input message.
        output_proto: the output message.
        config: the API call config.

    Returns:
        Return code (from __init__.py).
    """
    sysroot = controller_util.ParseSysroot(input_proto.sysroot)

    dlc_artifacts = image.generate_dlc_artifacts_metadata_list(sysroot.path)
    _parse_dlc_artifacts_to_response(output_proto, dlc_artifacts)

    return controller.RETURN_CODE_SUCCESS


def _parse_dlc_artifacts_to_response(
    output: "dlc_pb2.GenerateDlcArtifactsListResponse",
    dlc_artifacts: List[image.DlcArtifactsMetadata],
):
    """Parse the DLC artifacts into the output proto.

    Args:
        output: the output message.
        dlc_artifacts: the list of DLC artifacts.
    """
    for dlc_artifact in dlc_artifacts:
        artifact = output.dlc_artifacts.add()
        artifact.image_hash = dlc_artifact.image_hash
        artifact.image_name = dlc_artifact.image_name
        artifact.gs_uri_path = dlc_artifact.uri_path
        artifact.id = dlc_artifact.identifier
