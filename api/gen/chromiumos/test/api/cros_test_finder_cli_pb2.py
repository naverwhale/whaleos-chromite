# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/api/cros_test_finder_cli.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import message as _message
from chromite.third_party.google.protobuf import reflection as _reflection
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.test.api import test_suite_pb2 as chromiumos_dot_test_dot_api_dot_test__suite__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='chromiumos/test/api/cros_test_finder_cli.proto',
  package='chromiumos.test.api',
  syntax='proto3',
  serialized_options=b'Z-go.chromium.org/chromiumos/config/go/test/api',
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n.chromiumos/test/api/cros_test_finder_cli.proto\x12\x13\x63hromiumos.test.api\x1a$chromiumos/test/api/test_suite.proto\"L\n\x15\x43rosTestFinderRequest\x12\x33\n\x0btest_suites\x18\x01 \x03(\x0b\x32\x1e.chromiumos.test.api.TestSuite\"M\n\x16\x43rosTestFinderResponse\x12\x33\n\x0btest_suites\x18\x01 \x03(\x0b\x32\x1e.chromiumos.test.api.TestSuiteB/Z-go.chromium.org/chromiumos/config/go/test/apib\x06proto3'
  ,
  dependencies=[chromiumos_dot_test_dot_api_dot_test__suite__pb2.DESCRIPTOR,])




_CROSTESTFINDERREQUEST = _descriptor.Descriptor(
  name='CrosTestFinderRequest',
  full_name='chromiumos.test.api.CrosTestFinderRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='test_suites', full_name='chromiumos.test.api.CrosTestFinderRequest.test_suites', index=0,
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
  serialized_start=109,
  serialized_end=185,
)


_CROSTESTFINDERRESPONSE = _descriptor.Descriptor(
  name='CrosTestFinderResponse',
  full_name='chromiumos.test.api.CrosTestFinderResponse',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='test_suites', full_name='chromiumos.test.api.CrosTestFinderResponse.test_suites', index=0,
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
  serialized_start=187,
  serialized_end=264,
)

_CROSTESTFINDERREQUEST.fields_by_name['test_suites'].message_type = chromiumos_dot_test_dot_api_dot_test__suite__pb2._TESTSUITE
_CROSTESTFINDERRESPONSE.fields_by_name['test_suites'].message_type = chromiumos_dot_test_dot_api_dot_test__suite__pb2._TESTSUITE
DESCRIPTOR.message_types_by_name['CrosTestFinderRequest'] = _CROSTESTFINDERREQUEST
DESCRIPTOR.message_types_by_name['CrosTestFinderResponse'] = _CROSTESTFINDERRESPONSE
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

CrosTestFinderRequest = _reflection.GeneratedProtocolMessageType('CrosTestFinderRequest', (_message.Message,), {
  'DESCRIPTOR' : _CROSTESTFINDERREQUEST,
  '__module__' : 'chromiumos.test.api.cros_test_finder_cli_pb2'
  # @@protoc_insertion_point(class_scope:chromiumos.test.api.CrosTestFinderRequest)
  })
_sym_db.RegisterMessage(CrosTestFinderRequest)

CrosTestFinderResponse = _reflection.GeneratedProtocolMessageType('CrosTestFinderResponse', (_message.Message,), {
  'DESCRIPTOR' : _CROSTESTFINDERRESPONSE,
  '__module__' : 'chromiumos.test.api.cros_test_finder_cli_pb2'
  # @@protoc_insertion_point(class_scope:chromiumos.test.api.CrosTestFinderResponse)
  })
_sym_db.RegisterMessage(CrosTestFinderResponse)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)
