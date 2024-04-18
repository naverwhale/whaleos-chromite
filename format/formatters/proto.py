# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides utility for formatting proto definitions."""

import os
from typing import Optional, Union

from chromite.lib import constants
from chromite.lib import cros_build_lib


def Data(
    data: str,
    path: Optional[Union[str, os.PathLike]] = None,
) -> str:
    """Format proto definitions |data|.

    Args:
        data: The file content to format.
        path: The file name for diagnostics/configs/etc...

    Returns:
        Formatted data.
    """
    if path is None:
        path = "format.proto"
    result = cros_build_lib.run(
        [
            constants.CHROMITE_SCRIPTS_DIR / "clang-format",
            "--style=file",
            f"--assume-filename={path}",
        ],
        capture_output=True,
        input=data,
        encoding="utf-8",
    )
    return result.stdout
