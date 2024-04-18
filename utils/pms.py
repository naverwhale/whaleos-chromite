# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Package Manager Specification (PMS) utilities.

See: https://dev.gentoo.org/~ulm/pms/head/pms.html.

This functionality is largely meant to be the invisible backend powering more
user-friendly integration points, like the PackageInfo class
(chromite.lib.parser.package_info). Check for an existing integration point, or
perhaps where a new one could be added, before using this directly.
"""

import functools
import re


# One value, so make sure we skip all eviction logic with maxsize=None.
# TODO(python3.9): Change to functools.cache.
@functools.lru_cache(maxsize=None)
def _get_version_regex():
    """Get the compiled version regex.

    NB: Make sure to always use .fullmatch() and never .match().
    """
    return re.compile(
        r"^(?P<numbers>(\d+)((\.\d+)*))"
        r"(?P<letter>[a-z]?)"
        r"(?P<suffixes>(_(pre|p|beta|alpha|rc)\d*)*)"
        r"(-r(?P<revision>\d+))?$"
    )


def version_valid(v: str) -> bool:
    """Boolean function for checking |v| is valid."""
    return _get_version_regex().fullmatch(v) is not None


def version_ge(v1: str, v2: str) -> bool:
    """Boolean function for >= comparisons."""
    return _cmp_versions(v1, v2) in (0, 1)


def version_gt(v1: str, v2: str) -> bool:
    """Boolean function for > comparisons."""
    return _cmp_versions(v1, v2) == 1


def version_eq(v1: str, v2: str) -> bool:
    """Boolean function for > comparisons."""
    return _cmp_versions(v1, v2) == 0


def version_le(v1: str, v2: str) -> bool:
    """Boolean function for <= comparisons."""
    return _cmp_versions(v1, v2) in (-1, 0)


def version_lt(v1: str, v2: str) -> bool:
    """Boolean function for < comparisons."""
    return _cmp_versions(v1, v2) == -1


# TODO(python3.9): Change to functools.cache.
@functools.lru_cache(maxsize=None)
def _cmp_versions(v1: str, v2: str) -> int:
    """Portage version comparisons.

    See: https://dev.gentoo.org/~ulm/pms/head/pms.html#x1-260003.3

    Returns:
        int: 0 if v1==v2, 1 if v1 > v2, or -1 if v1 < v2.
    """
    if not v1 or not v2:
        raise ValueError("Version cannot be empty.")

    m1 = _get_version_regex().fullmatch(v1)
    m2 = _get_version_regex().fullmatch(v2)
    if not m1:
        raise ValueError(f"Invalid version: {v1}")
    elif not m2:
        raise ValueError(f"Invalid version: {v2}")
    elif v1 == v2:
        # Do this comparison here to first validate the version strings.
        return 0

    # Algorithm 3.1 L2: Compare number components using Algorithm 3.2.
    ncmp = _cmp_numbers(m1.group("numbers"), m2.group("numbers"))
    if ncmp:
        return ncmp

    # Algorithm 3.1 L3: Compare letter components using Algorithm 3.4.
    # Algorithm 3.4: ASCII stringwise comparison, using empty string when
    #   not present.
    lcmp = _cmp(m1.group("letter") or "", m2.group("letter") or "")
    if lcmp:
        return lcmp

    # Algorithm 3.1 L4: Compare suffixes using Algorithm 3.5.
    scmp = _cmp_suffixes(m1.group("suffixes"), m2.group("suffixes"))
    if scmp:
        return scmp

    # Algorithm 3.1 L5: Compare revisions using Algorithm 3.7.
    # Algorithm 3.7: Compare revision components as integers, using 0 when
    #   not present.
    return _cmp(int(m1.group("revision") or 0), int(m2.group("revision") or 0))


def _cmp_numbers(v1: str, v2: str):
    """Compare the number components.

    Algorithm 3.2 from https://dev.gentoo.org/~ulm/pms/head/pms.html#x1-26069r6.
    """
    if v1 == v2:
        # Short circuit the rest of the check when they're the same string.
        return 0

    v1_parts = v1.split(".")
    v2_parts = v2.split(".")

    # Algorithm 3.2 L2-6: Compare the first numbers as ints.
    cmp = _cmp(int(v1_parts[0]), int(v2_parts[0]))
    if cmp:
        return cmp

    # Algorithm 3.2 L9-10: Compare remaining parts with Algorithm 3.3.
    # Algorithm 3.3: Version comparison logic for each numeric component after
    #   the first.
    for p1, p2 in zip(v1_parts[1:], v2_parts[1:]):
        if p1.startswith("0") or p2.startswith("0"):
            # Algorithm 3.3 L1-8: Compare as strings with stripped trailing 0s
            # when either begins with 0.
            cmp = _cmp(p1.rstrip("0"), p2.rstrip("0"))
        else:
            # Algorithm 3.3 L9-15: Otherwise compare as ints.
            cmp = _cmp(int(p1 or 0), int(p2 or 0))
        if cmp:
            return cmp

    # Algorithm 3.2 L12-16: For k = min(len(X), len(Y)):
    #   X > Y if X[:k] == Y[:k] and len(X) > len(Y)
    # e.g. 1.2.3 > 1.2.
    return _cmp(len(v1_parts), len(v2_parts))


def _cmp_suffixes(s1: str, s2: str):
    """Compare version suffixes.

    Algorithm 3.5 from https://dev.gentoo.org/~ulm/pms/head/pms.html#x1-26069r6.
    """
    if s1 == s2:
        # Short circuit the rest of the work when they're identical.
        return 0

    suffix_re = r"(?P<suffix>_[a-z]+)(?P<number>\d*)"

    # Parse (suffix, suffix version) parts,
    # e.g. _alpha1_beta2 -> [('_alpha', 1), ('_beta', 2)].
    s1_parts = [
        (m.group("suffix"), int(m.group("number") or 0))
        for m in re.finditer(suffix_re, s1)
    ]
    s2_parts = [
        (m.group("suffix"), int(m.group("number") or 0))
        for m in re.finditer(suffix_re, s2)
    ]

    # Algorithm 3.6: Version comparison logic for each suffix.
    for (s1_sfx, s1_n), (s2_sfx, s2_n) in zip(s1_parts, s2_parts):
        # Algorithm 3.6 L9-13: Compare suffixes according to:
        #   _alpha < _beta < _pre < _rc < _p
        # As it happens, they're inverse ordered by length, so we just use that.
        # Invert the order in the _cmp call to get inverse length comparison,
        # i.e.:
        #   a > b == len(b) > len(a)
        # Algorithm 3.6 L1-8: When suffix is the same, do an integer comparison
        # of the numeric parts. Cast to ints and default 0 done in parsing
        # above.
        cmp = _cmp(len(s2_sfx), len(s1_sfx)) or _cmp(s1_n, s2_n)
        if cmp:
            return cmp

    if len(s1_parts) > len(s2_parts):
        # Algorithm 3.5 L7-12: if nsuffix(A) > nsuffix(B) then A < B unless
        #   A[nsuffix(B)] == _p.
        # e.g. _alpha_pre < _alpha and _alpha_p > _alpha.
        return 1 if s1_parts[len(s2_parts)][0] == "_p" else -1
    elif len(s1_parts) < len(s2_parts):
        # Algorithm 3.5 L13-18: if nsuffix(A) < nsuffix(B) then A > B unless
        #   B[nsuffix(A)] == _p.
        # Same as above but in reverse.
        return -1 if s2_parts[len(s1_parts)][0] == "_p" else 1

    # Generally shouldn't get here, but it is possible, e.g. _alpha0 == _alpha.
    return 0


def _cmp(x, y):
    """Simple compare helper function to simplify code above."""
    if x < y:
        return -1
    elif x > y:
        return 1
    else:
        return 0
