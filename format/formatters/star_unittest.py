# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the star module."""

import pytest

from chromite.format.formatters import star


@pytest.mark.parametrize(
    # exp=None means input is already formatted to avoid having to repeat.
    "data,exp",
    (
        ("", None),
        ('workspace(name = "foo")\n', None),
        ('workspace(name="foo")\n', 'workspace(name = "foo")\n'),
    ),
)
def test_check_format(data, exp):
    """Verify inputs match expected outputs."""
    if exp is None:
        exp = data
    assert exp == star.Data(data)


SPECIALIZATION_INPUT = """cc_library(deps=["z","x","y"],name="a123")"""
UNSPECIALIZED_OUTPUT = """cc_library(deps = ["z", "x", "y"], name = "a123")
"""
SPECIALIZED_OUTPUT = """cc_library(
    name = "a123",
    deps = [
        "x",
        "y",
        "z",
    ],
)
"""


@pytest.mark.parametrize(
    "path,exp",
    (
        ("config.star", UNSPECIALIZED_OUTPUT),
        ("BUILD", SPECIALIZED_OUTPUT),
        ("BUILD.bazel", SPECIALIZED_OUTPUT),
        ("WORKSPACE", SPECIALIZED_OUTPUT),
        ("WORKSPACE.bazel", SPECIALIZED_OUTPUT),
        ("defs.bzl", UNSPECIALIZED_OUTPUT),
    ),
)
def test_path_specialization(path, exp):
    assert star.Data(SPECIALIZATION_INPUT, path) == exp
