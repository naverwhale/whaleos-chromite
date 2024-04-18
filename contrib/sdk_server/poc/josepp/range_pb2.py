# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: range.proto

import sys
_b=sys.version_info[0]<3 and (lambda x:x) or (lambda x:x.encode('latin1'))
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
from google.protobuf import descriptor_pb2
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='range.proto',
  package='',
  syntax='proto3',
  serialized_pb=_b('\n\x0brange.proto\"+\n\x0cRangeRequest\x12\r\n\x05start\x18\x01 \x01(\r\x12\x0c\n\x04stop\x18\x02 \x01(\r\"\x1e\n\rRangeResponse\x12\r\n\x05value\x18\x01 \x01(\r2;\n\x0cRangeService\x12+\n\x08GetRange\x12\r.RangeRequest\x1a\x0e.RangeResponse0\x01\x62\x06proto3')
)




_RANGEREQUEST = _descriptor.Descriptor(
  name='RangeRequest',
  full_name='RangeRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='start', full_name='RangeRequest.start', index=0,
      number=1, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='stop', full_name='RangeRequest.stop', index=1,
      number=2, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=15,
  serialized_end=58,
)


_RANGERESPONSE = _descriptor.Descriptor(
  name='RangeResponse',
  full_name='RangeResponse',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='value', full_name='RangeResponse.value', index=0,
      number=1, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=60,
  serialized_end=90,
)

DESCRIPTOR.message_types_by_name['RangeRequest'] = _RANGEREQUEST
DESCRIPTOR.message_types_by_name['RangeResponse'] = _RANGERESPONSE
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

RangeRequest = _reflection.GeneratedProtocolMessageType('RangeRequest', (_message.Message,), dict(
  DESCRIPTOR = _RANGEREQUEST,
  __module__ = 'range_pb2'
  # @@protoc_insertion_point(class_scope:RangeRequest)
  ))
_sym_db.RegisterMessage(RangeRequest)

RangeResponse = _reflection.GeneratedProtocolMessageType('RangeResponse', (_message.Message,), dict(
  DESCRIPTOR = _RANGERESPONSE,
  __module__ = 'range_pb2'
  # @@protoc_insertion_point(class_scope:RangeResponse)
  ))
_sym_db.RegisterMessage(RangeResponse)



_RANGESERVICE = _descriptor.ServiceDescriptor(
  name='RangeService',
  full_name='RangeService',
  file=DESCRIPTOR,
  index=0,
  options=None,
  serialized_start=92,
  serialized_end=151,
  methods=[
  _descriptor.MethodDescriptor(
    name='GetRange',
    full_name='RangeService.GetRange',
    index=0,
    containing_service=None,
    input_type=_RANGEREQUEST,
    output_type=_RANGERESPONSE,
    options=None,
  ),
])
_sym_db.RegisterServiceDescriptor(_RANGESERVICE)

DESCRIPTOR.services_by_name['RangeService'] = _RANGESERVICE

# @@protoc_insertion_point(module_scope)
