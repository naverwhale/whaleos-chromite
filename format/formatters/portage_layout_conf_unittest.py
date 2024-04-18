# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the portage_layout_conf module."""

import pytest

from chromite.format import formatters


# None means input is already formatted to avoid having to repeat.
@pytest.mark.parametrize(
    "data,exp",
    (
        # Unsorted keys.
        ("z = Z\na = A\n", "a = A\nz = Z\n"),
        # Intermixed comments.
        ("# line\nkey = value\n# foo\n", None),
        # Incorrect key spacing.
        ("# OK!\n k=v \n", "# OK!\nk = v\n"),
        # Blank lines.
        ("# Ok\n\n\n", "# Ok\n"),
        ("k = v\n\nz = a\n", "k = v\nz = a\n"),
        # Sorted keys.
        ("eapis-banned = 4 1 2\n", "eapis-banned = 1 2 4\n"),
        # Empty value.
        ("foo = \n", "foo =\n"),
    ),
)
def test_check_format(data, exp):
    """Verify inputs match expected outputs."""
    if exp is None:
        exp = data
    assert exp == formatters.portage_layout_conf.Data(data)
