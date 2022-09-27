# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: test_platform/v2/request.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import message as _message
from chromite.third_party.google.protobuf import reflection as _reflection
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos import common_pb2 as chromiumos_dot_common__pb2
from chromite.api.gen.chromiumos.test.api import coverage_rule_pb2 as chromiumos_dot_test_dot_api_dot_coverage__rule__pb2
from chromite.api.gen.chromiumos.test.api import plan_pb2 as chromiumos_dot_test_dot_api_dot_plan__pb2
from chromite.api.gen.chromiumos.test.api import provision_state_pb2 as chromiumos_dot_test_dot_api_dot_provision__state__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='test_platform/v2/request.proto',
  package='test_platform.v2',
  syntax='proto3',
  serialized_options=b'Z:go.chromium.org/chromiumos/infra/proto/go/test_platform/v2',
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n\x1etest_platform/v2/request.proto\x12\x10test_platform.v2\x1a\x17\x63hromiumos/common.proto\x1a\'chromiumos/test/api/coverage_rule.proto\x1a\x1e\x63hromiumos/test/api/plan.proto\x1a)chromiumos/test/api/provision_state.proto\"y\n\x08TestSpec\x12,\n\x0f\x62uild_directory\x18\x01 \x01(\x0b\x32\x13.chromiumos.GcsPath\x12\x37\n\x0chw_test_plan\x18\x02 \x01(\x0b\x32\x1f.chromiumos.test.api.HWTestPlanH\x00\x42\x06\n\x04spec\"\xe7\x01\n\x07Request\x12,\n\x0f\x62uild_directory\x18\x01 \x01(\x0b\x32\x13.chromiumos.GcsPath\x12.\n\ntest_specs\x18\x02 \x03(\x0b\x32\x1a.test_platform.v2.TestSpec\x12G\n\x12scheduler_settings\x18\x03 \x01(\x0b\x32+.test_platform.v2.Request.SchedulerSettings\x1a\x35\n\x11SchedulerSettings\x12\x0c\n\x04pool\x18\x01 \x01(\t\x12\x12\n\nqs_account\x18\x02 \x01(\tB<Z:go.chromium.org/chromiumos/infra/proto/go/test_platform/v2b\x06proto3'
  ,
  dependencies=[chromiumos_dot_common__pb2.DESCRIPTOR,chromiumos_dot_test_dot_api_dot_coverage__rule__pb2.DESCRIPTOR,chromiumos_dot_test_dot_api_dot_plan__pb2.DESCRIPTOR,chromiumos_dot_test_dot_api_dot_provision__state__pb2.DESCRIPTOR,])




_TESTSPEC = _descriptor.Descriptor(
  name='TestSpec',
  full_name='test_platform.v2.TestSpec',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='build_directory', full_name='test_platform.v2.TestSpec.build_directory', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='hw_test_plan', full_name='test_platform.v2.TestSpec.hw_test_plan', index=1,
      number=2, type=11, cpp_type=10, label=1,
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
    _descriptor.OneofDescriptor(
      name='spec', full_name='test_platform.v2.TestSpec.spec',
      index=0, containing_type=None,
      create_key=_descriptor._internal_create_key,
    fields=[]),
  ],
  serialized_start=193,
  serialized_end=314,
)


_REQUEST_SCHEDULERSETTINGS = _descriptor.Descriptor(
  name='SchedulerSettings',
  full_name='test_platform.v2.Request.SchedulerSettings',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='pool', full_name='test_platform.v2.Request.SchedulerSettings.pool', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='qs_account', full_name='test_platform.v2.Request.SchedulerSettings.qs_account', index=1,
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
  serialized_start=495,
  serialized_end=548,
)

_REQUEST = _descriptor.Descriptor(
  name='Request',
  full_name='test_platform.v2.Request',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='build_directory', full_name='test_platform.v2.Request.build_directory', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='test_specs', full_name='test_platform.v2.Request.test_specs', index=1,
      number=2, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='scheduler_settings', full_name='test_platform.v2.Request.scheduler_settings', index=2,
      number=3, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[_REQUEST_SCHEDULERSETTINGS, ],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=317,
  serialized_end=548,
)

_TESTSPEC.fields_by_name['build_directory'].message_type = chromiumos_dot_common__pb2._GCSPATH
_TESTSPEC.fields_by_name['hw_test_plan'].message_type = chromiumos_dot_test_dot_api_dot_plan__pb2._HWTESTPLAN
_TESTSPEC.oneofs_by_name['spec'].fields.append(
  _TESTSPEC.fields_by_name['hw_test_plan'])
_TESTSPEC.fields_by_name['hw_test_plan'].containing_oneof = _TESTSPEC.oneofs_by_name['spec']
_REQUEST_SCHEDULERSETTINGS.containing_type = _REQUEST
_REQUEST.fields_by_name['build_directory'].message_type = chromiumos_dot_common__pb2._GCSPATH
_REQUEST.fields_by_name['test_specs'].message_type = _TESTSPEC
_REQUEST.fields_by_name['scheduler_settings'].message_type = _REQUEST_SCHEDULERSETTINGS
DESCRIPTOR.message_types_by_name['TestSpec'] = _TESTSPEC
DESCRIPTOR.message_types_by_name['Request'] = _REQUEST
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

TestSpec = _reflection.GeneratedProtocolMessageType('TestSpec', (_message.Message,), {
  'DESCRIPTOR' : _TESTSPEC,
  '__module__' : 'test_platform.v2.request_pb2'
  # @@protoc_insertion_point(class_scope:test_platform.v2.TestSpec)
  })
_sym_db.RegisterMessage(TestSpec)

Request = _reflection.GeneratedProtocolMessageType('Request', (_message.Message,), {

  'SchedulerSettings' : _reflection.GeneratedProtocolMessageType('SchedulerSettings', (_message.Message,), {
    'DESCRIPTOR' : _REQUEST_SCHEDULERSETTINGS,
    '__module__' : 'test_platform.v2.request_pb2'
    # @@protoc_insertion_point(class_scope:test_platform.v2.Request.SchedulerSettings)
    })
  ,
  'DESCRIPTOR' : _REQUEST,
  '__module__' : 'test_platform.v2.request_pb2'
  # @@protoc_insertion_point(class_scope:test_platform.v2.Request)
  })
_sym_db.RegisterMessage(Request)
_sym_db.RegisterMessage(Request.SchedulerSettings)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)