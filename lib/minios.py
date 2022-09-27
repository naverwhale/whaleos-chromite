# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""MiniOS build library."""

import logging
import os
import pathlib

from chromite.lib import build_target_lib
from chromite.lib import cros_build_lib
from chromite.lib import image_lib
from chromite.lib import kernel_builder


MINIOS_KERNEL_IMAGE = 'minios_vmlinuz.image'
KERNEL_FLAGS = ['minios', 'minios_ramfs', 'tpm', 'i2cdev', 'vfat',
                'kernel_compress_xz', 'pcserial', '-kernel_afdo']
PART_NAME = 'MINIOS-A'
BLOCK_SIZE = 512


class Error(Exception):
  """Base error class for the module."""


class MiniOsError(Error):
  """Raised when failing to build Mini OS image."""


def CreateMiniOsKernelImage(board: str, version: str, work_dir: str,
                            keys_dir: str, public_key: str,
                            private_key: str, keyblock: str,
                            serial: str) -> str:
  """Creates the MiniOS kernel image.

  And puts it in the work directory.

  Args:
    board: The board to build the kernel for.
    version: The chromeos version string.
    work_dir: The directory for keeping intermediary files.
    keys_dir: The path to kernel keys directories.
    public_key: Filename to the public key whose private part signed the
                keyblock.
    private_key: Filename to the private key whose public part is baked into
                 the keyblock.
    keyblock: Filename to the kernel keyblock.
    serial: Serial port for the kernel console (e.g. printks).

  Returns:
    The path to the generated kernel image.
  """
  install_root = os.path.join(
    (build_target_lib.get_default_sysroot_path(board)), 'factory-root')
  kb = kernel_builder.Builder(board, work_dir, install_root)
  # MiniOS ramfs cannot be built with multiple conflicting `_ramfs` flags.
  kb.CreateCustomKernel(KERNEL_FLAGS,
                        [x for x in os.environ.get('USE', '').split()
                         if not x.endswith('_ramfs')])
  kernel = os.path.join(work_dir, MINIOS_KERNEL_IMAGE)
  assert ' ' not in version, f'bad version: {version}'
  boot_args = f'noinitrd panic=60 cros_minios_version={version} cros_minios'
  kb.CreateKernelImage(kernel, boot_args=boot_args,
                       serial=serial, keys_dir=keys_dir, public_key=public_key,
                       private_key=private_key, keyblock=keyblock)
  return kernel


def InsertMiniOsKernelImage(image: str, kernel: str):
  """Writes the MiniOS into MINIOS-A partition of the Chromium OS image.

  It assumes the Chromium OS image has enough space in MINIOS-A partition,
  otherwise it will fail.

  Args:
    image: The path to the Chromium OS image.
    kernel: The path to the kernel image.
  """
  with image_lib.LoopbackPartitions(image) as devs:
    part_info = devs.GetPartitionInfo(PART_NAME)
    if pathlib.Path(kernel).stat().st_size > part_info.size:
      raise MiniOsError(
          'MiniOS kernel image is larger than the MINIOS-A partition.')

    device = devs.GetPartitionDevName(PART_NAME)
    logging.debug('Mini OS loopback partition is %s', device)

    logging.info('Writing the MiniOS kernel image %s into the Chromium OS '
                 'image %s', kernel, image)
    # First zero out the partition. This generally would help with update
    # payloads so we don't have to compress junk bytes. The target file is a
    # loopback dev device of the MINIOS-A partition.
    cros_build_lib.sudo_run(['dd', 'if=/dev/zero', f'of={device}',
                             f'bs={BLOCK_SIZE}',
                             f'count={part_info.size // BLOCK_SIZE}'])
    # Write the actual MiniOS kernel into the MINIOS-A partition.
    cros_build_lib.sudo_run(['dd', f'if={kernel}', f'of={device}',
                             f'bs={BLOCK_SIZE}'])
