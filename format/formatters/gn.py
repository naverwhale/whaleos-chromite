# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides utility for formatting GN files."""

import functools
import os
from typing import Optional, Union

from chromite.lib import cipd
from chromite.lib import cros_build_lib


@functools.lru_cache(maxsize=None)
def _find_gn() -> str:
    """Find the `gn` tool."""
    path = cipd.InstallPackage(
        cipd.GetCIPDFromCache(),
        "gn/gn/linux-amd64",
        "git_revision:41fef642de70ecdcaaa26be96d56a0398f95abd4",
    )
    return os.path.join(path, "gn")


def Data(
    data: str,
    # pylint: disable=unused-argument
    path: Optional[Union[str, os.PathLike]] = None,
) -> str:
    """Format GN |data|.

    Args:
        data: The file content to lint.
        path: The file name for diagnostics/configs/etc...

    Returns:
        Formatted data.
    """
    result = cros_build_lib.run(
        [_find_gn(), "format", "--stdin"],
        capture_output=True,
        input=data,
        encoding="utf-8",
    )
    return result.stdout
