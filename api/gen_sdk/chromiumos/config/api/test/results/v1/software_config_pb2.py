# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/test/results/v1/software_config.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2
from chromite.api.gen_sdk.chromiumos.config.api.test.results.v1 import package_pb2 as chromiumos_dot_config_dot_api_dot_test_dot_results_dot_v1_dot_package__pb2
from chromite.api.gen_sdk.chromiumos.config.api.test.results.v1 import software_config_id_pb2 as chromiumos_dot_config_dot_api_dot_test_dot_results_dot_v1_dot_software__config__id__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='chromiumos/config/api/test/results/v1/software_config.proto',
  package='chromiumos.config.api.test.results.v1',
  syntax='proto3',
  serialized_options=b'Z@go.chromium.org/chromiumos/config/go/api/test/results/v1;results',
  serialized_pb=b'\n;chromiumos/config/api/test/results/v1/software_config.proto\x12%chromiumos.config.api.test.results.v1\x1a\x1fgoogle/protobuf/timestamp.proto\x1a\x33\x63hromiumos/config/api/test/results/v1/package.proto\x1a>chromiumos/config/api/test/results/v1/software_config_id.proto\"\xf7\x06\n\x0eSoftwareConfig\x12\x43\n\x02id\x18\x01 \x01(\x0b\x32\x37.chromiumos.config.api.test.results.v1.SoftwareConfigId\x12/\n\x0b\x63reate_time\x18\x02 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12G\n\x06parent\x18\x03 \x01(\x0b\x32\x37.chromiumos.config.api.test.results.v1.SoftwareConfigId\x12@\n\x08packages\x18\x04 \x03(\x0b\x32..chromiumos.config.api.test.results.v1.Package\x12\x16\n\x0ekernel_release\x18\x05 \x01(\t\x12\x16\n\x0ekernel_version\x18\x06 \x01(\t\x12P\n\x08\x63hromeos\x18\x07 \x01(\x0b\x32>.chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS\x12\x44\n\x02os\x18\x08 \x01(\x0b\x32\x38.chromiumos.config.api.test.results.v1.SoftwareConfig.OS\x12\x14\n\x0c\x62ios_version\x18\t \x01(\t\x12\x12\n\nec_version\x18\n \x01(\t\x1a\xf3\x01\n\x08\x43hromeOS\x12\r\n\x05\x62oard\x18\x01 \x01(\t\x12\x15\n\rbranch_number\x18\x02 \x01(\r\x12\x14\n\x0c\x62uilder_path\x18\x03 \x01(\t\x12\x14\n\x0c\x62uild_number\x18\x04 \x01(\r\x12\x12\n\nbuild_type\x18\x05 \x01(\t\x12\x18\n\x10\x63hrome_milestone\x18\x06 \x01(\r\x12\x13\n\x0b\x64\x65scription\x18\x07 \x01(\t\x12\x0e\n\x06keyset\x18\x08 \x01(\t\x12\x0c\n\x04name\x18\t \x01(\t\x12\x14\n\x0cpatch_number\x18\n \x01(\t\x12\r\n\x05track\x18\x0b \x01(\t\x12\x0f\n\x07version\x18\x0c \x01(\t\x1a|\n\x02OS\x12\x10\n\x08\x62uild_id\x18\x01 \x01(\t\x12\x10\n\x08\x63odename\x18\x02 \x01(\t\x12\n\n\x02id\x18\x03 \x01(\t\x12\x0c\n\x04name\x18\x04 \x01(\t\x12\x13\n\x0bpretty_name\x18\x05 \x01(\t\x12\x12\n\nversion_id\x18\x06 \x01(\t\x12\x0f\n\x07version\x18\x07 \x01(\tBBZ@go.chromium.org/chromiumos/config/go/api/test/results/v1;resultsb\x06proto3'
  ,
  dependencies=[google_dot_protobuf_dot_timestamp__pb2.DESCRIPTOR,chromiumos_dot_config_dot_api_dot_test_dot_results_dot_v1_dot_package__pb2.DESCRIPTOR,chromiumos_dot_config_dot_api_dot_test_dot_results_dot_v1_dot_software__config__id__pb2.DESCRIPTOR,])




_SOFTWARECONFIG_CHROMEOS = _descriptor.Descriptor(
  name='ChromeOS',
  full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='board', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS.board', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='branch_number', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS.branch_number', index=1,
      number=2, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='builder_path', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS.builder_path', index=2,
      number=3, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='build_number', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS.build_number', index=3,
      number=4, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='build_type', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS.build_type', index=4,
      number=5, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='chrome_milestone', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS.chrome_milestone', index=5,
      number=6, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='description', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS.description', index=6,
      number=7, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='keyset', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS.keyset', index=7,
      number=8, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='name', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS.name', index=8,
      number=9, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='patch_number', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS.patch_number', index=9,
      number=10, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='track', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS.track', index=10,
      number=11, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='version', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS.version', index=11,
      number=12, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=771,
  serialized_end=1014,
)

_SOFTWARECONFIG_OS = _descriptor.Descriptor(
  name='OS',
  full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.OS',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='build_id', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.OS.build_id', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='codename', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.OS.codename', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='id', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.OS.id', index=2,
      number=3, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='name', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.OS.name', index=3,
      number=4, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='pretty_name', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.OS.pretty_name', index=4,
      number=5, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='version_id', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.OS.version_id', index=5,
      number=6, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='version', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.OS.version', index=6,
      number=7, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=1016,
  serialized_end=1140,
)

_SOFTWARECONFIG = _descriptor.Descriptor(
  name='SoftwareConfig',
  full_name='chromiumos.config.api.test.results.v1.SoftwareConfig',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='id', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.id', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='create_time', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.create_time', index=1,
      number=2, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='parent', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.parent', index=2,
      number=3, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='packages', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.packages', index=3,
      number=4, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='kernel_release', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.kernel_release', index=4,
      number=5, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='kernel_version', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.kernel_version', index=5,
      number=6, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='chromeos', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.chromeos', index=6,
      number=7, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='os', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.os', index=7,
      number=8, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='bios_version', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.bios_version', index=8,
      number=9, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='ec_version', full_name='chromiumos.config.api.test.results.v1.SoftwareConfig.ec_version', index=9,
      number=10, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[_SOFTWARECONFIG_CHROMEOS, _SOFTWARECONFIG_OS, ],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=253,
  serialized_end=1140,
)

_SOFTWARECONFIG_CHROMEOS.containing_type = _SOFTWARECONFIG
_SOFTWARECONFIG_OS.containing_type = _SOFTWARECONFIG
_SOFTWARECONFIG.fields_by_name['id'].message_type = chromiumos_dot_config_dot_api_dot_test_dot_results_dot_v1_dot_software__config__id__pb2._SOFTWARECONFIGID
_SOFTWARECONFIG.fields_by_name['create_time'].message_type = google_dot_protobuf_dot_timestamp__pb2._TIMESTAMP
_SOFTWARECONFIG.fields_by_name['parent'].message_type = chromiumos_dot_config_dot_api_dot_test_dot_results_dot_v1_dot_software__config__id__pb2._SOFTWARECONFIGID
_SOFTWARECONFIG.fields_by_name['packages'].message_type = chromiumos_dot_config_dot_api_dot_test_dot_results_dot_v1_dot_package__pb2._PACKAGE
_SOFTWARECONFIG.fields_by_name['chromeos'].message_type = _SOFTWARECONFIG_CHROMEOS
_SOFTWARECONFIG.fields_by_name['os'].message_type = _SOFTWARECONFIG_OS
DESCRIPTOR.message_types_by_name['SoftwareConfig'] = _SOFTWARECONFIG
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

SoftwareConfig = _reflection.GeneratedProtocolMessageType('SoftwareConfig', (_message.Message,), {

  'ChromeOS' : _reflection.GeneratedProtocolMessageType('ChromeOS', (_message.Message,), {
    'DESCRIPTOR' : _SOFTWARECONFIG_CHROMEOS,
    '__module__' : 'chromiumos.config.api.test.results.v1.software_config_pb2'
    # @@protoc_insertion_point(class_scope:chromiumos.config.api.test.results.v1.SoftwareConfig.ChromeOS)
    })
  ,

  'OS' : _reflection.GeneratedProtocolMessageType('OS', (_message.Message,), {
    'DESCRIPTOR' : _SOFTWARECONFIG_OS,
    '__module__' : 'chromiumos.config.api.test.results.v1.software_config_pb2'
    # @@protoc_insertion_point(class_scope:chromiumos.config.api.test.results.v1.SoftwareConfig.OS)
    })
  ,
  'DESCRIPTOR' : _SOFTWARECONFIG,
  '__module__' : 'chromiumos.config.api.test.results.v1.software_config_pb2'
  # @@protoc_insertion_point(class_scope:chromiumos.config.api.test.results.v1.SoftwareConfig)
  })
_sym_db.RegisterMessage(SoftwareConfig)
_sym_db.RegisterMessage(SoftwareConfig.ChromeOS)
_sym_db.RegisterMessage(SoftwareConfig.OS)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)