# Copyright 2016 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for scheduler stages."""

from unittest import mock

from chromite.cbuildbot import cbuildbot_run
from chromite.cbuildbot.stages import generic_stages_unittest
from chromite.cbuildbot.stages import scheduler_stages
from chromite.lib import cidb
from chromite.lib import config_lib
from chromite.lib import fake_cidb
from chromite.lib.buildstore import FakeBuildStore


class ScheduleSlavesStageTest(generic_stages_unittest.AbstractStageTestCase):
    """Unit tests for ScheduleSalvesStage."""

    BOT_ID = "master-release"

    def setUp(self):
        # pylint: disable=protected-access
        self.PatchObject(
            cbuildbot_run._BuilderRunBase,
            "GetVersion",
            return_value="R84-13099.77.0",
        )
        # Create and set up a fake cidb instance.
        self.fake_db = fake_cidb.FakeCIDBConnection()
        cidb.CIDBConnectionFactory.SetupMockCidb(self.fake_db)

        self.sync_stage = mock.Mock()
        self._Prepare()

    def ConstructStage(self):
        bs = FakeBuildStore()
        return scheduler_stages.ScheduleSlavesStage(
            self._run, bs, self.sync_stage
        )

    def testRequestBuild(self):
        config = config_lib.BuildConfig(
            name="child",
            important=True,
            display_label="cq",
            boards=["board_A"],
            build_type="paladin",
        )

        stage = self.ConstructStage()
        # pylint: disable=protected-access
        request = stage._CreateScheduledBuild(
            "child", config, 0, "master_bb_0", None
        )
        self.assertEqual(request.build_config, "child")
        self.assertEqual(request.master_buildbucket_id, "master_bb_0")
        self.assertEqual(
            request.extra_args,
            ["--buildbot", "--master-buildbucket-id", "master_bb_0"],
        )

    def testRequestBuildWithSnapshotRev(self):
        config = config_lib.BuildConfig(
            name="child",
            important=True,
            display_label="cq",
            boards=["board_A"],
            build_type="paladin",
        )

        stage = self.ConstructStage()
        # Set the annealing snapshot revision to pass to the child builders.
        # pylint: disable=protected-access
        stage._run.options.cbb_snapshot_revision = "hash1234"
        request = stage._CreateScheduledBuild(
            "child", config, 0, "master_bb_1", None
        )
        self.assertEqual(request.build_config, "child")
        self.assertEqual(request.master_buildbucket_id, "master_bb_1")
        expected_extra_args = [
            "--buildbot",
            "--master-buildbucket-id",
            "master_bb_1",
            "--cbb_snapshot_revision",
            "hash1234",
        ]
        self.assertEqual(request.extra_args, expected_extra_args)

    def testPostSlaveBuildToBuildbucket(self):
        """Test PostSlaveBuildToBuildbucket on builds with a single board."""
        slave_config = config_lib.BuildConfig(
            name="slave",
            important=True,
            display_label="cq",
            boards=["board_A"],
            build_type="paladin",
        )

        stage = self.ConstructStage()

        buildbucket_id, created_ts = stage.PostSlaveBuildToBuildbucket(
            "slave", slave_config, 0, "master_bb_id", dryrun=True
        )

        self.assertEqual(buildbucket_id, "0")
        self.assertEqual(created_ts, "1")
