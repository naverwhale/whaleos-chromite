# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Dumps a JSON file that describes objects installed for the given boards.

e.g.,

{
  'bob': {
    'chromeos-base/chromeos-chrome': [
      '/opt/google/chrome/chrome',
      '/opt/google/chrome/libchrome.so'
    ]
  }
}
"""

import collections
import json
import os

from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import portage_util


def get_all_package_objects(board):
    """Given a board, returns a dict of {package_name: [objects_in_package]}

    `objects_in_package` is specifically talking about objects of type `obj`
    which were installed by the given package. In other words, this will
    enumerate all regular files (e.g., excluding directories and symlinks)
    installed by a package.

    This dict comprises all packages currently installed on said board.
    """
    db = portage_util.PortageDB(root=os.path.join("/build", board))

    result = collections.defaultdict(set)
    for package in db.InstalledPackages():
        objects = (
            "/" + path
            for typ, path in package.ListContents()
            if typ == package.OBJ
        )
        result["%s/%s" % (package.category, package.package)].update(objects)

    return {k: sorted(v) for k, v in result.items()}


def main(argv):
    cros_build_lib.AssertInsideChroot()

    parser = commandline.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", required=True, help="File to write results to"
    )
    parser.add_argument("board", nargs="+")
    opts = parser.parse_args(argv)

    output = opts.output
    if output == "-":
        output = "/dev/stdout"

    results = {x: get_all_package_objects(x) for x in opts.board}
    with open(output, "w", encoding="utf-8") as f:
        json.dump(results, f)
