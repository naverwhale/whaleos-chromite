# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides utility for linting OWNERS."""

import logging
import os
from pathlib import Path
import re
from typing import Union

from chromite.lint import linters


# Cross-repository includes take the form:
# include [server/path[:branch]:]/path/to/file
_INCLUDE_RE = re.compile(
    r"^include +((?P<repo>[^:]*):((?P<branch>[^:]*):)?)?(?P<path>[^\s]*)"
)

# Current version of our owners repo.
_SHARED_OWNERS_BRANCH = "v1"

# Known bots that have shared owners settings.
_KNOWN_BOTS = {
    "3su6n15k.default@developer.gserviceaccount.com",
    "chromeos-ci-prod@chromeos-bot.iam.gserviceaccount.com",
    "chromeos-ci-release@chromeos-bot.iam.gserviceaccount.com",
}


def lint_data(path: Union[str, os.PathLike], data: str) -> bool:
    """Run basic checks on |data|.

    Args:
        path: The name of the file (for diagnostics).
        data: The file content to lint.

    Returns:
        True if everything passed.
    """
    path = Path(path)
    ret = linters.whitespace.Data(data, path)

    lines = data.splitlines()

    if not lines:
        ret = False
        logging.error("%s: empty owners file not allowed", path)

    for i, line in enumerate(lines):
        if "\t" in line:
            ret = False
            logging.error('%s:%i: no tabs allowed: "%s"', path, i, line)

        lstrip = line.lstrip()
        if lstrip != line:
            ret = False
            logging.error(
                '%s:%i: no leading whitespace allowed: "%s"', path, i, line
            )

        if not lstrip:
            continue

        # We don't want people listing bot accounts directly.
        # Unless it's explicitly the bots/ tree in the shared owners repo.
        owner = lstrip.split()[0]
        if owner in _KNOWN_BOTS and path.parent.name != "bots":
            ret = False
            logging.error(
                '%s:%i: use go/cros-shared-owners for bot accounts: "%s"',
                path,
                i,
                owner,
            )

        m = _INCLUDE_RE.match(lstrip)
        if m:
            if m.group("repo") in ("chromiumos/owners", "chromeos/owners"):
                if m.group("branch") != _SHARED_OWNERS_BRANCH:
                    ret = False
                    logging.error(
                        '%s:%i: shared owners must use branch "%s", not "%s"',
                        path,
                        i,
                        _SHARED_OWNERS_BRANCH,
                        m.group("branch"),
                    )

                p = m.group("path")
                if not p.startswith("/"):
                    ret = False
                    logging.error(
                        '%s:%i: shared owners files use absolute paths: "%s"',
                        path,
                        i,
                        line,
                    )

                if p.split("/")[-1] == "OWNERS":
                    ret = False
                    logging.error(
                        "%s:%i: shared owners files may not include plain "
                        '"OWNERS": "%s"',
                        path,
                        i,
                        line,
                    )

    return ret


def lint_path(path: Union[str, os.PathLike]) -> bool:
    """Run basic checks on |path|.

    Args:
        path: The name of the file.

    Returns:
        True if everything passed.
    """
    path = Path(path)
    if path.exists():
        return lint_data(path, path.read_text(encoding="utf-8"))
    else:
        return True
