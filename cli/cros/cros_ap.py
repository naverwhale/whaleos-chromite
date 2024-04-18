# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""cros ap: firmware AP related commands."""

import argparse
import logging
import os
from pathlib import Path

from chromite.cli import command
from chromite.lib import build_target_lib
from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib.firmware import dut
from chromite.lib.firmware import firmware_config
from chromite.lib.firmware import firmware_lib


# All known ap subcommands.
SUBCOMMANDS = {}


def subcommand_decorator(name):
    """Decorator that validates and registers subcommands."""

    def inner_decorator(original_class):
        """Inner decorator that actually wraps the class."""
        assert hasattr(original_class, "__doc__"), f"{name}: missing docstring"

        assert issubclass(
            original_class, command.CliCommand
        ), f"{original_class}: subcommands must derive from CliCommand"

        SUBCOMMANDS[name] = original_class

        return original_class

    return inner_decorator


@command.command_decorator("ap")
class APCommand(command.CliCommand):
    """Execute an AP-related command."""

    EPILOG = "Use `cros ${subcommand} --help` to see command-specific help."

    @classmethod
    def AddParser(cls, parser):
        """Add AP specific subcommands and options."""
        super(APCommand, cls).AddParser(parser)
        subparsers = parser.add_subparsers(
            title="AP subcommands", dest="ap_command"
        )
        subparsers.required = True

        for name, subcommand_class in SUBCOMMANDS.items():
            sub_parser = subparsers.add_parser(
                name,
                description=subcommand_class.__doc__,
                caching=parser.caching,
                dryrun=True,
                help=subcommand_class.__doc__,
                formatter_class=parser.formatter_class,
            )
            subcommand_class.AddParser(sub_parser)

    @classmethod
    def ProcessOptions(cls, parser, options):
        """Post process options."""
        sub_class = SUBCOMMANDS[options.ap_command]
        sub_class.ProcessOptions(parser, options)

    def Run(self):
        """The main handler of this CLI."""
        cls = SUBCOMMANDS[self.options.ap_command]
        subcmd = cls(self.options)
        return subcmd.Run()


@subcommand_decorator("build")
class BuildSubcommand(command.CliCommand):
    """Build the AP Firmware for the requested build target."""

    def __init__(self, options):
        super().__init__(options)
        self.build_target = build_target_lib.BuildTarget(
            self.options.build_target
        )

    @classmethod
    def AddParser(cls, parser):
        """Adds AP Build specific CLI arguments to parser."""
        parser.add_argument(
            "-b",
            "--build-target",
            dest="build_target",
            default=cros_build_lib.GetDefaultBoard(),
            required=not bool(cros_build_lib.GetDefaultBoard()),
            help="The build target whose AP firmware should be built.",
        )
        parser.add_argument(
            "--fw-name",
            "--variant",
            dest="fw_name",
            help="Sets the FW_NAME environment variable. Set to build only the "
            "specified variant's firmware.",
        )
        parser.epilog = """
To build the AP Firmware for foo:
  cros ap build -b foo

To build the AP Firmware only for foo-variant:
  cros ap build -b foo --fw-name foo-variant
"""

    def Run(self):
        commandline.RunInsideChroot(self)

        try:
            firmware_lib.build(
                self.build_target,
                fw_name=self.options.fw_name,
                dry_run=self.options.dryrun,
            )
        except firmware_lib.Error as e:
            cros_build_lib.Die(e)


@subcommand_decorator("read")
class ReadSubcommand(command.CliCommand):
    """Read the AP Firmware from a device."""

    @classmethod
    def ProcessOptions(cls, parser, options):
        """Post process options."""
        if options.device is None:
            parser.error("Specify device using --device argument.")
        options.output_path = Path(options.output)

    @classmethod
    def AddParser(cls, parser):
        """Adds AP Read specific CLI arguments to parser."""
        cls.AddDeviceArgument(
            parser,
            schemes=[
                commandline.DEVICE_SCHEME_SSH,
                commandline.DEVICE_SCHEME_SERVO,
            ],
        )
        parser.add_argument(
            "-b",
            "--build-target",
            default=cros_build_lib.GetDefaultBoard(),
            dest="build_target",
            help="The name of the build target.",
        )
        parser.add_argument(
            "-r" "--region", dest="region", type=str, help="Region to read."
        )
        parser.add_argument(
            "-o", "--output", type="path", required=True, help="Output file."
        )
        parser.epilog = """Command to read the AP firmware from a DUT.
To read image of device.cros via SSH:
  cros ap read -b volteer -o /tmp/volteer-image.bin -d ssh://device.cros

If you don't have ssh access from within the chroot, you may set up ssh tunnel:
  ssh -L 2222:localhost:22 device.cros
  cros ap read -b volteer -o /tmp/volteer-image.bin -d ssh://localhost:2222

To read image from DUT via SERVO on port 1234:
  cros ap read -b volteer -o /tmp/volteer-image.bin -d servo:port:1234

To read a specific region from DUT via SERVO on default port(9999):
  cros ap read -b volteer -r region -o /tmp/volteer-image.bin -d servo:port
"""

    def Run(self):
        if not cros_build_lib.IsInsideChroot():
            logging.notice(
                "Command will run in chroot, "
                "and the output file path will be inside."
            )
        commandline.RunInsideChroot(self)
        build_target = build_target_lib.BuildTarget(self.options.build_target)

        ip = None
        if self.options.device:
            port = self.options.device.port
            if self.options.device.scheme == commandline.DEVICE_SCHEME_SSH:
                ip = self.options.device.hostname
                port = port or self.options.device.port
        else:
            ip = os.getenv("IP")

        region = None
        if hasattr(self.options, "region"):
            region = self.options.region

        if ip:
            firmware_lib.ssh_read(
                self.options.output,
                self.options.verbose,
                ip,
                port,
                self.options.dryrun,
                region,
            )
        else:
            dut_ctl = dut.DutControl(port)
            servo = dut_ctl.get_servo()

            ap_config = firmware_config.get_config(build_target.name, servo)

            flashrom_cmd = [
                "flashrom",
                "-p",
                ap_config.programmer,
                "-r",
                self.options.output,
            ]
            if self.options.verbose:
                flashrom_cmd += ["-V"]
            if region:
                flashrom_cmd += ["-i", self.options.region]
            if not dut_ctl.servo_run(
                ap_config.dut_control_on,
                ap_config.dut_control_off,
                flashrom_cmd,
                self.options.verbose,
                self.options.dryrun,
            ):
                logging.error(
                    "Unable to read, verify servo connection "
                    "is correct and servod is running in the background."
                )


@subcommand_decorator("flash")
class FlashSubcommand(command.CliCommand):
    """Update the AP Firmware on a device."""

    @classmethod
    def ProcessOptions(cls, parser, options):
        """Post process options."""
        if not os.path.exists(options.image):
            parser.error(
                f"{options.image} does not exist, verify the path of your "
                "build and try again."
            )
        if options.fast:
            parser.error(
                "Flags such as --fast must be passed directly after --\n"
                "For futility use: cros ap flash ${OTHER_ARGS} -- --fast\n"
                "For flashrom use: cros ap flash --flashrom ${OTHER_ARGS} -- -n"
            )

    @classmethod
    def AddParser(cls, parser):
        """Adds AP Flash specific CLI arguments to parser."""
        cls.AddDeviceArgument(
            parser,
            schemes=[
                commandline.DEVICE_SCHEME_SSH,
                commandline.DEVICE_SCHEME_SERVO,
            ],
        )
        parser.add_argument(
            "-i",
            "--image",
            required=True,
            type="path",
            help="/path/to/BIOS_image.bin",
        )
        parser.add_argument(
            "-b",
            "--build-target",
            default=cros_build_lib.GetDefaultBoard(),
            dest="build_target",
            help="The name of the build target.",
        )
        parser.add_argument(
            "--flashrom",
            action="store_true",
            help="Use flashrom to flash instead of futility.",
        )
        parser.add_argument(
            "--flash-contents",
            type=str,
            help="Assume flash contents to be the specified file. "
            "Only available when using --flashrom.",
        )
        parser.add_argument(
            "--fast",
            action="store_true",
            help="Deprecated. Pass your arbitrary flags after --.",
        )
        parser.add_argument(
            "extra_options",
            nargs=argparse.REMAINDER,
            help="Pass additional options to flashrom/futility.",
        )
        parser.epilog = """
Command to flash the AP firmware onto a DUT.

To flash your zork DUT with an IP of 1.1.1.1 via SSH:
  cros ap flash -b zork -i /path/to/image.bin -d ssh://1.1.1.1

To flash your volteer DUT via SERVO on the default port (9999):
  cros ap flash -d servo:port -b volteer -i /path/to/image.bin

To flash your volteer DUT via SERVO on port 1234:
  cros ap flash -d servo:port:1234 -b volteer -i /path/to/image.bin

To pass additional options to futility or flashrom, provide them after `--`,
e.g.:
  cros ap flash -b zork -i /path/to/image.bin -d ssh://1.1.1.1 -- --force
"""

    def Run(self):
        commandline.RunInsideChroot(self)

        passthrough_args = self.options.extra_options
        if passthrough_args and passthrough_args[0] == "--":
            del passthrough_args[0]

        build_target = build_target_lib.BuildTarget(self.options.build_target)
        try:
            firmware_lib.deploy(
                build_target,
                self.options.image,
                self.options.device,
                flashrom=self.options.flashrom,
                verbose=self.options.verbose,
                dryrun=self.options.dryrun,
                flash_contents=self.options.flash_contents,
                passthrough_args=passthrough_args,
            )
        except firmware_lib.Error as e:
            cros_build_lib.Die(e)


@subcommand_decorator("clean")
class CleanSubcommand(command.CliCommand):
    """Clean up dependencies and artifacts for the requested build target."""

    def __init__(self, options):
        super().__init__(options)
        self.build_target = build_target_lib.BuildTarget(
            self.options.build_target
        )

    @classmethod
    def AddParser(cls, parser):
        """Adds AP Clean specific CLI arguments to parser."""
        parser.add_argument(
            "-b",
            "--build-target",
            default=cros_build_lib.GetDefaultBoard(),
            required=not bool(cros_build_lib.GetDefaultBoard()),
            help="The build target whose artifacts should be cleaned.",
        )
        parser.epilog = """
This command removes firmware-related packages, including everything in
`/build/${build_target}/firmware`.
"""

    def Run(self):
        if not cros_build_lib.IsInsideChroot():
            logging.notice(
                "Command will run in chroot, "
                "and the output file path will be inside."
            )
        commandline.RunInsideChroot(self)

        try:
            firmware_lib.clean(self.build_target, self.options.dryrun)
        except firmware_lib.Error as e:
            cros_build_lib.Die(e)
