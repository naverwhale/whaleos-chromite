# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromite/observability/shared.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.third_party.google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2
from chromite.api.gen.chromiumos import common_pb2 as chromiumos_dot_common__pb2
from chromite.api.gen.chromiumos import builder_config_pb2 as chromiumos_dot_builder__config__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n#chromite/observability/shared.proto\x12\x16\x63hromite.observability\x1a\x1fgoogle/protobuf/timestamp.proto\x1a\x17\x63hromiumos/common.proto\x1a\x1f\x63hromiumos/builder_config.proto\"\x95\x02\n\x0f\x42uilderMetadata\x12\x16\n\x0e\x62uildbucket_id\x18\x01 \x01(\x04\x12\x33\n\x0fstart_timestamp\x18\x02 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12-\n\x0c\x62uild_target\x18\x03 \x01(\x0b\x32\x17.chromiumos.BuildTarget\x12\x35\n\nbuild_type\x18\x04 \x01(\x0e\x32!.chromiumos.BuilderConfig.Id.Type\x12\x19\n\x11\x62uild_config_name\x18\x05 \x01(\t\x12\x1b\n\x13\x61nnealing_commit_id\x18\x06 \x01(\r\x12\x17\n\x0fmanifest_commit\x18\x07 \x01(\t\"h\n\x10\x42uildVersionData\x12\x11\n\tmilestone\x18\x01 \x01(\r\x12\x41\n\x10platform_version\x18\x02 \x01(\x0b\x32\'.chromite.observability.PlatformVersion\"Z\n\x0fPlatformVersion\x12\x16\n\x0eplatform_build\x18\x01 \x01(\r\x12\x17\n\x0fplatform_branch\x18\x02 \x01(\r\x12\x16\n\x0eplatform_patch\x18\x03 \x01(\rBBZ@go.chromium.org/chromiumos/infra/proto/go/chromite/observabilityb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromite.observability.shared_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z@go.chromium.org/chromiumos/infra/proto/go/chromite/observability'
  _BUILDERMETADATA._serialized_start=155
  _BUILDERMETADATA._serialized_end=432
  _BUILDVERSIONDATA._serialized_start=434
  _BUILDVERSIONDATA._serialized_end=538
  _PLATFORMVERSION._serialized_start=540
  _PLATFORMVERSION._serialized_end=630
# @@protoc_insertion_point(module_scope)
