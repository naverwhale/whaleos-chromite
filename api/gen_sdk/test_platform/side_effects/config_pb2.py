# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: test_platform/side_effects/config.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\'test_platform/side_effects/config.proto\x12\x1atest_platform.side_effects\"\xbd\x01\n\tTKOConfig\x12\"\n\x0cproxy_socket\x18\x01 \x01(\tR\x0cproxy_socket\x12\x1e\n\nmysql_user\x18\x02 \x01(\tR\nmysql_user\x12\x30\n\x13mysql_password_file\x18\x03 \x01(\tR\x13mysql_password_file\x12:\n\x18\x65ncrypted_mysql_password\x18\x04 \x01(\tR\x18\x65ncrypted_mysql_password\"Q\n\x13GoogleStorageConfig\x12\x0e\n\x06\x62ucket\x18\x01 \x01(\t\x12*\n\x10\x63redentials_file\x18\x02 \x01(\tR\x10\x63redentials_file\"#\n\x10\x43hromePerfConfig\x12\x0f\n\x07\x65nabled\x18\x01 \x01(\x08\"\x1c\n\tCTSConfig\x12\x0f\n\x07\x65nabled\x18\x01 \x01(\x08\"\x99\x02\n\x06\x43onfig\x12\x32\n\x03tko\x18\x01 \x01(\x0b\x32%.test_platform.side_effects.TKOConfig\x12W\n\x0egoogle_storage\x18\x02 \x01(\x0b\x32/.test_platform.side_effects.GoogleStorageConfigR\x0egoogle_storage\x12N\n\x0b\x63hrome_perf\x18\x03 \x01(\x0b\x32,.test_platform.side_effects.ChromePerfConfigR\x0b\x63hrome_perf\x12\x32\n\x03\x63ts\x18\x04 \x01(\x0b\x32%.test_platform.side_effects.CTSConfigBFZDgo.chromium.org/chromiumos/infra/proto/go/test_platform/side_effectsb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'test_platform.side_effects.config_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'ZDgo.chromium.org/chromiumos/infra/proto/go/test_platform/side_effects'
  _TKOCONFIG._serialized_start=72
  _TKOCONFIG._serialized_end=261
  _GOOGLESTORAGECONFIG._serialized_start=263
  _GOOGLESTORAGECONFIG._serialized_end=344
  _CHROMEPERFCONFIG._serialized_start=346
  _CHROMEPERFCONFIG._serialized_end=381
  _CTSCONFIG._serialized_start=383
  _CTSCONFIG._serialized_end=411
  _CONFIG._serialized_start=414
  _CONFIG._serialized_end=695
# @@protoc_insertion_point(module_scope)
