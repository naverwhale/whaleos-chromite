# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Linter for make.defaults."""

import re
from typing import Iterable, List

from chromite.utils.parser import make_defaults


# Match compiler -march flags:
# Group 1 (^^^) = 'armv8-a', 'znver3'
#     "-march=armv8-a+crc+crypto"
#             ^^^^^^^
#     "-march=znver3"
#             ^^^^^^
_COMPILER_MARCH_RE = re.compile(r"-march=([a-zA-Z0-9-]+)")


def _check_march_flags(data: str) -> Iterable[str]:
    """Check the march flags in make.defaults.

    Ensure boards have optimized binaries by making sure the compiler's
    |-march| flag matches the USE |march_| flag. The USE flag is used by
    google3 libraries to select the correct build with the desired
    microarchitecture optimizations enabled.

    1. If the make.defaults contains |BOARD_COMPILER_FLAGS|:
      a. |BOARD_COMPILER_FLAGS| must specify |-march=|
      b. |USE| must be present and specify |march_|
      c. |-march| must equal |march_|

    Supported LLVM march flags can be queried with:
        $ llc -march=x86-64 -mcpu=help
        $ llc -march=arm64 -mcpu=help
    """
    compiler_march = ""
    use_march = ""

    vars_dict = make_defaults.parse(data)

    vars_board_compiler_flags = vars_dict.get("BOARD_COMPILER_FLAGS", "")
    if not vars_board_compiler_flags:
        # If the make.defaults doesn't have a BOARD_COMPILER_FLAGS, then
        # there is nothing left for us to check, since there's no
        # |-march=| present to check against.
        return []

    # If BOARD_COMPILER_FLAGS is present:
    # 1. BOARD_COMPILER_FLAGS must contain |-march=|
    # 2. USE must exist

    # Get the compiler |-march| flag.
    m = _COMPILER_MARCH_RE.search(vars_board_compiler_flags)
    if not m:
        return [
            "BOARD_COMPILER_FLAGS must contain valid |-march|:"
            f" BOARD_COMPILER_FLAGS = '{vars_board_compiler_flags}'"
        ]
    compiler_march = m.group(1)

    # Get the USE |march_| flag.
    vars_use = vars_dict.get("USE", "")
    if not vars_use:
        return ["must contain USE"]
    use_flags = set(vars_use.split())
    # Verify they match.
    use_march = f"march_{compiler_march}"
    if use_march not in use_flags:
        bad_use_march = [
            x
            for x in use_flags
            if x.startswith("march_") or x.startswith("-march_")
        ]
        if bad_use_march:
            return [
                f"BOARD_COMPILER_FLAGS |-march| ('{compiler_march}')"
                f" must match USE |march_| ({bad_use_march})"
            ]
        else:
            matching_use_march = "march_" + compiler_march
            return [
                f"BOARD_COMPILER_FLAGS |-march| ('{compiler_march}'),"
                f" USE must contain matching |march_| ('{matching_use_march}')"
            ]

    # No errors.
    return []


def Data(data: str) -> List[str]:
    """Lint make.defaults in |data|.

    Args:
        data: The file content to process.
        path: The file name for diagnostics/configs/etc...

    Returns:
        Any errors found.
    """
    issues = []

    issues += _check_march_flags(data)
    return issues
