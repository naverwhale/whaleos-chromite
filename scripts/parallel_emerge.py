# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrapper script to run emerge, with reasonable defaults.

Usage:
 ./parallel_emerge [--board=BOARD] [--workon=PKGS]
                   [--force-remote-binary=PKGS] [emerge args] package

This script is a simple wrapper around emerge that handles legacy command line
arguments as well as setting reasonable defaults for parallelism.
"""

import argparse
import logging
import multiprocessing
import os

from chromite.lib import build_target_lib
from chromite.lib import commandline
from chromite.lib import cros_build_lib


class LookupBoardSysroot(argparse.Action):
    """Translates board argument to sysroot location."""

    def __call__(self, parser, namespace, values, option_string=None):
        sysroot = build_target_lib.get_default_sysroot_path(values)
        setattr(namespace, "sysroot", sysroot)


def ParallelEmergeArgParser():
    """Helper function to create command line argument parser for this wrapper.

    We need to be compatible with emerge arg format.  We scrape arguments that
    are specific to parallel_emerge, and pass through the rest directly to
    emerge.

    Returns:
        commandline.ArgumentParser that captures arguments specific to
        parallel_emerge.
    """
    parser = commandline.ArgumentParser(description=__doc__, dryrun=True)

    board_group = parser.add_mutually_exclusive_group()
    board_group.add_argument(
        "--board",
        default=None,
        action=LookupBoardSysroot,
    )
    board_group.add_argument(
        "--sysroot",
        action="store",
        metavar="PATH",
    )

    parser.add_argument(
        "--root",
        action="store",
        metavar="PATH",
    )
    parser.add_argument(
        "--workon",
        action="append",
        metavar="PKGS",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--force-remote-binary",
        action="append",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--root-deps",
        action="store",
        nargs="?",
        default=None,
        dest="root_deps",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "-j",
        "--jobs",
        default=multiprocessing.cpu_count(),
        metavar="PARALLEL_JOBCOUNT",
    )

    parser.add_argument(
        "--retries",
        help=argparse.SUPPRESS,
        deprecated="Build retries are no longer supported.",
    )
    parser.add_argument(
        "--eventlogfile",
        help=argparse.SUPPRESS,
        deprecated="parallel_emerge no longer records failed packages. Set "
        "CROS_METRICS_DIR in the system environment to get a log of failed "
        "packages and which phase they failed in.",
    )
    parser.add_argument(
        "--show-output",
        action="store_true",
        help=argparse.SUPPRESS,
        deprecated="This option is no longer supported.",
    )

    return parser


def main(argv):
    parser = ParallelEmergeArgParser()
    parsed_args, emerge_args = parser.parse_known_args(argv)
    parsed_args = vars(parsed_args)

    os.environ["CLEAN_DELAY"] = "0"

    if parsed_args.get("sysroot"):
        emerge_args.extend(["--sysroot", parsed_args["sysroot"]])
        os.environ["PORTAGE_CONFIGROOT"] = parsed_args["sysroot"]

    if parsed_args.get("root"):
        emerge_args.extend(["--root", parsed_args["root"]])

    if parsed_args.get("rebuild"):
        emerge_args.append("--rebuild-if-unbuilt")

    if parsed_args.get("workon"):
        emerge_args.append(
            f"--reinstall-atoms={' '.join(parsed_args['workon'])}"
        )
        emerge_args.append(
            f"--usepkg-exclude={' '.join(parsed_args['workon'])}"
        )

    if parsed_args.get("force_remote_binary"):
        emerge_args.append(
            f"--useoldpkg-atoms={' '.join(parsed_args['force_remote_binary'])}"
        )

    if parsed_args.get("root_deps") is not None:
        emerge_args.append(f"--root-deps={parsed_args['root_deps']}")
    else:
        emerge_args.append("--root-deps")

    emerge_args.append(f"--jobs={parsed_args['jobs']}")

    # The -v/--verbose flag gets eaten by the commandline.ArgumentParser to
    # set the log_level, but it was almost certainly meant to be passed through
    # to emerge. Check for -v/--verbose directly to avoid coupling this to the
    # semantics of chromite logging CLI args.
    if "-v" in argv or "--verbose" in argv:
        emerge_args.append("--verbose")

    cmd = ["emerge"] + emerge_args
    cmd_str = cros_build_lib.CmdToStr(cmd)
    if parsed_args.get("dryrun"):
        logging.notice("Would have run: %s", cmd_str)
        return

    logging.info("Running: %s", cmd_str)
    os.execvp("emerge", cmd)
