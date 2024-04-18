# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides utility for formatting JSON."""

import json
import os
from typing import Optional, Union

from chromite.format import formatters
from chromite.utils import pformat


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
    # If the file is one line, assume it should be condensed.  If it isn't,
    # assume it should be human-readable.
    try:
        obj = json.loads(data)
    except json.decoder.JSONDecodeError as e:
        raise formatters.ParseError(path) from e
    return pformat.json(obj, fp=None, compact="\n" not in data.strip())
