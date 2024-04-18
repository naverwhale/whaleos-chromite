# Copyright 2016 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Try to set up a chromite virtualenv, and print the import path."""

import pprint
import sys

from chromite.lib import commandline


def GetParser():
    """Creates the argparse parser."""
    parser = commandline.ArgumentParser(description=__doc__)
    return parser


def main(argv):
    parser = GetParser()
    parser.parse_args(argv)

    print("The import path is:")
    pprint.pprint(sys.path)
