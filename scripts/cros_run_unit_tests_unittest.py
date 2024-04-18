# Copyright 2018 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for cros_run_unit_tests.py."""

import os

from chromite.lib import cros_test_lib
from chromite.scripts import cros_run_unit_tests


pytestmark = cros_test_lib.pytestmark_inside_only


class CrosRunUnitTestsTest(cros_test_lib.MockTestCase):
    """Tests for cros_run_unit_tests functions."""

    def testNonEmptyPackageSet(self):
        """Asserts that the deps of a known package are non-empty"""
        self.assertTrue(
            cros_run_unit_tests.determine_packages(
                "/", ("virtual/implicit-system",)
            )
        )

    def testGetKeepGoing(self):
        """Tests set keep_going option based on env virables"""
        self.PatchObject(os, "environ", new={"USE": "chrome_internal coverage"})
        keep_going = cros_run_unit_tests.get_keep_going()
        self.assertEqual(keep_going, True)
