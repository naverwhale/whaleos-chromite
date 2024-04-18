# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Shell (e.g. bash) linter."""

import functools
import os

from chromite.lib import cipd


@functools.lru_cache(maxsize=None)
def _find_shellcheck() -> str:
    """Find the `shellcheck` tool."""
    path = cipd.InstallPackage(
        cipd.GetCIPDFromCache(),
        "infra/tricium/function/shellcheck",
        "8ppDhV4xsnPdBwPwJ4ROIxRHT_J2jd8XCYY93ssqJaAC",
    )
    return os.path.join(path, "bin", "shellcheck", "shellcheck")
