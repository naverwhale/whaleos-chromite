# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for strip_package.py"""

import os

from chromite.lib import build_target_lib
from chromite.lib import cros_test_lib
from chromite.lib import install_mask
from chromite.scripts import strip_package


class StripPackageTest(cros_test_lib.MockTestCase):
    """Tests for strip_package."""

    def setUp(self):
        self.sysroot_path = "/build/testboard"
        self.builder_mock = self.PatchObject(
            strip_package.builder, "UpdateGmergeBinhost"
        )
        self.PatchObject(
            build_target_lib,
            "get_default_sysroot_path",
            return_value=self.sysroot_path,
        )

    def testDefaultSysroot(self):
        """Test the base case."""
        strip_package.main(["--board=testboard", "foo"])
        self.builder_mock.assert_called_with(self.sysroot_path, ["foo"], False)

    def testMultiplePkg(self):
        """Test multiple package input."""
        strip_package.main(["--board=testboard", "foo", "foo1"])
        self.builder_mock.assert_called_with(
            self.sysroot_path, ["foo", "foo1"], False
        )

    def testCustomSysroot(self):
        """Test user given custom sysroot path."""
        strip_package.main(["--sysroot=/build/sysroot", "foo"])
        self.builder_mock.assert_called_with("/build/sysroot", ["foo"], False)

    def testInstallMask(self):
        """Test install mask environment variable."""
        strip_package.main(["--board=testboard", "foo"])
        self.assertEqual(
            os.environ.get("DEFAULT_INSTALL_MASK"),
            "\n".join(install_mask.DEFAULT),
        )

    def testDeepOption(self):
        """Test Deep option."""
        strip_package.main(["--board=testboard", "--deep", "foo"])
        self.builder_mock.assert_called_with(self.sysroot_path, ["foo"], True)
