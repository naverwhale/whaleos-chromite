# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for package_completers."""

import argparse
from pathlib import Path
from typing import Callable, List

import pytest

from chromite.lib import portage_util
from chromite.lib import sysroot_lib
from chromite.lib.completers import package_completers


# Pytest's method of declaring fixtures causes Pylint to complain about
# redefined outer names.
# pylint: disable=redefined-outer-name


class MockSysroot:
    """Class to mock a Sysroot object for testing."""

    def get_overlays(self):
        return [
            "/test/path/overlay1",
            "/test/path/overlay2",
        ]


@pytest.fixture
def simple_parser() -> argparse.ArgumentParser:
    """Create a simple parser with arguments needed for testing."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--sysroot")
    parser.add_argument("--board")
    parser.add_argument("--build-target")
    parser.add_argument("--foo")
    return parser


@pytest.fixture
def get_ebuilds() -> Callable:
    """Returns ebuild files for testing."""

    def mock_return(*_args, **_kwargs) -> List[Path]:
        return [
            Path("/package1/bar1/bar1-1.0.ebuild"),
            Path("/package2/bar2/bar2-2.0.ebuild"),
        ]

    return mock_return


def test_package(monkeypatch, get_ebuilds, simple_parser):
    """Test that the package completer returns packages with versions."""

    def mock_sysroot(sysroot_path, *_args, **_kwargs):
        assert sysroot_path == "/build/grunt"
        return MockSysroot()

    monkeypatch.setattr(sysroot_lib, "Sysroot", mock_sysroot)
    monkeypatch.setattr(portage_util, "FindEbuildsForOverlays", get_ebuilds)
    expected_packages = ["package1/bar1-1.0", "package2/bar2-2.0"]

    packages = package_completers.package(
        None, None, None, simple_parser.parse_args(["--board", "grunt"])
    )

    assert packages == expected_packages


def test_package_atom(monkeypatch, get_ebuilds, simple_parser):
    """Verify the package atom completer returns packages without versions."""

    def mock_sysroot(sysroot_path, *_args, **_kwargs):
        assert sysroot_path == "/"
        return MockSysroot()

    monkeypatch.setattr(sysroot_lib, "Sysroot", mock_sysroot)
    monkeypatch.setattr(portage_util, "FindEbuildsForOverlays", get_ebuilds)
    expected_packages = ["package1/bar1", "package2/bar2"]

    packages = package_completers.package_atom(
        None, None, None, simple_parser.parse_args(["--foo", "bar"])
    )

    assert packages == expected_packages
