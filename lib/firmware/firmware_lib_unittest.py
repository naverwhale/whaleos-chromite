# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for the firmware_lib module."""

import os
import tempfile
from unittest import mock

from chromite.lib import build_target_lib
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import partial_mock
from chromite.lib.firmware import dut
from chromite.lib.firmware import firmware_config
from chromite.lib.firmware import firmware_lib
from chromite.lib.firmware import servo_lib


# pylint: disable=unused-argument
# pylint: disable=protected-access


class CleanTest(cros_test_lib.RunCommandTestCase):
    """Tests for cleaning up firmware artifacts and dependencies."""

    def setUp(self):
        self.pkgs = [
            "pkg1",
            "pkg2",
            "coreboot-private-files",
            "chromeos-config-bsp",
        ]

    def test_clean(self):
        """Smoke check for the clean command (ideal case)."""
        fw_config = mock.MagicMock(
            build_workon_packages=None, build_packages=("pkg3", "pkg4")
        )

        self.PatchObject(firmware_config, "get_config", return_value=fw_config)

        pkgs = [*self.pkgs, *fw_config.build_packages]

        self.rc.AddCmdResult(
            partial_mock.In("qfile-boardname"), stdout="\n".join(pkgs).encode()
        )
        self.PatchObject(osutils, "RmDir")
        firmware_lib.clean(build_target_lib.BuildTarget("boardname"))
        self.rc.assertCommandCalled(
            ["emerge-boardname", "--rage-clean", *sorted(pkgs)],
            capture_output=mock.ANY,
            dryrun=False,
        )

    def test_nonexistent_board_clean(self):
        """Verifies exception thrown when target board was not configured."""
        self.rc.AddCmdResult(
            partial_mock.In("qfile-schrodinger"),
            side_effect=cros_build_lib.RunCommandError("qfile: not found"),
        )
        with self.assertRaisesRegex(firmware_lib.CleanError, "qfile"):
            firmware_lib.clean(build_target_lib.BuildTarget("schrodinger"))


class FlashTest(cros_test_lib.RunCommandTestCase):
    """Tests for flashing firmware."""

    def setUp(self):
        self.build_target = build_target_lib.BuildTarget("amd64-generic")
        self.flashrom = False
        self.verbose = False
        self.dryrun = False
        self.flash_contents = None
        self.ssh_ip = "1.2.3.4"
        self.ssh_port = "22"
        self.servo_port = "9999"
        self.passthrough_args = None

    def test_servo_args(self):
        """Sanity check for the clean command (ideal case)."""

        def get_servo_side_effect() -> servo_lib.Servo:
            return servo_lib.Servo("servo_v4p1_with_ccd", "123456ab")

        get_servo_mock = self.PatchObject(
            dut.DutControl, "get_servo", side_effect=get_servo_side_effect
        )

        with tempfile.NamedTemporaryFile() as image_file:
            firmware_lib._deploy_servo(
                self.build_target,
                image_file.name,
                self.flashrom,
                self.verbose,
                self.servo_port,
                self.dryrun,
                self.flash_contents,
                self.passthrough_args,
            )
        self.rc.assertCommandCalled(
            [
                "dut-control",
                f"--port={self.servo_port}",
                "ec_uart_timeout:10",
            ],
            print_cmd=False,
            dryrun=False,
        )
        self.rc.assertCommandCalled(
            [
                "dut-control",
                f"--port={self.servo_port}",
                "ccd_cpu_fw_spi:on",
            ],
            print_cmd=False,
            dryrun=False,
        )
        self.rc.assertCommandCalled(
            [
                "sudo",
                "--",
                "futility",
                "update",
                "-p",
                "raiden_debug_spi:target=AP,custom_rst=true,serial=123456ab",
                "-i",
                mock.ANY,
                "--force",
                "--wp=0",
                "--fast",
            ],
            print_cmd=False,
            dryrun=False,
        )
        self.rc.assertCommandCalled(
            [
                "dut-control",
                f"--port={self.servo_port}",
                "ccd_cpu_fw_spi:off",
            ],
            print_cmd=False,
            dryrun=False,
        )
        get_servo_mock.assert_any_call()

    def test_ssh_args(self):
        """Sanity check for the clean command (ideal case)."""
        with tempfile.NamedTemporaryFile() as image_file:
            firmware_lib._deploy_ssh(
                self.build_target,
                image_file.name,
                self.flashrom,
                self.verbose,
                self.ssh_ip,
                self.ssh_port,
                self.dryrun,
                self.passthrough_args,
            )
            ssh_keys_expected = ["-i", mock.ANY]
            if os.path.exists(firmware_lib._ssh_partner_id_filename):
                ssh_keys_expected += ["-i", mock.ANY]

            self.rc.assertCommandCalled(
                [
                    "scp",
                    *ssh_keys_expected,
                    "-P",
                    self.ssh_port,
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "CheckHostIP=no",
                    mock.ANY,
                    f"root@{self.ssh_ip}:/tmp",
                ],
                print_cmd=False,
                check=True,
                dryrun=False,
            )
            self.rc.assertCommandCalled(
                [
                    "ssh",
                    f"root@{self.ssh_ip}",
                    *ssh_keys_expected,
                    "-p",
                    self.ssh_port,
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "CheckHostIP=no",
                    "futility",
                    "update",
                    "-p",
                    "internal",
                    "-i",
                    mock.ANY,
                    "&& reboot",
                ],
                print_cmd=False,
                check=True,
                dryrun=False,
            )


class ReadTest(cros_test_lib.RunCommandTestCase):
    """Tests for reading firmware."""

    def setUp(self):
        self.verbose = False
        self.dryrun = False
        self.ssh_ip = "1.2.3.4"
        self.ssh_port = "22"
        self.region_to_read = ""

    def test_ssh_args(self):
        """Sanity check for the clean command (ideal case)."""
        with tempfile.NamedTemporaryFile() as image_file:
            firmware_lib.ssh_read(
                image_file.name,
                self.verbose,
                self.ssh_ip,
                self.ssh_port,
                self.dryrun,
                self.region_to_read,
            )
            ssh_keys_expected = ["-i", mock.ANY]
            if os.path.exists(firmware_lib._ssh_partner_id_filename):
                ssh_keys_expected += ["-i", mock.ANY]

            self.rc.assertCommandCalled(
                [
                    "ssh",
                    f"root@{self.ssh_ip}",
                    *ssh_keys_expected,
                    "-p",
                    self.ssh_port,
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "CheckHostIP=no",
                    "flashrom",
                    "-p",
                    "internal",
                    "-r",
                    image_file.name,
                ],
                print_cmd=False,
                check=True,
                dryrun=False,
            )
            self.rc.assertCommandCalled(
                [
                    "scp",
                    *ssh_keys_expected,
                    "-P",
                    self.ssh_port,
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "CheckHostIP=no",
                    mock.ANY,
                    image_file.name,
                ],
                print_cmd=False,
                check=True,
                dryrun=False,
            )
