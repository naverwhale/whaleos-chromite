# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrapper around gsutil.

This takes care of downloading the pinned version we use in chromite.
"""

from chromite.lib import gs


def main(argv):
  ctx = gs.GSContext(retries=0)
  return ctx.DoCommand(
      argv, print_cmd=False, stderr=None, check=False).returncode
