# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: config/replication_config.proto

from google.protobuf.internal import enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import field_mask_pb2 as google_dot_protobuf_dot_field__mask__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='config/replication_config.proto',
  package='config',
  syntax='proto3',
  serialized_options=b'Z-go.chromium.org/chromiumos/infra/proto/config',
  serialized_pb=b'\n\x1f\x63onfig/replication_config.proto\x12\x06\x63onfig\x1a google/protobuf/field_mask.proto\"6\n\x15StringReplacementRule\x12\x0e\n\x06\x62\x65\x66ore\x18\x01 \x01(\t\x12\r\n\x05\x61\x66ter\x18\x02 \x01(\t\"\x95\x02\n\x13\x46ileReplicationRule\x12\x13\n\x0bsource_path\x18\x01 \x01(\t\x12\x18\n\x10\x64\x65stination_path\x18\x02 \x01(\t\x12#\n\tfile_type\x18\x03 \x01(\x0e\x32\x10.config.FileType\x12\x31\n\x10replication_type\x18\x04 \x01(\x0e\x32\x17.config.ReplicationType\x12\x36\n\x12\x64\x65stination_fields\x18\x05 \x01(\x0b\x32\x1a.google.protobuf.FieldMask\x12?\n\x18string_replacement_rules\x18\x06 \x03(\x0b\x32\x1d.config.StringReplacementRule\"P\n\x11ReplicationConfig\x12;\n\x16\x66ile_replication_rules\x18\x01 \x03(\x0b\x32\x1b.config.FileReplicationRule*d\n\x08\x46ileType\x12\x19\n\x15\x46ILE_TYPE_UNSPECIFIED\x10\x00\x12\x12\n\x0e\x46ILE_TYPE_JSON\x10\x01\x12\x14\n\x10\x46ILE_TYPE_JSONPB\x10\x02\x12\x13\n\x0f\x46ILE_TYPE_OTHER\x10\x03*k\n\x0fReplicationType\x12 \n\x1cREPLICATION_TYPE_UNSPECIFIED\x10\x00\x12\x19\n\x15REPLICATION_TYPE_COPY\x10\x01\x12\x1b\n\x17REPLICATION_TYPE_FILTER\x10\x02\x42/Z-go.chromium.org/chromiumos/infra/proto/configb\x06proto3'
  ,
  dependencies=[google_dot_protobuf_dot_field__mask__pb2.DESCRIPTOR,])

_FILETYPE = _descriptor.EnumDescriptor(
  name='FileType',
  full_name='config.FileType',
  filename=None,
  file=DESCRIPTOR,
  values=[
    _descriptor.EnumValueDescriptor(
      name='FILE_TYPE_UNSPECIFIED', index=0, number=0,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='FILE_TYPE_JSON', index=1, number=1,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='FILE_TYPE_JSONPB', index=2, number=2,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='FILE_TYPE_OTHER', index=3, number=3,
      serialized_options=None,
      type=None),
  ],
  containing_type=None,
  serialized_options=None,
  serialized_start=495,
  serialized_end=595,
)
_sym_db.RegisterEnumDescriptor(_FILETYPE)

FileType = enum_type_wrapper.EnumTypeWrapper(_FILETYPE)
_REPLICATIONTYPE = _descriptor.EnumDescriptor(
  name='ReplicationType',
  full_name='config.ReplicationType',
  filename=None,
  file=DESCRIPTOR,
  values=[
    _descriptor.EnumValueDescriptor(
      name='REPLICATION_TYPE_UNSPECIFIED', index=0, number=0,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='REPLICATION_TYPE_COPY', index=1, number=1,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='REPLICATION_TYPE_FILTER', index=2, number=2,
      serialized_options=None,
      type=None),
  ],
  containing_type=None,
  serialized_options=None,
  serialized_start=597,
  serialized_end=704,
)
_sym_db.RegisterEnumDescriptor(_REPLICATIONTYPE)

ReplicationType = enum_type_wrapper.EnumTypeWrapper(_REPLICATIONTYPE)
FILE_TYPE_UNSPECIFIED = 0
FILE_TYPE_JSON = 1
FILE_TYPE_JSONPB = 2
FILE_TYPE_OTHER = 3
REPLICATION_TYPE_UNSPECIFIED = 0
REPLICATION_TYPE_COPY = 1
REPLICATION_TYPE_FILTER = 2



_STRINGREPLACEMENTRULE = _descriptor.Descriptor(
  name='StringReplacementRule',
  full_name='config.StringReplacementRule',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='before', full_name='config.StringReplacementRule.before', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='after', full_name='config.StringReplacementRule.after', index=1,
      number=2, type=9, cpp_type=9, label=1,
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
  serialized_start=77,
  serialized_end=131,
)


_FILEREPLICATIONRULE = _descriptor.Descriptor(
  name='FileReplicationRule',
  full_name='config.FileReplicationRule',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='source_path', full_name='config.FileReplicationRule.source_path', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='destination_path', full_name='config.FileReplicationRule.destination_path', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='file_type', full_name='config.FileReplicationRule.file_type', index=2,
      number=3, type=14, cpp_type=8, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='replication_type', full_name='config.FileReplicationRule.replication_type', index=3,
      number=4, type=14, cpp_type=8, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='destination_fields', full_name='config.FileReplicationRule.destination_fields', index=4,
      number=5, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='string_replacement_rules', full_name='config.FileReplicationRule.string_replacement_rules', index=5,
      number=6, type=11, cpp_type=10, label=3,
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
  serialized_start=134,
  serialized_end=411,
)


_REPLICATIONCONFIG = _descriptor.Descriptor(
  name='ReplicationConfig',
  full_name='config.ReplicationConfig',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='file_replication_rules', full_name='config.ReplicationConfig.file_replication_rules', index=0,
      number=1, type=11, cpp_type=10, label=3,
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
  serialized_start=413,
  serialized_end=493,
)

_FILEREPLICATIONRULE.fields_by_name['file_type'].enum_type = _FILETYPE
_FILEREPLICATIONRULE.fields_by_name['replication_type'].enum_type = _REPLICATIONTYPE
_FILEREPLICATIONRULE.fields_by_name['destination_fields'].message_type = google_dot_protobuf_dot_field__mask__pb2._FIELDMASK
_FILEREPLICATIONRULE.fields_by_name['string_replacement_rules'].message_type = _STRINGREPLACEMENTRULE
_REPLICATIONCONFIG.fields_by_name['file_replication_rules'].message_type = _FILEREPLICATIONRULE
DESCRIPTOR.message_types_by_name['StringReplacementRule'] = _STRINGREPLACEMENTRULE
DESCRIPTOR.message_types_by_name['FileReplicationRule'] = _FILEREPLICATIONRULE
DESCRIPTOR.message_types_by_name['ReplicationConfig'] = _REPLICATIONCONFIG
DESCRIPTOR.enum_types_by_name['FileType'] = _FILETYPE
DESCRIPTOR.enum_types_by_name['ReplicationType'] = _REPLICATIONTYPE
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

StringReplacementRule = _reflection.GeneratedProtocolMessageType('StringReplacementRule', (_message.Message,), {
  'DESCRIPTOR' : _STRINGREPLACEMENTRULE,
  '__module__' : 'config.replication_config_pb2'
  # @@protoc_insertion_point(class_scope:config.StringReplacementRule)
  })
_sym_db.RegisterMessage(StringReplacementRule)

FileReplicationRule = _reflection.GeneratedProtocolMessageType('FileReplicationRule', (_message.Message,), {
  'DESCRIPTOR' : _FILEREPLICATIONRULE,
  '__module__' : 'config.replication_config_pb2'
  # @@protoc_insertion_point(class_scope:config.FileReplicationRule)
  })
_sym_db.RegisterMessage(FileReplicationRule)

ReplicationConfig = _reflection.GeneratedProtocolMessageType('ReplicationConfig', (_message.Message,), {
  'DESCRIPTOR' : _REPLICATIONCONFIG,
  '__module__' : 'config.replication_config_pb2'
  # @@protoc_insertion_point(class_scope:config.ReplicationConfig)
  })
_sym_db.RegisterMessage(ReplicationConfig)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)
