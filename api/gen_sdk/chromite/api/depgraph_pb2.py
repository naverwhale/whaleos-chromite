# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromite/api/depgraph.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen_sdk.chromite.api import build_api_pb2 as chromite_dot_api_dot_build__api__pb2
from chromite.api.gen_sdk.chromite.api import sysroot_pb2 as chromite_dot_api_dot_sysroot__pb2
from chromite.api.gen_sdk.chromiumos import common_pb2 as chromiumos_dot_common__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1b\x63hromite/api/depgraph.proto\x12\x0c\x63hromite.api\x1a\x1c\x63hromite/api/build_api.proto\x1a\x1a\x63hromite/api/sysroot.proto\x1a\x17\x63hromiumos/common.proto\"\x95\x01\n\x08\x44\x65pGraph\x12-\n\x0c\x62uild_target\x18\x01 \x01(\x0b\x32\x17.chromiumos.BuildTarget\x12\x32\n\x0cpackage_deps\x18\x02 \x03(\x0b\x32\x1c.chromite.api.PackageDepInfo\x12&\n\x07sysroot\x18\x03 \x01(\x0b\x32\x15.chromite.api.Sysroot\"\xb0\x01\n\x0ePackageDepInfo\x12-\n\x0cpackage_info\x18\x01 \x01(\x0b\x32\x17.chromiumos.PackageInfo\x12\x34\n\x13\x64\x65pendency_packages\x18\x02 \x03(\x0b\x32\x17.chromiumos.PackageInfo\x12\x39\n\x17\x64\x65pendency_source_paths\x18\x03 \x03(\x0b\x32\x18.chromite.api.SourcePath\"\x1a\n\nSourcePath\x12\x0c\n\x04path\x18\x01 \x01(\t\"\xc6\x01\n\x1eGetBuildDependencyGraphRequest\x12&\n\x07sysroot\x18\x04 \x01(\x0b\x32\x15.chromite.api.Sysroot\x12-\n\x0c\x62uild_target\x18\x01 \x01(\x0b\x32\x17.chromiumos.BuildTarget\x12\"\n\x06\x63hroot\x18\x02 \x01(\x0b\x32\x12.chromiumos.Chroot\x12)\n\x08packages\x18\x03 \x03(\x0b\x32\x17.chromiumos.PackageInfo\"{\n\x1fGetBuildDependencyGraphResponse\x12)\n\tdep_graph\x18\x01 \x01(\x0b\x32\x16.chromite.api.DepGraph\x12-\n\rsdk_dep_graph\x18\x02 \x01(\x0b\x32\x16.chromite.api.DepGraph\">\n\x18GetToolchainPathsRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\"D\n\x19GetToolchainPathsResponse\x12\'\n\x05paths\x18\x01 \x03(\x0b\x32\x18.chromite.api.SourcePath\"\xcb\x01\n\x0bListRequest\x12&\n\x07sysroot\x18\x01 \x01(\x0b\x32\x15.chromite.api.Sysroot\x12\"\n\x06\x63hroot\x18\x02 \x01(\x0b\x32\x12.chromiumos.Chroot\x12+\n\tsrc_paths\x18\x03 \x03(\x0b\x32\x18.chromite.api.SourcePath\x12)\n\x08packages\x18\x04 \x03(\x0b\x32\x17.chromiumos.PackageInfo\x12\x18\n\x10include_rev_deps\x18\x05 \x01(\x08\"=\n\x0cListResponse\x12-\n\x0cpackage_deps\x18\x01 \x03(\x0b\x32\x17.chromiumos.PackageInfo2\xc4\x02\n\x11\x44\x65pendencyService\x12v\n\x17GetBuildDependencyGraph\x12,.chromite.api.GetBuildDependencyGraphRequest\x1a-.chromite.api.GetBuildDependencyGraphResponse\x12\x64\n\x11GetToolchainPaths\x12&.chromite.api.GetToolchainPathsRequest\x1a\'.chromite.api.GetToolchainPathsResponse\x12=\n\x04List\x12\x19.chromite.api.ListRequest\x1a\x1a.chromite.api.ListResponse\x1a\x12\xc2\xed\x1a\x0e\n\ndependency\x10\x01\x42\x38Z6go.chromium.org/chromiumos/infra/proto/go/chromite/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromite.api.depgraph_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z6go.chromium.org/chromiumos/infra/proto/go/chromite/api'
  _DEPENDENCYSERVICE._options = None
  _DEPENDENCYSERVICE._serialized_options = b'\302\355\032\016\n\ndependency\020\001'
  _DEPGRAPH._serialized_start=129
  _DEPGRAPH._serialized_end=278
  _PACKAGEDEPINFO._serialized_start=281
  _PACKAGEDEPINFO._serialized_end=457
  _SOURCEPATH._serialized_start=459
  _SOURCEPATH._serialized_end=485
  _GETBUILDDEPENDENCYGRAPHREQUEST._serialized_start=488
  _GETBUILDDEPENDENCYGRAPHREQUEST._serialized_end=686
  _GETBUILDDEPENDENCYGRAPHRESPONSE._serialized_start=688
  _GETBUILDDEPENDENCYGRAPHRESPONSE._serialized_end=811
  _GETTOOLCHAINPATHSREQUEST._serialized_start=813
  _GETTOOLCHAINPATHSREQUEST._serialized_end=875
  _GETTOOLCHAINPATHSRESPONSE._serialized_start=877
  _GETTOOLCHAINPATHSRESPONSE._serialized_end=945
  _LISTREQUEST._serialized_start=948
  _LISTREQUEST._serialized_end=1151
  _LISTRESPONSE._serialized_start=1153
  _LISTRESPONSE._serialized_end=1214
  _DEPENDENCYSERVICE._serialized_start=1217
  _DEPENDENCYSERVICE._serialized_end=1541
# @@protoc_insertion_point(module_scope)
