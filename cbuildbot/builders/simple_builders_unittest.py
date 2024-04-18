# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for simpler builders."""

import copy
import os

from chromite.cbuildbot import cbuildbot_run
from chromite.cbuildbot.builders import generic_builders
from chromite.cbuildbot.builders import simple_builders
from chromite.lib import config_lib
from chromite.lib import constants
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib.buildstore import FakeBuildStore
from chromite.scripts import cbuildbot


# pylint: disable=protected-access


class SimpleBuilderTest(cros_test_lib.MockTempDirTestCase):
    """Tests for the main code paths in simple_builders.SimpleBuilder"""

    def setUp(self):
        # List of all stages that would have been called as part of this run.
        self.called_stages = []

        # Map from stage class to exception to be raised when stage is run.
        self.stage_exceptions = {}

        self.buildstore = FakeBuildStore()

        # Simple new function that redirects RunStage to record all stages to be
        # run rather than mock them completely. These can be used in a test to
        # assert something has been called.
        def run_stage(_class_instance, stage_name, *_args, **_kwargs):
            self.called_stages.append(stage_name)
            if stage_name in self.stage_exceptions:
                raise self.stage_exceptions[stage_name]

        # Parallel version.
        def run_parallel_stages(_class_instance, *_args):
            # Since parallel stages are forked processes, we can't actually
            # update anything here unless we want to do interprocesses comms.
            pass

        self.buildroot = os.path.join(self.tempdir, "buildroot")
        chroot_path = os.path.join(self.buildroot, constants.DEFAULT_CHROOT_DIR)
        osutils.SafeMakedirs(os.path.join(chroot_path, "tmp"))

        self.PatchObject(generic_builders.Builder, "_RunStage", new=run_stage)
        self.PatchObject(
            simple_builders.SimpleBuilder,
            "_RunParallelStages",
            new=run_parallel_stages,
        )
        self.PatchObject(
            cbuildbot_run._BuilderRunBase,
            "GetVersion",
            return_value="R32-1234.0.0",
        )

        self._manager = parallel.Manager()
        # Pylint-1.9 has a false positive on this for some reason.
        self._manager.__enter__()  # pylint: disable=no-value-for-parameter

    def tearDown(self):
        # Mimic exiting a 'with' statement.
        self._manager.__exit__(None, None, None)

    def _initConfig(
        self,
        bot_id,
        master=False,
        extra_argv=None,
    ):
        """Return normal options/build_config for |bot_id|"""
        site_config = config_lib.GetConfig()
        build_config = copy.deepcopy(site_config[bot_id])
        build_config["master"] = master
        build_config["important"] = False

        # Use the cbuildbot parser to create properties and populate default
        # values.
        parser = cbuildbot._CreateParser()
        argv = (
            ["-r", self.buildroot, "--buildbot", "--debug"]
            + (extra_argv if extra_argv else [])
            + [bot_id]
        )
        options = cbuildbot.ParseCommandLine(parser, argv)

        # Yikes.
        options.managed_chrome = build_config["sync_chrome"]

        return cbuildbot_run.BuilderRun(
            options, site_config, build_config, self._manager
        )

    def testRunStagesDefaultBuild(self):
        """Verify RunStages for standard board builders"""
        builder_run = self._initConfig("amd64-generic-full")
        builder_run.attrs.chrome_version = "TheChromeVersion"
        simple_builders.SimpleBuilder(builder_run, self.buildstore).RunStages()
