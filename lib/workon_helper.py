# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Routines and a delegate for dealing with locally worked on packages."""

import collections
import glob
import logging
import os
from pathlib import Path
import re
from typing import Iterable

from chromite.lib import build_target_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import dependency_graph
from chromite.lib import git
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import sysroot_lib

if cros_build_lib.IsInsideChroot():
  from chromite.lib import depgraph

# A package is a canonical CP atom.
# A package may have 0 or more repositories, given as strings.
# Each repository may be mapped into our workspace at some path.
PackageInfo = collections.namedtuple('PackageInfo',
                                     ('package', 'repos', 'src_paths'))


def _IsWorkonEbuild(include_chrome, ebuild_path, ebuild_contents=None):
  """Returns True iff the ebuild at |ebuild_path| is a workon ebuild.

  This means roughly that the ebuild is compatible with our cros_workon based
  system.  For most packages, this means that it inherits the cros-workon
  overlay.

  Args:
    include_chrome: True iff we should include Chrome and chromium-source
        packages.
    ebuild_path: path an ebuild in question.
    ebuild_contents: None, or the contents of the ebuild at |ebuild_path|.
        If None, _IsWorkonEbuild will read the contents of the ebuild when
        necessary.

  Returns:
    True iff the ebuild can be used with cros_workon.
  """
  # TODO(rcui): remove special casing of chromeos-chrome here when we make it
  # inherit from cros-workon / chromium-source class (chromium-os:19259).
  if (include_chrome and
      portage_util.EbuildToCP(ebuild_path) == constants.CHROME_CP):
    return True

  workon_eclasses = 'cros-workon'
  if include_chrome:
    workon_eclasses += '|chromium-source'

  ebuild_contents = ebuild_contents or osutils.ReadFile(ebuild_path)
  if re.search('^inherit .*(%s)' % workon_eclasses,
               ebuild_contents, re.M):
    return True

  return False


def _GetLinesFromFile(path, line_prefix, line_suffix):
  """Get a unique set of lines from a file, stripping off a prefix and suffix.

  Rejects lines that do not start with |line_prefix| or end with |line_suffix|.
  Returns an empty set if the file at |path| does not exist.
  Discards duplicate lines.

  Args:
    path: path to file.
    line_prefix: prefix of line to look for and strip if found.
    line_suffix: suffix of line to look for and strip if found.

  Returns:
    A list of filtered lines from the file at |path|.
  """
  if not os.path.exists(path):
    return set()

  # Note that there is an opportunity to race with the file system here.
  lines = set()
  for line in osutils.ReadFile(path).splitlines():
    if not line.startswith(line_prefix) or not line.endswith(line_suffix):
      logging.warning('Filtering out malformed line: %s', line)
      continue
    lines.add(line[len(line_prefix):-len(line_suffix)])

  return lines


def _WriteLinesToFile(path, lines, line_prefix, line_suffix):
  """Write a set of lines to a file, adding prefixes, suffixes and newlines.

  Args:
    path: path to file.
    lines: iterable of lines to write.
    line_prefix: string to prefix each line with.
    line_suffix: string to append to each line before a newline.
  """
  contents = ''.join(
      ['%s%s%s\n' % (line_prefix, line, line_suffix) for line in lines])
  if not contents:
    osutils.SafeUnlink(path)
  else:
    osutils.WriteFile(path, contents, makedirs=True)


def GetWorkonPath(source_root=constants.CHROOT_SOURCE_ROOT, sub_path=None):
  """Get the path to files related to packages we're working locally on.

  Args:
    source_root: path to source root inside chroot.
    sub_path: optional path to file relative to the workon root directory.

  Returns:
    path to the workon root directory or file within the root directory.
  """
  ret = os.path.join(source_root, '.config/cros_workon')
  if sub_path:
    ret = os.path.join(ret, sub_path)

  return ret


class WorkonError(Exception):
  """Raised when invariants of the WorkonHelper are violated."""


def _FilterWorkonOnlyEbuilds(ebuilds):
  """Filter a list of ebuild paths to only with those no stable version.

  Args:
    ebuilds: list of string paths to ebuild files
        (e.g. ['/prefix/sys-app/app/app-9999.ebuild'])

  Returns:
    list of ebuild paths meeting this criterion.
  """
  result = []
  for ebuild_path in ebuilds:
    ebuild_pattern = os.path.join(os.path.dirname(ebuild_path), '*.ebuild')
    stable_ebuilds = [path for path in glob.glob(ebuild_pattern)
                      if not path.endswith('-9999.ebuild')]
    if not stable_ebuilds:
      result.append(ebuild_path)

  return result


def ListAllWorkedOnAtoms(src_root=constants.CHROOT_SOURCE_ROOT):
  """Get a list of all atoms we're currently working on.

  Args:
    src_root: path to source root inside chroot.

  Returns:
    Dictionary of atoms marked as worked on (e.g. ['chromeos-base/shill']) for
    each system.
  """
  workon_dir = GetWorkonPath(source_root=src_root)
  if not os.path.isdir(workon_dir):
    return dict()

  system_to_atoms = dict()
  for file_name in os.listdir(workon_dir):
    if file_name.endswith('.mask'):
      continue
    file_contents = osutils.ReadFile(os.path.join(workon_dir, file_name))

    atoms = []
    for line in file_contents.splitlines():
      match = re.match('=(.*)-9999', line)
      if match:
        atoms.append(match.group(1))
    if atoms:
      system_to_atoms[os.path.basename(file_name)] = atoms

  return system_to_atoms


class WorkonHelper(object):
  """Delegate that knows how to mark packages as being worked on locally.

  This class assumes that we're executing in the build root.
  """

  def __init__(self, sysroot, friendly_name=None, verbose=False,
               src_root=constants.CHROOT_SOURCE_ROOT):
    """Construct an instance.

    Args:
      sysroot: path to sysroot to work on packages within.
      friendly_name: friendly name of the system
          (e.g. 'host', <board name>, or a brick friendly name).
          Defaults to 'host' if sysroot is '/' or the last component of the
          sysroot path.
      verbose: boolean True iff we should print a lot more command output.
          This is intended for debugging, and you should never cause a script
          to depend on behavior enabled by this flag.
      src_root: path to source root inside chroot.
    """
    self._sysroot = sysroot
    if friendly_name:
      self._system = friendly_name
    else:
      self._system = ('host' if sysroot == '/'
                      else os.path.basename(sysroot.rstrip('/')))
    self._verbose = verbose
    self._src_root = src_root
    self._cached_overlays = None
    self._cached_arch = None
    self._depgraph = None

    profile = os.path.join(self._sysroot, 'etc', 'portage')
    self._unmasked_symlink = os.path.join(
        profile, 'package.unmask', 'cros-workon')
    self._keywords_symlink = os.path.join(
        profile, 'package.keywords', 'cros-workon')
    self._masked_symlink = os.path.join(
        profile, 'package.mask', 'cros-workon')

    # Clobber and re-create the WORKON_FILE symlinks every time. This is a
    # trivial operation and eliminates all kinds of corner cases as well as any
    # possible future renames of WORKON_FILE.
    # In particular, we build the chroot as a board (amd64-host), bundle it and
    # unpack it on /. After unpacking, the symlinks will point to
    # .config/cros_workon/amd64-host instead of .config/cros_workon/host.
    # Regenerating the symlinks here corrects it. crbug.com/23096.
    # Note: This is currently also relied upon as an indirect fix for
    # crbug.com/679831. Search the bug number for instance(s).
    self._RefreshSymlinks()

  @property
  def workon_file_path(self):
    """Returns path to the file holding our currently worked on atoms."""
    return GetWorkonPath(source_root=self._src_root, sub_path=self._system)

  @property
  def masked_file_path(self):
    """Returns path to file masking non-9999 ebuilds for worked on atoms."""
    return self.workon_file_path + '.mask'

  @property
  def _arch(self):
    if self._cached_arch is None:
      self._cached_arch = sysroot_lib.Sysroot(
          self._sysroot).GetStandardField(sysroot_lib.STANDARD_FIELD_ARCH)

    return self._cached_arch

  @property
  def _overlays(self):
    """Returns overlays installed for the selected system."""
    if self._cached_overlays is None:
      sysroot = sysroot_lib.Sysroot(self._sysroot)
      portdir_overlay = sysroot.GetStandardField('PORTDIR_OVERLAY')
      if portdir_overlay:
        self._cached_overlays = portdir_overlay.strip().splitlines()
      else:
        # This command is exceptionally slow, and we don't expect the list of
        # overlays to change during the lifetime of WorkonHelper.
        self._cached_overlays = portage_util.FindSysrootOverlays(self._sysroot)

    return self._cached_overlays

  def _SetWorkedOnAtoms(self, atoms):
    """Sets the unmasked atoms.

    This will generate both the unmasked atom list and the masked atoms list as
    the two files mention the same atom list.

    Args:
      atoms: Atoms to unmask.
    """
    _WriteLinesToFile(self.workon_file_path, atoms, '=', '-9999')
    _WriteLinesToFile(self.masked_file_path, atoms, '<', '-9999')
    self._RefreshSymlinks()

  def _RefreshSymlinks(self):
    """Recreates the symlinks.

    This will create the three symlinks needed:
    * package.mask/cros-workon: list of packages to mask.
    * package.unmask/cros-workon: list of packages to unmask.
    * package.keywords/cros-workon: list of hidden packages to accept.
    """
    if not os.path.exists(self._sysroot):
      return

    for target, symlink in ((self.masked_file_path, self._masked_symlink),
                            (self.workon_file_path, self._unmasked_symlink),
                            (self.workon_file_path, self._keywords_symlink)):
      if os.path.exists(target):
        osutils.SafeMakedirs(os.path.dirname(symlink), sudo=True)
        osutils.SafeSymlink(target, symlink, sudo=True)
      else:
        logging.debug("Symlink %s already exists. Don't recreate it.",
                      symlink)

  def _AtomsToEbuilds(self, atoms):
    """Maps from a list of CP atoms to a list of corresponding -9999 ebuilds.

    Args:
      atoms: iterable of portage atoms (e.g. ['sys-apps/dbus']).

    Returns:
      list of ebuilds corresponding to those atoms.
    """
    atoms_to_ebuilds = dict([(atom, None) for atom in atoms])

    for overlay in self._overlays:
      ebuild_paths = glob.glob(
          os.path.join(overlay, '*-*', '*', '*-9999.ebuild'))
      for ebuild_path in ebuild_paths:
        atom = portage_util.EbuildToCP(ebuild_path)
        if atom in atoms_to_ebuilds:
          atoms_to_ebuilds[atom] = ebuild_path

    ebuilds = []
    for atom, ebuild in atoms_to_ebuilds.items():
      if ebuild is None:
        raise WorkonError('Could not find ebuild for atom %s' % atom)
      ebuilds.append(ebuild)

    return ebuilds

  def _GetCanonicalAtom(self, package_fragment: str, find_stale=False):
    """Transform a package source path or name fragment to the canonical atom.

    If there are multiple atoms that a package fragment could map to,
    picks an arbitrary one and prints a warning.

    Args:
      package_fragment: Package source path or name fragment.
      find_stale: if True, allow stale (missing) worked on package.

    Returns:
      string canonical atom name (e.g. 'sys-apps/dbus')
    """
    # Attempt to not hit portage if at all possible for speed.
    if package_fragment in self._GetWorkedOnAtoms():
      return package_fragment

    # Ask portage directly what it thinks about that package.
    ebuild_path = self._FindEbuildForPackage(package_fragment)

    # If portage didn't know about that package, try and autocomplete it.
    if ebuild_path is None:
      possible_ebuilds = set()
      for ebuild in (portage_util.EbuildToCP(ebuild) for ebuild in
                     self._GetWorkonEbuilds(filter_on_arch=False)):
        if package_fragment in ebuild:
          possible_ebuilds.add(ebuild)

      # Also autocomplete from the worked-on list, in case the ebuild was
      # deleted.
      if find_stale:
        for ebuild in self._GetWorkedOnAtoms():
          if package_fragment in ebuild:
            possible_ebuilds.add(ebuild)

      if not possible_ebuilds:
        # Try finding the packages affected by a given path.
        path_atoms = sorted(self._GetPathAtoms(package_fragment))
        if not path_atoms:
          logging.warning('Could not find canonical package for "%s"',
                          package_fragment)
          return None

        if len(path_atoms) > 1:
          logging.warning('Multiple affected packages found for %s:',
                          package_fragment)
          for p in path_atoms:
            logging.warning('  %s', p)
          logging.warning('Using %s', path_atoms[0])
          logging.notice(
              'cros workon start command for the rest of the packages:')
          logging.notice(
              f'cros workon -b {self._system} start {" ".join(path_atoms[1:])}')

        logging.notice('Package %s found for path %s', path_atoms[0],
                       package_fragment)
        return path_atoms[0]

      # We want some consistent order for making our selection below.
      possible_ebuilds = sorted(possible_ebuilds)

      if len(possible_ebuilds) > 1:
        logging.warning('Multiple autocompletes found:')
        for possible_ebuild in possible_ebuilds:
          logging.warning('  %s', possible_ebuild)
      autocompleted_package = portage_util.EbuildToCP(possible_ebuilds[0])
      # Sanity check to avoid infinite loop.
      if package_fragment == autocompleted_package:
        logging.error('Resolved %s to itself', package_fragment)
        return None
      logging.info('Autocompleted "%s" to: "%s"',
                   package_fragment, autocompleted_package)

      return self._GetCanonicalAtom(autocompleted_package)

    if not _IsWorkonEbuild(True, ebuild_path):
      msg = ('In order to cros_workon a package, it must have a -9999 ebuild '
             'that inherits from cros-workon.\n')
      if '-9999' in ebuild_path:
        msg += ('"%s" is a -9999 ebuild, make sure it inherits from '
                'cros-workon.\n' % ebuild_path)
      else:
        msg += '"%s" is not a -9999 ebuild.\n' % ebuild_path

      logging.warning(msg)
      return None

    return portage_util.EbuildToCP(ebuild_path)

  def _GetCanonicalAtoms(self,
                         package_fragments: Iterable[str],
                         find_stale=False):
    """Transforms a list of package name fragments into a list of CP atoms.

    Args:
      package_fragments: list of package source paths and/or name fragments.
      find_stale: if True, allow stale (missing) worked on package.

    Returns:
      list of canonical portage atoms corresponding to the given fragments.
    """
    if not package_fragments:
      raise WorkonError('No packages specified')

    atoms = []
    for package_fragment in package_fragments:
      atom = self._GetCanonicalAtom(package_fragment, find_stale=find_stale)
      if atom is None:
        raise WorkonError('Error parsing package list')
      atoms.append(atom)

    return atoms

  def _GetDepGraph(self):
    """Get the dependency graph."""
    if self._depgraph:
      return self._depgraph

    try:
      # Get the graph for our target.
      if self._sysroot == build_target_lib.get_default_sysroot_path():
        self._depgraph = depgraph.get_sdk_dependency_graph(with_src_paths=True)
      else:
        self._depgraph = depgraph.get_build_target_dependency_graph(
            self._sysroot, with_src_paths=True)
    except dependency_graph.Error as e:
      logging.error(e)
      raise WorkonError('Error generating dependency graph.')

    return self._depgraph

  def _GetPathAtoms(self, raw_path) -> Iterable:
    """Get workon atoms affected by the current path."""
    # Make sure we're in a source path.
    path = Path(raw_path).resolve()
    if not path.exists():
      # The path doesn't exist. To avoid the long lookup when the dev misspells
      # a package name, lets just assume it's that and return no packages.
      logging.warning('%s (%s) does not exist. Is it a misspelled package?',
                      path, raw_path)
      return []

    try:
      path = path.relative_to(constants.SOURCE_ROOT)
    except ValueError as e:
      logging.error(e)
      raise WorkonError(
          f'Current path not in the source root: '
          f'{path} not in {constants.SOURCE_ROOT}'
      )

    graph = self._GetDepGraph()
    # Get the relevant packages from the dep graph.
    logging.debug('Getting packages relevant to %s', path)
    relevant_atoms = set(x.atom for x in graph.get_relevant_nodes([path]))

    if not relevant_atoms:
      return []

    logging.debug('Found relevant packages: %s', relevant_atoms)

    # Filter out any non-cros-workon packages.
    canonical = [self._GetCanonicalAtom(x) for x in relevant_atoms]
    workon_atoms = [x for x in canonical if x]

    logging.debug('Found relevant workon packages: %s', workon_atoms)

    return workon_atoms

  def _GetWorkedOnAtoms(self):
    """Returns a list of CP atoms that we're currently working on."""
    return _GetLinesFromFile(self.workon_file_path, '=', '-9999')

  def _FindEbuildForPackage(self, package):
    """Find an ebuild for a given atom (accepting even masked ebuilds).

    Args:
      package: package string.

    Returns:
      path to ebuild for given package.
    """
    return portage_util.FindEbuildForPackage(
        package, self._sysroot, include_masked=True,
        extra_env={'ACCEPT_KEYWORDS': '~%s' % self._arch})

  def _GetWorkonEbuilds(self, filter_workon=False, filter_on_arch=True,
                        include_chrome=True):
    """Get a list of all cros-workon ebuilds in the current system.

    Args:
      filter_workon: True iff we should filter the list of ebuilds to those
          packages which define only a workon ebuild (i.e. no stable version).
      filter_on_arch: True iff we should only return ebuilds which are marked
          as unstable for the architecture of the system we're interested in.
      include_chrome: True iff we should also include chromeos-chrome and
          related ebuilds.  These ebuilds can be worked on, but don't work
          like normal cros-workon ebuilds.

    Returns:
      list of paths to ebuilds meeting the above criteria.
    """
    result = []
    if filter_on_arch:
      keyword_pat = re.compile(r'^KEYWORDS=".*~(\*|%s).*"$' % self._arch, re.M)

    for overlay in self._overlays:
      ebuild_paths = glob.glob(
          os.path.join(overlay, '*-*', '*', '*-9999.ebuild'))
      for ebuild_path in ebuild_paths:
        ebuild_contents = osutils.ReadFile(ebuild_path)
        if not _IsWorkonEbuild(include_chrome, ebuild_path,
                               ebuild_contents=ebuild_contents):
          continue
        if filter_on_arch and not keyword_pat.search(ebuild_contents):
          continue
        result.append(ebuild_path)

    if filter_workon:
      result = _FilterWorkonOnlyEbuilds(result)

    return result

  def _GetLiveAtoms(self, filter_workon=False):
    """Get a list of atoms currently marked as being locally compiled.

    Args:
      filter_workon: True iff the list should be filtered to only those
          atoms without a stable version (i.e. the -9999 ebuild is the
          only ebuild).

    Returns:
      list of canonical portage atoms.
    """
    atoms = self._GetWorkedOnAtoms()

    if filter_workon:
      ebuilds = _FilterWorkonOnlyEbuilds(self._AtomsToEbuilds(atoms))
      return [portage_util.EbuildToCP(ebuild) for ebuild in ebuilds]

    return atoms

  def _AddProjectsToPartialManifests(self, atoms):
    """Add projects corresponding to a list of atoms to the local manifest.

    If we mark projects as workon that we don't have in our local checkout,
    it is convenient to have them added to the manifest.  Note that users
    will need to `repo sync` to pull down repositories added in this way.

    Args:
      atoms: iterable of atoms to ensure are in the manifest.
    """
    if git.ManifestCheckout.IsFullManifest(self._src_root):
      # If we're a full manifest, there is nothing to do.
      return

    should_repo_sync = False
    for ebuild_path in self._AtomsToEbuilds(atoms):
      infos = portage_util.GetRepositoryForEbuild(ebuild_path, self._sysroot)
      for info in infos:
        if not info.project:
          continue
        cmd = ['loman', 'add', '--workon', info.project]
        cros_build_lib.run(cmd, print_cmd=False)
        should_repo_sync = True

    if should_repo_sync:
      print('Please run "repo sync" now.')

  def ListAtoms(self, use_all=False, use_workon_only=False):
    """Returns a list of interesting atoms.

    By default, return a list of the atoms marked as being locally worked on
    for the system in question.

    Args:
      use_all: If true, return a list of all atoms we could possibly work on
          for the system in question.
      use_workon_only: If true, return a list of all atoms we could possibly
          work on that have no stable ebuild.

    Returns:
      a list of atoms (e.g. ['chromeos-base/shill', 'sys-apps/dbus']).
    """
    if use_workon_only or use_all:
      ebuilds = self._GetWorkonEbuilds(filter_workon=use_workon_only)
      packages = [portage_util.EbuildToCP(ebuild) for ebuild in ebuilds]
    else:
      packages = self._GetLiveAtoms()

    return sorted(packages)

  def StartWorkingOnPackages(self,
                             packages,
                             use_all: bool = False,
                             use_workon_only: bool = False,
                             quiet: bool = False):
    """Mark a list of packages as being worked on locally.

    Args:
      packages: list of package name fragments. While each fragment could be a
          complete portage atom, this helper will attempt to infer intent by
          looking for fragments in a list of all possible atoms for the system
          in question.
      use_all: True iff we should ignore the package list, and instead consider
          all possible atoms that we could mark as worked on locally.
      use_workon_only: True iff we should ignore the package list, and instead
          consider all possible atoms for the system in question that define
          only the -9999 ebuild.
      quiet: Does not log the started atoms when True. Used to avoid confusion
          in cases where the list must be toggled to compute the new packages.
    """
    if not os.path.exists(self._sysroot):
      raise WorkonError('Sysroot %s is not setup.' % self._sysroot)

    if use_all or use_workon_only:
      ebuilds = self._GetWorkonEbuilds(filter_workon=use_workon_only)
      atoms = [portage_util.EbuildToCP(ebuild) for ebuild in ebuilds]
    else:
      atoms = self._GetCanonicalAtoms(packages)
    atoms = set(atoms)

    # Read out what atoms we're already working on.
    existing_atoms = self._GetWorkedOnAtoms()

    # Warn the user if they're requested to work on an atom that's already
    # marked as being worked on.
    for atom in atoms & existing_atoms:
      logging.warning('Already working on %s', atom)

    # If we have no new atoms to work on, we can quit now.
    new_atoms = atoms - existing_atoms
    if not new_atoms:
      return

    # Write out all these atoms to the appropriate files.
    current_atoms = new_atoms | existing_atoms
    self._SetWorkedOnAtoms(current_atoms)

    self._AddProjectsToPartialManifests(new_atoms)

    if not quiet:
      # Legacy scripts used single quotes in their output, and we carry on this
      # honorable tradition.
      logging.info("Started working on '%s' for '%s'",
                   ' '.join(new_atoms), self._system)

  def StopWorkingOnPackages(self,
                            packages,
                            use_all: bool = False,
                            use_workon_only: bool = False,
                            quiet: bool = False):
    """Stop working on a list of packages currently marked as locally worked on.

    Args:
      packages: list of package name fragments.  These will be mapped to
          canonical portage atoms via the same process as
          StartWorkingOnPackages().
      use_all: True iff instead of the provided package list, we should just
          stop working on all currently worked on atoms for the system in
          question.
      use_workon_only: True iff instead of the provided package list, we should
          stop working on all currently worked on atoms that define only a
          -9999 ebuild.
      quiet: Does not log the started atoms when True. Used to avoid confusion
          in cases where the list must be toggled to compute the new packages.
    """
    if use_all or use_workon_only:
      atoms = self._GetLiveAtoms(filter_workon=use_workon_only)
    else:
      atoms = self._GetCanonicalAtoms(packages, find_stale=True)

    current_atoms = self._GetWorkedOnAtoms()
    stopped_atoms = []
    for atom in atoms:
      if not atom in current_atoms:
        logging.warning('Not working on %s', atom)
        continue

      current_atoms.discard(atom)
      stopped_atoms.append(atom)

    self._SetWorkedOnAtoms(current_atoms)

    if stopped_atoms and not quiet:
      # Legacy scripts used single quotes in their output, and we carry on this
      # honorable tradition.
      logging.info("Stopped working on '%s' for '%s'",
                   ' '.join(stopped_atoms), self._system)

  def GetPackageInfo(self, packages, use_all=False, use_workon_only=False):
    """Get information about packages.

    Args:
      packages: list of package name fragments.  These will be mapped to
          canonical portage atoms via the same process as
          StartWorkingOnPackages().
      use_all: True iff we should ignore the package list, and instead consider
          all possible workon-able atoms.
      use_workon_only: True iff we should ignore the package list, and instead
          consider all possible atoms for the system in question that define
          only the -9999 ebuild.

    Returns:
      Returns a list of PackageInfo tuples.
    """
    if use_all or use_workon_only:
      # You can't use info to find the source code from Chrome, since that
      # workflow is different.
      ebuilds = self._GetWorkonEbuilds(filter_workon=use_workon_only,
                                       include_chrome=False)
    else:
      atoms = self._GetCanonicalAtoms(packages)
      ebuilds = [self._FindEbuildForPackage(atom) for atom in atoms]

    build_root = self._src_root
    src_root = os.path.join(build_root, 'src')
    manifest = git.ManifestCheckout.Cached(build_root)

    ebuild_to_repos = {}
    ebuild_to_src_paths = collections.defaultdict(list)

    for ebuild in ebuilds:
      workon_vars = portage_util.EBuild.GetCrosWorkonVars(
          ebuild, portage_util.EbuildToCP(ebuild))
      projects = workon_vars.project if workon_vars else []
      ebuild_to_repos[ebuild] = projects
      ebuild_obj = portage_util.EBuild(ebuild)
      if ebuild_obj.is_manually_uprevved:
        # Manually uprevved ebuild is pinned to a specific git sha1, so change
        # in that repo matter to the ebuild.
        continue
      src_paths = ebuild_obj.GetSourceInfo(src_root, manifest).srcdirs
      src_paths = [os.path.relpath(path, build_root) for path in src_paths]
      ebuild_to_src_paths[ebuild] = src_paths

    result = []
    for ebuild in ebuilds:
      package = portage_util.EbuildToCP(ebuild)
      repos = ebuild_to_repos.get(ebuild, [])
      src_paths = ebuild_to_src_paths.get(ebuild, [])
      result.append(PackageInfo(package, repos, src_paths))

    result.sort()
    return result

  def RunCommandInAtomSourceDirectory(self, atom, command):
    """Run a command in the source directory of an atom.

    Args:
      atom: string atom to run the command in (e.g. 'chromeos-base/shill').
      command: string shell command to run in the source directory of |atom|.
    """
    logging.info('Running "%s" on %s', command, atom)
    ebuild_path = self._FindEbuildForPackage(atom)
    if ebuild_path is None:
      raise WorkonError('Error looking for atom %s' % atom)

    for info in portage_util.GetRepositoryForEbuild(ebuild_path, self._sysroot):
      cros_build_lib.run(command, shell=True, cwd=info.srcdir, print_cmd=False)

  def RunCommandInPackages(self, packages, command, use_all=False,
                           use_workon_only=False):
    """Run a command in the source directory of a list of packages.

    Args:
      packages: list of package name fragments.
      command: string shell command to run in the source directory of |atom|.
      use_all: True iff we should ignore the package list, and instead consider
          all possible workon-able atoms.
      use_workon_only: True iff we should ignore the package list, and instead
          consider all possible atoms for the system in question that define
          only the -9999 ebuild.
    """
    if use_all or use_workon_only:
      atoms = self._GetLiveAtoms(filter_workon=use_workon_only)
    else:
      atoms = self._GetCanonicalAtoms(packages)
    for atom in atoms:
      self.RunCommandInAtomSourceDirectory(atom, command)

  def InstalledWorkonAtoms(self):
    """Returns the set of installed cros_workon packages."""
    installed_cp = set()
    for pkg in portage_util.PortageDB(self._sysroot).InstalledPackages():
      installed_cp.add('%s/%s' % (pkg.category, pkg.package))

    return set(a for a in self.ListAtoms(use_all=True) if a in installed_cp)


class WorkonScope:
  """Context manager to assist managing workon status for packages."""

  def __init__(self, build_target: build_target_lib.BuildTarget,
               pkgs: Iterable[str] = tuple()):
    """Construct an instance.

    Args:
      build_target: The build target (board) being built.
      pkgs: The workon packages to be used in the context manager dunder
            methods.
    """
    self.helper = WorkonHelper(build_target.root, build_target.name)
    self.pkgs = pkgs
    self.target = build_target
    self.stop_packages = []
    self.start_packages = []
    self.before_workon = self.helper.ListAtoms()

  def __enter__(self: 'WorkonScope') -> 'WorkonScope':
    """Commence context manager tasks for starting and stopping packages.

    Returns:
      The initialized WorkonScope context manager.
    """
    self.start(self.pkgs)
    after_workon = self.helper.ListAtoms()

    # Stop = the set we actually started. Preserves workon started status for
    # any in the packages that were already worked on.
    self.stop_packages = sorted(set(after_workon) - set(self.before_workon))
    return self

  def __exit__(self, exc_type, exc_val, tb):
    """Clean up context manager tasks for starting and stopping packages.

    Args:
      exc_type: The exception type passed when the runtime context raises an
        exception.
      exc_val: The exception value raised by the runtime context.
      tb: The exception traceback raised by the runtime context.

    Raises:
      Any exception raised in the runtime context will be raised here after
      cleanup. Beyond that, all WorkonHelper methods are expected to be safe
      operations.
    """
    # Reset the environment.
    logging.notice('Restoring cros_workon status.')
    if self.stop_packages:
      # Stop the packages we started.
      logging.info('Stopping workon packages previously started.')
      try:
        self.stop(self.stop_packages)
      except WorkonError:
        to_stop = sorted(set(self.stop_packages) -
                         set(self.helper.ListAtoms()))
        logging.critical('Unable to stop started packages. Please stop the '
                         'following packages: %s', ' '.join(to_stop))
    else:
      logging.info('No packages needed to be stopped.')
    if self.start_packages:
      # Stop the packages we started.
      logging.info('Restarting workon packages previously stopped.')
      try:
        self._start_packages(self.start_packages)
      except WorkonError:
        to_start = sorted(set(self.start_packages) -
                          set(self.helper.ListAtoms()))
        logging.critical('Unable to start stopped packages. Please start the '
                         'following packages: %s', ' '.join(to_start))
    else:
      logging.info('No packages needed to be restarted.')

  def _start_packages(self, pkgs: Iterable[str]):
    """Wrapper for self.WorkonHelper.StartWorkingOnPackages."""
    self.helper.StartWorkingOnPackages(pkgs)

  def _stop_packages(self, pkgs: Iterable[str]):
    self.helper.StopWorkingOnPackages(pkgs)

  def start(self, pkgs: Iterable[str]):
    """Helper method to allow the context manager to explicitly start packages.

    Invocations of this method will track started packages and stop them when
    __exit__ is invoked, even when explicitly called by a client in a runtime
    context.

    Args:
      pkgs: A list of package name fragments.
    """
    if pkgs:
      logging.debug('cros-workon-%s start %s', self.target.name,
                    ' '.join(pkgs))
      self._start_packages(pkgs)
      after_workon = self.helper.ListAtoms()
      self.stop_packages = sorted(set(after_workon) - set(self.before_workon))


  def stop(self, pkgs: Iterable[str]):
    """Helper method to allow the context manager to explicitly stop packages.

    If a package is stopped that was marked as workon before entering the
    runtime context, that package will be restarted on exit.

    Args:
      pkgs: A list of package name fragments.
    """
    if pkgs:
      logging.debug('cros-workon-%s stop %s', self.target.name,
                    ' '.join(pkgs))
      self._stop_packages(pkgs)
      to_restart = set(pkgs) & set(self.before_workon)
      self.start_packages = sorted(to_restart | set(self.start_packages))
