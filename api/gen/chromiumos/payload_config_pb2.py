# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/payload_config.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1f\x63hromiumos/payload_config.proto\x12\nchromiumos\"=\n\rPayloadConfig\x12,\n\x05\x64\x65lta\x18\x01 \x03(\x0b\x32\x1d.chromiumos.PayloadProperties\"\xf1\x03\n\x11PayloadProperties\x12\x32\n\x05\x62oard\x18\x01 \x01(\x0b\x32#.chromiumos.PayloadProperties.Board\x12;\n\ndelta_type\x18\x02 \x01(\x0e\x32\'.chromiumos.PayloadProperties.DeltaType\x12\x0f\n\x07\x63hannel\x18\x03 \x01(\t\x12\x19\n\x11\x63hrome_os_version\x18\x04 \x01(\t\x12\x16\n\x0e\x63hrome_version\x18\x05 \x01(\t\x12\x11\n\tmilestone\x18\x06 \x01(\r\x12\x16\n\x0egenerate_delta\x18\x07 \x01(\x08\x12\x1b\n\x13\x64\x65lta_payload_tests\x18\x08 \x01(\x08\x12\x1a\n\x12\x66ull_payload_tests\x18\t \x01(\x08\x12\x19\n\x11\x61pplicable_models\x18\n \x03(\t\x1aI\n\x05\x42oard\x12\x17\n\x0fpublic_codename\x18\x01 \x01(\t\x12\x11\n\tis_active\x18\x02 \x01(\x08\x12\x14\n\x0c\x62uilder_name\x18\x03 \x01(\t\"]\n\tDeltaType\x12\x0b\n\x07NOT_SET\x10\x00\x12\x0c\n\x08NO_DELTA\x10\x01\x12\t\n\x05OMAHA\x10\x02\x12\x12\n\x0eSTEPPING_STONE\x10\x03\x12\r\n\tMILESTONE\x10\x04\x12\x07\n\x03\x46SI\x10\x05\x42Y\n!com.google.chrome.crosinfra.protoZ4go.chromium.org/chromiumos/infra/proto/go/chromiumosb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.payload_config_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'\n!com.google.chrome.crosinfra.protoZ4go.chromium.org/chromiumos/infra/proto/go/chromiumos'
  _PAYLOADCONFIG._serialized_start=47
  _PAYLOADCONFIG._serialized_end=108
  _PAYLOADPROPERTIES._serialized_start=111
  _PAYLOADPROPERTIES._serialized_end=608
  _PAYLOADPROPERTIES_BOARD._serialized_start=440
  _PAYLOADPROPERTIES_BOARD._serialized_end=513
  _PAYLOADPROPERTIES_DELTATYPE._serialized_start=515
  _PAYLOADPROPERTIES_DELTATYPE._serialized_end=608
# @@protoc_insertion_point(module_scope)
