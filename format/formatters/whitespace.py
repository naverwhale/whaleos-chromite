# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides utility for formatting whitespace."""

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
    # Remove all leading/trailing newlines.
    data = data.strip()

    # Remove trailing whitespace on all lines.
    data = "\n".join(x.rstrip() for x in data.splitlines())

    # Add a final newline.
    if data:
        data += "\n"

    return data
