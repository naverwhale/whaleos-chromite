# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides utility for linting whitespace."""

import logging


def Data(data: str, path: "Path") -> bool:
    """Run basic whitespace checks on |data|.

    Args:
        data: The file content to lint.
        path: The name of the file (for diagnostics).

    Returns:
        True if everything passed.
    """
    ret = True

    # Make sure files all have a trailing newline.
    if not data.endswith("\n"):
        ret = False
        logging.warning("%s: file needs a trailing newline", path)

    # Disallow leading & trailing blank lines.
    if data.startswith("\n"):
        ret = False
        logging.warning("%s: delete leading blank lines", path)
    if data.endswith("\n\n"):
        ret = False
        logging.warning("%s: delete trailing blank lines", path)

    for i, line in enumerate(data.splitlines(), start=1):
        if line.rstrip() != line:
            ret = False
            logging.warning(
                "%s:%i: trim trailing whitespace: %s", path, i, line
            )

    return ret
