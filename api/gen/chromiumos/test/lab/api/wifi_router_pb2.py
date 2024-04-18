# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/lab/api/wifi_router.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.third_party.google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n)chromiumos/test/lab/api/wifi_router.proto\x12\x17\x63hromiumos.test.lab.api\x1a\x1fgoogle/protobuf/timestamp.proto\"\xc3\x01\n\x10WifiRouterConfig\x12G\n\x07openwrt\x18\x01 \x03(\x0b\x32\x36.chromiumos.test.lab.api.WifiRouterConfig.OpenwrtEntry\x1a\x66\n\x0cOpenwrtEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\x45\n\x05value\x18\x02 \x01(\x0b\x32\x36.chromiumos.test.lab.api.OpenWrtWifiRouterDeviceConfig:\x02\x38\x01\"\xb2\x02\n\x1dOpenWrtWifiRouterDeviceConfig\x12\x1a\n\x12\x63urrent_image_uuid\x18\x01 \x01(\t\x12\x17\n\x0fnext_image_uuid\x18\x02 \x01(\t\x12(\n next_image_verification_dut_pool\x18\x03 \x03(\t\x12U\n\x06images\x18\x04 \x03(\x0b\x32\x45.chromiumos.test.lab.api.OpenWrtWifiRouterDeviceConfig.OpenWrtOSImage\x1a[\n\x0eOpenWrtOSImage\x12\x12\n\nimage_uuid\x18\x01 \x01(\t\x12\x14\n\x0c\x61rchive_path\x18\x02 \x01(\t\x12\x1f\n\x17min_dut_release_version\x18\x03 \x01(\t\"\x81\t\n\x19\x43rosOpenWrtImageBuildInfo\x12\x12\n\nimage_uuid\x18\x01 \x01(\t\x12\x19\n\x11\x63ustom_image_name\x18\x02 \x01(\t\x12P\n\nos_release\x18\x03 \x01(\x0b\x32<.chromiumos.test.lab.api.CrosOpenWrtImageBuildInfo.OSRelease\x12\x65\n\x15standard_build_config\x18\x04 \x01(\x0b\x32\x46.chromiumos.test.lab.api.CrosOpenWrtImageBuildInfo.StandardBuildConfig\x12\x43\n\x0frouter_features\x18\x05 \x03(\x0e\x32*.chromiumos.test.lab.api.WifiRouterFeature\x12.\n\nbuild_time\x18\x06 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12*\n\"cros_openwrt_image_builder_version\x18\x07 \x01(\t\x12j\n\x15\x63ustom_included_files\x18\x08 \x03(\x0b\x32K.chromiumos.test.lab.api.CrosOpenWrtImageBuildInfo.CustomIncludedFilesEntry\x12_\n\x0f\x63ustom_packages\x18\t \x03(\x0b\x32\x46.chromiumos.test.lab.api.CrosOpenWrtImageBuildInfo.CustomPackagesEntry\x12\x1f\n\x17\x65xtra_included_packages\x18\n \x03(\t\x12\x19\n\x11\x65xcluded_packages\x18\x0b \x03(\t\x12\x19\n\x11\x64isabled_services\x18\x0c \x03(\t\x1a\xcd\x01\n\x13StandardBuildConfig\x12\x18\n\x10openwrt_revision\x18\x01 \x01(\t\x12\x1c\n\x14openwrt_build_target\x18\x02 \x01(\t\x12\x15\n\rbuild_profile\x18\x03 \x01(\t\x12\x13\n\x0b\x64\x65vice_name\x18\x04 \x01(\t\x12\x1d\n\x15\x62uild_target_packages\x18\x05 \x03(\t\x12\x18\n\x10profile_packages\x18\x06 \x03(\t\x12\x19\n\x11supported_devices\x18\x07 \x03(\t\x1at\n\tOSRelease\x12\x0f\n\x07version\x18\x01 \x01(\t\x12\x10\n\x08\x62uild_id\x18\x02 \x01(\t\x12\x15\n\ropenwrt_board\x18\x03 \x01(\t\x12\x14\n\x0copenwrt_arch\x18\x04 \x01(\t\x12\x17\n\x0fopenwrt_release\x18\x05 \x01(\t\x1a:\n\x18\x43ustomIncludedFilesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\x1a\x35\n\x13\x43ustomPackagesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01*\x93\x03\n\x11WifiRouterFeature\x12\x1f\n\x1bWIFI_ROUTER_FEATURE_UNKNOWN\x10\x00\x12\x1f\n\x1bWIFI_ROUTER_FEATURE_INVALID\x10\x01\x12%\n!WIFI_ROUTER_FEATURE_IEEE_802_11_A\x10\x02\x12%\n!WIFI_ROUTER_FEATURE_IEEE_802_11_B\x10\x03\x12%\n!WIFI_ROUTER_FEATURE_IEEE_802_11_G\x10\x04\x12%\n!WIFI_ROUTER_FEATURE_IEEE_802_11_N\x10\x05\x12&\n\"WIFI_ROUTER_FEATURE_IEEE_802_11_AC\x10\x06\x12&\n\"WIFI_ROUTER_FEATURE_IEEE_802_11_AX\x10\x07\x12(\n$WIFI_ROUTER_FEATURE_IEEE_802_11_AX_E\x10\x08\x12&\n\"WIFI_ROUTER_FEATURE_IEEE_802_11_BE\x10\t*\x83\x02\n\x14WifiRouterDeviceType\x12#\n\x1fWIFI_ROUTER_DEVICE_TYPE_UNKNOWN\x10\x00\x12#\n\x1fWIFI_ROUTER_DEVICE_TYPE_INVALID\x10\x01\x12)\n%WIFI_ROUTER_DEVICE_TYPE_CHROMEOS_GALE\x10\x02\x12#\n\x1fWIFI_ROUTER_DEVICE_TYPE_OPENWRT\x10\x03\x12#\n\x1fWIFI_ROUTER_DEVICE_TYPE_ASUSWRT\x10\x04\x12,\n(WIFI_ROUTER_DEVICE_TYPE_UBUNTU_INTEL_NUC\x10\x05\x42\x33Z1go.chromium.org/chromiumos/config/go/test/lab/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.lab.api.wifi_router_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z1go.chromium.org/chromiumos/config/go/test/lab/api'
  _WIFIROUTERCONFIG_OPENWRTENTRY._options = None
  _WIFIROUTERCONFIG_OPENWRTENTRY._serialized_options = b'8\001'
  _CROSOPENWRTIMAGEBUILDINFO_CUSTOMINCLUDEDFILESENTRY._options = None
  _CROSOPENWRTIMAGEBUILDINFO_CUSTOMINCLUDEDFILESENTRY._serialized_options = b'8\001'
  _CROSOPENWRTIMAGEBUILDINFO_CUSTOMPACKAGESENTRY._options = None
  _CROSOPENWRTIMAGEBUILDINFO_CUSTOMPACKAGESENTRY._serialized_options = b'8\001'
  _WIFIROUTERFEATURE._serialized_start=1767
  _WIFIROUTERFEATURE._serialized_end=2170
  _WIFIROUTERDEVICETYPE._serialized_start=2173
  _WIFIROUTERDEVICETYPE._serialized_end=2432
  _WIFIROUTERCONFIG._serialized_start=104
  _WIFIROUTERCONFIG._serialized_end=299
  _WIFIROUTERCONFIG_OPENWRTENTRY._serialized_start=197
  _WIFIROUTERCONFIG_OPENWRTENTRY._serialized_end=299
  _OPENWRTWIFIROUTERDEVICECONFIG._serialized_start=302
  _OPENWRTWIFIROUTERDEVICECONFIG._serialized_end=608
  _OPENWRTWIFIROUTERDEVICECONFIG_OPENWRTOSIMAGE._serialized_start=517
  _OPENWRTWIFIROUTERDEVICECONFIG_OPENWRTOSIMAGE._serialized_end=608
  _CROSOPENWRTIMAGEBUILDINFO._serialized_start=611
  _CROSOPENWRTIMAGEBUILDINFO._serialized_end=1764
  _CROSOPENWRTIMAGEBUILDINFO_STANDARDBUILDCONFIG._serialized_start=1326
  _CROSOPENWRTIMAGEBUILDINFO_STANDARDBUILDCONFIG._serialized_end=1531
  _CROSOPENWRTIMAGEBUILDINFO_OSRELEASE._serialized_start=1533
  _CROSOPENWRTIMAGEBUILDINFO_OSRELEASE._serialized_end=1649
  _CROSOPENWRTIMAGEBUILDINFO_CUSTOMINCLUDEDFILESENTRY._serialized_start=1651
  _CROSOPENWRTIMAGEBUILDINFO_CUSTOMINCLUDEDFILESENTRY._serialized_end=1709
  _CROSOPENWRTIMAGEBUILDINFO_CUSTOMPACKAGESENTRY._serialized_start=1711
  _CROSOPENWRTIMAGEBUILDINFO_CUSTOMPACKAGESENTRY._serialized_end=1764
# @@protoc_insertion_point(module_scope)
