# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Parser for ebuild LICENSE settings.

Example values we have to handle:
LICENSE="
  licA
  licB
  flag1? ( licC )
  !flag1? ( licD )
  flag2? ( flag3? ( licE ) )
  || ( licF licG )
  || (
    licH
    flag4? ( licI licJ )
  )
  ( licK licL )
"

Parsed into:
Node
  LicenseNode(licA)
  LicenseNode(licB)
  UseNode(flag1)
    LicenseNode(licC)
  UseNode(!flag1)
    LicenseNode(licD)
  UseNode(flag2)
    UseNode(flag3)
      LicenseNode(licE)
  AnyOfNode
    LicenseNode(licF)
    LicenseNode(licG)
  AnyOfNode
    LicenseNode(licH)
    UseNode(flag4)
      LicenseNode(licI)
      LicenseNode(licJ)
  AllOfNode
    LicenseNode(licK)
    LicenseNode(licL)
"""

import re

from chromite.lib.parser import pms_dependency


# https://projects.gentoo.org/pms/7/pms.html#x1-220003.1.6
VALID_NAME_RE = re.compile(r"^[A-Za-z0-9+_.-]+$")


def parse(data: str) -> pms_dependency.RootNode:
    """Parse an ebuild license string into a structure."""
    return pms_dependency.parse(data, VALID_NAME_RE.match)
