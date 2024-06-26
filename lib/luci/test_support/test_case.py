# Copyright 2018 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This file is heavily based off of LUCI test_support/test_case.py."""

import datetime

from chromite.lib.luci import utils
from chromite.lib.luci.test_support import auto_stub


def mock_now(test, now, seconds):
    """Mocks utcnow().

    In particular handles when auto_now and auto_now_add are used.
    """
    now = now + datetime.timedelta(seconds=seconds)
    test.mock(utils, "utcnow", lambda: now)
    return now


class TestCase(auto_stub.TestCase):
    """Support class to enable more unit testing."""

    def set_up(self):
        """Initializes the commonly used stubs.

        Using init_all_stubs() costs ~10ms more to run all the tests so only
        enable the ones known to be required. Test cases requiring more stubs
        can enable them in their setUp() function.
        """
        super().setUp()

    def tear_down(self):
        super().tearDown()

    def mock_now(self, now, seconds=0):
        return mock_now(self, now, seconds)
