# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test_disablement.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n!chromiumos/test_disablement.proto\x12\nchromiumos\"\xdb\x03\n\x0fTestDisablement\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x41\n\x0c\x64ut_criteria\x18\x02 \x03(\x0b\x32+.chromiumos.TestDisablement.FilterCriterion\x12\x42\n\rtest_criteria\x18\x03 \x03(\x0b\x32+.chromiumos.TestDisablement.FilterCriterion\x12\x45\n\x10\x63ontext_criteria\x18\x04 \x03(\x0b\x32+.chromiumos.TestDisablement.FilterCriterion\x12:\n\x08\x62\x65havior\x18\x05 \x01(\x0e\x32(.chromiumos.TestDisablement.TestBehavior\x12\x0f\n\x07\x62ug_ids\x18\x06 \x03(\t\x1a?\n\x0f\x46ilterCriterion\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\x0e\n\x06values\x18\x02 \x03(\t\x12\x0f\n\x07negated\x18\x03 \x01(\x08\"^\n\x0cTestBehavior\x12\x0c\n\x08\x43RITICAL\x10\x00\x12\x11\n\rINFORMATIONAL\x10\x01\x12\x0b\n\x07INVALID\x10\x02\x12\x0c\n\x08WONT_FIX\x10\x03\x12\x12\n\x0eSKIP_TEMPORARY\x10\x04\"G\n\x12TestDisablementCfg\x12\x31\n\x0c\x64isablements\x18\x01 \x03(\x0b\x32\x1b.chromiumos.TestDisablement\"\xbf\x01\n\nExcludeCfg\x12\x39\n\rexclude_tests\x18\x01 \x03(\x0b\x32\".chromiumos.ExcludeCfg.ExcludeTest\x12;\n\x0e\x65xclude_suites\x18\x02 \x03(\x0b\x32#.chromiumos.ExcludeCfg.ExcludeSuite\x1a\x1b\n\x0b\x45xcludeTest\x12\x0c\n\x04name\x18\x01 \x01(\t\x1a\x1c\n\x0c\x45xcludeSuite\x12\x0c\n\x04name\x18\x01 \x01(\tBY\n!com.google.chrome.crosinfra.protoZ4go.chromium.org/chromiumos/infra/proto/go/chromiumosb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test_disablement_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'\n!com.google.chrome.crosinfra.protoZ4go.chromium.org/chromiumos/infra/proto/go/chromiumos'
  _TESTDISABLEMENT._serialized_start=50
  _TESTDISABLEMENT._serialized_end=525
  _TESTDISABLEMENT_FILTERCRITERION._serialized_start=366
  _TESTDISABLEMENT_FILTERCRITERION._serialized_end=429
  _TESTDISABLEMENT_TESTBEHAVIOR._serialized_start=431
  _TESTDISABLEMENT_TESTBEHAVIOR._serialized_end=525
  _TESTDISABLEMENTCFG._serialized_start=527
  _TESTDISABLEMENTCFG._serialized_end=598
  _EXCLUDECFG._serialized_start=601
  _EXCLUDECFG._serialized_end=792
  _EXCLUDECFG_EXCLUDETEST._serialized_start=735
  _EXCLUDECFG_EXCLUDETEST._serialized_end=762
  _EXCLUDECFG_EXCLUDESUITE._serialized_start=764
  _EXCLUDECFG_EXCLUDESUITE._serialized_end=792
# @@protoc_insertion_point(module_scope)
