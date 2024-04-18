# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities around the os module."""

import functools
import getpass
import os
from pathlib import Path
import pwd
import sys
from typing import Optional


class Error(Exception):
    """Base error class for the module."""


class UnknownHomeDirectoryError(Error):
    """Unable to locate the non-root user's home directory."""


class UnknownNonRootUserError(Error):
    """Unable to identify the non-root user."""


def is_root_user() -> bool:
    """Returns True if the user has root privileges.

    For a given process there are two ID's, that we care about. The real user ID
    and effective user ID. The real user ID or simply referred as uid, is the ID
    assigned for the user on whose behalf the process is running. Effective user
    ID is used for privilege checks.

    For a given process the real user ID and effective user ID can be different
    and the access to resources are determined based on the effective user ID.
    For example, a regular user with uid 12345, may not have access to certain
    resources. Running with sudo privileges will make the euid to be 0 (Root)
    (while the uid remains the same 12345) and will gain certain resource
    access.

    Hence to check if a user has root privileges, it is best to check the euid
    of the process.
    """
    return os.geteuid() == 0


def is_non_root_user() -> bool:
    """Returns True if user doesn't have root privileges."""
    return not is_root_user()


def assert_root_user(name: Optional[str] = None):
    """Assert root user."""
    name = name or Path(sys.argv[0]).name
    assert is_root_user(), f"{name}: please run as root user"


def assert_non_root_user(name: Optional[str] = None):
    """Assert root user."""
    name = name or Path(sys.argv[0]).name
    assert is_non_root_user(), f"{name}: please run as non root user"


def require_root_user(_reason):
    """Decorator to note/assert a function must be called as the root user."""

    def outer(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            assert_root_user(func.__name__)
            return func(*args, **kwargs)

        return wrapper

    return outer


def require_non_root_user(_reason):
    """Decorator to note/assert a function must be called as a non-root user."""

    def outer(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            assert_non_root_user(func.__name__)
            return func(*args, **kwargs)

        return wrapper

    return outer


def switch_to_sudo_user(
    clear_saved_id: bool = False,
) -> None:
    """Switch back to the user that ran sudo.

    This assumes the current user is root and was invoked via sudo.

    Args:
        clear_saved_id: Whether to clear the saved-uid & saved-gid.  Retaining
            will allow code to switch back to root via e.g. os.setuid() calls.
    """
    # NB: This assumes HOME was already initialized to the sudo user's home.
    # See commandline.RunAsRootUser that handles this.
    gid = int(os.environ.pop("SUDO_GID"))
    uid = int(os.environ.pop("SUDO_UID"))
    user = os.environ.pop("SUDO_USER")
    os.initgroups(user, gid)
    os.setresgid(gid, gid, gid if clear_saved_id else -1)
    os.setresuid(uid, uid, uid if clear_saved_id else -1)
    os.environ["USER"] = user


def non_root_home() -> Path:
    """Get the home directory for the relevant non-root user."""
    if is_non_root_user():
        return Path("~").expanduser()

    non_root_user = get_non_root_user()
    if non_root_user:
        try:
            return Path(f"~{non_root_user}").expanduser()
        except RuntimeError as e:
            raise UnknownHomeDirectoryError(
                f"Could not find home directory for {non_root_user}."
            ) from e

    raise UnknownNonRootUserError("Unable to identify the non-root user.")


def get_non_root_user() -> Optional[str]:
    """Returns a non-root user, defaults to the current user.

    If the current user is root, returns the username of the person who
    ran the emerge command. If running using sudo, returns the username
    of the person who ran the sudo command. If no non-root user is
    found, returns None.
    """
    if is_root_user():
        user = os.environ.get("PORTAGE_USERNAME", os.environ.get("SUDO_USER"))
    else:
        try:
            user = pwd.getpwuid(os.getuid()).pw_name
        except KeyError:
            user = getpass.getuser()

    if user == "root":
        return None
    else:
        return user
