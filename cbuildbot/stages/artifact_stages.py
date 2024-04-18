# Copyright 2013 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module containing stages that generate and/or archive artifacts."""

import glob
import itertools
import json
import logging
import multiprocessing
import os
import shutil

from chromite.cbuildbot import commands
from chromite.cbuildbot import prebuilts
from chromite.cbuildbot.stages import generic_stages
from chromite.lib import config_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import failures_lib
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib import path_util
from chromite.lib import portage_util
from chromite.utils import pformat


_FULL_BINHOST = "FULL_BINHOST"
_PORTAGE_BINHOST = "PORTAGE_BINHOST"


class DebugSymbolsUploadException(Exception):
    """Thrown if DebugSymbols fails during upload."""


class NothingToArchiveException(Exception):
    """Thrown if ArchiveStage found nothing to archive."""

    # We duplicate __init__ to specify a default for message.
    # pylint: disable=useless-super-delegation
    def __init__(self, message="No images found to archive."):
        super().__init__(message)


class ArchiveStage(
    generic_stages.BoardSpecificBuilderStage, generic_stages.ArchivingStageMixin
):
    """Archives build and test artifacts for developer consumption.

    Attributes:
        release_tag: The release tag. E.g. 2981.0.0
        version: The full version string, including the milestone. E.g.
            R26-2981.0.0-b123
    """

    option_name = "archive"
    config_name = "archive"
    category = constants.CI_INFRA_STAGE

    # This stage is intended to run in the background, in parallel with tests.
    def __init__(
        self, builder_run, buildstore, board, chrome_version=None, **kwargs
    ):
        super().__init__(builder_run, buildstore, board, **kwargs)
        self.chrome_version = chrome_version

        # TODO(mtennant): Places that use this release_tag attribute should
        # move to use self._run.attrs.release_tag directly.
        self.release_tag = getattr(self._run.attrs, "release_tag", None)

        self._release_upload_queue = multiprocessing.Queue()
        self._upload_queue = multiprocessing.Queue()
        self.artifacts = []

    def ArchiveStrippedPackages(self):
        """Generate and archive stripped versions of packages requested."""
        tarball = commands.BuildStrippedPackagesTarball(
            self._build_root,
            self._current_board,
            self._run.config.upload_stripped_packages,
            self.archive_path,
        )
        if tarball is not None:
            self._upload_queue.put([tarball])

    def LoadArtifactsList(self, board, image_dir):
        """Load the list of artifacts to upload for this board.

        It attempts to load a JSON file, scripts/artifacts.json, from the
        overlay directories for this board. This file specifies the artifacts
        to generate, if it can't be found, it will use a default set that
        uploads every .bin file as a .tar.xz file.

        See BuildStandaloneArchive in cbuildbot_commands.py for format docs.
        """
        custom_artifacts_file = portage_util.ReadOverlayFile(
            "scripts/artifacts.json", board=board
        )
        artifacts = None

        if custom_artifacts_file is not None:
            json_file = json.loads(custom_artifacts_file)
            artifacts = json_file.get("artifacts")

        if artifacts is None:
            artifacts = []
            for image_file in glob.glob(os.path.join(image_dir, "*.bin")):
                basename = os.path.basename(image_file)
                info = {"input": [basename], "archive": "tar", "compress": "xz"}
                artifacts.append(info)
            # We add the dlc folder (if exists) as artifact so we can copy all
            # DLC artifacts as is.
            if os.path.isdir(os.path.join(image_dir, "dlc")):
                artifacts.append({"input": ["dlc"]})

        for artifact in artifacts:
            # Resolve the (possible) globs in the input list, and store
            # the actual set of files to use in 'paths'
            paths = []
            for s in artifact["input"]:
                glob_paths = glob.glob(os.path.join(image_dir, s))
                if not glob_paths:
                    logging.warning("No artifacts generated for input: %s", s)
                else:
                    for path in glob_paths:
                        paths.append(os.path.relpath(path, image_dir))
            artifact["paths"] = paths
        self.artifacts = artifacts

    def IsArchivedFile(self, filename):
        """Return True if filename is the name of a file being archived."""
        for artifact in self.artifacts:
            for path in itertools.chain(artifact["paths"], artifact["input"]):
                if os.path.basename(path) == filename:
                    return True
        return False

    def PerformStage(self):
        buildroot = self._build_root
        config = self._run.config
        board = self._current_board
        debug = self._run.options.debug_forced
        upload_url = self.upload_url
        archive_path = self.archive_path
        image_dir = self.GetImageDirSymlink()

        extra_env = {}
        if config["useflags"]:
            extra_env["USE"] = " ".join(config["useflags"])

        if not archive_path:
            raise NothingToArchiveException()

        # The following functions are run in parallel (except where indicated
        # otherwise)
        # \- BuildAndArchiveArtifacts
        #    \- ArchiveReleaseArtifacts
        #       \- ArchiveFirmwareImages
        #       \- BuildAndArchiveAllImages
        #          (builds recovery image first, then launches functions below)
        #          \- BuildAndArchiveFactoryImages
        #          \- ArchiveStandaloneArtifacts
        #             \- ArchiveStandaloneArtifact
        #          \- ArchiveZipFiles
        #          \- ArchiveLicenseFile
        #       \- PushImage (blocks on BuildAndArchiveAllImages)
        #    \- ArchiveManifest
        #    \- ArchiveStrippedPackages
        #    \- ArchiveImageScripts
        #    \- ArchiveEbuildLogs

        def ArchiveManifest():
            """Create manifest.xml snapshot of the built code."""
            output_manifest = os.path.join(archive_path, "manifest.xml")
            cmd = ["repo", "manifest", "-r", "-o", output_manifest]
            cros_build_lib.run(cmd, cwd=buildroot, capture_output=True)
            self._upload_queue.put(["manifest.xml"])

        def BuildAndArchiveFactoryImages():
            """Build and archive the factory zip file.

            The factory zip file consists of the factory toolkit and the factory
            install image. Both are built here.
            """
            # Build factory install image and create a symlink to it.
            factory_install_symlink = None
            if "factory_install" in config["images"]:
                logging.info("Running commands.BuildFactoryInstallImage")
                alias = commands.BuildFactoryInstallImage(
                    buildroot, board, extra_env
                )
                factory_install_symlink = self.GetImageDirSymlink(alias)
                if config["factory_install_netboot"]:
                    logging.info("Running commands.MakeNetboot")
                    commands.MakeNetboot(
                        buildroot, board, factory_install_symlink
                    )

            # Build and upload factory zip if needed.
            if factory_install_symlink or config["factory_toolkit"]:
                logging.info("Running commands.BuildFactoryZip")
                filename = commands.BuildFactoryZip(
                    buildroot,
                    board,
                    archive_path,
                    factory_install_symlink,
                    self._run.attrs.release_tag,
                )
                self._release_upload_queue.put([filename])

            # Upload project toolkits tarball if needed.
            toolkits_src_path = os.path.join(
                path_util.FromChrootPath(
                    commands.FACTORY_PACKAGE_CHROOT_PATH % {"board": board},
                    source_path=buildroot,
                ),
                "project_toolkits",
                commands.FACTORY_PROJECT_PACKAGE,
            )
            if os.path.exists(toolkits_src_path):
                shutil.copy(toolkits_src_path, archive_path)
                self._release_upload_queue.put(
                    [commands.FACTORY_PROJECT_PACKAGE]
                )

        def ArchiveStandaloneArtifact(artifact_info):
            """Build and upload a single archive."""
            if artifact_info["paths"]:
                logging.info("Running commands.BuildStandaloneArchive")
                for path in commands.BuildStandaloneArchive(
                    archive_path, image_dir, artifact_info
                ):
                    self._release_upload_queue.put([path])

        def ArchiveStandaloneArtifacts():
            """Build and upload standalone archives for each image."""
            if config["upload_standalone_images"]:
                parallel.RunTasksInProcessPool(
                    ArchiveStandaloneArtifact, [[x] for x in self.artifacts]
                )

        def ArchiveEbuildLogs():
            """Tar and archive Ebuild logs.

            This includes all the files in /build/$BOARD/tmp/portage/logs.
            """
            logging.info("Running commands.BuildEbuildLogsTarball")
            tarpath = commands.BuildEbuildLogsTarball(
                self._build_root, self._current_board, self.archive_path
            )
            if tarpath is not None:
                self._upload_queue.put([tarpath])

        def ArchiveZipFiles():
            """Build and archive zip files.

            This includes:
              - image.zip (all images in one big zip file)
            """
            # Zip up everything in the image directory.
            logging.info("Running commands.BuildImageZip")
            image_zip = commands.BuildImageZip(archive_path, image_dir)
            self._release_upload_queue.put([image_zip])

        def ArchiveLicenseFile():
            """Archive licensing file."""
            filename = "license_credits.html"
            filepath = os.path.join(image_dir, filename)
            if os.path.isfile(filepath):
                shutil.copy(filepath, archive_path)
                self._release_upload_queue.put([filename])

        def ArchiveFirmwareImages():
            """Archive firmware images built from source if available."""
            logging.info("Running commands.BuildFirmwareArchive")
            archive = commands.BuildFirmwareArchive(
                buildroot, board, archive_path
            )
            if archive:
                self._release_upload_queue.put([archive])

        def BuildAndArchiveAllImages():
            # Generate the recovery image. To conserve loop devices, we try to
            # only run one instance of build_image at a time. TODO(davidjames):
            # Move the image generation out of the archive stage.
            self.LoadArtifactsList(self._current_board, image_dir)

            # For recovery image to be generated correctly, BuildRecoveryImage
            # must run before BuildAndArchiveFactoryImages.
            if "recovery" in config.images:
                base_image_path = os.path.join(
                    image_dir, constants.BASE_IMAGE_BIN
                )
                assert os.path.isfile(base_image_path)
                logging.info("Running commands.BuildRecoveryImage")
                commands.BuildRecoveryImage(
                    buildroot, board, image_dir, extra_env
                )
                recovery_image = constants.RECOVERY_IMAGE_BIN
                if not self.IsArchivedFile(recovery_image):
                    info = {
                        "paths": [recovery_image],
                        "input": [recovery_image],
                        "archive": "tar",
                        "compress": "xz",
                    }
                    self.artifacts.append(info)

            if config["images"]:
                if self._run.HasUseFlag(board, "no_factory_flow"):
                    steps = []
                else:
                    steps = [BuildAndArchiveFactoryImages]
                steps += [
                    ArchiveLicenseFile,
                    ArchiveStandaloneArtifacts,
                    ArchiveZipFiles,
                ]
                parallel.RunParallelSteps(steps)

        def ArchiveImageScripts():
            """Archive tarball of generated image manipulation scripts."""
            tarball_path = os.path.join(
                archive_path, constants.IMAGE_SCRIPTS_TAR
            )
            files = glob.glob(os.path.join(image_dir, "*.sh"))
            files = [os.path.basename(f) for f in files]
            cros_build_lib.CreateTarball(tarball_path, image_dir, inputs=files)
            self._upload_queue.put([constants.IMAGE_SCRIPTS_TAR])

        def PushImage():
            # This helper script is only available on internal manifests
            # currently.
            if not config["internal"]:
                return

            self.GetParallel(
                "debug_tarball_generated", pretty_name="debug tarball"
            )

            # Needed for stateful.tgz
            self.GetParallel(
                "test_artifacts_uploaded", pretty_name="test artifacts"
            )

            # Now that all data has been generated, we can upload the final
            # result to the image server. TODO: When we support branches fully,
            # the friendly name of the branch needs to be used with PushImages
            sign_types = []
            if config["sign_types"]:
                sign_types = config["sign_types"]
            logging.info("Running commands.PushImages")
            urls = commands.PushImages(
                board=board,
                archive_url=upload_url,
                dryrun=debug or not config["push_image"],
                profile=self._run.options.profile or config["profile"],
                sign_types=sign_types,
            )
            self.board_runattrs.SetParallel(
                "instruction_urls_per_channel", urls
            )

        def ArchiveReleaseArtifacts():
            with self.ArtifactUploader(
                self._release_upload_queue, archive=False
            ):
                steps = [BuildAndArchiveAllImages, ArchiveFirmwareImages]
                parallel.RunParallelSteps(steps)
            PushImage()

        def BuildAndArchiveArtifacts():
            # Run archiving steps in parallel.
            steps = [
                ArchiveReleaseArtifacts,
                ArchiveManifest,
                self.ArchiveStrippedPackages,
                ArchiveEbuildLogs,
            ]
            if config["images"]:
                steps.append(ArchiveImageScripts)

            with self.ArtifactUploader(self._upload_queue, archive=False):
                parallel.RunParallelSteps(steps)

            # Make sure no stage posted to the release queue when it should have
            # used the normal upload queue.  The release queue is processed in
            # parallel and then ignored, so there shouldn't be any items left in
            # here.
            assert self._release_upload_queue.empty()

        BuildAndArchiveArtifacts()

    def _HandleStageException(self, exc_info):
        # Tell the HWTestStage not to wait for artifacts to be uploaded
        # in case ArchiveStage throws an exception.
        self.board_runattrs.SetParallel("instruction_urls_per_channel", None)
        return super()._HandleStageException(exc_info)


class BuildConfigsExportStage(
    generic_stages.BoardSpecificBuilderStage, generic_stages.ArchivingStageMixin
):
    """Handles generation & upload of build related configs.

    NOTES: this is an ephemeral stage just to gather build config data for
      crbug.com/974795 and will be removed once that project finished.
    """

    config_name = "run_build_configs_export"
    category = constants.CI_INFRA_STAGE

    @failures_lib.SetFailureType(failures_lib.InfrastructureFailure)
    def PerformStage(self):
        """Generate and upload build configs.

        The build config includes config.yaml (for unibuild) and USE flags.
        """
        board = self._current_board
        config_useflags = self._run.config.useflags

        logging.info("Generating build configs.")
        results = commands.GenerateBuildConfigs(board, config_useflags)

        results_str = pformat.json(results)
        logging.info("Results:\n%s", results_str)

        logging.info("Writing build configs to files for archive.")
        results_filename = os.path.join(
            self.archive_path, "chromeos-build-configs-%s.json" % board
        )

        osutils.WriteFile(results_filename, results_str)

        logging.info("Uploading build config files.")
        self.UploadArtifact(os.path.basename(results_filename), archive=False)


class DebugSymbolsStage(
    generic_stages.BoardSpecificBuilderStage, generic_stages.ArchivingStageMixin
):
    """Handles generation & upload of debug symbols."""

    config_name = "debug_symbols"
    category = constants.PRODUCT_OS_STAGE

    @failures_lib.SetFailureType(failures_lib.InfrastructureFailure)
    def PerformStage(self):
        """Generate debug symbols and upload debug.tgz."""
        buildroot = self._build_root
        board = self._current_board
        dryrun = False

        # Generate breakpad symbols of Chrome OS binaries.
        commands.GenerateBreakpadSymbols(
            buildroot, board, self._run.options.debug_forced
        )

        # Generate breakpad symbols of Android binaries if we have a symbol
        # archive. This archive is created by AndroidDebugSymbolsStage in
        # Android PFQ. This must be done after GenerateBreakpadSymbols because
        # it clobbers the output directory.
        symbols_file = os.path.join(
            self.archive_path, constants.ANDROID_SYMBOLS_FILE
        )
        if os.path.exists(symbols_file):
            commands.GenerateAndroidBreakpadSymbols(
                buildroot, board, symbols_file
            )

        self.board_runattrs.SetParallel("breakpad_symbols_generated", True)

        # Upload them.
        self.GenerateDebugTarball(upload=not dryrun)

        # Upload debug/breakpad tarball.
        self.GenerateDebugBreakpadTarball(upload=not dryrun)

        # Upload them to crash server.
        if self._run.config.upload_symbols and not dryrun:
            self.UploadSymbols(buildroot, board)

        self.board_runattrs.SetParallel("debug_symbols_completed", True)

    def GenerateDebugTarball(self, upload=True):
        """Generate and upload the debug tarball.

        Args:
            upload: Boolean indicating whether to upload the generated debug
                tarball.
        """
        filename = commands.GenerateDebugTarball(
            self._build_root,
            self._current_board,
            self.archive_path,
            self._run.config.archive_build_debug,
        )
        if upload:
            self.UploadArtifact(filename, archive=False)
        else:
            logging.info(
                "DebugSymbolsStage dryrun: would have uploaded %s", filename
            )
        logging.info("Announcing availability of debug tarball now.")
        self.board_runattrs.SetParallel("debug_tarball_generated", True)

    def GenerateDebugBreakpadTarball(self, upload=True):
        """Generate and upload the debug tarball with only breakpad files.

        Args:
            upload: Boolean indicating whether to upload the generated debug
                tarball.
        """
        filename = commands.GenerateDebugTarball(
            self._build_root,
            self._current_board,
            self.archive_path,
            False,
            archive_name="debug_breakpad.tar.xz",
        )
        if upload:
            self.UploadArtifact(filename, archive=False)
        else:
            logging.info(
                "DebugSymbolsStage dryrun: would have uploaded %s", filename
            )

    def UploadSymbols(self, buildroot, board):
        """Upload generated debug symbols."""
        failed_name = "failed_upload_symbols.list"
        failed_list = os.path.join(self.archive_path, failed_name)

        if self._run.options.remote_trybot or self._run.options.debug_forced:
            # For debug builds, limit ourselves to just uploading 1 symbol.
            # This way trybots and such still exercise this code.
            cnt = 1
            official = False
        else:
            cnt = None
            official = self._run.config.chromeos_official

        upload_passed = True
        try:
            commands.UploadSymbols(buildroot, board, official, cnt, failed_list)
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
            raise DebugSymbolsUploadException("Failed to upload all symbols.")

    def _SymbolsNotGenerated(self):
        """Tell other stages that our symbols were not generated."""
        self.board_runattrs.SetParallelDefault(
            "breakpad_symbols_generated", False
        )
        self.board_runattrs.SetParallelDefault("debug_tarball_generated", False)

    def HandleSkip(self):
        """Tell other stages to not wait on us if we are skipped."""
        self._SymbolsNotGenerated()
        self.board_runattrs.SetParallel("debug_symbols_completed", True)
        return super().HandleSkip()

    def _HandleStageException(self, exc_info):
        """Tell other stages to not wait on us if we die for some reason."""
        self._SymbolsNotGenerated()
        self.board_runattrs.SetParallel("debug_symbols_completed", True)

        # TODO(dgarrett): Get failures tracked in metrics (crbug.com/652463).
        exc_type, e, _ = exc_info
        if issubclass(exc_type, DebugSymbolsUploadException) or (
            isinstance(e, failures_lib.CompoundFailure)
            and e.MatchesFailureType(DebugSymbolsUploadException)
        ):
            return self._HandleExceptionAsWarning(exc_info)

        return super()._HandleStageException(exc_info)


class UploadPrebuiltsStage(generic_stages.BoardSpecificBuilderStage):
    """Uploads binaries generated by this build for developer use."""

    option_name = "prebuilts"
    config_name = "prebuilts"
    category = constants.CI_INFRA_STAGE

    def __init__(self, builder_run, buildstore, board, version=None, **kwargs):
        self.prebuilts_version = version
        super().__init__(builder_run, buildstore, board, **kwargs)

    def GenerateCommonArgs(self, inc_chrome_ver=True):
        """Generate common prebuilt arguments."""
        generated_args = []
        if self._run.options.debug:
            generated_args.extend(["--debug", "--dry-run"])

        profile = self._run.options.profile or self._run.config.profile
        if profile:
            generated_args.extend(["--profile", profile])

        # Generate the version if we are a manifest_version build.
        if self._run.config.manifest_version:
            version = self._run.GetVersion(include_chrome=inc_chrome_ver)
        else:
            version = self.prebuilts_version
        if version is not None:
            generated_args.extend(["--set-version", version])

        if self._run.config.git_sync and self._run.options.publish:
            # Git sync should never be set for pfq type builds.
            assert not config_lib.IsPFQType(self._prebuilt_type)
            generated_args.append("--git-sync")
        if not self._run.options.publish:
            generated_args.append("--no-sync-remote-latest-sdk-file")

        return generated_args

    @classmethod
    def _AddOptionsForSlave(cls, slave_config, board):
        """Helper method to add upload_prebuilts args for a slave builder.

        Args:
            slave_config: The build config of a slave builder.
            board: The name of the "master" board on the master builder.

        Returns:
            An array of options to add to upload_prebuilts array that allow a
            master to submit prebuilt conf modifications on behalf of a slave.
        """
        args = []
        if slave_config["prebuilts"]:
            for slave_board in slave_config["boards"]:
                if slave_config["master"] and slave_board == board:
                    # Ignore self.
                    continue

                args.extend(["--slave-board", slave_board])
                slave_profile = slave_config["profile"]
                if slave_profile:
                    args.extend(["--slave-profile", slave_profile])

        return args

    @failures_lib.SetFailureType(failures_lib.InfrastructureFailure)
    def PerformStage(self):
        """Uploads prebuilts for master and slave builders."""
        prebuilt_type = self._prebuilt_type
        board = self._current_board

        # Whether we publish public or private prebuilts.
        public = self._run.config.prebuilts == constants.PUBLIC
        # Common args we generate for all types of builds.
        generated_args = self.GenerateCommonArgs()
        # Args we specifically add for public/private build types.
        public_args, private_args = [], []
        # Public / private builders.
        public_builders, private_builders = [], []

        common_kwargs = {
            "buildroot": self._build_root,
            "category": prebuilt_type,
            "version": self.prebuilts_version,
        }

        # Upload the public prebuilts, if any.
        if public_builders or public:
            public_board = board if public else None
            prebuilts.UploadPrebuilts(
                private_bucket=False,
                board=public_board,
                extra_args=generated_args + public_args,
                **common_kwargs,
            )

        # Upload the private prebuilts, if any.
        if private_builders or not public:
            private_board = board if not public else None
            prebuilts.UploadPrebuilts(
                private_bucket=True,
                board=private_board,
                extra_args=generated_args + private_args,
                **common_kwargs,
            )


class UploadTestArtifactsStage(
    generic_stages.BoardSpecificBuilderStage, generic_stages.ArchivingStageMixin
):
    """Upload needed hardware test artifacts."""

    category = constants.CI_INFRA_STAGE

    def BuildAutotestTarballs(self):
        """Build the autotest tarballs."""
        with osutils.TempDir(prefix="cbuildbot-autotest") as tempdir:
            with self.ArtifactUploader(strict=True) as queue:
                cwd = os.path.abspath(
                    os.path.join(
                        self._build_root,
                        "chroot",
                        "build",
                        self._current_board,
                        constants.AUTOTEST_BUILD_PATH,
                        "..",
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
                    queue.put([tarball])

    def BuildTastTarball(self):
        """Build the tarball containing private Tast test bundles."""
        with osutils.TempDir(prefix="cbuildbot-tast") as tempdir:
            cwd = os.path.abspath(
                os.path.join(
                    self._build_root,
                    "chroot",
                    "build",
                    self._current_board,
                    "build",
                )
            )
            logging.info("Running commands.BuildTastBundleTarball")
            tarball = commands.BuildTastBundleTarball(
                self._build_root, cwd, tempdir
            )
            if tarball:
                self.UploadArtifact(tarball)

    def BuildFpmcuUnittestsTarball(self):
        """Build the tarball containing fingerprint MCU on-device unittests."""
        with osutils.TempDir(prefix="cbuildbot-fpmcu-unittests") as tempdir:
            logging.info("Running commands.BuildFpmcuUnittestsArchive")
            tarball = commands.BuildFpmcuUnittestsArchive(
                self._build_root, self._current_board, tempdir
            )
            if tarball:
                self.UploadArtifact(tarball)

    def _GeneratePayloads(self, image_name, **kwargs):
        """Generate and upload payloads for |image_name|.

        Args:
            image_name: The image to use.
            **kwargs: Keyword arguments to pass to commands.GeneratePayloads.
        """
        with osutils.TempDir(prefix="cbuildbot-payloads") as tempdir:
            with self.ArtifactUploader() as queue:
                image_path = os.path.join(self.GetImageDirSymlink(), image_name)
                logging.info("Running commands.GeneratePayloads")
                commands.GeneratePayloads(
                    self._build_root, image_path, tempdir, **kwargs
                )
                for payload in os.listdir(tempdir):
                    queue.put([os.path.join(tempdir, payload)])

    def BuildUpdatePayloads(self):
        """Archives update payloads when they are ready."""
        # If we are not configured to generate payloads, don't.
        if not (
            self._run.options.build
            and self._run.options.tests
            and self._run.config.upload_hw_test_artifacts
            and self._run.config.images
        ):
            return

        # If there are no images to generate payloads from, don't.
        got_images = self.GetParallel("images_generated", pretty_name="images")
        if not got_images:
            return

        payload_type = "base"
        for t in ["test", "dev"]:
            if t in self._run.config.images:
                payload_type = t
                break
        image_name = constants.IMAGE_TYPE_TO_NAME[payload_type]
        logging.info("Generating payloads to upload for %s", image_name)
        self._GeneratePayloads(
            image_name, full=True, stateful=True, delta=True, dlc=True
        )

    @failures_lib.SetFailureType(failures_lib.InfrastructureFailure)
    def PerformStage(self):
        """Upload any needed HWTest artifacts."""
        # BuildUpdatePayloads also uploads the payloads to GS.
        steps = [self.BuildUpdatePayloads]

        if (
            self._run.ShouldBuildAutotest()
            and self._run.config.upload_hw_test_artifacts
        ):
            steps.append(self.BuildAutotestTarballs)
            steps.append(self.BuildTastTarball)
            steps.append(self.BuildFpmcuUnittestsTarball)

        parallel.RunParallelSteps(steps)
        # If we encountered any exceptions with any of the steps, they should
        # have set the attribute to False.
        self.board_runattrs.SetParallelDefault("test_artifacts_uploaded", True)

    def _HandleStageException(self, exc_info):
        # Tell the test stages not to wait for artifacts to be uploaded in case
        # UploadTestArtifacts throws an exception.
        self.board_runattrs.SetParallel("test_artifacts_uploaded", False)

        return super()._HandleStageException(exc_info)

    def HandleSkip(self):
        """Launch DebugSymbolsStage if UnitTestStage is skipped."""
        self.board_runattrs.SetParallel("test_artifacts_uploaded", False)
        return super().HandleSkip()
