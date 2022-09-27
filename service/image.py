# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The Image API is the entry point for image functionality."""

import logging
import os
import shutil
from pathlib import Path
from typing import Iterable, List, Optional, Union

from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import image_lib
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.lib.parser import package_info
from chromite.lib import sysroot_lib

PARALLEL_EMERGE_STATUS_FILE_NAME = 'status_file'


class Error(Exception):
  """Base module error."""


class InvalidArgumentError(Error, ValueError):
  """Invalid argument values."""


class MissingImageError(Error):
  """An image that was expected to exist was not found."""


class ImageToVmError(Error):
  """Error converting the image to a vm."""


class BuildConfig(object):
  """Value object to hold the build configuration options."""

  def __init__(self,
               builder_path: Optional[str] = None,
               disk_layout: Optional[str] = None,
               enable_rootfs_verification: bool = True,
               replace: bool = False,
               version: Optional[str] = None,
               build_attempt: Optional[int] = None,
               symlink: Optional[str] = None,
               output_dir_suffix: Optional[str] = None):
    """Build config initialization.

    Args:
      builder_path: The value to which the builder path lsb key should be
        set, the build_name installed on DUT during hwtest.
      disk_layout: The disk layout type.
      enable_rootfs_verification: Whether the rootfs verification is enabled.
      replace: Whether to replace existing output if any exists.
      version: The version string to use for the image.
      build_attempt: The build_attempt number to pass to build_image.
      symlink: Symlink name (defaults to "latest").
      output_dir_suffix: String to append to the image build directory.
    """
    self.builder_path = builder_path
    self.disk_layout = disk_layout
    self.enable_rootfs_verification = enable_rootfs_verification
    self.replace = replace
    self.version = version
    self.build_attempt = build_attempt
    self.symlink = symlink
    self.output_dir_suffix = output_dir_suffix

  def GetArguments(self):
    """Get the build_image arguments for the configuration."""
    args = []

    if self.builder_path:
      args.extend(['--builder_path', self.builder_path])
    if self.disk_layout:
      args.extend(['--disk_layout', self.disk_layout])
    if not self.enable_rootfs_verification:
      args.append('--noenable_rootfs_verification')
    if self.replace:
      args.append('--replace')
    if self.version:
      args.extend(['--version', self.version])
    if self.build_attempt:
      args.extend(['--build_attempt', self.build_attempt])
    if self.symlink:
      args.extend(['--symlink', self.symlink])
    if self.output_dir_suffix:
      args.extend(['--output_suffix', self.output_dir_suffix])

    return args


class BuildResult(object):
  """Class to record and report build image results."""

  def __init__(self, image_types: List[str]):
    """Init method.

    Args:
      image_types: A list of image names that were requested to be built.
    """
    self._unbuilt_image_types = image_types
    self.images = {}
    self.return_code = None
    self._failed_packages = []

  @property
  def failed_packages(self) -> List[package_info.PackageInfo]:
    """Get the failed packages."""
    return self._failed_packages

  @failed_packages.setter
  def failed_packages(self, packages: Union[Iterable[str], None]):
    """Set the failed packages."""
    self._failed_packages = [package_info.parse(x) for x in packages or []]

  @property
  def all_built(self) -> bool:
    """Check that all of the images that were meant to be built were built."""
    return not self._unbuilt_image_types

  @property
  def build_run(self) -> bool:
    """Check if build images has been run."""
    return self.return_code is not None

  @property
  def run_error(self) -> bool:
    """Check if an error occurred during the build.

    True iff build images ran and returned a non-zero return code.
    """
    return bool(self.return_code)

  @property
  def run_success(self) -> bool:
    """Check if the build was successful.

    True when the build ran, returned a zero return code, and no failed packages
    were parsed.
    """
    return self.return_code == 0 and not self.failed_packages

  def add_image(self, image_type: str, image_path: Path):
    """Add an image to the result.

    Record the image path by the image name, and remove the image type from the
    un-built image list.
    """
    if image_path and image_path.exists():
      self.images[image_type] = image_path
      logging.debug('Added %s image path %s', image_type, image_path)
      if image_type in self._unbuilt_image_types:
        self._unbuilt_image_types.remove(image_type)
        logging.debug('Removed unbuilt type %s', image_type)
      else:
        logging.warning('Unexpected Image Type %s', image_type)
    else:
      logging.error('%s image path does not exist: %s', image_type, image_path)


def Build(board: str,
          images: List[str],
          config: Optional[BuildConfig] = None,
          extra_env: Optional[dict] = None) -> BuildResult:
  """Build an image.

  Args:
    board: The board name.
    images: The image types to build.
    config: The build configuration options.
    extra_env: Environment variables to set for build_image.

  Returns:
    BuildResult
  """
  if not board:
    raise InvalidArgumentError('A build target name is required.')

  build_result = BuildResult(images[:])
  if not images:
    return build_result
  config = config or BuildConfig()

  if cros_build_lib.IsInsideChroot():
    cmd = [os.path.join(constants.CROSUTILS_DIR, 'build_image')]
  else:
    cmd = ['./build_image']

  cmd.extend(['--board', board])
  cmd.extend(config.GetArguments())
  cmd.extend(images)

  extra_env_local = extra_env.copy() if extra_env else {}

  with osutils.TempDir() as tempdir:
    status_file = os.path.join(tempdir, PARALLEL_EMERGE_STATUS_FILE_NAME)
    extra_env_local[constants.PARALLEL_EMERGE_STATUS_FILE_ENVVAR] = status_file
    result = cros_build_lib.run(
        cmd, enter_chroot=True, check=False, extra_env=extra_env_local)
    build_result.return_code = result.returncode
    try:
      content = osutils.ReadFile(status_file).strip()
    except IOError:
      # No file means no packages.
      pass
    else:
      build_result.failed_packages = content.split() if content else None

  # Save the path to each image that was built.
  image_dir = Path(
      image_lib.GetLatestImageLink(board, pointer=config.symlink))
  for image_type in images:
    filename = constants.IMAGE_TYPE_TO_NAME[image_type]
    image_path = (image_dir / filename).resolve()
    logging.debug('%s Resolved Image Path: %s', image_type, image_path)
    build_result.add_image(image_type, image_path)

  return build_result


def BuildRecoveryImage(board: str,
                       image_path: Optional[Path] = None) -> BuildResult:
  """Build a recovery image.

  This must be done after a base image has been created.

  Args:
    board: The board name.
    image_path: The chrooted path to the image, defaults to chromiums_image.bin.

  Returns:
    BuildResult
  """
  if not board:
    raise InvalidArgumentError('board is required.')

  if cros_build_lib.IsInsideChroot():
    cmd = [os.path.join(constants.CROSUTILS_DIR, 'mod_image_for_recovery.sh')]
  else:
    cmd = ['./mod_image_for_recovery.sh']

  cmd.extend(['--board', board])
  if image_path:
    cmd.extend(['--image', str(image_path)])

  build_result = BuildResult([constants.IMAGE_TYPE_RECOVERY])
  result = cros_build_lib.run(cmd, enter_chroot=True, check=False)
  build_result.return_code = result.returncode

  if result.returncode:
    return build_result

  # Record the image path.
  image_name = constants.IMAGE_TYPE_TO_NAME[constants.IMAGE_TYPE_RECOVERY]
  if image_path:
    recovery_image = image_path.parent / image_name
  else:
    image_dir = Path(image_lib.GetLatestImageLink(board))
    image_path = image_dir / image_name
    recovery_image = image_path.resolve()

  if recovery_image.exists():
    build_result.add_image(constants.IMAGE_TYPE_RECOVERY, recovery_image)

  return build_result


def CreateVm(board: str,
             disk_layout: Optional[str] = None,
             is_test: bool = False,
             chroot: Optional['chroot_lib.Chroot'] = None,
             image_dir: Optional[str] = None) -> str:
  """Create a VM from an image.

  Args:
    board: The board for which the VM is being created.
    disk_layout: The disk layout type.
    is_test: Whether it is a test image.
    chroot: The chroot where the image lives.
    image_dir: The built image directory.

  Returns:
    str: Path to the created VM .bin file.
  """
  assert board
  cmd = ['./image_to_vm.sh', '--board', board]

  if is_test:
    cmd.append('--test_image')

  if disk_layout:
    cmd.extend(['--disk_layout', disk_layout])

  if image_dir:
    if chroot:
      inside_image_dir = chroot.chroot_path(image_dir)
    else:
      inside_image_dir = path_util.ToChrootPath(image_dir)
    cmd.extend(['--from', inside_image_dir])

  chroot_args = None
  if chroot and cros_build_lib.IsOutsideChroot():
    chroot_args = chroot.get_enter_args()

  result = cros_build_lib.run(
      cmd, check=False, enter_chroot=True, chroot_args=chroot_args)

  if result.returncode:
    # Error running the command. Unfortunately we can't be much more helpful
    # than this right now.
    raise ImageToVmError('Unable to convert the image to a VM. '
                         'Consult the logs to determine the problem.')

  vm_path = os.path.join(
      image_dir or image_lib.GetLatestImageLink(board), constants.VM_IMAGE_BIN)
  return os.path.realpath(vm_path)


def CreateGuestVm(board, is_test=False, chroot=None, image_dir=None):
  """Convert an existing image into a guest VM image.

  Args:
    board (str): The name of the board to convert.
    is_test (bool): Flag to create a test guest VM image.
    chroot (chroot_lib.Chroot): The chroot where the cros image lives.
    image_dir: The directory containing the built images.

  Returns:
    str: Path to the created guest VM folder.
  """
  assert board

  cmd = [os.path.join(constants.TERMINA_TOOLS_DIR, 'termina_build_image.py')]

  if image_dir:
    if chroot:
      image_dir = chroot.chroot_path(image_dir)
    else:
      image_dir = path_util.ToChrootPath(image_dir)
  else:
    image_dir = image_lib.GetLatestImageLink(board, force_chroot=True)

  image_file = constants.TEST_IMAGE_BIN if is_test else constants.BASE_IMAGE_BIN
  image_path = os.path.join(image_dir, image_file)

  output_dir = (
      constants.TEST_GUEST_VM_DIR if is_test else constants.BASE_GUEST_VM_DIR)
  output_path = os.path.join(image_dir, output_dir)

  cmd.append(image_path)
  cmd.append(output_path)

  chroot_args = None
  if chroot and cros_build_lib.IsOutsideChroot():
    chroot_args = chroot.get_enter_args()

  result = cros_build_lib.sudo_run(
      cmd, check=False, enter_chroot=True, chroot_args=chroot_args)

  if result.returncode:
    # Error running the command. Unfortunately we can't be much more helpful
    # than this right now.
    raise ImageToVmError('Unable to convert the image to a Guest VM using'
                         'termina_build_image.py.'
                         'Consult the logs to determine the problem.')

  return os.path.realpath(output_path)


def _get_dlc_images_path(base_path: str) -> str:
  """Get the source path containing the dlc images.

  Specifically files expected to be in:
    /.../build/rootfs/dlc

  Args:
    base_path: Base path wherein DLC images are expected to be.

  Returns:
    Full path for the dlc images.
  """
  return os.path.join(base_path, 'build', 'rootfs', 'dlc')


def copy_dlc_image(base_path: str, output_dir: str) -> List[str]:
  """Copies DLC image folder from base_path to output_dir.

  Args:
    base_path: Base path wherein DLC images are expected to be.
    output_dir: Folder destination for DLC images folder.

  Returns:
    A list of folder paths after move or None if the source path doesn't exist
  """
  dlc_source_path = _get_dlc_images_path(base_path)
  if not os.path.exists(dlc_source_path):
    return None

  dlc_dest_path = os.path.join(output_dir, 'dlc')
  shutil.copytree(dlc_source_path, dlc_dest_path)
  return [dlc_dest_path]


def copy_license_credits(board: str,
                         output_dir: str,
                         symlink: Optional[str] = None) -> List[str]:
  """Copies license_credits.html from image build dir to output_dir.

  Args:
    board: The board name.
    output_dir: Folder destination for license_credits.html.
    symlink: Symlink name to use instead of "latest".

  Returns:
    The output path or None if the source path doesn't exist.
  """
  filename = 'license_credits.html'
  license_credits_source_path = os.path.join(
      image_lib.GetLatestImageLink(board, pointer=symlink), filename)
  if not os.path.exists(license_credits_source_path):
    return None

  license_credits_dest_path = os.path.join(output_dir, filename)
  shutil.copyfile(license_credits_source_path, license_credits_dest_path)
  return license_credits_dest_path


def Test(board, result_directory, image_dir=None):
  """Run tests on an already built image.

  Currently this is just running test_image.

  Args:
    board (str): The board name.
    result_directory (str): Root directory where the results should be stored
      relative to the chroot.
    image_dir (str): The path to the image. Uses the board's default image
      build path when not provided.

  Returns:
    bool - True if all tests passed, False otherwise.
  """
  if not board:
    raise InvalidArgumentError('Board is required.')
  if not result_directory:
    raise InvalidArgumentError('Result directory required.')

  if not image_dir:
    # We can build the path to the latest image directory.
    image_dir = image_lib.GetLatestImageLink(board, force_chroot=True)
  elif not cros_build_lib.IsInsideChroot() and os.path.exists(image_dir):
    # Outside chroot with outside chroot path--we need to convert it.
    image_dir = path_util.ToChrootPath(image_dir)

  cmd = [
      os.path.join(constants.CHROOT_SOURCE_ROOT, constants.CHROMITE_BIN_SUBDIR,
                   'test_image'),
      '--board',
      board,
      '--test_results_root',
      result_directory,
      image_dir,
  ]

  result = cros_build_lib.sudo_run(cmd, enter_chroot=True, check=False)

  return result.returncode == 0

def create_factory_image_zip(
  chroot: chroot_lib.Chroot,
  sysroot_class: sysroot_lib.Sysroot,
  factory_shim_dir: Path,
  version: str,
  output_dir: str) -> Union[str, None]:
  """Build factory_image.zip in archive_dir.

  Args:
    chroot: The chroot class used for these artifacts.
    sysroot_class (sysroot_lib.Sysroot): The sysroot where the original
      environment archive can be found.
    factory_shim_dir: Directory containing factory shim.
    version: if not None, version to include in factory_image.zip
    output_dir: Directory to store factory_image.zip.

  Returns:
    The path to the zipfile if it could be created, else None.
  """
  filename = 'factory_image.zip'

  zipfile = os.path.join(output_dir, filename)
  cmd = ['zip', '-r', zipfile]

  if not factory_shim_dir or not factory_shim_dir.exists():
    logging.error('create_factory_image_zip: %s not found', factory_shim_dir)
    return None
  files = ['*factory_install*.bin', '*partition*',
            os.path.join('netboot', '*')]
  cmd_files = []
  for file in files:
    cmd_files.extend(['--include', os.path.join(factory_shim_dir.name, file)])
  # factory_shim_dir may be a symlink. We can not use '-y' here.
  cros_build_lib.run(cmd + [factory_shim_dir.name] + cmd_files,
                      cwd=factory_shim_dir.parent,
                      capture_output=True)

  # Everything in /usr/local/factory/bundle gets overlaid into the
  # bundle.
  bundle_src_dir = chroot.full_path(sysroot_class.path, 'usr', 'local',
                                    'factory', 'bundle')
  if os.path.exists(bundle_src_dir):
    cros_build_lib.run(cmd + ['-y', '.'], cwd=bundle_src_dir,
                       capture_output=True)
  else:
    logging.warning('create_factory_image_zip: %s not found, skipping',
                    bundle_src_dir)

  # Add a version file in the zip file.
  if version is not None:
    version_filename = 'BUILD_VERSION'
    # Creates a staging temporary folder.
    with osutils.TempDir() as temp_dir:
      version_file = os.path.join(temp_dir, version_filename)
      osutils.WriteFile(version_file, version)
      cros_build_lib.run(cmd + [version_filename], cwd=temp_dir,
                         capture_output=True)

  return zipfile if os.path.exists(zipfile) else None
