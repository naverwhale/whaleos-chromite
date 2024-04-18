# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""CR and CQ +2 copybot project commits for downstreaming.

See go/copybot

For Zephyr Downstreaming Rotation: go/zephyr-downstreaming-guide
"""

from chromite.contrib import copybot_downstream
from chromite.contrib.copybot_downstream_config import downstream_argparser


class ZephyrDownstream(copybot_downstream.CopybotDownstream):
    """Class for extending copybot downstreaming class for zephyr."""


def main(args):
    """Main entry point for CLI."""
    parser = downstream_argparser.generate_copybot_arg_parser("zephyr")
    opts = parser.parse_args(args)
    ZephyrDownstream(opts).run(opts.cmd)
