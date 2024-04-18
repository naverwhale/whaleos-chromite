# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Library dealing with dm-verity related content."""

import re
from typing import Optional

from chromite.lib import osutils


ROOT_HEXDIGEST_RE = re.compile(r"root_hexdigest=([A-Fa-f0-9]{64})\b")


def ExtractRootHexdigest(verity_table: str) -> Optional[str]:
    """Extract the root hexdigest from dm-verity table.

    Args:
        verity_table: Path to the dm-verity table.

    Returns:
        The str of root hexdigest, otherwise None.
    """
    m = ROOT_HEXDIGEST_RE.search(osutils.ReadFile(verity_table))
    return m.group(1) if m else None
