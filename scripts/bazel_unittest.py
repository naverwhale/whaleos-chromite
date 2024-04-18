# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for bazel launcher."""

from chromite.scripts import bazel


def test_parse_known_args():
    """Test the parser will parse only known arguments."""
    script_args = ["--project", "fwsdk"]
    bazel_args = [
        "run",
        ":flash_brya",
        "--sandbox_debug",
        "--",
        "--some_arg",
        "--project",
        "ignore_this_value",
    ]
    opts, args = bazel.parse_arguments(script_args + bazel_args)
    assert opts.project == "fwsdk"
    assert args == bazel_args
