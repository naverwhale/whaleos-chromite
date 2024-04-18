# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Routines which facilitate data collection for build operations.

Service module to parse or extract data about build behavior for structured
data storage. Complementary to chromite.lib.metrics, chromite.api.metrics, and
related library usage.
"""

import functools
import logging
import os
import re
from typing import Dict, Iterable, NamedTuple, Pattern, Tuple

from chromite.lib import constants
from chromite.lib import image_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib.parser import package_info


_SUPPORTED_ISCP_PARTITIONS = {
    constants.IMAGE_TYPE_BASE: [constants.PART_ROOT_A],
    constants.IMAGE_TYPE_TEST: [constants.PART_ROOT_A, constants.PART_STATE],
    constants.IMAGE_TYPE_DEV: [constants.PART_ROOT_A, constants.PART_STATE],
}

_STATEFUL_PARTITION_VDB = "var_overlay/db/pkg"
_STATEFUL_PARTITION_INSTALL_PATH = "dev_image"


class PackageVersion(NamedTuple):
    """Container class akin to chromite.observability.PackageVersion proto."""

    major: int
    minor: int
    patch: int
    extended: int
    revision: int
    full_version: str


class PackageName(NamedTuple):
    """Container class akin to chromite.observability.PackageName proto."""

    atom: str
    category: str
    package_name: str


class PackageIdentifier(NamedTuple):
    """Container class like chromite.observability.PackageIdentifier proto."""

    package_name: PackageName
    package_version: PackageVersion


@functools.lru_cache(maxsize=None)
def _get_version_component_regex() -> Pattern:
    # Parse version number, expecting up to 4 integer components arranged
    # like: major[.minor[.patch[.extended]]]
    extended = r"(?:\.(?P<extended>\d+))?"
    patch = rf"(?:\.(?P<patch>\d+){extended})?"
    minor = rf"(?:\.(?P<minor>\d+){patch})?"
    complete = rf"^(?P<major>\d+){minor}"
    return re.compile(complete)


def get_image_size_data(
    image_details: Dict[os.PathLike, str]
) -> Dict[str, Dict[str, Dict[PackageIdentifier, portage_util.PackageSizes]]]:
    """Entry point method to parse input data and retrieve new data.

    Args:
        image_details: A mapping of the path to the image and the image type
            (dev, test, etc).

    Returns:
        A mapping of the image type (base, dev, test) to a partition:package
        mapping.
    """
    package_sizes = {}
    for image_path, image_type in image_details.items():
        result = get_installed_package_data(
            image_type=image_type, image_path=image_path
        )
        package_sizes[image_type] = result
    return package_sizes


def get_installed_package_data(
    image_type: str, image_path: os.PathLike
) -> Dict[str, Dict[PackageIdentifier, portage_util.PackageSizes]]:
    """Function for mounting an image and setting up a package database.

    Utility method which mounts each supported partition of a given image and
    produces the dataset of installed packages and their sizes.

    Args:
        image_type: The type of image being queried (base, dev, test).
        image_path: The path to the image in question.

    Returns:
        A mapping of the partition type (stateful, rootfs) to package details.
    """
    if image_type not in _SUPPORTED_ISCP_PARTITIONS:
        logging.warning("Provided image type is not supported.")
        return {}

    results = {}
    installed_package_files = []
    # We mount the stateful partition in all cases because the stateful
    # partition contains the package db that we need. We do this once and get
    # installed packages once for all image types, regardless of whether we care
    # about what's installed on the stateful partition.

    with osutils.TempDir() as temp_dir:
        # Get a dict of {partition:mountpoint}, including state always.
        partitions = set(
            _SUPPORTED_ISCP_PARTITIONS[image_type] + [constants.PART_STATE]
        )

        with image_lib.LoopbackPartitions(
            path=image_path, destination=temp_dir, part_ids=partitions
        ) as img:
            mount_points = img.Mounted()
            db = portage_util.PortageDB(
                root=mount_points[constants.PART_STATE],
                vdb=_STATEFUL_PARTITION_VDB,
                package_install_path=_STATEFUL_PARTITION_INSTALL_PATH,
            )
            installed_packages = db.InstalledPackages()
            installed_package_files = list(
                zip(
                    installed_packages,
                    [p.ListContents() for p in installed_packages],
                )
            )

            # Now that we have the set of installed packages for the image, we
            # mount each relevant partition that we want to check and calculate
            # the size of the installed package on the partition (if the package
            # is installed on that partition).
            for partition in _SUPPORTED_ISCP_PARTITIONS[image_type]:
                package_install_path = (
                    _STATEFUL_PARTITION_INSTALL_PATH
                    if partition == constants.PART_STATE
                    else ""
                )
                package_install_path = os.path.join(
                    mount_points[partition], package_install_path
                )
                results[partition] = get_package_details_for_partition(
                    package_install_path, installed_package_files
                )
    return results


# TODO(zland): refactor scripts/pkg_size (and this function) to use common
# library. This implementation does not want to recreate metrics records for the
# base image's rootfs, and we may not want to append all of the partition &
# image information to metrics, so a simplified approach to
# chromite/scripts/pkg_size is being used here.
def get_package_details_for_partition(
    installation_path: os.PathLike,
    pkgs: Iterable[
        Tuple[portage_util.InstalledPackage, Iterable[Tuple[str, str]]]
    ],
) -> Dict[PackageIdentifier, portage_util.PackageSizes]:
    """Retrieve package size and format name details for |pkgs|.

    Args:
        installation_path: The path to the partition's root that the package's
            installed files are relative to.
        pkgs: The packages of interest in the partition (typically, the entire
            contents of the package db).
    """
    details = {}
    for installed_package, pkg_fileset in pkgs:
        sizes = portage_util.CalculatePackageSize(
            pkg_fileset, installation_path
        )
        pkg_identifier = parse_package_name(installed_package.package_info)
        details[pkg_identifier] = sizes
    return details


def parse_package_name(pkg_info: package_info.PackageInfo) -> PackageIdentifier:
    """Produce detailed NamedTuple for a package from a PackageInfo object."""
    # Version number parsing, looking for 1-4 numerical components and ignoring
    # any alphanumeric suffixes (e.g. _alpha1).
    matcher = _get_version_component_regex()
    matches = matcher.match(pkg_info.version)
    major = int(matches.group("major") or 0)
    minor = int(matches.group("minor") or 0)
    patch = int(matches.group("patch") or 0)
    extended = int(matches.group("extended") or 0)
    version = PackageVersion(
        major=major,
        minor=minor,
        patch=patch,
        extended=extended,
        revision=pkg_info.revision,
        full_version=pkg_info.vr,
    )
    name = PackageName(
        atom=pkg_info.atom,
        category=pkg_info.category,
        package_name=pkg_info.package,
    )
    return PackageIdentifier(package_name=name, package_version=version)
