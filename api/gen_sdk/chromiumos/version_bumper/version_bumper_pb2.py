# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/version_bumper/version_bumper.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='chromiumos/version_bumper/version_bumper.proto',
  package='chromiumos.version_bumper',
  syntax='proto3',
  serialized_options=b'\n!com.google.chrome.crosinfra.protoZCgo.chromium.org/chromiumos/infra/proto/go/chromiumos/version_bumper',
  serialized_pb=b'\n.chromiumos/version_bumper/version_bumper.proto\x12\x19\x63hromiumos.version_bumper\"\xae\x02\n\x12\x42umpVersionRequest\x12\x1d\n\x15\x63hromiumosOverlayRepo\x18\x01 \x01(\t\x12W\n\x0f\x63omponentToBump\x18\x02 \x01(\x0e\x32>.chromiumos.version_bumper.BumpVersionRequest.VersionComponent\"\x9f\x01\n\x10VersionComponent\x12\x1e\n\x1a\x43OMPONENT_TYPE_UNSPECIFIED\x10\x00\x12\x1c\n\x18\x43OMPONENT_TYPE_MILESTONE\x10\x01\x12\x18\n\x14\x43OMPONENT_TYPE_BUILD\x10\x02\x12\x19\n\x15\x43OMPONENT_TYPE_BRANCH\x10\x03\x12\x18\n\x14\x43OMPONENT_TYPE_PATCH\x10\x04\"5\n\x13\x42umpVersionResponse\x12\x1e\n\x16\x65rror_summary_markdown\x18\x01 \x01(\tBh\n!com.google.chrome.crosinfra.protoZCgo.chromium.org/chromiumos/infra/proto/go/chromiumos/version_bumperb\x06proto3'
)



_BUMPVERSIONREQUEST_VERSIONCOMPONENT = _descriptor.EnumDescriptor(
  name='VersionComponent',
  full_name='chromiumos.version_bumper.BumpVersionRequest.VersionComponent',
  filename=None,
  file=DESCRIPTOR,
  values=[
    _descriptor.EnumValueDescriptor(
      name='COMPONENT_TYPE_UNSPECIFIED', index=0, number=0,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='COMPONENT_TYPE_MILESTONE', index=1, number=1,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='COMPONENT_TYPE_BUILD', index=2, number=2,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='COMPONENT_TYPE_BRANCH', index=3, number=3,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='COMPONENT_TYPE_PATCH', index=4, number=4,
      serialized_options=None,
      type=None),
  ],
  containing_type=None,
  serialized_options=None,
  serialized_start=221,
  serialized_end=380,
)
_sym_db.RegisterEnumDescriptor(_BUMPVERSIONREQUEST_VERSIONCOMPONENT)


_BUMPVERSIONREQUEST = _descriptor.Descriptor(
  name='BumpVersionRequest',
  full_name='chromiumos.version_bumper.BumpVersionRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='chromiumosOverlayRepo', full_name='chromiumos.version_bumper.BumpVersionRequest.chromiumosOverlayRepo', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='componentToBump', full_name='chromiumos.version_bumper.BumpVersionRequest.componentToBump', index=1,
      number=2, type=14, cpp_type=8, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
    _BUMPVERSIONREQUEST_VERSIONCOMPONENT,
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=78,
  serialized_end=380,
)


_BUMPVERSIONRESPONSE = _descriptor.Descriptor(
  name='BumpVersionResponse',
  full_name='chromiumos.version_bumper.BumpVersionResponse',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='error_summary_markdown', full_name='chromiumos.version_bumper.BumpVersionResponse.error_summary_markdown', index=0,
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
  serialized_start=382,
  serialized_end=435,
)

_BUMPVERSIONREQUEST.fields_by_name['componentToBump'].enum_type = _BUMPVERSIONREQUEST_VERSIONCOMPONENT
_BUMPVERSIONREQUEST_VERSIONCOMPONENT.containing_type = _BUMPVERSIONREQUEST
DESCRIPTOR.message_types_by_name['BumpVersionRequest'] = _BUMPVERSIONREQUEST
DESCRIPTOR.message_types_by_name['BumpVersionResponse'] = _BUMPVERSIONRESPONSE
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

BumpVersionRequest = _reflection.GeneratedProtocolMessageType('BumpVersionRequest', (_message.Message,), {
  'DESCRIPTOR' : _BUMPVERSIONREQUEST,
  '__module__' : 'chromiumos.version_bumper.version_bumper_pb2'
  # @@protoc_insertion_point(class_scope:chromiumos.version_bumper.BumpVersionRequest)
  })
_sym_db.RegisterMessage(BumpVersionRequest)

BumpVersionResponse = _reflection.GeneratedProtocolMessageType('BumpVersionResponse', (_message.Message,), {
  'DESCRIPTOR' : _BUMPVERSIONRESPONSE,
  '__module__' : 'chromiumos.version_bumper.version_bumper_pb2'
  # @@protoc_insertion_point(class_scope:chromiumos.version_bumper.BumpVersionResponse)
  })
_sym_db.RegisterMessage(BumpVersionResponse)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)
