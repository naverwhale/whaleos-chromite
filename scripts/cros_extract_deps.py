# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Command to extract the dependancy tree for a given package.

This produces JSON output for other tools to process.
"""

from __future__ import absolute_import

import logging
import sys

from chromite.lib import build_target_lib
from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import sysroot_lib
from chromite.lib.depgraph import DepGraphGenerator
from chromite.lib.parser import package_info
from chromite.utils import pformat


def FlattenDepTree(deptree, pkgtable=None, parentcpv=None, get_cpe=False):
  """Simplify dependency json.

Turn something like this (the parallel_emerge DepsTree format):
{
  "app-admin/eselect-1.2.9": {
    "action": "merge",
    "deps": {
      "sys-apps/coreutils-7.5-r1": {
        "action": "merge",
        "deps": {},
        "deptype": "runtime"
      },
      ...
    }
  }
}
  ...into something like this (the cros_extract_deps format):
{
  "app-admin/eselect-1.2.9": {
    "deps": ["coreutils-7.5-r1"],
    "rev_deps": [],
    "name": "eselect",
    "category": "app-admin",
    "version": "1.2.9",
    "full_name": "app-admin/eselect-1.2.9",
    "action": "merge"
  },
  "sys-apps/coreutils-7.5-r1": {
    "deps": [],
    "rev_deps": ["app-admin/eselect-1.2.9"],
    "name": "coreutils",
    "category": "sys-apps",
    "version": "7.5-r1",
    "full_name": "sys-apps/coreutils-7.5-r1",
    "action": "merge"
  }
}

  Args:
    deptree: The dependency tree.
    pkgtable: The package table to update. If None, create a new one.
    parentcpv: The parent CPV.
    get_cpe: If set True, include CPE in the flattened dependency tree.

  Returns:
    A flattened dependency tree.
  """
  if pkgtable is None:
    pkgtable = {}
  for cpv, record in deptree.items():
    if cpv not in pkgtable:
      split = package_info.SplitCPV(cpv)
      pkgtable[cpv] = {'deps': [],
                       'rev_deps': [],
                       'name': split.package,
                       'category': split.category,
                       'version': '%s' % split.version,
                       'full_name': cpv,
                       'cpes': [],
                       'action': record['action']}
      if get_cpe:
        pkgtable[cpv]['cpes'].extend(GetCPEFromCPV(
            split.category, split.package, split.version_no_rev))

    # If we have a parent, that is a rev_dep for the current package.
    if parentcpv:
      pkgtable[cpv]['rev_deps'].append(parentcpv)
    # If current package has any deps, record those.
    for childcpv in record['deps']:
      pkgtable[cpv]['deps'].append(childcpv)
    # Visit the subtree recursively as well.
    FlattenDepTree(record['deps'], pkgtable=pkgtable, parentcpv=cpv,
                   get_cpe=get_cpe)
    # Sort 'deps' & 'rev_deps' alphabetically to make them more readable.
    pkgtable[cpv]['deps'].sort()
    pkgtable[cpv]['rev_deps'].sort()
  return pkgtable


def GetCPEFromCPV(category, package, version):
  """Look up the CPE for a specified Portage package.

  Args:
    category: The Portage package's category, e.g. "net-misc"
    package: The Portage package's name, e.g. "curl"
    version: The Portage version, e.g. "7.30.0"

  Returns:
    A list of CPE Name strings, e.g.
    ["cpe:/a:curl:curl:7.30.0", "cpe:/a:curl:libcurl:7.30.0"]
  """
  equery_cmd = ['equery', 'm', '-U', '%s/%s' % (category, package)]
  lines = cros_build_lib.run(equery_cmd, check=False, print_cmd=False,
                             stdout=True, encoding='utf-8').stdout.splitlines()
  # Look for lines like "Remote-ID:   cpe:/a:kernel:linux-pam ID: cpe"
  # and extract the cpe URI.
  cpes = []
  for line in lines:
    if 'ID: cpe' not in line:
      continue
    cpes.append('%s:%s' % (line.split()[1], version.replace('_', '')))
  # Note that we're assuming we can combine the root of the CPE, taken
  # from metadata.xml, and tack on the version number as used by
  # Portage, and come up with a legitimate CPE. This works so long as
  # Portage and CPE agree on the precise formatting of the version
  # number, which they almost always do. The major exception we've
  # identified thus far is that our ebuilds have a pattern of inserting
  # underscores prior to patchlevels, that neither upstream nor CPE
  # use. For example, our code will decide we have
  # cpe:/a:todd_miller:sudo:1.8.6_p7 yet the advisories use a format
  # like cpe:/a:todd_miller:sudo:1.8.6p7, without the underscore. (CPE
  # is "right" in this example, in that it matches www.sudo.ws.)
  #
  # Removing underscores seems to improve our chances of correctly
  # arriving at the CPE used by NVD. However, at the end of the day,
  # ebuild version numbers are rev'd by people who don't have "try to
  # match NVD" as one of their goals, and there is always going to be
  # some risk of minor formatting disagreements at the version number
  # level, if not from stray underscores then from something else.
  #
  # This is livable so long as you do some fuzzy version number
  # comparison in your vulnerability monitoring, between what-we-have
  # and what-the-advisory-says-is-affected.
  return cpes


def GenerateCPEList(deps_list, sysroot):
  """Generate all CPEs for the packages included in deps_list and SDK packages

  Args:
    deps_list: A flattened dependency tree (cros_extract_deps format).
    sysroot: The board directory to use when finding SDK packages.

  Returns:
    A list of CPE info for packages in deps_list and SDK packages, e.g.
    [
      {
        "ComponentName": "app-admin/sudo",
        "Repository": "cros",
        "Targets": [
          "cpe:/a:todd_miller:sudo:1.8.19p2"
        ]
      },
      {
        "ComponentName": "sys-libs/glibc",
        "Repository": "cros",
        "Targets": [
          "cpe:/a:gnu:glibc:2.23"
        ]
      }
    ]
  """
  cpe_dump = []

  # Generate CPEs for SDK packages.
  for pkg_info in sorted(
      sysroot_lib.get_sdk_provided_packages(sysroot), key=lambda x: x.cpvr):
    # Only add CPE for SDK CPVs missing in deps_list.
    if deps_list.get(pkg_info.cpvr) is not None:
      continue

    cpes = GetCPEFromCPV(pkg_info.category, pkg_info.package, pkg_info.version)
    if cpes:
      cpe_dump.append({'ComponentName': '%s' % pkg_info.atom,
                       'Repository': 'cros',
                       'Targets': sorted(cpes)})
    else:
      logging.warning('No CPE entry for %s', pkg_info.cpvr)

  # Generage CPEs for packages in deps_list.
  for cpv, record in sorted(deps_list.items()):
    if record['cpes']:
      name = '%s/%s' % (record['category'], record['name'])
      cpe_dump.append({'ComponentName': name,
                       'Repository': 'cros',
                       'Targets': sorted(record['cpes'])})
    else:
      logging.warning('No CPE entry for %s', cpv)
  return sorted(cpe_dump, key=lambda k: k['ComponentName'])


def ParseArgs(argv):
  """Parse command line arguments."""
  parser = commandline.ArgumentParser(description=__doc__)
  target = parser.add_mutually_exclusive_group()
  target.add_argument('--sysroot', type='path', help='Path to the sysroot.')
  target.add_argument('--board', help='Board name.')

  parser.add_argument('--format', default='deps',
                      choices=['deps', 'cpe'],
                      help='Output either traditional deps or CPE-only JSON.')
  parser.add_argument('--output-path', default=None,
                      help='Write output to the given path.')
  parser.add_argument('pkgs', nargs='*')
  opts = parser.parse_args(argv)
  opts.Freeze()
  return opts


def FilterObsoleteDeps(package_deps):
  """Remove all the packages that are to be uninstalled from |package_deps|.

  Returns:
    None since this method mutates |package_deps| directly.
  """
  obsolete_package_deps = []
  for k, v in package_deps.items():
    if v['action'] in ('merge', 'nomerge'):
      continue
    elif v['action'] == 'uninstall':
      obsolete_package_deps.append(k)
    else:
      assert False, (
          'Unrecognized action. Package dep data: %s' % v)
  for p in obsolete_package_deps:
    del package_deps[p]


def ExtractDeps(sysroot,
                package_list,
                formatting='deps',
                include_bdepend=True,
                backtrack=True):
  """Returns the set of dependencies for the packages in package_list.

  For calculating dependencies graph, this should only consider packages
  that are DEPENDS, RDEPENDS, or BDEPENDS. Essentially, this should answer the
  question "which are all the packages which changing them may change the
  execution of any binaries produced by packages in |package_list|."

  Args:
    sysroot: the path (string) to the root directory into which the package is
      pretend to be merged. This value is also used for setting
      PORTAGE_CONFIGROOT.
    package_list: the list of packages (CP string) to extract their dependencies
      from.
    formatting: can either be 'deps' or 'cpe'. For 'deps', see the return
      format in docstring of FlattenDepTree, for 'cpe', see the return format in
      docstring of GenerateCPEList.
    include_bdepend: Controls whether BDEPEND packages that would be installed
      to BROOT (usually "/" instead of ROOT) are included in the output.
    backtrack: Setting to False disables backtracking in Portage's dependency
      solver. If the highest available version of dependencies doesn't produce
      a solvable graph Portage will give up and return an error instead of
      trying other candidates.

  Returns:
    A JSON-izable object that either follows 'deps' or 'cpe' format.
  """
  lib_argv = ['--quiet', '--pretend', '--emptytree']
  if include_bdepend:
    lib_argv += ['--include-bdepend']
  if not backtrack:
    lib_argv += ['--backtrack=0']
  lib_argv += ['--sysroot=%s' % sysroot]
  lib_argv.extend(package_list)

  deps = DepGraphGenerator()
  deps.Initialize(lib_argv)

  deps_tree, _deps_info, bdeps_tree = deps.GenDependencyTree()
  trees = (deps_tree, bdeps_tree)

  flattened_trees = tuple(
      FlattenDepTree(tree, get_cpe=(formatting == 'cpe')) for tree in trees)

  # Workaround: since emerge doesn't honor the --emptytree flag, for now we need
  # to manually filter out packages that are obsolete (meant to be
  # uninstalled by emerge)
  # TODO(crbug.com/938605): remove this work around once
  # https://bugs.gentoo.org/681308 is addressed.
  for tree in flattened_trees:
    FilterObsoleteDeps(tree)

  if formatting == 'cpe':
    flattened_trees = tuple(
        GenerateCPEList(tree, sysroot) for tree in flattened_trees)
  return flattened_trees


def main(argv):
  opts = ParseArgs(argv)

  sysroot = (opts.sysroot or
             build_target_lib.get_default_sysroot_path(opts.board))
  deps_list, _ = ExtractDeps(sysroot, opts.pkgs, opts.format)

  pformat.json(deps_list,
               fp=opts.output_path if opts.output_path else sys.stdout)
