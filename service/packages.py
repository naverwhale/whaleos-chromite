# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Package utility functionality."""

import collections
from distutils.version import LooseVersion
import fileinput
import functools
import json
import logging
import os
import re
import sys
from typing import List, Optional, TYPE_CHECKING, Union

from chromite.third_party.google.protobuf import json_format

from chromite.api.gen.config import replication_config_pb2
from chromite.cbuildbot import manifest_version
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import git
from chromite.lib import image_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import replication_lib
from chromite.lib import uprev_lib
from chromite.lib.parser import package_info

if TYPE_CHECKING:
  from chromite.lib import build_target_lib

if cros_build_lib.IsInsideChroot():
  from chromite.lib import depgraph
  from chromite.service import dependency

# Registered handlers for uprevving versioned packages.
_UPREV_FUNCS = {}


class Error(Exception):
  """Module's base error class."""


class UnknownPackageError(Error):
  """Uprev attempted for a package without a registered handler."""


class UprevError(Error):
  """An error occurred while uprevving packages."""


class NoAndroidVersionError(Error):
  """An error occurred while trying to determine the android version."""


class NoAndroidBranchError(Error):
  """An error occurred while trying to determine the android branch."""


class NoAndroidTargetError(Error):
  """An error occurred while trying to determine the android target."""


class AndroidIsPinnedUprevError(UprevError):
  """Raised when we try to uprev while Android is pinned."""

  def __init__(self, new_android_atom):
    """Initialize a AndroidIsPinnedUprevError.

    Args:
      new_android_atom: The Android atom that we failed to
                        uprev to, due to Android being pinned.
    """
    assert new_android_atom
    msg = ('Failed up uprev to Android version %s as Android was pinned.' %
           new_android_atom)
    super().__init__(msg)
    self.new_android_atom = new_android_atom


class GeneratedCrosConfigFilesError(Error):
  """Error when cros_config_schema does not produce expected files"""

  def __init__(self, expected_files, found_files):
    msg = ('Expected to find generated C files: %s. Actually found: %s' %
           (expected_files, found_files))
    super().__init__(msg)


NeedsChromeSourceResult = collections.namedtuple('NeedsChromeSourceResult', (
    'needs_chrome_source',
    'builds_chrome',
    'packages',
    'missing_chrome_prebuilt',
    'missing_follower_prebuilt',
    'local_uprev',
))


def patch_ebuild_vars(ebuild_path, variables):
  """Updates variables in ebuild.

  Use this function rather than portage_util.EBuild.UpdateEBuild when you
  want to preserve the variable position and quotes within the ebuild.

  Args:
    ebuild_path: The path of the ebuild.
    variables: Dictionary of variables to update in ebuild.
  """
  try:
    for line in fileinput.input(ebuild_path, inplace=1):
      varname, eq, _ = line.partition('=')
      if eq == '=' and varname.strip() in variables:
        value = variables[varname]
        sys.stdout.write('%s="%s"\n' % (varname, value))
      else:
        sys.stdout.write(line)
  finally:
    fileinput.close()


def uprevs_versioned_package(package):
  """Decorator to register package uprev handlers."""
  assert package

  def register(func):
    """Registers |func| as a handler for |package|."""
    _UPREV_FUNCS[package] = func

    @functools.wraps(func)
    def pass_through(*args, **kwargs):
      return func(*args, **kwargs)

    return pass_through

  return register


def uprev_android(android_package,
                  chroot,
                  build_targets=None,
                  android_build_branch=None,
                  android_version=None,
                  skip_commit=False):
  """Returns the portage atom for the revved Android ebuild - see man emerge."""
  command = [
      'cros_mark_android_as_stable',
      f'--android_package={android_package}',
  ]
  if build_targets:
    command.append(f'--boards={":".join(bt.name for bt in build_targets)}')
  if android_build_branch:
    command.append(f'--android_build_branch={android_build_branch}')
  if android_version:
    command.append(f'--force_version={android_version}')
  if skip_commit:
    command.append('--skip_commit')

  result = cros_build_lib.run(
      command,
      stdout=True,
      enter_chroot=True,
      encoding='utf-8',
      chroot_args=chroot.get_enter_args())

  portage_atom_string = result.stdout.strip()
  android_atom = None
  if portage_atom_string:
    android_atom = portage_atom_string.splitlines()[-1].partition('=')[-1]
  if not android_atom:
    logging.info('Found nothing to rev.')
    return None

  for target in build_targets or []:
    # Sanity check: We should always be able to merge the version of
    # Android we just unmasked.
    command = [f'emerge-{target.name}', '-p', '--quiet', f'={android_atom}']
    try:
      cros_build_lib.run(
          command, enter_chroot=True, chroot_args=chroot.get_enter_args())
    except cros_build_lib.RunCommandError:
      logging.error(
          'Cannot emerge-%s =%s\nIs Android pinned to an older '
          'version?', target, android_atom)
      raise AndroidIsPinnedUprevError(android_atom)

  return android_atom


def uprev_build_targets(build_targets,
                        overlay_type,
                        chroot=None,
                        output_dir=None):
  """Uprev the set provided build targets, or all if not specified.

  Args:
    build_targets (list[build_target_lib.BuildTarget]|None): The build targets
      whose overlays should be uprevved, empty or None for all.
    overlay_type (str): One of the valid overlay types except None (see
      constants.VALID_OVERLAYS).
    chroot (chroot_lib.Chroot|None): The chroot to clean, if desired.
    output_dir (str|None): The path to optionally dump result files.
  """
  # Need a valid overlay, but exclude None.
  assert overlay_type and overlay_type in constants.VALID_OVERLAYS

  if build_targets:
    overlays = portage_util.FindOverlaysForBoards(
        overlay_type, boards=[t.name for t in build_targets])
  else:
    overlays = portage_util.FindOverlays(overlay_type)

  return uprev_overlays(
      overlays,
      build_targets=build_targets,
      chroot=chroot,
      output_dir=output_dir)


def uprev_overlays(overlays, build_targets=None, chroot=None, output_dir=None):
  """Uprev the given overlays.

  Args:
    overlays (list[str]): The list of overlay paths.
    build_targets (list[build_target_lib.BuildTarget]|None): The build targets
      to clean in |chroot|, if desired. No effect unless |chroot| is provided.
    chroot (chroot_lib.Chroot|None): The chroot to clean, if desired.
    output_dir (str|None): The path to optionally dump result files.

  Returns:
    list[str] - The paths to all of the modified ebuild files. This includes the
      new files that were added (i.e. the new versions) and all of the removed
      files (i.e. the old versions).
  """
  assert overlays

  manifest = git.ManifestCheckout.Cached(constants.SOURCE_ROOT)

  uprev_manager = uprev_lib.UprevOverlayManager(
      overlays,
      manifest,
      build_targets=build_targets,
      chroot=chroot,
      output_dir=output_dir)
  uprev_manager.uprev()

  return uprev_manager.modified_ebuilds, uprev_manager.revved_packages


def uprev_versioned_package(package, build_targets, refs, chroot):
  """Call registered uprev handler function for the package.

  Args:
    package (package_info.CPV): The package being uprevved.
    build_targets (list[build_target_lib.BuildTarget]): The build targets to
        clean on a successful uprev.
    refs (list[uprev_lib.GitRef]):
    chroot (chroot_lib.Chroot): The chroot to enter for cleaning.

  Returns:
    UprevVersionedPackageResult: The result.
  """
  assert package

  if package.cp not in _UPREV_FUNCS:
    raise UnknownPackageError(
        'Package "%s" does not have a registered handler.' % package.cp)

  return _UPREV_FUNCS[package.cp](build_targets, refs, chroot)


@uprevs_versioned_package('media-libs/virglrenderer')
def uprev_virglrenderer(_build_targets, refs, _chroot):
  """Updates virglrenderer ebuilds.

  See: uprev_versioned_package.

  Returns:
    UprevVersionedPackageResult: The result of updating virglrenderer ebuilds.
  """
  overlay = os.path.join(constants.SOURCE_ROOT,
                         constants.CHROMIUMOS_OVERLAY_DIR)
  repo_path = os.path.join(constants.SOURCE_ROOT, 'src', 'third_party',
                           'virglrenderer')
  manifest = git.ManifestCheckout.Cached(repo_path)

  uprev_manager = uprev_lib.UprevOverlayManager([overlay], manifest)
  # TODO(crbug.com/1066242): Ebuilds for virglrenderer are currently
  # denylisted. Do not force uprevs after builder is stable and ebuilds are no
  # longer denylisted.
  uprev_manager.uprev(package_list=['media-libs/virglrenderer'], force=True)

  updated_files = uprev_manager.modified_ebuilds
  result = uprev_lib.UprevVersionedPackageResult()
  result.add_result(refs[0].revision, updated_files)
  return result

@uprevs_versioned_package('chromeos-base/drivefs')
def uprev_drivefs(_build_targets, refs, chroot):
  """Updates drivefs ebuilds.

  DriveFS versions follow the tag format of refs/tags/drivefs_1.2.3.
  See: uprev_versioned_package.

  Returns:
    UprevVersionedPackageResult: The result of updating drivefs ebuilds.
  """

  DRIVEFS_PATH_PREFIX = 'src/private-overlays/chromeos-overlay/chromeos-base'
  result = uprev_lib.UprevVersionedPackageResult()
  all_changed_files = []

  DRIVEFS_REFS_PREFIX = 'refs/tags/drivefs_'
  drivefs_version = _get_latest_version_from_refs(DRIVEFS_REFS_PREFIX, refs)
  if not drivefs_version:
    # No valid DriveFS version is identified.
    return result

  logging.debug('DriveFS version determined from refs: %s', drivefs_version)

  # Attempt to uprev drivefs package.
  pkg_path = os.path.join(DRIVEFS_PATH_PREFIX, 'drivefs')
  uprev_result = uprev_lib.uprev_workon_ebuild_to_version(pkg_path,
                                                          drivefs_version,
                                                          chroot,
                                                          allow_downrev=False)

  if not uprev_result:
    return result
  all_changed_files.extend(uprev_result.changed_files)

  # Attempt to uprev drivefs-ipc package.
  pkg_path = os.path.join(DRIVEFS_PATH_PREFIX, 'drivefs-ipc')
  uprev_result = uprev_lib.uprev_workon_ebuild_to_version(pkg_path,
                                                          drivefs_version,
                                                          chroot,
                                                          allow_downrev=False)

  if not uprev_result:
    logging.warning(
        'drivefs package has changed files %s but drivefs-ipc does not',
        all_changed_files)
    return result

  all_changed_files.extend(uprev_result.changed_files)
  result.add_result(drivefs_version, all_changed_files)

  return result

@uprevs_versioned_package('chromeos-base/perfetto')
def uprev_perfetto(_build_targets, refs, chroot):
  """Updates Perfetto ebuilds.

  Perfetto versions follow the tag format of refs/tags/v1.2.
  See: uprev_versioned_package.

  Returns:
    UprevVersionedPackageResult: The result of updating Perfetto ebuilds.
  """
  result = uprev_lib.UprevVersionedPackageResult()

  PERFETTO_REFS_PREFIX = 'refs/tags/v'
  perfetto_version = _get_latest_version_from_refs(PERFETTO_REFS_PREFIX, refs)
  if not perfetto_version:
    # No valid Perfetto version is identified.
    return result

  logging.debug('Perfetto version determined from refs: %s', perfetto_version)

  # Attempt to uprev perfetto package.
  PERFETTO_PATH = 'src/third_party/chromiumos-overlay/chromeos-base/perfetto'

  uprev_result = uprev_lib.uprev_workon_ebuild_to_version(
      PERFETTO_PATH,
      perfetto_version,
      chroot,
      allow_downrev=False,
      ref=PERFETTO_REFS_PREFIX + perfetto_version)

  if not uprev_result:
    return result

  result.add_result(perfetto_version, uprev_result.changed_files)

  return result

@uprevs_versioned_package('afdo/kernel-profiles')
def uprev_kernel_afdo(*_args, **_kwargs):
  """Updates kernel ebuilds with versions from kernel_afdo.json.

  See: uprev_versioned_package.

  Raises:
    EbuildManifestError: When ebuild manifest does not complete successfuly.
  """
  path = os.path.join(constants.SOURCE_ROOT, 'src', 'third_party',
                      'toolchain-utils', 'afdo_metadata', 'kernel_afdo.json')

  with open(path, 'r') as f:
    versions = json.load(f)

  result = uprev_lib.UprevVersionedPackageResult()
  for kernel_pkg, version_info in versions.items():
    path = os.path.join(constants.CHROMIUMOS_OVERLAY_DIR,
                        'sys-kernel', kernel_pkg)
    ebuild_path = os.path.join(constants.SOURCE_ROOT, path,
                               '%s-9999.ebuild' % kernel_pkg)
    chroot_ebuild_path = os.path.join(constants.CHROOT_SOURCE_ROOT, path,
                                      '%s-9999.ebuild' % kernel_pkg)
    afdo_profile_version = version_info['name']
    patch_ebuild_vars(ebuild_path,
                      dict(AFDO_PROFILE_VERSION=afdo_profile_version))

    try:
      cmd = ['ebuild', chroot_ebuild_path, 'manifest', '--force']
      cros_build_lib.run(cmd, enter_chroot=True)
    except cros_build_lib.RunCommandError as e:
      raise uprev_lib.EbuildManifestError(
          'Error encountered when regenerating the manifest for ebuild: %s\n%s'
          % (chroot_ebuild_path, e), e)

    manifest_path = os.path.join(constants.SOURCE_ROOT, path, 'Manifest')

    result.add_result(afdo_profile_version, [ebuild_path, manifest_path])

  return result


@uprevs_versioned_package('chromeos-base/termina-dlc')
def uprev_termina_dlc(_build_targets, _refs, chroot):
  """Updates shared termina-dlc ebuild - chromeos-base/termina-dlc.

  See: uprev_versioned_package.
  """
  package = 'termina-dlc'
  package_path = os.path.join(constants.CHROMIUMOS_OVERLAY_DIR, 'chromeos-base',
                              package)

  version_pin_src_path = _get_version_pin_src_path(package_path)
  version_no_rev = osutils.ReadFile(version_pin_src_path).strip()

  return uprev_lib.uprev_ebuild_from_pin(package_path, version_no_rev, chroot)


@uprevs_versioned_package('chromeos-base/chromeos-lacros')
def uprev_lacros(_build_targets, refs, chroot):
  """Updates lacros ebuilds.

  Version to uprev to is gathered from the QA qualified version tracking file
  stored in chromium/src/chrome/LACROS_QA_QUALIFIED_VERSION. Uprev is triggered
  on modification of this file across all chromium/src branches.

  See: uprev_versioned_package.
  """
  result = uprev_lib.UprevVersionedPackageResult()
  path = os.path.join(
      constants.CHROMIUMOS_OVERLAY_DIR, 'chromeos-base','chromeos-lacros')
  lacros_version = refs[0].revision
  uprev_result = uprev_lib.uprev_workon_ebuild_to_version(path,
                                                          lacros_version,
                                                          chroot,
                                                          allow_downrev=False)

  if not uprev_result:
    return result

  result.add_result(lacros_version, uprev_result.changed_files)
  return result


@uprevs_versioned_package('app-emulation/parallels-desktop')
def uprev_parallels_desktop(_build_targets, _refs, chroot):
  """Updates Parallels Desktop ebuild - app-emulation/parallels-desktop.

  See: uprev_versioned_package

  Returns:
    UprevVersionedPackageResult: The result.
  """
  package = 'parallels-desktop'
  package_path = os.path.join(constants.CHROMEOS_PARTNER_OVERLAY_DIR,
                              'app-emulation', package)
  version_pin_src_path = _get_version_pin_src_path(package_path)

  # Expect a JSON blob like the following:
  # {
  #   "version": "1.2.3",
  #   "test_image": { "url": "...", "size": 12345678,
  #                   "sha256sum": "<32 bytes of hexadecimal>" }
  # }
  with open(version_pin_src_path, 'r') as f:
    pinned = json.load(f)

  if 'version' not in pinned or 'test_image' not in pinned:
    raise UprevError('VERSION-PIN for %s missing version and/or '
                     'test_image field' % package)

  version = pinned['version']
  if not isinstance(version, str):
    raise UprevError('version in VERSION-PIN for %s not a string' % package)

  # Update the ebuild.
  result = uprev_lib.uprev_ebuild_from_pin(package_path, version, chroot)

  # Update the VM image used for testing.
  test_image_path = ('src/platform/tast-tests-private/src/chromiumos/tast/'
                     'local/bundles/crosint/pita/data/'
                     'pluginvm_image.zip.external')
  test_image_src_path = os.path.join(constants.SOURCE_ROOT, test_image_path)
  with open(test_image_src_path, 'w') as f:
    json.dump(pinned['test_image'], f, indent=2)
  result.add_result(version, [test_image_src_path])

  return result


@uprevs_versioned_package('chromeos-base/chromeos-dtc-vm')
def uprev_sludge(_build_targets, _refs, chroot):
  """Updates sludge VM - chromeos-base/chromeos-dtc-vm.

  See: uprev_versioned_package.
  """
  package = 'chromeos-dtc-vm'
  package_path = os.path.join('src', 'private-overlays',
                              'project-wilco-private', 'chromeos-base', package)
  version_pin_src_path = _get_version_pin_src_path(package_path)
  version_no_rev = osutils.ReadFile(version_pin_src_path).strip()

  return uprev_lib.uprev_ebuild_from_pin(package_path, version_no_rev, chroot)


def _get_version_pin_src_path(package_path):
  """Returns the path to the VERSION-PIN file for the given package."""
  return os.path.join(constants.SOURCE_ROOT, package_path, 'VERSION-PIN')


@uprevs_versioned_package(constants.CHROME_CP)
def uprev_chrome_from_ref(build_targets, refs, chroot):
  """Uprev chrome and its related packages.

  See: uprev_versioned_package.
  """
  # Determine the version from the refs (tags), i.e. the chrome versions are the
  # tag names.
  chrome_version = uprev_lib.get_chrome_version_from_refs(refs)
  logging.debug('Chrome version determined from refs: %s', chrome_version)

  return uprev_chrome(build_targets, chrome_version, chroot)


def revbump_chrome(
    build_targets: List['build_target_lib.BuildTarget'],
    chroot: Optional['chroot_lib.Chroot'] = None
) -> uprev_lib.UprevVersionedPackageResult:
  """Attempt to revbump chrome.

  Revbumps are done by executing an uprev using the current stable version.
  E.g. if chrome is on 1.2.3.4 and has a 1.2.3.4_rc-r2.ebuild, performing an
  uprev on version 1.2.3.4 when there are applicable changes (e.g. to the 9999
  ebuild) will result in a revbump to 1.2.3.4_rc-r3.ebuild.
  """
  chrome_version = uprev_lib.get_stable_chrome_version()
  return uprev_chrome(build_targets, chrome_version, chroot)


def uprev_chrome(
    build_targets: List['build_target_lib.BuildTarget'], chrome_version: str,
    chroot: Union['chroot_lib.Chroot', None]
) -> uprev_lib.UprevVersionedPackageResult:
  """Attempt to uprev chrome and its related packages to the given version."""
  uprev_manager = uprev_lib.UprevChromeManager(
      chrome_version, build_targets=build_targets, chroot=chroot)
  result = uprev_lib.UprevVersionedPackageResult()
  # TODO(crbug.com/1080429): Handle all possible outcomes of a Chrome uprev
  #     attempt. The expected behavior is documented in the following table:
  #
  #     Outcome of Chrome uprev attempt:
  #     NEWER_VERSION_EXISTS:
  #       Do nothing.
  #     SAME_VERSION_EXISTS or REVISION_BUMP:
  #       Uprev followers
  #       Assert not VERSION_BUMP (any other outcome is fine)
  #     VERSION_BUMP or NEW_EBUILD_CREATED:
  #       Uprev followers
  #       Assert that Chrome & followers are at same package version

  # Start with chrome itself so we can proceed accordingly.
  chrome_result = uprev_manager.uprev(constants.CHROME_CP)
  if chrome_result.newer_version_exists:
    # Cannot use the given version (newer version already exists).
    return result

  # Also uprev related packages.
  for package in constants.OTHER_CHROME_PACKAGES:
    follower_result = uprev_manager.uprev(package)
    if chrome_result.stable_version and follower_result.version_bump:
      logging.warning('%s had a version bump, but no more than a revision bump '
                      'should have been possible.', package)

  if uprev_manager.modified_ebuilds:
    # Record changes when we have them.
    return result.add_result(chrome_version, uprev_manager.modified_ebuilds)

  return result


def _get_latest_version_from_refs(refs_prefix: str,
                                  refs: List[uprev_lib.GitRef]) -> str:
  """Get the latest version from refs

  Versions are compared using |distutils.version.LooseVersion| and
  the latest version is returned.

  Args:
    refs_prefix: The refs prefix of the tag format.
    refs: The tags to parse for the latest Perfetto version.

  Returns:
    The latest Perfetto version to use.
  """
  valid_refs = []
  for gitiles in refs:
    if gitiles.ref.startswith(refs_prefix):
      valid_refs.append(gitiles.ref)

  if not valid_refs:
    return None

  # Sort by version and take the latest version.
  target_version_ref = sorted(valid_refs,
                              key=LooseVersion,
                              reverse=True)[0]
  return target_version_ref.replace(refs_prefix, '')


def _generate_platform_c_files(replication_config, chroot):
  """Generates platform C files from a platform JSON payload.

  Args:
    replication_config (replication_config_pb2.ReplicationConfig): A
      ReplicationConfig that has already been run. If it produced a
      build_config.json file, that file will be used to generate platform C
      files. Otherwise, nothing will be generated.
    chroot (chroot_lib.Chroot): The chroot to use to generate.

  Returns:
    A list of generated files.
  """
  # Generate the platform C files from the build config. Note that it would be
  # more intuitive to generate the platform C files from the platform config;
  # however, cros_config_schema does not allow this, because the platform config
  # payload is not always valid input. For example, if a property is both
  # 'required' and 'build-only', it will fail schema validation. Thus, use the
  # build config, and use '-f' to filter.
  build_config_path = [
      rule.destination_path
      for rule in replication_config.file_replication_rules
      if rule.destination_path.endswith('build_config.json')
  ]

  if not build_config_path:
    logging.info(
        'No build_config.json found, will not generate platform C files. '
        'Replication config: %s', replication_config)
    return []

  if len(build_config_path) > 1:
    raise ValueError('Expected at most one build_config.json destination path. '
                     'Replication config: %s' % replication_config)

  build_config_path = build_config_path[0]

  # Paths to the build_config.json and dir to output C files to, in the
  # chroot.
  build_config_chroot_path = os.path.join(constants.CHROOT_SOURCE_ROOT,
                                          build_config_path)
  generated_output_chroot_dir = os.path.join(constants.CHROOT_SOURCE_ROOT,
                                             os.path.dirname(build_config_path))

  command = [
      'cros_config_schema', '-m', build_config_chroot_path, '-g',
      generated_output_chroot_dir, '-f', '"TRUE"'
  ]

  cros_build_lib.run(
      command, enter_chroot=True, chroot_args=chroot.get_enter_args())

  # A relative (to the source root) path to the generated C files.
  generated_output_dir = os.path.dirname(build_config_path)
  generated_files = []
  expected_c_files = ['config.c', 'ec_config.c', 'ec_config.h']
  for f in expected_c_files:
    if os.path.exists(
        os.path.join(constants.SOURCE_ROOT, generated_output_dir, f)):
      generated_files.append(os.path.join(generated_output_dir, f))

  if len(expected_c_files) != len(generated_files):
    raise GeneratedCrosConfigFilesError(expected_c_files, generated_files)

  return generated_files


def _get_private_overlay_package_root(ref, package):
  """Returns the absolute path to the root of a given private overlay.

  Args:
    ref (uprev_lib.GitRef): GitRef for the private overlay.
    package (str): Path to the package in the overlay.
  """
  # There might be a cleaner way to map from package -> path within the source
  # tree. For now, just use string patterns.
  private_overlay_ref_pattern = r'/chromeos\/overlays\/overlay-([\w-]+)-private'
  match = re.match(private_overlay_ref_pattern, ref.path)
  if not match:
    raise ValueError('ref.path must match the pattern: %s. Actual ref: %s' %
                     (private_overlay_ref_pattern, ref))

  overlay = match.group(1)

  return os.path.join(constants.SOURCE_ROOT,
                      'src/private-overlays/overlay-%s-private' % overlay,
                      package)


@uprevs_versioned_package('chromeos-base/chromeos-config-bsp')
def replicate_private_config(_build_targets, refs, chroot):
  """Replicate a private cros_config change to the corresponding public config.

  See uprev_versioned_package for args
  """
  package = 'chromeos-base/chromeos-config-bsp'

  if len(refs) != 1:
    raise ValueError('Expected exactly one ref, actual %s' % refs)

  # Expect a replication_config.jsonpb in the package root.
  package_root = _get_private_overlay_package_root(refs[0], package)
  replication_config_path = os.path.join(package_root,
                                         'replication_config.jsonpb')

  try:
    replication_config = json_format.Parse(
        osutils.ReadFile(replication_config_path),
        replication_config_pb2.ReplicationConfig())
  except IOError:
    raise ValueError(
        'Expected ReplicationConfig missing at %s' % replication_config_path)

  replication_lib.Replicate(replication_config)

  modified_files = [
      rule.destination_path
      for rule in replication_config.file_replication_rules
  ]

  # The generated platform C files are not easily filtered by replication rules,
  # i.e. JSON / proto filtering can be described by a FieldMask, arbitrary C
  # files cannot. Therefore, replicate and filter the JSON payloads, and then
  # generate filtered C files from the JSON payload.
  modified_files.extend(_generate_platform_c_files(replication_config, chroot))

  # Use the private repo's commit hash as the new version.
  new_private_version = refs[0].revision

  # modified_files should contain only relative paths at this point, but the
  # returned UprevVersionedPackageResult must contain only absolute paths.
  for i, modified_file in enumerate(modified_files):
    assert not os.path.isabs(modified_file)
    modified_files[i] = os.path.join(constants.SOURCE_ROOT, modified_file)

  return uprev_lib.UprevVersionedPackageResult().add_result(
      new_private_version, modified_files)


@uprevs_versioned_package('chromeos-base/crosvm')
def uprev_crosvm(_build_targets, refs, _chroot):
  """Updates crosvm ebuilds to latest revision

  crosvm is not versioned. We are updating to the latest commit on the main
  branch.

  See: uprev_versioned_package.

  Returns:
    UprevVersionedPackageResult: The result of updating crosvm ebuilds.
  """
  overlay = os.path.join(constants.SOURCE_ROOT,
                         constants.CHROMIUMOS_OVERLAY_DIR)
  repo_path = os.path.join(constants.SOURCE_ROOT, 'src', 'crosvm')
  manifest = git.ManifestCheckout.Cached(repo_path)

  uprev_manager = uprev_lib.UprevOverlayManager([overlay], manifest)
  uprev_manager.uprev(package_list=['chromeos-base/crosvm'], force=True)

  updated_files = uprev_manager.modified_ebuilds
  result = uprev_lib.UprevVersionedPackageResult()
  result.add_result(refs[0].revision, updated_files)
  return result


def get_best_visible(
    atom: str,
    build_target: Optional['build_target_lib.BuildTarget'] = None
) -> package_info.PackageInfo:
  """Returns the best visible CPV for the given atom.

  Args:
    atom: The atom to look up.
    build_target: The build target whose sysroot should be searched, or the SDK
      if not provided.

  Returns:
    The best visible package, or None if none are visible.
  """
  assert atom

  return portage_util.PortageqBestVisible(
      atom,
      board=build_target.name if build_target else None,
      sysroot=build_target.root if build_target else None)


def has_prebuilt(atom, build_target=None, useflags=None):
  """Check if a prebuilt exists.

  Args:
    atom (str): The package whose prebuilt is being queried.
    build_target (build_target_lib.BuildTarget): The build target whose
        sysroot should be searched, or the SDK if not provided.
    useflags: Any additional USE flags that should be set. May be a string
        of properly formatted USE flags, or an iterable of individual flags.

  Returns:
    bool: True iff there is an available prebuilt, False otherwise.
  """
  assert atom

  board = build_target.name if build_target else None
  extra_env = None
  if useflags:
    new_flags = useflags
    if not isinstance(useflags, str):
      new_flags = ' '.join(useflags)

    existing = os.environ.get('USE', '')
    final_flags = '%s %s' % (existing, new_flags)
    extra_env = {'USE': final_flags.strip()}
  return portage_util.HasPrebuilt(atom, board=board, extra_env=extra_env)


def builds(atom, build_target, packages=None):
  """Check if |build_target| builds |atom| (has it in its depgraph)."""
  cros_build_lib.AssertInsideChroot()

  pkgs = tuple(packages) if packages else None
  # TODO(crbug/1081828): Receive and use sysroot.
  graph, _sdk_graph = dependency.GetBuildDependency(
      build_target.root, build_target.name, pkgs)
  return any(atom in package for package in graph['package_deps'])


def needs_chrome_source(
    build_target: 'build_target_lib.BuildTarget',
    compile_source=False,
    packages: Optional[List[package_info.PackageInfo]] = None,
    useflags=None):
  """Check if the chrome source is needed.

  The chrome source is needed if the build target builds chrome or any of its
  follower packages, and can't use a prebuilt for them either because it's not
  available, or because we can't use prebuilts because it must build from
  source.
  """
  cros_build_lib.AssertInsideChroot()

  # Check if it builds chrome and/or a follower package.
  graph = depgraph.get_sysroot_dependency_graph(build_target.root, packages)
  builds_chrome = constants.CHROME_CP in graph
  builds_follower = {
      pkg: pkg in graph for pkg in constants.OTHER_CHROME_PACKAGES
  }

  local_uprev = builds_chrome and revbump_chrome([build_target])

  # When we are compiling source set False since we do not use prebuilts.
  # When not compiling from source, start with True, i.e. we have every prebuilt
  # we've checked for up to this point.
  has_chrome_prebuilt = not compile_source
  has_follower_prebuilts = not compile_source
  # Save packages that need prebuilts for reporting.
  pkgs_needing_prebuilts = []
  if compile_source:
    # Need everything.
    pkgs_needing_prebuilts.append(constants.CHROME_CP)
    pkgs_needing_prebuilts.extend(
        [pkg for pkg, builds_pkg in builds_follower.items() if builds_pkg])
  else:
    # Check chrome itself.
    if builds_chrome:
      has_chrome_prebuilt = has_prebuilt(
          constants.CHROME_CP, build_target=build_target, useflags=useflags)
      if not has_chrome_prebuilt:
        pkgs_needing_prebuilts.append(constants.CHROME_CP)
    # Check follower packages.
    for pkg, builds_pkg in builds_follower.items():
      if not builds_pkg:
        continue
      prebuilt = has_prebuilt(pkg, build_target=build_target, useflags=useflags)
      has_follower_prebuilts &= prebuilt
      if not prebuilt:
        pkgs_needing_prebuilts.append(pkg)
  # Postcondition: has_chrome_prebuilt and has_follower_prebuilts now correctly
  # reflect whether we actually have the corresponding prebuilts for the build.

  needs_chrome = builds_chrome and not has_chrome_prebuilt
  needs_follower = any(builds_follower.values()) and not has_follower_prebuilts

  return NeedsChromeSourceResult(
      needs_chrome_source=needs_chrome or needs_follower,
      builds_chrome=builds_chrome,
      packages=[package_info.parse(p) for p in pkgs_needing_prebuilts],
      missing_chrome_prebuilt=not has_chrome_prebuilt,
      missing_follower_prebuilt=not has_follower_prebuilts,
      local_uprev=local_uprev,
  )


def determine_chrome_version(build_target):
  """Returns the current Chrome version for the board (or in buildroot).

  Args:
    build_target (build_target_lib.BuildTarget): The board build target.

  Returns:
    str|None: The chrome version if available.
  """
  # TODO(crbug/1019770): Long term we should not need the try/catch here once
  # the builds function above only returns True for chrome when
  # determine_chrome_version will succeed.
  try:
    pkg_info = portage_util.PortageqBestVisible(
        constants.CHROME_CP, build_target.name, cwd=constants.SOURCE_ROOT)
  except cros_build_lib.RunCommandError as e:
    # Return None because portage failed when trying to determine the chrome
    # version.
    logging.warning('Caught exception in determine_chrome_package: %s', e)
    return None
  # Something like 78.0.3877.4_rc -> 78.0.3877.4
  return pkg_info.version.partition('_')[0]


def determine_android_package(board):
  """Returns the active Android container package in use by the board.

  Args:
    board: The board name this is specific to.

  Returns:
    str|None: The android package string if there is one.
  """
  try:
    packages = portage_util.GetPackageDependencies(board, 'virtual/target-os')
  except cros_build_lib.RunCommandError as e:
    # Return None because a command (likely portage) failed when trying to
    # determine the package.
    logging.warning('Caught exception in determine_android_package: %s', e)
    return None

  # We assume there is only one Android package in the depgraph.
  for package in packages:
    if (package.startswith('chromeos-base/android-container-') or
        package.startswith('chromeos-base/android-vm-')):
      return package
  return None


def determine_android_version(board, package=None):
  """Determine the current Android version in buildroot now and return it.

  This uses the typical portage logic to determine which version of Android
  is active right now in the buildroot.

  Args:
    board: The board name this is specific to.
    package: The Android package, if already computed.

  Returns:
    The Android build ID of the container for the board.

  Raises:
    NoAndroidVersionError: if no unique Android version can be determined.
  """
  if not package:
    package = determine_android_package(board)
  if not package:
    return None
  cpv = package_info.SplitCPV(package)
  if not cpv:
    raise NoAndroidVersionError(
        'Android version could not be determined for %s' % board)
  return cpv.version_no_rev


def determine_android_branch(board, package=None):
  """Returns the Android branch in use by the active container ebuild."""
  if not package:
    package = determine_android_package(board)
  if not package:
    return None
  ebuild_path = portage_util.FindEbuildForBoardPackage(package, board)
  # We assume all targets pull from the same branch and that we always
  # have at least one of the following targets.
  targets = constants.ANDROID_ALL_BUILD_TARGETS
  ebuild_content = osutils.SourceEnvironment(ebuild_path, targets)
  for target in targets:
    if target in ebuild_content:
      branch = re.search(r'(.*?)-linux-', ebuild_content[target])
      if branch is not None:
        return branch.group(1)
  raise NoAndroidBranchError(
      'Android branch could not be determined for %s (ebuild empty?)' % board)


def determine_android_target(board, package=None):
  """Returns the Android target in use by the active container ebuild."""
  if not package:
    package = determine_android_package(board)
  if not package:
    return None
  if package.startswith('chromeos-base/android-vm-'):
    return 'bertha'
  elif package.startswith('chromeos-base/android-container-'):
    return 'cheets'

  raise NoAndroidTargetError(
      'Android Target cannot be determined for the package: %s' %
      package)


def determine_platform_version():
  """Returns the platform version from the source root."""
  # Platform version is something like '12575.0.0'.
  version = manifest_version.VersionInfo.from_repo(constants.SOURCE_ROOT)
  return version.VersionString()


def determine_milestone_version():
  """Returns the platform version from the source root."""
  # Milestone version is something like '79'.
  version = manifest_version.VersionInfo.from_repo(constants.SOURCE_ROOT)
  return version.chrome_branch


def determine_full_version():
  """Returns the full version from the source root."""
  # Full version is something like 'R79-12575.0.0'.
  milestone_version = determine_milestone_version()
  platform_version = determine_platform_version()
  full_version = ('R%s-%s' % (milestone_version, platform_version))
  return full_version


def find_fingerprints(build_target):
  """Returns a list of fingerprints for this build.

  Args:
    build_target (build_target_lib.BuildTarget): The build target.

  Returns:
    list[str] - List of fingerprint strings.
  """
  cros_build_lib.AssertInsideChroot()
  fp_file = 'cheets-fingerprint.txt'
  fp_path = os.path.join(
      image_lib.GetLatestImageLink(build_target.name),
      fp_file)
  if not os.path.isfile(fp_path):
    logging.info('Fingerprint file not found: %s', fp_path)
    return []
  logging.info('Reading fingerprint file: %s', fp_path)
  fingerprints = osutils.ReadFile(fp_path).splitlines()
  return fingerprints


def get_all_firmware_versions(build_target):
  """Extract firmware version for all models present.

  Args:
    build_target (build_target_lib.BuildTarget): The build target.

  Returns:
    A dict of FirmwareVersions namedtuple instances by model.
    Each element will be populated based on whether it was present in the
    command output.
  """
  cros_build_lib.AssertInsideChroot()
  result = {}
  # Note that example output for _get_firmware_version_cmd_result is available
  # in the packages_unittest.py for testing get_all_firmware_versions.
  cmd_result = _get_firmware_version_cmd_result(build_target)

  # There is a blank line between the version info for each model.
  firmware_version_payloads = cmd_result.split('\n\n')
  for firmware_version_payload in firmware_version_payloads:
    if 'BIOS' in firmware_version_payload:
      firmware_version = _find_firmware_versions(firmware_version_payload)
      result[firmware_version.model] = firmware_version
  return result


FirmwareVersions = collections.namedtuple(
    'FirmwareVersions', ['model', 'main', 'main_rw', 'ec', 'ec_rw'])


def get_firmware_versions(build_target):
  """Extract version information from the firmware updater, if one exists.

  Args:
    build_target (build_target_lib.BuildTarget): The build target.

  Returns:
    A FirmwareVersions namedtuple instance.
    Each element will either be set to the string output by the firmware
    updater shellball, or None if there is no firmware updater.
  """
  cros_build_lib.AssertInsideChroot()
  cmd_result = _get_firmware_version_cmd_result(build_target)
  if cmd_result:
    return _find_firmware_versions(cmd_result)
  else:
    return FirmwareVersions(None, None, None, None, None)


def _get_firmware_version_cmd_result(build_target):
  """Gets the raw result output of the firmware updater version command.

  Args:
    build_target (build_target_lib.BuildTarget): The build target.

  Returns:
    Command execution result.
  """
  updater = os.path.join(build_target.root,
                         'usr/sbin/chromeos-firmwareupdate')
  logging.info('Calling updater %s', updater)
  # Call the updater using the chroot-based path.
  return cros_build_lib.run([updater, '-V'],
                            capture_output=True, log_output=True,
                            encoding='utf-8').stdout


def _find_firmware_versions(cmd_output):
  """Finds firmware version output via regex matches against the cmd_output.

  Args:
    cmd_output: The raw output to search against.

  Returns:
    FirmwareVersions namedtuple with results.
    Each element will either be set to the string output by the firmware
    updater shellball, or None if there is no match.
  """

  # Sometimes a firmware bundle includes a special combination of RO+RW
  # firmware.  In this case, the RW firmware version is indicated with a "(RW)
  # version" field.  In other cases, the "(RW) version" field is not present.
  # Therefore, search for the "(RW)" fields first and if they aren't present,
  # fallback to the other format. e.g. just "BIOS version:".
  # TODO(mmortensen): Use JSON once the firmware updater supports it.
  main = None
  main_rw = None
  ec = None
  ec_rw = None
  model = None

  match = re.search(r'BIOS version:\s*(?P<version>.*)', cmd_output)
  if match:
    main = match.group('version')

  match = re.search(r'BIOS \(RW\) version:\s*(?P<version>.*)', cmd_output)
  if match:
    main_rw = match.group('version')

  match = re.search(r'EC version:\s*(?P<version>.*)', cmd_output)
  if match:
    ec = match.group('version')

  match = re.search(r'EC \(RW\) version:\s*(?P<version>.*)', cmd_output)
  if match:
    ec_rw = match.group('version')

  match = re.search(r'Model:\s*(?P<model>.*)', cmd_output)
  if match:
    model = match.group('model')

  return FirmwareVersions(model, main, main_rw, ec, ec_rw)


MainEcFirmwareVersions = collections.namedtuple(
    'MainEcFirmwareVersions', ['main_fw_version', 'ec_fw_version'])

def determine_firmware_versions(build_target):
  """Returns a namedtuple with main and ec firmware versions.

  Args:
    build_target (build_target_lib.BuildTarget): The build target.

  Returns:
    MainEcFirmwareVersions namedtuple with results.
  """
  fw_versions = get_firmware_versions(build_target)
  main_fw_version = fw_versions.main_rw or fw_versions.main
  ec_fw_version = fw_versions.ec_rw or fw_versions.ec

  return MainEcFirmwareVersions(main_fw_version, ec_fw_version)

def determine_kernel_version(build_target):
  """Returns a string containing the kernel version for this build target.

  Args:
    build_target (build_target_lib.BuildTarget): The build target.

  Returns:
    (str) The kernel versions, or None.
  """
  try:
    packages = portage_util.GetPackageDependencies(build_target.name,
                                                   'virtual/linux-sources')
  except cros_build_lib.RunCommandError as e:
    logging.warning('Unable to get package list for metadata: %s', e)
    return None
  for package in packages:
    if package.startswith('sys-kernel/chromeos-kernel-'):
      kernel_version = package_info.SplitCPV(package).version
      logging.info('Found active kernel version: %s', kernel_version)
      return kernel_version
  return None


def get_models(build_target, log_output=True):
  """Obtain a list of models supported by a unified board.

  This ignored whitelabel models since GoldenEye has no specific support for
  these at present.

  Args:
    build_target (build_target_lib.BuildTarget): The build target.
    log_output: Whether to log the output of the cros_config_host invocation.

  Returns:
    A list of models supported by this board, if it is a unified build; None,
    if it is not a unified build.
  """
  return _run_cros_config_host(build_target, ['list-models'],
                               log_output=log_output)


def get_key_id(build_target, model):
  """Obtain the key_id for a model within the build_target.

  Args:
    build_target (build_target_lib.BuildTarget): The build target.
    model (str): The model name

  Returns:
    A key_id (str) or None.
  """
  model_arg = '--model=' + model
  key_id_list = _run_cros_config_host(
      build_target,
      [model_arg, 'get', '/firmware-signing', 'key-id'])
  key_id = None
  if len(key_id_list) == 1:
    key_id = key_id_list[0]
  return key_id


def _run_cros_config_host(build_target, args, log_output=True):
  """Run the cros_config_host tool.

  Args:
    build_target (build_target_lib.BuildTarget): The build target.
    args: List of arguments to pass.
    log_output: Whether to log the output of the cros_config_host.

  Returns:
    Output of the tool
  """
  cros_build_lib.AssertInsideChroot()
  tool = '/usr/bin/cros_config_host'
  if not os.path.isfile(tool):
    return None

  config_fname = build_target.full_path(
      'usr/share/chromeos-config/yaml/config.yaml')

  result = cros_build_lib.run(
      [tool, '-c', config_fname] + args,
      capture_output=True,
      encoding='utf-8',
      log_output=log_output,
      check=False)
  if result.returncode:
    # Show the output for debugging purposes.
    if 'No such file or directory' not in result.error:
      logging.error('cros_config_host failed: %s\n', result.error)
    return None
  return result.output.strip().splitlines()
