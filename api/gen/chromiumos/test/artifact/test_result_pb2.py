# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/artifact/test_result.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos import storage_path_pb2 as chromiumos_dot_storage__path__pb2
from chromite.api.gen.chromiumos.test.api import provision_state_pb2 as chromiumos_dot_test_dot_api_dot_provision__state__pb2
from chromite.api.gen.chromiumos.test.api import test_case_metadata_pb2 as chromiumos_dot_test_dot_api_dot_test__case__metadata__pb2
from chromite.api.gen.chromiumos.test.api import test_case_result_pb2 as chromiumos_dot_test_dot_api_dot_test__case__result__pb2
from chromite.api.gen.chromiumos.test.api import test_harness_pb2 as chromiumos_dot_test_dot_api_dot_test__harness__pb2
from chromite.api.gen.chromiumos.test.lab.api import dut_pb2 as chromiumos_dot_test_dot_lab_dot_api_dot_dut__pb2
from chromite.third_party.google.protobuf import duration_pb2 as google_dot_protobuf_dot_duration__pb2
from chromite.third_party.google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n*chromiumos/test/artifact/test_result.proto\x12\x18\x63hromiumos.test.artifact\x1a\x1d\x63hromiumos/storage_path.proto\x1a)chromiumos/test/api/provision_state.proto\x1a,chromiumos/test/api/test_case_metadata.proto\x1a*chromiumos/test/api/test_case_result.proto\x1a&chromiumos/test/api/test_harness.proto\x1a!chromiumos/test/lab/api/dut.proto\x1a\x1egoogle/protobuf/duration.proto\x1a\x1fgoogle/protobuf/timestamp.proto\"\x96\x01\n\nTestResult\x12\x0f\n\x07version\x18\x01 \x01(\r\x12\x41\n\x0ftest_invocation\x18\x02 \x01(\x0b\x32(.chromiumos.test.artifact.TestInvocation\x12\x34\n\ttest_runs\x18\x03 \x03(\x0b\x32!.chromiumos.test.artifact.TestRun\"\xe0\x03\n\x0eTestInvocation\x12\x43\n\x10test_environment\x18\x01 \x01(\x0b\x32).chromiumos.test.artifact.TestEnvironment\x12:\n\x0c\x64ut_topology\x18\x02 \x01(\x0b\x32$.chromiumos.test.lab.api.DutTopology\x12G\n\x16primary_execution_info\x18\x03 \x01(\x0b\x32\'.chromiumos.test.artifact.ExecutionInfo\x12J\n\x19secondary_executions_info\x18\x04 \x03(\x0b\x32\'.chromiumos.test.artifact.ExecutionInfo\x12I\n\x13scheduling_metadata\x18\x05 \x01(\x0b\x32,.chromiumos.test.artifact.SchedulingMetadata\x12@\n\x04tags\x18\x06 \x03(\x0b\x32\x32.chromiumos.test.artifact.TestInvocation.TagsEntry\x1a+\n\tTagsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\"\xaf\x01\n\x0fTestEnvironment\x12\x38\n\x02id\x18\x01 \x01(\x0b\x32,.chromiumos.test.artifact.TestEnvironment.Id\x12\x42\n\x0c\x61ncestor_ids\x18\x02 \x03(\x0b\x32,.chromiumos.test.artifact.TestEnvironment.Id\x1a\x1e\n\x02Id\x12\n\n\x02id\x18\x01 \x01(\t\x12\x0c\n\x04name\x18\x02 \x01(\t\"\xd7\x03\n\x07TestRun\x12>\n\x0etest_case_info\x18\x01 \x01(\x0b\x32&.chromiumos.test.artifact.TestCaseInfo\x12*\n\tlogs_info\x18\x02 \x03(\x0b\x32\x17.chromiumos.StoragePath\x12>\n\x0e\x63ustom_results\x18\x03 \x03(\x0b\x32&.chromiumos.test.artifact.CustomResult\x12\x37\n\ttime_info\x18\x04 \x01(\x0b\x32$.chromiumos.test.artifact.TimingInfo\x12\x36\n\x0ctest_harness\x18\x05 \x01(\x0b\x32 .chromiumos.test.api.TestHarness\x12G\n\x12\x65xecution_metadata\x18\x06 \x01(\x0b\x32+.chromiumos.test.artifact.ExecutionMetadata\x12\x39\n\x04tags\x18\x07 \x03(\x0b\x32+.chromiumos.test.artifact.TestRun.TagsEntry\x1a+\n\tTagsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\"\x85\x02\n\x0cTestCaseInfo\x12\x41\n\x12test_case_metadata\x18\x01 \x01(\x0b\x32%.chromiumos.test.api.TestCaseMetadata\x12=\n\x10test_case_result\x18\x02 \x01(\x0b\x32#.chromiumos.test.api.TestCaseResult\x12\x14\n\x0c\x64isplay_name\x18\x03 \x01(\t\x12\r\n\x05suite\x18\x04 \x01(\t\x12\x0e\n\x06\x62ranch\x18\x05 \x01(\t\x12\x19\n\x11main_builder_name\x18\x06 \x01(\t\x12\x11\n\trequester\x18\x07 \x01(\t\x12\x10\n\x08\x63ontacts\x18\x08 \x03(\t\"\x80\x02\n\tBuildInfo\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x11\n\tmilestone\x18\x02 \x01(\x04\x12\x19\n\x11\x63hrome_os_version\x18\x03 \x01(\t\x12\x0e\n\x06source\x18\x04 \x01(\t\x12\x18\n\x10snapshot_version\x18\x05 \x01(\t\x12\x14\n\x0c\x62uild_target\x18\x06 \x01(\t\x12\x15\n\rboard_variant\x18\x07 \x01(\t\x12\r\n\x05\x62oard\x18\x08 \x01(\t\x12?\n\x0e\x62uild_metadata\x18\t \x01(\x0b\x32\'.chromiumos.test.artifact.BuildMetadata\x12\x10\n\x08\x63ritical\x18\n \x01(\x08\"\x8c\x07\n\rBuildMetadata\x12\x38\n\x03\x61rc\x18\x01 \x01(\x0b\x32+.chromiumos.test.artifact.BuildMetadata.Arc\x12>\n\x06\x63hrome\x18\x02 \x01(\x0b\x32..chromiumos.test.artifact.BuildMetadata.Chrome\x12\x43\n\tchrome_os\x18\x03 \x01(\x0b\x32\x30.chromiumos.test.artifact.BuildMetadata.ChromeOs\x12\x42\n\x08\x66irmware\x18\x04 \x01(\x0b\x32\x30.chromiumos.test.artifact.BuildMetadata.Firmware\x12>\n\x06kernel\x18\x05 \x01(\x0b\x32..chromiumos.test.artifact.BuildMetadata.Kernel\x12\x38\n\x03sku\x18\x06 \x01(\x0b\x32+.chromiumos.test.artifact.BuildMetadata.Sku\x12@\n\x07\x63hipset\x18\x07 \x01(\x0b\x32/.chromiumos.test.artifact.BuildMetadata.Chipset\x12\x42\n\x08\x63\x65llular\x18\x08 \x01(\x0b\x32\x30.chromiumos.test.artifact.BuildMetadata.Cellular\x12>\n\x06lacros\x18\t \x01(\x0b\x32..chromiumos.test.artifact.BuildMetadata.Lacros\x1a&\n\x03\x41rc\x12\x0f\n\x07version\x18\x01 \x01(\t\x12\x0e\n\x06\x62ranch\x18\x02 \x01(\t\x1a\x19\n\x06\x43hrome\x12\x0f\n\x07version\x18\x01 \x01(\t\x1a\x1b\n\x08\x43hromeOs\x12\x0f\n\x07version\x18\x01 \x01(\t\x1a\x32\n\x08\x46irmware\x12\x12\n\nro_version\x18\x01 \x01(\t\x12\x12\n\nrw_version\x18\x02 \x01(\t\x1a\x19\n\x06Kernel\x12\x0f\n\x07version\x18\x01 \x01(\t\x1a\x17\n\x03Sku\x12\x10\n\x08hwid_sku\x18\x01 \x01(\t\x1a\x1c\n\x07\x43hipset\x12\x11\n\twifi_chip\x18\x01 \x01(\t\x1a\x1b\n\x08\x43\x65llular\x12\x0f\n\x07\x63\x61rrier\x18\x01 \x01(\t\x1a\x35\n\x06Lacros\x12\x13\n\x0b\x61sh_version\x18\x01 \x01(\t\x12\x16\n\x0elacros_version\x18\x02 \x01(\t\"\xe7\x01\n\x07\x44utInfo\x12)\n\x03\x64ut\x18\x01 \x01(\x0b\x32\x1c.chromiumos.test.lab.api.Dut\x12<\n\x0fprovision_state\x18\x02 \x01(\x0b\x32#.chromiumos.test.api.ProvisionState\x12\x39\n\x04tags\x18\x03 \x03(\x0b\x32+.chromiumos.test.artifact.DutInfo.TagsEntry\x12\x0b\n\x03\x63\x62x\x18\x04 \x01(\x08\x1a+\n\tTagsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\"E\n\tDroneInfo\x12\r\n\x05\x64rone\x18\x01 \x01(\t\x12\x13\n\x0b\x64rone_image\x18\x02 \x01(\t\x12\x14\n\x0c\x64rone_server\x18\x03 \x01(\t\"k\n\x0cSwarmingInfo\x12\x0f\n\x07task_id\x18\x01 \x01(\t\x12\x15\n\rsuite_task_id\x18\x02 \x01(\t\x12\x11\n\ttask_name\x18\x03 \x01(\t\x12\x0c\n\x04pool\x18\x04 \x01(\t\x12\x12\n\nlabel_pool\x18\x05 \x01(\t\"=\n\tBuilderID\x12\x0f\n\x07project\x18\x01 \x01(\t\x12\x0e\n\x06\x62ucket\x18\x02 \x01(\t\x12\x0f\n\x07\x62uilder\x18\x03 \x01(\t\"i\n\x0f\x42uildbucketInfo\x12\n\n\x02id\x18\x01 \x01(\x03\x12\x34\n\x07\x62uilder\x18\x02 \x01(\x0b\x32#.chromiumos.test.artifact.BuilderID\x12\x14\n\x0c\x61ncestor_ids\x18\x03 \x03(\x03\"\xc9\x01\n\nSkylabInfo\x12\x37\n\ndrone_info\x18\x01 \x01(\x0b\x32#.chromiumos.test.artifact.DroneInfo\x12=\n\rswarming_info\x18\x02 \x01(\x0b\x32&.chromiumos.test.artifact.SwarmingInfo\x12\x43\n\x10\x62uildbucket_info\x18\x03 \x01(\x0b\x32).chromiumos.test.artifact.BuildbucketInfo\"\x90\x01\n\nSatlabInfo\x12=\n\rswarming_info\x18\x01 \x01(\x0b\x32&.chromiumos.test.artifact.SwarmingInfo\x12\x43\n\x10\x62uildbucket_info\x18\x02 \x01(\x0b\x32).chromiumos.test.artifact.BuildbucketInfo\"\x83\x02\n\rExecutionInfo\x12\x37\n\nbuild_info\x18\x01 \x01(\x0b\x32#.chromiumos.test.artifact.BuildInfo\x12\x33\n\x08\x64ut_info\x18\x02 \x01(\x0b\x32!.chromiumos.test.artifact.DutInfo\x12;\n\x0bskylab_info\x18\x03 \x01(\x0b\x32$.chromiumos.test.artifact.SkylabInfoH\x00\x12;\n\x0bsatlab_info\x18\x04 \x01(\x0b\x32$.chromiumos.test.artifact.SatlabInfoH\x00\x42\n\n\x08\x65nv_info\"\x8f\x01\n\x0c\x43ustomResult\x12\x35\n\x14result_artifact_path\x18\x01 \x01(\x0b\x32\x17.chromiumos.StoragePath\x12\x39\n\x03\x63ts\x18\x02 \x01(\x0b\x32*.chromiumos.test.artifact.CustomResult.CtsH\x00\x1a\x05\n\x03\x43tsB\x06\n\x04type\"\x9c\x01\n\nTimingInfo\x12/\n\x0bqueued_time\x18\x01 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12\x30\n\x0cstarted_time\x18\x02 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12+\n\x08\x64uration\x18\x03 \x01(\x0b\x32\x19.google.protobuf.Duration\"\x83\x03\n\x12SchedulingMetadata\x12\x65\n\x15hardware_dependencies\x18\x01 \x03(\x0b\x32\x46.chromiumos.test.artifact.SchedulingMetadata.HardwareDependenciesEntry\x12Y\n\x0fscheduling_args\x18\x02 \x03(\x0b\x32@.chromiumos.test.artifact.SchedulingMetadata.SchedulingArgsEntry\x12\x37\n\ttime_info\x18\x03 \x01(\x0b\x32$.chromiumos.test.artifact.TimingInfo\x1a;\n\x19HardwareDependenciesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\x1a\x35\n\x13SchedulingArgsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\"\xb5\x02\n\x11\x45xecutionMetadata\x12\x64\n\x15software_dependencies\x18\x01 \x03(\x0b\x32\x45.chromiumos.test.artifact.ExecutionMetadata.SoftwareDependenciesEntry\x12L\n\ttest_args\x18\x02 \x03(\x0b\x32\x39.chromiumos.test.artifact.ExecutionMetadata.TestArgsEntry\x1a;\n\x19SoftwareDependenciesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\x1a/\n\rTestArgsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\x42\x34Z2go.chromium.org/chromiumos/config/go/test/artifactb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.artifact.test_result_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z2go.chromium.org/chromiumos/config/go/test/artifact'
  _TESTINVOCATION_TAGSENTRY._options = None
  _TESTINVOCATION_TAGSENTRY._serialized_options = b'8\001'
  _TESTRUN_TAGSENTRY._options = None
  _TESTRUN_TAGSENTRY._serialized_options = b'8\001'
  _DUTINFO_TAGSENTRY._options = None
  _DUTINFO_TAGSENTRY._serialized_options = b'8\001'
  _SCHEDULINGMETADATA_HARDWAREDEPENDENCIESENTRY._options = None
  _SCHEDULINGMETADATA_HARDWAREDEPENDENCIESENTRY._serialized_options = b'8\001'
  _SCHEDULINGMETADATA_SCHEDULINGARGSENTRY._options = None
  _SCHEDULINGMETADATA_SCHEDULINGARGSENTRY._serialized_options = b'8\001'
  _EXECUTIONMETADATA_SOFTWAREDEPENDENCIESENTRY._options = None
  _EXECUTIONMETADATA_SOFTWAREDEPENDENCIESENTRY._serialized_options = b'8\001'
  _EXECUTIONMETADATA_TESTARGSENTRY._options = None
  _EXECUTIONMETADATA_TESTARGSENTRY._serialized_options = b'8\001'
  _TESTRESULT._serialized_start=377
  _TESTRESULT._serialized_end=527
  _TESTINVOCATION._serialized_start=530
  _TESTINVOCATION._serialized_end=1010
  _TESTINVOCATION_TAGSENTRY._serialized_start=967
  _TESTINVOCATION_TAGSENTRY._serialized_end=1010
  _TESTENVIRONMENT._serialized_start=1013
  _TESTENVIRONMENT._serialized_end=1188
  _TESTENVIRONMENT_ID._serialized_start=1158
  _TESTENVIRONMENT_ID._serialized_end=1188
  _TESTRUN._serialized_start=1191
  _TESTRUN._serialized_end=1662
  _TESTRUN_TAGSENTRY._serialized_start=967
  _TESTRUN_TAGSENTRY._serialized_end=1010
  _TESTCASEINFO._serialized_start=1665
  _TESTCASEINFO._serialized_end=1926
  _BUILDINFO._serialized_start=1929
  _BUILDINFO._serialized_end=2185
  _BUILDMETADATA._serialized_start=2188
  _BUILDMETADATA._serialized_end=3096
  _BUILDMETADATA_ARC._serialized_start=2784
  _BUILDMETADATA_ARC._serialized_end=2822
  _BUILDMETADATA_CHROME._serialized_start=2824
  _BUILDMETADATA_CHROME._serialized_end=2849
  _BUILDMETADATA_CHROMEOS._serialized_start=2851
  _BUILDMETADATA_CHROMEOS._serialized_end=2878
  _BUILDMETADATA_FIRMWARE._serialized_start=2880
  _BUILDMETADATA_FIRMWARE._serialized_end=2930
  _BUILDMETADATA_KERNEL._serialized_start=2932
  _BUILDMETADATA_KERNEL._serialized_end=2957
  _BUILDMETADATA_SKU._serialized_start=2959
  _BUILDMETADATA_SKU._serialized_end=2982
  _BUILDMETADATA_CHIPSET._serialized_start=2984
  _BUILDMETADATA_CHIPSET._serialized_end=3012
  _BUILDMETADATA_CELLULAR._serialized_start=3014
  _BUILDMETADATA_CELLULAR._serialized_end=3041
  _BUILDMETADATA_LACROS._serialized_start=3043
  _BUILDMETADATA_LACROS._serialized_end=3096
  _DUTINFO._serialized_start=3099
  _DUTINFO._serialized_end=3330
  _DUTINFO_TAGSENTRY._serialized_start=967
  _DUTINFO_TAGSENTRY._serialized_end=1010
  _DRONEINFO._serialized_start=3332
  _DRONEINFO._serialized_end=3401
  _SWARMINGINFO._serialized_start=3403
  _SWARMINGINFO._serialized_end=3510
  _BUILDERID._serialized_start=3512
  _BUILDERID._serialized_end=3573
  _BUILDBUCKETINFO._serialized_start=3575
  _BUILDBUCKETINFO._serialized_end=3680
  _SKYLABINFO._serialized_start=3683
  _SKYLABINFO._serialized_end=3884
  _SATLABINFO._serialized_start=3887
  _SATLABINFO._serialized_end=4031
  _EXECUTIONINFO._serialized_start=4034
  _EXECUTIONINFO._serialized_end=4293
  _CUSTOMRESULT._serialized_start=4296
  _CUSTOMRESULT._serialized_end=4439
  _CUSTOMRESULT_CTS._serialized_start=4426
  _CUSTOMRESULT_CTS._serialized_end=4431
  _TIMINGINFO._serialized_start=4442
  _TIMINGINFO._serialized_end=4598
  _SCHEDULINGMETADATA._serialized_start=4601
  _SCHEDULINGMETADATA._serialized_end=4988
  _SCHEDULINGMETADATA_HARDWAREDEPENDENCIESENTRY._serialized_start=4874
  _SCHEDULINGMETADATA_HARDWAREDEPENDENCIESENTRY._serialized_end=4933
  _SCHEDULINGMETADATA_SCHEDULINGARGSENTRY._serialized_start=4935
  _SCHEDULINGMETADATA_SCHEDULINGARGSENTRY._serialized_end=4988
  _EXECUTIONMETADATA._serialized_start=4991
  _EXECUTIONMETADATA._serialized_end=5300
  _EXECUTIONMETADATA_SOFTWAREDEPENDENCIESENTRY._serialized_start=5192
  _EXECUTIONMETADATA_SOFTWAREDEPENDENCIESENTRY._serialized_end=5251
  _EXECUTIONMETADATA_TESTARGSENTRY._serialized_start=5253
  _EXECUTIONMETADATA_TESTARGSENTRY._serialized_end=5300
# @@protoc_insertion_point(module_scope)
