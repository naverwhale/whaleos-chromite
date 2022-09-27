# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/design_config_package.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import message as _message
from chromite.third_party.google.protobuf import reflection as _reflection
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.config.api import design_pb2 as chromiumos_dot_config_dot_api_dot_design__pb2
from chromite.api.gen.chromiumos.config.api import partner_pb2 as chromiumos_dot_config_dot_api_dot_partner__pb2
from chromite.api.gen.chromiumos.config.api import program_pb2 as chromiumos_dot_config_dot_api_dot_program__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='chromiumos/config/api/design_config_package.proto',
  package='chromiumos.config.api',
  syntax='proto3',
  serialized_options=b'Z(go.chromium.org/chromiumos/config/go/api',
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n1chromiumos/config/api/design_config_package.proto\x12\x15\x63hromiumos.config.api\x1a\"chromiumos/config/api/design.proto\x1a#chromiumos/config/api/partner.proto\x1a#chromiumos/config/api/program.proto\"\xdf\x01\n\x13\x44\x65signConfigPackage\x12;\n\rdesign_config\x18\x01 \x01(\x0b\x32$.chromiumos.config.api.Design.Config\x12-\n\x06\x64\x65sign\x18\x02 \x01(\x0b\x32\x1d.chromiumos.config.api.Design\x12+\n\x03odm\x18\x03 \x01(\x0b\x32\x1e.chromiumos.config.api.Partner\x12/\n\x07program\x18\x04 \x01(\x0b\x32\x1e.chromiumos.config.api.ProgramB*Z(go.chromium.org/chromiumos/config/go/apib\x06proto3'
  ,
  dependencies=[chromiumos_dot_config_dot_api_dot_design__pb2.DESCRIPTOR,chromiumos_dot_config_dot_api_dot_partner__pb2.DESCRIPTOR,chromiumos_dot_config_dot_api_dot_program__pb2.DESCRIPTOR,])




_DESIGNCONFIGPACKAGE = _descriptor.Descriptor(
  name='DesignConfigPackage',
  full_name='chromiumos.config.api.DesignConfigPackage',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='design_config', full_name='chromiumos.config.api.DesignConfigPackage.design_config', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='design', full_name='chromiumos.config.api.DesignConfigPackage.design', index=1,
      number=2, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='odm', full_name='chromiumos.config.api.DesignConfigPackage.odm', index=2,
      number=3, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='program', full_name='chromiumos.config.api.DesignConfigPackage.program', index=3,
      number=4, type=11, cpp_type=10, label=1,
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
  serialized_start=187,
  serialized_end=410,
)

_DESIGNCONFIGPACKAGE.fields_by_name['design_config'].message_type = chromiumos_dot_config_dot_api_dot_design__pb2._DESIGN_CONFIG
_DESIGNCONFIGPACKAGE.fields_by_name['design'].message_type = chromiumos_dot_config_dot_api_dot_design__pb2._DESIGN
_DESIGNCONFIGPACKAGE.fields_by_name['odm'].message_type = chromiumos_dot_config_dot_api_dot_partner__pb2._PARTNER
_DESIGNCONFIGPACKAGE.fields_by_name['program'].message_type = chromiumos_dot_config_dot_api_dot_program__pb2._PROGRAM
DESCRIPTOR.message_types_by_name['DesignConfigPackage'] = _DESIGNCONFIGPACKAGE
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

DesignConfigPackage = _reflection.GeneratedProtocolMessageType('DesignConfigPackage', (_message.Message,), {
  'DESCRIPTOR' : _DESIGNCONFIGPACKAGE,
  '__module__' : 'chromiumos.config.api.design_config_package_pb2'
  # @@protoc_insertion_point(class_scope:chromiumos.config.api.DesignConfigPackage)
  })
_sym_db.RegisterMessage(DesignConfigPackage)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)