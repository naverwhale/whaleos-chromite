# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Deploy packages into a termina-dlc image on a device"""

import logging
import os
import tempfile
import textwrap
import time
from typing import List, NamedTuple

from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.lib import remote_access


class FileSet(NamedTuple):
    """A set of files from a source to a destination image."""

    source_root: str
    destination_image: str
    files: List[str]


TOOLS_PREFIX = "/opt/google/cros-containers"
DLC_IMAGES = {
    "termina-dlc": ("vm_rootfs", "vm_tools"),
    "termina-tools-dlc": ("vm_tools",),
}


def is_in_tools_images(path: str) -> bool:
    """Check if a file is deployed in the tools image."""
    return path.startswith(TOOLS_PREFIX)


def get_deployment_plan(board: str, packages: List[str]) -> List[FileSet]:
    """Figures out which files get deployed where for a set of inputs.

    Examples:
        get_deployment_plan('tatl', 'true', 'tremplin') inside the chroot will
        return [FileSet('/build/tatl', 'vm_rootfs', '/usr/bin/tremplin')]
        meaning that /build/tatl/usr/bin/tremplin should be copied to
        /usr/bin/tremplin inside vm_rootfs.img

    Args:
        board: The board to fetch packages for.
        packages: A list of packages (as understood by equery)

    Returns:
        A list of FileSets which describe the source root, destination image,
        and a list of file paths which should be copied (relative to the source
        root) to that location within the destination image.
    """
    # TODO(crbug/1222489): We should validate user input. At the moment
    # ambiguous packages deploy files from every package (fine), an unmatched
    # package gives an exception (all right), and an unmatched package in a list
    # with packages that exist skips the missing package e.g. `deploy tremlin
    # sommelier will only deploy Sommelier with no warnings (less fine).
    # It's messy to do so without having extra chroot enters, and slower if we
    # do, so leave that for a separate task.
    files = cros_build_lib.run(
        [f"qlist-{board}"] + packages,
        enter_chroot=True,
        stdout=True,
        print_cmd=False,
        encoding="utf-8",
    ).stdout.splitlines()

    files_rootfs: List[str] = []
    files_tools: List[str] = []

    for file in files:
        if not file.strip():
            continue
        if is_in_tools_images(file):
            # The files are located at e.g. opt/google/.../bin/blah, but their
            # destination, so trip off the prefix.
            files_tools.append(file[len(TOOLS_PREFIX) :])
        else:
            files_rootfs.append(file)

    rootfs = FileSet(
        path_util.FromChrootPath(f"/build/{board}"), "vm_rootfs", files_rootfs
    )
    tools = FileSet(
        path_util.FromChrootPath(f"/build/{board}{TOOLS_PREFIX}"),
        "vm_tools",
        files_tools,
    )
    return [rootfs, tools]


def deploy_into_remote_dlc(
    remote: remote_access.ChromiumOSDeviceHandler,
    transfers: List[FileSet],
    dlc_id: str,
):
    """Copies the specified files into a DLC image on hostname."""
    logging.notice("Unpacking DLC")
    remote_dir = remote.work_dir
    # We unpack the dlc disk image, add an extra 200M of empty space to each
    # inner image to fit whatever we're about to copy over, then mount the
    # images. Run the entire thing inside set -e so a failure of any step
    # causes the entire command to fail, which then turns into an exception.
    imgs = [f"dlc/root/{img}.img" for img in DLC_IMAGES[dlc_id]]
    command = textwrap.dedent(
        f"""
    (set -e
      cd {remote_dir}
      dlctool --unpack --id {dlc_id} dlc
      for path in {" ".join(imgs)}; do
        mkdir $(basename $path .img)
        truncate -s +200M $path
        e2fsck -yf $path
        resize2fs $path
        mount $path $(basename $path .img)
      done)"""
    )
    remote.run(command, shell=True, capture_output=False)

    logging.notice("Transferring files")
    for transfer in transfers:
        if not transfer.files:
            # If we don't have any files don't call rsync
            continue
        if transfer.destination_image not in DLC_IMAGES[dlc_id]:
            # The image isn't part of the current DLC
            continue
        logging.info(
            "Deploying the following files to the %s image: %s",
            transfer.destination_image,
            ", ".join(transfer.files),
        )
        with tempfile.TemporaryDirectory() as d:
            files_file = os.path.join(d, "files.txt")
            osutils.WriteFile(files_file, "\n".join(transfer.files))
            remote.CopyToDevice(
                transfer.source_root,
                f"{remote_dir}/{transfer.destination_image}",
                mode="rsync",
                files_from=files_file,
                inplace=True,
            )

    logging.notice("Repacking DLC")
    # Unmount the inner images, shrink them back to minimum size (so we
    # don't constantly grow the image by 200M every time we run) then repack
    # the DLC image. Run the entire thing inside set -e so a failure of any
    # step causes the entire command to fail, which then turns into an
    # exception.
    command = textwrap.dedent(
        f"""
    (set -e
      cd {remote_dir}
      for path in {" ".join(imgs)}; do
        umount $(basename $path .img)
        rm -rf $(basename $path .img)
        e2fsck -yf $path
        resize2fs -M $path
      done
      dlctool --id {dlc_id} dlc $(
        grep -qm1 compress $(which dlctool) && echo --nocompress)
      rm -rf dlc)"""
    )
    remote.run(command, shell=True, capture_output=False)


def get_parser() -> commandline.ArgumentParser:
    parser = commandline.ArgumentParser(
        description=__doc__, default_log_level="info"
    )

    parser.add_argument(
        "-b",
        "--board",
        choices=["tatl", "tael"],
        required=True,
        help="The termina board to deploy packages for",
    )
    parser.add_argument(
        "device",
        type=commandline.DeviceParser([commandline.DEVICE_SCHEME_SSH]),
        help="Target a device with hostname",
    )
    parser.add_argument("packages", help="Packages to install", nargs="+")
    parser.add_argument(
        "--restart-services",
        default=False,
        action="store_true",
        help="Restart affected services. Will shut down all running VMs",
    )
    parser.add_argument(
        "--dlc-ids",
        default=["termina-dlc"],
        nargs="+",
        choices=["termina-dlc", "termina-tools-dlc"],
        help="DLCs to deploy packages for",
    )
    return parser


def main(argv: List[str]):
    parser = get_parser()
    opts = parser.parse_args(argv)

    logging.notice("Getting package files")
    files = get_deployment_plan(opts.board, opts.packages)

    with remote_access.ChromiumOSDeviceHandler(
        hostname=opts.device.hostname,
        port=opts.device.port,
        username=opts.device.username,
    ) as remote:
        if opts.restart_services:
            remote.run(
                "stop vm_concierge && start vm_concierge",
                shell=True,
                capture_output=False,
            )
        for i, dlc_id in enumerate(opts.dlc_ids):
            deploy_into_remote_dlc(remote, files, dlc_id)
            if i < len(opts.dlc_ids) - 1:
                time.sleep(1)  # dlcservice may not be ready yet

    if not opts.restart_services:
        logging.notice(
            "Changes deployed. You must reboot before your changes take effect"
        )
    else:
        logging.notice(
            "Changes deployed. They will be picked up when you next launch a VM"
        )
