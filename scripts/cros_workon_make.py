# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Build cros_workon package incrementally.

Simple wrapper script to build a cros_workon package incrementally. You
must already be cros_workon'ing the package in question. This had been
migrated to python from chromiumos/src/scripts/cros_workon_make.
"""

import logging
from typing import List, Optional

from chromite.third_party.opentelemetry import trace

from chromite.lib import build_target_lib
from chromite.lib import chromite_config
from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import workon_helper
from chromite.utils import telemetry


tracer = trace.get_tracer(__name__)


def GetParser() -> commandline.ArgumentParser:
    """Get a CLI parser."""
    parser = commandline.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-b",
        "--board",
        "--build-target",
        default=cros_build_lib.GetDefaultBoard(),
        required=True,
        help="The board to set package keywords for.",
    )
    parser.add_argument(
        "--test",
        default=False,
        action="store_true",
        help="Compile and run tests as well",
    )
    parser.add_argument(
        "--reconf",
        default=False,
        action="store_true",
        help="Re-run configure and prepare steps",
    )
    parser.add_argument(
        "--install",
        default=False,
        action="store_true",
        help="Incrementally build and install your package",
    )
    parser.add_argument(
        "--scrub",
        default=False,
        action="store_true",
        help="Blow away all in-tree files not managed by git",
    )
    parser.add_argument(
        "package",
        help="Package to build.",
    )
    return parser


def main(argv: Optional[List[str]]) -> Optional[int]:
    commandline.RunInsideChroot()

    chromite_config.initialize()
    telemetry.initialize(chromite_config.TELEMETRY_CONFIG)
    DoMain(argv)


@tracer.start_as_current_span("scripts.cros_workon_make")
def DoMain(argv: Optional[List[str]]) -> Optional[int]:
    parser = GetParser()
    options = parser.parse_args(argv)
    options.Freeze()

    board = options.board
    sysroot = build_target_lib.get_default_sysroot_path(board)
    helper = workon_helper.WorkonHelper(sysroot, board)

    pkg = options.package
    span = trace.get_current_span()
    span.set_attribute("package", pkg)

    if options.scrub:
        logging.warning("--scrub will destroy ALL FILES unknown to git!")
        if cros_build_lib.BooleanPrompt():
            helper.ScrubPackage(pkg)
        else:
            logging.info("Not scrubbing; exiting gracefully")
    elif options.install:
        helper.InstallPackage(pkg)
    else:
        helper.BuildPackage(
            pkg,
            clean=options.reconf,
            test=options.test,
        )
