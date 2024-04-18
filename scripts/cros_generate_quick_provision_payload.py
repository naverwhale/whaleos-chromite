# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Script to generate Chromium OS quick provision payloads."""

import os

from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib.paygen import partition_lib
from chromite.lib.paygen import paygen_stateful_payload_lib


def ParseArguments(argv):
    """Returns a namespace for the CLI arguments."""
    parser = commandline.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image",
        type="path",
        required=True,
        help="The path to local image to build the quick "
        "provision payloads for.",
    )
    parser.add_argument(
        "--output",
        type="path",
        help="The output directory to generate quick "
        "provision payloads for.",
        default=".",
    )

    opts = parser.parse_args(argv)
    # Check if output is valid directory.
    if not os.path.isdir(opts.output):
        parser.error("Please pass in a valid output directory.")

    opts.Freeze()

    return opts


def CreateKernelQuickProvisionPayload(image, output):
    with osutils.TempDir() as temp_dir:
        # Extract kernel.
        kern = os.path.join(temp_dir, "kern")
        partition_lib.ExtractKernel(image, os.path.join(temp_dir, kern))
        # Compress kernel.
        cros_build_lib.CompressFile(
            kern, os.path.join(output, constants.QUICK_PROVISION_PAYLOAD_KERNEL)
        )


def CreateRootQuickProvisionPayload(image, output):
    with osutils.TempDir() as temp_dir:
        # Extract root.
        root = os.path.join(temp_dir, "root")
        partition_lib.ExtractRoot(image, os.path.join(temp_dir, root))
        # Compress root.
        cros_build_lib.CompressFile(
            root, os.path.join(output, constants.QUICK_PROVISION_PAYLOAD_ROOTFS)
        )


def CreateStatefulQuickProvisionPayload(image, output):
    # Create stateful quick provision payload.
    paygen_stateful_payload_lib.GenerateStatefulPayload(image, output)
    # Change output ownership of file.


def main(argv):
    opts = ParseArguments(argv)

    parallel.RunParallelSteps(
        [
            # Stateful generation is usually the slowest.
            lambda: CreateStatefulQuickProvisionPayload(
                opts.image, opts.output
            ),
            lambda: CreateKernelQuickProvisionPayload(opts.image, opts.output),
            lambda: CreateRootQuickProvisionPayload(opts.image, opts.output),
        ]
    )
