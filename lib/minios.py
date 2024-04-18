# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""MiniOS build library."""

import logging
import os

from chromite.lib import build_target_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import image_lib
from chromite.lib import kernel_builder


CROS_DEBUG_FLAG = "cros_debug"
MINIOS_KERNEL_IMAGE = "minios_vmlinuz.image"
KERNEL_FLAGS = [
    "minios",
    "minios_ramfs",
    "tpm",
    "i2cdev",
    "vfat",
    "kernel_compress_xz",
    "pcserial",
    "-kernel_afdo",
]
BLOCK_SIZE = 512


class Error(Exception):
    """Base error class for the module."""


class MiniOsError(Error):
    """Raised when failing to build Mini OS image."""


def CreateMiniOsKernelImage(
    board: str,
    version: str,
    work_dir: str,
    keys_dir: str,
    public_key: str,
    private_key: str,
    keyblock: str,
    serial: str,
    jobs: int,
    build_kernel: bool = True,
    developer_mode: bool = False,
) -> str:
    """Creates the MiniOS kernel image.

    And puts it in the work directory.

    Args:
        jobs: The number of packages to build in parallel.
        board: The board to build the kernel for.
        version: The chromeos version string.
        work_dir: The directory for keeping intermediary files.
        keys_dir: The path to kernel keys directories.
        public_key: Filename to the public key whose private part signed the
            keyblock.
        private_key: Filename to the private key whose public part is baked into
            the keyblock.
        keyblock: Filename to the kernel keyblock.
        serial: Serial port for the kernel console (e.g. printks).
        build_kernel: Build a new kernel from source.
        developer_mode: Add developer mode flags to the kernel image.

    Returns:
        The path to the generated kernel image.
    """
    install_root = os.path.join(
        (build_target_lib.get_default_sysroot_path(board)), "factory-root"
    )
    kb = kernel_builder.Builder(board, work_dir, install_root, jobs)
    if build_kernel:
        # MiniOS ramfs cannot be built with multiple conflicting `_ramfs` flags.
        kb.CreateCustomKernel(
            KERNEL_FLAGS,
            [
                x
                for x in os.environ.get("USE", "").split()
                if not x.endswith("_ramfs")
            ],
        )
    kernel = os.path.join(work_dir, MINIOS_KERNEL_IMAGE)
    assert " " not in version, f"bad version: {version}"
    boot_args = f"noinitrd panic=60 cros_minios_version={version} cros_minios"
    if developer_mode:
        boot_args += f" {CROS_DEBUG_FLAG}"
    kb.CreateKernelImage(
        kernel,
        boot_args=boot_args,
        serial=serial,
        keys_dir=keys_dir,
        public_key=public_key,
        private_key=private_key,
        keyblock=keyblock,
    )
    return kernel


def InsertMiniOsKernelImage(image: str, kernel: str):
    """Writes miniOS kernel into A + B miniOS partitions of the image.

    A + B partitions of miniOS need to have enough space allocated for each copy
    of the miniOS kernel to fit into.

    Args:
        image: The path to the Chromium OS image.
        kernel: The path to the kernel image.
    """
    with image_lib.LoopbackPartitions(image) as devs:
        for part_name in (constants.PART_MINIOS_A, constants.PART_MINIOS_B):
            part_info = devs.GetPartitionInfo(part_name)
            kernel_size = os.path.getsize(kernel)
            if kernel_size > part_info.size:
                raise MiniOsError(
                    f"MiniOS kernel is larger than the {part_name} partition."
                )

            device = devs.GetPartitionDevName(part_name)
            logging.debug("MiniOS loopback partition is %s", device)

            logging.info(
                "Writing the MiniOS kernel %s into image %s at %s",
                kernel,
                image,
                device,
            )

            kernel_blocks = kernel_size // BLOCK_SIZE
            part_blocks = part_info.size // BLOCK_SIZE

            # First zero out partition.
            # This generally would help with update payloads so we don't have
            # to compress junk bytes. The target file is a loopback dev device
            # of a miniOS partition.
            cros_build_lib.sudo_run(
                [
                    "dd",
                    "if=/dev/zero",
                    f"of={device}",
                    f"bs={BLOCK_SIZE}",
                    f"seek={kernel_blocks}",
                    f"count={part_blocks - kernel_blocks}",
                ]
            )
            # Write the actual MiniOS kernel into the A + B partitions.
            cros_build_lib.sudo_run(
                ["dd", f"if={kernel}", f"of={device}", f"bs={BLOCK_SIZE}"]
            )
