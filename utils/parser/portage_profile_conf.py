# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Parser for common Portage profile configs, e.g., use.mask, package.use, etc.

These files are lines with space-separated tokens, and single-line comments
starting with `#`.
"""

from typing import Iterator, List


def parse(contents: str) -> Iterator[List[str]]:
    """Parse the contents of the config.

    Args:
        contents: The contents of the config file.

    Yields:
        Lists of tokens on applicable lines.
    """
    for line in contents.splitlines():
        # Strip comments
        line, _, _ = line.partition("#")
        tokens = line.split()
        if tokens:
            yield tokens
