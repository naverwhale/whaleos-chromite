# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/api/instance.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.third_party.google.protobuf import duration_pb2 as google_dot_protobuf_dot_duration__pb2
from chromite.api.gen.chromiumos.test.api import image_pb2 as chromiumos_dot_test_dot_api_dot_image__pb2
from chromite.api.gen.chromiumos.test.api import vm_leaser_pb2 as chromiumos_dot_test_dot_api_dot_vm__leaser__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\"chromiumos/test/api/instance.proto\x12\x13\x63hromiumos.test.api\x1a\x1egoogle/protobuf/duration.proto\x1a\x1f\x63hromiumos/test/api/image.proto\x1a#chromiumos/test/api/vm_leaser.proto\"v\n\nVmInstance\x12\x0c\n\x04name\x18\x01 \x01(\t\x12-\n\x03ssh\x18\x02 \x01(\x0b\x32 .chromiumos.test.api.AddressPort\x12+\n\x06\x63onfig\x18\x03 \x01(\x0b\x32\x1b.chromiumos.test.api.Config\"\xb9\x01\n\x17\x43reateVmInstanceRequest\x12+\n\x06\x63onfig\x18\x01 \x01(\x0b\x32\x1b.chromiumos.test.api.Config\x12\x44\n\x04tags\x18\x02 \x03(\x0b\x32\x36.chromiumos.test.api.CreateVmInstanceRequest.TagsEntry\x1a+\n\tTagsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\"\xca\x01\n\x16ListVmInstancesRequest\x12+\n\x06\x63onfig\x18\x02 \x01(\x0b\x32\x1b.chromiumos.test.api.Config\x12P\n\x0btag_filters\x18\x01 \x03(\x0b\x32;.chromiumos.test.api.ListVmInstancesRequest.TagFiltersEntry\x1a\x31\n\x0fTagFiltersEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\",\n\x0b\x41\x64\x64ressPort\x12\x0f\n\x07\x61\x64\x64ress\x18\x01 \x01(\t\x12\x0c\n\x04port\x18\x02 \x01(\x05\"\x92\x05\n\x06\x43onfig\x12\x43\n\x0egcloud_backend\x18\x01 \x01(\x0b\x32).chromiumos.test.api.Config.GCloudBackendH\x00\x12H\n\x11vm_leaser_backend\x18\x02 \x01(\x0b\x32+.chromiumos.test.api.Config.VmLeaserBackendH\x00\x1a\xdf\x01\n\rGCloudBackend\x12\x0f\n\x07project\x18\x01 \x01(\t\x12\x0c\n\x04zone\x18\x02 \x01(\t\x12\x14\n\x0cmachine_type\x18\x03 \x01(\t\x12\x17\n\x0finstance_prefix\x18\x04 \x01(\t\x12\x0f\n\x07network\x18\x07 \x01(\t\x12\x0e\n\x06subnet\x18\x08 \x01(\t\x12\x11\n\tpublic_ip\x18\x05 \x01(\x08\x12\x1e\n\x16\x61lways_ssh_internal_ip\x18\t \x01(\x08\x12,\n\x05image\x18\x06 \x01(\x0b\x32\x1d.chromiumos.test.api.GceImage\x1a\x8b\x02\n\x0fVmLeaserBackend\x12\x44\n\x03\x65nv\x18\x03 \x01(\x0e\x32\x37.chromiumos.test.api.Config.VmLeaserBackend.Environment\x12<\n\x0fvm_requirements\x18\x01 \x01(\x0b\x32#.chromiumos.test.api.VMRequirements\x12\x31\n\x0elease_duration\x18\x02 \x01(\x0b\x32\x19.google.protobuf.Duration\"A\n\x0b\x45nvironment\x12\r\n\tENV_LOCAL\x10\x00\x12\x0f\n\x0b\x45NV_STAGING\x10\x01\x12\x12\n\x0e\x45NV_PRODUCTION\x10\x02\x42\t\n\x07\x62\x61\x63kend*B\n\nProviderId\x12\x0b\n\x07UNKNOWN\x10\x00\x12\n\n\x06GCLOUD\x10\x01\x12\x0c\n\x08\x43LOUDSDK\x10\x02\x12\r\n\tVM_LEASER\x10\x03\x42/Z-go.chromium.org/chromiumos/config/go/test/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.api.instance_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z-go.chromium.org/chromiumos/config/go/test/api'
  _CREATEVMINSTANCEREQUEST_TAGSENTRY._options = None
  _CREATEVMINSTANCEREQUEST_TAGSENTRY._serialized_options = b'8\001'
  _LISTVMINSTANCESREQUEST_TAGFILTERSENTRY._options = None
  _LISTVMINSTANCESREQUEST_TAGFILTERSENTRY._serialized_options = b'8\001'
  _PROVIDERID._serialized_start=1381
  _PROVIDERID._serialized_end=1447
  _VMINSTANCE._serialized_start=161
  _VMINSTANCE._serialized_end=279
  _CREATEVMINSTANCEREQUEST._serialized_start=282
  _CREATEVMINSTANCEREQUEST._serialized_end=467
  _CREATEVMINSTANCEREQUEST_TAGSENTRY._serialized_start=424
  _CREATEVMINSTANCEREQUEST_TAGSENTRY._serialized_end=467
  _LISTVMINSTANCESREQUEST._serialized_start=470
  _LISTVMINSTANCESREQUEST._serialized_end=672
  _LISTVMINSTANCESREQUEST_TAGFILTERSENTRY._serialized_start=623
  _LISTVMINSTANCESREQUEST_TAGFILTERSENTRY._serialized_end=672
  _ADDRESSPORT._serialized_start=674
  _ADDRESSPORT._serialized_end=718
  _CONFIG._serialized_start=721
  _CONFIG._serialized_end=1379
  _CONFIG_GCLOUDBACKEND._serialized_start=875
  _CONFIG_GCLOUDBACKEND._serialized_end=1098
  _CONFIG_VMLEASERBACKEND._serialized_start=1101
  _CONFIG_VMLEASERBACKEND._serialized_end=1368
  _CONFIG_VMLEASERBACKEND_ENVIRONMENT._serialized_start=1303
  _CONFIG_VMLEASERBACKEND_ENVIRONMENT._serialized_end=1368
# @@protoc_insertion_point(module_scope)
