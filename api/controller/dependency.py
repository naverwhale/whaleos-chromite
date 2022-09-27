# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Build graph dependency creation service.

This service handles the creation of the portage build dependency graphs and the
graphs mapping from portage packages to the dependency source.
"""

from chromite.api import api_config
from chromite.api import faux
from chromite.api import validate
from chromite.api.controller import controller_util
from chromite.api.gen.chromite.api import depgraph_pb2
# TODO(crbug/1081828): stop using build_target and drop it from the proto.
from chromite.lib import build_target_lib
from chromite.lib.parser import package_info
from chromite.service import dependency


def AugmentDepGraphProtoFromJsonMap(json_map, graph):
  """Augment package deps from |json_map| to graph object.

  Args:
    json_map: the json object that stores the portage package. This is
      generated from chromite.lib.service.dependency.GetBuildDependency()
    graph: the proto object that represents the dependency graph (see DepGraph
      message in chromite/api/depgraph.proto)
  """
  graph.sysroot.build_target.name = json_map['target_board']
  graph.sysroot.path = json_map['sysroot_path']
  # TODO(crbug/1081828): Drop this when no longer used.
  graph.build_target.name = json_map['target_board']

  for data in json_map['package_deps'].values():
    package_dep_info = graph.package_deps.add()
    package_info_msg = package_dep_info.package_info
    package_info_msg.package_name = data['name']
    package_info_msg.category = data['category']
    package_info_msg.version = data['version']
    for dep in data['deps']:
      cpv = package_info.parse(dep)
      dep_package = package_dep_info.dependency_packages.add()
      controller_util.serialize_package_info(cpv, dep_package)

    package_CPV = controller_util.PackageInfoToString(package_info_msg)
    for path in json_map['source_path_mapping'][package_CPV]:
      source_path = package_dep_info.dependency_source_paths.add()
      source_path.path = path


def _GetBuildDependencyGraphResponse(_input_proto, output_proto, _config):
  """Add fake dep_graph data to a successful response."""
  output_proto.dep_graph.build_target.name = 'target_board'


@faux.success(_GetBuildDependencyGraphResponse)
@faux.empty_error
@validate.require_each('packages', ['category', 'package_name'])
@validate.validation_complete
def GetBuildDependencyGraph(
    input_proto: depgraph_pb2.GetBuildDependencyGraphRequest,
    output_proto: depgraph_pb2.GetBuildDependencyGraphResponse,
    _config: api_config.ApiConfig) -> None:
  """Create the build dependency graph.

  Args:
    input_proto: The input arguments message.
    output_proto: The empty output message.
    _config: The API call config.
  """
  if input_proto.HasField('sysroot'):
    board = input_proto.sysroot.build_target.name
    sysroot_path = input_proto.sysroot.path
  else:
    # TODO(crbug/1081828): stop using build_target and drop it from the proto.
    board = input_proto.build_target.name
    sysroot_path = build_target_lib.get_default_sysroot_path(board or None)

  packages = tuple(
      controller_util.PackageInfoToCPV(x) for x in input_proto.packages)

  json_map, sdk_json_map = dependency.GetBuildDependency(sysroot_path, board,
                                                         packages)
  AugmentDepGraphProtoFromJsonMap(json_map, output_proto.dep_graph)
  AugmentDepGraphProtoFromJsonMap(sdk_json_map, output_proto.sdk_dep_graph)


def _ListResponse(_input_proto, output_proto, _config):
  """Add fake dependency data to a successful response."""
  package_dep = output_proto.package_deps.add()
  package_dep.category = 'category'
  package_dep.package_name = 'name'


@faux.success(_ListResponse)
@faux.empty_error
@validate.require('sysroot.build_target.name')
@validate.exists('sysroot.path')
@validate.require_each('src_paths', ['path'])
@validate.require_each('packages', ['category', 'package_name'])
@validate.validation_complete
def List(input_proto: depgraph_pb2.ListRequest,
         output_proto: depgraph_pb2.ListResponse,
         _config: api_config.ApiConfig):
  """Get a list of package dependencies.

  Args:
    input_proto: The input arguments message.
    output_proto: The empty output message.
    _config: The API call config.
  """
  sysroot_path = input_proto.sysroot.path
  src_paths = [src_path.path for src_path in input_proto.src_paths]
  package_deps = dependency.GetDependencies(
      sysroot_path,
      src_paths=src_paths,
      packages=[
          controller_util.deserialize_package_info(package)
          for package in input_proto.packages
      ],
      include_rev_dependencies=input_proto.include_rev_deps)
  for package in package_deps:
    pkg_info_msg = output_proto.package_deps.add()
    controller_util.serialize_package_info(package, pkg_info_msg)


def _DummyGetToolchainPathsResponse(_input_proto, output_proto, _config):
  """Create a fake successful response for GetToolchainPaths."""
  dummy_entry = output_proto.paths.add()
  dummy_entry.path = 'src/third_party/dummy-package'


@faux.success(_DummyGetToolchainPathsResponse)
@faux.empty_error
@validate.validation_complete
def GetToolchainPaths(_input_proto, output_proto, _config):
  """Get a list of paths that affect the toolchain."""
  toolchain_paths = dependency.DetermineToolchainSourcePaths()
  for p in toolchain_paths:
    source_path = output_proto.paths.add()
    source_path.path = p
