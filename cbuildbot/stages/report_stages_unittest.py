# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for report stages."""

import datetime as dt
import json
from unittest import mock

import pytest  # pylint: disable=import-error

from chromite.cbuildbot import cbuildbot_alerts
from chromite.cbuildbot import cbuildbot_run
from chromite.cbuildbot import cbuildbot_unittest
from chromite.cbuildbot import commands
from chromite.cbuildbot import topology
from chromite.cbuildbot import topology_unittest
from chromite.cbuildbot.stages import generic_stages_unittest
from chromite.cbuildbot.stages import report_stages
from chromite.lib import alerts
from chromite.lib import buildstore
from chromite.lib import chromeos_version
from chromite.lib import cidb
from chromite.lib import constants
from chromite.lib import failure_message_lib_unittest
from chromite.lib import fake_cidb
from chromite.lib import gs_unittest
from chromite.lib import metrics
from chromite.lib import osutils
from chromite.lib import results_lib
from chromite.lib import retry_stats
from chromite.lib import toolchain
from chromite.utils import hostname_util


# pylint: disable=protected-access
# pylint: disable=too-many-ancestors


class BuildReexecutionStageTest(generic_stages_unittest.AbstractStageTestCase):
    """Tests that BuildReexecutionFinishedStage behaves as expected."""

    def setUp(self):
        self.fake_db = fake_cidb.FakeCIDBConnection()
        self.buildstore = buildstore.FakeBuildStore(self.fake_db)
        cidb.CIDBConnectionFactory.SetupMockCidb(self.fake_db)
        build_id = self.fake_db.InsertBuild(
            "builder name", 1, "build config", "bot hostname"
        )

        self._Prepare(build_id=build_id)

        release_tag = "4815.0.0-rc1"
        self._run.attrs.release_tag = "4815.0.0-rc1"
        fake_versioninfo = chromeos_version.VersionInfo(release_tag, "39")
        self.gs_mock = self.StartPatcher(gs_unittest.GSContextMock())
        self.gs_mock.SetDefaultCmdResult()
        self.PatchObject(
            cbuildbot_run._BuilderRunBase,
            "GetVersionInfo",
            return_value=fake_versioninfo,
        )
        self.PatchObject(toolchain, "get_toolchains_for_build_target")
        self.PatchObject(
            toolchain,
            "GetToolchainTupleForBoard",
            return_value=["i686-pc-linux-gnu", "arm-none-eabi"],
        )

    def tearDown(self):
        cidb.CIDBConnectionFactory.SetupMockCidb()

    def testPerformStage(self):
        """Test that a normal runs completes without error."""
        self.RunStage()
        tags = self._run.attrs.metadata.GetValue(constants.METADATA_TAGS)
        self.assertEqual(tags["version_full"], "R39-4815.0.0-rc1")

    def ConstructStage(self):
        return report_stages.BuildReexecutionFinishedStage(
            self._run, self.buildstore
        )


class ConfigDumpStageTest(generic_stages_unittest.AbstractStageTestCase):
    """Tests that ConfigDumpStage runs without syntax error."""

    def setUp(self):
        self.buildstore = buildstore.FakeBuildStore()

    def ConstructStage(self):
        return report_stages.ConfigDumpStage(self._run, self.buildstore)

    def testPerformStage(self):
        self._Prepare()
        self.RunStage()


class SlaveFailureSummaryStageTest(
    generic_stages_unittest.AbstractStageTestCase
):
    """Tests that SlaveFailureSummaryStage behaves as expected."""

    def setUp(self):
        self.db = mock.MagicMock()
        self.buildstore = buildstore.FakeBuildStore(self.db)
        cidb.CIDBConnectionFactory.SetupMockCidb(self.db)
        self._Prepare(build_id=1)

    # Our API here is not great when it comes to kwargs passing.
    def _Prepare(self, **kwargs):  # pylint: disable=arguments-differ
        """Prepare stage with config['master']=True."""
        super()._Prepare(**kwargs)
        self._run.config["master"] = True

    def ConstructStage(self):
        return report_stages.SlaveFailureSummaryStage(
            self._run, self.buildstore
        )

    def testPerformStage(self):
        """Tests that stage runs without syntax errors."""
        fake_failure = (
            failure_message_lib_unittest.StageFailureHelper.CreateStageFailure(
                build_id=10,
                build_stage_id=11,
                builder_name="builder_name",
                build_number=12,
                build_config="build-config",
                stage_name="FailingStage",
                stage_status=constants.BUILDER_STATUS_FAILED,
                build_status=constants.BUILDER_STATUS_FAILED,
            )
        )
        self.PatchObject(
            self.buildstore, "GetBuildsFailures", return_value=[fake_failure]
        )
        self.PatchObject(cbuildbot_alerts, "PrintBuildbotLink")
        self.RunStage()
        self.assertEqual(cbuildbot_alerts.PrintBuildbotLink.call_count, 1)


@pytest.mark.usefixtures("singleton_manager")
class BuildStartStageTest(generic_stages_unittest.AbstractStageTestCase):
    """Tests that BuildStartStage behaves as expected."""

    def setUp(self):
        self.db = fake_cidb.FakeCIDBConnection()
        self.buildstore = buildstore.FakeBuildStore(self.db)
        cidb.CIDBConnectionFactory.SetupMockCidb(self.db)
        retry_stats.SetupStats()

        master_build_id = self.db.InsertBuild(
            "master_build", 1, "master_build_config", "bot_hostname"
        )

        self.PatchObject(toolchain, "get_toolchains_for_build_target")
        self.PatchObject(toolchain, "GetArchForTarget", return_value="x86")

        self._Prepare(build_id=None, master_build_id=master_build_id)

    def testPerformStage(self):
        """Test that a normal run of the stage does a database insert."""
        self.RunStage()

        build_id = self._run.attrs.metadata.GetValue("build_id")
        self.assertGreater(build_id, 0)
        self.assertEqual(
            self._run.attrs.metadata.GetValue("db_type"),
            cidb.CONNECTION_TYPE_MOCK,
        )

    def testSuiteSchedulingEqualsFalse(self):
        """Test that a run of the stage makes suite_scheduling False."""
        # Test suite_scheduling for **-paladin
        self._Prepare(bot_id="amd64-generic-full")
        self.RunStage()
        self.assertFalse(self._run.attrs.metadata.GetValue("suite_scheduling"))

    def testSuiteSchedulingEqualsTrue(self):
        """Test that a run of the stage makes suite_scheduling True."""
        # Test suite_scheduling for **-release
        self._Prepare(bot_id="eve-release")
        self.RunStage()
        self.assertTrue(self._run.attrs.metadata.GetValue("suite_scheduling"))

    def testHandleSkipWithInstanceChange(self):
        """Test that HandleSkip disables cidb and dies when necessary."""
        # This test verifies that switching to a 'mock' database type once
        # metadata already has an id in 'previous_db_type' will fail.
        self._run.attrs.metadata.UpdateWithDict(
            {"build_id": 31337, "db_type": "previous_db_type"}
        )
        stage = self.ConstructStage()
        self.assertRaises(AssertionError, stage.HandleSkip)
        self.assertEqual(
            cidb.CIDBConnectionFactory.GetCIDBConnectionType(),
            cidb.CONNECTION_TYPE_INV,
        )
        # The above test has the side effect of invalidating
        # CIDBConnectionFactory. Undo that side effect so other unit tests can
        # run.
        cidb.CIDBConnectionFactory.SetupMockCidb()

    def testHandleSkipWithNoDbType(self):
        """Test that HandleSkip passes when db_type is missing."""
        self._run.attrs.metadata.UpdateWithDict({"build_id": 31337})
        stage = self.ConstructStage()
        stage.HandleSkip()

    def testHandleSkipWithDbType(self):
        """Test that HandleSkip passes when db_type is specified."""
        self._run.attrs.metadata.UpdateWithDict(
            {"build_id": 31337, "db_type": cidb.CONNECTION_TYPE_MOCK}
        )
        stage = self.ConstructStage()
        stage.HandleSkip()

    def ConstructStage(self):
        return report_stages.BuildStartStage(self._run, self.buildstore)


class AbstractReportStageTestCase(
    generic_stages_unittest.AbstractStageTestCase,
    cbuildbot_unittest.SimpleBuilderTestCase,
):
    """Base class for testing the Report stage."""

    def setUp(self):
        for cmd in (
            (osutils, "WriteFile"),
            (commands, "UploadArchivedFile"),
            (alerts, "SendEmail"),
        ):
            self.StartPatcher(mock.patch.object(*cmd, autospec=True))
        retry_stats.SetupStats()

        self.PatchObject(
            report_stages.ReportStage, "_GetBuildDuration", return_value=1000
        )
        self.PatchObject(toolchain, "get_toolchains_for_build_target")
        self.PatchObject(toolchain, "GetArchForTarget", return_value="x86")

        # Set up a general purpose cidb mock. Tests with more specific
        # mock requirements can replace this with a separate call to
        # SetupMockCidb
        self.mock_cidb = mock.MagicMock()
        self.buildstore = buildstore.FakeBuildStore(self.mock_cidb)
        cidb.CIDBConnectionFactory.SetupMockCidb(self.mock_cidb)

        # Setup topology for unittests
        keyvals = {topology.DATASTORE_WRITER_CREDS_KEY: "./foo/bar.cert"}
        topology_unittest.FakeFetchTopology(keyvals=keyvals)

        self._Prepare()

    def ConstructStage(self):
        return report_stages.ReportStage(self._run, self.buildstore, None)


@pytest.mark.usefixtures("singleton_manager")
class ReportStageTest(AbstractReportStageTestCase):
    """Test the Report stage."""

    RELEASE_TAG = ""

    def setUp(self):
        self.mock_cidb.GetSlaveStatuses = mock.Mock(return_value=None)

    def testCheckResults(self):
        """Basic sanity check for results stage functionality"""
        self.CreateMockOverlay("amd64-generic")

        stages = [
            {
                "build_config": "build1",
                "name": "stage1",
                "start_time": dt.datetime.now() - dt.timedelta(0, 500),
                "finish_time": dt.datetime.now() - dt.timedelta(0, 300),
                "status": constants.BUILDER_STATUS_PASSED,
            },
            {
                "build_config": "build1",
                "name": "stage2",
                "start_time": dt.datetime.now() - dt.timedelta(0, 500),
                "finish_time": dt.datetime.now() - dt.timedelta(0, 200),
                "status": constants.BUILDER_STATUS_PASSED,
            },
            {
                "build_config": "build1",
                "name": "stage3",
                "start_time": dt.datetime.now() - dt.timedelta(0, 200),
                "finish_time": dt.datetime.now() - dt.timedelta(0, 100),
                "status": constants.BUILDER_STATUS_PASSED,
            },
        ]
        statuses = [
            {
                "build_config": "build1",
                "build_number": "64",
                "start_time": dt.datetime.now() - dt.timedelta(0, 600),
                "finish_time": dt.datetime.now() - dt.timedelta(0, 330),
                "status": constants.BUILDER_STATUS_PASSED,
            },
            {
                "build_config": "build2",
                "build_number": "27",
                "start_time": dt.datetime.now() - dt.timedelta(0, 300),
                "finish_time": dt.datetime.now() - dt.timedelta(0, 100),
                "status": constants.BUILDER_STATUS_PASSED,
            },
            {
                "build_config": "build3",
                "build_number": "288282",
                "start_time": dt.datetime.now() - dt.timedelta(0, 400),
                "finish_time": dt.datetime.now() - dt.timedelta(0, 200),
                "status": constants.BUILDER_STATUS_PASSED,
            },
        ]
        self.buildstore.GetBuildsStages = mock.Mock(return_value=stages)
        self.mock_cidb.GetSlaveStatuses = mock.Mock(return_value=statuses)
        self.PatchObject(report_stages.ReportStage, "_LinkArtifacts")
        self.RunStage()
        filenames = (
            "LATEST-%s" % self.TARGET_MANIFEST_BRANCH,
            "LATEST-%s" % self.VERSION,
        )
        calls = [
            mock.call(
                mock.ANY,
                mock.ANY,
                "metadata.json",
                False,
                update_list=True,
                acl=mock.ANY,
            )
        ]
        calls += [
            mock.call(mock.ANY, mock.ANY, filename, False, acl=mock.ANY)
            for filename in filenames
        ]

    def testDoNotUpdateLATESTMarkersWhenBuildFailed(self):
        """Check that we do not update the latest markers on failed build."""
        self.PatchObject(report_stages.ReportStage, "_LinkArtifacts")
        self.PatchObject(
            results_lib.Results, "BuildSucceededSoFar", return_value=False
        )
        stage = self.ConstructStage()
        self.PatchObject(stage, "GetBuildFailureMessage")
        stage.Run()
        calls = [
            mock.call(
                mock.ANY,
                mock.ANY,
                "metadata.json",
                False,
                update_list=True,
                acl=mock.ANY,
            )
        ]
        self.assertEqual(calls, commands.UploadArchivedFile.call_args_list)

    def testWriteBasicMetadata(self):
        """Test that WriteBasicMetadata writes expected keys correctly."""
        report_stages.WriteBasicMetadata(self._run)
        metadata_dict = self._run.attrs.metadata.GetDict()
        self.assertEqual(
            metadata_dict["build-number"],
            generic_stages_unittest.DEFAULT_BUILD_NUMBER,
        )
        self.assertIn("builder-name", metadata_dict)
        self.assertIn("bot-hostname", metadata_dict)

    def testWriteTagMetadata(self):
        """Test that WriteTagMetadata writes expected keys correctly."""
        self.PatchObject(
            hostname_util, "get_host_name", return_value="cros-wimpy2"
        )
        report_stages.WriteTagMetadata(self._run)
        tags_dict = self._run.attrs.metadata.GetValue(constants.METADATA_TAGS)
        self.assertEqual(
            tags_dict["build_number"],
            generic_stages_unittest.DEFAULT_BUILD_NUMBER,
        )
        self.assertIn("builder_name", tags_dict)
        self.assertIn("bot_hostname", tags_dict)
        self.RunStage()
        tags_content = osutils.WriteFile.call_args_list[0][0][1]
        tags_content_dict = json.loads(tags_content)["tags"]
        self.assertEqual(
            tags_content_dict["build_number"],
            generic_stages_unittest.DEFAULT_BUILD_NUMBER,
        )

    def testPerformStage(self):
        """Test PerformStage."""
        mock_sd = self.PatchObject(metrics, "CumulativeSecondsDistribution")
        self.PatchObject(report_stages.ReportStage, "ArchiveResults")
        stage = self.ConstructStage()
        stage.PerformStage()
        self.assertEqual(mock_sd.call_count, 1)


@pytest.mark.usefixtures("singleton_manager")
class ReportStageNoSyncTest(AbstractReportStageTestCase):
    """Test the Report stage if SyncStage didn't complete.

    If SyncStage doesn't complete, we don't know the release tag, and can't
    archive results.
    """

    RELEASE_TAG = None

    def testCommitQueueResults(self):
        """Check that we can run with a RELEASE_TAG of None."""
        self.RunStage()
