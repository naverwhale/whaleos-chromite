# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Support for XDG paths.

https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
"""

import functools
import getpass
import logging
import os
from pathlib import Path
import tempfile

from chromite.utils import os_util


@functools.lru_cache(maxsize=None)
def _is_chrome_bot() -> bool:
    """Is the current user/run the 'chrome-bot' builder.

    chrome-bot gets permission denied for /home/chrome-bot/.config/chromite.
    """
    return "chrome-bot" in (
        getpass.getuser(),
        os.environ.get("SUDO_USER"),
    )


@functools.lru_cache(maxsize=None)
def _get_homedir() -> Path:
    """Find the user's homedir."""
    if _is_chrome_bot():
        # pylint: disable=consider-using-with
        return Path(tempfile.gettempdir())
    elif os_util.is_root_user():
        # Running as root, fall back to hardcoded, most common answer for the
        # user.
        try:
            return os_util.non_root_home()
        except os_util.Error as e:
            logging.warning(
                "Unable to locate a non-root user home, "
                "falling back to root's configs."
            )
            logging.debug(e)

    return Path("~").expanduser()


def _get_path(subdir: str, xdg_property: str) -> Path:
    """Get the xdg path.

    Args:
        subdir: The subdir name if XDG APIs are not available.
        xdg_property: The XDG module API to use if available.
    """
    if _is_chrome_bot() or os_util.is_root_user():
        return _get_homedir() / subdir

    try:
        import xdg.BaseDirectory

        return Path(getattr(xdg.BaseDirectory, xdg_property))
    except ImportError:
        pass

    return _get_homedir() / subdir


def _get_cache_home() -> Path:
    """The $XDG_CACHE_HOME."""
    return _get_path(".cache", "xdg_cache_home")


def _get_config_home() -> Path:
    """The $XDG_CONFIG_HOME."""
    return _get_path(".config", "xdg_config_home")


def _get_state_home() -> Path:
    """The $XDG_STATE_HOME."""
    return _get_path(".local/state", "xdg_state_home")


# The base directory relative to which user-specific non-essential data files
# should be stored.
CACHE_HOME = _get_cache_home()


# The base directory relative to which user-specific configuration files should
# be stored.
CONFIG_HOME = _get_config_home()


# The base directory relative to which user-specific state files should be
# stored.
STATE_HOME = _get_state_home()
