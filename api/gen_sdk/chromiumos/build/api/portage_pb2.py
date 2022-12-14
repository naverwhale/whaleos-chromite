# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/build/api/portage.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='chromiumos/build/api/portage.proto',
  package='chromiumos.build.api',
  syntax='proto3',
  serialized_options=b'Z.go.chromium.org/chromiumos/config/go/build/api',
  serialized_pb=b'\n\"chromiumos/build/api/portage.proto\x12\x14\x63hromiumos.build.api\"\xad\x01\n\x07Portage\x1a^\n\x0b\x42uildTarget\x12\x14\n\x0coverlay_name\x18\x01 \x01(\t\x12\x14\n\x0cprofile_name\x18\x02 \x01(\t\x12\x11\n\tuse_flags\x18\x03 \x03(\t\x12\x10\n\x08\x66\x65\x61tures\x18\x04 \x03(\t\x1a\x42\n\x07Package\x12\x14\n\x0cpackage_name\x18\x01 \x01(\t\x12\x10\n\x08\x63\x61tegory\x18\x02 \x01(\t\x12\x0f\n\x07version\x18\x03 \x01(\tB0Z.go.chromium.org/chromiumos/config/go/build/apib\x06proto3'
)




_PORTAGE_BUILDTARGET = _descriptor.Descriptor(
  name='BuildTarget',
  full_name='chromiumos.build.api.Portage.BuildTarget',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='overlay_name', full_name='chromiumos.build.api.Portage.BuildTarget.overlay_name', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='profile_name', full_name='chromiumos.build.api.Portage.BuildTarget.profile_name', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='use_flags', full_name='chromiumos.build.api.Portage.BuildTarget.use_flags', index=2,
      number=3, type=9, cpp_type=9, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='features', full_name='chromiumos.build.api.Portage.BuildTarget.features', index=3,
      number=4, type=9, cpp_type=9, label=3,
      has_default_value=False, default_value=[],
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
  serialized_start=72,
  serialized_end=166,
)

_PORTAGE_PACKAGE = _descriptor.Descriptor(
  name='Package',
  full_name='chromiumos.build.api.Portage.Package',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='package_name', full_name='chromiumos.build.api.Portage.Package.package_name', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='category', full_name='chromiumos.build.api.Portage.Package.category', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='version', full_name='chromiumos.build.api.Portage.Package.version', index=2,
      number=3, type=9, cpp_type=9, label=1,
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
  serialized_start=168,
  serialized_end=234,
)

_PORTAGE = _descriptor.Descriptor(
  name='Portage',
  full_name='chromiumos.build.api.Portage',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
  ],
  extensions=[
  ],
  nested_types=[_PORTAGE_BUILDTARGET, _PORTAGE_PACKAGE, ],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=61,
  serialized_end=234,
)

_PORTAGE_BUILDTARGET.containing_type = _PORTAGE
_PORTAGE_PACKAGE.containing_type = _PORTAGE
DESCRIPTOR.message_types_by_name['Portage'] = _PORTAGE
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

Portage = _reflection.GeneratedProtocolMessageType('Portage', (_message.Message,), {

  'BuildTarget' : _reflection.GeneratedProtocolMessageType('BuildTarget', (_message.Message,), {
    'DESCRIPTOR' : _PORTAGE_BUILDTARGET,
    '__module__' : 'chromiumos.build.api.portage_pb2'
    # @@protoc_insertion_point(class_scope:chromiumos.build.api.Portage.BuildTarget)
    })
  ,

  'Package' : _reflection.GeneratedProtocolMessageType('Package', (_message.Message,), {
    'DESCRIPTOR' : _PORTAGE_PACKAGE,
    '__module__' : 'chromiumos.build.api.portage_pb2'
    # @@protoc_insertion_point(class_scope:chromiumos.build.api.Portage.Package)
    })
  ,
  'DESCRIPTOR' : _PORTAGE,
  '__module__' : 'chromiumos.build.api.portage_pb2'
  # @@protoc_insertion_point(class_scope:chromiumos.build.api.Portage)
  })
_sym_db.RegisterMessage(Portage)
_sym_db.RegisterMessage(Portage.BuildTarget)
_sym_db.RegisterMessage(Portage.Package)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)
