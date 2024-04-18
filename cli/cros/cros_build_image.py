# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""cros build-image is used to build a ChromiumOS image.

ChromiumOS comes in many different forms. This script can be used to build
the following:

base - Pristine ChromiumOS image. As similar to ChromeOS as possible.
dev [default] - Developer image. Like base but with additional dev packages.
test - Like dev, but with additional test specific packages and can be easily
    used for automated testing using scripts like test_that, etc.
factory_install - Install shim for bootstrapping the factory test process.
    Cannot be built along with any other image.

Examples:

cros build-image --board=<board> dev test - build developer and test images.
cros build-image --board=<board> factory_install - build a factory install shim.

Note if you want to build an image with custom size partitions, either consider
adding a new disk layout in build_library/legacy_disk_layout.json OR use
adjust-part. Here are a few examples:

adjust-part='STATE:+1G' -- add one GB to the size the stateful partition
adjust-part='ROOT-A:-1G' -- remove one GB from the primary rootfs partition
adjust-part='STATE:=1G' --  make the stateful partition 1 GB
"""

import argparse
import logging
import os
from pathlib import Path
import sys
from typing import List, Optional

from chromite.third_party.opentelemetry import trace
from chromite.third_party.opentelemetry.trace import status

from chromite.cli import command
from chromite.lib import chromite_config
from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import namespaces
from chromite.lib import path_util
from chromite.service import image
from chromite.utils import telemetry
from chromite.utils import timer


def build_shell_bool_style_args(
    parser: commandline.ArgumentParser,
    name: str,
    default_val: bool,
    help_str: str,
    deprecation_note: str,
    alternate_name: Optional[str] = None,
    additional_neg_options: Optional[List[str]] = None,
) -> None:
    """Build the shell boolean input argument equivalent.

    There are two cases which we will need to handle,
    case 1: A shell boolean arg, which doesn't need to be re-worded in python.
    case 2: A shell boolean arg, which needs to be re-worded in python.
    Example below.
    For Case 1, for a given input arg name 'argA', we create three python
    arguments.
    --argA, --noargA, --no-argA. The arguments --argA and --no-argA will be
    retained after deprecating --noargA.
    For Case 2, for a given input arg name 'arg_A' we need to use alternate
    argument name 'arg-A'. we create four python arguments in this case.
    --arg_A, --noarg_A, --arg-A, --no-arg-A. The first two arguments will be
    deprecated later.
    TODO(b/232566937): Remove the creation of --noargA in case 1 and --arg_A and
    --noarg_A in case 2.

    Args:
        parser: The parser to update.
        name: The input argument name. This will be used as 'dest' variable
            name.
        default_val: The default value to assign.
        help_str: The help string for the input argument.
        deprecation_note: A deprecation note to use.
        alternate_name: Alternate argument to be used after deprecation.
        additional_neg_options: Additional negative alias options to use.
    """
    arg = f"--{name}"
    shell_narg = f"--no{name}"
    py_narg = f"--no-{name}"
    alt_arg = f"--{alternate_name}" if alternate_name else None
    alt_py_narg = f"--no-{alternate_name}" if alternate_name else None
    default_val_str = f"{help_str} (Default: %(default)s)."

    if alternate_name:
        _alternate_narg_list = [alt_py_narg]
        if additional_neg_options:
            _alternate_narg_list.extend(additional_neg_options)

        parser.add_argument(
            alt_arg,
            action="store_true",
            default=default_val,
            dest=name,
            help=default_val_str,
        )
        parser.add_argument(
            *_alternate_narg_list,
            action="store_false",
            dest=name,
            help="Don't " + help_str.lower(),
        )

    parser.add_argument(
        arg,
        action="store_true",
        default=default_val,
        dest=name,
        deprecated=deprecation_note % alt_arg if alternate_name else None,
        help=default_val_str if not alternate_name else argparse.SUPPRESS,
    )
    parser.add_argument(
        shell_narg,
        action="store_false",
        dest=name,
        deprecated=deprecation_note
        % (alt_py_narg if alternate_name else py_narg),
        help=argparse.SUPPRESS,
    )

    if not alternate_name:
        _py_narg_list = [py_narg]
        if additional_neg_options:
            _py_narg_list.extend(additional_neg_options)

        parser.add_argument(
            *_py_narg_list,
            action="store_false",
            dest=name,
            help="Don't " + help_str.lower(),
        )


def build_shell_string_style_args(
    parser: commandline.ArgumentParser,
    name: str,
    default_val: Optional[str],
    help_str: str,
    deprecation_note: str,
    alternate_name: str,
) -> None:
    """Build the shell string input argument equivalent.

    Args:
        parser: The parser to update.
        name: The input argument name. This will be used as 'dest' variable
            name.
        default_val: The default value to assign.
        help_str: The help string for the input argument.
        deprecation_note: A deprecation note to use.
        alternate_name: Alternate argument to be used after deprecation.
    """
    default_val_str = (
        f"{help_str} (Default: %(default)s)." if default_val else help_str
    )

    parser.add_argument(
        f"--{alternate_name}",
        dest=f"{name}",
        default=default_val,
        help=default_val_str,
    )
    parser.add_argument(
        f"--{name}",
        deprecated=deprecation_note % f"--{alternate_name}",
        help=argparse.SUPPRESS,
    )


tracer = trace.get_tracer(__name__)


@timer.timed("Elapsed time (cros build-image)")
def inner_main(options: commandline.ArgumentNamespace) -> image.BuildResult:
    """Inner main that processes building the image."""

    # If the opts.board is not set, then it means user hasn't specified a
    # default board in 'src/scripts/.default_board' and didn't specify it as
    # input argument.
    if not options.board:
        options.parser.error("--board is required")

    invalid_image = [
        x for x in options.images if x not in constants.IMAGE_TYPE_TO_NAME
    ]
    if invalid_image:
        options.parser.error(f"Invalid image type argument(s) {invalid_image}")

    return image.Build(options.board, options.images, options.build_run_config)


@command.command_decorator("build-image")
class BuildImageCommand(command.CliCommand):
    """Build a ChromiumOS image."""

    @classmethod
    def AddParser(cls, parser: commandline.ArgumentParser):
        """Build the parser.

        Args:
            parser: The parser.
        """
        super().AddParser(parser)
        parser.description = __doc__

        deprecation_note = (
            "Argument will be removed January 2023. Use %s instead."
        )

        parser.add_argument(
            "-b",
            "--board",
            "--build-target",
            dest="board",
            default=cros_build_lib.GetDefaultBoard(),
            help="The board to build images for.",
        )
        build_shell_string_style_args(
            parser,
            "adjust_part",
            None,
            "Adjustments to apply to partition table (LABEL:[+-=]SIZE) "
            "e.g. ROOT-A:+1G.",
            deprecation_note,
            "adjust-partition",
        )
        build_shell_string_style_args(
            parser,
            "output_root",
            constants.DEFAULT_BUILD_ROOT / "images",
            "Directory in which to place image result directories "
            "(named by version).",
            deprecation_note,
            "output-root",
        )
        build_shell_string_style_args(
            parser,
            "builder_path",
            None,
            "The build name to be installed on DUT during hwtest.",
            deprecation_note,
            "builder-path",
        )
        build_shell_string_style_args(
            parser,
            "disk_layout",
            "default",
            "The disk layout type to use for this image.",
            deprecation_note,
            "disk-layout",
        )

        # Kernel related options.
        group = parser.add_argument_group("Kernel Options")
        build_shell_string_style_args(
            group,
            "enable_serial",
            None,
            "Enable serial port for printks. Example values: ttyS0.",
            deprecation_note,
            "enable-serial",
        )
        group.add_argument(
            "--kernel-loglevel",
            type=int,
            default=7,
            help="The loglevel to add to the kernel command line. "
            "(Default: %(default)s).",
        )
        group.add_argument(
            "--loglevel",
            dest="kernel_loglevel",
            type=int,
            deprecated=deprecation_note % "kernel-loglevel",
            help=argparse.SUPPRESS,
        )

        # Bootloader related options.
        group = parser.add_argument_group("Bootloader Options")
        build_shell_string_style_args(
            group,
            "boot_args",
            "noinitrd",
            "Additional boot arguments to pass to the commandline.",
            deprecation_note,
            "boot-args",
        )
        build_shell_bool_style_args(
            group,
            "enable_rootfs_verification",
            True,
            "Make all bootloaders use kernel based rootfs integrity checking.",
            deprecation_note,
            "enable-rootfs-verification",
            ["-r"],
        )

        # Advanced options.
        group = parser.add_argument_group("Advanced Options")
        group.add_argument(
            "--build-attempt",
            type=int,
            help="Build attempt for this image build. (Default: %(default)s).",
        )
        group.add_argument(
            "--build_attempt",
            type=int,
            deprecated=deprecation_note % "build-attempt",
            help=argparse.SUPPRESS,
        )
        build_shell_string_style_args(
            group,
            "build_root",
            constants.DEFAULT_BUILD_ROOT / "images",
            "Directory in which to compose the image, before copying it to "
            "output_root.",
            deprecation_note,
            "build-root",
        )
        group.add_argument(
            "-j",
            "--jobs",
            dest="jobs",
            type=int,
            default=os.cpu_count(),
            help="Number of packages to build in parallel at maximum. "
            "(Default: %(default)s).",
        )
        build_shell_bool_style_args(
            group,
            "replace",
            False,
            "Overwrite existing output, if any.",
            deprecation_note,
        )
        group.add_argument(
            "--symlink",
            default="latest",
            help="Symlink name to use for this image. (Default: %(default)s).",
        )
        group.add_argument(
            "--version",
            default=None,
            help="Overrides version number in name to this version.",
        )
        build_shell_string_style_args(
            group,
            "output_suffix",
            None,
            "Add custom suffix to output directory.",
            deprecation_note,
            "output-suffix",
        )
        group.add_argument(
            "--eclean",
            action="store_true",
            default=True,
            dest="eclean",
            deprecated=(
                "eclean is being removed from `cros build-image`.  Argument "
                "will be removed January 2023."
            ),
            help=argparse.SUPPRESS,
        )
        group.add_argument(
            "--noeclean",
            action="store_false",
            dest="eclean",
            deprecated=(
                "eclean is being removed from `cros build-image`.  Argument "
                "will be removed January 2023."
            ),
            help=argparse.SUPPRESS,
        )
        group.add_argument(
            "--no-eclean",
            action="store_false",
            dest="eclean",
            deprecated=(
                "eclean is being removed from `cros build-image`.  Argument "
                "will be removed January 2023."
            ),
            help=argparse.SUPPRESS,
        )

        parser.add_argument(
            "images",
            nargs="*",
            default=["dev"],
            help="list of images to build. (Default: %(default)s).",
        )

    @classmethod
    def ProcessOptions(cls, parser, options):
        """Post-process options prior to freeze."""
        options.parser = parser
        options.build_run_config = image.BuildConfig(
            adjust_partition=options.adjust_part,
            output_root=options.output_root,
            builder_path=options.builder_path,
            disk_layout=options.disk_layout,
            enable_serial=options.enable_serial,
            kernel_loglevel=options.kernel_loglevel,
            boot_args=options.boot_args,
            enable_rootfs_verification=options.enable_rootfs_verification,
            build_attempt=options.build_attempt,
            build_root=options.build_root,
            jobs=options.jobs,
            replace=options.replace,
            symlink=options.symlink,
            version=options.version,
            output_dir_suffix=options.output_suffix,
        )

    def Run(self):
        chroot_args = []
        try:
            chroot_args += ["--working-dir", path_util.ToChrootPath(Path.cwd())]
        except ValueError:
            logging.warning("Unable to translate CWD to a chroot path.")
        commandline.RunInsideChroot(self, chroot_args=chroot_args)
        commandline.RunAsRootUser(sys.argv, preserve_env=True)

        chromite_config.initialize()
        telemetry.initialize(
            chromite_config.TELEMETRY_CONFIG,
            log_traces=self.options.log_telemetry,
        )

        result = None

        with tracer.start_as_current_span("cli.cros.cros_build_image.Run") as s:
            with namespaces.use_network_sandbox():
                result = inner_main(self.options)

            if result and result.run_error:
                s.record_exception(
                    # TODO(zland): capture underlying exception details/runtime
                    # errors to stringify for trace data.
                    cros_build_lib.RunCommandError(
                        "an exception occurred when running "
                        "chromite.service.image.Build."
                    )
                )
                s.set_status(status.StatusCode.ERROR)
                cros_build_lib.Die(
                    "Error running build-image. "
                    f"Exit Code: {result.return_code}"
                )
