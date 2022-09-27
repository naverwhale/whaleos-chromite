# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""AP firmware utilities."""

import collections
import importlib
import logging
import os
from typing import Iterable, Optional

from chromite.lib import build_target_lib
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import workon_helper
from chromite.lib.firmware import flash_ap
from chromite.service import sysroot

_BUILD_TARGET_CONFIG_MODULE = 'chromite.lib.firmware.ap_firmware_config.%s'
_CONFIG_BUILD_WORKON_PACKAGES = 'BUILD_WORKON_PACKAGES'
_CONFIG_BUILD_PACKAGES = 'BUILD_PACKAGES'
_GENERIC_CONFIG_NAME = 'generic'

# The build configs. The workon and build fields both contain tuples of
# packages.
BuildConfig = collections.namedtuple('BuildConfig', ('workon', 'build'))

# The set of commands for a servo deploy.
ServoDeployCommands = collections.namedtuple('ServoDeployCommands',
                                             ('dut_on', 'dut_off', 'flash'))


class Error(Exception):
  """Base error class for the module."""


class BuildError(Error):
  """Failure in the build command."""


class BuildTargetNotConfiguredError(Error):
  """Thrown when a config module does not exist for the build target."""


class DeployError(Error):
  """Failure in the deploy command."""


class InvalidConfigError(Error):
  """The config does not contain the required information for the operation."""


class CleanError(Error):
  """Failure in the clean command."""


def build(build_target, fw_name=None, dry_run=False):
  """Build the AP Firmware.

  Args:
    build_target (BuildTarget): The build target (board) being built.
    fw_name (str|None): Optionally set the FW_NAME envvar to allow building
      the firmware for only a specific variant.
    dry_run (bool): Whether to perform a dry run.
  """
  logging.notice('Building AP Firmware.')

  if not os.path.exists(build_target.root):
    logging.warning('Sysroot for target %s is not available. Attempting '
                    'to configure sysroot via default setup_board command.',
                    build_target.name)
    try:
      sysroot.SetupBoard(build_target)
    except (portage_util.MissingOverlayError, sysroot.Error):
      cros_build_lib.Die('setup_board with default specifications failed. '
                         "Please configure the board's sysroot separately.")

  config = _get_build_config(build_target)

  with workon_helper.WorkonScope(build_target, config.workon):
    extra_env = {'FW_NAME': fw_name} if fw_name else None
    # Run the emerge command to build the packages. Don't raise an exception
    # here if it fails so we can cros workon stop afterwords.
    logging.info('Building the AP firmware packages.')
    # Print command with --debug.
    print_cmd = logging.getLogger(__name__).getEffectiveLevel() == logging.DEBUG
    default_build_flags = [
        '--deep', '--update', '--newuse', '--newrepo', '--jobs', '--verbose'
    ]
    result = cros_build_lib.run(
        [build_target.get_command('emerge')] + default_build_flags +
        list(config.build),
        print_cmd=print_cmd,
        check=False,
        debug_level=logging.DEBUG,
        dryrun=dry_run,
        extra_env=extra_env)

  if result.returncode:
    # Now raise the emerge failure since we're done cleaning up.
    raise BuildError('The emerge command failed. Run with --verbose or --debug '
                     'to see the emerge output for details.')

  logging.notice('AP firmware image for device %s was built successfully '
                 'and is available at %s.',
                 build_target.name, build_target.full_path())


def deploy(build_target,
           image,
           device,
           flashrom=False,
           fast=False,
           verbose=False,
           dryrun=False,
           flash_contents: Optional[str] = None,
           passthrough_args: Iterable[str] = tuple()):
  """Deploy a firmware image to a device.

  Args:
    build_target (build_target_lib.BuildTarget): The build target.
    image (str): The path to the image to flash.
    device (commandline.Device): The DUT being flashed.
    flashrom (bool): Whether to use flashrom or futility.
    fast (bool): Perform a faster flash that isn't validated.
    verbose (bool): Whether to enable verbose output of the flash commands.
    dryrun (bool): Whether to actually execute the deployment or just print the
      operations that would have been performed.
    flash_contents: Path to the file that contains the existing contents.
    passthrough_args: List of additional options passed to flashrom or futility.
  """
  try:
    flash_ap.deploy(
        build_target=build_target,
        image=image,
        device=device,
        flashrom=flashrom,
        fast=fast,
        verbose=verbose,
        dryrun=dryrun,
        flash_contents=flash_contents,
        passthrough_args=passthrough_args)
  except flash_ap.Error as e:
    # Reraise as a DeployError for future compatibility.
    raise DeployError(str(e))


class DeployConfig(object):
  """Deploy configuration wrapper."""

  FORCE_FLASHROM = 'flashrom'
  FORCE_FUTILITY = 'futility'

  def __init__(self,
               get_config,
               force_fast=None,
               servo_force_command=None,
               ssh_force_command=None):
    """DeployConfig init.

    Args:
      get_config: A function that takes a servo and returns a
        servo_lib.FirmwareConfig with settings to flash a servo
        for a particular build target.
      force_fast: A function that takes two arguments; a bool to indicate if it
        is for a futility (True) or flashrom (False) command.
      servo_force_command: One of the FORCE_{command} constants to force use of
        a specific command, or None to not force.
      ssh_force_command: One of the FORCE_{command} constants to force use of
        a specific command, or None to not force.
    """
    self._get_config = get_config
    self._force_fast = force_fast
    self._servo_force_command = servo_force_command
    self._ssh_force_command = ssh_force_command

  @property
  def servo_force_flashrom(self):
    return self._servo_force_command == self.FORCE_FLASHROM

  @property
  def servo_force_futility(self):
    return self._servo_force_command == self.FORCE_FUTILITY

  @property
  def ssh_force_flashrom(self):
    return self._ssh_force_command == self.FORCE_FLASHROM

  @property
  def ssh_force_futility(self):
    return self._ssh_force_command == self.FORCE_FUTILITY

  def force_fast(self, servo, flashrom):
    """Check if the fast flash option is required.

    Some configurations fail flash verification, which can be skipped with
    a fast flash.

    Args:
      servo (servo_lib.Servo): The servo connected to the DUT.
      flashrom (bool): Whether flashrom is being used instead of futility.

    Returns:
      bool: True if it requires a fast flash, False otherwise.
    """
    if not self._force_fast:
      # No function defined in the module, so no required cases.
      return False

    return self._force_fast(not flashrom, servo)

  def get_servo_commands(self,
                         servo,
                         image_path,
                         flashrom=False,
                         fast=False,
                         verbose=False):
    """Get the servo flash commands from the build target config."""
    ap_conf = self._get_config(servo)

    # Make any forced changes to the given options.
    if not flashrom and self.servo_force_flashrom:
      logging.notice('Forcing flashrom flash.')
      flashrom = True
    elif flashrom and self.servo_force_futility:
      logging.notice('Forcing futility flash.')
      flashrom = False

    if not fast and self.force_fast(servo, flashrom):
      logging.notice('Forcing fast flash.')
      fast = True

    # Make common command additions here to simplify the config modules.
    flashrom_cmd = ['flashrom', '-p', ap_conf.programmer, '-w', image_path]
    futility_cmd = [
        'futility',
        'update',
        '-p',
        ap_conf.programmer,
        '-i',
        image_path,
    ]
    futility_cmd += ['--force', '--wp=0']

    if fast:
      flashrom_cmd += ['-n']
      futility_cmd += ['--fast']
    if verbose:
      flashrom_cmd += ['-V']
      futility_cmd += ['-v']

    return ServoDeployCommands(
        dut_on=ap_conf.dut_control_on,
        dut_off=ap_conf.dut_control_off,
        flash=flashrom_cmd if flashrom else futility_cmd)


def _get_build_config(build_target):
  """Get the relevant build config for |build_target|."""
  module = get_config_module(build_target.name)
  workon_pkgs = getattr(module, _CONFIG_BUILD_WORKON_PACKAGES, None)
  build_pkgs = getattr(module, _CONFIG_BUILD_PACKAGES, None)

  if not build_pkgs:
    build_pkgs = ('chromeos-bootimage',)

  return BuildConfig(workon=workon_pkgs, build=build_pkgs)


def _get_deploy_config(build_target):
  """Get the relevant deploy config for |build_target|."""
  module = get_config_module(build_target.name)

  # Get the force fast function if available.
  force_fast = getattr(module, 'is_fast_required', None)

  # Check the force servo command options.
  servo_force = None
  if getattr(module, 'DEPLOY_SERVO_FORCE_FLASHROM', False):
    servo_force = DeployConfig.FORCE_FLASHROM
  elif getattr(module, 'DEPLOY_SERVO_FORCE_FUTILITY', False):
    servo_force = DeployConfig.FORCE_FUTILITY

  # Check the force SSH command options.
  ssh_force = None
  if getattr(module, 'DEPLOY_SSH_FORCE_FLASHROM', False):
    ssh_force = DeployConfig.FORCE_FLASHROM
  elif getattr(module, 'DEPLOY_SSH_FORCE_FUTILITY', False):
    ssh_force = DeployConfig.FORCE_FUTILITY

  return DeployConfig(
      module.get_config,
      force_fast=force_fast,
      servo_force_command=servo_force,
      ssh_force_command=ssh_force)


def get_config_module(build_target_name, disable_fallback=False):
  """Return configuration module for a given build target.

  Args:
    build_target_name: Name of the build target, e.g. 'dedede'.
    disable_fallback: Disables falling back to generic config if the config for
                      build_target_name is not found.

  Returns:
    module: Python configuration module for a given build target.
  """
  name = _BUILD_TARGET_CONFIG_MODULE % build_target_name
  try:
    return importlib.import_module(name)
  except ImportError:
    name_path = name.replace('.', '/') + '.py'
    if disable_fallback:
      raise BuildTargetNotConfiguredError(
          f'Could not find a config module for {build_target_name}. '
          f'Fill in the config in {name_path}.')
  # Failling back to generic config.
  logging.notice(
      'Did not find a dedicated config module for %s at %s. '
      'Using default config.', build_target_name, name_path)
  name = _BUILD_TARGET_CONFIG_MODULE % _GENERIC_CONFIG_NAME
  try:
    return importlib.import_module(name)
  except ImportError:
    name_path = name.replace('.', '/') + '.py'
    if disable_fallback:
      raise BuildTargetNotConfiguredError(
          f'Could not find a generic config module at {name_path}. '
          'Is your checkout broken?')


def clean(build_target: build_target_lib.BuildTarget, dry_run=False):
  """Cleans packages and dependencies related to a specified target.

  After running the command, the user's environment should be able to
  successfully build packages for a target board.

  Args:
    build_target: Target board to be cleaned
    dry_run: Indicates that packages and system files should not be modified
  """
  pkgs = []
  try:
    qfile_pkgs = cros_build_lib.run([build_target.get_command('qfile'),
                                     '/firmware'], capture_output=True,
                                    check=False, dryrun=dry_run).stdout
    pkgs = [l.split()[0] for l in qfile_pkgs.decode().splitlines()]
  except cros_build_lib.RunCommandError as e:
    raise CleanError('qfile for target board %s is not present; board may '
                     'not have been set up.' % build_target.name)

  try:
    config = _get_build_config(build_target)
    pkgs = set(pkgs).union(config.build)
  except InvalidConfigError:
    pass
  pkgs = sorted(set(pkgs).union(['coreboot-private-files',
                                 'chromeos-config-bsp']))

  err = []
  try:
    cros_build_lib.run([build_target.get_command('emerge'), '--rage-clean',
                        *pkgs], capture_output=True, dryrun=dry_run)
  except cros_build_lib.RunCommandError as e:
    err.append(e)

  try:
    if dry_run:
      logging.notice('rm -rf -- /build/%s/firmware/*', build_target.name)
    else:
      osutils.RmDir('/build/%s/firmware/*' % build_target.name, sudo=True,
                    ignore_missing=True)
  except (EnvironmentError, cros_build_lib.RunCommandError) as e:
    err.append(e)

  if err:
    logging.warning('All processes for %s have completed, but some were '
                    'completed with errors.', build_target.name)
    for e in err:
      logging.error(e)
    raise CleanError("`cros ap clean -b %s' did not complete successfully."
                     % build_target.name)

  logging.notice('AP firmware image for device %s was successfully cleaned.'
                 '\nThe following packages were unmerged: %s'
                 '\nThe following build target directory was removed: '
                 '/build/%s/firmware', build_target.name, ' '.join(pkgs),
                 build_target.name)
