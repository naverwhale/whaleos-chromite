# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the make.defaults parser."""

import pytest

from chromite.utils.parser import make_defaults


@pytest.mark.parametrize(
    ["contents", "expected"],
    [
        ["", {}],
        ["# a comment", {}],
        ["     \t\n", {}],
        ['USE=""\nUSE="$USE ohea"\n', {"USE": " ohea"}],
        ['ARCH="${notset}x86_64"', {"ARCH": "x86_64"}],
        ['USE="\n\tmultiline\n"', {"USE": "\n\tmultiline\n"}],
        ['VIDEO_CARDS="citrus \\\n radon"', {"VIDEO_CARDS": "citrus \n radon"}],
        ['VAR="\\${noexpand}"', {"VAR": "${noexpand}"}],
        ["VAR='${noexpand}'", {"VAR": "${noexpand}"}],
        [
            """
# Initial value just for style purposes.
USE=""

# Set some flag.
USE="${USE} some"

# Set another flag.
USE="${USE} another"
""",
            {"USE": " some another"},
        ],
    ],
)
def test_parse_make_defaults(contents, expected):
    """Test the `parse` function."""
    assert make_defaults.parse(contents) == expected
