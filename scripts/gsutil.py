# Copyright 2018 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrapper around gsutil.

This takes care of downloading the pinned version we use in chromite.
"""

import logging
import signal

from chromite.lib import gs


def main(argv):
    ctx = gs.GSContext(retries=0)
    try:
        return ctx.DoCommand(
            argv, print_cmd=False, stderr=None, check=False
        ).returncode
    except KeyboardInterrupt:
        logging.debug("Aborted due to keyboard interrupt.")
        return 128 + signal.SIGINT
