# Copyright 2017 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Build stages related to a secondary workspace directory.

A workspace is a compelete ChromeOS checkout and may contain it's own chroot,
.cache directory, etc. Conceptually, cbuildbot_launch creates a workspace for
the intitial ChromeOS build, but these stages are for creating a secondary
build.

This might be useful if a build needs to work with more than one branch at a
time, or make changes to ChromeOS code without changing the code it is currently
running.

A secondary workspace may not be inside an existing ChromeOS repo checkout.
Also, the initial sync will usually take about 40 minutes, so performance should
be considered carefully.
"""

import dataclasses
import logging
import os
from pathlib import Path
import re
from typing import Tuple

from chromite.cbuildbot import cbuildbot_alerts
from chromite.cbuildbot import cbuildbot_run
from chromite.cbuildbot import commands
from chromite.cbuildbot import manifest_version
from chromite.cbuildbot import trybot_patch_pool
from chromite.cbuildbot.stages import artifact_stages
from chromite.cbuildbot.stages import generic_stages
from chromite.lib import buildbucket_v2
from chromite.lib import config_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_sdk_lib
from chromite.lib import failures_lib
from chromite.lib import gs
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.lib import portage_util
from chromite.lib import request_build
from chromite.lib import timeout_util
from chromite.lib.parser import package_info
from chromite.service import android


BUILD_PACKAGES_PREBUILTS = "10774.0.0"
BUILD_IMAGE_BUILDER_PATH = "8183.0.0"
BUILD_IMAGE_ECLEAN_FLAG = "8318.0.0"
ANDROID_BREAKPAD = "9667.0.0"
PORTAGE_2_3_75_UPDATE = "12693.0.0"
SETUP_BOARD_PORT_COMPLETE = "11802.0.0"
BUILD_PACKAGES_PORT_COMPLETE = "14950.0.0"


class InvalidWorkspace(failures_lib.StepFailure):
    """Raised when a workspace isn't usable."""


def ChrootArgs(options):
    """cros_sdk command line arguments.

    To ensure consistent arguments passed into cros_sdk for workspace stages,
    compute them here.

    Args:
        options: self._run.options

    Returns:
        List of command line arguments, normally passed into run as chroot_args.
    """
    chroot_args = ["--cache-dir", options.cache_dir]
    if options.chrome_root:
        chroot_args += ["--chrome_root", options.chrome_root]

    return chroot_args


class WorkspaceStageBase(generic_stages.BuilderStage):
    """Base class for Workspace stages."""

    def __init__(self, builder_run, buildstore, build_root, **kwargs):
        """Initializer.

        Properties for subclasses:
          self._build_root to access the workspace directory,
          self._orig_root to access the original buildroot.

        Args:
            builder_run: BuilderRun object.
            buildstore: BuildStore instance to make DB calls with.
            build_root: Fully qualified path to use as a string.
        """
        super().__init__(
            builder_run, buildstore, build_root=build_root, **kwargs
        )

        self._orig_root = builder_run.buildroot

    def GetWorkspaceRepo(self):
        """Fetch a repo object for the workspace.

        Returns:
            repository.RepoRepository instance for the workspace.
        """
        # TODO: Properly select the manifest. Currently hard coded to internal
        # branch checkouts.
        manifest_url = config_lib.GetSiteParams().MANIFEST_INT_URL

        # Workspace repos use the workspace URL / branch.
        return self.GetRepoRepository(
            manifest_repo_url=manifest_url,
            branch=self._run.config.workspace_branch,
        )

    def GetWorkspaceVersionInfo(self):
        """Fetch a VersionInfo for the workspace.

        Only valid after the workspace has been synced.

        Returns:
            manifest-version.VersionInfo object based on the workspace checkout.
        """
        return commands.GetBuildrootVersionInfo(self._build_root)

    def AfterLimit(self, limit):
        """Is workspace version newer than cutoff limit?

        Args:
            limit: String version of format '123.0.0'

        Returns:
            bool: True if workspace has newer version than limit.
        """
        return commands.IsBuildRootAfterLimit(self._build_root, limit)

    # Standardize manifest_versions paths for workspaces.

    @property
    def int_manifest_versions_path(self):
        """Path to use for internal manifest_versions."""
        return os.path.join(
            self._orig_root,
            config_lib.GetSiteParams().INTERNAL_MANIFEST_VERSIONS_PATH,
        )

    @property
    def ext_manifest_versions_path(self):
        """Path to use for external manifest_versions."""
        return os.path.join(
            self._orig_root,
            config_lib.GetSiteParams().EXTERNAL_MANIFEST_VERSIONS_PATH,
        )

    def GetWorkspaceReleaseTag(self):
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


class SyncStage(WorkspaceStageBase):
    """Perform a repo sync."""

    category = constants.CI_INFRA_STAGE

    def __init__(
        self,
        builder_run,
        buildstore,
        build_root,
        external=False,
        branch=None,
        version=None,
        patch_pool=None,
        copy_repo=None,
        **kwargs,
    ):
        """Initializer.

        Args:
            builder_run: BuilderRun object.
            buildstore: BuildStore instance to make DB calls with.
            build_root: Path to sync into.
            external: Boolean telling if this an internal or external checkout.
            branch: Branch to sync, with default to master.
            version: Version number to sync too.
            patch_pool: None or a list of lib.patch.GerritPatch objects.
            copy_repo: None, or the copy of a repo to seed the sync from.
        """
        super().__init__(
            builder_run, buildstore, build_root=build_root, **kwargs
        )

        self.external = external
        self.branch = branch
        self.version = version
        self.patch_pool = patch_pool
        self.copy_repo = copy_repo

    def PerformStage(self):
        """Sync stuff!"""
        logging.info("SubWorkspaceSync")

        cmd = [
            constants.CHROMITE_DIR / "scripts" / "repo_sync_manifest",
            "--repo-root",
            self._build_root,
            "--manifest-versions-int",
            self.int_manifest_versions_path,
            "--manifest-versions-ext",
            self.ext_manifest_versions_path,
        ]

        if self.external:
            cmd += ["--external"]

        if self.branch and not self.version:
            cmd += ["--branch", self.branch]

        if self.version:
            cbuildbot_alerts.PrintBuildbotStepText("Version: %s" % self.version)
            cmd += ["--version", self.version]

        if self.patch_pool:
            patch_options = []
            for patch in self.patch_pool:
                cbuildbot_alerts.PrintBuildbotLink(str(patch), patch.url)
                patch_options += ["--gerrit-patches", patch.gerrit_number_str]

            cmd += patch_options

        if self.copy_repo:
            cmd += ["--copy-repo", self.copy_repo]

        assert not (
            self.version and self.patch_pool
        ), 'Can\'t cherry-pick "%s" into an official version "%s."' % (
            patch_options,
            self.version,
        )

        cros_build_lib.run(cmd)


class WorkspaceSyncStage(WorkspaceStageBase):
    """Checkout both infra and workspace repos."""

    category = constants.CI_INFRA_STAGE

    def PerformStage(self):
        """Sync all the stuff!"""
        # Select changes to cherry-pick into the build, and filter them into
        # chromite versus branch changes.
        patch_pool = trybot_patch_pool.TrybotPatchPool.FromOptions(
            gerrit_patches=self._run.options.gerrit_patches
        )

        infra_pool = patch_pool.FilterFn(trybot_patch_pool.ChromiteFilter)
        branch_pool = patch_pool.FilterFn(
            trybot_patch_pool.ChromiteFilter, negate=True
        )

        infra_branch = self._run.manifest_branch

        SyncStage(
            self._run,
            self.buildstore,
            build_root=self._orig_root,
            external=True,
            branch=infra_branch,
            patch_pool=infra_pool,
            suffix=" [Infra %s]" % infra_branch,
        ).Run()

        branch = self._run.config.workspace_branch

        SyncStage(
            self._run,
            self.buildstore,
            build_root=self._build_root,
            external=not self._run.config.internal,
            branch=branch,
            version=self._run.options.force_version,
            patch_pool=branch_pool,
            copy_repo=self._orig_root,
            suffix=" [%s]" % branch,
        ).Run()


class WorkspaceSyncChromeStage(WorkspaceStageBase):
    """Stage that syncs Chrome sources if needed."""

    category = constants.PRODUCT_CHROME_STAGE

    # 12 hours in seconds should be long enough to fetch Chrome. I hope.
    SYNC_CHROME_TIMEOUT = 12 * 60 * 60

    def DetermineChromeVersion(self):
        pkg_info = portage_util.PortageqBestVisible(
            constants.CHROME_CP, cwd=self._build_root
        )
        return pkg_info.version.partition("_")[0]

    @failures_lib.SetFailureType(failures_lib.InfrastructureFailure)
    def PerformStage(self):
        chrome_version = self.DetermineChromeVersion()

        cbuildbot_alerts.PrintBuildbotStepText("tag %s" % chrome_version)

        git_cache_dir = (
            self._run.options.chrome_preload_dir
            or self._run.options.git_cache_dir
        )
        with timeout_util.Timeout(self.SYNC_CHROME_TIMEOUT):
            commands.SyncChrome(
                self._orig_root,
                self._run.options.chrome_root,
                self._run.config.useflags,
                tag=chrome_version,
                git_cache_dir=git_cache_dir,
                workspace=self._build_root,
            )


class WorkspaceUprevStage(WorkspaceStageBase):
    """Uprev ebuilds.

    This stage updates ebuilds to top of branch with no verification, or
    prebuilt generation. This is generally intended only for branch builds.
    """

    config_name = "uprev"

    def __init__(self, builder_run, buildstore, boards=None, **kwargs):
        super().__init__(builder_run, buildstore, **kwargs)
        if boards is not None:
            self._boards = boards

    def PerformStage(self):
        """Perform the uprev."""
        commands.UprevPackages(
            self._orig_root,
            self._boards,
            overlay_type=self._run.config.overlays,
            workspace=self._build_root,
        )


class WorkspacePublishStage(WorkspaceStageBase):
    """Publish ebuilds."""

    config_name = "push_overlays"

    def PerformStage(self):
        """Perform the push."""
        logging.info("Pushing.")
        commands.UprevPush(
            self._orig_root,
            overlay_type=self._run.config.push_overlays,
            dryrun=self._run.options.debug,
            workspace=self._build_root,
        )


class WorkspacePublishBuildspecStage(WorkspaceStageBase):
    """Increment the ChromeOS version, and publish a buildspec."""

    def PerformStage(self):
        """Increment ChromeOS version, and publish buildpec."""
        repo = self.GetWorkspaceRepo()

        # TODO: Add 'patch' support somehow,
        if repo.branch in ("main", "master"):
            incr_type = "build"
        else:
            incr_type = "branch"

        build_spec_path = manifest_version.GenerateAndPublishOfficialBuildSpec(
            repo,
            incr_type,
            manifest_versions_int=self.int_manifest_versions_path,
            manifest_versions_ext=self.ext_manifest_versions_path,
            dryrun=self._run.options.debug,
        )

        if self._run.options.debug:
            msg = "DEBUG: Would have defined: %s" % build_spec_path
        else:
            msg = "Defined: %s" % build_spec_path

        cbuildbot_alerts.PrintBuildbotStepText(msg)


class WorkspaceScheduleChildrenStage(WorkspaceStageBase):
    """Schedule child builds for this buildspec."""

    def PerformStage(self):
        """Schedule child builds for this buildspec."""
        # build_identifier, _ = self._run.GetCIDBHandle()
        # build_id = build_identifier.cidb_id
        # master_buildbucket_id = self._run.options.buildbucket_id
        version_info = self.GetWorkspaceVersionInfo()

        extra_args = [
            "--buildbot",
            "--version",
            version_info.VersionString(),
        ]

        if self._run.options.debug:
            extra_args.append("--debug")

        for child_name in self._run.config.slave_configs:
            raw_request = request_build.RequestBuild(
                build_config=child_name,
                branch=self._run.manifest_branch,
                # See crbug.com/940969. These id's get children killed during
                # multiple quick builds.
                # master_cidb_id=build_id,
                # master_buildbucket_id=master_buildbucket_id,
                extra_args=extra_args,
            )
            request = raw_request.CreateBuildRequest()
            buildbucket_client = buildbucket_v2.BuildbucketV2()

            if self._run.options.debug:
                logging.info(
                    "Build_name %s request_branch %s",
                    child_name,
                    raw_request.branch,
                )
                continue
            result = buildbucket_client.ScheduleBuild(
                request_id=str(request["request_id"]),
                builder=request["builder"],
                properties=request["properties"],
                tags=request["tags"],
                dimensions=request["dimensions"],
            )

            logging.info(
                "Build_name %s buildbucket_id %s created_timestamp %s",
                child_name,
                result.id,
                result.create_time.ToJsonString(),
            )
            cbuildbot_alerts.PrintBuildbotLink(
                child_name, f"{constants.CHROMEOS_MILO_HOST}{result.id}"
            )


class WorkspaceInitSDKStage(WorkspaceStageBase):
    """Stage that is responsible for initializing the SDK."""

    category = constants.CI_INFRA_STAGE

    def PerformStage(self):
        chroot_path = os.path.join(
            self._build_root, constants.DEFAULT_CHROOT_DIR
        )

        # Worksapce chroots are always wiped by cleanup stage, no need to
        # update.
        cmd = ["cros_sdk", "--create"] + ChrootArgs(self._run.options)

        commands.RunBuildScript(
            self._build_root,
            cmd,
            chromite_cmd=True,
            extra_env=self._portage_extra_env,
        )

        post_ver = cros_sdk_lib.GetChrootVersion(chroot_path)
        cbuildbot_alerts.PrintBuildbotStepText(post_ver)


@dataclasses.dataclass
class MountPathInfo:
    """Simple object to hold data about where a chroot path gets mounted.

    Attributes:
        chroot_path: The absolute path inside the chroot that gets mounted.
        old_style_path: The host-absolute path to which the chroot_path was
            mounted for older branches.
        new_style_path: The host-absolute path to which the chroot_path is
            mounted for new branches (and tip-of-tree).
    """

    chroot_path: Path
    old_style_path: Path
    new_style_path: Path


class WorkspaceLinkMountPathsStage(WorkspaceStageBase):
    """Stage that sets up symlinks to let us access new-style mount paths.

    Paths inside the chroot are accessible from outside the chroot via
    well-known mount paths. However, in 2023 several of those mount paths have
    changed.

    This causes a problem when cbuildbot tries to convert an inside-path to a
    host-absolute path for a workspace branch. Cbuildbot runs from tip-of-tree,
    so it will return the new-style mounted path, even if the workspace branch's
    chroot still uses old-style mounting logic.

    This stage solves that problem by creating symlinks from the new-style mount
    paths to the old-style paths. That way, if tip-of-tree cbuildbot reports
    that a file should be found at a new-style location, it will work even if
    the file is actually mounted to the old-style location.

    This is a quick fix, because workspace builders are expected to be fully
    deleted in 2023.

    This class currently ignores `/out` mounting, because cbuildbot doesn't seem
    to rely on `/out`, and because the symlink would need to somehow contain
    other symlinks, which seems gnarly. `/out` mounting was added in 15439.0.0;
    see http://crrev.com/c/4477625.
    """

    category = constants.CI_INFRA_STAGE

    def __init__(self, *args, **kwargs) -> None:
        """Set up attributes needed for this class."""
        # super().__init__() must come first, since it creates self._build_root.
        super().__init__(*args, **kwargs)

        self.chroot_path = Path(self._build_root) / constants.DEFAULT_CHROOT_DIR
        self.out_path = Path(self._build_root) / constants.DEFAULT_OUT_DIR

        self._required_mount_paths: Tuple[MountPathInfo] = (
            # Previously, /tmp in the chroot was mounted at ${CHROOT}/tmp.
            # Since 15483.0.0, it has been mounted at ${OUT}/tmp.
            # See https://crrev.com/c/4522313.
            MountPathInfo(
                chroot_path=Path("/tmp"),
                old_style_path=self.chroot_path / "tmp",
                new_style_path=self.out_path / "tmp",
            ),
            # Previously, /home in the chroot was mounted at ${CHROOT}/home.
            # Since 15588.0.0, it has been mounted at ${OUT}/home.
            # See https://crrev.com/c/4522314.
            MountPathInfo(
                chroot_path=Path("/home"),
                old_style_path=self.chroot_path / "home",
                new_style_path=self.out_path / "home",
            ),
            # Previously, /build in the chroot was mounted at ${CHROOT}/build.
            # Since 15613, it has been mounted at ${OUT}/build.
            # See https://crrev.com/c/4808858.
            MountPathInfo(
                chroot_path=Path("/build"),
                old_style_path=self.chroot_path / "build",
                new_style_path=self.out_path / "build",
            ),
        )

    def PerformStage(self) -> None:
        """Create the symlinks, and prove that they worked right."""
        self._CreateOutDir()
        self._CreateLinks()
        self._VerifyLinks()

    def _CreateOutDir(self) -> None:
        """Make an out-dir next to the workspace chroot, if it doesn't exist."""
        if self.out_path.exists():
            return
        osutils.SafeMakedirs(self.out_path)

    def _CreateLinks(self) -> None:
        """Create the symlinks."""
        for mount_path in self._required_mount_paths:
            self._CreateLink(mount_path)

    def _CreateLink(self, mount_path: MountPathInfo) -> None:
        """Create a link from the new-style path pointing to the old-style path.

        If the new-style mount path already exists, assume that the workspace
        branch is already mounting to that new path, so return early.

        If the old-style mount path doesn't already exist, create it so that the
        symlink target will definitely exist.
        """
        if mount_path.new_style_path.exists():
            return
        if not mount_path.old_style_path.exists():
            logging.info(
                "Creating old-style mount path as a symlink target: %s",
                mount_path.old_style_path,
            )
            osutils.SafeMakedirs(
                mount_path.old_style_path, sudo=True, mode=0o775
            )
        logging.info(
            "Creating symlink at %s pointing to %s",
            mount_path.new_style_path,
            mount_path.old_style_path,
        )
        osutils.SafeSymlink(
            mount_path.old_style_path, mount_path.new_style_path
        )

    def _VerifyLinks(self) -> None:
        """Prove that all the symlinks work as expected.

        Factory builders take a long time to run, sometimes over 10 hours. It
        would be unfortunate to wait 10 hours before we discover that our
        builders can't find chroot files at the expected location.
        """
        for mount_path in self._required_mount_paths:
            self._VerifyLink(mount_path)

    def _VerifyLink(self, mount_path: MountPathInfo) -> None:
        """Prove that the symlink for the given mount path works as expected.

        Create a file in the chroot, and then try to find it at the new-style
        location. Then, just to be double-sure, also use
        path_util.FromChrootPath() to make sure we'll actually find it in
        practice.

        No need to double down with chroot.full_path(), since it uses the same
        logic.

        Raises:
            FileNotFoundError: If we couldn't find a newly created file in any
                of the required mount paths.
        """
        _filename = "find_me"

        # Create the file inside the SDK.
        inside_path = mount_path.chroot_path / _filename
        commands.RunBuildScript(
            self._build_root,
            ["touch", str(inside_path)],
            sudo=True,
            enter_chroot=True,
        )

        # Try to find the file in the directory that we mounted.
        new_style_filepath = mount_path.new_style_path / _filename
        if not new_style_filepath.exists():
            raise FileNotFoundError(new_style_filepath)

        # Try to find the file where path_util thinks it should be.
        path_util_filepath = path_util.FromChrootPath(
            inside_path, source_path=self._build_root
        )
        if not Path(path_util_filepath).exists():
            raise FileNotFoundError(path_util_filepath)


class WorkspaceUpdateSDKStage(WorkspaceStageBase):
    """Stage that is responsible for updating the chroot."""

    option_name = "build"
    category = constants.CI_INFRA_STAGE

    def PerformStage(self):
        """Do the work of updating the chroot."""
        commands.UpdateChroot(
            self._build_root,
            usepkg=not self._latest_toolchain,
            extra_env=self._portage_extra_env,
            chroot_args=["--cache-dir", self._run.options.cache_dir],
        )


class WorkspaceSetupBoardStage(
    generic_stages.BoardSpecificBuilderStage, WorkspaceStageBase
):
    """Stage responsible for building host pkgs and setting up a board."""

    category = constants.CI_INFRA_STAGE

    def PerformStage(self):
        usepkg = self._run.config.usepkg_build_packages
        func = (
            commands.SetupBoard
            if self.AfterLimit(SETUP_BOARD_PORT_COMPLETE)
            else commands.LegacySetupBoard
        )
        func(
            self._build_root,
            board=self._current_board,
            usepkg=usepkg,
            force=self._run.config.board_replace,
            profile=self._run.options.profile or self._run.config.profile,
            chroot_upgrade=False,
            chroot_args=ChrootArgs(self._run.options),
            extra_env=self._portage_extra_env,
        )


class WorkspaceBuildPackagesStage(
    generic_stages.BoardSpecificBuilderStage, WorkspaceStageBase
):
    """Build Chromium OS packages."""

    category = constants.PRODUCT_OS_STAGE

    def PerformStage(self):
        usepkg = (
            self._run.config.usepkg_build_packages
            if self.AfterLimit(BUILD_PACKAGES_PREBUILTS)
            else False
        )

        build_packages_func = (
            commands.Build
            if self.AfterLimit(BUILD_PACKAGES_PORT_COMPLETE)
            else commands.LegacyBuild
        )
        build_packages_func(
            self._build_root,
            self._current_board,
            self._run.options.tests,
            usepkg,
            packages=self.GetListOfPackagesToBuild(),
            skip_chroot_upgrade=True,
            extra_env=self._portage_extra_env,
            noretry=self._run.config.nobuildretry,
            chroot_args=ChrootArgs(self._run.options),
        )


class WorkspaceUnitTestStage(
    generic_stages.BoardSpecificBuilderStage, WorkspaceStageBase
):
    """Run unit tests."""

    option_name = "tests"
    config_name = "unittests"
    category = constants.PRODUCT_OS_STAGE

    # If the unit tests take longer than 120 minutes, abort.
    UNIT_TEST_TIMEOUT = 120 * 60

    def PerformStage(self):
        extra_env = {}
        if self._run.config.useflags:
            extra_env["USE"] = " ".join(self._run.config.useflags)
        r = " Reached UnitTestStage timeout."
        with timeout_util.Timeout(self.UNIT_TEST_TIMEOUT, reason_message=r):
            try:
                commands.RunUnitTests(
                    self._build_root,
                    self._current_board,
                    build_stage=self._run.config.build_packages,
                    chroot_args=ChrootArgs(self._run.options),
                    extra_env=extra_env,
                )
            except failures_lib.BuildScriptFailure:
                cbuildbot_alerts.PrintBuildbotStepWarnings()
                logging.warning("Unittests failed. Ignored crbug.com/936123.")


class WorkspaceBuildImageStage(
    generic_stages.BoardSpecificBuilderStage, WorkspaceStageBase
):
    """Build standard Chromium OS images."""

    option_name = "build"
    config_name = "images"
    category = constants.PRODUCT_OS_STAGE

    def PerformStage(self):
        # Collect build_image arguments.
        version = self.GetWorkspaceReleaseTag()
        rootfs_verification = self._run.config.rootfs_verification
        builder_path = "/".join([self._bot_id, version])

        # We only build base, dev, and test images from this stage.
        images_can_build = set(["base", "dev", "test"])
        images_to_build = set(self._run.config.images).intersection(
            images_can_build
        )
        assert images_to_build

        # Build up command line.
        cmd = [
            "./build_image",
            "--board",
            self._current_board,
            "--replace",
            "--version",
            version,
        ]

        if self.AfterLimit(BUILD_IMAGE_ECLEAN_FLAG):
            cmd += ["--noeclean"]

        if not rootfs_verification:
            cmd += ["--noenable_rootfs_verification"]

        if self.AfterLimit(BUILD_IMAGE_BUILDER_PATH):
            cmd += ["--builder_path", builder_path]

        cmd += sorted(images_to_build)

        # Run command.
        commands.RunBuildScript(
            self._build_root,
            cmd,
            enter_chroot=True,
            extra_env=self._portage_extra_env,
            chroot_args=ChrootArgs(self._run.options),
        )


class WorkspaceDebugSymbolsStage(
    WorkspaceStageBase,
    generic_stages.BoardSpecificBuilderStage,
    generic_stages.ArchivingStageMixin,
):
    """Handles generation & upload of debug symbols."""

    config_name = "debug_symbols"
    category = constants.PRODUCT_OS_STAGE

    @failures_lib.SetFailureType(failures_lib.InfrastructureFailure)
    def PerformStage(self):
        """Generate debug symbols and upload debug.tgz."""
        buildroot = self._build_root
        board = self._current_board

        # Generate breakpad symbols of Chrome OS binaries.
        commands.GenerateBreakpadSymbols(
            buildroot,
            board,
            self._run.options.debug_forced,
            chroot_args=ChrootArgs(self._run.options),
            extra_env=self._portage_extra_env,
        )

        # Download android symbols (if this build has them), and Generate
        # breakpad symbols of Android binaries. This must be done after
        # GenerateBreakpadSymbols because it clobbers the output
        # directory.
        symbols_file = self.DownloadAndroidSymbols()

        if symbols_file:
            try:
                commands.GenerateAndroidBreakpadSymbols(
                    buildroot,
                    board,
                    symbols_file,
                    chroot_args=ChrootArgs(self._run.options),
                    extra_env=self._portage_extra_env,
                )
            except failures_lib.BuildScriptFailure:
                # Android breakpad symbol preparation is expected to work in
                # modern branches.
                if self.AfterLimit(ANDROID_BREAKPAD):
                    raise

                # For older branches, we only process them on a best effort
                # basis.
                cbuildbot_alerts.PrintBuildbotStepWarnings()
                logging.warning("Preparing Android symbols failed, ignoring..")

        # Upload them.
        self.UploadDebugTarball()

        # Upload debug/breakpad tarball.
        self.UploadDebugBreakpadTarball()

        # Upload them to crash server.
        if self._run.config.upload_symbols:
            self.UploadSymbols(buildroot, board)

    def UploadDebugTarball(self):
        """Generate and upload the debug tarball."""
        filename = commands.GenerateDebugTarball(
            buildroot=self._build_root,
            board=self._current_board,
            archive_path=self.archive_path,
            gdb_symbols=self._run.config.archive_build_debug,
            archive_name="debug.tgz",
            chroot_compression=False,
        )
        self.UploadArtifact(filename, archive=False)

    def UploadDebugBreakpadTarball(self):
        """Generate and upload the debug tarball with only breakpad files."""
        filename = commands.GenerateDebugTarball(
            buildroot=self._build_root,
            board=self._current_board,
            archive_path=self.archive_path,
            gdb_symbols=False,
            archive_name="debug_breakpad.tar.xz",
            chroot_compression=False,
        )
        self.UploadArtifact(filename, archive=False)

    def UploadSymbols(self, buildroot, board):
        """Upload generated debug symbols."""
        failed_name = "failed_upload_symbols.list"
        failed_list = os.path.join(self.archive_path, failed_name)

        if self._run.options.debug:
            # For debug builds, limit ourselves to just uploading 1 symbol.
            # This way trybots and such still exercise this code.
            cnt = 1
            official = False
        else:
            cnt = None
            official = self._run.config.chromeos_official

        upload_passed = True
        try:
            commands.UploadSymbols(
                buildroot,
                board,
                official,
                cnt,
                failed_list,
                chroot_args=ChrootArgs(self._run.options),
                extra_env=self._portage_extra_env,
            )
        except failures_lib.BuildScriptFailure:
            upload_passed = False

        if os.path.exists(failed_list):
            self.UploadArtifact(failed_name, archive=False)

            logging.notice(
                "To upload the missing symbols from this build, run:"
            )
            for url in self._GetUploadUrls(filename=failed_name):
                logging.notice(
                    "upload_symbols --failed-list %s %s",
                    os.path.join(url, failed_name),
                    os.path.join(url, "debug_breakpad.tar.xz"),
                )

        # Delay throwing the exception until after we uploaded the list.
        if not upload_passed:
            raise artifact_stages.DebugSymbolsUploadException(
                "Failed to upload all symbols."
            )

    def DetermineAndroidPackage(self):
        """Returns the active Android container package in use by the board.

        Workspace version of cbuildbot_run.DetermineAndroidPackage().

        Returns:
            String identifier for a package, or None
        """
        packages = portage_util.GetPackageDependencies(
            "virtual/target-os",
            board=self._current_board,
            buildroot=self._build_root,
            set_empty_root=not self.AfterLimit(PORTAGE_2_3_75_UPDATE),
        )

        android_packages = {
            p
            for p in packages
            if p.startswith("chromeos-base/android-container-")
            or p.startswith("chromeos-base/android-vm-")
        }

        assert len(android_packages) <= 1

        if android_packages:
            return next(iter(android_packages))
        else:
            return None

    def DetermineAndroidBranch(self, package):
        """Returns the Android branch in use by the active container ebuild.

        Workspace version of cbuildbot_run.DetermineAndroidBranch().

        Args:
            package: String name of Android package to get branch of.

        Returns:
            String with the android container branch name.
        """
        ebuild_path = portage_util.FindEbuildForBoardPackage(
            package, self._current_board, buildroot=self._build_root
        )
        host_ebuild_path = path_util.FromChrootPath(
            ebuild_path, source_path=self._build_root
        )
        # We assume all targets pull from the same branch and that we always
        # have at least one of the following targets.
        targets = android.GetAllAndroidEbuildTargets()
        ebuild_content = osutils.SourceEnvironment(host_ebuild_path, targets)
        logging.info("Got ebuild env: %s", ebuild_content)
        for target in targets:
            if target in ebuild_content:
                branch = re.search(r"(.*?)-linux-", ebuild_content[target])
                if branch is not None:
                    return branch.group(1)
        raise cbuildbot_run.NoAndroidBranchError(
            "Android branch could not be determined for %s (ebuild empty?)"
            % ebuild_path
        )

    def DetermineAndroidVersion(self, package):
        """Determine the current Android version in buildroot now and return it.

        This uses the typical portage logic to determine which version of
        Android is active right now in the buildroot.

        Workspace version of cbuildbot_run.DetermineAndroidVersion().

        Args:
            package: String name of Android package to get version of.

        Returns:
            The Android build ID of the container for the boards.
        """
        cpv = package_info.SplitCPV(package)
        return cpv.version_no_rev

    def DetermineAndroidABI(self):
        """Returns the Android ABI in use by the active container ebuild.

        Workspace version of cbuildbot_run.DetermineAndroidABI().

        Args:
            package: String name of Android package to get ABI version of.

        Returns:
            string defining ABI of the container.
        """
        use_flags = portage_util.GetInstalledPackageUseFlags(
            "sys-devel/arc-build",
            self._current_board,
            buildroot=self._build_root,
        )
        if "abi_x86_64" in use_flags.get("sys-devel/arc-build", []):
            return "x86_64"
        elif "abi_x86_32" in use_flags.get("sys-devel/arc-build", []):
            return "x86"
        else:
            # ARM only supports 32-bit so it does not have abi_x86_{32,64} set.
            # But it is also the last possible ABI, so returning by default.
            return "arm"

    def DetermineAndroidVariant(self, package):
        """Returns the Android variant in use by the active container ebuild."""

        all_use_flags = portage_util.GetInstalledPackageUseFlags(
            package, self._current_board, buildroot=self._build_root
        )
        for use_flags in all_use_flags.values():
            for use_flag in use_flags:
                if (
                    "cheets_userdebug" in use_flag
                    or "cheets_sdk_userdebug" in use_flag
                ):
                    return "userdebug"
                elif "cheets_user" in use_flag or "cheets_sdk_user" in use_flag:
                    return "user"

        # We iterated through all the flags and could not find user or
        # userdebug. This should not be possible given that this code is only
        # ran by builders, which will never use local images.
        raise cbuildbot_run.NoAndroidVariantError(
            "Android Variant cannot be determined for the packge: %s" % package
        )

    def DetermineAndroidTarget(self, package):
        if package.startswith("chromeos-base/android-vm-"):
            return "bertha"
        if package.startswith("chromeos-base/android-container-"):
            return "cheets"

        raise cbuildbot_run.NoAndroidTargetError(
            "Android Target cannot be determined for the package: %s" % package
        )

    def DownloadAndroidSymbols(self):
        """Helper to download android container symbols, as needed.

        Determines which, if any, Android container this build includes, and
        downloads it's symbols.

        Returns:
            path to downloaded symbols file, or None if not downloaded.
        """
        android_package = self.DetermineAndroidPackage()
        if not android_package:
            logging.info(
                "Android is not enabled on this board. Skipping symbols."
            )
            return None

        android_build_branch = self.DetermineAndroidBranch(android_package)
        android_version = self.DetermineAndroidVersion(android_package)
        arch = self.DetermineAndroidABI()
        variant = self.DetermineAndroidVariant(android_package)
        android_target = self.DetermineAndroidTarget(android_package)

        logging.info(
            "Downloading symbols of Android %s (%s)...",
            android_version,
            android_build_branch,
        )

        symbols_file_url = constants.ANDROID_SYMBOLS_URL_TEMPLATE % {
            "branch": android_build_branch,
            "target": android_target,
            "arch": arch,
            "version": android_version,
            "variant": variant,
        }

        # Should be based on self.archive_path, but we need a path inside
        # the workspace chroot, not infra chroot.
        symbols_file = os.path.join(
            self._build_root, "buildbot_archive", constants.ANDROID_SYMBOLS_FILE
        )
        gs_context = gs.GSContext()
        gs_context.Copy(symbols_file_url, symbols_file)

        return symbols_file
