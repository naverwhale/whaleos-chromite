# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for dependency_graph.py."""

import pytest

from chromite.lib import dependency_graph
from chromite.lib.parser import package_info


def _build_depgraph():
    """Build a DependencyGraph to test against."""
    sysroot = "/build/target/"
    sdk_root = "/"

    virtual = package_info.parse("virtual/target-foo-1.2.3")
    dep = package_info.parse("cat/dep-1.0.0-r1")
    depdep = package_info.parse("cat/depdep-2.0.1-r5")
    bdep = package_info.parse("cat/bdep-3.4")

    virtual_node = dependency_graph.PackageNode(
        virtual, sysroot, src_paths=["/virtual/foo"]
    )
    dep_node = dependency_graph.PackageNode(
        dep, sysroot, src_paths=["/cat/dep"]
    )
    depdep_node = dependency_graph.PackageNode(
        depdep, sysroot, src_paths=["/cat/depdep", "/other/depdep"]
    )
    bdep_node = dependency_graph.PackageNode(
        bdep, sdk_root, src_paths=["/cat/bdep"]
    )
    depbdep_node = dependency_graph.PackageNode(
        dep, sdk_root, src_paths=["/cat/dep"]
    )

    virtual_node.add_dependency(dep_node)
    virtual_node.add_dependency(bdep_node)
    virtual_node.add_dependency(depbdep_node)
    dep_node.add_dependency(depdep_node)
    depbdep_node.add_dependency(depdep_node)

    nodes = (virtual_node, dep_node, depdep_node, bdep_node, depbdep_node)

    return dependency_graph.DependencyGraph(nodes, sysroot, [virtual])


def test_dependency_graph_incorrect_sysroot():
    """Test building a graph with the wrong sysroot fails."""
    pkg = package_info.parse("foo/bar-1.0-r2")
    sdk_root = "/"
    sysroot = "/build/target"
    n1 = dependency_graph.PackageNode(pkg, sdk_root)
    n2 = dependency_graph.PackageNode(pkg, sysroot)

    with pytest.raises(dependency_graph.SysrootValueError):
        dependency_graph.DependencyGraph(
            [n1, n2], sysroot="/wrong/sysroot", root_packages=[pkg]
        )


def test_create_invalid_depgraph_too_many_roots():
    """Test building a graph with too many roots fails."""
    pkg = package_info.parse("foo/bar-1.0-r2")
    n1 = dependency_graph.PackageNode(pkg, "/")
    n2 = dependency_graph.PackageNode(pkg, "/build/target")
    n3 = dependency_graph.PackageNode(pkg, "/build/other")

    with pytest.raises(AssertionError):
        dependency_graph.DependencyGraph(
            [n1, n2, n3], sysroot="/build/target", root_packages=[pkg]
        )


def test_create_invalid_depgraph_node_conflict():
    """Test building a graph with non-equivalent nodes for one package fails."""
    pkg = package_info.parse("foo/bar-1.0-r2")
    dep = package_info.parse("foo/baz-2.0")
    sysroot = "/build/target"
    pkg_node = dependency_graph.PackageNode(pkg, sysroot)
    pkg_node2 = dependency_graph.PackageNode(pkg, sysroot)
    dep_node = dependency_graph.PackageNode(dep, sysroot)
    pkg_node.add_dependency(dep_node)

    with pytest.raises(dependency_graph.NodeCollisionError):
        dependency_graph.DependencyGraph(
            [pkg_node, dep_node, pkg_node2],
            sysroot=sysroot,
            root_packages=[pkg],
        )


def test_create_valid_depgraph_duplicate_nodes():
    """Test deduplication of nodes in depgraph creation."""
    pkg = package_info.parse("foo/bar-1.0-r2")
    dep = package_info.parse("foo/baz-2.0")
    sysroot = "/build/target"

    pkg_node = dependency_graph.PackageNode(pkg, sysroot)
    pkg_node2 = dependency_graph.PackageNode(pkg, sysroot)
    pkg_node3 = dependency_graph.PackageNode(pkg, sysroot)
    dep_node = dependency_graph.PackageNode(dep, sysroot)

    pkg_node.add_dependency(dep_node)
    pkg_node2.add_dependency(dep_node)
    pkg_node3.add_dependency(dep_node)

    assert pkg_node == pkg_node2 == pkg_node3
    assert len(list(dep_node.reverse_dependencies)) == 1

    # Add multiple instances of the same node instance, plus multiple equal
    # nodes.
    packages = (pkg_node, pkg_node, pkg_node2, pkg_node3, dep_node)
    graph = dependency_graph.DependencyGraph(
        packages, sysroot=sysroot, root_packages=[pkg]
    )
    # Should only have the nodes for the two packages at the end.
    assert len(graph) == 2


def test_dependency_graph_roots():
    """Test the roots get parsed correctly."""
    graph = _build_depgraph()

    assert graph.sdk_root == "/"
    assert graph.sysroot_path == "/build/target"


def test_dependency_graph_len():
    """Test the graph size."""
    graph = _build_depgraph()
    assert len(graph) == 5


def test_dependency_graph_in():
    """Test __contains__."""
    graph = _build_depgraph()

    virtual = package_info.parse("virtual/target-foo-1.2.3")

    # Full package info instance should be found (via cpvr).
    assert virtual in graph
    # CPVR string should be found.
    assert virtual.cpvr in graph
    # Atom string should be found.
    assert virtual.atom in graph
    # Package not in graph should not be found.
    assert "not/in-1.0" not in graph


def test_dependency_graph_iter():
    """Test __iter__ BFS traversal."""
    graph = _build_depgraph()

    virtual = package_info.parse("virtual/target-foo-1.2.3")
    dep = package_info.parse("cat/dep-1.0.0-r1")
    depdep = package_info.parse("cat/depdep-2.0.1-r5")
    bdep = package_info.parse("cat/bdep-3.4")

    # Expected Order:
    # 1. the root package (virtual/target-foo).
    # 2-4. cat/dep (sysroot), cat/dep (sdk), cat/bdep in any order.
    # 5. depdep.
    expected_order = [
        [virtual],
        [dep, bdep],
        [dep, bdep],
        [dep, bdep],
        [depdep],
    ]
    for i, node in enumerate(graph):
        assert node.pkg_info in expected_order[i]


def test_dependency_graph_get_nodes_default_values():
    """Test get_nodes retrieves the expected results with default args."""
    graph = _build_depgraph()
    assert len(graph.get_nodes()) == 5


def test_dependency_graph_get_nodes():
    """Test get_nodes retrieves the expected results."""
    graph = _build_depgraph()

    virtual = package_info.parse("virtual/target-foo-1.2.3")
    virtual_atom = package_info.parse("virtual/target-foo")

    # Test fetching by different values.
    pi_nodes = graph.get_nodes([virtual])
    cpvr_nodes = graph.get_nodes([virtual.cpvr])
    atom_nodes = graph.get_nodes([virtual.atom])
    pi_atom_nodes = graph.get_nodes([virtual_atom])
    assert pi_nodes == cpvr_nodes == atom_nodes == pi_atom_nodes


def test_dependency_graph_get_nodes_by_roots():
    """Test get_nodes correctly filters by the root types."""
    graph = _build_depgraph()

    dep = package_info.parse("cat/dep-1.0.0-r1")

    # Verify the correct counts.
    dep_all = graph.get_nodes([dep])
    dep_sysroot = graph.get_nodes([dep], dependency_graph.RootType.SYSROOT)
    dep_sdk = graph.get_nodes([dep], dependency_graph.RootType.SDK)
    assert len(dep_all) == 2
    assert len(dep_sysroot) == 1
    assert len(dep_sdk) == 1

    # Verify we got the correct nodes.
    dep_sysroot_node = dep_sysroot.pop()
    dep_sdk_node = dep_sdk.pop()
    assert dep_sysroot_node in dep_all
    assert dep_sdk_node in dep_all
    assert dep_sysroot_node.root == "/build/target"
    assert dep_sdk_node.root == "/"


def test_dependency_graph_get_nodes_multi_version_package():
    """Test handling of multiple packages with different versions."""
    virtual = package_info.parse("virtual/foo-1.0")
    pkg1 = package_info.parse("cat/pkg-1.0")
    pkg2 = package_info.parse("cat/pkg-2.0")

    sysroot = "/build/target"
    sdk = "/"

    virtual_pn = dependency_graph.PackageNode(virtual, sysroot)
    pkg1_pn = dependency_graph.PackageNode(pkg1, sysroot)
    pkg1_pn_sdk = dependency_graph.PackageNode(pkg1, sdk)
    pkg2_pn = dependency_graph.PackageNode(pkg2, sysroot)
    pkg2_pn_sdk = dependency_graph.PackageNode(pkg2, sdk)

    virtual_pn.add_dependency(pkg1_pn)
    virtual_pn.add_dependency(pkg1_pn_sdk)
    virtual_pn.add_dependency(pkg2_pn)
    virtual_pn.add_dependency(pkg2_pn_sdk)

    graph = dependency_graph.DependencyGraph(
        (virtual_pn,), sysroot, root_packages=[virtual]
    )

    # Should get both instances of cat/pkg-1.0.
    assert len(graph.get_nodes([pkg1])) == 2
    assert len(graph.get_nodes([pkg1.cpvr])) == 2
    assert all(p.pkg_info.cpvr == pkg1.cpvr for p in graph.get_nodes([pkg1]))

    # Should get both instances of cat/pkg-2.0.
    assert len(graph.get_nodes([pkg2])) == 2
    assert len(graph.get_nodes([pkg2.cpvr])) == 2
    assert all(p.pkg_info.cpvr == pkg2.cpvr for p in graph.get_nodes([pkg2]))

    atom = package_info.parse(pkg1.atom)
    # Should get both instances of cat/pkg-1.0 and both instances of
    # cat/pkg-2.0.
    assert len(graph.get_nodes([atom])) == 4
    assert len(graph.get_nodes([atom.atom])) == 4
    assert all(p.pkg_info.atom == atom.atom for p in graph.get_nodes([atom]))


def test_dependency_graph_dependencies():
    """Tests for get_dependencies and get_reverse_dependencies."""
    graph = _build_depgraph()

    virtual = package_info.parse("virtual/target-foo-1.2.3")
    dep = package_info.parse("cat/dep-1.0.0-r1")
    depdep = package_info.parse("cat/depdep-2.0.1-r5")
    bdep = package_info.parse("cat/bdep-3.4")

    dep_nodes = graph.get_nodes([dep])
    bdep_node = graph.get_nodes(
        [bdep], root_type=dependency_graph.RootType.SDK
    ).pop()
    # The virtual has three dependencies; dep x2(sdk + sysroot), and bdep.
    assert set(graph.get_dependencies(virtual)) == {*dep_nodes, bdep_node}
    # Virtual has no revdeps.
    assert not list(graph.get_reverse_dependencies(virtual))

    # Leaf node has no dependencies.
    assert not list(graph.get_dependencies(depdep))
    # Leaf node has two revdeps.
    assert set(graph.get_reverse_dependencies(depdep)) == set(dep_nodes)


def test_dependency_graph_is_dependency():
    """Test is_dependency method."""
    graph = _build_depgraph()

    virtual = package_info.parse("virtual/target-foo-1.2.3")
    dep = package_info.parse("cat/dep-1.0.0-r1")
    depdep = package_info.parse("cat/depdep-2.0.1-r5")
    bdep = package_info.parse("cat/bdep-3.4")

    # Direct dependency.
    assert graph.is_dependency(dep, virtual)
    # Specifying direct=True should make no difference.
    assert graph.is_dependency(dep, virtual, direct=True)
    # Indirect dependency.
    assert graph.is_dependency(depdep, virtual)
    # Indirect dependency checking direct only.
    assert not graph.is_dependency(depdep, virtual, direct=True)
    # Not a dependency.
    assert not graph.is_dependency(depdep, bdep)


def test_dependency_graph_is_dependency_root_types():
    """Test is_dependency method when using the root type filters."""
    graph = _build_depgraph()

    virtual = package_info.parse("virtual/target-foo-1.2.3")
    bdep = package_info.parse("cat/bdep-3.4")

    # Valid dependency when filtering roots.
    # bdep is in the SDK.
    assert graph.is_dependency(
        bdep, virtual, dep_root_type=dependency_graph.RootType.SDK
    )
    # bdep is also direct dependency.
    assert graph.is_dependency(
        bdep, virtual, dep_root_type=dependency_graph.RootType.SDK, direct=True
    )
    # virtual is in the sysroot.
    assert graph.is_dependency(
        bdep,
        virtual,
        dep_root_type=dependency_graph.RootType.SDK,
        src_root_type=dependency_graph.RootType.SYSROOT,
    )

    # Invalid dependency when filtering roots.
    # bdep is not in the sysroot.
    assert not graph.is_dependency(
        bdep, virtual, dep_root_type=dependency_graph.RootType.SYSROOT
    )
    # virtual is not in the SDK.
    assert not graph.is_dependency(
        bdep, virtual, src_root_type=dependency_graph.RootType.SDK
    )


def test_depedency_graph_is_relevant():
    """Test the is_relevant method."""
    graph = _build_depgraph()
    # Dependency.
    # Fetch node and call directly.
    assert graph.get_nodes(["cat/depdep"])[0].is_relevant("/cat/depdep")
    # Search the depgraph.
    assert graph.is_relevant("/cat/depdep")

    # Reverse dependency.
    assert graph.is_relevant("/cat/bdep")

    # Irrelevant path.
    assert not graph.is_relevant("/not/relevant")


def test_dependency_graph_any_relevant():
    """Test the any_relevant method."""
    graph = _build_depgraph()
    # Both relevant.
    assert graph.any_relevant(["/cat/dep", "/cat/bdep"])
    # One relevant.
    assert graph.any_relevant(["/not/relevant", "/cat/bdep"])
    # Neither relevant.
    assert not graph.any_relevant(["/not/relevant", "/also/not/relevant"])


def test_get_relevant_nodes():
    """Test the get_relevant_nodes method."""
    graph = _build_depgraph()
    dep = package_info.parse("cat/dep-1.0.0-r1")

    # No root type specified, defaults to all.
    assert set(graph.get_relevant_nodes(["/cat/dep"])) == set(
        graph.get_nodes([dep])
    )

    # Get dependencies for all root types.
    assert set(
        graph.get_relevant_nodes(["/cat/dep"], dependency_graph.RootType.ALL)
    ) == set(graph.get_nodes([dep]))
    # Only sysroot dependencies.
    assert set(
        graph.get_relevant_nodes(
            ["/cat/dep"], dependency_graph.RootType.SYSROOT
        )
    ) == set(graph.get_nodes([dep], dependency_graph.RootType.SYSROOT))

    # Only SDK dependencies.
    assert set(
        graph.get_relevant_nodes(["/cat/dep"], dependency_graph.RootType.SDK)
    ) == set(graph.get_nodes([dep], dependency_graph.RootType.SDK))
