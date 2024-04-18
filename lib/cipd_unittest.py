# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for cipd."""

import hashlib
import json
from pathlib import Path
from unittest import mock

from chromite.third_party import httplib2
import pytest

from chromite.lib import cipd
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import path_util


class CIPDTest(cros_test_lib.MockTestCase):
    """Tests for chromite.lib.cipd"""

    def testDownloadCIPD(self):
        MockHttp = self.PatchObject(httplib2, "Http")
        first_body = b")]}'\n" + json.dumps(
            {
                "clientBinary": {
                    "signedUrl": "http://example.com",
                },
                "clientRefAliases": [
                    {
                        "hashAlgo": "SKIP",
                        "hexDigest": "aaaa",
                    },
                    {
                        "hashAlgo": "SHA256",
                        "hexDigest": "bogus-sha256",
                    },
                ],
            }
        ).encode("utf-8")
        response = mock.Mock()
        response.status = 200
        MockHttp.return_value.request.side_effect = [
            (response, first_body),
            (response, b"bogus binary file"),
        ]

        sha1 = self.PatchObject(hashlib, "sha256")
        sha1.return_value.hexdigest.return_value = "bogus-sha256"

        # pylint: disable=protected-access
        self.assertEqual(
            b"bogus binary file", cipd._DownloadCIPD("bogus-instance-sha256")
        )


class CipdCacheTest(cros_test_lib.MockTempDirTestCase):
    """Tests for CipdCache helper."""

    def setUp(self):
        self.download_mock = self.PatchObject(
            cipd, "_DownloadCIPD", return_value=b"data"
        )

    def testFetch(self):
        """Check CipdCache._Fetch behavior."""
        cache = cipd.CipdCache(self.tempdir)
        ref = cache.Lookup(("1234",))
        ref.SetDefault("cipd://1234")
        self.assertEqual("data", osutils.ReadFile(ref.path))

    def testGetCIPDFromCache(self):
        """Check GetCIPDFromCache behavior."""
        self.PatchObject(path_util, "GetCacheDir", return_value=self.tempdir)
        path = cipd.GetCIPDFromCache()
        # This is more about making sure the func doesn't crash than inspecting
        # the internal caching logic (which is handled by lib.cache_unittest
        # already).
        self.assertTrue(path.startswith(str(self.tempdir)))


def test_get_instance_id(run_mock: cros_test_lib.RunCommandMock) -> None:
    """Validate the command creation and processing of GetInstanceID."""
    run_mock.SetDefaultCmdResult(
        stdout="""\
Packages:
  some/package:-V4koaHp92NryA4-caFteRpED8nsWY8z7PyZq5a7CXQC
"""
    )
    expected = ["/cipd.fake", "resolve", "some/package", "-version", "version"]
    kwargs = {"capture_output": True, "encoding": "utf-8"}

    assert (
        cipd.GetInstanceID("/cipd.fake", "some/package", "version")
        == "-V4koaHp92NryA4-caFteRpED8nsWY8z7PyZq5a7CXQC"
    )
    run_mock.assertCommandCalled(expected, **kwargs)

    cipd.GetInstanceID(
        "/cipd.fake",
        "some/package",
        "version",
        service_account_json="/creds.json",
    )
    run_mock.assertCommandCalled(
        expected + ["-service-account-json", "/creds.json"], **kwargs
    )


def test_search_instances(run_mock: cros_test_lib.RunCommandMock) -> None:
    """Validate the command creation and processing of search_instances."""
    run_mock.SetDefaultCmdResult(
        stdout="""\
Instances:
  some/package:nn9mIcZ_6_OymZEJylQtv0OlH0hhR_1BCrt4egbjiasC
  some/package:-V4koaHp92NryA4-caFteRpED8nsWY8z7PyZq5a7CXQC
"""
    )
    assert cipd.search_instances(
        "/cipd.fake", "some/package", {"tag1": "value1"}
    ) == [
        "nn9mIcZ_6_OymZEJylQtv0OlH0hhR_1BCrt4egbjiasC",
        "-V4koaHp92NryA4-caFteRpED8nsWY8z7PyZq5a7CXQC",
    ]
    run_mock.assertCommandCalled(
        ["/cipd.fake", "search", "some/package", "-tag", "tag1:value1"],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


def test_search_instances_no_matches(
    run_mock: cros_test_lib.RunCommandMock,
) -> None:
    """Validate search_instances when package exists, no instances are found."""
    run_mock.SetDefaultCmdResult(stdout="No matching instances.\n")
    assert cipd.search_instances("/cipd.fake", "some/package", {}) == []


def test_search_instances_no_prefix(
    run_mock: cros_test_lib.RunCommandMock,
) -> None:
    """Validate search_instances when no package exists (or no permission)."""
    run_mock.SetDefaultCmdResult(
        returncode=1,
        stderr="""\
Error: prefix "some/package" doesn't exist or "user:foo@bar.com" is not allowed\
 to see it, run `cipd auth-login` to login or relogin.
""",
    )
    assert cipd.search_instances("/cipd.fake", "some/package", {}) == []


def test_search_instances_other_error(
    run_mock: cros_test_lib.RunCommandMock,
) -> None:
    """Validate search_instances when an unanticipated cipd error occurs."""
    test_error = "Error: (cipd test) something bad."
    run_mock.SetDefaultCmdResult(returncode=1, stderr=test_error)
    with pytest.raises(cros_build_lib.CalledProcessError) as error_info:
        cipd.search_instances("/cipd.fake", "some/package", {})
    assert test_error in str(error_info.value)


def test_install_package(run_mock: cros_test_lib.RunCommandMock) -> None:
    """Validate the command created by InstallPackage"""
    cipd.InstallPackage(
        "/cipd.fake", "some/package", "version-ref", destination="/destination"
    )
    run_mock.assertCommandContains(
        [
            "/cipd.fake",
            "ensure",
            "-root",
            Path("/destination/some/package"),
            "-list",
            # Ignore the temporary file arg.
        ]
    )


def test_create_package(run_mock: cros_test_lib.RunCommandMock) -> None:
    """Validate the command created by CreatePackage."""
    cipd.CreatePackage(
        "/cipd.fake",
        "some/package",
        "input/bundle",
        tags={"tag1": "value1", "tag2": "value2"},
        refs=["latest"],
        cred_path="/creds.json",
        service_url=cipd.STAGING_SERVICE_URL,
    )
    run_mock.assertCommandContains(
        [
            "/cipd.fake",
            "create",
            "-name",
            "some/package",
            "-in",
            "input/bundle",
            "-tag",
            "tag1:value1",
            "-tag",
            "tag2:value2",
            "-ref",
            "latest",
            "-service-account-json",
            "/creds.json",
            "-service-url",
            "https://chrome-infra-packages-dev.appspot.com",
        ]
    )
