# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: go.chromium.org/luci/vpython/api/vpython/spec.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen_test.go.chromium.org.luci.vpython.api.vpython import pep425_pb2 as go_dot_chromium_dot_org_dot_luci_dot_vpython_dot_api_dot_vpython_dot_pep425__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n3go.chromium.org/luci/vpython/api/vpython/spec.proto\x12\x07vpython\x1a\x35go.chromium.org/luci/vpython/api/vpython/pep425.proto\"\x9a\x02\n\x04Spec\x12\x16\n\x0epython_version\x18\x01 \x01(\t\x12$\n\x05wheel\x18\x02 \x03(\x0b\x32\x15.vpython.Spec.Package\x12)\n\nvirtualenv\x18\x03 \x01(\x0b\x32\x15.vpython.Spec.Package\x12-\n\x11verify_pep425_tag\x18\x04 \x03(\x0b\x32\x12.vpython.PEP425Tag\x1az\n\x07Package\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x0f\n\x07version\x18\x02 \x01(\t\x12%\n\tmatch_tag\x18\x03 \x03(\x0b\x32\x12.vpython.PEP425Tag\x12)\n\rnot_match_tag\x18\x04 \x03(\x0b\x32\x12.vpython.PEP425TagB*Z(go.chromium.org/luci/vpython/api/vpythonb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'go.chromium.org.luci.vpython.api.vpython.spec_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z(go.chromium.org/luci/vpython/api/vpython'
  _SPEC._serialized_start=120
  _SPEC._serialized_end=402
  _SPEC_PACKAGE._serialized_start=280
  _SPEC_PACKAGE._serialized_end=402
# @@protoc_insertion_point(module_scope)