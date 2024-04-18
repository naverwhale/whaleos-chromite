# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the upstart module."""

from chromite.lib import cros_test_lib
from chromite.lint.linters import upstart


class CheckForRequiredLinesTest(cros_test_lib.TestCase):
    """Test the functionality of the required lines check."""

    def _getTestRequiredLines(self):
        """Create a test set for use with CheckForRequiredLines."""
        return {"one", "two", "three"}

    def testOneNotPresent(self):
        """Check the case some are present and some are not."""
        self.assertEqual(
            upstart.CheckForRequiredLines(
                """one
two""",
                "test-string",
                self._getTestRequiredLines(),
            ),
            False,
        )

    def testNonePresent(self):
        """Check the case none are present."""
        self.assertEqual(
            upstart.CheckForRequiredLines(
                """four
five
six""",
                "test-string",
                self._getTestRequiredLines(),
            ),
            False,
        )

    def testAllPresent(self):
        """Check the case all are present."""
        self.assertEqual(
            upstart.CheckForRequiredLines(
                """three
two
one""",
                "test-string",
                self._getTestRequiredLines(),
            ),
            True,
        )

    def testPrefix(self):
        """Check the case one is a prefix match but not a true match."""
        self.assertEqual(
            upstart.CheckForRequiredLines(
                """three
two-with-extra
one""",
                "test-string",
                self._getTestRequiredLines(),
            ),
            False,
        )


class ExtractCommandsTest(cros_test_lib.TestCase):
    """Test the functionality of the command extractor."""

    def testEmpty(self):
        """Make sure an empty string doesn't break anything."""
        self.assertEqual(list(upstart.ExtractCommands("")), [])

    def testMultipleSingleLineCommands(self):
        """Check that single-line commands are handled as expected."""
        self.assertEqual(
            list(
                upstart.ExtractCommands(
                    """
pre-start script
  mkdir -p /run/upstart-test; `chmod 0750 /run/upstart-test`
  echo test && $(chown test:test /run/upstart-test)
end script
"""
                )
            ),
            [
                ["mkdir", "-p", "/run/upstart-test"],
                ["`chmod", "0750", "/run/upstart-test`"],
                ["$(chown", "test:test", "/run/upstart-test)"],
            ],
        )

    def testMultilineCommands(self):
        """Check that multi-line commands are handled as expected."""
        self.assertEqual(
            list(
                upstart.ExtractCommands(
                    """
pre-start script
  mkdir \
    -p \
    /run/upstart-test
  `chmod \
    0750 \
    /run/upstart-test`
  $(chown \
    test:test \
    /run/upstart-test) && touch /run/upstart-test/done
end script
"""
                )
            ),
            [
                ["mkdir", "-p", "/run/upstart-test"],
                ["`chmod", "0750", "/run/upstart-test`"],
                [
                    "$(chown",
                    "test:test",
                    "/run/upstart-test)",
                    "&&",
                    "touch",
                    "/run/upstart-test/done",
                ],
            ],
        )

    def testDisable(self):
        """Check that commands with '# croslint: disable' are ignored"""
        self.assertEqual(
            list(
                upstart.ExtractCommands(
                    """
pre-start script
  mkdir \
    -p \
    /run/upstart-test
  chmod \
    0750 \
    /run/upstart-test  # croslint: disable because...
  chown \
    test:test \
    /run/upstart-test
end script
"""
                )
            ),
            [
                ["mkdir", "-p", "/run/upstart-test"],
                ["chown", "test:test", "/run/upstart-test"],
            ],
        )
