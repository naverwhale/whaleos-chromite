# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for completion stages."""

from unittest import mock

from chromite.cbuildbot import manifest_version
from chromite.cbuildbot.stages import completion_stages
from chromite.cbuildbot.stages import generic_stages
from chromite.cbuildbot.stages import generic_stages_unittest
from chromite.cbuildbot.stages import sync_stages
from chromite.cbuildbot.stages import sync_stages_unittest
from chromite.lib import builder_status_lib
from chromite.lib import config_lib
from chromite.lib import constants
from chromite.lib.buildstore import FakeBuildStore


# pylint: disable=protected-access


class ManifestVersionedSyncCompletionStageTest(
    sync_stages_unittest.ManifestVersionedSyncStageTest
):
    """Tests the ManifestVersionedSyncCompletion stage."""

    # pylint: disable=abstract-method

    BOT_ID = "eve-release"

    def setUp(self):
        self.buildstore = FakeBuildStore()

    def testManifestVersionedSyncCompletedSuccess(self):
        """Tests basic ManifestVersionedSyncStageCompleted on success"""
        board_runattrs = self._run.GetBoardRunAttrs("eve")
        board_runattrs.SetParallel("success", True)
        update_status_mock = self.PatchObject(
            manifest_version.BuildSpecsManager, "UpdateStatus"
        )

        stage = completion_stages.ManifestVersionedSyncCompletionStage(
            self._run, self.buildstore, self.sync_stage, success=True
        )

        stage.Run()
        update_status_mock.assert_called_once_with(
            message=None, success_map={self.BOT_ID: True}
        )

    def testManifestVersionedSyncCompletedFailure(self):
        """Tests basic ManifestVersionedSyncStageCompleted on failure"""
        stage = completion_stages.ManifestVersionedSyncCompletionStage(
            self._run, self.buildstore, self.sync_stage, success=False
        )
        message = "foo"
        get_msg_mock = self.PatchObject(
            generic_stages.BuilderStage,
            "GetBuildFailureMessage",
            return_value=message,
        )
        update_status_mock = self.PatchObject(
            manifest_version.BuildSpecsManager, "UpdateStatus"
        )

        stage.Run()
        update_status_mock.assert_called_once_with(
            message="foo", success_map={self.BOT_ID: False}
        )
        get_msg_mock.assert_called_once_with()

    def testManifestVersionedSyncCompletedIncomplete(self):
        """Basic ManifestVersionedSyncStageCompleted on incomplete build."""
        stage = completion_stages.ManifestVersionedSyncCompletionStage(
            self._run, self.buildstore, self.sync_stage, success=False
        )
        stage.Run()

    def testGetBuilderSuccessMap(self):
        """Tests that the builder success map is properly created."""
        board_runattrs = self._run.GetBoardRunAttrs("eve")
        board_runattrs.SetParallel("success", True)
        builder_success_map = completion_stages.GetBuilderSuccessMap(
            self._run, True
        )
        expected_map = {self.BOT_ID: True}
        self.assertEqual(expected_map, builder_success_map)


class MasterSlaveSyncCompletionStageMockConfigTest(
    generic_stages_unittest.AbstractStageTestCase
):
    """Tests MasterSlaveSyncCompletionStage with ManifestVersionedSyncStage."""

    BOT_ID = "master"

    def setUp(self):
        self.source_repo = "ssh://source/repo"
        self.manifest_version_url = "fake manifest url"
        self.branch = "master"
        self.build_type = constants.PFQ_TYPE

        # Use our mocked out SiteConfig for all tests.
        self.test_config = self._GetTestConfig()
        self._Prepare(site_config=self.test_config)
        self.buildstore = FakeBuildStore()

    def ConstructStage(self):
        sync_stage = sync_stages.ManifestVersionedSyncStage(
            self._run, self.buildstore
        )
        return completion_stages.MasterSlaveSyncCompletionStage(
            self._run, self.buildstore, sync_stage, success=True
        )

    def _GetTestConfig(self):
        test_config = config_lib.SiteConfig()
        test_config.Add(
            "master",
            config_lib.BuildConfig(),
            boards=[],
            build_type=self.build_type,
            master=True,
            slave_configs=["test3", "test5"],
            manifest_version=True,
        )
        test_config.Add(
            "test1",
            config_lib.BuildConfig(),
            boards=["amd64-generic"],
            manifest_version=True,
            build_type=constants.PFQ_TYPE,
            overlays="public",
            important=False,
            chrome_rev=None,
            branch=False,
            internal=False,
            master=False,
        )
        test_config.Add(
            "test2",
            config_lib.BuildConfig(),
            boards=["amd64-generic"],
            manifest_version=False,
            build_type=constants.PFQ_TYPE,
            overlays="public",
            important=True,
            chrome_rev=None,
            branch=False,
            internal=False,
            master=False,
        )
        test_config.Add(
            "test3",
            config_lib.BuildConfig(),
            boards=["amd64-generic"],
            manifest_version=True,
            build_type=constants.PFQ_TYPE,
            overlays="both",
            important=True,
            chrome_rev=None,
            branch=False,
            internal=True,
            master=False,
        )
        test_config.Add(
            "test4",
            config_lib.BuildConfig(),
            boards=["amd64-generic"],
            manifest_version=True,
            build_type=constants.PFQ_TYPE,
            overlays="both",
            important=True,
            chrome_rev=None,
            branch=True,
            internal=True,
            master=False,
        )
        test_config.Add(
            "test5",
            config_lib.BuildConfig(),
            boards=["amd64-generic"],
            manifest_version=True,
            build_type=constants.PFQ_TYPE,
            overlays="public",
            important=True,
            chrome_rev=None,
            branch=False,
            internal=False,
            master=False,
        )
        return test_config

    def testGetSlavesForMaster(self):
        """Tests we get the slaves for a fake unified master configuration."""
        stage = self.ConstructStage()
        p = stage._GetSlaveConfigs()
        self.assertEqual(
            [self.test_config["test3"], self.test_config["test5"]], p
        )


class CanaryCompletionStageTest(generic_stages_unittest.AbstractStageTestCase):
    """Tests how canary master handles failures in CanaryCompletionStage."""

    BOT_ID = "master-release"

    # We duplicate __init__ to specify a default for bot_id.
    # pylint: disable=arguments-differ,useless-super-delegation
    def _Prepare(self, bot_id=BOT_ID, **kwargs):
        super()._Prepare(bot_id, **kwargs)

    def setUp(self):
        self.build_type = constants.CANARY_TYPE
        self._Prepare()
        self.buildstore = FakeBuildStore()

    def ConstructStage(self):
        """Returns a CanaryCompletionStage object."""
        sync_stage = sync_stages.ManifestVersionedSyncStage(
            self._run, self.buildstore
        )
        return completion_stages.CanaryCompletionStage(
            self._run, self.buildstore, sync_stage, success=True
        )

    def testGetBuilderStatusesFetcher(self):
        """Test GetBuilderStatusesFetcher."""
        mock_fetcher = mock.Mock()
        self.PatchObject(
            builder_status_lib,
            "BuilderStatusesFetcher",
            return_value=mock_fetcher,
        )
        mock_wait = self.PatchObject(
            completion_stages.MasterSlaveSyncCompletionStage,
            "_WaitForSlavesToComplete",
        )
        stage = self.ConstructStage()
        stage._run.attrs.manifest_manager = mock.Mock()

        self.assertEqual(stage._GetBuilderStatusesFetcher(), mock_fetcher)
        self.assertEqual(mock_wait.call_count, 1)
