# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for setting up and cleaning up the chroot environment."""

import collections
import grp
import logging
import os
from pathlib import Path
import pwd
import re
import shutil
import time
from typing import List, Optional, Union

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.lib import timeout_util


# Version file location inside chroot.
CHROOT_VERSION_FILE = '/etc/cros_chroot_version'
# Version hooks directory.
_CHROOT_VERSION_HOOKS_DIR = os.path.join(constants.CROSUTILS_DIR,
                                         'chroot_version_hooks.d')


# Name of the LV that contains the active chroot inside the chroot.img file.
CHROOT_LV_NAME = 'chroot'


# Name of the thin pool used for the chroot and snapshots inside chroot.img.
CHROOT_THINPOOL_NAME = 'thinpool'


# Max times to recheck the result of an lvm command that doesn't finish quickly.
_MAX_LVM_RETRIES = 3


class Error(Exception):
  """Base cros sdk error class."""


class ChrootDeprecatedError(Error):
  """Raised when the chroot is too old to update."""

  def __init__(self, *args, **kwargs):
    # Message defined here because it's long and gives specific instructions.
    msg = ('Upgrade hook missing for your chroot version.\n'
           'Your chroot is so old that some updates have been deprecated and'
           'it will need to be recreated. A fresh chroot can be built with:\n'
           '    cros_sdk --replace\n')
    super().__init__(msg, *args, **kwargs)


class ChrootUpdateError(Error):
  """Error encountered when updating the chroot."""


class InvalidChrootVersionError(Error):
  """Chroot version is not a valid version."""


class UninitializedChrootError(Error):
  """Chroot has not been initialized."""


class VersionHasMultipleHooksError(Error):
  """When it is found that a single version has multiple hooks."""


def GetChrootVersion(chroot):
  """Extract the version of the chroot.

  Args:
    chroot: Full path to the chroot to examine.

  Returns:
    The version of the chroot dir, or None if the version is missing/invalid.
  """
  if chroot:
    ver_path = os.path.join(chroot, CHROOT_VERSION_FILE.lstrip(os.sep))
  else:
    ver_path = CHROOT_VERSION_FILE

  updater = ChrootUpdater(version_file=ver_path)
  try:
    return updater.GetVersion()
  except (IOError, Error) as e:
    logging.debug(e)

  return None


def IsChrootVersionValid(chroot_path, hooks_dir=None):
  """Check if the chroot version exists and is a valid version."""
  version = GetChrootVersion(chroot_path)
  return version and version <= LatestChrootVersion(hooks_dir)


def LatestChrootVersion(hooks_dir=None):
  """Get the most recent update hook version."""
  hook_files = os.listdir(hooks_dir or _CHROOT_VERSION_HOOKS_DIR)

  # Hook file names must follow the "version_short_description" convention.
  # Pull out just the version number and find the max.
  return max(int(hook.split('_', 1)[0]) for hook in hook_files)


def EarliestChrootVersion(hooks_dir=None):
  """Get the oldest update hook version."""
  hook_files = os.listdir(hooks_dir or _CHROOT_VERSION_HOOKS_DIR)

  # Hook file names must follow the "version_short_description" convention.
  # Pull out just the version number and find the max.
  return min(int(hook.split('_', 1)[0]) for hook in hook_files)


def IsChrootDirValid(chroot_path):
  """Check the permissions and owner on a chroot directory.

  Args:
    chroot_path: The path to a chroot.

  Returns:
    bool - False iff there are incorrect values on an existing directory.
  """
  if not os.path.exists(chroot_path):
    # No directory == no incorrect values.
    return True

  return (IsChrootOwnerValid(chroot_path) and
          IsChrootPermissionsValid(chroot_path))


def IsChrootOwnerValid(chroot_path):
  """Check if the chroot owner is root."""
  chroot_stat = os.stat(chroot_path)
  return not chroot_stat.st_uid and not chroot_stat.st_gid


def IsChrootPermissionsValid(chroot_path):
  """Check if the permissions on the directory are correct."""
  chroot_stat = os.stat(chroot_path)
  return chroot_stat.st_mode & 0o7777 == 0o755


def IsChrootReady(chroot):
  """Checks if the chroot is mounted and set up.

  /etc/cros_chroot_version is set to the current version of the chroot at the
  end of the setup process.  If this file exists and contains a non-zero value,
  the chroot is ready for use.

  Args:
    chroot: Full path to the chroot to examine.

  Returns:
    True iff the chroot contains a valid version.
  """
  version = GetChrootVersion(chroot)
  return version is not None and version > 0


def MountChrootPaths(path: Union[Path, str]):
  """Setup all the mounts for |path|.

  NB: This assumes running in a unique mount namespace.  If it is running in the
  root mount namespace, then it will probably change settings for the worse.
  """
  KNOWN_FILESYSTEMS = set(
      x.split()[-1] for x in osutils.ReadFile('/proc/filesystems').splitlines())

  path = Path(path).resolve()

  logging.debug('Mounting chroot paths at %s', path)

  # Mark all existing mounts as slave mounts: that means changes made to mounts
  # in the parent mount namespace will propagate down (like unmounts).
  osutils.Mount(None, '/', None, osutils.MS_REC | osutils.MS_SLAVE)

  # If the mount path is already mounted, make it private so we can make changes
  # without it propagating back out.
  for info in osutils.IterateMountPoints():
    if info.destination == str(path):
      osutils.Mount(None, path, None, osutils.MS_REC | osutils.MS_PRIVATE)
      break

  # The source checkout must be mounted first.  We'll be mounting paths into the
  # chroot, and that chroot lives inside SOURCE_ROOT, so if we did the recursive
  # bind at the end, we'd double bind things.
  osutils.Mount(
      constants.SOURCE_ROOT, path / constants.CHROOT_SOURCE_ROOT[1:],
      '~/chromiumos', osutils.MS_BIND | osutils.MS_REC)

  defflags = (osutils.MS_NOSUID | osutils.MS_NODEV | osutils.MS_NOEXEC |
              osutils.MS_RELATIME)
  osutils.Mount('proc', path / 'proc', 'proc', defflags)
  osutils.Mount('sysfs', path / 'sys', 'sysfs', defflags)

  if 'binfmt_misc' in KNOWN_FILESYSTEMS:
    osutils.Mount('binfmt_misc', path / 'proc/sys/fs/binfmt_misc',
                  'binfmt_misc', defflags)

  if 'configfs' in KNOWN_FILESYSTEMS:
    osutils.Mount('configfs', path / 'sys/kernel/config', 'configfs', defflags)

  # We expose /dev so we can access loopback & USB drives for flashing.
  osutils.Mount('/dev', path / 'dev', '/dev', osutils.MS_BIND | osutils.MS_REC)


def FindVolumeGroupForDevice(chroot_path, chroot_dev):
  """Find a usable VG name for a given path and device.

  If there is an existing VG associated with the device, it will be returned
  even if the path doesn't match.  If not, find an unused name in the format
  cros_<safe_path>_NNN, where safe_path is an escaped version of the last 90
  characters of the path and NNN is a counter.  Example:
    /home/user/cros/chroot/ -> cros_home+user+cros+chroot_000.
  If no unused name with this pattern can be found, return None.

  A VG with the returned name will not necessarily exist.  The caller should
  call vgs or otherwise check the name before attempting to use it.

  Args:
    chroot_path: Path where the chroot will be mounted.
    chroot_dev: Device that should hold the VG, e.g. /dev/loop0.

  Returns:
    A VG name that can be used for the chroot/device pair, or None if no name
    can be found.
  """

  safe_path = re.sub(r'[^A-Za-z0-9_+.-]', '+', chroot_path.strip('/'))[-90:]
  vg_prefix = 'cros_%s_' % safe_path

  cmd = ['pvs', '-q', '--noheadings', '-o', 'vg_name,pv_name', '--unbuffered',
         '--separator', '\t']
  result = cros_build_lib.sudo_run(
      cmd, capture_output=True, print_cmd=False, encoding='utf-8')
  existing_vgs = set()
  for line in result.output.strip().splitlines():
    # Typical lines are '  vg_name\tpv_name\n'.  Match with a regex
    # instead of split because the first field can be empty or missing when
    # a VG isn't completely set up.
    match = re.match(r'([^\t]+)\t(.*)$', line.strip(' '))
    if not match:
      continue
    vg_name, pv_name = match.group(1), match.group(2)
    if chroot_dev == pv_name:
      return vg_name
    elif vg_name.startswith(vg_prefix):
      existing_vgs.add(vg_name)

  for i in range(1000):
    vg_name = '%s%03d' % (vg_prefix, i)
    if vg_name not in existing_vgs:
      return vg_name

  logging.error('Unable to find an unused VG with prefix %s', vg_prefix)
  return None


def _DeviceFromFile(chroot_image):
  """Finds the loopback device associated with |chroot_image|.

  Returns:
    The path to a loopback device (e.g. /dev/loop0) attached to |chroot_image|
    if one is found, or None if no device is found.
  """
  chroot_dev = None
  cmd = ['losetup', '-j', chroot_image]
  result = cros_build_lib.sudo_run(
      cmd, capture_output=True, check=False, print_cmd=False,
      encoding='utf-8')
  if result.returncode == 0:
    match = re.match(r'/dev/loop\d+', result.output)
    if match:
      chroot_dev = match.group(0)
  return chroot_dev


def _AttachDeviceToFile(chroot_image):
  """Attaches a new loopback device to |chroot_image|.

  Returns:
    The path to the new loopback device.

  Raises:
    RunCommandError: The losetup command failed to attach a new device.
  """
  cmd = ['losetup', '--show', '-f', chroot_image]
  # Result should be '/dev/loopN\n' for whatever loop device is chosen.
  result = cros_build_lib.sudo_run(
      cmd, capture_output=True, print_cmd=False, encoding='utf-8')
  chroot_dev = result.output.strip()

  # Force rescanning the new device in case lvmetad doesn't pick it up.
  _RescanDeviceLvmMetadata(chroot_dev)
  return chroot_dev


def MountChroot(chroot=None, buildroot=None, create=True,
                proc_mounts='/proc/mounts'):
  """Mount a chroot image on |chroot| if it doesn't already contain a chroot.

  This function does not populate the chroot.  If there is an existing .img
  file, it will be mounted on |chroot|.  Otherwise a new empty filesystem will
  be mounted.  This function is a no-op if |chroot| already appears to contain
  a populated chroot.

  Args:
    chroot: Full path to the chroot to examine, or None to find it relative
        to |buildroot|.
    buildroot: Ignored if |chroot| is set.  If |chroot| is None, find the chroot
        relative to |buildroot|.
    create: Create a new image file if needed.  If False, only mount an
        existing image.
    proc_mounts: Full path to a file containing a list of mounted filesystems.
        Intended for testing only.

  Returns:
    True if the chroot is mounted, or False if not.

  Raises:
    RunCommandError: An external command failed.
  """
  if chroot is None and buildroot is None:
    raise ValueError('need either |chroot| or |buildroot| to search')
  if chroot is None:
    chroot = os.path.join(buildroot, constants.DEFAULT_CHROOT_DIR)

  # If there's a version file, this chroot is already set up.
  ver_path = os.path.join(chroot, 'etc', 'cros_chroot_version')
  if os.path.exists(ver_path):
    return True

  # Even if there isn't a version file in the chroot, there might already
  # be an image mounted on it.
  chroot_vg, chroot_lv = FindChrootMountSource(chroot, proc_mounts=proc_mounts)
  if chroot_vg and chroot_lv:
    return True

  # Make sure nothing else is mounted on the chroot.  We could mount over the
  # top, but this seems likely to be an error, so we'll bail out instead.
  chroot_mounts = [m.source
                   for m in osutils.IterateMountPoints(proc_file=proc_mounts)
                   if m.destination == chroot]
  if chroot_mounts:
    logging.error('Found %s mounted on %s.  Not mounting a chroot over the top',
                  ','.join(chroot_mounts), chroot)
    return False

  # Create a sparse 500GB file to hold the chroot image.  If we create an
  # image, immediately attach to a loopback device to skip one call to losetup.
  chroot_image = chroot + '.img'
  chroot_dev = None
  if not os.path.exists(chroot_image):
    if not create:
      return False

    logging.debug('Creating image %s', chroot_image)
    with open(chroot_image, 'w') as f:
      f.seek(500 * 2**30)  # 500GB sparse image.
      f.write('\0')

    chroot_dev = _AttachDeviceToFile(chroot_image)

  # Attach the image to a loopback device.
  if not chroot_dev:
    chroot_dev = _DeviceFromFile(chroot_image)
    if chroot_dev:
      logging.debug('Used existing device %s for %s', chroot_dev, chroot_image)
    else:
      chroot_dev = _AttachDeviceToFile(chroot_image)
  logging.debug('Loopback device is %s', chroot_dev)

  # Make sure there is a VG on the loopback device.
  chroot_vg = FindVolumeGroupForDevice(chroot, chroot_dev)
  if not chroot_vg:
    logging.error('Unable to find a VG for %s on %s', chroot, chroot_dev)
    return False
  cmd = ['vgs', chroot_vg]
  result = cros_build_lib.sudo_run(
      cmd, capture_output=True, check=False, print_cmd=False,
      encoding='utf-8')
  if result.returncode == 0:
    logging.debug('Activating existing VG %s', chroot_vg)
    cmd = ['vgchange', '-q', '-ay', chroot_vg]
    # Sometimes LVM's internal thin volume check won't finish quickly enough
    # and this command will fail.  When this is the case, it will succeed if
    # we retry.  If it fails three times in a row, assume there's a real error
    # and re-raise the exception.
    try_count = list(range(1, 4))
    for i in try_count:
      try:
        cros_build_lib.sudo_run(cmd, capture_output=True, print_cmd=False)
        break
      except cros_build_lib.RunCommandError:
        logging.warning('Failed to activate VG on try %d.', i)
        if i == len(try_count):
          raise
  else:
    cmd = ['vgcreate', '-q', chroot_vg, chroot_dev]
    cros_build_lib.sudo_run(cmd, capture_output=True, print_cmd=False)

  # Make sure there is an LV containing a filesystem in our VG.
  chroot_lv = '%s/chroot' % chroot_vg
  chroot_dev_path = '/dev/%s' % chroot_lv
  cmd = ['lvs', chroot_lv]
  result = cros_build_lib.sudo_run(
      cmd, capture_output=True, check=False, print_cmd=False,
      encoding='utf-8')
  if result.returncode != 0:
    cmd = ['lvcreate', '-q', '-L499G', '-T',
           '%s/%s' % (chroot_vg, CHROOT_THINPOOL_NAME), '-V500G',
           '-n', CHROOT_LV_NAME]
    cros_build_lib.sudo_run(cmd, capture_output=True, print_cmd=False)

    cmd = ['mke2fs', '-q', '-m', '0', '-t', 'ext4', chroot_dev_path]
    cros_build_lib.sudo_run(cmd, capture_output=True, print_cmd=False)

  osutils.SafeMakedirsNonRoot(chroot)

  # Sometimes lvchange can take a few seconds to run.  Try to wait for the
  # device to appear before mounting it.
  count = 0
  while not os.path.exists(chroot_dev_path):
    if count > _MAX_LVM_RETRIES:
      logging.error('Device %s still does not exist.  Expect mounting the '
                    'filesystem to fail.', chroot_dev_path)
      break

    count += 1
    logging.warning('Device file %s does not exist yet on try %d.',
                    chroot_dev_path, count)
    time.sleep(1)

  cmd = ['mount', '-text4', '-onoatime', chroot_dev_path, chroot]
  cros_build_lib.sudo_run(cmd, capture_output=True, print_cmd=False)

  return True


def FindChrootMountSource(chroot_path, proc_mounts='/proc/mounts'):
  """Find the VG and LV mounted on |chroot_path|.

  Args:
    chroot_path: The full path to a mounted chroot.
    proc_mounts: The path to a list of mounts to read (intended for testing).

  Returns:
    A tuple containing the VG and LV names, or (None, None) if an appropriately
    named device mounted on |chroot_path| isn't found.
  """
  mount = [m for m in osutils.IterateMountPoints(proc_file=proc_mounts)
           if m.destination == chroot_path]
  if not mount:
    return (None, None)

  # Take the last mount entry because it's the one currently visible.
  # Expected VG/LV source path is /dev/mapper/cros_XX_NNN-LV.
  # See FindVolumeGroupForDevice for details.
  mount_source = mount[-1].source
  match = re.match(r'/dev.*/(cros[^-]+)-(.+)', mount_source)
  if not match:
    return (None, None)

  return (match.group(1), match.group(2))


FileSystemDebugInfo = collections.namedtuple('FileSystemDebugInfo',
                                             ('fuser', 'lsof', 'ps'))

def GetFileSystemDebug(path: str, run_ps: bool = True) -> FileSystemDebugInfo:
  """Collect filesystem debugging information.

  Dump some information to help find processes that may still be sing
  files. Running ps auxf can also be done to see what processes are
  still running.

  Args:
    path: Full path for directory we want information on.
    run_ps: When true, show processes running.

  Returns:
    FileSystemDebugInfo with debug info.
  """
  cmd_kwargs = {
      'check': False,
      'capture_output': True,
      'encoding': 'utf-8',
      'errors': 'replace'
  }
  fuser = cros_build_lib.sudo_run(['fuser', path], **cmd_kwargs)
  lsof = cros_build_lib.sudo_run(['lsof', path], **cmd_kwargs)
  if run_ps:
    ps = cros_build_lib.run(['ps', 'auxf'], **cmd_kwargs)
    ps_stdout = ps.stdout
  else:
    ps_stdout = None
  return FileSystemDebugInfo(fuser.stdout, lsof.stdout, ps_stdout)


# Raise an exception if cleanup takes more than 10 minutes.
@timeout_util.TimeoutDecorator(600)
def CleanupChrootMount(chroot=None, buildroot=None, delete=False,
                       proc_mounts='/proc/mounts'):
  """Unmounts a chroot and cleans up attached devices.

  This function attempts to perform all of the cleanup steps even if the chroot
  directory and/or image isn't present.  This ensures that a partially destroyed
  chroot can still be cleaned up.  This function does not remove the actual
  chroot directory (or its content for non-loopback chroots).

  Args:
    chroot: Full path to the chroot to examine, or None to find it relative
        to |buildroot|.
    buildroot: Ignored if |chroot| is set.  If |chroot| is None, find the chroot
        relative to |buildroot|.
    delete: Delete chroot contents and the .img file after cleaning up.  If
        |delete| is False, the chroot contents will still be present and
        can be immediately re-mounted without recreating a fresh chroot.
    proc_mounts: The path to a list of mounts to read (intended for testing).
  """
  if chroot is None and buildroot is None:
    raise ValueError('need either |chroot| or |buildroot| to search')
  if chroot is None:
    chroot = os.path.join(buildroot, constants.DEFAULT_CHROOT_DIR)
  chroot_img = chroot + '.img'

  # Try to find the VG that might already be mounted on the chroot before we
  # unmount it.
  vg_name, _ = FindChrootMountSource(chroot, proc_mounts=proc_mounts)

  try:
    osutils.UmountTree(chroot)
  except cros_build_lib.RunCommandError as e:
    # TODO(lamontjones): Dump some information to help find the process still
    # inside the chroot, causing crbug.com/923432.  In the end, this is likely
    # to become fuser -k.
    fs_debug = GetFileSystemDebug(chroot, run_ps=True)
    raise Error(
        'Umount failed: %s.\nfuser output=%s\nlsof output=%s\nps output=%s\n' %
        (e.result.error, fs_debug.fuser, fs_debug.lsof, fs_debug.ps))

  # Find the loopback device by either matching the VG or the image.
  chroot_dev = None
  if vg_name:
    cmd = ['vgs', '-q', '--noheadings', '-o', 'pv_name', '--unbuffered',
           vg_name]
    result = cros_build_lib.sudo_run(
        cmd, capture_output=True, check=False, print_cmd=False,
        encoding='utf-8')
    if result.returncode == 0:
      chroot_dev = result.output.strip()
    else:
      vg_name = None
  if not chroot_dev:
    chroot_dev = _DeviceFromFile(chroot_img)

  # If we didn't find a mounted VG before but we did find a loopback device,
  # re-check for a VG attached to the loopback.
  if not vg_name:
    vg_name = FindVolumeGroupForDevice(chroot, chroot_dev)
    if vg_name:
      cmd = ['vgs', vg_name]
      result = cros_build_lib.sudo_run(
          cmd, capture_output=True, check=False, print_cmd=False,
          encoding='utf-8')
      if result.returncode != 0:
        vg_name = None

  # Clean up all the pieces we found above.
  if vg_name:
    cmd = ['vgchange', '-an', vg_name]
    cros_build_lib.sudo_run(cmd, capture_output=True, print_cmd=False)
  if chroot_dev:
    cmd = ['losetup', '-d', chroot_dev]
    cros_build_lib.sudo_run(cmd, capture_output=True, print_cmd=False)
  if delete:
    osutils.SafeUnlink(chroot_img)
    osutils.RmDir(chroot, ignore_missing=True, sudo=True)

  if chroot_dev:
    # Force a rescan after everything is gone to make sure lvmetad is updated.
    _RescanDeviceLvmMetadata(chroot_dev)


def _RescanDeviceLvmMetadata(chroot_dev):
  """Forces lvmetad to rescan a device.

  After attaching or detaching a loopback device, lvmetad is supposed to
  automatically scan it.  This doesn't always happen reliably, so this function
  lets you force an LVM rescan.  This is intended for cases where the whole
  device will be used as an LVM PV, not for cases where you want to rescan a
  device's partition table.  For manipulating loopback device partitions, see
  the image_lib.LoopbackPartitions class.

  Args:
    chroot_dev: Full path to the device that should be rescanned.
  """
  # This may fail if lvmetad isn't in use, but it's faster to ignore the
  # exit code than to check if we should actually run the command.
  cmd = ['pvscan', '--cache', chroot_dev]
  cros_build_lib.sudo_run(
      cmd, capture_output=True, print_cmd=False, check=False)


def RunChrootVersionHooks(version_file=None, hooks_dir=None):
  """Run the chroot version hooks to bring the chroot up to date."""
  if not cros_build_lib.IsInsideChroot():
    command = ['run_chroot_version_hooks']
    cros_build_lib.run(command, enter_chroot=True)
  else:
    chroot = ChrootUpdater(version_file=version_file, hooks_dir=hooks_dir)
    chroot.ApplyUpdates()


def InitLatestVersion(version_file=None, hooks_dir=None):
  """Initialize the chroot version to the latest version."""
  if not cros_build_lib.IsInsideChroot():
    # Run the command in the chroot.
    command = ['run_chroot_version_hooks', '--init-latest']
    cros_build_lib.run(command, enter_chroot=True)
  else:
    # Initialize the version.
    chroot = ChrootUpdater(version_file=version_file, hooks_dir=hooks_dir)
    if chroot.IsInitialized():
      logging.info('Chroot is already initialized to %s.', chroot.GetVersion())
    else:
      logging.info('Initializing chroot to version %s.', chroot.latest_version)
      chroot.SetVersion(chroot.latest_version)


class ChrootUpdater(object):
  """Chroot version and update related functionality."""

  def __init__(self, version_file=None, hooks_dir=None):
    if version_file:
      # We have one. Just here to skip the logic below since we don't need it.
      default_version_file = None
    elif cros_build_lib.IsInsideChroot():
      # Use the absolute path since we're inside the chroot.
      default_version_file = CHROOT_VERSION_FILE
    else:
      # Otherwise convert to the path outside the chroot.
      default_version_file = path_util.FromChrootPath(CHROOT_VERSION_FILE)

    self._version_file = version_file or default_version_file
    self._hooks_dir = hooks_dir or _CHROOT_VERSION_HOOKS_DIR

    self._version = None
    self._latest_version = None
    self._hook_files = None

  @property
  def latest_version(self):
    """Get the highest available version for the chroot."""
    if self._latest_version is None:
      self._latest_version = LatestChrootVersion(self._hooks_dir)
    return self._latest_version

  def GetVersion(self):
    """Get the chroot version.

    Returns:
      int

    Raises:
      InvalidChrootVersionError when the file contents are not a valid version.
      IOError when the file cannot be read.
      UninitializedChrootError when the version file does not exist.
    """
    if self._version is None:
      # Check for existence so IOErrors from osutils.ReadFile are limited to
      # permissions problems.
      if not os.path.exists(self._version_file):
        raise UninitializedChrootError(
            'Version file does not exist: %s' % self._version_file)

      version = osutils.ReadFile(self._version_file)

      try:
        self._version = int(version)
      except ValueError:
        raise InvalidChrootVersionError(
            'Invalid chroot version in %s: %s' % (self._version_file, version))

    return self._version

  def SetVersion(self, version):
    """Set and store the chroot version."""
    self._version = version
    osutils.WriteFile(self._version_file, str(version), sudo=True)
    # TODO(saklein) Verify if this chown is necessary. The version file
    # is in /etc, so it's reasonable to expect root would own it, but the bash
    # version had the chown for many years before the conversion.
    osutils.Chown(self._version_file)

  def IsInitialized(self):
    """Initialized Check."""
    try:
      return self.GetVersion() > 0
    except (Error, IOError):
      return False

  def ApplyUpdates(self):
    """Apply all necessary updates to the chroot."""
    if self.GetVersion() > self.latest_version:
      raise InvalidChrootVersionError(
          'Missing upgrade hook for version %s.\n'
          'Chroot is too new. Consider running:\n'
          '    cros_sdk --replace' %  self.GetVersion())

    for hook, version in self.GetChrootUpdates():
      result = cros_build_lib.run(['bash', hook],
                                  enter_chroot=True, check=False)
      if not result.returncode:
        self.SetVersion(version)
      else:
        raise ChrootUpdateError('Error running chroot version hook: %s' % hook)

  def GetChrootUpdates(self):
    """Get all (update file, version) pairs that have not been run.

    Returns:
      list of (/path/to/hook/file, version) pairs in order.

    Raises:
      ChrootDeprecatedError when one or more required update files have been
          deprecated.
    """
    hooks = self._GetHookFilesByVersion()

    # Create the relevant ChrootUpdates.
    updates = []
    # Current version has already been run and we need to run the latest, so +1
    # for each end of the version range.
    for version in range(self.GetVersion() + 1, self.latest_version + 1):
      # Deprecation check: Deprecation is done by removing old scripts. Updates
      # must form a continuous sequence. If the sequence is broken between the
      # chroot's current version and the most recent, then the chroot must be
      # recreated.
      if version not in hooks:
        raise ChrootDeprecatedError()

      updates.append((hooks[version], version))

    return updates

  def _GetHookFilesByVersion(self):
    """Find and store the hooks by their version number.

    Returns:
      dict - {version: /path/to/hook/file} mapping.

    Raises:
      VersionHasMultipleHooksError when multiple hooks exist for a version.
    """
    if self._hook_files:
      return self._hook_files

    hook_files = {}
    for hook in os.listdir(self._hooks_dir):
      version = int(hook.split('_', 1)[0])

      # Sanity check: Each version may only have a single script. Multiple CLs
      # landed at the same time and no one noticed the version overlap.
      if version in hook_files:
        raise VersionHasMultipleHooksError(
            'Version %s has multiple hooks.' % version)

      hook_files[version] = os.path.join(self._hooks_dir, hook)

    self._hook_files = hook_files
    return self._hook_files


class ChrootCreator:
  """Creates a new chroot from a given SDK."""

  MAKE_CHROOT = os.path.join(
      constants.SOURCE_ROOT, 'src/scripts/sdk_lib/make_chroot.sh')

  # If the host timezone isn't set, we'll use this inside the SDK.
  DEFAULT_TZ = 'usr/share/zoneinfo/PST8PDT'

  # Groups to add the user to inside the chroot.
  # This group list is a bit dated and probably contains a number of items that
  # no longer make sense.
  # TODO(crbug.com/762445): Remove "adm".
  # TODO(build): Remove cdrom & floppy.
  # TODO(build): See if audio is still needed.  Host distros might use diff
  # "audio" group, so we wouldn't get access to /dev/snd/ nodes directly.
  # TODO(build): See if video is still needed.  Host distros might use diff
  # "video" group, so we wouldn't get access to /dev/dri/ nodes directly.
  DEFGROUPS = {'adm', 'cdrom', 'floppy', 'audio', 'video', 'portage'}

  def __init__(self, chroot_path: Path, sdk_tarball: Path, cache_dir: Path,
               usepkg: bool = True):
    """Initialize.

    Args:
      chroot_path: Path where the new chroot will be created.
      sdk_tarball: Path to a downloaded Chromium OS SDK tarball.
      cache_dir: Path to a directory that will be used for caching files.
      usepkg: If False, pass --nousepkg to cros_setup_toolchains inside the
          chroot.
    """
    self.chroot_path = chroot_path
    self.sdk_tarball = sdk_tarball
    self.cache_dir = cache_dir
    self.usepkg = usepkg

  def _make_chroot(self):
    """Create the chroot."""
    cmd = [
        self.MAKE_CHROOT,
        '--chroot', str(self.chroot_path),
        '--cache_dir', str(self.cache_dir),
    ]

    if not self.usepkg:
      cmd.append('--nousepkg')

    try:
      cros_build_lib.dbg_run(cmd)
    except cros_build_lib.RunCommandError as e:
      cros_build_lib.Die('Creating chroot failed!\n%s', e)

  def init_timezone(self):
    """Setup the timezone info inside the chroot."""
    tz_path = Path('etc/localtime')
    host_tz = '/' / tz_path
    chroot_tz = self.chroot_path / tz_path
    # Nuke it in case it's a broken symlink.
    osutils.SafeUnlink(chroot_tz)
    if host_tz.exists():
      logging.debug('%s: copying from %s', chroot_tz, host_tz)
      chroot_tz.write_bytes(host_tz.read_bytes())
    else:
      logging.debug('%s: symlinking to %s', chroot_tz, self.DEFAULT_TZ)
      chroot_tz.symlink_to(self.DEFAULT_TZ)

  def init_user(self,
                user: Optional[str] = None,
                uid: Optional[int] = None,
                gid: Optional[int] = None):
    """Setup the current user inside the chroot.

    The user account name & id are synced with the active account outside of the
    SDK.  This helps facilitate copying of files in & out of the SDK without the
    need of sudo.

    The user account must not already exist inside the SDK (as a pre-existing
    reserved name) otherwise we can't create it with the right uid.

    Args:
      user: The username to create.
      uid: The new account's userid.
      gid: The new account's groupid.
    """
    if not user:
      user = os.getenv('SUDO_USER')
    if uid is None:
      uid = int(os.getenv('SUDO_UID'))
    if gid is None:
      gid = pwd.getpwnam(user).pw_gid

    path = self.chroot_path / 'etc' / 'passwd'
    lines = path.read_text().splitlines()

    # Make sure the user isn't one the existing reserved ones.
    for line in lines:
      existing_user = line.split(':', 1)[0]
      if existing_user == user:
        cros_build_lib.Die(f'{user}: this account cannot be used to build CrOS')

    # Create the account.
    home = f'/home/{user}'
    line = f'{user}:x:{uid}:{gid}:ChromeOS Developer:{home}:/bin/bash'
    logging.debug('%s: adding user: %s', path, line)
    lines.insert(0, line)
    path.write_text('\n'.join(lines) + '\n')

    home = self.chroot_path / home[1:]
    self.init_user_home(home, uid, gid)

  def init_group(self,
                 user: Optional[str] = None,
                 groups: Optional[List[str]] = None,
                 group: Optional[str] = None,
                 gid: Optional[int] = None):
    """Setup the current user's groups inside the chroot.

    This will create the user's primary group and add them to a bunch of
    supplemental groups.  The primary group is synced with the active account
    outside of the SDK to help facilitate accessing of files & resources (e.g.
    any /dev nodes).

    The primary group must not already exist inside the SDK (as a pre-existing
    reserved name) otherwise we can't create it with the right gid.

    Args:
      user: The username to add to groups.
      groups: The account's supplemental groups.
      group: The account's primary group (to be created).
      gid: The primary group's gid.
    """
    if not user:
      user = os.getenv('SUDO_USER')
    if groups is None:
      groups = self.DEFGROUPS
    if gid is None:
      gid = pwd.getpwnam(user).pw_gid
    if group is None:
      group = grp.getgrgid(gid).gr_name

    path = self.chroot_path / 'etc' / 'group'
    lines = path.read_text().splitlines()

    # Make sure the group isn't one the existing reserved ones.
    # Add the user to all the existing ones too.
    for i, line in enumerate(lines):
      entry = line.split(':')
      if entry[0] == group:
        # If the group exists with the same gid, no need to add a new one.
        # This often comes up with e.g. the "users" group.
        if entry[2] == str(gid):
          return
        cros_build_lib.Die(f'{group}: this group cannot be used to build CrOS')
      if entry[0] in groups:
        if entry[-1]:
          entry[-1] += ','
        entry[-1] += user
        lines[i] = ':'.join(entry)

    line = f'{group}:x:{gid}:{user}'
    logging.debug('%s: adding group: %s', path, line)
    lines.insert(0, line)
    path.write_text('\n'.join(lines) + '\n')

  def init_user_home(self, home: Path, uid: int, gid: int):
    """Initialize the user's /home dir."""
    shutil.copytree(self.chroot_path / 'etc/skel', home)

    # TODO(build): Delete this leftover from SVN someday.
    (home / 'trunk').symlink_to(constants.CHROOT_SOURCE_ROOT)
    (home / 'chromiumos').symlink_to(constants.CHROOT_SOURCE_ROOT)
    (home / 'depot_tools').symlink_to('/mnt/host/depot_tools')

    # Automatically change to scripts directory.
    bash_profile = home / '.bash_profile'
    osutils.Touch(bash_profile)
    data = bash_profile.read_text().rstrip()
    if data:
      data += '\n\n'
    data += (
        'cd "${CHROOT_CWD:-${HOME}/chromiumos/src/scripts}"\n'
    )
    bash_profile.write_text(data)

    # Enable bash completion.
    bashrc = home / '.bashrc'
    osutils.Touch(bashrc)
    data = bashrc.read_text().rstrip()
    if data:
      data += '\n\n'
    data += (
        '# Set up bash autocompletion.\n'
        '. ~/chromiumos/src/scripts/bash_completion\n'
    )
    bashrc.write_text(data)

    osutils.Chown(home, user=uid, group=gid, recursive=True)

  def init_filesystem_basic(self):
    """Create various dirs & simple config files."""
    # Create random empty dirs.
    for path in (
        constants.CHROOT_SOURCE_ROOT,
        '/mnt/host/depot_tools',
        '/run',
    ):
      (self.chroot_path / path[1:]).mkdir(
          mode=0o755, parents=True, exist_ok=True)

  def init_etc(self, user: str = None):
    """Setup the /etc paths."""
    if user is None:
      user = os.getenv('SUDO_USER')

    etc_dir = self.chroot_path / 'etc'

    # Setup some symlinks.
    mtab = etc_dir / 'mtab'
    if not mtab.is_symlink():
      osutils.SafeUnlink(mtab)
      mtab.symlink_to('/proc/mounts')

    # Copy config from outside chroot into chroot.
    for path in ('hosts', 'resolve.conf'):
      host_path = Path('/etc') / path
      chroot_path = etc_dir / path
      if host_path.exists():
        chroot_path.write_bytes(host_path.read_bytes())
        chroot_path.chmod(0o644)

    # Add chromite/bin and depot_tools into the path globally; note that the
    # chromite wrapper itself might also be found in depot_tools.
    # We rely on 'env-update' getting called below.
    env_d = etc_dir / 'env.d' / '99chromiumos'
    env_d.write_text(f"""\
PATH="{constants.CHROOT_SOURCE_ROOT}/chromite/bin:/mnt/host/depot_tools"
CROS_WORKON_SRCROOT="{constants.CHROOT_SOURCE_ROOT}"
PORTAGE_USERNAME="{user}"
""")

    profile_d = etc_dir / 'profile.d'
    profile_d.mkdir(mode=0o755, parents=True, exist_ok=True)
    (profile_d / '50-chromiumos-niceties.sh').symlink_to(
        f'{constants.CHROOT_SOURCE_ROOT}/chromite/sdk/etc/profile.d/'
        '50-chromiumos-niceties.sh')

    # Select a small set of locales for the user if they haven't done so
    # already.  This makes glibc upgrades cheap by only generating a small
    # set of locales.  The ones listed here are basically for the buildbots
    # which always assume these are available.  This works in conjunction
    # with `cros_sdk --enter`.
    # http://crosbug.com/20378
    localegen = etc_dir / 'locale.gen'
    osutils.Touch(localegen)
    data = localegen.read_text().rstrip()
    if data:
      data += '\n\n'
    localegen.write_text(data + 'en_US.UTF-8 UTF-8\n')

  def print_success_summary(self):
    """Show a summary of the chroot to the user."""
    default_chroot = Path(constants.SOURCE_ROOT) / constants.DEFAULT_CHROOT_DIR
    chroot_opt = ''
    if default_chroot != self.chroot_path:
      chroot_opt = f' --chroot={self.chroot_path}'
    logging.info("""
All set up.  To enter the chroot, run:
$ cros_sdk --enter%s

CAUTION: Do *NOT* rm -rf the chroot directory; if there are stale bind mounts
you may end up deleting your source tree too.  To unmount & delete cleanly, use:
$ cros_sdk --delete%s
""", chroot_opt, chroot_opt)

  def run(self,
          user: str = None, uid: int = None,
          group: str = None, gid: int = None):
    """Create the chroot.

    Args:
      user: The user account to use (e.g. for testing).
      uid: The user id to use (e.g. for testing).
      group: The group account to use (e.g. for testing).
      gid: The group id to use (e.g. for testing).
    """
    logging.notice('Creating chroot. This may take a few minutes...')

    # Unpack the chroot & reset the version.
    self.chroot_path.mkdir(mode=0o755, parents=True, exist_ok=True)
    cros_build_lib.ExtractTarball(self.sdk_tarball, self.chroot_path)
    updater = ChrootUpdater(self.chroot_path / CHROOT_VERSION_FILE[1:])
    updater.SetVersion(0)

    self.init_timezone()
    self.init_user(user=user, uid=uid, gid=gid)
    self.init_group(user=user, group=group, gid=gid)
    self.init_filesystem_basic()
    self.init_etc(user=user)

    MountChrootPaths(self.chroot_path)

    self._make_chroot()

    # TODO(build): Delete this once all users migrate to cros_chroot_version.
    osutils.Touch(self.chroot_path / 'etc' / 'debian_chroot')

    self.print_success_summary()


def CreateChroot(*args, **kwargs):
  """Convenience method."""
  ChrootCreator(*args, **kwargs).run()
