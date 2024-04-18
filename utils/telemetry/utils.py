# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides utility classes and functions."""

import getpass
import re
from typing import Optional, Pattern, Sequence, Tuple


class Anonymizer:
    """Redact the personally identifiable information."""

    def __init__(
        self, replacements: Optional[Sequence[Tuple[Pattern[str], str]]] = None
    ):
        self._replacements = replacements or []
        self._replacements.append((re.escape(getpass.getuser()), "<user>"))

    def apply(self, data: str) -> str:
        """Applies the replacement rules to data text."""
        if not data:
            return data

        for repl_from, repl_to in self._replacements:
            data, _ = re.subn(repl_from, repl_to, data)

        return data
