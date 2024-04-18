# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/build/api/firmware_config.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.build.api import portage_pb2 as chromiumos_dot_build_dot_api_dot_portage__pb2
from chromite.api.gen.chromiumos import storage_path_pb2 as chromiumos_dot_storage__path__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n*chromiumos/build/api/firmware_config.proto\x12\x14\x63hromiumos.build.api\x1a\"chromiumos/build/api/portage.proto\x1a\x1d\x63hromiumos/storage_path.proto\"=\n\x0c\x46irmwareType\"-\n\x04Type\x12\x0b\n\x07UNKNOWN\x10\x00\x12\x08\n\x04MAIN\x10\x01\x12\x06\n\x02\x45\x43\x10\x02\x12\x06\n\x02PD\x10\x03\"6\n\x07Version\x12\r\n\x05major\x18\x01 \x01(\x05\x12\r\n\x05minor\x18\x02 \x01(\x05\x12\r\n\x05patch\x18\x03 \x01(\x05\"\xeb\x01\n\x0f\x46irmwarePayload\x12\x36\n\x13\x66irmware_image_path\x18\x05 \x01(\x0b\x32\x17.chromiumos.StoragePathH\x00\x12!\n\x13\x66irmware_image_name\x18\x02 \x01(\tB\x02\x18\x01H\x00\x12\x35\n\x04type\x18\x03 \x01(\x0e\x32\'.chromiumos.build.api.FirmwareType.Type\x12.\n\x07version\x18\x04 \x01(\x0b\x32\x1d.chromiumos.build.api.VersionB\x10\n\x0e\x66irmware_imageJ\x04\x08\x01\x10\x02\"\xd0\x02\n\x0e\x46irmwareConfig\x12>\n\x0fmain_ro_payload\x18\x01 \x01(\x0b\x32%.chromiumos.build.api.FirmwarePayload\x12>\n\x0fmain_rw_payload\x18\x02 \x01(\x0b\x32%.chromiumos.build.api.FirmwarePayload\x12<\n\rec_ro_payload\x18\x03 \x01(\x0b\x32%.chromiumos.build.api.FirmwarePayload\x12<\n\rpd_ro_payload\x18\x05 \x01(\x0b\x32%.chromiumos.build.api.FirmwarePayload\x12<\n\rec_rw_payload\x18\x06 \x01(\x0b\x32%.chromiumos.build.api.FirmwarePayloadJ\x04\x08\x04\x10\x05\"\xd2\x02\n\x08\x46irmware\x12\x42\n\rbuild_targets\x18\x01 \x01(\x0b\x32+.chromiumos.build.api.Firmware.BuildTargets\x1a\x81\x02\n\x0c\x42uildTargets\x12\x10\n\x08\x63oreboot\x18\x01 \x01(\t\x12\x13\n\x0b\x64\x65pthcharge\x18\x02 \x01(\t\x12\n\n\x02\x65\x63\x18\x03 \x01(\t\x12\x11\n\tec_extras\x18\x04 \x03(\t\x12\x12\n\nlibpayload\x18\x05 \x01(\t\x12G\n\x14portage_build_target\x18\x06 \x01(\x0b\x32).chromiumos.build.api.Portage.BuildTarget\x12\x11\n\tzephyr_ec\x18\x07 \x01(\t\x12\x0e\n\x06\x62mpblk\x18\x08 \x01(\t\x12\x0b\n\x03ish\x18\t \x01(\t\x12\x1e\n\x16zephyr_detachable_base\x18\n \x01(\t\"Y\n\x13\x46irmwareBuildConfig\x12\x42\n\rbuild_targets\x18\x01 \x01(\x0b\x32+.chromiumos.build.api.Firmware.BuildTargetsB0Z.go.chromium.org/chromiumos/config/go/build/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.build.api.firmware_config_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z.go.chromium.org/chromiumos/config/go/build/api'
  _FIRMWAREPAYLOAD.fields_by_name['firmware_image_name']._options = None
  _FIRMWAREPAYLOAD.fields_by_name['firmware_image_name']._serialized_options = b'\030\001'
  _FIRMWARETYPE._serialized_start=135
  _FIRMWARETYPE._serialized_end=196
  _FIRMWARETYPE_TYPE._serialized_start=151
  _FIRMWARETYPE_TYPE._serialized_end=196
  _VERSION._serialized_start=198
  _VERSION._serialized_end=252
  _FIRMWAREPAYLOAD._serialized_start=255
  _FIRMWAREPAYLOAD._serialized_end=490
  _FIRMWARECONFIG._serialized_start=493
  _FIRMWARECONFIG._serialized_end=829
  _FIRMWARE._serialized_start=832
  _FIRMWARE._serialized_end=1170
  _FIRMWARE_BUILDTARGETS._serialized_start=913
  _FIRMWARE_BUILDTARGETS._serialized_end=1170
  _FIRMWAREBUILDCONFIG._serialized_start=1172
  _FIRMWAREBUILDCONFIG._serialized_end=1261
# @@protoc_insertion_point(module_scope)
