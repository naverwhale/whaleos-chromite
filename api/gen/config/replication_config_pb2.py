# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: config/replication_config.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.third_party.google.protobuf import field_mask_pb2 as google_dot_protobuf_dot_field__mask__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1f\x63onfig/replication_config.proto\x12\x06\x63onfig\x1a google/protobuf/field_mask.proto\"6\n\x15StringReplacementRule\x12\x0e\n\x06\x62\x65\x66ore\x18\x01 \x01(\t\x12\r\n\x05\x61\x66ter\x18\x02 \x01(\t\"\x95\x02\n\x13\x46ileReplicationRule\x12\x13\n\x0bsource_path\x18\x01 \x01(\t\x12\x18\n\x10\x64\x65stination_path\x18\x02 \x01(\t\x12#\n\tfile_type\x18\x03 \x01(\x0e\x32\x10.config.FileType\x12\x31\n\x10replication_type\x18\x04 \x01(\x0e\x32\x17.config.ReplicationType\x12\x36\n\x12\x64\x65stination_fields\x18\x05 \x01(\x0b\x32\x1a.google.protobuf.FieldMask\x12?\n\x18string_replacement_rules\x18\x06 \x03(\x0b\x32\x1d.config.StringReplacementRule\"P\n\x11ReplicationConfig\x12;\n\x16\x66ile_replication_rules\x18\x01 \x03(\x0b\x32\x1b.config.FileReplicationRule*d\n\x08\x46ileType\x12\x19\n\x15\x46ILE_TYPE_UNSPECIFIED\x10\x00\x12\x12\n\x0e\x46ILE_TYPE_JSON\x10\x01\x12\x14\n\x10\x46ILE_TYPE_JSONPB\x10\x02\x12\x13\n\x0f\x46ILE_TYPE_OTHER\x10\x03*k\n\x0fReplicationType\x12 \n\x1cREPLICATION_TYPE_UNSPECIFIED\x10\x00\x12\x19\n\x15REPLICATION_TYPE_COPY\x10\x01\x12\x1b\n\x17REPLICATION_TYPE_FILTER\x10\x02\x42/Z-go.chromium.org/chromiumos/infra/proto/configb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'config.replication_config_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z-go.chromium.org/chromiumos/infra/proto/config'
  _FILETYPE._serialized_start=495
  _FILETYPE._serialized_end=595
  _REPLICATIONTYPE._serialized_start=597
  _REPLICATIONTYPE._serialized_end=704
  _STRINGREPLACEMENTRULE._serialized_start=77
  _STRINGREPLACEMENTRULE._serialized_end=131
  _FILEREPLICATIONRULE._serialized_start=134
  _FILEREPLICATIONRULE._serialized_end=411
  _REPLICATIONCONFIG._serialized_start=413
  _REPLICATIONCONFIG._serialized_end=493
# @@protoc_insertion_point(module_scope)
