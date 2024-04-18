# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Python formatter."""

import os
from pathlib import Path
from typing import Optional, Union

from chromite.format import formatters
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import git


def _find_pyproject_toml(
    path: Optional[Union[str, os.PathLike]] = None
) -> Path:
    """Locate pyproject.toml to use with |path|."""
    if path:
        project_root = git.FindGitTopLevel(path)
        for dir_path in Path(path).resolve().parents:
            config_path = dir_path / "pyproject.toml"
            try:
                if "[tool.black]" in config_path.read_text(encoding="utf-8"):
                    return config_path
            except FileNotFoundError:
                pass

            if dir_path == project_root:
                break

    return constants.CHROMITE_DIR / "pyproject.toml"


def _custom_format_data(data: str) -> str:
    """Apply some custom rules that black doesn't handle."""
    lines = data.splitlines()

    def _trim_blank_comments(i):
        """Trim blank lines & empty comment lines at the top of the file."""
        while len(lines) > i:
            if lines[i] in ("", "#"):
                lines.pop(i)
            else:
                break

    # Trim leading comment lines.
    _trim_blank_comments(0)
    if lines and lines[0].startswith("#!"):
        # Skip shebang and trim some more.
        _trim_blank_comments(1)

    # Skip license block and trim some more.
    i = None
    for i, line in enumerate(lines):
        if line and not line.startswith("#"):
            if line.startswith('"""'):
                oneliner = line.endswith('"""')

                # Clean up the content before the module docstring.
                while i and lines[i - 1] in ("", "#"):
                    i -= 1
                _trim_blank_comments(i)
                if i:
                    lines.insert(i, "")
                    i += 1

                # Move past the first line of the docstring.
                i += 1

                # Find the end of the module docstring.
                if not oneliner:
                    try:
                        i = lines.index('"""', i) + 1
                    except ValueError:
                        break
                # Clean up blank lines after the module docstring.
                if i < len(lines):
                    _trim_blank_comments(i)
                    lines.insert(i, "")

                    # If the next group is a class/func, give it room.  This
                    # isn't normally because it means the code doesn't import
                    # any modules, but defines classes & funcs, but it happens
                    # a little for our core stub modules (e.g. common Error's).
                    i += 1
                    if lines[i].startswith(("class ", "def ")):
                        lines.insert(i, "")

            break

    return "\n".join(lines) + "\n" if lines else ""


def Data(
    data: str,
    path: Optional[Union[str, os.PathLike]] = None,
) -> str:
    """Format python |data|.

    Args:
        data: The file content to lint.
        path: The file name for diagnostics/configs/etc...

    Returns:
        Formatted data.
    """
    # We run through isort first to enforce module sorting order, then run that
    # result through black. We can't run isort independently (or after black)
    # because it has some known edge cases where it formats in
    # black-incompatible ways. See b/235526476 for details.
    result = cros_build_lib.run(
        [
            constants.CHROMITE_SCRIPTS_DIR / "isort",
            "--settings-file",
            constants.CHROMITE_DIR / ".isort.cfg",
            "-",
            "-d",
        ],
        capture_output=True,
        input=data,
        encoding="utf-8",
    )

    try:
        result = cros_build_lib.run(
            [
                constants.CHROMITE_SCRIPTS_DIR / "black",
                f"--config={_find_pyproject_toml(path)}",
                f"--stdin-filename={path}",
                "-",
            ],
            input=result.stdout,
            capture_output=True,
            encoding="utf-8",
        )
    except cros_build_lib.RunCommandError as e:
        # Black will emit the entire input to stdout which is both excessively
        # noisy and useless for errors, so discard it.
        e.stdout = None
        raise formatters.ParseError(path) from e

    return _custom_format_data(result.stdout)
