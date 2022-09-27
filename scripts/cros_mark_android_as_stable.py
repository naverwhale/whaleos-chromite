# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module uprevs Android for cbuildbot.

After calling, it prints outs ANDROID_VERSION_ATOM=(version atom string).  A
caller could then use this atom with emerge to build the newly uprevved version
of Android e.g.

./cros_mark_android_as_stable \
    --android_build_branch=git_pi-arc \
    --android_package=android-container-pi

Returns chromeos-base/android-container-pi-6417892-r1

emerge-eve =chromeos-base/android-container-pi-6417892-r1
"""

import filecmp
import glob
import json
import logging
import os

from chromite.cbuildbot import cbuildbot_alerts
from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import git
from chromite.lib import gs
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import repo_util
from chromite.scripts import cros_mark_as_stable
from chromite.service import android


# Dir where all the action happens.
_OVERLAY_DIR = '%(srcroot)s/private-overlays/project-cheets-private/'

_GIT_COMMIT_MESSAGE = """Marking latest for %(android_package)s ebuild with \
version %(android_version)s as stable.

BUG=None
TEST=CQ
"""

_RUNTIME_ARTIFACTS_BUCKET_URL = 'gs://chromeos-arc-images/runtime_artifacts'


def FindAndroidCandidates(package_dir):
  """Return a tuple of Android's unstable ebuild and stable ebuilds.

  Args:
    package_dir: The path to where the package ebuild is stored.

  Returns:
    Tuple [unstable_ebuild, stable_ebuilds].

  Raises:
    Exception: if no unstable ebuild exists for Android.
  """
  stable_ebuilds = []
  unstable_ebuilds = []
  for path in glob.glob(os.path.join(package_dir, '*.ebuild')):
    ebuild = portage_util.EBuild(path)
    if ebuild.version == '9999':
      unstable_ebuilds.append(ebuild)
    else:
      stable_ebuilds.append(ebuild)

  # Apply some sanity checks.
  if not unstable_ebuilds:
    raise Exception('Missing 9999 ebuild for %s' % package_dir)
  if not stable_ebuilds:
    logging.warning('Missing stable ebuild for %s', package_dir)

  return portage_util.BestEBuild(unstable_ebuilds), stable_ebuilds


def PrintUprevMetadata(build_branch, stable_candidate, new_ebuild):
  """Shows metadata on buildbot page at UprevAndroid step.

  Args:
    build_branch: The branch of Android builds.
    stable_candidate: The existing stable ebuild.
    new_ebuild: The newly written ebuild.
  """
  # Examples:
  # "android-container-pi revved 6461825-r1 -> 6468247-r1"
  # "android-container-pi revved 6461825-r1 -> 6461825-r2 (ebuild update only)"
  msg = '%s revved %s -> %s' % (stable_candidate.pkgname,
                                stable_candidate.version,
                                new_ebuild.version)

  old_android = stable_candidate.version_no_rev
  new_android = new_ebuild.version_no_rev

  if old_android == new_android:
    msg += ' (ebuild update only)'
  else:
    ab_link = ('https://android-build.googleplex.com'
               '/builds/%s/branches/%s/cls?end=%s'
               % (new_android, build_branch, old_android))
    cbuildbot_alerts.PrintBuildbotLink('Android changelog', ab_link)

  cbuildbot_alerts.PrintBuildbotStepText(msg)
  cbuildbot_alerts.PrintKitchenSetBuildProperty('android_uprev', json.dumps({
      'branch': build_branch,
      'new': new_ebuild.version,
      'old': stable_candidate.version,
      'pkgname': stable_candidate.pkgname,
  }))


def FindDataCollectorArtifacts(gs_context,
                               android_version,
                               runtime_artifacts_bucket_url,
                               version_reference):
  r"""Finds and includes into variables artifacts from arc.DataCollector.

  This is used from UpdateDataCollectorArtifacts in order to check the
  particular version.

  Args:
    gs_context: context to execute gsutil
    android_version: The \d+ build id of Android.
    runtime_artifacts_bucket_url: root of runtime artifacts
    build_branch: build branch. Used to determine the pinned version if exists.
    version_reference: which version to use as a reference. Could be '${PV}' in
                       case version of data collector artifacts matches the
                       Android version or direct version in case of override.

  Returns:
    dictionary with filled ebuild variables. This dictionary is empty in case
    no artificats are found.
  """
  variables = {}

  buckets = ['ureadahead_pack', 'gms_core_cache']
  archs = ['arm', 'arm64', 'x86', 'x86_64']
  build_types = ['user', 'userdebug']

  for bucket in buckets:
    for arch in archs:
      for build_type in build_types:
        path = (f'{runtime_artifacts_bucket_url}/{bucket}_{arch}_{build_type}_'
                f'{android_version}.tar')
        if gs_context.Exists(path):
          variables[(f'{arch}_{build_type}_{bucket}').upper()] = (
              f'{runtime_artifacts_bucket_url}/{bucket}_{arch}_{build_type}_'
              f'{version_reference}.tar')

  return variables


def UpdateDataCollectorArtifacts(android_version,
                                 runtime_artifacts_bucket_url,
                                 build_branch):
  r"""Finds and includes into variables artifacts from arc.DataCollector.

  This verifies default android version. In case artificts are not found for
  default Android version it tries to find artifacts for pinned version. If
  pinned version is provided, it is required artifacts exist for the pinned
  version.

  Args:
    android_version: The \d+ build id of Android.
    runtime_artifacts_bucket_url: root of runtime artifacts
    build_branch: build branch. Used to determine the pinned version if exists.

  Returns:
    dictionary with filled ebuild variables.
  """

  gs_context = gs.GSContext()
  # Check the existing version. If we find any artifacts, use them.
  variables = FindDataCollectorArtifacts(gs_context,
                                         android_version,
                                         runtime_artifacts_bucket_url,
                                         '${PV}')
  if variables:
    # Data artificts were found.
    return variables

  # Check pinned version for the current branch.
  pin_path = (f'{runtime_artifacts_bucket_url}/{build_branch}_pin_version')
  if not gs_context.Exists(pin_path):
    # No pinned version.
    logging.warning(
        'No data collector artifacts were found for %s',
        android_version)
    return variables

  pin_version = gs_context.Cat(pin_path, encoding='utf-8').rstrip()
  logging.info('Pinned version %s overrides %s',
               pin_version, android_version)
  variables = FindDataCollectorArtifacts(gs_context,
                                         pin_version,
                                         runtime_artifacts_bucket_url,
                                         pin_version)
  if not variables:
    # If pin version set it must contain data.
    raise Exception('Pinned version %s:%s does not contain artificats' % (
        build_branch, pin_version))

  return variables


def MarkAndroidEBuildAsStable(stable_candidate, unstable_ebuild,
                              android_package, android_version, package_dir,
                              build_branch, arc_bucket_url,
                              runtime_artifacts_bucket_url):
  r"""Uprevs the Android ebuild.

  This is the main function that uprevs from a stable candidate
  to its new version.

  Args:
    stable_candidate: ebuild that corresponds to the stable ebuild we are
      revving from.  If None, builds the a new ebuild given the version
      with revision set to 1.
    unstable_ebuild: ebuild corresponding to the unstable ebuild for Android.
    android_package: android package name.
    android_version: The \d+ build id of Android.
    package_dir: Path to the android-container package dir.
    build_branch: branch of Android builds.
    arc_bucket_url: URL of the target ARC build gs bucket.
    runtime_artifacts_bucket_url: root of runtime artifacts

  Returns:
    Tuple[str, List[str], List[str]] if revved, or None
    1. Full portage version atom (including rc's, etc) that was revved.
    2. List of files to be `git add`ed.
    3. List of files to be `git rm`ed.
  """
  def IsTheNewEBuildRedundant(new_ebuild, stable_ebuild):
    """Returns True if the new ebuild is redundant.

    This is True if there if the current stable ebuild is the exact same copy
    of the new one.
    """
    if not stable_ebuild:
      return False

    if stable_candidate.version_no_rev == new_ebuild.version_no_rev:
      return filecmp.cmp(
          new_ebuild.ebuild_path, stable_ebuild.ebuild_path, shallow=False)
    return False

  # Case where we have the last stable candidate with same version just rev.
  if stable_candidate and stable_candidate.version_no_rev == android_version:
    new_ebuild_path = '%s-r%d.ebuild' % (
        stable_candidate.ebuild_path_no_revision,
        stable_candidate.current_revision + 1)
  else:
    pf = '%s-%s-r1' % (android_package, android_version)
    new_ebuild_path = os.path.join(package_dir, '%s.ebuild' % pf)

  build_targets = constants.ANDROID_BRANCH_TO_BUILD_TARGETS[build_branch]
  variables = {'BASE_URL': arc_bucket_url}
  for var, target in build_targets.items():
    variables[var] = f'{build_branch}-linux-{target}'

  variables.update(UpdateDataCollectorArtifacts(
      android_version, runtime_artifacts_bucket_url, build_branch))

  portage_util.EBuild.MarkAsStable(
      unstable_ebuild.ebuild_path, new_ebuild_path,
      variables, make_stable=True)
  new_ebuild = portage_util.EBuild(new_ebuild_path)

  # Determine whether this is ebuild is redundant.
  if IsTheNewEBuildRedundant(new_ebuild, stable_candidate):
    msg = 'Previous ebuild with same version found and ebuild is redundant.'
    logging.info(msg)
    cbuildbot_alerts.PrintBuildbotStepText('%s %s not revved'
                                  % (stable_candidate.pkgname,
                                     stable_candidate.version))
    osutils.SafeUnlink(new_ebuild_path)
    return None

  # PFQ runs should always be able to find a stable candidate.
  if stable_candidate:
    PrintUprevMetadata(build_branch, stable_candidate, new_ebuild)

  files_to_add = [new_ebuild_path]
  files_to_remove = []
  if stable_candidate and not stable_candidate.IsSticky():
    osutils.SafeUnlink(stable_candidate.ebuild_path)
    files_to_remove.append(stable_candidate.ebuild_path)

  # Update ebuild manifest and git add it.
  gen_manifest_cmd = ['ebuild', new_ebuild_path, 'manifest', '--force']
  cros_build_lib.run(gen_manifest_cmd, extra_env=None, print_cmd=True)
  files_to_add.append('Manifest')

  return (
      f'{new_ebuild.package}-{new_ebuild.version}',
      files_to_add,
      files_to_remove,
  )


def _PrepareGitBranch(overlay_dir):
  """Prepares a git branch for the uprev commit.

  If the overlay project is currently on a branch (e.g. patches are being
  applied), rebase the new branch on top of it.

  Args:
    overlay_dir: The overlay directory.
  """
  existing_branch = git.GetCurrentBranch(overlay_dir)
  repo_util.Repository.MustFind(overlay_dir).StartBranch(
      constants.STABLE_EBUILD_BRANCH, projects=['.'], cwd=overlay_dir)
  if existing_branch:
    git.RunGit(overlay_dir, ['rebase', existing_branch])


def _CommitChange(message, android_package_dir, files_to_add, files_to_remove):
  """Commit changes to git with list of files to add/remove."""
  git.RunGit(android_package_dir, ['add', '--'] + files_to_add)
  git.RunGit(android_package_dir, ['rm', '--'] + files_to_remove)

  portage_util.EBuild.CommitChange(message, android_package_dir)


def GetParser():
  """Creates the argument parser."""
  parser = commandline.ArgumentParser()
  parser.add_argument('-b', '--boards')
  parser.add_argument('--android_bucket_url',
                      default=android.ANDROID_BUCKET_URL,
                      type='gs_path')
  parser.add_argument('--android_build_branch',
                      choices=constants.ANDROID_BRANCH_TO_BUILD_TARGETS,
                      help='Android branch to import from, overriding default')
  parser.add_argument('--android_package',
                      required=True,
                      choices=constants.ANDROID_ALL_PACKAGES,
                      help='Android package to uprev')
  parser.add_argument('--arc_bucket_url',
                      default=constants.ARC_BUCKET_URL,
                      type='gs_path')
  parser.add_argument('-f', '--force_version',
                      help='Android build id to use')
  parser.add_argument('-s', '--srcroot',
                      default=os.path.join(os.environ['HOME'], 'trunk', 'src'),
                      help='Path to the src directory')
  parser.add_argument('--runtime_artifacts_bucket_url',
                      default=_RUNTIME_ARTIFACTS_BUCKET_URL,
                      type='gs_path')
  parser.add_argument('--skip_commit',
                      action='store_true',
                      help='Skip commiting uprev changes to git')
  return parser


def main(argv):
  cbuildbot_alerts.EnableBuildbotMarkers()
  parser = GetParser()
  options = parser.parse_args(argv)
  options.Freeze()

  overlay_dir = os.path.abspath(_OVERLAY_DIR % {'srcroot': options.srcroot})
  android_package_dir = os.path.join(
      overlay_dir,
      portage_util.GetFullAndroidPortagePackageName(options.android_package))

  # Use default Android branch if not overridden.
  android_build_branch = (
      options.android_build_branch or
      android.GetAndroidBranchForPackage(options.android_package))

  (unstable_ebuild, stable_ebuilds) = FindAndroidCandidates(android_package_dir)
  # Mirror artifacts, i.e., images and some sdk tools (e.g., adb, aapt).
  version_to_uprev = android.MirrorArtifacts(options.android_bucket_url,
                                             android_build_branch,
                                             options.arc_bucket_url,
                                             android_package_dir,
                                             options.force_version)

  stable_candidate = portage_util.BestEBuild(stable_ebuilds)

  if stable_candidate:
    logging.info('Stable candidate found %s', stable_candidate.version)
  else:
    logging.info('No stable candidate found.')

  if not options.skip_commit:
    _PrepareGitBranch(overlay_dir)

  revved = MarkAndroidEBuildAsStable(
      stable_candidate, unstable_ebuild, options.android_package,
      version_to_uprev, android_package_dir, android_build_branch,
      options.arc_bucket_url, options.runtime_artifacts_bucket_url)

  if revved:
    android_version_atom, files_to_add, files_to_remove = revved
    if not options.skip_commit:
      _CommitChange(
          _GIT_COMMIT_MESSAGE % {'android_package': options.android_package,
                                 'android_version': version_to_uprev},
          android_package_dir,
          files_to_add,
          files_to_remove,
      )
    if options.boards:
      cros_mark_as_stable.CleanStalePackages(options.srcroot,
                                             options.boards.split(':'),
                                             [android_version_atom])

    # Explicit print to communicate to caller.
    print('ANDROID_VERSION_ATOM=%s' % android_version_atom)
