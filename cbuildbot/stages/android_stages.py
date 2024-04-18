# Copyright 2016 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module containing the Android stages."""

import logging
import os

from chromite.cbuildbot import cbuildbot_alerts
from chromite.cbuildbot import cbuildbot_run
from chromite.cbuildbot.stages import generic_stages
from chromite.lib import config_lib
from chromite.lib import constants
from chromite.lib import gs
from chromite.lib import osutils


class AndroidMetadataStage(
    generic_stages.BuilderStage, generic_stages.ArchivingStageMixin
):
    """Stage that records Android container version in metadata.

    This stage runs on every builder, not limited to Android PFQ. Metadata
    written by this stage must reflect the actual Android version of the build
    artifact.

    Metadata written by this stage will be consumed by various external tools
    such as GoldenEye.
    """

    category = constants.PRODUCT_ANDROID_STAGE

    def _UpdateBoardDictsForAndroidBuildInfo(self):
        """Updates board metadata to fill in Android build info.

        Returns:
            (versions, branches, targets) where:
                versions: A set of Android versions used in target boards.
                branches: A set of Android branch names used in target boards.
                targets: A set of Android targets used in target boards.
        """
        # Need to always iterate through and generate the board-specific
        # Android version metadata.  Each board must be handled separately
        # since there might be differing builds in the same release group.
        versions = set()
        branches = set()
        targets = set()

        for builder_run in [self._run]:
            for board in builder_run.config.boards:
                try:
                    # Determine the version for each board and record metadata.
                    version = self._run.DetermineAndroidVersion(boards=[board])
                    builder_run.attrs.metadata.UpdateBoardDictWithDict(
                        board, {"android-container-version": version}
                    )
                    versions.add(version)
                    logging.info(
                        "Board %s has Android version %s", board, version
                    )
                except cbuildbot_run.NoAndroidVersionError as ex:
                    logging.info(
                        "Board %s does not contain Android (%s)", board, ex
                    )
                try:
                    # Determine the branch for each board and record metadata.
                    branch = self._run.DetermineAndroidBranch(board)
                    builder_run.attrs.metadata.UpdateBoardDictWithDict(
                        board, {"android-container-branch": branch}
                    )
                    branches.add(branch)
                    logging.info(
                        "Board %s has Android branch %s", board, branch
                    )
                except cbuildbot_run.NoAndroidBranchError as ex:
                    logging.info(
                        "Board %s does not contain Android (%s)", board, ex
                    )
                try:
                    # Determine the target for each board and record metadata.
                    target = self._run.DetermineAndroidTarget(board)
                    builder_run.attrs.metadata.UpdateBoardDictWithDict(
                        board, {"android-container-target": target}
                    )
                    targets.add(target)
                    logging.info(
                        "Board %s has Android target %s", board, target
                    )
                except cbuildbot_run.NoAndroidTargetError as ex:
                    logging.info(
                        "Board %s does not contain Android (%s)", board, ex
                    )
                arc_use = self._run.HasUseFlag(board, "arc")
                logging.info(
                    "Board %s %s arc USE flag set.",
                    board,
                    "has" if arc_use else "does not have",
                )
                builder_run.attrs.metadata.UpdateBoardDictWithDict(
                    board, {"arc-use-set": arc_use}
                )

        return (versions, branches, targets)

    def PerformStage(self):
        with osutils.ChdirContext(self._build_root):
            (
                versions,
                branches,
                targets,
            ) = self._UpdateBoardDictsForAndroidBuildInfo()

        # If there is a unique one across all the boards, treat it as the
        # version for the build.
        # TODO(nya): Represent "N/A" and "Multiple" differently in metadata.
        def _Aggregate(v):
            if not v:
                return (None, "N/A")
            elif len(v) == 1:
                return (v[0], str(v[0]))
            return (None, "Multiple")

        metadata_version, debug_version = _Aggregate(list(versions))
        metadata_branch, debug_branch = _Aggregate(list(branches))
        metadata_target, debug_target = _Aggregate(list(targets))

        # Update the primary metadata and upload it.
        self._run.attrs.metadata.UpdateKeyDictWithDict(
            "version",
            {
                "android": metadata_version,
                "android-branch": metadata_branch,
                "android-target": metadata_target,
            },
        )
        self.UploadMetadata(filename=constants.PARTIAL_METADATA_JSON)

        # Leave build info in buildbot steps page for convenience.
        cbuildbot_alerts.PrintBuildbotStepText("tag %s" % debug_version)
        cbuildbot_alerts.PrintBuildbotStepText("branch %s" % debug_branch)
        cbuildbot_alerts.PrintBuildbotStepText("target %s" % debug_target)


class DownloadAndroidDebugSymbolsStage(
    generic_stages.BoardSpecificBuilderStage, generic_stages.ArchivingStageMixin
):
    """Stage that downloads Android debug symbols.

    Downloaded archive will be picked up by DebugSymbolsStage.
    """

    category = constants.CI_INFRA_STAGE

    def PerformStage(self):
        if not config_lib.IsCanaryType(self._run.config.build_type):
            logging.info("This stage runs only in release builders.")
            return

        # Get the Android versions set by AndroidMetadataStage.
        version_dict = self._run.attrs.metadata.GetDict().get("version", {})
        android_build_branch = version_dict.get("android-branch")
        android_version = version_dict.get("android")

        # On boards not supporting Android, versions will be None.
        if not (android_build_branch and android_version):
            logging.info("Android is not enabled on this board. Skipping.")
            return

        logging.info(
            "Downloading symbols of Android %s (%s)...",
            android_version,
            android_build_branch,
        )

        with osutils.ChdirContext(self._build_root):
            arch = self._run.DetermineAndroidABI(self._current_board)
            variant = self._run.DetermineAndroidVariant(self._current_board)
            android_target = self._run.DetermineAndroidTarget(
                self._current_board
            )

        symbols_file_url = constants.ANDROID_SYMBOLS_URL_TEMPLATE % {
            "branch": android_build_branch,
            "target": android_target,
            "arch": arch,
            "version": android_version,
            "variant": variant,
        }
        symbols_file = os.path.join(
            self.archive_path, constants.ANDROID_SYMBOLS_FILE
        )
        gs_context = gs.GSContext()
        gs_context.Copy(symbols_file_url, symbols_file)
