# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for workspace builders."""

import os
from unittest import mock

from chromite.cbuildbot import cbuildbot_run
from chromite.cbuildbot.builders import generic_builders
from chromite.cbuildbot.builders import workspace_builders
from chromite.cbuildbot.stages import branch_archive_stages
from chromite.cbuildbot.stages import workspace_stages
from chromite.config import chromeos_config
from chromite.lib import buildstore
from chromite.lib import config_lib
from chromite.lib import config_lib_unittest
from chromite.lib import cros_test_lib
from chromite.lib import parallel
from chromite.scripts import cbuildbot


# pylint: disable=protected-access


def CreateMockSiteConfig():
    """Create a mocked site_config object for workspace builds.

    Returns:
        SiteConfig instance with new configs on it.
    """
    site_config = config_lib_unittest.MockSiteConfig()
    production_config = config_lib.GetConfig()

    # Copy some templates from production.
    site_config.AddTemplate(
        "buildspec",
        production_config.templates.buildspec,
    )

    site_config.AddTemplate(
        "factorybranch",
        production_config.templates.factorybranch,
    )

    # Create test configs.
    site_config.Add(
        "buildspec",
        site_config.templates.buildspec,
        workspace_branch="test-branch",
    )

    buildspec_parent = site_config.Add(
        "buildspec-child",
        site_config.templates.buildspec,
        workspace_branch="test-branch",
    )

    buildspec_parent.AddSlaves(
        [
            site_config.Add(
                "test-factorybranch",
                site_config.templates.factorybranch,
                workspace_branch="test-branch",
                boards=["board"],
            ),
        ]
    )

    chromeos_config.TryjobMirrors(site_config)

    return site_config


class BuildspecBuilderTest(cros_test_lib.MockTempDirTestCase):
    """Tests for the main code paths in simple_builders.SimpleBuilder"""

    def setUp(self):
        self.buildstore = buildstore.FakeBuildStore()

        self.buildroot = os.path.join(self.tempdir, "buildroot")
        self.workspace = os.path.join(self.tempdir, "workspace")
        self.chroot_path = os.path.join(self.tempdir, "chroot")

        self._manager = parallel.Manager()
        # Pylint-1.9 has a false positive on this for some reason.
        self._manager.__enter__()  # pylint: disable=no-value-for-parameter

        self.site_config = CreateMockSiteConfig()

        self.mock_run_stage = self.PatchObject(
            generic_builders.Builder, "_RunStage"
        )

    def tearDown(self):
        # Mimic exiting a 'with' statement.
        self._manager.__exit__(None, None, None)

    def _InitConfig(self, bot_id, extra_argv=None):
        """Return normal options/build_config for |bot_id|"""
        build_config = self.site_config[bot_id]

        # Use the cbuildbot parser to create properties and populate default
        # values.
        parser = cbuildbot._CreateParser()
        argv = (
            [
                "--buildbot",
                "--buildroot",
                self.buildroot,
                "--workspace",
                self.workspace,
            ]
            + (extra_argv if extra_argv else [])
            + [bot_id]
        )
        options = cbuildbot.ParseCommandLine(parser, argv)
        cbuildbot._PostParseCheck(parser, options, self.site_config)

        return cbuildbot_run.BuilderRun(
            options, self.site_config, build_config, self._manager
        )

    def testBuildspec(self):
        """Verify RunStages for buildspec builder."""
        builder_run = self._InitConfig("buildspec")
        workspace_builders.BuildSpecBuilder(
            builder_run, self.buildstore
        ).RunStages()

        self.assertEqual(
            self.mock_run_stage.call_args_list,
            [
                mock.call(
                    workspace_stages.WorkspaceUprevStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspacePublishStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspacePublishBuildspecStage,
                    build_root=self.workspace,
                ),
            ],
        )

    def testBuildspecWithVersion(self):
        """Verify RunStages for buildspec with --version."""
        builder_run = self._InitConfig(
            "buildspec", extra_argv=["--version", "1.2.3"]
        )
        workspace_builders.BuildSpecBuilder(
            builder_run, self.buildstore
        ).RunStages()

        self.assertEqual(self.mock_run_stage.call_args_list, [])

    def testBuildspecChild(self):
        """Verify RunStages for buildspec with child configs."""
        builder_run = self._InitConfig("buildspec-child")
        workspace_builders.BuildSpecBuilder(
            builder_run, self.buildstore
        ).RunStages()

        self.assertEqual(
            self.mock_run_stage.call_args_list,
            [
                mock.call(
                    workspace_stages.WorkspaceUprevStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspacePublishStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspacePublishBuildspecStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceScheduleChildrenStage,
                    build_root=self.workspace,
                ),
            ],
        )

    def testBuildspecChildWithVersion(self):
        """Verify RunStages for buildspec with --version and child configs."""
        builder_run = self._InitConfig(
            "buildspec-child", extra_argv=["--version", "1.2.3"]
        )
        workspace_builders.BuildSpecBuilder(
            builder_run, self.buildstore
        ).RunStages()

        self.assertEqual(
            self.mock_run_stage.call_args_list,
            [
                mock.call(
                    workspace_stages.WorkspaceScheduleChildrenStage,
                    build_root=self.workspace,
                ),
            ],
        )

    def testFactoryBranch(self):
        """Verify RunStages for FactoryBranchBuilder."""
        builder_run = self._InitConfig("test-factorybranch")
        workspace_builders.FactoryBranchBuilder(
            builder_run, self.buildstore
        ).RunStages()

        self.assertEqual(
            self.mock_run_stage.call_args_list,
            [
                mock.call(
                    workspace_stages.WorkspaceUprevStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspacePublishStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspacePublishBuildspecStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceInitSDKStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceLinkMountPathsStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceUpdateSDKStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceSyncChromeStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceSetupBoardStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    workspace_stages.WorkspaceBuildPackagesStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    workspace_stages.WorkspaceUnitTestStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    workspace_stages.WorkspaceBuildImageStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    workspace_stages.WorkspaceDebugSymbolsStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    branch_archive_stages.FactoryArchiveStage,
                    build_root=self.workspace,
                    board="board",
                ),
            ],
        )

    def testFactoryBranchWithVersion(self):
        """Verify RunStages for FactoryBranchBuilder with --version."""
        builder_run = self._InitConfig(
            "test-factorybranch", extra_argv=["--version", "1.2.3"]
        )

        workspace_builders.FactoryBranchBuilder(
            builder_run, self.buildstore
        ).RunStages()

        self.assertEqual(
            self.mock_run_stage.call_args_list,
            [
                mock.call(
                    workspace_stages.WorkspaceInitSDKStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceLinkMountPathsStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceUpdateSDKStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceSyncChromeStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceSetupBoardStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    workspace_stages.WorkspaceBuildPackagesStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    workspace_stages.WorkspaceUnitTestStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    workspace_stages.WorkspaceBuildImageStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    workspace_stages.WorkspaceDebugSymbolsStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    branch_archive_stages.FactoryArchiveStage,
                    build_root=self.workspace,
                    board="board",
                ),
            ],
        )

    def testFactoryBranchTryjob(self):
        """Verify RunStages for FactoryBranchBuilder Tryjob."""
        builder_run = self._InitConfig("test-factorybranch-tryjob")
        workspace_builders.FactoryBranchBuilder(
            builder_run, self.buildstore
        ).RunStages()

        self.assertEqual(
            self.mock_run_stage.call_args_list,
            [
                mock.call(
                    workspace_stages.WorkspaceUprevStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceInitSDKStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceLinkMountPathsStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceUpdateSDKStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceSyncChromeStage,
                    build_root=self.workspace,
                ),
                mock.call(
                    workspace_stages.WorkspaceSetupBoardStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    workspace_stages.WorkspaceBuildPackagesStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    workspace_stages.WorkspaceUnitTestStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    workspace_stages.WorkspaceBuildImageStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    workspace_stages.WorkspaceDebugSymbolsStage,
                    build_root=self.workspace,
                    board="board",
                ),
                mock.call(
                    branch_archive_stages.FactoryArchiveStage,
                    build_root=self.workspace,
                    board="board",
                ),
            ],
        )
