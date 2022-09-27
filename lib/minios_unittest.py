# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests the minios module."""

import os

from chromite.lib import cros_test_lib
from chromite.lib import image_lib
from chromite.lib import image_lib_unittest
from chromite.lib import kernel_builder
from chromite.lib import minios
from chromite.lib import osutils


class BuilderTest(cros_test_lib.RunCommandTempDirTestCase):
  """Tests Builder."""

  FAKE_PARTITIONS = (
    image_lib.PartitionInfo(9, 10, 10+512*4, 512*4, 'fs', 'MINIOS-A', ''),
  )

  def setUp(self):
    """Sets up common objects for testing."""
    self.image = image_lib_unittest.LoopbackPartitionsMock('foo-image')
    self.PatchObject(image_lib, 'LoopbackPartitions', return_value=self.image)
    self.PatchObject(self.image, 'GetPartitionDevName',
                     return_value='/foo/dev0')
    self.PatchObject(self.image, 'GetPartitionInfo',
                     return_value=self.FAKE_PARTITIONS[0])

  def testCreateMiniOsKernelImage(self):
    """Tests CreateMiniOsKernelImage()."""
    self.PatchObject(os.environ, 'get', return_value='')
    bck_mock = self.PatchObject(kernel_builder.Builder,
                                'CreateCustomKernel')
    bki_mock = self.PatchObject(kernel_builder.Builder,
                                'CreateKernelImage')

    minios.CreateMiniOsKernelImage('foo-board', '0.0.0.0', self.tempdir,
                                   'foo-keys-dir', 'foo-public-key',
                                   'foo-private-key', 'foo-keyblock',
                                   'foo-tty')
    bck_mock.assert_called_once_with(
      ['minios', 'minios_ramfs', 'tpm', 'i2cdev', 'vfat',
       'kernel_compress_xz', 'pcserial', '-kernel_afdo'], [])
    bki_mock.assert_called_once_with(
        os.path.join(self.tempdir,
                     minios.MINIOS_KERNEL_IMAGE),
        boot_args='noinitrd panic=60 cros_minios_version=0.0.0.0 cros_minios',
        serial='foo-tty',
        keys_dir='foo-keys-dir', public_key='foo-public-key',
        private_key='foo-private-key', keyblock='foo-keyblock')

  def testCreateMiniOsKernelImageOverrideUseFlags(self):
    """Tests CreateMiniOsKernelImage()."""
    self.PatchObject(os.environ, 'get', return_value='other_ramfs foo bar')
    bck_mock = self.PatchObject(kernel_builder.Builder,
                                'CreateCustomKernel')
    bki_mock = self.PatchObject(kernel_builder.Builder,
                                'CreateKernelImage')

    minios.CreateMiniOsKernelImage('foo-board', '0.0.0.0', self.tempdir,
                                   'foo-keys-dir', 'foo-public-key',
                                   'foo-private-key', 'foo-keyblock',
                                   'foo-tty')
    bck_mock.assert_called_once_with(
      ['minios', 'minios_ramfs', 'tpm', 'i2cdev', 'vfat',
       'kernel_compress_xz', 'pcserial', '-kernel_afdo'],
      ['foo', 'bar'])
    bki_mock.assert_called_once_with(
        os.path.join(self.tempdir,
                     minios.MINIOS_KERNEL_IMAGE),
        boot_args='noinitrd panic=60 cros_minios_version=0.0.0.0 cros_minios',
        serial='foo-tty',
        keys_dir='foo-keys-dir', public_key='foo-public-key',
        private_key='foo-private-key', keyblock='foo-keyblock')

  def testInsertMiniOsKernelImage(self):
    """Tests InsertMiniOsKernelImage()."""
    kernel_path = os.path.join(self.tempdir,
                               minios.MINIOS_KERNEL_IMAGE)
    osutils.WriteFile(kernel_path, 'helloworld')

    minios.InsertMiniOsKernelImage('foo-image', kernel_path)

    self.assertCommandCalled(['sudo', '--', 'dd', 'if=/dev/zero',
                              'of=/foo/dev0', 'bs=512', 'count=4'])
    self.assertCommandCalled(['sudo', '--', 'dd', f'if={kernel_path}',
                              'of=/foo/dev0', 'bs=512'])

  def testLargeKernelFail(self):
    """Tests that larger than partition kernel image should fail."""
    kernel_path = os.path.join(self.tempdir,
                               minios.MINIOS_KERNEL_IMAGE)
    osutils.WriteFile(kernel_path, '\0' * 512 * 5)

    with self.assertRaisesRegex(minios.MiniOsError, 'larger than'):
      minios.InsertMiniOsKernelImage('foo-image', kernel_path)

  def testNoMiniOsPartitionFail(self):
    """Tests fail if no MiniOS partition is found."""
    self.PatchObject(self.image, 'GetPartitionInfo',
                     side_effect=KeyError('foo'))
    with self.assertRaisesRegex(KeyError, 'foo'):
      minios.InsertMiniOsKernelImage('foo-image', 'foo-path')
