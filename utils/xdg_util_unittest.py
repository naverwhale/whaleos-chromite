# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for xdg_util."""

import getpass
from pathlib import Path
import tempfile
from unittest import mock

import pytest

from chromite.utils import os_util
from chromite.utils import xdg_util


# pylint: disable=protected-access


@pytest.fixture(name="as_chrome_bot")
def _as_chrome_bot(monkeypatch):
    """Monkeypatch the runtime as if we're chrome-bot."""
    monkeypatch.setattr(getpass, "getpass", lambda: "chrome-bot")
    monkeypatch.setenv("SUDO_USER", "chrome-bot")
    yield


@pytest.fixture(name="as_not_chrome_bot")
def _as_not_chrome_bot(monkeypatch):
    """Monkeypatch the runtime as if we're not chrome-bot."""
    monkeypatch.setattr(getpass, "getpass", lambda: "user")
    monkeypatch.setenv("SUDO_USER", "user")
    yield


@pytest.fixture(autouse=True)
def reset_xdg_util_caches():
    """Reset the various cache state so each test runs fresh."""
    xdg_util._is_chrome_bot.cache_clear()
    xdg_util._get_homedir.cache_clear()


def test_chrome_bot_paths(as_chrome_bot):  # pylint: disable=unused-argument
    """Check paths when run as chrome-bot."""
    assert xdg_util._is_chrome_bot()

    d = xdg_util._get_cache_home()
    assert d.name == ".cache"
    # NB: This will crash if it isn't relative to the tempdir.
    d.relative_to(tempfile.tempdir)

    d = xdg_util._get_config_home()
    assert d.name == ".config"
    # NB: This will crash if it isn't relative to the tempdir.
    d.relative_to(tempfile.tempdir)

    d = xdg_util._get_state_home()
    assert d.parts[-2:] == (".local", "state")
    # NB: This will crash if it isn't relative to the tempdir.
    d.relative_to(tempfile.tempdir)


@mock.patch.multiple(os_util, is_root_user=lambda: False)
def test_non_root_paths(as_not_chrome_bot):  # pylint: disable=unused-argument
    """Check paths when run as non-root user."""
    assert not xdg_util._is_chrome_bot()

    d = xdg_util._get_cache_home()
    assert d.name == ".cache"
    # NB: This will crash if it isn't relative to the tempdir.
    d.relative_to(Path("~").expanduser())

    d = xdg_util._get_config_home()
    assert d.name == ".config"
    # NB: This will crash if it isn't relative to the tempdir.
    d.relative_to(Path("~").expanduser())

    d = xdg_util._get_state_home()
    assert d.parts[-2:] == (".local", "state")
    # NB: This will crash if it isn't relative to the tempdir.
    d.relative_to(Path("~").expanduser())


@mock.patch.multiple(
    os_util, is_root_user=lambda: True, non_root_home=lambda: Path("/foo")
)
def test_root_paths(as_not_chrome_bot):  # pylint: disable=unused-argument
    """Check paths when run as root user."""
    assert not xdg_util._is_chrome_bot()
    assert xdg_util._get_cache_home() == Path("/foo/.cache")
    assert xdg_util._get_config_home() == Path("/foo/.config")
    assert xdg_util._get_state_home() == Path("/foo/.local/state")
