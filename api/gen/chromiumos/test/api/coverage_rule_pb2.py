# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/api/coverage_rule.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.third_party.google.protobuf import wrappers_pb2 as google_dot_protobuf_dot_wrappers__pb2
from chromite.api.gen.chromiumos.test.api import dut_attribute_pb2 as chromiumos_dot_test_dot_api_dot_dut__attribute__pb2
from chromite.api.gen.chromiumos.test.api import test_suite_pb2 as chromiumos_dot_test_dot_api_dot_test__suite__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\'chromiumos/test/api/coverage_rule.proto\x12\x13\x63hromiumos.test.api\x1a\x1egoogle/protobuf/wrappers.proto\x1a\'chromiumos/test/api/dut_attribute.proto\x1a$chromiumos/test/api/test_suite.proto\"\x86\x02\n\x0c\x43overageRule\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x33\n\x0btest_suites\x18\x02 \x03(\x0b\x32\x1e.chromiumos.test.api.TestSuite\x12\x33\n\x0b\x64ut_targets\x18\x04 \x03(\x0b\x32\x1e.chromiumos.test.api.DutTarget\x12,\n\x08\x63ritical\x18\x05 \x01(\x0b\x32\x1a.google.protobuf.BoolValue\x12\x13\n\x0brun_via_cft\x18\x06 \x01(\x08\x12;\n\x0c\x64ut_criteria\x18\x03 \x03(\x0b\x32!.chromiumos.test.api.DutCriterionB\x02\x18\x01\"z\n\x11\x43overageRuleBqRow\x12\x0c\n\x04host\x18\x01 \x01(\t\x12\x0f\n\x07project\x18\x02 \x01(\t\x12\x0c\n\x04path\x18\x03 \x01(\t\x12\x38\n\rcoverage_rule\x18\x04 \x01(\x0b\x32!.chromiumos.test.api.CoverageRuleB/Z-go.chromium.org/chromiumos/config/go/test/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.api.coverage_rule_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z-go.chromium.org/chromiumos/config/go/test/api'
  _COVERAGERULE.fields_by_name['dut_criteria']._options = None
  _COVERAGERULE.fields_by_name['dut_criteria']._serialized_options = b'\030\001'
  _COVERAGERULE._serialized_start=176
  _COVERAGERULE._serialized_end=438
  _COVERAGERULEBQROW._serialized_start=440
  _COVERAGERULEBQROW._serialized_end=562
# @@protoc_insertion_point(module_scope)
