# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Run upstart-specific lint checks on the specified .conf files."""

import functools
import json
import logging
import os
from pathlib import Path
import re
from typing import Dict, Generator, List

from chromite.lint import linters


_DOC_RESOURCE_URL = (
    "https://dev.chromium.org/chromium-os/chromiumos-design-docs/"
    "boot-design/#runtime-resource-limits"
)
_AUDITED_SHELL_COMMAND_REGEX = re.compile(
    # Match comment lines so they can be excluded.
    r"(?P<comment>^\s*#.*$)|"
    # Match common command delimiters.
    r"(?:^\s*|;|&&|[|][|]|(?P<prefix>(?:[$][(]|`)+)\s*)"
    # Match command name.
    r"\b(?P<command>chown|chgrp|chmod|mkdir|ln|rm|mv|cp|touch)\s+"
    # Match command args across line splits.
    r"(?P<args>(?:\\\n|[^\n;])*)",
    re.MULTILINE,
)
_SHELL_TOKEN_SPLIT_REGEX = re.compile(r"(?:\\\n|\s)+", re.MULTILINE)
_IGNORE_LINT_REGEX = re.compile(r"#\s+croslint:\s+disable")


# TODO(python3.9): Change to functools.cache.
@functools.lru_cache(maxsize=None)
def GetIgnoreLookup() -> Dict[str, List[str]]:
    """Returns the lookup table of upstart config lines to ignore.

    On first invocation this loads the list from upstart_exceptions.json.
    Otherwise the cached copy is used.

    This is intended to be removed once the call sites are either migrated to
    tmpfiles.d or have '# croslint: disable' added.
    """
    FILE = Path(__file__).resolve()
    exceptions_path = FILE.parent / "upstart_exceptions.json"
    with exceptions_path.open("rb") as fp:
        return json.load(fp)


def ExtractCommands(text: str) -> Generator[List[str], None, None]:
    """Finds and normalizes audited commands."""
    for match in _AUDITED_SHELL_COMMAND_REGEX.finditer(text, re.S):
        # Skip comments.
        if match.group("comment"):
            continue

        cmd_prefix = match.group("prefix")
        cmd_name = match.group("command")
        cmd_args = match.group("args")

        # Skip if 'croslint: disable' is set.
        if _IGNORE_LINT_REGEX.search(cmd_args):
            continue

        if cmd_prefix:
            cmd = [_SHELL_TOKEN_SPLIT_REGEX.sub(cmd_prefix, " ") + cmd_name]
        else:
            cmd = [cmd_name]
        cmd.extend(x for x in _SHELL_TOKEN_SPLIT_REGEX.split(cmd_args) if x)
        yield cmd


def CheckForRequiredLines(
    text: str, full_path: Path, tokens_to_find=None
) -> bool:
    """Check the upstart config for required clause."""
    ret = True
    if not tokens_to_find:
        tokens_to_find = {
            "author",
            "description",
            "oom",
        }
    for line in text.splitlines():
        tokens = line.split()
        try:
            token = tokens[0]
        except IndexError:
            continue

        if tokens[0:3] == ["oom", "score", "-1000"]:
            logging.error('Use "oom score never" instead of "oom score -1000".')
            ret = False

        try:
            tokens_to_find.remove(token)
        except KeyError:
            continue

        if not tokens_to_find:
            break
    if tokens_to_find:
        logging.error(
            'Missing clauses from upstart script "%s": %s\nPlease see:\n%s',
            full_path,
            ", ".join(tokens_to_find),
            _DOC_RESOURCE_URL,
        )
        ret = False
    return ret


def Data(
    data: str,
    path: Path,
    relaxed: bool,
) -> bool:
    """Check an upstart conf file for linter errors."""
    ret = True
    if not CheckForRequiredLines(data, path) and not relaxed:
        ret = False

    label = os.path.basename(path)
    ignore_set = set(GetIgnoreLookup().get(label, [])) if relaxed else ()

    found = []
    for cmd in ExtractCommands(data):
        norm_cmd = " ".join(cmd)
        if norm_cmd not in ignore_set:
            found.append(norm_cmd)

    if found:
        logging.error('Init script "%s" has unsafe commands:', path)
        for cmd in found:
            logging.error("    %s", cmd)
        logging.error(
            "Please use a tmpfiles.d config for the commands or have "
            'them reviewed by security and add "# croslint: disable:". '
            "A security consultation bug can be filed through:\n"
            "https://b.corp.google.com/issues/new?component=1030291"
        )
        ret = False

    if not linters.whitespace.Data(data, path) and not relaxed:
        ret = False

    return ret
