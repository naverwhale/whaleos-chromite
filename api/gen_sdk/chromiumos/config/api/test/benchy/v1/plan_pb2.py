# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/test/benchy/v1/plan.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n/chromiumos/config/api/test/benchy/v1/plan.proto\x12\"chromium.config.api.test.benchy.v1\"<\n\x07Payload\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x0e\n\x06source\x18\x02 \x01(\t\x12\x13\n\x0b\x64\x65stination\x18\x03 \x01(\t\"8\n\x06\x44\x65vice\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x11\n\thost_name\x18\x02 \x01(\t\x12\r\n\x05\x62oard\x18\x03 \x01(\t\"&\n\x05\x42uild\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x0f\n\x07version\x18\x02 \x01(\t\"\x85\x02\n\tParameter\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x0e\n\x06values\x18\x02 \x03(\t\x12\x14\n\x0c\x63ommand_line\x18\x03 \x01(\t\x12S\n\x0e\x65xecution_mode\x18\x04 \x01(\x0e\x32;.chromium.config.api.test.benchy.v1.Parameter.ExecutionMode\"o\n\rExecutionMode\x12\x19\n\x15\x45XECUTION_UNSPECIFIED\x10\x00\x12\x13\n\x0f\x45XECUTION_LOCAL\x10\x01\x12\x11\n\rEXECUTION_DUT\x10\x02\x12\x1b\n\x17\x45XECUTION_TAST_VARIABLE\x10\x03\"]\n\x08Workload\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x14\n\x0c\x63ommand_line\x18\x02 \x01(\t\x12\x17\n\x0flocal_execution\x18\x03 \x01(\x08\x12\x14\n\x0crepeat_count\x18\x04 \x01(\r\"\xe9\x02\n\x04Plan\x12\x0c\n\x04name\x18\x01 \x01(\t\x12=\n\x08payloads\x18\x02 \x03(\x0b\x32+.chromium.config.api.test.benchy.v1.Payload\x12;\n\x07\x64\x65vices\x18\x03 \x03(\x0b\x32*.chromium.config.api.test.benchy.v1.Device\x12\x39\n\x06\x62uilds\x18\x04 \x03(\x0b\x32).chromium.config.api.test.benchy.v1.Build\x12?\n\tworkloads\x18\x05 \x03(\x0b\x32,.chromium.config.api.test.benchy.v1.Workload\x12\x41\n\nparameters\x18\x06 \x03(\x0b\x32-.chromium.config.api.test.benchy.v1.Parameter\x12\x18\n\x10\x63ooldown_seconds\x18\x07 \x01(\rB@Z>go.chromium.org/chromiumos/config/go/api/test/benchy/v1;benchyb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.config.api.test.benchy.v1.plan_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z>go.chromium.org/chromiumos/config/go/api/test/benchy/v1;benchy'
  _PAYLOAD._serialized_start=87
  _PAYLOAD._serialized_end=147
  _DEVICE._serialized_start=149
  _DEVICE._serialized_end=205
  _BUILD._serialized_start=207
  _BUILD._serialized_end=245
  _PARAMETER._serialized_start=248
  _PARAMETER._serialized_end=509
  _PARAMETER_EXECUTIONMODE._serialized_start=398
  _PARAMETER_EXECUTIONMODE._serialized_end=509
  _WORKLOAD._serialized_start=511
  _WORKLOAD._serialized_end=604
  _PLAN._serialized_start=607
  _PLAN._serialized_end=968
# @@protoc_insertion_point(module_scope)
