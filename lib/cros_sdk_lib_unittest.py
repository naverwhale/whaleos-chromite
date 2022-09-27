# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the cros_sdk_lib module."""

import os
from pathlib import Path

from chromite.lib import cros_build_lib
from chromite.lib import cros_sdk_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import partial_mock


class VersionHookTestCase(cros_test_lib.TempDirTestCase):
  """Class to set up tests that use the version hooks."""

  def setUp(self):
    # Build set of expected scripts.
    D = cros_test_lib.Directory
    filesystem = (
        D('hooks', (
            '8_invalid_gap',
            '10_run_success',
            '11_run_success',
            '12_run_success',
        )),
        'version_file',
    )
    cros_test_lib.CreateOnDiskHierarchy(self.tempdir, filesystem)

    self.chroot_path = os.path.join(self.tempdir, 'chroot')
    self.version_file = os.path.join(
        self.chroot_path, cros_sdk_lib.CHROOT_VERSION_FILE.lstrip(os.sep))
    osutils.WriteFile(self.version_file, '0', makedirs=True)
    self.hooks_dir = os.path.join(self.tempdir, 'hooks')

    self.earliest_version = 8
    self.latest_version = 12
    self.deprecated_versions = (6, 7, 8)
    self.invalid_versions = (13,)
    self.success_versions = (9, 10, 11, 12)


class TestGetFileSystemDebug(cros_test_lib.RunCommandTestCase):
  """Tests GetFileSystemDebug functionality."""

  def testNoPs(self):
    """Verify with run_ps=False."""
    self.rc.AddCmdResult(
        ['sudo', '--', 'fuser', '/some/path'], stdout='fuser_output')
    self.rc.AddCmdResult(
        ['sudo', '--', 'lsof', '/some/path'], stdout='lsof_output')
    file_system_debug_tuple = cros_sdk_lib.GetFileSystemDebug(
        '/some/path', run_ps=False)
    self.assertEqual(file_system_debug_tuple.fuser, 'fuser_output')
    self.assertEqual(file_system_debug_tuple.lsof, 'lsof_output')
    self.assertIsNone(file_system_debug_tuple.ps)

  def testWithPs(self):
    """Verify with run_ps=False."""
    self.rc.AddCmdResult(
        ['sudo', '--', 'fuser', '/some/path'], stdout='fuser_output')
    self.rc.AddCmdResult(
        ['sudo', '--', 'lsof', '/some/path'], stdout='lsof_output')
    self.rc.AddCmdResult(
        ['ps', 'auxf'], stdout='ps_output')
    file_system_debug_tuple = cros_sdk_lib.GetFileSystemDebug(
        '/some/path', run_ps=True)
    self.assertEqual(file_system_debug_tuple.fuser, 'fuser_output')
    self.assertEqual(file_system_debug_tuple.lsof, 'lsof_output')
    self.assertEqual(file_system_debug_tuple.ps, 'ps_output')


class TestGetChrootVersion(cros_test_lib.MockTestCase):
  """Tests GetChrootVersion functionality."""

  def testNoChroot(self):
    """Verify we don't blow up when there is no chroot yet."""
    self.PatchObject(cros_sdk_lib.ChrootUpdater, 'GetVersion',
                     side_effect=IOError())
    self.assertIsNone(cros_sdk_lib.GetChrootVersion('/.$om3/place/nowhere'))


class TestChrootVersionValid(VersionHookTestCase):
  """Test valid chroot version method."""

  def testLowerVersionValid(self):
    """Lower versions are considered valid."""
    osutils.WriteFile(self.version_file, str(self.latest_version - 1))
    self.assertTrue(
        cros_sdk_lib.IsChrootVersionValid(self.chroot_path, self.hooks_dir))

  def testLatestVersionValid(self):
    """Test latest version."""
    osutils.WriteFile(self.version_file, str(self.latest_version))
    self.assertTrue(
        cros_sdk_lib.IsChrootVersionValid(self.chroot_path, self.hooks_dir))

  def testInvalidVersion(self):
    """Test version higher than latest."""
    osutils.WriteFile(self.version_file, str(self.latest_version + 1))
    self.assertFalse(
        cros_sdk_lib.IsChrootVersionValid(self.chroot_path, self.hooks_dir))


class TestLatestChrootVersion(VersionHookTestCase):
  """LatestChrootVersion tests."""

  def testLatest(self):
    """Test latest version."""
    self.assertEqual(self.latest_version,
                     cros_sdk_lib.LatestChrootVersion(self.hooks_dir))


class TestEarliestChrootVersion(VersionHookTestCase):
  """EarliestChrootVersion tests."""

  def testEarliest(self):
    """Test earliest version."""
    self.assertEqual(self.earliest_version,
                     cros_sdk_lib.EarliestChrootVersion(self.hooks_dir))


class TestIsChrootReady(cros_test_lib.MockTestCase):
  """Tests IsChrootReady functionality."""

  def setUp(self):
    self.version_mock = self.PatchObject(cros_sdk_lib, 'GetChrootVersion')

  def testMissing(self):
    """Check behavior w/out a chroot."""
    self.version_mock.return_value = None
    self.assertFalse(cros_sdk_lib.IsChrootReady('/'))

  def testNotSetup(self):
    """Check behavior w/an existing uninitialized chroot."""
    self.version_mock.return_value = 0
    self.assertFalse(cros_sdk_lib.IsChrootReady('/'))

  def testUpToDate(self):
    """Check behavior w/a valid chroot."""
    self.version_mock.return_value = 123
    self.assertTrue(cros_sdk_lib.IsChrootReady('/'))


class TestFindVolumeGroupForDevice(cros_test_lib.MockTempDirTestCase):
  """Tests the FindVolumeGroupForDevice function."""

  def testExistingDevice(self):
    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.SetDefaultCmdResult(output="""
  wrong_vg1\t/dev/sda1
  test_vg\t/dev/loop1
  wrong_vg2\t/dev/loop0
""")
      vg = cros_sdk_lib.FindVolumeGroupForDevice('/chroot', '/dev/loop1')
      self.assertEqual(vg, 'test_vg')

  def testNoMatchingVolumeGroup(self):
    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.SetDefaultCmdResult(output="""
  wrong_vg1\t/dev/sda1
  wrong_vg2\t/dev/loop0
""")
      vg = cros_sdk_lib.FindVolumeGroupForDevice('/chroot', '')
      self.assertEqual(vg, 'cros_chroot_000')

  def testPhysicalVolumeWithoutVolumeGroup(self):
    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.SetDefaultCmdResult(output="""
  wrong_vg1\t/dev/sda1
  \t/dev/loop0
""")
      vg = cros_sdk_lib.FindVolumeGroupForDevice('/chroot', '/dev/loop0')
      self.assertEqual(vg, 'cros_chroot_000')

  def testMatchingVolumeGroup(self):
    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.SetDefaultCmdResult(output="""
  wrong_vg1\t/dev/sda1
  cros_chroot_000\t/dev/loop1
  wrong_vg2\t/dev/loop0
""")
      vg = cros_sdk_lib.FindVolumeGroupForDevice('/chroot', '')
      self.assertEqual(vg, 'cros_chroot_001')

  def testTooManyVolumeGroups(self):
    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.SetDefaultCmdResult(output="""
  wrong_vg1\t/dev/sda1
%s
  wrong_vg2\t/dev/loop0
""" % '\n'.join(['  cros_chroot_%03d\t/dev/any' % i for i in range(1000)]))
      vg = cros_sdk_lib.FindVolumeGroupForDevice('/chroot', '')
      self.assertIsNone(vg)

  def testInvalidChars(self):
    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.SetDefaultCmdResult(output="""
  wrong_vg1\t/dev/sda1
  cros_chroot_000\t/dev/loop1
  wrong_vg2\t/dev/loop0
""")
      vg = cros_sdk_lib.FindVolumeGroupForDevice(
          '//full path /to& "my" /chroot', '')
      self.assertEqual(vg, 'cros_full+path++to+++my+++chroot_000')

  def testInvalidLines(self):
    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.SetDefaultCmdResult(output="""
  \t/dev/sda1

  wrong_vg2\t/dev/loop0\t
""")
      vg = cros_sdk_lib.FindVolumeGroupForDevice('/chroot', '')
      self.assertEqual(vg, 'cros_chroot_000')


class TestMountChroot(cros_test_lib.MockTempDirTestCase):
  """Tests various partial setups for MountChroot."""

  _VGS_LOOKUP = ['sudo', '--', 'vgs', partial_mock.Ignore()]
  _VGCREATE = ['sudo', '--', 'vgcreate', '-q', partial_mock.Ignore(),
               partial_mock.Ignore()]
  _VGCHANGE = ['sudo', '--', 'vgchange', '-q', '-ay', partial_mock.Ignore()]
  _LVS_LOOKUP = ['sudo', '--', 'lvs', partial_mock.Ignore()]
  _LVCREATE = ['sudo', '--', 'lvcreate', '-q', '-L499G', '-T',
               partial_mock.Ignore(), '-V500G', '-n', partial_mock.Ignore()]
  _MKE2FS = ['sudo', '--', 'mke2fs', '-q', '-m', '0', '-t', 'ext4',
             partial_mock.Ignore()]
  _MOUNT = []  # Set correctly in setUp.
  _LVM_FAILURE_CODE = 5  # Shell exit code when lvm commands fail.
  _LVM_SUCCESS_CODE = 0  # Shell exit code when lvm commands succeed.

  def _makeImageFile(self, chroot_img):
    with open(chroot_img, 'w') as f:
      f.seek(2**30)
      f.write('\0')

  def _mockFindVolumeGroupForDevice(self):
    m = self.PatchObject(cros_sdk_lib, 'FindVolumeGroupForDevice')
    m.return_value = 'cros_test_chroot_000'
    return m

  def _mockAttachDeviceToFile(self, loop_dev='loop0'):
    m = self.PatchObject(cros_sdk_lib, '_AttachDeviceToFile')
    m.return_value = '/dev/%s' % loop_dev
    return m

  def _mockDeviceFromFile(self, dev):
    m = self.PatchObject(cros_sdk_lib, '_DeviceFromFile')
    m.return_value = dev
    return m

  def setUp(self):
    self.chroot_path = os.path.join(self.tempdir, 'chroot')
    osutils.SafeMakedirsNonRoot(self.chroot_path)
    self.chroot_img = self.chroot_path + '.img'

    self._MOUNT = ['sudo', '--', 'mount', '-text4', '-onoatime',
                   partial_mock.Ignore(), self.chroot_path]

  def testFromScratch(self):
    # Create the whole setup from nothing.
    # Should call losetup, vgs, vgcreate, lvs, lvcreate, mke2fs, mount
    m = self._mockFindVolumeGroupForDevice()
    m2 = self._mockAttachDeviceToFile()

    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.AddCmdResult(self._VGS_LOOKUP, returncode=self._LVM_FAILURE_CODE)
      rc_mock.AddCmdResult(self._VGCREATE, output='')
      rc_mock.AddCmdResult(self._LVS_LOOKUP, returncode=self._LVM_FAILURE_CODE)
      rc_mock.AddCmdResult(self._LVCREATE)
      rc_mock.AddCmdResult(self._MKE2FS)
      rc_mock.AddCmdResult(self._MOUNT)

      success = cros_sdk_lib.MountChroot(self.chroot_path)
      self.assertTrue(success)

    m.assert_called_with(self.chroot_path, '/dev/loop0')
    m2.assert_called_with(self.chroot_img)

  def testMissingMount(self):
    # Re-mount an image that has a loopback and VG active but isn't mounted.
    # This can happen if the person unmounts the chroot or calls
    # osutils.UmountTree() on the path.
    # Should call losetup, vgchange, lvs, mount
    self._makeImageFile(self.chroot_img)

    m = self._mockFindVolumeGroupForDevice()
    m2 = self._mockDeviceFromFile('/dev/loop1')

    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.AddCmdResult(self._VGS_LOOKUP, returncode=self._LVM_SUCCESS_CODE)
      rc_mock.AddCmdResult(self._VGCHANGE)
      rc_mock.AddCmdResult(self._LVS_LOOKUP, returncode=self._LVM_SUCCESS_CODE)
      rc_mock.AddCmdResult(self._MOUNT)

      success = cros_sdk_lib.MountChroot(self.chroot_path)
      self.assertTrue(success)

    m.assert_called_with(self.chroot_path, '/dev/loop1')
    m2.assert_called_with(self.chroot_img)

  def testImageAfterReboot(self):
    # Re-mount an image that has everything setup, but doesn't have anything
    # attached, e.g. after reboot.
    # Should call losetup -j, losetup -f, vgs, vgchange, lvs, lvchange, mount
    self._makeImageFile(self.chroot_img)

    m = self._mockFindVolumeGroupForDevice()
    m2 = self._mockDeviceFromFile('')
    m3 = self._mockAttachDeviceToFile('loop1')

    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.AddCmdResult(self._VGS_LOOKUP, returncode=self._LVM_SUCCESS_CODE)
      rc_mock.AddCmdResult(self._VGCHANGE)
      rc_mock.AddCmdResult(self._LVS_LOOKUP, returncode=self._LVM_SUCCESS_CODE)
      rc_mock.AddCmdResult(self._MOUNT)

      success = cros_sdk_lib.MountChroot(self.chroot_path)
      self.assertTrue(success)

    m.assert_called_with(self.chroot_path, '/dev/loop1')
    m2.assert_called_with(self.chroot_img)
    m3.assert_called_with(self.chroot_img)

  def testImagePresentNotSetup(self):
    # Mount an image that is present but doesn't have anything set up.  This
    # can't arise in normal usage, but could happen if cros_sdk crashes in the
    # middle of setup.
    # Should call losetup -j, losetup -f, vgs, vgcreate, lvs, lvcreate, mke2fs,
    # mount
    self._makeImageFile(self.chroot_img)

    m = self._mockFindVolumeGroupForDevice()
    m2 = self._mockAttachDeviceToFile()
    m3 = self._mockDeviceFromFile('')

    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.AddCmdResult(self._VGS_LOOKUP, returncode=self._LVM_FAILURE_CODE)
      rc_mock.AddCmdResult(self._VGCREATE)
      rc_mock.AddCmdResult(self._LVS_LOOKUP, returncode=self._LVM_FAILURE_CODE)
      rc_mock.AddCmdResult(self._LVCREATE)
      rc_mock.AddCmdResult(self._MKE2FS)
      rc_mock.AddCmdResult(self._MOUNT)

      success = cros_sdk_lib.MountChroot(self.chroot_path)
      self.assertTrue(success)

    m.assert_called_with(self.chroot_path, '/dev/loop0')
    m2.assert_called_with(self.chroot_img)
    m3.assert_called_with(self.chroot_img)

  def testImagePresentOnlyLoopbackSetup(self):
    # Mount an image that is present and attached to a loopback device, but
    # doesn't have anything else set up.  This can't arise in normal usage, but
    # could happen if cros_sdk crashes in the middle of setup.
    # Should call losetup, vgs, vgcreate, lvs, lvcreate, mke2fs, mount
    self._makeImageFile(self.chroot_img)

    m = self._mockFindVolumeGroupForDevice()
    m2 = self._mockDeviceFromFile('/dev/loop0')

    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.AddCmdResult(self._VGS_LOOKUP, returncode=self._LVM_FAILURE_CODE)
      rc_mock.AddCmdResult(self._VGCREATE)
      rc_mock.AddCmdResult(self._LVS_LOOKUP, returncode=self._LVM_FAILURE_CODE)
      rc_mock.AddCmdResult(self._LVCREATE)
      rc_mock.AddCmdResult(self._MKE2FS)
      rc_mock.AddCmdResult(self._MOUNT)

      success = cros_sdk_lib.MountChroot(self.chroot_path)
      self.assertTrue(success)

    m.assert_called_with(self.chroot_path, '/dev/loop0')
    m2.assert_called_with(self.chroot_img)

  def testImagePresentOnlyVgSetup(self):
    # Mount an image that is present, attached to a loopback device, and has a
    # VG, but doesn't have anything else set up.  This can't arise in normal
    # usage, but could happen if cros_sdk crashes in the middle of setup.
    # Should call losetup, vgs, vgchange, lvs, lvcreate, mke2fs, mount
    self._makeImageFile(self.chroot_img)

    m = self._mockFindVolumeGroupForDevice()
    m2 = self._mockDeviceFromFile('/dev/loop0')

    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.AddCmdResult(self._VGS_LOOKUP, returncode=self._LVM_SUCCESS_CODE)
      rc_mock.AddCmdResult(self._VGCHANGE)
      rc_mock.AddCmdResult(self._LVS_LOOKUP, returncode=self._LVM_FAILURE_CODE)
      rc_mock.AddCmdResult(self._LVCREATE)
      rc_mock.AddCmdResult(self._MKE2FS)
      rc_mock.AddCmdResult(self._MOUNT)

      success = cros_sdk_lib.MountChroot(self.chroot_path)
      self.assertTrue(success)

    m.assert_called_with(self.chroot_path, '/dev/loop0')
    m2.assert_called_with(self.chroot_img)

  def testMissingNoCreate(self):
    # Chroot image isn't present, but create is False.
    # Should return False without running any commands.
    success = cros_sdk_lib.MountChroot(self.chroot_path, create=False)
    self.assertFalse(success)

  def testExistingChroot(self):
    # Chroot version file exists in the chroot.
    # Should return True without running any commands.
    osutils.Touch(os.path.join(self.chroot_path, 'etc', 'cros_chroot_version'),
                  makedirs=True)

    success = cros_sdk_lib.MountChroot(self.chroot_path, create=False)
    self.assertTrue(success)

    success = cros_sdk_lib.MountChroot(self.chroot_path, create=True)
    self.assertTrue(success)

  def testEmptyChroot(self):
    # Chroot mounted from proper image but without the version file present,
    # e.g. if cros_sdk fails in the middle of populating the chroot.
    # Should return True without running any commands.
    proc_mounts = os.path.join(self.tempdir, 'proc_mounts')
    with open(proc_mounts, 'w') as f:
      f.write('/dev/mapper/cros_test_000-chroot %s ext4 rw 0 0\n' %
              self.chroot_path)

    success = cros_sdk_lib.MountChroot(
        self.chroot_path, create=False, proc_mounts=proc_mounts)
    self.assertTrue(success)

    success = cros_sdk_lib.MountChroot(
        self.chroot_path, create=True, proc_mounts=proc_mounts)
    self.assertTrue(success)

  def testBadMount(self):
    # Chroot with something else mounted on it.
    # Should return False without running any commands.
    proc_mounts = os.path.join(self.tempdir, 'proc_mounts')
    with open(proc_mounts, 'w') as f:
      f.write('/dev/sda1 %s ext4 rw 0 0\n' % self.chroot_path)

    success = cros_sdk_lib.MountChroot(
        self.chroot_path, create=False, proc_mounts=proc_mounts)
    self.assertFalse(success)

    success = cros_sdk_lib.MountChroot(
        self.chroot_path, create=True, proc_mounts=proc_mounts)
    self.assertFalse(success)


class TestFindChrootMountSource(cros_test_lib.MockTempDirTestCase):
  """Tests the FindChrootMountSource function."""
  def testNoMatchingMount(self):
    proc_mounts = os.path.join(self.tempdir, 'proc_mounts')
    with open(proc_mounts, 'w') as f:
      f.write('sysfs /sys sysfs rw 0 0\n')

    vg, lv = cros_sdk_lib.FindChrootMountSource('/chroot',
                                                proc_mounts=proc_mounts)
    self.assertIsNone(vg)
    self.assertIsNone(lv)

  def testMatchWrongName(self):
    proc_mounts = os.path.join(self.tempdir, 'proc_mounts')
    with open(proc_mounts, 'w') as f:
      f.write('/dev/sda1 /chroot ext4 rw 0 0\n')

    vg, lv = cros_sdk_lib.FindChrootMountSource('/chroot',
                                                proc_mounts=proc_mounts)
    self.assertIsNone(vg)
    self.assertIsNone(lv)

  def testMatchRightName(self):
    proc_mounts = os.path.join(self.tempdir, 'proc_mounts')
    with open(proc_mounts, 'w') as f:
      f.write('/dev/mapper/cros_vg_name-lv_name /chroot ext4 rw 0 0\n')

    vg, lv = cros_sdk_lib.FindChrootMountSource('/chroot',
                                                proc_mounts=proc_mounts)
    self.assertEqual(vg, 'cros_vg_name')
    self.assertEqual(lv, 'lv_name')

  def testMatchMultipleMounts(self):
    proc_mounts = os.path.join(self.tempdir, 'proc_mounts')
    with open(proc_mounts, 'w') as f:
      f.write("""/dev/mapper/cros_first_mount-lv_name /chroot ext4 rw 0 0
/dev/mapper/cros_inner_mount-lv /chroot/inner ext4 rw 0 0
/dev/mapper/cros_second_mount-lv_name /chroot ext4 rw 0 0
""")

    vg, lv = cros_sdk_lib.FindChrootMountSource('/chroot',
                                                proc_mounts=proc_mounts)
    self.assertEqual(vg, 'cros_second_mount')
    self.assertEqual(lv, 'lv_name')


class TestCleanupChrootMount(cros_test_lib.MockTempDirTestCase):
  """Tests the CleanupChrootMount function."""

  _VGS_DEV_LOOKUP = ['sudo', '--', 'vgs', '-q', '--noheadings', '-o', 'pv_name',
                     '--unbuffered', partial_mock.Ignore()]
  _VGS_VG_LOOKUP = ['sudo', '--', 'vgs', partial_mock.Ignore()]
  _LOSETUP_FIND = ['sudo', '--', 'losetup', '-j', partial_mock.Ignore()]
  _LOSETUP_DETACH = ['sudo', '--', 'losetup', '-d', partial_mock.Ignore()]
  _VGCHANGE_N = ['sudo', '--', 'vgchange', '-an', partial_mock.Ignore()]
  _LVM_FAILURE_CODE = 5  # Shell exit code when lvm commands fail.
  _LVM_SUCCESS_CODE = 0  # Shell exit code when lvm commands succeed.

  def setUp(self):
    self.chroot_path = os.path.join(self.tempdir, 'chroot')
    osutils.SafeMakedirsNonRoot(self.chroot_path)
    self.chroot_img = self.chroot_path + '.img'

  def testMountedCleanup(self):
    m = self.PatchObject(osutils, 'UmountTree')
    m2 = self.PatchObject(cros_sdk_lib, '_RescanDeviceLvmMetadata')

    proc_mounts = os.path.join(self.tempdir, 'proc_mounts')
    with open(proc_mounts, 'w') as f:
      f.write('/dev/mapper/cros_vg_name-chroot %s ext4 rw 0 0\n' %
              self.chroot_path)

    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.AddCmdResult(self._VGS_DEV_LOOKUP, output='  /dev/loop0')
      rc_mock.AddCmdResult(self._VGCHANGE_N)
      rc_mock.AddCmdResult(self._LOSETUP_DETACH)

      cros_sdk_lib.CleanupChrootMount(
          self.chroot_path, None, proc_mounts=proc_mounts)

    m.assert_called_with(self.chroot_path)
    m2.assert_called_with('/dev/loop0')

  def testMountedCleanupByBuildroot(self):
    m = self.PatchObject(osutils, 'UmountTree')
    m2 = self.PatchObject(cros_sdk_lib, '_RescanDeviceLvmMetadata')

    proc_mounts = os.path.join(self.tempdir, 'proc_mounts')
    with open(proc_mounts, 'w') as f:
      f.write('/dev/mapper/cros_vg_name-chroot %s ext4 rw 0 0\n' %
              self.chroot_path)

    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.AddCmdResult(self._VGS_DEV_LOOKUP, output='  /dev/loop0')
      rc_mock.AddCmdResult(self._VGCHANGE_N)
      rc_mock.AddCmdResult(self._LOSETUP_DETACH)

      cros_sdk_lib.CleanupChrootMount(
          None, self.tempdir, proc_mounts=proc_mounts)

    m.assert_called_with(self.chroot_path)
    m2.assert_called_with('/dev/loop0')

  def testMountedCleanupWithDelete(self):
    m = self.PatchObject(osutils, 'UmountTree')
    m2 = self.PatchObject(osutils, 'SafeUnlink')
    m3 = self.PatchObject(osutils, 'RmDir')
    m4 = self.PatchObject(cros_sdk_lib, '_RescanDeviceLvmMetadata')

    proc_mounts = os.path.join(self.tempdir, 'proc_mounts')
    with open(proc_mounts, 'w') as f:
      f.write('/dev/mapper/cros_vg_name-chroot %s ext4 rw 0 0\n' %
              self.chroot_path)

    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.AddCmdResult(self._VGS_DEV_LOOKUP, output='  /dev/loop0')
      rc_mock.AddCmdResult(self._VGCHANGE_N)
      rc_mock.AddCmdResult(self._LOSETUP_DETACH)

      cros_sdk_lib.CleanupChrootMount(
          self.chroot_path, None, delete=True, proc_mounts=proc_mounts)

    m.assert_called_with(self.chroot_path)
    m2.assert_called_with(self.chroot_img)
    m3.assert_called_with(self.chroot_path, ignore_missing=True, sudo=True)
    m4.assert_called_with('/dev/loop0')

  def testUnmountedCleanup(self):
    m = self.PatchObject(osutils, 'UmountTree')
    m2 = self.PatchObject(cros_sdk_lib, 'FindVolumeGroupForDevice')
    m2.return_value = 'cros_chroot_001'
    m3 = self.PatchObject(cros_sdk_lib, '_RescanDeviceLvmMetadata')

    proc_mounts = os.path.join(self.tempdir, 'proc_mounts')
    with open(proc_mounts, 'w') as f:
      f.write('sysfs /sys sysfs rw 0 0\n')

    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.AddCmdResult(self._LOSETUP_FIND, output='/dev/loop1')
      rc_mock.AddCmdResult(self._VGS_VG_LOOKUP,
                           returncode=self._LVM_SUCCESS_CODE)
      rc_mock.AddCmdResult(self._VGCHANGE_N)
      rc_mock.AddCmdResult(self._LOSETUP_DETACH)

      cros_sdk_lib.CleanupChrootMount(
          self.chroot_path, None, proc_mounts=proc_mounts)

    m.assert_called_with(self.chroot_path)
    m2.assert_called_with(self.chroot_path, '/dev/loop1')
    m3.assert_called_with('/dev/loop1')

  def testDevOnlyCleanup(self):
    m = self.PatchObject(osutils, 'UmountTree')
    m2 = self.PatchObject(cros_sdk_lib, 'FindVolumeGroupForDevice')
    m2.return_value = 'cros_chroot_001'
    m3 = self.PatchObject(cros_sdk_lib, '_RescanDeviceLvmMetadata')

    proc_mounts = os.path.join(self.tempdir, 'proc_mounts')
    with open(proc_mounts, 'w') as f:
      f.write('sysfs /sys sysfs rw 0 0\n')

    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.AddCmdResult(self._LOSETUP_FIND, output='/dev/loop1')
      rc_mock.AddCmdResult(self._VGS_VG_LOOKUP,
                           returncode=self._LVM_FAILURE_CODE)
      rc_mock.AddCmdResult(self._LOSETUP_DETACH)

      cros_sdk_lib.CleanupChrootMount(
          self.chroot_path, None, proc_mounts=proc_mounts)

    m.assert_called_with(self.chroot_path)
    m2.assert_called_with(self.chroot_path, '/dev/loop1')
    m3.assert_called_with('/dev/loop1')

  def testNothingCleanup(self):
    m = self.PatchObject(osutils, 'UmountTree')
    m2 = self.PatchObject(cros_sdk_lib, 'FindVolumeGroupForDevice')
    m2.return_value = 'cros_chroot_001'

    proc_mounts = os.path.join(self.tempdir, 'proc_mounts')
    with open(proc_mounts, 'w') as f:
      f.write('sysfs /sys sysfs rw 0 0\n')

    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.AddCmdResult(self._LOSETUP_FIND, returncode=1)
      rc_mock.AddCmdResult(self._VGS_VG_LOOKUP,
                           returncode=self._LVM_FAILURE_CODE)

      cros_sdk_lib.CleanupChrootMount(
          self.chroot_path, None, proc_mounts=proc_mounts)

    m.assert_called_with(self.chroot_path)
    m2.assert_called_with(self.chroot_path, None)

  def testNothingCleanupWithDelete(self):
    m = self.PatchObject(osutils, 'UmountTree')
    m2 = self.PatchObject(cros_sdk_lib, 'FindVolumeGroupForDevice')
    m2.return_value = 'cros_chroot_001'
    m3 = self.PatchObject(osutils, 'SafeUnlink')
    m4 = self.PatchObject(osutils, 'RmDir')

    proc_mounts = os.path.join(self.tempdir, 'proc_mounts')
    with open(proc_mounts, 'w') as f:
      f.write('sysfs /sys sysfs rw 0 0\n')

    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.AddCmdResult(self._LOSETUP_FIND, returncode=1)
      rc_mock.AddCmdResult(self._VGS_VG_LOOKUP,
                           returncode=self._LVM_FAILURE_CODE)

      cros_sdk_lib.CleanupChrootMount(
          self.chroot_path, None, delete=True, proc_mounts=proc_mounts)

    m.assert_called_with(self.chroot_path)
    m2.assert_called_with(self.chroot_path, None)
    m3.assert_called_with(self.chroot_img)
    m4.assert_called_with(self.chroot_path, ignore_missing=True, sudo=True)


class ChrootUpdaterTest(cros_test_lib.MockTestCase, VersionHookTestCase):
  """ChrootUpdater tests."""

  def setUp(self):
    # Avoid sudo password prompt for config writing.
    self.PatchObject(os, 'getuid', return_value=0)
    self.PatchObject(os, 'geteuid', return_value=0)

    self.chroot = cros_sdk_lib.ChrootUpdater(version_file=self.version_file,
                                             hooks_dir=self.hooks_dir)

  def testVersion(self):
    """Test the version property logic."""
    # Testing default value.
    self.assertEqual(0, self.chroot.GetVersion())

    # Test setting the version.
    self.chroot.SetVersion(5)
    self.assertEqual(5, self.chroot.GetVersion())
    self.assertEqual('5', osutils.ReadFile(self.version_file))

    # The current behavior is that outside processes writing to the file
    # does not affect our view after we've already read it. This shouldn't
    # generally be a problem since run_chroot_version_hooks should be the only
    # process writing to it.
    osutils.WriteFile(self.version_file, '10')
    self.assertEqual(5, self.chroot.GetVersion())

  def testInvalidVersion(self):
    """Test invalid version file contents."""
    osutils.WriteFile(self.version_file, 'invalid')
    with self.assertRaises(cros_sdk_lib.InvalidChrootVersionError):
      self.chroot.GetVersion()

  def testMissingFileVersion(self):
    """Test missing version file."""
    osutils.SafeUnlink(self.version_file)
    with self.assertRaises(cros_sdk_lib.UninitializedChrootError):
      self.chroot.GetVersion()

  def testLatestVersion(self):
    """Test the latest_version property/_LatestScriptsVersion method."""
    self.assertEqual(self.latest_version, self.chroot.latest_version)

  def testGetChrootUpdates(self):
    """Test GetChrootUpdates."""
    # Test the deprecated error conditions.
    for version in self.deprecated_versions:
      self.chroot.SetVersion(version)
      with self.assertRaises(cros_sdk_lib.ChrootDeprecatedError):
        self.chroot.GetChrootUpdates()

  def testMultipleUpdateFiles(self):
    """Test handling of multiple files existing for a single version."""
    # When the version would be run.
    osutils.WriteFile(os.path.join(self.hooks_dir, '10_duplicate'), '')

    self.chroot.SetVersion(9)
    with self.assertRaises(cros_sdk_lib.VersionHasMultipleHooksError):
      self.chroot.GetChrootUpdates()

    # When the version would not be run.
    self.chroot.SetVersion(11)
    with self.assertRaises(cros_sdk_lib.VersionHasMultipleHooksError):
      self.chroot.GetChrootUpdates()

  def testApplyUpdates(self):
    """Test ApplyUpdates."""
    self.PatchObject(cros_build_lib, 'run',
                     return_value=cros_build_lib.CommandResult(returncode=0))
    for version in self.success_versions:
      self.chroot.SetVersion(version)
      self.chroot.ApplyUpdates()
      self.assertEqual(self.latest_version, self.chroot.GetVersion())

  def testApplyInvalidUpdates(self):
    """Test the invalid version conditions for ApplyUpdates."""
    for version in self.invalid_versions:
      self.chroot.SetVersion(version)
      with self.assertRaises(cros_sdk_lib.InvalidChrootVersionError):
        self.chroot.ApplyUpdates()

  def testIsInitialized(self):
    """Test IsInitialized conditions."""
    self.chroot.SetVersion(0)
    self.assertFalse(self.chroot.IsInitialized())

    self.chroot.SetVersion(1)
    self.assertTrue(self.chroot.IsInitialized())

    # Test handling each of the errors thrown by GetVersion.
    self.PatchObject(self.chroot, 'GetVersion',
                     side_effect=cros_sdk_lib.InvalidChrootVersionError())
    self.assertFalse(self.chroot.IsInitialized())

    self.PatchObject(self.chroot, 'GetVersion',
                     side_effect=IOError())
    self.assertFalse(self.chroot.IsInitialized())

    self.PatchObject(self.chroot, 'GetVersion',
                     side_effect=cros_sdk_lib.UninitializedChrootError())
    self.assertFalse(self.chroot.IsInitialized())


class ChrootCreatorTests(cros_test_lib.MockTempDirTestCase):
  """ChrootCreator tests."""

  def setUp(self):
    tempdir = Path(self.tempdir)
    self.chroot_path = tempdir / 'chroot'
    self.sdk_tarball = tempdir / 'chroot.tar'
    self.cache_dir = tempdir / 'cache_dir'

    # We can't really verify these in any useful way atm.
    self.mount_mock = self.PatchObject(osutils, 'Mount')

    self.creater = cros_sdk_lib.ChrootCreator(
        self.chroot_path, self.sdk_tarball, self.cache_dir)

    # Create a minimal tarball to extract during testing.
    tar_dir = tempdir / 'tar_dir'
    D = cros_test_lib.Directory
    cros_test_lib.CreateOnDiskHierarchy(tar_dir, (
        D('etc', (
            D('env.d', ()),
            'passwd',
            'group',
            D('skel', (
                D('.ssh', (
                    'foo',
                )),
            )),
        )),
    ))
    (tar_dir / 'etc/passwd').write_text('root:x:0:0:Root:/root:/bin/bash\n')
    (tar_dir / 'etc/group').write_text('root::0\nusers::100\n')
    osutils.Touch(tar_dir / self.creater.DEFAULT_TZ, makedirs=True)
    cros_build_lib.CreateTarball(self.sdk_tarball, tar_dir)

  def testMakeChroot(self):
    """Verify make_chroot invocation."""
    with cros_test_lib.RunCommandMock() as rc_mock:
      rc_mock.SetDefaultCmdResult()
      # pylint: disable=protected-access
      self.creater._make_chroot()
      rc_mock.assertCommandContains([
          '--chroot', str(self.chroot_path),
          '--cache_dir', str(self.cache_dir),
      ])

  def testRun(self):
    """Verify run works."""
    TEST_USER = 'a-test-user'
    TEST_UID = 20100908
    TEST_GROUP = 'a-test-group'
    TEST_GID = 9082010
    self.PatchObject(cros_sdk_lib.ChrootCreator, '_make_chroot')
    # The files won't be root owned, but they won't be user owned.
    self.ExpectRootOwnedFiles()

    self.creater.run(user=TEST_USER, uid=TEST_UID,
                     group=TEST_GROUP, gid=TEST_GID)

    # Check various root files.
    self.assertExists(self.chroot_path / 'etc' / 'debian_chroot')
    self.assertExists(self.chroot_path / 'etc' / 'localtime')

    # Check user home files.
    user_file = self.chroot_path / 'home' / 'a-test-user' / '.ssh' / 'foo'
    self.assertExists(user_file)
    st = user_file.stat()
    self.assertEqual(st.st_uid, TEST_UID)
    self.assertEqual(st.st_gid, TEST_GID)

    # Check the user/group accounts.
    db = (self.chroot_path / 'etc' / 'passwd').read_text()
    self.assertStartsWith(db, f'{TEST_USER}:x:{TEST_UID}:{TEST_GID}:')
    # Make sure Python None didn't leak in.
    self.assertNotIn('None', db)
    db = (self.chroot_path / 'etc' / 'group').read_text()
    self.assertStartsWith(db, f'{TEST_GROUP}:x:{TEST_GID}:{TEST_USER}')
    # Make sure Python None didn't leak in.
    self.assertNotIn('None', db)

    # Check various /etc paths.
    etc = self.chroot_path / 'etc'
    self.assertExists(etc / 'mtab')
    self.assertIn(f'PORTAGE_USERNAME="{TEST_USER}"',
                  (etc / 'env.d' / '99chromiumos').read_text())
    self.assertIn('en_US.UTF-8 UTF-8', (etc / 'locale.gen').read_text())

  def testExistingCompatGroup(self):
    """Verify running with an existing, but matching, group works."""
    TEST_USER = 'a-test-user'
    TEST_UID = 20100908
    TEST_GROUP = 'users'
    TEST_GID = 100
    self.PatchObject(cros_sdk_lib.ChrootCreator, '_make_chroot')
    # The files won't be root owned, but they won't be user owned.
    self.ExpectRootOwnedFiles()

    self.creater.run(user=TEST_USER, uid=TEST_UID,
                     group=TEST_GROUP, gid=TEST_GID)
