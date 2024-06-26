# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the remote_access module."""

import collections
import os
from pathlib import Path

from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import partial_mock
from chromite.lib import remote_access


# pylint: disable=protected-access


class TestNormalizePort(cros_test_lib.TestCase):
    """Verifies we normalize port."""

    def testNormalizePortStrOK(self):
        """Tests that string will be converted to integer."""
        self.assertEqual(remote_access.NormalizePort("123"), 123)

    def testNormalizePortStrNotOK(self):
        """Tests that error is raised if port is string and str_ok=False."""
        self.assertRaises(
            ValueError, remote_access.NormalizePort, "123", str_ok=False
        )

    def testNormalizePortOutOfRange(self):
        """Tests that error is raised when port is out of range."""
        self.assertRaises(ValueError, remote_access.NormalizePort, "-1")
        self.assertRaises(ValueError, remote_access.NormalizePort, 99999)


class TestRemoveKnownHost(cros_test_lib.MockTempDirTestCase):
    """Verifies RemoveKnownHost() functionality."""

    # ssh-keygen doesn't check for a valid hostname so use something that won't
    # be in the user's known_hosts to avoid changing their file contents.
    _HOST = remote_access.TEST_IP

    _HOST_KEY = (
        _HOST
        + " ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCjysPTaDAtRaxRaW1JjqzCHp2"
        "88gvlUgtJxd2Jt/v63fkqZ5zzLLoeoAMwv0oYSRU82qhLimXpHxXRkrMC5nrpz5zJch+"
        "ktql0rSRgo+dqc1GzmyOOAq5NkQsgBb3hefxMxCZRV8Dv0n7qaindZRxE8MnRJmVUoj8W"
        "q8wryabp+fUBkesBwaJhPXa4WBJeI5d+rO5tEBSNkvIp0USU6Ku3Ct0q2sZbOkY5g1VF"
        "AUYm4wyshCfoWvU8ivMFp0pCezMISGstKpkIQApq2dLUb6EmeIgnhHzZXOn7doxIGD33J"
        "UfFmwNi0qfk3vV6vKRVDEZD68+ix6gjKpicY5upA/9P\n"
    )

    def testRemoveKnownHostDefaultFile(self):
        """Tests RemoveKnownHost() on the default known_hosts file.

        `ssh-keygen -R` on its own fails when run from within the chroot
        since the default known_hosts is bind mounted.
        """
        # It doesn't matter if known_hosts actually has this host in it or not,
        # this test just makes sure the command doesn't fail. The default
        # known_hosts file always exists in the chroot due to the bind mount.
        remote_access.RemoveKnownHost(self._HOST)

    def testRemoveKnownHostCustomFile(self):
        """Tests RemoveKnownHost() on a custom known_hosts file."""
        path = os.path.join(self.tempdir, "known_hosts")
        osutils.WriteFile(path, self._HOST_KEY)
        remote_access.RemoveKnownHost(self._HOST, known_hosts_path=path)
        self.assertEqual(osutils.ReadFile(path), "")

    def testRemoveKnownHostNonexistentFile(self):
        """Tests RemoveKnownHost() on a nonexistent known_hosts file."""
        path = os.path.join(self.tempdir, "known_hosts")
        remote_access.RemoveKnownHost(self._HOST, known_hosts_path=path)


class TestCompileSSHConnectSettings(cros_test_lib.TestCase):
    """Verifies CompileSSHConnectSettings()."""

    def testCustomSettingIncluded(self):
        """Tests that a custom setting will be included in the output."""
        self.assertIn(
            "-oNumberOfPasswordPrompts=100",
            remote_access.CompileSSHConnectSettings(
                NumberOfPasswordPrompts=100
            ),
        )

    def testNoneSettingOmitted(self):
        """Verify a None value will omit a default setting from the output."""
        self.assertIn("-oProtocol=2", remote_access.CompileSSHConnectSettings())
        self.assertNotIn(
            "-oProtocol=2",
            remote_access.CompileSSHConnectSettings(Protocol=None),
        )


class CreateTunnelPopenMock(partial_mock.PartialCmdMock):
    """Mocks the subprocess.Popen function where it is used in RemoteAccess."""

    TARGET = "chromite.lib.remote_access.RemoteAccess"
    ATTRS = ("_mockable_popen",)
    DEFAULT_ATTR = "_mockable_popen"

    PopenFake = collections.namedtuple("PopenFake", ("args",))

    def _mockable_popen(self, inst, *_args, **_kwargs):
        return self.PopenFake(inst)


class RemoteShMock(partial_mock.PartialCmdMock):
    """Mocks the RemoteSh function."""

    TARGET = "chromite.lib.remote_access.RemoteAccess"
    ATTRS = ("RemoteSh",)
    DEFAULT_ATTR = "RemoteSh"

    def RemoteSh(self, inst, cmd, *args, **kwargs):
        """Simulates a RemoteSh invocation.

        Returns:
            A CompletedProcess object with an additional member |rc_mock| to
            enable examination of the underlying run() function call.
        """
        # NB: Keep in sync with RunCommandMock.run.
        if isinstance(cmd, (tuple, list)):
            cmd = [str(x) if isinstance(x, os.PathLike) else x for x in cmd]
        result = self._results["RemoteSh"].LookupResult(
            (cmd,),
            hook_args=(
                inst,
                cmd,
            )
            + args,
            hook_kwargs=kwargs,
        )

        # Run the real RemoteSh with run mocked out.
        rc_mock = cros_test_lib.RunCommandMock()
        rc_mock.AddCmdResult(
            partial_mock.Ignore(),
            result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

        with rc_mock:
            result = self.backup["RemoteSh"](inst, cmd, *args, **kwargs)
        result.rc_mock = rc_mock
        return result


class RemoteDeviceMock(partial_mock.PartialMock):
    """Mocks the RemoteDevice function."""

    TARGET = "chromite.lib.remote_access.RemoteDevice"
    ATTRS = ("Pingable",)

    def Pingable(self, _):
        return True


class CreateTunnelTest(cros_test_lib.MockTempDirTestCase):
    """Base class with popen mocked for RemoteAccess.CreateTunnel() tests."""

    def setUp(self):
        self.popen_mock = self.StartPatcher(CreateTunnelPopenMock())
        self.host = remote_access.RemoteAccess("foon", self.tempdir)

    def testDefault(self):
        """Test default behavior."""
        plain_result = self.host.CreateTunnel().args
        self.assertNotIn("-R", plain_result)
        self.assertNotIn("-L", plain_result)

    def testLocal(self):
        """Test behavior of to_local parameter."""
        for spec, expected_output in (
            (
                remote_access.PortForwardSpec(local_port=3240),
                "localhost:3240:localhost:3240",
            ),
            (
                remote_access.PortForwardSpec(
                    local_host="foo",
                    local_port=3240,
                    remote_host="",
                    remote_port=12345,
                ),
                "12345:foo:3240",
            ),
        ):
            result = self.host.CreateTunnel(to_local=[spec]).args
            self.assertEqual(result[result.index("-L") + 1], expected_output)

    def testRemote(self):
        """Test behavior of to_remote parameter."""
        for spec, expected_output in (
            (
                remote_access.PortForwardSpec(local_port=3240),
                "localhost:3240:localhost:3240",
            ),
            (
                remote_access.PortForwardSpec(
                    local_host="foo",
                    local_port=3240,
                    remote_host="",
                    remote_port=12345,
                ),
                "12345:foo:3240",
            ),
        ):
            result = self.host.CreateTunnel(to_remote=[spec]).args
            self.assertEqual(result[result.index("-R") + 1], expected_output)

    def testInvalid(self):
        """Test behavior of invalid parameters."""
        for kwargs in (
            {"to_local": ""},
            {"to_local": [""]},
            {"to_remote": ""},
            {"to_remote": [""]},
        ):
            self.assertRaises(
                AttributeError, self.host.CreateTunnel, [], kwargs
            )


class RemoteAccessTest(cros_test_lib.MockTempDirTestCase):
    """Base class with RemoteSh mocked out for testing RemoteAccess."""

    def setUp(self):
        self.rsh_mock = self.StartPatcher(RemoteShMock())
        self.host = remote_access.RemoteAccess("foon", self.tempdir)


class RemoteShTest(RemoteAccessTest):
    """Tests of basic RemoteSh functions"""

    TEST_CMD = ["ls"]
    RETURN_CODE = 0
    OUTPUT = "witty"
    ERROR = "error"

    def assertRemoteShRaises(self, **kwargs):
        """Asserts that RunCommandError is raised when running TEST_CMD."""
        self.assertRaises(
            cros_build_lib.RunCommandError,
            self.host.RemoteSh,
            self.TEST_CMD,
            **kwargs,
        )

    def assertRemoteShRaisesSSHConnectionError(self, **kwargs):
        """Asserts that SSHConnectionError is raised when running TEST_CMD."""
        self.assertRaises(
            remote_access.SSHConnectionError,
            self.host.RemoteSh,
            self.TEST_CMD,
            **kwargs,
        )

    def SetRemoteShResult(
        self, returncode=RETURN_CODE, stdout=OUTPUT, stderr=ERROR
    ):
        """Sets the RemoteSh command results."""
        self.rsh_mock.AddCmdResult(
            self.TEST_CMD, returncode=returncode, stdout=stdout, stderr=stderr
        )

    def testNormal(self):
        """Test normal functionality."""
        self.SetRemoteShResult()
        result = self.host.RemoteSh(self.TEST_CMD)
        self.assertEqual(result.returncode, self.RETURN_CODE)
        self.assertEqual(result.stdout.strip(), self.OUTPUT)
        self.assertEqual(result.stderr.strip(), self.ERROR)

    def testShell(self):
        """Test normal functionality with shell=True."""
        test_cmd = "ls && pwd"
        self.rsh_mock.AddCmdResult(test_cmd, returncode=0)
        result = self.host.RemoteSh(test_cmd, shell=True)
        self.assertTrue(result.cmd[-1].endswith("'%s'" % test_cmd))

    def testRemoteCmdFailure(self):
        """Test failure in remote cmd."""
        self.SetRemoteShResult(returncode=1)
        self.assertRemoteShRaises()
        self.assertRemoteShRaises(ssh_error_ok=True)
        self.host.RemoteSh(self.TEST_CMD, check=False)
        self.host.RemoteSh(self.TEST_CMD, ssh_error_ok=True, check=False)

    def testSshFailure(self):
        """Test failure in ssh command."""
        self.SetRemoteShResult(returncode=remote_access.SSH_ERROR_CODE)
        self.assertRemoteShRaisesSSHConnectionError()
        self.assertRemoteShRaisesSSHConnectionError(check=False)
        self.host.RemoteSh(self.TEST_CMD, ssh_error_ok=True)
        self.host.RemoteSh(self.TEST_CMD, ssh_error_ok=True, check=False)

    def testEnvLcMessagesSet(self):
        """Test that LC_MESSAGES is set to 'C' for an SSH command."""
        self.SetRemoteShResult()
        result = self.host.RemoteSh(self.TEST_CMD)
        rc_kwargs = result.rc_mock.call_args_list[-1][1]
        self.assertEqual(rc_kwargs["extra_env"]["LC_MESSAGES"], "C")

    def testEnvLcMessagesOverride(self):
        """Test that LC_MESSAGES is overridden to 'C' for an SSH command."""
        self.SetRemoteShResult()
        result = self.host.RemoteSh(
            self.TEST_CMD, extra_env={"LC_MESSAGES": "fr"}
        )
        rc_kwargs = result.rc_mock.call_args_list[-1][1]
        self.assertEqual(rc_kwargs["extra_env"]["LC_MESSAGES"], "C")


class CheckIfRebootedTest(RemoteAccessTest):
    """Tests of the CheckIfRebooted function."""

    _OLD_BOOT_ID = "1234"
    _NEW_BOOT_ID = "5678"

    def _SetCheckRebootResult(self, returncode=0, stdout="", stderr=""):
        """Sets the result object fields to mock a specific ssh command.

        The command is the one used to fetch the boot ID (cat /proc/sys/...)
        """
        self.rsh_mock.AddCmdResult(
            partial_mock.ListRegex("/proc/sys/.*"),
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def testSuccess(self):
        """Test the case of successful reboot."""
        self._SetCheckRebootResult(returncode=0, stdout=self._NEW_BOOT_ID)
        self.assertTrue(self.host.CheckIfRebooted(self._OLD_BOOT_ID))

    def testFailure(self):
        """Test case of failed reboot (boot ID did not change)."""
        self._SetCheckRebootResult(0, stdout=self._OLD_BOOT_ID)
        self.assertFalse(self.host.CheckIfRebooted(self._OLD_BOOT_ID))

    def testSshFailure(self):
        """Test case of reboot pending (ssh failed)."""
        self._SetCheckRebootResult(returncode=remote_access.SSH_ERROR_CODE)
        self.assertFalse(self.host.CheckIfRebooted(self._OLD_BOOT_ID))

    def testInvalidErrorCode(self):
        """Test case of bad error code returned."""
        self._SetCheckRebootResult(returncode=2)
        self.assertRaises(
            Exception, lambda: self.host.CheckIfRebooted(self._OLD_BOOT_ID)
        )


class RemoteDeviceTest(cros_test_lib.MockTestCase):
    """Tests for RemoteDevice class."""

    def setUp(self):
        self.rsh_mock = self.StartPatcher(RemoteShMock())
        self.pingable_mock = self.PatchObject(
            remote_access.RemoteDevice, "Pingable", return_value=True
        )

    def _SetupRemoteTempDir(self):
        """Mock out the calls needed for a remote tempdir."""
        self.rsh_mock.AddCmdResult(partial_mock.In("mktemp"))
        self.rsh_mock.AddCmdResult(partial_mock.In("rm"))

    def testCommands(self):
        """Tests simple run() usage."""
        command = ["echo", "foo"]
        expected_output = "foo"
        self.rsh_mock.AddCmdResult(command, stdout=expected_output)
        self._SetupRemoteTempDir()

        with remote_access.RemoteDeviceHandler(remote_access.TEST_IP) as device:
            self.assertEqual(
                expected_output, device.run(["echo", "foo"]).stdout
            )

    def testCommandsExtraEnv(self):
        """Tests simple RunCommand() usage with extra_env arg."""
        self._SetupRemoteTempDir()

        with remote_access.RemoteDeviceHandler(remote_access.TEST_IP) as device:
            # RemoteSh accepts cmd as either string or list, so try both.
            self.rsh_mock.AddCmdResult(["VAR=val", "echo", "foo"], stdout="foo")
            self.assertEqual(
                "foo",
                device.run(["echo", "foo"], extra_env={"VAR": "val"}).stdout,
            )

            self.rsh_mock.AddCmdResult("VAR=val echo foo", stdout="foo")
            self.assertEqual(
                "foo",
                device.run(
                    "echo foo", extra_env={"VAR": "val"}, shell=True
                ).stdout,
            )

    def testRunCommandShortCmdline(self):
        """Verify short command lines execute env settings directly."""
        with remote_access.RemoteDeviceHandler(remote_access.TEST_IP) as device:
            self.PatchObject(
                remote_access.RemoteDevice,
                "CopyToWorkDir",
                side_effect=Exception("should not be copying files"),
            )
            self.rsh_mock.AddCmdResult(partial_mock.In("runit"))
            device.run(["runit"], extra_env={"VAR": "val"})

    def testRunCommandLongCmdline(self):
        """Verify long command lines execute env settings via script."""
        with remote_access.RemoteDeviceHandler(remote_access.TEST_IP) as device:
            self._SetupRemoteTempDir()
            m = self.PatchObject(remote_access.RemoteDevice, "CopyToWorkDir")
            self.rsh_mock.AddCmdResult(partial_mock.In("runit"))
            device.run(["runit"], extra_env={"VAR": "v" * 1024 * 1024})
            # We'll assume that the test passed when it tries to copy a file to
            # the remote side (the shell script to run indirectly).
            self.assertEqual(m.call_count, 1)

    def testRunPathlib(self):
        """Test pathlib usage in commands."""
        with remote_access.RemoteDeviceHandler(remote_access.TEST_IP) as device:
            self.rsh_mock.AddCmdResult(["ls", Path("/")], returncode=0)
            result = device.run(["ls", Path("/")])
            self.assertEqual(result.cmd[-2:], ["ls", "/"])

    def testRunPathlibEnv(self):
        """Test pathlib usage in commands w/custom env."""
        with remote_access.RemoteDeviceHandler(remote_access.TEST_IP) as device:
            self.rsh_mock.AddCmdResult(
                ["FOO=bar", "ls", Path("/")], returncode=0
            )
            result = device.run(["ls", Path("/")], extra_env={"FOO": "bar"})
            self.assertEqual(result.cmd[-2:], ["ls", "/"])

    def testNoDeviceBaseDir(self):
        """Tests base_dir=None."""
        command = ["echo", "foo"]
        expected_output = "foo"
        self.rsh_mock.AddCmdResult(command, stdout=expected_output)

        with remote_access.RemoteDeviceHandler(
            remote_access.TEST_IP, base_dir=None
        ) as device:
            self.assertEqual(
                expected_output, device.run(["echo", "foo"]).stdout
            )

    def testDelayedRemoteDirs(self):
        """Tests the delayed creation of base_dir/work_dir."""
        with remote_access.RemoteDeviceHandler(
            remote_access.TEST_IP, base_dir="/f"
        ) as device:
            # Make sure we didn't talk to the remote yet.
            self.assertEqual(self.rsh_mock.call_count, 0)

            # The work dir will get automatically created when we use it.
            self.rsh_mock.AddCmdResult(partial_mock.In("mktemp"))
            _ = device.work_dir
            self.assertEqual(self.rsh_mock.call_count, 1)

            # Add a mock for the clean up logic.
            self.rsh_mock.AddCmdResult(partial_mock.In("rm"))

        self.assertEqual(self.rsh_mock.call_count, 2)

    def testSELinuxAvailable(self):
        """Test IsSELinuxAvailable() and IsSELinuxEnforced() when available."""
        self.rsh_mock.AddCmdResult(
            partial_mock.ListRegex("which restorecon"), returncode=0
        )
        self.rsh_mock.AddCmdResult(
            partial_mock.ListRegex("test -f"), returncode=0
        )
        with remote_access.RemoteDeviceHandler(remote_access.TEST_IP) as device:
            self.rsh_mock.AddCmdResult(
                partial_mock.ListRegex("cat /sys/fs/selinux/enforce"),
                returncode=0,
                stdout="1",
            )
            self.assertEqual(device.IsSELinuxAvailable(), True)
            self.assertEqual(device.IsSELinuxEnforced(), True)

            self.rsh_mock.AddCmdResult(
                partial_mock.ListRegex("cat /sys/fs/selinux/enforce"),
                returncode=0,
                stdout="0",
            )
            self.assertEqual(device.IsSELinuxAvailable(), True)
            self.assertEqual(device.IsSELinuxEnforced(), False)

    def testSELinuxUnavailable(self):
        """Test IsSELinux{Available|Enforced}() when unavailable."""
        self.rsh_mock.AddCmdResult(
            partial_mock.ListRegex("which restorecon"), returncode=0
        )
        self.rsh_mock.AddCmdResult(
            partial_mock.ListRegex("test -f"), returncode=1
        )
        with remote_access.RemoteDeviceHandler(remote_access.TEST_IP) as device:
            self.assertEqual(device.IsSELinuxAvailable(), False)
            self.assertEqual(device.IsSELinuxEnforced(), False)

    def testGetDecompressor(self):
        """Test correct decompressor is returned."""
        self.rsh_mock.AddCmdResult(partial_mock.In("xz"), returncode=0)
        self.rsh_mock.AddCmdResult(partial_mock.In("bzip2"), returncode=0)
        self.rsh_mock.AddCmdResult(partial_mock.In("gzip"), returncode=0)
        self.rsh_mock.AddCmdResult(partial_mock.In("zstd"), returncode=0)
        with remote_access.RemoteDeviceHandler(remote_access.TEST_IP) as device:
            self.assertEqual(
                ["xz", "--decompress", "--stdout"],
                device.GetDecompressor(cros_build_lib.CompressionType.XZ),
            )
            self.assertEqual(
                ["bzip2", "--decompress", "--stdout"],
                device.GetDecompressor(cros_build_lib.CompressionType.BZIP2),
            )
            self.assertEqual(
                ["gzip", "--decompress", "--stdout"],
                device.GetDecompressor(cros_build_lib.CompressionType.GZIP),
            )
            self.assertEqual(
                ["zstd", "--decompress", "--stdout"],
                device.GetDecompressor(cros_build_lib.CompressionType.ZSTD),
            )
            self.assertEqual(
                ["cat"],
                device.GetDecompressor(cros_build_lib.CompressionType.NONE),
            )

            with self.assertRaises(ValueError):
                device.GetDecompressor("foo")

    def testGetDecompressorFails(self):
        """Tests decompressor program not found."""
        self.rsh_mock.AddCmdResult(partial_mock.In("xz"), returncode=1)
        with remote_access.RemoteDeviceHandler(remote_access.TEST_IP) as device:
            with self.assertRaises(remote_access.ProgramNotFoundError):
                device.GetDecompressor(cros_build_lib.CompressionType.XZ)


class ChromiumOSDeviceTest(cros_test_lib.MockTestCase):
    """Tests for ChromiumOSDevice class."""

    def setUp(self):
        self.rsh_mock = self.StartPatcher(RemoteShMock())
        self.rsh_mock.AddCmdResult(partial_mock.In("${PATH}"), stdout="")
        self.path_env = "PATH=%s:" % remote_access.DEV_BIN_PATHS

    def testRun(self):
        """Tests simple run() usage."""
        with remote_access.ChromiumOSDeviceHandler(
            remote_access.TEST_IP
        ) as device:
            # RemoteSh accepts cmd as either string or list, so try both.
            self.rsh_mock.AddCmdResult(
                [self.path_env, "echo", "foo"], stdout="foo"
            )
            self.assertEqual("foo", device.run(["echo", "foo"]).stdout)

            self.rsh_mock.AddCmdResult(
                self.path_env + " echo foo", stdout="foo"
            )
            self.assertEqual("foo", device.run("echo foo", shell=True).stdout)

            # Run the same commands, but make sure PATH isn't modified when
            # fix_path is False.
            device._include_dev_paths = False
            self.rsh_mock.AddCmdResult(["echo", "foo"], stdout="foo")
            self.assertEqual("foo", device.run(["echo", "foo"]).stdout)

            self.rsh_mock.AddCmdResult("echo foo", stdout="foo")
            self.assertEqual("foo", device.run("echo foo", shell=True).stdout)

    def test_root_dev(self):
        """Tests getting the path to the current root device."""
        with remote_access.ChromiumOSDeviceHandler(
            remote_access.TEST_IP
        ) as device:
            self.rsh_mock.AddCmdResult(
                [self.path_env, "rootdev", "-s"], stdout="/dev/foop5"
            )
            self.assertEqual(device.root_dev, "/dev/foop5")

    def testClearTpmOwner(self):
        """Test clearing the TPM owner."""
        with remote_access.ChromiumOSDeviceHandler(
            remote_access.TEST_IP
        ) as device:
            self.rsh_mock.AddCmdResult(
                [self.path_env, "crossystem", "clear_tpm_owner_request=1"]
            )
            device.ClearTpmOwner()


class ScpTest(cros_test_lib.MockTempDirTestCase):
    """Tests for RemoteAccess.Scp"""

    def setUp(self):
        self.mock = cros_test_lib.RunCommandMock()
        self.mock.AddCmdResult(partial_mock.Ignore())

    def testHostname(self):
        host = remote_access.RemoteAccess("chromium.org", self.tempdir)

        with self.mock:
            result = host.Scp(self.tempdir, "/tmp/remote")

        self.assertIn("root@chromium.org:/tmp/remote", result.cmd)

    def testIpV4(self):
        host = remote_access.RemoteAccess("127.0.0.1", self.tempdir)

        with self.mock:
            result = host.Scp(self.tempdir, "/tmp/remote")

        self.assertIn("root@127.0.0.1:/tmp/remote", result.cmd)

    def testIpV6ToLocal(self):
        host = remote_access.RemoteAccess("::1", self.tempdir)

        with self.mock:
            result = host.Scp(self.tempdir, "/tmp/remote")

        self.assertIn("root@[::1]:/tmp/remote", result.cmd)

    def testIpV6FromRemote(self):
        host = remote_access.RemoteAccess("::1", self.tempdir)

        with self.mock:
            result = host.Scp("/tmp/remote", self.tempdir, to_local=True)

        self.assertIn("root@[::1]:/tmp/remote", result.cmd)
