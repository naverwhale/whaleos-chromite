# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for the shebang.py module."""

from chromite.lib import cros_test_lib
from chromite.utils.parser import shebang


class SplitShebangTest(cros_test_lib.TestCase):
    """Test the SplitShebang function."""

    def testSimple(self):
        """Test a simple case."""
        self.assertEqual(("/bin/sh", ""), shebang.parse("#!/bin/sh"))

    def testWithArguments(self):
        """Test a case with arguments."""
        self.assertEqual(
            ("/bin/sh", '-i -c "ls"'),
            shebang.parse('#!/bin/sh  -i -c "ls"'),
        )

    def testWithEndline(self):
        """Test a case finished with a newline char."""
        self.assertEqual(("/bin/sh", "-i"), shebang.parse("#!/bin/sh  -i\n"))

    def testMultiLine(self):
        """Verify multiline inputs where we only parse the first."""
        self.assertEqual(
            ("/bin/sh", "-i"), shebang.parse("#!/bin/sh  -i\n# My program\n")
        )

    def testWithSpaces(self):
        """Test a case with several spaces in the line."""
        self.assertEqual(
            ("/bin/sh", "-i"), shebang.parse("#!  /bin/sh  -i   \n")
        )

    def testWithArgSpaces(self):
        """Test arguments with spaces in them."""
        self.assertEqual(
            ("/bin/sh", "-e -x"), shebang.parse("#!/bin/sh -e -x\n")
        )

    def testValidBytes(self):
        """Test bytes inputs."""
        self.assertEqual(("/foo", "-v"), shebang.parse(b"#!/foo -v"))

    def testInvalidBytes(self):
        """Test bytes input but not valid UTF-8."""
        self.assertRaises(ValueError, shebang.parse, b"#!/fo\xff")

    def testInvalidCases(self):
        """Thes invalid cases."""
        self.assertRaises(ValueError, shebang.parse, "/bin/sh -i")
        self.assertRaises(ValueError, shebang.parse, "#!")
        self.assertRaises(ValueError, shebang.parse, "#!env python")

    def testRealCommand(self):
        """Test real_command helper."""
        # If /usr/bin/env has an arg, that's the real command.
        result = shebang.parse("#!/usr/bin/env ls")
        assert result.command == "/usr/bin/env"
        assert result.real_command == "ls"

        # If /usr/bin/env doesn't have an arg, then env is the real command.
        result = shebang.parse("#!/usr/bin/env")
        assert result.command == "/usr/bin/env"
        assert result.real_command == "/usr/bin/env"

        # Don't skip non-wrapper tools.
        result = shebang.parse("#!/bin/foo -x")
        assert result.command == "/bin/foo"
        assert result.real_command == "/bin/foo"
