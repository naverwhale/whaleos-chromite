# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/conductor.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos import checkpoint_pb2 as chromiumos_dot_checkpoint__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1a\x63hromiumos/conductor.proto\x12\nchromiumos\x1a\x1b\x63hromiumos/checkpoint.proto\"\xcd\x02\n\tRetryRule\x12\x14\n\x0cinsufficient\x18\n \x01(\x08\x12\x0e\n\x06status\x18\x01 \x03(\x05\x12\x17\n\x0f\x62uilder_name_re\x18\x02 \x03(\t\x12\x1b\n\x13summary_markdown_re\x18\x03 \x03(\t\x12\x30\n\x11\x66\x61iled_checkpoint\x18\x04 \x01(\x0e\x32\x15.chromiumos.RetryStep\x12\x30\n\x11\x62\x65\x66ore_checkpoint\x18\x0b \x01(\x0e\x32\x15.chromiumos.RetryStep\x12\x16\n\x0e\x63utoff_percent\x18\x05 \x01(\x02\x12\x16\n\x0e\x63utoff_seconds\x18\x06 \x01(\x05\x12\x1c\n\x14\x62uild_runtime_cutoff\x18\t \x01(\x05\x12\x13\n\x0bmax_retries\x18\x07 \x01(\x05\x12\x1d\n\x15max_retries_per_build\x18\x08 \x01(\x05\"5\n\rCollectConfig\x12$\n\x05rules\x18\x01 \x03(\x0b\x32\x15.chromiumos.RetryRuleBY\n!com.google.chrome.crosinfra.protoZ4go.chromium.org/chromiumos/infra/proto/go/chromiumosb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.conductor_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'\n!com.google.chrome.crosinfra.protoZ4go.chromium.org/chromiumos/infra/proto/go/chromiumos'
  _RETRYRULE._serialized_start=72
  _RETRYRULE._serialized_end=405
  _COLLECTCONFIG._serialized_start=407
  _COLLECTCONFIG._serialized_end=460
# @@protoc_insertion_point(module_scope)
