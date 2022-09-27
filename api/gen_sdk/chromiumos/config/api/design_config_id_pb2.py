# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/design_config_id.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='chromiumos/config/api/design_config_id.proto',
  package='chromiumos.config.api',
  syntax='proto3',
  serialized_options=b'Z(go.chromium.org/chromiumos/config/go/api',
  serialized_pb=b'\n,chromiumos/config/api/design_config_id.proto\x12\x15\x63hromiumos.config.api\"\x9f\x01\n\x0e\x44\x65signConfigId\x12\r\n\x05value\x18\x01 \x01(\t\x1a~\n\nScanConfig\x12\x1b\n\x11smbios_name_match\x18\x01 \x01(\tH\x00\x12&\n\x1c\x64\x65vice_tree_compatible_match\x18\x02 \x01(\tH\x00\x12\x14\n\x0c\x66irmware_sku\x18\x03 \x01(\rB\x15\n\x13\x66irmware_name_matchB*Z(go.chromium.org/chromiumos/config/go/apib\x06proto3'
)




_DESIGNCONFIGID_SCANCONFIG = _descriptor.Descriptor(
  name='ScanConfig',
  full_name='chromiumos.config.api.DesignConfigId.ScanConfig',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='smbios_name_match', full_name='chromiumos.config.api.DesignConfigId.ScanConfig.smbios_name_match', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='device_tree_compatible_match', full_name='chromiumos.config.api.DesignConfigId.ScanConfig.device_tree_compatible_match', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='firmware_sku', full_name='chromiumos.config.api.DesignConfigId.ScanConfig.firmware_sku', index=2,
      number=3, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
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
    _descriptor.OneofDescriptor(
      name='firmware_name_match', full_name='chromiumos.config.api.DesignConfigId.ScanConfig.firmware_name_match',
      index=0, containing_type=None, fields=[]),
  ],
  serialized_start=105,
  serialized_end=231,
)

_DESIGNCONFIGID = _descriptor.Descriptor(
  name='DesignConfigId',
  full_name='chromiumos.config.api.DesignConfigId',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='value', full_name='chromiumos.config.api.DesignConfigId.value', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[_DESIGNCONFIGID_SCANCONFIG, ],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=72,
  serialized_end=231,
)

_DESIGNCONFIGID_SCANCONFIG.containing_type = _DESIGNCONFIGID
_DESIGNCONFIGID_SCANCONFIG.oneofs_by_name['firmware_name_match'].fields.append(
  _DESIGNCONFIGID_SCANCONFIG.fields_by_name['smbios_name_match'])
_DESIGNCONFIGID_SCANCONFIG.fields_by_name['smbios_name_match'].containing_oneof = _DESIGNCONFIGID_SCANCONFIG.oneofs_by_name['firmware_name_match']
_DESIGNCONFIGID_SCANCONFIG.oneofs_by_name['firmware_name_match'].fields.append(
  _DESIGNCONFIGID_SCANCONFIG.fields_by_name['device_tree_compatible_match'])
_DESIGNCONFIGID_SCANCONFIG.fields_by_name['device_tree_compatible_match'].containing_oneof = _DESIGNCONFIGID_SCANCONFIG.oneofs_by_name['firmware_name_match']
DESCRIPTOR.message_types_by_name['DesignConfigId'] = _DESIGNCONFIGID
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

DesignConfigId = _reflection.GeneratedProtocolMessageType('DesignConfigId', (_message.Message,), {

  'ScanConfig' : _reflection.GeneratedProtocolMessageType('ScanConfig', (_message.Message,), {
    'DESCRIPTOR' : _DESIGNCONFIGID_SCANCONFIG,
    '__module__' : 'chromiumos.config.api.design_config_id_pb2'
    # @@protoc_insertion_point(class_scope:chromiumos.config.api.DesignConfigId.ScanConfig)
    })
  ,
  'DESCRIPTOR' : _DESIGNCONFIGID,
  '__module__' : 'chromiumos.config.api.design_config_id_pb2'
  # @@protoc_insertion_point(class_scope:chromiumos.config.api.DesignConfigId)
  })
_sym_db.RegisterMessage(DesignConfigId)
_sym_db.RegisterMessage(DesignConfigId.ScanConfig)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)