# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for the analyzers module."""

from typing import List
from unittest import mock

from chromite.cli import analyzers
from chromite.lib import commandline


def process_args(args: List[str]) -> commandline.ArgumentNamespace:
    """Feeds an ArgumentParser with the provided `args` to AnalyzerCommand."""
    parser = commandline.ArgumentParser()
    analyzers.AnalyzerCommand.AddParser(parser)
    parser_namespace = parser.parse_args(args)
    analyzers.AnalyzerCommand.ProcessOptions(parser, parser_namespace)
    return parser_namespace


# Patch can_modify_files to return True for additional coverage.
@mock.patch(
    "chromite.cli.analyzers.AnalyzerCommand.can_modify_files", return_value=True
)
def test_get_files_from_commit(_, run_mock) -> None:
    """Test files from commit are correctly reconstructed as absolute paths."""
    run_mock.AddCmdResult(
        ["git", "rev-parse", "--show-toplevel"], stdout="/path/to/root\n"
    )
    run_mock.AddCmdResult(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "ignored"],
        stdout="file1\nsub/file2\n",
    )
    # There is a third, more verbose call to `git` to check for uncommitted
    # changes. Use no output to indicate that there are none.
    run_mock.SetDefaultCmdResult(stdout="")
    parser_namespace = process_args(["--commit", "ignored"])
    assert run_mock.call_count == 3
    assert parser_namespace.files == [
        "/path/to/root/file1",
        "/path/to/root/sub/file2",
    ]


def test_commit_is_pre_submit(run_mock) -> None:
    """Test the special "pre-submit" commit id used by pre-upload.py."""
    parser_namespace = process_args(["--commit", "pre-submit"])
    assert not run_mock.called, "Should not call out to git."
    assert not parser_namespace.files, "Files should remain empty."


@mock.patch.multiple(
    analyzers.AnalyzerCommand, can_modify_files=True, use_dryrun_options=True
)
def test_dry_run_never_inplace() -> None:
    """Ensure --check ignores --inplace (sets it to False)."""
    assert process_args(["--inplace"]).inplace
    assert not process_args(["--check"]).inplace
    assert not process_args(["--check", "--inplace"]).inplace


def test_has_uncommitted_changes(run_mock) -> None:
    """Test handling of porcelain output for uncommitted change."""
    run_mock.SetDefaultCmdResult(stdout="M file\n")
    assert analyzers.HasUncommittedChanges(["/path/to/file"]) is True


def test_has_no_uncommitted_changes(run_mock) -> None:
    """Test handling of porcelain output when no uncommitted changes."""
    run_mock.SetDefaultCmdResult(stdout="")
    assert analyzers.HasUncommittedChanges(["/path/to/file"]) is False


@mock.patch.multiple(
    analyzers.AnalyzerCommand, can_modify_files=True, use_dryrun_options=True
)
def test_inplace_dryrun_default(caplog) -> None:
    """Check default inplace behavior."""
    result = process_args(["f.txt"])
    assert result.inplace

    result = process_args(["--inplace", "f.txt"])
    assert result.inplace

    result = process_args(["--check", "f.txt"])
    assert not result.inplace

    # The inplace & dry-run *defaults* should *not* warn on conflicts.
    assert caplog.text == ""

    result = process_args(["--inplace", "--check", "f.txt"])
    assert not result.inplace

    # inplace & dry-run options should warn on conflicts.
    assert caplog.text != ""


@mock.patch.multiple(
    analyzers.AnalyzerCommand, can_modify_files=True, use_dryrun_options=False
)
def test_inplace_no_dryrun_default(caplog) -> None:
    """Check default inplace behavior."""
    result = process_args(["f.txt"])
    assert result.inplace

    result = process_args(["--stdout", "f.txt"])
    assert not result.inplace

    result = process_args(["--stdout", "--inplace", "f.txt"])
    assert result.inplace

    result = process_args(["--inplace", "--stdout", "f.txt"])
    assert not result.inplace

    assert caplog.text == ""


@mock.patch.multiple(
    analyzers.AnalyzerCommand, can_modify_files=False, use_dryrun_options=True
)
def test_no_inplace_dryrun_default(caplog) -> None:
    """Make sure we don't crash when inplace isn't enabled."""
    result = process_args(["f.txt"])
    assert not hasattr(result, "inplace")

    assert caplog.text == ""


@mock.patch.multiple(
    analyzers.AnalyzerCommand, can_modify_files=False, use_dryrun_options=False
)
def test_no_inplace_no_dryrun_default(caplog) -> None:
    """Make sure we don't crash when these options aren't enabled."""
    result = process_args(["f.txt"])
    assert not hasattr(result, "inplace")

    assert caplog.text == ""
