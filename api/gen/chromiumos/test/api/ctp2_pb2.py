# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/api/ctp2.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.test.api import provision_pb2 as chromiumos_dot_test_dot_api_dot_provision__pb2
from chromite.api.gen.chromiumos.test.api import test_suite_pb2 as chromiumos_dot_test_dot_api_dot_test__suite__pb2
from chromite.api.gen.chromiumos.test.api import test_case_metadata_pb2 as chromiumos_dot_test_dot_api_dot_test__case__metadata__pb2
from chromite.api.gen.chromiumos.build.api import container_metadata_pb2 as chromiumos_dot_build_dot_api_dot_container__metadata__pb2
from chromite.api.gen.chromiumos.test.lab.api import dut_pb2 as chromiumos_dot_test_dot_lab_dot_api_dot_dut__pb2
from chromite.third_party.google.protobuf import any_pb2 as google_dot_protobuf_dot_any__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1e\x63hromiumos/test/api/ctp2.proto\x12\x13\x63hromiumos.test.api\x1a#chromiumos/test/api/provision.proto\x1a$chromiumos/test/api/test_suite.proto\x1a,chromiumos/test/api/test_case_metadata.proto\x1a-chromiumos/build/api/container_metadata.proto\x1a!chromiumos/test/lab/api/dut.proto\x1a\x19google/protobuf/any.proto\"\xe6\x02\n\x0c\x43TPv2Request\x12\x38\n\rsuite_request\x18\x01 \x01(\x0b\x32!.chromiumos.test.api.SuiteRequest\x12-\n\x07targets\x18\x02 \x03(\x0b\x32\x1c.chromiumos.test.api.Targets\x12>\n\x10schedule_targets\x18\x07 \x03(\x0b\x32$.chromiumos.test.api.ScheduleTargets\x12\x36\n\x0ekarbon_filters\x18\x03 \x03(\x0b\x32\x1e.chromiumos.test.api.CTPFilter\x12\x36\n\x0ekoffee_filters\x18\x04 \x03(\x0b\x32\x1e.chromiumos.test.api.CTPFilter\x12\x0c\n\x04pool\x18\x05 \x01(\t\x12/\n\x11scheduke_metadata\x18\x06 \x01(\x0b\x32\x14.google.protobuf.Any\"\x91\x01\n\x0cSuiteRequest\x12\x34\n\ntest_suite\x18\x01 \x01(\x0b\x32\x1e.chromiumos.test.api.TestSuiteH\x00\x12:\n\x11hierarchical_plan\x18\x02 \x01(\x0b\x32\x1d.chromiumos.test.api.ReservedH\x00\x42\x0f\n\rsuite_request\"&\n\x08KeyValue\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t\"@\n\x0fScheduleTargets\x12-\n\x07targets\x18\x01 \x03(\x0b\x32\x1c.chromiumos.test.api.Targets\"n\n\x07Targets\x12\x30\n\thw_target\x18\x01 \x01(\x0b\x32\x1d.chromiumos.test.api.HWTarget\x12\x31\n\nsw_targets\x18\x02 \x03(\x0b\x32\x1d.chromiumos.test.api.SWTarget\"v\n\x08HWTarget\x12\x32\n\tlegacy_hw\x18\x01 \x01(\x0b\x32\x1d.chromiumos.test.api.LegacyHWH\x00\x12,\n\x06\x64\x64\x64_hw\x18\x02 \x01(\x0b\x32\x1a.chromiumos.test.api.DDDHWH\x00\x42\x08\n\x06target\"y\n\x08SWTarget\x12\x32\n\tlegacy_sw\x18\x01 \x01(\x0b\x32\x1d.chromiumos.test.api.LegacySWH\x00\x12,\n\x06\x64\x64\x64_sw\x18\x02 \x01(\x0b\x32\x1a.chromiumos.test.api.DDDSWH\x00\x42\x0b\n\tsw_target\"o\n\x08LegacySW\x12\r\n\x05\x62uild\x18\x01 \x01(\t\x12\x10\n\x08gcs_path\x18\x02 \x01(\t\x12\x31\n\nkey_values\x18\x03 \x03(\x0b\x32\x1d.chromiumos.test.api.KeyValue\x12\x0f\n\x07variant\x18\x04 \x01(\t\"\x07\n\x05\x44\x44\x44SW\"s\n\x08LegacyHW\x12\r\n\x05\x62oard\x18\x01 \x01(\t\x12\r\n\x05model\x18\x02 \x01(\t\x12\x13\n\x07variant\x18\x03 \x01(\tB\x02\x18\x01\x12\x34\n\tmulti_dut\x18\x04 \x01(\x0b\x32\x1d.chromiumos.test.api.MultiDutB\x02\x18\x01\"\x07\n\x05\x44\x44\x44HW\"*\n\x04Pair\x12\x0f\n\x07primary\x18\x01 \x01(\t\x12\x11\n\tsecondary\x18\x02 \x01(\t\"_\n\x08MultiDut\x12)\n\x06\x62oards\x18\x01 \x01(\x0b\x32\x19.chromiumos.test.api.Pair\x12(\n\x05model\x18\x02 \x01(\x0b\x32\x19.chromiumos.test.api.Pair\"\xc2\x01\n\tCTPFilter\x12;\n\tcontainer\x18\x01 \x01(\x0b\x32(.chromiumos.build.api.ContainerImageInfo\x12\x46\n\x14\x64\x65pendent_containers\x18\x02 \x03(\x0b\x32(.chromiumos.build.api.ContainerImageInfo\x12\x30\n\x12\x63ontainer_metadata\x18\x03 \x01(\x0b\x32\x14.google.protobuf.Any\"\n\n\x08Reserved\"|\n\x10InternalTestplan\x12\x34\n\ntest_cases\x18\x01 \x03(\x0b\x32 .chromiumos.test.api.CTPTestCase\x12\x32\n\nsuite_info\x18\x02 \x01(\x0b\x32\x1e.chromiumos.test.api.SuiteInfo\"\xd0\x01\n\x0b\x43TPTestCase\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x37\n\x08metadata\x18\x02 \x01(\x0b\x32%.chromiumos.test.api.TestCaseMetadata\x12<\n\x0fhw_requirements\x18\x03 \x03(\x0b\x32#.chromiumos.test.api.HWRequirements\x12<\n\x0fsw_requirements\x18\x04 \x03(\x0b\x32#.chromiumos.test.api.SWRequirements\"\x81\x01\n\tSuiteInfo\x12:\n\x0esuite_metadata\x18\x01 \x01(\x0b\x32\".chromiumos.test.api.SuiteMetadata\x12\x38\n\rsuite_request\x18\x02 \x01(\x0b\x32!.chromiumos.test.api.SuiteRequest\"\xcc\x01\n\rSuiteMetadata\x12\x44\n\x13target_requirements\x18\x01 \x03(\x0b\x32\'.chromiumos.test.api.TargetRequirements\x12U\n\x1cschedule_target_requirements\x18\x04 \x03(\x0b\x32/.chromiumos.test.api.ScheduleTargetRequirements\x12\x10\n\x08\x63hannels\x18\x02 \x03(\t\x12\x0c\n\x04pool\x18\x03 \x01(\t\"b\n\x1aScheduleTargetRequirements\x12\x44\n\x13target_requirements\x18\x01 \x03(\x0b\x32\'.chromiumos.test.api.TargetRequirements\"\x8a\x01\n\x12TargetRequirements\x12<\n\x0fhw_requirements\x18\x01 \x01(\x0b\x32#.chromiumos.test.api.HWRequirements\x12\x36\n\x0fsw_requirements\x18\x02 \x03(\x0b\x32\x1d.chromiumos.test.api.LegacySW\"\xd5\x01\n\x0eHWRequirements\x12>\n\rhw_definition\x18\x01 \x03(\x0b\x32\'.chromiumos.test.api.SwarmingDefinition\x12\x38\n\x05state\x18\x06 \x01(\x0e\x32).chromiumos.test.api.HWRequirements.State\"I\n\x05State\x12\x0c\n\x08REQUIRED\x10\x00\x12\x0c\n\x08OPTIONAL\x10\x01\x12\r\n\tPREFERRED\x10\x02\x12\n\n\x06\x42\x41NNED\x10\x03\x12\t\n\x05ONEOF\x10\x04\"\x10\n\x0eSWRequirements\"\xc1\x01\n\rProvisionInfo\x12<\n\x0finstall_request\x18\x01 \x01(\x0b\x32#.chromiumos.test.api.InstallRequest\x12\x12\n\nidentifier\x18\x02 \x01(\t\x12\x35\n\x04type\x18\x03 \x01(\x0e\x32\'.chromiumos.test.api.ProvisionInfo.Type\"\'\n\x04Type\x12\x08\n\x04\x43ROS\x10\x00\x12\x0b\n\x07\x41NDROID\x10\x01\x12\x08\n\x04ROFW\x10\x02\"\x99\x01\n\x12SwarmingDefinition\x12.\n\x08\x64ut_info\x18\x01 \x01(\x0b\x32\x1c.chromiumos.test.lab.api.Dut\x12:\n\x0eprovision_info\x18\x02 \x03(\x0b\x32\".chromiumos.test.api.ProvisionInfo\x12\x17\n\x0fswarming_labels\x18\x03 \x03(\t\"R\n\rCTPv2Response\x12\x41\n\rtest_requests\x18\x01 \x03(\x0b\x32*.chromiumos.test.api.CrosTestRunnerRequest\"\x17\n\x15\x43rosTestRunnerRequest2h\n\x0c\x43TPv2Service\x12X\n\x0fRequestResolver\x12!.chromiumos.test.api.CTPv2Request\x1a\".chromiumos.test.api.CTPv2Response2o\n\x14GenericFilterService\x12W\n\x07\x45xecute\x12%.chromiumos.test.api.InternalTestplan\x1a%.chromiumos.test.api.InternalTestplanB/Z-go.chromium.org/chromiumos/config/go/test/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.api.ctp2_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z-go.chromium.org/chromiumos/config/go/test/api'
  _LEGACYHW.fields_by_name['variant']._options = None
  _LEGACYHW.fields_by_name['variant']._serialized_options = b'\030\001'
  _LEGACYHW.fields_by_name['multi_dut']._options = None
  _LEGACYHW.fields_by_name['multi_dut']._serialized_options = b'\030\001'
  _CTPV2REQUEST._serialized_start=286
  _CTPV2REQUEST._serialized_end=644
  _SUITEREQUEST._serialized_start=647
  _SUITEREQUEST._serialized_end=792
  _KEYVALUE._serialized_start=794
  _KEYVALUE._serialized_end=832
  _SCHEDULETARGETS._serialized_start=834
  _SCHEDULETARGETS._serialized_end=898
  _TARGETS._serialized_start=900
  _TARGETS._serialized_end=1010
  _HWTARGET._serialized_start=1012
  _HWTARGET._serialized_end=1130
  _SWTARGET._serialized_start=1132
  _SWTARGET._serialized_end=1253
  _LEGACYSW._serialized_start=1255
  _LEGACYSW._serialized_end=1366
  _DDDSW._serialized_start=1368
  _DDDSW._serialized_end=1375
  _LEGACYHW._serialized_start=1377
  _LEGACYHW._serialized_end=1492
  _DDDHW._serialized_start=1494
  _DDDHW._serialized_end=1501
  _PAIR._serialized_start=1503
  _PAIR._serialized_end=1545
  _MULTIDUT._serialized_start=1547
  _MULTIDUT._serialized_end=1642
  _CTPFILTER._serialized_start=1645
  _CTPFILTER._serialized_end=1839
  _RESERVED._serialized_start=1841
  _RESERVED._serialized_end=1851
  _INTERNALTESTPLAN._serialized_start=1853
  _INTERNALTESTPLAN._serialized_end=1977
  _CTPTESTCASE._serialized_start=1980
  _CTPTESTCASE._serialized_end=2188
  _SUITEINFO._serialized_start=2191
  _SUITEINFO._serialized_end=2320
  _SUITEMETADATA._serialized_start=2323
  _SUITEMETADATA._serialized_end=2527
  _SCHEDULETARGETREQUIREMENTS._serialized_start=2529
  _SCHEDULETARGETREQUIREMENTS._serialized_end=2627
  _TARGETREQUIREMENTS._serialized_start=2630
  _TARGETREQUIREMENTS._serialized_end=2768
  _HWREQUIREMENTS._serialized_start=2771
  _HWREQUIREMENTS._serialized_end=2984
  _HWREQUIREMENTS_STATE._serialized_start=2911
  _HWREQUIREMENTS_STATE._serialized_end=2984
  _SWREQUIREMENTS._serialized_start=2986
  _SWREQUIREMENTS._serialized_end=3002
  _PROVISIONINFO._serialized_start=3005
  _PROVISIONINFO._serialized_end=3198
  _PROVISIONINFO_TYPE._serialized_start=3159
  _PROVISIONINFO_TYPE._serialized_end=3198
  _SWARMINGDEFINITION._serialized_start=3201
  _SWARMINGDEFINITION._serialized_end=3354
  _CTPV2RESPONSE._serialized_start=3356
  _CTPV2RESPONSE._serialized_end=3438
  _CROSTESTRUNNERREQUEST._serialized_start=3440
  _CROSTESTRUNNERREQUEST._serialized_end=3463
  _CTPV2SERVICE._serialized_start=3465
  _CTPV2SERVICE._serialized_end=3569
  _GENERICFILTERSERVICE._serialized_start=3571
  _GENERICFILTERSERVICE._serialized_end=3682
# @@protoc_insertion_point(module_scope)
