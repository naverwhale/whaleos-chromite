# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the whitespace module."""

import pytest

from chromite.format.formatters import whitespace


# None means input is already formatted to avoid having to repeat.
@pytest.mark.parametrize(
    "data,exp",
    (
        ("", None),
        ("ok\n", None),
        ("ok\nline\n", None),
        (" ", ""),
        ("\n", ""),
        ("\t", ""),
        ("\n\n", ""),
        ("\nno leading line\n", "no leading line\n"),
        ("missing trailing newling", "missing trailing newling\n"),
        ("blah ", "blah\n"),
        ("blah\n\n", "blah\n"),
        (" no leading space\n", "no leading space\n"),
    ),
)
def test_check_format(data, exp):
    """Verify inputs match expected outputs."""
    if exp is None:
        exp = data
    assert exp == whitespace.Data(data)
