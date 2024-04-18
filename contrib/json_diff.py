# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Human readable diff two JSON files."""

import difflib
import json
import logging
from pathlib import Path

from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.utils import pformat


def get_parser():
    """Build the argument parser."""
    parser = commandline.ArgumentParser(
        description=__doc__, default_log_level="notice"
    )
    parser.add_argument(
        "--format",
        choices=("unidiff",),
        default="unidiff",
        help="Diff output format",
    )
    parser.add_argument("files", nargs=2, help="JSON files to diff")
    return parser


def _parse_arguments(argv):
    """Parse and validate arguments."""
    parser = get_parser()
    opts = parser.parse_args(argv)

    opts.files = [Path(x) for x in opts.files]

    opts.Freeze()
    return opts


def main(argv):
    opts = _parse_arguments(argv)

    file1, file2 = opts.files

    try:
        json1 = json.loads(file1.read_bytes())
        json2 = json.loads(file2.read_bytes())
    except (FileNotFoundError, json.decoder.JSONDecodeError) as e:
        cros_build_lib.Die("%s", e)

    if json1 == json2:
        logging.info("Files are the same")
        return 0

    lines1 = pformat.json(json1).splitlines()
    lines2 = pformat.json(json2).splitlines()

    print(
        "\n".join(
            difflib.unified_diff(
                lines1,
                lines2,
                fromfile=f"a/{file1}",
                tofile=f"b/{file2}",
                lineterm="",
            )
        )
    )
    return 1
