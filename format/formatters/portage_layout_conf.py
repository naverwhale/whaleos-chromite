# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides utility for formatting Portage metadata/layout.conf."""

import os
from typing import Optional, Union


def Data(
    data: str,
    # pylint: disable=unused-argument
    path: Optional[Union[str, os.PathLike]] = None,
) -> str:
    """Clean up basic whitespace problems in |data|.

    Args:
        data: The file content to lint.
        path: The file name for diagnostics/configs/etc...

    Returns:
        Formatted data.
    """

    # Normalize whitespace and trim blank lines.
    def _normalize_key_value(line: str) -> str:
        if not line.startswith("#"):
            k, v = line.split("=", 1)
            line = f"{k.strip()} = {v.strip()}".strip()
        return line

    lines = [
        _normalize_key_value(y)
        for y in (x.strip() for x in data.splitlines())
        if y
    ]

    # Make sure keys are sorted.  We don't always sort because it'll mess up
    # intermingled comments.  Hopefully people can handle this.
    curr_keys = [x for x in lines if not x.startswith("#")]
    sorted_keys = sorted(curr_keys)
    if curr_keys != sorted_keys:
        lines.sort()

    # Sort values for some keys.
    for i, line in enumerate(lines):
        elements = line.split(" = ", 1)
        if len(elements) != 2:
            continue

        key, value = elements
        if key in {"eapis-banned", "eapis-deprecated", "profile-formats"}:
            values = sorted(value.split())
            lines[i] = f"{key} = {' '.join(values)}"

    return "".join(f"{x}\n" for x in lines)
