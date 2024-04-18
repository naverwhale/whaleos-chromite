# Copyright 2013 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module containing the build stages."""

import base64
import glob
import logging
import os
from pathlib import Path

from chromite.cbuildbot import cbuildbot_alerts
from chromite.cbuildbot import commands
from chromite.cbuildbot import repository
from chromite.cbuildbot.stages import generic_stages
from chromite.lib import build_summary
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_sdk_lib
from chromite.lib import failures_lib
from chromite.lib import git
from chromite.lib import goma_lib
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib import path_util
from chromite.lib import portage_util
from chromite.lib.parser import package_info
from chromite.service import binhost as binhost_service


class CleanUpStage(generic_stages.BuilderStage):
    """Stages that cleans up build artifacts from previous runs.

    This stage cleans up previous KVM state, temporary git commits,
    clobbers, and wipes tmp inside the chroot.
    """

    option_name = "clean"
    category = constants.CI_INFRA_STAGE

    def _CleanChroot(self):
        logging.info("Cleaning chroot.")
        path_resolver = path_util.ChrootPathResolver(
            source_path=self._build_root
        )
        chroot_tmpdir = path_resolver.FromChroot("/tmp")
        if os.path.exists(chroot_tmpdir):
            osutils.RmDir(chroot_tmpdir, ignore_missing=True, sudo=True)
            cros_build_lib.sudo_run(
                ["mkdir", "--mode", "1777", chroot_tmpdir], print_cmd=False
            )

        # Clear out the incremental build cache between runs.
        cache_dir = "var/cache/portage"
        d = path_resolver.FromChroot(cache_dir)
        osutils.RmDir(d, ignore_missing=True, sudo=True)
        for board in self._boards:
            d = path_resolver.FromChroot(
                os.path.join(os.path.sep, "build", board, cache_dir)
            )
            osutils.RmDir(d, ignore_missing=True, sudo=True)

    def _DeleteChroot(self):
        logging.info("Deleting chroot.")
        chroot = chroot_lib.Chroot(
            path=self._build_root / Path(constants.DEFAULT_CHROOT_DIR),
            out_path=self._build_root / constants.DEFAULT_OUT_DIR,
        )
        if os.path.exists(chroot.path):
            # At this stage, it's not safe to run the cros_sdk inside the
            # buildroot itself because we haven't sync'd yet, and the version of
            # the chromite in there might be broken. Since we've already
            # unmounted everything in there, we can just remove it using rm -rf.
            cros_sdk_lib.CleanupChrootMount(chroot, delete=True)

    def _DeleteArchivedTrybotImages(self):
        """Clear all previous archive images to save space."""
        logging.info("Deleting archived trybot images.")
        for trybot in (False, True):
            archive_root = self._run.GetArchive().GetLocalArchiveRoot(
                trybot=trybot
            )
            osutils.RmDir(archive_root, ignore_missing=True)

    def _DeleteChromeBuildOutput(self):
        logging.info("Deleting Chrome build output.")
        chrome_src = os.path.join(self._run.options.chrome_root, "src")
        for out_dir in glob.glob(os.path.join(chrome_src, "out_*")):
            osutils.RmDir(out_dir)

    def _BuildRootGitCleanup(self):
        logging.info("Cleaning up buildroot git repositories.")
        # Run git gc --auto --prune=all on all repos in CleanUpStage
        repo = self.GetRepoRepository()
        repo.BuildRootGitCleanup(prune_all=True)

    def _DeleteAutotestSitePackages(self):
        """Clears any previously downloaded site-packages."""
        logging.info("Deleting autotest site packages.")
        site_packages_dir = os.path.join(
            self._build_root,
            "src",
            "third_party",
            "autotest",
            "files",
            "site-packages",
        )
        # Note that these shouldn't be recreated but might be around from stale
        # builders.
        osutils.RmDir(site_packages_dir, ignore_missing=True)

    def _WipeOldOutput(self):
        logging.info("Wiping old output.")
        commands.WipeOldOutput(self._build_root)

    def _CleanWorkspace(self):
        logging.info("Cleaning up workspace checkout.")
        assert self._run.options.workspace
        workspace = self._run.options.workspace

        logging.info("Remove Chroot.")
        chroot = chroot_lib.Chroot(
            path=workspace / Path(constants.DEFAULT_CHROOT_DIR),
            out_path=workspace / constants.DEFAULT_OUT_DIR,
        )
        if os.path.exists(chroot.path):
            cros_sdk_lib.CleanupChrootMount(chroot, delete=True)

        logging.info("Remove all workspace files except .repo.")
        repository.ClearBuildRoot(workspace, [".repo"])

    def _GetPreviousBuildStatus(self):
        """Extract the status of the previous build from command-line arguments.

        Returns:
            A BuildSummary object representing the previous build.
        """
        previous_state = build_summary.BuildSummary()
        if self._run.options.previous_build_state:
            try:
                state_json = base64.b64decode(
                    self._run.options.previous_build_state
                )
                previous_state.from_json(state_json)
                logging.info(
                    "Previous local build %s finished in state %s.",
                    previous_state.build_description(),
                    previous_state.status,
                )
            except ValueError as e:
                logging.error("Failed to decode previous build state: %s", e)
        return previous_state

    def _GetPreviousMasterStatus(self, previous_state):
        """Get the state of the previous master build from CIDB.

        Args:
            previous_state: A BuildSummary object representing the previous
                build.

        Returns:
            A tuple containing the master build number and status, or None, None
            if there isn't one.
        """
        if not previous_state.master_build_id:
            return None, None

        if not self.buildstore.AreClientsReady():
            return None, None

        status_list = self.buildstore.GetBuildStatuses(
            build_ids=[previous_state.master_build_id]
        )
        master_status = status_list[0] if status_list else None
        if not master_status:
            logging.warning(
                "Previous master build id %s not found.",
                previous_state.master_build_id,
            )
            return None, None
        logging.info(
            "Previous master build %s finished in state %s",
            master_status["build_number"],
            master_status["status"],
        )

        return master_status["build_number"], master_status["status"]

    def CanReuseChroot(self):
        """Determine if the chroot can be reused.

        A chroot can be reused if all of the following are true:
            1.  The build config doesn't request chroot_replace.
            2.  The previous local build succeeded.
            3.  If there was a previous master build, that build also succeeded.

        Returns:
            True if the chroot can be reused, False if not.
        """

        if self._run.config.chroot_replace and self._run.options.build:
            logging.info(
                "Build config has chroot_replace=True. Cannot reuse chroot."
            )
            return False

        previous_state = self._GetPreviousBuildStatus()
        if previous_state.status != constants.BUILDER_STATUS_PASSED:
            logging.info(
                "Previous local build %s did not pass. Cannot reuse chroot.",
                previous_state.build_number,
            )
            return False

        if previous_state.master_build_id:
            build_number, status = self._GetPreviousMasterStatus(previous_state)
            if status != constants.BUILDER_STATUS_PASSED:
                logging.info(
                    "Previous master build %s did not pass (%s).  "
                    "Cannot reuse chroot.",
                    build_number,
                    status,
                )
                return False

        return True

    @failures_lib.SetFailureType(failures_lib.InfrastructureFailure)
    def PerformStage(self):
        if (
            not (self._run.options.buildbot or self._run.options.remote_trybot)
            and self._run.options.clobber
        ):
            if not commands.ValidateClobber(self._build_root):
                cros_build_lib.Die("--clobber in local mode must be approved.")

        # If we can't get a manifest out of it, then it's not usable and must be
        # clobbered.
        manifest = None
        delete_chroot = False
        if not self._run.options.clobber:
            try:
                manifest = git.ManifestCheckout.Cached(
                    self._build_root, search=False
                )
            except (KeyboardInterrupt, MemoryError, SystemExit):
                raise
            except Exception as e:
                # Either there is no repo there, or the manifest isn't usable.
                # If the directory exists, log the exception for debugging
                # reasons.  Either way, the checkout needs to be wiped since
                # it's in an unknown state.
                if os.path.exists(self._build_root):
                    logging.warning(
                        "ManifestCheckout at %s is unusable: %s",
                        self._build_root,
                        e,
                    )
                delete_chroot = True

        # Clean mount points first to be safe about deleting.
        chroot = chroot_lib.Chroot(
            path=self._build_root / Path(constants.DEFAULT_CHROOT_DIR),
            out_path=self._build_root / constants.DEFAULT_OUT_DIR,
        )
        cros_sdk_lib.CleanupChrootMount(chroot=chroot)
        logging.info("Build root path: %s", self._build_root)
        if not os.path.ismount(self._build_root):
            osutils.UmountTree(self._build_root)

        if not delete_chroot:
            delete_chroot = not self.CanReuseChroot()

        if manifest is None:
            self._DeleteChroot()
            repository.ClearBuildRoot(
                self._build_root, self._run.options.preserve_paths
            )
        else:
            tasks = [
                self._WipeOldOutput,
                self._DeleteArchivedTrybotImages,
                self._DeleteAutotestSitePackages,
            ]
            if not os.path.ismount(self._build_root):
                tasks.insert(0, self._BuildRootGitCleanup)
            if self._run.options.chrome_root:
                tasks.append(self._DeleteChromeBuildOutput)
            if delete_chroot:
                tasks.append(self._DeleteChroot)
            else:
                tasks.append(self._CleanChroot)
            if self._run.options.workspace:
                tasks.append(self._CleanWorkspace)

            parallel.RunParallelSteps(tasks)


class InitSDKStage(generic_stages.BuilderStage):
    """Stage that is responsible for initializing the SDK."""

    option_name = "build"
    category = constants.CI_INFRA_STAGE

    def __init__(self, builder_run, buildstore, chroot_replace=False, **kwargs):
        """InitSDK constructor.

        Args:
            builder_run: Builder run instance for this run.
            buildstore: BuildStore instance to make DB calls with.
            chroot_replace: If True, force the chroot to be replaced.
        """
        super().__init__(builder_run, buildstore, **kwargs)
        self.force_chroot_replace = chroot_replace

    def PerformStage(self):
        chroot_path = os.path.join(
            self._build_root, constants.DEFAULT_CHROOT_DIR
        )
        chroot_exists = os.path.isdir(self._build_root)
        replace = self._run.config.chroot_replace or self.force_chroot_replace
        pre_ver = None

        if chroot_exists and not replace:
            # Make sure the chroot has a valid version before we update it.
            pre_ver = cros_sdk_lib.GetChrootVersion(chroot_path)
            if pre_ver is None:
                cbuildbot_alerts.PrintBuildbotStepText(
                    "Replacing broken chroot"
                )
                cbuildbot_alerts.PrintBuildbotStepWarnings()
                replace = True

        if not chroot_exists or replace:
            use_sdk = self._run.config.use_sdk and not self._run.options.nosdk
            pre_ver = None
            commands.MakeChroot(
                buildroot=self._build_root,
                replace=replace,
                use_sdk=use_sdk,
                chrome_root=self._run.options.chrome_root,
                extra_env=self._portage_extra_env,
                cache_dir=self._run.options.cache_dir,
            )

        post_ver = cros_sdk_lib.GetChrootVersion(chroot_path)
        if pre_ver is not None and pre_ver != post_ver:
            cbuildbot_alerts.PrintBuildbotStepText(
                "%s->%s" % (pre_ver, post_ver)
            )
        else:
            cbuildbot_alerts.PrintBuildbotStepText(post_ver)


class UpdateSDKStage(generic_stages.BuilderStage):
    """Stage that is responsible for updating the chroot."""

    option_name = "build"
    category = constants.CI_INFRA_STAGE

    def PerformStage(self):
        """Do the work of updating the chroot."""
        # Ensure we don't run on SDK builder. https://crbug.com/225509
        assert self._run.config.build_type != constants.CHROOT_BUILDER_TYPE

        chroot_args = None
        if self._run.options.cache_dir:
            chroot_args = ["--cache-dir", self._run.options.cache_dir]

        commands.UpdateChroot(
            self._build_root,
            usepkg=not self._latest_toolchain,
            extra_env=self._portage_extra_env,
            chroot_args=chroot_args,
        )


class SetupBoardStage(generic_stages.BoardSpecificBuilderStage, InitSDKStage):
    """Stage responsible for building host pkgs and setting up a board."""

    option_name = "build"
    category = constants.CI_INFRA_STAGE

    def PerformStage(self):
        chroot_args = None
        if self._run.options.cache_dir:
            chroot_args = ["--cache-dir", self._run.options.cache_dir]

        # Ensure we don't run on SDK builder. https://crbug.com/225509
        if self._run.config.build_type != constants.CHROOT_BUILDER_TYPE:
            # Setup board's toolchain.
            commands.SetupToolchains(
                self._build_root,
                usepkg=not self._latest_toolchain,
                targets="boards",
                boards=self._current_board,
                chroot_args=chroot_args,
            )

        # Update the board.
        usepkg = self._run.config.usepkg_build_packages

        commands.SetupBoard(
            self._build_root,
            board=self._current_board,
            usepkg=usepkg,
            force=self._run.config.board_replace,
            extra_env=self._portage_extra_env,
            chroot_upgrade=False,
            profile=self._run.options.profile or self._run.config.profile,
            chroot_args=chroot_args,
        )


class BuildPackagesStage(
    generic_stages.BoardSpecificBuilderStage, generic_stages.ArchivingStageMixin
):
    """Build Chromium OS packages."""

    category = constants.PRODUCT_OS_STAGE
    option_name = "build"
    config_name = "build_packages"

    def __init__(
        self,
        builder_run,
        buildstore,
        board,
        suffix=None,
        afdo_use=False,
        update_metadata=False,
        record_packages_under_test=True,
        **kwargs,
    ):
        if not afdo_use:
            suffix = self.UpdateSuffix("-" + constants.USE_AFDO_USE, suffix)
        super().__init__(
            builder_run, buildstore, board, suffix=suffix, **kwargs
        )
        self._update_metadata = update_metadata
        self._record_packages_under_test = record_packages_under_test

        useflags = self._portage_extra_env.get("USE", "").split()
        if not afdo_use:
            useflags.append("-" + constants.USE_AFDO_USE)

        if useflags:
            self._portage_extra_env["USE"] = " ".join(useflags)

    def VerifyChromeBinpkg(self, packages):
        # Sanity check: If we didn't check out Chrome (and we're running on
        # ToT), we should be building Chrome from a binary package.
        if (
            not self._run.options.managed_chrome
            and self._run.manifest_branch in ("main", "master")
        ):
            commands.VerifyBinpkg(
                self._build_root,
                self._current_board,
                constants.CHROME_CP,
                packages,
                extra_env=self._portage_extra_env,
            )

    def RecordPackagesUnderTest(self):
        """Records all packages that may affect the board to BuilderRun."""
        packages = set()
        deps = commands.ExtractBuildDepsGraph(
            self._build_root, self._current_board
        )
        for package_dep in deps["packageDeps"]:
            info = package_dep["packageInfo"]
            packages.add(
                "%s/%s-%s"
                % (info["category"], info["packageName"], info["version"])
            )

        logging.info("Sucessfully extract packages under test")
        self.board_runattrs.SetParallel("packages_under_test", packages)

    def _IsGomaEnabledOnlyForLogs(self):
        # HACK: our ninja log uploading bits for Chromium are pretty closely
        # tied to goma's logging bits. In latest-toolchain builds, these logs
        # are useful, but actually using goma isn't, since it just does local
        # fallbacks.
        return self._latest_toolchain

    def _ShouldEnableGoma(self):
        # Enable goma if 1) chrome actually needs to be built, or we want to use
        # goma to build regular packages 2) not latest_toolchain (because
        # toolchain prebuilt package may not be available for goma,
        # crbug.com/728971) and 3) goma is available.
        return self._run.options.managed_chrome and self._run.options.goma_dir

    def _SetupGomaIfNecessary(self):
        """Sets up goma envs if necessary.

        Updates related env vars, and returns args to chroot.

        Returns:
            args which should be provided to chroot in order to enable goma.
            If goma is unusable or disabled, None is returned.
        """
        if not self._ShouldEnableGoma():
            return None

        # TODO(crbug.com/751010): Revisit to enable DepsCache for non-chrome-pfq
        # bots, too.
        use_goma_deps_cache = self._run.config.name.endswith("chrome-pfq")
        goma_approach = goma_lib.GomaApproach(
            "?cros", "goma.chromium.org", True
        )
        goma = goma_lib.Goma(
            self._run.options.goma_dir,
            stage_name=self.StageNamePrefix() if use_goma_deps_cache else None,
            chromeos_goma_dir=self._run.options.chromeos_goma_dir,
            chroot_dir=self._build_root / Path(constants.DEFAULT_CHROOT_DIR),
            out_dir=self._build_root / Path(constants.DEFAULT_OUT_DIR),
            goma_approach=goma_approach,
        )

        # Set USE_GOMA env var so that chrome is built with goma.
        if not self._IsGomaEnabledOnlyForLogs():
            self._portage_extra_env["USE_GOMA"] = "true"
        self._portage_extra_env.update(goma.GetChrootExtraEnv())

        # Keep GOMA_TMP_DIR for Report stage to upload logs.
        self._run.attrs.metadata.UpdateWithDict(
            {"goma_tmp_dir": str(goma.goma_tmp_dir)}
        )

        # Mount goma directory and service account json file (if necessary)
        # into chroot.
        chroot_args = ["--goma_dir", str(goma.chromeos_goma_dir)]
        return chroot_args

    def PerformStage(self):
        packages = self.GetListOfPackagesToBuild()
        self.VerifyChromeBinpkg(packages)
        if self._record_packages_under_test:
            self.RecordPackagesUnderTest()

        # Set up goma. Use goma iff chrome needs to be built.
        chroot_args = self._SetupGomaIfNecessary()
        run_goma = bool(chroot_args)
        if self._run.options.cache_dir:
            chroot_args = chroot_args or []
            chroot_args += ["--cache-dir", self._run.options.cache_dir]

        # Disable revdep logic on full and release builders. These builders
        # never reuse sysroots, so the revdep logic only causes unnecessary
        # rebuilds in the SDK. The SDK rebuilds sometimes hit build critical
        # packages causing races & build failures.
        clean_build = (
            # TODO(b/236161656): Fix.
            # pylint: disable-next=consider-using-in
            self._run.config.build_type == constants.CANARY_TYPE
            or self._run.config.build_type == constants.FULL_TYPE
        )

        # Set property to specify bisection builder job to run for Findit.
        cbuildbot_alerts.PrintKitchenSetBuildProperty(
            "BISECT_BUILDER", self._current_board + "-postsubmit-tryjob"
        )
        try:
            commands.Build(
                self._build_root,
                self._current_board,
                build_autotest=self._run.ShouldBuildAutotest(),
                usepkg=self._run.config.usepkg_build_packages,
                packages=packages,
                skip_chroot_upgrade=True,
                chrome_root=self._run.options.chrome_root,
                noretry=self._run.config.nobuildretry,
                chroot_args=chroot_args,
                extra_env=self._portage_extra_env,
                run_goma=run_goma,
                disable_revdep_logic=clean_build,
            )
        except failures_lib.PackageBuildFailure as ex:
            failure_json = ex.BuildCompileFailureOutputJson()
            failures_filename = os.path.join(
                self.archive_path, "BuildCompileFailureOutput.json"
            )
            osutils.WriteFile(failures_filename, failure_json)
            self.UploadArtifact(
                os.path.basename(failures_filename), archive=False
            )
            self.PrintDownloadLink(
                os.path.basename(failures_filename),
                text_to_display="BuildCompileFailureOutput",
            )
            gs_url = os.path.join(
                self.upload_url, "BuildCompileFailureOutput.json"
            )
            cbuildbot_alerts.PrintKitchenSetBuildProperty(
                "BuildCompileFailureOutput", gs_url
            )
            raise

        if self._update_metadata:
            # Extract firmware version information from the newly created
            # updater.
            fw_versions = commands.GetFirmwareVersions(
                self._build_root, self._current_board
            )
            main = fw_versions.main_rw or fw_versions.main
            ec = fw_versions.ec_rw or fw_versions.ec
            update_dict = {
                "main-firmware-version": main,
                "ec-firmware-version": ec,
            }
            self._run.attrs.metadata.UpdateBoardDictWithDict(
                self._current_board, update_dict
            )

            # Write board metadata update to cidb
            build_identifier, _ = self._run.GetCIDBHandle()
            build_id = build_identifier.cidb_id
            if self.buildstore.AreClientsReady():
                self.buildstore.InsertBoardPerBuild(
                    build_id, self._current_board, update_dict
                )

            # Get a list of models supported by this board.
            models = commands.GetModels(
                self._build_root, self._current_board, log_output=False
            )
            self._run.attrs.metadata.UpdateWithDict({"unibuild": bool(models)})
            if models:
                all_fw_versions = commands.GetAllFirmwareVersions(
                    self._build_root, self._current_board
                )
                models_data = {}
                for model in models:
                    if model in all_fw_versions:
                        fw_versions = all_fw_versions[model]

                        ec = fw_versions.ec_rw or fw_versions.ec
                        main_ro = fw_versions.main
                        main_rw = fw_versions.main_rw or main_ro

                        # Get the firmware key-id for the current board and
                        # model.
                        model_arg = "--model=" + model
                        key_id_list = commands.RunCrosConfigHost(
                            self._build_root,
                            self._current_board,
                            [model_arg, "get", "/firmware-signing", "key-id"],
                        )
                        key_id = None
                        if len(key_id_list) == 1:
                            key_id = key_id_list[0]

                        models_data[model] = {
                            "main-readonly-firmware-version": main_ro,
                            "main-readwrite-firmware-version": main_rw,
                            "ec-firmware-version": ec,
                            "firmware-key-id": key_id,
                        }
                if models_data:
                    self._run.attrs.metadata.UpdateBoardDictWithDict(
                        self._current_board, {"models": models_data}
                    )


class BuildImageStage(BuildPackagesStage):
    """Build standard Chromium OS images."""

    option_name = "build"
    config_name = "images"
    category = constants.PRODUCT_OS_STAGE

    def _BuildImages(self):
        # We only build base, dev, and test images from this stage.
        images_can_build = set(["base", "dev", "test"])
        images_to_build = set(self._run.config.images).intersection(
            images_can_build
        )

        version = self._run.attrs.release_tag

        rootfs_verification = self._run.config.rootfs_verification
        builder_path = "/".join([self._bot_id, self.version])

        chroot_args = None
        if self._run.options.cache_dir:
            chroot_args = ["--cache-dir", self._run.options.cache_dir]

        commands.BuildImage(
            self._build_root,
            self._current_board,
            sorted(images_to_build),
            rootfs_verification=rootfs_verification,
            version=version,
            builder_path=builder_path,
            extra_env=self._portage_extra_env,
            chroot_args=chroot_args,
        )

        # Update link to latest image.
        latest_image = os.readlink(self.GetImageDirSymlink("latest"))
        cbuildbot_image_link = self.GetImageDirSymlink()
        if os.path.lexists(cbuildbot_image_link):
            os.remove(cbuildbot_image_link)

        os.symlink(latest_image, cbuildbot_image_link)

        self.board_runattrs.SetParallel("images_generated", True)

    def _UpdateBuildImageMetadata(self):
        """Update the new metadata available to the build image stage."""
        update = {}
        fingerprints = self._FindFingerprints()
        if fingerprints:
            update["fingerprints"] = fingerprints
        kernel_version = self._FindKernelVersion()
        if kernel_version:
            update["kernel-version"] = kernel_version
        self._run.attrs.metadata.UpdateBoardDictWithDict(
            self._current_board, update
        )

    def _FindFingerprints(self):
        """Returns a list of build fingerprints for this build."""
        fp_file = "cheets-fingerprint.txt"
        fp_path = os.path.join(self.GetImageDirSymlink("latest"), fp_file)
        if not os.path.isfile(fp_path):
            return None
        fingerprints = osutils.ReadFile(fp_path).splitlines()
        logging.info("Found build fingerprint(s): %s", fingerprints)
        return fingerprints

    def _FindKernelVersion(self):
        """Returns a string containing the kernel version for this build."""
        try:
            packages = portage_util.GetPackageDependencies(
                "virtual/linux-sources", board=self._current_board
            )
        except cros_build_lib.RunCommandError:
            logging.warning("Unable to get package list for metadata.")
            return None
        for package in packages:
            if package.startswith("sys-kernel/chromeos-kernel-"):
                kernel_version = package_info.parse(package).vr
                logging.info("Found active kernel version: %s", kernel_version)
                return kernel_version
        return None

    def _HandleStageException(self, exc_info):
        """Tell other stages to not wait on us if we die for some reason."""
        self.board_runattrs.SetParallelDefault("images_generated", False)
        return super()._HandleStageException(exc_info)

    def PerformStage(self):
        self._BuildImages()
        self._UpdateBuildImageMetadata()


class UprevStage(generic_stages.BuilderStage):
    """Uprevs Chromium OS packages that the builder intends to validate."""

    config_name = "uprev"
    option_name = "uprev"
    category = constants.CI_INFRA_STAGE

    def __init__(self, builder_run, buildstore, boards=None, **kwargs):
        super().__init__(builder_run, buildstore, **kwargs)
        if boards is not None:
            self._boards = boards

    def PerformStage(self):
        # Perform other uprevs.
        commands.UprevPackages(
            self._build_root,
            self._boards,
            overlay_type=self._run.config.overlays,
        )


class RegenPortageCacheStage(generic_stages.BuilderStage):
    """Regenerates the Portage ebuild cache."""

    # We only need to run this if we're pushing at least one overlay.
    config_name = "push_overlays"
    category = constants.CI_INFRA_STAGE

    def PerformStage(self):
        chroot = chroot_lib.Chroot(
            path=self._build_root / Path(constants.DEFAULT_CHROOT_DIR),
            out_path=self._build_root / constants.DEFAULT_OUT_DIR,
        )
        binhost_service.RegenBuildCache(
            chroot,
            self._run.config.push_overlays,
            buildroot=self._build_root,
        )
