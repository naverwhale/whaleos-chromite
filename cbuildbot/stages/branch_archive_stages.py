# Copyright 2017 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Build stages specific to factory builds.

Factory builds use a mix of standard stages, and custom stages
related to how build artifacts are generated and published.
"""

import datetime
import json
import logging
import os
import shutil

from chromite.cbuildbot import cbuildbot_alerts
from chromite.cbuildbot import commands
from chromite.cbuildbot.stages import generic_stages
from chromite.cbuildbot.stages import workspace_stages
from chromite.lib import config_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import gs
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.lib import portage_util
from chromite.lib import timeout_util
from chromite.utils import gs_urls_util
from chromite.utils import pformat


class UnsafeBuildForPushImage(Exception):
    """Raised if push_image is run against a non-signable build."""


class WorkspaceArchiveBase(
    workspace_stages.WorkspaceStageBase,
    generic_stages.BoardSpecificBuilderStage,
    generic_stages.ArchivingStageMixin,
):
    """Base class for workspace archive stages.

    The expectation is that the archive stages will be creating a "branch"
    upload that looks like an older style branched infrastructure build would
    have generated in addition to a factory branch set of archive results.
    """

    BRANCH_NAME = "branch"

    @property
    def branch_config(self):
        """Uniqify the name across boards."""
        if self._run.options.debug:
            return "%s-%s-tryjob" % (self._current_board, self.BRANCH_NAME)
        else:
            return "%s-%s" % (self._current_board, self.BRANCH_NAME)

    @property
    def branch_version(self):
        """Uniqify the name across boards."""
        workspace_version_info = self.GetWorkspaceVersionInfo()

        if self._run.options.debug:
            build_identifier, _ = self._run.GetCIDBHandle()
            build_id = build_identifier.cidb_id
            return "R%s-%s-b%s" % (
                workspace_version_info.chrome_branch,
                workspace_version_info.VersionString(),
                build_id,
            )
        else:
            return "R%s-%s" % (
                workspace_version_info.chrome_branch,
                workspace_version_info.VersionString(),
            )

    @property
    def branch_archive_url(self):
        """Uniqify the name across boards."""
        return self.UniqifyArchiveUrl(config_lib.GetSiteParams().ARCHIVE_URL)

    def UniqifyArchiveUrl(self, archive_url):
        """Return an archive url unique to the current board.

        Args:
            archive_url: The base archive URL (e.g. 'chromeos-image-archive').

        Returns:
            The unique archive URL.
        """
        return os.path.join(
            archive_url, self.branch_config, self.branch_version
        )

    def GetBranchArchiveUrls(self):
        """Returns upload URLs for branch artifacts based on artifacts.json."""
        upload_urls = [self.branch_archive_url]
        artifacts_file = portage_util.ReadOverlayFile(
            "scripts/artifacts.json",
            board=self._current_board,
            buildroot=self._build_root,
        )
        if artifacts_file is not None:
            artifacts_json = json.loads(artifacts_file)
            extra_upload_urls = artifacts_json.get("extra_upload_urls", [])
            upload_urls += [
                self.UniqifyArchiveUrl(url) for url in extra_upload_urls
            ]
        return upload_urls

    def UploadBranchArtifact(self, path):
        """Upload artifacts to the branch build results."""
        logging.info("UploadBranchArtifact: %s", path)
        with osutils.TempDir(prefix="branch") as tempdir:
            artifact_path = os.path.join(
                tempdir, "%s/%s" % (self._current_board, os.path.basename(path))
            )

            logging.info("Rename: %s -> %s", path, artifact_path)
            os.mkdir(os.path.join(tempdir, self._current_board))
            shutil.copyfile(path, artifact_path)

            logging.info("Main artifact from: %s", artifact_path)
            self.UploadArtifact(artifact_path, archive=True)

        gs_context = gs.GSContext(dry_run=self._run.options.debug_forced)
        for url in self.GetBranchArchiveUrls():
            logging.info("Uploading branch artifact to %s...", url)
            with timeout_util.Timeout(20 * 60):
                logging.info("Branch artifact from: %s", path)
                gs_context.CopyInto(path, url, parallel=True, recursive=True)

    def PushBoardImage(self):
        """Helper to run push_image against the branch boards artifacts."""
        # This helper script is only available on internal manifests currently.
        if not self._run.config["internal"]:
            raise UnsafeBuildForPushImage(
                "Can't use push_image on external builds."
            )

        logging.info(
            "Use pushimage to publish signing artifacts for: %s",
            self._current_board,
        )

        # Push build artifacts to gs://chromeos-releases for signing and
        # release. This runs TOT pushimage against the build artifacts for the
        # branch.
        commands.PushImages(
            board=self._current_board,
            archive_url=self.branch_archive_url,
            dryrun=self._run.options.debug
            or not self._run.config["push_image"],
            profile=self._run.options.profile or self._run.config["profile"],
            sign_types=self._run.config["sign_types"] or [],
            buildroot=self._build_root,
        )

    def CreateBranchMetadataJson(self):
        """Create/publish the factory build artifact for the current board."""
        workspace_version_info = self.GetWorkspaceVersionInfo()

        # Use the metadata for the main build, with selected fields modified.
        board_metadata = self._run.attrs.metadata.GetDict()
        board_metadata["boards"] = [self._current_board]
        board_metadata["branch"] = self._run.config.workspace_branch
        board_metadata["version_full"] = self.branch_version
        board_metadata[
            "version_milestone"
        ] = workspace_version_info.chrome_branch
        board_metadata[
            "version_platform"
        ] = workspace_version_info.VersionString()
        board_metadata["version"] = {
            "platform": workspace_version_info.VersionString(),
            "full": self.branch_version,
            "milestone": workspace_version_info.chrome_branch,
        }

        current_time = datetime.datetime.now()
        current_time_stamp = cros_build_lib.UserDateTimeFormat(
            timeval=current_time
        )

        # We report the build as passing, since we can't get here if isn't.
        board_metadata["status"] = {
            "status": "pass",
            "summary": "",
            "current-time": current_time_stamp,
        }

        with osutils.TempDir(prefix="metadata") as tempdir:
            metadata_path = os.path.join(tempdir, constants.METADATA_JSON)
            logging.info("Writing metadata to %s.", metadata_path)
            osutils.WriteFile(
                metadata_path, pformat.json(board_metadata), atomic=True
            )

            self.UploadBranchArtifact(metadata_path)


class FactoryArchiveStage(WorkspaceArchiveBase):
    """Generates and publishes factory specific build artifacts."""

    BRANCH_NAME = "factory"

    def CreateFactoryZip(self):
        """Create/publish the firmware build artifact for the current board."""
        logging.info("Create factory_image.zip")

        # TODO: Move this image creation logic back into WorkspaceBuildImages.

        factory_install_symlink = None
        if "factory_install" in self._run.config["images"]:
            alias = commands.BuildFactoryInstallImage(
                self._build_root,
                self._current_board,
                extra_env=self._portage_extra_env,
            )

            factory_install_symlink = self.GetImageDirSymlink(
                alias, self._build_root
            )
            if self._run.config["factory_install_netboot"]:
                commands.MakeNetboot(
                    self._build_root,
                    self._current_board,
                    factory_install_symlink,
                )

        # Build and upload factory zip if needed.
        assert self._run.config["factory_toolkit"]

        with osutils.TempDir(prefix="factory_zip") as zip_dir:
            filename = commands.BuildFactoryZip(
                self._build_root,
                self._current_board,
                zip_dir,
                factory_install_symlink,
                self.branch_version,
            )

            self.UploadBranchArtifact(os.path.join(zip_dir, filename))

    def CreateTestImageTar(self):
        """Create and upload chromiumos_test_image.tar.xz.

        This depends on the WorkspaceBuildImage stage having previously created
        chromiumos_test_image.bin.
        """
        with osutils.TempDir(prefix="test_image_dir") as tempdir:
            tarball_path = os.path.join(tempdir, constants.TEST_IMAGE_TAR)

            cros_build_lib.CreateTarball(
                tarball_path,
                inputs=[constants.TEST_IMAGE_BIN],
                cwd=self.GetImageDirSymlink(
                    pointer="latest", buildroot=self._build_root
                ),
                compression=cros_build_lib.CompressionType.XZ,
            )

            self.UploadBranchArtifact(tarball_path)

    def CreateFactoryProjectToolkitsZip(self):
        """Create/publish the factory project toolkits for the current board."""
        toolkits_src_path = os.path.join(
            path_util.FromChrootPath(
                commands.FACTORY_PACKAGE_CHROOT_PATH
                % {"board": self._current_board},
                source_path=self._build_root,
            ),
            "project_toolkits",
            commands.FACTORY_PROJECT_PACKAGE,
        )
        if os.path.exists(toolkits_src_path):
            self.UploadBranchArtifact(toolkits_src_path)

    def BuildAutotestTarballs(self):
        """Build the autotest tarballs."""
        with osutils.TempDir(prefix="cbuildbot-autotest") as tempdir:
            cwd = os.path.abspath(
                path_util.FromChrootPath(
                    os.path.join(
                        os.path.sep,
                        "build",
                        self._current_board,
                        constants.AUTOTEST_BUILD_PATH,
                        "..",
                    ),
                    source_path=self._build_root,
                )
            )
            logging.debug(
                "Running BuildAutotestTarballsForHWTest root %s cwd %s"
                " target %s",
                self._build_root,
                cwd,
                tempdir,
            )
            for tarball in commands.BuildAutotestTarballsForHWTest(
                self._build_root, cwd, tempdir
            ):
                self.UploadBranchArtifact(tarball)

    def BuildTastTarball(self):
        """Build the tarball containing private Tast test bundles."""
        with osutils.TempDir(prefix="cbuildbot-tast") as tempdir:
            cwd = os.path.abspath(
                path_util.FromChrootPath(
                    os.path.join(
                        os.path.sep,
                        "build",
                        self._current_board,
                        "build",
                    ),
                    source_path=self._build_root,
                )
            )
            logging.debug("Running commands.BuildTastBundleTarball")
            tarball = commands.BuildTastBundleTarball(
                self._build_root, cwd, tempdir
            )
            if tarball:
                self.UploadBranchArtifact(tarball)

    def PerformStage(self):
        """Archive and publish the factory build artifacts."""
        logging.info("Factory version: %s", self.branch_version)
        logging.info("Archive build as: %s", self.branch_config)

        # Link branch build artifacts from build.
        branch_http_url = gs_urls_util.GsUrlToHttp(
            self.branch_archive_url, public=False, directory=True
        )

        label = "%s factory [%s]" % (self._current_board, self.branch_version)
        cbuildbot_alerts.PrintBuildbotLink(label, branch_http_url)

        # factory_image.zip
        self.CreateFactoryZip()
        self.CreateFactoryProjectToolkitsZip()
        self.CreateTestImageTar()
        self.CreateBranchMetadataJson()
        self.PushBoardImage()

        # Upload any needed HWTest artifacts.
        if (
            self._run.ShouldBuildAutotest()
            and self._run.config.upload_hw_test_artifacts
        ):
            self.BuildAutotestTarballs()
            self.BuildTastTarball()
