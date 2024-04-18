# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Update the SDK.

Performs an update of the chroot. This script is called as part of
build_packages, so there is typically no need to call this script directly.
"""

import argparse
from typing import List, Optional

from chromite.lib import commandline
from chromite.service import sdk as sdk_service
from chromite.service import sysroot
from chromite.utils import timer


def get_parser() -> commandline.ArgumentParser:
    """Build the argument parser."""
    # TODO(vapier): Remove underscore separated arguments and the deprecated
    # message after Jun 2024.
    deprecated = "Argument will be removed Jun 2024. Use %s instead."

    parser = commandline.ArgumentParser(description=__doc__)

    parser.add_bool_argument(
        "--usepkg",
        True,
        "Use binary packages to bootstrap.",
        "Do not use binary packages to bootstrap.",
    )
    parser.add_argument(
        "--nousepkg",
        dest="usepkg",
        action="store_false",
        deprecated=deprecated % "--no-usepkg",
        help=argparse.SUPPRESS,
    )

    # Not really a common argument, but argument_group doesn't have our custom
    # bool extension yet.
    parser.add_bool_argument(
        "--eclean",
        True,
        "Clean out old SDK binpkgs.",
        "Do not clean out SDK binpkgs.",
    )
    parser.add_argument(
        "--noeclean",
        dest="eclean",
        action="store_false",
        deprecated=deprecated % "--no-eclean",
        help=argparse.SUPPRESS,
    )

    group = parser.add_argument_group("Advanced Build Modification Options")
    group.add_argument(
        "--jobs",
        type=int,
        help="Maximum number of packages to build in parallel.",
    )
    group.add_argument(
        "--skip-toolchain-update",
        dest="update_toolchain",
        action="store_false",
        default=True,
        help="Don't update toolchain automatically.",
    )
    group.add_argument(
        "--skip_toolchain_update",
        dest="update_toolchain",
        action="store_false",
        default=True,
        deprecated=deprecated % "--skip-toolchain-update",
        help=argparse.SUPPRESS,
    )
    group.add_argument(
        "--toolchain-boards",
        nargs="+",
        help="Extra toolchains to setup for the specified boards.",
    )
    group.add_argument(
        "--toolchain_boards",
        nargs="+",
        deprecated=deprecated % "--toolchain-boards",
        help=argparse.SUPPRESS,
    )
    group.add_argument(
        "--backtrack",
        type=int,
        default=sysroot.BACKTRACK_DEFAULT,
        help="See emerge --backtrack.",
    )

    return parser


@timer.timed("Elapsed time (update_chroot)")
def main(argv: Optional[List[str]] = None) -> Optional[int]:
    commandline.RunInsideChroot()

    parser = get_parser()
    opts = parser.parse_args(argv)
    opts.Freeze()

    update_args = sdk_service.UpdateArguments(
        build_source=not opts.usepkg,
        toolchain_targets=opts.toolchain_boards,
        jobs=opts.jobs,
        backtrack=opts.backtrack,
        update_toolchain=opts.update_toolchain,
        eclean=opts.eclean,
    )
    result = sdk_service.Update(update_args)
    return result.return_code
