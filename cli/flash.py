# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Install/copy the image to the device."""

from __future__ import division

import logging
import os
import re
import shutil

from chromite.cli import device_imager
from chromite.cli.cros import cros_chrome_sdk
from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import dev_server_wrapper as ds_wrapper
from chromite.lib import operation
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.lib import remote_access


def GetDefaultBoard():
    """Look up default board.

    In a chrome checkout, return $SDK_BOARD. In a chromeos checkout,
    return the contents of .default_board.
    """
    if path_util.DetermineCheckout().type == path_util.CheckoutType.GCLIENT:
        return os.environ.get(cros_chrome_sdk.SDKFetcher.SDK_BOARD_ENV)
    return cros_build_lib.GetDefaultBoard()


class UsbImagerOperation(operation.ProgressBarOperation):
    """Progress bar for flashing image to operation."""

    def __init__(self, image):
        super().__init__()
        self._size = os.path.getsize(image)
        self._transferred = 0
        self._bytes = re.compile(r"(\d+) bytes")

    def _GetDDPid(self):
        """Get the Pid of dd."""
        try:
            pids = cros_build_lib.run(
                ["pgrep", "dd"],
                capture_output=True,
                print_cmd=False,
                encoding="utf-8",
            ).stdout
            for pid in pids.splitlines():
                if osutils.IsChildProcess(int(pid), name="dd"):
                    return int(pid)
            return -1
        except cros_build_lib.RunCommandError:
            # If dd isn't still running, then we assume that it is finished.
            return -1

    def _PingDD(self, dd_pid):
        """Send USR1 signal to dd to get status update."""
        try:
            cmd = ["kill", "-USR1", str(dd_pid)]
            cros_build_lib.sudo_run(cmd, print_cmd=False)
        except cros_build_lib.RunCommandError:
            # Here we assume that dd finished in the background.
            return

    def ParseOutput(self, output=None):
        """Parse the output of dd to update progress bar."""
        dd_pid = self._GetDDPid()
        if dd_pid == -1:
            return

        self._PingDD(dd_pid)

        if output is None:
            stdout = self._stdout.read()
            stderr = self._stderr.read()
            output = stdout + stderr

        match = self._bytes.search(output)
        if match:
            self._transferred = int(match.groups()[0])

        self.ProgressBar(self._transferred / self._size)


def _IsFilePathGPTDiskImage(file_path, require_pmbr=False):
    """Determines if a file is a valid GPT disk.

    Args:
        file_path: Path to the file to test.
        require_pmbr: Whether to require a PMBR in LBA0.
    """
    if os.path.isfile(file_path):
        with open(file_path, "rb") as image_file:
            if require_pmbr:
                # Seek to the end of LBA0 and look for the PMBR boot signature.
                image_file.seek(0x1FE)
                if image_file.read(2) != b"\x55\xaa":
                    return False
                # Current file position is start of LBA1 now.
            else:
                # Seek to LBA1 where the GPT starts.
                image_file.seek(0x200)

            # See if there's a GPT here.
            if image_file.read(8) == b"EFI PART":
                return True

    return False


def _ChooseImageFromDirectory(dir_path):
    """Lists all image files in |dir_path| and ask user to select one.

    Args:
        dir_path: Path to the directory.
    """
    images = sorted(
        [
            x
            for x in os.listdir(dir_path)
            if _IsFilePathGPTDiskImage(os.path.join(dir_path, x))
        ]
    )
    idx = 0
    if not images:
        raise ValueError("No image found in %s." % dir_path)
    elif len(images) > 1:
        idx = cros_build_lib.GetChoice(
            "Multiple images found in %s. Please select one to continue:"
            % ((dir_path,)),
            images,
        )

    return os.path.join(dir_path, images[idx])


class FlashError(Exception):
    """Thrown when there is an unrecoverable error during flash."""


class USBImager:
    """Copy image to the target removable device."""

    def __init__(self, device, board, image, version, debug=False, yes=False):
        """Initializes USBImager."""
        self.device = device
        self.board = board if board else GetDefaultBoard()
        self.image = image
        self.version = version
        self.debug = debug
        self.debug_level = logging.DEBUG if debug else logging.INFO
        self.yes = yes

    def DeviceNameToPath(self, device_name):
        return "/dev/%s" % device_name

    def GetRemovableDeviceDescription(self, device):
        """Returns a informational description of the removable |device|.

        Args:
            device: the device name (e.g. sdc).

        Returns:
            A string describing |device| (e.g. Patriot Memory 7918 MB).
        """
        desc = [
            osutils.GetDeviceInfo(device, keyword="manufacturer"),
            osutils.GetDeviceInfo(device, keyword="product"),
            osutils.GetDeviceSize(self.DeviceNameToPath(device)),
            "(%s)" % self.DeviceNameToPath(device),
        ]
        return " ".join([x for x in desc if x])

    def ListAllRemovableDevices(self):
        """Returns a list of removable devices.

        Returns:
            A list of device names (e.g. ['sdb', 'sdc']).
        """
        devices = osutils.ListBlockDevices()
        removable_devices = []
        for d in devices:
            if d.TYPE == "disk" and (d.RM == "1" or d.HOTPLUG == "1"):
                removable_devices.append(d.NAME)

        return removable_devices

    def ChooseRemovableDevice(self, devices):
        """Lists all removable devices and asks user to select/confirm.

        Args:
            devices: a list of device names (e.g. ['sda', 'sdb']).

        Returns:
            The device name chosen by the user.
        """
        idx = cros_build_lib.GetChoice(
            "Removable device(s) found. Please select/confirm to continue:",
            [self.GetRemovableDeviceDescription(x) for x in devices],
        )

        return devices[idx]

    def CopyImageToDevice(self, image, device):
        """Copies |image| to the removable |device|.

        Args:
            image: Path to the image to copy.
            device: Device to copy to.
        """
        cmd = [
            "dd",
            "if=%s" % image,
            "of=%s" % device,
            "bs=4M",
            "iflag=fullblock",
            "oflag=direct",
            "conv=fdatasync",
        ]
        if logging.getLogger().getEffectiveLevel() <= logging.NOTICE:
            op = UsbImagerOperation(image)
            op.Run(
                cros_build_lib.sudo_run,
                cmd,
                debug_level=logging.NOTICE,
                encoding="utf-8",
                update_period=0.5,
            )
        else:
            cros_build_lib.sudo_run(
                cmd,
                debug_level=logging.NOTICE,
                print_cmd=logging.getLogger().getEffectiveLevel()
                < logging.NOTICE,
            )

        # dd likely didn't put the backup GPT in the last block. sfdisk fixes
        # this up for us with a 'write' command, so we have a
        # standards-conforming GPT. Ignore errors because sfdisk (util-linux <
        # v2.32) isn't always happy to fix GPT correctness issues.
        cros_build_lib.sudo_run(
            ["sfdisk", device],
            input="write\n",
            check=False,
            debug_level=self.debug_level,
        )

        cros_build_lib.sudo_run(
            ["partx", "-u", device], debug_level=self.debug_level
        )
        osutils.sync_storage(device, data_only=True, sudo=True)

    def _GetImagePath(self):
        """Returns the image path to use."""
        image_path = None
        if os.path.isfile(self.image):
            if not self.yes and not _IsFilePathGPTDiskImage(self.image):
                # TODO(wnwen): Open the tarball and if there is just one file in
                #   it, use that instead. Existing code in upload_symbols.py.
                if cros_build_lib.BooleanPrompt(
                    prolog="The given image file is not a valid disk image. "
                    "Perhaps you forgot to untar it.",
                    prompt="Terminate the current flash process?",
                ):
                    raise FlashError("Update terminated by user.")
            image_path = self.image
        elif os.path.isdir(self.image):
            # Ask user which image (*.bin) in the folder to use.
            image_path = _ChooseImageFromDirectory(self.image)
        else:
            # Translate the xbuddy path to get the exact image to use.
            _, image_path = ds_wrapper.GetImagePathWithXbuddy(
                self.image, self.board, self.version
            )

        logging.info("Using image %s", image_path)
        return image_path

    def Run(self):
        """Image the removable device."""
        devices = self.ListAllRemovableDevices()

        if self.device:
            # If user specified a device path, check if it exists.
            if not os.path.exists(self.device):
                raise FlashError("Device path %s does not exist." % self.device)

            # Then check if it is removable.
            if self.device not in [self.DeviceNameToPath(x) for x in devices]:
                msg = "%s is not a removable device." % self.device
                if not (
                    self.yes
                    or cros_build_lib.BooleanPrompt(default=False, prolog=msg)
                ):
                    raise FlashError(
                        "You can specify usb:// to choose from a list of "
                        "removable devices."
                    )
        target = None
        if self.device:
            # Get device name from path (e.g. sdc in /dev/sdc).
            target = self.device.rsplit(os.path.sep, 1)[-1]
        elif devices:
            # Ask user to choose from the list.
            target = self.ChooseRemovableDevice(devices)
        else:
            raise FlashError("No removable devices detected.")

        image_path = self._GetImagePath()
        device = self.DeviceNameToPath(target)

        device_size_bytes = osutils.GetDeviceSize(device, in_bytes=True)
        image_size_bytes = os.path.getsize(image_path)
        if device_size_bytes < image_size_bytes:
            raise FlashError(
                "Removable device %s has less storage (%d) than the image size "
                "(%d)." % (device, device_size_bytes, image_size_bytes)
            )

        try:
            self.CopyImageToDevice(image_path, device)
        except cros_build_lib.RunCommandError:
            logging.error(
                "Failed copying image to device %s",
                self.DeviceNameToPath(target),
            )


class FileImager(USBImager):
    """Copy image to the target path."""

    def Run(self):
        """Copy the image to the path specified by self.device."""
        if not os.path.isdir(os.path.dirname(self.device)):
            raise FlashError(
                "Parent of path %s is not a directory." % self.device
            )

        image_path = self._GetImagePath()
        if os.path.isdir(self.device):
            logging.info(
                "Copying to %s",
                os.path.join(self.device, os.path.basename(image_path)),
            )
        else:
            logging.info("Copying to %s", self.device)
        try:
            shutil.copy(image_path, self.device)
        except IOError:
            logging.error(
                "Failed to copy image %s to %s", image_path, self.device
            )


# TODO(b/190631159, b/196056723): Change default of no_minios_update to |False|.
def Flash(
    device,
    image,
    board=None,
    version=None,
    no_rootfs_update=False,
    no_stateful_update=False,
    no_minios_update=True,
    clobber_stateful=False,
    reboot=True,
    ssh_private_key=None,
    ping=True,
    disable_rootfs_verification=False,
    clear_cache=False,
    yes=False,
    force=False,
    debug=False,
    clear_tpm_owner=False,
    delta=False,
    reboot_timeout=None,
):
    """Flashes a device, USB drive, or file with an image.

    This provides functionality common to `cros flash` and `brillo flash`
    so that they can parse the commandline separately but still use the
    same underlying functionality.

    Args:
        device: commandline.Device object; None to use the default device.
        image: Path (string) to the update image. Can be a local or xbuddy path;
            non-existent local paths are converted to xbuddy.
        board: Board to use; None to automatically detect.
        no_rootfs_update: Don't update rootfs partition; SSH |device| scheme
            only.
        no_stateful_update: Don't update stateful partition; SSH |device| scheme
            only.
        no_minios_update: Don't update miniOS partition; SSH |device| scheme
            only.
        clobber_stateful: Clobber stateful partition; SSH |device| scheme only.
        clear_tpm_owner: Clear the TPM owner on reboot; SSH |device| scheme
            only.
        reboot: Reboot device after update; SSH |device| scheme only.
        ssh_private_key: Path to an SSH private key file; None to use test keys.
        ping: Ping the device before attempting update; SSH |device| scheme
            only.
        disable_rootfs_verification: Remove rootfs verification after update;
            SSH |device| scheme only.
        clear_cache: Clear the devserver static directory.
        yes: Assume "yes" for any prompt.
        force: Ignore confidence checks and prompts. Overrides |yes| if True.
        debug: Print additional debugging messages.
        version: Default version.
        delta: Whether to use delta compression when transferring image bytes.
        reboot_timeout: The timeout for reboot.

    Raises:
        FlashError: An unrecoverable error occurred.
        ValueError: Invalid parameter combination.
    """
    if force:
        yes = True

    if clear_cache:
        ds_wrapper.DevServerWrapper.WipeStaticDirectory()
    ds_wrapper.DevServerWrapper.CreateStaticDirectory()

    # The user may not have specified a source image, use version as the
    # default.
    image = image or version
    if not device or device.scheme == commandline.DEVICE_SCHEME_SSH:
        if device:
            hostname, port = device.hostname, device.port
        else:
            hostname, port = None, None

        with remote_access.ChromiumOSDeviceHandler(
            hostname, port=port, private_key=ssh_private_key, ping=ping
        ) as device_p:
            device_imager.DeviceImager(
                device_p,
                image,
                board=board,
                version=version,
                no_rootfs_update=no_rootfs_update,
                no_stateful_update=no_stateful_update,
                no_minios_update=no_minios_update,
                no_reboot=not reboot,
                disable_verification=disable_rootfs_verification,
                clobber_stateful=clobber_stateful,
                clear_tpm_owner=clear_tpm_owner,
                delta=delta,
                reboot_timeout=reboot_timeout,
            ).Run()
    elif device.scheme == commandline.DEVICE_SCHEME_USB:
        path = osutils.ExpandPath(device.path) if device.path else ""
        logging.info("Preparing to image the removable device %s", path)
        imager = USBImager(path, board, image, version, debug=debug, yes=yes)
        imager.Run()
    elif device.scheme == commandline.DEVICE_SCHEME_FILE:
        logging.info("Preparing to copy image to %s", device.path)
        imager = FileImager(
            device.path, board, image, version, debug=debug, yes=yes
        )
        imager.Run()
