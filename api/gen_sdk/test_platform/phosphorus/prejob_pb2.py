# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: test_platform/phosphorus/prejob.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2
from chromite.api.gen_sdk.test_platform.phosphorus import common_pb2 as test__platform_dot_phosphorus_dot_common__pb2
from chromite.api.gen_sdk.test_platform import request_pb2 as test__platform_dot_request__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='test_platform/phosphorus/prejob.proto',
  package='test_platform.phosphorus',
  syntax='proto3',
  serialized_options=b'ZBgo.chromium.org/chromiumos/infra/proto/go/test_platform/phosphorus',
  serialized_pb=b'\n%test_platform/phosphorus/prejob.proto\x12\x18test_platform.phosphorus\x1a\x1fgoogle/protobuf/timestamp.proto\x1a%test_platform/phosphorus/common.proto\x1a\x1btest_platform/request.proto\"\xc0\x07\n\rPrejobRequest\x12\x30\n\x06\x63onfig\x18\x01 \x01(\x0b\x32 .test_platform.phosphorus.Config\x12\x14\n\x0c\x64ut_hostname\x18\x02 \x01(\t\x12\x62\n\x14provisionable_labels\x18\x03 \x03(\x0b\x32@.test_platform.phosphorus.PrejobRequest.ProvisionableLabelsEntryB\x02\x18\x01\x12q\n\x1c\x64\x65sired_provisionable_labels\x18\x04 \x03(\x0b\x32G.test_platform.phosphorus.PrejobRequest.DesiredProvisionableLabelsEntryB\x02\x18\x01\x12O\n\x15software_dependencies\x18\x08 \x03(\x0b\x32\x30.test_platform.Request.Params.SoftwareDependency\x12o\n\x1d\x65xisting_provisionable_labels\x18\x05 \x03(\x0b\x32H.test_platform.phosphorus.PrejobRequest.ExistingProvisionableLabelsEntry\x12,\n\x08\x64\x65\x61\x64line\x18\x06 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12\x0f\n\x07use_tls\x18\x07 \x01(\x08\x12R\n\x11\x61\x64\x64tional_targets\x18\t \x03(\x0b\x32\x37.test_platform.phosphorus.PrejobRequest.ProvisionTarget\x1a:\n\x18ProvisionableLabelsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\x1a\x41\n\x1f\x44\x65siredProvisionableLabelsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\x1a\x42\n ExistingProvisionableLabelsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\x1ax\n\x0fProvisionTarget\x12\x14\n\x0c\x64ut_hostname\x18\x01 \x01(\t\x12O\n\x15software_dependencies\x18\x02 \x03(\x0b\x32\x30.test_platform.Request.Params.SoftwareDependency\"\xa6\x01\n\x0ePrejobResponse\x12=\n\x05state\x18\x01 \x01(\x0e\x32..test_platform.phosphorus.PrejobResponse.State\"U\n\x05State\x12\x15\n\x11STATE_UNSPECIFIED\x10\x00\x12\r\n\tSUCCEEDED\x10\x01\x12\n\n\x06\x46\x41ILED\x10\x02\x12\r\n\tTIMED_OUT\x10\x03\x12\x0b\n\x07\x41\x42ORTED\x10\x04\x42\x44ZBgo.chromium.org/chromiumos/infra/proto/go/test_platform/phosphorusb\x06proto3'
  ,
  dependencies=[google_dot_protobuf_dot_timestamp__pb2.DESCRIPTOR,test__platform_dot_phosphorus_dot_common__pb2.DESCRIPTOR,test__platform_dot_request__pb2.DESCRIPTOR,])



_PREJOBRESPONSE_STATE = _descriptor.EnumDescriptor(
  name='State',
  full_name='test_platform.phosphorus.PrejobResponse.State',
  filename=None,
  file=DESCRIPTOR,
  values=[
    _descriptor.EnumValueDescriptor(
      name='STATE_UNSPECIFIED', index=0, number=0,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='SUCCEEDED', index=1, number=1,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='FAILED', index=2, number=2,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='TIMED_OUT', index=3, number=3,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='ABORTED', index=4, number=4,
      serialized_options=None,
      type=None),
  ],
  containing_type=None,
  serialized_options=None,
  serialized_start=1213,
  serialized_end=1298,
)
_sym_db.RegisterEnumDescriptor(_PREJOBRESPONSE_STATE)


_PREJOBREQUEST_PROVISIONABLELABELSENTRY = _descriptor.Descriptor(
  name='ProvisionableLabelsEntry',
  full_name='test_platform.phosphorus.PrejobRequest.ProvisionableLabelsEntry',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='key', full_name='test_platform.phosphorus.PrejobRequest.ProvisionableLabelsEntry.key', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='value', full_name='test_platform.phosphorus.PrejobRequest.ProvisionableLabelsEntry.value', index=1,
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
  serialized_options=b'8\001',
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=814,
  serialized_end=872,
)

_PREJOBREQUEST_DESIREDPROVISIONABLELABELSENTRY = _descriptor.Descriptor(
  name='DesiredProvisionableLabelsEntry',
  full_name='test_platform.phosphorus.PrejobRequest.DesiredProvisionableLabelsEntry',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='key', full_name='test_platform.phosphorus.PrejobRequest.DesiredProvisionableLabelsEntry.key', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='value', full_name='test_platform.phosphorus.PrejobRequest.DesiredProvisionableLabelsEntry.value', index=1,
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
  serialized_options=b'8\001',
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=874,
  serialized_end=939,
)

_PREJOBREQUEST_EXISTINGPROVISIONABLELABELSENTRY = _descriptor.Descriptor(
  name='ExistingProvisionableLabelsEntry',
  full_name='test_platform.phosphorus.PrejobRequest.ExistingProvisionableLabelsEntry',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='key', full_name='test_platform.phosphorus.PrejobRequest.ExistingProvisionableLabelsEntry.key', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='value', full_name='test_platform.phosphorus.PrejobRequest.ExistingProvisionableLabelsEntry.value', index=1,
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
  serialized_options=b'8\001',
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=941,
  serialized_end=1007,
)

_PREJOBREQUEST_PROVISIONTARGET = _descriptor.Descriptor(
  name='ProvisionTarget',
  full_name='test_platform.phosphorus.PrejobRequest.ProvisionTarget',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='dut_hostname', full_name='test_platform.phosphorus.PrejobRequest.ProvisionTarget.dut_hostname', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='software_dependencies', full_name='test_platform.phosphorus.PrejobRequest.ProvisionTarget.software_dependencies', index=1,
      number=2, type=11, cpp_type=10, label=3,
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
  serialized_start=1009,
  serialized_end=1129,
)

_PREJOBREQUEST = _descriptor.Descriptor(
  name='PrejobRequest',
  full_name='test_platform.phosphorus.PrejobRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='config', full_name='test_platform.phosphorus.PrejobRequest.config', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='dut_hostname', full_name='test_platform.phosphorus.PrejobRequest.dut_hostname', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='provisionable_labels', full_name='test_platform.phosphorus.PrejobRequest.provisionable_labels', index=2,
      number=3, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=b'\030\001', file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='desired_provisionable_labels', full_name='test_platform.phosphorus.PrejobRequest.desired_provisionable_labels', index=3,
      number=4, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=b'\030\001', file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='software_dependencies', full_name='test_platform.phosphorus.PrejobRequest.software_dependencies', index=4,
      number=8, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='existing_provisionable_labels', full_name='test_platform.phosphorus.PrejobRequest.existing_provisionable_labels', index=5,
      number=5, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='deadline', full_name='test_platform.phosphorus.PrejobRequest.deadline', index=6,
      number=6, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='use_tls', full_name='test_platform.phosphorus.PrejobRequest.use_tls', index=7,
      number=7, type=8, cpp_type=7, label=1,
      has_default_value=False, default_value=False,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='addtional_targets', full_name='test_platform.phosphorus.PrejobRequest.addtional_targets', index=8,
      number=9, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[_PREJOBREQUEST_PROVISIONABLELABELSENTRY, _PREJOBREQUEST_DESIREDPROVISIONABLELABELSENTRY, _PREJOBREQUEST_EXISTINGPROVISIONABLELABELSENTRY, _PREJOBREQUEST_PROVISIONTARGET, ],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=169,
  serialized_end=1129,
)


_PREJOBRESPONSE = _descriptor.Descriptor(
  name='PrejobResponse',
  full_name='test_platform.phosphorus.PrejobResponse',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='state', full_name='test_platform.phosphorus.PrejobResponse.state', index=0,
      number=1, type=14, cpp_type=8, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
    _PREJOBRESPONSE_STATE,
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=1132,
  serialized_end=1298,
)

_PREJOBREQUEST_PROVISIONABLELABELSENTRY.containing_type = _PREJOBREQUEST
_PREJOBREQUEST_DESIREDPROVISIONABLELABELSENTRY.containing_type = _PREJOBREQUEST
_PREJOBREQUEST_EXISTINGPROVISIONABLELABELSENTRY.containing_type = _PREJOBREQUEST
_PREJOBREQUEST_PROVISIONTARGET.fields_by_name['software_dependencies'].message_type = test__platform_dot_request__pb2._REQUEST_PARAMS_SOFTWAREDEPENDENCY
_PREJOBREQUEST_PROVISIONTARGET.containing_type = _PREJOBREQUEST
_PREJOBREQUEST.fields_by_name['config'].message_type = test__platform_dot_phosphorus_dot_common__pb2._CONFIG
_PREJOBREQUEST.fields_by_name['provisionable_labels'].message_type = _PREJOBREQUEST_PROVISIONABLELABELSENTRY
_PREJOBREQUEST.fields_by_name['desired_provisionable_labels'].message_type = _PREJOBREQUEST_DESIREDPROVISIONABLELABELSENTRY
_PREJOBREQUEST.fields_by_name['software_dependencies'].message_type = test__platform_dot_request__pb2._REQUEST_PARAMS_SOFTWAREDEPENDENCY
_PREJOBREQUEST.fields_by_name['existing_provisionable_labels'].message_type = _PREJOBREQUEST_EXISTINGPROVISIONABLELABELSENTRY
_PREJOBREQUEST.fields_by_name['deadline'].message_type = google_dot_protobuf_dot_timestamp__pb2._TIMESTAMP
_PREJOBREQUEST.fields_by_name['addtional_targets'].message_type = _PREJOBREQUEST_PROVISIONTARGET
_PREJOBRESPONSE.fields_by_name['state'].enum_type = _PREJOBRESPONSE_STATE
_PREJOBRESPONSE_STATE.containing_type = _PREJOBRESPONSE
DESCRIPTOR.message_types_by_name['PrejobRequest'] = _PREJOBREQUEST
DESCRIPTOR.message_types_by_name['PrejobResponse'] = _PREJOBRESPONSE
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

PrejobRequest = _reflection.GeneratedProtocolMessageType('PrejobRequest', (_message.Message,), {

  'ProvisionableLabelsEntry' : _reflection.GeneratedProtocolMessageType('ProvisionableLabelsEntry', (_message.Message,), {
    'DESCRIPTOR' : _PREJOBREQUEST_PROVISIONABLELABELSENTRY,
    '__module__' : 'test_platform.phosphorus.prejob_pb2'
    # @@protoc_insertion_point(class_scope:test_platform.phosphorus.PrejobRequest.ProvisionableLabelsEntry)
    })
  ,

  'DesiredProvisionableLabelsEntry' : _reflection.GeneratedProtocolMessageType('DesiredProvisionableLabelsEntry', (_message.Message,), {
    'DESCRIPTOR' : _PREJOBREQUEST_DESIREDPROVISIONABLELABELSENTRY,
    '__module__' : 'test_platform.phosphorus.prejob_pb2'
    # @@protoc_insertion_point(class_scope:test_platform.phosphorus.PrejobRequest.DesiredProvisionableLabelsEntry)
    })
  ,

  'ExistingProvisionableLabelsEntry' : _reflection.GeneratedProtocolMessageType('ExistingProvisionableLabelsEntry', (_message.Message,), {
    'DESCRIPTOR' : _PREJOBREQUEST_EXISTINGPROVISIONABLELABELSENTRY,
    '__module__' : 'test_platform.phosphorus.prejob_pb2'
    # @@protoc_insertion_point(class_scope:test_platform.phosphorus.PrejobRequest.ExistingProvisionableLabelsEntry)
    })
  ,

  'ProvisionTarget' : _reflection.GeneratedProtocolMessageType('ProvisionTarget', (_message.Message,), {
    'DESCRIPTOR' : _PREJOBREQUEST_PROVISIONTARGET,
    '__module__' : 'test_platform.phosphorus.prejob_pb2'
    # @@protoc_insertion_point(class_scope:test_platform.phosphorus.PrejobRequest.ProvisionTarget)
    })
  ,
  'DESCRIPTOR' : _PREJOBREQUEST,
  '__module__' : 'test_platform.phosphorus.prejob_pb2'
  # @@protoc_insertion_point(class_scope:test_platform.phosphorus.PrejobRequest)
  })
_sym_db.RegisterMessage(PrejobRequest)
_sym_db.RegisterMessage(PrejobRequest.ProvisionableLabelsEntry)
_sym_db.RegisterMessage(PrejobRequest.DesiredProvisionableLabelsEntry)
_sym_db.RegisterMessage(PrejobRequest.ExistingProvisionableLabelsEntry)
_sym_db.RegisterMessage(PrejobRequest.ProvisionTarget)

PrejobResponse = _reflection.GeneratedProtocolMessageType('PrejobResponse', (_message.Message,), {
  'DESCRIPTOR' : _PREJOBRESPONSE,
  '__module__' : 'test_platform.phosphorus.prejob_pb2'
  # @@protoc_insertion_point(class_scope:test_platform.phosphorus.PrejobResponse)
  })
_sym_db.RegisterMessage(PrejobResponse)


DESCRIPTOR._options = None
_PREJOBREQUEST_PROVISIONABLELABELSENTRY._options = None
_PREJOBREQUEST_DESIREDPROVISIONABLELABELSENTRY._options = None
_PREJOBREQUEST_EXISTINGPROVISIONABLELABELSENTRY._options = None
_PREJOBREQUEST.fields_by_name['provisionable_labels']._options = None
_PREJOBREQUEST.fields_by_name['desired_provisionable_labels']._options = None
# @@protoc_insertion_point(module_scope)
