# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/lab/api/tape_service.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n*chromiumos/test/lab/api/tape_service.proto\x12\x17\x63hromiumos.test.lab.api\"s\n\x0f\x43\x61llTapeRequest\x12\x18\n\x10request_endpoint\x18\x01 \x01(\t\x12\x16\n\x0erequest_method\x18\x02 \x01(\t\x12\x17\n\x0frequest_timeout\x18\x03 \x01(\x05\x12\x15\n\rpayload_bytes\x18\x04 \x01(\x0c\")\n\x10\x43\x61llTapeResponse\x12\x15\n\rpayload_bytes\x18\x01 \x01(\x0c\x32n\n\x0bTapeService\x12_\n\x08\x43\x61llTape\x12(.chromiumos.test.lab.api.CallTapeRequest\x1a).chromiumos.test.lab.api.CallTapeResponseB3Z1go.chromium.org/chromiumos/config/go/test/lab/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.lab.api.tape_service_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z1go.chromium.org/chromiumos/config/go/test/lab/api'
  _CALLTAPEREQUEST._serialized_start=71
  _CALLTAPEREQUEST._serialized_end=186
  _CALLTAPERESPONSE._serialized_start=188
  _CALLTAPERESPONSE._serialized_end=229
  _TAPESERVICE._serialized_start=231
  _TAPESERVICE._serialized_end=341
# @@protoc_insertion_point(module_scope)
