# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Logic to handle chromeos-base/protofiles uprev."""

import base64
import enum
import glob
import logging
from pathlib import Path
import re
import shutil
from typing import Dict, List
import urllib.request

from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import uprev_lib
from chromite.lib.parser import package_info


_REMOTE_BRANCH_CROS_MAIN = "cros/main"


class ProtofilesLib:
    """Handles chromeos-base/protofiles uprevs."""

    _UPREV_PROJECTS_PATHS = [
        "components/policy",
        "third_party/private_membership",
        "third_party/shell-encryption",
    ]
    _VERSION_URL = (
        "https://chromium.googlesource.com/chromium/src.git"
        + "/+/refs/heads/main/chrome/VERSION?format=TEXT"
    )

    class _GitObjectType(enum.Enum):
        """Git object types."""

        COMMIT = 0
        TREE = 1

    def Uprev(self, cros_path: Path) -> None:
        """Uprevs chromeos-base/protofiles package.

        Uprevs protofiles package with ToT hashes of components/policy,
        third_party/private_membership, third_party/shell-encryption.

        Args:
            cros_path: absolute path to ChromeOS repo checkout
        """

        chromium_path = cros_path / "chromium/src"
        project_full_path_list = [
            chromium_path / project_path
            for project_path in self._UPREV_PROJECTS_PATHS
        ]

        logging.info(
            "Fetching latest commit hashes for %s.", self._UPREV_PROJECTS_PATHS
        )
        commit_hashes = self._FetchLatestCommitHashes(
            project_full_path_list, self._GitObjectType.COMMIT
        )
        tree_hashes = self._FetchLatestCommitHashes(
            project_full_path_list, self._GitObjectType.TREE
        )

        package_name = "protofiles"
        package_path = (
            cros_path
            / "third_party/chromiumos-overlay/chromeos-base"
            / package_name
        )

        logging.info("Updating ebuild file for %s.", package_path)
        self._UpdateEbuildFile(
            package_path, package_name, commit_hashes, tree_hashes
        )

        version_file_path = package_path / "files/VERSION"
        version_content = self._FetchChromeVersion()

        logging.info("Updating version file %s.", version_file_path)
        osutils.WriteFile(version_file_path, version_content, "wb")

    def _FetchLatestCommitHashes(
        self, project_full_path_list: List[Path], object_type: _GitObjectType
    ) -> Dict[Path, str]:
        """Fetches object hashes of the latest commits of passed projects.

        Args:
            project_full_path_list: list of absolute paths to projects
            object_type: _GitObjectType to fetch the hash of

        Returns:
            A dictionary that maps from |project_full_path| to an object hash
        """

        object_type_to_git_format = {
            self._GitObjectType.COMMIT: "%H",
            self._GitObjectType.TREE: "%T",
        }

        object_hashes: Dict[Path, str] = {}
        git_log_cmd = (
            f"git log -1 --format={object_type_to_git_format[object_type]} "
            + f"{_REMOTE_BRANCH_CROS_MAIN}"
        )
        for project_full_path in project_full_path_list:
            object_hash = cros_build_lib.run(
                git_log_cmd,
                capture_output=True,
                cwd=project_full_path,
                encoding="utf-8",
                shell=True,
            ).stdout.rstrip()
            object_hashes[project_full_path] = object_hash

        return object_hashes

    def _UpdateEbuildFile(
        self,
        package_path: Path,
        package_name: str,
        commit_hashes: Dict[Path, str],
        tree_hashes: Dict[Path, str],
    ) -> None:
        """Updates a stable ebuild file in the |package_path| with new hashes.

        Searches for the stable ebuild file with |package_name| prefix
        (not *-9999 ebuild) and updates it with the following steps:
            1. Rename the ebuild file with incremented index.
            2. Updates ebuild's hashes with new |commit_hashes|
            and |tree_hashes|.

        Args:
            package_path: path to the protofiles package
            package_name: name of the protofiles package
            commit_hashes: dictionary of projects mapped to latest commit hashes
            tree_hashes: dictionary of projects mapped to latest tree hashes

        Raises:
            NoEbuildsError: if there are no stable ebuild files found
            TooManyStableEbuildsError: if multiple stable ebuild files found
        """

        with osutils.ChdirContext(package_path):
            ebuild_pattern = f"{package_name}-0.0.*.ebuild"
            ebuild_files = glob.glob(ebuild_pattern)
            if len(ebuild_files) < 1:
                raise uprev_lib.NoEbuildsError(
                    f"Have not found a single ebuild file in {package_path}"
                )
            if len(ebuild_files) > 1:
                raise uprev_lib.TooManyStableEbuildsError(
                    f"Found too many ebuild files in {package_path}"
                )

            old_filename = Path(ebuild_files[0])
            old_package_info = package_info.parse(old_filename)
            old_last_version_component = int(
                old_package_info.version.split(".")[-1]
            )
            new_last_version_component = old_last_version_component + 1
            new_package_info = package_info.PackageInfo(
                old_package_info.category,
                old_package_info.package,
                f"0.0.{new_last_version_component}",
            )

            new_ebuild_path = package_path / new_package_info.ebuild
            old_ebuild_path = package_path / old_filename
            shutil.move(old_ebuild_path, new_ebuild_path)

            self._ReplaceHashes(new_ebuild_path, commit_hashes, tree_hashes)

    def _ReplaceHashes(
        self,
        ebuild_path: Path,
        commit_hashes: Dict[Path, str],
        tree_hashes: Dict[Path, str],
    ) -> None:
        """Replaces CROS_WORKON_[COMMIT|TREE] hashes in the ebuild file.

        Replaces hashes in the file in |ebuild_path| for entries with
        the following format:

        CROS_WORKON_[COMMIT|TREE] = (
            <hash> # <project_name>
            <other_hash> # <other_project_name>
        )

        Args:
            ebuild_path: path to ebuild file.
            commit_hashes: dictionary of projects with latest commit hashes
            tree_hashes: dictionary of projects with latest tree hashes
        """

        ebuild_content = osutils.ReadFile(ebuild_path)
        assert commit_hashes.keys() == tree_hashes.keys()

        for project_full_path in commit_hashes.keys():
            project_name = project_full_path.name

            commit_hash = commit_hashes[project_full_path]
            commit_replacement = rf"\g<1>{commit_hash}\2"
            commit_pattern = (
                rf"(CROS_WORKON_COMMIT=\([^)]*\")[a-z0-9]*(\" # {project_name})"
            )
            ebuild_content = re.sub(
                commit_pattern, commit_replacement, ebuild_content
            )
            assert commit_hash in ebuild_content, (
                f"commit hash {commit_hash} for {project_name} "
                + "not found in output"
            )

            tree_hash = tree_hashes[project_full_path]
            tree_replacement = rf"\g<1>{tree_hash}\2"
            tree_pattern = (
                rf"(CROS_WORKON_TREE=\([^)]*\")[a-z0-9]*(\" # {project_name})"
            )
            ebuild_content = re.sub(
                tree_pattern, tree_replacement, ebuild_content
            )
            assert (
                tree_hash in ebuild_content
            ), f"tree hash {tree_hash} for {project_name} not found in output"

        osutils.WriteFile(ebuild_path, ebuild_content, "w")

    def _FetchChromeVersion(self) -> bytes:
        """Fetches the current Chrome version.

        Fetches the current Chrome version via an HTTPS request from
        the chromium repo.
        Currently, the only way to get the contents of the version file
        from the repo is to download the base64 encoded contents.
        See https://github.com/google/gitiles/issues/7.

        Returns:
            base64 decoded bytes with the contents of the Chrome version file.
        """

        request = urllib.request.Request(self._VERSION_URL)
        with urllib.request.urlopen(request) as response:
            data = response.read()
            version = base64.b64decode(data)

        return version
