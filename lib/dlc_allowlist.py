# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""File to hold DLC allowlists for review require fields."""

import itertools
import re
from typing import Pattern, Tuple


# In order to add a DLC below, please reach out to:
# chromeos-core-services@google.com

# Add DLC ID that requires factory installation.
# By default, factory installed DLCs are allowed to be powerwash safe.
DLC_FACTORY_INSTALL = (r"sample-dlc",)

# Add DLC ID that requires factory installation with regex matching.
# By default, factory installed DLCs are allowed to be powerwash safe.
DLC_FACTORY_INSTALL_RE = (r"modem-fw-dlc[-a-zA-Z0-9]+",)

# Add DLC ID that requires powerwash safety.
DLC_POWERWASH_SAFE = (r"prebuilt-test-dlc",) + DLC_FACTORY_INSTALL

# Add DLC ID that requires powerwash safety with regex matching.
DLC_POWERWASH_SAFE_RE = ()

# Do not add anything to these variables.
DLC_FACTORY_INSTALL_RE_COMPILED = tuple(
    re.compile(pat) for pat in DLC_FACTORY_INSTALL_RE
)
DLC_POWERWASH_SAFE_RE_COMPILED = tuple(
    itertools.chain(
        (re.compile(pat) for pat in DLC_POWERWASH_SAFE_RE),
        DLC_FACTORY_INSTALL_RE_COMPILED,
    )
)


def IsAllowlisted(dlc_id: str, allowlist: Tuple[str]) -> bool:
    """Checks if the DLC is allowlisted.

    Args:
        dlc_id: The DLC ID.
        allowlist: A group of allowlisted DLCs.

    Returns:
        True if DLC given is allowlisted.
    """
    return dlc_id in allowlist


def IsAllowlistedRe(dlc_id: str, allowlist_re: Tuple[Pattern]) -> bool:
    """Checks if the DLC is allowlisted with full regex match.

    Args:
        dlc_id: The DLC ID.
        allowlist_re: A group of allowlisted DLC regexes compiled.

    Returns:
        True if DLC given is allowlisted per full regex match.
    """
    return any(r.fullmatch(dlc_id) is not None for r in allowlist_re)


def IsPowerwashSafeAllowlisted(dlc_id: str) -> bool:
    """Checks if the DLC is allowed to be powerwash safe.

    Args:
        dlc_id: The DLC ID.

    Returns:
        True if DLC is allowed to be powerwash safe.
    """
    return IsAllowlisted(dlc_id, DLC_POWERWASH_SAFE) or IsAllowlistedRe(
        dlc_id, DLC_POWERWASH_SAFE_RE_COMPILED
    )


def IsFactoryInstallAllowlisted(dlc_id: str) -> bool:
    """Checks if the DLC is allowed to factory install.

    Args:
        dlc_id: The DLC ID.

    Returns:
        True if DLC is allowed to be factory installed.
    """
    return IsAllowlisted(dlc_id, DLC_FACTORY_INSTALL) or IsAllowlistedRe(
        dlc_id, DLC_FACTORY_INSTALL_RE_COMPILED
    )
