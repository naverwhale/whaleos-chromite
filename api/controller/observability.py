# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Observability API Service.

The monitoring-related API endpoints should generally be found here.
"""

from typing import Dict, Tuple, TYPE_CHECKING

from chromite.api import faux
from chromite.api import validate
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import constants
from chromite.service import observability as observability_service


if TYPE_CHECKING:
    from chromite.api.gen.chromite.api import observability_pb2


# Dict to allow easily translating names to enum ids and vice versa.
_IMAGE_MAPPING = {
    common_pb2.IMAGE_TYPE_BASE: constants.IMAGE_TYPE_BASE,
    constants.IMAGE_TYPE_BASE: common_pb2.IMAGE_TYPE_BASE,
    common_pb2.IMAGE_TYPE_DEV: constants.IMAGE_TYPE_DEV,
    constants.IMAGE_TYPE_DEV: common_pb2.IMAGE_TYPE_DEV,
    common_pb2.IMAGE_TYPE_TEST: constants.IMAGE_TYPE_TEST,
    constants.IMAGE_TYPE_TEST: common_pb2.IMAGE_TYPE_TEST,
}


@faux.all_empty
@validate.validation_complete
def GetImageSizeData(
    input_proto: "observability_pb2.GetImageSizeDataRequest",
    output_proto: "observability_pb2.GetImageSizeDataResponse",
    _config: "api_config.ApiConfig",
):
    """Kick off data reshaping and retrieval for ImageSize dataset.

    Args:
        input_proto: The data provided by the request.
        output_proto: The resulting output message.
        _config: The config provided with the API call.
    """
    reshaped_input = {}
    for image in input_proto.built_images:
        if image.type not in _IMAGE_MAPPING:
            continue
        reshaped_input[image.path] = _IMAGE_MAPPING[image.type]

    package_size_data = observability_service.get_image_size_data(
        reshaped_input
    )

    for image_type, package_sizes in package_size_data.items():
        _build_package_size_output(image_type, package_sizes, output_proto)


def _build_package_size_output(
    image_type: str,
    package_sizes: Dict[
        str, Dict[observability_service.PackageIdentifier, Tuple[int, int]]
    ],
    output_proto: "observability_pb2.GetImageSizeDataResponse",
):
    """Convert package size data to equivalent proto format.

    Args:
        image_type: The string representation of the type of image
            (base, dev, test).
        package_sizes: The structured Python dict of partition:(PackageId:size)
        output_proto: The proto to insert structured data into
    """
    image_data_proto = output_proto.image_data.add()
    image_data_proto.image_type = _IMAGE_MAPPING[image_type]
    for partition, package_data in package_sizes.items():
        image_partition_proto = image_data_proto.image_partition_data.add()
        image_partition_proto.partition_name = partition
        partition_apparent_size = 0
        partition_disk_utilization = 0
        # TODO: summation of individual package sizes?
        for package_id, sizes in package_data.items():
            package_size_proto = image_partition_proto.packages.add()
            _get_package_identifier_proto(
                package_id, package_size_proto.identifier
            )
            package_size_proto.apparent_size = sizes[0]
            partition_apparent_size += sizes[0]
            package_size_proto.disk_utilization_size = sizes[1]
            partition_disk_utilization += sizes[1]
        image_partition_proto.partition_apparent_size = partition_apparent_size
        image_partition_proto.partition_disk_utilization_size = (
            partition_disk_utilization
        )


def _get_package_identifier_proto(
    python_copy: observability_service.PackageIdentifier,
    proto_copy: "sizes_pb2.PackageIdentifier",
):
    """Convert PackageIdentifier named tuple to PackageIdentifier protobuf.

    Args:
        python_copy: The named tuple version of PackageIdentifier.
        proto_copy: The protobuf version of PackageIdentifier.

    Returns:
        None
    """
    proto_copy.package_name.atom = python_copy.package_name.atom
    proto_copy.package_name.category = python_copy.package_name.category
    proto_copy.package_name.package_name = python_copy.package_name.package_name
    proto_copy.package_version.major = python_copy.package_version.major
    proto_copy.package_version.minor = python_copy.package_version.minor
    proto_copy.package_version.patch = python_copy.package_version.patch
    proto_copy.package_version.extended = python_copy.package_version.extended
    proto_copy.package_version.revision = python_copy.package_version.revision
    proto_copy.package_version.full_version = (
        python_copy.package_version.full_version
    )
