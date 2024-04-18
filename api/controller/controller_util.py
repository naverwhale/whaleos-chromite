# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility functions that are useful for controllers."""

import glob
import logging
import os
from pathlib import Path
from typing import Iterable, Optional, TYPE_CHECKING, Union

from chromite.api.gen.chromite.api import sdk_subtools_pb2
from chromite.api.gen.chromite.api import sysroot_pb2
from chromite.api.gen.chromite.api import test_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import binpkg
from chromite.lib import build_target_lib
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import goma_lib
from chromite.lib import remoteexec_util
from chromite.lib import sysroot_lib
from chromite.lib.parser import package_info


if TYPE_CHECKING:
    from chromite.api.gen.chromiumos.build.api import portage_pb2


class Error(Exception):
    """Base error class for the module."""


class InvalidMessageError(Error):
    """Invalid message."""


def ParseChroot(chroot_message: common_pb2.Chroot) -> chroot_lib.Chroot:
    """Create a chroot object from the chroot message.

    Args:
        chroot_message: The chroot message.

    Returns:
        Chroot: The parsed chroot object.

    Raises:
        AssertionError: When the message is not a Chroot message.
    """
    assert isinstance(chroot_message, common_pb2.Chroot)

    path = chroot_message.path or constants.DEFAULT_CHROOT_PATH
    cache_dir = chroot_message.cache_dir
    chrome_root = chroot_message.chrome_dir
    out_path = (
        Path(chroot_message.out_path)
        if chroot_message.out_path
        else constants.DEFAULT_OUT_PATH
    )

    use_flags = [u.flag for u in chroot_message.env.use_flags]
    features = [f.feature for f in chroot_message.env.features]

    env = {}
    if use_flags:
        env["USE"] = " ".join(use_flags)

    # Make sure it'll use the local source to build chrome when we have it.
    if chrome_root:
        env["CHROME_ORIGIN"] = "LOCAL_SOURCE"

    if features:
        env["FEATURES"] = " ".join(features)

    chroot = chroot_lib.Chroot(
        path=path,
        out_path=out_path,
        cache_dir=cache_dir,
        chrome_root=chrome_root,
        env=env,
    )

    return chroot


def ParseSysroot(sysroot_message: sysroot_pb2.Sysroot) -> sysroot_lib.Sysroot:
    """Create a sysroot object from the sysroot message.

    Args:
        sysroot_message: The sysroot message.

    Returns:
        Sysroot: The parsed sysroot object.

    Raises:
        AssertionError: When the message is not a Sysroot message.
    """
    assert isinstance(sysroot_message, sysroot_pb2.Sysroot)

    return sysroot_lib.Sysroot(sysroot_message.path)


def ParseRemoteexecConfig(remoteexec_message: common_pb2.RemoteexecConfig):
    """Parse a remoteexec config message."""
    assert isinstance(remoteexec_message, common_pb2.RemoteexecConfig)

    if not (
        remoteexec_message.reclient_dir or remoteexec_message.reproxy_cfg_file
    ):
        return None

    return remoteexec_util.Remoteexec(
        remoteexec_message.reclient_dir, remoteexec_message.reproxy_cfg_file
    )


def ParseGomaConfig(goma_message, chroot_path, out_path):
    """Parse a goma config message."""
    assert isinstance(goma_message, common_pb2.GomaConfig)

    if not goma_message.goma_dir:
        return None

    # Parse the goma config.
    chromeos_goma_dir = goma_message.chromeos_goma_dir or None
    if goma_message.goma_approach == common_pb2.GomaConfig.RBE_STAGING:
        goma_approach = goma_lib.GomaApproach(
            "?staging", "staging-goma.chromium.org", True
        )
    elif goma_message.goma_approach == common_pb2.GomaConfig.RBE_PROD:
        goma_approach = goma_lib.GomaApproach(
            "?prod", "goma.chromium.org", True
        )
    else:
        goma_approach = goma_lib.GomaApproach(
            "?cros", "goma.chromium.org", True
        )

    # Note that we are not specifying the goma log_dir so that goma will create
    # and use a tmp dir for the logs.
    stats_filename = goma_message.stats_file or None
    counterz_filename = goma_message.counterz_file or None

    return goma_lib.Goma(
        goma_message.goma_dir,
        stage_name="BuildAPI",
        chromeos_goma_dir=chromeos_goma_dir,
        chroot_dir=chroot_path,
        out_dir=out_path,
        goma_approach=goma_approach,
        stats_filename=stats_filename,
        counterz_filename=counterz_filename,
    )


def ParseBuildTarget(
    build_target_message: common_pb2.BuildTarget,
    profile_message: Optional[sysroot_pb2.Profile] = None,
) -> build_target_lib.BuildTarget:
    """Create a BuildTarget object from a build_target message.

    Args:
        build_target_message: The BuildTarget message.
        profile_message: The profile message.

    Returns:
        BuildTarget: The parsed instance.

    Raises:
        AssertionError: When the field is not a BuildTarget message.
    """
    assert isinstance(build_target_message, common_pb2.BuildTarget)
    assert profile_message is None or isinstance(
        profile_message, sysroot_pb2.Profile
    )

    profile_name = profile_message.name if profile_message else None
    return build_target_lib.BuildTarget(
        build_target_message.name, profile=profile_name
    )


def ParseBuildTargets(repeated_build_target_field):
    """Create a BuildTarget for each entry in the repeated field.

    Args:
        repeated_build_target_field: The repeated BuildTarget field.

    Returns:
        list[BuildTarget]: The parsed BuildTargets.

    Raises:
        AssertionError: When the field contains non-BuildTarget messages.
    """
    return [ParseBuildTarget(target) for target in repeated_build_target_field]


def deserialize_profile(profile: common_pb2.Profile) -> sysroot_lib.Profile:
    """Deserialize a portage profile message to a Profile object."""
    return sysroot_lib.Profile(profile.name)


def deserialize_package_index_info(
    message: common_pb2.PackageIndexInfo,
) -> binpkg.PackageIndexInfo:
    """Deserialize a PackageIndexInfo message to an object."""
    return binpkg.PackageIndexInfo(
        snapshot_sha=message.snapshot_sha,
        snapshot_number=message.snapshot_number,
        build_target=ParseBuildTarget(message.build_target),
        profile=deserialize_profile(message.profile),
        location=message.location,
    )


def serialize_package_info(
    pkg_info: package_info.PackageInfo,
    pkg_info_msg: Union[common_pb2.PackageInfo, "portage_pb2.Portage.Package"],
):
    """Serialize a PackageInfo object to a PackageInfo proto."""
    if not isinstance(pkg_info, package_info.PackageInfo):
        # Allows us to swap everything to serialize_package_info, and search the
        # logs for usages that aren't passing though a PackageInfo yet.
        logging.warning(
            "serialize_package_info: Got a %s instead of a PackageInfo.",
            type(pkg_info),
        )
        pkg_info = package_info.parse(pkg_info)
    pkg_info_msg.package_name = pkg_info.package
    if pkg_info.category:
        pkg_info_msg.category = pkg_info.category
    if pkg_info.vr:
        pkg_info_msg.version = pkg_info.vr


def deserialize_package_info(pkg_info_msg):
    """Deserialize a PackageInfo message to a PackageInfo object."""
    return package_info.parse(PackageInfoToString(pkg_info_msg))


def retrieve_package_log_paths(
    packages: Iterable[package_info.PackageInfo],
    output_proto: Union[
        sysroot_pb2.InstallPackagesResponse,
        sysroot_pb2.InstallToolchainResponse,
        sdk_subtools_pb2.BuildSdkSubtoolsResponse,
        test_pb2.BuildTargetUnitTestResponse,
    ],
    target_sysroot: sysroot_lib.Sysroot,
) -> None:
    """Get the path to the log file for each package that failed to build.

    Args:
        packages: A list of packages which failed to build.
        output_proto: The Response message for a given API call. This response
            proto must contain a failed_package_data field.
        target_sysroot: The sysroot used by the build step.
    """
    for pkg_info in packages:
        # Grab the paths to the log files for each failed package from the
        # sysroot.
        # Logs currently exist within the sysroot in the form of:
        # /build/${BOARD}/tmp/portage/logs/$CATEGORY:$PF:$TIMESTAMP.log
        failed_pkg_data_msg = output_proto.failed_package_data.add()
        serialize_package_info(pkg_info, failed_pkg_data_msg.name)
        glob_path = os.path.join(
            target_sysroot.portage_logdir,
            f"{pkg_info.category}:{pkg_info.pvr}:*.log",
        )
        log_files = glob.glob(glob_path)
        log_files.sort(reverse=True)
        # Omit path if files don't exist for some reason.
        if not log_files:
            logging.warning(
                "Log file for %s was not found. Search path: %s",
                pkg_info.cpvr,
                glob_path,
            )
            continue
        failed_pkg_data_msg.log_path.path = log_files[0]
        failed_pkg_data_msg.log_path.location = common_pb2.Path.INSIDE


def PackageInfoToString(package_info_msg):
    """Combine the components into the full package string."""
    # TODO: Use the lib.parser.package_info.PackageInfo class instead.
    if not package_info_msg.package_name:
        raise ValueError("Invalid PackageInfo message.")

    c = ("%s/" % package_info_msg.category) if package_info_msg.category else ""
    p = package_info_msg.package_name
    v = ("-%s" % package_info_msg.version) if package_info_msg.version else ""
    return "%s%s%s" % (c, p, v)


def pb2_path_to_pathlib_path(
    pb2_path: "common_pb2.Path",
    chroot: Optional["common_pb2.Chroot"] = None,
) -> Path:
    """Convert an absolute pb2 path to a pathlib.Path outside the chroot.

    Args:
        pb2_path: An absolute path, which might be inside or outside chroot.
        chroot: The chroot that the path might be inside of.

    Returns:
        A Path pointing to the same location as pb2_path, originating
        outside the chroot.

    Raises:
        ValueError: If the given path is relative instead of absolute.
        ValueError: If the given path is inside the chroot, but a chroot is not
            provided.
    """
    if pb2_path.path[0] != "/":
        raise ValueError(f"Cannot convert relative path: {pb2_path.path}")
    if pb2_path.location is common_pb2.Path.Location.OUTSIDE:
        return Path(pb2_path.path)
    if chroot is None:
        raise ValueError("Cannot convert inside path without a chroot.")
    return Path(ParseChroot(chroot).full_path(pb2_path.path))
