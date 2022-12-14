# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: go.chromium.org/luci/buildbucket/proto/service_config.proto

from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import message as _message
from chromite.third_party.google.protobuf import reflection as _reflection
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.third_party.infra_libs.buildbucket.proto import project_config_pb2 as go_dot_chromium_dot_org_dot_luci_dot_buildbucket_dot_proto_dot_project__config__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='go.chromium.org/luci/buildbucket/proto/service_config.proto',
  package='buildbucket',
  syntax='proto3',
  serialized_options=b'Z4go.chromium.org/luci/buildbucket/proto;buildbucketpb',
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n;go.chromium.org/luci/buildbucket/proto/service_config.proto\x12\x0b\x62uildbucket\x1a;go.chromium.org/luci/buildbucket/proto/project_config.proto\"\xbf\x01\n\x0bSettingsCfg\x12/\n\x08swarming\x18\x01 \x01(\x0b\x32\x1d.buildbucket.SwarmingSettings\x12+\n\x06logdog\x18\x02 \x01(\x0b\x32\x1b.buildbucket.LogDogSettings\x12/\n\x08resultdb\x18\x04 \x01(\x0b\x32\x1d.buildbucket.ResultDBSettings\x12!\n\x19known_public_gerrit_hosts\x18\x03 \x03(\t\"\xb7\x03\n\x10SwarmingSettings\x12\x15\n\rmilo_hostname\x18\x02 \x01(\t\x12\x36\n\rglobal_caches\x18\x04 \x03(\x0b\x32\x1f.buildbucket.Builder.CacheEntry\x12<\n\ruser_packages\x18\x05 \x03(\x0b\x32%.buildbucket.SwarmingSettings.Package\x12>\n\x0f\x62\x62\x61gent_package\x18\x08 \x01(\x0b\x32%.buildbucket.SwarmingSettings.Package\x12>\n\x0fkitchen_package\x18\x07 \x01(\x0b\x32%.buildbucket.SwarmingSettings.Package\x1a\x89\x01\n\x07Package\x12\x14\n\x0cpackage_name\x18\x01 \x01(\t\x12\x0f\n\x07version\x18\x02 \x01(\t\x12\x16\n\x0eversion_canary\x18\x03 \x01(\t\x12/\n\x08\x62uilders\x18\x04 \x01(\x0b\x32\x1d.buildbucket.BuilderPredicate\x12\x0e\n\x06subdir\x18\x05 \x01(\tJ\x04\x08\x01\x10\x02J\x04\x08\x06\x10\x07\"\"\n\x0eLogDogSettings\x12\x10\n\x08hostname\x18\x01 \x01(\t\"8\n\x10\x42uilderPredicate\x12\r\n\x05regex\x18\x01 \x03(\t\x12\x15\n\rregex_exclude\x18\x02 \x03(\t\"$\n\x10ResultDBSettings\x12\x10\n\x08hostname\x18\x01 \x01(\tB6Z4go.chromium.org/luci/buildbucket/proto;buildbucketpbb\x06proto3'
  ,
  dependencies=[go_dot_chromium_dot_org_dot_luci_dot_buildbucket_dot_proto_dot_project__config__pb2.DESCRIPTOR,])




_SETTINGSCFG = _descriptor.Descriptor(
  name='SettingsCfg',
  full_name='buildbucket.SettingsCfg',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='swarming', full_name='buildbucket.SettingsCfg.swarming', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='logdog', full_name='buildbucket.SettingsCfg.logdog', index=1,
      number=2, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='resultdb', full_name='buildbucket.SettingsCfg.resultdb', index=2,
      number=4, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='known_public_gerrit_hosts', full_name='buildbucket.SettingsCfg.known_public_gerrit_hosts', index=3,
      number=3, type=9, cpp_type=9, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
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
  serialized_start=138,
  serialized_end=329,
)


_SWARMINGSETTINGS_PACKAGE = _descriptor.Descriptor(
  name='Package',
  full_name='buildbucket.SwarmingSettings.Package',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='package_name', full_name='buildbucket.SwarmingSettings.Package.package_name', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='version', full_name='buildbucket.SwarmingSettings.Package.version', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='version_canary', full_name='buildbucket.SwarmingSettings.Package.version_canary', index=2,
      number=3, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='builders', full_name='buildbucket.SwarmingSettings.Package.builders', index=3,
      number=4, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='subdir', full_name='buildbucket.SwarmingSettings.Package.subdir', index=4,
      number=5, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
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
  serialized_start=622,
  serialized_end=759,
)

_SWARMINGSETTINGS = _descriptor.Descriptor(
  name='SwarmingSettings',
  full_name='buildbucket.SwarmingSettings',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='milo_hostname', full_name='buildbucket.SwarmingSettings.milo_hostname', index=0,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='global_caches', full_name='buildbucket.SwarmingSettings.global_caches', index=1,
      number=4, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='user_packages', full_name='buildbucket.SwarmingSettings.user_packages', index=2,
      number=5, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='bbagent_package', full_name='buildbucket.SwarmingSettings.bbagent_package', index=3,
      number=8, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='kitchen_package', full_name='buildbucket.SwarmingSettings.kitchen_package', index=4,
      number=7, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[_SWARMINGSETTINGS_PACKAGE, ],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=332,
  serialized_end=771,
)


_LOGDOGSETTINGS = _descriptor.Descriptor(
  name='LogDogSettings',
  full_name='buildbucket.LogDogSettings',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='hostname', full_name='buildbucket.LogDogSettings.hostname', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
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
  serialized_start=773,
  serialized_end=807,
)


_BUILDERPREDICATE = _descriptor.Descriptor(
  name='BuilderPredicate',
  full_name='buildbucket.BuilderPredicate',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='regex', full_name='buildbucket.BuilderPredicate.regex', index=0,
      number=1, type=9, cpp_type=9, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='regex_exclude', full_name='buildbucket.BuilderPredicate.regex_exclude', index=1,
      number=2, type=9, cpp_type=9, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
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
  serialized_start=809,
  serialized_end=865,
)


_RESULTDBSETTINGS = _descriptor.Descriptor(
  name='ResultDBSettings',
  full_name='buildbucket.ResultDBSettings',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='hostname', full_name='buildbucket.ResultDBSettings.hostname', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
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
  serialized_start=867,
  serialized_end=903,
)

_SETTINGSCFG.fields_by_name['swarming'].message_type = _SWARMINGSETTINGS
_SETTINGSCFG.fields_by_name['logdog'].message_type = _LOGDOGSETTINGS
_SETTINGSCFG.fields_by_name['resultdb'].message_type = _RESULTDBSETTINGS
_SWARMINGSETTINGS_PACKAGE.fields_by_name['builders'].message_type = _BUILDERPREDICATE
_SWARMINGSETTINGS_PACKAGE.containing_type = _SWARMINGSETTINGS
_SWARMINGSETTINGS.fields_by_name['global_caches'].message_type = go_dot_chromium_dot_org_dot_luci_dot_buildbucket_dot_proto_dot_project__config__pb2._BUILDER_CACHEENTRY
_SWARMINGSETTINGS.fields_by_name['user_packages'].message_type = _SWARMINGSETTINGS_PACKAGE
_SWARMINGSETTINGS.fields_by_name['bbagent_package'].message_type = _SWARMINGSETTINGS_PACKAGE
_SWARMINGSETTINGS.fields_by_name['kitchen_package'].message_type = _SWARMINGSETTINGS_PACKAGE
DESCRIPTOR.message_types_by_name['SettingsCfg'] = _SETTINGSCFG
DESCRIPTOR.message_types_by_name['SwarmingSettings'] = _SWARMINGSETTINGS
DESCRIPTOR.message_types_by_name['LogDogSettings'] = _LOGDOGSETTINGS
DESCRIPTOR.message_types_by_name['BuilderPredicate'] = _BUILDERPREDICATE
DESCRIPTOR.message_types_by_name['ResultDBSettings'] = _RESULTDBSETTINGS
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

SettingsCfg = _reflection.GeneratedProtocolMessageType('SettingsCfg', (_message.Message,), {
  'DESCRIPTOR' : _SETTINGSCFG,
  '__module__' : 'go.chromium.org.luci.buildbucket.proto.service_config_pb2'
  # @@protoc_insertion_point(class_scope:buildbucket.SettingsCfg)
  })
_sym_db.RegisterMessage(SettingsCfg)

SwarmingSettings = _reflection.GeneratedProtocolMessageType('SwarmingSettings', (_message.Message,), {

  'Package' : _reflection.GeneratedProtocolMessageType('Package', (_message.Message,), {
    'DESCRIPTOR' : _SWARMINGSETTINGS_PACKAGE,
    '__module__' : 'go.chromium.org.luci.buildbucket.proto.service_config_pb2'
    # @@protoc_insertion_point(class_scope:buildbucket.SwarmingSettings.Package)
    })
  ,
  'DESCRIPTOR' : _SWARMINGSETTINGS,
  '__module__' : 'go.chromium.org.luci.buildbucket.proto.service_config_pb2'
  # @@protoc_insertion_point(class_scope:buildbucket.SwarmingSettings)
  })
_sym_db.RegisterMessage(SwarmingSettings)
_sym_db.RegisterMessage(SwarmingSettings.Package)

LogDogSettings = _reflection.GeneratedProtocolMessageType('LogDogSettings', (_message.Message,), {
  'DESCRIPTOR' : _LOGDOGSETTINGS,
  '__module__' : 'go.chromium.org.luci.buildbucket.proto.service_config_pb2'
  # @@protoc_insertion_point(class_scope:buildbucket.LogDogSettings)
  })
_sym_db.RegisterMessage(LogDogSettings)

BuilderPredicate = _reflection.GeneratedProtocolMessageType('BuilderPredicate', (_message.Message,), {
  'DESCRIPTOR' : _BUILDERPREDICATE,
  '__module__' : 'go.chromium.org.luci.buildbucket.proto.service_config_pb2'
  # @@protoc_insertion_point(class_scope:buildbucket.BuilderPredicate)
  })
_sym_db.RegisterMessage(BuilderPredicate)

ResultDBSettings = _reflection.GeneratedProtocolMessageType('ResultDBSettings', (_message.Message,), {
  'DESCRIPTOR' : _RESULTDBSETTINGS,
  '__module__' : 'go.chromium.org.luci.buildbucket.proto.service_config_pb2'
  # @@protoc_insertion_point(class_scope:buildbucket.ResultDBSettings)
  })
_sym_db.RegisterMessage(ResultDBSettings)


DESCRIPTOR._options = None
# @@protoc_insertion_point(module_scope)
