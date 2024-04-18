# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The Package Size Reporting CLI entry point."""

import os

from chromite.lib import commandline
from chromite.lib import metrics_lib
from chromite.lib import portage_util
from chromite.utils import pformat


_PARTITION_NAMES = ["rootfs", "stateful"]


def _get_parser():
    """Create an argument parser for this script."""
    parser = commandline.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        required=True,
        type="path",
        help="Specify the rootfs to investigate.",
    )
    parser.add_argument(
        "--image-type",
        help="Specify the type of image being investigated. "
        "e.g. [base, dev, test]",
    )
    parser.add_argument(
        "--partition-name",
        choices=_PARTITION_NAMES,
        help="Specify the partition name. " "e.g. [rootfs, stateful]",
    )
    parser.add_argument(
        "packages",
        nargs="*",
        help="Names of packages to investigate. Must be "
        "specified as category/package-version.",
    )
    return parser


def generate_package_size_report(
    db, root, image_type, partition_name, installed_packages
):
    """Collect package sizes and generate a report."""
    results = {}
    package_sizes = portage_util.GeneratePackageSizes(
        db, root, installed_packages
    )
    timestamp = metrics_lib.current_milli_time()
    for package_cpv, size in package_sizes:
        results[package_cpv] = size
        metrics_lib.append_metrics_log(
            timestamp,
            "package_size.%s.%s.%s" % (image_type, partition_name, package_cpv),
            metrics_lib.OP_GAUGE,
            arg=size,
        )

    rootfs_stat = os.statvfs(root)
    block_size = rootfs_stat.f_bsize
    blocks_used = rootfs_stat.f_blocks - rootfs_stat.f_bfree
    total_size = block_size * blocks_used

    metrics_lib.append_metrics_log(
        timestamp,
        "total_size.%s.%s" % (image_type, partition_name),
        metrics_lib.OP_GAUGE,
        arg=total_size,
    )
    return {
        "root": root,
        "package_sizes": results,
        "total_size": total_size,
        "package_database_path": db.db_path,
        "package_install_path": db.package_install_path,
    }


def main(argv):
    """Find and report approximate size info for a particular built package."""
    commandline.RunInsideChroot()

    parser = _get_parser()
    opts = parser.parse_args(argv)
    opts.Freeze()

    vdb = package_install_path = ""
    if opts.partition_name == "stateful":
        vdb = "var_overlay/db/pkg"
        package_install_path = "dev_image"
    db = portage_util.PortageDB(
        root=opts.root, vdb=vdb, package_install_path=package_install_path
    )

    if opts.packages:
        installed_packages = portage_util.GenerateInstalledPackages(
            db, opts.root, opts.packages
        )
    else:
        installed_packages = db.InstalledPackages()

    results = generate_package_size_report(
        db, opts.root, opts.image_type, opts.partition_name, installed_packages
    )
    print(pformat.json(results))
