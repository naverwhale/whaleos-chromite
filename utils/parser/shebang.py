# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Parser for script shebangs."""

import re
from typing import NamedTuple, Optional, Union


# Extract a script's shebang.
RE = re.compile(rb"^#!\s*([^\s]+)\s*(.*)$", flags=re.M)


class Shebang(NamedTuple):
    """A shebang."""

    # The script interpreter.
    command: str

    # Arguments to the interpreter.
    args: Optional[str]

    @property
    def real_command(self) -> str:
        """Try to find the 'real' command by ignoring common wrappers."""
        if self.args and self.command in {"/bin/env", "/usr/bin/env"}:
            return self.args
        return self.command


def parse(data: Union[bytes, str]) -> Shebang:
    r"""Splits a shebang (#!) into command and arguments.

    We only support UTF-8 programs & arguments.  The OS usually doesn't have
    such restrictions, but until such a use case comes up where non-UTF-8 data
    is needed, assume it to simplify the code (strings are easier to handle).

    Args:
        data: The first line of a shebang file, for example
            "#!/usr/bin/env -uPWD python foo.py\n". The referenced command must
            be an absolute path with optionally some arguments.

    Returns:
        A Shebang with the command & arguments broken out.

    Raises:
        ValueError if the passed data is not a valid shebang line.
    """
    # We convert strings to bytes and then scan the bytes so we don't have to
    # worry about being given non-UTF-8 binary data.  If we're unable to decode
    # back into UTF-8, we'll just ignore the shebang.  There's no situation that
    # we care to support that would matter here.
    if isinstance(data, str):
        data = data.encode("utf-8")
    m = RE.match(data)
    if m:
        try:
            ret = Shebang(
                command=m.group(1).decode("utf-8"),
                args=m.group(2).strip().decode("utf-8"),
            )
        except UnicodeDecodeError:
            raise ValueError("shebang (#!) line is not valid UTF-8")

        if not ret.command.startswith("/"):
            raise ValueError("shebang (#!) program must be absolute path")

        return ret

    raise ValueError("shebang (#!) line expected")
