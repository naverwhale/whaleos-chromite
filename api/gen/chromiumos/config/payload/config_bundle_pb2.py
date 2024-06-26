# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/payload/config_bundle.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.config.api import component_pb2 as chromiumos_dot_config_dot_api_dot_component__pb2
from chromite.api.gen.chromiumos.config.api import design_pb2 as chromiumos_dot_config_dot_api_dot_design__pb2
from chromite.api.gen.chromiumos.config.api import device_brand_pb2 as chromiumos_dot_config_dot_api_dot_device__brand__pb2
from chromite.api.gen.chromiumos.config.api import partner_pb2 as chromiumos_dot_config_dot_api_dot_partner__pb2
from chromite.api.gen.chromiumos.config.api import program_pb2 as chromiumos_dot_config_dot_api_dot_program__pb2
from chromite.api.gen.chromiumos.config.api.software import brand_config_pb2 as chromiumos_dot_config_dot_api_dot_software_dot_brand__config__pb2
from chromite.api.gen.chromiumos.config.api.software import software_config_pb2 as chromiumos_dot_config_dot_api_dot_software_dot_software__config__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n-chromiumos/config/payload/config_bundle.proto\x12\x19\x63hromiumos.config.payload\x1a%chromiumos/config/api/component.proto\x1a\"chromiumos/config/api/design.proto\x1a(chromiumos/config/api/device_brand.proto\x1a#chromiumos/config/api/partner.proto\x1a#chromiumos/config/api/program.proto\x1a\x31\x63hromiumos/config/api/software/brand_config.proto\x1a\x34\x63hromiumos/config/api/software/software_config.proto\"\xd5\x03\n\x0c\x43onfigBundle\x12\x34\n\x0cpartner_list\x18\x0b \x03(\x0b\x32\x1e.chromiumos.config.api.Partner\x12\x34\n\ncomponents\x18\x0c \x03(\x0b\x32 .chromiumos.config.api.Component\x12\x34\n\x0cprogram_list\x18\r \x03(\x0b\x32\x1e.chromiumos.config.api.Program\x12\x32\n\x0b\x64\x65sign_list\x18\x0e \x03(\x0b\x32\x1d.chromiumos.config.api.Design\x12=\n\x11\x64\x65vice_brand_list\x18\x0f \x03(\x0b\x32\".chromiumos.config.api.DeviceBrand\x12H\n\x10software_configs\x18\t \x03(\x0b\x32..chromiumos.config.api.software.SoftwareConfig\x12\x42\n\rbrand_configs\x18\n \x03(\x0b\x32+.chromiumos.config.api.software.BrandConfigJ\x04\x08\x02\x10\x03J\x04\x08\x06\x10\x07J\x04\x08\x07\x10\x08J\x04\x08\x08\x10\tJ\x04\x08\x10\x10\x11J\x04\x08\x11\x10\x12\"K\n\x10\x43onfigBundleList\x12\x37\n\x06values\x18\x01 \x03(\x0b\x32\'.chromiumos.config.payload.ConfigBundleB.Z,go.chromium.org/chromiumos/config/go/payloadb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.config.payload.config_bundle_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z,go.chromium.org/chromiumos/config/go/payload'
  _CONFIGBUNDLE._serialized_start=373
  _CONFIGBUNDLE._serialized_end=842
  _CONFIGBUNDLELIST._serialized_start=844
  _CONFIGBUNDLELIST._serialized_end=919
# @@protoc_insertion_point(module_scope)
