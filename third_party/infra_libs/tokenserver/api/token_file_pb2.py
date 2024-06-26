# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: go.chromium.org/luci/tokenserver/api/token_file.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import message as _message
from chromite.third_party.google.protobuf import reflection as _reflection
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='go.chromium.org/luci/tokenserver/api/token_file.proto',
  package='tokenserver',
  syntax='proto3',
  serialized_options=b'Z0go.chromium.org/luci/tokenserver/api;tokenserver',
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n5go.chromium.org/luci/tokenserver/api/token_file.proto\x12\x0btokenserver\"\xf3\x02\n\tTokenFile\x12\"\n\x0c\x61\x63\x63\x65ss_token\x18\x01 \x01(\tR\x0c\x61\x63\x63\x65ss_token\x12\x1e\n\ntoken_type\x18\x02 \x01(\tR\ntoken_type\x12.\n\x12luci_machine_token\x18\x03 \x01(\tR\x12luci_machine_token\x12\x16\n\x06\x65xpiry\x18\x04 \x01(\x03R\x06\x65xpiry\x12 \n\x0blast_update\x18\x05 \x01(\x03R\x0blast_update\x12 \n\x0bnext_update\x18\x06 \x01(\x03R\x0bnext_update\x12\x34\n\x15service_account_email\x18\x07 \x01(\tR\x15service_account_email\x12<\n\x19service_account_unique_id\x18\x08 \x01(\tR\x19service_account_unique_id\x12\"\n\x0ctokend_state\x18\x32 \x01(\x0cR\x0ctokend_stateB2Z0go.chromium.org/luci/tokenserver/api;tokenserverb\x06proto3'
)




_TOKENFILE = _descriptor.Descriptor(
  name='TokenFile',
  full_name='tokenserver.TokenFile',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='access_token', full_name='tokenserver.TokenFile.access_token', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, json_name='access_token', file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='token_type', full_name='tokenserver.TokenFile.token_type', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, json_name='token_type', file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='luci_machine_token', full_name='tokenserver.TokenFile.luci_machine_token', index=2,
      number=3, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, json_name='luci_machine_token', file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='expiry', full_name='tokenserver.TokenFile.expiry', index=3,
      number=4, type=3, cpp_type=2, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, json_name='expiry', file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='last_update', full_name='tokenserver.TokenFile.last_update', index=4,
      number=5, type=3, cpp_type=2, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, json_name='last_update', file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='next_update', full_name='tokenserver.TokenFile.next_update', index=5,
      number=6, type=3, cpp_type=2, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, json_name='next_update', file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='service_account_email', full_name='tokenserver.TokenFile.service_account_email', index=6,
      number=7, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, json_name='service_account_email', file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='service_account_unique_id', full_name='tokenserver.TokenFile.service_account_unique_id', index=7,
      number=8, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, json_name='service_account_unique_id', file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='tokend_state', full_name='tokenserver.TokenFile.tokend_state', index=8,
      number=50, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=b"",
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, json_name='tokend_state', file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
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
  serialized_start=71,
  serialized_end=442,
)

DESCRIPTOR.message_types_by_name['TokenFile'] = _TOKENFILE
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

TokenFile = _reflection.GeneratedProtocolMessageType('TokenFile', (_message.Message,), {
  'DESCRIPTOR' : _TOKENFILE,
  '__module__' : 'go.chromium.org.luci.tokenserver.api.token_file_pb2'
  # @@protoc_insertion_point(class_scope:tokenserver.TokenFile)
  })
_sym_db.RegisterMessage(TokenFile)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)
