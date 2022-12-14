# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: test_platform/migration/test_runner/config.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import message as _message
from chromite.third_party.google.protobuf import reflection as _reflection
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='test_platform/migration/test_runner/config.proto',
  package='test_platform.migration.test_runner',
  syntax='proto3',
  serialized_options=b'ZMgo.chromium.org/chromiumos/infra/proto/go/test_platform/migration/test_runner',
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n0test_platform/migration/test_runner/config.proto\x12#test_platform.migration.test_runner\"a\n\x06\x43onfig\x12W\n\x15redirect_instructions\x18\x01 \x03(\x0b\x32\x38.test_platform.migration.test_runner.RedirectInstruction\"~\n\x13RedirectInstruction\x12J\n\nconstraint\x18\x01 \x01(\x0b\x32\x36.test_platform.migration.test_runner.TrafficConstraint\x12\x1b\n\x13percent_of_requests\x18\x02 \x01(\x05\"<\n\x11TrafficConstraint\x12\x10\n\x08\x64ut_pool\x18\x01 \x01(\t\x12\x15\n\rquota_account\x18\x02 \x01(\tBOZMgo.chromium.org/chromiumos/infra/proto/go/test_platform/migration/test_runnerb\x06proto3'
)




_CONFIG = _descriptor.Descriptor(
  name='Config',
  full_name='test_platform.migration.test_runner.Config',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='redirect_instructions', full_name='test_platform.migration.test_runner.Config.redirect_instructions', index=0,
      number=1, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
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
  serialized_start=89,
  serialized_end=186,
)


_REDIRECTINSTRUCTION = _descriptor.Descriptor(
  name='RedirectInstruction',
  full_name='test_platform.migration.test_runner.RedirectInstruction',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='constraint', full_name='test_platform.migration.test_runner.RedirectInstruction.constraint', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='percent_of_requests', full_name='test_platform.migration.test_runner.RedirectInstruction.percent_of_requests', index=1,
      number=2, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
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
  serialized_start=188,
  serialized_end=314,
)


_TRAFFICCONSTRAINT = _descriptor.Descriptor(
  name='TrafficConstraint',
  full_name='test_platform.migration.test_runner.TrafficConstraint',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='dut_pool', full_name='test_platform.migration.test_runner.TrafficConstraint.dut_pool', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='quota_account', full_name='test_platform.migration.test_runner.TrafficConstraint.quota_account', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
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
  serialized_start=316,
  serialized_end=376,
)

_CONFIG.fields_by_name['redirect_instructions'].message_type = _REDIRECTINSTRUCTION
_REDIRECTINSTRUCTION.fields_by_name['constraint'].message_type = _TRAFFICCONSTRAINT
DESCRIPTOR.message_types_by_name['Config'] = _CONFIG
DESCRIPTOR.message_types_by_name['RedirectInstruction'] = _REDIRECTINSTRUCTION
DESCRIPTOR.message_types_by_name['TrafficConstraint'] = _TRAFFICCONSTRAINT
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

Config = _reflection.GeneratedProtocolMessageType('Config', (_message.Message,), {
  'DESCRIPTOR' : _CONFIG,
  '__module__' : 'test_platform.migration.test_runner.config_pb2'
  # @@protoc_insertion_point(class_scope:test_platform.migration.test_runner.Config)
  })
_sym_db.RegisterMessage(Config)

RedirectInstruction = _reflection.GeneratedProtocolMessageType('RedirectInstruction', (_message.Message,), {
  'DESCRIPTOR' : _REDIRECTINSTRUCTION,
  '__module__' : 'test_platform.migration.test_runner.config_pb2'
  # @@protoc_insertion_point(class_scope:test_platform.migration.test_runner.RedirectInstruction)
  })
_sym_db.RegisterMessage(RedirectInstruction)

TrafficConstraint = _reflection.GeneratedProtocolMessageType('TrafficConstraint', (_message.Message,), {
  'DESCRIPTOR' : _TRAFFICCONSTRAINT,
  '__module__' : 'test_platform.migration.test_runner.config_pb2'
  # @@protoc_insertion_point(class_scope:test_platform.migration.test_runner.TrafficConstraint)
  })
_sym_db.RegisterMessage(TrafficConstraint)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)
