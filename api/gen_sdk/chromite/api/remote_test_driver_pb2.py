# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromite/api/remote_test_driver.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen_sdk.chromite.api import build_api_pb2 as chromite_dot_api_dot_build__api__pb2
from chromite.api.gen_sdk.chromiumos import common_pb2 as chromiumos_dot_common__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='chromite/api/remote_test_driver.proto',
  package='chromite.api',
  syntax='proto3',
  serialized_options=b'Z6go.chromium.org/chromiumos/infra/proto/go/chromite/api',
  serialized_pb=b'\n%chromite/api/remote_test_driver.proto\x12\x0c\x63hromite.api\x1a\x1c\x63hromite/api/build_api.proto\x1a\x17\x63hromiumos/common.proto\"a\n\x0f\x41ssembleRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\x12*\n\ntarget_dir\x18\x02 \x01(\x0b\x32\x16.chromiumos.ResultPath\"O\n\x10\x41ssembleResponse\x12;\n\x13remote_test_drivers\x18\x01 \x03(\x0b\x32\x1e.chromite.api.RemoteTestDriver\";\n\x10RemoteTestDriver\x12\'\n\rbuild_context\x18\x01 \x01(\x0b\x32\x10.chromiumos.Path2\x80\x01\n\x17RemoteTestDriverService\x12I\n\x08\x41ssemble\x12\x1d.chromite.api.AssembleRequest\x1a\x1e.chromite.api.AssembleResponse\x1a\x1a\xc2\xed\x1a\x16\n\x12remote_test_driver\x10\x01\x42\x38Z6go.chromium.org/chromiumos/infra/proto/go/chromite/apib\x06proto3'
  ,
  dependencies=[chromite_dot_api_dot_build__api__pb2.DESCRIPTOR,chromiumos_dot_common__pb2.DESCRIPTOR,])




_ASSEMBLEREQUEST = _descriptor.Descriptor(
  name='AssembleRequest',
  full_name='chromite.api.AssembleRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='chroot', full_name='chromite.api.AssembleRequest.chroot', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='target_dir', full_name='chromite.api.AssembleRequest.target_dir', index=1,
      number=2, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
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
  serialized_start=110,
  serialized_end=207,
)


_ASSEMBLERESPONSE = _descriptor.Descriptor(
  name='AssembleResponse',
  full_name='chromite.api.AssembleResponse',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='remote_test_drivers', full_name='chromite.api.AssembleResponse.remote_test_drivers', index=0,
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
  serialized_start=209,
  serialized_end=288,
)


_REMOTETESTDRIVER = _descriptor.Descriptor(
  name='RemoteTestDriver',
  full_name='chromite.api.RemoteTestDriver',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='build_context', full_name='chromite.api.RemoteTestDriver.build_context', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
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
  serialized_start=290,
  serialized_end=349,
)

_ASSEMBLEREQUEST.fields_by_name['chroot'].message_type = chromiumos_dot_common__pb2._CHROOT
_ASSEMBLEREQUEST.fields_by_name['target_dir'].message_type = chromiumos_dot_common__pb2._RESULTPATH
_ASSEMBLERESPONSE.fields_by_name['remote_test_drivers'].message_type = _REMOTETESTDRIVER
_REMOTETESTDRIVER.fields_by_name['build_context'].message_type = chromiumos_dot_common__pb2._PATH
DESCRIPTOR.message_types_by_name['AssembleRequest'] = _ASSEMBLEREQUEST
DESCRIPTOR.message_types_by_name['AssembleResponse'] = _ASSEMBLERESPONSE
DESCRIPTOR.message_types_by_name['RemoteTestDriver'] = _REMOTETESTDRIVER
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

AssembleRequest = _reflection.GeneratedProtocolMessageType('AssembleRequest', (_message.Message,), {
  'DESCRIPTOR' : _ASSEMBLEREQUEST,
  '__module__' : 'chromite.api.remote_test_driver_pb2'
  # @@protoc_insertion_point(class_scope:chromite.api.AssembleRequest)
  })
_sym_db.RegisterMessage(AssembleRequest)

AssembleResponse = _reflection.GeneratedProtocolMessageType('AssembleResponse', (_message.Message,), {
  'DESCRIPTOR' : _ASSEMBLERESPONSE,
  '__module__' : 'chromite.api.remote_test_driver_pb2'
  # @@protoc_insertion_point(class_scope:chromite.api.AssembleResponse)
  })
_sym_db.RegisterMessage(AssembleResponse)

RemoteTestDriver = _reflection.GeneratedProtocolMessageType('RemoteTestDriver', (_message.Message,), {
  'DESCRIPTOR' : _REMOTETESTDRIVER,
  '__module__' : 'chromite.api.remote_test_driver_pb2'
  # @@protoc_insertion_point(class_scope:chromite.api.RemoteTestDriver)
  })
_sym_db.RegisterMessage(RemoteTestDriver)


DESCRIPTOR._options = None

_REMOTETESTDRIVERSERVICE = _descriptor.ServiceDescriptor(
  name='RemoteTestDriverService',
  full_name='chromite.api.RemoteTestDriverService',
  file=DESCRIPTOR,
  index=0,
  serialized_options=b'\302\355\032\026\n\022remote_test_driver\020\001',
  serialized_start=352,
  serialized_end=480,
  methods=[
  _descriptor.MethodDescriptor(
    name='Assemble',
    full_name='chromite.api.RemoteTestDriverService.Assemble',
    index=0,
    containing_service=None,
    input_type=_ASSEMBLEREQUEST,
    output_type=_ASSEMBLERESPONSE,
    serialized_options=None,
  ),
])
_sym_db.RegisterServiceDescriptor(_REMOTETESTDRIVERSERVICE)

DESCRIPTOR.services_by_name['RemoteTestDriverService'] = _REMOTETESTDRIVERSERVICE

# @@protoc_insertion_point(module_scope)
