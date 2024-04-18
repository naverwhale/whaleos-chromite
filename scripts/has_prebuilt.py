# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Script to check if the package(s) have prebuilts.

The script must be run inside the chroot. The output is a json dict mapping the
package atoms to a boolean for whether a prebuilt exists.
"""

import json
import logging
import os

from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib.parser import package_info


if cros_build_lib.IsInsideChroot():
    from chromite.lib import depgraph


def GetParser():
    """Build the argument parser."""
    parser = commandline.ArgumentParser(description=__doc__)

    parser.add_argument(
        "-b",
        "--build-target",
        dest="build_target_name",
        help="The build target that is being checked.",
    )
    parser.add_argument(
        "--output",
        type="path",
        required=True,
        help="The file path where the result json should be stored.",
    )
    parser.add_argument(
        "packages", nargs="+", help="The package atoms that are being checked."
    )

    return parser


def _ParseArguments(argv):
    """Parse and validate arguments."""
    parser = GetParser()
    opts = parser.parse_args(argv)

    if not os.path.exists(os.path.dirname(opts.output)):
        parser.error("Path containing the output file does not exist.")

    # Manually parse the packages as CPVs.
    packages = []
    for pkg in opts.packages:
        cpv = package_info.parse(pkg)
        if not cpv.atom:
            parser.error("Invalid package atom: %s" % pkg)

        packages.append(cpv)
    opts.packages = packages

    opts.Freeze()
    return opts


def main(argv):
    opts = _ParseArguments(argv)
    cros_build_lib.AssertInsideChroot()

    board = opts.build_target_name

    portage_binhost = portage_util.PortageqEnvvar("PORTAGE_BINHOST", board)
    logging.info("PORTAGE_BINHOST: %s", portage_binhost)

    results = {}
    bests = {}
    for cpv in opts.packages:
        query = cpv.cpvr or cpv.atom
        try:
            bests[query] = portage_util.PortageqBestVisible(query, board=board)
            logging.debug("Resolved %s best visible to %s", query, bests[query])
        except portage_util.NoVisiblePackageError:
            results[query] = False

    if bests:
        args = [
            # Fetch remote binpkg databases.
            "--getbinpkg",
            # Update packages to the latest version (we want updates to
            # invalidate installed packages).
            "--update",
            # Consider full tree rather than just immediate deps (changes in
            # dependencies and transitive deps can invalidate a binpkg).
            "--deep",
            # Packages with changed USE flags should be considered (changes in
            # dependencies and transitive deps can invalidate a binpkg).
            "--newuse",
            # Simplifies output.
            "--quiet",
            # Don't actually install it :).
            "--pretend",
            "--selective=n",
            # We run build_packages by default with these flags which can
            # trigger rebuilds (and ignoring of binpkgs) in more cases.
            "--newrepo",
            "--with-test-deps=y",
        ]
        if board:
            args.append("--board=%s" % board)
        args.extend("=%s" % best.cpvr for best in bests.values())

        generator = depgraph.DepGraphGenerator()
        logging.debug(
            "Initializing depgraph with: %s", cros_build_lib.CmdToStr(args)
        )
        generator.Initialize(args)

        for atom, best in bests.items():
            results[atom] = generator.HasPrebuilt(best.cpvr)

    osutils.WriteFile(opts.output, json.dumps(results))
