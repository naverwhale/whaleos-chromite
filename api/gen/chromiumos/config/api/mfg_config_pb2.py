# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/mfg_config.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import message as _message
from chromite.third_party.google.protobuf import reflection as _reflection
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.config.api import component_package_pb2 as chromiumos_dot_config_dot_api_dot_component__package__pb2
from chromite.api.gen.chromiumos.config.api import mfg_config_id_pb2 as chromiumos_dot_config_dot_api_dot_mfg__config__id__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='chromiumos/config/api/mfg_config.proto',
  package='chromiumos.config.api',
  syntax='proto3',
  serialized_options=b'Z(go.chromium.org/chromiumos/config/go/api',
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n&chromiumos/config/api/mfg_config.proto\x12\x15\x63hromiumos.config.api\x1a-chromiumos/config/api/component_package.proto\x1a)chromiumos/config/api/mfg_config_id.proto\"\xc2\x01\n\tMfgConfig\x12.\n\x02id\x18\x01 \x01(\x0b\x32\".chromiumos.config.api.MfgConfigId\x12\x12\n\npcb_vendor\x18\x02 \x01(\t\x12\x17\n\x0fram_part_number\x18\x03 \x01(\t\x12\x0e\n\x06region\x18\x04 \x01(\t\x12\x42\n\x11\x63omponent_package\x18\x06 \x01(\x0b\x32\'.chromiumos.config.api.ComponentPackageJ\x04\x08\x05\x10\x06\x42*Z(go.chromium.org/chromiumos/config/go/apib\x06proto3'
  ,
  dependencies=[chromiumos_dot_config_dot_api_dot_component__package__pb2.DESCRIPTOR,chromiumos_dot_config_dot_api_dot_mfg__config__id__pb2.DESCRIPTOR,])




_MFGCONFIG = _descriptor.Descriptor(
  name='MfgConfig',
  full_name='chromiumos.config.api.MfgConfig',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='id', full_name='chromiumos.config.api.MfgConfig.id', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='pcb_vendor', full_name='chromiumos.config.api.MfgConfig.pcb_vendor', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='ram_part_number', full_name='chromiumos.config.api.MfgConfig.ram_part_number', index=2,
      number=3, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='region', full_name='chromiumos.config.api.MfgConfig.region', index=3,
      number=4, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='component_package', full_name='chromiumos.config.api.MfgConfig.component_package', index=4,
      number=6, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
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
  ],
  serialized_start=156,
  serialized_end=350,
)

_MFGCONFIG.fields_by_name['id'].message_type = chromiumos_dot_config_dot_api_dot_mfg__config__id__pb2._MFGCONFIGID
_MFGCONFIG.fields_by_name['component_package'].message_type = chromiumos_dot_config_dot_api_dot_component__package__pb2._COMPONENTPACKAGE
DESCRIPTOR.message_types_by_name['MfgConfig'] = _MFGCONFIG
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

MfgConfig = _reflection.GeneratedProtocolMessageType('MfgConfig', (_message.Message,), {
  'DESCRIPTOR' : _MFGCONFIG,
  '__module__' : 'chromiumos.config.api.mfg_config_pb2'
  # @@protoc_insertion_point(class_scope:chromiumos.config.api.MfgConfig)
  })
_sym_db.RegisterMessage(MfgConfig)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)
