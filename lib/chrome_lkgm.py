# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Find LKGM or older latest version of ChromeOS image for a board

This module reads //chromeos/CHROMEOS_LKGM file in a chrome checkout to
determine what the current LKGM version is.
"""

import logging
import os
from typing import Optional

from chromite.lib import config_lib
from chromite.lib import constants
from chromite.lib import gs
from chromite.lib import osutils
from chromite.lib import path_util


class Error(Exception):
    """Base class for the errors happened upon finding ChromeOS image version"""


class NoChromiumSrcDir(Error):
    """Error thrown when no chromium src dir is found."""

    def __init__(self, path):
        super().__init__(f"No chromium src dir found in {path}")


class MissingLkgmFile(Error):
    """Error thrown when we cannot get the version from CHROMEOS_LKGM."""

    def __init__(self, path):
        super().__init__(f"Cannot parse CHROMEOS_LKGM file: {path}")


def GetChromeLkgm(chrome_src_dir: str = "") -> Optional[str]:
    """Get the CHROMEOS LKGM checked into the Chrome tree.

    Args:
        chrome_src_dir: chrome source directory.

    Returns:
        Version number in format '10171.0.0'.
    """
    if not chrome_src_dir:
        chrome_src_dir = path_util.DetermineCheckout().chrome_src_dir
    if not chrome_src_dir:
        return None
    lkgm_file = os.path.join(chrome_src_dir, constants.PATH_TO_CHROME_LKGM)
    version = osutils.ReadFile(lkgm_file).rstrip()
    logging.debug("Read LKGM version from %s: %s", lkgm_file, version)
    return version


class ChromeOSVersionFinder:
    """Finds LKGM or latest version of ChromeOS image for a board"""

    def __init__(
        self,
        cache_dir,
        board,
        fallback_versions,
        chrome_src=None,
        use_external_config=None,
    ):
        """Create a new object

        Args:
            cache_dir: The toplevel cache dir to use.
            board: The board to manage the SDK for.
            fallback_versions: number of older versions to be considered
            chrome_src: The location of the chrome checkout. If unspecified, the
                cwd is presumed to be within a chrome checkout.
            use_external_config: When identifying the configuration for a board,
                force usage of the external configuration if both external and
                internal are available.
        """
        self.cache_dir = cache_dir
        self.board = board
        if use_external_config or not self._HasInternalConfig():
            self.config_name = f"{board}-{config_lib.CONFIG_TYPE_PUBLIC}"
            self.gs_base = f"gs://chromiumos-image-archive/{self.config_name}"
        else:
            self.config_name = f"{board}-{config_lib.CONFIG_TYPE_RELEASE}"
            self.gs_base = f"gs://chromeos-image-archive/{self.config_name}"

        self.gs_ctx = gs.GSContext(cache_dir=cache_dir, init_boto=False)
        self.fallback_versions = fallback_versions
        self.chrome_src = chrome_src

    def _HasInternalConfig(self):
        """Determines if the SDK we need is provided by an internal builder.

        A given board can have a public and/or an internal builder that
        publishes its Simple Chrome SDK. e.g. "amd64-generic" only has a public
        builder, "scarlet" only has an internal builder, "octopus" has both. So
        if we haven't explicitly passed "--use-external-config", we need to
        figure out if we want to use a public or internal builder.

        The configs inside gs://chromeos-build-release-console are the proper
        source of truth for what boards have public or internal builders.
        However, the ACLs on that bucket make it difficult for some folk to
        inspect it. So we instead simply assume that everything but the
        "*-generic" boards have internal configs.

        TODO(b/241964080): Inspect gs://chromeos-build-release-console here
            instead if/when ACLs on that bucket are opened up.

        Returns:
            True if there's an internal builder available that publishes SDKs
            for the board.
        """
        return "generic" not in self.board

    def _GetFullVersionFromStorage(self, version_file):
        """Cat |version_file| in google storage.

        Args:
            version_file: google storage path of the version file.

        Returns:
            Version number in the format 'R30-3929.0.0' or None.
        """
        try:
            # If the version doesn't exist in google storage,
            # which isn't unlikely, don't waste time on retries.
            full_version = self.gs_ctx.Cat(
                version_file, retries=0, encoding="utf-8"
            )
            assert full_version.startswith("R")
            return full_version
        except (gs.GSNoSuchKey, gs.GSCommandError):
            return None

    def _GetFullVersionFromRecentLatest(self, version):
        """Gets the full version number from a recent LATEST- file.

        If LATEST-{version} does not exist, we need to look for a recent
        LATEST- file to get a valid full version from.

        Args:
            version: The version number to look backwards from. If version is
                not a canary version (ending in .0.0), returns None.

        Returns:
            Version number in the format 'R30-3929.0.0' or None.
        """

        # If version does not end in .0.0 it is not a canary so fail.
        if not version.endswith(".0.0"):
            return None
        version_base = int(version.split(".")[0])
        version_base_min = max(version_base - self.fallback_versions, 0)

        for v in range(version_base - 1, version_base_min, -1):
            version_file = f"{self.gs_base}/LATEST-{v}.0.0"
            logging.info("Trying: %s", version_file)
            full_version = self._GetFullVersionFromStorage(version_file)
            if full_version is not None:
                logging.info(
                    "Using cros version from most recent LATEST file: %s -> %s",
                    version_file,
                    full_version,
                )
                return full_version
        logging.warning(
            "No recent LATEST file found from %s.0.0 to %s.0.0",
            version_base_min,
            version_base,
        )
        return None

    def GetFullVersionFromLatest(self, version):
        """Gets the full version number from the LATEST-{version} file.

        Args:
            version: The version number or branch to look at.

        Returns:
            Version number in the format 'R30-3929.0.0' or None.
        """
        version_file = f"{self.gs_base}/LATEST-{version}"
        full_version = self._GetFullVersionFromStorage(version_file)
        if full_version is None:
            logging.warning("No LATEST file matching SDK version %s", version)
            return self._GetFullVersionFromRecentLatest(version)
        return full_version
