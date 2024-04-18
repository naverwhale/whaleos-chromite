# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for os_util.py."""

import os
from pathlib import Path
from unittest import mock

import pytest

from chromite.utils import os_util


@pytest.fixture(name="as_root_user")
def _as_root_user(monkeypatch):
    """Monkeypatch the euid as 0."""
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    yield


@pytest.fixture(name="as_non_root_user")
def _as_non_root_user(monkeypatch):
    """Monkeypatch the euid as non-0."""
    monkeypatch.setattr(os, "geteuid", lambda: 1)
    yield


# pylint: disable=unused-argument
def test_root_user_checks_as_root_user(as_root_user):
    """Test is_[non_]root_user as the root user."""
    assert os_util.is_root_user()
    os_util.assert_root_user()

    assert not os_util.is_non_root_user()
    with pytest.raises(AssertionError):
        os_util.assert_non_root_user()


def test_root_user_checks_as_non_root_user(as_non_root_user):
    """Test is_[non_]root_user as a non-root user."""
    assert os_util.is_non_root_user()
    os_util.assert_non_root_user()

    assert not os_util.is_root_user()
    with pytest.raises(AssertionError):
        os_util.assert_root_user()


def test_root_user_decorator_as_root(as_root_user):
    """Success case for require root user decorator."""

    @os_util.require_root_user("Passes")
    def passes():
        pass

    passes()


@pytest.mark.xfail(raises=AssertionError)
def test_root_user_decorator_as_non_root(as_non_root_user):
    """Failure case for require root user decorator."""

    @os_util.require_root_user("Fails")
    def fails():
        pytest.fail("Allowed to execute as wrong user.")

    fails()


@pytest.mark.xfail(raises=AssertionError)
def test_non_root_user_decorator_as_root(as_root_user):
    """Failure case for require non-root user decorator."""

    @os_util.require_non_root_user("Fails")
    def fails():
        pytest.fail("Allowed to execute as wrong user.")

    fails()


def test_non_root_user_decorator_as_non_root(as_non_root_user):
    """Success case for require non-root user decorator."""

    @os_util.require_non_root_user("Passes")
    def passes():
        pass

    passes()


@pytest.fixture(name="switch_to_sudo_user_mock")
def _switch_to_sudo_user_mock():
    """Mock out privileged APIs."""
    with mock.patch.multiple(
        os,
        initgroups=mock.DEFAULT,
        setresgid=mock.DEFAULT,
        setresuid=mock.DEFAULT,
    ):
        yield


def test_switch_to_sudo_user_saved(as_root_user, switch_to_sudo_user_mock):
    """Verify we switch state properly."""
    os.environ.update(
        {
            "SUDO_GID": "123",
            "SUDO_UID": "456",
            "SUDO_USER": "testuser",
            "USER": "root",
        }
    )
    os_util.switch_to_sudo_user()
    assert "SUDO_GID" not in os.environ
    assert "SUDO_UID" not in os.environ
    assert "SUDO_USER" not in os.environ
    assert os.environ["USER"] == "testuser"
    os.initgroups.assert_called_once_with("testuser", 123)
    os.setresgid.assert_called_once_with(123, 123, -1)
    os.setresuid.assert_called_once_with(456, 456, -1)


def test_switch_to_sudo_user_cleared(as_root_user, switch_to_sudo_user_mock):
    """Verify we switch state properly."""
    os.environ.update(
        {
            "SUDO_GID": "123",
            "SUDO_UID": "456",
            "SUDO_USER": "testuser",
            "USER": "root",
        }
    )
    os_util.switch_to_sudo_user(clear_saved_id=True)
    assert "SUDO_GID" not in os.environ
    assert "SUDO_UID" not in os.environ
    assert "SUDO_USER" not in os.environ
    assert os.environ["USER"] == "testuser"
    os.initgroups.assert_called_once_with("testuser", 123)
    os.setresgid.assert_called_once_with(123, 123, 123)
    os.setresuid.assert_called_once_with(456, 456, 456)


def test_non_root_user_home_as_root(as_root_user, monkeypatch, tmp_path: Path):
    """Test non-root-user-home as root user."""
    user = "user"
    user_home = tmp_path / "home" / user
    user_home.mkdir(parents=True)

    def expanduser(self, *_args, **_kwargs):
        """expanduser patch."""
        assert str(self) == f"~{user}"
        return user_home

    monkeypatch.setattr(Path, "expanduser", expanduser)
    monkeypatch.setenv("PORTAGE_USERNAME", user)

    assert user_home == os_util.non_root_home()


def test_non_root_user_home_as_root_not_found(as_root_user, monkeypatch):
    """Test non-root-user-home as root user when no user found."""
    env = os.environ.copy()
    env.pop("PORTAGE_USERNAME", None)
    env.pop("SUDO_USER", None)
    monkeypatch.setattr(os, "environ", env)

    with pytest.raises(os_util.UnknownNonRootUserError):
        os_util.non_root_home()


def test_non_root_user_home_as_root_pwd_error(as_root_user, monkeypatch):
    def expanduser(self, *_args, **_kwargs):
        """expanduser patch."""
        raise RuntimeError("Error")

    monkeypatch.setattr(Path, "expanduser", expanduser)
    monkeypatch.setenv("PORTAGE_USERNAME", "user")

    with pytest.raises(os_util.UnknownHomeDirectoryError):
        os_util.non_root_home()


def test_get_non_root_user_portage_username(as_root_user, monkeypatch):
    """Test get_non_root_user from PORTAGE_USERNAME."""
    user = "portage_username"
    monkeypatch.setenv("PORTAGE_USERNAME", user)

    assert user == os_util.get_non_root_user()


def test_get_non_root_user_sudo_user(as_root_user, monkeypatch):
    """Test get_non_root_user from SUDO_USER."""
    user = "user"
    env = os.environ.copy()
    env.pop("PORTAGE_USERNAME", None)
    env["SUDO_USER"] = user
    monkeypatch.setattr(os, "environ", env)

    assert user == os_util.get_non_root_user()


def test_get_non_root_user_no_user(as_root_user, monkeypatch):
    """Test get_non_root_user with no user."""
    env = os.environ.copy()
    env.pop("PORTAGE_USERNAME", None)
    env.pop("SUDO_USER", None)
    monkeypatch.setattr(os, "environ", env)

    assert not os_util.get_non_root_user()


# pylint: enable=unused-argument
