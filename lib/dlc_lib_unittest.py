# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Unit tests for dlc_lib."""

import json
import os
from unittest import mock

from chromite.lib import cros_test_lib
from chromite.lib import dlc_lib
from chromite.lib import osutils
from chromite.lib import partial_mock
from chromite.scripts import cros_set_lsb_release


_PRE_ALLOCATED_BLOCKS = 100
_VERSION = '1.0'
_ID = 'id'
_PACKAGE = 'package'
_NAME = 'name'
_DESCRIPTION = 'description'
_BOARD = 'test_board'
_FULLNAME_REV = None
_BLOCK_SIZE = 4096
_IMAGE_SIZE_NEARING_RATIO = 1.05
_IMAGE_SIZE_GROWTH_RATIO = 1.2
_DAYS_TO_PURGE = 3

# pylint: disable=protected-access


class UtilsTest(cros_test_lib.TempDirTestCase):
  """Tests dlc_lib utility functions."""

  def testHashFile(self):
    """Test the hash of a simple file."""
    file_path = os.path.join(self.tempdir, 'f.txt')
    osutils.WriteFile(file_path, '0123')
    hash_value = dlc_lib.HashFile(file_path)
    self.assertEqual(
        hash_value, '1be2e452b46d7a0d9656bbb1f768e824'
        '8eba1b75baed65f5d99eafa948899a6a')

  def testValidateDlcIdentifier(self):
    """Tests dlc_lib.ValidateDlcIdentifier."""
    dlc_lib.ValidateDlcIdentifier('hello-world')
    dlc_lib.ValidateDlcIdentifier('hello-world2')
    dlc_lib.ValidateDlcIdentifier('this-string-has-length-40-exactly-now---')

    self.assertRaises(Exception, dlc_lib.ValidateDlcIdentifier, '')
    self.assertRaises(Exception, dlc_lib.ValidateDlcIdentifier, '-')
    self.assertRaises(Exception, dlc_lib.ValidateDlcIdentifier, '-hi')
    self.assertRaises(Exception, dlc_lib.ValidateDlcIdentifier, 'hello%')
    self.assertRaises(Exception, dlc_lib.ValidateDlcIdentifier, 'hello_world')
    self.assertRaises(Exception, dlc_lib.ValidateDlcIdentifier,
                      'this-string-has-length-greater-than-40-now')


class EbuildParamsTest(cros_test_lib.TempDirTestCase):
  """Tests EbuildParams functions."""

  def GetVaryingEbuildParams(self):
    return {
        'dlc_id': f'{_ID}_new',
        'dlc_package': f'{_PACKAGE}_new',
        'fs_type': dlc_lib.EXT4_TYPE,
        'name': f'{_NAME}_new',
        'description': f'{_DESCRIPTION}_new',
        'pre_allocated_blocks': _PRE_ALLOCATED_BLOCKS * 2,
        'version': f'{_VERSION}_new',
        'preload': True,
        'used_by': dlc_lib.USED_BY_USER,
        'days_to_purge': _DAYS_TO_PURGE,
        'mount_file_required': True,
    }

  def testGetParamsPath(self):
    """Tests EbuildParams.GetParamsPath"""
    install_root_dir = os.path.join(self.tempdir, 'install_root_dir')

    self.assertEqual(
        dlc_lib.EbuildParams.GetParamsPath(install_root_dir, _ID, _PACKAGE),
        os.path.join(install_root_dir, dlc_lib.DLC_BUILD_DIR, _ID,
                     _PACKAGE, dlc_lib.EBUILD_PARAMETERS))

  def CheckParams(self,
                  ebuild_params,
                  dlc_id=_ID,
                  dlc_package=_PACKAGE,
                  fs_type=dlc_lib.SQUASHFS_TYPE,
                  name=_NAME,
                  description=_DESCRIPTION,
                  pre_allocated_blocks=_PRE_ALLOCATED_BLOCKS,
                  version=_VERSION,
                  preload=False,
                  used_by=dlc_lib.USED_BY_SYSTEM,
                  days_to_purge=_DAYS_TO_PURGE,
                  mount_file_required=False,
                  fullnamerev=_FULLNAME_REV):
    """Tests EbuildParams JSON values"""
    self.assertDictEqual(ebuild_params,
                         {'dlc_id': dlc_id,
                          'dlc_package': dlc_package,
                          'fs_type': fs_type,
                          'pre_allocated_blocks': pre_allocated_blocks,
                          'version': version,
                          'name': name,
                          'description': description,
                          'preload': preload,
                          'used_by': used_by,
                          'days_to_purge': days_to_purge,
                          'mount_file_required': mount_file_required,
                          'fullnamerev': fullnamerev})

  def GenerateParams(self,
                     install_root_dir,
                     dlc_id=_ID,
                     dlc_package=_PACKAGE,
                     fs_type=dlc_lib.SQUASHFS_TYPE,
                     name=_NAME,
                     description=_DESCRIPTION,
                     pre_allocated_blocks=_PRE_ALLOCATED_BLOCKS,
                     version=_VERSION,
                     preload=False,
                     used_by=dlc_lib.USED_BY_SYSTEM,
                     days_to_purge=_DAYS_TO_PURGE,
                     mount_file_required=False,
                     fullnamerev=_FULLNAME_REV):
    """Creates and Stores DLC params at install_root_dir"""
    params = dlc_lib.EbuildParams(
        dlc_id=dlc_id,
        dlc_package=dlc_package,
        fs_type=fs_type,
        name=name,
        description=description,
        pre_allocated_blocks=pre_allocated_blocks,
        version=version,
        preload=preload,
        used_by=used_by,
        days_to_purge=days_to_purge,
        mount_file_required=mount_file_required,
        fullnamerev=fullnamerev)
    return params.StoreDlcParameters(
        install_root_dir=install_root_dir, sudo=False)

  def testStoreDlcParameters(self):
    """Tests EbuildParams.StoreDlcParameters"""
    sysroot = os.path.join(self.tempdir, 'build_root')
    self.GenerateParams(sysroot)
    ebuild_params_path = os.path.join(sysroot, dlc_lib.DLC_BUILD_DIR, _ID,
                                      _PACKAGE, dlc_lib.EBUILD_PARAMETERS)
    self.assertExists(ebuild_params_path)

    with open(ebuild_params_path, 'rb') as f:
      self.CheckParams(json.load(f))

  def testStoreVaryingDlcParameters(self):
    """Tests EbuildParams.StoreDlcParameters with non default values"""
    sysroot = os.path.join(self.tempdir, 'build_root')
    params = self.GetVaryingEbuildParams()
    self.GenerateParams(sysroot, **params)
    ebuild_params_path = os.path.join(sysroot, dlc_lib.DLC_BUILD_DIR,
                                      params['dlc_id'], params['dlc_package'],
                                      dlc_lib.EBUILD_PARAMETERS)
    self.assertExists(ebuild_params_path)

    with open(ebuild_params_path, 'rb') as f:
      self.CheckParams(json.load(f), **params)

  def testLoadDlcParameters(self):
    """Tests EbuildParams.LoadDlcParameters"""
    sysroot = os.path.join(self.tempdir, 'build_root')
    self.GenerateParams(sysroot)
    ebuild_params_class = dlc_lib.EbuildParams.LoadEbuildParams(
        sysroot, _ID, _PACKAGE)
    self.CheckParams(ebuild_params_class.__dict__)

  def testLoadVaryingDlcParameters(self):
    """Tests EbuildParams.LoadDlcParameters"""
    sysroot = os.path.join(self.tempdir, 'build_root')
    params = self.GetVaryingEbuildParams()
    self.GenerateParams(sysroot, **params)
    ebuild_params_class = dlc_lib.EbuildParams.LoadEbuildParams(
        sysroot, params['dlc_id'], params['dlc_package'])
    self.CheckParams(ebuild_params_class.__dict__, **params)


class DlcGeneratorTest(cros_test_lib.LoggingTestCase,
                       cros_test_lib.RunCommandTempDirTestCase):
  """Tests DlcGenerator."""

  def setUp(self):
    self.ExpectRootOwnedFiles()

  def GetDlcGenerator(self, fs_type=dlc_lib.SQUASHFS_TYPE):
    """Factory method for a DcGenerator object"""
    src_dir = os.path.join(self.tempdir, 'src')
    osutils.SafeMakedirs(src_dir)

    sysroot = os.path.join(self.tempdir, 'build_root')
    osutils.WriteFile(
        os.path.join(sysroot, dlc_lib.LSB_RELEASE),
        '%s=%s\n' % (cros_set_lsb_release.LSB_KEY_APPID_RELEASE, 'foo'),
        makedirs=True)
    ue_conf = os.path.join(sysroot, 'etc', 'update_engine.conf')
    osutils.WriteFile(ue_conf, 'foo-content', makedirs=True)

    params = dlc_lib.EbuildParams(
        dlc_id=_ID,
        dlc_package=_PACKAGE,
        fs_type=fs_type,
        name=_NAME,
        description=_DESCRIPTION,
        pre_allocated_blocks=_PRE_ALLOCATED_BLOCKS,
        version=_VERSION,
        preload=False,
        used_by=dlc_lib.USED_BY_SYSTEM,
        days_to_purge=_DAYS_TO_PURGE,
        mount_file_required=False,
        fullnamerev=_FULLNAME_REV)
    return dlc_lib.DlcGenerator(
        ebuild_params=params,
        src_dir=src_dir,
        sysroot=sysroot,
        install_root_dir=sysroot,
        board=_BOARD)

  def testSquashOwnerships(self):
    """Test dlc_lib.SquashOwnershipsTest"""
    self.GetDlcGenerator().SquashOwnerships(self.tempdir)
    self.assertCommandContains(['chown', '-R', '0:0'])
    self.assertCommandContains(['find'])

  def testCreateExt4Image(self):
    """Test CreateExt4Image to make sure it runs with valid parameters."""
    copy_dir_mock = self.PatchObject(osutils, 'CopyDirContents')
    mount_mock = self.PatchObject(osutils, 'MountDir')
    umount_mock = self.PatchObject(osutils, 'UmountDir')

    self.GetDlcGenerator(fs_type=dlc_lib.EXT4_TYPE).CreateExt4Image()
    self.assertCommandContains(
        ['/sbin/mkfs.ext4', '-b', '4096', '-O', '^has_journal'])
    self.assertCommandContains(['/sbin/e2fsck', '-y', '-f'])
    self.assertCommandContains(['/sbin/resize2fs', '-M'])
    copy_dir_mock.assert_called_once_with(
        partial_mock.HasString('src'),
        partial_mock.HasString('root'),
        symlinks=True)
    mount_mock.assert_called_once_with(
        mock.ANY,
        partial_mock.HasString('mount_point'),
        mount_opts=('loop', 'rw'))
    umount_mock.assert_called_once_with(partial_mock.HasString('mount_point'))

  def testCreateSquashfsImage(self):
    """Test that creating squashfs commands are run with correct parameters."""
    self.PatchObject(
        os.path,
        'getsize',
        return_value=(_BLOCK_SIZE * 2))
    copy_dir_mock = self.PatchObject(osutils, 'CopyDirContents')

    self.GetDlcGenerator().CreateSquashfsImage()
    self.assertCommandContains(['mksquashfs', '-4k-align', '-noappend'])
    copy_dir_mock.assert_called_once_with(
        partial_mock.HasString('src'),
        partial_mock.HasString('root'),
        symlinks=True)

  def testCreateSquashfsImagePageAlignment(self):
    """Test that creating squashfs commands are run with page alignment."""
    self.PatchObject(
        os.path,
        'getsize',
        return_value=(_BLOCK_SIZE * 1))
    truncate_mock = self.PatchObject(os, 'truncate')
    copy_dir_mock = self.PatchObject(osutils, 'CopyDirContents')

    self.GetDlcGenerator().CreateSquashfsImage()
    self.assertCommandContains(['mksquashfs', '-4k-align', '-noappend'])
    truncate_mock.asset_called()
    copy_dir_mock.assert_called_once_with(
        partial_mock.HasString('src'),
        partial_mock.HasString('root'),
        symlinks=True)

  def testPrepareLsbRelease(self):
    """Tests that lsb-release is created correctly."""
    generator = self.GetDlcGenerator()
    dlc_dir = os.path.join(self.tempdir, 'dlc_dir')

    generator.PrepareLsbRelease(dlc_dir)

    expected_lsb_release = '\n'.join([
        'DLC_ID=%s' % _ID,
        'DLC_PACKAGE=%s' % _PACKAGE,
        'DLC_NAME=%s' % _NAME,
        'DLC_RELEASE_APPID=foo_%s' % _ID,
    ]) + '\n'

    self.assertEqual(
        osutils.ReadFile(os.path.join(dlc_dir, 'etc/lsb-release')),
        expected_lsb_release)

  def testCollectExtraResources(self):
    """Tests that extra resources are collected correctly."""
    generator = self.GetDlcGenerator()

    dlc_dir = os.path.join(self.tempdir, 'dlc_dir')
    generator.CollectExtraResources(dlc_dir)

    ue_conf = 'etc/update_engine.conf'
    self.assertEqual(
        osutils.ReadFile(os.path.join(self.tempdir, 'build_root', ue_conf)),
        'foo-content')

  def testGetImageloaderJsonContent(self):
    """Test that GetImageloaderJsonContent returns correct content."""
    blocks = 100
    content = self.GetDlcGenerator().GetImageloaderJsonContent(
        '01234567', 'deadbeef', blocks)
    self.assertEqual(
        content, {
            'fs-type': dlc_lib.SQUASHFS_TYPE,
            'pre-allocated-size': str(_PRE_ALLOCATED_BLOCKS * _BLOCK_SIZE),
            'id': _ID,
            'package': _PACKAGE,
            'size': str(blocks * _BLOCK_SIZE),
            'table-sha256-hash': 'deadbeef',
            'name': _NAME,
            'description': _DESCRIPTION,
            'image-sha256-hash': '01234567',
            'image-type': 'dlc',
            'version': _VERSION,
            'is-removable': True,
            'manifest-version': 1,
            'mount-file-required': False,
            'preload-allowed': False,
            'used-by': dlc_lib.USED_BY_SYSTEM,
            'days-to-purge': _DAYS_TO_PURGE,
        })

  def testVerifyImageSize(self):
    """Test that VerifyImageSize throws exception on errors only."""
    # Succeeds since image size is smaller than preallocated size.
    self.PatchObject(
        os.path,
        'getsize',
        return_value=(_PRE_ALLOCATED_BLOCKS - 1) * _BLOCK_SIZE)
    self.GetDlcGenerator().VerifyImageSize()

    with self.assertRaises(ValueError):
      # Fails since image size is bigger than preallocated size.
      self.PatchObject(
          os.path,
          'getsize',
          return_value=(_PRE_ALLOCATED_BLOCKS + 1) * _BLOCK_SIZE)
      self.GetDlcGenerator().VerifyImageSize()

  def testVerifyImageSizeNearingWarning(self):
    """Test that VerifyImageSize logs the correct nearing warning."""
    # Logs a warning that actual size is near the preallocated size.
    with cros_test_lib.LoggingCapturer() as logs:
      self.PatchObject(
          os.path,
          'getsize',
          return_value=(_PRE_ALLOCATED_BLOCKS * _BLOCK_SIZE
                        / _IMAGE_SIZE_NEARING_RATIO))
      self.GetDlcGenerator().VerifyImageSize()
      self.AssertLogsContain(logs, 'is nearing the preallocated size')

  def testVerifyImageSizeGrowthWarning(self):
    """Test that VerifyImageSize logs the correct growth warning."""
    # Logs a warning that actual size is significantly less than the
    # preallocated size.
    with cros_test_lib.LoggingCapturer() as logs:
      self.PatchObject(
          os.path,
          'getsize',
          return_value=(_PRE_ALLOCATED_BLOCKS * _BLOCK_SIZE
                        / _IMAGE_SIZE_GROWTH_RATIO))
      self.GetDlcGenerator().VerifyImageSize()
      self.AssertLogsContain(logs,
                             'is significantly less than the preallocated size')

  def testGetOptimalImageBlockSize(self):
    """Test that GetOptimalImageBlockSize returns the valid block size."""
    dlc_generator = self.GetDlcGenerator()
    self.assertEqual(dlc_generator.GetOptimalImageBlockSize(0), 0)
    self.assertEqual(dlc_generator.GetOptimalImageBlockSize(1), 1)
    self.assertEqual(dlc_generator.GetOptimalImageBlockSize(_BLOCK_SIZE), 1)
    self.assertEqual(dlc_generator.GetOptimalImageBlockSize(_BLOCK_SIZE + 1), 2)


class FinalizeDlcsTest(cros_test_lib.MockTempDirTestCase):
  """Tests functions that generate the final DLC images."""

  def setUp(self):
    """Setup FinalizeDlcsTest."""
    self.ExpectRootOwnedFiles()

  def testInstallDlcImages(self):
    """Tests InstallDlcImages to make sure all DLCs are copied correctly"""
    sysroot = os.path.join(self.tempdir, 'sysroot')
    osutils.WriteFile(
        os.path.join(sysroot, dlc_lib.DLC_BUILD_DIR, _ID, 'pkg',
                     dlc_lib.DLC_IMAGE),
        'content',
        makedirs=True)
    osutils.SafeMakedirs(os.path.join(sysroot, dlc_lib.DLC_BUILD_DIR, _ID,
                                      'pkg'))
    output = os.path.join(self.tempdir, 'output')
    dlc_lib.InstallDlcImages(board=_BOARD, sysroot=sysroot,
                             install_root_dir=output)
    self.assertExists(os.path.join(output, _ID, 'pkg', dlc_lib.DLC_IMAGE))

  def testInstallDlcImagesNoDlc(self):
    copy_contents_mock = self.PatchObject(osutils, 'CopyDirContents')
    sysroot = os.path.join(self.tempdir, 'sysroot')
    output = os.path.join(self.tempdir, 'output')
    dlc_lib.InstallDlcImages(board=_BOARD, sysroot=sysroot,
                             install_root_dir=output)
    copy_contents_mock.assert_not_called()

  def testInstallDlcImagesWithPreloadAllowed(self):
    package_nums = 2
    preload_allowed_json = '{"preload-allowed": true}'
    sysroot = os.path.join(self.tempdir, 'sysroot')
    for package_num in range(package_nums):
      osutils.WriteFile(
          os.path.join(sysroot, dlc_lib.DLC_BUILD_DIR, _ID,
                       _PACKAGE + str(package_num), dlc_lib.DLC_IMAGE),
          'image content',
          makedirs=True)
      osutils.WriteFile(
          os.path.join(sysroot, dlc_lib.DLC_BUILD_DIR, _ID,
                       _PACKAGE + str(package_num),
                       dlc_lib.DLC_TMP_META_DIR,
                       dlc_lib.IMAGELOADER_JSON),
          preload_allowed_json,
          makedirs=True)
    output = os.path.join(self.tempdir, 'output')
    dlc_lib.InstallDlcImages(board=_BOARD, sysroot=sysroot,
                             install_root_dir=output, preload=True)
    for package_num in range(package_nums):
      self.assertExists(
          os.path.join(output, _ID, _PACKAGE + str(package_num),
                       dlc_lib.DLC_IMAGE))

  def testInstallDlcImagesWithPreloadNotAllowed(self):
    package_nums = 2
    preload_not_allowed_json = '{"preload-allowed": false}'
    sysroot = os.path.join(self.tempdir, 'sysroot')
    for package_num in range(package_nums):
      osutils.WriteFile(
          os.path.join(sysroot, dlc_lib.DLC_BUILD_DIR, _ID,
                       _PACKAGE + str(package_num), dlc_lib.DLC_IMAGE),
          'image content',
          makedirs=True)
      osutils.WriteFile(
          os.path.join(sysroot, dlc_lib.DLC_BUILD_DIR, _ID,
                       _PACKAGE + str(package_num),
                       dlc_lib.DLC_TMP_META_DIR,
                       dlc_lib.IMAGELOADER_JSON),
          preload_not_allowed_json,
          makedirs=True)
    output = os.path.join(self.tempdir, 'output')
    dlc_lib.InstallDlcImages(board=_BOARD, sysroot=sysroot,
                             install_root_dir=output, preload=True)
    for package_num in range(package_nums):
      self.assertNotExists(
          os.path.join(output, _ID, _PACKAGE + str(package_num),
                       dlc_lib.DLC_IMAGE))
