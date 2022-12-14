# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/component_package.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import message as _message
from chromite.third_party.google.protobuf import reflection as _reflection
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.config.api import component_pb2 as chromiumos_dot_config_dot_api_dot_component__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='chromiumos/config/api/component_package.proto',
  package='chromiumos.config.api',
  syntax='proto3',
  serialized_options=b'Z(go.chromium.org/chromiumos/config/go/api',
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n-chromiumos/config/api/component_package.proto\x12\x15\x63hromiumos.config.api\x1a%chromiumos/config/api/component.proto\"\xd8\x08\n\x10\x43omponentPackage\x12\x31\n\x03soc\x18\x01 \x01(\x0b\x32$.chromiumos.config.api.Component.Soc\x12\x37\n\x06memory\x18\x02 \x03(\x0b\x32\'.chromiumos.config.api.Component.Memory\x12=\n\tbluetooth\x18\x03 \x01(\x0b\x32*.chromiumos.config.api.Component.Bluetooth\x12\x37\n\x06\x63\x61mera\x18\x04 \x01(\x0b\x32\'.chromiumos.config.api.Component.Camera\x12;\n\x0btouchscreen\x18\x05 \x01(\x0b\x32&.chromiumos.config.api.Component.Touch\x12\x33\n\x04wifi\x18\x06 \x01(\x0b\x32%.chromiumos.config.api.Component.Wifi\x12\x38\n\x08touchpad\x18\x07 \x01(\x0b\x32&.chromiumos.config.api.Component.Touch\x12\x44\n\rdisplay_panel\x18\x08 \x01(\x0b\x32-.chromiumos.config.api.Component.DisplayPanel\x12@\n\x0b\x61udio_codec\x18\t \x01(\x0b\x32+.chromiumos.config.api.Component.AudioCodec\x12\x39\n\x07\x62\x61ttery\x18\n \x01(\x0b\x32(.chromiumos.config.api.Component.Battery\x12\x41\n\rec_flash_chip\x18\x0b \x01(\x0b\x32*.chromiumos.config.api.Component.FlashChip\x12\x45\n\x11system_flash_chip\x18\x0c \x01(\x0b\x32*.chromiumos.config.api.Component.FlashChip\x12?\n\x02\x65\x63\x18\r \x01(\x0b\x32\x33.chromiumos.config.api.Component.EmbeddedController\x12\x39\n\x07storage\x18\x0e \x01(\x0b\x32(.chromiumos.config.api.Component.Storage\x12\x31\n\x03tpm\x18\x0f \x01(\x0b\x32$.chromiumos.config.api.Component.Tpm\x12@\n\x08usb_host\x18\x10 \x01(\x0b\x32..chromiumos.config.api.Component.Interface.Usb\x12\x37\n\x06stylus\x18\x11 \x01(\x0b\x32\'.chromiumos.config.api.Component.Stylus\x12=\n\tamplifier\x18\x12 \x01(\x0b\x32*.chromiumos.config.api.Component.AmplifierB*Z(go.chromium.org/chromiumos/config/go/apib\x06proto3'
  ,
  dependencies=[chromiumos_dot_config_dot_api_dot_component__pb2.DESCRIPTOR,])




_COMPONENTPACKAGE = _descriptor.Descriptor(
  name='ComponentPackage',
  full_name='chromiumos.config.api.ComponentPackage',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='soc', full_name='chromiumos.config.api.ComponentPackage.soc', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='memory', full_name='chromiumos.config.api.ComponentPackage.memory', index=1,
      number=2, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='bluetooth', full_name='chromiumos.config.api.ComponentPackage.bluetooth', index=2,
      number=3, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='camera', full_name='chromiumos.config.api.ComponentPackage.camera', index=3,
      number=4, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='touchscreen', full_name='chromiumos.config.api.ComponentPackage.touchscreen', index=4,
      number=5, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='wifi', full_name='chromiumos.config.api.ComponentPackage.wifi', index=5,
      number=6, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='touchpad', full_name='chromiumos.config.api.ComponentPackage.touchpad', index=6,
      number=7, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='display_panel', full_name='chromiumos.config.api.ComponentPackage.display_panel', index=7,
      number=8, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='audio_codec', full_name='chromiumos.config.api.ComponentPackage.audio_codec', index=8,
      number=9, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='battery', full_name='chromiumos.config.api.ComponentPackage.battery', index=9,
      number=10, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='ec_flash_chip', full_name='chromiumos.config.api.ComponentPackage.ec_flash_chip', index=10,
      number=11, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='system_flash_chip', full_name='chromiumos.config.api.ComponentPackage.system_flash_chip', index=11,
      number=12, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='ec', full_name='chromiumos.config.api.ComponentPackage.ec', index=12,
      number=13, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='storage', full_name='chromiumos.config.api.ComponentPackage.storage', index=13,
      number=14, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='tpm', full_name='chromiumos.config.api.ComponentPackage.tpm', index=14,
      number=15, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='usb_host', full_name='chromiumos.config.api.ComponentPackage.usb_host', index=15,
      number=16, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='stylus', full_name='chromiumos.config.api.ComponentPackage.stylus', index=16,
      number=17, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='amplifier', full_name='chromiumos.config.api.ComponentPackage.amplifier', index=17,
      number=18, type=11, cpp_type=10, label=1,
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
  serialized_start=112,
  serialized_end=1224,
)

_COMPONENTPACKAGE.fields_by_name['soc'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_SOC
_COMPONENTPACKAGE.fields_by_name['memory'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_MEMORY
_COMPONENTPACKAGE.fields_by_name['bluetooth'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_BLUETOOTH
_COMPONENTPACKAGE.fields_by_name['camera'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_CAMERA
_COMPONENTPACKAGE.fields_by_name['touchscreen'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_TOUCH
_COMPONENTPACKAGE.fields_by_name['wifi'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_WIFI
_COMPONENTPACKAGE.fields_by_name['touchpad'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_TOUCH
_COMPONENTPACKAGE.fields_by_name['display_panel'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_DISPLAYPANEL
_COMPONENTPACKAGE.fields_by_name['audio_codec'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_AUDIOCODEC
_COMPONENTPACKAGE.fields_by_name['battery'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_BATTERY
_COMPONENTPACKAGE.fields_by_name['ec_flash_chip'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_FLASHCHIP
_COMPONENTPACKAGE.fields_by_name['system_flash_chip'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_FLASHCHIP
_COMPONENTPACKAGE.fields_by_name['ec'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_EMBEDDEDCONTROLLER
_COMPONENTPACKAGE.fields_by_name['storage'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_STORAGE
_COMPONENTPACKAGE.fields_by_name['tpm'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_TPM
_COMPONENTPACKAGE.fields_by_name['usb_host'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_INTERFACE_USB
_COMPONENTPACKAGE.fields_by_name['stylus'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_STYLUS
_COMPONENTPACKAGE.fields_by_name['amplifier'].message_type = chromiumos_dot_config_dot_api_dot_component__pb2._COMPONENT_AMPLIFIER
DESCRIPTOR.message_types_by_name['ComponentPackage'] = _COMPONENTPACKAGE
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

ComponentPackage = _reflection.GeneratedProtocolMessageType('ComponentPackage', (_message.Message,), {
  'DESCRIPTOR' : _COMPONENTPACKAGE,
  '__module__' : 'chromiumos.config.api.component_package_pb2'
  # @@protoc_insertion_point(class_scope:chromiumos.config.api.ComponentPackage)
  })
_sym_db.RegisterMessage(ComponentPackage)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)
