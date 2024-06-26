# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/api/cros_publish_service.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen_sdk.chromiumos.longrunning import operations_pb2 as chromiumos_dot_longrunning_dot_operations__pb2
from google.protobuf import any_pb2 as google_dot_protobuf_dot_any__pb2
from chromite.api.gen_sdk.chromiumos import storage_path_pb2 as chromiumos_dot_storage__path__pb2
from chromite.api.gen_sdk.chromiumos.test.api import cros_test_cli_pb2 as chromiumos_dot_test_dot_api_dot_cros__test__cli__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n.chromiumos/test/api/cros_publish_service.proto\x12\x13\x63hromiumos.test.api\x1a\'chromiumos/longrunning/operations.proto\x1a\x19google/protobuf/any.proto\x1a\x1d\x63hromiumos/storage_path.proto\x1a\'chromiumos/test/api/cros_test_cli.proto\"\xbf\x01\n\x0ePublishRequest\x12\x32\n\x11\x61rtifact_dir_path\x18\x01 \x01(\x0b\x32\x17.chromiumos.StoragePath\x12<\n\rtest_response\x18\x02 \x01(\x0b\x32%.chromiumos.test.api.CrosTestResponse\x12\x13\n\x0bretry_count\x18\x03 \x01(\x05\x12&\n\x08metadata\x18\x04 \x01(\x0b\x32\x14.google.protobuf.Any\"\xed\x01\n\x0fPublishResponse\x12;\n\x06status\x18\x01 \x01(\x0e\x32+.chromiumos.test.api.PublishResponse.Status\x12\x0f\n\x07message\x18\x02 \x01(\t\x12&\n\x08metadata\x18\x03 \x01(\x0b\x32\x14.google.protobuf.Any\"d\n\x06Status\x12\x16\n\x12STATUS_UNSPECIFIED\x10\x00\x12\x12\n\x0eSTATUS_SUCCESS\x10\x01\x12\x1a\n\x16STATUS_INVALID_REQUEST\x10\x02\x12\x12\n\x0eSTATUS_FAILURE\x10\x03\x32\x91\x01\n\x15GenericPublishService\x12x\n\x07Publish\x12#.chromiumos.test.api.PublishRequest\x1a!.chromiumos.longrunning.Operation\"%\xd2\x41\"\n\x0fPublishResponse\x12\x0fPublishMetadataB/Z-go.chromium.org/chromiumos/config/go/test/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.api.cros_publish_service_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z-go.chromium.org/chromiumos/config/go/test/api'
  _GENERICPUBLISHSERVICE.methods_by_name['Publish']._options = None
  _GENERICPUBLISHSERVICE.methods_by_name['Publish']._serialized_options = b'\322A\"\n\017PublishResponse\022\017PublishMetadata'
  _PUBLISHREQUEST._serialized_start=212
  _PUBLISHREQUEST._serialized_end=403
  _PUBLISHRESPONSE._serialized_start=406
  _PUBLISHRESPONSE._serialized_end=643
  _PUBLISHRESPONSE_STATUS._serialized_start=543
  _PUBLISHRESPONSE_STATUS._serialized_end=643
  _GENERICPUBLISHSERVICE._serialized_start=646
  _GENERICPUBLISHSERVICE._serialized_end=791
# @@protoc_insertion_point(module_scope)
