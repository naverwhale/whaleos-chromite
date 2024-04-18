# Copyright 2016 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Send system monitoring data to the timeseries monitoring API."""

from __future__ import absolute_import

from chromite.scripts.sysmon import mainlib


if __name__ == "__main__":
    mainlib.main()
