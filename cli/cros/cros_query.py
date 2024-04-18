# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The `cros query` CLI.

This is merely a lightweight wrapper around lib/build_query.py, which,
in turn, lets lib/portage_util.py do much of the heavy lifting.  Go to
those files if you want to see how the guts of the query logic works.
"""

import collections
import logging
from typing import Any, Callable

from chromite.cli import command
from chromite.lib import build_query
from chromite.lib import commandline
from chromite.lib import constants


# A minimal set of globals for -f expression evaluation.  We want to give people
# some capabilities, and we cannot stop them from accessing larger sets (eval is
# not safe), but this command line isn't used in a secure context: the input is
# from users executing code on their own machine.  So our only goal here is
# to limit the API boundary of things that you might normally do.
_GLOBALS = {
    "BAD": build_query.Stability.BAD,
    "Board": build_query.Board,
    "Ebuild": build_query.Ebuild,
    "Overlay": build_query.Overlay,
    "Profile": build_query.Profile,
    "Query": build_query.Query,
    "STABLE": build_query.Stability.STABLE,
    "UNSPECIFIED": build_query.Stability.UNSPECIFIED,
    "UNSTABLE": build_query.Stability.UNSTABLE,
    "__builtins__": {},
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
}


class ObjectMapping(collections.abc.Mapping):
    """Provides a dictionary view of any object.

    For example, given an object x and ObjectMapping y, x.attr can be
    referenced as y["attr"].
    """

    def __init__(self, obj: Any):
        self._obj = obj

    def __getitem__(self, item):
        try:
            return getattr(self._obj, item)
        except AttributeError as e:
            # The contract for __getitem__ expects a KeyError.  Translate.
            raise KeyError from e

    def __iter__(self):
        return iter(dir(self._obj))

    def __len__(self):
        return len(dir(self._obj))


def compile_filter(arg: str) -> Callable[[build_query.QueryTarget], bool]:
    """Take a command-line filter argument and compile it to a function.

    Args:
        arg: A command-line Python string.

    Returns:
        A callable which takes a QueryTarget and returns True when the
        filter accepts, and False when the filter rejects.
    """
    code = compile(arg, "<command_line>", "eval")

    def _result(query_result: build_query.QueryTarget) -> bool:
        mapping = ObjectMapping(query_result)
        try:
            # pylint: disable=eval-used
            return bool(eval(code, _GLOBALS, mapping))
        except Exception:
            logging.error(
                "Failed to evaluate expression %r on %r.", arg, query_result
            )
            raise

    return _result


def compile_formatter(arg: str) -> Callable[[build_query.QueryTarget], str]:
    """Take a command-line output format argument and compile it to a function.

    Args:
        arg: A command-line Python formatting string.

    Returns:
        A callable which takes a QueryTarget and returns a string with the
        formatted output.
    """
    f_string = f"f{arg!r}"
    code = compile(f_string, "<command_line>", "eval")

    def _result(query_result: build_query.QueryTarget) -> str:
        mapping = ObjectMapping(query_result)
        try:
            # pylint: disable=eval-used
            return eval(code, _GLOBALS, mapping)
        except Exception:
            logging.error(
                "Failed to evaluate f-string %s on %r.", f_string, query_result
            )
            raise

    return _result


def tree_result(
    result: build_query.QueryTarget,
    fmt: Callable[[build_query.QueryTarget], str],
):
    """Output a tree of the result.

    Args:
        result: An object returned from a query.
        fmt: The formatter function to use.
    """

    def _rec(item, prefix, indent):
        # If the child is not of the result type, we cannot use the
        # user-provided format string, as it's specific to the output result's
        # type.
        fmt_item = fmt if isinstance(item, type(result)) else str
        print(f"{indent[:-len(prefix)]}{prefix}{fmt_item(item)}")
        children = list(item.tree())
        if children:
            for child in children[:-1]:
                _rec(child, "├─", indent + "│ ")
            _rec(children[-1], "╰─", indent + "  ")

    _rec(result, "", "")


QUERY_TARGETS = {
    "boards": build_query.Board,
    "ebuilds": build_query.Ebuild,
    "overlays": build_query.Overlay,
    "profiles": build_query.Profile,
}


@command.command_decorator("query")
class QueryCommand(command.CliCommand):
    """Query information from the build system."""

    @classmethod
    def AddParser(cls, parser: commandline.ArgumentParser):
        """Build the parser.

        Args:
            parser: The parser.
        """
        super().AddParser(parser)

        parser.add_argument(
            "query_target",
            choices=list(QUERY_TARGETS.values()),
            metavar=f"{{{','.join(QUERY_TARGETS)}}}",
            type=QUERY_TARGETS.get,
            help="Target type to query.",
        )
        parser.add_argument(
            "-o",
            "--format",
            type=compile_formatter,
            default=str,
            help="Output format.",
        )
        parser.add_argument(
            "-f",
            "--filter",
            dest="filters",
            action="append",
            default=[],
            help="Filter outputs with expressions.",
        )

        parser.add_argument(
            "-t",
            "--tree",
            action="store_true",
            help="Provide a tree-like output format for some types.",
        )
        parser.add_argument(
            "-b",
            "--board",
            "--build-target",
            help="Limit overlays to only the overlays for this board.",
        )
        parser.add_argument(
            "--public",
            action="store_const",
            dest="overlays",
            const=constants.PUBLIC_OVERLAYS,
            default=constants.BOTH_OVERLAYS,
            help=(
                "Artificially limit overlays to only public overlays, even if "
                "running in a private checkout."
            ),
        )
        parser.epilog = """Examples:

Get a list of all boards known to the build system:
  cros query boards

Show only boards that have the "bootimage" USE flag set:
  cros query boards -f '"bootimage" in use_flags'

For each board, show the path to its top level overlay:
  cros query boards -o '{name} {top_level_overlay}'

Show the computed global USE flags for the "volteer" board:
  cros query boards -f 'name == "volteer"' -o '{use_flags}'

Show which profiles modify (set or unset) the "bootimage" USE flag:
  cros query profiles -f '"bootimage" in use_flags_set | use_flags_unset'

Show which ebuilds IUSE the "bootimage" flag:
  cros query ebuilds -f '"bootimage" in iuse'

Show all ebuilds which inherit python-r1 and have EAPI <= 6:
  cros query ebuilds -f '"python-r1" in eclasses' -f 'eapi <= 6'
"""

        return parser

    def Run(self):
        query = build_query.Query(
            self.options.query_target,
            board=self.options.board,
            overlays=self.options.overlays,
        )
        for filter_code in self.options.filters:
            query = query.filter(compile_filter(filter_code))

        for result in query:
            if self.options.tree:
                tree_result(result, self.options.format)
            else:
                print(self.options.format(result))
