# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Linter for Portage metadata/layout.conf."""

import os
from typing import Dict, Iterable, List, Optional, Union

from chromite.lib import constants
from chromite.lib import portage_util
from chromite.utils import key_value_store


def _check_eapis_banned(settings: Dict[str, str]) -> Iterable[str]:
    """Check the 'eapis-banned' key."""
    key = "eapis-banned"

    value = settings.get("eapis-banned", "").split()
    unique = set(value)
    if len(value) != len(unique):
        yield f"'{key}' must not contain duplicate entries: {value}"

    # We aren't requiring people set this, but if they do, they have to ban
    # common versions.
    required_banned = {"0", "1", "2", "3", "4"}
    if value:
        missing = required_banned - unique
        if missing:
            yield f"'{key}' must include: {' '.join(missing)}"


def _check_masters(settings: Dict[str, str]) -> Iterable[str]:
    """Check the 'masters' key."""
    key = "masters"
    required = ["portage-stable", "chromiumos", "eclass-overlay"]

    value = settings.get(key, "").split()
    unique = set(value)
    if len(value) != len(unique):
        yield f"'{key}' must not contain duplicate entries: {value}"

    repo_name = settings.get("repo-name")
    exempt_overlays = ["amd64-host", "toolchains"] + required
    if repo_name not in exempt_overlays and value[0:3] != required:
        yield f"'{key}' must start with: '{' '.join(required)}'"

    if repo_name in unique:
        yield f"'{key}' must not contain itself: {repo_name}"

    overlays = portage_util.FindOverlays(constants.BOTH_OVERLAYS)
    for current in value:
        if current.endswith("-private"):
            # Make sure the public overlay is listed if it exists.
            public = current[: -len("-private")]
            if public in value:
                # The public overlay is already listed.
                continue

            overlay = [
                x for x in overlays if portage_util.GetOverlayName(x) == public
            ]
            if not overlay:
                # The public overlay doesn't exist.
                continue

            yield (
                f"{key}: '{current}' (private) is listed, so "
                f"'{public}' (public) must be listed too."
            )
        else:
            # Make sure private overlays are listed after their public
            # counterparts.
            private = f"{current}-private"
            if private not in value:
                continue

            public_idx = value.index(current)
            private_idx = value.index(private)
            if private_idx < public_idx:
                yield (
                    f"{key}: '{current}' (public) must be listed before "
                    f"'{private}' (private)"
                )


# All the profile-formats that portage supports.
_VALID_PROFILE_FORMATS = {
    "pms",
    "portage-1",
    "portage-2",
    "profile-bashrcs",
    "profile-set",
    "profile-default-eapi",
    "build-id",
}


def _check_profile_formats(settings: Dict[str, str]) -> Iterable[str]:
    """Check the 'profile-formats' key."""
    key = "profile-formats"
    required = {"portage-2", "profile-default-eapi"}

    value = settings.get(key, "").split()
    unique = set(value)
    if len(value) != len(unique):
        yield f"'{key}' must not contain duplicate entries: {value}"

    missing = required - unique
    if missing:
        yield f"'{key}' must contain: {' '.join(missing)}"

    banned = {"portage-1"}
    found = unique & banned
    if found:
        yield f"'{key}' must not contain: {' '.join(found)}"

    invalid = unique - _VALID_PROFILE_FORMATS
    if invalid:
        yield f"'{key}' has invalid values: {' '.join(invalid)}"


def Data(
    data: str,
    path: Optional[Union[str, os.PathLike]] = None,
) -> List[str]:
    """Lint metadata/layout.conf in |data|.

    Args:
        data: The file content to process.
        path: The file name for diagnostics/configs/etc...

    Returns:
        Any errors found.
    """
    issues = []
    settings = key_value_store.LoadData(data, source=path)

    # Require people to set specific values all the time.
    required_settings = (
        ("fast caching", "cache-format", "md5-dict"),
        ("newer eapi", "profile_eapi_when_unspecified", "5-progress"),
        ("fast manifests", "thin-manifests", "true"),
        ("file checking", "use-manifests", "strict"),
    )
    for reason, key, value in required_settings:
        if key not in settings:
            issues += [f"missing '{key} = {value}' line needed for {reason}"]
        elif settings[key] != value:
            issues += [
                f"{key} should be set to '{value}', not '{settings[key]}'"
            ]

    if "repo-name" not in settings:
        issues += ["repo-name must be set to the current project/board name"]

    issues += _check_eapis_banned(settings)
    issues += _check_masters(settings)
    issues += _check_profile_formats(settings)
    return issues
