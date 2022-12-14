# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: test_platform/autotest/dynamic_suite.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen_sdk.chromite.api import test_metadata_pb2 as chromite_dot_api_dot_test__metadata__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='test_platform/autotest/dynamic_suite.proto',
  package='test_platform.autotest',
  syntax='proto3',
  serialized_options=b'Z@go.chromium.org/chromiumos/infra/proto/go/test_platform/autotest',
  serialized_pb=b'\n*test_platform/autotest/dynamic_suite.proto\x12\x16test_platform.autotest\x1a chromite/api/test_metadata.proto\"=\n\x10TestPlatformArgs\x12)\n\x05tests\x18\x01 \x03(\x0b\x32\x1a.chromite.api.AutotestTestBBZ@go.chromium.org/chromiumos/infra/proto/go/test_platform/autotestb\x06proto3'
  ,
  dependencies=[chromite_dot_api_dot_test__metadata__pb2.DESCRIPTOR,])




_TESTPLATFORMARGS = _descriptor.Descriptor(
  name='TestPlatformArgs',
  full_name='test_platform.autotest.TestPlatformArgs',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='tests', full_name='test_platform.autotest.TestPlatformArgs.tests', index=0,
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
  serialized_start=104,
  serialized_end=165,
)

_TESTPLATFORMARGS.fields_by_name['tests'].message_type = chromite_dot_api_dot_test__metadata__pb2._AUTOTESTTEST
DESCRIPTOR.message_types_by_name['TestPlatformArgs'] = _TESTPLATFORMARGS
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

TestPlatformArgs = _reflection.GeneratedProtocolMessageType('TestPlatformArgs', (_message.Message,), {
  'DESCRIPTOR' : _TESTPLATFORMARGS,
  '__module__' : 'test_platform.autotest.dynamic_suite_pb2'
  # @@protoc_insertion_point(class_scope:test_platform.autotest.TestPlatformArgs)
  })
_sym_db.RegisterMessage(TestPlatformArgs)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)
