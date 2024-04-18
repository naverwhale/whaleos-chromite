# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Dump the graph of a board or the host SDK, including source file mapping.
"""

import logging
import sys
from typing import List

from chromite.lib import build_target_lib
from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib.dependency_graph import PackageNode
from chromite.utils import pformat


# depgraph has imports which only resolve inside the SDK, whereas we need to
# support being called from inside or outside. If invoked from outside we rerun
# ourselves inside.
if cros_build_lib.IsInsideChroot():
    from chromite.lib import depgraph


def node_to_dict(node: PackageNode) -> dict:
    pkg_info = node.pkg_info.__dict__
    deps = [p.pkg_info.__dict__ for p in node.dependencies]
    rdeps = [p.pkg_info.__dict__ for p in node.reverse_dependencies]
    src_paths = node.source_paths

    data = {
        "pkg_info": pkg_info,
        "root": node.root,
        "deps": deps,
        "rdeps": rdeps,
        "source_paths": src_paths,
    }
    return data


def parse_args(argv: List[str]):
    """Parse the arguments

    Args:
        argv: array of arguments passed to the script.
    """
    parser = commandline.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sysroot", help="Path to the sysroot.", default="/")
    group.add_argument("--board", help="Board name.")
    group.add_argument(
        "--host", action="store_true", help="Dumps the graph for the host SDK."
    )

    parser.add_argument(
        "--output",
        metavar="FILE",
        default=sys.stdout,
        help="Output to FILE. If omitted will output to stdout",
    )

    options = parser.parse_args(argv)
    options.Freeze()
    return options


def main(argv: List[str]):
    commandline.RunInsideChroot()
    opts = parse_args(argv)
    logging.notice(
        "Generating graph. Note that Chromite takes a few minutes to do this "
        "and fails completely on some boards see e.g. b/214874483."
    )
    # The --host case is handled implicitly, since it's the only way board can
    # be unset and sysroot have its default.
    sysroot = opts.sysroot
    if opts.board:
        sysroot = build_target_lib.get_default_sysroot_path(opts.board)
    graph = depgraph.get_build_target_dependency_graph(
        sysroot, with_src_paths=True
    )
    nodes = [node_to_dict(n) for n in graph]

    pformat.json(nodes, opts.output)
