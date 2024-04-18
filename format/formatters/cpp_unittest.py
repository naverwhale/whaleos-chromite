# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the cpp module."""

import pytest

from chromite.format.formatters import cpp


# None means input is already formatted to avoid having to repeat.
@pytest.mark.parametrize(
    "data,exp",
    (
        ("", None),
        ("int main() {}", None),
        ("int main(){return 0;}", "int main() { return 0; }"),
    ),
)
def test_check_format(data, exp):
    """Verify inputs match expected outputs."""
    if exp is None:
        exp = data
    assert exp == cpp.Data(data)
