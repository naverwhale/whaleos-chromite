# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the json module."""

import pytest

from chromite.format.formatters import json


# None means input is already formatted to avoid having to repeat.
@pytest.mark.parametrize(
    "data,exp",
    (
        ("{}", None),
        ("[]", None),
        ("{}\n", "{}"),
        (" {}\n", "{}"),
        ("\n{}\n", "{}"),
        ("[1,2, 3,4]", "[1,2,3,4]"),
        ("[1,\n2,4]", "[\n  1,\n  2,\n  4\n]\n"),
    ),
)
def test_check_format(data, exp):
    """Verify inputs match expected outputs."""
    if exp is None:
        exp = data
    assert exp == json.Data(data)
