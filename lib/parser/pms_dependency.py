# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Parser for ebuild dependency specifications.

This is the foundation for parsing many conditional ebuild variables.

https://projects.gentoo.org/pms/8/pms.html#x1-730008.2
"""

from typing import Callable, List, NamedTuple, Optional


class Error(Exception):
    """Base error class for the module."""


class PmsNameError(Error):
    """A token name is invalid."""


class PmsSyntaxError(Error):
    """The syntax is invalid."""


class NestedOrUnsupportedError(Error):
    """Using ||() directly within ||() doesn't make sense."""


def _dedupe_in_order(iterable) -> List:
    """Dedupe elements while maintaining order."""
    # This uses Python dict insertion order that is guaranteed in newer
    # versions.
    return dict((x, None) for x in iterable).keys()


class Node(NamedTuple):
    """A single element."""

    name: str

    # pylint: disable=unused-argument
    def reduce(
        self,
        use_flags: Optional[set] = None,
        anyof_reduce: Optional[Callable] = None,
        flatten_allof: Optional[bool] = True,
    ) -> List[str]:
        return [self.name]

    def __str__(self):
        return self.name


class RootNode:
    """A group of nodes."""

    def __init__(self):
        self.children = []

    def reduce(
        self,
        use_flags: Optional[set] = None,
        anyof_reduce: Optional[Callable] = None,
        flatten_allof: Optional[bool] = True,
    ) -> List[str]:
        return list(
            _dedupe_in_order(
                x
                for child in self.children
                for x in child.reduce(use_flags, anyof_reduce, flatten_allof)
            )
        )

    def __str__(self):
        return " ".join(_dedupe_in_order(str(x) for x in self.children))


class AllOfNode(RootNode):
    """A group of nodes that should be kept together."""

    def reduce(
        self,
        use_flags: Optional[set] = None,
        anyof_reduce: Optional[Callable] = None,
        flatten_allof: Optional[bool] = True,
    ) -> List[str]:
        ret = super().reduce(use_flags, anyof_reduce, flatten_allof)
        if not flatten_allof:
            ret = (tuple(ret),)
        return ret

    def __str__(self):
        return f"( {super().__str__()} )"


class AnyOfNode(RootNode):
    """A group of optional/alternative nodes."""

    def reduce(
        self,
        use_flags: Optional[set] = None,
        anyof_reduce: Optional[Callable] = None,
        flatten_allof: Optional[bool] = True,
    ) -> List[str]:
        choices = super().reduce(use_flags, anyof_reduce, False)
        if anyof_reduce:
            return [anyof_reduce(choices)]

        # Just peel off the first group.  If there are any tuples (which come
        # from AllOfNodes), we need to flatten.
        def _flatten(eles):
            for e in eles:
                if isinstance(e, tuple):
                    yield from _flatten(e)
                else:
                    yield e

        return list(_flatten(choices[:1]))

    def __str__(self):
        return f"|| ( {super().__str__()} )"


class UseNode(RootNode):
    """A conditional node."""

    def __init__(self, flag: str):
        super().__init__()
        self.flag = flag

    def reduce(
        self,
        use_flags: Optional[set] = None,
        anyof_reduce: Optional[Callable] = None,
        flatten_allof: Optional[bool] = True,
    ) -> List[str]:
        if use_flags is None:
            use_flags = []

        if self.flag.startswith("!"):
            test = self.flag[1:] not in use_flags
        else:
            test = self.flag in use_flags

        return (
            super().reduce(use_flags, anyof_reduce, flatten_allof)
            if test
            else []
        )

    def __str__(self):
        return (
            f"{self.flag}? ( " + " ".join(str(x) for x in self.children) + " )"
        )


def parse(data: str, check_token: Optional[Callable] = None) -> RootNode:
    """Parse a PMS dependency specification into a structure."""
    root = RootNode()
    cur = root
    stack = [root]
    tokens = iter(data.split())
    for token in tokens:
        if token == "||":
            if cur is AnyOfNode:
                # We could support this, but it doesn't make sense in general.
                # (A || (B || C)) is simply (A || B || C).
                raise NestedOrUnsupportedError(
                    f'Redundant nested OR deps are not supported: "{data}"'
                )
            node = AnyOfNode()
            cur.children.append(node)
            stack.append(node)
            cur = node

            token = next(tokens)
            if token != "(":
                raise PmsSyntaxError(f'Expected "(": "{data}"')
        elif token == "(":
            node = AllOfNode()
            cur.children.append(node)
            stack.append(node)
            cur = node
        elif token == ")":
            stack.pop()
            if not stack:
                raise PmsSyntaxError(f'Unexpected ")": "{data}"')
            cur = stack[-1]
        elif token.endswith("?"):
            # USE flag conditional.
            node = UseNode(token[:-1])
            cur.children.append(node)
            stack.append(node)
            cur = node

            token = next(tokens)
            if token != "(":
                raise PmsSyntaxError(f'Expected "(": "{data}"')
        elif not check_token or check_token(token):
            cur.children.append(Node(token))
        else:
            raise PmsNameError(f'Invalid token name: "{token}"')

    # Make sure all '(...)' nodes finished processing.
    if len(stack) != 1:
        raise PmsSyntaxError(f'Incomplete specification: "{data}"')

    return root
