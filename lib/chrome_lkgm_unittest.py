# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module tests the logic to find ChromeOS image version for a board."""

from chromite.lib import chrome_lkgm
from chromite.lib import cros_test_lib
from chromite.lib import gs
from chromite.lib import gs_unittest
from chromite.lib import partial_mock


class ChromeOSVersionFinderTest(
    gs_unittest.AbstractGSContextTest,
    cros_test_lib.MockTempDirTestCase,
    cros_test_lib.LoggingTestCase,
):
    """Tests the determination of which SDK version to use."""

    VERSION = "3543.0.0"
    FULL_VERSION = "R55-%s" % VERSION
    RECENT_VERSION_MISSING = "3542.0.0"
    RECENT_VERSION_FOUND = "3541.0.0"
    FULL_VERSION_RECENT = "R55-%s" % RECENT_VERSION_FOUND
    NON_CANARY_VERSION = "3543.2.1"
    FULL_VERSION_NON_CANARY = "R55-%s" % NON_CANARY_VERSION
    BOARD = "eve"

    VERSION_BASE = "gs://chromeos-image-archive/%s-release/LATEST-%s" % (
        BOARD,
        VERSION,
    )

    CAT_ERROR = "CommandException: No URLs matched %s" % VERSION_BASE

    def setUp(self):
        self.finder = chrome_lkgm.ChromeOSVersionFinder(
            self.tempdir, self.BOARD, 10
        )

    def testConfigName(self):
        """Test config_name contains the given board name."""
        self.assertTrue(self.BOARD in self.finder.config_name)

    def testFullVersionFromPlatformVersion(self):
        """Test full version calculation from the platform version."""
        self.gs_mock.AddCmdResult(
            partial_mock.ListRegex("cat .*/LATEST-%s" % self.VERSION),
            stdout=self.FULL_VERSION,
        )
        self.assertEqual(
            self.FULL_VERSION,
            self.finder.GetFullVersionFromLatest(self.VERSION),
        )

    def _SetupMissingVersions(self):
        """Version & Version-1 are missing, but Version-2 exists."""

        def _RaiseGSNoSuchKey(*_args, **_kwargs):
            raise gs.GSNoSuchKey("file does not exist")

        self.gs_mock.AddCmdResult(
            partial_mock.ListRegex("cat .*/LATEST-%s" % self.VERSION),
            side_effect=_RaiseGSNoSuchKey,
        )
        self.gs_mock.AddCmdResult(
            partial_mock.ListRegex(
                "cat .*/LATEST-%s" % self.RECENT_VERSION_MISSING
            ),
            side_effect=_RaiseGSNoSuchKey,
        )
        self.gs_mock.AddCmdResult(
            partial_mock.ListRegex(
                "cat .*/LATEST-%s" % self.RECENT_VERSION_FOUND
            ),
            stdout=self.FULL_VERSION_RECENT,
        )

    def testNoFallbackVersion(self):
        """Test that all versions are checked before returning None."""

        def _RaiseGSNoSuchKey(*_args, **_kwargs):
            raise gs.GSNoSuchKey("file does not exist")

        self.gs_mock.AddCmdResult(
            partial_mock.ListRegex("cat .*/LATEST-*"),
            side_effect=_RaiseGSNoSuchKey,
        )
        self.finder.fallback_versions = 2000000
        with cros_test_lib.LoggingCapturer() as logs:
            self.assertEqual(
                None, self.finder.GetFullVersionFromLatest(self.VERSION)
            )
        self.AssertLogsContain(logs, "LATEST-1.0.0")
        self.AssertLogsContain(logs, "LATEST--1.0.0", inverted=True)

    def testFallbackVersions(self):
        """Test full version calculation with various fallback versions."""
        self._SetupMissingVersions()
        for version in range(6):
            self.finder.fallback_versions = version
            # _SetupMissingVersions mocks the result of 3 files.
            # The file ending with LATEST-3.0.0 is the only one that would pass.
            self.assertEqual(
                self.FULL_VERSION_RECENT if version >= 3 else None,
                self.finder.GetFullVersionFromLatest(self.VERSION),
            )

    def testNonCanaryFullVersion(self):
        """Test full version calculation for a non canary version."""
        self.gs_mock.AddCmdResult(
            partial_mock.ListRegex(
                "cat .*/LATEST-%s" % self.NON_CANARY_VERSION
            ),
            stdout=self.FULL_VERSION_NON_CANARY,
        )
        self.assertEqual(
            self.FULL_VERSION_NON_CANARY,
            self.finder.GetFullVersionFromLatest(self.NON_CANARY_VERSION),
        )

    def testNonCanaryNoLatestVersion(self):
        """There is no matching latest non canary."""
        self.gs_mock.AddCmdResult(
            partial_mock.ListRegex(
                "cat .*/LATEST-%s" % self.NON_CANARY_VERSION
            ),
            stdout="",
            stderr=self.CAT_ERROR,
            returncode=1,
        )
        # Set any other query to return a valid version, but we don't expect
        # that to occur for non canary versions.
        self.gs_mock.SetDefaultCmdResult(stdout=self.FULL_VERSION_NON_CANARY)
        self.assertEqual(
            None, self.finder.GetFullVersionFromLatest(self.NON_CANARY_VERSION)
        )
