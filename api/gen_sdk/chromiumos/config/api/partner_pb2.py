# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/partner.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen_sdk.chromiumos.config.api import partner_id_pb2 as chromiumos_dot_config_dot_api_dot_partner__id__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='chromiumos/config/api/partner.proto',
  package='chromiumos.config.api',
  syntax='proto3',
  serialized_options=b'Z(go.chromium.org/chromiumos/config/go/api',
  serialized_pb=b'\n#chromiumos/config/api/partner.proto\x12\x15\x63hromiumos.config.api\x1a&chromiumos/config/api/partner_id.proto\"\xe4\x03\n\x07Partner\x12,\n\x02id\x18\x01 \x01(\x0b\x32 .chromiumos.config.api.PartnerId\x12\x0c\n\x04name\x18\x02 \x01(\t\x12\x13\n\x0b\x65mail_group\x18\x03 \x01(\t\x12@\n\x0ctouch_vendor\x18\x04 \x01(\x0b\x32*.chromiumos.config.api.Partner.TouchVendor\x12O\n\x14\x64isplay_panel_vendor\x18\x05 \x01(\x0b\x32\x31.chromiumos.config.api.Partner.DisplayPanelVendor\x12\x44\n\x0e\x62\x61ttery_vendor\x18\x06 \x01(\x0b\x32,.chromiumos.config.api.Partner.BatteryVendor\x1a^\n\x0bTouchVendor\x12\x11\n\tvendor_id\x18\x04 \x01(\t\x12\x1b\n\x13symlink_file_format\x18\x05 \x01(\t\x12\x1f\n\x17\x64\x65stination_file_format\x18\x06 \x01(\t\x1a)\n\x12\x44isplayPanelVendor\x12\x13\n\x0bvendor_code\x18\x01 \x01(\t\x1a$\n\rBatteryVendor\x12\x13\n\x0bvendor_name\x18\x04 \x01(\tB*Z(go.chromium.org/chromiumos/config/go/apib\x06proto3'
  ,
  dependencies=[chromiumos_dot_config_dot_api_dot_partner__id__pb2.DESCRIPTOR,])




_PARTNER_TOUCHVENDOR = _descriptor.Descriptor(
  name='TouchVendor',
  full_name='chromiumos.config.api.Partner.TouchVendor',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='vendor_id', full_name='chromiumos.config.api.Partner.TouchVendor.vendor_id', index=0,
      number=4, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='symlink_file_format', full_name='chromiumos.config.api.Partner.TouchVendor.symlink_file_format', index=1,
      number=5, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='destination_file_format', full_name='chromiumos.config.api.Partner.TouchVendor.destination_file_format', index=2,
      number=6, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
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
  ],
  serialized_start=412,
  serialized_end=506,
)

_PARTNER_DISPLAYPANELVENDOR = _descriptor.Descriptor(
  name='DisplayPanelVendor',
  full_name='chromiumos.config.api.Partner.DisplayPanelVendor',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='vendor_code', full_name='chromiumos.config.api.Partner.DisplayPanelVendor.vendor_code', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
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
  ],
  serialized_start=508,
  serialized_end=549,
)

_PARTNER_BATTERYVENDOR = _descriptor.Descriptor(
  name='BatteryVendor',
  full_name='chromiumos.config.api.Partner.BatteryVendor',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='vendor_name', full_name='chromiumos.config.api.Partner.BatteryVendor.vendor_name', index=0,
      number=4, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
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
  ],
  serialized_start=551,
  serialized_end=587,
)

_PARTNER = _descriptor.Descriptor(
  name='Partner',
  full_name='chromiumos.config.api.Partner',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='id', full_name='chromiumos.config.api.Partner.id', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='name', full_name='chromiumos.config.api.Partner.name', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='email_group', full_name='chromiumos.config.api.Partner.email_group', index=2,
      number=3, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='touch_vendor', full_name='chromiumos.config.api.Partner.touch_vendor', index=3,
      number=4, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='display_panel_vendor', full_name='chromiumos.config.api.Partner.display_panel_vendor', index=4,
      number=5, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='battery_vendor', full_name='chromiumos.config.api.Partner.battery_vendor', index=5,
      number=6, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[_PARTNER_TOUCHVENDOR, _PARTNER_DISPLAYPANELVENDOR, _PARTNER_BATTERYVENDOR, ],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=103,
  serialized_end=587,
)

_PARTNER_TOUCHVENDOR.containing_type = _PARTNER
_PARTNER_DISPLAYPANELVENDOR.containing_type = _PARTNER
_PARTNER_BATTERYVENDOR.containing_type = _PARTNER
_PARTNER.fields_by_name['id'].message_type = chromiumos_dot_config_dot_api_dot_partner__id__pb2._PARTNERID
_PARTNER.fields_by_name['touch_vendor'].message_type = _PARTNER_TOUCHVENDOR
_PARTNER.fields_by_name['display_panel_vendor'].message_type = _PARTNER_DISPLAYPANELVENDOR
_PARTNER.fields_by_name['battery_vendor'].message_type = _PARTNER_BATTERYVENDOR
DESCRIPTOR.message_types_by_name['Partner'] = _PARTNER
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

Partner = _reflection.GeneratedProtocolMessageType('Partner', (_message.Message,), {

  'TouchVendor' : _reflection.GeneratedProtocolMessageType('TouchVendor', (_message.Message,), {
    'DESCRIPTOR' : _PARTNER_TOUCHVENDOR,
    '__module__' : 'chromiumos.config.api.partner_pb2'
    # @@protoc_insertion_point(class_scope:chromiumos.config.api.Partner.TouchVendor)
    })
  ,

  'DisplayPanelVendor' : _reflection.GeneratedProtocolMessageType('DisplayPanelVendor', (_message.Message,), {
    'DESCRIPTOR' : _PARTNER_DISPLAYPANELVENDOR,
    '__module__' : 'chromiumos.config.api.partner_pb2'
    # @@protoc_insertion_point(class_scope:chromiumos.config.api.Partner.DisplayPanelVendor)
    })
  ,

  'BatteryVendor' : _reflection.GeneratedProtocolMessageType('BatteryVendor', (_message.Message,), {
    'DESCRIPTOR' : _PARTNER_BATTERYVENDOR,
    '__module__' : 'chromiumos.config.api.partner_pb2'
    # @@protoc_insertion_point(class_scope:chromiumos.config.api.Partner.BatteryVendor)
    })
  ,
  'DESCRIPTOR' : _PARTNER,
  '__module__' : 'chromiumos.config.api.partner_pb2'
  # @@protoc_insertion_point(class_scope:chromiumos.config.api.Partner)
  })
_sym_db.RegisterMessage(Partner)
_sym_db.RegisterMessage(Partner.TouchVendor)
_sym_db.RegisterMessage(Partner.DisplayPanelVendor)
_sym_db.RegisterMessage(Partner.BatteryVendor)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)
