# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module tests the cros fix command."""

from chromite.cli.cros import cros_fix
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.scripts import cros


# pylint: disable=protected-access


class FixCommandTestCase(cros_test_lib.TestCase):
    """Utils for testing the fix subcommand."""

    def setUp(self):
        # Set up default options for tests to play with for running cros fix.
        self._parser = cros.GetOptions("fix")
        self.options = self.parse_args([])

    def parse_args(self, args, **kwargs):
        return self._parser.parse_args(["fix"] + args, **kwargs)


class FixCommandTempDirTests(FixCommandTestCase, cros_test_lib.TempDirTestCase):
    """Tests that use real files."""

    def testCliOneFile(self):
        """Check behavior with one file."""
        file = self.tempdir / "foo.txt"
        osutils.Touch(file)
        opts = self.parse_args([str(file)])
        cmd = cros_fix.FixCommand(opts)
        self.assertEqual(0, cmd.Run())
