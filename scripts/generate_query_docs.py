# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Generate documentation for `cros query` types in Markdown."""

import functools
import io
from pathlib import Path
import typing
from typing import Any, TextIO

from chromite.format import formatters
from chromite.lib import build_query
from chromite.lib import commandline
from chromite.lib import constants


_DEFAULT_OUTPUT = constants.CHROMITE_DIR / "docs" / "cros-query-types.md"
_QUERY_TARGETS = [
    build_query.Board,
    build_query.Ebuild,
    build_query.Profile,
    build_query.Overlay,
]


def _repr_type(type_: Any) -> str:
    """Format a data type for the markdown document.

    Args:
        type_: A typing annotation.

    Returns:
        A string of how the type should be represented.
    """

    # In Python 3.8 and earlier, we have to hack around to get the type name.
    # This is made easier in Python 3.9+, where __name__ is populated correctly.
    # Once we stop supporting Python 3.8 and earlier, this can be dropped.
    def _get_type_name():
        name = getattr(type_, "__name__", None)
        if name:
            return name

        # This is hacks for Python 3.8 and earlier only.
        # pylint: disable=protected-access
        name = getattr(type_, "_name", None)
        if name:
            return name

        return type_.__origin__._name

    name = _get_type_name()
    args = typing.get_args(type_)
    if not args:
        return name

    # Python 3.8 and earlier loose track of Optional[T] and store it as
    # Union[T, NoneType].  Translate this back for consistent behavior.
    if name == "Union" and len(args) == 2 and args[1] == type(None):
        name = "Optional"

    # Optional[T] type is weird, and provides args (T, NoneType).  Strip the
    # excess NoneType.
    if name == "Optional":
        args = args[:1]

    return f"{name}[{', '.join(_repr_type(x) for x in args)}]"


def _gen_docs(output: TextIO):
    """Generate the documentation in Markdown format.

    Args:
        output: The file-like object for the documentation to be written to.
    """

    def _pr(*args, **kwargs):
        kwargs.setdefault("file", output)
        print(*args, **kwargs)

    def _doc_attr(func, call_anno="", type_anno=""):
        _pr(f"* `{func.__name__}{call_anno}`{type_anno}: {func.__doc__}")

    def _doc_prop(func):
        return_type = typing.get_type_hints(func).get("return")
        _doc_attr(func, type_anno=f" (`{_repr_type(return_type)}`)")

    _pr("<!-- This file is auto-generated!  Do not edit by hand. -->")
    _pr("<!-- To update, run chromite/scripts/generate_query_docs. -->")
    _pr()
    _pr("# `cros query` Target Types")

    for target in _QUERY_TARGETS:
        _pr()
        _pr(f"## {target.__name__}")
        _pr()
        _pr("**Attributes:**")
        _pr()

        for attr in sorted(dir(target)):
            if attr.startswith("_"):
                continue
            # tree() is considered internal to the CLI.
            if attr == "tree":
                continue
            method = getattr(target, attr)
            if not method.__doc__:
                continue
            if isinstance(method, property):
                _doc_prop(method.fget)
            elif isinstance(method, functools.cached_property):
                _doc_prop(method.func)
            else:
                hints = typing.get_type_hints(method)
                return_type = hints.pop("return")
                args = ", ".join(
                    f"{k}: {_repr_type(v)}" for k, v in hints.items()
                )
                call_anno = f"({args}) -> {_repr_type(return_type)}"
                _doc_attr(method, call_anno=call_anno)


def _parse_args(argv):
    parser = commandline.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output-file",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help="Path to write markdown",
    )
    return parser.parse_args(argv)


def main(argv):
    args = _parse_args(argv)
    buf = io.StringIO()
    _gen_docs(buf)
    contents = formatters.whitespace.Data(buf.getvalue(), path=args.output_file)
    args.output_file.write_text(contents, encoding="utf-8")
