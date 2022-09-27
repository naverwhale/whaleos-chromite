# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Library containing functions to install an image on a Chromium OS device."""

import abc
import enum
import logging
import os
import re
import tempfile
import threading
import time
from typing import Dict, Tuple

from chromite.cli import command
from chromite.cli import flash
from chromite.lib import cgpt
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import gs
from chromite.lib import image_lib
from chromite.lib import operation
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib import remote_access
from chromite.lib import retry_util
from chromite.lib import stateful_updater
from chromite.lib.paygen import partition_lib
from chromite.lib.paygen import paygen_stateful_payload_lib
from chromite.lib.xbuddy import devserver_constants
from chromite.lib.xbuddy import xbuddy


class Error(Exception):
  """Thrown when there is a general Chromium OS-specific flash error."""


class ImageType(enum.Enum):
  """Type of the image that is used for flashing the device."""

  # The full image on disk (e.g. chromiumos_test_image.bin).
  FULL = 0
  # The remote directory path
  # (e.g gs://chromeos-image-archive/eve-release/R90-x.x.x)
  REMOTE_DIRECTORY = 1


class Partition(enum.Enum):
  """An enum for partition types like kernel and rootfs."""
  KERNEL = 0
  ROOTFS = 1
  MINIOS = 2


class DeviceImager(object):
  """A class to flash a Chromium OS device.

  This utility uses parallelism as much as possible to achieve its goal as fast
  as possible. For example, it uses parallel compressors, parallel transfers,
  and simultaneous pipes.
  """

  # The parameters of the kernel and rootfs's two main partitions.
  A = {Partition.KERNEL: 2, Partition.ROOTFS: 3}
  B = {Partition.KERNEL: 4, Partition.ROOTFS: 5}

  MINIOS_A = {Partition.MINIOS: 9}
  MINIOS_B = {Partition.MINIOS: 10}

  def __init__(self, device, image: str,
               board: str = None,
               version: str = None,
               no_rootfs_update: bool = False,
               no_stateful_update: bool = False,
               no_minios_update: bool = False,
               no_reboot: bool = False,
               disable_verification: bool = False,
               clobber_stateful: bool = False,
               clear_tpm_owner: bool = False):
    """Initialize DeviceImager for flashing a Chromium OS device.

    Args:
      device: The ChromiumOSDevice to be updated.
      image: The target image path (can be xBuddy path).
      board: Board to use.
      version: Image version to use.
      no_rootfs_update: Whether to do rootfs partition update.
      no_stateful_update: Whether to do stateful partition update.
      no_minios_update: Whether to do minios partition update.
      no_reboot: Whether to reboot device after update. The default is True.
      disable_verification: Whether to disabling rootfs verification on the
          device.
      clobber_stateful: Whether to do a clean stateful partition.
      clear_tpm_owner: If true, it will clear the TPM owner on reboot.
    """

    self._device = device
    self._image = image
    self._board = board
    self._version = version
    self._no_rootfs_update = no_rootfs_update
    self._no_stateful_update = no_stateful_update
    self._no_minios_update = no_minios_update
    self._no_reboot = no_reboot
    self._disable_verification = disable_verification
    self._clobber_stateful = clobber_stateful
    self._clear_tpm_owner = clear_tpm_owner

    self._image_type = None
    self._compression = cros_build_lib.COMP_GZIP
    self._inactive_state = None

  def Run(self):
    """Update the device with image of specific version."""
    self._LocateImage()
    logging.notice('Preparing to update the remote device %s with image %s',
                   self._device.hostname, self._image)

    try:
      if command.UseProgressBar():
        op = DeviceImagerOperation()
        op.Run(self._Run)
      else:
        self._Run()
    except Exception as e:
      raise Error(f'DeviceImager Failed with error: {e}')

    # DeviceImagerOperation will look for this log.
    logging.info('DeviceImager completed.')

  def _Run(self):
    """Runs the various operations to install the image on device."""
    # Override the compression as remote quick provision images are gzip
    # compressed only.
    if self._image_type == ImageType.REMOTE_DIRECTORY:
      self._compression = cros_build_lib.COMP_GZIP

    self._InstallPartitions()

    if self._clear_tpm_owner:
      self._device.ClearTpmOwner()

    if not self._no_reboot:
      self._Reboot()
      self._VerifyBootExpectations()

    if self._disable_verification:
      self._device.DisableRootfsVerification()

  def _LocateImage(self):
    """Locates the path to the final image(s) that need to be installed.

    If the paths is local, the image should be the Chromium OS GPT image
    (e.g. chromiumos_test_image.bin). If the path is remote, it should be the
    remote directory where we can find the quick-provision and stateful update
    files (e.g. gs://chromeos-image-archive/eve-release/R90-x.x.x).

    NOTE: At this point there is no caching involved. Hence we always download
    the partition payloads or extract them from the Chromium OS image.
    """
    if os.path.isfile(self._image):
      self._image_type = ImageType.FULL
      return

    # TODO(b/172212406): We could potentially also allow this by searching
    # through the directory to see whether we have quick-provision and stateful
    # payloads. This only makes sense when a user has their workstation at home
    # and doesn't want to incur the bandwidth cost of downloading the same
    # image multiple times. For that, they can simply download the GPT image
    # image first and flash that instead.
    if os.path.isdir(self._image):
      raise ValueError(
          f'{self._image}: input must be a disk image, not a directory.')

    if gs.PathIsGs(self._image):
      # TODO(b/172212406): Check whether it is a directory. If it wasn't a
      # directory download the image into some temp location and use it instead.
      self._image_type = ImageType.REMOTE_DIRECTORY
      return

    # Assuming it is an xBuddy path.
    board = cros_build_lib.GetBoard(
        device_board=self._device.board or flash.GetDefaultBoard(),
        override_board=self._board, force=True)

    xb = xbuddy.XBuddy(board=board, version=self._version)
    build_id, local_file = xb.Translate([self._image])
    if build_id is None:
      raise Error(f'{self._image}: unable to find matching xBuddy path.')
    logging.info('XBuddy path translated to build ID %s', build_id)

    if local_file:
      self._image = local_file
      self._image_type = ImageType.FULL
      return

    self._image = f'{devserver_constants.GS_IMAGE_DIR}/{build_id}'
    self._image_type = ImageType.REMOTE_DIRECTORY

  def _SplitDevPath(self, path: str) -> Tuple[str, int]:
    """Splits the given /dev/x path into prefix and the dev number.

    Args:
      path: The path to a block dev device.

    Returns:
      A tuple of representing the prefix and the index of the dev path.
      e.g.: '/dev/mmcblk0p1' -> ['/dev/mmcblk0p', 1]
    """
    match = re.search(r'(.*)([0-9]+)$', path)
    if match is None:
      raise Error(f'{path}: Could not parse root dev path.')

    return match.group(1), int(match.group(2))

  def _GetKernelState(self, root_num: int) -> Tuple[Dict, Dict]:
    """Returns the kernel state.

    Returns:
      A tuple of two dictionaries: The current active kernel state and the
      inactive kernel state. (Look at A and B constants in this class.)
    """
    if root_num == self.A[Partition.ROOTFS]:
      return self.A, self.B
    elif root_num == self.B[Partition.ROOTFS]:
      return self.B, self.A
    else:
      raise Error(f'Invalid root partition number {root_num}')

  def _GetMiniOSState(self, minios_num: int) -> Tuple[Dict, Dict]:
    """Returns the miniOS state.

    Returns:
      A tuple of dictionaries: The current active miniOS state and the inactive
      miniOS state.
    """
    if minios_num == self.MINIOS_A[Partition.MINIOS]:
      return self.MINIOS_A, self.MINIOS_B
    elif minios_num == self.MINIOS_B[Partition.MINIOS]:
      return self.MINIOS_B, self.MINIOS_A
    else:
      raise Error(f'Invalid minios partition number {minios_num}')

  def _InstallPartitions(self):
    """The main method that installs the partitions of a Chrome OS device.

    It uses parallelism to install the partitions as fast as possible.
    """
    prefix, root_num = self._SplitDevPath(self._device.root_dev)
    active_state, self._inactive_state = self._GetKernelState(root_num)

    updaters = []
    if not self._no_rootfs_update:
      current_root = prefix + str(active_state[Partition.ROOTFS])
      target_root = prefix + str(self._inactive_state[Partition.ROOTFS])
      updaters.append(RootfsUpdater(current_root, self._device, self._image,
                                    self._image_type, target_root,
                                    self._compression))

      target_kernel = prefix + str(self._inactive_state[Partition.KERNEL])
      updaters.append(KernelUpdater(self._device, self._image, self._image_type,
                                    target_kernel, self._compression))

    if not self._no_stateful_update:
      updaters.append(StatefulUpdater(self._clobber_stateful, self._device,
                                      self._image, self._image_type, None,
                                      None))

    if not self._no_minios_update:
      # Reference disk_layout_v3 for partition numbering.
      _, inactive_minios_state = self._GetMiniOSState(
          9 if self._device.run(
              ['crossystem', constants.MINIOS_PRIORITY]).output == 'A' else 10)
      target_minios = prefix + str(inactive_minios_state[Partition.MINIOS])
      updaters.append(MiniOSUpdater(self._device, self._image, self._image_type,
                                    target_minios, self._compression))

    # Retry the partitions updates that failed, in case a transient error (like
    # SSH drop, etc) caused the error.
    num_retries = 1
    try:
      retry_util.RetryException(Error, num_retries,
                                parallel.RunParallelSteps,
                                (x.Run for x in updaters if not x.IsFinished()),
                                halt_on_error=True)
    except Exception:
      # If one of the partitions failed to be installed, revert all partitions.
      parallel.RunParallelSteps(x.Revert for x in updaters)
      raise

  def _Reboot(self):
    """Reboots the device."""
    try:
      self._device.Reboot(timeout_sec=300)
    except remote_access.RebootError:
      raise Error('Could not recover from reboot. Once example reason'
                  ' could be the image provided was a non-test image'
                  ' or the system failed to boot after the update.')
    except Exception as e:
      raise Error(f'Failed to reboot to the device with error: {e}')

  def _VerifyBootExpectations(self):
    """Verify that we fully booted into the expected kernel state."""
    # Discover the newly active kernel.
    _, root_num = self._SplitDevPath(self._device.root_dev)
    active_state, _ = self._GetKernelState(root_num)

    # If this happens, we should rollback.
    if active_state != self._inactive_state:
      raise Error('The expected kernel state after update is invalid.')

    logging.info('Verified boot expectations.')


class ReaderBase(threading.Thread):
  """The base class for reading different inputs and writing into output.

  This class extends threading.Thread, so it will be run on its own thread. Also
  it can be used as a context manager. Internally, it opens necessary files for
  writing to and reading from. This class cannot be instantiated, it needs to be
  sub-classed first to provide necessary function implementations.
  """

  def __init__(self, use_named_pipes: bool = False):
    """Initializes the class.

    Args:
      use_named_pipes: Whether to use a named pipe or anonymous file
        descriptors.
    """
    super().__init__()
    self._use_named_pipes = use_named_pipes
    self._pipe_target = None
    self._pipe_source = None

  def __del__(self):
    """Destructor.

    Make sure to clean up any named pipes we might have created.
    """
    if self._use_named_pipes:
      osutils.SafeUnlink(self._pipe_target)

  def __enter__(self):
    """Enters the context manager"""
    if self._use_named_pipes:
      # There is no need for the temp file, we only need its path. So the named
      # pipe is created after this temp file is deleted.
      with tempfile.NamedTemporaryFile(prefix='chromite-device-imager') as fp:
        self._pipe_target = self._pipe_source = fp.name
      os.mkfifo(self._pipe_target)
    else:
      self._pipe_target, self._pipe_source = os.pipe()

    self.start()
    return self

  def __exit__(self, *args, **kwargs):
    """Exits the context manager."""
    self.join()

  def _Source(self):
    """Returns the source pipe to write data into.

    Sub-classes can use this function to determine where to write their data
    into.
    """
    return self._pipe_source

  def _CloseSource(self):
    """Closes the source pipe.

    Sub-classes should use this function to close the pipe after they are done
    writing into it. Failure to do so may result reader of the data to hang
    indefinitely.
    """
    if not self._use_named_pipes:
      os.close(self._pipe_source)

  def Target(self):
    """Returns the target pipe to read data from.

    Users of this class can use this path to read data from.
    """
    return self._pipe_target

  def CloseTarget(self):
    """Closes the target pipe.

    Users of this class should use this function to close the pipe after they
    are done reading from it.
    """
    if self._use_named_pipes:
      os.remove(self._pipe_target)
    else:
      os.close(self._pipe_target)


class PartialFileReader(ReaderBase):
  """A class to read specific offset and length from a file and compress it.

  This class can be used to read from specific location and length in a file
  (e.g. A partition in a GPT image). Then it compresses the input and writes it
  out (to a pipe). Look at the base class for more information.
  """

  # The offset of different partitions in a Chromium OS image does not always
  # align to larger values like 4096. It seems that 512 is the maximum value to
  # be divisible by partition offsets. This size should not be increased just
  # for 'performance reasons'. Since we are doing everything in parallel, in
  # practice there is not much difference between this and larger block sizes as
  # parallelism hides the possible extra latency provided by smaller block
  # sizes.
  _BLOCK_SIZE = 512

  def __init__(self, image: str, offset: int, length: int, compression):
    """Initializes the class.

    Args:
      image: The path to an image (local or remote directory).
      offset: The offset (in bytes) to read from the image.
      length: The length (in bytes) to read from the image.
      compression: The compression type (see cros_build_lib.COMP_XXX).
    """
    super().__init__()

    self._image = image
    self._offset = offset
    self._length = length
    self._compression = compression

  def run(self):
    """Runs the reading and compression."""
    cmd = [
        'dd',
        'status=none',
        f'if={self._image}',
        f'ibs={self._BLOCK_SIZE}',
        f'skip={int(self._offset/self._BLOCK_SIZE)}',
        f'count={int(self._length/self._BLOCK_SIZE)}',
        '|',
        cros_build_lib.FindCompressor(self._compression),
    ]

    try:
      cros_build_lib.run(' '.join(cmd), stdout=self._Source(), shell=True)
    finally:
      self._CloseSource()


class GsFileCopier(ReaderBase):
  """A class for downloading gzip compressed file from GS bucket into a pipe."""

  def __init__(self, image: str):
    """Initializes the class.

    Args:
      image: The path to an image (local or remote directory).
    """
    super().__init__(use_named_pipes=True)
    self._image = image

  def run(self):
    """Runs the download and write into the output pipe."""
    try:
      gs.GSContext().Copy(self._image, self._Source())
    finally:
      self._CloseSource()


class PartitionUpdaterBase(object):
  """A base abstract class to use for installing an image into a partition.

  Sub-classes should implement the abstract methods to provide the core
  functionality.
  """
  def __init__(self, device, image: str, image_type, target: str, compression):
    """Initializes this base class with values that most sub-classes will need.

    Args:
      device: The ChromiumOSDevice to be updated.
      image: The target image path for the partition update.
      image_type: The type of the image (ImageType).
      target: The target path (e.g. block dev) to install the update.
      compression: The compression used for compressing the update payload.
    """
    self._device = device
    self._image = image
    self._image_type = image_type
    self._target = target
    self._compression = compression
    self._finished = False

  def Run(self):
    """The main function that does the partition update job."""
    with cros_build_lib.TimedSection() as timer:
      try:
        self._Run()
      finally:
        self._finished = True

    logging.debug('Completed %s in %s', self.__class__.__name__, timer.delta)

  @abc.abstractmethod
  def _Run(self):
    """The method that need to be implemented by sub-classes."""
    raise NotImplementedError('Sub-classes need to implement this.')

  def IsFinished(self):
    """Returns whether the partition update has been successful."""
    return self._finished

  @abc.abstractmethod
  def Revert(self):
    """Reverts the partition update.

    Sub-classes need to implement this function to provide revert capability.
    """
    raise NotImplementedError('Sub-classes need to implement this.')


class RawPartitionUpdater(PartitionUpdaterBase):
  """A class to update a raw partition on a Chromium OS device."""

  def _Run(self):
    """The function that does the job of kernel partition update."""
    if self._image_type == ImageType.FULL:
      self._CopyPartitionFromImage(self._GetPartitionName())
    elif self._image_type == ImageType.REMOTE_DIRECTORY:
      self._RedirectPartition(self._GetRemotePartitionName())
    else:
      raise ValueError(f'Invalid image type {self._image_type}')

  def _GetPartitionName(self):
    """Returns the name of the partition in a Chromium OS GPT layout.

    Subclasses should override this function to return correct name.
    """
    raise NotImplementedError('Subclasses need to implement this.')

  def _CopyPartitionFromImage(self, part_name: str):
    """Updates the device's partition from a local Chromium OS image.

    Args:
      part_name: The name of the partition in the source image that needs to be
        extracted.
    """
    cmd = self._GetWriteToTargetCommand()

    offset, length = self._GetPartLocation(part_name)
    offset, length = self._OptimizePartLocation(offset, length)
    with PartialFileReader(self._image, offset, length,
                           self._compression) as generator:
      try:
        self._device.run(cmd, input=generator.Target(), shell=True)
      finally:
        generator.CloseTarget()

  def _GetWriteToTargetCommand(self):
    """Returns a write to target command to run on a Chromium OS device.

    Returns:
      A string command to run on a device to read data from stdin, uncompress it
      and write it to the target partition.
    """
    cmd = self._device.GetDecompressor(self._compression)
    # Using oflag=direct to tell the OS not to cache the writes (faster).
    cmd += ['|', 'dd', 'bs=1M', 'oflag=direct', f'of={self._target}']
    return ' '.join(cmd)

  def _GetPartLocation(self, part_name: str):
    """Extracts the location and size of the raw partition from the image.

    Args:
      part_name: The name of the partition in the source image that needs to be
        extracted.

    Returns:
      A tuple of offset and length (in bytes) from the image.
    """
    try:
      parts = image_lib.GetImageDiskPartitionInfo(self._image)
      part_info = [p for p in parts if p.name == part_name][0]
    except IndexError:
      raise Error(f'No partition named {part_name} found.')

    return int(part_info.start), int(part_info.size)

  def _GetRemotePartitionName(self):
    """Returns the name of the quick-provision partition file.

    Subclasses should override this function to return correct name.
    """
    raise NotImplementedError('Subclasses need to implement this.')

  def _OptimizePartLocation(self, offset: int, length: int):
    """Optimizes the offset and length of the partition.

    Subclasses can override this to provide better offset/length than what is
    defined in the PGT partition layout.

    Args:
      offset: The offset (in bytes) of the partition in the image.
      length: The length (in bytes) of the partition.

    Returns:
      A tuple of offset and length (in bytes) from the image.
    """
    return offset, length

  def _RedirectPartition(self, file_name: str):
    """Downloads the partition from a remote path and writes it into target.

    Args:
      file_name: The file name in the remote directory self._image.
    """
    cmd = self._GetWriteToTargetCommand()

    image_path = os.path.join(self._image, file_name)
    with GsFileCopier(image_path) as generator:
      try:
        with open(generator.Target(), 'rb') as fp:
          self._device.run(cmd, input=fp, shell=True)
      finally:
        generator.CloseTarget()


class KernelUpdater(RawPartitionUpdater):
  """A class to update the kernel partition on a Chromium OS device."""

  def _GetPartitionName(self):
    """See RawPartitionUpdater._GetPartitionName()."""
    return constants.PART_KERN_B

  def _GetRemotePartitionName(self):
    """See RawPartitionUpdater._GetRemotePartitionName()."""
    return constants.QUICK_PROVISION_PAYLOAD_KERNEL

  def Revert(self):
    """Reverts the kernel partition update."""
    # There is nothing to do for reverting kernel partition.


class RootfsUpdater(RawPartitionUpdater):
  """A class to update the root partition on a Chromium OS device."""

  def __init__(self, current_root: str, *args):
    """Initializes the class.

    Args:
      current_root: The current root device path.
      *args: See PartitionUpdaterBase
    """
    super().__init__(*args)

    self._current_root = current_root
    self._ran_postinst = False

  def _GetPartitionName(self):
    """See RawPartitionUpdater._GetPartitionName()."""
    return constants.PART_ROOT_A

  def _GetRemotePartitionName(self):
    """See RawPartitionUpdater._GetRemotePartitionName()."""
    return constants.QUICK_PROVISION_PAYLOAD_ROOTFS

  def _Run(self):
    """The function that does the job of rootfs partition update."""
    with ProgressWatcher(self._device, self._target):
      super()._Run()

    self._RunPostInst()

  def _OptimizePartLocation(self, offset: int, length: int):
    """Optimizes the size of the root partition of the image.

    Normally the file system does not occupy the entire partition. Furthermore
    we don't need the verity hash tree at the end of the root file system
    because postinst will recreate it. This function reads the (approximate)
    superblock of the ext4 partition and extracts the actual file system size in
    the root partition.
    """
    superblock_size = 4096 * 2
    with open(self._image, 'rb') as r:
      r.seek(offset)
      with tempfile.NamedTemporaryFile(delete=False) as fp:
        fp.write(r.read(superblock_size))
        fp.close()
        return offset, partition_lib.Ext2FileSystemSize(fp.name)

  def _RunPostInst(self, on_target: bool = True):
    """Runs the postinst process in the root partition.

    Args:
      on_target: If true the postinst is run on the target (inactive)
        partition. This is used when doing normal updates. If false, the
        postinst is run on the current (active) partition. This is used when
        reverting an update.
    """
    try:
      postinst_dir = '/'
      partition = self._current_root
      if on_target:
        postinst_dir = self._device.run(
            ['mktemp', '-d', '-p', self._device.work_dir],
            capture_output=True).stdout.strip()
        self._device.run(['mount', '-o', 'ro', self._target, postinst_dir])
        partition = self._target

      self._ran_postinst = True
      postinst = os.path.join(postinst_dir, 'postinst')
      result = self._device.run([postinst, partition], capture_output=True)

      logging.debug('Postinst result on %s: \n%s', postinst, result.stdout)
      # DeviceImagerOperation will look for this log.
      logging.info('Postinstall completed.')
    finally:
      if on_target:
        self._device.run(['umount', postinst_dir])

  def Revert(self):
    """Reverts the root update install."""
    logging.info('Reverting the rootfs partition update.')
    if self._ran_postinst:
      # We don't have to do anything for revert if we haven't changed the kernel
      # priorities yet.
      self._RunPostInst(on_target=False)


class MiniOSUpdater(RawPartitionUpdater):
  """A class to update the miniOS partition on a Chromium OS device."""

  def __init__(self, *args):
    """Initializes the class.

    Args:
      *args: See PartitionUpdaterBase
    """
    super().__init__(*args)

    self._ran_postinst = False

  def _GetPartitionName(self):
    """See RawPartitionUpdater._GetPartitionName()."""
    return constants.PART_MINIOS_A

  def _GetRemotePartitionName(self):
    """See RawPartitionUpdater._GetRemotePartitionName()."""
    # TODO(b/190631159, b/196056723): Allow fetching once miniOS payloads exist.
    raise NotImplementedError("MiniOS payloads aren't uploaded yet.")

  def _Run(self):
    """The function that does the job of rootfs partition update."""
    if self._image_type in [ImageType.FULL, ImageType.REMOTE_DIRECTORY]:
      if self._MiniOSPartitionExists():
        logging.info('Updating miniOS partition.')
        super()._Run()
      else:
        logging.info('Not updating miniOS partition as it does not exist.')
    else:
      # Let super() handle this error.
      super()._Run()

    self._RunPostInstall()

  def _RunPostInstall(self):
    """The function will change the priority of the miniOS partitions."""
    self._FlipMiniOSPriority()
    self._ran_postinst = True

  def Revert(self):
    """Reverts the miniOS partition update."""
    if self._ran_postinst:
      self._FlipMiniOSPriority()

  def _GetMiniOSPriority(self):
    return self._device.run(['crossystem', constants.MINIOS_PRIORITY]).output

  def _SetMiniOSPriority(self, priority: str):
    self._device.run(
        ['crossystem', f'{constants.MINIOS_PRIORITY}={priority}'])

  def _FlipMiniOSPriority(self):
    inactive_minios_priority = 'B' if self._GetMiniOSPriority() == 'A' else 'A'
    logging.info('Setting miniOS priority to %s', inactive_minios_priority)
    self._SetMiniOSPriority(inactive_minios_priority)

  def _MiniOSPartitionExists(self):
    """Checks if miniOS partition exists."""
    if self._image_type == ImageType.FULL:
      d = cgpt.Disk.FromImage(self._image)
      try:
        d.GetPartitionByTypeGuid(cgpt.MINIOS_TYPE_GUID)
        return True
      except KeyError:
        return False
    elif self._image_type == ImageType.REMOTE_DIRECTORY:
      # TODO(b/190631159, b/196056723): Check miniOS payload in remote.
      return False


class StatefulPayloadGenerator(ReaderBase):
  """A class for generating a stateful update payload in a separate thread."""
  def __init__(self, image: str):
    """Initializes that class.

    Args:
      image: The path to a local Chromium OS image.
    """
    super().__init__()
    self._image = image

  def run(self):
    """Generates the stateful update and writes it into the output pipe."""
    try:
      paygen_stateful_payload_lib.GenerateStatefulPayload(
          self._image, self._Source())
    finally:
      self._CloseSource()


class StatefulUpdater(PartitionUpdaterBase):
  """A class to update the stateful partition on a device."""
  def __init__(self, clobber_stateful: bool, *args):
    """Initializes the class

    Args:
      clobber_stateful: Whether to clobber the stateful or not.
      *args: Look at PartitionUpdaterBase.
    """
    super().__init__(*args)
    self._clobber_stateful = clobber_stateful

  def _Run(self):
    """Reads/Downloads the stateful updates and writes it into the device."""
    if self._image_type == ImageType.FULL:
      generator_cls = StatefulPayloadGenerator
    elif self._image_type == ImageType.REMOTE_DIRECTORY:
      generator_cls = GsFileCopier
      self._image = os.path.join(self._image,
                                 paygen_stateful_payload_lib.STATEFUL_FILE)
    else:
      raise ValueError(f'Invalid image type {self._image_type}')

    with generator_cls(self._image) as generator:
      try:
        updater = stateful_updater.StatefulUpdater(self._device)
        updater.Update(
            generator.Target(),
            is_payload_on_device=False,
            update_type=(stateful_updater.StatefulUpdater.UPDATE_TYPE_CLOBBER if
                         self._clobber_stateful else None))
      finally:
        generator.CloseTarget()

  def Revert(self):
    """Reverts the stateful partition update."""
    logging.info('Reverting the stateful update.')
    stateful_updater.StatefulUpdater(self._device).Reset()


class ProgressWatcher(threading.Thread):
  """A class used for watching the progress of rootfs update."""

  def __init__(self, device, target_root: str):
    """Initializes the class.

    Args:
      device: The ChromiumOSDevice to be updated.
      target_root: The target root partition to monitor the progress of.
    """
    super().__init__()

    self._device = device
    self._target_root = target_root
    self._exit = False

  def __enter__(self):
    """Starts the thread."""
    self.start()
    return self

  def __exit__(self, *args, **kwargs):
    """Exists the thread."""
    self._exit = True
    self.join()

  def _ShouldExit(self):
    return self._exit

  def run(self):
    """Monitors the progress of the target root partitions' update.

    This is done by periodically, reading the fd position of the process that is
    writing into the target partition and reporting it back. Then the position
    is divided by the size of the block device to report an approximate
    progress.
    """
    cmd = ['blockdev', '--getsize64', self._target_root]
    output = self._device.run(cmd, capture_output=True).stdout.strip()
    if output is None:
      raise Error(f'Cannot get the block device size from {output}.')
    dev_size = int(output)

    # Using lsof to find out which process is writing to the target rootfs.
    cmd = f'lsof 2>/dev/null | grep {self._target_root}'
    while not self._ShouldExit():
      try:
        output = self._device.run(cmd, capture_output=True,
                                  shell=True).stdout.strip()
        if output:
          break
      except cros_build_lib.RunCommandError:
        continue
      finally:
        time.sleep(1)

    # Now that we know which process is writing to it, we can look the fdinfo of
    # stdout of that process to get its offset. We're assuming there will be no
    # seek, which is correct.
    pid = output.split()[1]
    cmd = ['cat', f'/proc/{pid}/fdinfo/1']
    while not self._ShouldExit():
      try:
        output = self._device.run(cmd, capture_output=True).stdout.strip()
        m = re.search(r'^pos:\s*(\d+)$', output, flags=re.M)
        if m:
          offset = int(m.group(1))
          # DeviceImagerOperation will look for this log.
          logging.info('RootFS progress: %f', offset/dev_size)
      except cros_build_lib.RunCommandError:
        continue
      finally:
        time.sleep(1)


class DeviceImagerOperation(operation.ProgressBarOperation):
  """A class to provide a progress bar for DeviceImager operation."""

  def __init__(self):
    """Initializes the class."""
    super().__init__()

    self._progress = 0.0

  def ParseOutput(self, output=None):
    """Override function to parse the output and provide progress.

    Args:
      output: The stderr or stdout.
    """
    output = self._stdout.read()
    match = re.findall(r'RootFS progress: (\d+(?:\.\d+)?)', output)
    if match:
      progress = float(match[0])
      self._progress = max(self._progress, progress)

    # If postinstall completes, move half of the remaining progress.
    if re.findall(r'Postinstall completed', output):
      self._progress += (1.0 - self._progress) / 2

    # While waiting for reboot, each time, move half of the remaining progress.
    if re.findall(r'Unable to get new boot_id', output):
      self._progress += (1.0 - self._progress) / 2

    if re.findall(r'DeviceImager completed.', output):
      self._progress = 1.0

    self.ProgressBar(self._progress)
