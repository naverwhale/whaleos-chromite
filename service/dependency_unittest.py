# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for the dependency.py module."""

import pytest

from chromite.lib import cros_test_lib
from chromite.lib import dependency_graph
from chromite.lib import dependency_lib
from chromite.lib import depgraph
from chromite.lib.parser import package_info
from chromite.service import dependency


pytestmark = cros_test_lib.pytestmark_inside_only


class DependencyTests(cros_test_lib.MockTestCase):
    """General unittests for dependency module."""

    def _build_sysroot_depgraph(self):
        """Build a DependencyGraph to test against."""
        sysroot = "/build/target"

        virtual = package_info.parse("virtual/target-foo-1.2.3")
        dep1 = package_info.parse("cat/dep-1.0.0-r1")
        dep2 = package_info.parse("cat/dep-2.0.0-r1")
        virtual_dep = package_info.parse("virtual/depdep-1.0")
        depdep = package_info.parse("cat/depdep-2.0.1-r5")

        virtual_node = dependency_graph.PackageNode(
            virtual, sysroot, src_paths=["/virtual/foo"]
        )
        dep1_node = dependency_graph.PackageNode(
            dep1, sysroot, src_paths=["/cat/dep/one"]
        )
        dep2_node = dependency_graph.PackageNode(
            dep2, sysroot, src_paths=["/cat/dep/two"]
        )
        virtual_dep_node = dependency_graph.PackageNode(
            virtual_dep, sysroot, src_paths=["/virtual/depdep"]
        )
        depdep_node = dependency_graph.PackageNode(
            depdep, sysroot, src_paths=["/cat/depdep", "/other/depdep"]
        )

        virtual_node.add_dependency(dep1_node)
        virtual_node.add_dependency(dep2_node)
        dep1_node.add_dependency(virtual_dep_node)
        virtual_dep_node.add_dependency(depdep_node)

        nodes = (
            virtual_node,
            dep1_node,
            dep2_node,
            virtual_dep_node,
            depdep_node,
        )

        return dependency_graph.DependencyGraph(nodes, sysroot, [virtual])

    def setUp(self):
        self.json_deps = {
            "target_board": "deathstar",
            "sysroot_path": "/build/deathstar",
            "package_deps": {
                "commander/darthvader-1.49.3.3": {
                    "action": "merge",
                    "category": "commander",
                    "cpes": [],
                    "deps": ["troop/clone", "troop/robot"],
                    "rev_deps": [],
                    "full_name": "commander/darthvader-1.49.3.3",
                    "name": "darthvader",
                    "version": "1.49.3.3",
                },
                "troop/clone-1.2.3": {
                    "action": "merge",
                    "category": "troop",
                    "cpes": [],
                    "deps": ["equipment/jetpack"],
                    "rev_deps": ["commander/darthvader"],
                    "full_name": "troop/clone-1.2.3",
                    "name": "clone",
                    "version": "1.2.3",
                },
                "troop/robot-2.3.4": {
                    "action": "merge",
                    "category": "troop",
                    "cpes": [],
                    "deps": [],
                    "rev_deps": ["commander/darthvader"],
                    "full_name": "troop/robot-2.3.4",
                    "name": "robot",
                    "version": "2.3.4",
                },
                "equipment/jetpack-3.4.5": {
                    "action": "merge",
                    "category": "equipment",
                    "cpes": [],
                    "deps": [],
                    "rev_deps": ["commander/darthvader"],
                    "full_name": "equipment/jetpack-3.4.5",
                    "name": "jetpack",
                    "version": "3.4.5",
                },
            },
            "source_path_mapping": {
                "commander/darthvader-1.49.3.3": ["/control/room"],
                "troop/clone-1.2.3": ["/bunker"],
                "troop/robot-2.3.4": ["/factory"],
                "equipment/jetpack-3.4.5": ["/factory"],
            },
        }

    def testDeterminePackageRelevanceNotRelevant(self):
        """Test determine_package_relevance with no matching paths."""
        src_paths = ["foo/bar/baz", "foo/bar/b", "foo/bar", "bar/foo"]
        dep_src_paths = ["foo/bar/ba"]
        self.assertFalse(
            dependency.determine_package_relevance(dep_src_paths, src_paths)
        )

    def testDeterminePackageRelevanceExactMatch(self):
        """Test determine_package_relevance given an exact match."""
        src_paths = ["foo/bar/baz"]
        dep_src_paths = ["foo/bar/baz"]
        self.assertTrue(
            dependency.determine_package_relevance(dep_src_paths, src_paths)
        )

    def testDeterminePackageRelevanceDirectoryMatch(self):
        """Test determine_package_relevance given a directory match."""
        src_paths = ["foo/bar/baz"]
        dep_src_paths = ["foo/bar"]
        self.assertTrue(
            dependency.determine_package_relevance(dep_src_paths, src_paths)
        )

    def testGetDependenciesWithDefaultArgs(self):
        """Test GetDependencies using the default args."""
        self.PatchObject(
            depgraph,
            "get_sysroot_dependency_graph",
            return_value=(self._build_sysroot_depgraph()),
        )
        sysroot_path = "/build/target"
        actual_deps = dependency.GetDependencies(sysroot_path)
        dep1 = package_info.parse("cat/dep-1.0.0-r1")
        dep2 = package_info.parse("cat/dep-2.0.0-r1")
        virtual = package_info.parse("virtual/target-foo-1.2.3")
        virtual_depdep = package_info.parse("virtual/depdep-1.0")
        depdep = package_info.parse("cat/depdep-2.0.1-r5")

        expected_deps = [dep1, dep2, virtual, virtual_depdep, depdep]
        self.assertEqual(set(expected_deps), set(actual_deps))

    def testGetDependenciesWithSrcPaths(self):
        """Test GetDependencies given a list of paths."""
        self.PatchObject(
            depgraph,
            "get_sysroot_dependency_graph",
            return_value=(self._build_sysroot_depgraph()),
        )
        sysroot_path = "/build/target"
        src_paths = ["/cat/dep/one"]
        actual_deps = dependency.GetDependencies(sysroot_path, src_paths)
        dep = package_info.parse("cat/dep-1.0.0-r1")
        self.assertCountEqual([dep], actual_deps)

    def testGetDependenciesWithSrcPathsAndReverseDeps(self):
        """Test GetDependencies given a list of paths."""
        self.PatchObject(
            depgraph,
            "get_sysroot_dependency_graph",
            return_value=(self._build_sysroot_depgraph()),
        )
        sysroot_path = "/build/target"
        src_paths = ["/cat/dep/one"]
        actual_deps = dependency.GetDependencies(
            sysroot_path, src_paths, include_rev_dependencies=True
        )

        revdep = package_info.parse("virtual/target-foo-1.2.3")
        dep = package_info.parse("cat/dep-1.0.0-r1")
        self.assertEqual({dep, revdep}, actual_deps)

    def testGetDependenciesAffectedPackagesVirtualRedirect(self):
        """Test include_affected_pkgs traverses redirection virtuals."""
        self.PatchObject(
            depgraph,
            "get_sysroot_dependency_graph",
            return_value=(self._build_sysroot_depgraph()),
        )
        sysroot_path = "/build/target"
        src_paths = ["/cat/depdep"]

        actual_deps = dependency.GetDependencies(
            sysroot_path,
            src_paths,
            include_affected_pkgs=True,
        )

        expected = {
            package_info.parse("cat/depdep-2.0.1-r5"),
            package_info.parse("virtual/depdep-1.0"),
            package_info.parse("cat/dep-1.0.0-r1"),
        }

        self.assertEqual(expected, actual_deps)

    def testGetDependenciesAffectedPackagesVirtualParent(self):
        """Test include_affected_pkgs does not include virtual parents."""
        self.PatchObject(
            depgraph,
            "get_sysroot_dependency_graph",
            return_value=(self._build_sysroot_depgraph()),
        )
        sysroot_path = "/build/target"
        src_paths = ["/cat/dep/one"]
        actual_deps = dependency.GetDependencies(
            sysroot_path,
            src_paths,
            include_affected_pkgs=True,
        )

        dep = package_info.parse("cat/dep-1.0.0-r1")
        self.assertEqual({dep}, actual_deps)


def test_generate_source_path_mapping_sdk(monkeypatch):
    """Test GenerateSourcePathMapping sdk argument."""

    def gspm_patch(_packages, sysroot_path, board, *_args, **_kwargs):
        assert sysroot_path == "/"
        assert board is None

    monkeypatch.setattr(dependency_lib, "get_source_path_mapping", gspm_patch)
    dependency.GenerateSourcePathMapping(["cat/pkg"], sdk=True)


def test_generate_source_path_mapping_sdk_only():
    """Test GenerateSourcePathMapping argument handling when setting sdk."""
    # Board.
    with pytest.raises(AssertionError):
        dependency.GenerateSourcePathMapping(
            ["cat/pkg"], sdk=True, board="board"
        )
    # Sysroot.
    with pytest.raises(AssertionError):
        dependency.GenerateSourcePathMapping(
            ["cat/pkg"], sdk=True, sysroot_path="/build/board"
        )
    # Board and sysroot.
    with pytest.raises(AssertionError):
        dependency.GenerateSourcePathMapping(
            ["cat/pkg"], sdk=True, board="board", sysroot_path="/build/board"
        )


def test_generate_source_path_mapping_sdk_sysroot(monkeypatch):
    """Test GenerateSourcePathMapping with the sdk's sysroot."""

    def gspm_patch(_packages, sysroot_path, board, *_args, **_kwargs):
        assert sysroot_path == "/"
        assert board is None

    monkeypatch.setattr(dependency_lib, "get_source_path_mapping", gspm_patch)
    dependency.GenerateSourcePathMapping(["cat/pkg"], sysroot_path="/")


def test_generate_source_path_mapping_board_sysroot(monkeypatch):
    """Test GenerateSourcePathMapping with a board's sysroot."""

    def gspm_patch(_packages, sysroot_path, board, *_args, **_kwargs):
        assert sysroot_path == "/build/board"
        assert board == "board"

    monkeypatch.setattr(dependency_lib, "get_source_path_mapping", gspm_patch)
    dependency.GenerateSourcePathMapping(
        ["cat/pkg"], sysroot_path="/build/board"
    )


def test_generate_source_path_mapping_board(monkeypatch):
    """Test GenerateSourcePathMapping with a board."""

    def gspm_patch(_packages, sysroot_path, board, *_args, **_kwargs):
        assert sysroot_path == "/build/board"
        assert board == "board"

    monkeypatch.setattr(dependency_lib, "get_source_path_mapping", gspm_patch)
    dependency.GenerateSourcePathMapping(["cat/pkg"], board="board")


def test_generate_source_path_mapping_board_and_sysroot(monkeypatch):
    """Test GenerateSourcePathMapping with a board and custom sysroot."""

    def gspm_patch(_packages, sysroot_path, board, *_args, **_kwargs):
        assert sysroot_path == "/some/sysroot"
        assert board == "board"

    monkeypatch.setattr(dependency_lib, "get_source_path_mapping", gspm_patch)
    dependency.GenerateSourcePathMapping(
        ["cat/pkg"], board="board", sysroot_path="/some/sysroot"
    )
