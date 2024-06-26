# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/software/software_config.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.build.api import factory_pb2 as chromiumos_dot_build_dot_api_dot_factory__pb2
from chromite.api.gen.chromiumos.build.api import firmware_config_pb2 as chromiumos_dot_build_dot_api_dot_firmware__config__pb2
from chromite.api.gen.chromiumos.build.api import system_image_pb2 as chromiumos_dot_build_dot_api_dot_system__image__pb2
from chromite.api.gen.chromiumos.config.api import design_config_id_pb2 as chromiumos_dot_config_dot_api_dot_design__config__id__pb2
from chromite.api.gen.chromiumos.config.api import resource_config_pb2 as chromiumos_dot_config_dot_api_dot_resource__config__pb2
from chromite.api.gen.chromiumos.config.api.software import audio_config_pb2 as chromiumos_dot_config_dot_api_dot_software_dot_audio__config__pb2
from chromite.api.gen.chromiumos.config.api.software import bluetooth_config_pb2 as chromiumos_dot_config_dot_api_dot_software_dot_bluetooth__config__pb2
from chromite.api.gen.chromiumos.config.api.software import camera_config_pb2 as chromiumos_dot_config_dot_api_dot_software_dot_camera__config__pb2
from chromite.api.gen.chromiumos.config.api.software import alt_firmware_config_pb2 as chromiumos_dot_config_dot_api_dot_software_dot_alt__firmware__config__pb2
from chromite.api.gen.chromiumos.config.api.software import health_config_pb2 as chromiumos_dot_config_dot_api_dot_software_dot_health__config__pb2
from chromite.api.gen.chromiumos.config.api.software import nnpalm_config_pb2 as chromiumos_dot_config_dot_api_dot_software_dot_nnpalm__config__pb2
from chromite.api.gen.chromiumos.config.api.software import power_config_pb2 as chromiumos_dot_config_dot_api_dot_software_dot_power__config__pb2
from chromite.api.gen.chromiumos.config.api.software import rma_config_pb2 as chromiumos_dot_config_dot_api_dot_software_dot_rma__config__pb2
from chromite.api.gen.chromiumos.config.api.software import ui_config_pb2 as chromiumos_dot_config_dot_api_dot_software_dot_ui__config__pb2
from chromite.api.gen.chromiumos.config.api.software import usb_config_pb2 as chromiumos_dot_config_dot_api_dot_software_dot_usb__config__pb2
from chromite.api.gen.chromiumos.config.api import wifi_config_pb2 as chromiumos_dot_config_dot_api_dot_wifi__config__pb2
from chromite.api.gen.chromiumos.config.public_replication import public_replication_pb2 as chromiumos_dot_config_dot_public__replication_dot_public__replication__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n4chromiumos/config/api/software/software_config.proto\x12\x1e\x63hromiumos.config.api.software\x1a\"chromiumos/build/api/factory.proto\x1a*chromiumos/build/api/firmware_config.proto\x1a\'chromiumos/build/api/system_image.proto\x1a,chromiumos/config/api/design_config_id.proto\x1a+chromiumos/config/api/resource_config.proto\x1a\x31\x63hromiumos/config/api/software/audio_config.proto\x1a\x35\x63hromiumos/config/api/software/bluetooth_config.proto\x1a\x32\x63hromiumos/config/api/software/camera_config.proto\x1a\x38\x63hromiumos/config/api/software/alt_firmware_config.proto\x1a\x32\x63hromiumos/config/api/software/health_config.proto\x1a\x32\x63hromiumos/config/api/software/nnpalm_config.proto\x1a\x31\x63hromiumos/config/api/software/power_config.proto\x1a/chromiumos/config/api/software/rma_config.proto\x1a.chromiumos/config/api/software/ui_config.proto\x1a/chromiumos/config/api/software/usb_config.proto\x1a\'chromiumos/config/api/wifi_config.proto\x1a=chromiumos/config/public_replication/public_replication.proto\"\x8a\x0b\n\x0eSoftwareConfig\x12S\n\x12public_replication\x18\x0c \x01(\x0b\x32\x37.chromiumos.config.public_replication.PublicReplication\x12?\n\x10\x64\x65sign_config_id\x18\x07 \x01(\x0b\x32%.chromiumos.config.api.DesignConfigId\x12H\n\x0eid_scan_config\x18\x08 \x01(\x0b\x32\x30.chromiumos.config.api.DesignConfigId.ScanConfig\x12\x36\n\x08\x66irmware\x18\x03 \x01(\x0b\x32$.chromiumos.build.api.FirmwareConfig\x12H\n\x15\x66irmware_build_config\x18\t \x01(\x0b\x32).chromiumos.build.api.FirmwareBuildConfig\x12K\n\x16\x66irmware_build_targets\x18\x10 \x01(\x0b\x32+.chromiumos.build.api.Firmware.BuildTargets\x12J\n\x13system_build_target\x18\r \x01(\x0b\x32-.chromiumos.build.api.SystemImage.BuildTarget\x12G\n\x14\x66\x61\x63tory_build_target\x18\x0e \x01(\x0b\x32).chromiumos.build.api.Factory.BuildTarget\x12I\n\x10\x62luetooth_config\x18\x04 \x01(\x0b\x32/.chromiumos.config.api.software.BluetoothConfig\x12\x41\n\x0cpower_config\x18\x05 \x01(\x0b\x32+.chromiumos.config.api.software.PowerConfig\x12>\n\x0fresource_config\x18\x13 \x01(\x0b\x32%.chromiumos.config.api.ResourceConfig\x12\x42\n\raudio_configs\x18\n \x03(\x0b\x32+.chromiumos.config.api.software.AudioConfig\x12\x36\n\x0bwifi_config\x18\x0b \x01(\x0b\x32!.chromiumos.config.api.WifiConfig\x12\x43\n\rhealth_config\x18\x12 \x01(\x0b\x32,.chromiumos.config.api.software.HealthConfig\x12\x43\n\rcamera_config\x18\x0f \x01(\x0b\x32,.chromiumos.config.api.software.CameraConfig\x12;\n\tui_config\x18\x11 \x01(\x0b\x32(.chromiumos.config.api.software.UiConfig\x12=\n\nusb_config\x18\x14 \x01(\x0b\x32).chromiumos.config.api.software.UsbConfig\x12\x43\n\rnnpalm_config\x18\x15 \x01(\x0b\x32,.chromiumos.config.api.software.NnpalmConfig\x12=\n\nrma_config\x18\x16 \x01(\x0b\x32).chromiumos.config.api.software.RmaConfig\x12N\n\x13\x61lt_firmware_config\x18\x17 \x01(\x0b\x32\x31.chromiumos.config.api.software.AltFirmwareConfigJ\x04\x08\x01\x10\x02J\x04\x08\x02\x10\x03J\x04\x08\x06\x10\x07\x42\x33Z1go.chromium.org/chromiumos/config/go/api/softwareb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.config.api.software.software_config_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z1go.chromium.org/chromiumos/config/go/api/software'
  _SOFTWARECONFIG._serialized_start=922
  _SOFTWARECONFIG._serialized_end=2340
# @@protoc_insertion_point(module_scope)
