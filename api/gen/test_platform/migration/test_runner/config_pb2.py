# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: test_platform/migration/test_runner/config.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n0test_platform/migration/test_runner/config.proto\x12#test_platform.migration.test_runner\"a\n\x06\x43onfig\x12W\n\x15redirect_instructions\x18\x01 \x03(\x0b\x32\x38.test_platform.migration.test_runner.RedirectInstruction\"~\n\x13RedirectInstruction\x12J\n\nconstraint\x18\x01 \x01(\x0b\x32\x36.test_platform.migration.test_runner.TrafficConstraint\x12\x1b\n\x13percent_of_requests\x18\x02 \x01(\x05\"<\n\x11TrafficConstraint\x12\x10\n\x08\x64ut_pool\x18\x01 \x01(\t\x12\x15\n\rquota_account\x18\x02 \x01(\tBOZMgo.chromium.org/chromiumos/infra/proto/go/test_platform/migration/test_runnerb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'test_platform.migration.test_runner.config_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'ZMgo.chromium.org/chromiumos/infra/proto/go/test_platform/migration/test_runner'
  _CONFIG._serialized_start=89
  _CONFIG._serialized_end=186
  _REDIRECTINSTRUCTION._serialized_start=188
  _REDIRECTINSTRUCTION._serialized_end=314
  _TRAFFICCONSTRAINT._serialized_start=316
  _TRAFFICCONSTRAINT._serialized_end=376
# @@protoc_insertion_point(module_scope)
