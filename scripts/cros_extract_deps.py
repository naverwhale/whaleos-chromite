# Copyright 2010 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Command to extract the dependency tree for a given package.

This produces JSON output for other tools to process.
"""

from __future__ import absolute_import

import sys

from chromite.lib import build_target_lib
from chromite.lib import commandline
from chromite.lib.depgraph import DepGraphGenerator
from chromite.lib.parser import package_info
from chromite.utils import pformat


def FlattenDepTree(deptree, pkgtable=None, parentcpv=None):
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

    Returns:
        A flattened dependency tree.
    """
    if pkgtable is None:
        pkgtable = {}
    for cpv, record in deptree.items():
        if cpv not in pkgtable:
            pkg_info = package_info.parse(cpv)
            pkgtable[cpv] = {
                "deps": [],
                "rev_deps": [],
                "name": pkg_info.package,
                "category": pkg_info.category,
                "version": pkg_info.vr,
                "full_name": cpv,
                "action": record["action"],
            }

        # If we have a parent, that is a rev_dep for the current package.
        if parentcpv:
            pkgtable[cpv]["rev_deps"].append(parentcpv)
        # If current package has any deps, record those.
        for childcpv in record["deps"]:
            pkgtable[cpv]["deps"].append(childcpv)
        # Visit the subtree recursively as well.
        FlattenDepTree(record["deps"], pkgtable=pkgtable, parentcpv=cpv)
        # Sort 'deps' & 'rev_deps' alphabetically to make them more readable.
        pkgtable[cpv]["deps"].sort()
        pkgtable[cpv]["rev_deps"].sort()
    return pkgtable


def ParseArgs(argv):
    """Parse command line arguments."""
    parser = commandline.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--sysroot", type="path", help="Path to the sysroot.")
    target.add_argument("--board", help="Board name.")

    parser.add_argument(
        "--output-path", default=None, help="Write output to the given path."
    )
    parser.add_argument("pkgs", nargs="*")
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
        if v["action"] in ("merge", "nomerge"):
            continue
        elif v["action"] == "uninstall":
            obsolete_package_deps.append(k)
        else:
            assert False, "Unrecognized action. Package dep data: %s" % v
    for p in obsolete_package_deps:
        del package_deps[p]


def ExtractDeps(
    sysroot,
    package_list,
    include_bdepend=True,
    backtrack=True,
):
    """Returns the set of dependencies for the packages in package_list.

    For calculating dependencies graph, this should only consider packages
    that are DEPENDS, RDEPENDS, or BDEPENDS. Essentially, this should answer the
    question "which are all the packages which changing them may change the
    execution of any binaries produced by packages in |package_list|."

    Args:
        sysroot: the path (string) to the root directory into which the package
            is pretend to be merged. This value is also used for setting
            PORTAGE_CONFIGROOT.
        package_list: the list of packages (CP string) to extract their
            dependencies from.
        include_bdepend: Controls whether BDEPEND packages that would be
            installed to BROOT (usually "/" instead of ROOT) are included in the
            output.
        backtrack: Setting to False disables backtracking in Portage's
            dependency solver. If the highest available version of dependencies
            doesn't produce a solvable graph Portage will give up and return an
            error instead of trying other candidates.

    Returns:
        A JSON-izable object.
    """
    lib_argv = ["--quiet", "--pretend", "--emptytree"]
    if include_bdepend:
        lib_argv += ["--include-bdepend"]
    if not backtrack:
        lib_argv += ["--backtrack=0"]
    lib_argv += ["--sysroot=%s" % sysroot]
    lib_argv.extend(package_list)

    deps = DepGraphGenerator()
    deps.Initialize(lib_argv)

    deps_tree, _deps_info, bdeps_tree = deps.GenDependencyTree()
    trees = (deps_tree, bdeps_tree)

    flattened_trees = tuple(FlattenDepTree(x) for x in trees)

    # Workaround: since emerge doesn't honor the --emptytree flag, for now we
    # need to manually filter out packages that are obsolete (meant to be
    # uninstalled by emerge)
    # TODO(crbug.com/938605): remove this work around once
    # https://bugs.gentoo.org/681308 is addressed.
    for tree in flattened_trees:
        FilterObsoleteDeps(tree)

    return flattened_trees


def main(argv):
    opts = ParseArgs(argv)

    sysroot = opts.sysroot or build_target_lib.get_default_sysroot_path(
        opts.board
    )
    deps_list, _ = ExtractDeps(sysroot, opts.pkgs, opts.format)

    pformat.json(
        deps_list, fp=opts.output_path if opts.output_path else sys.stdout
    )
