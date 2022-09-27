# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/software/brand_config.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen_sdk.chromiumos.config.api import device_brand_id_pb2 as chromiumos_dot_config_dot_api_dot_device__brand__id__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='chromiumos/config/api/software/brand_config.proto',
  package='chromiumos.config.api.software',
  syntax='proto3',
  serialized_options=b'Z1go.chromium.org/chromiumos/config/go/api/software',
  serialized_pb=b'\n1chromiumos/config/api/software/brand_config.proto\x12\x1e\x63hromiumos.config.api.software\x1a+chromiumos/config/api/device_brand_id.proto\"\xd1\x01\n\x0b\x42randConfig\x12\x36\n\x08\x62rand_id\x18\x01 \x01(\x0b\x32$.chromiumos.config.api.DeviceBrandId\x12\x44\n\x0bscan_config\x18\x02 \x01(\x0b\x32/.chromiumos.config.api.DeviceBrandId.ScanConfig\x12\x11\n\twallpaper\x18\x03 \x01(\t\x12\x18\n\x10regulatory_label\x18\x04 \x01(\t\x12\x17\n\x0fhelp_content_id\x18\x05 \x01(\tB3Z1go.chromium.org/chromiumos/config/go/api/softwareb\x06proto3'
  ,
  dependencies=[chromiumos_dot_config_dot_api_dot_device__brand__id__pb2.DESCRIPTOR,])




_BRANDCONFIG = _descriptor.Descriptor(
  name='BrandConfig',
  full_name='chromiumos.config.api.software.BrandConfig',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='brand_id', full_name='chromiumos.config.api.software.BrandConfig.brand_id', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='scan_config', full_name='chromiumos.config.api.software.BrandConfig.scan_config', index=1,
      number=2, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='wallpaper', full_name='chromiumos.config.api.software.BrandConfig.wallpaper', index=2,
      number=3, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='regulatory_label', full_name='chromiumos.config.api.software.BrandConfig.regulatory_label', index=3,
      number=4, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='help_content_id', full_name='chromiumos.config.api.software.BrandConfig.help_content_id', index=4,
      number=5, type=9, cpp_type=9, label=1,
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
  serialized_start=131,
  serialized_end=340,
)

_BRANDCONFIG.fields_by_name['brand_id'].message_type = chromiumos_dot_config_dot_api_dot_device__brand__id__pb2._DEVICEBRANDID
_BRANDCONFIG.fields_by_name['scan_config'].message_type = chromiumos_dot_config_dot_api_dot_device__brand__id__pb2._DEVICEBRANDID_SCANCONFIG
DESCRIPTOR.message_types_by_name['BrandConfig'] = _BRANDCONFIG
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

BrandConfig = _reflection.GeneratedProtocolMessageType('BrandConfig', (_message.Message,), {
  'DESCRIPTOR' : _BRANDCONFIG,
  '__module__' : 'chromiumos.config.api.software.brand_config_pb2'
  # @@protoc_insertion_point(class_scope:chromiumos.config.api.software.BrandConfig)
  })
_sym_db.RegisterMessage(BrandConfig)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)