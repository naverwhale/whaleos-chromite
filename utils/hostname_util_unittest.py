# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for hostname_util."""

import socket
from unittest import mock

from chromite.lib import cros_test_lib
from chromite.utils import hostname_util


def test_google_host_to_be_true_for_valid_hosts(monkeypatch):
    """Test that is_google_host returns true for valid host."""

    for suffix in hostname_util.GOOGLE_HOSTNAME_SUFFIX:
        m = mock.Mock(return_value=f"something{suffix}")
        # pylint: disable=cell-var-from-loop
        monkeypatch.setattr(hostname_util, "get_host_name", m)

        assert hostname_util.is_google_host()
        m.assert_called_once_with(fully_qualified=True)


def test_google_host_to_be_false_for_invalid_hosts(monkeypatch):
    """Test that is_google_host returns true for invalid host."""
    m = mock.Mock(return_value="some.host.com")
    monkeypatch.setattr(hostname_util, "get_host_name", m)

    assert not hostname_util.is_google_host()
    m.assert_called_once_with(fully_qualified=True)


class TestGetHostname(cros_test_lib.MockTestCase):
    """Tests get_host_name & get_host_domain functionality."""

    def setUp(self):
        self.gethostname_mock = self.PatchObject(
            socket, "gethostname", return_value="m!!n"
        )
        self.gethostbyaddr_mock = self.PatchObject(
            socket,
            "gethostbyaddr",
            return_value=(
                "m!!n.google.com",
                (
                    "cow",
                    "bar",
                ),
                ("127.0.0.1.a",),
            ),
        )

    def testget_host_nameNonQualified(self):
        """Verify non-qualified behavior"""
        self.assertEqual(hostname_util.get_host_name(), "m!!n")

    def testget_host_nameFullyQualified(self):
        """Verify fully qualified behavior"""
        self.assertEqual(
            hostname_util.get_host_name(fully_qualified=True), "m!!n.google.com"
        )

    def testget_host_nameBadDns(self):
        """Do not fail when the user's dns is bad"""
        self.gethostbyaddr_mock.side_effect = socket.gaierror(
            "should be caught"
        )
        self.assertEqual(hostname_util.get_host_name(), "m!!n")

    def testget_host_domain(self):
        """Verify basic behavior"""
        self.assertEqual(hostname_util.get_host_domain(), "google.com")

    def testhost_is_ci_builder(self):
        """Test host_is_ci_builder."""
        fq_hostname_golo = "test.golo.chromium.org"
        fq_hostname_gce_1 = "test.chromeos-bot.internal"
        fq_hostname_gce_2 = "test.chrome.corp.google.com"
        fq_hostname_invalid = "test"
        self.assertTrue(hostname_util.host_is_ci_builder(fq_hostname_golo))
        self.assertTrue(hostname_util.host_is_ci_builder(fq_hostname_gce_1))
        self.assertTrue(hostname_util.host_is_ci_builder(fq_hostname_gce_2))
        self.assertFalse(hostname_util.host_is_ci_builder(fq_hostname_invalid))
        self.assertFalse(
            hostname_util.host_is_ci_builder(
                fq_hostname=fq_hostname_golo, gce_only=True
            )
        )
        self.assertFalse(
            hostname_util.host_is_ci_builder(
                fq_hostname=fq_hostname_gce_1, golo_only=True
            )
        )
