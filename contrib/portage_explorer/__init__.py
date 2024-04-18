# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Init file for Portage Explorer. Calls run_portage_exporer to run spiders."""

from chromite.contrib.portage_explorer import run_portage_explorer


def execute():
    """Call and return run_portage_explorer.

    Returns:
        SpiderOutput from run_portage_explorer containing all the data collected
        from all the spiders.
    """
    return run_portage_explorer.execute()
