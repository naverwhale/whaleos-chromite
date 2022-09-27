# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromite/api/depgraph.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import message as _message
from chromite.third_party.google.protobuf import reflection as _reflection
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromite.api import build_api_pb2 as chromite_dot_api_dot_build__api__pb2
from chromite.api.gen.chromite.api import sysroot_pb2 as chromite_dot_api_dot_sysroot__pb2
from chromite.api.gen.chromiumos import common_pb2 as chromiumos_dot_common__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='chromite/api/depgraph.proto',
  package='chromite.api',
  syntax='proto3',
  serialized_options=b'Z6go.chromium.org/chromiumos/infra/proto/go/chromite/api',
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n\x1b\x63hromite/api/depgraph.proto\x12\x0c\x63hromite.api\x1a\x1c\x63hromite/api/build_api.proto\x1a\x1a\x63hromite/api/sysroot.proto\x1a\x17\x63hromiumos/common.proto\"\x95\x01\n\x08\x44\x65pGraph\x12-\n\x0c\x62uild_target\x18\x01 \x01(\x0b\x32\x17.chromiumos.BuildTarget\x12\x32\n\x0cpackage_deps\x18\x02 \x03(\x0b\x32\x1c.chromite.api.PackageDepInfo\x12&\n\x07sysroot\x18\x03 \x01(\x0b\x32\x15.chromite.api.Sysroot\"\xb0\x01\n\x0ePackageDepInfo\x12-\n\x0cpackage_info\x18\x01 \x01(\x0b\x32\x17.chromiumos.PackageInfo\x12\x34\n\x13\x64\x65pendency_packages\x18\x02 \x03(\x0b\x32\x17.chromiumos.PackageInfo\x12\x39\n\x17\x64\x65pendency_source_paths\x18\x03 \x03(\x0b\x32\x18.chromite.api.SourcePath\"\x1a\n\nSourcePath\x12\x0c\n\x04path\x18\x01 \x01(\t\"\xc6\x01\n\x1eGetBuildDependencyGraphRequest\x12&\n\x07sysroot\x18\x04 \x01(\x0b\x32\x15.chromite.api.Sysroot\x12-\n\x0c\x62uild_target\x18\x01 \x01(\x0b\x32\x17.chromiumos.BuildTarget\x12\"\n\x06\x63hroot\x18\x02 \x01(\x0b\x32\x12.chromiumos.Chroot\x12)\n\x08packages\x18\x03 \x03(\x0b\x32\x17.chromiumos.PackageInfo\"{\n\x1fGetBuildDependencyGraphResponse\x12)\n\tdep_graph\x18\x01 \x01(\x0b\x32\x16.chromite.api.DepGraph\x12-\n\rsdk_dep_graph\x18\x02 \x01(\x0b\x32\x16.chromite.api.DepGraph\">\n\x18GetToolchainPathsRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\"D\n\x19GetToolchainPathsResponse\x12\'\n\x05paths\x18\x01 \x03(\x0b\x32\x18.chromite.api.SourcePath\"\xcb\x01\n\x0bListRequest\x12&\n\x07sysroot\x18\x01 \x01(\x0b\x32\x15.chromite.api.Sysroot\x12\"\n\x06\x63hroot\x18\x02 \x01(\x0b\x32\x12.chromiumos.Chroot\x12+\n\tsrc_paths\x18\x03 \x03(\x0b\x32\x18.chromite.api.SourcePath\x12)\n\x08packages\x18\x04 \x03(\x0b\x32\x17.chromiumos.PackageInfo\x12\x18\n\x10include_rev_deps\x18\x05 \x01(\x08\"=\n\x0cListResponse\x12-\n\x0cpackage_deps\x18\x01 \x03(\x0b\x32\x17.chromiumos.PackageInfo2\xc4\x02\n\x11\x44\x65pendencyService\x12v\n\x17GetBuildDependencyGraph\x12,.chromite.api.GetBuildDependencyGraphRequest\x1a-.chromite.api.GetBuildDependencyGraphResponse\x12\x64\n\x11GetToolchainPaths\x12&.chromite.api.GetToolchainPathsRequest\x1a\'.chromite.api.GetToolchainPathsResponse\x12=\n\x04List\x12\x19.chromite.api.ListRequest\x1a\x1a.chromite.api.ListResponse\x1a\x12\xc2\xed\x1a\x0e\n\ndependency\x10\x01\x42\x38Z6go.chromium.org/chromiumos/infra/proto/go/chromite/apib\x06proto3'
  ,
  dependencies=[chromite_dot_api_dot_build__api__pb2.DESCRIPTOR,chromite_dot_api_dot_sysroot__pb2.DESCRIPTOR,chromiumos_dot_common__pb2.DESCRIPTOR,])




_DEPGRAPH = _descriptor.Descriptor(
  name='DepGraph',
  full_name='chromite.api.DepGraph',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='build_target', full_name='chromite.api.DepGraph.build_target', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='package_deps', full_name='chromite.api.DepGraph.package_deps', index=1,
      number=2, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='sysroot', full_name='chromite.api.DepGraph.sysroot', index=2,
      number=3, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=129,
  serialized_end=278,
)


_PACKAGEDEPINFO = _descriptor.Descriptor(
  name='PackageDepInfo',
  full_name='chromite.api.PackageDepInfo',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='package_info', full_name='chromite.api.PackageDepInfo.package_info', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='dependency_packages', full_name='chromite.api.PackageDepInfo.dependency_packages', index=1,
      number=2, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='dependency_source_paths', full_name='chromite.api.PackageDepInfo.dependency_source_paths', index=2,
      number=3, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=281,
  serialized_end=457,
)


_SOURCEPATH = _descriptor.Descriptor(
  name='SourcePath',
  full_name='chromite.api.SourcePath',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='path', full_name='chromite.api.SourcePath.path', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=459,
  serialized_end=485,
)


_GETBUILDDEPENDENCYGRAPHREQUEST = _descriptor.Descriptor(
  name='GetBuildDependencyGraphRequest',
  full_name='chromite.api.GetBuildDependencyGraphRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='sysroot', full_name='chromite.api.GetBuildDependencyGraphRequest.sysroot', index=0,
      number=4, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='build_target', full_name='chromite.api.GetBuildDependencyGraphRequest.build_target', index=1,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='chroot', full_name='chromite.api.GetBuildDependencyGraphRequest.chroot', index=2,
      number=2, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='packages', full_name='chromite.api.GetBuildDependencyGraphRequest.packages', index=3,
      number=3, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=488,
  serialized_end=686,
)


_GETBUILDDEPENDENCYGRAPHRESPONSE = _descriptor.Descriptor(
  name='GetBuildDependencyGraphResponse',
  full_name='chromite.api.GetBuildDependencyGraphResponse',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='dep_graph', full_name='chromite.api.GetBuildDependencyGraphResponse.dep_graph', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='sdk_dep_graph', full_name='chromite.api.GetBuildDependencyGraphResponse.sdk_dep_graph', index=1,
      number=2, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=688,
  serialized_end=811,
)


_GETTOOLCHAINPATHSREQUEST = _descriptor.Descriptor(
  name='GetToolchainPathsRequest',
  full_name='chromite.api.GetToolchainPathsRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='chroot', full_name='chromite.api.GetToolchainPathsRequest.chroot', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=813,
  serialized_end=875,
)


_GETTOOLCHAINPATHSRESPONSE = _descriptor.Descriptor(
  name='GetToolchainPathsResponse',
  full_name='chromite.api.GetToolchainPathsResponse',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='paths', full_name='chromite.api.GetToolchainPathsResponse.paths', index=0,
      number=1, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=877,
  serialized_end=945,
)


_LISTREQUEST = _descriptor.Descriptor(
  name='ListRequest',
  full_name='chromite.api.ListRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='sysroot', full_name='chromite.api.ListRequest.sysroot', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='chroot', full_name='chromite.api.ListRequest.chroot', index=1,
      number=2, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='src_paths', full_name='chromite.api.ListRequest.src_paths', index=2,
      number=3, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='packages', full_name='chromite.api.ListRequest.packages', index=3,
      number=4, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='include_rev_deps', full_name='chromite.api.ListRequest.include_rev_deps', index=4,
      number=5, type=8, cpp_type=7, label=1,
      has_default_value=False, default_value=False,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=948,
  serialized_end=1151,
)


_LISTRESPONSE = _descriptor.Descriptor(
  name='ListResponse',
  full_name='chromite.api.ListResponse',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='package_deps', full_name='chromite.api.ListResponse.package_deps', index=0,
      number=1, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=1153,
  serialized_end=1214,
)

_DEPGRAPH.fields_by_name['build_target'].message_type = chromiumos_dot_common__pb2._BUILDTARGET
_DEPGRAPH.fields_by_name['package_deps'].message_type = _PACKAGEDEPINFO
_DEPGRAPH.fields_by_name['sysroot'].message_type = chromite_dot_api_dot_sysroot__pb2._SYSROOT
_PACKAGEDEPINFO.fields_by_name['package_info'].message_type = chromiumos_dot_common__pb2._PACKAGEINFO
_PACKAGEDEPINFO.fields_by_name['dependency_packages'].message_type = chromiumos_dot_common__pb2._PACKAGEINFO
_PACKAGEDEPINFO.fields_by_name['dependency_source_paths'].message_type = _SOURCEPATH
_GETBUILDDEPENDENCYGRAPHREQUEST.fields_by_name['sysroot'].message_type = chromite_dot_api_dot_sysroot__pb2._SYSROOT
_GETBUILDDEPENDENCYGRAPHREQUEST.fields_by_name['build_target'].message_type = chromiumos_dot_common__pb2._BUILDTARGET
_GETBUILDDEPENDENCYGRAPHREQUEST.fields_by_name['chroot'].message_type = chromiumos_dot_common__pb2._CHROOT
_GETBUILDDEPENDENCYGRAPHREQUEST.fields_by_name['packages'].message_type = chromiumos_dot_common__pb2._PACKAGEINFO
_GETBUILDDEPENDENCYGRAPHRESPONSE.fields_by_name['dep_graph'].message_type = _DEPGRAPH
_GETBUILDDEPENDENCYGRAPHRESPONSE.fields_by_name['sdk_dep_graph'].message_type = _DEPGRAPH
_GETTOOLCHAINPATHSREQUEST.fields_by_name['chroot'].message_type = chromiumos_dot_common__pb2._CHROOT
_GETTOOLCHAINPATHSRESPONSE.fields_by_name['paths'].message_type = _SOURCEPATH
_LISTREQUEST.fields_by_name['sysroot'].message_type = chromite_dot_api_dot_sysroot__pb2._SYSROOT
_LISTREQUEST.fields_by_name['chroot'].message_type = chromiumos_dot_common__pb2._CHROOT
_LISTREQUEST.fields_by_name['src_paths'].message_type = _SOURCEPATH
_LISTREQUEST.fields_by_name['packages'].message_type = chromiumos_dot_common__pb2._PACKAGEINFO
_LISTRESPONSE.fields_by_name['package_deps'].message_type = chromiumos_dot_common__pb2._PACKAGEINFO
DESCRIPTOR.message_types_by_name['DepGraph'] = _DEPGRAPH
DESCRIPTOR.message_types_by_name['PackageDepInfo'] = _PACKAGEDEPINFO
DESCRIPTOR.message_types_by_name['SourcePath'] = _SOURCEPATH
DESCRIPTOR.message_types_by_name['GetBuildDependencyGraphRequest'] = _GETBUILDDEPENDENCYGRAPHREQUEST
DESCRIPTOR.message_types_by_name['GetBuildDependencyGraphResponse'] = _GETBUILDDEPENDENCYGRAPHRESPONSE
DESCRIPTOR.message_types_by_name['GetToolchainPathsRequest'] = _GETTOOLCHAINPATHSREQUEST
DESCRIPTOR.message_types_by_name['GetToolchainPathsResponse'] = _GETTOOLCHAINPATHSRESPONSE
DESCRIPTOR.message_types_by_name['ListRequest'] = _LISTREQUEST
DESCRIPTOR.message_types_by_name['ListResponse'] = _LISTRESPONSE
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

DepGraph = _reflection.GeneratedProtocolMessageType('DepGraph', (_message.Message,), {
  'DESCRIPTOR' : _DEPGRAPH,
  '__module__' : 'chromite.api.depgraph_pb2'
  # @@protoc_insertion_point(class_scope:chromite.api.DepGraph)
  })
_sym_db.RegisterMessage(DepGraph)

PackageDepInfo = _reflection.GeneratedProtocolMessageType('PackageDepInfo', (_message.Message,), {
  'DESCRIPTOR' : _PACKAGEDEPINFO,
  '__module__' : 'chromite.api.depgraph_pb2'
  # @@protoc_insertion_point(class_scope:chromite.api.PackageDepInfo)
  })
_sym_db.RegisterMessage(PackageDepInfo)

SourcePath = _reflection.GeneratedProtocolMessageType('SourcePath', (_message.Message,), {
  'DESCRIPTOR' : _SOURCEPATH,
  '__module__' : 'chromite.api.depgraph_pb2'
  # @@protoc_insertion_point(class_scope:chromite.api.SourcePath)
  })
_sym_db.RegisterMessage(SourcePath)

GetBuildDependencyGraphRequest = _reflection.GeneratedProtocolMessageType('GetBuildDependencyGraphRequest', (_message.Message,), {
  'DESCRIPTOR' : _GETBUILDDEPENDENCYGRAPHREQUEST,
  '__module__' : 'chromite.api.depgraph_pb2'
  # @@protoc_insertion_point(class_scope:chromite.api.GetBuildDependencyGraphRequest)
  })
_sym_db.RegisterMessage(GetBuildDependencyGraphRequest)

GetBuildDependencyGraphResponse = _reflection.GeneratedProtocolMessageType('GetBuildDependencyGraphResponse', (_message.Message,), {
  'DESCRIPTOR' : _GETBUILDDEPENDENCYGRAPHRESPONSE,
  '__module__' : 'chromite.api.depgraph_pb2'
  # @@protoc_insertion_point(class_scope:chromite.api.GetBuildDependencyGraphResponse)
  })
_sym_db.RegisterMessage(GetBuildDependencyGraphResponse)

GetToolchainPathsRequest = _reflection.GeneratedProtocolMessageType('GetToolchainPathsRequest', (_message.Message,), {
  'DESCRIPTOR' : _GETTOOLCHAINPATHSREQUEST,
  '__module__' : 'chromite.api.depgraph_pb2'
  # @@protoc_insertion_point(class_scope:chromite.api.GetToolchainPathsRequest)
  })
_sym_db.RegisterMessage(GetToolchainPathsRequest)

GetToolchainPathsResponse = _reflection.GeneratedProtocolMessageType('GetToolchainPathsResponse', (_message.Message,), {
  'DESCRIPTOR' : _GETTOOLCHAINPATHSRESPONSE,
  '__module__' : 'chromite.api.depgraph_pb2'
  # @@protoc_insertion_point(class_scope:chromite.api.GetToolchainPathsResponse)
  })
_sym_db.RegisterMessage(GetToolchainPathsResponse)

ListRequest = _reflection.GeneratedProtocolMessageType('ListRequest', (_message.Message,), {
  'DESCRIPTOR' : _LISTREQUEST,
  '__module__' : 'chromite.api.depgraph_pb2'
  # @@protoc_insertion_point(class_scope:chromite.api.ListRequest)
  })
_sym_db.RegisterMessage(ListRequest)

ListResponse = _reflection.GeneratedProtocolMessageType('ListResponse', (_message.Message,), {
  'DESCRIPTOR' : _LISTRESPONSE,
  '__module__' : 'chromite.api.depgraph_pb2'
  # @@protoc_insertion_point(class_scope:chromite.api.ListResponse)
  })
_sym_db.RegisterMessage(ListResponse)


DESCRIPTOR._options = None

_DEPENDENCYSERVICE = _descriptor.ServiceDescriptor(
  name='DependencyService',
  full_name='chromite.api.DependencyService',
  file=DESCRIPTOR,
  index=0,
  serialized_options=b'\302\355\032\016\n\ndependency\020\001',
  create_key=_descriptor._internal_create_key,
  serialized_start=1217,
  serialized_end=1541,
  methods=[
  _descriptor.MethodDescriptor(
    name='GetBuildDependencyGraph',
    full_name='chromite.api.DependencyService.GetBuildDependencyGraph',
    index=0,
    containing_service=None,
    input_type=_GETBUILDDEPENDENCYGRAPHREQUEST,
    output_type=_GETBUILDDEPENDENCYGRAPHRESPONSE,
    serialized_options=None,
    create_key=_descriptor._internal_create_key,
  ),
  _descriptor.MethodDescriptor(
    name='GetToolchainPaths',
    full_name='chromite.api.DependencyService.GetToolchainPaths',
    index=1,
    containing_service=None,
    input_type=_GETTOOLCHAINPATHSREQUEST,
    output_type=_GETTOOLCHAINPATHSRESPONSE,
    serialized_options=None,
    create_key=_descriptor._internal_create_key,
  ),
  _descriptor.MethodDescriptor(
    name='List',
    full_name='chromite.api.DependencyService.List',
    index=2,
    containing_service=None,
    input_type=_LISTREQUEST,
    output_type=_LISTRESPONSE,
    serialized_options=None,
    create_key=_descriptor._internal_create_key,
  ),
])
_sym_db.RegisterServiceDescriptor(_DEPENDENCYSERVICE)

DESCRIPTOR.services_by_name['DependencyService'] = _DEPENDENCYSERVICE

# @@protoc_insertion_point(module_scope)