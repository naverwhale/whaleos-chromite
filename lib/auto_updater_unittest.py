# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for the auto_updater module.

The main parts of unittest include:
  1. test transfer methods in ChromiumOSUpdater.
  2. test precheck methods in ChromiumOSUpdater.
  3. test update methods in ChromiumOSUpdater.
  4. test reboot and verify method in ChromiumOSUpdater.
  5. test error raising in ChromiumOSUpdater.
"""

import json
import os
from unittest import mock

from chromite.lib import auto_updater
from chromite.lib import auto_updater_transfer
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import nebraska_wrapper
from chromite.lib import partial_mock
from chromite.lib import remote_access
from chromite.lib import remote_access_unittest
from chromite.lib import stateful_updater


class ChromiumOSBaseUpdaterMock(partial_mock.PartialCmdMock):
  """Mock out all update and verify functions in ChromiumOSUpdater."""
  TARGET = 'chromite.lib.auto_updater.ChromiumOSUpdater'
  ATTRS = ('RestoreStateful', 'UpdateRootfs',
           'SetupRootfsUpdate', 'RebootAndVerify')

  def __init__(self):
    partial_mock.PartialCmdMock.__init__(self)

  def RestoreStateful(self, _inst, *_args, **_kwargs):
    """Mock out RestoreStateful."""

  def UpdateRootfs(self, _inst, *_args, **_kwargs):
    """Mock out UpdateRootfs."""

  def SetupRootfsUpdate(self, _inst, *_args, **_kwargs):
    """Mock out SetupRootfsUpdate."""

  def RebootAndVerify(self, _inst, *_args, **_kwargs):
    """Mock out RebootAndVerify."""


class TransferMock(partial_mock.PartialCmdMock):
  """Mock out all transfer functions in auto_updater_transfer.LocalTransfer."""
  TARGET = 'chromite.lib.auto_updater_transfer.LocalTransfer'
  ATTRS = ('TransferUpdateUtilsPackage', 'TransferRootfsUpdate',
           'TransferStatefulUpdate', 'CheckPayloads')

  def __init__(self):
    partial_mock.PartialCmdMock.__init__(self)

  def CheckPayloads(self, _inst, *_args, **_kwargs):
    """Mock auto_updater_transfer.Transfer.CheckPayloads."""

  def TransferUpdateUtilsPackage(self, _inst, *_args, **_kwargs):
    """Mock auto_updater_transfer.LocalTransfer.TransferUpdateUtilsPackage."""

  def TransferRootfsUpdate(self, _inst, *_args, **_kwargs):
    """Mock auto_updater_transfer.LocalTransfer.TransferRootfsUpdate."""

  def TransferStatefulUpdate(self, _inst, *_args, **_kwargs):
    """Mock auto_updater_transfer.LocalTransfer.TransferStatefulUpdate."""


class ChromiumOSPreCheckMock(partial_mock.PartialCmdMock):
  """Mock out Precheck function in auto_updater.ChromiumOSUpdater."""
  TARGET = 'chromite.lib.auto_updater.ChromiumOSUpdater'
  ATTRS = ('CheckRestoreStateful', '_CheckNebraskaCanRun')

  def __init__(self):
    partial_mock.PartialCmdMock.__init__(self)

  def CheckRestoreStateful(self, _inst, *_args, **_kwargs):
    """Mock out auto_updater.ChromiumOSUpdater.CheckRestoreStateful."""

  def _CheckNebraskaCanRun(self, _inst, *_args, **_kwargs):
    """Mock out auto_updater.ChromiumOSUpdater._CheckNebraskaCanRun."""


class RemoteAccessMock(remote_access_unittest.RemoteShMock):
  """Mock out RemoteAccess."""

  ATTRS = ('RemoteSh', 'Rsync', 'Scp')

  def Rsync(self, *_args, **_kwargs):
    return cros_build_lib.CommandResult(returncode=0)

  def Scp(self, *_args, **_kwargs):
    return cros_build_lib.CommandResult(returncode=0)


class ChromiumOSUpdaterBaseTest(cros_test_lib.MockTempDirTestCase):
  """The base class for auto_updater.ChromiumOSUpdater test.

  In the setup, device, all transfer and update functions are mocked.
  """

  def setUp(self):
    self._payload_dir = self.tempdir
    self._base_updater_mock = self.StartPatcher(ChromiumOSBaseUpdaterMock())
    self._transfer_mock = self.StartPatcher(TransferMock())
    self.PatchObject(remote_access.ChromiumOSDevice, 'Pingable',
                     return_value=True)
    m = self.StartPatcher(RemoteAccessMock())
    m.SetDefaultCmdResult()


class TransferTest(ChromiumOSUpdaterBaseTest):
  """Test the transfer code path."""

  def testTransferForRootfs(self):
    """Test transfer functions for rootfs update.

    When rootfs update is enabled, update-utils and rootfs update payload are
    transferred. Stateful update payload is not.
    """
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir, do_stateful_update=False,
          transfer_class=auto_updater_transfer.LocalTransfer)
      CrOS_AU.RunUpdate()
      self.assertTrue(
          self._transfer_mock.patched['CheckPayloads'].called)
      self.assertTrue(
          self._transfer_mock.patched['TransferUpdateUtilsPackage'].called)
      self.assertTrue(
          self._transfer_mock.patched['TransferRootfsUpdate'].called)
      self.assertFalse(
          self._transfer_mock.patched['TransferStatefulUpdate'].called)


class ChromiumOSUpdatePreCheckTest(ChromiumOSUpdaterBaseTest):
  """Test precheck function."""

  def testCheckRestoreStateful(self):
    """Test whether CheckRestoreStateful is called in update process."""
    precheck_mock = self.StartPatcher(ChromiumOSPreCheckMock())
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir,
          transfer_class=auto_updater_transfer.LocalTransfer)
      CrOS_AU.RunUpdate()
      self.assertTrue(precheck_mock.patched['CheckRestoreStateful'].called)

  def testCheckRestoreStatefulError(self):
    """Test CheckRestoreStateful fails with raising ChromiumOSUpdateError."""
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir,
          transfer_class=auto_updater_transfer.LocalTransfer)
      self.PatchObject(cros_build_lib, 'BooleanPrompt', return_value=False)
      self.PatchObject(auto_updater.ChromiumOSUpdater,
                       '_CheckNebraskaCanRun',
                       side_effect=nebraska_wrapper.NebraskaStartupError())
      self.assertRaises(auto_updater.ChromiumOSUpdateError, CrOS_AU.RunUpdate)

  def testNoPomptWithYes(self):
    """Test prompts won't be called if yes is set as True."""
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir, yes=True,
          transfer_class=auto_updater_transfer.LocalTransfer)
      self.PatchObject(cros_build_lib, 'BooleanPrompt')
      CrOS_AU.RunUpdate()
      self.assertFalse(cros_build_lib.BooleanPrompt.called)


class ChromiumOSUpdaterRunTest(ChromiumOSUpdaterBaseTest):
  """Test all update functions."""

  def testRestoreStateful(self):
    """Test RestoreStateful is called when it's required."""
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir,
          transfer_class=auto_updater_transfer.LocalTransfer)
      self.PatchObject(auto_updater.ChromiumOSUpdater,
                       'CheckRestoreStateful',
                       return_value=True)
      CrOS_AU.RunUpdate()
      self.assertTrue(self._base_updater_mock.patched['RestoreStateful'].called)

  def testRunRootfs(self):
    """Test the update functions are called correctly.

    SetupRootfsUpdate and UpdateRootfs are called for rootfs update.
    """
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir, do_stateful_update=False,
          transfer_class=auto_updater_transfer.LocalTransfer)
      stateful_update_mock = self.PatchObject(auto_updater.ChromiumOSUpdater,
                                              'UpdateStateful')

      CrOS_AU.RunUpdate()
      self.assertTrue(
          self._base_updater_mock.patched['SetupRootfsUpdate'].called)
      self.assertTrue(self._base_updater_mock.patched['UpdateRootfs'].called)
      stateful_update_mock.assert_not_called()

  def testUpdateStatefulCopyStateful(self):
    """Tests stateful update when stateful payload is copied to device."""
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir, do_rootfs_update=False,
          transfer_class=auto_updater_transfer.LocalTransfer)
      update_mock = self.PatchObject(stateful_updater.StatefulUpdater, 'Update')

      CrOS_AU.RunUpdate()
      update_mock.assert_called_with(
          auto_updater_transfer.STATEFUL_FILENAME, is_payload_on_device=True,
          update_type=None)
      self.assertTrue(
          self._transfer_mock.patched['TransferStatefulUpdate'].called)

  def testUpdateStatefulNoCopyStateful(self):
    """Tests stateful update when stateful payload is not copied to device."""
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir, do_rootfs_update=False,
          transfer_class=auto_updater_transfer.LocalTransfer,
          copy_payloads_to_device=False)
      update_mock = self.PatchObject(stateful_updater.StatefulUpdater, 'Update')

      CrOS_AU.RunUpdate()
      update_mock.assert_called_with(
          os.path.join(self._payload_dir,
                       auto_updater_transfer.STATEFUL_FILENAME),
          is_payload_on_device=False,
          update_type=None)

  def testMismatchedAppId(self):
    """Tests if App ID is set to empty when there's a mismatch."""
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir, payload_filename='payload',
          transfer_class=auto_updater_transfer.LocalTransfer)
      prop_file = os.path.join(self._payload_dir, 'payload.json')
      with open(prop_file, 'w') as fp:
        json.dump({'appid': 'helloworld!'}, fp)
      type(device).app_id = mock.PropertyMock(return_value='different')
      # pylint: disable=protected-access
      CrOS_AU._ResolveAPPIDMismatchIfAny()
      with open(prop_file) as fp:
        self.assertEqual(json.load(fp), {'appid': ''})

  def testMatchedAppId(self):
    """Tests if App ID is unchanged when there's a match."""
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir, payload_filename='payload',
          transfer_class=auto_updater_transfer.LocalTransfer)
      prop_file = os.path.join(self._payload_dir, 'payload.json')
      with open(prop_file, 'w') as fp:
        json.dump({'appid': 'same'}, fp)
      type(device).app_id = mock.PropertyMock(return_value='same')
      # pylint: disable=protected-access
      CrOS_AU._ResolveAPPIDMismatchIfAny()
      with open(prop_file) as fp:
        self.assertEqual(json.load(fp), {'appid': 'same'})

  def testCreateTransferObjectError(self):
    """Test ChromiumOSUpdater.CreateTransferObject method.

    Tests if the method throws ChromiumOSUpdater error when a class that is not
    a subclass of auto_updater_transfer.Transfer is passed as value for the
    transfer_class argument.
    """
    class NotATransferSubclass(object):
      """Dummy class for testing ChromiumOSUpdater.CreateTransferObject."""

    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      self.assertRaises(AssertionError,
                        auto_updater.ChromiumOSUpdater, device=device,
                        build_name=None, payload_dir=self._payload_dir,
                        staging_server='http://0.0.0.0:8082/',
                        transfer_class=NotATransferSubclass)


class ChromiumOSUpdaterVerifyTest(ChromiumOSUpdaterBaseTest):
  """Test verify function in ChromiumOSUpdater."""

  def testRebootAndVerifyWithRootfsAndReboot(self):
    """Test RebootAndVerify if rootfs update and reboot are enabled."""
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir,
          transfer_class=auto_updater_transfer.LocalTransfer)
      CrOS_AU.RunUpdate()
      self.assertTrue(self._base_updater_mock.patched['RebootAndVerify'].called)

  def testRebootAndVerifyWithoutReboot(self):
    """Test RebootAndVerify doesn't run if reboot is unenabled."""
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir, reboot=False,
          transfer_class=auto_updater_transfer.LocalTransfer)
      CrOS_AU.RunUpdate()
      self.assertFalse(
          self._base_updater_mock.patched['RebootAndVerify'].called)


class ChromiumOSErrorTest(cros_test_lib.MockTestCase):
  """Base class for error test in auto_updater."""

  def setUp(self):
    """Mock device's functions for update.

    Not mock the class ChromiumOSDevice, in order to raise the errors that
    caused by a inner function of the device's base class, like 'run'.
    """
    self._payload_dir = ''
    self.PatchObject(remote_access.RemoteDevice, 'Pingable', return_value=True)
    self.PatchObject(remote_access.RemoteDevice, 'work_dir', new='')
    self.PatchObject(remote_access.RemoteDevice, 'Reboot')
    self.PatchObject(remote_access.RemoteDevice, 'Cleanup')


class ChromiumOSUpdaterRunErrorTest(ChromiumOSErrorTest):
  """Test whether error is correctly reported during update process."""

  def setUp(self):
    """Mock device's function, and transfer/precheck functions for update.

    Since cros_test_lib.MockTestCase run all setUp & tearDown methods in the
    inheritance tree, we don't call super().setUp().
    """
    self.StartPatcher(TransferMock())
    self.StartPatcher(ChromiumOSPreCheckMock())

  def prepareRootfsUpdate(self):
    """Prepare work for test errors in rootfs update."""
    self.PatchObject(auto_updater.ChromiumOSUpdater, 'SetupRootfsUpdate')
    self.PatchObject(auto_updater.ChromiumOSUpdater, 'GetRootDev')
    self.PatchObject(nebraska_wrapper.RemoteNebraskaWrapper, 'PrintLog')
    self.PatchObject(remote_access.RemoteDevice, 'CopyFromDevice')

  def testRestoreStatefulError(self):
    """Test ChromiumOSUpdater.RestoreStateful with raising exception.

    Nebraska still cannot run after restoring stateful partition will lead
    to ChromiumOSUpdateError.
    """
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir,
          transfer_class=auto_updater_transfer.LocalTransfer)
      self.PatchObject(auto_updater.ChromiumOSUpdater,
                       'CheckRestoreStateful',
                       return_value=True)
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'SetupRootfsUpdate')
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'RunUpdateRootfs')
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'PreSetupStatefulUpdate')
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'ResetStatefulPartition')
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'UpdateStateful')
      self.PatchObject(auto_updater.ChromiumOSUpdater,
                       'PostCheckStatefulUpdate')
      self.PatchObject(auto_updater.ChromiumOSUpdater,
                       '_IsUpdateUtilsPackageInstalled')
      self.PatchObject(auto_updater.ChromiumOSUpdater,
                       '_CheckNebraskaCanRun',
                       side_effect=nebraska_wrapper.NebraskaStartupError())
      self.assertRaises(auto_updater.ChromiumOSUpdateError, CrOS_AU.RunUpdate)

  def testSetupRootfsUpdateError(self):
    """Test ChromiumOSUpdater.SetupRootfsUpdate with raising exception.

    RootfsUpdateError is raised if it cannot get status from GetUpdateStatus.
    """
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir,
          transfer_class=auto_updater_transfer.LocalTransfer)
      self.PatchObject(auto_updater.ChromiumOSUpdater,
                       '_StartUpdateEngineIfNotRunning')
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'GetUpdateStatus',
                       return_value=('cannot_update', ))
      self.assertRaises(auto_updater.RootfsUpdateError, CrOS_AU.RunUpdate)

  def testRootfsUpdateNebraskaError(self):
    """Test ChromiumOSUpdater.UpdateRootfs with raising exception.

    RootfsUpdateError is raised if nebraska cannot start.
    """
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir,
          transfer_class=auto_updater_transfer.LocalTransfer)
      self.prepareRootfsUpdate()
      self.PatchObject(nebraska_wrapper.RemoteNebraskaWrapper, 'Start',
                       side_effect=nebraska_wrapper.Error())
      self.PatchObject(auto_updater.ChromiumOSUpdater,
                       'RevertBootPartition')
      with mock.patch('os.path.join', return_value=''):
        self.assertRaises(auto_updater.RootfsUpdateError, CrOS_AU.RunUpdate)

  def testRootfsUpdateCmdError(self):
    """Test ChromiumOSUpdater.UpdateRootfs with raising exception.

    RootfsUpdateError is raised if device fails to run rootfs update command
    'update_engine_client ...'.
    """
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir,
          transfer_class=auto_updater_transfer.LocalTransfer)
      self.prepareRootfsUpdate()
      self.PatchObject(nebraska_wrapper.RemoteNebraskaWrapper, 'Start')
      self.PatchObject(nebraska_wrapper.RemoteNebraskaWrapper, 'GetURL')
      self.PatchObject(remote_access.ChromiumOSDevice, 'run',
                       side_effect=cros_build_lib.RunCommandError('fail'))
      self.PatchObject(auto_updater.ChromiumOSUpdater,
                       'RevertBootPartition')
      with mock.patch('os.path.join', return_value=''):
        self.assertRaises(auto_updater.RootfsUpdateError, CrOS_AU.RunUpdate)

  def testRootfsUpdateTrackError(self):
    """Test ChromiumOSUpdater.UpdateRootfs with raising exception.

    RootfsUpdateError is raised if it fails to track device's status by
    GetUpdateStatus.
    """
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir,
          transfer_class=auto_updater_transfer.LocalTransfer)
      self.prepareRootfsUpdate()
      self.PatchObject(nebraska_wrapper.RemoteNebraskaWrapper, 'Start')
      self.PatchObject(nebraska_wrapper.RemoteNebraskaWrapper, 'GetURL')
      self.PatchObject(remote_access.ChromiumOSDevice, 'run')
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'GetUpdateStatus',
                       side_effect=ValueError('Cannot get update status'))
      with mock.patch('os.path.join', return_value=''):
        self.assertRaises(auto_updater.RootfsUpdateError, CrOS_AU.RunUpdate)

  def testRootfsUpdateIdleError(self):
    """Test ChromiumOSUpdater.UpdateRootfs with raising exception.

    RootfsUpdateError is raised if the update engine goes to idle state
    after downloading.
    """
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir,
          transfer_class=auto_updater_transfer.LocalTransfer)
      self.prepareRootfsUpdate()
      self.PatchObject(nebraska_wrapper.RemoteNebraskaWrapper, 'Start')
      self.PatchObject(nebraska_wrapper.RemoteNebraskaWrapper, 'GetURL')
      mock_run = self.PatchObject(remote_access.ChromiumOSDevice, 'run')
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'GetUpdateStatus',
                       side_effect=(
                           ('UPDATE_STATUS_DOWNLOADING', '0.5'),
                           ('UPDATE_STATUS_DOWNLOADING', '0.9'),
                           ('UPDATE_STATUS_FINALIZING', 0),
                           ('UPDATE_STATUS_IDLE', 0),
                       ))
      patch_join = mock.patch('os.path.join', return_value='')
      patch_sleep = mock.patch('time.sleep')
      with patch_sleep as mock_sleep, patch_join as _:
        self.assertRaises(auto_updater.RootfsUpdateError, CrOS_AU.RunUpdate)
        mock_sleep.assert_called()
        mock_run.assert_any_call(['cat', '/var/log/update_engine.log'])

  def testStatefulUpdateCmdError(self):
    """Test ChromiumOSUpdater.UpdateStateful with raising exception.

    StatefulUpdateError is raised if device fails to update stateful partition.
    """
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir, do_rootfs_update=False,
          transfer_class=auto_updater_transfer.LocalTransfer)
      self.PatchObject(remote_access.ChromiumOSDevice, 'run',
                       side_effect=cros_build_lib.RunCommandError('fail'))
      self.PatchObject(stateful_updater.StatefulUpdater, 'Update',
                       side_effect=stateful_updater.Error())
      self.PatchObject(stateful_updater.StatefulUpdater, 'Reset',
                       side_effect=stateful_updater.Error())
      self.assertRaises(auto_updater.StatefulUpdateError, CrOS_AU.RunUpdate)

  def testVerifyErrorWithSameRootDev(self):
    """Test RebootAndVerify fails with raising AutoUpdateVerifyError."""
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir, do_stateful_update=False,
          transfer_class=auto_updater_transfer.LocalTransfer)
      self.PatchObject(remote_access.ChromiumOSDevice, 'run')
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'SetupRootfsUpdate')
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'UpdateRootfs')
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'GetRootDev',
                       return_value='fake_path')
      self.assertRaises(auto_updater.AutoUpdateVerifyError, CrOS_AU.RunUpdate)

  def testVerifyErrorWithRootDevEqualsNone(self):
    """Test RebootAndVerify fails with raising AutoUpdateVerifyError."""
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir, do_stateful_update=False,
          transfer_class=auto_updater_transfer.LocalTransfer)
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'SetupRootfsUpdate')
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'UpdateRootfs')
      self.PatchObject(remote_access.ChromiumOSDevice, 'run')
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'GetRootDev',
                       return_value=None)
      self.assertRaises(auto_updater.AutoUpdateVerifyError, CrOS_AU.RunUpdate)

  def testNoVerifyError(self):
    """Test RebootAndVerify won't raise any error when unable do_rootfs_update.

    If do_rootfs_update is unabled, verify logic won't be touched, which means
    no AutoUpdateVerifyError will be thrown.
    """
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, self._payload_dir, do_rootfs_update=False,
          transfer_class=auto_updater_transfer.LocalTransfer)
      self.PatchObject(remote_access.ChromiumOSDevice, 'run')
      self.PatchObject(auto_updater.ChromiumOSUpdater, 'GetRootDev',
                       return_value=None)
      self.PatchObject(stateful_updater.StatefulUpdater, 'Update')

      try:
        CrOS_AU.RunUpdate()
      except auto_updater.AutoUpdateVerifyError:
        self.fail('RunUpdate raise AutoUpdateVerifyError.')


class RetryCommand(cros_test_lib.RunCommandTestCase):
  """Base class for _RetryCommand tests."""

  def testRetryCommand(self):
    """Ensures that _RetryCommand can take both string and list args for cmd."""
    with remote_access.ChromiumOSDeviceHandler(
        remote_access.TEST_IP) as device:
      CrOS_AU = auto_updater.ChromiumOSUpdater(
          device, None, None, reboot=False,
          transfer_class=auto_updater_transfer.LocalTransfer)
      # pylint: disable=protected-access
      CrOS_AU._RetryCommand(['some', 'list', 'command'])
      self.assertCommandContains(['some', 'list', 'command'])
      CrOS_AU._RetryCommand('some string command')
      self.assertCommandContains('some string command')
