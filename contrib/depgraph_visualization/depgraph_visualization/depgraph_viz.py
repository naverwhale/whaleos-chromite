# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Command to visualize dependency tree for a given package."""

import subprocess
import sys
from typing import Dict, List

from chromite.lib import build_target_lib
from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import json_lib

from . import visualize


_DEFAULT_PACKAGES = [
    "virtual/target-os",
    "virtual/target-os-dev",
    "virtual/target-os-test",
    "virtual/target-os-factory",
]


def ParseArgs(argv):
    """Parse command line arguments."""
    parser = commandline.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--sysroot", type="path", help="Path to the sysroot.")
    target.add_argument("-b", "--build-target", help="Name of the target build")
    parser.add_argument(
        "--output-path", default=None, help="Write output to the given path."
    )
    parser.add_argument(
        "--output-name", default="DepGraph", help="Write output file name."
    )
    parser.add_argument(
        "--include-histograms",
        default=False,
        help="Create and save histograms about dependencies.",
    )
    parser.add_argument("pkgs", nargs="*", default=_DEFAULT_PACKAGES)
    opts = parser.parse_args(argv)
    opts.Freeze()
    return opts


def CreateRuntimeTree(sysroot: str, pkg_list: str) -> Dict[str, List[str]]:
    """Calculate all packages that are RDEPENDS.

    Use the dependency information about packages to build a tree
    of only RDEPEDS packages and dependencies.

    Args:
        sysroot: The path to the root directory into which the package is
            pretend to be merged. This value is also used for setting
            PORTAGE_CONFIGROOT.
        pkg_list: The list of packages to extract their dependencies from.

    Returns:
        Returns a dictionary of runtime packages with their immediate
        dependencies.
    """

    # Setup for dependency extraction.
    extract_deps_argv = ["cros_extract_deps"]
    extract_deps_argv += [f"--sysroot={sysroot}"]
    extract_deps_argv.extend(pkg_list)
    result = cros_build_lib.run(
        extract_deps_argv, enter_chroot=True, stdout=subprocess.PIPE
    )
    deps_tree = json_lib.loads(result.stdout)
    return {pkg: deps_tree[pkg]["deps"] for pkg in deps_tree}


def main():
    opts = ParseArgs(sys.argv[1:])
    sysroot = opts.sysroot or build_target_lib.get_default_sysroot_path(
        opts.build_target
    )
    out_dir = opts.output_path or "."
    out_name = opts.output_name
    runtime_tree = CreateRuntimeTree(sysroot, opts.pkgs)
    dep_vis = visualize.DepVisualizer(runtime_tree)
    dep_vis.VisualizeGraph(output_name=out_name, output_dir=out_dir)
    if opts.include_histograms:
        dep_vis.GenerateHistograms(opts.build_target, out_dir)
