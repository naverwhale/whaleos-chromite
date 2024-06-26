# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides matching utilities."""

import difflib
import fnmatch
import os
from typing import Any, Callable, Iterable, List


def GetMostLikelyMatchedObject(
    haystack: List[Any],
    needle: str,
    name_func: Callable[[Any], str] = lambda x: x,
    matched_score_threshold: float = 0.4,
) -> List[Any]:
    """Matches objects whose names are most likely matched with target.

    Args:
        haystack: Objects to search against.
        needle: The name to match.
        name_func: Function to get object name to match. Default is the identity
            function.
        matched_score_threshold: The threshold of likelihood to match. Must be
            in the range [0,1].

    Returns:
        A list of entities from |haystack| whose names are likely |needle|.
    """

    def _Score(obj):
        return difflib.SequenceMatcher(a=name_func(obj), b=needle).ratio()

    return sorted(o for o in haystack if _Score(o) > matched_score_threshold)


def FindFilesMatching(
    pattern: str,
    target: str = "./",
    cwd: str = os.curdir,
    exclude_dirs: Iterable[str] = (),
) -> List[str]:
    """Search the root directory recursively for matching filenames.

    The |target| and |cwd| args allow manipulating how the found paths are
    returned as well as specifying where the search needs to be executed.

    If our filesystem only has /path/to/example.txt, and our pattern is '*.txt':
    |target|='./', |cwd|='/path'    =>  ./to/example.txt
    |target|='to', |cwd|='/path'    =>  to/example.txt
    |target|='./', |cwd|='/path/to' =>  ./example.txt
    |target|='/path'                =>  /path/to/example.txt
    |target|='/path/to'             =>  /path/to/example.txt

    Args:
        pattern: the pattern used to match the filenames.
        target: the target directory to search.
        cwd: current working directory.
        exclude_dirs: Directories to not include when searching.

    Returns:
        A list of paths of the matched files.
    """
    assert cwd
    assert os.path.exists(cwd)

    # Backup the current working directory before changing it.
    old_cwd = os.getcwd()
    os.chdir(cwd)

    matches = []
    for directory, _, filenames in os.walk(target):
        if any(directory.startswith(e) for e in exclude_dirs):
            # Skip files in excluded directories.
            continue

        for filename in fnmatch.filter(filenames, pattern):
            matches.append(os.path.join(directory, filename))

    # Restore the working directory.
    os.chdir(old_cwd)

    return matches
