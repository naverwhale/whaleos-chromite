# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module uprevs Chrome for cbuildbot."""

import base64
import distutils.version  # pylint: disable=import-error,no-name-in-module
import re
import urllib.parse

from chromite.lib import gob_util


def CheckIfChromeRightForOS(deps_content):
    """Checks if DEPS is right for Chrome OS.

    This function checks for a variable called 'buildspec_platforms' to
    find out if its 'chromeos' or 'all'. If any of those values,
    then it chooses that DEPS.

    Args:
        deps_content: Content of release buildspec DEPS file.

    Returns:
        True if DEPS is the right Chrome for Chrome OS.
    """
    platforms_search = re.search(r"buildspec_platforms.*\s.*\s", deps_content)

    if platforms_search:
        platforms = platforms_search.group()
        if "chromeos" in platforms or "all" in platforms:
            return True

    return False


def GetLatestRelease(git_url, branch=None):
    """Gets the latest release version from the release tags in the repository.

    Args:
        git_url: URL of git repository.
        branch: If set, gets the latest release for branch, otherwise latest
            release.

    Returns:
        Latest version string.
    """
    # TODO(szager): This only works for public release buildspecs in the
    # chromium src repository.  Internal buildspecs are tracked differently.  At
    # the time of writing, I can't find any callers that use this method to scan
    # for internal buildspecs.  But there may be something lurking...

    parsed_url = urllib.parse.urlparse(git_url)
    path = parsed_url[2].rstrip("/") + "/+refs/tags?format=JSON"
    j = gob_util.FetchUrlJson(parsed_url[1], path, ignore_404=False)
    if branch:
        chrome_version_re = re.compile(r"^%s\.\d+.*" % branch)
    else:
        chrome_version_re = re.compile(r"^[0-9]+\..*")
    matching_versions = [
        key for key in j.keys() if chrome_version_re.match(key)
    ]
    matching_versions.sort(key=distutils.version.LooseVersion)
    for chrome_version in reversed(matching_versions):
        path = parsed_url[2].rstrip() + (
            "/+/refs/tags/%s/DEPS?format=text" % chrome_version
        )
        content = gob_util.FetchUrl(parsed_url[1], path, ignore_404=False)
        if content:
            deps_content = base64.b64decode(content).decode("utf-8")
            if CheckIfChromeRightForOS(deps_content):
                return chrome_version

    return None
