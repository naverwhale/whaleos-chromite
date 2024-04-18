# Copyright 2014 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module tests the cros lint command."""

import os
from pathlib import Path
from typing import List
from unittest import mock

import pytest

from chromite.cli.cros import cros_lint
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.scripts import cros


# pylint: disable=protected-access


def test_breakout_files_by_tool():
    """Check extension<->tool mapping."""
    assert not cros_lint._BreakoutFilesByTool([])
    assert not cros_lint._BreakoutFilesByTool([Path("foo"), Path("blah.xxx")])

    tool_map = cros_lint._BreakoutFilesByTool([Path("foo.md")])
    items = list(tool_map.items())
    assert len(items) == 2
    key, value = items[0]
    assert key is cros_lint._MarkdownLintFile
    assert value == [Path("foo.md")]


def test_breakout_files_by_tool_order():
    """Verify we prefer names over extensions."""
    tool_map = cros_lint._BreakoutFilesByTool([Path("OWNERS.css")])
    items = list(tool_map.items())
    assert len(items) == 2
    assert items[0][0] is cros_lint._OwnersLintFile


@mock.patch.dict(
    cros_lint._TOOL_MAP,
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
    tool_map = cros_lint._BreakoutFilesByTool(source_files)
    items = list(tool_map.items())
    assert len(items) == 1
    assert items[0][0] is mock.sentinel.tool
    assert sorted(items[0][1]) == source_files


class LintCommandTest(cros_test_lib.TestCase):
    """Test class for our LintCommand class."""

    def testOutputArgument(self):
        """Tests that the --output argument mapping for cpplint is complete."""
        self.assertEqual(
            set(cros_lint.LintCommand.OUTPUT_FORMATS),
            set(cros_lint.CPPLINT_OUTPUT_FORMAT_MAP.keys()) | {"default"},
        )


class JsonTest(cros_test_lib.TempDirTestCase):
    """Tests for _JsonLintFile."""

    def testValid(self):
        """Verify valid json file is accepted."""
        path = os.path.join(self.tempdir, "x.json")
        osutils.WriteFile(path, "{}\n")
        ret = cros_lint._JsonLintFile(path, None, None, False, "")
        self.assertEqual(ret.returncode, 0)

    def testInvalid(self):
        """Verify invalid json file is rejected."""
        path = os.path.join(self.tempdir, "x.json")
        osutils.WriteFile(path, "{")
        ret = cros_lint._JsonLintFile(path, None, None, False, "")
        self.assertEqual(ret.returncode, 1)

    def testUnicodeBom(self):
        """Verify we skip the Unicode BOM."""
        path = os.path.join(self.tempdir, "x.json")
        osutils.WriteFile(path, b"\xef\xbb\xbf{}\n", mode="wb")
        ret = cros_lint._JsonLintFile(path, None, None, False, "")
        self.assertEqual(ret.returncode, 0)


def test_non_exec(tmp_path):
    """Tests for _NonExecLintFile."""
    # Ignore dirs.
    ret = cros_lint._NonExecLintFile(tmp_path, False, False, False, "")
    assert ret.returncode == 0

    # Create a data file.
    path = tmp_path / "foo.txt"
    path.write_text("", encoding="utf-8")

    # -x data files are OK.
    path.chmod(0o644)
    ret = cros_lint._NonExecLintFile(path, False, False, False, "")
    assert ret.returncode == 0

    # +x data files are not OK.
    path.chmod(0o755)
    ret = cros_lint._NonExecLintFile(path, False, False, False, "")
    assert ret.returncode == 1

    # Ignore symlinks to bad files.
    sym_path = tmp_path / "sym.txt"
    sym_path.symlink_to(path.name)
    ret = cros_lint._NonExecLintFile(sym_path, False, False, False, "")
    assert ret.returncode == 0

    # Ignore broken symlinks.
    sym_path = tmp_path / "broken.txt"
    sym_path.symlink_to("asdfasdfasdfasdf")
    ret = cros_lint._NonExecLintFile(sym_path, False, False, False, "")
    assert ret.returncode == 0


def test_cpplint(tmp_path):
    """Tests for _CpplintFile."""
    path = tmp_path / "test.cc"

    # Simple file should pass.
    path.write_text(
        "// Copyright\nint main() {\n  return 0;\n}\n", encoding="utf-8"
    )
    ret = cros_lint._CpplintFile(path, "colorized", False, False, "")
    assert ret.returncode == 0

    # File missing trailing newlines.
    path.write_text(
        "// Copyright\nint main() {\n  return 0;\n}", encoding="utf-8"
    )
    ret = cros_lint._CpplintFile(path, "colorized", False, False, "")
    assert ret.returncode


def _call_cros_lint(args: List[str]) -> int:
    """Call "cros lint" with the given command line arguments.

    Args:
        args: The command line arguments.

    Returns:
        The return code of "cros lint".
    """
    return cros.main(["lint"] + args)


@pytest.fixture(name="breakout_files")
def breakout_files_fixture() -> object:
    """Fixture that mocks _BreakoutFilesByTool to observe files to process."""
    with mock.patch(
        "chromite.cli.cros.cros_lint._BreakoutFilesByTool", spec=True
    ) as breakout_files:
        yield breakout_files


def test_no_files(breakout_files):
    """Test to ensure passing no files is not an error."""
    assert _call_cros_lint([]) == 0
    assert not breakout_files.called


def test_expand_dir(tmp_path, breakout_files):
    """Test the CLI expands directories when given one."""
    files = [tmp_path / "foo.txt", tmp_path / "bar.txt"]
    for file in files:
        osutils.Touch(file)
    assert _call_cros_lint([str(tmp_path)]) == 0
    assert set(breakout_files.call_args.args[0]) == set(files)
