# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Locates past-AUE overlay candidates."""

import datetime

from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import portage_util


_QUERY = """
SELECT buildTargets, aueDate
FROM chromeos_build_release_data.device_live_builds
WHERE buildTargets IS NOT NULL
    AND aueDate IS NOT NULL
    AND EXTRACT(YEAR FROM aueDate) > 2000
GROUP BY buildTargets, aueDate ORDER BY aueDate;"""


def get_parser():
    """Build the argument parser."""
    parser = commandline.ArgumentParser(description=__doc__)

    return parser


def _parse_arguments(argv):
    """Parse and validate arguments."""
    parser = get_parser()
    opts = parser.parse_args(argv)

    opts.Freeze()
    return opts


def main(argv):
    _ = _parse_arguments(argv)

    result = cros_build_lib.run(
        ["dremel", "--output", "csv"],
        input=_QUERY,
        capture_output=True,
        encoding="utf-8",
    )

    # TODO: Parse the parent config for the overlays to allow determining
    #  actual usages, and then also check for overlays with no usages and
    #  overlays with missing parents.
    now = datetime.datetime.now()
    overlays = portage_util.FindOverlays(constants.BOTH_OVERLAYS)
    overlay_names = {portage_util.GetOverlayName(x): x for x in overlays}
    aue_overlays = []
    lines = [x for x in result.stdout.splitlines() if x]
    for line in lines[1:]:
        build_target, aue_date_str = line.split(",")
        aue_date = datetime.datetime.strptime(
            aue_date_str.split("+")[0], "%Y-%m-%d %H:%M:%S"
        )

        if aue_date > now:
            continue

        for k in overlay_names:
            # Check if the build target is in the name to catch variants.
            # TODO: Use the parent configs instead.
            if build_target in k:
                aue_overlays.append(
                    (build_target, aue_date_str, k, overlay_names[k])
                )

    if not aue_overlays:
        print("No candidates found.")
        return

    lines = ["\t".join(x) for x in aue_overlays]
    print("Found AUE boards:")
    print("\n".join(lines))
