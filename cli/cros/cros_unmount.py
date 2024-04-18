# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Recursively unmount directory trees.

This is a convenience command for developers to quickly tear down & clean up
whatever random paths they have.
"""

import logging
from pathlib import Path

from chromite.cli import command
from chromite.lib import osutils


class UnmountCommandBase(command.CliCommand):
    """Recursively unmount directory trees.

    Base class for unmount & umount alias commands.
    """

    @classmethod
    def AddParser(cls, parser):
        """Add parser arguments."""
        super().AddParser(parser)

        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Trim empty mount dirs",
        )
        parser.add_argument(
            "--lazy", action="store_true", help="Perform a lazy unmount"
        )

        # NB: We don't use type='path' in order to handle symlinks directly.
        parser.add_argument(
            "paths", nargs="+", help="Base directory to cleanup"
        )

    @classmethod
    def ProcessOptions(cls, parser, options):
        """Post process options."""
        options.paths = [Path(x).expanduser() for x in options.paths]

    def Run(self):
        """Perform the cros mount command."""
        for path in self.options.paths:
            if not path.exists():
                # Funky edge case: ignore broken symlinks.  We use these when
                # mounting to provide dir_<partition number> and dir_<label>.
                if path.is_symlink():
                    if self.options.cleanup:
                        path.unlink()
                        continue
                logging.warning("%s: directory does not exist", path)
                continue

            logging.info("Unmounting %s recursively", path)
            osutils.UmountTree(
                path, lazy=self.options.lazy, cleanup=self.options.cleanup
            )


@command.command_decorator("unmount")
class UnmountCommand(UnmountCommandBase):
    """Recursively unmount directory trees."""
