# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test for cros_generate_coverage_artifacts."""

import logging
from pathlib import Path

import pytest

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.scripts import cros_generate_coverage_artifacts


def test_generate_kernel_artifacts_success(
    run_mock: cros_test_lib.RunCommandMock, tmp_path: Path
):
    """Test happy path for generating kernel artifacts."""
    filesystem = [
        cros_test_lib.Directory("dir1", ["file1.gcno"]),
        cros_test_lib.Directory("dir2", ["file1.gcno", "file2.gcno"]),
    ]

    cros_test_lib.CreateOnDiskHierarchy(tmp_path, filesystem)
    run_mock.SetDefaultCmdResult(stdout="foo")
    result = cros_generate_coverage_artifacts.generate_kernel_artifacts(
        tmp_path
    )
    expected = {
        "dir1_file1.gcov": "foo",
        "dir2_file1.gcov": "foo",
        "dir2_file2.gcov": "foo",
    }
    assert result == expected


def test_generate_kernel_artifacts_exception(
    run_mock: cros_test_lib.RunCommandMock, tmp_path: Path
):
    """Test exception is thrown for runc cmd errors."""
    filesystem = [
        cros_test_lib.Directory("dir1", ["file1.gcno"]),
    ]

    cros_test_lib.CreateOnDiskHierarchy(tmp_path, filesystem)
    run_mock.SetDefaultCmdResult(returncode=1)
    with pytest.raises(cros_build_lib.RunCommandError):
        cros_generate_coverage_artifacts.generate_kernel_artifacts(tmp_path)


def test_generate_kernel_artifacts_nil_gcno(tmp_path: Path):
    """Test none result when no gcno files present."""
    filesystem = [
        cros_test_lib.Directory("dir1", ["file1.cc"]),
    ]
    cros_test_lib.CreateOnDiskHierarchy(tmp_path, filesystem)
    result = cros_generate_coverage_artifacts.generate_kernel_artifacts(
        tmp_path
    )
    assert not result


def test_generate_LLVM_artifacts_success(
    run_mock: cros_test_lib.RunCommandMock,
):
    """Test happy path for generating LLVM artifacts."""
    files = ["file1", "file2"]
    path = constants.CHROMITE_SCRIPTS_DIR / "testdata/test.profdata"
    expected = [
        "llvm-cov",
        "export",
        "--skip-expansions",
        "--object=file1",
        "--object=file2",
        f"-instr-profile={path}",
    ]
    kwargs = {
        "capture_output": True,
        "encoding": "utf-8",
        "debug_level": logging.DEBUG,
    }

    run_mock.SetDefaultCmdResult(stdout="foo")
    out = cros_generate_coverage_artifacts.generate_llvm_artifacts(files)
    run_mock.assertCommandCalled(expected, **kwargs)
    assert out == "foo"


def test_generate_LLVM_artifacts_exception(
    run_mock: cros_test_lib.RunCommandMock,
):
    """Test exception is thrown for runc cmd errors."""
    files = ["file1", "file2"]
    run_mock.SetDefaultCmdResult(returncode=1)
    with pytest.raises(cros_build_lib.RunCommandError):
        cros_generate_coverage_artifacts.generate_llvm_artifacts(files)


def test_generate_LLVM_artifacts_empty_files():
    """Test None returns for no valid object files."""
    files = []
    assert (
        cros_generate_coverage_artifacts.generate_llvm_artifacts(files) is None
    )
