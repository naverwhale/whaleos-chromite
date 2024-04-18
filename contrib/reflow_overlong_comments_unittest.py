# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the reflow_overlong_comments script."""

import io

import pytest

from chromite.contrib.reflow_overlong_comments import reflow_comments


FOURTY_CHARS = "This text is exactly 40 characters long"


EXPECTATIONS = [
    # Test candidate comment detection and basic output.
    (
        f"""\
#!/bin/python
# Copyright
# Authors

# Not wrapped.
# {FOURTY_CHARS} {FOURTY_CHARS}
# Wrapped.
#
# Not wrapped.

# {FOURTY_CHARS} {FOURTY_CHARS}
# Word.
""",
        """\
#!/bin/python
# Copyright
# Authors

# Not wrapped.
# This text is exactly 40 characters long This text is exactly 40 characters
# long Wrapped.
#
# Not wrapped.

# This text is exactly 40 characters long This text is exactly 40 characters
# long Word.
""",
    ),
    # Test that pylint directives interrupt coalescing.
    (
        f"""\
# {FOURTY_CHARS} {FOURTY_CHARS}
# pylint: disable-next=line-too-long
""",
        """\
# This text is exactly 40 characters long This text is exactly 40 characters
# long
# pylint: disable-next=line-too-long
""",
    ),
    # Test that indentation change interrupts coalescing.
    (
        f"""\
# {FOURTY_CHARS} {FOURTY_CHARS}
  # Why is this indented?
""",
        """\
# This text is exactly 40 characters long This text is exactly 40 characters
# long
  # Why is this indented?
""",
    ),
    # Test we don't break up long URIs.  Leave it to the author to figure out.
    (
        """\
# https://chromium.googlesource.com/infra/infra/+/HEAD/recipes/recipe_modules/recipe_autoroller/api.py
""",
        """\
# https://chromium.googlesource.com/infra/infra/+/HEAD/recipes/recipe_modules/recipe_autoroller/api.py
""",
    ),
]


@pytest.mark.parametrize("input_string,expected", EXPECTATIONS)
def test_reflow_comments(input_string: str, expected: str) -> None:
    input_file = io.StringIO(input_string)
    output = io.StringIO()
    reflow_comments(input_file, output)
    assert output.getvalue() == expected
