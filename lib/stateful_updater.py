# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for updating the stateful partition on the device.

Use this module to update the stateful partition given a stateful payload
(e.g. stateful.tgz) on the device. This module untars/uncompresses the payload
on the device into var_new and dev_image_new directories. Optionally, you can
ask this module to reset a stateful partition by preparing it to be clobbered on
reboot.
"""

import logging
import os
import tempfile

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils


class Error(Exception):
    """Base exception class of StatefulUpdater errors."""


class StatefulUpdater:
    """The module for updating the stateful partition."""

    UPDATE_TYPE_STANDARD = "standard"
    UPDATE_TYPE_CLOBBER = "clobber"

    _VAR_DIR = "var_new"
    _DEV_IMAGE_DIR = "dev_image_new"
    _UPDATE_TYPE_FILE = ".update_available"

    def __init__(self, device, stateful_dir=constants.STATEFUL_DIR):
        """Initializes the module.

        Args:
            device: The ChromiumOsDevice to be updated.
            stateful_dir: The stateful directory on the Chromium OS device.
        """
        self._device = device
        self._stateful_dir = stateful_dir
        self._var_dir = os.path.join(self._stateful_dir, self._VAR_DIR)
        self._dev_image_dir = os.path.join(
            self._stateful_dir, self._DEV_IMAGE_DIR
        )
        self._update_type_file = os.path.join(
            self._stateful_dir, self._UPDATE_TYPE_FILE
        )

    def Update(self, payload_path, is_payload_on_device=True, update_type=None):
        """Updates the stateful partition given the update file.

        Args:
            payload_path: The path to the stateful update (stateful.tgz). It can
                also be just a file descriptor.
            is_payload_on_device: True if the payload is on the device. False
                if it is on the workstation.
            update_type: The type of the stateful update to be marked. Accepted
                values: 'standard' (default) and 'clobber'.
        """
        try:
            cmd = [
                "tar",
                "--ignore-command-error",
                "--overwrite",
                "--selinux",
                "--directory",
                self._stateful_dir,
                "-xzf",
            ]
            if is_payload_on_device:
                if not self._device.IfPathExists(payload_path):
                    raise Error("Missing the file: %s" % payload_path)

                cmd += [payload_path]
                self._device.run(cmd)
            elif isinstance(payload_path, int):
                cmd += ["-"]
                self._device.run(cmd, input=payload_path)
            else:
                with open(payload_path, "rb") as f:
                    cmd += ["-"]
                    self._device.run(cmd, input=f)
        except cros_build_lib.RunCommandError as e:
            raise Error("Failed to untar the stateful update with error %s" % e)

        # Make sure target directories are generated on the device.
        if not self._device.IfPathExists(
            self._var_dir
        ) or not self._device.IfPathExists(self._dev_image_dir):
            raise Error("Missing var or dev_image in stateful payload.")

        self._MarkUpdateType(
            update_type
            if update_type is not None
            else self.UPDATE_TYPE_STANDARD
        )

    def _MarkUpdateType(self, update_type):
        """Marks the type of the update.

        Args:
            update_type: The type of the update to be marked. See Update()
        """
        if update_type not in (
            self.UPDATE_TYPE_CLOBBER,
            self.UPDATE_TYPE_STANDARD,
        ):
            raise Error("Invalid update type %s" % update_type)

        with tempfile.NamedTemporaryFile() as f:
            if update_type == self.UPDATE_TYPE_STANDARD:
                logging.notice("Performing standard stateful update...")
            elif update_type == self.UPDATE_TYPE_CLOBBER:
                logging.notice(
                    "Restoring stateful to factory_install " "with dev_image..."
                )
                osutils.WriteFile(f.name, "clobber")

            try:
                self._device.CopyToDevice(f.name, self._update_type_file, "scp")
            except cros_build_lib.RunCommandError as e:
                raise Error(
                    "Failed to copy update type file to device with error %s"
                    % e
                )

    def Reset(self):
        """Resets the stateful partition."""
        logging.info("Resetting stateful update state.")

        try:
            self._device.run(
                [
                    "rm",
                    "-rf",
                    self._update_type_file,
                    self._var_dir,
                    self._dev_image_dir,
                ]
            )
        except cros_build_lib.RunCommandError as e:
            logging.warning(
                "(ignoring) Failed to delete stateful update paths with"
                " error: %s",
                e,
            )
