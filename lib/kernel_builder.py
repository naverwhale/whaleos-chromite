# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A set of utilities to build the Chrome OS kernel."""

import logging
import os
import pathlib
from typing import List, Optional

from chromite.lib import build_target_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import kernel_cmdline


class Error(Exception):
  """Base error class for the module."""


class KernelBuildError(Error):
  """Error class thrown when failing to build kernel (image)."""


class Builder:
  """A class for building kernel images."""

  def __init__(self, board: str, work_dir: str, install_root: str):
    """Initialize this class.

    Args:
      board: The board to build the kernel for.
      work_dir: The directory for keeping intermediary files.
      install_root: A directory to put the built kernel files (e.g. vmlinuz).
    """
    self._board = board
    self._work_dir = pathlib.Path(work_dir)
    self._install_root = pathlib.Path(install_root)

    self._board_root = build_target_lib.get_default_sysroot_path(board)

  def CreateCustomKernel(self, kernel_flags: List[str],
                         use_flags_override: Optional[List[str]] = None):
    """Builds a custom kernel and initramfs.

    Args:
      kernel_flags: A list of USE flags for building the kernel.
      use_flags_override: A list of USE flags to override the default env USE
                          variable.
    """
    pkgdir = self._work_dir / 'packages'
    logging.info('Using PKGDIR: %s', pkgdir)
    try:
      self._CreateCustomKernel(str(pkgdir), kernel_flags, use_flags_override)
    finally:
      # The reason we need to specifically remove the pkgdir is that some of the
      # content of this directory will be read-only by non-root and tools like
      # shutil.rmtree won't be able to remove them. So we just do a force
      # delete.
      try:
        cros_build_lib.sudo_run(['rm', '-rf', str(pkgdir)])
      except cros_build_lib.RunCommandError as e:
        logging.error('Failed to delete directory %s with error: %s', pkgdir, e)
        # For whatever reason it failed but, for now we just ignore it. It is
        # probably going to fail at the end anyway.

  def _CreateCustomKernel(self, pkgdir: str, kernel_flags: List[str],
                          use_flags_override: Optional[List[str]] = None):
    """Internal function for CreateCustomKernel()

    This code is mainly borrowed from src/scripts/build_library/build_common.sh.

    Args:
      pkgdir: The path to a working dir for installing packages.
      kernel_flags: See CreateCustomKernel().
      use_flags_override: See CreateCustomKernel().
    """
    logging.info('Building custom kernel.')
    # Clean up any leftover state in custom directories.
    use_flags = use_flags_override or os.environ.get('USE', '').split()
    use_flags += kernel_flags
    logging.debug('Using USE flags: %s', use_flags)
    extra_env = {'PKGDIR': pkgdir, 'USE': ' '.join(use_flags)}
    build_target = build_target_lib.BuildTarget(self._board)
    emerge = build_target.get_command('emerge')

    # Update chromeos-initramfs to contain the latest binaries from the build
    # tree. This is basically just packaging up already-built binaries from
    # root. We are careful not to muck with the existing prebuilts so that
    # prebuilts can be uploaded in parallel.
    #
    # TODO(davidjames): Implement ABI deps so that chromeos-initramfs will be
    # rebuilt automatically when its dependencies change.
    logging.info('Building initramfs package.')
    try:
      cros_build_lib.run(
          [emerge, 'chromeos-base/chromeos-initramfs'],
          enter_chroot=True, extra_env=extra_env)
    except cros_build_lib.RunCommandError as e:
      raise KernelBuildError(
          'kernel_builder: Failed to build initramfs package: %s' % e)

    # Verify all dependencies of the kernel are installed. This should be a
    # no-op, but it's good to check in case a developer didn't run
    # build_packages.  We need the `expand_virtual` call to workaround a bug in
    # portage where it only installs the virtual pkg.
    logging.info('Verifiying dependecies of the kernel.')
    try:
      kernel = cros_build_lib.run(
          [build_target.get_command('portageq'), 'expand_virtual',
           self._board_root, 'virtual/linux-sources'], encoding='utf-8',
          enter_chroot=True, capture_output=True).stdout.strip()
      logging.debug('Building kernel package %s', kernel)
      cros_build_lib.run([emerge, '--onlydeps', kernel],
                         enter_chroot=True, extra_env=extra_env)
    except cros_build_lib.RunCommandError as e:
      raise KernelBuildError('kernel_builder: Failed verify all kernel '
                             'dependencies are built: %s' % e)

    # Build the kernel. This uses the standard root so that we can pick up the
    # initramfs from there. But we don't actually install the kernel to the
    # standard root, because that'll muck up the kernel debug symbols there,
    # which we want to upload in parallel.
    logging.info('Builing the custom kernel.')
    try:
      cros_build_lib.run([emerge, '--buildpkgonly', kernel],
                         enter_chroot=True, extra_env=extra_env)
    except cros_build_lib.RunCommandError as e:
      raise KernelBuildError(
          'kernel_builder: Failed to build the custom kernel: %s' % e)

    logging.info('Installing the custom kernel image into install root %s.',
                 self._install_root)
    # Install the custom kernel to the provided install root.
    try:
      cros_build_lib.run(
          [emerge, '--usepkgonly', f'--root={self._install_root}', kernel],
          enter_chroot=True, extra_env=extra_env)
    except cros_build_lib.RunCommandError as e:
      raise KernelBuildError(
          'kernel_builder: Failed to install the custom kernel: %s' % e)

  def CreateKernelImage(self, output: str,
                        boot_args: Optional[str] = None,
                        serial: Optional[str] = None,
                        keys_dir: str = constants.VBOOT_DEVKEYS_DIR,
                        public_key: str = constants.KERNEL_PUBLIC_SUBKEY,
                        private_key: str = constants.KERNEL_DATA_PRIVATE_KEY,
                        keyblock: str = constants.KERNEL_KEYBLOCK,
                        disable_rootfs_verification: bool = False):
    """Builds the final initramfs kernel image.

    Args:
      output: The output file to put the final kernel image.
      boot_args: A string of kernel boot arguments.
      serial: Serial ports for printks.
      keys_dir: The path to kernel keys directories. Default is dev keys.
      public_key: Filename to the public key whose private part signed the
                  keyblock.
      private_key: Filename to the private key whose public part is baked into
                   the keyblock.
      keyblock: Filename to the kernel keyblock.
      disable_rootfs_verification: If True, the rootfs verification is disabled.
    """
    logging.info('Building kernel image into %s.', output)

    portageq = build_target_lib.BuildTarget(self._board).get_command('portageq')
    try:
      arch = cros_build_lib.run([portageq, 'envvar', 'ARCH'], encoding='utf-8',
                                enter_chroot=True,
                                capture_output=True).stdout.strip()
      logging.debug('Using architecture %s', arch)
    except cros_build_lib.RunCommandError as e:
      raise KernelBuildError(
          'kernel_builder: Failed to query kernel architecture: %s' % e)

    vmlinuz = self._install_root / 'boot' / 'vmlinuz'
    cmd = [
        os.path.join(constants.CROSUTILS_DIR, 'build_kernel_image.sh'),
        f'--board={self._board}',
        f'--arch={arch}',
        f'--to={output}',
        f'--vmlinuz={vmlinuz}',
        f'--working_dir={self._work_dir}',
        # Clean up is left to the caller of this class.
        '--keep_work',
        f'--keys_dir={keys_dir}',
        f'--public={public_key}',
        f'--private={private_key}',
        f'--keyblock={keyblock}',
    ]
    if disable_rootfs_verification:
      cmd += ['--noenable_rootfs_verification']
    if boot_args:
      arg_list = kernel_cmdline.KernelArgList(boot_args)
      cmd += [f'--boot_args="{arg_list.Format()}"']
    if serial:
      if not serial.startswith('tty'):
        raise KernelBuildError('Possibly invalid argument for serial port: %s' %
                               serial)
      cmd += [f'--enable_serial={serial}']

    try:
      cros_build_lib.run(cmd, enter_chroot=True)
    except cros_build_lib.RunCommandError as e:
      raise KernelBuildError(
          'kernel_builder: Failed to create kernel image: %s' % e)
