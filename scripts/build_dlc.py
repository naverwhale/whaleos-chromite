# Copyright 2018 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Script to generate a DLC (Downloadable Content) artifact."""

import logging

from chromite.lib import commandline
from chromite.lib import dlc_lib


def GetParser():
    """Creates an argument parser and returns it."""
    parser = commandline.ArgumentParser(description=__doc__)
    # This script is used both for building an individual DLC or copying all
    # final DLCs images to their final destination nearby
    # chromiumos_test_image.bin, etc. These two arguments are required in both
    # cases.
    parser.add_argument(
        "--sysroot",
        type="path",
        metavar="DIR",
        help="The root path to the board's build root, e.g. /build/eve",
    )
    # TODO(andrewlassalle): Remove src-dir in the future(2021?) if nobody uses
    #  it.
    parser.add_argument(
        "--src-dir",
        type="path",
        metavar="SRC_DIR_PATH",
        help=(
            "Override the default Root directory path that contains all DLC "
            "files to be packed."
        ),
    )
    parser.add_argument(
        "--install-root-dir",
        type="path",
        metavar="DIR",
        help=(
            "If building a specific DLC, it is the root path to"
            " install DLC images (%s) and metadata (%s). Otherwise it"
            " is the target directory where the Chrome OS images gets"
            " dropped in `cros build-image`, e.g. "
            "src/build/images/<board>/latest."
        )
        % (dlc_lib.DLC_BUILD_DIR, dlc_lib.DLC_META_DIR),
    )

    one_dlc = parser.add_argument_group(
        "Arguments required for building only one DLC"
    )
    one_dlc.add_argument(
        "--rootfs",
        type="path",
        metavar="ROOT_FS_PATH",
        help="Path to the platform rootfs.",
    )
    one_dlc.add_argument(
        "--stateful",
        type="path",
        metavar="STATEFUL_PATH",
        help="Path to the platform stateful.",
    )
    one_dlc.add_argument(
        "--pre-allocated-blocks",
        type=int,
        metavar="PREALLOCATEDBLOCKS",
        help=(
            "Number of blocks (block size is 4k) that need to"
            "be pre-allocated on device."
        ),
    )
    one_dlc.add_argument("--version", metavar="VERSION", help="DLC Version.")
    one_dlc.add_argument("--id", metavar="ID", help="DLC ID (unique per DLC).")
    one_dlc.add_argument(
        "--package",
        metavar="PACKAGE",
        help=(
            "The package ID that is unique within a DLC, One"
            " DLC cannot have duplicate package IDs."
        ),
    )
    one_dlc.add_argument(
        "--name", metavar="NAME", help="A human-readable name for the DLC."
    )
    one_dlc.add_argument("--description", help="The description for the DLC.")
    one_dlc.add_argument(
        "--board", metavar="BOARD", help="The target board we are building for."
    )
    one_dlc.add_argument(
        "--fullnamerev",
        metavar="FULL_NAME_REV",
        help="The full ebuild package name.",
    )
    one_dlc.add_argument(
        "--fs-type",
        metavar="FS_TYPE",
        default=dlc_lib.SQUASHFS_TYPE,
        choices=(dlc_lib.SQUASHFS_TYPE, dlc_lib.EXT4_TYPE),
        help="File system type of the image.",
    )
    one_dlc.add_argument(
        "--preload",
        default=False,
        action="store_true",
        help="Allow preloading of DLC.",
    )
    one_dlc.add_argument(
        "--factory-install",
        default=False,
        action="store_true",
        help="Allow factory installing of DLC.",
    )
    one_dlc.add_argument(
        "--loadpin-verity-digest",
        default=False,
        action="store_true",
        help="Allow DLC to be a trusted dm-verity digest.",
    )
    one_dlc.add_argument(
        "--mount-file-required",
        default=False,
        action="store_true",
        help="Allow indirect mount file generation for DLC.",
    )
    one_dlc.add_argument(
        "--scaled",
        default=False,
        action="store_true",
        help="DLC will be fed through scaling design.",
    )
    one_dlc.add_argument(
        "--reserved",
        default=False,
        action="store_true",
        help="Always reserve space for this DLC.",
    )
    one_dlc.add_argument(
        "--critical-update",
        default=False,
        action="store_true",
        help="Always update with the OS for this DLC.",
    )
    one_dlc.add_argument(
        "--build-package",
        default=False,
        action="store_true",
        help=(
            "Flag to indicate if the script is executed during the "
            "`cros build-packages` phase."
        ),
    )
    one_dlc.add_argument(
        "--powerwash-safe",
        default=False,
        action="store_true",
        help="DLC will be powerwash safe. (Only on LVM supported devices)",
    )
    # Arguments groups don't support `add_bool_argument` yet.
    one_dlc.add_argument(
        "--use-logical-volume",
        default=False,
        action="store_true",
        help="DLC will use logical volumes on LVM stateful partition "
        "migrated devices. (scaled option takes precedence)",
    )
    return parser


def ValidateArguments(parser, opts, req_flags, invalid_flags):
    """Validates the correctness of the passed arguments.

    Args:
        parser: Arguments parser.
        opts: Parsed arguments.
        req_flags: all the required flags.
        invalid_flags: all the flags that are not allowed.
    """
    # Make sure if the intention is to build one DLC, all the required arguments
    # are passed and none of the invalid ones are passed. This will ensure the
    # script is called twice per DLC.
    if opts.id:
        if not all(vars(opts)[x] is not None for x in req_flags):
            parser.error(
                "If the intention is to build only one DLC, all the flags"
                "%s required for it should be passed." % req_flags
            )
        if any(vars(opts)[x] is not None for x in invalid_flags):
            parser.error(
                "If the intention is to build only one DLC, all the flags"
                "%s should be passed in the `cros build-packages` phase, not "
                "in the `cros build-image` phase." % invalid_flags
            )

    if opts.fs_type == dlc_lib.EXT4_TYPE:
        parser.error("ext4 unsupported for DLC, see https://crbug.com/890060")

    if opts.id:
        dlc_lib.ValidateDlcIdentifier(opts.id)
    if opts.package:
        dlc_lib.ValidateDlcIdentifier(opts.package)


def main(argv):
    parser = GetParser()
    opts = parser.parse_args(argv)
    opts.Freeze()
    per_dlc_req_args = ["id"]
    per_dlc_invalid_args = []
    if opts.build_package:
        per_dlc_req_args += [
            "pre_allocated_blocks",
            "version",
            "name",
            "description",
            "package",
            "install_root_dir",
        ]
        per_dlc_invalid_args += ["src_dir", "sysroot", "stateful"]
    else:
        per_dlc_req_args += ["sysroot", "board"]
        per_dlc_invalid_args += [
            "name",
            "pre_allocated_blocks",
            "version",
            "package",
            "reserved",
            "critical_update",
        ]

    ValidateArguments(parser, opts, per_dlc_req_args, per_dlc_invalid_args)

    if opts.build_package:
        logging.info("Building package: DLC %s", opts.id)
        params = dlc_lib.EbuildParams(
            dlc_id=opts.id,
            dlc_package=opts.package,
            fs_type=opts.fs_type,
            name=opts.name,
            description=opts.description,
            pre_allocated_blocks=opts.pre_allocated_blocks,
            version=opts.version,
            preload=opts.preload,
            factory_install=opts.factory_install,
            loadpin_verity_digest=opts.loadpin_verity_digest,
            mount_file_required=opts.mount_file_required,
            reserved=opts.reserved,
            critical_update=opts.critical_update,
            fullnamerev=opts.fullnamerev,
            scaled=opts.scaled,
            powerwash_safe=opts.powerwash_safe,
            use_logical_volume=opts.use_logical_volume,
        )
        params.VerifyDlcParameters()
        params.StoreDlcParameters(
            install_root_dir=opts.install_root_dir, sudo=True
        )

    else:
        dlc_lib.InstallDlcImages(
            sysroot=opts.sysroot,
            dlc_id=opts.id,
            install_root_dir=opts.install_root_dir,
            preload=opts.preload,
            factory_install=opts.factory_install,
            src_dir=opts.src_dir,
            rootfs=opts.rootfs,
            stateful=opts.stateful,
            board=opts.board,
        )
