# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/api/firmware_provision.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.build.api import firmware_config_pb2 as chromiumos_dot_build_dot_api_dot_firmware__config__pb2
from chromite.api.gen.chromiumos.longrunning import operations_pb2 as chromiumos_dot_longrunning_dot_operations__pb2
from chromite.api.gen.chromiumos.test.lab.api import ip_endpoint_pb2 as chromiumos_dot_test_dot_lab_dot_api_dot_ip__endpoint__pb2
from chromite.api.gen.chromiumos import storage_path_pb2 as chromiumos_dot_storage__path__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n,chromiumos/test/api/firmware_provision.proto\x12\x13\x63hromiumos.test.api\x1a*chromiumos/build/api/firmware_config.proto\x1a\'chromiumos/longrunning/operations.proto\x1a)chromiumos/test/lab/api/ip_endpoint.proto\x1a\x1d\x63hromiumos/storage_path.proto\"_\n\x15SimpleFirmwareRequest\x12\x34\n\x13\x66irmware_image_path\x18\x01 \x01(\x0b\x32\x17.chromiumos.StoragePath\x12\x10\n\x08\x66lash_ro\x18\x02 \x01(\x08\"\xf9\x02\n\x18ProvisionFirmwareRequest\x12\x44\n\x0esimple_request\x18\x01 \x01(\x0b\x32*.chromiumos.test.api.SimpleFirmwareRequestH\x00\x12@\n\x10\x64\x65tailed_request\x18\x02 \x01(\x0b\x32$.chromiumos.build.api.FirmwareConfigH\x00\x12?\n\x12\x64ut_server_address\x18\x03 \x01(\x0b\x32#.chromiumos.test.lab.api.IpEndpoint\x12@\n\x13\x63ros_servod_address\x18\x04 \x01(\x0b\x32#.chromiumos.test.lab.api.IpEndpoint\x12\r\n\x05\x62oard\x18\x06 \x01(\t\x12\r\n\x05model\x18\x07 \x01(\t\x12\r\n\x05\x66orce\x18\x08 \x01(\x08\x12\x11\n\tuse_servo\x18\t \x01(\x08\x42\x12\n\x10\x66irmware_request\"\xc9\x02\n\x19ProvisionFirmwareResponse\x12\x45\n\x06status\x18\x01 \x01(\x0e\x32\x35.chromiumos.test.api.ProvisionFirmwareResponse.Status\"\xe4\x01\n\x06Status\x12\r\n\tSTATUS_OK\x10\x00\x12\x1a\n\x16STATUS_INVALID_REQUEST\x10\x01\x12(\n$STATUS_DUT_UNREACHABLE_PRE_PROVISION\x10\x02\x12!\n\x1dSTATUS_UPDATE_FIRMWARE_FAILED\x10\x03\x12\x31\n-STATUS_FIRMWARE_MISMATCH_POST_FIRMWARE_UPDATE\x10\x04\x12/\n+STATUS_DUT_UNREACHABLE_POST_FIRMWARE_UPDATE\x10\x05\"\x1b\n\x19ProvisionFirmwareMetadata2\xb5\x01\n\x18\x46irmwareProvisionService\x12\x98\x01\n\tProvision\x12-.chromiumos.test.api.ProvisionFirmwareRequest\x1a!.chromiumos.longrunning.Operation\"9\xd2\x41\x36\n\x19ProvisionFirmwareResponse\x12\x19ProvisionFirmwareMetadataB/Z-go.chromium.org/chromiumos/config/go/test/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.api.firmware_provision_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z-go.chromium.org/chromiumos/config/go/test/api'
  _FIRMWAREPROVISIONSERVICE.methods_by_name['Provision']._options = None
  _FIRMWAREPROVISIONSERVICE.methods_by_name['Provision']._serialized_options = b'\322A6\n\031ProvisionFirmwareResponse\022\031ProvisionFirmwareMetadata'
  _SIMPLEFIRMWAREREQUEST._serialized_start=228
  _SIMPLEFIRMWAREREQUEST._serialized_end=323
  _PROVISIONFIRMWAREREQUEST._serialized_start=326
  _PROVISIONFIRMWAREREQUEST._serialized_end=703
  _PROVISIONFIRMWARERESPONSE._serialized_start=706
  _PROVISIONFIRMWARERESPONSE._serialized_end=1035
  _PROVISIONFIRMWARERESPONSE_STATUS._serialized_start=807
  _PROVISIONFIRMWARERESPONSE_STATUS._serialized_end=1035
  _PROVISIONFIRMWAREMETADATA._serialized_start=1037
  _PROVISIONFIRMWAREMETADATA._serialized_end=1064
  _FIRMWAREPROVISIONSERVICE._serialized_start=1067
  _FIRMWAREPROVISIONSERVICE._serialized_end=1248
# @@protoc_insertion_point(module_scope)
