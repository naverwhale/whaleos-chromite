# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to download and run the CIPD client.

CIPD is the Chrome Infra Package Deployer, a simple method of resolving a
package/version into a GStorage link and installing them.
"""

import hashlib
import json
import logging
import os
from pathlib import Path
import pprint
import tempfile
from typing import Dict, Iterable, List, Optional, Union
import urllib.parse

from chromite.third_party import httplib2

from chromite.lib import cache
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.utils import memoize


# pylint: disable=line-too-long
# CIPD client to download.
#
# Preferred way to switch to another version:
#   1. Look up the version of CIPD that depot_tools is using:
#      https://crsrc.org/d/cipd_client_version
#      -> should look like "git_revision:(hex-string)".
#   2. Find it in CIPD Web UI, e.g.,
#      https://chrome-infra-packages.appspot.com/p/infra/tools/cipd/linux-amd64/+/git_revision:(hex-string)
#   3. Use the SHA256 field shown there.
# pylint: enable=line-too-long
CIPD_CLIENT_PACKAGE = "infra/tools/cipd/linux-amd64"
CIPD_CLIENT_SHA256 = (
    # This is version "git_revision:6e9be28a4c4e3a804f400dc6c2ed08b866f0a38b".
    "93cfdb346920b4bd13e55d6e981182daebec3991f4aa482154f834485a8aae94"
)

CHROME_INFRA_PACKAGES_API_BASE = (
    "https://chrome-infra-packages.appspot.com/prpc/cipd.Repository/"
)


STAGING_SERVICE_URL = "https://chrome-infra-packages-dev.appspot.com"


class Error(Exception):
    """Raised on fatal errors."""


def _ChromeInfraRequest(method, request):
    """Makes a request to the Chrome Infra Packages API with httplib2.

    Args:
        method: Name of RPC method to call.
        request: RPC request body.

    Returns:
        Deserialized RPC response body.
    """
    resp, body = httplib2.Http().request(
        uri=CHROME_INFRA_PACKAGES_API_BASE + method,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "chromite",
        },
        body=json.dumps(request),
    )
    if resp.status != 200:
        raise Error(
            "Got HTTP %d from CIPD %r: %s" % (resp.status, method, body)
        )
    try:
        return json.loads(body.lstrip(b")]}'\n"))
    except ValueError:
        raise Error("Bad response from CIPD server:\n%s" % (body,))


def _DownloadCIPD(instance_sha256):
    """Finds the CIPD download link and requests the binary.

    Args:
        instance_sha256: The version of CIPD client to download.

    Returns:
        The CIPD binary as a string.
    """
    # Grab the signed URL to fetch the client binary from.
    resp = _ChromeInfraRequest(
        "DescribeClient",
        {
            "package": CIPD_CLIENT_PACKAGE,
            "instance": {
                "hashAlgo": "SHA256",
                "hexDigest": instance_sha256,
            },
        },
    )
    if "clientBinary" not in resp:
        logging.error(
            "Error requesting the link to download CIPD from. Got:\n%s",
            pprint.pformat(resp),
        )
        raise Error("Failed to bootstrap CIPD client")

    # Download the actual binary.
    http = httplib2.Http(cache=None)
    response, binary = http.request(uri=resp["clientBinary"]["signedUrl"])
    if response.status != 200:
        raise Error("Got a %d response from Google Storage." % response.status)

    # Check SHA256 matches what server expects.
    digest = hashlib.sha256(binary).hexdigest()
    for alias in resp["clientRefAliases"]:
        if alias["hashAlgo"] == "SHA256":
            if digest != alias["hexDigest"]:
                raise Error(
                    "Unexpected CIPD client SHA256: got %s, want %s"
                    % (digest, alias["hexDigest"])
                )
            break
    else:
        raise Error("CIPD server didn't provide expected SHA256")

    return binary


class CipdCache(cache.RemoteCache):
    """Supports caching of the CIPD download."""

    def _Fetch(self, url, local_path):  # pylint: disable=arguments-differ
        instance_sha256 = urllib.parse.urlparse(url).netloc
        binary = _DownloadCIPD(instance_sha256)
        logging.info(
            "Fetched CIPD package %s:%s", CIPD_CLIENT_PACKAGE, instance_sha256
        )
        osutils.WriteFile(local_path, binary, mode="wb")
        os.chmod(local_path, 0o755)


def GetCIPDFromCache():
    """Checks the cache, downloading CIPD if it is missing.

    Returns:
        Path to the CIPD binary.
    """
    cache_dir = os.path.join(path_util.GetCacheDir(), "cipd")
    bin_cache = CipdCache(cache_dir)
    key = (CIPD_CLIENT_SHA256,)
    ref = bin_cache.Lookup(key)
    ref.SetDefault("cipd://" + CIPD_CLIENT_SHA256)
    return ref.path


def _shared_cipd_args(
    tags: Optional[Dict[str, str]] = None,
    refs: Optional[Iterable[str]] = None,
    cred_path: Optional[Union[os.PathLike, str]] = None,
    service_url: Optional[str] = None,
) -> List[Union[os.PathLike, str]]:
    """Creates a list of cipd args shared by multiple subcommands."""
    ret: List[Union[os.PathLike, str]] = []
    if tags:
        for key, value in tags.items():
            ret.extend(["-tag", f"{key}:{value}"])
    if refs:
        for ref in refs:
            ret.extend(["-ref", ref])
    if cred_path:
        ret.extend(["-service-account-json", cred_path])
    if service_url:
        ret.extend(["-service-url", service_url])
    return ret


def GetInstanceID(cipd_path, package, version, service_account_json=None):
    """Get the latest instance ID for ref latest.

    Args:
        cipd_path: Path to a cipd executable. GetCIPDFromCache can give this.
        package: A string package name.
        version: A string version of package.
        service_account_json: The path of the service account credentials.

    Returns:
        A string instance ID.
    """
    result = cros_build_lib.run(
        [cipd_path, "resolve", package, "-version", version]
        + _shared_cipd_args(cred_path=service_account_json),
        capture_output=True,
        encoding="utf-8",
    )
    # An example output of resolve is like:
    #   Packages:\n package:instance_id
    return result.stdout.splitlines()[-1].split(":")[-1]


def search_instances(
    cipd_path: Union[os.PathLike, str],
    package: str,
    tags: Dict[str, str],
    cred_path: Optional[Union[os.PathLike, str]] = None,
    service_url: Optional[str] = None,
) -> List[str]:
    """Search for instances of `package` in cipd with the given `tags`.

    Returns:
        Ths list of Instance IDs matching the search. An empty list if there is
        no match, or no package exists at the given location, or the client does
        not have permission to read that location.
    """
    cmd = [cipd_path, "search", package] + _shared_cipd_args(
        tags, [], cred_path, service_url
    )
    result = cros_build_lib.run(
        cmd, capture_output=True, encoding="utf-8", check=False
    )
    package_missing = f"""Error: prefix "{package}" doesn't exist"""
    if result.returncode == 1 and result.stderr.startswith(package_missing):
        # We never want an error to propagate simply because a prefix is being
        # used for the first time, but other errors should propagate. Also note
        # that a "package missing" error is indistinguishable from a permissions
        # issue where the client does not have read permissions on that prefix.
        return []

    result.check_returncode()

    # An example output of search is like:
    #   Instances:\n  package:instance_id1\n  package:instance_id2
    return [x.split(":")[-1] for x in result.stdout.splitlines()[1:]]


@memoize.Memoize
def InstallPackage(
    cipd_path,
    package,
    version,
    destination: Optional[Union[os.PathLike, str]] = None,
    service_account_json=None,
    print_cmd: bool = True,
):
    """Installs a package at a given destination using cipd.

    Args:
        cipd_path: Path to a cipd executable. GetCIPDFromCache can give this.
        package: A package name.
        version: The CIPD version of the package to install (can be instance ID
            or a ref).
        destination: The folder to install the package under.
        service_account_json: The path of the service account credentials.
        print_cmd: Whether to print the command before running it.

    Returns:
        The path of the package.
    """
    if not destination:
        # GetCacheDir does a non-trivial amount of work,
        # too much for a constant. If needed elsewhere, a
        # memoized function would be a good alternative.
        destination = (
            Path(path_util.GetCacheDir()).absolute() / "cipd" / "packages"
        )

    destination = Path(destination) / package

    with tempfile.NamedTemporaryFile() as f:
        f.write(("%s %s" % (package, version)).encode("utf-8"))
        f.flush()

        cros_build_lib.run(
            [cipd_path, "ensure", "-root", destination, "-list", f.name]
            + _shared_cipd_args(cred_path=service_account_json),
            capture_output=True,
            print_cmd=print_cmd,
        )

    return destination


def CreatePackage(
    cipd_path: Union[os.PathLike, str],
    package: str,
    in_dir: Union[os.PathLike, str],
    tags: Dict[str, str],
    refs: Iterable[str],
    cred_path: Optional[Union[os.PathLike, str]] = None,
    service_url: Optional[str] = None,
) -> None:
    """Create (build and register) a package using cipd.

    Args:
        cipd_path: Path to a cipd executable. GetCIPDFromCache can give this.
        package: A package name.
        in_dir: The directory to create the package from.
        tags: A mapping of tags to apply to the package.
        refs: An Iterable of refs to apply to the package.
        cred_path: The path of the service account credentials.
        service_url: If provided, overrides the default CIPD backend URL. E.g.,
            `STAGING_SERVICE_URL` will use staging.
    """
    args = [
        cipd_path,
        "create",
        "-name",
        package,
        "-in",
        in_dir,
    ] + _shared_cipd_args(tags, refs, cred_path, service_url)

    cros_build_lib.dbg_run(args)
