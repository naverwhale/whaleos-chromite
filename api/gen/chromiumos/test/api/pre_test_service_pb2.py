# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/api/pre_test_service.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.test.api import test_suite_pb2 as chromiumos_dot_test_dot_api_dot_test__suite__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n*chromiumos/test/api/pre_test_service.proto\x12\x13\x63hromiumos.test.api\x1a$chromiumos/test/api/test_suite.proto\"\xcd\x02\n\x12\x46ilterFlakyRequest\x12?\n\x10pass_rate_policy\x18\x01 \x01(\x0b\x32#.chromiumos.test.api.PassRatePolicyH\x00\x12M\n\x17stability_sensor_policy\x18\x02 \x01(\x0b\x32*.chromiumos.test.api.StabilitySensorPolicyH\x00\x12\x33\n\x0btest_suites\x18\x03 \x03(\x0b\x32\x1e.chromiumos.test.api.TestSuite\x12\x11\n\tmilestone\x18\x04 \x01(\t\x12\x0f\n\x05\x62oard\x18\x05 \x01(\tH\x01\x12\x17\n\x0f\x64\x65\x66\x61ult_enabled\x18\x06 \x01(\x08\x12\x0c\n\x04\x62\x62id\x18\x07 \x01(\t\x12\x12\n\nis_dry_run\x18\x08 \x01(\x08\x42\x08\n\x06policyB\t\n\x07variant\"a\n\x13\x46ilterFlakyResponse\x12\x33\n\x0btest_suites\x18\x01 \x03(\x0b\x32\x1e.chromiumos.test.api.TestSuite\x12\x15\n\rremoved_tests\x18\x02 \x03(\t\"\x17\n\x15StabilitySensorPolicy\"\xf7\x02\n\x0ePassRatePolicy\x12\x11\n\tpass_rate\x18\x01 \x01(\x05\x12\x10\n\x08min_runs\x18\x02 \x01(\x05\x12\x19\n\x11num_of_milestones\x18\x04 \x01(\x05\x12\x1b\n\x13\x66orce_enabled_tests\x18\x05 \x03(\t\x12\x1c\n\x14\x66orce_disabled_tests\x18\x06 \x03(\t\x12\x1c\n\x14\x66orce_enabled_boards\x18\x07 \x03(\t\x12\x18\n\x10pass_rate_recent\x18\x08 \x01(\x05\x12\x17\n\x0fmin_runs_recent\x18\t \x01(\x05\x12\x15\n\rrecent_window\x18\n \x01(\x05\x12\x0e\n\x06\x64ryrun\x18\x0b \x01(\x08\x12:\n\x0btestconfigs\x18\x0c \x03(\x0b\x32%.chromiumos.test.api.FilterTestConfig\x12\x1c\n\x14max_filtered_percent\x18\r \x01(\x05\x12\x18\n\x10max_filtered_int\x18\x0e \x01(\x05\"@\n\nFilterCfgs\x12\x32\n\nfilter_cfg\x18\x01 \x03(\x0b\x32\x1e.chromiumos.test.api.FilterCfg\"p\n\tFilterCfg\x12=\n\x10pass_rate_policy\x18\x01 \x01(\x0b\x32#.chromiumos.test.api.PassRatePolicy\x12\x13\n\x0btest_suites\x18\x02 \x03(\t\x12\x0f\n\x07opt_out\x18\x04 \x01(\x08\"\xb0\x01\n\x10\x46ilterTestConfig\x12\x0c\n\x04test\x18\x01 \x01(\t\x12\r\n\x05\x62oard\x18\x02 \x03(\t\x12>\n\x07setting\x18\x03 \x01(\x0e\x32-.chromiumos.test.api.FilterTestConfig.Setting\x12\x0c\n\x04\x62ugs\x18\x04 \x03(\t\"1\n\x07Setting\x12\x0b\n\x07NOT_SET\x10\x00\x12\x0b\n\x07\x45NABLED\x10\x01\x12\x0c\n\x08\x44ISABLED\x10\x02\x32w\n\x0ePreTestService\x12\x65\n\x10\x46ilterFlakyTests\x12\'.chromiumos.test.api.FilterFlakyRequest\x1a(.chromiumos.test.api.FilterFlakyResponseB/Z-go.chromium.org/chromiumos/config/go/test/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.api.pre_test_service_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z-go.chromium.org/chromiumos/config/go/test/api'
  _FILTERFLAKYREQUEST._serialized_start=106
  _FILTERFLAKYREQUEST._serialized_end=439
  _FILTERFLAKYRESPONSE._serialized_start=441
  _FILTERFLAKYRESPONSE._serialized_end=538
  _STABILITYSENSORPOLICY._serialized_start=540
  _STABILITYSENSORPOLICY._serialized_end=563
  _PASSRATEPOLICY._serialized_start=566
  _PASSRATEPOLICY._serialized_end=941
  _FILTERCFGS._serialized_start=943
  _FILTERCFGS._serialized_end=1007
  _FILTERCFG._serialized_start=1009
  _FILTERCFG._serialized_end=1121
  _FILTERTESTCONFIG._serialized_start=1124
  _FILTERTESTCONFIG._serialized_end=1300
  _FILTERTESTCONFIG_SETTING._serialized_start=1251
  _FILTERTESTCONFIG_SETTING._serialized_end=1300
  _PRETESTSERVICE._serialized_start=1302
  _PRETESTSERVICE._serialized_end=1421
# @@protoc_insertion_point(module_scope)
