# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Board build dependency service tests."""

import os

from chromite.api import api_config
from chromite.api.controller import controller_util
from chromite.api.controller import dependency
from chromite.api.gen.chromite.api import depgraph_pb2
from chromite.api.gen.chromite.api import sysroot_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib.parser import package_info
from chromite.service import dependency as dependency_service

pytestmark = cros_test_lib.pytestmark_inside_only


class BoardBuildDependencyTest(cros_test_lib.MockTestCase,
                               api_config.ApiConfigMixin):
  """Unittests for board_build_dependency."""

  def setUp(self):
    self.response = depgraph_pb2.GetBuildDependencyGraphResponse()
    self.json_deps = {
        'target_board': 'deathstar',
        'sysroot_path': '/build/deathstar',
        'package_deps': {
            'commander/darthvader-1.49.3.3': {
                'action': 'merge',
                'category': 'commander',
                'cpes': [],
                'deps': ['troop/clone', 'troop/robot'],
                'rev_deps': [],
                'full_name': 'commander/darthvader-1.49.3.3',
                'name': 'darthvader',
                'version': '1.49.3.3'
            },
            'troop/clone-1.2.3': {
                'action': 'merge',
                'category': 'troop',
                'cpes': [],
                'deps': ['equipment/jetpack'],
                'rev_deps': ['commander/darthvader'],
                'full_name': 'troop/clone-1.2.3',
                'name': 'clone',
                'version': '1.2.3'
            },
            'troop/robot-2.3.4': {
                'action': 'merge',
                'category': 'troop',
                'cpes': [],
                'deps': [],
                'rev_deps': ['commander/darthvader'],
                'full_name': 'troop/robot-2.3.4',
                'name': 'robot',
                'version': '2.3.4'
            },
            'equipment/jetpack-3.4.5': {
                'action': 'merge',
                'category': 'equipment',
                'cpes': [],
                'deps': [],
                'rev_deps': ['commander/darthvader'],
                'full_name': 'equipment/jetpack-3.4.5',
                'name': 'jetpack',
                'version': '3.4.5'
            },
        },
        'source_path_mapping': {
            'commander/darthvader-1.49.3.3': ['/control/room'],
            'troop/clone-1.2.3': ['/bunker'],
            'troop/robot-2.3.4': ['/factory'],
            'equipment/jetpack-3.4.5': ['/factory'],
        },
    }

  def testCreateDepGraphProtoFromJsonMap(self):
    """Test creating DepGraph protobuf from json map."""
    depgraph_proto = depgraph_pb2.DepGraph()
    dependency.AugmentDepGraphProtoFromJsonMap(
        self.json_deps, depgraph_proto)
    self.assertEqual(depgraph_proto.build_target.name, 'deathstar')
    darthvader_dep = None
    for package_dep_info in depgraph_proto.package_deps:
      if package_dep_info.package_info.package_name == 'darthvader':
        darthvader_dep = package_dep_info
    self.assertTrue(darthvader_dep)
    self.assertEqual(darthvader_dep.dependency_packages[0].category,
                     'troop')
    self.assertEqual(darthvader_dep.dependency_packages[0].package_name,
                     'clone')
    self.assertEqual(darthvader_dep.dependency_source_paths[0].path,
                     '/control/room')

  def testGetBuildDependencyGraph(self):
    """GetBuildDependencyGraph calls helper method with correct args."""
    patch = self.PatchObject(
        dependency_service,
        'GetBuildDependency',
        return_value=(self.json_deps, self.json_deps))
    input_proto = depgraph_pb2.GetBuildDependencyGraphRequest()
    input_proto.build_target.name = 'target'
    dependency.GetBuildDependencyGraph(input_proto, self.response,
                                       self.api_config)
    self.assertEqual(self.response.dep_graph.build_target.name, 'deathstar')
    patch.assert_called_once()

  def testGetBuildDependencyGraphForPackages(self):
    """GetBuildDependencyGraph calls helper method with correct args."""
    get_dep = self.PatchObject(
        dependency_service,
        'GetBuildDependency',
        return_value=(self.json_deps, self.json_deps))
    pkg_mock = 'package-CPV'
    pkg_to_cpv = self.PatchObject(
        controller_util,
        'PackageInfoToCPV', return_value=pkg_mock)
    package = common_pb2.PackageInfo(
        package_name='chromeos-chrome', category='chromeos-base')
    input_proto = depgraph_pb2.GetBuildDependencyGraphRequest(
        build_target=common_pb2.BuildTarget(name='target'),
        packages=[package]
    )
    dependency.GetBuildDependencyGraph(input_proto, self.response,
                                       self.api_config)
    self.assertEqual(self.response.dep_graph.build_target.name, 'deathstar')
    pkg_to_cpv.assert_called_once_with(package)
    get_dep.assert_called_once_with('/build/target', 'target', (pkg_mock,))

  def testValidateOnly(self):
    """Test that a validate only call does not execute any logic."""
    patch = self.PatchObject(dependency_service, 'GetBuildDependency')
    input_proto = depgraph_pb2.GetBuildDependencyGraphRequest()
    input_proto.build_target.name = 'target'
    dependency.GetBuildDependencyGraph(input_proto, self.response,
                                       self.validate_only_config)
    patch.assert_not_called()

  def testMockCall(self):
    """Test that a mock call does not execute logic, returns mocked value."""
    patch = self.PatchObject(dependency_service, 'GetBuildDependency')
    input_proto = depgraph_pb2.GetBuildDependencyGraphRequest()
    input_proto.build_target.name = 'target'
    dependency.GetBuildDependencyGraph(input_proto, self.response,
                                       self.mock_call_config)
    patch.assert_not_called()
    self.assertEqual(self.response.dep_graph.build_target.name, 'target_board')


class ListTest(cros_test_lib.MockTempDirTestCase, api_config.ApiConfigMixin):
  """Unittests for the List endpoint."""

  def setUp(self):
    self.response = depgraph_pb2.ListResponse()
    self.build_target = common_pb2.BuildTarget(name='target')
    self.sysroot = os.path.join(self.tempdir, 'target')
    osutils.SafeMakedirs(self.sysroot)

  def testValidateOnly(self):
    """Test that a validate only call does not execute any logic."""
    sysroot = sysroot_pb2.Sysroot(
        path=self.sysroot, build_target=self.build_target)
    input_proto = depgraph_pb2.ListRequest(sysroot=sysroot)
    dependency.List(input_proto, self.response, self.validate_only_config)

  def testArgumentValidationMissingSysrootPath(self):
    """Test missing sysroot path."""
    sysroot = sysroot_pb2.Sysroot(build_target=self.build_target)
    input_proto = depgraph_pb2.ListRequest(sysroot=sysroot)
    with self.assertRaises(cros_build_lib.DieSystemExit):
      dependency.List(input_proto, self.response, self.api_config)

  def testArgumentValidationMissingBuildTarget(self):
    """Test missing build target name."""
    sysroot = sysroot_pb2.Sysroot(
        path=self.sysroot, build_target=common_pb2.BuildTarget())
    input_proto = depgraph_pb2.ListRequest(sysroot=sysroot)
    with self.assertRaises(cros_build_lib.DieSystemExit):
      dependency.List(input_proto, self.response, self.api_config)

  def testDefaultArguments(self):
    """Test with default arguments."""
    sysroot = sysroot_pb2.Sysroot(
        path=self.sysroot, build_target=self.build_target)
    input_proto = depgraph_pb2.ListRequest(sysroot=sysroot)
    mock_get_deps = self.PatchObject(dependency_service, 'GetDependencies')
    dependency.List(input_proto, self.response, self.api_config)
    mock_get_deps.assert_called_once_with(
        self.sysroot, src_paths=[], packages=[], include_rev_dependencies=False)

  def testListResponse(self):
    """Test calls helper method with correct args."""
    sysroot = sysroot_pb2.Sysroot(
        path=self.sysroot, build_target=self.build_target)
    path = '/path'
    return_package_info = package_info.parse('foo/bar-1.2.3')
    return_package_info_proto = common_pb2.PackageInfo(
        category='foo', package_name='bar', version='1.2.3')
    mock_get_deps = self.PatchObject(
        dependency_service,
        'GetDependencies',
        return_value=[return_package_info])

    input_package_info_proto = common_pb2.PackageInfo(
        category='foo', package_name='bar')
    input_package_info = package_info.parse('foo/bar')
    input_proto = depgraph_pb2.ListRequest(
        sysroot=sysroot,
        src_paths=[
            depgraph_pb2.SourcePath(path=path),
        ],
        packages=[input_package_info_proto],
        include_rev_deps=True)
    dependency.List(input_proto, self.response, self.api_config)
    mock_get_deps.assert_called_once_with(
        self.sysroot,
        src_paths=[path],
        packages=[input_package_info],
        include_rev_dependencies=True)
    self.assertCountEqual([return_package_info_proto],
                          self.response.package_deps)
