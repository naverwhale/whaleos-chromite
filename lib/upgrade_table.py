# Copyright 2011 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""UpgradeTable class is used in Portage package upgrade process."""


class UpgradeTable:
    """Class to represent upgrade data in memory, can be written to csv."""

    # Column names.  Note that 'ARCH' is replaced with a real arch name when
    # these are accessed as attributes off an UpgradeTable object.
    COL_PACKAGE = "Package"
    COL_SLOT = "Slot"
    COL_OVERLAY = "Overlay"
    COL_CURRENT_VER = "Current ARCH Version"
    COL_STABLE_UPSTREAM_VER = "Stable Upstream ARCH Version"
    COL_LATEST_UPSTREAM_VER = "Latest Upstream ARCH Version"
    COL_STATE = "State On ARCH"
    COL_DEPENDS_ON = "Dependencies On ARCH"
    COL_USED_BY = "Required By On ARCH"
    COL_TARGET = "Root Target"
    COL_UPGRADED = "Upgraded ARCH Version"

    # COL_STATE values should be one of the following:
    STATE_UNKNOWN = "unknown"
    STATE_LOCAL_ONLY = "local only"
    STATE_UPSTREAM_ONLY = "upstream only"
    STATE_NEEDS_UPGRADE = "needs upgrade"
    STATE_PATCHED = "patched locally"
    STATE_DUPLICATED = "duplicated locally"
    STATE_NEEDS_UPGRADE_AND_PATCHED = "needs upgrade and patched locally"
    STATE_NEEDS_UPGRADE_AND_DUPLICATED = "needs upgrade and duplicated locally"
    STATE_CURRENT = "current"
