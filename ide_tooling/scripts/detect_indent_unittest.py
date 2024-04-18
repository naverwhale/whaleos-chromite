# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for detect_indent.py.
"""

import os
import sys

import detect_indent


sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."),
)
# pylint: disable=wrong-import-position
from chromite.lib import cros_test_lib


# pylint: enable=wrong-import-position

TEXT_EMPTY = ""

TEXT_NO_INDENT = """
Organize the world's information and
make it universally accessible
and useful.
"""

TEXT_LONG_INDENT = """
Some
                   text.
"""

TEXT_2_INDENT = """
[
  {
    "command": "x86_64-cros-linux-gnu-clang++",
    "directory": "/build/"
  },
  {
    "command": "x86_64-cros-linux-gnu-clang++",
    "directory": "/build/",
  }
]
"""

TEXT_4_INDENT = """
#include <stdio.h>
int main() {
    printf("Hello, World!");
}
"""

TEXT_WITH_EMPTY_LINES = """
if a:
  if b:
    foo()

    foo()

    foo()

    foo()
"""


class GenerateTest(cros_test_lib.TestCase):
    """Tests detect_indentation()"""

    def testAll(self):
        cases = {
            TEXT_EMPTY: None,
            TEXT_NO_INDENT: None,
            TEXT_LONG_INDENT: 19,
            TEXT_2_INDENT: 2,
            TEXT_4_INDENT: 4,
            TEXT_WITH_EMPTY_LINES: 2,
        }
        for text, expected in cases.items():
            detected = detect_indent.detect_indentation(text)
            self.assertEqual(detected, expected)
