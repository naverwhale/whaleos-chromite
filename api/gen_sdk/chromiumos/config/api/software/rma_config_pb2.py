# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/software/rma_config.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n/chromiumos/config/api/software/rma_config.proto\x12\x1e\x63hromiumos.config.api.software\"\xb0\x04\n\tRmaConfig\x12\x0f\n\x07\x65nabled\x18\x01 \x01(\x08\x12\x0f\n\x07has_cbi\x18\x02 \x01(\x08\x12I\n\x0bssfc_config\x18\x03 \x01(\x0b\x32\x34.chromiumos.config.api.software.RmaConfig.SsfcConfig\x12\x1f\n\x17use_legacy_custom_label\x18\x04 \x01(\x08\x1a\x94\x03\n\nSsfcConfig\x12\x0c\n\x04mask\x18\x01 \x01(\r\x12l\n\x16\x63omponent_type_configs\x18\x02 \x03(\x0b\x32L.chromiumos.config.api.software.RmaConfig.SsfcConfig.SsfcComponentTypeConfig\x1a\x89\x02\n\x17SsfcComponentTypeConfig\x12\x16\n\x0e\x63omponent_type\x18\x01 \x01(\t\x12\x15\n\rdefault_value\x18\x02 \x01(\r\x12\x81\x01\n\x14probeable_components\x18\x03 \x03(\x0b\x32\x63.chromiumos.config.api.software.RmaConfig.SsfcConfig.SsfcComponentTypeConfig.SsfcProbeableComponent\x1a;\n\x16SsfcProbeableComponent\x12\x12\n\nidentifier\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\rB3Z1go.chromium.org/chromiumos/config/go/api/softwareb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.config.api.software.rma_config_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z1go.chromium.org/chromiumos/config/go/api/software'
  _RMACONFIG._serialized_start=84
  _RMACONFIG._serialized_end=644
  _RMACONFIG_SSFCCONFIG._serialized_start=240
  _RMACONFIG_SSFCCONFIG._serialized_end=644
  _RMACONFIG_SSFCCONFIG_SSFCCOMPONENTTYPECONFIG._serialized_start=379
  _RMACONFIG_SSFCCONFIG_SSFCCOMPONENTTYPECONFIG._serialized_end=644
  _RMACONFIG_SSFCCONFIG_SSFCCOMPONENTTYPECONFIG_SSFCPROBEABLECOMPONENT._serialized_start=585
  _RMACONFIG_SSFCCONFIG_SSFCCOMPONENTTYPECONFIG_SSFCPROBEABLECOMPONENT._serialized_end=644
# @@protoc_insertion_point(module_scope)
