# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromite/api/metadata.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen_sdk.chromite.api import build_api_pb2 as chromite_dot_api_dot_build__api__pb2
from chromite.api.gen_sdk.chromite.api import sysroot_pb2 as chromite_dot_api_dot_sysroot__pb2
from chromite.api.gen_sdk.chromiumos import common_pb2 as chromiumos_dot_common__pb2
from chromite.api.gen_sdk.chromiumos.build.api import system_image_pb2 as chromiumos_dot_build_dot_api_dot_system__image__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1b\x63hromite/api/metadata.proto\x12\x0c\x63hromite.api\x1a\x1c\x63hromite/api/build_api.proto\x1a\x1a\x63hromite/api/sysroot.proto\x1a\x17\x63hromiumos/common.proto\x1a\'chromiumos/build/api/system_image.proto\"h\n\x1aSystemImageMetadataRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\x12&\n\x07sysroot\x18\x02 \x01(\x0b\x32\x15.chromite.api.Sysroot\"V\n\x1bSystemImageMetadataResponse\x12\x37\n\x0csystem_image\x18\x01 \x01(\x0b\x32!.chromiumos.build.api.SystemImage2\x8f\x01\n\x0fMetadataService\x12j\n\x13SystemImageMetadata\x12(.chromite.api.SystemImageMetadataRequest\x1a).chromite.api.SystemImageMetadataResponse\x1a\x10\xc2\xed\x1a\x0c\n\x08metadata\x10\x01\x42\x38Z6go.chromium.org/chromiumos/infra/proto/go/chromite/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromite.api.metadata_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z6go.chromium.org/chromiumos/infra/proto/go/chromite/api'
  _METADATASERVICE._options = None
  _METADATASERVICE._serialized_options = b'\302\355\032\014\n\010metadata\020\001'
  _SYSTEMIMAGEMETADATAREQUEST._serialized_start=169
  _SYSTEMIMAGEMETADATAREQUEST._serialized_end=273
  _SYSTEMIMAGEMETADATARESPONSE._serialized_start=275
  _SYSTEMIMAGEMETADATARESPONSE._serialized_end=361
  _METADATASERVICE._serialized_start=364
  _METADATASERVICE._serialized_end=507
# @@protoc_insertion_point(module_scope)