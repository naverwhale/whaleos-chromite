# Copyright 2014 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for the namespaces.py module."""

import builtins
import errno
import os
import unittest

from chromite.lib import commandline
from chromite.lib import cros_test_lib
from chromite.lib import namespaces
from chromite.lib import process_util
from chromite.utils import os_util


class SetNSTests(cros_test_lib.TestCase):
    """Tests for SetNS()"""

    def testBasic(self):
        """Simple functionality test."""
        NS_PATH = "/proc/self/ns/mnt"
        if not os.path.exists(NS_PATH):
            raise unittest.SkipTest("kernel too old (missing %s)" % NS_PATH)

        with open(NS_PATH, encoding="utf-8") as f:
            try:
                namespaces.SetNS(f.fileno(), 0)
            except OSError as e:
                if e.errno != errno.EPERM:
                    # Running as non-root will fail, so ignore it.  We ran most
                    # of the code in the process which is all we really wanted.
                    raise


class UnshareTests(cros_test_lib.TestCase):
    """Tests for Unshare()"""

    def testBasic(self):
        """Simple functionality test."""
        try:
            namespaces.Unshare(namespaces.CLONE_NEWNS)
        except OSError as e:
            if e.errno != errno.EPERM:
                # Running as non-root will fail, so ignore it.  We ran most
                # of the code in the process which is all we really wanted.
                raise


class UnshareCGroupsTests(cros_test_lib.TestCase):
    """Tests for Unshare() of CGroups"""

    def testBasic(self):
        """Simple functionality test."""
        try:
            namespaces.Unshare(namespaces.CLONE_NEWCGROUP)
            # After we have unshared cgroups, every cgroups entry in
            # /proc/self/cgroups should have a path that's root (ie "/").
            with open("/proc/self/cgroup", encoding="utf-8") as cgroups:
                for cgroup in cgroups:
                    self.assertRegex(cgroup, ":/\n$")
        except OSError as e:
            if e.errno != errno.EPERM:
                # Running as non-root will fail, so ignore it.  We ran most
                # of the code in the process which is all we really wanted.
                raise


class SimpleUnshareCgroupsTests(cros_test_lib.MockTestCase):
    """Tests for SimpleUnshare with cgroups."""

    def testSimpleUnshare(self):
        """Simple functionality test."""
        unshare_mock = self.PatchObject(namespaces, "Unshare")
        namespaces.SimpleUnshare(
            mount=False,
            uts=False,
            ipc=False,
            net=False,
            pid=False,
            cgroup=True,
        )
        unshare_mock.assert_called_once_with(namespaces.CLONE_NEWCGROUP)


class CreateUserNsTests(cros_test_lib.TestCase):
    """Tests for CreateUserNs()"""

    def testBasic(self):
        """Simple functionality test."""
        # Since entering namespaces will modify the state of the current
        # process, fork in advance.
        pid = os.fork()
        if pid == 0:
            # Below we call os._exit() to exit the process directly. It is one
            # of the officially justified usage of the function.
            # pylint: disable=protected-access
            try:
                # Enter a new user namespace. The current process will gain
                # capabilities within the namespace.
                namespaces.CreateUserNs()
            except Exception:
                os._exit(10)
            try:
                # Enter a new mount namespace. This operation requires
                # privileges, but we have one thanks to the user namespace.
                namespaces.Unshare(namespaces.CLONE_NEWNS)
            except Exception:
                os._exit(20)
            os._exit(0)

        status = os.waitpid(pid, 0)[1]
        self.assertEqual(process_util.GetExitStatus(status), 0)


class ReExecuteWithNamespaceTests(cros_test_lib.MockTestCase):
    """Tests for ReExecuteWithNamespace()."""

    def testReExecuteWithNamespace(self):
        """Verify SimpleUnshare is called and the non-root user is restored."""
        run_as_root_user_mock = self.PatchObject(commandline, "RunAsRootUser")
        simple_unshare_mock = self.PatchObject(namespaces, "SimpleUnshare")
        switch_mock = self.PatchObject(os_util, "switch_to_sudo_user")

        namespaces.ReExecuteWithNamespace([], preserve_env=True)

        run_as_root_user_mock.assert_called_once_with([], preserve_env=True)
        simple_unshare_mock.assert_called_once_with(net=True, pid=True)
        switch_mock.assert_called_once_with(clear_saved_id=False)

    def testClearSavedId(self):
        """Verify clear_saved_id works."""
        run_as_root_user_mock = self.PatchObject(commandline, "RunAsRootUser")
        simple_unshare_mock = self.PatchObject(namespaces, "SimpleUnshare")
        switch_mock = self.PatchObject(os_util, "switch_to_sudo_user")

        namespaces.ReExecuteWithNamespace(
            [], preserve_env=True, clear_saved_id=True
        )

        run_as_root_user_mock.assert_called_once_with([], preserve_env=True)
        simple_unshare_mock.assert_called_once_with(net=True, pid=True)
        switch_mock.assert_called_once_with(clear_saved_id=True)


class UseNetworkSandboxTests(cros_test_lib.MockTestCase):
    """Tests for the use_network_sandbox() context manager."""

    def testBasic(self):
        """Test context manager's baseline success case."""
        self.PatchObject(commandline, "RunAsRootUser")
        set_ns_mock = self.PatchObject(namespaces, "SetNS")
        simple_unshare_mock = self.PatchObject(namespaces, "SimpleUnshare")
        switch_mock = self.PatchObject(os_util, "switch_to_sudo_user")
        os_setresuid_mock = self.PatchObject(os, "setresuid")
        os_setresgid_mock = self.PatchObject(os, "setresgid")

        with namespaces.use_network_sandbox():
            simple_unshare_mock.assert_called_once_with(net=True, pid=True)
            switch_mock.assert_called_once()
            set_ns_mock.assert_not_called()
        os_setresuid_mock.assert_called_with(0, 0, -1)
        os_setresgid_mock.assert_called_with(0, 0, -1)
        set_ns_mock.assert_called_once()

    def testRaisedExceptionStillRestoresNetNS(self):
        """Test context manager cleanup if client code raises exception."""
        self.PatchObject(commandline, "RunAsRootUser")
        set_ns_mock = self.PatchObject(namespaces, "SetNS")
        simple_unshare_mock = self.PatchObject(namespaces, "SimpleUnshare")
        switch_mock = self.PatchObject(os_util, "switch_to_sudo_user")
        os_setresuid_mock = self.PatchObject(os, "setresuid")
        os_setresgid_mock = self.PatchObject(os, "setresgid")

        m = unittest.mock.Mock(side_effect=KeyboardInterrupt)

        with self.assertRaises(KeyboardInterrupt):
            with namespaces.use_network_sandbox():
                simple_unshare_mock.assert_called_once_with(net=True, pid=True)
                switch_mock.assert_called_once()
                set_ns_mock.assert_not_called()
                m()
        os_setresuid_mock.assert_called_with(0, 0, -1)
        os_setresgid_mock.assert_called_with(0, 0, -1)
        set_ns_mock.assert_called_once()

    def testNetworkRestorationFails(self):
        """Test exception behavior of finally block in context manager."""
        self.PatchObject(commandline, "RunAsRootUser")
        set_ns_mock = self.PatchObject(namespaces, "SetNS", side_effect=OSError)
        simple_unshare_mock = self.PatchObject(namespaces, "SimpleUnshare")
        switch_mock = self.PatchObject(os_util, "switch_to_sudo_user")
        os_setresuid_mock = self.PatchObject(os, "setresuid")
        os_setresgid_mock = self.PatchObject(os, "setresgid")

        with namespaces.use_network_sandbox():
            simple_unshare_mock.assert_called_once_with(net=True, pid=True)
            switch_mock.assert_called_once()
        os_setresuid_mock.assert_called_with(0, 0, -1)
        os_setresgid_mock.assert_called_with(0, 0, -1)
        set_ns_mock.assert_called_once()

    def testSimpleUnshareFails(self):
        """Test failure behavior of context manager's re-exec call."""
        self.PatchObject(commandline, "RunAsRootUser")
        set_ns_mock = self.PatchObject(namespaces, "SetNS")
        simple_unshare_mock = self.PatchObject(
            namespaces, "SimpleUnshare", side_effect=OSError
        )
        switch_mock = self.PatchObject(os_util, "switch_to_sudo_user")
        os_setresuid_mock = self.PatchObject(os, "setresuid")
        os_setresgid_mock = self.PatchObject(os, "setresgid")

        with namespaces.use_network_sandbox():
            simple_unshare_mock.assert_called_once_with(net=True, pid=True)
            switch_mock.assert_not_called()
            set_ns_mock.assert_not_called()
        os_setresuid_mock.assert_called_with(0, 0, -1)
        os_setresgid_mock.assert_called_with(0, 0, -1)
        set_ns_mock.assert_called_once()

    def testNetworkFileOpenFails(self):
        """Test failure behavior of context manager's early call to open()."""
        self.PatchObject(commandline, "RunAsRootUser")
        set_ns_mock = self.PatchObject(namespaces, "SetNS")
        simple_unshare_mock = self.PatchObject(namespaces, "SimpleUnshare")
        switch_mock = self.PatchObject(os_util, "switch_to_sudo_user")

        def mock_open(file, *args, **kwargs):
            if file == "/proc/self/ns/net":
                raise OSError
            else:
                return open(file, args, kwargs)

        self.PatchObject(builtins, "open", new=mock_open)

        with namespaces.use_network_sandbox():
            simple_unshare_mock.assert_called_once_with(net=True, pid=True)
            switch_mock.assert_called_once()
            set_ns_mock.assert_not_called()
        set_ns_mock.assert_not_called()
