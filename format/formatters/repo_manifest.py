# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides utility for formatting repo manifests.

There does not seem to be any good off-the-shelf XML formatters.

The format we enforce:
* 2 space indents
* All elements start on new lines
* One attribute per line for most elements
* Attributes are indented & aligned to the first one
* Attributes are kept in a consistent order
* Use <foo/> closing syntax when element has no child elements
* Space before the closing />
* No space before the closing >
* Groups of <project> nodes are sorted by checkout path
* Single space between element name and attributes
* Comments have spaces around the <!-- and --> markers
* Comments are indented to the end of the <!-- marker
* Non-whitespace text nodes are deleted

See the files in our manifest repos for living examples.
"""

import collections
import io
import os
import re
from typing import List, Optional, Union
from xml.dom import minidom


def attrsToDict(node):
    """Turn the attributes into a dict for easier management.

    The XML API is not easy to work with.
    """
    ret = collections.OrderedDict()
    for i in range(node.attributes.length):
        attr = node.attributes.item(i)
        ret[attr.name] = attr.value
    return ret


# Force ordering for some elements/attributes.
ATTR_ORDER = {
    "annotation": ("name", "value", "keep"),
    "copyfile": ("src", "dest"),
    "linkfile": ("src", "dest"),
    "project": ("path", "remote", "name", "revision", "dest-branch", "groups"),
    "remote": ("name", "alias", "fetch", "pushurl", "review", "revision"),
    "repo-hooks": ("in-project", "enabled-list"),
}


def orderAttrs(node):
    """Yields |node|'s attributes in the preferred order."""
    attrs = attrsToDict(node)
    for name in ATTR_ORDER.get(node.nodeName, ()):
        if name in attrs:
            yield (name, attrs.pop(name))
    yield from attrs.items()


def has_children(node) -> bool:
    """Determine whether |node| has any (useful) children."""
    if not node.childNodes:
        return False

    # Make sure the children aren't just whitespace text nodes.
    for child in node.childNodes:
        if child.nodeType != child.TEXT_NODE:
            return True

        # Make sure the text node is just whitespace.  Who knows!
        assert child.data.strip() == "", f"Unexpected text node: {child}"

    return False


def _sort_children(nodes: List[minidom.Node]) -> List[minidom.Node]:
    """Sort |nodes| based on attributes.

    Currently this only sorts <project> nodes.
    """

    def project_key(node):
        """Find the sort key for the project |node|."""
        attrs = attrsToDict(node)
        # Splitting out numbers allows for natural sorting of versioned paths.
        parts = re.split(r"([0-9]+)", attrs.get("path", attrs["name"]).lower())
        for i, part in enumerate(parts):
            try:
                parts[i] = int(part)
            except ValueError:
                pass
        return parts

    def flush(*args):
        """Sort the current block of nodes and yield them to the caller."""
        # The nodes might contain more than just projects.  Sorting all the
        # nodes is tricky as we don't know how to compare <project> to
        # whitespace text nodes such that they stay in the right order.
        # Instead, we'll extract all the project nodes and sort them.  If things
        # were sorted, then we yield the block as-is.  If things weren't sorted,
        # we'll weave the existing block together with the sorted block by
        # yielding the next sorted project.  This can lead to slightly
        # undesirable behavior when a comment node is for a specific project,
        # but we leave it to the developer to fix that.  Fixing this in the code
        # is possible, but would require a bit more logic, so we won't bother
        # for now since it should be pretty rare.
        #
        # For example, <comment><proj b><proj a> will be sorted as
        # <comment><proj a><proj b> instead of <proj a><comment><proj b>.
        project_nodes = [x for x in pending_nodes if x.nodeName == "project"]
        sorted_project_nodes = sorted(project_nodes, key=project_key)
        if project_nodes != sorted_project_nodes:
            while pending_nodes:
                node = pending_nodes.pop(0)
                if node.nodeName == "project":
                    yield sorted_project_nodes.pop(0)
                else:
                    yield node
        else:
            yield from pending_nodes
        yield from args
        pending_nodes.clear()

    # Walk the nodes and gather them as groups.  Blank lines and non-project
    # nodes mark the end of a group of nodes.
    pending_nodes = []
    for node in nodes:
        if node.nodeType == node.COMMENT_NODE:
            pending_nodes.append(node)
        elif node.nodeType == node.TEXT_NODE:
            # Allow blank lines to reset sorting.
            if node.data.strip(" ") != "\n":
                yield from flush(node)
            else:
                pending_nodes.append(node)
        elif node.nodeName != "project":
            yield from flush(node)
        else:
            pending_nodes.append(node)

    yield from flush()


def Data(
    data: str,
    # pylint: disable=unused-argument
    path: Optional[Union[str, os.PathLike]] = None,
) -> str:
    """Format |data|.

    Args:
        data: The file content to lint.
        path: The file name for diagnostics/configs/etc...

    Returns:
        Formatted data.
    """
    ONE_LINE_NODES = {"annotation", "copyfile", "linkfile"}

    def _format(buffer: io.StringIO, root: minidom.Node, level: int = 0):
        """Recursively format the nodes starting at |root|."""
        indent = "  " * level

        for node in _sort_children(root.childNodes):
            if node.nodeType == node.COMMENT_NODE:
                # Reformat comment nodes.
                # If the --> was on a line by itself, pull it up.
                comment = node.data.strip()
                lines = [x.strip() for x in comment.splitlines()]
                # If it's a one-liner, leave it as-is.
                if len(lines) == 1:
                    comment = lines[0]
                elif lines:
                    # Indent lines that have content.
                    comment = f"{lines.pop(0)}\n" + "\n".join(
                        f"{indent}     {x}" if x else "" for x in lines
                    )
                buffer.write(f"{indent}<!-- {comment} -->")

                # For some reason the minidom implementation doesn't generate
                # text nodes in the top level, so comments all get compacted
                # into a single line. Fake it by inserting our own text node
                # newline.
                # https://bugs.python.org/issue42341
                if not level:
                    buffer.write("\n")
            elif node.nodeType == node.TEXT_NODE:
                # These are inter-node whitespace (indentation) and newlines.
                # We will handle reformatting of indentation below, but we want
                # to preserve any existing newlines as we largely don't enforce
                # anything with them atm.
                output = node.data.strip(" ")
                # We don't allow multiple blank lines in a row.
                output = re.sub(r"\n\n\n+", "\n\n", output)
                # Finally, strip non-whitespace characters.  There never should
                # be any.
                buffer.write(re.sub(r"[^\s]+", "", output))
            else:
                # We don't expect any other node type in manifests currently.
                assert node.nodeType == node.ELEMENT_NODE, str(node)

                # Reformat normal nodes, their attributes, and their children.
                node_start = f"{indent}<{node.nodeName}"
                buffer.write(node_start)

                attr_indent = " " * len(node_start)
                if node.attributes:
                    # Indent all the attributes.
                    first = True
                    for name, value in orderAttrs(node):
                        if not first and node.nodeName not in ONE_LINE_NODES:
                            buffer.write("\n" + attr_indent)
                        first = False
                        # No attributes currently need leading/trailing
                        # whitespace.
                        value = value.strip()
                        # No attributes currently use embedded whitespace.  This
                        # might change, but enforce it for now until someone
                        # complains.
                        value = re.sub(r"\s+", "", value)
                        buffer.write(f' {name}="{value}"')

                # Close the tag.
                if not has_children(node):
                    if node.attributes:
                        buffer.write(" ")
                    buffer.write("/>")
                else:
                    buffer.write(">")

                # Yield any children.
                _format(buffer, node, level + 1)

                # Close the element if we haven't yet.
                if has_children(node):
                    buffer.write(f"{indent}</{node.nodeName}>")

    manifest = minidom.parseString(data)
    buffer = io.StringIO()
    buffer.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    _format(buffer, manifest)
    buffer.write("\n")
    return buffer.getvalue()
