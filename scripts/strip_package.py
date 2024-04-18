# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Strip packages and place them in <sysroot>/stripped-packages."""

import os
import sys
from typing import List

from chromite.lib import build_target_lib
from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import install_mask


# The builder module lives in the devserver path.
# pylint: disable=import-error,wrong-import-position
sys.path.append("/usr/lib/devserver/")
import builder


def create_parser() -> commandline.ArgumentParser:
    """Creates the cmdline argparser, populates the options and description."""
    parser = commandline.ArgumentParser(description=__doc__)

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--board",
        default=cros_build_lib.GetDefaultBoard(),
        help="The board that processed packages belong to.",
    )
    group.add_argument(
        "--sysroot",
        type="path",
        help="Sysroot that processed packages belong to. "
        "This is incompatible with --board.",
    )

    parser.add_argument(
        "--deep",
        action="store_true",
        default=False,
        help="Also strip dependencies of packages.",
    )
    parser.add_argument(
        "packages", nargs="+", metavar="package", help="Packages to strip."
    )
    return parser


def main(argv: List[str]) -> int:
    """Main function."""
    cros_build_lib.AssertInsideChroot()
    parser = create_parser()
    options = parser.parse_args(argv)
    options.Freeze()

    if options.sysroot is not None:
        sysroot = options.sysroot
    else:
        sysroot = build_target_lib.get_default_sysroot_path(options.board)

    os.environ["DEFAULT_INSTALL_MASK"] = "\n".join(install_mask.DEFAULT)

    if not builder.UpdateGmergeBinhost(sysroot, options.packages, options.deep):
        return 1
    return 0
