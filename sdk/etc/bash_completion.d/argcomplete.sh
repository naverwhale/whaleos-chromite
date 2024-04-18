#!/bin/bash
# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Find and source the bash completion script for Python argcomplete
# if the script exists.
# This search is hacky. It dynamically adapts to different paths between
# Python versions. Ideally argcomplete can tell us the path directly, but
# its tools don't yet support this.
# See https://github.com/kislyuk/argcomplete/issues/364.
argcomplete_path=$(find /usr/lib*/py*/site-packages/argcomplete \
  -name python-argcomplete.sh 2>/dev/null | head -n 1)
if [[ -n "${argcomplete_path}" ]]; then
  # shellcheck source=/dev/null
  source "${argcomplete_path}"
fi
