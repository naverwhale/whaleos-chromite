# Copyright 2018 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Chrome OS dump_image_config unittests"""

from chromite.lib import cros_test_lib
from chromite.signing.bin import dump_image_config
from chromite.signing.image_signing import imagefile


class TestMain(cros_test_lib.RunCommandTestCase):
    """Test main() function."""

    def testDumpConfig(self):
        """Test dump_config."""
        self.rc.SetDefaultCmdResult()
        dc = self.PatchObject(imagefile, "DumpConfig")
        self.assertIsNone(dump_image_config.main(["/path/to/image.bin"]))
        dc.assert_called_once_with("/path/to/image.bin")
