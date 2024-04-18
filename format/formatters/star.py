# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides utility for formatting Starlark files."""

import functools
import os
from typing import Optional, Union

from chromite.lib import cipd
from chromite.lib import cros_build_lib


@functools.lru_cache(maxsize=None)
def _find_buildifier() -> str:
    """Find or install the `buildifier` tool."""
    path = cipd.InstallPackage(
        cipd.GetCIPDFromCache(),
        "infra/3pp/tools/buildifier/linux-amd64",
        "version:2@6.0.1",
    )
    return os.path.join(path, "buildifier")


def Data(
    data: str,
    # pylint: disable=unused-argument
    path: Optional[Union[str, os.PathLike]] = None,
) -> str:
    """Format starlark |data|.

    Args:
        data: The file content to lint.
        path: The file name for diagnostics/configs/etc...

    Returns:
        Formatted data.
    """
    cmd = [_find_buildifier()]
    if path is not None:
        cmd.append(f"--path={path}")
    result = cros_build_lib.run(
        cmd,
        capture_output=True,
        input=data,
        encoding="utf-8",
    )
    return result.stdout
