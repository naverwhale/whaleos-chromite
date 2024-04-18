# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Path filter module to support --include, --exclude flags in commands."""

import fnmatch
import os
import re
from typing import Any, List, NamedTuple, Optional, Union


class _Rule(NamedTuple):
    """A rule for PathFilter.

    When `regex` matches, the `includes` of the rule is applied.
    """

    regex: Any
    includes: bool

    def match(self, path: Union[str, os.PathLike]) -> Optional[bool]:
        """Returns whether path should be included, None if indecisive."""
        return self.includes if self.regex.fullmatch(str(path)) else None


def exclude(pattern):
    """Returns an exclusion rule for the pattern."""
    return _Rule(re.compile(fnmatch.translate(pattern)), includes=False)


def include(pattern):
    """Returns an inclusion rule for the pattern."""
    return _Rule(re.compile(fnmatch.translate(pattern)), includes=True)


class PathFilter(NamedTuple):
    """A path pattern filter.

    - the first rule to match is used
    - any unmatched paths will default to "include"
    """

    rules: List[_Rule]

    def match(self, path: Union[str, os.PathLike]) -> bool:
        """Returns whether the given path name is included"""
        for rule in self.rules:
            result = rule.match(path)
            if result is not None:
                return result
        # If no rules matched, include by default.
        return True

    def filter(
        self, paths: List[Union[str, os.PathLike]]
    ) -> List[Union[str, os.PathLike]]:
        """Returns a subset of names that should be included"""
        return [x for x in paths if self.match(x)]
