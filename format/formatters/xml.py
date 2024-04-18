# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides utility for formatting XML files.

Not all XML files are formatted the same unfortunately.
"""

import os
from typing import Optional, Union
from xml.etree import ElementTree

from chromite.format import formatters


def Data(
    data: str,
    # pylint: disable=unused-argument
    path: Optional[Union[str, os.PathLike]] = None,
) -> str:
    """Format XML |data|.

    Args:
        data: The file content to lint.
        path: The file name for diagnostics/configs/etc...

    Returns:
        Formatted data.
    """
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as e:
        raise formatters.ParseError(path) from e
    if root.tag == "manifest":
        data = formatters.repo_manifest.Data(data)
    else:
        data = formatters.whitespace.Data(data)
    return data
