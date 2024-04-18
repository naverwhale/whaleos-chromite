# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the owners module."""

import pytest

from chromite.lint.linters import owners


def test_missing_file():
    """Given a missing file should be OK."""
    assert owners.lint_path("/.....ajlsdkfjalskdfjalskdfasdf")


GOOD_DATA = (
    "v@e.x\n",
    # Shared owners includes.
    "include chromiumos/owners:v1:/OWNERS.foo\n"
    "include chromeos/owners:v1:/OWNERS.foo\n",
)


@pytest.mark.parametrize("data", GOOD_DATA)
def test_good_owners(data):
    """Test good owners files."""
    assert owners.lint_data("pylint", data)


BAD_DATA = (
    "",
    # Leading blank line.
    "\nv@e.x\n",
    # Trailing blank line.
    "\nv@e.x\n\n",
    # Missing final blank line.
    "\nv@e.x",
    # Tabs!
    "\tv@e.x\n",
    # Leading whitespace.
    "  v@e.x\n",
    # Shared owners missing branch.
    "include chromiumos/owners:/OWNERS.foo\n"
    "include chromeos/owners:/OWNERS.foo\n"
    # Shared owners bad branch.
    "include chromiumos/owners:foo:/OWNERS.foo\n"
    "include chromeos/owners:foo:/OWNERS.foo\n"
    # Shared owners bad includes.
    "include chromiumos/owners:v1:OWNERS.foo\n"
    "include chromeos/owners:v1:OWNERS.foo\n"
    "include chromiumos/owners:v1:/OWNERS\n"
    "include chromeos/owners:v1:/OWNERS\n"
    "include chromiumos/owners:v1:/foo/OWNERS\n"
    "include chromeos/owners:v1:/foo/OWNERS\n",
    # Bots listed directly.
    "3su6n15k.default@developer.gserviceaccount.com\n",
)


@pytest.mark.parametrize("data", BAD_DATA)
def test_bad_owners(data):
    """Test good owners files."""
    assert not owners.lint_data("pylint", data)
