# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the partition_lib module."""

import os

from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import image_lib
from chromite.lib import image_lib_unittest
from chromite.lib import osutils

from chromite.lib.paygen import paygen_stateful_payload_lib


class GenerateStatefulPayloadTest(cros_test_lib.RunCommandTempDirTestCase):
  """Tests generating correct stateful payload."""


  def setUp(self):
    self.image = image_lib_unittest.LoopbackPartitionsMock(
        'outfile', self.tempdir)
    self.PatchObject(image_lib, 'LoopbackPartitions', return_value=self.image)

  def testGenerateStatefulPayload(self):
    """Test correct arguments propagated to tar call."""

    self.PatchObject(osutils.TempDir, '__enter__', return_value=self.tempdir)
    fake_partitions = (
        image_lib.PartitionInfo(3, 0, 4, 4, 'fs', 'STATE', ''),
    )
    self.PatchObject(image_lib, 'GetImageDiskPartitionInfo',
                     return_value=fake_partitions)
    create_tarball_mock = self.PatchObject(cros_build_lib, 'CreateTarball')

    paygen_stateful_payload_lib.GenerateStatefulPayload('dev/null',
                                                        self.tempdir)

    create_tarball_mock.assert_called_once_with(
        os.path.join(self.tempdir, 'stateful.tgz'), '.', sudo=True,
        compression=cros_build_lib.COMP_GZIP,
        inputs=['dev_image', 'var_overlay'],
        extra_args=['--directory=%s' % os.path.join(self.tempdir, 'dir-1'),
                    '--transform=s,^dev_image,dev_image_new,',
                    '--transform=s,^var_overlay,var_new,'])

  def testGenerateStatefulPayloadIntoFileDescriptor(self):
    """Test correct arguments propagated to tar call."""

    self.PatchObject(osutils.TempDir, '__enter__', return_value=self.tempdir)
    fake_partitions = (
        image_lib.PartitionInfo(3, 0, 4, 4, 'fs', 'STATE', ''),
    )
    self.PatchObject(image_lib, 'GetImageDiskPartitionInfo',
                     return_value=fake_partitions)
    create_tarball_mock = self.PatchObject(cros_build_lib, 'CreateTarball')

    # Assuming the fd is 1.
    paygen_stateful_payload_lib.GenerateStatefulPayload('dev/null', 1)

    create_tarball_mock.assert_called_once_with(
        1, '.', sudo=True,
        compression=cros_build_lib.COMP_GZIP,
        inputs=['dev_image', 'var_overlay'],
        extra_args=['--directory=%s' % os.path.join(self.tempdir, 'dir-1'),
                    '--transform=s,^dev_image,dev_image_new,',
                    '--transform=s,^var_overlay,var_new,'])
