# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for depgraph."""

from chromite.lib import dependency_graph
from chromite.lib import depgraph


def _get_trees():
    """Get the hand-built deps trees for tests.

    Returns:
        tuple: (deps tree with bdeps,
            deps tree without bdeps,
            bdeps tree,
            sdk tree)
    """
    sysroot = "/build/target/"
    # Quick access to complete deps entries for each package.
    deps = {
        "virtual/sysroot-1": [
            {
                "action": "merge",
                "deptypes": [],
                "deps": {},
                "root": sysroot,
            }
        ],
        "virtual/sdk-1": [
            {
                "action": "merge",
                "deptypes": [],
                "deps": {},
                "root": "/",
            }
        ],
        "sysroot/both-1": [
            {
                "action": "merge",
                "deptypes": [],
                "deps": {},
                "root": "/",
            },
            {
                "action": "merge",
                "deptypes": [],
                "deps": {},
                "root": sysroot,
            },
        ],
        "sysroot/both-1-sysroot": [
            {
                "action": "merge",
                "deptypes": [],
                "deps": {},
                "root": sysroot,
            }
        ],
        "sysroot/dep-1": [
            {
                "action": "merge",
                "deptypes": [],
                "deps": {},
                "root": sysroot,
            }
        ],
        "sysroot/bdep-1": [
            {
                "action": "merge",
                "deptypes": [],
                "deps": {},
                "root": "/",
            }
        ],
        "sdk/dep-1": [
            {
                "action": "merge",
                "deptypes": [],
                "deps": {},
                "root": "/",
            }
        ],
        "sdk/bdep-1": [
            {
                "action": "merge",
                "deptypes": [],
                "deps": {},
                "root": "/",
            }
        ],
    }
    # The build target tree, deps + bdeps.
    full_dep_tree = {
        "virtual/sysroot-1": [
            {
                "action": "merge",
                "deps": {
                    "sysroot/dep-1": deps["sysroot/dep-1"],
                    "sysroot/bdep-1": deps["sysroot/bdep-1"],
                    "sysroot/both-1": deps["sysroot/both-1"],
                },
                "root": sysroot,
            }
        ],
        "sysroot/dep-1": [
            {
                "action": "merge",
                "deps": {},
                "root": sysroot,
            }
        ],
        "sysroot/bdep-1": [
            {
                "action": "merge",
                "deps": {},
                "root": "/",
            }
        ],
        "sysroot/both-1": [
            {
                "action": "merge",
                "deps": {},
                "root": "/",
            },
            {
                "action": "merge",
                "deps": {},
                "root": sysroot,
            },
        ],
    }
    # The sysroot tree, only deps.
    no_bdeps_dep_tree = {
        "virtual/sysroot-1": [
            {
                "action": "merge",
                "deps": {
                    "sysroot/dep-1": deps["sysroot/dep-1"],
                    "sysroot/both-1": deps["sysroot/both-1-sysroot"],
                },
                "root": sysroot,
            }
        ],
        "sysroot/both-1": [
            {
                "action": "merge",
                "deps": {},
                "root": sysroot,
            }
        ],
        "sysroot/dep-1": [
            {
                "action": "merge",
                "deps": {},
                "root": sysroot,
            }
        ],
    }
    # The bdeps tree for build target and sysroot trees.
    bdep_tree = {
        "sysroot/both-1": [
            {
                "action": "merge",
                "deps": {},
                "root": "/",
            }
        ],
        "sysroot/bdep-1": [
            {
                "action": "merge",
                "deps": {},
                "root": "/",
            }
        ],
    }
    # The SDK tree.
    sdk_tree = {
        "virtual/sdk-1": [
            {
                "action": "merge",
                "deps": {
                    "sdk/dep-1": deps["sdk/dep-1"],
                    "sdk/bdep-1": deps["sdk/bdep-1"],
                },
                "root": "/",
            }
        ],
        "sdk/dep-1": [
            {
                "action": "merge",
                "deps": {},
                "root": "/",
            }
        ],
        "sdk/bdep-1": [
            {
                "action": "merge",
                "deps": {},
                "root": "/",
            }
        ],
    }
    return full_dep_tree, no_bdeps_dep_tree, bdep_tree, sdk_tree


def _get_raw_sdk_depgraph(*_args, **_kwargs):
    """Build a DepgraphResult instance corresponding to the test SDK data."""
    _, _, _, sdk_tree = _get_trees()
    return depgraph.DepgraphResult(sdk_tree, {}, ["virtual/sdk-1"])


def _get_raw_sysroot_depgraph(*_args, **_kwargs):
    """Get a DepgraphResult instance corresponding to the test sysroot data."""
    _, deps_tree, bdeps_tree, _ = _get_trees()
    return depgraph.DepgraphResult(deps_tree, bdeps_tree, ["virtual/sysroot-1"])


def _get_raw_build_target_depgraph(*_args, **_kwargs):
    """Get a DepgraphResult instance corresponding to the full depgraph data."""
    deps_tree, _, bdeps_tree, _ = _get_trees()
    return depgraph.DepgraphResult(deps_tree, bdeps_tree, ["virtual/sysroot-1"])


def test_get_sdk_dependency_graph(monkeypatch):
    """Test the SDK depgraph is built correctly."""
    monkeypatch.setattr(
        depgraph, "_get_raw_sdk_depgraph", _get_raw_sdk_depgraph
    )
    graph = depgraph.get_sdk_dependency_graph()

    assert "virtual/sdk-1" in graph
    assert "sdk/dep-1" in graph
    assert "sdk/bdep-1" in graph
    assert "virtual/sysroot-1" not in graph
    assert "sysroot/both-1" not in graph
    assert "sysroot/dep-1" not in graph
    assert "sysroot/bdep-1" not in graph
    assert graph.sysroot_path == "/"


def test_get_sysroot_dependency_graph(monkeypatch):
    """Test the sysroot depgraph is built correctly."""
    monkeypatch.setattr(
        depgraph, "_get_raw_sysroot_depgraph", _get_raw_sysroot_depgraph
    )
    graph = depgraph.get_sysroot_dependency_graph("/build/target")

    assert "virtual/sysroot-1" in graph
    assert "sysroot/both-1" in graph
    assert "sysroot/dep-1" in graph
    assert "sysroot/bdep-1" not in graph
    assert "virtual/sdk-1" not in graph
    assert "sdk/dep-1" not in graph
    assert "sdk/bdep-1" not in graph
    assert graph.sysroot_path == "/build/target"
    assert not graph.sdk_root
    assert len(graph.get_nodes(["sysroot/both-1"])) == 1
    assert graph.get_nodes(
        ["sysroot/both-1"], dependency_graph.RootType.SYSROOT
    )
    assert not graph.get_nodes(
        ["sysroot/both-1"], dependency_graph.RootType.SDK
    )


def test_get_build_target_dependency_graph(monkeypatch):
    """Test the build target depgraph is built correctly."""
    monkeypatch.setattr(
        depgraph,
        "_get_raw_build_target_depgraph",
        _get_raw_build_target_depgraph,
    )
    graph = depgraph.get_build_target_dependency_graph("/build/target")

    assert "virtual/sysroot-1" in graph
    assert "sysroot/both-1" in graph
    assert "sysroot/dep-1" in graph
    assert "sysroot/bdep-1" in graph
    assert "virtual/sdk-1" not in graph
    assert "sdk/dep-1" not in graph
    assert "sdk/bdep-1" not in graph
    assert graph.sysroot_path == "/build/target"
    assert graph.sdk_root
    assert len(graph.get_nodes(["sysroot/both-1"])) == 2
    assert graph.get_nodes(
        ["sysroot/both-1"], dependency_graph.RootType.SYSROOT
    )
    assert graph.get_nodes(["sysroot/both-1"], dependency_graph.RootType.SDK)
