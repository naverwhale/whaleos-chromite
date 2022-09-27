#!/usr/bin/env python3
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to detect flashing infrastructure and flash ap firmware.

This script automatically detects the flashing infrastructure and uses that to
flash AP fw to the DUT. First it checks for the environment variable $IP, then
tries flash via ssh to that address if one is present. If not it looks up what
servo version is connected and uses that to flash the AP firmware. Right now
this script only works with octopus, grunt, wilco, and hatch devices but will
be extended to support more in the future.
"""

import logging
import os
import shutil
import tempfile
import time
from typing import Iterable, Optional

from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib.firmware import ap_firmware
from chromite.lib.firmware import servo_lib


class Error(Exception):
  """Base module error class."""


class DeployFailed(Error):
  """Error raised when deploy fails."""


class MissingBuildTargetCommandsError(Error):
  """Error thrown when board-specific functionality can't be imported."""


def _build_flash_ssh_cmds(futility, ip, port, path, tmp_file_name, fast,
                          verbose, passthrough_args: Iterable[str] = tuple()):
  """Helper function to build commands for flashing over ssh

  Args:
    futility (bool): if True then flash with futility, otherwise flash
      with flashrom.
    ip (string): ip address of dut to flash.
    port (int): The port to ssh to.
    path (string): path to BIOS image to be flashed.
    tmp_file_name (string): name of tempfile with copy of testing_rsa
      keys.
    fast (bool): if True pass through --fast (-n for flashrom) to
      flashing command.
    verbose (bool): if True set -v flag in flash command.
    passthrough_args: List of additional options passed to flashrom or futility.

  Returns:
    scp_cmd ([string]):
    flash_cmd ([string]):
  """
  ssh_parameters = [
      '-o', 'UserKnownHostsFile=/dev/null', '-o', 'StrictHostKeyChecking=no',
      '-o', 'CheckHostIP=no'
  ]
  ssh_port = ['-p', str(port)] if port else []
  scp_port = ['-P', str(port)] if port else []
  tmp = '/tmp'
  hostname = 'root@%s' % ip
  scp_cmd = (['scp', '-i', tmp_file_name] + scp_port + ssh_parameters +
             [path, '%s:%s' % (hostname, tmp)])
  flash_cmd = ['ssh', hostname, '-i', tmp_file_name] + ssh_port + ssh_parameters
  if futility:
    flash_cmd += [
        'futility', 'update', '-p', 'host', '-i',
        os.path.join(tmp, os.path.basename(path))
    ]
    if fast:
      flash_cmd += ['--fast']
    if verbose:
      flash_cmd += ['-v']
  else:
    flash_cmd += [
        'flashrom', '-p', 'host', '-w',
        os.path.join(tmp, os.path.basename(path))
    ]
    if fast:
      flash_cmd += ['-n']
    if verbose:
      flash_cmd += ['-V']
  if passthrough_args:
    flash_cmd += passthrough_args
  flash_cmd += ['&& reboot']
  return scp_cmd, flash_cmd


def _ssh_flash(futility, path, verbose, ip, port, fast, dryrun,
               passthrough_args: Iterable[str] = tuple()):
  """This function flashes AP firmware over ssh.

  Tries to ssh to ip address once. If the ssh connection is successful the
  file to be flashed is copied over to the DUT then flashed using either
  futility or flashrom.

  Args:
    futility (bool): if True then flash with futility, otherwise flash
      with flashrom.
    path (str): path to the BIOS image to be flashed.
    verbose (bool): if True to set -v flag in flash command and
      print other debug info, if False do nothing.
    ip (str): ip address of dut to flash.
    port (int): The port to ssh to.
    fast (bool): if True pass through --fast (-n for flashrom) to
      flashing command.
    dryrun (bool): Whether to actually execute the commands or just print
      the commands that would have been run.
    passthrough_args: List of additional options passed to flashrom or futility.

  Returns:
    bool: True on success, False on failure.
  """
  logging.info('connecting to: %s\n', ip)
  id_filename = '/mnt/host/source/chromite/ssh_keys/testing_rsa'
  tmpfile = tempfile.NamedTemporaryFile()
  shutil.copyfile(id_filename, tmpfile.name)

  scp_cmd, flash_cmd = _build_flash_ssh_cmds(futility, ip, port, path,
                                             tmpfile.name, fast, verbose,
                                             passthrough_args)
  try:
    cros_build_lib.run(scp_cmd, print_cmd=verbose, check=True, dryrun=dryrun)
  except cros_build_lib.CalledProcessError:
    logging.error('Could not copy image to dut.')
    return False

  logging.info('Flashing now, may take several minutes.')
  try:
    cros_build_lib.run(flash_cmd, print_cmd=verbose, check=True, dryrun=dryrun)
  except cros_build_lib.CalledProcessError:
    logging.error('Flashing failed.')
    return False

  return True


def _build_read_ssh_cmds(ip, port, path, tmp_file_name, verbose, region):
  """Helper function to build commands for reading images over ssh

  Args:
    ip (string): ip address of DUT.
    port (int): The port to ssh to.
    path (string): path to store the read BIOS image.
    tmp_file_name (string): name of tempfile with copy of testing_rsa
      keys.
    verbose (bool): if True set -v flag in flash command.
    region (str): Region to read.

  Returns:
    scp_cmd ([string]):
    flash_cmd ([string]):
  """
  ssh_parameters = [
      '-o', 'UserKnownHostsFile=/dev/null', '-o', 'StrictHostKeyChecking=no',
      '-o', 'CheckHostIP=no'
  ]
  ssh_port = ['-p', str(port)] if port else []
  scp_port = ['-P', str(port)] if port else []
  remote_path = os.path.join('/tmp', os.path.basename(path))
  hostname = 'root@%s' % ip
  scp_cmd = (['scp', '-i', tmp_file_name] + scp_port + ssh_parameters +
             ['%s:%s' % (hostname, remote_path), path])
  flash_cmd = (['ssh', hostname, '-i', tmp_file_name] + ssh_port +
               ssh_parameters + ['flashrom', '-p', 'host', '-r', remote_path])
  if region:
    flash_cmd += ['-i', region]
  if verbose:
    flash_cmd += ['-V']
  return scp_cmd, flash_cmd


def ssh_read(path, verbose, ip, port, dryrun, region):
  """This function reads AP firmware over ssh.

  Tries to ssh to ip address once. If the ssh connection is successful the
  image is read from the DUT using flashrom, and then is copied back via scp.

  Args:
    path (str): path to the BIOS image to be flashed or read.
    verbose (bool): if True to set -v flag in flash command and
      print other debug info, if False do nothing.
    ip (str): ip address of DUT.
    port (int): The port to ssh to.
    dryrun (bool): Whether to actually execute the commands or just print
      the commands that would have been run.
    region (str): Region to read.

  Returns:
    bool: True on success, False on failure.
  """
  logging.info('Connecting to: %s\n', ip)
  id_filename = '/mnt/host/source/chromite/ssh_keys/testing_rsa'
  tmpfile = tempfile.NamedTemporaryFile()
  shutil.copyfile(id_filename, tmpfile.name)

  scp_cmd, flash_cmd = _build_read_ssh_cmds(ip, port, path, tmpfile.name,
                                            verbose, region)

  logging.info('Reading now, may take several minutes.')
  try:
    cros_build_lib.run(flash_cmd, print_cmd=verbose, check=True, dryrun=dryrun)
  except cros_build_lib.CalledProcessError:
    logging.error('Read failed.')
    return False

  try:
    cros_build_lib.run(scp_cmd, print_cmd=verbose, check=True, dryrun=dryrun)
  except cros_build_lib.CalledProcessError:
    logging.error('Could not copy image from dut.')
    return False

  return True


def servo_run(dut_ctl, dut_cmd_on, dut_cmd_off, flash_cmd, verbose, dryrun):
  """Runs subprocesses for setting dut controls and executing flash_cmd.

  Args:
    dut_ctl (DutControl): The dut_control command runner instance.
    dut_cmd_on ([[str]]): 2d array of dut-control commands
      in the form [['dut-control', 'cmd1', 'cmd2'...],
      ['dut-control', 'cmd3'...]]
      that get executed before the dut_cmd.
    dut_cmd_off ([[str]]): 2d array of dut-control commands
      in the same form that get executed after the dut_cmd.
    flash_cmd ([str]): array containing all arguments for
      the actual command. Run as root user on host.
    verbose (bool): if True then print out the various
      commands before running them.
    dryrun (bool): Whether to actually execute the commands or just print them.

  Returns:
    bool: True if commands were run successfully, otherwise False.
  """
  success = True
  try:
    # Dut on command runs.
    dut_ctl.run_all(dut_cmd_on, verbose=verbose, dryrun=dryrun)

    # Need to wait for SPI chip power to stabilize (for some designs)
    time.sleep(1)

    # Run the flash command.
    cros_build_lib.sudo_run(flash_cmd, print_cmd=verbose, dryrun=dryrun)
  except cros_build_lib.CalledProcessError:
    logging.error('DUT command failed, see output above for more info.')
    success = False
  finally:
    # Run the dut off commands to clean up state if possible.
    try:
      dut_ctl.run_all(dut_cmd_off, verbose=verbose, dryrun=dryrun)
    except cros_build_lib.CalledProcessError:
      logging.error('DUT cmd off failed, see output above for more info.')
      success = False

  return success


def deploy(build_target,
           image,
           device=None,
           flashrom=False,
           fast=False,
           port=None,
           verbose=False,
           dryrun=False,
           flash_contents: Optional[str] = None,
           passthrough_args: Iterable[str] = tuple()):
  """Deploy an AP FW image to a device.

  Args:
    build_target (build_target_lib.BuildTarget): The DUT build target.
    image (str): The image path.
    device (commandline.Device): The device to be used. Temporarily optional.
    flashrom (bool): Whether to use flashrom or futility.
    fast (bool): Whether to do a fast (no verification) flash.
    port (int|None): The servo port.
    verbose (bool): Whether to use verbose output for flash commands.
    dryrun (bool): Whether to actually execute the deployment or just print the
      operations that would have been performed.
    flash_contents: Path to the file that contains the existing contents.
    passthrough_args: List of additional options passed to flashrom or futility.
  """
  ip = None
  if device:
    port = device.port
    if device.scheme == commandline.DEVICE_SCHEME_SSH:
      ip = device.hostname
      port = port or device.port
  else:
    ip = os.getenv('IP')

  module = ap_firmware.get_config_module(build_target.name)

  if ip:
    _deploy_ssh(image, module, flashrom, fast, verbose, ip, port, dryrun,
                passthrough_args)
  else:
    _deploy_servo(image, module, flashrom, fast, verbose, port, dryrun,
                  flash_contents, passthrough_args)


def _deploy_servo(image,
                  module,
                  flashrom,
                  fast,
                  verbose,
                  port,
                  dryrun,
                  flash_contents: Optional[str] = None,
                  passthrough_args: Iterable[str] = tuple()):
  """Deploy to a servo connection.

  Args:
    image (str): Path to the image to flash.
    module: The config module.
    flashrom (bool): Whether to use flashrom or futility.
    fast (bool): Whether to do a fast (no verification) flash.
    verbose (bool): Whether to use verbose output for flash commands.
    port (int|None): The servo port.
    dryrun (bool): Whether to actually execute the deployment or just print the
      operations that would have been performed.
    flash_contents: Path to the file that contains the existing contents.
    passthrough_args: Additional options passed to flashrom or futility.
  """
  logging.notice('Attempting to flash via servo.')
  dut_ctl = servo_lib.DutControl(port)
  servo = servo_lib.get(dut_ctl)
  # TODO(b/143240576): Fast mode is sometimes necessary to flash successfully.
  if (not fast and hasattr(module, 'is_fast_required') and
      module.is_fast_required(not flashrom, servo)):
    logging.notice('There is a known error with the board and servo type being '
                   'used, enabling --fast to bypass this problem.')
    fast = True
  if (hasattr(module, 'DEPLOY_SERVO_FORCE_FLASHROM') and
      module.DEPLOY_SERVO_FORCE_FLASHROM):
    # Futility needs VBoot to flash so boards without functioning VBoot
    # can set this attribute to True to force the use of flashrom.
    flashrom = True
  ap_config = module.get_config(servo)
  flashrom_cmd = ['flashrom', '-p', ap_config.programmer, '-w', image]
  futility_cmd = [
      'futility',
      'update',
      '-p',
      ap_config.programmer,
      '-i',
      image,
  ]
  futility_cmd += ['--force', '--wp=0']
  if fast:
    futility_cmd += ['--fast']
    flashrom_cmd += ['-n']
  if verbose:
    flashrom_cmd += ['-V']
    futility_cmd += ['-v']
  if flash_contents is not None:
    flashrom_cmd += ['--flash-contents', flash_contents]
  if passthrough_args:
    flashrom_cmd += passthrough_args
    futility_cmd += passthrough_args
  flash_cmd = flashrom_cmd if flashrom else futility_cmd
  if servo_run(dut_ctl, ap_config.dut_control_on, ap_config.dut_control_off,
               flash_cmd, verbose, dryrun):
    logging.notice('SUCCESS. Exiting flash_ap.')
  else:
    logging.error('Unable to complete flash, verify servo connection '
                  'is correct and servod is running in the background.')


def _deploy_ssh(image, module, flashrom, fast, verbose, ip, port, dryrun,
                passthrough_args: Iterable[str] = tuple()):
  """Deploy to a servo connection.

  Args:
    image (str): Path to the image to flash.
    module: The config module.
    flashrom (bool): Whether to use flashrom or futility.
    fast (bool): Whether to do a fast (no verification) flash.
    verbose (bool): Whether to use verbose output for flash commands.
    ip (str): The DUT ip address.
    port (int): The port to ssh to.
    dryrun (bool): Whether to execute the deployment or just print the
      commands that would have been executed.
    passthrough_args: List of additional options passed to flashrom or futility.
  """
  logging.notice('Attempting to flash via ssh.')
  # TODO(b/143241417): Can't use flashrom over ssh on wilco.
  if (hasattr(module, 'DEPLOY_SSH_FORCE_FUTILITY') and
      module.DEPLOY_SSH_FORCE_FUTILITY and flashrom):
    logging.warning('Flashing with flashrom over ssh on this device fails '
                    'consistently, flashing with futility instead.')
    flashrom = False
  if _ssh_flash(not flashrom, image, verbose, ip, port, fast, dryrun,
                passthrough_args):
    logging.notice('ssh flash successful. Exiting flash_ap')
  else:
    raise DeployFailed('ssh failed, try using a servo connection instead.')
