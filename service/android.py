# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides utility for performing Android uprev."""

import itertools
import json
import logging
import os
import re
import time
from typing import Dict, Iterable, Optional, Tuple, Union

from chromite.lib import constants
from chromite.lib import gs


# List of Android Portage packages. When adding/removing packages make sure the
# ANDROID_PACKAGE_TO_BUILD_TARGETS / ARTIFACTS_TO_COPY maps are also updated.
ANDROID_PI_PACKAGE = "android-container-pi"
ANDROID_RVC_PACKAGE = "android-container-rvc"
ANDROID_VMRVC_PACKAGE = "android-vm-rvc"
ANDROID_VMSC_PACKAGE = "android-vm-sc"
ANDROID_VMTM_PACKAGE = "android-vm-tm"
# V uses master until the V branch is cut.
ANDROID_VMVIC_PACKAGE = "android-vm-master"


# Supported Android build targets for each package. Maps from *_TARGET variables
# in Android ebuilds to Android build targets. Used during Android uprev to fill
# in corresponding variables.
ANDROID_PACKAGE_TO_BUILD_TARGETS = {
    ANDROID_PI_PACKAGE: {
        "APPS_TARGET": "apps",
        "ARM_TARGET": "cheets_arm-user",
        "ARM64_TARGET": "cheets_arm64-user",
        "X86_TARGET": "cheets_x86-user",
        "X86_64_TARGET": "cheets_x86_64-user",
        "ARM_USERDEBUG_TARGET": "cheets_arm-userdebug",
        "ARM64_USERDEBUG_TARGET": "cheets_arm64-userdebug",
        "X86_USERDEBUG_TARGET": "cheets_x86-userdebug",
        "X86_64_USERDEBUG_TARGET": "cheets_x86_64-userdebug",
        "SDK_GOOGLE_X86_USERDEBUG_TARGET": "sdk_cheets_x86-userdebug",
        "SDK_GOOGLE_X86_64_USERDEBUG_TARGET": "sdk_cheets_x86_64-userdebug",
    },
    ANDROID_RVC_PACKAGE: {
        "APPS_TARGET": "apps",
        "ARM64_TARGET": "cheets_arm64-user",
        "X86_64_TARGET": "cheets_x86_64-user",
        "ARM64_USERDEBUG_TARGET": "cheets_arm64-userdebug",
        "X86_64_USERDEBUG_TARGET": "cheets_x86_64-userdebug",
    },
    ANDROID_VMRVC_PACKAGE: {
        "APPS_TARGET": "apps",
        "ARM64_TARGET": "bertha_arm64-user",
        "X86_64_TARGET": "bertha_x86_64-user",
        "ARM64_USERDEBUG_TARGET": "bertha_arm64-userdebug",
        "X86_64_USERDEBUG_TARGET": "bertha_x86_64-userdebug",
    },
    ANDROID_VMSC_PACKAGE: {
        "ARM64_USERDEBUG_TARGET": "bertha_arm64-userdebug",
        "X86_64_USERDEBUG_TARGET": "bertha_x86_64-userdebug",
    },
    ANDROID_VMTM_PACKAGE: {
        "APPS_TARGET": "apps",
        "ARM64_TARGET": "bertha_arm64-user",
        "X86_64_TARGET": "bertha_x86_64-user",
        "ARM64_USERDEBUG_TARGET": "bertha_arm64-userdebug",
        "X86_64_USERDEBUG_TARGET": "bertha_x86_64-userdebug",
    },
    ANDROID_VMVIC_PACKAGE: {
        "ARM64_USERDEBUG_TARGET": "bertha_arm64-trunk_staging-userdebug",
        "X86_64_USERDEBUG_TARGET": "bertha_x86_64-trunk_staging-userdebug",
    },
}


# Regex patterns of artifacts to copy for each branch and build target.
ARTIFACTS_TO_COPY = {
    ANDROID_PI_PACKAGE: {
        "apps": "org.chromium.arc.cachebuilder.jar",
        "cheets_arm-user": r"\.zip$",
        "cheets_arm64-user": r"\.zip$",
        "cheets_x86-user": r"\.zip$",
        "cheets_x86_64-user": r"\.zip$",
        "cheets_arm-userdebug": r"\.zip$",
        "cheets_arm64-userdebug": r"\.zip$",
        "cheets_x86-userdebug": r"\.zip$",
        "cheets_x86_64-userdebug": r"\.zip$",
        "sdk_cheets_x86-userdebug": r"\.zip$",
        "sdk_cheets_x86_64-userdebug": r"\.zip$",
    },
    ANDROID_RVC_PACKAGE: {
        # org.chromium.cts.helpers.apk contains helpers needed for CTS.  It is
        # installed on the board, but not into the VM.
        "apps": "org.chromium.arc.cachebuilder.jar",
        "cheets_arm64-user": (r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"),
        "cheets_x86_64-user": (r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"),
        "cheets_arm64-userdebug": (
            r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"
        ),
        "cheets_x86_64-userdebug": (
            r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"
        ),
    },
    ANDROID_VMRVC_PACKAGE: {
        # org.chromium.cts.helpers.apk contains helpers needed for CTS.  It is
        # installed on the board, but not into the VM.
        "apps": "org.chromium.arc.cachebuilder.jar",
        "bertha_arm64-user": (r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"),
        "bertha_x86_64-user": (r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"),
        "bertha_arm64-userdebug": (
            r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"
        ),
        "bertha_x86_64-userdebug": (
            r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"
        ),
    },
    ANDROID_VMSC_PACKAGE: {
        # org.chromium.cts.helpers.apk contains helpers needed for CTS.  It is
        # installed on the board, but not into the VM.
        "bertha_arm64-userdebug": (
            r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"
        ),
        "bertha_x86_64-userdebug": (
            r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"
        ),
    },
    ANDROID_VMTM_PACKAGE: {
        # org.chromium.cts.helpers.apk contains helpers needed for CTS.  It is
        # installed on the board, but not into the VM.
        "apps": "org.chromium.arc.cachebuilder.jar",
        "bertha_arm64-user": (r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"),
        "bertha_x86_64-user": (r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"),
        "bertha_arm64-userdebug": (
            r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"
        ),
        "bertha_x86_64-userdebug": (
            r"(\.zip"
            r"|/org.chromium.arc.cts.helpers.apk"
            r"|/kernel|/ramdisk.img)$"
        ),
    },
    ANDROID_VMVIC_PACKAGE: {
        # org.chromium.cts.helpers.apk contains helpers needed for CTS.  It is
        # installed on the board, but not into the VM.
        "bertha_arm64-trunk_staging-userdebug": (
            r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"
        ),
        "bertha_x86_64-trunk_staging-userdebug": (
            r"(\.zip|/org.chromium.arc.cts.helpers.apk)$"
        ),
    },
}

# The bucket where Android infra publishes build artifacts. Files are only kept
# for 90 days.
ANDROID_BUCKET_URL = "gs://android-build-chromeos/builds"

# ACL definition files that live under the Portage package directory.
# We set ACLs when copying Android artifacts to the ARC bucket, using
# definitions for corresponding architecture (and public for the `apps` target).
ARC_BUCKET_ACL_ARM = "googlestorage_acl_arm.txt"
ARC_BUCKET_ACL_X86 = "googlestorage_acl_x86.txt"
ARC_BUCKET_ACL_PUBLIC = "googlestorage_acl_public.txt"


# The overlay that hosts Android packages.
OVERLAY_DIR = os.path.join(
    constants.SOURCE_ROOT, "src", "private-overlays", "project-cheets-private"
)


def GetAllAndroidPackages() -> Iterable[str]:
    """Returns a list of all supported Android packages."""
    return list(ANDROID_PACKAGE_TO_BUILD_TARGETS)


def GetAndroidPackageDir(
    android_package: str, overlay_dir: str = OVERLAY_DIR
) -> str:
    """Returns the Portage package directory of the given Android package.

    Args:
        android_package: the Android package name e.g. 'android-vm-rvc'
        overlay_dir: specify to override the default overlay.

    Returns:
        The Portage package directory
    """
    return os.path.join(overlay_dir, "chromeos-base", android_package)


def GetAndroidBranchForPackage(android_package: str) -> str:
    """Returns the default Android branch of given Android package.

    Args:
        android_package: the Android package name e.g. 'android-vm-rvc'

    Returns:
        The corresponding Android branch e.g. 'git_rvc-arc'
    """
    mapping = {
        ANDROID_PI_PACKAGE: "git_pi-arc",
        ANDROID_RVC_PACKAGE: "git_rvc-arc",
        ANDROID_VMRVC_PACKAGE: "git_rvc-arc",
        ANDROID_VMSC_PACKAGE: "git_sc-arc-dev",
        ANDROID_VMTM_PACKAGE: "git_tm-arc",
        ANDROID_VMVIC_PACKAGE: "git_main-arc-dev",
    }
    try:
        return mapping[android_package]
    except KeyError:
        raise ValueError(f'Unknown Android package "{android_package}"')


def GetAndroidEbuildTargetsForPackage(android_package: str) -> Dict[str, str]:
    """Returns the ebuild targets map for given Android package.

    This is the mapping between Android ebuild variables and Android build
    targets. Required when generating new stable ebuilds.
    """
    try:
        return ANDROID_PACKAGE_TO_BUILD_TARGETS[android_package]
    except KeyError:
        raise ValueError(f'Unknown Android package "{android_package}"')


def GetAllAndroidEbuildTargets() -> Iterable[str]:
    """Returns all possible Android ebuild target variables.

    This is required by packages.determine_android_branch() to parse Android
    branch info from stable ebuilds.
    """
    return frozenset(
        itertools.chain.from_iterable(ANDROID_PACKAGE_TO_BUILD_TARGETS.values())
    )


def IsBuildIdValid(
    android_package: str,
    build_branch: str,
    build_id: str,
    bucket_url: str = ANDROID_BUCKET_URL,
) -> Optional[dict]:
    """Checks that a specific build_id is valid.

    Looks for that build_id for all builds. Confirms that the subpath can
    be found and that the zip file is present in that subdirectory.

    Args:
        android_package: The Android package to check for.
        build_branch: The Android build branch.
        build_id: A string. The Android build id number to check.
        bucket_url: URL of Android build gs bucket

    Returns:
        Returns subpaths dictionary if build_id is valid.
        None if the build_id is not valid.
    """
    targets = ARTIFACTS_TO_COPY[android_package]
    gs_context = gs.GSContext()
    subpaths_dict = {}
    for target in targets:
        build_dir = f"{build_branch}-linux-{target}"
        build_id_path = os.path.join(bucket_url, build_dir, build_id)

        # Find name of subpath.
        try:
            subpaths = gs_context.List(build_id_path)
        except gs.GSNoSuchKey:
            logging.warning(
                "Directory [%s] does not contain any subpath, ignoring it.",
                build_id_path,
            )
            return None
        # b/215041592: Sometimes there can be multiple subpaths which presumably
        # contain the exact same artifacts.
        if len(subpaths) > 1:
            logging.warning(
                "Directory [%s] contains more than one subpath, using the "
                "first one.",
                build_id_path,
            )

        subpath_dir = subpaths[0].url.rstrip("/")
        subpath_name = os.path.basename(subpath_dir)

        # Look for a zipfile ending in the build_id number.
        try:
            gs_context.List(subpath_dir)
        except gs.GSNoSuchKey:
            logging.warning(
                "Did not find a file for build id [%s] in directory [%s].",
                build_id,
                subpath_dir,
            )
            return None

        # Record subpath for the target.
        subpaths_dict[target] = subpath_name

    # If we got here, it means we found an appropriate build for all platforms.
    return subpaths_dict


def GetLatestBuild(
    android_package: str,
    build_branch: Optional[str] = None,
    bucket_url: str = ANDROID_BUCKET_URL,
) -> Union[Tuple[None, None], Tuple[str, dict]]:
    """Searches the gs bucket for the latest green build.

    Args:
        android_package: The Android package to find latest build for.
        build_branch: The Android build branch.
        bucket_url: URL of Android build gs bucket

    Returns:
        Tuple of (latest version string, subpaths dictionary)
        If no latest build can be found, returns None, None
    """
    build_branch = build_branch or GetAndroidBranchForPackage(android_package)
    targets = ARTIFACTS_TO_COPY[android_package]
    gs_context = gs.GSContext()
    common_build_ids = None
    # Find builds for each target.
    for target in targets:
        build_dir = f"{build_branch}-linux-{target}"
        base_path = os.path.join(bucket_url, build_dir)
        build_ids = []
        for gs_result in gs_context.List(base_path):
            # Remove trailing slashes and get the base name, which is the
            # build_id.
            build_id = os.path.basename(gs_result.url.rstrip("/"))
            if not build_id.isdigit():
                logging.warning(
                    "Directory [%s] does not look like a valid build_id.",
                    gs_result.url,
                )
                continue
            build_ids.append(build_id)

        # Update current list of builds.
        if common_build_ids is None:
            # First run, populate it with the first platform.
            common_build_ids = set(build_ids)
        else:
            # Already populated, find the ones that are common.
            common_build_ids.intersection_update(build_ids)

    if common_build_ids is None:
        logging.warning("Did not find a build_id common to all platforms.")
        return None, None

    # Otherwise, find the most recent one that is valid.
    for build_id in sorted(common_build_ids, key=int, reverse=True):
        subpaths = IsBuildIdValid(
            android_package, build_branch, build_id, bucket_url
        )
        if subpaths:
            return build_id, subpaths

    # If not found, no build_id is valid.
    logging.warning("Did not find a build_id valid on all platforms.")
    return None, None


def _GetAcl(target: str, package_dir: str) -> str:
    """Returns the path to ACL file corresponding to target.

    Args:
        target: Android build target.
        package_dir: Path to the Android portage package.

    Returns:
        Path to the ACL definition file.
    """
    if "arm" in target:
        return os.path.join(package_dir, ARC_BUCKET_ACL_ARM)
    if "x86" in target:
        return os.path.join(package_dir, ARC_BUCKET_ACL_X86)
    if target == "apps":
        return os.path.join(package_dir, ARC_BUCKET_ACL_PUBLIC)
    raise ValueError(f"Unknown target {target}")


def CopyToArcBucket(
    android_bucket_url: str,
    android_package: str,
    build_branch: str,
    build_id: str,
    subpaths: Dict[str, str],
    arc_bucket_url: str,
    package_dir: str,
) -> None:
    """Copies from source Android bucket to ARC++ specific bucket.

    Copies each build to the ARC bucket eliminating the subpath.
    Applies build specific ACLs for each file.

    Args:
        android_bucket_url: URL of Android build gs bucket
        android_package: The Android package to copy artifacts for.
        build_branch: The Android build branch.
        build_id: A string. The Android build id number to check.
        subpaths: Subpath dictionary for each build to copy.
        arc_bucket_url: URL of the target ARC build gs bucket
        package_dir: Path to the Android portage package.
    """
    targets = ARTIFACTS_TO_COPY[android_package]
    gs_context = gs.GSContext()
    for target, pattern in targets.items():
        subpath = subpaths[target]
        build_dir = f"{build_branch}-linux-{target}"
        android_dir = os.path.join(
            android_bucket_url, build_dir, build_id, subpath
        )
        arc_dir = os.path.join(arc_bucket_url, build_dir, build_id)
        acl = _GetAcl(target, package_dir)

        # Copy all target files from android_dir to arc_dir, setting ACLs.
        for targetfile in gs_context.List(android_dir):
            if re.search(pattern, targetfile.url):
                arc_path = os.path.join(
                    arc_dir, os.path.basename(targetfile.url)
                )
                needs_copy = True
                retry_count = 2

                # Retry in case race condition when several boards trying to
                # copy the same resource
                while True:
                    # Check a pre-existing file with the original source.
                    if gs_context.Exists(arc_path):
                        if (
                            gs_context.Stat(targetfile.url).hash_crc32c
                            != gs_context.Stat(arc_path).hash_crc32c
                        ):
                            logging.warning(
                                "Removing incorrect file %s", arc_path
                            )
                            gs_context.Remove(arc_path)
                        else:
                            logging.info(
                                "Skipping already copied file %s", arc_path
                            )
                            needs_copy = False

                    # Copy if necessary, and set the ACL unconditionally. The
                    # Stat() call above doesn't verify the ACL is correct and
                    # the ChangeACL should be relatively cheap compared to the
                    # copy.
                    # This covers the following case:
                    # - handling an interrupted copy from a previous run.
                    # - rerunning the copy in case one of the
                    #       googlestorage_acl_X.txt
                    #   files changes (e.g. we add a new variant which reuses a
                    #       build).
                    if needs_copy:
                        logging.info(
                            "Copying %s -> %s (acl %s)",
                            targetfile.url,
                            arc_path,
                            acl,
                        )
                        try:
                            gs_context.Copy(targetfile.url, arc_path, version=0)
                        except gs.GSContextPreconditionFailed as error:
                            if not retry_count:
                                raise error
                            # Retry one more time after a short delay
                            logging.warning(
                                "Will retry copying %s -> %s",
                                targetfile.url,
                                arc_path,
                            )
                            time.sleep(5)
                            retry_count = retry_count - 1
                            continue
                    gs_context.ChangeACL(arc_path, acl_args_file=acl)
                    break


def MirrorArtifacts(
    android_package: str,
    android_bucket_url: str,
    android_build_branch: str,
    arc_bucket_url: str,
    package_dir: str,
    version: Optional[str] = None,
) -> Optional[str]:
    """Mirrors artifacts from Android bucket to ARC bucket.

    First, this function identifies which build version should be copied,
    if not given. Please see GetLatestBuild() and IsBuildIdValid() for details.

    On build version identified, then copies target artifacts to the ARC bucket,
    with setting ACLs.

    Args:
        android_package: The Android package to mirror artifacts for.
        android_bucket_url: URL of Android build gs bucket
        android_build_branch: The Android build branch.
        arc_bucket_url: URL of the target ARC build gs bucket
        package_dir: Path to the Android portage package.
        version: A string. The Android build id number to check. If not passed,
            detect latest good build version.

    Returns:
        Mirrored version.
    """
    if version:
        subpaths = IsBuildIdValid(
            android_package, android_build_branch, version, android_bucket_url
        )
        if not subpaths:
            logging.error("Requested build %s is not valid", version)
    else:
        version, subpaths = GetLatestBuild(
            android_package, android_build_branch, android_bucket_url
        )

    CopyToArcBucket(
        android_bucket_url,
        android_package,
        android_build_branch,
        version,
        subpaths,
        arc_bucket_url,
        package_dir,
    )

    return version


_LKGB_JSON = "LKGB.json"


class MissingLKGBError(Exception):
    """LKGB file for the given Android package is missing."""


class InvalidLKGBError(Exception):
    """LKGB file for the given Android package contains invalid content."""


def LKGB(
    build_id: str,
    branch: Optional[str] = None,
    runtime_artifacts_pin: Optional[str] = None,
    **kwargs,
) -> dict:
    """Constructs an "LKGB object".

    The LKGB object is basically a dict with additional handling for optional
    keys to make sure two LKGB objects are comparable, and to discard unwanted
    fields from the JSON file (absorbed by **kwargs).

    Args:
        build_id: The last known good Android build ID.
        branch: The Android branch associated with build_id.
        runtime_artifacts_pin: The runtime artifacts pin, if present.

    Returns:
        The constructed LKGB object.
    """
    del kwargs  # Delete unused var to make pylint happy.

    lkgb = dict(build_id=build_id)
    if branch:
        lkgb["branch"] = branch
    if runtime_artifacts_pin is not None:
        lkgb["runtime_artifacts_pin"] = runtime_artifacts_pin
    return lkgb


def WriteLKGB(android_package_dir: str, lkgb: dict) -> str:
    """Writes the LKGB file under the given Android package directory.

    Args:
        android_package_dir: The Android package directory.
        lkgb: The LKGB object; see LKGB().

    Returns:
        Path to the updated file.
    """
    path = os.path.join(android_package_dir, _LKGB_JSON)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(lkgb, f, indent=2, sort_keys=True)
        f.write("\n")
    return path


def ReadLKGB(android_package_dir: str) -> dict:
    """Reads the LKGB file under the given Android package directory.

    See LKGB() for possible fields in the dict; if additional fields are found
    in the LKGB file, they are silently discarded without triggering an error.

    Args:
        android_package_dir: The Android package directory.

    Returns:
        An LKGB object from the file; see LKGB().

    Raises:
        MissingLKGBError: If the LKGB file is not found under
            |android_package_dir|.
        InvalidLKGBError: If the LKGB file contains invalid content.
    """
    path = os.path.join(android_package_dir, _LKGB_JSON)
    if not os.path.exists(path):
        raise MissingLKGBError(path)

    try:
        with open(path, "r", encoding="utf-8") as f:
            lkgb = json.load(f)
    except json.JSONDecodeError as e:
        raise InvalidLKGBError("Error decoding LKGB file as JSON: " + str(e))

    if "build_id" not in lkgb:
        raise InvalidLKGBError("Field build_id not found in LKGB file")
    return LKGB(**lkgb)


_RUNTIME_ARTIFACTS_BUCKET_URL = "gs://chromeos-arc-images/runtime_artifacts"


def FindDataCollectorArtifacts(
    android_package: str,
    android_version: str,
    version_reference: str,
    runtime_artifacts_bucket_url: Optional[str] = _RUNTIME_ARTIFACTS_BUCKET_URL,
) -> dict:
    r"""Finds and includes into variables artifacts from arc.DataCollector.

    This is used from UpdateDataCollectorArtifacts in order to check the
    particular version.

    Args:
        android_package: android package name. Used as folder to locate the
            cache.
        android_version: The \d+ build id of Android.
        version_reference: which version to use as a reference. Could be '${PV}'
            in case version of data collector artifacts matches the Android
            version or direct version in case of override.
        runtime_artifacts_bucket_url: root of runtime artifacts

    Returns:
        dictionary with filled ebuild variables. This dictionary is empty in
        case no artifacts are found.
    """
    gs_context = gs.GSContext()
    variables = {}

    _BUCKETS = (
        "packages_reference",
        "gms_core_cache",
        "tts_cache",
        "dex_opt_cache",
    )
    _ARCHES = ("arm", "arm64", "arm64only", "x86", "x86_64", "x64only")
    _BUILD_TYPES = ("user", "userdebug")

    for bucket in _BUCKETS:
        for arch in _ARCHES:
            for build_type in _BUILD_TYPES:
                root_path = (
                    f"{runtime_artifacts_bucket_url}/{android_package}/"
                    f"{bucket}_{arch}_{build_type}"
                )
                if gs_context.Exists(f"{root_path}_{android_version}.tar"):
                    variables[
                        (f"{arch}_{build_type}_{bucket}").upper()
                    ] = f"{root_path}_{version_reference}.tar"

    _UREADAHEAD_BUCKET = "ureadahead_pack_host"
    _BINARY_TRANSLATION_TYPES = ("houdini", "ndk", "native")
    # Special format for _UREADAHEAD_BUCKET.
    for arch in _ARCHES:
        for build_type in _BUILD_TYPES:
            for binary_translation_type in _BINARY_TRANSLATION_TYPES:
                if ("x86" in arch and binary_translation_type == "native") or (
                    "arm" in arch and binary_translation_type != "native"
                ):
                    # Ignore invalid format combinations.
                    continue

                root_path = (
                    f"{runtime_artifacts_bucket_url}/{android_package}/"
                    f"{_UREADAHEAD_BUCKET}_{arch}_{binary_translation_type}_"
                    f"{build_type}"
                )
                if gs_context.Exists(f"{root_path}_{android_version}.tar"):
                    variables[
                        (
                            f"{arch}_{binary_translation_type}_{build_type}_"
                            f"{_UREADAHEAD_BUCKET}"
                        ).upper()
                    ] = f"{root_path}_{version_reference}.tar"

    return variables


def FindRuntimeArtifactsPin(
    android_package: str,
    milestone: str,
    runtime_artifacts_bucket_url: Optional[str] = _RUNTIME_ARTIFACTS_BUCKET_URL,
) -> Optional[str]:
    """Finds the runtime artifacts pin for given package/milestone, if present.

    Args:
        android_package: The Android package.
        milestone: The ChromeOS milestone (can be found using
            chromite.service.packages.determine_milestone_version)
        runtime_artifacts_bucket_url: URL of the runtime artifacts bucket.

    Returns:
        The pinned version, or None if not present.
    """
    gs_context = gs.GSContext()
    pin_path = (
        f"{runtime_artifacts_bucket_url}/{android_package}/"
        f"M{milestone}_pin_version"
    )
    if not gs_context.Exists(pin_path):
        return None

    return gs_context.Cat(pin_path, encoding="utf-8").rstrip()
