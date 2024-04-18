# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provide a namespace for our helpers."""

from chromite.utils import lazy_loader


# TODO(build): Switch to module __getattr__ when we're Python 3.7+.
# https://peps.python.org/pep-0562/
locals().update(
    (x, lazy_loader.ForFunctions(f"chromite.format.formatters.{x}"))
    for x in (
        "cpp",
        "gn",
        "go",
        "json",
        "portage_layout_conf",
        "proto",
        "python",
        "repo_manifest",
        "rust",
        "star",
        "textproto",
        "whitespace",
        "xml",
    )
)


class Error(Exception):
    """General formatting error."""


class ParseError(Error):
    """Parsing error in the format input."""
