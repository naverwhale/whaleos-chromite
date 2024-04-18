# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities to run DUT Control commands, get values from Servo."""

import logging
import time
from typing import List

from chromite.lib import cros_build_lib
from chromite.lib.firmware import servo_lib


class Error(Exception):
    """Base error class for the module."""


class InvalidServoVersionError(Error):
    """Invalid servo version error."""


class DutConnectionError(Error):
    """Error when fetching data from a dut."""


class DutControl:
    """Wrapper for dut_control calls."""

    def __init__(self, port):
        self._base_cmd = ["dut-control"]
        if port:
            self._base_cmd.append("--port=%s" % port)

    def get_servo(self) -> servo_lib.Servo:
        """Get the Servo instance the given dut_control command is using."""
        servo_type = self.get_value("servo_type")

        if "_and_" in servo_type:
            # If servod is working with multiple interfaces then servo_type will
            # be along the lines of "servo_v4p1_with_servo_micro_and_ccd_cr50".
            # We need to pick an interface, so grab everything before "_and_".
            first_servo_type = servo_type.split("_and_")[0]
            logging.warning(
                "Dual-mode servo detected. Treating %s as %s",
                servo_type,
                first_servo_type,
            )
            servo_type = first_servo_type

        if servo_type not in servo_lib.VALID_SERVOS:
            raise InvalidServoVersionError(
                "Unrecognized servo version: %s" % servo_type
            )

        option = servo_lib.get_serial_option(servo_type)
        serial = self.get_value(option)
        return servo_lib.Servo(servo_type, serial)

    def get_value(self, arg):
        """Get the value of |arg| from dut_control."""
        try:
            result = cros_build_lib.run(
                self._base_cmd + [arg], stdout=True, encoding="utf-8"
            )
        except cros_build_lib.CalledProcessError as e:
            logging.debug("dut-control error: %s", str(e))
            raise DutConnectionError(
                "Could not establish servo connection. Verify servod is running"
                "in the background, and the servo is properly connected."
            )

        # Return value from the "key:value" output.
        return result.stdout.partition(":")[2].strip()

    def run(
        self,
        cmd_fragment: List[str],
        verbose: bool = False,
        dryrun: bool = False,
    ):
        """Run a dut_control command.

        Args:
            cmd_fragment: The dut_control command to run.
            verbose: Whether to print the command before it's run.
            dryrun: Whether to actually execute the command or just print it.
        """
        cros_build_lib.run(
            self._base_cmd + cmd_fragment, print_cmd=verbose, dryrun=dryrun
        )

    def run_all(
        self,
        cmd_fragments: List[List[str]],
        verbose: bool = False,
        dryrun: bool = False,
    ):
        """Run multiple dut_control commands in the order given.

        Args:
            cmd_fragments: The dut_control commands to run.
            verbose: Whether to print the commands as they are run.
            dryrun: Whether to actually execute the command or just print it.
        """
        for cmd in cmd_fragments:
            self.run(cmd, verbose=verbose, dryrun=dryrun)

    def servo_run(
        self,
        dut_cmd_on: List[List[str]],
        dut_cmd_off: List[List[str]],
        flash_cmd: List[str],
        verbose: bool,
        dryrun: bool,
    ):
        """Runs subprocesses for setting dut controls and executing flash_cmd.

        Args:
            dut_cmd_on: 2d array of dut-control commands
                in the form [['dut-control', 'cmd1', 'cmd2'...],
                ['dut-control', 'cmd3'...]]
                that get executed before the dut_cmd.
            dut_cmd_off: 2d array of dut-control commands
                in the same form that get executed after the dut_cmd.
            flash_cmd: array containing all arguments for
                the actual command. Run as root user on host.
            verbose: if True then print out the various
                commands before running them.
            dryrun: if True then print the commands without executing.

        Returns:
            bool: True if commands were run successfully, otherwise False.
        """
        success = True
        try:
            # Dut on command runs.
            self.run_all(dut_cmd_on, verbose=verbose, dryrun=dryrun)

            # Need to wait for SPI chip power to stabilize (for some designs)
            time.sleep(1)

            # Run the flash command.
            cros_build_lib.sudo_run(flash_cmd, print_cmd=verbose, dryrun=dryrun)
        except cros_build_lib.CalledProcessError:
            logging.error("DUT command failed, see output above for more info.")
            success = False
        finally:
            # Run the dut off commands to clean up state if possible.
            try:
                self.run_all(dut_cmd_off, verbose=verbose, dryrun=dryrun)
            except cros_build_lib.CalledProcessError:
                logging.error(
                    "DUT cmd off failed, see output above for more info."
                )
                success = False

        return success
