# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Text proto message formatter."""

import functools
import os
from typing import Optional, Union

from chromite.format import formatters
from chromite.lib import cipd
from chromite.lib import cros_build_lib


@functools.lru_cache(maxsize=None)
def _find_txtpbfmt() -> str:
    """Find or install the `txtpbfmt` tool."""
    path = cipd.InstallPackage(
        cipd.GetCIPDFromCache(),
        "infra/3pp/tools/txtpbfmt/linux-amd64",
        "ZFbTNfGMUzHt-xzwXMftKeDb0pL6ODNW4x3EYfTiw3oC",
    )
    return os.path.join(path, "txtpbfmt")


def Data(
    data: str,
    # pylint: disable=unused-argument
    path: Optional[Union[str, os.PathLike]] = None,
) -> str:
    """Format text proto message |data|.

    Args:
        data: The file content to format.
        path: The file name for diagnostics/configs/etc...

    Returns:
        Formatted data.
    """
    # txtpbfmt doesn't fully trim whitespace currently.
    data = formatters.whitespace.Data(data, path)

    result = cros_build_lib.run(
        [
            _find_txtpbfmt(),
        ],
        capture_output=True,
        input=data,
        encoding="utf-8",
    )
    return result.stdout
