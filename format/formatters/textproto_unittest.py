# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the textproto module."""

import pytest

from chromite.format import formatters


# None means input is already formatted to avoid having to repeat.
@pytest.mark.parametrize(
    "data,exp",
    (
        ("", None),
        ("\n FOO {}\n\n\n", "FOO {}\n"),
        ("FOO { BAR { blah: 1 }\n}", "FOO {\n  BAR { blah: 1 }\n}\n"),
    ),
)
def test_check_format(data, exp):
    """Verify inputs match expected outputs."""
    if exp is None:
        exp = data
    assert exp == formatters.textproto.Data(data)
