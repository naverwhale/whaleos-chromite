# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for the device_imager module."""

import os
import tempfile
import time
from unittest import mock

from chromite.cli import device_imager
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import gs
from chromite.lib import image_lib
from chromite.lib import image_lib_unittest
from chromite.lib import partial_mock
from chromite.lib import remote_access
from chromite.lib import remote_access_unittest
from chromite.lib import stateful_updater
from chromite.lib.paygen import paygen_stateful_payload_lib
from chromite.lib.xbuddy import xbuddy


# pylint: disable=protected-access


def GetFdPath(fd):
  """Returns the fd path for the current process."""
  return f'/proc/self/fd/{fd}'


class DeviceImagerTest(cros_test_lib.MockTestCase):
  """Tests DeviceImager class methods."""

  def setUp(self):
    """Sets up the class by creating proper mocks."""
    self.rsh_mock = self.StartPatcher(remote_access_unittest.RemoteShMock())
    self.rsh_mock.AddCmdResult(partial_mock.In('${PATH}'), stdout='')
    self.path_env = 'PATH=%s:' % remote_access.DEV_BIN_PATHS

  def test_LocateImageLocalFile(self):
    """Tests getting the path to local image."""
    with tempfile.NamedTemporaryFile() as fp:
      di = device_imager.DeviceImager(None, fp.name)
      di._LocateImage()
      self.assertEqual(di._image, fp.name)
      self.assertEqual(di._image_type, device_imager.ImageType.FULL)

  def test_LocateImageDir(self):
    """Tests failing on a given directory as a path."""
    di = device_imager.DeviceImager(None, '/tmp')
    with self.assertRaises(ValueError):
      di._LocateImage()

  @mock.patch.object(xbuddy.XBuddy, 'Translate', return_value=('eve/R90', None))
  @mock.patch.object(remote_access.ChromiumOSDevice, 'board',
                     return_value='foo', new_callable=mock.PropertyMock)
  # pylint: disable=unused-argument
  def test_LocateImageXBuddyRemote(self, _, board_mock):
    """Tests getting remote xBuddy image path."""
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      di = device_imager.DeviceImager(device, 'xbuddy://remote/eve/latest')
      di._LocateImage()
      self.assertEqual(di._image, 'gs://chromeos-image-archive/eve/R90')
      self.assertEqual(di._image_type, device_imager.ImageType.REMOTE_DIRECTORY)

  @mock.patch.object(xbuddy.XBuddy, 'Translate',
                     return_value=('eve/R90', 'path/to/file'))
  @mock.patch.object(remote_access.ChromiumOSDevice, 'board',
                     return_value='foo', new_callable=mock.PropertyMock)
  # pylint: disable=unused-argument
  def test_LocateImageXBuddyLocal(self, _, board_mock):
    """Tests getting local xBuddy image path."""
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      di = device_imager.DeviceImager(device, 'xbuddy://local/eve/latest')
      di._LocateImage()
      self.assertEqual(di._image, 'path/to/file')
      self.assertEqual(di._image_type, device_imager.ImageType.FULL)

  def test_SplitDevPath(self):
    """Tests splitting a device path into prefix and partition number."""

    di = device_imager.DeviceImager(None, None)
    self.assertEqual(di._SplitDevPath('/dev/foop3'), ('/dev/foop', 3))

    with self.assertRaises(device_imager.Error):
      di._SplitDevPath('/foo')

    with self.assertRaises(device_imager.Error):
      di._SplitDevPath('/foo/p3p')

  def test_GetKernelState(self):
    """Tests getting the current active and inactive kernel states."""
    di = device_imager.DeviceImager(None, None)
    self.assertEqual(di._GetKernelState(3), (device_imager.DeviceImager.A,
                                             device_imager.DeviceImager.B))
    self.assertEqual(di._GetKernelState(5), (device_imager.DeviceImager.B,
                                             device_imager.DeviceImager.A))

    with self.assertRaises(device_imager.Error):
      di._GetKernelState(1)

  @mock.patch.object(remote_access.ChromiumOSDevice, 'root_dev',
                     return_value='/dev/foop3', new_callable=mock.PropertyMock)
  def test_VerifyBootExpectations(self, _):
    """Tests verifying the boot expectations after reboot."""

    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      di = device_imager.DeviceImager(device, None)
      di._inactive_state = device_imager.DeviceImager.A
      di._VerifyBootExpectations()

  @mock.patch.object(remote_access.ChromiumOSDevice, 'root_dev',
                     return_value='/dev/foop3', new_callable=mock.PropertyMock)
  def test_VerifyBootExpectationsFails(self, _):
    """Tests failure of boot expectations."""

    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      di = device_imager.DeviceImager(device, None)
      di._inactive_state = device_imager.DeviceImager.B
      with self.assertRaises(device_imager.Error):
        di._VerifyBootExpectations()


class TestReaderBase(cros_test_lib.MockTestCase):
  """Test ReaderBase class"""

  def testNamedPipe(self):
    """Tests initializing the class with named pipe."""
    with device_imager.ReaderBase(use_named_pipes=True) as r:
      self.assertIsInstance(r.Target(), str)
      self.assertEqual(r._Source(), r.Target())
      self.assertExists(r.Target())

      r._CloseSource()  # Should not have any effect.
      self.assertExists(r._Source())

    # Closing target should delete the named pipe.
    r.CloseTarget()
    self.assertNotExists(r.Target())

  def testFdPipe(self):
    """Tests initializing the class with normal file descriptor pipes."""
    with device_imager.ReaderBase() as r:
      self.assertIsInstance(r.Target(), int)
      self.assertIsInstance(r._Source(), int)
      self.assertNotEqual(r._Source(), r.Target())
      self.assertExists(GetFdPath(r.Target()))
      self.assertExists(GetFdPath(r._Source()))

      # Per crbug.com/1196702 it seems like some other process gets the file
      # descriptor right after we close it and by the time we check its
      # existence, it is still there and this can flake. So it might be better
      # to make sure this is checked properly through real paths and not
      # symlinks.
      path = GetFdPath(r._Source())
      old_path = os.path.realpath(path)
      r._CloseSource()
      with self.assertRaises(OSError):
        new_path = os.path.realpath(path)
        self.assertNotEqual(old_path, new_path)
        raise OSError('Fake the context manager.')

      self.assertExists(GetFdPath(r.Target()))

    path = GetFdPath(r.Target())
    old_path = os.path.realpath(path)
    r.CloseTarget()
    with self.assertRaises(OSError):
      new_path = os.path.realpath(path)
      self.assertNotEqual(old_path, new_path)
      raise OSError('Fake the context manager.')

  def testFdPipeCommunicate(self):
    """Tests that file descriptors pipe can actually communicate."""
    with device_imager.ReaderBase() as r:
      with os.fdopen(r._Source(), 'w') as fp:
        fp.write('helloworld')

    with os.fdopen(r.Target(), 'r') as fp:
      self.assertEqual(fp.read(), 'helloworld')


class PartialFileReaderTest(cros_test_lib.RunCommandTestCase):
  """Tests PartialFileReader class."""

  def testRun(self):
    """Tests the main run() function."""
    with device_imager.PartialFileReader(
          '/foo', 512 * 2, 512, cros_build_lib.COMP_GZIP) as pfr:
      pass

    self.assertCommandCalled(
        'dd status=none if=/foo ibs=512 skip=2 count=1 | /usr/bin/pigz',
        stdout=pfr._Source(), shell=True)

    # Make sure the source has been close.
    self.assertNotExists(GetFdPath(pfr._Source()))


class GsFileCopierTest(cros_test_lib.TestCase):
  """Tests GsFileCopier class."""

  @mock.patch.object(gs.GSContext, 'Copy')
  def testRun(self, copy_mock):
    """Tests the run() function."""
    image = 'gs://path/to/image'
    with device_imager.GsFileCopier(image) as gfc:
      self.assertTrue(gfc._use_named_pipes)

    copy_mock.assert_called_with(image, gfc._Source())


class PartitionUpdaterBaseTest(cros_test_lib.TestCase):
  """Tests PartitionUpdaterBase class"""

  def testRunNotImplemented(self):
    """Tests running the main Run() function is not implemented."""
    # We just want to make sure the _Run() function is not implemented here.
    pub = device_imager.PartitionUpdaterBase(None, None, None, None, None)
    with self.assertRaises(NotImplementedError):
      pub.Run()

  def testRevertNotImplemented(self):
    """Tests running the Revert() function is not implemented."""
    pub = device_imager.PartitionUpdaterBase(None, None, None, None, None)
    with self.assertRaises(NotImplementedError):
      pub.Revert()

  @mock.patch.object(device_imager.PartitionUpdaterBase, '_Run')
  def testIsFinished(self, _):
    """Tests IsFinished() function."""
    pub = device_imager.PartitionUpdaterBase(None, None, None, None, None)
    self.assertFalse(pub.IsFinished())
    pub.Run()
    self.assertTrue(pub.IsFinished())


class RawPartitionUpdaterTest(cros_test_lib.MockTempDirTestCase):
  """Tests RawPartitionUpdater class."""

  def setUp(self):
    """Sets up the class by creating proper mocks."""
    self.rsh_mock = self.StartPatcher(remote_access_unittest.RemoteShMock())
    self.rsh_mock.AddCmdResult(partial_mock.In('${PATH}'), stdout='')
    self.path_env = 'PATH=%s:' % remote_access.DEV_BIN_PATHS

  @mock.patch.object(device_imager.RawPartitionUpdater, '_GetPartitionName',
                     return_value=constants.PART_KERN_A)
  @mock.patch.object(image_lib, 'GetImageDiskPartitionInfo',
                     return_value=image_lib_unittest.LOOP_PARTITION_INFO)
  @mock.patch.object(device_imager.PartialFileReader, 'CloseTarget')
  @mock.patch.object(device_imager.PartialFileReader, 'run')
  def test_RunFullImage(self, run_mock, close_mock, _, name_mock):
    """Test main Run() function for full image.

    This function should parts of the source image and write it into the device
    using proper compression programs.
    """
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      self.rsh_mock.AddCmdResult([partial_mock.In('which'), 'gzip'],
                                 returncode=0)
      self.rsh_mock.AddCmdResult(
        self.path_env +
        ' gzip --decompress --stdout | dd bs=1M oflag=direct of=/dev/mmcblk0p2')

      device_imager.RawPartitionUpdater(
          device, 'foo-image', device_imager.ImageType.FULL,
          '/dev/mmcblk0p2', cros_build_lib.COMP_GZIP).Run()
      run_mock.assert_called()
      close_mock.assert_called()
      name_mock.assert_called()

  def test_RunRemoteImage(self):
    """Test main Run() function for remote images."""
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      self.rsh_mock.AddCmdResult([partial_mock.In('which'), 'gzip'],
                                 returncode=0)
      self.rsh_mock.AddCmdResult(
        self.path_env +
        ' gzip --decompress --stdout | dd bs=1M oflag=direct of=/dev/mmcblk0p2')

      path = os.path.join(self.tempdir,
                          constants.QUICK_PROVISION_PAYLOAD_KERNEL)
      with open(path, 'w') as image:
        image.write('helloworld')

      device_imager.KernelUpdater(
          device, self.tempdir, device_imager.ImageType.REMOTE_DIRECTORY,
          '/dev/mmcblk0p2', cros_build_lib.COMP_GZIP).Run()


class KernelUpdaterTest(cros_test_lib.MockTempDirTestCase):
  """Tests KernelUpdater class."""

  def test_GetPartitionName(self):
    """Tests the name of the partitions."""
    ku = device_imager.KernelUpdater(None, None, None, None, None)
    self.assertEqual(constants.PART_KERN_B, ku._GetPartitionName())

  def test_GetRemotePartitionName(self):
    """Tests the name of the partitions."""
    ku = device_imager.KernelUpdater(None, None, None, None, None)
    self.assertEqual(constants.QUICK_PROVISION_PAYLOAD_KERNEL,
                     ku._GetRemotePartitionName())


class MiniOSUpdaterTest(cros_test_lib.MockTempDirTestCase):
  """Tests MiniOSUpdater class."""

  def test_GetPartitionName(self):
    """Tests the name of the partitions."""
    u = device_imager.MiniOSUpdater(*([None] * 5))
    self.assertEqual(constants.PART_MINIOS_A, u._GetPartitionName())

  def test_GetRemotePartitionName(self):
    """Tests the name of the partitions."""
    # TODO(b/190631159, b/196056723): Allow fetching once miniOS payloads exist.
    u = device_imager.MiniOSUpdater(*([None] * 5))
    with self.assertRaises(NotImplementedError):
      u._GetRemotePartitionName()

  @mock.patch.object(device_imager.MiniOSUpdater, '_CopyPartitionFromImage')
  @mock.patch.object(device_imager.MiniOSUpdater, '_MiniOSPartitionExists',
                     return_value=True)
  @mock.patch.object(device_imager.MiniOSUpdater, '_RunPostInstall')
  def test_Run(self, postinstall_mock, minios_mock, copy_mock):
    """Test main Run() function."""
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      device_imager.MiniOSUpdater(
          device, 'foo-image', device_imager.ImageType.FULL,
          '/dev/mmcblk0p10', cros_build_lib.COMP_GZIP).Run()

      copy_mock.assert_called_with(constants.PART_MINIOS_A)
      minios_mock.assert_called_with()
      postinstall_mock.assert_called_with()

  @mock.patch.object(device_imager.MiniOSUpdater, '_CopyPartitionFromImage')
  @mock.patch.object(device_imager.MiniOSUpdater, '_MiniOSPartitionExists',
                     return_value=False)
  @mock.patch.object(device_imager.MiniOSUpdater, '_RunPostInstall')
  def test_RunMissingMiniOS(self, postinstall_mock, minios_mock, copy_mock):
    """Test main Run() function."""
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      device_imager.MiniOSUpdater(
          device, 'foo-image', device_imager.ImageType.FULL,
          '/dev/mmcblk0p10', cros_build_lib.COMP_GZIP).Run()

      copy_mock.assert_not_called()
      minios_mock.assert_called_with()
      postinstall_mock.assert_called_with()

  @mock.patch.object(device_imager.MiniOSUpdater, '_FlipMiniOSPriority')
  def test_RunPostInstall(self, flip_mock):
    """Test _RunPostInstall() function."""
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      device_imager.MiniOSUpdater(
          device, 'foo-image', device_imager.ImageType.FULL,
          '/dev/mmcblk0p10', cros_build_lib.COMP_GZIP)._RunPostInstall()

      flip_mock.assert_called_with()

  @mock.patch.object(device_imager.MiniOSUpdater, '_FlipMiniOSPriority')
  def test_Revert(self, flip_mock):
    """Test Revert() function."""
    u = device_imager.MiniOSUpdater(
          None, 'foo-image', device_imager.ImageType.FULL,
          '/dev/mmcblk0p10', cros_build_lib.COMP_GZIP)

    # Before PostInstall runs.
    u.Revert()
    flip_mock.assert_not_called()

    u._ran_postinst = True
    u.Revert()

    flip_mock.assert_called_with()

  @mock.patch.object(device_imager.MiniOSUpdater, '_GetMiniOSPriority',
                     return_value='A')
  @mock.patch.object(device_imager.MiniOSUpdater, '_SetMiniOSPriority')
  def test_FlipMiniOSPriority(self, set_mock, get_mock):
    """Test _FlipMiniOSPriority() function."""
    device_imager.MiniOSUpdater(
          None, 'foo-image', device_imager.ImageType.FULL,
          '/dev/mmcblk0p10', cros_build_lib.COMP_GZIP)._FlipMiniOSPriority()

    get_mock.assert_called_with()
    set_mock.assert_called_with('B')


class RootfsUpdaterTest(cros_test_lib.MockTestCase):
  """Tests RootfsUpdater class."""

  def setUp(self):
    """Sets up the class by creating proper mocks."""
    self.rsh_mock = self.StartPatcher(remote_access_unittest.RemoteShMock())
    self.rsh_mock.AddCmdResult(partial_mock.In('${PATH}'), stdout='')
    self.path_env = 'PATH=%s:' % remote_access.DEV_BIN_PATHS

  def test_GetPartitionName(self):
    """Tests the name of the partitions."""
    ru = device_imager.RootfsUpdater(None, None, None, None, None, None)
    self.assertEqual(constants.PART_ROOT_A, ru._GetPartitionName())

  def test_GetRemotePartitionName(self):
    """Tests the name of the partitions."""
    ru = device_imager.RootfsUpdater(None, None, None, None, None, None)
    self.assertEqual(constants.QUICK_PROVISION_PAYLOAD_ROOTFS,
                     ru._GetRemotePartitionName())

  @mock.patch.object(device_imager.ProgressWatcher, 'run')
  @mock.patch.object(device_imager.RootfsUpdater, '_RunPostInst')
  @mock.patch.object(device_imager.RootfsUpdater, '_CopyPartitionFromImage')
  def test_Run(self, copy_mock, postinst_mock, pw_mock):
    """Test main Run() function.

    This function should parts of the source image and write it into the device
    using proper compression programs.
    """
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      device_imager.RootfsUpdater(
          '/dev/mmcblk0p5', device, 'foo-image', device_imager.ImageType.FULL,
          '/dev/mmcblk0p3', cros_build_lib.COMP_GZIP).Run()

      copy_mock.assert_called_with(constants.PART_ROOT_A)
      postinst_mock.assert_called_with()
      pw_mock.assert_called()

  def test_RunPostInstOnTarget(self):
    """Test _RunPostInst() function."""
    target = '/dev/mmcblk0p3'
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      device._work_dir = '/tmp/work_dir'
      temp_dir = os.path.join(device.work_dir, 'dir')
      self.rsh_mock.AddCmdResult(
          [self.path_env, 'mktemp', '-d', '-p', device.work_dir],
          stdout=temp_dir)
      self.rsh_mock.AddCmdResult(
          [self.path_env, 'mount', '-o', 'ro', target, temp_dir])
      self.rsh_mock.AddCmdResult(
          [self.path_env, os.path.join(temp_dir, 'postinst'), target])
      self.rsh_mock.AddCmdResult([self.path_env, 'umount', temp_dir])

      device_imager.RootfsUpdater(
          '/dev/mmcblk0p5', device, 'foo-image', device_imager.ImageType.FULL,
          target, cros_build_lib.COMP_GZIP)._RunPostInst()

  def test_RunPostInstOnCurrentRoot(self):
    """Test _RunPostInst() on current root (used for reverting an update)."""
    root_dev = '/dev/mmcblk0p5'
    self.rsh_mock.AddCmdResult([self.path_env, '/postinst', root_dev])

    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      device_imager.RootfsUpdater(
          root_dev, device, 'foo-image', device_imager.ImageType.FULL,
          '/dev/mmcblk0p3', cros_build_lib.COMP_GZIP)._RunPostInst(
              on_target=False)

  @mock.patch.object(device_imager.RootfsUpdater, '_RunPostInst')
  def testRevert(self, postinst_mock):
    """Tests Revert() function."""
    ru = device_imager.RootfsUpdater(None, None, None, None, None, None)

    ru.Revert()
    postinst_mock.assert_not_called()

    ru._ran_postinst = True
    ru.Revert()
    postinst_mock.assert_called_with(on_target=False)


class StatefulPayloadGeneratorTest(cros_test_lib.TestCase):
  """Tests stateful payload generator."""
  @mock.patch.object(paygen_stateful_payload_lib, 'GenerateStatefulPayload')
  def testRun(self, paygen_mock):
    """Tests run() function."""
    image = '/foo/image'
    with device_imager.StatefulPayloadGenerator(image) as spg:
      pass

    paygen_mock.assert_called_with(image, spg._Source())


class StatefulUpdaterTest(cros_test_lib.TestCase):
  """Tests StatefulUpdater."""
  @mock.patch.object(paygen_stateful_payload_lib, 'GenerateStatefulPayload')
  @mock.patch.object(stateful_updater.StatefulUpdater, 'Update')
  def test_RunFullImage(self, update_mock, paygen_mock):
    """Test main Run() function for full image."""
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      device_imager.StatefulUpdater(False, device, 'foo-image',
                                 device_imager.ImageType.FULL, None, None).Run()
      update_mock.assert_called_with(mock.ANY,
                                     is_payload_on_device=False,
                                     update_type=None)
      paygen_mock.assert_called()

  @mock.patch.object(gs.GSContext, 'Copy')
  @mock.patch.object(stateful_updater.StatefulUpdater, 'Update')
  def test_RunRemoteImage(self, update_mock, copy_mock):
    """Test main Run() function for remote images."""
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      device_imager.StatefulUpdater(False, device, 'gs://foo-image',
                                 device_imager.ImageType.REMOTE_DIRECTORY, None,
                                 None).Run()
      copy_mock.assert_called_with('gs://foo-image/stateful.tgz',mock.ANY)
      update_mock.assert_called_with(mock.ANY, is_payload_on_device=False,
                                     update_type=None)

  @mock.patch.object(stateful_updater.StatefulUpdater, 'Reset')
  def testRevert(self, reset_mock):
    """Tests Revert() function."""
    su = device_imager.StatefulUpdater(False, None, None, None, None, None)

    su.Revert()
    reset_mock.assert_called()


class ProgressWatcherTest(cros_test_lib.MockTestCase):
  """Tests ProgressWatcher class"""

  def setUp(self):
    """Sets up the class by creating proper mocks."""
    self.rsh_mock = self.StartPatcher(remote_access_unittest.RemoteShMock())
    self.rsh_mock.AddCmdResult(partial_mock.In('${PATH}'), stdout='')
    self.path_env = 'PATH=%s:' % remote_access.DEV_BIN_PATHS

  @mock.patch.object(time, 'sleep')
  @mock.patch.object(device_imager.ProgressWatcher, '_ShouldExit',
                     side_effect=[False, False, True])
  # pylint: disable=unused-argument
  def testRun(self, exit_mock, _):
    """Tests the run() function."""
    with remote_access.ChromiumOSDeviceHandler(remote_access.TEST_IP) as device:
      target_root = '/foo/root'
      self.rsh_mock.AddCmdResult(
          [self.path_env, 'blockdev', '--getsize64', target_root], stdout='100')
      self.rsh_mock.AddCmdResult(
          self.path_env + f' lsof 2>/dev/null | grep {target_root}',
          stdout='xz 999')
      self.rsh_mock.AddCmdResult([self.path_env, 'cat', '/proc/999/fdinfo/1'],
                                 stdout='pos:   10\nflags:  foo')
      pw = device_imager.ProgressWatcher(device, target_root)
      pw.run()
