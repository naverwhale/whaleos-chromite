# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/api/publish_service.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.longrunning import operations_pb2 as chromiumos_dot_longrunning_dot_operations__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n)chromiumos/test/api/publish_service.proto\x12\x13\x63hromiumos.test.api\x1a\'chromiumos/longrunning/operations.proto\"B\n\x11UploadToGSRequest\x12\x14\n\x0cgs_directory\x18\x01 \x01(\t\x12\x17\n\x0flocal_directory\x18\x02 \x01(\t\"$\n\x12UploadToGSResponse\x12\x0e\n\x06gs_url\x18\x01 \x01(\t\"\x14\n\x12UploadToGSMetadata2\x97\x01\n\x0ePublishService\x12\x84\x01\n\nUploadToGS\x12&.chromiumos.test.api.UploadToGSRequest\x1a!.chromiumos.longrunning.Operation\"+\xd2\x41(\n\x12UploadToGSResponse\x12\x12UploadToGSMetadataB/Z-go.chromium.org/chromiumos/config/go/test/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.api.publish_service_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z-go.chromium.org/chromiumos/config/go/test/api'
  _PUBLISHSERVICE.methods_by_name['UploadToGS']._options = None
  _PUBLISHSERVICE.methods_by_name['UploadToGS']._serialized_options = b'\322A(\n\022UploadToGSResponse\022\022UploadToGSMetadata'
  _UPLOADTOGSREQUEST._serialized_start=107
  _UPLOADTOGSREQUEST._serialized_end=173
  _UPLOADTOGSRESPONSE._serialized_start=175
  _UPLOADTOGSRESPONSE._serialized_end=211
  _UPLOADTOGSMETADATA._serialized_start=213
  _UPLOADTOGSMETADATA._serialized_end=233
  _PUBLISHSERVICE._serialized_start=236
  _PUBLISHSERVICE._serialized_end=387
# @@protoc_insertion_point(module_scope)
