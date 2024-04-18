#!/usr/bin/env python3
# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Detect indentation in a file indented with spaces.

The heuristic is to use the most common difference
in the number of leading spaces between consecutive lines.
"""

import argparse
import sys
from typing import Dict, List, Optional


def diff_histogram(text: str) -> Dict[int, int]:
    """Split the input text into lines and calculate indentation freqeuency.

    The result is a dictionary from indentation length (in spaces)
    to number of occurencess in the input.
    """
    histogram = {}
    prev_indent = None
    for line in text.splitlines():
        if not line:
            continue
        indent = len(line) - len(line.lstrip(" "))
        if prev_indent is not None:
            diff = indent - prev_indent
            # Consider only the line pairs which increase indentation.
            if diff > 0:
                if diff in histogram:
                    histogram[diff] += 1
                else:
                    histogram[diff] = 1
        prev_indent = indent
    return histogram


def detect_indentation(text: str) -> Optional[int]:
    """Detect indentation in the input text."""
    hist = diff_histogram(text)

    selected = None
    maxFreq = None
    for diff, freq in hist.items():
        if maxFreq is None or freq > maxFreq:
            selected = diff

    return selected


def main(argv: Optional[List[str]] = None) -> Optional[int]:
    """main function for manual testing"""
    parser = argparse.ArgumentParser(
        description="Read stdin and detect indentation."
    )
    # Verify no arguments are passed to the script.
    parser.parse_args(argv)
    text = sys.stdin.read()
    print(detect_indentation(text))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
