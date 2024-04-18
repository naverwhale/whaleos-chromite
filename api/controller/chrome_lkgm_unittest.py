# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for ChromeLkgm operations."""

from chromite.api import api_config
from chromite.api.controller import chrome_lkgm
from chromite.api.gen.chromite.api import chrome_lkgm_pb2
from chromite.lib import chrome_lkgm as chrome_lkgm_lib
from chromite.lib import cros_test_lib


class FindLkgmTest(cros_test_lib.MockTestCase, api_config.ApiConfigMixin):
    """Unittests for FindLkgm."""

    LKGM_VERSION = "123.0.0.4566"
    FALLBACK_VERSION = "123.0.0.4562"

    def setUp(self):
        self.request = chrome_lkgm_pb2.FindLkgmRequest()
        self.request.build_target.name = "newboard"
        self.request.chrome_src = "/home/user/chromium/src"
        self.request.fallback_versions = 10
        self.response = chrome_lkgm_pb2.FindLkgmResponse()
        self.finder_mock = self.PatchObject(
            chrome_lkgm_lib, "ChromeOSVersionFinder"
        )
        self.instance = self.finder_mock.return_value
        self.instance.config_name = f"{self.request.build_target.name}/release"
        self.get_full_version_mock = self.PatchObject(
            self.instance,
            "GetFullVersionFromLatest",
            return_value=self.FALLBACK_VERSION,
        )

    def testInvalidLkgm(self):
        """LKGM version file found, but not successfully parsed."""

        self.PatchObject(chrome_lkgm_lib, "GetChromeLkgm", return_value=None)

        chrome_lkgm.FindLkgm(self.request, self.response, self.api_config)
        self.assertTrue(self.response.error)
        self.get_full_version_mock.assert_not_called()

    def testLkgmNotFound(self):
        """LKGM version file not found."""

        self.PatchObject(
            chrome_lkgm_lib,
            "GetChromeLkgm",
            side_effect=FileNotFoundError("CHROMEOS_LKGM not found"),
        )

        chrome_lkgm.FindLkgm(self.request, self.response, self.api_config)
        self.assertTrue(self.response.error)
        self.get_full_version_mock.assert_not_called()

    def testLkgmFound(self):
        """LKGM version found."""

        self.PatchObject(
            chrome_lkgm_lib, "GetChromeLkgm", return_value=self.LKGM_VERSION
        )
        self.instance.config_name = f"{self.request.build_target.name}/release"

        chrome_lkgm.FindLkgm(self.request, self.response, self.api_config)
        self.assertFalse(self.response.error)
        self.assertEqual(self.FALLBACK_VERSION, self.response.full_version)
        self.assertEqual("newboard/release", self.response.config_name)
        self.assertEqual(self.LKGM_VERSION, self.response.chromeos_lkgm)
        self.get_full_version_mock.assert_called_with(self.LKGM_VERSION)

    def testFailToGetFullVersion(self):
        """LKGM version found, but fallbacked full version wasn't found."""

        self.PatchObject(
            chrome_lkgm_lib, "GetChromeLkgm", return_value=self.LKGM_VERSION
        )
        self.PatchObject(
            self.instance, "GetFullVersionFromLatest", return_value=None
        )

        chrome_lkgm.FindLkgm(self.request, self.response, self.api_config)
        self.assertTrue(self.response.error)
