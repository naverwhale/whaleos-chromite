# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/test/tls/dependencies/longrunning/operations.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import any_pb2 as google_dot_protobuf_dot_any__pb2
from google.protobuf import descriptor_pb2 as google_dot_protobuf_dot_descriptor__pb2
from google.protobuf import duration_pb2 as google_dot_protobuf_dot_duration__pb2
from google.protobuf import empty_pb2 as google_dot_protobuf_dot_empty__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\nHchromiumos/config/api/test/tls/dependencies/longrunning/operations.proto\x12\x12google.longrunning\x1a\x19google/protobuf/any.proto\x1a google/protobuf/descriptor.proto\x1a\x1egoogle/protobuf/duration.proto\x1a\x1bgoogle/protobuf/empty.proto\"\xb0\x01\n\tOperation\x12\x0c\n\x04name\x18\x01 \x01(\t\x12&\n\x08metadata\x18\x02 \x01(\x0b\x32\x14.google.protobuf.Any\x12\x0c\n\x04\x64one\x18\x03 \x01(\x08\x12+\n\x05\x65rror\x18\x04 \x01(\x0b\x32\x1a.google.longrunning.StatusH\x00\x12(\n\x08response\x18\x05 \x01(\x0b\x32\x14.google.protobuf.AnyH\x00\x42\x08\n\x06result\"#\n\x13GetOperationRequest\x12\x0c\n\x04name\x18\x01 \x01(\t\"\\\n\x15ListOperationsRequest\x12\x0c\n\x04name\x18\x04 \x01(\t\x12\x0e\n\x06\x66ilter\x18\x01 \x01(\t\x12\x11\n\tpage_size\x18\x02 \x01(\x05\x12\x12\n\npage_token\x18\x03 \x01(\t\"d\n\x16ListOperationsResponse\x12\x31\n\noperations\x18\x01 \x03(\x0b\x32\x1d.google.longrunning.Operation\x12\x17\n\x0fnext_page_token\x18\x02 \x01(\t\"&\n\x16\x43\x61ncelOperationRequest\x12\x0c\n\x04name\x18\x01 \x01(\t\"&\n\x16\x44\x65leteOperationRequest\x12\x0c\n\x04name\x18\x01 \x01(\t\"P\n\x14WaitOperationRequest\x12\x0c\n\x04name\x18\x01 \x01(\t\x12*\n\x07timeout\x18\x02 \x01(\x0b\x32\x19.google.protobuf.Duration\"=\n\rOperationInfo\x12\x15\n\rresponse_type\x18\x01 \x01(\t\x12\x15\n\rmetadata_type\x18\x02 \x01(\t\"N\n\x06Status\x12\x0c\n\x04\x63ode\x18\x01 \x01(\x05\x12\x0f\n\x07message\x18\x02 \x01(\t\x12%\n\x07\x64\x65tails\x18\x03 \x03(\x0b\x32\x14.google.protobuf.Any2\xdf\x03\n\nOperations\x12i\n\x0eListOperations\x12).google.longrunning.ListOperationsRequest\x1a*.google.longrunning.ListOperationsResponse\"\x00\x12X\n\x0cGetOperation\x12\'.google.longrunning.GetOperationRequest\x1a\x1d.google.longrunning.Operation\"\x00\x12W\n\x0f\x44\x65leteOperation\x12*.google.longrunning.DeleteOperationRequest\x1a\x16.google.protobuf.Empty\"\x00\x12W\n\x0f\x43\x61ncelOperation\x12*.google.longrunning.CancelOperationRequest\x1a\x16.google.protobuf.Empty\"\x00\x12Z\n\rWaitOperation\x12(.google.longrunning.WaitOperationRequest\x1a\x1d.google.longrunning.Operation\"\x00:Z\n\x0eoperation_info\x12\x1e.google.protobuf.MethodOptions\x18\x99\x08 \x01(\x0b\x32!.google.longrunning.OperationInfoBLZJgo.chromium.org/chromiumos/config/go/api/test/tls/dependencies/longrunningb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.config.api.test.tls.dependencies.longrunning.operations_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:
  google_dot_protobuf_dot_descriptor__pb2.MethodOptions.RegisterExtension(operation_info)

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'ZJgo.chromium.org/chromiumos/config/go/api/test/tls/dependencies/longrunning'
  _OPERATION._serialized_start=219
  _OPERATION._serialized_end=395
  _GETOPERATIONREQUEST._serialized_start=397
  _GETOPERATIONREQUEST._serialized_end=432
  _LISTOPERATIONSREQUEST._serialized_start=434
  _LISTOPERATIONSREQUEST._serialized_end=526
  _LISTOPERATIONSRESPONSE._serialized_start=528
  _LISTOPERATIONSRESPONSE._serialized_end=628
  _CANCELOPERATIONREQUEST._serialized_start=630
  _CANCELOPERATIONREQUEST._serialized_end=668
  _DELETEOPERATIONREQUEST._serialized_start=670
  _DELETEOPERATIONREQUEST._serialized_end=708
  _WAITOPERATIONREQUEST._serialized_start=710
  _WAITOPERATIONREQUEST._serialized_end=790
  _OPERATIONINFO._serialized_start=792
  _OPERATIONINFO._serialized_end=853
  _STATUS._serialized_start=855
  _STATUS._serialized_end=933
  _OPERATIONS._serialized_start=936
  _OPERATIONS._serialized_end=1415
# @@protoc_insertion_point(module_scope)
