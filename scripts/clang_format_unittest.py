# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests the clang-format wrapper."""

from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.scripts import clang_format


class ClangFormatTest(cros_test_lib.TestCase):
    """Tests the clang-format wrapper."""

    def testClangFormatVersion(self):
        """Check that clang-format can return the version."""
        with clang_format.ClangFormat() as prog:
            result = cros_build_lib.run(
                [prog, "--version"],
                encoding="utf-8",
                capture_output=True,
            )
        self.assertStartsWith(result.stdout, "clang-format version ")

    def testClangFormatStdin(self):
        """Check clang-format can format from stdin."""
        with clang_format.ClangFormat() as prog:
            result = cros_build_lib.run(
                [prog, "--style={BasedOnStyle: Chromium}"],
                input="int main(){   }",
                encoding="utf-8",
                capture_output=True,
            )
        self.assertEqual(result.stdout, "int main() {}")
