# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/ge_config.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1a\x63hromiumos/ge_config.proto\x12\nchromiumos\"\xed\x01\n\x05Model\x12\x12\n\nboard_name\x18\x01 \x01(\t\x12\x0c\n\x04name\x18\x02 \x01(\t\x12\x13\n\x0btest_suites\x18\x03 \x03(\t\x12\x17\n\x0f\x63q_test_enabled\x18\x04 \x01(\x08\x12!\n\x19release_builder_test_pool\x18\x05 \x01(\t\x12\x10\n\x08\x62oard_id\x18\x06 \x01(\x03\x12\x11\n\tis_active\x18\x07 \x01(\x08\x12\x12\n\nhwid_match\x18\x08 \x01(\t\x12\x1f\n\x17stable_target_milestone\x18\t \x01(\x05\x12\x17\n\x0fis_experimental\x18\n \x01(\x08\"\x9a\x02\n ReferenceBoardUnifiedBuildConfig\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x1c\n\x14reference_board_name\x18\x02 \x01(\t\x12&\n\x04\x61rch\x18\x03 \x01(\x0e\x32\x18.chromiumos.Architecture\x12(\n\x07\x62uilder\x18\x04 \x01(\x0e\x32\x17.chromiumos.BuilderType\x12\x14\n\x0c\x65xperimental\x18\x05 \x01(\x08\x12!\n\x06models\x18\x06 \x03(\x0b\x32\x11.chromiumos.Model\x12\x1e\n\x16rubik_target_milestone\x18\x07 \x01(\x05\x12\x1f\n\x17stable_target_milestone\x18\x08 \x01(\x05\"\x9b\x01\n\x06\x43onfig\x12(\n\x07\x62uilder\x18\x01 \x01(\x0e\x32\x17.chromiumos.BuilderType\x12\x14\n\x0c\x65xperimental\x18\x02 \x01(\x08\x12\x14\n\x0cleader_board\x18\x03 \x01(\x08\x12\x13\n\x0b\x62oard_group\x18\x04 \x01(\t\x12&\n\x04\x61rch\x18\x05 \x01(\x0e\x32\x18.chromiumos.Architecture\"\x80\x01\n\nBuildBoard\x12\x0c\n\x04name\x18\x01 \x01(\t\x12#\n\x07\x63onfigs\x18\x02 \x03(\x0b\x32\x12.chromiumos.Config\x12\x1e\n\x16rubik_target_milestone\x18\x03 \x01(\x05\x12\x1f\n\x17stable_target_milestone\x18\x04 \x01(\x05\"\xba\x01\n\x08GEConfig\x12\x18\n\x10metadata_version\x18\x01 \x01(\t\x12&\n\x06\x62oards\x18\x02 \x03(\x0b\x32\x16.chromiumos.BuildBoard\x12\x16\n\x0erelease_branch\x18\x03 \x01(\x08\x12T\n\x1ereference_board_unified_builds\x18\x04 \x03(\x0b\x32,.chromiumos.ReferenceBoardUnifiedBuildConfig*4\n\x0b\x42uilderType\x12\x18\n\x14UNKNOWN_BUILDER_TYPE\x10\x00\x12\x0b\n\x07RELEASE\x10\x01*?\n\x0c\x41rchitecture\x12\x0b\n\x07UNKNOWN\x10\x00\x12\x10\n\x0cX86_INTERNAL\x10\x01\x12\x10\n\x0c\x41RM_INTERNAL\x10\x02\x42Y\n!com.google.chrome.crosinfra.protoZ4go.chromium.org/chromiumos/infra/proto/go/chromiumosb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.ge_config_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'\n!com.google.chrome.crosinfra.protoZ4go.chromium.org/chromiumos/infra/proto/go/chromiumos'
  _BUILDERTYPE._serialized_start=1045
  _BUILDERTYPE._serialized_end=1097
  _ARCHITECTURE._serialized_start=1099
  _ARCHITECTURE._serialized_end=1162
  _MODEL._serialized_start=43
  _MODEL._serialized_end=280
  _REFERENCEBOARDUNIFIEDBUILDCONFIG._serialized_start=283
  _REFERENCEBOARDUNIFIEDBUILDCONFIG._serialized_end=565
  _CONFIG._serialized_start=568
  _CONFIG._serialized_end=723
  _BUILDBOARD._serialized_start=726
  _BUILDBOARD._serialized_end=854
  _GECONFIG._serialized_start=857
  _GECONFIG._serialized_end=1043
# @@protoc_insertion_point(module_scope)
