# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implement the `cros try` CLI, which forwards to the try binary.

The try binary is defined in the infra/infra repository, and distributed via
CIPD. This CLI ensures that the CIPD package is installed and up-to-date,
captures all input arguments, and forwards them to the try binary.
"""

import argparse
import os
from pathlib import Path
import re
import sys
from typing import List

from chromite.cli import command
from chromite.lib import cipd
from chromite.lib import constants
from chromite.lib import cros_build_lib


CIPD_TRY_PACKAGE = "chromiumos/infra/try/linux-amd64"


@command.command_decorator("try")
class TryCommand(command.CliCommand):
    """Implementation of the `cros try` command."""

    EPILOG = """
Run a builder with bespoke configurations via the try package.
For help, run `cros try help` (with no hyphens).
"""

    @classmethod
    def AddParser(cls, parser: argparse.ArgumentParser):
        """Capture all CLI args to forward to the go bin."""
        super().AddParser(parser)
        parser.add_argument(
            "--try-version",
            default="prod",
            help="CIPD version of the try CLI. Can be instance ID or ref. "
            "Must be provided before other try subcommands/flags.",
        )
        parser.add_argument("input", action="append", nargs=argparse.REMAINDER)

    def Run(self) -> int:
        """Install and run the try binary.

        Returns:
            The return code of the completed try process.
        """
        try_bin = _InstallTryPackage(self.options.try_version)
        return self._RunTry(try_bin, self.options.input[0])

    def _RunTry(self, try_bin: Path, args: List[str]) -> int:
        """Run the `try` command with the specified arguments.

        Args:
            try_bin: Path to the try binary.
            args: command-line args to pass into try.

        Returns:
            The return code of the completed try process.
        """
        cmd = [str(try_bin)] + args
        # TODO(b/266233948): Drop this hack if the underlying binary stops
        # relying on depot_tools being at the front of the PATH.
        path = os.pathsep.join(
            (str(constants.DEPOT_TOOLS_DIR), os.getenv("PATH"))
        )
        p = cros_build_lib.run(
            cmd,
            check=False,
            stderr=True,
            encoding="utf-8",
            extra_env={"PATH": path},
        )
        # Modify usage messages to refer to double-dash flags ('--foo').
        # The gobin's usage messages are sent to stderr and contain 'usage:'.
        if "usage:" in p.stderr:
            p.stderr = _ModifyFlagsToDoubleDashes(p.stderr)
        print(p.stderr, file=sys.stderr)
        return p.returncode


def _ModifyFlagsToDoubleDashes(message: str) -> str:
    """Take a message with single-dash flags, and make them double-dashes.

    Go bins like `try` accept both one-dash flags (-foo) and two-dash flags
    (--foo). But their help messages only report the one-dash version. For
    consistency with other `cros` tools, we want to print a help message with
    two dashes. Single-character flags (ex. '-g') should not be modified.

    This function edits the messages output by `try` into the desired format.
    """
    return re.sub(
        r"(^|[^A-Za-z0-9_\-])-(\w[A-Za-z0-9_\-]+)\b", r"\1--\2", message
    )


def _InstallTryPackage(version: str) -> Path:
    """Install the `try` package from CIPD, and save its path.

    If the package is already present in the CIPD cache, it will be updated
    to the specified version.

    Args:
        version: The CIPD version of the package to install. Can be either
            an instance ID or a ref.

    Returns:
        The path to the try binary.
    """
    try_dir = cipd.InstallPackage(
        cipd.GetCIPDFromCache(),
        CIPD_TRY_PACKAGE,
        version,
    )
    return Path(try_dir) / "try"
