# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Attempt automated fixes on the specified files."""

from chromite.cli import analyzers
from chromite.cli import command
from chromite.cli.cros import cros_format


@command.command_decorator("fix")
class FixCommand(analyzers.AnalyzerCommand):
    """Automatically fix format/lint/etc... issues."""

    # AnalyzerCommand overrides.
    can_modify_files = True
    use_dryrun_options = True

    def Run(self):
        files = self.options.files
        if not files:
            return 0

        # TODO(build): Integrate linters that have a --fix option.
        cmd = cros_format.FormatCommand(self.options)
        return cmd.Run()
