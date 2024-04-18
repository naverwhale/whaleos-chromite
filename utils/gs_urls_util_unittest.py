# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for the gs_urls_util.py module."""

from pathlib import Path

from chromite.lib import cros_test_lib
from chromite.utils import gs_urls_util


class CanonicalizeURLTest(cros_test_lib.TestCase):
    """Tests for the CanonicalizeURL function."""

    def _checkit(self, in_url, exp_url):
        self.assertEqual(gs_urls_util.CanonicalizeURL(in_url), exp_url)

    def testPublicUrl(self):
        """Test public https URLs."""
        self._checkit(
            "https://commondatastorage.googleapis.com/releases/some/file/t.gz",
            "gs://releases/some/file/t.gz",
        )

    def testPrivateUrl(self):
        """Test private https URLs."""
        self._checkit(
            "https://storage.cloud.google.com/releases/some/file/t.gz",
            "gs://releases/some/file/t.gz",
        )
        self._checkit(
            "https://pantheon.corp.google.com/storage/browser/releases/some/"
            "file/t.gz",
            "gs://releases/some/file/t.gz",
        )
        self._checkit(
            "https://stainless.corp.google.com/browse/releases/some/file/t.gz",
            "gs://releases/some/file/t.gz",
        )

    def testDuplicateBase(self):
        """Test multiple prefixes in a single URL."""
        self._checkit(
            (
                "https://storage.cloud.google.com/releases/some/"
                "https://storage.cloud.google.com/some/file/t.gz"
            ),
            (
                "gs://releases/some/"
                "https://storage.cloud.google.com/some/file/t.gz"
            ),
        )


class PathIsGsTests(cros_test_lib.TestCase):
    """Tests for the PathIsGs function."""

    def testString(self):
        """Test strings!"""
        self.assertTrue(gs_urls_util.PathIsGs("gs://foo"))
        self.assertFalse(gs_urls_util.PathIsGs("/tmp/f"))

    def testPath(self):
        """Test Path objects!"""
        self.assertFalse(gs_urls_util.PathIsGs(Path.cwd()))
        self.assertFalse(gs_urls_util.PathIsGs(Path("gs://foo")))


class GsUrlToHttpTest(cros_test_lib.TestCase):
    """Tests for the GsUrlToHttp function."""

    def setUp(self):
        self.testUrls = [
            "gs://releases",
            "gs://releases/",
            "gs://releases/path",
            "gs://releases/path/",
            "gs://releases/path/file",
        ]

    def testPublicUrls(self):
        """Test public https URLs."""
        expected = [
            "https://storage.googleapis.com/releases",
            "https://storage.googleapis.com/releases/",
            "https://storage.googleapis.com/releases/path",
            "https://storage.googleapis.com/releases/path/",
            "https://storage.googleapis.com/releases/path/file",
        ]

        for gs_url, http_url in zip(self.testUrls, expected):
            self.assertEqual(gs_urls_util.GsUrlToHttp(gs_url), http_url)
            self.assertEqual(
                gs_urls_util.GsUrlToHttp(gs_url, directory=True), http_url
            )

    def testPrivateUrls(self):
        """Test private https URLs."""
        expected = [
            "https://storage.cloud.google.com/releases",
            "https://stainless.corp.google.com/browse/releases/",
            "https://storage.cloud.google.com/releases/path",
            "https://stainless.corp.google.com/browse/releases/path/",
            "https://storage.cloud.google.com/releases/path/file",
        ]

        for gs_url, http_url in zip(self.testUrls, expected):
            self.assertEqual(
                gs_urls_util.GsUrlToHttp(gs_url, public=False), http_url
            )

    def testPrivateDirectoryUrls(self):
        """Test private https directory URLs."""
        expected = [
            "https://stainless.corp.google.com/browse/releases",
            "https://stainless.corp.google.com/browse/releases/",
            "https://stainless.corp.google.com/browse/releases/path",
            "https://stainless.corp.google.com/browse/releases/path/",
            "https://stainless.corp.google.com/browse/releases/path/file",
        ]

        for gs_url, http_url in zip(self.testUrls, expected):
            self.assertEqual(
                gs_urls_util.GsUrlToHttp(gs_url, public=False, directory=True),
                http_url,
            )
