# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for topology module."""

from chromite.cbuildbot import topology
from chromite.lib import cros_test_lib


class TopologyTest(cros_test_lib.TestCase):
    """Unit test of topology module."""

    def setUp(self):
        # Mutually isolate these tests and make them independent of
        # TOPOLOGY_DEFAULTS
        topology.topology = topology.LockedDefaultDict()

    def testNotFetched(self):
        with self.assertRaises(topology.LockedDictAccessException):
            topology.topology.get("/foo")


def FakeFetchTopology(keyvals=None):
    """Setup topology without the need for a DB

    Args:
        keyvals: optional dictionary to populate topology
    """
    keyvals = keyvals if keyvals is not None else {}

    topology.FetchTopology()
    topology.topology.update(keyvals)
    topology.topology.unlock()


class FakeFetchTopologyTest(cros_test_lib.TestCase):
    """Test FakeFetchTopologyunittest helper function"""

    def setUp(self):
        _resetTopology()

    def testFakeTopology(self):
        data = {1: "one", 2: "two", 3: "three"}
        FakeFetchTopology(data)
        self.assertGreaterEqual(topology.topology.items(), data.items())

    def testFakeTopologyEmpty(self):
        FakeFetchTopology()
        # pylint: disable=protected-access
        self.assertFalse(topology.topology._locked)


def _resetTopology():
    """Remove effects of unittests on topology"""
    topology.topology = topology.LockedDefaultDict()
    topology.topology.update(topology.TOPOLOGY_DEFAULTS)
