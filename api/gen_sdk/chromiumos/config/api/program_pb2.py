# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/program.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen_sdk.chromiumos.config.api import component_pb2 as chromiumos_dot_config_dot_api_dot_component__pb2
from chromite.api.gen_sdk.chromiumos.config.api import design_pb2 as chromiumos_dot_config_dot_api_dot_design__pb2
from chromite.api.gen_sdk.chromiumos.config.api import design_id_pb2 as chromiumos_dot_config_dot_api_dot_design__id__pb2
from chromite.api.gen_sdk.chromiumos.config.api import device_brand_id_pb2 as chromiumos_dot_config_dot_api_dot_device__brand__id__pb2
from chromite.api.gen_sdk.chromiumos.config.api import program_id_pb2 as chromiumos_dot_config_dot_api_dot_program__id__pb2
from chromite.api.gen_sdk.chromiumos.config.api import resource_config_pb2 as chromiumos_dot_config_dot_api_dot_resource__config__pb2
from chromite.api.gen_sdk.chromiumos.config.api import topology_pb2 as chromiumos_dot_config_dot_api_dot_topology__pb2
from chromite.api.gen_sdk.chromiumos.config.public_replication import public_replication_pb2 as chromiumos_dot_config_dot_public__replication_dot_public__replication__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n#chromiumos/config/api/program.proto\x12\x15\x63hromiumos.config.api\x1a%chromiumos/config/api/component.proto\x1a\"chromiumos/config/api/design.proto\x1a%chromiumos/config/api/design_id.proto\x1a+chromiumos/config/api/device_brand_id.proto\x1a&chromiumos/config/api/program_id.proto\x1a+chromiumos/config/api/resource_config.proto\x1a$chromiumos/config/api/topology.proto\x1a=chromiumos/config/public_replication/public_replication.proto\":\n\x1c\x46irmwareConfigurationSegment\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x0c\n\x04mask\x18\x02 \x01(\r\"k\n\x15\x44\x65signConfigIdSegment\x12\x32\n\tdesign_id\x18\x01 \x01(\x0b\x32\x1f.chromiumos.config.api.DesignId\x12\x0e\n\x06min_id\x18\x02 \x01(\r\x12\x0e\n\x06max_id\x18\x03 \x01(\r\"\xa2\x01\n\x12\x44\x65viceSignerConfig\x12\x38\n\x08\x62rand_id\x18\x01 \x01(\x0b\x32$.chromiumos.config.api.DeviceBrandIdH\x00\x12\x34\n\tdesign_id\x18\x03 \x01(\x0b\x32\x1f.chromiumos.config.api.DesignIdH\x00\x12\x0e\n\x06key_id\x18\x02 \x01(\tB\x0c\n\nidentifier\"\x90\x12\n\x07Program\x12S\n\x12public_replication\x18\x08 \x01(\x0b\x32\x37.chromiumos.config.public_replication.PublicReplication\x12,\n\x02id\x18\x01 \x01(\x0b\x32 .chromiumos.config.api.ProgramId\x12\x0c\n\x04name\x18\x02 \x01(\t\x12\x1b\n\x13mosys_platform_name\x18\n \x01(\t\x12\x39\n\x08platform\x18\x0b \x01(\x0b\x32\'.chromiumos.config.api.Program.Platform\x12@\n\x0c\x61udio_config\x18\x0c \x01(\x0b\x32*.chromiumos.config.api.Program.AudioConfig\x12&\n\x1egenerate_camera_media_profiles\x18\r \x01(\x08\x12R\n\x19\x64\x65sign_config_constraints\x18\x03 \x03(\x0b\x32/.chromiumos.config.api.Design.Config.Constraint\x12G\n\x0f\x63omponent_quals\x18\x04 \x03(\x0b\x32..chromiumos.config.api.Component.Qualification\x12\\\n\x1f\x66irmware_configuration_segments\x18\x05 \x03(\x0b\x32\x33.chromiumos.config.api.FirmwareConfigurationSegment\x12J\n\rssfc_segments\x18\t \x03(\x0b\x32\x33.chromiumos.config.api.FirmwareConfigurationSegment\x12O\n\x19\x64\x65sign_config_id_segments\x18\x07 \x03(\x0b\x32,.chromiumos.config.api.DesignConfigIdSegment\x12H\n\x15\x64\x65vice_signer_configs\x18\x06 \x03(\x0b\x32).chromiumos.config.api.DeviceSignerConfig\x1a\x9d\n\n\x08Platform\x12\x12\n\nsoc_family\x18\x01 \x01(\t\x12>\n\x08soc_arch\x18\x02 \x01(\x0e\x32,.chromiumos.config.api.Program.Platform.Arch\x12\x12\n\ngpu_family\x18\x03 \x01(\t\x12J\n\rgraphics_apis\x18\x04 \x03(\x0e\x32\x33.chromiumos.config.api.Program.Platform.GraphicsApi\x12S\n\x0cvideo_codecs\x18\x05 \x03(\x0e\x32=.chromiumos.config.api.Program.Platform.AcceleratedVideoCodec\x12J\n\x0c\x63\x61pabilities\x18\x06 \x01(\x0b\x32\x34.chromiumos.config.api.Program.Platform.Capabilities\x12M\n\x0escheduler_tune\x18\x07 \x01(\x0b\x32\x35.chromiumos.config.api.Program.Platform.SchedulerTune\x12I\n\x0c\x61rc_settings\x18\x08 \x01(\x0b\x32\x33.chromiumos.config.api.Program.Platform.ArcSettings\x12\x45\n\x0chevc_support\x18\t \x01(\x0e\x32/.chromiumos.config.api.HardwareFeatures.Present\x12>\n\x0fresource_config\x18\n \x01(\x0b\x32%.chromiumos.config.api.ResourceConfig\x1aP\n\x0c\x43\x61pabilities\x12\x17\n\x0fsuspend_to_idle\x18\x01 \x01(\x08\x12\x13\n\x0b\x64\x61rk_resume\x18\x02 \x01(\x08\x12\x12\n\nwake_on_dp\x18\x03 \x01(\x08\x1a\x80\x01\n\rSchedulerTune\x12\x14\n\x0c\x62oost_urgent\x18\x01 \x01(\r\x12\x18\n\x10\x63puset_nonurgent\x18\x02 \x01(\t\x12\x13\n\x0binput_boost\x18\x03 \x01(\r\x12\x15\n\rboost_top_app\x18\x04 \x01(\r\x12\x13\n\x0b\x62oost_arcvm\x18\x05 \x01(\x01\x1a*\n\x0b\x41rcSettings\x12\x1b\n\x13media_codecs_suffix\x18\x01 \x01(\t\"A\n\x04\x41rch\x12\x10\n\x0c\x41RCH_UNKNOWN\x10\x00\x12\x07\n\x03X86\x10\x01\x12\n\n\x06X86_64\x10\x02\x12\x07\n\x03\x41RM\x10\x03\x12\t\n\x05\x41RM64\x10\x04\"\xf6\x01\n\x15\x41\x63\x63\x65leratedVideoCodec\x12\x13\n\x0f\x43ODEC_UNDEFINED\x10\x00\x12\x0f\n\x0bH264_DECODE\x10\x01\x12\x0f\n\x0bH264_ENCODE\x10\x02\x12\x0e\n\nVP8_DECODE\x10\x03\x12\x0e\n\nVP8_ENCODE\x10\x04\x12\x0e\n\nVP9_DECODE\x10\x05\x12\x0e\n\nVP9_ENCODE\x10\x06\x12\x10\n\x0cVP9_2_DECODE\x10\x07\x12\x10\n\x0cVP9_2_ENCODE\x10\x08\x12\x0f\n\x0bH265_DECODE\x10\t\x12\x0f\n\x0bH265_ENCODE\x10\n\x12\x0f\n\x0bMJPG_DECODE\x10\x0b\x12\x0f\n\x0bMJPG_ENCODE\x10\x0c\"^\n\x0bGraphicsApi\x12\x1a\n\x16GRAPHICS_API_UNDEFINED\x10\x00\x12\x17\n\x13GRAPHICS_API_OPENGL\x10\x01\x12\x1a\n\x16GRAPHICS_API_OPENGL_ES\x10\x02\x1a\xaf\x01\n\x0b\x41udioConfig\x12N\n\x0c\x63\x61rd_configs\x18\x01 \x03(\x0b\x32\x38.chromiumos.config.api.HardwareFeatures.Audio.CardConfig\x12\x17\n\x0fhas_module_file\x18\x02 \x01(\x08\x12\x1a\n\x12\x64\x65\x66\x61ult_ucm_suffix\x18\x03 \x01(\t\x12\x1b\n\x13\x64\x65\x66\x61ult_cras_suffix\x18\x04 \x01(\tB*Z(go.chromium.org/chromiumos/config/go/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.config.api.program_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z(go.chromium.org/chromiumos/config/go/api'
  _FIRMWARECONFIGURATIONSEGMENT._serialized_start=407
  _FIRMWARECONFIGURATIONSEGMENT._serialized_end=465
  _DESIGNCONFIGIDSEGMENT._serialized_start=467
  _DESIGNCONFIGIDSEGMENT._serialized_end=574
  _DEVICESIGNERCONFIG._serialized_start=577
  _DEVICESIGNERCONFIG._serialized_end=739
  _PROGRAM._serialized_start=742
  _PROGRAM._serialized_end=3062
  _PROGRAM_PLATFORM._serialized_start=1575
  _PROGRAM_PLATFORM._serialized_end=2884
  _PROGRAM_PLATFORM_CAPABILITIES._serialized_start=2217
  _PROGRAM_PLATFORM_CAPABILITIES._serialized_end=2297
  _PROGRAM_PLATFORM_SCHEDULERTUNE._serialized_start=2300
  _PROGRAM_PLATFORM_SCHEDULERTUNE._serialized_end=2428
  _PROGRAM_PLATFORM_ARCSETTINGS._serialized_start=2430
  _PROGRAM_PLATFORM_ARCSETTINGS._serialized_end=2472
  _PROGRAM_PLATFORM_ARCH._serialized_start=2474
  _PROGRAM_PLATFORM_ARCH._serialized_end=2539
  _PROGRAM_PLATFORM_ACCELERATEDVIDEOCODEC._serialized_start=2542
  _PROGRAM_PLATFORM_ACCELERATEDVIDEOCODEC._serialized_end=2788
  _PROGRAM_PLATFORM_GRAPHICSAPI._serialized_start=2790
  _PROGRAM_PLATFORM_GRAPHICSAPI._serialized_end=2884
  _PROGRAM_AUDIOCONFIG._serialized_start=2887
  _PROGRAM_AUDIOCONFIG._serialized_end=3062
# @@protoc_insertion_point(module_scope)
