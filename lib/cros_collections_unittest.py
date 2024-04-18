# Copyright 2018 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the cros_collections module."""

import collections

from chromite.lib import cros_collections
from chromite.lib import cros_test_lib


class GroupNamedtuplesByKeyTests(cros_test_lib.TestCase):
    """Tests for GroupNamedtuplesByKey"""

    def testGroupNamedtuplesByKey(self):
        """Test GroupNamedtuplesByKey."""
        TestTuple = collections.namedtuple("TestTuple", ("key1", "key2"))
        r1 = TestTuple("t1", "val1")
        r2 = TestTuple("t2", "val2")
        r3 = TestTuple("t2", "val2")
        r4 = TestTuple("t3", "val3")
        r5 = TestTuple("t3", "val3")
        r6 = TestTuple("t3", "val3")
        input_iter = [r1, r2, r3, r4, r5, r6]

        expected_result = {"t1": [r1], "t2": [r2, r3], "t3": [r4, r5, r6]}
        self.assertDictEqual(
            cros_collections.GroupNamedtuplesByKey(input_iter, "key1"),
            expected_result,
        )

        expected_result = {"val1": [r1], "val2": [r2, r3], "val3": [r4, r5, r6]}
        self.assertDictEqual(
            cros_collections.GroupNamedtuplesByKey(input_iter, "key2"),
            expected_result,
        )

        expected_result = {None: [r1, r2, r3, r4, r5, r6]}
        self.assertDictEqual(
            cros_collections.GroupNamedtuplesByKey(input_iter, "test"),
            expected_result,
        )
