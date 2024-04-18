# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides utility for formatting Rust code."""

import os
from pathlib import Path
from typing import Optional, Union

from chromite.lib import cros_build_lib


def Data(
    data: str,
    path: Optional[Union[str, os.PathLike]] = None,
) -> str:
    """Clean up Rust format problems in |data|.

    Args:
        data: The file content to lint.
        path: The file name for diagnostics/configs/etc...

    Returns:
        Formatted data.
    """
    if path is not None:
        # The path may not exist since the file can be from git history. Look up
        # for existing directory.
        path = Path(path).resolve()
        while not path.is_dir():
            path = path.parent
    result = cros_build_lib.run(
        ["rustfmt", "--edition", "2018"],
        capture_output=True,
        cwd=path,
        input=data,
        encoding="utf-8",
    )
    return result.stdout
