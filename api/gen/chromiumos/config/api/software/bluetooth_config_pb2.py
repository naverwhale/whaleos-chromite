# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/software/bluetooth_config.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import message as _message
from chromite.third_party.google.protobuf import reflection as _reflection
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='chromiumos/config/api/software/bluetooth_config.proto',
  package='chromiumos.config.api.software',
  syntax='proto3',
  serialized_options=b'Z1go.chromium.org/chromiumos/config/go/api/software',
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n5chromiumos/config/api/software/bluetooth_config.proto\x12\x1e\x63hromiumos.config.api.software\"\x8a\x01\n\x0f\x42luetoothConfig\x12I\n\x05\x66lags\x18\x01 \x03(\x0b\x32:.chromiumos.config.api.software.BluetoothConfig.FlagsEntry\x1a,\n\nFlagsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\x08:\x02\x38\x01\x42\x33Z1go.chromium.org/chromiumos/config/go/api/softwareb\x06proto3'
)




_BLUETOOTHCONFIG_FLAGSENTRY = _descriptor.Descriptor(
  name='FlagsEntry',
  full_name='chromiumos.config.api.software.BluetoothConfig.FlagsEntry',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='key', full_name='chromiumos.config.api.software.BluetoothConfig.FlagsEntry.key', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='value', full_name='chromiumos.config.api.software.BluetoothConfig.FlagsEntry.value', index=1,
      number=2, type=8, cpp_type=7, label=1,
      has_default_value=False, default_value=False,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=b'8\001',
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=184,
  serialized_end=228,
)

_BLUETOOTHCONFIG = _descriptor.Descriptor(
  name='BluetoothConfig',
  full_name='chromiumos.config.api.software.BluetoothConfig',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='flags', full_name='chromiumos.config.api.software.BluetoothConfig.flags', index=0,
      number=1, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[_BLUETOOTHCONFIG_FLAGSENTRY, ],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=90,
  serialized_end=228,
)

_BLUETOOTHCONFIG_FLAGSENTRY.containing_type = _BLUETOOTHCONFIG
_BLUETOOTHCONFIG.fields_by_name['flags'].message_type = _BLUETOOTHCONFIG_FLAGSENTRY
DESCRIPTOR.message_types_by_name['BluetoothConfig'] = _BLUETOOTHCONFIG
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

BluetoothConfig = _reflection.GeneratedProtocolMessageType('BluetoothConfig', (_message.Message,), {

  'FlagsEntry' : _reflection.GeneratedProtocolMessageType('FlagsEntry', (_message.Message,), {
    'DESCRIPTOR' : _BLUETOOTHCONFIG_FLAGSENTRY,
    '__module__' : 'chromiumos.config.api.software.bluetooth_config_pb2'
    # @@protoc_insertion_point(class_scope:chromiumos.config.api.software.BluetoothConfig.FlagsEntry)
    })
  ,
  'DESCRIPTOR' : _BLUETOOTHCONFIG,
  '__module__' : 'chromiumos.config.api.software.bluetooth_config_pb2'
  # @@protoc_insertion_point(class_scope:chromiumos.config.api.software.BluetoothConfig)
  })
_sym_db.RegisterMessage(BluetoothConfig)
_sym_db.RegisterMessage(BluetoothConfig.FlagsEntry)


DESCRIPTOR._options = None
_BLUETOOTHCONFIG_FLAGSENTRY._options = None
# @@protoc_insertion_point(module_scope)
