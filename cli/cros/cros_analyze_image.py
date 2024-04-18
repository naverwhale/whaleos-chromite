# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Analyze image sizes.

Lists the sizes of any subdirectries in a Chrome OS image that are larger than
a minimum size.

The image may exist locally or be fetched from Google Storage by version number.

Live builds found here:
https://cros-goldeneye.corp.google.com/chromeos/console/liveBuilds

Example run with board and version:
$ cros analyze-image --board=coral --version=R86-13421.0.0 --spreadsheet

Example run, first download then process image numbers:
$ cros analyze-image --board=coral --version=R86-13421.0.0 \
    --local-path=/tmp/cros-analyze-coral-m86.bin
$ cros analyze-image --image=/tmp/cros-analyze-coral-m86.bin
"""

import csv
import logging
import shutil
import sys
import typing

from chromite.cli import command
from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import dev_server_wrapper as ds_wrapper
from chromite.lib import image_lib
from chromite.lib import osutils
from chromite.utils import file_util
from chromite.utils import pformat


IMAGE_NAME = "chromiumos_base_image"
TEMPFILE_PREFIX = "cros_analyze_image-"
DEFAULT_MIN_SIZE = 1024 * 1024 * 10

# This list is used by the --spreadsheet option.
# These are the list of paths we are watching on go/cros-image-size-spreadsheet.
WATCHED_PATHS = [
    "/",
    "/lib/firmware",
    "/lib/modules",
    "/opt/google/chrome/locales",
    "/opt/google/chrome/nacl_helper",
    "/opt/google/chrome/pepper/libpepflashplayer.so",
    "/opt/google/chrome/pnacl",
    "/opt/google/chrome/resources.pak",
    "/opt/google/chrome/resources/chromeos/accessibility/chromevox",
    "/opt/google/containers/android",
    "/opt/google/vms/android",
    "/usr/bin",
    "/usr/lib",
    "/usr/lib64",  # on 32-bit systems this check will come up as -1.
    "/usr/sbin",
    "/usr/share/chromeos-assets/demo_app",
    "/usr/share/chromeos-assets/genius_app",
    "/usr/share/chromeos-assets/input_methods/input_tools",
    "/usr/share/chromeos-assets/quickoffice",
    "/usr/share/chromeos-assets/speech_synthesis",
    "/usr/share/fonts",
]


def sub_paths_size_iter(
    root_path: str,
) -> typing.Generator[typing.Tuple[str, int], None, None]:
    """Calculates sizes for paths below root_path.

    Args:
        root_path: path to start analyzing from

    Returns:
        Generator tuple of path and int size of path.
    """
    root_path_len = len(root_path)

    cmd = ["du", "--all", "--one-file-system", "-B1", root_path]
    result = cros_build_lib.sudo_run(
        cmd, print_cmd=False, capture_output=True, encoding="utf-8"
    )
    for line in result.stdout.splitlines():
        if not line:
            continue

        size, path = line.split("\t")
        path = path[root_path_len:]
        if not path:
            path = "/"
        yield path, int(size)


def get_image_sizes(
    image_filepath: str, required_paths: list = None, min_size: int = None
) -> typing.Dict[str, int]:
    """Extracts an image to a temporary directory and calls sub_paths_size_iter.

    Args:
        image_filepath: The filepath of the image to analyze.
        required_paths: get sizes for only these paths
        min_size: if required_paths not set will filter to only return
            paths where size of path is at least min_size

    Returns:
        A dictionary of path -> size.
    """
    sizes = {}
    with osutils.TempDir(
        prefix=TEMPFILE_PREFIX
    ) as temp_dir, image_lib.LoopbackPartitions(
        image_filepath, temp_dir
    ) as image:
        root_path = image.Mount([constants.PART_ROOT_A])[0]
        for path, size in sub_paths_size_iter(root_path):
            if required_paths:
                if path not in required_paths:
                    continue
            elif size < min_size:
                continue

            sizes[path] = size

    return sizes


def fetch_image(board: str, version: str, local_path: str = None) -> str:
    """Downloads an image from Google Storage.

    Args:
        board: The name of the board.
        version: The version to download.
        local_path: directory to save image to.

    Returns:
        Local path to image file.
    """
    _, image_path = ds_wrapper.GetImagePathWithXbuddy(
        "xBuddy://remote", board, version
    )

    if local_path:
        try:
            shutil.copyfile(image_path, local_path)
        except OSError as e:
            cros_build_lib.Die(
                f"Copy error '{image_path}' to '{local_path}': {e}"
            )

        return local_path

    return image_path


def write_sizes(
    sizes: dict,
    required_paths: list,
    human_readable: bool,
    output_format: str,
    output_path: typing.Union[str, typing.TextIO],
):
    """Writes the sizes in CSV format.

    Args:
        sizes: A dictionary of path -> size.
        required_paths: list of paths to order results by
        human_readable: set to True to output in a human-readable format.
        output_format: output format (json or csv)
        output_path: path to write output to
    """

    def size_string(sz):
        if human_readable:
            return pformat.size(sz)
        return sz

    output = []

    # If required_paths passed in, emit output in same order as passed in.
    if required_paths:
        for path in required_paths:
            if path not in sizes:
                size = -1
            else:
                size = size_string(sizes[path])
            output.append({"path": path, "size": size})
    else:
        for path, size in sorted(sizes.items()):
            output.append({"path": path, "size": size_string(sizes[path])})

    with file_util.Open(output_path, mode="w") as f:
        if output_format == "csv":
            writer = csv.DictWriter(f, ["path", "size"])
            writer.writeheader()
            for row in output:
                writer.writerow(row)
        elif output_format == "json":
            pformat.json(output, f)


@command.command_decorator("analyze-image")
class AnalyzeImageCommand(command.CliCommand):
    """Analyze cros images listing large directory and file sizes."""

    @classmethod
    def ProcessOptions(cls, parser, options):
        """Post process options."""
        if options.image:
            return

        if not options.board or not options.version:
            parser.error("--image or (--board and --version) required")

    def Run(self):
        """Perform the command."""
        # Get the sudo password immediately.
        cros_build_lib.sudo_run(["echo"])

        image_filepath = None
        if self.options.image:
            logging.notice("Getting sizes for image: %s", self.options.image)
            image_filepath = self.options.image
        else:
            if self.options.local_path:
                image_filepath = self.options.local_path

            logging.notice("Getting sizes for: %s", self.options.version)
            image_filepath = fetch_image(
                board=self.options.board,
                version=self.options.version,
                local_path=image_filepath,
            )

        required_paths = []
        if self.options.spreadsheet:
            required_paths = WATCHED_PATHS

        logging.notice(
            "Analyzing disk usage of locally-mounted image: %s", image_filepath
        )
        sizes = get_image_sizes(
            image_filepath=image_filepath,
            required_paths=required_paths,
            min_size=self.options.minsize,
        )
        write_sizes(
            sizes=sizes,
            required_paths=required_paths,
            human_readable=self.options.human_readable,
            output_format=self.options.format,
            output_path=self.options.output,
        )

    @classmethod
    def AddParser(cls, parser: commandline.ArgumentParser):
        """Add parser arguments."""
        super(AnalyzeImageCommand, cls).AddParser(parser)

        parser.add_argument(
            "--board",
            default=None,
            help="Board name used for fetching an image.",
        )
        parser.add_argument(
            "--format",
            choices=("csv", "json"),
            default="csv",
            help='Choose output format (from "csv" or "json").'
            'Default: "%(default)s".',
        )
        parser.add_argument(
            "--human",
            dest="human_readable",
            default=False,
            action="store_true",
            help="Output human readable sizes.",
        )
        parser.add_argument(
            "--image",
            type="path",
            help="Specify a local image file to analyze.",
        )
        parser.add_argument(
            "--local-path", type="path", help="Local path to fetch image to."
        )
        parser.add_argument(
            "--minsize",
            default=DEFAULT_MIN_SIZE,
            type=int,
            help="Minimum file or directory size (in bytes) to list.",
        )
        parser.add_argument(
            "--output",
            default=sys.stdout,
            help="Write output to a specified path.",
        )
        parser.add_argument(
            "--spreadsheet",
            default=False,
            action="store_true",
            help="Use a preset list of paths that are specifically monitored "
            "in the size tracking spreadsheet "
            "(go/cros-image-size-spreadsheet).",
        )
        parser.add_argument(
            "--version",
            help="Version string used for fetching an image, e.g. R12-3456.7.0",
        )
