# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Library containing functions to transfer files onto a remote device.

Transfer Base class includes:

  ----Tranfer----
  * @retry functionality for all public transfer functions.

LocalTransfer includes:

  ----Precheck---
  * Pre-check payload's existence before auto-update.

  ----Tranfer----
  * Transfer update-utils (nebraska, et. al.) package at first.
  * Transfer rootfs update files if rootfs update is required.
  * Transfer stateful update files if stateful update is required.

LabEndToEndPayloadTransfer includes:

  ----Precheck---
  * Pre-check payload's existence on the staging server before auto-update.

  ----Tranfer----
  * Download the update-utils (nebraska, et. al.) package onto the DUT directly
    from the staging server at first.
  * Download rootfs update files onto the DUT directly from the staging server
    if rootfs update is required.
  * Download stateful update files onto the DUT directly from the staging server
    if stateful update is required.
"""

from __future__ import absolute_import
from __future__ import division

import abc
import logging
import os
import urllib.parse

from chromite.lib import cros_build_lib
from chromite.lib import nebraska_wrapper
from chromite.lib import osutils
from chromite.lib import retry_util


# Naming conventions for global variables:
#   Path on remote host with slash: REMOTE_XXX_PATH
#   File on local server without slash: LOCAL_XXX_FILENAME
#   Path on local server: LOCAL_XXX_PATH

# Max number of the times for retry:
# 1. for transfer functions to be retried.
# 2. for some retriable commands to be retried.
_MAX_RETRY = 5

# The delay between retriable tasks.
_DELAY_SEC_FOR_RETRY = 5

# Update file names for rootfs+kernel and stateful partitions.
ROOTFS_FILENAME = 'update.gz'
STATEFUL_FILENAME = 'stateful.tgz'

# Regular expression that is used to evaluate payload names to determine payload
# validity.
_PAYLOAD_PATTERN = r'payloads/chromeos_(?P<image_version>[^_]+)_.*'

# File copying modes.
_SCP = 'scp'


class Error(Exception):
  """A generic auto updater transfer error."""


class ChromiumOSTransferError(Error):
  """Thrown when there is a general transfer specific error."""


def GetPayloadPropertiesFileName(payload):
  """Returns the payload properties file given the path to the payload."""
  return payload + '.json'


class Transfer(object, metaclass=abc.ABCMeta):
  """Abstract Base Class that handles payload precheck and transfer."""

  PAYLOAD_DIR_NAME = 'payloads'

  def __init__(self, device, payload_dir, tempdir,
               payload_name, cmd_kwargs, device_payload_dir,
               payload_mode='scp', transfer_stateful_update=True,
               transfer_rootfs_update=True):
    """Initialize Base Class for transferring payloads functionality.

    Args:
      device: The ChromiumOSDevice to be updated.
      payload_dir: The directory of payload(s).
      tempdir: The temp directory in caller, not in the device. For example,
          the tempdir for cros flash is /tmp/cros-flash****/, used to
          temporarily keep files when transferring update-utils package, and
          reserve nebraska and update engine logs.
      payload_name: Filename of exact payload file to use for update.
      cmd_kwargs: Keyword arguments that are sent along with the commands that
          are run on the device.
      device_payload_dir: Path to the payload directory in the device's work
          directory.
      payload_mode: The payload mode - it can be 'parallel' or 'scp'.
      transfer_stateful_update: Whether to transfer payloads necessary for
          stateful update. The default is True.
      transfer_rootfs_update: Whether to transfer payloads necessary for
          rootfs update. The default is True.
    """
    self._device = device
    self._payload_dir = payload_dir
    self._tempdir = tempdir
    self._payload_name = payload_name
    self._cmd_kwargs = cmd_kwargs
    self._device_payload_dir = device_payload_dir
    if payload_mode not in ('scp', 'parallel'):
      raise ValueError('The given value %s for payload mode is not valid.' %
                       payload_mode)
    self._payload_mode = payload_mode
    self._transfer_stateful_update = transfer_stateful_update
    self._transfer_rootfs_update = transfer_rootfs_update

  @abc.abstractmethod
  def CheckPayloads(self):
    """Verify that all required payloads are in |self.payload_dir|."""

  def TransferUpdateUtilsPackage(self):
    """Transfer update-utils package to work directory of the remote device."""
    retry_util.RetryException(
        cros_build_lib.RunCommandError,
        _MAX_RETRY,
        self._TransferUpdateUtilsPackage,
        delay_sec=_DELAY_SEC_FOR_RETRY)

  def TransferRootfsUpdate(self):
    """Transfer files for rootfs update.

    The corresponding payloads are copied to the remote device for rootfs
    update.
    """
    retry_util.RetryException(
        cros_build_lib.RunCommandError,
        _MAX_RETRY,
        self._TransferRootfsUpdate,
        delay_sec=_DELAY_SEC_FOR_RETRY)

  def TransferStatefulUpdate(self):
    """Transfer files for stateful update.

    The stateful update bin and the corresponding payloads are copied to the
    target remote device for stateful update.
    """
    retry_util.RetryException(
        cros_build_lib.RunCommandError,
        _MAX_RETRY,
        self._TransferStatefulUpdate,
        delay_sec=_DELAY_SEC_FOR_RETRY)

  def _EnsureDeviceDirectory(self, directory):
    """Mkdir the directory no matther whether this directory exists on host.

    Args:
      directory: The directory to be made on the device.
    """
    self._device.run(['mkdir', '-p', directory], **self._cmd_kwargs)


class LocalTransfer(Transfer):
  """Abstracts logic that handles transferring local files to the DUT."""

  def __init__(self, *args, **kwargs):
    """Initialize LocalTransfer to handle transferring files from local to DUT.

    Args:
      *args: The list of arguments to be passed. See Base class for a complete
          list of accepted arguments.
      **kwargs: Any keyword arguments to be passed. See Base class for a
          complete list of accepted keyword arguments.
    """
    super().__init__(*args, **kwargs)

  def CheckPayloads(self):
    """Verify that all required payloads are in |self.payload_dir|."""
    logging.debug('Checking if payloads have been stored in directory %s...',
                  self._payload_dir)
    filenames = []

    if self._transfer_rootfs_update:
      filenames += [self._payload_name,
                    GetPayloadPropertiesFileName(self._payload_name)]

    if self._transfer_stateful_update:
      filenames += [STATEFUL_FILENAME]

    for fname in filenames:
      payload = os.path.join(self._payload_dir, fname)
      if not os.path.exists(payload):
        raise ChromiumOSTransferError('Payload %s does not exist!' % payload)

  def _TransferUpdateUtilsPackage(self):
    """Transfer update-utils package to work directory of the remote device."""
    logging.notice('Copying update script to device...')
    source_dir = os.path.join(self._tempdir, 'src')
    osutils.SafeMakedirs(source_dir)
    nebraska_wrapper.RemoteNebraskaWrapper.GetNebraskaSrcFile(source_dir)

    # Make sure the device.work_dir exists after any installation and reboot.
    self._EnsureDeviceDirectory(self._device.work_dir)
    # Python packages are plain text files.
    self._device.CopyToWorkDir(source_dir, mode=_SCP, log_output=True,
                               **self._cmd_kwargs)

  def _TransferRootfsUpdate(self):
    """Transfer files for rootfs update.

    Copy the update payload to the remote device for rootfs update.
    """
    self._EnsureDeviceDirectory(self._device_payload_dir)
    logging.notice('Copying rootfs payload to device...')
    payload = os.path.join(self._payload_dir, self._payload_name)
    self._device.CopyToWorkDir(payload, self.PAYLOAD_DIR_NAME,
                               mode=self._payload_mode,
                               log_output=True, **self._cmd_kwargs)
    payload_properties_path = GetPayloadPropertiesFileName(payload)
    self._device.CopyToWorkDir(payload_properties_path, self.PAYLOAD_DIR_NAME,
                               mode=self._payload_mode,
                               log_output=True, **self._cmd_kwargs)

  def _TransferStatefulUpdate(self):
    """Transfer files for stateful update.

    The stateful update payloads are copied to the target remote device for
    stateful update.
    """
    logging.notice('Copying target stateful payload to device...')
    payload = os.path.join(self._payload_dir, STATEFUL_FILENAME)
    self._device.CopyToWorkDir(payload, mode=self._payload_mode,
                               log_output=True, **self._cmd_kwargs)


class LabEndToEndPayloadTransfer(Transfer):
  """Abstracts logic that transfers files from staging server to the DUT."""

  def __init__(self, staging_server, *args, **kwargs):
    """Initialize to transfer files from staging server to DUT.

    Args:
      staging_server: Url of the server that's staging the payload files.
      *args: The list of arguments to be passed. See Base class for a complete
          list of accepted arguments.
      **kwargs: Any keyword arguments to be passed. See Base class for a
          complete list of accepted keyword arguments.
    """
    self._staging_server = staging_server
    super().__init__(*args, **kwargs)

  def _RemoteDevserverCall(self, cmd, stdout=False):
    """Runs a command on a remote devserver by sshing into it.

    Raises cros_build_lib.RunCommandError() if the command could not be run
    successfully.

    Args:
      cmd: (list) the command to be run.
      stdout: True if the stdout of the command should be captured.
    """
    ip = urllib.parse.urlparse(self._staging_server).hostname
    return cros_build_lib.run(['ssh', ip] + cmd, log_output=True, stdout=stdout)

  def _CheckPayloads(self, payload_name):
    """Runs the curl command that checks if payloads have been staged."""
    payload_url = self._GetStagedUrl(staged_filename=payload_name,
                                     build_id=self._payload_dir)
    cmd = ['curl', '-I', payload_url, '--fail']
    try:
      self._RemoteDevserverCall(cmd)
    except cros_build_lib.RunCommandError as e:
      raise ChromiumOSTransferError(
          'Could not verify if %s was staged at %s. Received exception: %s' %
          (payload_name, payload_url, e))

  def CheckPayloads(self):
    """Verify that all required payloads are staged on staging server."""
    logging.debug('Checking if payloads have been staged on server %s...',
                  self._staging_server)

    if self._transfer_rootfs_update:
      self._CheckPayloads(self._payload_name)
      self._CheckPayloads(GetPayloadPropertiesFileName(self._payload_name))

    if self._transfer_stateful_update:
      self._CheckPayloads(STATEFUL_FILENAME)

  def _GetStagedUrl(self, staged_filename, build_id=None):
    """Returns a valid url to check availability of staged files.

    Args:
      staged_filename: Name of the staged file.
      build_id: This is the path at which the needed file can be found. It
        is usually of the format <board_name>-release/R79-12345.6.0. By default,
        the path is set to be None.

    Returns:
      A URL in the format:
        http://<ip>:<port>/static/<board>-release/<version>/<staged_filename>
    """
    # Formulate the download URL out of components.
    url = urllib.parse.urljoin(self._staging_server, 'static/')
    if build_id:
      # Add slash at the end of image_name if necessary.
      if not build_id.endswith('/'):
        build_id = build_id + '/'
      url = urllib.parse.urljoin(url, build_id)
    return urllib.parse.urljoin(url, staged_filename)

  def _GetCurlCmdForPayloadDownload(self, payload_dir, payload_filename,
                                    build_id=None):
    """Returns a valid curl command to download payloads into device tmp dir.

    Args:
      payload_dir: Path to the payload directory on the device.
      payload_filename: Name of the file by which the downloaded payload should
        be saved. This is assumed to be the same as the name of the payload.
        If the payload_name must is in this format:
        payloads/whatever_file_name, the 'payloads/' at the start will be
        removed while saving the file as the files need to be saved in specific
        directories for their subsequent installation. Keeping the 'payloads/'
        at the beginning of the payload_filename, adds a new directory that
        messes up its installation.
      build_id: This is the path at which the needed payload can be found. It
        is usually of the format <board_name>-release/R79-12345.6.0. By default,
        the path is set to None.

    Returns:
      A fully formed curl command in the format:
      ['curl', '-o', '<path where payload should be saved>',
      '<payload download URL>']
    """
    saved_filename = payload_filename
    if saved_filename.startswith('payloads/'):
      saved_filename = '/'.join(saved_filename.split('/')[1:])
    cmd = ['curl', '-o', os.path.join(payload_dir, saved_filename),
           self._GetStagedUrl(payload_filename, build_id)]
    return cmd

  def _TransferUpdateUtilsPackage(self):
    """Transfer update-utils package to work directory of the remote device.

    The update-utils package will be transferred to the device from the
    staging server via curl.
    """
    logging.notice('Copying update script to device...')
    source_dir = os.path.join(self._device.work_dir, 'src')
    self._EnsureDeviceDirectory(source_dir)

    self._device.run(self._GetCurlCmdForPayloadDownload(
        payload_dir=source_dir,
        payload_filename=nebraska_wrapper.NEBRASKA_FILENAME))

    # Make sure the device.work_dir exists after any installation and reboot.
    self._EnsureDeviceDirectory(self._device.work_dir)

  def _TransferStatefulUpdate(self):
    """Transfer files for stateful update.

    The stateful update bin and the corresponding payloads are copied to the
    target remote device for stateful update from the staging server via curl.
    """
    self._EnsureDeviceDirectory(self._device_payload_dir)

    # TODO(crbug.com/1024639): Another way to make the payloads available is
    # to make update_engine download it directly from the staging_server. This
    # will avoid a disk copy but has the potential to be harder to debug if
    # update engine does not report the error clearly.

    logging.notice('Copying target stateful payload to device...')
    self._device.run(self._GetCurlCmdForPayloadDownload(
        payload_dir=self._device.work_dir, build_id=self._payload_dir,
        payload_filename=STATEFUL_FILENAME))

  def _TransferRootfsUpdate(self):
    """Transfer files for rootfs update.

    Copy the update payload to the remote device for rootfs update from the
    staging server via curl.
    """
    self._EnsureDeviceDirectory(self._device_payload_dir)

    logging.notice('Copying rootfs payload to device...')

    # TODO(crbug.com/1024639): Another way to make the payloads available is
    # to make update_engine download it directly from the staging_server. This
    # will avoid a disk copy but has the potential to be harder to debug if
    # update engine does not report the error clearly.

    self._device.run(self._GetCurlCmdForPayloadDownload(
        payload_dir=self._device_payload_dir, build_id=self._payload_dir,
        payload_filename=self._payload_name))

    self._device.run(self._GetCurlCmdForPayloadDownload(
        payload_dir=self._device_payload_dir, build_id=self._payload_dir,
        payload_filename=GetPayloadPropertiesFileName(self._payload_name)))
