# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the portage_layout_conf module."""

import os
from typing import List, Optional

import pytest

from chromite.lib import portage_util
from chromite.lint import linters


# pylint: disable=protected-access


@pytest.mark.parametrize(
    "data",
    (
        """
cache-format = md5-dict
masters = portage-stable chromiumos eclass-overlay mobbase
profile-formats = portage-2 profile-default-eapi
profile_eapi_when_unspecified = 5-progress
repo-name = labstation
thin-manifests = true
use-manifests = strict
""",
    ),
)
def test_good(data):
    """Verify good formats are accepted."""
    assert linters.portage_layout_conf.Data(data) == []


@pytest.mark.parametrize(
    "data,msg",
    (
        # Empty file missing a lot of stuff.
        ("", "cache-format"),
        ("", "thin-manifests"),
        ("", "use-manifests"),
        # Missing masters.
        (
            """
cache-format = md5-dict
profile-formats = portage-2 profile-default-eapi
profile_eapi_when_unspecified = 5-progress
repo-name = labstation
thin-manifests = true
use-manifests = strict
""",
            "masters",
        ),
        # Incorrect manifest value.
        (
            """
cache-format = md5-dict
profile-formats = portage-2 profile-default-eapi
profile_eapi_when_unspecified = 5-progress
repo-name = labstation
thin-manifests = true
use-manifests = true
""",
            "use-manifests",
        ),
    ),
)
def test_bad(data, msg):
    """Verify bad formats are rejected."""
    ret = linters.portage_layout_conf.Data(data)
    assert ret
    assert any(msg in x for x in ret)


def test_eapis_banned():
    """Verify eapis-banned works correctly."""

    def _get(eapis_banned: Optional[str] = None) -> List[str]:
        settings = {}
        if eapis_banned is not None:
            settings["eapis-banned"] = eapis_banned
        return list(linters.portage_layout_conf._check_eapis_banned(settings))

    # Handle missing key gracefully.
    assert not _get()

    # Handle empty key.
    assert not _get("")

    # Check valid values.
    assert not _get("0 1 2 3 4 5 6")

    # Require older versions if we use it at all.
    assert _get("5 6")

    # Reject duplicates.
    assert _get("0 1 2 3 4 5 6 6")


def test_masters(monkeypatch):
    """Verify masters works correctly."""

    def _get(
        masters: Optional[str] = None, repo_name: Optional[str] = None
    ) -> List[str]:
        settings = {}
        if masters is not None:
            settings["masters"] = masters
        if repo_name is not None:
            settings["repo-name"] = repo_name
        return list(linters.portage_layout_conf._check_masters(settings))

    # Setup overlays for public/private checks.
    repo_names = (
        "portage-stable",
        "chromiumos",
        "eclass_overlay",
        "foo",
        "foo-private",
        "only-private",
    )
    monkeypatch.setattr(
        portage_util,
        "FindOverlays",
        lambda *_args, **_kwargs: [f"/overlays/{x}" for x in repo_names],
    )
    monkeypatch.setattr(portage_util, "GetOverlayName", os.path.basename)

    # Handle missing key gracefully.
    assert _get()

    # Check valid values.
    assert not _get("portage-stable chromiumos eclass-overlay")
    assert not _get("portage-stable chromiumos eclass-overlay something else")
    assert not _get("portage-stable chromiumos eclass-overlay foo foo-private")
    assert not _get("portage-stable chromiumos eclass-overlay only-private")

    # Handle empty key.
    assert _get("")

    # Leading values is incorrect.
    assert _get("portage-stable eclass-overlay chromiumos")

    # Reject duplicates.
    assert _get("portage-stable chromiumos eclass-overlay chromiumos")
    assert _get("portage-stable chromiumos eclass-overlay a a")

    # Reject self-inclusion.
    assert _get("portage-stable chromiumos eclass-overlay foo", "foo")

    # Reject private-then-public.
    assert _get("portage-stable chromiumos eclass-overlay foo-private foo")

    # Reject private overlays listed without existing public overlay.
    assert _get("portage-stable chromiumos eclass-overlay foo-private")


def test_profile_formats():
    """Verify profile-formats works correctly."""

    def _get(profile_formats: Optional[str] = None) -> List[str]:
        settings = {}
        if profile_formats is not None:
            settings["profile-formats"] = profile_formats
        return list(
            linters.portage_layout_conf._check_profile_formats(settings)
        )

    # Handle missing key gracefully.
    assert _get()

    # Handle empty key.
    assert _get("")

    # Check valid values.
    assert not _get("portage-2 profile-default-eapi")
    assert not _get("portage-2 profile-default-eapi profile-bashrcs")

    # Check invalid values.
    assert _get("portage-2 profile-default-eapi a b c")

    # Reject duplicates.
    assert _get("portage-2 profile-default-eapi portage-2")
