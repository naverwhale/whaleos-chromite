# Copyright 2018 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test gen_luci_scheduler."""

from chromite.lib import config_lib
from chromite.lib import config_lib_unittest
from chromite.lib import cros_test_lib
from chromite.scripts import gen_luci_scheduler


# It's reasonable for unittests to look at internals.
# pylint: disable=protected-access


class GenLuciSchedulerTest(cros_test_lib.MockTestCase):
    """Tests for cbuildbot_launch script."""

    def testSanityAgainstProd(self):
        """Test we can generate a luci scheduler config with live data."""
        # If it runs without crashing, we pass.
        gen_luci_scheduler.genLuciSchedulerConfig(config_lib.GetConfig())

    def testGenSchedulerJob(self):
        """Test the job creation helper."""
        build_config = config_lib_unittest.MockBuildConfig().apply(
            schedule="funky schedule"
        )

        expected = """
job {
  id: "amd64-generic-release"
  realm: "cbb-jobs"
  acl_sets: "default"
  schedule: "funky schedule"
  buildbucket: {
    server: "cr-buildbucket.appspot.com"
    bucket: "general"
    builder: "LegacyRelease"
    tags: "cbb_branch:main"
    tags: "cbb_config:amd64-generic-release"
    tags: "cbb_display_label:MockLabel"
    properties: "cbb_branch:main"
    properties: "cbb_config:amd64-generic-release"
    properties: "cbb_display_label:MockLabel"
    properties: "cbb_extra_args:[\\"--buildbot\\"]"
  }
}
"""

        result = gen_luci_scheduler.genSchedulerJob(build_config)
        self.assertEqual(result, expected)

    def testGenSchedulerTriggerSimple(self):
        """Test the trigger creation helper."""
        trigger_name = "simple"
        repo = "url://repo"
        refs = ["refs/path"]
        path_regexps = ["path/regexps"]
        builds = ["test_build"]

        expected = """
trigger {
  id: "simple"
  realm: "cbb-jobs"
  acl_sets: "default"
  schedule: "with 5m interval"
  gitiles: {
    repo: "url://repo"
    refs: "refs/path"
    path_regexps: "path/regexps"
  }
  triggers: "test_build"
}
"""

        result = gen_luci_scheduler.genSchedulerTrigger(
            trigger_name, repo, refs, path_regexps, builds
        )

        self.assertEqual(result, expected)

    def testGenSchedulerTriggerComplex(self):
        """Test the trigger creation helper."""
        trigger_name = "complex"
        repo = "url://repo"
        refs = ["refs/path", "refs/other_path"]
        builds = ["test_build_a", "test_build_b"]

        expected = """
trigger {
  id: "complex"
  realm: "cbb-jobs"
  acl_sets: "default"
  schedule: "with 5m interval"
  gitiles: {
    repo: "url://repo"
    refs: "refs/path"
    refs: "refs/other_path"
  }
  triggers: "test_build_a"
  triggers: "test_build_b"
}
"""

        result = gen_luci_scheduler.genSchedulerTrigger(
            trigger_name, repo, refs, None, builds
        )

        self.assertEqual(result, expected)

    def testGenSchedulerBranched(self):
        """Test the job creation helper."""
        build_config = config_lib_unittest.MockBuildConfig().apply(
            schedule_branch="mock_branch",
            schedule="funky schedule",
        )

        expected = """
job {
  id: "mock_branch-amd64-generic-release"
  realm: "cbb-jobs"
  acl_sets: "default"
  schedule: "funky schedule"
  buildbucket: {
    server: "cr-buildbucket.appspot.com"
    bucket: "general"
    builder: "LegacyRelease"
    tags: "cbb_branch:mock_branch"
    tags: "cbb_config:amd64-generic-release"
    tags: "cbb_display_label:MockLabel"
    properties: "cbb_branch:mock_branch"
    properties: "cbb_config:amd64-generic-release"
    properties: "cbb_display_label:MockLabel"
    properties: "cbb_extra_args:[\\"--buildbot\\"]"
  }
}
"""

        result = gen_luci_scheduler.genSchedulerJob(build_config)
        self.assertEqual(result, expected)

    def testGenSchedulerWorkspaceBranch(self):
        """Test the job creation helper."""
        build_config = config_lib_unittest.MockBuildConfig().apply(
            workspace_branch="work_branch",
            schedule="funky schedule",
        )

        expected = """
job {
  id: "amd64-generic-release"
  realm: "cbb-jobs"
  acl_sets: "default"
  schedule: "funky schedule"
  buildbucket: {
    server: "cr-buildbucket.appspot.com"
    bucket: "general"
    builder: "LegacyRelease"
    tags: "cbb_branch:main"
    tags: "cbb_config:amd64-generic-release"
    tags: "cbb_display_label:MockLabel"
    tags: "cbb_workspace_branch:work_branch"
    properties: "cbb_branch:main"
    properties: "cbb_config:amd64-generic-release"
    properties: "cbb_display_label:MockLabel"
    properties: "cbb_workspace_branch:work_branch"
    properties: "cbb_extra_args:[\\"--buildbot\\"]"
  }
}
"""

        result = gen_luci_scheduler.genSchedulerJob(build_config)
        self.assertEqual(result, expected)

    def testGenLuciSchedulerConfig(self):
        """Test a full LUCI Scheduler config file."""
        site_config = config_lib.SiteConfig()

        site_config.Add(
            "not_scheduled",
            luci_builder="ReleaseBuilder",
            display_label="MockLabel",
        )

        site_config.Add(
            "build_prod",
            luci_builder="ReleaseBuilder",
            display_label="MockLabel",
            schedule="run once in a while",
        )

        site_config.Add(
            "build_tester",
            luci_builder="TestBuilder",
            display_label="TestLabel",
            schedule="run daily",
        )

        site_config.Add(
            "build_triggered_a",
            luci_builder="ReleaseBuilder",
            display_label="MockLabel",
            schedule="triggered",
            triggered_gitiles=[
                [
                    "gitiles_url_a",
                    ["ref_a", "ref_b"],
                ],
                [
                    "gitiles_url_b",
                    ["ref_c"],
                ],
            ],
        )

        site_config.Add(
            "build_triggered_b",
            luci_builder="ProdBuilder",
            display_label="MockLabel",
            schedule="triggered",
            triggered_gitiles=[
                [
                    "gitiles_url_b",
                    ["ref_c"],
                ]
            ],
        )

        expected = """# Defines buckets on luci-scheduler.appspot.com.
#
# For schema of this file and documentation see ProjectConfig message in
# https://github.com/luci/luci-go/blob/HEAD/scheduler/appengine/messages/config.proto

# Generated with chromite/scripts/gen_luci_scheduler

# Autodeployed with:
# https://data.corp.google.com/sites/chromeos_ci_cros_ci_builds/utility/?f=board_name:in:luci-scheduler-updater

acl_sets {
  name: "default"
  acls {
    role: READER
    granted_to: "group:googlers"
  }
  acls {
    role: OWNER
    granted_to: "group:project-chromeos-admins"
  }
  acls {
    role: TRIGGERER
    granted_to: "group:mdb/chromeos-build-access"
  }
  acls {
    role: TRIGGERER
    granted_to: "group:project-chromeos-buildbucket-schedulers"
  }
}

trigger {
  id: "trigger_0"
  realm: "cbb-jobs"
  acl_sets: "default"
  schedule: "with 5m interval"
  gitiles: {
    repo: "gitiles_url_a"
    refs: "ref_a"
    refs: "ref_b"
  }
  triggers: "build_triggered_a"
}

trigger {
  id: "trigger_1"
  realm: "cbb-jobs"
  acl_sets: "default"
  schedule: "with 5m interval"
  gitiles: {
    repo: "gitiles_url_b"
    refs: "ref_c"
  }
  triggers: "build_triggered_a"
  triggers: "build_triggered_b"
}

job {
  id: "build_prod"
  realm: "cbb-jobs"
  acl_sets: "default"
  schedule: "run once in a while"
  buildbucket: {
    server: "cr-buildbucket.appspot.com"
    bucket: "general"
    builder: "ReleaseBuilder"
    tags: "cbb_branch:main"
    tags: "cbb_config:build_prod"
    tags: "cbb_display_label:MockLabel"
    properties: "cbb_branch:main"
    properties: "cbb_config:build_prod"
    properties: "cbb_display_label:MockLabel"
    properties: "cbb_extra_args:[\\"--buildbot\\"]"
  }
}

job {
  id: "build_tester"
  realm: "cbb-jobs"
  acl_sets: "default"
  schedule: "run daily"
  buildbucket: {
    server: "cr-buildbucket.appspot.com"
    bucket: "general"
    builder: "TestBuilder"
    tags: "cbb_branch:main"
    tags: "cbb_config:build_tester"
    tags: "cbb_display_label:TestLabel"
    properties: "cbb_branch:main"
    properties: "cbb_config:build_tester"
    properties: "cbb_display_label:TestLabel"
    properties: "cbb_extra_args:[\\"--buildbot\\"]"
  }
}

job {
  id: "build_triggered_a"
  realm: "cbb-jobs"
  acl_sets: "default"
  schedule: "triggered"
  buildbucket: {
    server: "cr-buildbucket.appspot.com"
    bucket: "general"
    builder: "ReleaseBuilder"
    tags: "cbb_branch:main"
    tags: "cbb_config:build_triggered_a"
    tags: "cbb_display_label:MockLabel"
    properties: "cbb_branch:main"
    properties: "cbb_config:build_triggered_a"
    properties: "cbb_display_label:MockLabel"
    properties: "cbb_extra_args:[\\"--buildbot\\"]"
  }
}

job {
  id: "build_triggered_b"
  realm: "cbb-jobs"
  acl_sets: "default"
  schedule: "triggered"
  buildbucket: {
    server: "cr-buildbucket.appspot.com"
    bucket: "general"
    builder: "ProdBuilder"
    tags: "cbb_branch:main"
    tags: "cbb_config:build_triggered_b"
    tags: "cbb_display_label:MockLabel"
    properties: "cbb_branch:main"
    properties: "cbb_config:build_triggered_b"
    properties: "cbb_display_label:MockLabel"
    properties: "cbb_extra_args:[\\"--buildbot\\"]"
  }
}
"""
        result = gen_luci_scheduler.genLuciSchedulerConfig(site_config)

        self.assertEqual(result, expected)
