# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Internal helper for attaching & detaching disk images.

We have a long history of the kernel flaking when working with loopback devices,
so this helper takes care of setting up & tearing it down reliably.
"""

import logging
from pathlib import Path
import sys
from typing import List, Optional

from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import image_lib
from chromite.lib import osutils
from chromite.utils import pformat


_UDEV_RULE_TEMPLATE = """# Don't edit this file.
# This file will be updated by chromite.
# This rule looks for images mounted from cros checkout and ignores
# udev processing (b/273697462 for more context).
SUBSYSTEM!="block", GOTO="block_udev_end"
KERNELS!="loop[0-9]*", GOTO="block_udev_end"
ENV{DEVTYPE}=="disk", TEST!="loop/backing_file", GOTO="block_udev_end"
ENV{DEVTYPE}=="partition", ENV{ID_PART_ENTRY_SCHEME}!="gpt", \
    GOTO="block_udev_end"

ATTRS{loop/backing_file}=="%s/*", ENV{CROS_IGNORE_LOOP_DEV}="1"

ENV{CROS_IGNORE_LOOP_DEV}=="1", ENV{SYSTEMD_READY}="0", \
    ENV{UDEV_DISABLE_PERSISTENT_STORAGE_RULES_FLAG}="1", \
    ENV{UDISKS_IGNORE}="1", ENV{DM_UDEV_DISABLE_OTHER_RULES_FLAG}="1"

LABEL="block_udev_end"
"""
_UDEV_RULE_FILE = Path("/etc/udev/rules.d/99-chromite-loop-dev.rules")


def _create_udev_loopdev_ignore_rule():
    """Create udev rules to ignore processing cros image loop device events."""
    if cros_build_lib.IsInsideChroot():
        return

    new_rule = _UDEV_RULE_TEMPLATE % constants.SOURCE_ROOT
    try:
        existing_rule = _UDEV_RULE_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing_rule = None
    if existing_rule == new_rule:
        return

    logging.debug(
        "Creating udev rule to ignore loop device in %s.", _UDEV_RULE_FILE
    )
    _UDEV_RULE_FILE.write_text(new_rule, encoding="utf-8")
    cros_build_lib.run(["udevadm", "control", "--reload-rules"], check=False)


def get_parser() -> commandline.ArgumentParser:
    """Return a command line parser."""
    parser = commandline.ArgumentParser(description=__doc__)

    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.required = True

    subparser = subparsers.add_parser(
        "attach", help="Attach a disk image to a loopback device."
    )
    subparser.add_argument(
        "path",
        type=Path,
        help="Disk image to attach.",
    )

    subparser = subparsers.add_parser(
        "detach", help="Detach a loopback device."
    )
    subparser.add_argument(
        "path",
        type=Path,
        help="Loopback device to free.",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> Optional[int]:
    parser = get_parser()
    opts = parser.parse_args(argv)

    if not osutils.IsRootUser():
        result = cros_build_lib.sudo_run(
            [constants.CHROMITE_SCRIPTS_DIR / "cros_losetup"] + argv,
            check=False,
        )
        return result.returncode

    _create_udev_loopdev_ignore_rule()

    if opts.subcommand == "attach":
        loop_path = image_lib.LoopbackPartitions.attach_image(opts.path)
        print(
            pformat.json(
                {
                    "path": loop_path,
                },
                compact=not sys.stdin.isatty(),
            ),
            end="",
        )
    elif opts.subcommand == "detach":
        if not image_lib.LoopbackPartitions.detach_loopback(opts.path):
            return 1
    else:
        raise RuntimeError(f"Unknown command: {opts.subcommand}")

    return 0
