# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for the deploy_chrome script."""

import errno
import os
import time
from unittest import mock

from chromite.cli.cros import cros_chrome_sdk_unittest
from chromite.lib import chrome_util
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import parallel_unittest
from chromite.lib import partial_mock
from chromite.lib import remote_access
from chromite.lib import remote_access_unittest
from chromite.scripts import deploy_chrome


# pylint: disable=protected-access


_REGULAR_TO = ('--device', 'monkey')
_TARGET_BOARD = 'eve'
_GS_PATH = 'gs://foon'


def _ParseCommandLine(argv):
  return deploy_chrome._ParseCommandLine(['--log-level', 'debug'] + argv)


class InterfaceTest(cros_test_lib.OutputTestCase):
  """Tests the commandline interface of the script."""

  def testGsLocalPathUnSpecified(self):
    """Test no chrome path specified."""
    with self.OutputCapturer():
      self.assertRaises2(SystemExit, _ParseCommandLine,
                         list(_REGULAR_TO) + ['--board', _TARGET_BOARD],
                         check_attrs={'code': 2})

  def testBuildDirSpecified(self):
    """Test case of build dir specified."""
    argv = list(_REGULAR_TO) + ['--board', _TARGET_BOARD, '--build-dir',
                                '/path/to/chrome']
    _ParseCommandLine(argv)

  def testBuildDirSpecifiedWithoutBoard(self):
    """Test case of build dir specified without --board."""
    argv = list(_REGULAR_TO) + [
        '--build-dir', '/path/to/chrome/out_' + _TARGET_BOARD + '/Release']
    options = _ParseCommandLine(argv)
    self.assertEqual(options.board, _TARGET_BOARD)

  def testBuildDirSpecifiedWithoutBoardError(self):
    """Test case of irregular build dir specified without --board."""
    argv = list(_REGULAR_TO) + ['--build-dir', '/path/to/chrome/foo/bar']
    self.assertParseError(argv)

  def testGsPathSpecified(self):
    """Test case of GS path specified."""
    argv = list(_REGULAR_TO) + ['--board', _TARGET_BOARD, '--gs-path', _GS_PATH]
    _ParseCommandLine(argv)

  def testLocalPathSpecified(self):
    """Test case of local path specified."""
    argv = list(_REGULAR_TO) + ['--board', _TARGET_BOARD, '--local-pkg-path',
                                '/path/to/chrome']
    _ParseCommandLine(argv)

  def testNoBoard(self):
    """Test no board specified."""
    argv = list(_REGULAR_TO) + ['--gs-path', _GS_PATH]
    self.assertParseError(argv)

  def testNoTarget(self):
    """Test no target specified."""
    argv = ['--board', _TARGET_BOARD, '--gs-path', _GS_PATH]
    self.assertParseError(argv)

  def testLacros(self):
    """Test basic lacros invocation."""
    argv = ['--lacros', '--nostrip', '--build-dir', '/path/to/nowhere',
            '--device', 'monkey']
    options = _ParseCommandLine(argv)
    self.assertTrue(options.lacros)
    self.assertEqual(options.target_dir, deploy_chrome.LACROS_DIR)

  def testLacrosRequiresNostrip(self):
    """Lacros requires --nostrip"""
    argv = ['--lacros', '--build-dir', '/path/to/nowhere', '--device',
            'monkey']
    self.assertRaises2(SystemExit, _ParseCommandLine, argv,
                       check_attrs={'code': 2})

  def assertParseError(self, argv):
    with self.OutputCapturer():
      self.assertRaises2(SystemExit, _ParseCommandLine, argv,
                         check_attrs={'code': 2})

  def testMountOptionSetsTargetDir(self):
    argv = list(_REGULAR_TO) + ['--board', _TARGET_BOARD, '--gs-path', _GS_PATH,
                                '--mount']
    options = _ParseCommandLine(argv)
    self.assertIsNot(options.target_dir, None)

  def testMountOptionSetsMountDir(self):
    argv = list(_REGULAR_TO) + ['--board', _TARGET_BOARD, '--gs-path', _GS_PATH,
                                '--mount']
    options = _ParseCommandLine(argv)
    self.assertIsNot(options.mount_dir, None)

  def testMountOptionDoesNotOverrideTargetDir(self):
    argv = list(_REGULAR_TO) + ['--board', _TARGET_BOARD, '--gs-path', _GS_PATH,
                                '--mount', '--target-dir', '/foo/bar/cow']
    options = _ParseCommandLine(argv)
    self.assertEqual(options.target_dir, '/foo/bar/cow')

  def testMountOptionDoesNotOverrideMountDir(self):
    argv = list(_REGULAR_TO) + ['--board', _TARGET_BOARD, '--gs-path', _GS_PATH,
                                '--mount', '--mount-dir', '/foo/bar/cow']
    options = _ParseCommandLine(argv)
    self.assertEqual(options.mount_dir, '/foo/bar/cow')

  def testSshIdentityOptionSetsOption(self):
    argv = list(_REGULAR_TO) + ['--board', _TARGET_BOARD,
                                '--private-key', '/foo/bar/key',
                                '--build-dir', '/path/to/nowhere']
    options = _ParseCommandLine(argv)
    self.assertEqual(options.private_key, '/foo/bar/key')

class DeployChromeMock(partial_mock.PartialMock):
  """Deploy Chrome Mock Class."""

  TARGET = 'chromite.scripts.deploy_chrome.DeployChrome'
  ATTRS = ('_KillAshChromeIfNeeded', '_DisableRootfsVerification')

  def __init__(self):
    partial_mock.PartialMock.__init__(self)
    self.remote_device_mock = remote_access_unittest.RemoteDeviceMock()
    # Target starts off as having rootfs verification enabled.
    self.rsh_mock = remote_access_unittest.RemoteShMock()
    self.rsh_mock.SetDefaultCmdResult(0)
    self.MockMountCmd(1)
    self.rsh_mock.AddCmdResult(
        deploy_chrome.LSOF_COMMAND_CHROME % (deploy_chrome._CHROME_DIR,), 1)

  def MockMountCmd(self, returnvalue):
    self.rsh_mock.AddCmdResult(deploy_chrome.MOUNT_RW_COMMAND,
                               returnvalue)

  def _DisableRootfsVerification(self, inst):
    with mock.patch.object(time, 'sleep'):
      self.backup['_DisableRootfsVerification'](inst)

  def PreStart(self):
    self.remote_device_mock.start()
    self.rsh_mock.start()

  def PreStop(self):
    self.rsh_mock.stop()
    self.remote_device_mock.stop()

  def _KillAshChromeIfNeeded(self, _inst):
    # Fully stub out for now.
    pass


class DeployTest(cros_test_lib.MockTempDirTestCase):
  """Setup a deploy object with a GS-path for use in tests."""

  def _GetDeployChrome(self, args):
    options = _ParseCommandLine(args)
    return deploy_chrome.DeployChrome(
        options, self.tempdir, os.path.join(self.tempdir, 'staging'))

  def setUp(self):
    self.deploy_mock = self.StartPatcher(DeployChromeMock())
    self.deploy = self._GetDeployChrome(list(_REGULAR_TO) +
                                        ['--board', _TARGET_BOARD, '--gs-path',
                                         _GS_PATH, '--force', '--mount'])
    self.remote_reboot_mock = self.PatchObject(
        remote_access.RemoteAccess, 'RemoteReboot', return_value=True)


class TestCheckIfBoardMatches(DeployTest):
  """Testing checking whether the DUT board matches the target board."""

  def testMatchedBoard(self):
    """Test the case where the DUT board matches the target board."""
    self.PatchObject(remote_access.ChromiumOSDevice, 'board', _TARGET_BOARD)
    self.assertTrue(self.deploy.options.force)
    self.deploy._CheckBoard()
    self.deploy.options.force = False
    self.deploy._CheckBoard()

  def testMismatchedBoard(self):
    """Test the case where the DUT board does not match the target board."""
    self.PatchObject(remote_access.ChromiumOSDevice, 'board', 'cedar')
    self.assertTrue(self.deploy.options.force)
    self.deploy._CheckBoard()
    self.deploy.options.force = False
    self.PatchObject(cros_build_lib, 'BooleanPrompt', return_value=True)
    self.deploy._CheckBoard()
    self.PatchObject(cros_build_lib, 'BooleanPrompt', return_value=False)
    self.assertRaises(deploy_chrome.DeployFailure, self.deploy._CheckBoard)


class TestDisableRootfsVerification(DeployTest):
  """Testing disabling of rootfs verification and RO mode."""

  def testDisableRootfsVerificationSuccess(self):
    """Test the working case, disabling rootfs verification."""
    self.deploy_mock.MockMountCmd(0)
    self.deploy._DisableRootfsVerification()
    self.assertFalse(self.deploy._root_dir_is_still_readonly.is_set())

  def testDisableRootfsVerificationFailure(self):
    """Test failure to disable rootfs verification."""
    # pylint: disable=unused-argument
    def RaiseRunCommandError(timeout_sec=None):
      raise cros_build_lib.RunCommandError('Mock RunCommandError')
    self.remote_reboot_mock.side_effect = RaiseRunCommandError
    self.assertRaises(cros_build_lib.RunCommandError,
                      self.deploy._DisableRootfsVerification)
    self.remote_reboot_mock.side_effect = None
    self.assertFalse(self.deploy._root_dir_is_still_readonly.is_set())


class TestMount(DeployTest):
  """Testing mount success and failure."""

  def testSuccess(self):
    """Test case where we are able to mount as writable."""
    self.assertFalse(self.deploy._root_dir_is_still_readonly.is_set())
    self.deploy_mock.MockMountCmd(0)
    self.deploy._MountRootfsAsWritable()
    self.assertFalse(self.deploy._root_dir_is_still_readonly.is_set())

  def testMountError(self):
    """Test that mount failure doesn't raise an exception by default."""
    self.assertFalse(self.deploy._root_dir_is_still_readonly.is_set())
    self.PatchObject(remote_access.ChromiumOSDevice, 'IsDirWritable',
                     return_value=False, autospec=True)
    self.deploy._MountRootfsAsWritable()
    self.assertTrue(self.deploy._root_dir_is_still_readonly.is_set())

  def testMountRwFailure(self):
    """Test that mount failure raises an exception if check=True."""
    self.assertRaises(cros_build_lib.RunCommandError,
                      self.deploy._MountRootfsAsWritable, check=True)
    self.assertFalse(self.deploy._root_dir_is_still_readonly.is_set())

  def testMountTempDir(self):
    """Test that mount succeeds if target dir is writable."""
    self.assertFalse(self.deploy._root_dir_is_still_readonly.is_set())
    self.PatchObject(remote_access.ChromiumOSDevice, 'IsDirWritable',
                     return_value=True, autospec=True)
    self.deploy._MountRootfsAsWritable()
    self.assertFalse(self.deploy._root_dir_is_still_readonly.is_set())


class TestMountTarget(DeployTest):
  """Testing mount and umount command handling."""

  def testMountTargetUmountFailure(self):
    """Test error being thrown if umount fails.

    Test that 'lsof' is run on mount-dir and 'mount -rbind' command is not run
    if 'umount' cmd fails.
    """
    mount_dir = self.deploy.options.mount_dir
    target_dir = self.deploy.options.target_dir
    self.deploy_mock.rsh_mock.AddCmdResult(
        deploy_chrome._UMOUNT_DIR_IF_MOUNTPOINT_CMD %
        {'dir': mount_dir}, returncode=errno.EBUSY, stderr='Target is Busy')
    self.deploy_mock.rsh_mock.AddCmdResult(deploy_chrome.LSOF_COMMAND %
                                           (mount_dir,), returncode=0,
                                           stdout='process ' + mount_dir)
    # Check for RunCommandError being thrown.
    self.assertRaises(cros_build_lib.RunCommandError,
                      self.deploy._MountTarget)
    # Check for the 'mount -rbind' command not run.
    self.deploy_mock.rsh_mock.assertCommandContains(
        (deploy_chrome._BIND_TO_FINAL_DIR_CMD % (target_dir, mount_dir)),
        expected=False)
    # Check for lsof command being called.
    self.deploy_mock.rsh_mock.assertCommandContains(
        (deploy_chrome.LSOF_COMMAND % (mount_dir,)))


class TestUiJobStarted(DeployTest):
  """Test detection of a running 'ui' job."""

  def MockStatusUiCmd(self, **kwargs):
    self.deploy_mock.rsh_mock.AddCmdResult('status ui', **kwargs)

  def testUiJobStartedFalse(self):
    """Correct results with a stopped job."""
    self.MockStatusUiCmd(output='ui stop/waiting')
    self.assertFalse(self.deploy._CheckUiJobStarted())

  def testNoUiJob(self):
    """Correct results when the job doesn't exist."""
    self.MockStatusUiCmd(error='start: Unknown job: ui', returncode=1)
    self.assertFalse(self.deploy._CheckUiJobStarted())

  def testCheckRootfsWriteableTrue(self):
    """Correct results with a running job."""
    self.MockStatusUiCmd(output='ui start/running, process 297')
    self.assertTrue(self.deploy._CheckUiJobStarted())


class StagingTest(cros_test_lib.MockTempDirTestCase):
  """Test user-mode and ebuild-mode staging functionality."""

  def setUp(self):
    self.staging_dir = os.path.join(self.tempdir, 'staging')
    self.build_dir = os.path.join(self.tempdir, 'build_dir')
    self.common_flags = ['--board', _TARGET_BOARD,
                         '--build-dir', self.build_dir, '--staging-only',
                         '--cache-dir', self.tempdir]
    self.sdk_mock = self.StartPatcher(cros_chrome_sdk_unittest.SDKFetcherMock())
    self.PatchObject(
        osutils, 'SourceEnvironment', autospec=True,
        return_value={'STRIP': 'x86_64-cros-linux-gnu-strip'})

  def testSingleFileDeployFailure(self):
    """Default staging enforces that mandatory files are copied"""
    options = _ParseCommandLine(self.common_flags)
    osutils.Touch(os.path.join(self.build_dir, 'chrome'), makedirs=True)
    self.assertRaises(
        chrome_util.MissingPathError, deploy_chrome._PrepareStagingDir,
        options, self.tempdir, self.staging_dir, chrome_util._COPY_PATHS_CHROME)

  def testSloppyDeployFailure(self):
    """Sloppy staging enforces that at least one file is copied."""
    options = _ParseCommandLine(self.common_flags + ['--sloppy'])
    self.assertRaises(
        chrome_util.MissingPathError, deploy_chrome._PrepareStagingDir,
        options, self.tempdir, self.staging_dir, chrome_util._COPY_PATHS_CHROME)

  def testSloppyDeploySuccess(self):
    """Sloppy staging - stage one file."""
    options = _ParseCommandLine(self.common_flags + ['--sloppy'])
    osutils.Touch(os.path.join(self.build_dir, 'chrome'), makedirs=True)
    deploy_chrome._PrepareStagingDir(options, self.tempdir, self.staging_dir,
                                     chrome_util._COPY_PATHS_CHROME)


class DeployTestBuildDir(cros_test_lib.MockTempDirTestCase):
  """Set up a deploy object with a build-dir for use in deployment type tests"""

  def _GetDeployChrome(self, args):
    options = _ParseCommandLine(args)
    return deploy_chrome.DeployChrome(
        options, self.tempdir, os.path.join(self.tempdir, 'staging'))

  def setUp(self):
    self.staging_dir = os.path.join(self.tempdir, 'staging')
    self.build_dir = os.path.join(self.tempdir, 'build_dir')
    self.deploy_mock = self.StartPatcher(DeployChromeMock())
    self.deploy = self._GetDeployChrome(
        list(_REGULAR_TO) + ['--board', _TARGET_BOARD,
                             '--build-dir', self.build_dir, '--staging-only',
                             '--cache-dir', self.tempdir, '--sloppy'])

  def getCopyPath(self, source_path):
    """Return a chrome_util.Path or None if not present."""
    paths = [p for p in self.deploy.copy_paths if p.src == source_path]
    return paths[0] if paths else None

class TestDeploymentType(DeployTestBuildDir):
  """Test detection of deployment type using build dir."""

  def testAppShellDetection(self):
    """Check for an app_shell deployment"""
    osutils.Touch(os.path.join(self.deploy.options.build_dir, 'app_shell'),
                  makedirs=True)
    self.deploy._CheckDeployType()
    self.assertTrue(self.getCopyPath('app_shell'))
    self.assertFalse(self.getCopyPath('chrome'))

  def testChromeAndAppShellDetection(self):
    """Check for a chrome deployment when app_shell also exists."""
    osutils.Touch(os.path.join(self.deploy.options.build_dir, 'chrome'),
                  makedirs=True)
    osutils.Touch(os.path.join(self.deploy.options.build_dir, 'app_shell'),
                  makedirs=True)
    self.deploy._CheckDeployType()
    self.assertTrue(self.getCopyPath('chrome'))
    self.assertFalse(self.getCopyPath('app_shell'))

  def testChromeDetection(self):
    """Check for a regular chrome deployment"""
    osutils.Touch(os.path.join(self.deploy.options.build_dir, 'chrome'),
                  makedirs=True)
    self.deploy._CheckDeployType()
    self.assertTrue(self.getCopyPath('chrome'))
    self.assertFalse(self.getCopyPath('app_shell'))


class TestDeployTestBinaries(cros_test_lib.RunCommandTempDirTestCase):
  """Tests _DeployTestBinaries()."""

  def setUp(self):
    options = _ParseCommandLine(list(_REGULAR_TO) + [
        '--board', _TARGET_BOARD, '--force', '--mount',
        '--build-dir', os.path.join(self.tempdir, 'build_dir'),
        '--nostrip'])
    self.deploy = deploy_chrome.DeployChrome(
        options, self.tempdir, os.path.join(self.tempdir, 'staging'))

  def _SimulateBinaries(self):
    # Ensure the staging dir contains the right binaries to copy over.
    test_binaries = [
        'run_a_tests',
        'run_b_tests',
        'run_c_tests',
    ]
    # Simulate having the binaries both on the device and in our local build
    # dir.
    self.rc.AddCmdResult(
        partial_mock.In(deploy_chrome._FIND_TEST_BIN_CMD),
        stdout='\n'.join(test_binaries))
    for binary in test_binaries:
      osutils.Touch(os.path.join(self.deploy.options.build_dir, binary),
                    makedirs=True, mode=0o700)
    return test_binaries

  def _AssertBinariesInStagingDir(self, test_binaries):
    # Ensure the binaries were placed in the staging dir used to copy them over.
    staging_dir = os.path.join(
        self.tempdir, os.path.basename(deploy_chrome._CHROME_TEST_BIN_DIR))
    for binary in test_binaries:
      self.assertIn(binary, os.listdir(staging_dir))

  def testFindError(self):
    """Ensure an error is thrown if we can't inspect the device."""
    self.rc.AddCmdResult(
        partial_mock.In(deploy_chrome._FIND_TEST_BIN_CMD), 1)
    self.assertRaises(
        deploy_chrome.DeployFailure, self.deploy._DeployTestBinaries)

  def testSuccess(self):
    """Ensure that the happy path succeeds as expected."""
    test_binaries = self._SimulateBinaries()
    self.deploy._DeployTestBinaries()
    self._AssertBinariesInStagingDir(test_binaries)

  def testRetrySuccess(self):
    """Ensure that a transient exception still results in success."""
    # Raises a RunCommandError on its first invocation, but passes on subsequent
    # calls.
    def SideEffect(*args, **kwargs):
      # pylint: disable=unused-argument
      if not SideEffect.called:
        SideEffect.called = True
        raise cros_build_lib.RunCommandError('fail')
    SideEffect.called = False

    test_binaries = self._SimulateBinaries()
    with mock.patch.object(
        remote_access.ChromiumOSDevice, 'CopyToDevice',
        side_effect=SideEffect) as copy_mock:
      self.deploy._DeployTestBinaries()
      self.assertEqual(copy_mock.call_count, 2)
    self._AssertBinariesInStagingDir(test_binaries)

  def testRetryFailure(self):
    """Ensure that consistent exceptions result in failure."""
    self._SimulateBinaries()
    with self.assertRaises(cros_build_lib.RunCommandError):
      with mock.patch.object(
          remote_access.ChromiumOSDevice, 'CopyToDevice',
          side_effect=cros_build_lib.RunCommandError('fail')):
        self.deploy._DeployTestBinaries()


class LacrosPerformTest(cros_test_lib.RunCommandTempDirTestCase):
  """Line coverage for Perform() method with --lacros option."""

  def setUp(self):
    self.deploy = None
    self._ran_start_command = False
    self.StartPatcher(parallel_unittest.ParallelMock())

    def start_ui_side_effect(*args, **kwargs):
      # pylint: disable=unused-argument
      self._ran_start_command = True

    self.rc.AddCmdResult(partial_mock.In('start ui'),
                         side_effect=start_ui_side_effect)

  def prepareDeploy(self, options=None):
    if not options:
      options = _ParseCommandLine([
          '--lacros', '--nostrip', '--build-dir', '/path/to/nowhere',
          '--device', 'monkey'
      ])
    self.deploy = deploy_chrome.DeployChrome(
        options, self.tempdir, os.path.join(self.tempdir, 'staging'))

    # These methods being mocked are all side effects expected for a --lacros
    # deploy.
    self.deploy._EnsureTargetDir = mock.Mock()
    self.deploy._GetDeviceInfo = mock.Mock()
    self.deploy._CheckConnection = mock.Mock()
    self.deploy._MountRootfsAsWritable = mock.Mock()
    self.deploy._PrepareStagingDir = mock.Mock()
    self.deploy._CheckDeviceFreeSpace = mock.Mock()
    self.deploy._KillAshChromeIfNeeded = mock.Mock()

  def testConfNotModified(self):
    """When the conf file is not modified we don't restart chrome ."""
    self.prepareDeploy()
    self.deploy.Perform()
    self.deploy._KillAshChromeIfNeeded.assert_not_called()
    self.assertFalse(self._ran_start_command)

  def testConfModified(self):
    """When the conf file is modified we restart chrome."""
    self.prepareDeploy()

    # We intentionally add '\n' to MODIFIED_CONF_FILE to simulate echo adding a
    # newline when invoked in the shell.
    self.rc.AddCmdResult(
        partial_mock.In(deploy_chrome.ENABLE_LACROS_VIA_CONF_COMMAND),
        stdout=deploy_chrome.MODIFIED_CONF_FILE + '\n')

    self.deploy.Perform()
    self.deploy._KillAshChromeIfNeeded.assert_called()
    self.assertTrue(self._ran_start_command)

  def testSkipModifyingConf(self):
    """SKip modifying the config file when the argument is specified."""
    self.prepareDeploy(
        _ParseCommandLine([
            '--lacros', '--nostrip', '--build-dir', '/path/to/nowhere',
            '--device', 'monkey', '--skip-modifying-config-file'
        ]))

    self.rc.AddCmdResult(
        partial_mock.In(deploy_chrome.ENABLE_LACROS_VIA_CONF_COMMAND),
        stdout=deploy_chrome.MODIFIED_CONF_FILE + '\n')

    self.deploy.Perform()
    self.deploy._KillAshChromeIfNeeded.assert_not_called()
    self.assertFalse(self._ran_start_command)
