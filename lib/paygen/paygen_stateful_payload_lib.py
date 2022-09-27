# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Library for handling Chrome OS partition."""

import logging
import os

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import image_lib
from chromite.lib import osutils


STATEFUL_FILE = 'stateful.tgz'


def GenerateStatefulPayload(image_path, output):
  """Generates a stateful update payload given a full path to an image.

  Args:
    image_path: Full path to the image.
    output: Can be either the path to the directory to leave the resulting
      payload or a file descriptor to write the payload into.

  Returns:
    str: The full path to the generated file.
  """
  logging.info('Generating stateful update file.')

  if isinstance(output, int):
    output_gz = output
  else:
    output_gz = os.path.join(output, STATEFUL_FILE)

  # Mount the image to pull out the important directories.
  with osutils.TempDir() as stateful_mnt, \
      image_lib.LoopbackPartitions(image_path, stateful_mnt) as image:
    rootfs_dir = image.Mount((constants.PART_STATE,))[0]

    try:
      logging.info('Tarring up /usr/local and /var!')
      cros_build_lib.CreateTarball(
          output_gz, '.', sudo=True, compression=cros_build_lib.COMP_GZIP,
          inputs=['dev_image', 'var_overlay'],
          extra_args=[
              '--directory=%s' % rootfs_dir,
              '--transform=s,^dev_image,dev_image_new,',
              '--transform=s,^var_overlay,var_new,'])
    except:
      logging.error('Failed to create stateful update file')
      raise

  logging.info('Successfully generated %s', output_gz)

  return output_gz
