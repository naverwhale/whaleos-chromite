# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Functionality for building the ChromiumOS SDK."""

import logging
from pathlib import Path
import re

from chromite.lib import chromeos_version
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils


def CleanupMakeConfBoardSetup(board_location: Path) -> None:
    """Cleanup etc/make.conf.board_setup to be usable in the SDK.

    Args:
        board_location: Directory that contains the built SDK
            (e.g. /something/chroot/build/amd64-host).
    """
    board_setup = board_location / "etc/make.conf.board_setup"
    lines = osutils.ReadFile(board_setup).splitlines()
    to_remove = re.compile(r"^(ROOT|PKG_CONFIG)=")
    lines = [x for x in lines if not to_remove.match(x)]
    data = "\n".join(lines) + "\n"
    if "/build/" in data:
        logging.error("%s content:\n%s", board_setup, data)
        raise ValueError("/build/ paths must be cleaned from make.conf")
    osutils.WriteFile(board_setup, data, sudo=True)


def CreateTarballForSdk(tarball_path: Path, board_location: Path) -> None:
    """Create a tarball from a previously built SDK (e.g. by BuildPrebuilts).

    The tree at board_location must already have been cleaned (see
    CleanupMakeConfBoardSetup).

    Args:
        tarball_path: The path at which to create the tarball.
        board_location: The directory that contains the SDK to package.
    """
    exclude_paths = constants.SDK_PACKAGE_EXCLUDED_PATHS
    extra_args = ["--anchored"]
    extra_args.extend("--exclude=./%s/*" % x for x in exclude_paths)
    # Options for maximum compression.
    extra_env = {"XZ_OPT": "-e9"}
    cros_build_lib.CreateTarball(
        tarball_path,
        board_location,
        sudo=True,
        extra_args=extra_args,
        extra_env=extra_env,
    )
    # Make the tarball readable by all users.
    osutils.Chmod(tarball_path, 0o644, sudo=True)


def write_os_release(
    output_path: Path,
    version_info: chromeos_version.VersionInfo,
    sdk_version: str,
) -> None:
    """Create an /etc/os-release file.

    Args:
        output_path: The location to write the file.
        version_info: A VersionInfo to populate fields using.
        sdk_version: The BUILD_ID.
    """
    entries = {
        "NAME": "CrOS SDK",
        "ID": "cros_sdk",
        "ID_LIKE": "gentoo",
        "VERSION_ID": version_info.VersionString(),
        "BUILD_ID": sdk_version,
    }
    if version_info.chrome_branch:
        entries["VERSION"] = version_info.chrome_branch

    lines = []
    for key, value in sorted(entries.items()):
        lines.append(f"{key}={cros_build_lib.ShellQuote(value)}\n")

    osutils.WriteFile(
        output_path, "".join(lines), encoding="utf-8", sudo=True, makedirs=True
    )


def BuildSdkTarball(sdk_path: Path, sdk_version: str) -> Path:
    """Package a previously built (e.g. by BuildPrebuilts) SDK into a tarball.

    Args:
        sdk_path: The path that contains the SDK to package.
        sdk_version: The version to be included as BUILD_ID in /etc/os-release.

    Returns:
        The path to the tarball that has been created.
    """
    tarball_path = constants.SOURCE_ROOT / constants.SDK_TARBALL_NAME
    write_os_release(
        output_path=sdk_path / "etc" / "os-release",
        version_info=chromeos_version.VersionInfo.from_repo(
            constants.SOURCE_ROOT
        ),
        sdk_version=sdk_version,
    )
    CleanupMakeConfBoardSetup(sdk_path)
    CreateTarballForSdk(tarball_path, sdk_path)
    return tarball_path
