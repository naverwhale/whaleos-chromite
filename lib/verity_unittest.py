# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for verity."""

import os

from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import verity


class VerityTest(cros_test_lib.TempDirTestCase):
    """Tests verity functions."""

    def testExtractRootHexDigest(self):
        """Test the extraction of root hexdigest from dm-verity table."""
        table = os.path.join(self.tempdir, "table")
        root_hexdigest = (
            "af7d331ac908dd6e4f6771a3146310bc7edcfe8d9794abcd34512e1a7b704adc"
        )
        osutils.WriteFile(
            table,
            "0 128 verity payload=ROOT_DEV hashtree=HASH_DEV hashstart=128 "
            f"alg=sha256 root_hexdigest={root_hexdigest} "
            "salt="
            "471347ffffff2f4a1cff1224ff7b04ffff68ff19ff2dffff63ff47ffffff387c",
        )
        self.assertEqual(verity.ExtractRootHexdigest(table), root_hexdigest)

    def testExtractBadRootHexDigest(self):
        """Test the bad extraction of root hexdigest from dm-verityt table."""
        table = os.path.join(self.tempdir, "table")
        osutils.WriteFile(table, "")
        self.assertEqual(verity.ExtractRootHexdigest(table), None)
