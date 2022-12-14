# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/repo_cache_state.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import message as _message
from chromite.third_party.google.protobuf import reflection as _reflection
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='chromiumos/repo_cache_state.proto',
  package='chromiumos',
  syntax='proto3',
  serialized_options=b'\n!com.google.chrome.crosinfra.protoZ4go.chromium.org/chromiumos/infra/proto/go/chromiumos',
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n!chromiumos/repo_cache_state.proto\x12\nchromiumos\"\xbc\x01\n\tRepoState\x12*\n\x05state\x18\x01 \x01(\x0e\x32\x1b.chromiumos.RepoState.State\x12\x17\n\x0fmanifest_branch\x18\x02 \x01(\t\x12\x14\n\x0cmanifest_url\x18\x03 \x01(\t\"T\n\x05State\x12\x15\n\x11STATE_UNSPECIFIED\x10\x00\x12\x0f\n\x0bSTATE_CLEAN\x10\x01\x12\x0f\n\x0bSTATE_DIRTY\x10\x02\x12\x12\n\x0eSTATE_RECOVERY\x10\x03\x42Y\n!com.google.chrome.crosinfra.protoZ4go.chromium.org/chromiumos/infra/proto/go/chromiumosb\x06proto3'
)



_REPOSTATE_STATE = _descriptor.EnumDescriptor(
  name='State',
  full_name='chromiumos.RepoState.State',
  filename=None,
  file=DESCRIPTOR,
  create_key=_descriptor._internal_create_key,
  values=[
    _descriptor.EnumValueDescriptor(
      name='STATE_UNSPECIFIED', index=0, number=0,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
    _descriptor.EnumValueDescriptor(
      name='STATE_CLEAN', index=1, number=1,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
    _descriptor.EnumValueDescriptor(
      name='STATE_DIRTY', index=2, number=2,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
    _descriptor.EnumValueDescriptor(
      name='STATE_RECOVERY', index=3, number=3,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
  ],
  containing_type=None,
  serialized_options=None,
  serialized_start=154,
  serialized_end=238,
)
_sym_db.RegisterEnumDescriptor(_REPOSTATE_STATE)


_REPOSTATE = _descriptor.Descriptor(
  name='RepoState',
  full_name='chromiumos.RepoState',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='state', full_name='chromiumos.RepoState.state', index=0,
      number=1, type=14, cpp_type=8, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='manifest_branch', full_name='chromiumos.RepoState.manifest_branch', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='manifest_url', full_name='chromiumos.RepoState.manifest_url', index=2,
      number=3, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
    _REPOSTATE_STATE,
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=50,
  serialized_end=238,
)

_REPOSTATE.fields_by_name['state'].enum_type = _REPOSTATE_STATE
_REPOSTATE_STATE.containing_type = _REPOSTATE
DESCRIPTOR.message_types_by_name['RepoState'] = _REPOSTATE
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

RepoState = _reflection.GeneratedProtocolMessageType('RepoState', (_message.Message,), {
  'DESCRIPTOR' : _REPOSTATE,
  '__module__' : 'chromiumos.repo_cache_state_pb2'
  # @@protoc_insertion_point(class_scope:chromiumos.RepoState)
  })
_sym_db.RegisterMessage(RepoState)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)
