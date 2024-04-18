# Copyright 2016 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""CLI entry point into lib/vm.py; used for VM management."""

import logging

from chromite.scripts import cros


def main(argv):
    # TODO(2024-07-01): Delete this script.
    logging.notice(
        "`cros_vm` is deprecated in favor of `cros vm`, and will be removed on "
        "July 1, 2024. Please update your scripts and begin using that instead."
    )
    cros.main(["vm", *argv])
