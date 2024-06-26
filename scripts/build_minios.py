# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A script to generate MiniOS kernel images.

And inserting them into the Chromium OS images.
"""

import os
import tempfile

from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import minios


def GetParser():
    """Creates an argument parser and returns it."""
    parser = commandline.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--board", "-b", "--build-target", required=True, help="The board name."
    )
    parser.add_argument(
        "--version", required=True, help="The chromeos version string."
    )
    parser.add_argument(
        "--image",
        type="path",
        required=True,
        help="The path to the chromium os image.",
    )
    parser.add_argument(
        "--keys-dir",
        type="path",
        help="The path to keyset.",
        default=constants.VBOOT_DEVKEYS_DIR,
    )
    parser.add_argument(
        "--public-key",
        help="Filename to the public key whose private part "
        "signed the keyblock.",
        default=constants.RECOVERY_PUBLIC_KEY,
    )
    parser.add_argument(
        "--private-key",
        help="Filename to the private key whose public part is "
        "baked into the keyblock.",
        default=constants.MINIOS_DATA_PRIVATE_KEY,
    )
    parser.add_argument(
        "--keyblock",
        help="Filename to the kernel keyblock.",
        default=constants.MINIOS_KEYBLOCK,
    )
    parser.add_argument(
        "--serial",
        type=str,
        help="Serial port for the kernel console (e.g. printks)",
    )
    parser.add_argument(
        "--mod-for-dev",
        action="store_true",
        help="Repack the MiniOS image with debug flags.",
    )
    parser.add_argument(
        "--force-build",
        action="store_true",
        help="Force the kernel to be rebuilt when repacking with "
        "debug flags. Use with --mod-for-dev in case kernel is "
        "not already built or needs to be rebuilt.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=os.cpu_count(),
        help="Number of packages to build in parallel. "
        "(Default: %(default)s)",
    )
    return parser


def main(argv):
    parser = GetParser()
    opts = parser.parse_args(argv)
    opts.Freeze()

    with tempfile.TemporaryDirectory() as work_dir:
        build_kernel = opts.force_build if opts.mod_for_dev else True
        kernel = minios.CreateMiniOsKernelImage(
            opts.board,
            opts.version,
            work_dir,
            opts.keys_dir,
            opts.public_key,
            opts.private_key,
            opts.keyblock,
            opts.serial,
            opts.jobs,
            build_kernel,
            opts.mod_for_dev,
        )
        minios.InsertMiniOsKernelImage(opts.image, kernel)
