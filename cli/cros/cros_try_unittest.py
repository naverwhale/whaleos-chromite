# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests the `cros try` command."""

from pathlib import Path
from typing import List

from chromite.cli.cros import cros_try
from chromite.lib import cipd
from chromite.lib import constants
from chromite.lib import cros_test_lib
from chromite.scripts import cros


MOCK_TRY_DIR = Path("/tmp/try")
MOCK_TRY_BIN = MOCK_TRY_DIR / "try"


class StringStartsWith(str):
    """String-like object that matches a prefix."""

    def __eq__(self, other):
        return other.startswith(self)


class TryCommandTest(cros_test_lib.RunCommandTestCase):
    """Test the TryCommand class."""

    def setUp(self):
        """Create patches."""
        self._cipd_install_patch = self.PatchObject(
            cipd, "InstallPackage", return_value=MOCK_TRY_DIR
        )
        self._extra_env = {
            "PATH": StringStartsWith(str(constants.DEPOT_TOOLS_DIR) + ":"),
        }

    def runCrosTry(self, try_args: List[str]):
        """Simulate running the `cros try` command with the specified args."""
        return cros.main(["try"] + try_args)

    def testArgsForwarding(self):
        """Test that calling `cros try` forwards args to the try binary."""
        self.runCrosTry(["release", "-staging"])
        self.rc.assertCommandCalled(
            [str(MOCK_TRY_BIN), "release", "-staging"],
            check=False,
            stderr=True,
            encoding="utf-8",
            extra_env=self._extra_env,
        )

    def testExitCode(self):
        """Test that `cros try` returns the try binary's exit code."""
        self.rc.AddCmdResult([str(MOCK_TRY_BIN), "invalid-cmd"], returncode=128)
        actual_retcode = self.runCrosTry(["invalid-cmd"])
        self.assertEqual(actual_retcode, 128)

    def testDoubleDashes(self):
        """Unit tests for _ModifyFlagsToDoubleDashes."""
        # pylint: disable=protected-access
        for in_str, expected_out in (
            ("-flag", "--flag"),
            ("\n-flag", "\n--flag"),
            ("--flag", "--flag"),
            ("-contains-dash", "--contains-dash"),
            ("[-flag]", "[--flag]"),
            ("-g", "-g"),
        ):
            actual_out = cros_try._ModifyFlagsToDoubleDashes(in_str)
            self.assertEqual(actual_out, expected_out)

    def testTryVersion(self):
        """Test the default/overridden try version."""
        self.runCrosTry(["release"])
        self._cipd_install_patch.assert_called_with(
            cipd.GetCIPDFromCache(),
            cros_try.CIPD_TRY_PACKAGE,
            "prod",
        )
        self.runCrosTry(
            ["--try-version", "my-cool-version", "release", "--staging"]
        )
        self._cipd_install_patch.assert_called_with(
            cipd.GetCIPDFromCache(),
            cros_try.CIPD_TRY_PACKAGE,
            "my-cool-version",
        )
        self.rc.assertCommandCalled(
            [str(MOCK_TRY_BIN), "release", "--staging"],
            check=False,
            stderr=True,
            encoding="utf-8",
            extra_env=self._extra_env,
        )
