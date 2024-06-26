# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for the artifact stages."""

import os
import sys
from unittest import mock

from chromite.cbuildbot import cbuildbot_unittest
from chromite.cbuildbot import commands
from chromite.cbuildbot.stages import artifact_stages
from chromite.cbuildbot.stages import build_stages_unittest
from chromite.cbuildbot.stages import generic_stages_unittest
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import failures_lib
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib import parallel_unittest
from chromite.lib import path_util
from chromite.lib import results_lib
from chromite.lib.buildstore import FakeBuildStore


# pylint: disable=too-many-ancestors


class ArchiveStageTest(
    generic_stages_unittest.AbstractStageTestCase,
    cbuildbot_unittest.SimpleBuilderTestCase,
):
    """Exercise ArchiveStage functionality."""

    # pylint: disable=protected-access

    RELEASE_TAG = ""
    VERSION = "3333.1.0"

    def _PatchDependencies(self):
        """Patch dependencies of ArchiveStage.PerformStage()."""
        to_patch = [
            (parallel, "RunParallelSteps"),
            (commands, "PushImages"),
            (commands, "UploadArchivedFile"),
        ]
        self.AutoPatch(to_patch)

    def setUp(self):
        self._PatchDependencies()

        self._Prepare()
        self.buildstore = FakeBuildStore()

    # Our API here is not great when it comes to kwargs passing.
    def _Prepare(
        self, bot_id=None, **kwargs
    ):  # pylint: disable=arguments-differ
        extra_config = {"upload_symbols": True, "push_image": True}
        super()._Prepare(bot_id, extra_config=extra_config, **kwargs)

    def ConstructStage(self):
        self._run.GetArchive().SetupArchivePath()
        return artifact_stages.ArchiveStage(
            self._run, self.buildstore, self._current_board
        )

    def testArchive(self):
        """Simple did-it-run test."""
        # TODO(davidjames): Test the individual archive steps as well.
        self.RunStage()

    # TODO(build): This test is not actually testing anything real.  It confirms
    # that PushImages is not called, but the mock for RunParallelSteps already
    # prevents PushImages from being called, regardless of whether this is a
    # trybot flow.
    def testNoPushImagesForRemoteTrybot(self):
        """Test that remote trybot overrides work to disable push images."""
        self._Prepare(
            cmd_args=[
                "--remote-trybot",
                "-r",
                self.build_root,
                "--buildnumber=1234",
                "eve-release",
            ]
        )
        self.RunStage()
        # pylint: disable=no-member
        self.assertEqual(commands.PushImages.call_count, 0)

    def ConstructStageForArchiveStep(self):
        """Stage construction for archive steps."""
        stage = self.ConstructStage()
        self.PatchObject(stage._upload_queue, "put", autospec=True)
        self.PatchObject(
            path_util, "ToChrootPath", return_value="", autospec=True
        )
        return stage


class UploadPrebuiltsStageTest(
    generic_stages_unittest.RunCommandAbstractStageTestCase,
    cbuildbot_unittest.SimpleBuilderTestCase,
):
    """Tests for the UploadPrebuilts stage."""

    cmd = "upload_prebuilts"
    RELEASE_TAG = ""

    # Our API here is not great when it comes to kwargs passing.
    def _Prepare(
        self, bot_id=None, **kwargs
    ):  # pylint: disable=arguments-differ
        super()._Prepare(bot_id, **kwargs)
        self.cmd = os.path.join(
            self.build_root, constants.CHROMITE_BIN_SUBDIR, "upload_prebuilts"
        )
        self._run.options.prebuilts = True
        self.buildstore = FakeBuildStore()

    def ConstructStage(self):
        return artifact_stages.UploadPrebuiltsStage(
            self._run, self.buildstore, self._run.config.boards[-1]
        )

    def _VerifyBoardMap(
        self, bot_id, count, board_map, public_args=None, private_args=None
    ):
        """Verify that the prebuilts are uploaded for the specified bot.

        Args:
            bot_id: Bot to upload prebuilts for.
            count: Number of assert checks that should be performed.
            board_map: Map from slave boards to whether the bot is public.
            public_args: List of extra arguments for public boards.
            private_args: List of extra arguments for private boards.
        """
        self._Prepare(bot_id)
        self.RunStage()
        public_prefix = [self.cmd] + (public_args or [])
        private_prefix = [self.cmd] + (private_args or [])
        for board, public in board_map.items():
            if public or public_args:
                public_cmd = public_prefix + ["--slave-board", board]
                self.assertCommandContains(public_cmd, expected=public)
                count -= 1
            private_cmd = private_prefix + ["--slave-board", board, "--private"]
            self.assertCommandContains(private_cmd, expected=not public)
            count -= 1
        if board_map:
            self.assertCommandContains(
                [self.cmd, "--set-version", self._run.GetVersion()],
            )
            count -= 1
        self.assertEqual(
            count,
            0,
            "Number of asserts performed does not match (%d remaining)" % count,
        )

    def testFullPrebuiltsUpload(self):
        """Test uploading of full builder prebuilts."""
        self._VerifyBoardMap("amd64-generic-full", 0, {})
        self.assertCommandContains([self.cmd, "--git-sync"])

    def testIncorrectCount(self):
        """Test that _VerifyBoardMap asserts when the count is wrong."""
        self.assertRaises(
            AssertionError, self._VerifyBoardMap, "amd64-generic-full", 1, {}
        )


class DebugSymbolsStageTest(
    generic_stages_unittest.AbstractStageTestCase,
    cbuildbot_unittest.SimpleBuilderTestCase,
):
    """Test DebugSymbolsStage"""

    # pylint: disable=protected-access

    def setUp(self):
        self.CreateMockOverlay("amd64-generic")
        self.StartPatcher(generic_stages_unittest.ArchivingStageMixinMock())

        self.gen_mock = self.PatchObject(commands, "GenerateBreakpadSymbols")
        self.gen_android_mock = self.PatchObject(
            commands, "GenerateAndroidBreakpadSymbols"
        )
        self.upload_mock = self.PatchObject(commands, "UploadSymbols")
        self.upload_artifact_mock = self.PatchObject(
            artifact_stages.DebugSymbolsStage, "UploadArtifact"
        )
        self.tar_mock = self.PatchObject(commands, "GenerateDebugTarball")

        self.rc_mock = self.StartPatcher(cros_test_lib.RunCommandMock())
        self.rc_mock.SetDefaultCmdResult(stdout="")

        self.stage = None

    # Our API here is not great when it comes to kwargs passing.
    # pylint: disable=arguments-differ
    def _Prepare(self, extra_config=None, **kwargs):
        """Prepare this stage for testing."""
        if extra_config is None:
            extra_config = {
                "archive_build_debug": True,
                "upload_symbols": True,
            }
        super()._Prepare(extra_config=extra_config, **kwargs)
        self._run.attrs.release_tag = self.VERSION
        self.buildstore = FakeBuildStore()

    # pylint: enable=arguments-differ

    def ConstructStage(self):
        """Create a DebugSymbolsStage instance for testing"""
        self._run.GetArchive().SetupArchivePath()
        return artifact_stages.DebugSymbolsStage(
            self._run, self.buildstore, self._current_board
        )

    def assertBoardAttrEqual(self, attr, expected_value):
        """Assert the value of a board run |attr| against |expected_value|."""
        value = self.stage.board_runattrs.GetParallel(attr)
        self.assertEqual(expected_value, value)

    def _TestPerformStage(
        self, extra_config=None, create_android_symbols_archive=False
    ):
        """Run PerformStage for the stage with the given extra config."""
        self._Prepare(extra_config=extra_config)

        self.tar_mock.side_effect = "/my/tar/ball"
        self.stage = self.ConstructStage()

        if create_android_symbols_archive:
            symbols_file = os.path.join(
                self.stage.archive_path, constants.ANDROID_SYMBOLS_FILE
            )
            osutils.Touch(symbols_file)

        try:
            self.stage.PerformStage()
        except Exception:
            return self.stage._HandleStageException(sys.exc_info())

    def testPerformStageWithSymbols(self):
        """Smoke test for an PerformStage when debugging is enabled"""
        self._TestPerformStage()

        self.assertEqual(self.gen_mock.call_count, 1)
        self.assertEqual(self.gen_android_mock.call_count, 0)
        self.assertEqual(self.upload_mock.call_count, 1)
        self.assertEqual(self.tar_mock.call_count, 2)
        self.assertEqual(self.upload_artifact_mock.call_count, 2)

        self.assertBoardAttrEqual("breakpad_symbols_generated", True)
        self.assertBoardAttrEqual("debug_tarball_generated", True)

    def testPerformStageWithAndroidSymbols(self):
        """Smoke test for an PerformStage when Android symbols are available"""
        self._TestPerformStage(create_android_symbols_archive=True)

        self.assertEqual(self.gen_mock.call_count, 1)
        self.assertEqual(self.gen_android_mock.call_count, 1)
        self.assertEqual(self.upload_mock.call_count, 1)
        self.assertEqual(self.tar_mock.call_count, 2)
        self.assertEqual(self.upload_artifact_mock.call_count, 2)

        self.assertBoardAttrEqual("breakpad_symbols_generated", True)
        self.assertBoardAttrEqual("debug_tarball_generated", True)

    def testPerformStageNoSymbols(self):
        """Smoke test for an PerformStage when debugging is disabled"""
        extra_config = {
            "archive_build_debug": False,
            "upload_symbols": False,
        }
        result = self._TestPerformStage(extra_config)
        self.assertIsNone(result)

        self.assertEqual(self.gen_mock.call_count, 1)
        self.assertEqual(self.gen_android_mock.call_count, 0)
        self.assertEqual(self.upload_mock.call_count, 0)
        self.assertEqual(self.tar_mock.call_count, 2)
        self.assertEqual(self.upload_artifact_mock.call_count, 2)

        self.assertBoardAttrEqual("breakpad_symbols_generated", True)
        self.assertBoardAttrEqual("debug_tarball_generated", True)

    def testGenerateCrashStillNotifies(self):
        """Crashes in symbol generation should still notify external events."""

        class TestError(Exception):
            """Unique test exception"""

        self.gen_mock.side_effect = TestError("mew")
        result = self._TestPerformStage()
        self.assertIsInstance(result[0], failures_lib.InfrastructureFailure)

        self.assertEqual(self.gen_mock.call_count, 1)
        self.assertEqual(self.gen_android_mock.call_count, 0)
        self.assertEqual(self.upload_mock.call_count, 0)
        self.assertEqual(self.tar_mock.call_count, 0)
        self.assertEqual(self.upload_artifact_mock.call_count, 0)

        self.assertBoardAttrEqual("breakpad_symbols_generated", False)
        self.assertBoardAttrEqual("debug_tarball_generated", False)

    def testUploadCrashStillNotifies(self):
        """Crashes in symbol upload should still notify external events."""
        self.upload_mock.side_effect = failures_lib.BuildScriptFailure(
            cros_build_lib.RunCommandError("mew"), "mew"
        )
        result = self._TestPerformStage()
        self.assertIs(result[0], results_lib.Results.FORGIVEN)

        self.assertBoardAttrEqual("breakpad_symbols_generated", True)
        self.assertBoardAttrEqual("debug_tarball_generated", True)

    def testUploadCrashUploadsList(self):
        """A crash in symbol upload should still post the failed list file."""
        self.upload_mock.side_effect = failures_lib.BuildScriptFailure(
            cros_build_lib.RunCommandError("mew"), "mew"
        )
        self._Prepare()
        stage = self.ConstructStage()

        with mock.patch.object(
            os.path, "exists"
        ) as mock_exists, mock.patch.object(
            artifact_stages.DebugSymbolsStage, "UploadArtifact"
        ) as mock_upload:
            mock_exists.return_value = True
            self.assertRaises(
                artifact_stages.DebugSymbolsUploadException,
                stage.UploadSymbols,
                stage._build_root,
                stage._current_board,
            )
            self.assertEqual(mock_exists.call_count, 1)
            self.assertEqual(mock_upload.call_count, 1)


class UploadTestArtifactsStageMock(
    generic_stages_unittest.ArchivingStageMixinMock
):
    """Partial mock for BuildImageStage."""

    TARGET = (
        "chromite.cbuildbot.stages.artifact_stages.UploadTestArtifactsStage"
    )
    ATTRS = generic_stages_unittest.ArchivingStageMixinMock.ATTRS + (
        "BuildAutotestTarballs",
        "BuildTastTarball",
    )

    def BuildAutotestTarballs(self, *args, **kwargs):
        with mock.patch.object(
            commands, "BuildTarball", autospec=True
        ), mock.patch.object(
            commands,
            "FindFilesWithPattern",
            autospec=True,
            return_value=["foo.txt"],
        ):
            self.backup["BuildAutotestTarballs"](*args, **kwargs)

    def BuildTastTarball(self, *args, **kwargs):
        with mock.patch.object(commands, "BuildTarball", autospec=True):
            self.backup["BuildTastTarball"](*args, **kwargs)


class UploadTestArtifactsStageTest(
    build_stages_unittest.AllConfigsTestCase,
    cbuildbot_unittest.SimpleBuilderTestCase,
):
    """Tests UploadTestArtifactsStage."""

    def setUp(self):
        self._release_tag = None

        osutils.SafeMakedirs(os.path.join(self.build_root, "chroot", "tmp"))
        self.StartPatcher(UploadTestArtifactsStageMock())
        self.buildstore = FakeBuildStore()

    def ConstructStage(self):
        return artifact_stages.UploadTestArtifactsStage(
            self._run, self.buildstore, self._current_board
        )

    def RunTestsWithBotId(self, bot_id, options_tests=True):
        """Test with the config for the specified bot_id."""
        self._Prepare(bot_id)
        self._run.options.tests = options_tests
        self._run.attrs.release_tag = "0.0.1"

        # Simulate images being ready.
        board_runattrs = self._run.GetBoardRunAttrs(self._current_board)
        board_runattrs.SetParallel("images_generated", True)

        generate_update_payloads_mock = self.PatchObject(
            commands, "GeneratePayloads"
        )

        with parallel_unittest.ParallelMock():
            with self.RunStageWithConfig():
                if (
                    self._run.config.upload_hw_test_artifacts
                    and self._run.config.images
                ):
                    self.assertNotEqual(
                        generate_update_payloads_mock.call_count, 0
                    )
                else:
                    self.assertEqual(
                        generate_update_payloads_mock.call_count, 0
                    )

    def testAllConfigs(self):
        """Test all major configurations"""
        self.RunAllConfigs(self.RunTestsWithBotId)
