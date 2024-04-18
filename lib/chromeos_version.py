# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for reading and manipulating chromeos_version.sh script."""

from datetime import datetime
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Optional, Union

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import git


_PUSH_BRANCH = "temp_auto_checkin_branch"


class VersionUpdateException(Exception):
    """Exception gets thrown for failing to update the version file"""


class VersionInfo:
    """Class to encapsulate the Chrome OS version info scheme.

    You can instantiate this class in three ways.
    1) using a version file, specifically chromeos_version.sh,
        which contains the version information.
    2) passing in a string with the 3 version components.
    3) using a source repo and calling from_repo().
    """

    # Pattern for matching build name format.  Includes chrome branch hack.
    VER_PATTERN = r"(\d+).(\d+).(\d+)(?:-R(\d+))*"
    KEY_VALUE_PATTERN = r"%s=(\d+)\s*$"
    VALID_INCR_TYPES = ("chrome_branch", "build", "branch", "patch")
    DATE_TIME_FORMAT = "%Y_%m_%d_%H%M%S"

    def __init__(
        self,
        version_string: Optional[str] = None,
        chrome_branch: Optional[str] = None,
        incr_type: str = "build",
        version_file: Optional[Union[str, os.PathLike]] = None,
    ):
        """Initialize.

        Args:
            version_string: Optional 3 component version string to parse.
                Contains:
                    build_number: release build number.
                    branch_build_number: current build number on a branch.
                    patch_number: patch number.
            chrome_branch: If version_string specified, specify chrome_branch
                i.e. 13.
            incr_type: How we should increment this version -
                chrome_branch|build|branch|patch
            version_file: version file location.
        """
        if version_file:
            if isinstance(version_file, str):
                version_file = Path(version_file)
            self.version_file = version_file
            logging.debug("Using VERSION _FILE = %s", version_file)
            self._LoadFromFile()
        else:
            match = re.search(self.VER_PATTERN, version_string)
            self.build_number = match.group(1)
            self.branch_build_number = match.group(2)
            self.patch_number = match.group(3)
            self.patch_number_with_date_time = self.patch_number
            self.chrome_branch = chrome_branch
            self.version_file = None

        self.incr_type = incr_type

    @classmethod
    def from_repo(cls, source_repo: Union[str, os.PathLike], **kwargs):
        kwargs["version_file"] = Path(source_repo) / constants.VERSION_FILE
        return cls(**kwargs)

    def _GetDateTime(self):
        return datetime.now().strftime(self.DATE_TIME_FORMAT)

    def _LoadFromFile(self):
        """Read the version file and set the version components"""
        with open(self.version_file, "r", encoding="utf-8") as version_fh:
            for line in version_fh:
                if not line.strip():
                    continue

                match = self.FindValue("CHROME_BRANCH", line)
                if match:
                    self.chrome_branch = match
                    logging.debug(
                        "Set the Chrome branch number to:%s", self.chrome_branch
                    )
                    continue

                match = self.FindValue("CHROMEOS_BUILD", line)
                if match:
                    self.build_number = match
                    logging.debug(
                        "Set the build version to:%s", self.build_number
                    )
                    continue

                match = self.FindValue("CHROMEOS_BRANCH", line)
                if match:
                    self.branch_build_number = match
                    logging.debug(
                        "Set the branch version to:%s", self.branch_build_number
                    )
                    continue

                match = self.FindValue("CHROMEOS_PATCH", line)
                if match:
                    self.patch_number = match
                    self.patch_number_with_date_time = self.patch_number
                    # For developer builds, append a date and time string.
                    if os.environ.get("CHROMEOS_OFFICIAL") != "1":
                        self.patch_number_with_date_time += (
                            f"-d{self._GetDateTime()}"
                        )
                    logging.debug(
                        "Set the patch version to:%s", self.patch_number
                    )
                    logging.debug(
                        "Set the patch version with date to:%s",
                        self.patch_number_with_date_time,
                    )
                    continue

        logging.debug(self.VersionString())

    def _PushGitChanges(
        self,
        git_repo: Union[str, os.PathLike],
        message: str,
        dry_run: bool = False,
        push_to: Optional[git.RemoteRef] = None,
    ) -> None:
        """Push the final commit into the git repo.

        Args:
            git_repo: Path to the git repository.
            message: Commit message.
            dry_run: If true, don't actually push changes to the server.
            push_to: The remote branch to push the changes to. Defaults to the
                tracking branch of the current branch.
        """
        if push_to is None:
            push_to = git.GetTrackingBranch(
                git_repo, for_checkout=False, for_push=True
            )

        git.RunGit(git_repo, ["add", "-A"])

        # It's possible that while we are running on dry_run, someone has
        # already committed our change.
        try:
            git.RunGit(git_repo, ["commit", "-m", message])
        except cros_build_lib.RunCommandError:
            if dry_run:
                return
            raise

        logging.info(
            "Pushing to branch (%s) with message: %s %s.",
            push_to,
            message,
            " (dryrun)" if dry_run else "",
        )
        git.GitPush(git_repo, _PUSH_BRANCH, push_to, skip=dry_run)

    def FindValue(self, key, line):
        """Given the key find the value from the line, if it finds key = value

        Args:
            key: key to look for
            line: string to search

        Returns:
            None: on a non match
            value: for a matching key
        """
        match = re.search(self.KEY_VALUE_PATTERN % (key,), line)
        return match.group(1) if match else None

    def IncrementVersion(self):
        """Updates the version file by incrementing the patch component."""
        if not self.incr_type or self.incr_type not in self.VALID_INCR_TYPES:
            raise VersionUpdateException(
                "Need to specify the part of the version to" " increment"
            )

        if self.incr_type == "chrome_branch":
            self.chrome_branch = str(int(self.chrome_branch) + 1)

        # Increment build_number for 'chrome_branch' incr_type to avoid
        # crbug.com/213075.
        if self.incr_type in ("build", "chrome_branch"):
            self.build_number = str(int(self.build_number) + 1)
            self.branch_build_number = "0"
            self.patch_number = "0"
        elif self.incr_type == "branch" and self.patch_number == "0":
            self.branch_build_number = str(int(self.branch_build_number) + 1)
        else:
            self.patch_number = str(int(self.patch_number) + 1)

        return self.VersionString()

    def UpdateVersionFile(self, message, dry_run, push_to=None):
        """Update the version file with our current version.

        Args:
            message: Commit message.
            dry_run: Git dryrun.
            push_to: A git.RemoteRef object.
        """

        if not self.version_file:
            raise VersionUpdateException(
                "Cannot call UpdateVersionFile without "
                "an associated version_file"
            )

        components = (
            ("CHROMEOS_BUILD", self.build_number),
            ("CHROMEOS_BRANCH", self.branch_build_number),
            ("CHROMEOS_PATCH", self.patch_number),
            ("CHROME_BRANCH", self.chrome_branch),
        )

        with tempfile.NamedTemporaryFile(prefix="mvp", mode="w") as temp_fh:
            with open(
                self.version_file, "r", encoding="utf-8"
            ) as source_version_fh:
                for line in source_version_fh:
                    for key, value in components:
                        line = re.sub(
                            self.KEY_VALUE_PATTERN % (key,),
                            "%s=%s\n" % (key, value),
                            line,
                        )
                    temp_fh.write(line)

            temp_fh.flush()

            repo_dir = self.version_file.parent

            logging.info("Updating version file to: %s", self.VersionString())
            try:
                git.CreateBranch(repo_dir, _PUSH_BRANCH)
                shutil.copyfile(temp_fh.name, self.version_file)
                self._PushGitChanges(repo_dir, message, dry_run, push_to)
            finally:
                # Update to the remote version that contains our changes. This
                # is needed to ensure that we don't build a release using a
                # local commit.
                git.CleanAndCheckoutUpstream(repo_dir)

    def VersionString(self):
        """returns the version string"""
        return (
            f"{self.build_number}.{self.branch_build_number}."
            f"{self.patch_number}"
        )

    def VersionStringWithDateTime(self):
        """returns the version string with date and time."""
        return (
            f"{self.build_number}.{self.branch_build_number}."
            f"{self.patch_number_with_date_time}"
        )

    def VersionComponents(self):
        """Return an array of ints of the version fields for comparing."""
        return [
            int(x)
            for x in [
                self.build_number,
                self.branch_build_number,
                self.patch_number,
            ]
        ]

    @classmethod
    def VersionCompare(cls, version_string):
        """Useful method to return a comparable version of a LKGM string."""
        return cls(version_string).VersionComponents()

    def __lt__(self, other):
        return self.VersionComponents() < other.VersionComponents()

    def __le__(self, other):
        return self.VersionComponents() <= other.VersionComponents()

    def __eq__(self, other):
        return self.VersionComponents() == other.VersionComponents()

    def __ne__(self, other):
        return self.VersionComponents() != other.VersionComponents()

    def __gt__(self, other):
        return self.VersionComponents() > other.VersionComponents()

    def __ge__(self, other):
        return self.VersionComponents() >= other.VersionComponents()

    __hash__ = None

    def BuildPrefix(self):
        """Get the build prefix to match the buildspecs in manifest-versions."""
        if self.incr_type == "branch":
            if self.patch_number == "0":
                return "%s." % self.build_number
            else:
                return "%s.%s." % (self.build_number, self.branch_build_number)
        # Default to build incr_type.
        return ""

    def __str__(self):
        return "%s(%s)" % (self.__class__, self.VersionString())
