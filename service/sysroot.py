# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Sysroot service."""

import logging
import glob
import multiprocessing
import os
import shutil
import tempfile
from typing import List, NamedTuple
import urllib

from chromite.lib import build_target_lib
from chromite.lib import cache
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import sysroot_lib
from chromite.lib import workon_helper
from chromite.utils import metrics


class Error(Exception):
  """Base error class for the module."""


class NoFilesError(Error):
  """When there are no files to archive."""


class InvalidArgumentsError(Error):
  """Invalid arguments."""


class NotInChrootError(Error):
  """When SetupBoard is run outside of the chroot."""


class UpdateChrootError(Error):
  """Error occurred when running update chroot."""


class SetupBoardRunConfig(object):
  """Value object for full setup board run configurations."""

  def __init__(self, set_default=False, force=False, usepkg=True, jobs=None,
               regen_configs=False, quiet=False, update_toolchain=True,
               upgrade_chroot=True, init_board_pkgs=True, local_build=False,
               toolchain_changed=False, package_indexes=None,
               expanded_binhost_inheritance: bool = False):
    """Initialize method.

    Args:
      set_default (bool): Whether to set the passed board as the default.
      force (bool): Force a new sysroot creation when it already exists.
      usepkg (bool): Whether to use binary packages to bootstrap.
      jobs (int): Max number of simultaneous packages to build.
      regen_configs (bool): Whether to only regen the configs.
      quiet (bool): Whether to print notification when sysroot exists.
      update_toolchain (bool): Update the toolchain?
      upgrade_chroot (bool): Upgrade the chroot before building?
      init_board_pkgs (bool): Emerging packages to sysroot?
      local_build (bool): Bootstrap only from local packages?
      toolchain_changed (bool): Has a toolchain change occurred? Implies
        'force'.
      package_indexes (list[PackageIndexInfo]): List of information about
        available prebuilts, youngest first, or None.
      expanded_binhost_inheritance: Allow expanded binhost inheritance.
    """
    self.set_default = set_default
    self.force = force or toolchain_changed
    self.usepkg = usepkg
    self.jobs = jobs
    self.regen_configs = regen_configs
    self.quiet = quiet
    self.update_toolchain = update_toolchain
    self.update_chroot = upgrade_chroot
    self.init_board_pkgs = init_board_pkgs
    self.local_build = local_build
    self.package_indexes = package_indexes or []
    self.expanded_binhost_inheritance = expanded_binhost_inheritance

  def GetUpdateChrootArgs(self):
    """Create a list containing the relevant update_chroot arguments.

    Returns:
      list[str]
    """
    args = []
    if self.usepkg:
      args += ['--usepkg']
    else:
      args += ['--nousepkg']

    if self.jobs:
      args += ['--jobs', str(self.jobs)]

    if not self.update_toolchain:
      args += ['--skip_toolchain_update']

    return args


class BuildPackagesRunConfig(object):
  """Value object to hold build packages run configs."""

  def __init__(self,
               usepkg=True,
               install_debug_symbols=False,
               packages=None,
               use_flags=None,
               use_goma=False,
               incremental_build=True,
               package_indexes=None,
               expanded_binhosts: bool = False,
               setup_board: bool = True,
               dryrun: bool = False):
    """Init method.

    Args:
      usepkg (bool): Whether to use binpkgs or build from source. False
        currently triggers a local build, which will enable local reuse.
      install_debug_symbols (bool): Whether to include the debug symbols for all
        packages.
      packages (list[str]|None): The list of packages to install, by default
        install all packages for the target.
      use_flags (list[str]|None): A list of use flags to set.
      use_goma (bool): Whether to enable goma.
      incremental_build (bool): Whether to treat the build as an incremental
        build or a fresh build. Always treating it as an incremental build is
        safe, but certain operations can be faster when we know we are doing
        a fresh build.
      package_indexes (list[PackageIndexInfo]): List of information about
        available prebuilts, youngest first, or None.
      expanded_binhosts: Whether to enable/disable the expanded binhost
        inheritance feature for the sysroot.
      setup_board: Whether to run setup_board in build_packages.
      dryrun: Whether to do a dryrun and not actually build any packages.
    """
    self.usepkg = usepkg
    self.install_debug_symbols = install_debug_symbols
    self.packages = packages
    self.use_flags = use_flags
    self.use_goma = use_goma
    self.is_incremental = incremental_build
    self.package_indexes = package_indexes or []
    self.expanded_binhosts = expanded_binhosts
    self.setup_board = setup_board
    self.dryrun = dryrun

  def GetBuildPackagesArgs(self):
    """Get the build_packages script arguments."""
    # Defaults for the builder.
    # TODO(saklein): Parametrize/rework the defaults when build_packages is
    #   ported to chromite.
    args = [
        '--accept_licenses',
        '@CHROMEOS',
        '--skip_chroot_upgrade',
        '--nouse_any_chrome',
    ]

    if not self.usepkg:
      args.append('--nousepkg')

    if self.install_debug_symbols:
      args.append('--withdebugsymbols')

    if self.use_goma:
      args.append('--run_goma')

    if not self.is_incremental:
      args.append('--nowithrevdeps')

    if self.expanded_binhosts:
      args.append('--expandedbinhosts')
    else:
      args.append('--noexpandedbinhosts')

    if not self.setup_board:
      args.append('--skip_setup_board')

    if self.packages:
      args.extend(self.packages)

    if self.dryrun:
      args.append('--pretend')

    return args

  def HasUseFlags(self):
    """Check if we have use flags."""
    return bool(self.use_flags)

  def GetUseFlags(self):
    """Get the use flags as a single string."""
    use_flags = self.use_flags
    if use_flags:
      # We have use flags to set, but we need to append them to any existing
      # use flags rather than overwrite them completely.
      # TODO(saklein) Add config for whether to extend or overwrite?
      existing_flags = os.environ.get('USE', '').split()
      existing_flags.extend(use_flags)
      use_flags = existing_flags

      return ' '.join(use_flags)

    return None

  def GetEnv(self):
    """Get the env from this config."""
    env = {}
    if self.HasUseFlags():
      env['USE'] = self.GetUseFlags()

    if self.use_goma:
      env['USE_GOMA'] = 'true'

    if self.package_indexes:
      env['PORTAGE_BINHOST'] = ' '.join(
          x.location for x in reversed(self.package_indexes))

    return env


def SetupBoard(target, accept_licenses=None, run_configs=None):
  """Run the full process to setup a board's sysroot.

  This is the entry point to run the setup_board script.

  Args:
    target (build_target_lib.BuildTarget): The build target configuration.
    accept_licenses (str|None): The additional licenses to accept.
    run_configs (SetupBoardRunConfig): The run configs.

  Raises:
    sysroot_lib.ToolchainInstallError when the toolchain fails to install.
  """
  if not cros_build_lib.IsInsideChroot():
    # TODO(saklein) switch to build out command and run inside chroot.
    raise NotInChrootError('SetupBoard must be run from inside the chroot')

  # Make sure we have valid run configs setup.
  run_configs = run_configs or SetupBoardRunConfig()

  sysroot = Create(target, run_configs, accept_licenses)

  if run_configs.regen_configs:
    # We're now done if we're only regenerating the configs.
    return

  InstallToolchain(target, sysroot, run_configs)


def Create(target, run_configs, accept_licenses):
  """Create a sysroot.

  This entry point is the subset of the full setup process that does the
  creation and configuration of a sysroot, including installing portage.

  Args:
    target (build_target.BuildTarget): The build target being installed in the
      sysroot being created.
    run_configs (SetupBoardRunConfig): The run configs.
    accept_licenses (str|None): The additional licenses to accept.
  """
  cros_build_lib.AssertInsideChroot()

  sysroot = sysroot_lib.Sysroot(target.root)

  if sysroot.Exists() and not run_configs.force and not run_configs.quiet:
    logging.warning('Board output directory already exists: %s\n'
                    'Use --force to clobber the board root and start again.',
                    sysroot.path)

  # Override regen_configs setting to force full setup run if the sysroot does
  # not exist.
  run_configs.regen_configs = run_configs.regen_configs and sysroot.Exists()

  # Make sure the chroot is fully up to date before we start unless the
  # chroot update is explicitly disabled.
  if run_configs.update_chroot:
    logging.info('Updating chroot.')
    update_chroot = [os.path.join(constants.CROSUTILS_DIR, 'update_chroot'),
                     '--toolchain_boards', target.name]
    update_chroot += run_configs.GetUpdateChrootArgs()
    try:
      cros_build_lib.run(update_chroot)
    except cros_build_lib.RunCommandError:
      raise UpdateChrootError('Error occurred while updating the chroot. '
                              'See the logs for more information.')

  # Delete old sysroot to force a fresh start if requested.
  if sysroot.Exists() and run_configs.force:
    sysroot.Delete(background=True)

  # Step 1: Create folders.
  # Dependencies: None.
  # Create the skeleton.
  logging.info('Creating sysroot directories.')
  _CreateSysrootSkeleton(sysroot)

  # Step 2: Standalone configurations.
  # Dependencies: Folders exist.
  # Install main, board setup, and user make.conf files.
  logging.info('Installing configurations into sysroot.')
  _InstallConfigs(sysroot, target)

  # Step 3: Portage configurations.
  # Dependencies: make.conf.board_setup.
  # Create the command wrappers, choose profile, and make.conf.board.
  # Refresh the workon symlinks to compensate for crbug.com/679831.
  logging.info('Setting up portage in the sysroot.')
  _InstallPortageConfigs(
      sysroot,
      target,
      accept_licenses,
      run_configs.local_build,
      package_indexes=run_configs.package_indexes,
      expanded_binhost_inheritance=run_configs.expanded_binhost_inheritance)

  # Developer Experience Step: Set default board (if requested) to allow
  # running later commands without needing to pass the --board argument.
  if run_configs.set_default:
    cros_build_lib.SetDefaultBoard(target.name)

  return sysroot


def GenerateArchive(output_dir, build_target_name, pkg_list):
  """Generate a sysroot tarball for informational builders.

  Args:
    output_dir (string): Directory to contain the created the sysroot.
    build_target_name (string): The build target for the sysroot being created.
    pkg_list (list[string]|None): List of 'category/package' package strings.

  Returns:
    Path to the sysroot tar file.
  """
  cmd = ['cros_generate_sysroot',
         '--out-file', constants.TARGET_SYSROOT_TAR,
         '--out-dir', output_dir,
         '--board', build_target_name,
         '--package', ' '.join(pkg_list)]
  cros_build_lib.run(cmd, cwd=constants.SOURCE_ROOT)
  return os.path.join(output_dir, constants.TARGET_SYSROOT_TAR)


def CreateSimpleChromeSysroot(chroot, _sysroot_class, build_target, output_dir):
  """Create a sysroot for SimpleChrome to use.

  Args:
    chroot: The chroot class used for these artifacts.
    sysroot_class: The sysroot class used for these artifacts.
    build_target: The build target used for these artifacts.
    output_dir: The path to write artifacts to.

  Returns:
    Path to the sysroot tar file.
  """
  cmd = ['cros_generate_sysroot', '--out-dir', '/tmp', '--board',
         build_target.name, '--deps-only', '--package', constants.CHROME_CP]
  cros_build_lib.run(cmd, cwd=constants.SOURCE_ROOT, enter_chroot=True,
                     chroot_args=chroot.get_enter_args(), extra_env=chroot.env)

  # Move the artifact out of the chroot.
  sysroot_tar_path = os.path.join(
      chroot.path, os.path.join('tmp', constants.CHROME_SYSROOT_TAR))
  shutil.copy(sysroot_tar_path, output_dir)
  return os.path.join(output_dir, constants.CHROME_SYSROOT_TAR)


def CreateChromeEbuildEnv(chroot, sysroot_class, _build_target, output_dir):
  """Generate Chrome ebuild environment.

  Args:
    chroot: The chroot class used for these artifacts.
    sysroot_class (sysroot_lib.Sysroot): The sysroot where the original
      environment archive can be found.
    output_dir (str): Where the result should be stored.

  Returns:
    str: The path to the archive, or None.
  """
  pkg_dir = chroot.full_path(sysroot_class.path, portage_util.VDB_PATH)
  files = glob.glob(os.path.join(pkg_dir, constants.CHROME_CP) + '-*')
  if not files:
    logging.warning('No package found for %s', constants.CHROME_CP)
    return None

  if len(files) > 1:
    logging.warning('Expected one package for %s, found %d',
                    constants.CHROME_CP, len(files))

  chrome_dir = sorted(files)[-1]
  env_bzip = os.path.join(chrome_dir, 'environment.bz2')
  result_path = os.path.join(output_dir, constants.CHROME_ENV_TAR)
  with osutils.TempDir() as tempdir:
    # Convert from bzip2 to tar format.
    bzip2 = cros_build_lib.FindCompressor(cros_build_lib.COMP_BZIP2)
    tempdir_tar_path = os.path.join(tempdir, constants.CHROME_ENV_FILE)
    cros_build_lib.run([bzip2, '-d', env_bzip, '-c'],
                       stdout=tempdir_tar_path)

    cros_build_lib.CreateTarball(result_path, tempdir)

  return result_path


def InstallToolchain(target, sysroot, run_configs):
  """Update the toolchain to a sysroot.

  This entry point just installs the target's toolchain into the sysroot.
  Everything else must have been done already for this to be successful.

  Args:
    target (build_target_lib.BuildTarget): The target whose toolchain is being
      installed.
    sysroot (sysroot_lib.Sysroot): The sysroot where the toolchain is being
      installed.
    run_configs (SetupBoardRunConfig): The run configs.
  """
  cros_build_lib.AssertInsideChroot()
  if not sysroot.Exists():
    # Sanity check before we try installing anything.
    raise ValueError('The sysroot must exist, run Create first.')

  # Step 4: Install toolchain and packages.
  # Dependencies: Portage configs and wrappers have been installed.
  if run_configs.init_board_pkgs:
    logging.info('Updating toolchain.')
    # Use the local packages if we're doing a local only build or usepkg is set.
    local_init = run_configs.usepkg or run_configs.local_build
    _InstallToolchain(sysroot, target, local_init=local_init)


def BuildPackages(target, sysroot, run_configs):
  """Build and install packages into a sysroot.

  Args:
    target (build_target_lib.BuildTarget): The target whose packages are being
      installed.
    sysroot (sysroot_lib.Sysroot): The sysroot where the packages are being
      installed.
    run_configs (BuildPackagesRunConfig): The run configs.
  """
  cros_build_lib.AssertInsideChroot()

  cmd = [os.path.join(constants.CROSUTILS_DIR, 'build_packages'),
         '--board', target.name, '--board_root', sysroot.path]
  cmd += run_configs.GetBuildPackagesArgs()

  extra_env = run_configs.GetEnv()
  extra_env['USE_NEW_PARALLEL_EMERGE'] = '1'
  with osutils.TempDir() as tempdir:
    extra_env[constants.CROS_METRICS_DIR_ENVVAR] = tempdir

    try:
      # REVIEW: discuss which dimensions to flatten into the metric
      # name other than target.name...
      with metrics.timer('service.sysroot.BuildPackages.RunCommand'):
        cros_build_lib.run(cmd, extra_env=extra_env)
    except cros_build_lib.RunCommandError as e:
      failed_pkgs = portage_util.ParseDieHookStatusFile(tempdir)
      raise sysroot_lib.PackageInstallError(
          str(e), e.result, exception=e, packages=failed_pkgs)


def _CreateSysrootSkeleton(sysroot):
  """Create the sysroot skeleton.

  Dependencies: None.
  Creates the sysroot directory structure and installs the portage hooks.

  Args:
    sysroot (sysroot_lib.Sysroot): The sysroot.
  """
  sysroot.CreateSkeleton()


def _InstallConfigs(sysroot, target):
  """Install standalone configuration files into the sysroot.

  Dependencies: The sysroot exists (i.e. CreateSysrootSkeleton).
  Installs the main, board setup, and user make.conf files.

  Args:
    sysroot (sysroot_lib.Sysroot): The sysroot.
    target (build_target.BuildTarget): The build target being setup in
      the sysroot.
  """
  sysroot.InstallMakeConf()
  sysroot.InstallMakeConfBoardSetup(target.name)
  sysroot.InstallMakeConfUser()


def _InstallPortageConfigs(sysroot,
                           target,
                           accept_licenses,
                           local_build,
                           package_indexes=None,
                           expanded_binhost_inheritance: bool = False):
  """Install portage wrappers and configurations.

  Dependencies: make.conf.board_setup (InstallConfigs).
  Create the command wrappers, choose profile, and generate make.conf.board.
  Refresh the workon symlinks to compensate for crbug.com/679831.

  Args:
    sysroot (sysroot_lib.Sysroot): The sysroot.
    target (build_target.BuildTarget): The build target being installed
      in the sysroot.
    accept_licenses (str): Additional accepted licenses as a string.
    local_build (bool): If the build is a local only build.
    package_indexes (list[PackageIndexInfo]): List of information about
      available prebuilts, youngest first, or None.
    expanded_binhost_inheritance: Whether to allow expanded binhost inheritance.
  """
  sysroot.CreateAllWrappers(friendly_name=target.name)
  _ChooseProfile(target, sysroot)
  _RefreshWorkonSymlinks(target.name, sysroot)
  # Must be done after the profile is chosen or binhosts may be incomplete.
  sysroot.InstallMakeConfBoard(
      accepted_licenses=accept_licenses,
      local_only=local_build,
      package_indexes=package_indexes,
      expanded_binhost_inheritance=expanded_binhost_inheritance)


def _InstallToolchain(sysroot, target, local_init=True):
  """Install toolchain and packages.

  Dependencies: Portage configs and wrappers have been installed
    (InstallPortageConfigs).
  Install the toolchain and the implicit dependencies.

  Args:
    sysroot (sysroot_lib.Sysroot): The sysroot to install to.
    target (build_target.BuildTarget): The build target whose toolchain is
      being installed.
    local_init (bool): Whether to use local packages to bootstrap implicit
      dependencies.
  """
  sysroot.UpdateToolchain(target.name, local_init=local_init)


def _RefreshWorkonSymlinks(target, sysroot):
  """Force refresh the workon symlinks.

  Create an instance of the WorkonHelper, which will recreate all symlinks
  to masked/unmasked packages currently worked on in case the sysroot was
  recreated (crbug.com/679831).

  This was done with a call to `cros_workon list` in the bash version of
  the script, but all we actually need is for the WorkonHelper to be
  instantiated since it refreshes the symlinks in its __init__.

  Args:
    target (str): The build target name.
    sysroot (sysroot_lib.Sysroot): The board's sysroot.
  """
  workon_helper.WorkonHelper(sysroot.path, friendly_name=target)


def _ChooseProfile(target, sysroot):
  """Helper function to execute cros_choose_profile.

  TODO(saklein) Refactor cros_choose_profile to avoid needing the run
  call here, and by extension this method all together.

  Args:
    target (build_target_lib.BuildTarget): The build target whose profile is
      being chosen.
    sysroot (sysroot_lib.Sysroot): The sysroot for which the profile is
      being chosen.
  """
  choose_profile = ['cros_choose_profile', '--board', target.name,
                    '--board-root', sysroot.path]
  if target.profile:
    # Chooses base by default, only override when we have a passed param.
    choose_profile += ['--profile', target.profile]
  try:
    cros_build_lib.run(choose_profile, print_cmd=False)
  except cros_build_lib.RunCommandError as e:
    logging.error('Selecting profile failed, removing incomplete board '
                  'directory!')
    sysroot.Delete()
    raise e


def BundleDebugSymbols(chroot: chroot_lib.Chroot,
                       sysroot_class: sysroot_lib.Sysroot,
                       _build_target: build_target_lib.BuildTarget,
                       output_dir: str) -> str:
  """Bundle debug symbols into a tarball for importing into GCE.

  Bundle the debug symbols found in the sysroot into a .tgz. This assumes
  these files are present.

  Args:
    chroot: The chroot class used for these artifacts.
    sysroot_class: The sysroot class used for these artifacts.
    build_target: The build target used for these artifacts.
    output_dir: The path to write artifacts to.

  Returns:
    A string path to the output debug.tgz artifact, or None.
  """
  base_path = chroot.full_path(sysroot_class.path)
  debug_dir = os.path.join(base_path, 'usr/lib/debug')

  if not os.path.isdir(debug_dir):
    logging.error('No debug directory found at %s.', debug_dir)
    return None

  # Create tarball from destination_tmp, then copy it...
  tarball_path = os.path.join(output_dir, constants.DEBUG_SYMBOLS_TAR)
  exclude_breakpad_tar_arg = ('--exclude=%s' %
                              os.path.join(debug_dir, 'breakpad'))
  result = None
  try:
    result = cros_build_lib.CreateTarball(
        tarball_path,
        debug_dir,
        compression=cros_build_lib.COMP_GZIP,
        sudo=True,
        extra_args=[exclude_breakpad_tar_arg])
  except cros_build_lib.TarballError:
    pass
  if not result or result.returncode:
    # We don't abort here, because the tar may still be somewhat intact.
    err = result.return_code if result else 'TarballError'
    logging.error('Error (%s) when creating tarball %s from %s', err,
                  tarball_path, debug_dir)
  if os.path.exists(tarball_path):
    return tarball_path
  else:
    return None


def BundleBreakpadSymbols(chroot: chroot_lib.Chroot,
                          sysroot_class: sysroot_lib.Sysroot,
                          build_target: build_target_lib.BuildTarget,
                          output_dir: str) -> str:
  """Bundle breakpad debug symbols into a tarball for importing into GCE.

  Call the GenerateBreakpadSymbols function and archive this into a tar.gz.

  Args:
    chroot: The chroot class used for these artifacts.
    sysroot_class: The sysroot class used for these artifacts.
    build_target: The build target used for these artifacts.
    output_dir: The path to write artifacts to.

  Returns:
    A string path to the output debug_breakpad.tar.gz artifact, or None.
  """
  base_path = chroot.full_path(sysroot_class.path)

  result = GenerateBreakpadSymbols(chroot, build_target, debug=True)

  # Verify breakpad symbol generation before gathering the sym files.
  if result.returncode:
    logging.error('Error (%d) when generating breakpad symbols',
                  result.returncode)
    return None
  with chroot.tempdir() as symbol_tmpdir, chroot.tempdir() as dest_tmpdir:
    breakpad_dir = os.path.join(base_path, 'usr/lib/debug/breakpad')
    # Call list on the atifacts.GatherSymbolFiles generator function to
    # materialize and consume all entries so that all are copied to
    # dest dir and complete list of all symbol files is returned.
    sym_file_list = list(
        GatherSymbolFiles(tempdir=symbol_tmpdir, destdir=dest_tmpdir,
                          paths=[breakpad_dir]))

    if not sym_file_list:
      logging.warning('No sym files found in %s.', breakpad_dir)
    # Create tarball from destination_tmp, then copy it...
    tarball_path = os.path.join(output_dir,
                                constants.BREAKPAD_DEBUG_SYMBOLS_TAR)
    result = cros_build_lib.CreateTarball(tarball_path, dest_tmpdir)
    if result.returncode != 0:
      logging.error('Error (%d) when creating tarball %s from %s',
                    result.returncode, tarball_path, dest_tmpdir)
      return None
  return tarball_path


# A SymbolFileTuple is a data object that contains:
#  relative_path (str): Relative path to the file based on initial search path.
#  source_file_name (str): Full path to where the SymbolFile was found.
# For example, if the search path for symbol files is '/some/bot/path/'
# and a symbol file is found at '/some/bot/path/a/b/c/file1.sym',
# then the relative_path would be 'a/b/c/file1.sym' and the source_file_name
# would be '/some/bot/path/a/b/c/file1.sym'.
# The source_file_name is informational for two reasons:
# 1) They are typically copied off a machine (such as a build bot) where
#    that path will disappear, which is why when we find them they get
#    copied to a destination directory.
# 2) For tar files, the source_file_name is not a full path that can be
#    opened, since it is the path the tar file plus the relative path of
#    the file when we untar it.
class SymbolFileTuple(NamedTuple):
  """Contain a relative and full path to a SymbolFile."""
  relative_path: str
  source_file_name: str


def GenerateBreakpadSymbols(chroot: chroot_lib.Chroot,
                            build_target: build_target_lib.BuildTarget,
                            debug: bool) -> cros_build_lib.CommandResult:
  """Generate breakpad (go/breakpad) symbols for debugging.

  This function generates .sym files to /build/<board>/usr/lib/debug/breakpad
  from .debug files found in /build/<board>/usr/lib/debug by calling
  cros_generate_breakpad_symbols.

  Args:
    chroot: The chroot in which the sysroot should be built.
    build_target: The sysroot's build target.
    debug: Include extra debugging output.
  """
  # The firmware directory contains elf symbols that we have trouble parsing
  # and that don't help with breakpad debugging (see https://crbug.com/213670).
  exclude_dirs = ['firmware']

  cmd = [
      'cros_generate_breakpad_symbols'
  ]
  if debug:
    cmd += ['--debug']

  # Execute for board in parallel with half # of cpus available to avoid
  # starving other parallel processes on the same machine.
  cmd += [
      '--board=%s' % build_target.name,
      '--jobs', str(max(1, multiprocessing.cpu_count() // 2))
  ]
  cmd += ['--exclude-dir=%s' % x for x in exclude_dirs]

  logging.info('Generating breakpad symbols: %s.', cmd)
  result = cros_build_lib.run(
      cmd,
      enter_chroot=True,
      chroot_args=chroot.get_enter_args())
  return result


def GatherSymbolFiles(tempdir:str, destdir:str,
                      paths: List[str]) -> List[SymbolFileTuple]:
  """Locate symbol files in |paths|

  This generator function searches all paths for .sym files and copies them to
  destdir. A path to a tarball will result in the tarball being unpacked and
  examined. A path to a directory will result in the directory being searched
  for .sym files. The generator yields SymbolFileTuple objects that contain
  symbol file references which are valid after this exits. Those files may exist
  externally, or be created in the tempdir (when expanding tarballs). Typical
  usage in the BuildAPI will be for the .sym files to exist under a directory
  such as /build/<board>/usr/lib/debug/breakpad so that the path to a sym file
  will always be unique.
  Note: the caller must clean up the tempdir.
  Note: this function is recursive for tar files.

  Args:
    tempdir: Path to use for temporary files.
    destdir: All .sym files are copied to this path. Tarfiles are opened inside
      a tempdir and any .sym files within them are copied to destdir from within
      that temp path.
    paths: A list of input paths to walk. Files are returned based on .sym name
      w/out any checking internal symbol file format.
      Dirs are searched for files that end in ".sym". Urls are not handled.
      Tarballs are unpacked and walked.

  Yields:
    A SymbolFileTuple for every symbol file found in paths.
  """
  logging.info('GatherSymbolFiles tempdir %s destdir %s paths %s',
               tempdir, destdir, paths)
  for p in paths:
    o = urllib.parse.urlparse(p)
    if o.scheme:
      raise NotImplementedError('URL paths are not expected/handled: ', p)
    elif not os.path.exists(p):
      raise NoFilesError('The path did not exist: ', p)
    elif os.path.isdir(p):
      for root, _, files in os.walk(p):
        for f in files:
          if f.endswith('.sym'):
            # If p is '/tmp/foo' and filename is '/tmp/foo/bar/bar.sym',
            # relative_path = 'bar/bar.sym'
            filename = os.path.join(root, f)
            relative_path = filename[len(p):].lstrip('/')
            try:
              shutil.copy(filename, os.path.join(destdir, relative_path))
            except IOError:
              # Handles pre-3.3 Python where we may need to make the target
              # path's dirname before copying.
              os.makedirs(os.path.join(destdir, os.path.dirname(relative_path)))
              shutil.copy(filename, os.path.join(destdir, relative_path))
            yield SymbolFileTuple(relative_path=relative_path,
                                  source_file_name=filename)

    elif cros_build_lib.IsTarball(p):
      tardir = tempfile.mkdtemp(dir=tempdir)
      cache.Untar(os.path.realpath(p), tardir)
      for sym in GatherSymbolFiles(tardir, destdir, [tardir]):
        # The SymbolFileTuple is generated from [tardir], but we want the
        # source_file_name (which informational) to reflect the tar path
        # plus the relative path after the file is untarred.
        # Thus, something like /botpath/some/path/tmp22dl33sa/dir1/fileB.sym
        # (where the tardir is /botpath/some/path/tmp22dl33sa)
        # has a resulting path /botpath/some/path/symfiles.tar/dir1/fileB.sym
        # When we call GatherSymbolFiles with [tardir] as the argument,
        # the os.path.isdir case above will walk the tar contents,
        # processing only .sym. Non-sym files within the tar file will be
        # ignored (even tar files within tar files, which we don't expect).
        new_source_file_name = sym.source_file_name.replace(tardir, p)
        yield SymbolFileTuple(
            relative_path=sym.relative_path,
            source_file_name=new_source_file_name)

    elif os.path.isfile(p):
      # Path p is a file. This code path is only executed when a full file path
      # is one of the elements in the 'paths' argument. When a directory is an
      # element of the 'paths' argument, we walk the tree (above) and process
      # each file. When a tarball is an element of the 'paths' argument, we
      # untar it into a directory and recurse with the temp tardir as the
      # directory, so that tarfile contents are processed (above) in the os.walk
      # of the directory.
      if p.endswith('.sym'):
        shutil.copy(p, destdir)
        yield SymbolFileTuple(relative_path=os.path.basename(p),
                              source_file_name=p)
    else:
      raise ValueError('Unexpected input to GatherSymbolFiles: ', p)
