# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module tests the cros format command."""

from pathlib import Path
from typing import List
from unittest import mock

from chromite.cli.cros import cros_format
from chromite.format import formatters
from chromite.lib import osutils
from chromite.scripts import cros


# pylint: disable=protected-access


def _call_cros_format(args: List[str]) -> int:
    """Call "cros format" with the given command line arguments.

    Args:
        args: The command line arguments.

    Returns:
        The return code of "cros format".
    """
    return cros.main(["format"] + args)


def test_breakout_files_by_tool():
    """Check extension<->tool mapping."""
    assert not cros_format._BreakoutFilesByTool([])
    assert not cros_format._BreakoutFilesByTool([Path("foo"), Path("blah.xxx")])

    tool_map = cros_format._BreakoutFilesByTool([Path("foo.md")])
    # It's not easy to test the tool_map as the keys are functools partials
    # which do not support equality tests.
    items = list(tool_map.items())
    assert len(items) == 1
    key, value = items[0]
    assert key.func == formatters.whitespace.Data.func
    assert value == [Path("foo.md")]


def test_breakout_files_by_tool_order():
    """Verify we prefer names over extensions."""
    tool_map = cros_format._BreakoutFilesByTool([Path("OWNERS.css")])
    items = list(tool_map.items())
    assert len(items) == 1
    key, value = items[0]
    assert key.func == formatters.whitespace.Data.func
    assert value == [Path("OWNERS.css")]


@mock.patch.dict(
    cros_format._TOOL_MAP,
    {frozenset({"dir/foo.ZZZ"}): (mock.sentinel.tool,)},
)
def test_breakout_files_full_paths():
    """Verify we match files in named subdirs."""
    source_files = sorted(
        Path(x)
        for x in (
            "dir/foo.ZZZ",
            "./dir/foo.ZZZ",
            "../dir/foo.ZZZ",
            "blah/dir/foo.ZZZ",
            "/a/b/c/d/dir/foo.ZZZ",
        )
    )
    tool_map = cros_format._BreakoutFilesByTool(source_files)
    items = list(tool_map.items())
    assert len(items) == 1
    assert items[0][0] is mock.sentinel.tool
    assert sorted(items[0][1]) == source_files


def test_cli_no_files(caplog):
    """Check cros format handling with no files."""
    assert _call_cros_format([]) == 0
    assert "No files found to process." in caplog.text


def test_cli_no_matched_files(caplog):
    """Check cros format handling with no matched files."""
    assert _call_cros_format(["foo"]) == 0
    assert "No files support formatting." in caplog.text


def test_cli_one_file(tmp_path):
    """Check behavior with one file."""
    file = tmp_path / "foo.txt"
    osutils.Touch(file)
    assert _call_cros_format([str(file)]) == 0


def test_cli_dir(tmp_path):
    """Test the CLI expands directories when given one."""
    files = [tmp_path / "foo.txt", tmp_path / "bar.txt"]
    for file in files:
        osutils.Touch(file)
    assert _call_cros_format([str(tmp_path)]) == 0


def test_cli_many_files(tmp_path):
    """Check behavior with many files."""
    files = []
    for n in range(0, 10):
        file = tmp_path / f"foo.{n}.txt"
        osutils.Touch(file)
        files.append(str(file))
    assert _call_cros_format(files) == 0


def test_diff_file(tmp_path):
    """Check behavior with --diff file."""
    file = tmp_path / "foo.txt"
    file.write_text(" ", encoding="utf-8")
    assert _call_cros_format(["--diff", str(file)]) == 1
    assert " " == file.read_text(encoding="utf-8")


def test_check_file(tmp_path):
    """Check behavior with --check file."""
    file = tmp_path / "foo.txt"
    file.write_text(" ", encoding="utf-8")
    for arg in ("-n", "--dry-run", "--check"):
        assert _call_cros_format([arg, str(file)]) == 1
        assert " " == file.read_text(encoding="utf-8")


def check_multiple_files(tmp_path, contents, expected_ret):
    """Helper to check behavior with --check with multiple files."""
    files = []
    for i, content in enumerate(contents):
        file = tmp_path / f"foo.{i}.txt"
        files.append(str(file))
        file.write_text(content, encoding="utf-8")
    for arg in ("-n", "--dry-run", "--check"):
        assert _call_cros_format([arg, *files]) == expected_ret


def test_check_multiple_files_with_first_broken(tmp_path):
    """Check --check fails when the first supplied file is broken."""
    check_multiple_files(tmp_path, [" ", ""], 1)


def test_check_multiple_files_with_last_broken(tmp_path):
    """Check --check fails when the last supplied file is broken."""
    check_multiple_files(tmp_path, ["", " "], 1)


def test_stdout_file(tmp_path):
    """Check behavior with --stdout file."""
    file = tmp_path / "foo.txt"
    file.write_text(" ", encoding="utf-8")
    assert _call_cros_format(["--stdout", str(file)]) == 1
    assert " " == file.read_text(encoding="utf-8")


def test_inplace_file(tmp_path):
    """Check behavior with --inplace file."""
    file = tmp_path / "foo.txt"
    file.write_text(" ", encoding="utf-8")
    assert _call_cros_format([str(file)]) == 0
    assert "" == file.read_text(encoding="utf-8")


def test_missing_file(tmp_path):
    """Check behavior with missing files."""
    file = tmp_path / "foo.py"
    assert _call_cros_format([str(file)]) == 1


def test_unicode_error(tmp_path):
    """Check binary files don't crash."""
    file = tmp_path / "foo.txt"
    file.write_bytes(b"\xff")
    assert _call_cros_format([str(file)]) == 1


def test_parse_error_json(tmp_path):
    """Check JSON parsing errors don't crash."""
    file = tmp_path / "foo.json"
    file.write_bytes(b"{")
    assert _call_cros_format([str(file)]) == 1


def test_parse_error_python(tmp_path):
    """Check Python parsing errors don't crash."""
    file = tmp_path / "foo.py"
    file.write_bytes(b"'")
    assert _call_cros_format([str(file)]) == 1


def test_parse_error_xml(tmp_path):
    """Check XML parsing errors don't crash."""
    file = tmp_path / "foo.xml"
    file.write_bytes(b"<")
    assert _call_cros_format([str(file)]) == 1
