# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module tests helpers in devserver_wrapper."""

from chromite.lib import cros_test_lib
from chromite.lib import dev_server_wrapper
from chromite.lib import partial_mock


pytestmark = cros_test_lib.pytestmark_inside_only


# pylint: disable=protected-access
class TestXbuddyHelpers(cros_test_lib.MockTempDirTestCase):
    """Test xbuddy helper functions."""


class TestGetIPv4Address(cros_test_lib.RunCommandTestCase):
    """Tests the GetIPv4Address function."""

    IP_GLOBAL_OUTPUT = """
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 16436 qdisc noqueue state UNKNOWN
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
2: eth0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc pfifo_fast state \
DOWN qlen 1000
    link/ether cc:cc:cc:cc:cc:cc brd ff:ff:ff:ff:ff:ff
3: eth1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast state UP \
qlen 1000
    link/ether dd:dd:dd:dd:dd:dd brd ff:ff:ff:ff:ff:ff
    inet 111.11.11.111/22 brd 111.11.11.255 scope global eth1
    inet6 cdef:0:cdef:cdef:cdef:cdef:cdef:cdef/64 scope global dynamic
       valid_lft 2592000sec preferred_lft 604800sec
"""

    def testGetIPv4AddressParseResult(self):
        """Verifies we can parse the output and get correct IP address."""
        self.rc.AddCmdResult(
            partial_mock.In("ip"), stdout=self.IP_GLOBAL_OUTPUT
        )
        self.assertEqual(dev_server_wrapper.GetIPv4Address(), "111.11.11.111")

    def testGetIPv4Address(self):
        """Tests that correct shell commmand is called."""
        dev_server_wrapper.GetIPv4Address(global_ip=False, dev="eth0")
        self.rc.assertCommandContains(
            ["ip", "addr", "show", "scope", "host", "dev", "eth0"]
        )

        dev_server_wrapper.GetIPv4Address(global_ip=True)
        self.rc.assertCommandContains(["ip", "addr", "show", "scope", "global"])
