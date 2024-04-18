# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for generate_query_docs.py."""

from chromite.scripts import generate_query_docs


def test_generated_contents(tmp_path):
    """Test the output file matches the generated contents."""
    # pylint: disable=protected-access
    current_file = generate_query_docs._DEFAULT_OUTPUT
    current_contents = current_file.read_text(encoding="utf-8")

    new_file = tmp_path / "output.md"
    generate_query_docs.main(["-o", str(new_file)])
    new_contents = new_file.read_text(encoding="utf-8")

    assert current_contents == new_contents, (
        f"{current_file} needs regenerated.  Please run "
        "scripts/generate_query_docs.",
    )
