# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: test_platform/result_flow/common.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n&test_platform/result_flow/common.proto\x12\x19test_platform.result_flow\"d\n\x0cPubSubConfig\x12\x0f\n\x07project\x18\x01 \x01(\t\x12\r\n\x05topic\x18\x02 \x01(\t\x12\x14\n\x0csubscription\x18\x03 \x01(\t\x12\x1e\n\x16max_receiving_messages\x18\x04 \x01(\x05\"S\n\x11\x42uildbucketConfig\x12\x0c\n\x04host\x18\x01 \x01(\t\x12\x0f\n\x07project\x18\x02 \x01(\t\x12\x0e\n\x06\x62ucket\x18\x03 \x01(\t\x12\x0f\n\x07\x62uilder\x18\x04 \x01(\t\"A\n\x0e\x42igqueryConfig\x12\x0f\n\x07project\x18\x01 \x01(\t\x12\x0f\n\x07\x64\x61taset\x18\x02 \x01(\t\x12\r\n\x05table\x18\x03 \x01(\t\"\x8b\x01\n\x06Source\x12\x37\n\x06pubsub\x18\x01 \x01(\x0b\x32\'.test_platform.result_flow.PubSubConfig\x12\x38\n\x02\x62\x62\x18\x02 \x01(\x0b\x32,.test_platform.result_flow.BuildbucketConfig\x12\x0e\n\x06\x66ields\x18\x03 \x03(\t\"?\n\x06Target\x12\x35\n\x02\x62q\x18\x01 \x01(\x0b\x32).test_platform.result_flow.BigqueryConfig*U\n\x05State\x12\x15\n\x11STATE_UNSPECIFIED\x10\x00\x12\r\n\tSUCCEEDED\x10\x01\x12\n\n\x06\x46\x41ILED\x10\x02\x12\r\n\tTIMED_OUT\x10\x03\x12\x0b\n\x07\x41\x42ORTED\x10\x04\x42\x45ZCgo.chromium.org/chromiumos/infra/proto/go/test_platform/result_flowb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'test_platform.result_flow.common_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'ZCgo.chromium.org/chromiumos/infra/proto/go/test_platform/result_flow'
  _STATE._serialized_start=530
  _STATE._serialized_end=615
  _PUBSUBCONFIG._serialized_start=69
  _PUBSUBCONFIG._serialized_end=169
  _BUILDBUCKETCONFIG._serialized_start=171
  _BUILDBUCKETCONFIG._serialized_end=254
  _BIGQUERYCONFIG._serialized_start=256
  _BIGQUERYCONFIG._serialized_end=321
  _SOURCE._serialized_start=324
  _SOURCE._serialized_end=463
  _TARGET._serialized_start=465
  _TARGET._serialized_end=528
# @@protoc_insertion_point(module_scope)
