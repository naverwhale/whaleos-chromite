# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from pathlib import Path
import sys


THIS_FILE = Path(__file__).resolve()

# Hardcode Chromite's root path in the SDK to make it importable. Note THIS_FILE
# will be under site-packages in the virtual env.
sys.path.append(str(THIS_FILE.parents[8]))
