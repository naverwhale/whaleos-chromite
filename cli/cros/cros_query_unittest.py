# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for cros_query.py."""

from unittest import mock

import pytest

from chromite.cli.cros import cros_query
from chromite.lib import build_query
from chromite.lib import commandline


def test_compile_filter():
    """Test the compile_filter function."""
    board_foo = build_query.Board("foo")
    board_bar = build_query.Board("bar")
    flt = cros_query.compile_filter("name == 'foo'")
    assert flt(board_foo)
    assert not flt(board_bar)


def test_filter_globals():
    """Test compiled filters have access to a limited set of globals."""
    board_foo = build_query.Board("foo")
    board_bar = build_query.Board("bar")
    board_foobar = build_query.Board("foobar")
    flt = cros_query.compile_filter("any(x == 'o' for x in name)")
    assert flt(board_foo)
    assert not flt(board_bar)
    assert flt(board_foobar)


class FakeProfile(build_query.Profile):
    """Fake profile for testing purposes."""

    def __init__(self, name, overlay_name, parents):
        # pylint: disable=super-init-not-called
        self.name = name
        self.overlay = mock.Mock()
        self.overlay.name = overlay_name
        self.parents = parents

    @classmethod
    def find_all(cls, board=None, overlays=""):
        yield CHIPSET_LAKELAKE
        yield BASEBOARD_MALTEER
        yield MALTEER
        yield CHIPSET_LAKELAKE_PRIVATE
        yield BASEBOARD_MALTEER_PRIVATE
        yield CHEETS_PRIVATE
        yield MALTEER_PRIVATE

    def some_method(self, arg):
        """Fake method for testing output format functionality."""
        return f"{self.name} {arg}"


# Some fake profiles for testing.
CHIPSET_LAKELAKE = FakeProfile("base", "chipset-lakelake", [])
BASEBOARD_MALTEER = FakeProfile("base", "baseboard-malteer", [CHIPSET_LAKELAKE])
MALTEER = FakeProfile("base", "malteer", [BASEBOARD_MALTEER])
CHIPSET_LAKELAKE_PRIVATE = FakeProfile(
    "base", "chipset-lakelake-private", [CHIPSET_LAKELAKE]
)
BASEBOARD_MALTEER_PRIVATE = FakeProfile(
    "base",
    "baseboard-malteer-private",
    [BASEBOARD_MALTEER, CHIPSET_LAKELAKE_PRIVATE],
)
CHEETS_PRIVATE = FakeProfile("android", "cheets-private", [])
MALTEER_PRIVATE = FakeProfile(
    "base",
    "malteer-private",
    [MALTEER, BASEBOARD_MALTEER_PRIVATE, CHEETS_PRIVATE],
)


def test_tree(capsys):
    """Test the tree_result functionality."""
    cros_query.tree_result(MALTEER_PRIVATE, str)
    captured = capsys.readouterr()
    assert (
        captured.out
        == """\
malteer-private:base
├─malteer:base
│ ╰─baseboard-malteer:base
│   ╰─chipset-lakelake:base
├─baseboard-malteer-private:base
│ ├─baseboard-malteer:base
│ │ ╰─chipset-lakelake:base
│ ╰─chipset-lakelake-private:base
│   ╰─chipset-lakelake:base
╰─cheets-private:android
"""
    )


def _run_cros_query(args):
    """Helper to run cros query with the given arguments."""
    parser = commandline.ArgumentParser(filter=True)
    cros_query.QueryCommand.AddParser(parser)
    opts = parser.parse_args(args)
    cmd = cros_query.QueryCommand(opts)
    return cmd.Run()


def test_query_profiles(capsys, monkeypatch):
    """Test querying profiles with a filter."""
    monkeypatch.setattr(cros_query, "QUERY_TARGETS", {"profiles": FakeProfile})
    _run_cros_query(["profiles", "-f", "'malteer' in overlay.name"])
    captured = capsys.readouterr()
    assert (
        captured.out
        == """\
baseboard-malteer:base
malteer:base
baseboard-malteer-private:base
malteer-private:base
"""
    )


def test_query_profiles_alt_format(capsys, monkeypatch):
    """Test querying profiles with -o formatting argument."""
    monkeypatch.setattr(cros_query, "QUERY_TARGETS", {"profiles": FakeProfile})
    _run_cros_query(
        [
            "profiles",
            "-f",
            "'malteer' in overlay.name",
            "-o",
            "{overlay.name} {some_method('ohea')}",
        ]
    )
    captured = capsys.readouterr()
    assert (
        captured.out
        == """\
baseboard-malteer base ohea
malteer base ohea
baseboard-malteer-private base ohea
malteer-private base ohea
"""
    )


def test_query_bad_positional():
    """Test a bad positional arg."""
    # argparse should gracefully catch this, instead of throwing some other
    # exception.
    with pytest.raises(SystemExit):
        # "board" is a misspelling of "boards".
        _run_cros_query(["board"])
