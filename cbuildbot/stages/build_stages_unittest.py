# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for build stages."""

import contextlib
import os
from pathlib import Path
from unittest import mock

from chromite.cbuildbot import cbuildbot_unittest
from chromite.cbuildbot import commands
from chromite.cbuildbot.stages import build_stages
from chromite.cbuildbot.stages import generic_stages_unittest
from chromite.lib import build_summary
from chromite.lib import buildstore
from chromite.lib import cidb
from chromite.lib import config_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_sdk_lib
from chromite.lib import cros_test_lib
from chromite.lib import fake_cidb
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib import parallel_unittest
from chromite.lib import partial_mock
from chromite.lib import path_util
from chromite.utils import hostname_util


# pylint: disable=too-many-ancestors
# pylint: disable=protected-access


class _RunAbstractStageTestCase(
    generic_stages_unittest.RunCommandAbstractStageTestCase
):
    """Helper with a RunStage wrapper."""

    def _Run(self, dir_exists):
        """Helper for running the build."""
        with mock.patch.object(
            os.path, "isdir", autospec=True, return_value=dir_exists
        ):
            self.RunStage()

    def ConstructStage(self):
        """Returns an instance of the stage to be tested.

        Note: Must be implemented in subclasses.
        """
        raise NotImplementedError(
            self, "ConstructStage: Implement in your test"
        )


class InitSDKTest(_RunAbstractStageTestCase):
    """Test building the SDK"""

    def setUp(self):
        self.PatchObject(cros_sdk_lib, "GetChrootVersion", return_value="12")
        self.cros_sdk = os.path.join(
            self.tempdir, "buildroot", constants.CHROMITE_BIN_SUBDIR, "cros_sdk"
        )
        self.fake_db = fake_cidb.FakeCIDBConnection()
        self.buildstore = buildstore.FakeBuildStore(self.fake_db)
        cidb.CIDBConnectionFactory.SetupMockCidb(self.fake_db)

    def ConstructStage(self):
        return build_stages.InitSDKStage(self._run, self.buildstore)

    def testFullBuildWithExistingChroot(self):
        """Tests whether we create chroots for full builds."""
        self._PrepareFull()
        self._Run(dir_exists=True)
        self.assertCommandContains([self.cros_sdk])

    def testBinBuildWithMissingChroot(self):
        """Tests whether we create chroots when needed."""
        self._PrepareBin()
        # Do not force chroot replacement in build config.
        self._run._config.chroot_replace = False
        self._Run(dir_exists=False)
        self.assertCommandContains([self.cros_sdk])

    def testFullBuildWithMissingChroot(self):
        """Tests whether we create chroots when needed."""
        self._PrepareFull()
        self._Run(dir_exists=True)
        self.assertCommandContains([self.cros_sdk])

    def testFullBuildWithNoSDK(self):
        """Tests whether the --nosdk option works."""
        self._PrepareFull(extra_cmd_args=["--nosdk"])
        self._Run(dir_exists=False)
        self.assertCommandContains([self.cros_sdk, "--bootstrap"])

    def testBinBuildWithExistingChroot(self):
        """Tests whether the --nosdk option works."""
        self._PrepareFull(extra_cmd_args=["--nosdk"])
        # Do not force chroot replacement in build config.
        self._run._config.chroot_replace = False
        self._run.config.useflags = ["foo"]
        self._Run(dir_exists=True)
        self.assertCommandContains([self.cros_sdk], expected=False)
        self.assertCommandContains(["./update_chroot"], expected=False)


class UpdateSDKTest(_RunAbstractStageTestCase):
    """Test UpdateSDKStage."""

    def ConstructStage(self):
        self.buildstore = buildstore.FakeBuildStore()
        return build_stages.UpdateSDKStage(
            self._run, self.buildstore, self._current_board
        )

    def _RunFull(self, dir_exists=False):
        """Helper for testing a full builder."""
        self._Run(dir_exists)
        self.assertCommandContains(["./update_chroot"])

    def testFullBuildWithProfile(self):
        """Tests whether full builds add profile flag when requested."""
        self._PrepareFull(extra_config={"profile": "foo"})
        self._RunFull(dir_exists=False)

    def testFullBuildWithOverriddenProfile(self):
        """Whether full builds add overridden profile flag when requested."""
        self._PrepareFull(extra_cmd_args=["--profile", "smock"])
        self._RunFull(dir_exists=False)

    def _RunBin(self, dir_exists):
        """Helper for testing a binary builder."""
        self._Run(dir_exists)
        update_nousepkg = self._run.options.latest_toolchain
        self.assertCommandContains(
            ["./update_chroot", "--nousepkg"], expected=update_nousepkg
        )

    def testBinBuildWithLatestToolchain(self):
        """Tests whether we use --nousepkg for creating the board."""
        self._PrepareBin()
        self._run.options.latest_toolchain = True
        self._RunBin(dir_exists=False)

    def testBinBuildWithLatestToolchainAndDirExists(self):
        """Tests whether we use --nousepkg for creating the board."""
        self._PrepareBin()
        self._run.options.latest_toolchain = True
        self._RunBin(dir_exists=True)


class SetupBoardTest(_RunAbstractStageTestCase):
    """Test building the board"""

    def setUp(self):
        self.setup_toolchains_mock = self.PatchObject(
            commands, "SetupToolchains"
        )
        self.fake_db = fake_cidb.FakeCIDBConnection()
        self.buildstore = buildstore.FakeBuildStore(self.fake_db)
        cidb.CIDBConnectionFactory.SetupMockCidb(self.fake_db)

        # Prevent the setup_board tempdir path from being translated because it
        # ends up raising an error when that path can't be found in the chroot.
        self.PatchObject(
            path_util, "ToChrootPath", side_effect=lambda x, **kwargs: x
        )
        self.setup_board = os.path.join(
            self.tempdir,
            "buildroot",
            constants.CHROMITE_BIN_SUBDIR,
            "setup_board",
        )

    def ConstructStage(self):
        return build_stages.SetupBoardStage(
            self._run, self.buildstore, self._current_board
        )

    def _RunFull(self, dir_exists=False):
        """Helper for testing a full builder."""
        self._Run(dir_exists)
        cmd = [
            self.setup_board,
            "--board=%s" % self._current_board,
            "--nousepkg",
        ]
        self.assertCommandContains(cmd)
        cmd = [self.setup_board, "--skip-chroot-upgrade"]
        self.assertCommandContains(cmd)

    def testFullBuildWithProfile(self):
        """Tests whether full builds add profile flag when requested."""
        self._PrepareFull(extra_config={"profile": "foo"})
        self._RunFull(dir_exists=False)
        self.assertCommandContains([self.setup_board, "--profile=foo"])

    def testFullBuildWithOverriddenProfile(self):
        """Tests if full builds add overridden profile flag when requested."""
        self._PrepareFull(extra_cmd_args=["--profile", "smock"])
        self._RunFull(dir_exists=False)
        self.assertCommandContains([self.setup_board, "--profile=smock"])

    def _RunBin(self, dir_exists):
        """Helper for testing a binary builder."""
        self._Run(dir_exists)
        self.assertTrue(self.setup_toolchains_mock.called)
        self.assertCommandContains([self.setup_board])
        cmd = [self.setup_board, "--skip-chroot-upgrade"]
        self.assertCommandContains(cmd)
        cmd = [self.setup_board, "--nousepkg"]
        self.assertCommandContains(
            cmd, not self._run.config.usepkg_build_packages
        )

    def testBinBuildWithLatestToolchain(self):
        """Tests whether we use --nousepkg for creating the board."""
        self._PrepareBin()
        self._run.options.latest_toolchain = True
        self._RunBin(dir_exists=False)

    def testBinBuildWithLatestToolchainAndDirExists(self):
        """Tests whether we use --nousepkg for creating the board."""
        self._PrepareBin()
        self._run.options.latest_toolchain = True
        self._RunBin(dir_exists=True)

    def testSDKBuild(self):
        """Tests whether we use --skip_chroot_upgrade for SDK builds."""
        extra_config = {"build_type": constants.CHROOT_BUILDER_TYPE}
        self._PrepareFull(extra_config=extra_config)
        self._Run(dir_exists=False)
        self.assertCommandContains(["./update_chroot"], expected=False)
        self.assertCommandContains([self.setup_board, "--skip-chroot-upgrade"])


class UprevStageTest(generic_stages_unittest.AbstractStageTestCase):
    """Tests for the UprevStage class."""

    def setUp(self):
        self.uprev_mock = self.PatchObject(commands, "UprevPackages")

        self._Prepare()
        self.fake_db = fake_cidb.FakeCIDBConnection()
        self.buildstore = buildstore.FakeBuildStore(self.fake_db)
        cidb.CIDBConnectionFactory.SetupMockCidb(self.fake_db)

    def ConstructStage(self):
        return build_stages.UprevStage(self._run, self.buildstore)

    def testBuildRev(self):
        """Uprevving the build without uprevving chrome."""
        self._run.config["uprev"] = True
        self.RunStage()
        self.assertTrue(self.uprev_mock.called)

    def testNoRev(self):
        """No paths are enabled."""
        self._run.config["uprev"] = False
        self.RunStage()
        self.assertFalse(self.uprev_mock.called)


class AllConfigsTestCase(
    generic_stages_unittest.AbstractStageTestCase, cros_test_lib.OutputTestCase
):
    """Test case for testing against all bot configs."""

    def ConstructStage(self):
        """Bypass lint warning"""
        generic_stages_unittest.AbstractStageTestCase.ConstructStage(self)

    @contextlib.contextmanager
    def RunStageWithConfig(self, mock_configurator=None):
        """Run the given config"""
        try:
            with cros_test_lib.RunCommandMock() as rc:
                rc.SetDefaultCmdResult()
                if mock_configurator:
                    mock_configurator(rc)
                with self.OutputCapturer():
                    with cros_test_lib.LoggingCapturer():
                        self.RunStage()

                yield rc

        except AssertionError as ex:
            msg = "%s failed the following test:\n%s" % (self._bot_id, ex)
            raise AssertionError(msg)

    def RunAllConfigs(self, task, site_config=None):
        """Run |task| against all major configurations"""
        if site_config is None:
            site_config = config_lib.GetConfig()

        boards = ("hatch", "kevin")

        for board in boards:
            self.CreateMockOverlay(board)

        with parallel.BackgroundTaskRunner(task) as queue:
            # Test every build config on an waterfall, that builds something.
            for bot_id, cfg in site_config.items():
                if not cfg.boards or cfg.boards[0] not in boards:
                    continue

                queue.put([bot_id])


class BuildPackagesStageTest(
    AllConfigsTestCase, cbuildbot_unittest.SimpleBuilderTestCase
):
    """Tests BuildPackagesStage."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)
        self.path_resolver = path_util.ChrootPathResolver(
            source_path=self.build_root
        )
        osutils.SafeMakedirs(self.path_resolver.FromChroot("/tmp"))

        self._release_tag = None
        self._update_metadata = False
        self._mock_configurator = None
        self.fake_db = fake_cidb.FakeCIDBConnection()
        self.buildstore = buildstore.FakeBuildStore(self.fake_db)
        cidb.CIDBConnectionFactory.SetupMockCidb(self.fake_db)

    def ConstructStage(self):
        self._run.attrs.release_tag = self._release_tag
        return build_stages.BuildPackagesStage(
            self._run,
            self.buildstore,
            self._current_board,
            record_packages_under_test=False,
            update_metadata=self._update_metadata,
        )

    def RunTestsWithBotId(self, bot_id, options_tests=True):
        """Test with the config for the specified bot_id."""
        self._Prepare(bot_id)
        self._run.options.tests = options_tests
        build_packages = self.path_resolver.ToChroot(
            os.path.join(
                self.tempdir,
                "buildroot",
                constants.CHROMITE_BIN_SUBDIR,
                "build_packages",
            )
        )

        with self.RunStageWithConfig(self._mock_configurator) as rc:
            cfg = self._run.config
            rc.assertCommandContains([build_packages])
            rc.assertCommandContains(["--skip-chroot-upgrade"])
            rc.assertCommandContains(
                ["--no-usepkg"], expected=not cfg["usepkg_build_packages"]
            )
            rc.assertCommandContains(
                ["--no-withautotest"], expected=not self._run.options.tests
            )

    def testAllConfigs(self):
        """Test all major configurations"""
        self.RunAllConfigs(self.RunTestsWithBotId)

    def testNoTests(self):
        """Test that self.options.tests = False works."""
        self.RunTestsWithBotId("amd64-generic-full", options_tests=False)

    def testFirmwareVersionsMixedImage(self):
        """Test that firmware versions are extracted correctly."""
        expected_main_firmware_version = "reef_v1.1.5822-78709a5"
        expected_ec_firmware_version = "Google_Reef.9042.30.0"

        def _HookRunCommandFirmwareUpdate(rc):
            # A mixed RO+RW image will have separate "(RW) version" fields.
            rc.AddCmdResult(
                partial_mock.ListRegex("chromeos-firmwareupdate"),
                stdout="BIOS (RW) version: %s\nEC (RW) version: %s"
                % (
                    expected_main_firmware_version,
                    expected_ec_firmware_version,
                ),
            )

        self._update_metadata = True
        update = self.path_resolver.FromChroot(
            "/build/amd64-generic/usr/sbin/chromeos-firmwareupdate"
        )
        osutils.Touch(update, makedirs=True)

        self._mock_configurator = _HookRunCommandFirmwareUpdate
        self.RunTestsWithBotId("amd64-generic-full", options_tests=False)
        board_metadata = self._run.attrs.metadata.GetDict()[
            "board-metadata"
        ].get("amd64-generic")
        if board_metadata:
            self.assertIn("main-firmware-version", board_metadata)
            self.assertEqual(
                board_metadata["main-firmware-version"],
                expected_main_firmware_version,
            )
            self.assertIn("ec-firmware-version", board_metadata)
            self.assertEqual(
                board_metadata["ec-firmware-version"],
                expected_ec_firmware_version,
            )
            self.assertFalse(self._run.attrs.metadata.GetDict()["unibuild"])

    def testFirmwareVersions(self):
        """Test that firmware versions are extracted correctly."""
        expected_main_firmware_version = "reef_v1.1.5822-78709a5"
        expected_ec_firmware_version = "Google_Reef.9042.30.0"

        def _HookRunCommandFirmwareUpdate(rc):
            rc.AddCmdResult(
                partial_mock.ListRegex("chromeos-firmwareupdate"),
                stdout="BIOS version: %s\nEC version: %s"
                % (
                    expected_main_firmware_version,
                    expected_ec_firmware_version,
                ),
            )

        self._update_metadata = True
        update = self.path_resolver.FromChroot(
            "/build/amd64-generic/usr/sbin/chromeos-firmwareupdate"
        )
        osutils.Touch(update, makedirs=True)

        self._mock_configurator = _HookRunCommandFirmwareUpdate
        self.RunTestsWithBotId("amd64-generic-full", options_tests=False)
        board_metadata = self._run.attrs.metadata.GetDict()[
            "board-metadata"
        ].get("amd64-generic")
        import logging

        logging.error("board-metatdata: %s", board_metadata)
        if board_metadata:
            self.assertIn("main-firmware-version", board_metadata)
            self.assertEqual(
                board_metadata["main-firmware-version"],
                expected_main_firmware_version,
            )
            self.assertIn("ec-firmware-version", board_metadata)
            self.assertEqual(
                board_metadata["ec-firmware-version"],
                expected_ec_firmware_version,
            )
            self.assertFalse(self._run.attrs.metadata.GetDict()["unibuild"])

    def testFirmwareVersionsUnibuild(self):
        """Test that firmware versions are extracted correctly for unibuilds."""

        def _HookRunCommand(rc):
            rc.AddCmdResult(
                partial_mock.In("list-models"), stdout="reef\npyro\nelectro"
            )
            rc.AddCmdResult(partial_mock.In("get"), stdout="key-123")
            rc.AddCmdResult(
                partial_mock.ListRegex("chromeos-firmwareupdate"),
                stdout="""
Model:        reef
BIOS image:
BIOS version: Google_Reef.9042.87.1
BIOS (RW) version: Google_Reef.9042.110.0
EC version:   reef_v1.1.5900-ab1ee51
EC (RW) version: reef_v1.1.5909-bd1f0c9

Model:        pyro
BIOS image:
BIOS version: Google_Pyro.9042.87.1
BIOS (RW) version: Google_Pyro.9042.110.0
EC version:   pyro_v1.1.5900-ab1ee51
EC (RW) version: pyro_v1.1.5909-bd1f0c9

Model:        electro
BIOS image:
BIOS version: Google_Reef.9042.87.1
EC version:   reef_v1.1.5900-ab1ee51
EC (RW) version: reef_v1.1.5909-bd1f0c9
""",
            )

        self._update_metadata = True
        update = self.path_resolver.FromChroot(
            "/build/amd64-generic/usr/sbin/chromeos-firmwareupdate"
        )
        osutils.Touch(update, makedirs=True)

        cros_config_host = self.path_resolver.FromChroot(
            "/usr/bin/cros_config_host"
        )
        osutils.Touch(cros_config_host, makedirs=True)

        self._mock_configurator = _HookRunCommand
        self.RunTestsWithBotId("amd64-generic-full", options_tests=False)
        board_metadata = self._run.attrs.metadata.GetDict()[
            "board-metadata"
        ].get("amd64-generic")
        self.assertIsNotNone(board_metadata)

        if "models" in board_metadata:
            reef = board_metadata["models"]["reef"]
            self.assertEqual(
                "Google_Reef.9042.87.1", reef["main-readonly-firmware-version"]
            )
            self.assertEqual(
                "Google_Reef.9042.110.0",
                reef["main-readwrite-firmware-version"],
            )
            self.assertEqual(
                "reef_v1.1.5909-bd1f0c9", reef["ec-firmware-version"]
            )
            self.assertEqual("key-123", reef["firmware-key-id"])

            self.assertIn("pyro", board_metadata["models"])
            self.assertIn("electro", board_metadata["models"])
            electro = board_metadata["models"]["electro"]
            self.assertEqual(
                "Google_Reef.9042.87.1",
                electro["main-readonly-firmware-version"],
            )
            # Test RW firmware is defaulted to RO version if isn't specified.
            self.assertEqual(
                "Google_Reef.9042.87.1",
                electro["main-readwrite-firmware-version"],
            )

    def testUnifiedBuilds(self):
        """Test that unified builds are marked as such."""

        def _HookRunCommandCrosConfigHost(rc):
            rc.AddCmdResult(
                partial_mock.ListRegex("cros_config_host"), stdout="reef"
            )

        self._update_metadata = True
        cros_config_host = self.path_resolver.FromChroot(
            "/usr/bin/cros_config_host"
        )
        osutils.Touch(cros_config_host, makedirs=True)
        self._mock_configurator = _HookRunCommandCrosConfigHost
        self.RunTestsWithBotId("amd64-generic-full", options_tests=False)
        self.assertTrue(self._run.attrs.metadata.GetDict()["unibuild"])

    def testGoma(self):
        self.PatchObject(
            build_stages.BuildPackagesStage,
            "_ShouldEnableGoma",
            return_value=True,
        )
        self._Prepare("amd64-generic-full")
        # Set stub dir name to enable goma.
        with osutils.TempDir() as goma_dir:
            goma_dir = Path(goma_dir)
            self._run.options.goma_dir = goma_dir
            self._run.options.chromeos_goma_dir = goma_dir

            stage = self.ConstructStage()
            chroot_args = stage._SetupGomaIfNecessary()
            self.assertEqual(
                [
                    "--goma_dir",
                    str(goma_dir),
                ],
                chroot_args,
            )
            portage_env = stage._portage_extra_env
            self.assertEqual(
                portage_env.get("GOMA_DIR", ""), os.path.expanduser("~/goma")
            )
            self.assertEqual(portage_env.get("USE_GOMA", ""), "true")

    def testGomaOnBotWithoutCertFile(self):
        self.PatchObject(
            build_stages.BuildPackagesStage,
            "_ShouldEnableGoma",
            return_value=True,
        )
        self.PatchObject(hostname_util, "host_is_ci_builder", return_value=True)
        self._Prepare("amd64-generic-full")
        # Set stub dir name to enable goma.
        with osutils.TempDir() as goma_dir:
            self._run.options.goma_dir = goma_dir
            stage = self.ConstructStage()
            self._run.options.chromeos_goma_dir = goma_dir
            chroot_args = stage._SetupGomaIfNecessary()
            self.assertEqual(
                [
                    "--goma_dir",
                    str(goma_dir),
                ],
                chroot_args,
            )
            portage_env = stage._portage_extra_env
            self.assertEqual(
                portage_env.get("GOMA_DIR", ""), os.path.expanduser("~/goma")
            )
            self.assertEqual(
                portage_env.get("GOMA_GCE_SERVICE_ACCOUNT", ""), "default"
            )


class BuildImageStageMock(partial_mock.PartialMock):
    """Partial mock for BuildImageStage."""

    TARGET = "chromite.cbuildbot.stages.build_stages.BuildImageStage"
    ATTRS = ("_BuildImages",)

    def _BuildImages(self, *args, **kwargs):
        with mock.patch.object(os, "symlink", autospec=True):
            self.backup["_BuildImages"](*args, **kwargs)


class BuildImageStageTest(BuildPackagesStageTest):
    """Tests BuildImageStage."""

    def setUp(self):
        self.fake_db = fake_cidb.FakeCIDBConnection()
        self.buildstore = buildstore.FakeBuildStore(self.fake_db)
        cidb.CIDBConnectionFactory.SetupMockCidb(self.fake_db)

    def ConstructStage(self):
        latest_image_dir = (
            Path(self.build_root)
            / "src"
            / "build"
            / "images"
            / self._current_board
        )
        osutils.SafeMakedirs(latest_image_dir)
        osutils.SafeSymlink("someboard", latest_image_dir / "latest")
        self.StartPatcher(BuildImageStageMock())

        return build_stages.BuildImageStage(
            self._run, self.buildstore, self._current_board
        )

    def RunTestsWithReleaseConfig(self, release_tag):
        self._release_tag = release_tag

        with parallel_unittest.ParallelMock():
            with self.RunStageWithConfig() as rc:
                cfg = self._run.config
                cmd = [
                    "./build_image",
                    "--version=%s" % (self._release_tag or ""),
                ]
                rc.assertCommandContains(cmd, expected=cfg["images"])

    def RunTestsWithBotId(self, bot_id, options_tests=True):
        """Test with the config for the specified bot_id."""
        release_tag = "0.0.1"
        self._Prepare(bot_id)
        self._run.options.tests = options_tests
        self._run.attrs.release_tag = release_tag

        task = self.RunTestsWithReleaseConfig
        # TODO: This test is broken atm with tag=None.
        steps = [lambda tag=x: task(tag) for x in (release_tag,)]
        parallel.RunParallelSteps(steps)

    def testUnifiedBuilds(self):
        pass


class CleanUpStageTest(generic_stages_unittest.StageTestCase):
    """Test CleanUpStage."""

    BOT_ID = "amd64-generic-full"

    def setUp(self):
        self.fake_db = fake_cidb.FakeCIDBConnection()
        self.buildstore = buildstore.FakeBuildStore(self.fake_db)
        cidb.CIDBConnectionFactory.SetupMockCidb(self.fake_db)

        self.fake_db.InsertBuild(
            "test_builder",
            666,
            "test_config",
            "test_hostname",
            status=constants.BUILDER_STATUS_INFLIGHT,
            timeout_seconds=23456,
            buildbucket_id="100",
        )

        self.fake_db.InsertBuild(
            "test_builder",
            666,
            "test_config",
            "test_hostname",
            status=constants.BUILDER_STATUS_INFLIGHT,
            timeout_seconds=23456,
            buildbucket_id="200",
        )

        self._Prepare()

    def ConstructStage(self):
        return build_stages.CleanUpStage(self._run, self.buildstore)

    def testChrootReuseChrootReplace(self):
        self._Prepare(extra_config={"chroot_replace": True})

        self.PatchObject(
            build_stages.CleanUpStage,
            "_GetPreviousBuildStatus",
            return_value=build_summary.BuildSummary(
                build_number=314, status=constants.BUILDER_STATUS_PASSED
            ),
        )

        stage = self.ConstructStage()
        self.assertFalse(stage.CanReuseChroot())

    def testChrootReusePreviousFailed(self):
        self.PatchObject(
            build_stages.CleanUpStage,
            "_GetPreviousBuildStatus",
            return_value=build_summary.BuildSummary(
                build_number=314, status=constants.BUILDER_STATUS_FAILED
            ),
        )

        stage = self.ConstructStage()
        self.assertFalse(stage.CanReuseChroot())

    def testChrootReusePreviousMasterMissing(self):
        self.PatchObject(
            build_stages.CleanUpStage,
            "_GetPreviousBuildStatus",
            return_value=build_summary.BuildSummary(
                build_number=314,
                master_build_id=2178,
                status=constants.BUILDER_STATUS_PASSED,
            ),
        )

        stage = self.ConstructStage()
        self.assertFalse(stage.CanReuseChroot())

    def testChrootReusePreviousMasterFailed(self):
        master_id = self.fake_db.InsertBuild(
            "test_builder",
            123,
            "test_config",
            "test_hostname",
            status=constants.BUILDER_STATUS_FAILED,
            buildbucket_id="2178",
        )
        self.PatchObject(
            build_stages.CleanUpStage,
            "_GetPreviousBuildStatus",
            return_value=build_summary.BuildSummary(
                build_number=314,
                master_build_id=master_id,
                status=constants.BUILDER_STATUS_PASSED,
            ),
        )

        stage = self.ConstructStage()
        self.assertFalse(stage.CanReuseChroot())
