# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: test_platform/multibot/requests.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import message as _message
from chromite.third_party.google.protobuf import reflection as _reflection
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.test_platform.phosphorus import prejob_pb2 as test__platform_dot_phosphorus_dot_prejob__pb2
from chromite.api.gen.test_platform.multibot import common_pb2 as test__platform_dot_multibot_dot_common__pb2
from chromite.api.gen.test_platform import request_pb2 as test__platform_dot_request__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='test_platform/multibot/requests.proto',
  package='test_platform.multibot',
  syntax='proto3',
  serialized_options=b'Z@go.chromium.org/chromiumos/infra/proto/go/test_platform/multibot',
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n%test_platform/multibot/requests.proto\x12\x16test_platform.multibot\x1a%test_platform/phosphorus/prejob.proto\x1a#test_platform/multibot/common.proto\x1a\x1btest_platform/request.proto\"{\n\rLeaderRequest\x12,\n\x07payload\x18\x01 \x01(\x0b\x32\x1b.test_platform.Request.Test\x12<\n\x0e\x66ollower_specs\x18\x02 \x03(\x0b\x32$.test_platform.multibot.FollowerSpec\"\x8b\x03\n\x0f\x46ollowerRequest\x12\x19\n\x11subscription_name\x18\x01 \x01(\t\x12T\n\x0fincoming_filter\x18\x02 \x03(\x0b\x32;.test_platform.multibot.FollowerRequest.IncomingFilterEntry\x12\\\n\x13outgoing_attributes\x18\x03 \x03(\x0b\x32?.test_platform.multibot.FollowerRequest.OutgoingAttributesEntry\x12\x37\n\x06prejob\x18\x04 \x01(\x0b\x32\'.test_platform.phosphorus.PrejobRequest\x1a\x35\n\x13IncomingFilterEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\x1a\x39\n\x17OutgoingAttributesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\x42\x42Z@go.chromium.org/chromiumos/infra/proto/go/test_platform/multibotb\x06proto3'
  ,
  dependencies=[test__platform_dot_phosphorus_dot_prejob__pb2.DESCRIPTOR,test__platform_dot_multibot_dot_common__pb2.DESCRIPTOR,test__platform_dot_request__pb2.DESCRIPTOR,])




_LEADERREQUEST = _descriptor.Descriptor(
  name='LeaderRequest',
  full_name='test_platform.multibot.LeaderRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='payload', full_name='test_platform.multibot.LeaderRequest.payload', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='follower_specs', full_name='test_platform.multibot.LeaderRequest.follower_specs', index=1,
      number=2, type=11, cpp_type=10, label=3,
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
  serialized_start=170,
  serialized_end=293,
)


_FOLLOWERREQUEST_INCOMINGFILTERENTRY = _descriptor.Descriptor(
  name='IncomingFilterEntry',
  full_name='test_platform.multibot.FollowerRequest.IncomingFilterEntry',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='key', full_name='test_platform.multibot.FollowerRequest.IncomingFilterEntry.key', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='value', full_name='test_platform.multibot.FollowerRequest.IncomingFilterEntry.value', index=1,
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
  serialized_options=b'8\001',
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=579,
  serialized_end=632,
)

_FOLLOWERREQUEST_OUTGOINGATTRIBUTESENTRY = _descriptor.Descriptor(
  name='OutgoingAttributesEntry',
  full_name='test_platform.multibot.FollowerRequest.OutgoingAttributesEntry',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='key', full_name='test_platform.multibot.FollowerRequest.OutgoingAttributesEntry.key', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='value', full_name='test_platform.multibot.FollowerRequest.OutgoingAttributesEntry.value', index=1,
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
  serialized_options=b'8\001',
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=634,
  serialized_end=691,
)

_FOLLOWERREQUEST = _descriptor.Descriptor(
  name='FollowerRequest',
  full_name='test_platform.multibot.FollowerRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='subscription_name', full_name='test_platform.multibot.FollowerRequest.subscription_name', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='incoming_filter', full_name='test_platform.multibot.FollowerRequest.incoming_filter', index=1,
      number=2, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='outgoing_attributes', full_name='test_platform.multibot.FollowerRequest.outgoing_attributes', index=2,
      number=3, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='prejob', full_name='test_platform.multibot.FollowerRequest.prejob', index=3,
      number=4, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[_FOLLOWERREQUEST_INCOMINGFILTERENTRY, _FOLLOWERREQUEST_OUTGOINGATTRIBUTESENTRY, ],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=296,
  serialized_end=691,
)

_LEADERREQUEST.fields_by_name['payload'].message_type = test__platform_dot_request__pb2._REQUEST_TEST
_LEADERREQUEST.fields_by_name['follower_specs'].message_type = test__platform_dot_multibot_dot_common__pb2._FOLLOWERSPEC
_FOLLOWERREQUEST_INCOMINGFILTERENTRY.containing_type = _FOLLOWERREQUEST
_FOLLOWERREQUEST_OUTGOINGATTRIBUTESENTRY.containing_type = _FOLLOWERREQUEST
_FOLLOWERREQUEST.fields_by_name['incoming_filter'].message_type = _FOLLOWERREQUEST_INCOMINGFILTERENTRY
_FOLLOWERREQUEST.fields_by_name['outgoing_attributes'].message_type = _FOLLOWERREQUEST_OUTGOINGATTRIBUTESENTRY
_FOLLOWERREQUEST.fields_by_name['prejob'].message_type = test__platform_dot_phosphorus_dot_prejob__pb2._PREJOBREQUEST
DESCRIPTOR.message_types_by_name['LeaderRequest'] = _LEADERREQUEST
DESCRIPTOR.message_types_by_name['FollowerRequest'] = _FOLLOWERREQUEST
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

LeaderRequest = _reflection.GeneratedProtocolMessageType('LeaderRequest', (_message.Message,), {
  'DESCRIPTOR' : _LEADERREQUEST,
  '__module__' : 'test_platform.multibot.requests_pb2'
  # @@protoc_insertion_point(class_scope:test_platform.multibot.LeaderRequest)
  })
_sym_db.RegisterMessage(LeaderRequest)

FollowerRequest = _reflection.GeneratedProtocolMessageType('FollowerRequest', (_message.Message,), {

  'IncomingFilterEntry' : _reflection.GeneratedProtocolMessageType('IncomingFilterEntry', (_message.Message,), {
    'DESCRIPTOR' : _FOLLOWERREQUEST_INCOMINGFILTERENTRY,
    '__module__' : 'test_platform.multibot.requests_pb2'
    # @@protoc_insertion_point(class_scope:test_platform.multibot.FollowerRequest.IncomingFilterEntry)
    })
  ,

  'OutgoingAttributesEntry' : _reflection.GeneratedProtocolMessageType('OutgoingAttributesEntry', (_message.Message,), {
    'DESCRIPTOR' : _FOLLOWERREQUEST_OUTGOINGATTRIBUTESENTRY,
    '__module__' : 'test_platform.multibot.requests_pb2'
    # @@protoc_insertion_point(class_scope:test_platform.multibot.FollowerRequest.OutgoingAttributesEntry)
    })
  ,
  'DESCRIPTOR' : _FOLLOWERREQUEST,
  '__module__' : 'test_platform.multibot.requests_pb2'
  # @@protoc_insertion_point(class_scope:test_platform.multibot.FollowerRequest)
  })
_sym_db.RegisterMessage(FollowerRequest)
_sym_db.RegisterMessage(FollowerRequest.IncomingFilterEntry)
_sym_db.RegisterMessage(FollowerRequest.OutgoingAttributesEntry)


DESCRIPTOR._options = None
_FOLLOWERREQUEST_INCOMINGFILTERENTRY._options = None
_FOLLOWERREQUEST_OUTGOINGATTRIBUTESENTRY._options = None
# @@protoc_insertion_point(module_scope)
