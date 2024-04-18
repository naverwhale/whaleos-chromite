# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Parse and operate based on disk layout files.

For information on the JSON format, see:
  http://dev.chromium.org/chromium-os/developer-guide/disk-layout-format

The --adjust_part flag takes arguments like:
  <label>:<op><size>
Where:
  <label> is a label name as found in the disk layout file
  <op> is one of the three: + - =
  <size> is a number followed by an optional size qualifier:
         B, KiB, MiB, GiB, TiB: bytes, kibi-, mebi-, gibi-, tebi- (base 1024)
         B,   K,   M,   G,   T: short hand for above
         B,  KB,  MB,  GB,  TB: bytes, kilo-, mega-, giga-, tera- (base 1000)

This will set the ROOT-A partition size to 1 gibibytes (1024 * 1024 * 1024 * 1):
  --adjust_part ROOT-A:=1GiB
This will grow the ROOT-A partition size by 500 mebibytes (1024 * 1024 * 500):
  --adjust_part ROOT-A:+500MiB
This will shrink the ROOT-A partition size by 10 mebibytes (1024 * 1024 * 10):
  --adjust_part ROOT-A:-20MiB
"""

import argparse
import inspect
import os
import sys
from typing import List, Union

from chromite.lib import disk_layout


def WritePartitionScript(
    options: List[str],
    image_type: str,
    layout_filename: Union[str, os.PathLike],
    sfilename: Union[str, os.PathLike],
    vfilename: Union[str, os.PathLike],
):
    """Writes a shell script with functions for the base and requested layouts.

    Args:
        options: Flags passed to the script
        image_type: Type of image eg base/test/dev/factory_install
        layout_filename: Path to partition configuration file
        sfilename: Filename to write the finished script to
        vfilename: Filename to write the partition variables json data to
    """

    return disk_layout.DiskLayout(
        layout_filename, options.adjust_part.split()
    ).WritePartitionScript(image_type, sfilename, vfilename)


def GetBlockSize(
    _options: List[str], layout_filename: Union[str, os.PathLike]
) -> str:
    """Returns the partition table block size.

    Args:
        options: Flags passed to the script.
        layout_filename: Path to partition configuration file.

    Returns:
        Block size of all partitions in the layout.
    """

    return disk_layout.DiskLayout(layout_filename).GetBlockSize()


def GetFilesystemBlockSize(
    _options: List[str], layout_filename: Union[str, os.PathLike]
) -> str:
    """Returns the filesystem block size.

    This is used for all partitions in the table that have filesystems.

    Args:
        options: Flags passed to the script.
        layout_filename: Path to partition configuration file.

    Returns:
        Block size of all filesystems in the layout.
    """

    return disk_layout.DiskLayout(layout_filename).GetFilesystemBlockSize()


def GetPartitionSize(
    options: List[str],
    image_type: str,
    layout_filename: Union[str, os.PathLike],
    num: str,
) -> str:
    """Returns the partition size of a given partition for a given layout type.

    Args:
        options: Flags passed to the script.
        image_type: Type of image eg base/test/dev/factory_install.
        layout_filename: Path to partition configuration file.
        num: Number of the partition you want to read from.

    Returns:
        Size of selected partition in bytes.
    """

    return disk_layout.DiskLayout(
        layout_filename, options.adjust_part.split()
    ).GetPartitionSize(image_type, int(num))


def GetFormat(
    options: List[str],
    image_type: str,
    layout_filename: Union[str, os.PathLike],
    num: str,
) -> str:
    """Returns the format of a given partition for a given layout type.

    Args:
        options: Flags passed to the script.
        image_type: Type of image eg base/test/dev/factory_install.
        layout_filename: Path to partition configuration file.
        num: Number of the partition you want to read from.

    Returns:
        Format of the selected partition's filesystem.
    """

    return disk_layout.DiskLayout(
        layout_filename, options.adjust_part.split()
    ).GetFormat(image_type, int(num))


def GetFilesystemFormat(
    options: List[str],
    image_type: str,
    layout_filename: Union[str, os.PathLike],
    num: str,
) -> str:
    """Returns the filesystem format of a partition for a given layout type.

    Args:
        options: Flags passed to the script
        image_type: Type of image eg base/test/dev/factory_install
        layout_filename: Path to partition configuration file
        num: Number of the partition you want to read from

    Returns:
        Format of the selected partition's filesystem
    """

    return disk_layout.DiskLayout(
        layout_filename, options.adjust_part.split()
    ).GetFilesystemFormat(image_type, int(num))


def GetFilesystemSize(
    options: List[str],
    image_type: str,
    layout_filename: Union[str, os.PathLike],
    num: str,
) -> int:
    """Returns the filesystem size of a given partition for a given layout type.

    If no filesystem size is specified, returns the partition size.

    Args:
        options: Flags passed to the script.
        image_type: Type of image eg base/test/dev/factory_install.
        layout_filename: Path to partition configuration file.
        num: Number of the partition you want to read from.

    Returns:
        Size of selected partition filesystem in bytes.
    """

    return disk_layout.DiskLayout(
        layout_filename, options.adjust_part.split()
    ).GetFilesystemSize(image_type, int(num))


def GetImageTypes(
    _options: List[str], layout_filename: Union[str, os.PathLike]
) -> str:
    """Returns a list of all the image types in the layout.

    Args:
        options: Flags passed to the script.
        layout_filename: Path to partition configuration file.

    Returns:
        List of all image types.
    """

    image_types = disk_layout.DiskLayout(layout_filename).GetImageTypes()
    return " ".join(image_types)


def GetFilesystemOptions(
    options: List[str],
    image_type: str,
    layout_filename: Union[str, os.PathLike],
    num: str,
) -> str:
    """Returns the filesystem options of a given partition and layout type.

    Args:
        options: Flags passed to the script.
        image_type: Type of image eg base/test/dev/factory_install.
        layout_filename: Path to partition configuration file.
        num: Number of the partition you want to read from.

    Returns:
        The selected partition's filesystem options.
    """

    return disk_layout.DiskLayout(
        layout_filename, options.adjust_part.split()
    ).GetFilesystemOptions(image_type, int(num))


def GetLabel(
    options: List[str],
    image_type: str,
    layout_filename: Union[str, os.PathLike],
    num: str,
) -> str:
    """Returns the label for a given partition.

    Args:
        options: Flags passed to the script.
        image_type: Type of image eg base/test/dev/factory_install.
        layout_filename: Path to partition configuration file.
        num: Number of the partition you want to read from.

    Returns:
        Label of selected partition, or 'UNTITLED' if none specified.
    """

    return disk_layout.DiskLayout(
        layout_filename, options.adjust_part.split()
    ).GetLabel(image_type, int(num))


def GetNumber(
    options: List[str],
    image_type: str,
    layout_filename: Union[str, os.PathLike],
    label,
) -> int:
    """Returns the partition number of a given label.

    Args:
        options: Flags passed to the script.
        image_type: Type of image eg base/test/dev/factory_install.
        layout_filename: Path to partition configuration file.
        label: Number of the partition you want to read from.

    Returns:
        The number of the partition corresponding to the label.
    """

    return disk_layout.DiskLayout(
        layout_filename, options.adjust_part.split()
    ).GetNumber(image_type, label)


def GetReservedEraseBlocks(
    options: List[str],
    image_type: str,
    layout_filename: Union[str, os.PathLike],
    num: str,
) -> int:
    """Returns the number of erase blocks reserved in the partition.

    Args:
        options: Flags passed to the script.
        image_type: Type of image eg base/test/dev/factory_install.
        layout_filename: Path to partition configuration file.
        num: Number of the partition you want to read from.

    Returns:
        Number of reserved erase blocks.
    """

    return disk_layout.DiskLayout(
        layout_filename, options.adjust_part.split()
    ).GetReservedEraseBlocks(image_type, int(num))


def GetType(
    options: List[str],
    image_type: str,
    layout_filename: Union[str, os.PathLike],
    num: str,
) -> str:
    """Returns the type of a given partition for a given layout.

    Args:
        options: Flags passed to the script.
        image_type: Type of image eg base/test/dev/factory_install.
        layout_filename: Path to partition configuration file.
        num: Number of the partition you want to read from.

    Returns:
        Type of the specified partition.
    """

    return disk_layout.DiskLayout(
        layout_filename, options.adjust_part.split()
    ).GetType(image_type, int(num))


def GetPartitions(
    options: List[str],
    image_type: str,
    layout_filename: Union[str, os.PathLike],
) -> str:
    """Returns the partition numbers for the image_type.

    Args:
        options: Flags passed to the script.
        image_type: Type of image eg base/test/dev/factory_install.
        layout_filename: Path to partition configuration file.

    Returns:
        A space delimited string of partition numbers.
    """

    return disk_layout.DiskLayout(
        layout_filename, options.adjust_part.split()
    ).GetPartitions(image_type)


def GetUUID(
    options: List[str],
    image_type: str,
    layout_filename: Union[str, os.PathLike],
    num: str,
) -> str:
    """Returns the filesystem UUID of a given partition for a given layout type.

    Args:
        options: Flags passed to the script.
        image_type: Type of image eg base/test/dev/factory_install.
        layout_filename: Path to partition configuration file.
        num: Number of the partition you want to read from.

    Returns:
        UUID of specified partition. Defaults to random if not set.
    """

    return disk_layout.DiskLayout(
        layout_filename, options.adjust_part.split()
    ).GetUUID(image_type, int(num))


def DoDebugOutput(
    options: List[str],
    layout_filename: Union[str, os.PathLike],
    image_type: str,
):
    """Prints out a human readable disk layout in on-disk order.

    Args:
        options: Flags passed to the script.
        layout_filename: Path to partition configuration file.
        image_type: Type of image e.g. ALL/LIST/base/test/dev/factory_install.
    """

    return disk_layout.DiskLayout(
        layout_filename, options.adjust_part.split()
    ).DoDebugOutput(image_type)


def Validate(
    options: List[str],
    image_type: str,
    layout_filename: Union[str, os.PathLike],
):
    """Validates a layout file, used before reading sizes to check for errors.

    Args:
        options: Flags passed to the script.
        image_type: Type of image eg base/test/dev/factory_install.
        layout_filename: Path to partition configuration file.
    """

    return disk_layout.DiskLayout(
        layout_filename, options.adjust_part.split()
    ).Validate(image_type)


class ArgsAction(argparse.Action):  # pylint: disable=no-init
    """Helper to add all arguments to an args array.

    ArgumentParser does not let you specify the same dest for multiple args.
    We take care of appending to the 'args' array ourselves here.
    """

    def __call__(self, parser, namespace, values, option_string=None):
        args = getattr(namespace, "args", [])
        args.append(values)
        setattr(namespace, "args", args)


class HelpAllAction(argparse.Action):
    """Display all subcommands help in one go."""

    def __init__(self, *args, **kwargs):
        if "nargs" in kwargs:
            raise ValueError("nargs not allowed")
        kwargs["nargs"] = 0
        argparse.Action.__init__(self, *args, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        print("%s\nCommands:" % (parser.description,), end="")
        subparser = getattr(namespace, "help_all")
        for key, subparser in namespace.help_all.choices.items():
            # Should we include the desc of each arg too ?
            print(
                "\n  %s %s\n    %s"
                % (
                    key,
                    subparser.get_default("help_all"),
                    subparser.description,
                )
            )
        sys.exit(0)


def GetParser():
    """Return a parser for the CLI.

    We use the function docstring to build the cli argument, help text
    and their arguments.
    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--adjust_part",
        metavar="SPEC",
        default="",
        help="adjust partition sizes",
    )

    action_map = {
        "write": WritePartitionScript,
        "readblocksize": GetBlockSize,
        "readfsblocksize": GetFilesystemBlockSize,
        "readpartsize": GetPartitionSize,
        "readformat": GetFormat,
        "readfsformat": GetFilesystemFormat,
        "readfssize": GetFilesystemSize,
        "readimagetypes": GetImageTypes,
        "readfsoptions": GetFilesystemOptions,
        "readlabel": GetLabel,
        "readnumber": GetNumber,
        "readreservederaseblocks": GetReservedEraseBlocks,
        "readtype": GetType,
        "readpartitionnums": GetPartitions,
        "readuuid": GetUUID,
        "debug": DoDebugOutput,
        "validate": Validate,
    }

    # Subparsers are required by default under Python 2.  Python 3 changed to
    # not required, but didn't include a required option until 3.7.  Setting
    # the required member works in all versions (and setting dest name).
    subparsers = parser.add_subparsers(title="Commands", dest="command")
    subparsers.required = True

    for name, func in sorted(action_map.items()):
        # Turn the func's docstring into something we can show the user.
        desc, doc = func.__doc__.split("\n", 1)
        # Extract the help for each argument.
        args_help = {}
        for line in doc.splitlines():
            if ":" in line:
                arg, text = line.split(":", 1)
                args_help[arg.strip()] = text.strip()

        argspec = inspect.getfullargspec(func)
        # Skip the first argument as that'll be the options field.
        args = argspec.args[1:]

        subparser = subparsers.add_parser(name, description=desc, help=desc)
        subparser.set_defaults(
            callback=func, help_all=" ".join("<%s>" % x for x in args)
        )
        for arg in args:
            subparser.add_argument(arg, action=ArgsAction, help=args_help[arg])

    parser.add_argument(
        "--help-all",
        action=HelpAllAction,
        default=subparsers,
        help="show all commands and their help in one screen",
    )

    return parser


def main(argv):
    parser = GetParser()
    opts = parser.parse_args(argv)

    ret = opts.callback(opts, *opts.args)
    if ret is not None:
        print(ret)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
