# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Calculate the size deltas for packages between two images.

Example:
    ./img-size /path/to/baseline.bin /path/to/target.bin cat/pkg-a cat/pkg-b
"""

import argparse
import collections
from pathlib import Path
from typing import List, Optional

from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib.parser import package_info
from chromite.service import observability


def get_parser() -> commandline.ArgumentParser:
    """Build the argument parser."""
    parser = commandline.ArgumentParser(description=__doc__)

    sizes = parser.add_mutually_exclusive_group()
    sizes.add_argument(
        "--mib",
        dest="size_div",
        default=1,
        action="store_const",
        const=2**20,
        help="Show all sizes in MiB.",
    )
    sizes.add_argument(
        "--byte",
        "--bytes",
        dest="size_div",
        action="store_const",
        const=1,
        help="Show all sizes in bytes.",
    )

    parser.add_argument(
        "baseline",
        type="path",
        help="The image to use as a baseline for the size deltas.",
    )
    parser.add_argument(
        "target", type="path", help="The target image being measured."
    )
    parser.add_argument(
        "packages", nargs="+", help="The package atom(s) being measured."
    )

    return parser


def parse_arguments(argv: List) -> argparse.Namespace:
    """Parse and validate arguments."""
    parser = get_parser()
    opts = parser.parse_args(argv)

    opts.baseline = Path(opts.baseline)
    opts.target = Path(opts.target)

    if not opts.baseline.exists() or not opts.target.exists():
        parser.error("The baseline and target images must be valid images.")

    opts.packages = [package_info.parse(x) for x in opts.packages]

    opts.Freeze()
    return opts


def main(argv: Optional[List[str]]) -> Optional[int]:
    """Main."""
    opts = parse_arguments(argv)

    package_size_data = observability.get_image_size_data(
        {
            opts.baseline: constants.IMAGE_TYPE_TEST,
            opts.target: constants.IMAGE_TYPE_DEV,
        }
    )

    partitions = (constants.PART_ROOT_A, constants.PART_STATE)
    baseline_data = collections.defaultdict(dict)
    target_data = collections.defaultdict(dict)

    baseline_totals = {x: {"apparent": 0, "disk_usage": 0} for x in partitions}
    target_totals = {x: {"apparent": 0, "disk_usage": 0} for x in partitions}
    for partition, partition_data in package_size_data[
        constants.IMAGE_TYPE_TEST
    ].items():
        for pkg in opts.packages:
            baseline_data[partition][pkg] = [
                v
                for k, v in partition_data.items()
                if k.package_name.atom == pkg.atom
            ]
            baseline_totals[partition]["apparent"] += sum(
                x.apparent_size for x in baseline_data[partition][pkg]
            )
            baseline_totals[partition]["disk_usage"] += sum(
                x.disk_utilization_size for x in baseline_data[partition][pkg]
            )

    for partition, partition_data in package_size_data[
        constants.IMAGE_TYPE_DEV
    ].items():
        for pkg in opts.packages:
            target_data[partition][pkg] = [
                v
                for k, v in partition_data.items()
                if k.package_name.atom == pkg.atom
            ]
            target_totals[partition]["apparent"] += sum(
                x.apparent_size for x in target_data[partition][pkg]
            )
            target_totals[partition]["disk_usage"] += sum(
                x.disk_utilization_size for x in target_data[partition][pkg]
            )

    final_data = [
        ",".join(
            [
                "Package",
                "Baseline rootfs apparent",
                "Baseline rootfs disk utilization",
                "Target rootfs apparent",
                "Target rootfs disk utilization",
                "rootfs apparent Delta",
                "rootfs disk utilization Delta",
                "Baseline stateful apparent",
                "Baseline stateful disk utilization",
                "Target stateful apparent",
                "Target stateful disk utilization",
                "stateful apparent Delta",
                "stateful disk utilization Delta",
            ]
        )
    ]

    for pkg in opts.packages:
        pkg_data = [pkg.atom]
        for partition in partitions:
            base_app = sum(
                x.apparent_size for x in baseline_data[partition][pkg]
            )
            base_du = sum(
                x.disk_utilization_size for x in baseline_data[partition][pkg]
            )
            target_app = sum(
                x.apparent_size for x in target_data[partition][pkg]
            )
            target_du = sum(
                x.disk_utilization_size for x in target_data[partition][pkg]
            )
            pkg_data.extend(
                [
                    round(base_app / opts.size_div, 3),
                    round(base_du / opts.size_div, 3),
                    round(target_app / opts.size_div, 3),
                    round(target_du / opts.size_div, 3),
                    round((target_app - base_app) / opts.size_div, 3),
                    round((target_du - base_du) / opts.size_div, 3),
                ]
            )
        final_data.append(",".join(str(x) for x in pkg_data))

    totals_data = ["TOTALS"]
    for partition in partitions:
        base_app = baseline_totals[partition]["apparent"]
        base_du = baseline_totals[partition]["disk_usage"]
        target_app = target_totals[partition]["apparent"]
        target_du = target_totals[partition]["disk_usage"]
        totals_data.extend(
            [
                round(base_app / opts.size_div, 3),
                round(base_du / opts.size_div, 3),
                round(target_app / opts.size_div, 3),
                round(target_du / opts.size_div, 3),
                round((target_app - base_app) / opts.size_div, 3),
                round((target_du - base_du) / opts.size_div, 3),
            ]
        )
    final_data.append(",".join(str(x) for x in totals_data))

    print("\n".join(final_data))
