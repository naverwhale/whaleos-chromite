# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/test/rtd/v1/invocation.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.config.api.test.rtd.v1 import progress_pb2 as chromiumos_dot_config_dot_api_dot_test_dot_rtd_dot_v1_dot_progress__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n2chromiumos/config/api/test/rtd/v1/invocation.proto\x12!chromiumos.config.api.test.rtd.v1\x1a\x30\x63hromiumos/config/api/test/rtd/v1/progress.proto\"\xb8\x02\n\nInvocation\x12<\n\x08requests\x18\x01 \x03(\x0b\x32*.chromiumos.config.api.test.rtd.v1.Request\x12`\n\x1bprogress_sink_client_config\x18\x02 \x01(\x0b\x32;.chromiumos.config.api.test.rtd.v1.ProgressSinkClientConfig\x12T\n\x18test_lab_services_config\x18\x03 \x01(\x0b\x32\x32.chromiumos.config.api.test.rtd.v1.TLSClientConfig\x12\x34\n\x04\x64uts\x18\x04 \x03(\x0b\x32&.chromiumos.config.api.test.rtd.v1.DUT\"\x93\x01\n\x07Request\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x0c\n\x04test\x18\x02 \x01(\t\x12K\n\x0b\x65nvironment\x18\x03 \x01(\x0b\x32\x36.chromiumos.config.api.test.rtd.v1.Request.Environment\x1a\x1f\n\x0b\x45nvironment\x12\x10\n\x08work_dir\x18\x01 \x01(\t\"\x1b\n\x03\x44UT\x12\x14\n\x0ctls_dut_name\x18\x01 \x01(\t\"_\n\x0fTLSClientConfig\x12\x13\n\x0btls_address\x18\x01 \x01(\t\x12\x10\n\x08tls_port\x18\x02 \x01(\x05\x12\x13\n\x0btlw_address\x18\x03 \x01(\t\x12\x10\n\x08tlw_port\x18\x04 \x01(\x05\x42:Z8go.chromium.org/chromiumos/config/go/api/test/rtd/v1;rtdb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.config.api.test.rtd.v1.invocation_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z8go.chromium.org/chromiumos/config/go/api/test/rtd/v1;rtd'
  _INVOCATION._serialized_start=140
  _INVOCATION._serialized_end=452
  _REQUEST._serialized_start=455
  _REQUEST._serialized_end=602
  _REQUEST_ENVIRONMENT._serialized_start=571
  _REQUEST_ENVIRONMENT._serialized_end=602
  _DUT._serialized_start=604
  _DUT._serialized_end=631
  _TLSCLIENTCONFIG._serialized_start=633
  _TLSCLIENTCONFIG._serialized_end=728
# @@protoc_insertion_point(module_scope)
