# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Print the environment allowlist."""

import sys

from chromite.lib import constants


def main(argv):
    if argv:
        sys.exit(f"{sys.argv[0]}: {__doc__}")
    print(" ".join(constants.CHROOT_ENVIRONMENT_ALLOWLIST))
