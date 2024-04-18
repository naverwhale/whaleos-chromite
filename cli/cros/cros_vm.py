# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""VM management commands."""

import logging

from chromite.cli import command
from chromite.lib import vm

@command.command_decorator("vm")
class VmCommand(command.CliCommand):
    """cros vm command implementation."""

    EPILOG="""VM management commands."""

    use_dryrun_options = True

    @classmethod
    def AddParser(cls, parser):
        """Add parser arguments."""
        super().AddParser(parser)
        vm.VM.GetParser(parser)

    def Run(self):
        """Run the cros vm command."""
        try:
            vm.VM(self.options).Run()
            return 0
        except vm.VMError as e:
            logging.error("%s", e)
            if self.options.debug:
                raise

            logging.error("(Re-run with --debug for more details.)")
            return 1
