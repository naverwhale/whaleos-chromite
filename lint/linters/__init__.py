# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provide a namespace for our helpers."""

from chromite.utils import lazy_loader


# TODO(build): Switch to module __getattr__ when we're Python 3.7+.
# https://peps.python.org/pep-0562/
locals().update(
    (x, lazy_loader.ForFunctions(f"chromite.lint.linters.{x}"))
    for x in (
        "gnlint",
        "make_defaults",
        "owners",
        "portage_layout_conf",
        "shell",
        "upstart",
        "whitespace",
    )
)
