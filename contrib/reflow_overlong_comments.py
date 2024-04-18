# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Finds blocks of #-style comments that are over 80 chars and reflows them."""

import io
from pathlib import Path
import textwrap
from typing import List, Optional, Tuple

from chromite.lib import commandline


LINE_LENGTH = 80


def _write_comment(
    file_handle: io.TextIOBase, leading_whitespace: str, comment: str
) -> None:
    """Wraps, then writes `comment` out to `file_handle`.

    Args:
        file_handle: Output stream.
        leading_whitespace: Whitespace to start each line with.
        comment: The comment text to write.
    """
    line_start_str = f"{leading_whitespace}# "

    comment_lines = textwrap.wrap(
        comment,
        break_on_hyphens=False,
        break_long_words=False,
        initial_indent=line_start_str,
        subsequent_indent=line_start_str,
        width=LINE_LENGTH,
    )

    for line in comment_lines:
        print(line, file=file_handle)


def _tmp_file_for(input_file: Path) -> Path:
    """Returns a temporary output file that can be later moved to `input_file`.

    Args:
        input_file: File path that will be used for input.
    """
    return input_file.with_name(f"__temp__{input_file.name}")


def _comment_text(
    line: str, comment_start_index: Optional[int] = None
) -> Tuple[str, str]:
    """Extract #-style comment text from `line`.

    If the line does not look like a candidate for comment-wrapping, returns
    empty strings.

    Args:
        line: A line from the input file.
        comment_start_index: The indent to expect the starting '#' to appear,
            for a line to be considered as a continuation of a comment.

    Returns:
        The text portion of the line, not including indent and '#', and the
        whitespace leading up to the '#', as a Tuple.
    """
    if not line.lstrip().startswith("#"):
        return "", ""

    # Ensure indentation doesn't change mid-comment. Note this doesn't handle
    # comments that change indentation _before_ the '#'. (That's weird?).
    if comment_start_index is None:
        comment_start_index = line.index("#")
    elif line[comment_start_index] != "#":
        return "", ""

    leading_whitespace = line[:comment_start_index]
    text = line[comment_start_index + 1 :].strip()
    if text.startswith("pylint:"):
        return "", ""

    return text, leading_whitespace


def reflow_comments(input_file: io.TextIOBase, output: io.TextIOBase) -> None:
    """Detects #-style comments in `input_file`, and reflows them.

    Args:
        input_file: An open file to read from.
        output: An open file to write to.
    """
    comment = ""
    leading_whitespace = ""

    for line in input_file:
        if not comment and len(line) > LINE_LENGTH + 1:
            comment, leading_whitespace = _comment_text(line)
            if not comment:
                # Overlong line that isn't a comment.
                output.write(line)
            continue

        if not comment:
            output.write(line)
            continue

        extra, _ = _comment_text(line, len(leading_whitespace))

        if extra:
            comment = f"{comment} {extra}"
        else:
            _write_comment(output, leading_whitespace, comment)
            output.write(line)
            comment = ""

    if comment:
        _write_comment(output, leading_whitespace, comment)


def main(argv: Optional[List[str]] = None) -> Optional[int]:
    parser = commandline.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input", nargs="+", help="input files", type=commandline.ExistingFile
    )
    opts = parser.parse_args(argv)
    inputs: List[Path] = opts.input

    for input_file in inputs:
        input_file = input_file.resolve()
        temp_output_handle = io.StringIO()

        with input_file.open("r", encoding="utf-8") as input_file_handle:
            reflow_comments(input_file_handle, temp_output_handle)

        input_file.write_text(temp_output_handle.getvalue(), encoding="utf-8")
    return 0
