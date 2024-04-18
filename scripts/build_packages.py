# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrapper to call "cros build-packages".

Eventually, this script will hard-error instead of calling "cros build-packages"
after the notice.
"""

import logging
import sys
from typing import List, Optional

from chromite.lib import cros_build_lib
from chromite.scripts import cros


def main(argv: Optional[List[str]]) -> Optional[int]:
    """Wrapper main to call "cros build-packages"."""
    argv = argv or sys.argv[1:]
    new_argv = ["build-packages", *argv]
    new_command_str = cros_build_lib.CmdToStr(["cros", *new_argv])
    logging.notice(
        "build_packages has been renamed to `cros build-packages`.  Please call"
        f" as `{new_command_str}`.  This will eventually turn into an error."
    )
    return cros.main(new_argv)
