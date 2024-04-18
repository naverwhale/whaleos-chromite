# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for portage_profile_conf.py."""

import pytest

from chromite.utils.parser import portage_profile_conf


@pytest.mark.parametrize(
    ["contents", "expected"],
    [
        ["", []],
        ["  # comment only\n", []],
        ["\n\n\n", []],
        [
            """\
# Mask docs for GTK 2.x
=x11-libs/gtk+-2* doc
# Unmask mysql support for QT
x11-libs/qt -mysql
""",
            [["=x11-libs/gtk+-2*", "doc"], ["x11-libs/qt", "-mysql"]],
        ],
    ],
)
def test_parse(contents, expected):
    """Test the parse() function."""
    assert list(portage_profile_conf.parse(contents)) == expected
