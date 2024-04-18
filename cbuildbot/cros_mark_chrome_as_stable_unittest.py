# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for cros_mark_chrome_as_stable.py."""

import base64
import textwrap

from chromite.cbuildbot import cros_mark_chrome_as_stable
from chromite.lib import cros_test_lib
from chromite.lib import gob_util


class CrosMarkChromeAsStableTests(cros_test_lib.MockTestCase):
    """Tests for cros_mark_chrome_as_stable."""

    def testCheckIfChromeRightForOS(self):
        """Tests if we can find the chromeos build from our mock DEPS."""
        test_data1 = "buildspec_platforms:\n    'chromeos,',\n"
        test_data2 = "buildspec_platforms:\n    'android,',\n"
        expected_deps = cros_mark_chrome_as_stable.CheckIfChromeRightForOS(
            test_data1
        )
        unexpected_deps = cros_mark_chrome_as_stable.CheckIfChromeRightForOS(
            test_data2
        )
        self.assertTrue(expected_deps)
        self.assertFalse(unexpected_deps)

    def testGetLatestRelease(self):
        """Tests if we can find the latest release from our mock url data."""
        TEST_HOST = "sores.chromium.org"
        TEST_URL = "phthp://%s/tqs" % TEST_HOST
        TEST_TAGS = [
            "7.0.224.1",
            "7.0.224",
            "8.0.365.5",
            "foo",
            "bar-12.13.14.15",
        ]
        TEST_REFS_JSON = dict((tag, None) for tag in TEST_TAGS)
        TEST_BAD_DEPS_CONTENT = textwrap.dedent(
            """\
        buildspec_platforms: 'TRS-80,',
        """
        ).encode("utf-8")
        TEST_GOOD_DEPS_CONTENT = textwrap.dedent(
            """\
        buildspec_platforms: 'chromeos,',
        """
        ).encode("utf-8")

        self.PatchObject(
            gob_util,
            "FetchUrl",
            side_effect=(
                base64.b64encode(TEST_BAD_DEPS_CONTENT),
                base64.b64encode(TEST_GOOD_DEPS_CONTENT),
            ),
        )
        self.PatchObject(
            gob_util, "FetchUrlJson", side_effect=(TEST_REFS_JSON,)
        )
        release = cros_mark_chrome_as_stable.GetLatestRelease(TEST_URL)
        self.assertEqual("7.0.224.1", release)

    def testGetLatestStickyRelease(self):
        """Test we can find the latest sticky release from our mock url data."""
        TEST_HOST = "sores.chromium.org"
        TEST_URL = "phthp://%s/tqs" % TEST_HOST
        TEST_TAGS = [
            "7.0.224.2",
            "7.0.224",
            "7.0.365.5",
            "foo",
            "bar-12.13.14.15",
        ]
        TEST_REFS_JSON = dict((tag, None) for tag in TEST_TAGS)
        TEST_DEPS_CONTENT = textwrap.dedent(
            """\
        buildspec_platforms: 'chromeos,',
        """
        ).encode("utf-8")

        self.PatchObject(
            gob_util,
            "FetchUrl",
            side_effect=(base64.b64encode(TEST_DEPS_CONTENT),),
        )
        self.PatchObject(
            gob_util, "FetchUrlJson", side_effect=(TEST_REFS_JSON,)
        )
        release = cros_mark_chrome_as_stable.GetLatestRelease(
            TEST_URL, "7.0.224"
        )
        self.assertEqual("7.0.224.2", release)
