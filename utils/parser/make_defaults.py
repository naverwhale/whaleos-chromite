# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A parser for make.defaults files, from portage profiles.

Note: This is just a parser for a single make.defaults file, not a full profile
evaluator.  To fully evaluate profile variables in the context of their parent
profiles, you'll want to use lib/build_query.py.
"""

import re
from typing import Dict, Iterator


# This regex is used to do lexical analysis on make.defaults files.
_lex_re = re.compile(
    r"""
    (   (?P<comment>\#[^\n]*(?:\n|$))
    |   (?P<ifs>[ \t\n]+)
    |   (?P<dqstr>"(?:\\.|[^\\"])*")
    |   (?P<qstr>'(?:\\.|[^\\'])*')
    |   (?P<word>[^ \t\n\#"']+)
    )""",
    re.VERBOSE | re.DOTALL,
)

# This regex matches a variable substitution in make.defaults (either $var or
# ${var}).
_var_re = re.compile(
    r"""
    (?<!\\)  # A backslash should not precede the dollar sign.
    \$
    (?:
        \{([^}]+)\}  # Either surrounded by braces.
    |   ([A-Za-z_]+)  # Or not.
    )""",
    re.VERBOSE,
)


def _lex(contents: str) -> Iterator[str]:
    """Do lexical analysis on a make.defaults file.

    This breaks the file contents down into a list of tokens that we can act
    upon at a higher level in parse_make_defaults.

    Args:
        contents: The file contents of a make.defaults file.

    Yields:
        Strings, each representing a "word" to be acted upon.
    """
    word = ""
    for m in _lex_re.finditer(contents):
        d = {k: v for k, v in m.groupdict().items() if v is not None}
        typename, token = d.popitem()
        if typename in ("comment", "ifs"):
            if word:
                yield word
            word = ""
        elif typename == "dqstr":
            word += token[1:-1]
        elif typename == "word":
            word += token
        elif typename == "qstr":
            word += "".join(f"\\{x}" for x in token[1:-1])
    if word:
        yield word


def parse(contents: str) -> Dict[str, str]:
    """Parse the contents of a make.defaults file.

    This parses a very limited subset of shell-like contents typically found in
    make.defaults.  See the Gentoo Package Manager Specification for the subset
    we need to support:
    https://projects.gentoo.org/pms/7/pms.html#x1-470005.2.4

    Args:
        contents: The file contents of a make.defaults file.

    Returns:
        A dictionary, mapping variable names to their values.
    """
    variables = {}

    def _var_sub_fn(m):
        var_name = m.group(1) or m.group(2)
        return variables.get(var_name, "")

    for token in _lex(contents):
        token = _var_re.sub(_var_sub_fn, token)
        token = token.replace("\\", "")
        var_name, sep, value = token.partition("=")
        if sep:
            variables[var_name] = value

    return variables
