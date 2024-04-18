# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for ebuild license parsing module."""

import pytest

from chromite.lib.parser import ebuild_license
from chromite.lib.parser import pms_dependency


TEST_CASES_PARSE_BASIC = (
    ("", None, []),
    ("BSD", None, ["BSD"]),
    ("BSD BSD", "BSD", ["BSD"]),
    ("BSD GPL BAR LIC", None, ["BSD", "GPL", "BAR", "LIC"]),
    (" BSD\tGPL\nBAR  ", "BSD GPL BAR", ["BSD", "GPL", "BAR"]),
)


@pytest.mark.parametrize("test,exp,reduced", TEST_CASES_PARSE_BASIC)
def test_parse_basic(test, exp, reduced):
    """Verify basic license parsing."""
    if exp is None:
        exp = test
    licenses = ebuild_license.parse(test)
    assert str(licenses) == exp
    assert licenses.reduce() == reduced


TEST_CASES_PARSE_ANY_OF = (
    ("|| ( BSD )", None, ["BSD"]),
    ("|| ( BSD BSD )", "|| ( BSD )", ["BSD"]),
    ("||\t(\nBSD\n)", "|| ( BSD )", ["BSD"]),
    ("|| ( BSD\tGPL )", "|| ( BSD GPL )", ["BSD"]),
    ("|| ( BSD GPL ) GPL-2", None, ["BSD", "GPL-2"]),
    ("BSD-1 || ( BSD GPL )", None, ["BSD-1", "BSD"]),
    ("BSD-1 || ( BSD GPL ) GPL-2", None, ["BSD-1", "BSD", "GPL-2"]),
    (
        "BSD-1 || ( BSD GPL ) || ( BSD-2 GPL-3 )",
        None,
        ["BSD-1", "BSD", "BSD-2"],
    ),
)


@pytest.mark.parametrize("test,exp,reduced", TEST_CASES_PARSE_ANY_OF)
def test_parse_any_of(test, exp, reduced):
    """Verify ||() parsing."""
    if exp is None:
        exp = test
    licenses = ebuild_license.parse(test)
    assert str(licenses) == exp
    assert licenses.reduce() == reduced


TEST_CASES_PARSE_USE = (
    ("foo? ( BSD )", None, []),
    ("foo? ( BSD )", ["foo"], ["BSD"]),
    ("BSD-1 foo? ( BSD )", None, ["BSD-1"]),
    ("foo? ( BSD ) GPL-2", None, ["GPL-2"]),
    ("foo? ( BSD ) !foo? ( BAR ) GPL-2", None, ["BAR", "GPL-2"]),
    ("foo? ( BSD flag? ( BSD-1 ) ) !foo? ( BA ) GPL-2", None, ["BA", "GPL-2"]),
    ("foo? ( flag? ( BSD ) )", ["foo"], []),
    ("foo? ( flag? ( BSD ) )", ["flag"], []),
    ("foo? ( flag? ( BSD ) )", ["foo", "flag"], ["BSD"]),
)


@pytest.mark.parametrize("test,flags,reduced", TEST_CASES_PARSE_USE)
def test_parse_use(test, flags, reduced):
    """Verify flag?() parsing."""
    licenses = ebuild_license.parse(test)
    assert str(licenses) == test
    assert licenses.reduce(use_flags=flags) == reduced


TEST_CASES_PARSE_GROUPS = (
    ("( A B )", None, ["A", "B"]),
    ("( ( A ( B ) ) )", None, ["A", "B"]),
    ("|| ( ( A ) B )", None, ["A"]),
    ("|| ( ( A B ) C )", None, ["A", "B"]),
    ("|| ( A ( B ) C )", None, ["A"]),
    ("|| ( ( ( A ) ) )", None, ["A"]),
)


@pytest.mark.parametrize("test,flags,reduced", TEST_CASES_PARSE_GROUPS)
def test_parse_groups(test, flags, reduced):
    """Verify group parsing."""
    licenses = ebuild_license.parse(test)
    assert str(licenses) == test
    assert licenses.reduce(use_flags=flags) == reduced


def test_parse_any_of_use():
    """Verify ||(flag?()) parsing."""
    test = "GPL-1 || ( foo? ( || ( BSD BSD-2 ) ) BSD-3 )"
    licenses = ebuild_license.parse(test)
    assert str(licenses) == test
    assert licenses.reduce() == ["GPL-1", "BSD-3"]
    assert licenses.reduce(use_flags=["foo"]) == ["GPL-1", "BSD"]


def test_any_of_reduce():
    """Verify ||() reduction."""
    test = "GPL-1 || ( BSD-1 foo? ( BSD-2 ) BSD-3 )"
    licenses = ebuild_license.parse(test)
    assert licenses.reduce() == ["GPL-1", "BSD-1"]

    def pick1(choices):
        return "BSD-1" if "BSD-1" in choices else choices[0]

    assert licenses.reduce(anyof_reduce=pick1) == ["GPL-1", "BSD-1"]

    def pick2(choices):
        return "BSD-2" if "BSD-2" in choices else choices[0]

    assert licenses.reduce(anyof_reduce=pick2) == ["GPL-1", "BSD-1"]
    assert licenses.reduce(use_flags=["foo"], anyof_reduce=pick2) == [
        "GPL-1",
        "BSD-2",
    ]

    def pick3(choices):
        return "BSD-3" if "BSD-3" in choices else choices[0]

    assert licenses.reduce(anyof_reduce=pick3) == ["GPL-1", "BSD-3"]


@pytest.mark.xfail(raises=pms_dependency.PmsNameError)
def test_invalid_license_name():
    """Handle invalid license names."""
    ebuild_license.parse("BSD!!!")


TEST_CASES_INVALID_SYNTAX = (
    "|| ( BSD",
    "( BSD )",
    "BSD )",
    "|| foo? ( BSD )",
)


@pytest.mark.parametrize("test", TEST_CASES_INVALID_SYNTAX)
@pytest.mark.xfail(raises=pms_dependency.PmsSyntaxError)
def test_invalid_syntax(test):
    """Handle invalid syntax."""
    ebuild_license.parse(test)
