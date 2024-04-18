# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""copybot downstreaming config argparser.

Used for generating a common config to use across different downstream projects.
"""

import argparse
from typing import Optional

from chromite.lib import commandline


def generate_copybot_arg_parser(
    project: Optional[str] = None,
) -> argparse.Namespace:
    """Create a copybot downstreaming arg parser and return it to the caller."""
    # TODO(b/278748731): Add option to rebase CLs.
    parser = commandline.ArgumentParser(__doc__, default_log_level="debug")
    parser.add_argument(
        "--project",
        required=bool(not project),
        default=project,
        help="Project to downstream.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run, no updates to Gerrit."
    )
    parser.add_argument(
        "--cq-dry-run",
        action="store_true",
        help="Label the patches for dry run (CQ+1) instead of merge (CQ+2, "
        "default behavior).",
    )
    parser.add_argument(
        "--limit", type=int, help="How many changes to modify, from the oldest."
    )
    parser.add_argument(
        "--stop-at", type=int, help="Stop at the specified change number."
    )
    parser.add_argument(
        "--ignore-warnings",
        action="store_true",
        default=False,
        help="Ignore warnings and proceed with downstreaming action.",
    )

    #
    # Subcommands
    #
    # Used to extend the functionality of the script. If none is specified,
    # default to the main downstreaming program (original behavior)
    #

    # Utility to remove the current user from the attention set on merged CLs,
    # as this sometimes does not happen automatically and leaves the user's
    # Gerrit dashboard cluttered.
    subparser_clear_attention = parser.add_subparsers(
        title="Subcommands", dest="cmd"
    )
    subparser_clear_attention.add_parser(
        "clear_attention",
        help="Remove current user from attention set on merged downstreaming "
        "CLs",
    )
    return parser
