# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: test_platform/skylab_test_runner/cros_test_runner_request.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import any_pb2 as google_dot_protobuf_dot_any__pb2
from chromite.api.gen_sdk.chromiumos.test.api import cros_tool_runner_container_service_templates_pb2 as chromiumos_dot_test_dot_api_dot_cros__tool__runner__container__service__templates__pb2
from chromite.api.gen_sdk.chromiumos.test.lab.api import ip_endpoint_pb2 as chromiumos_dot_test_dot_lab_dot_api_dot_ip__endpoint__pb2
from chromite.api.gen_sdk.chromiumos.test.api import provision_pb2 as chromiumos_dot_test_dot_api_dot_provision__pb2
from chromite.api.gen_sdk.chromiumos.test.api import cros_publish_service_pb2 as chromiumos_dot_test_dot_api_dot_cros__publish__service__pb2
from chromite.api.gen_sdk.chromiumos.test.api import cros_test_cli_pb2 as chromiumos_dot_test_dot_api_dot_cros__test__cli__pb2
from chromite.api.gen_sdk.chromiumos.test.api import test_suite_pb2 as chromiumos_dot_test_dot_api_dot_test__suite__pb2
from chromite.api.gen_sdk.chromiumos.build.api import container_metadata_pb2 as chromiumos_dot_build_dot_api_dot_container__metadata__pb2
from chromite.api.gen_sdk.test_platform.skylab_test_runner import cros_test_runner_service_pb2 as test__platform_dot_skylab__test__runner_dot_cros__test__runner__service__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n?test_platform/skylab_test_runner/cros_test_runner_request.proto\x12 test_platform.skylab_test_runner\x1a\x19google/protobuf/any.proto\x1a\x46\x63hromiumos/test/api/cros_tool_runner_container_service_templates.proto\x1a)chromiumos/test/lab/api/ip_endpoint.proto\x1a#chromiumos/test/api/provision.proto\x1a.chromiumos/test/api/cros_publish_service.proto\x1a\'chromiumos/test/api/cros_test_cli.proto\x1a$chromiumos/test/api/test_suite.proto\x1a-chromiumos/build/api/container_metadata.proto\x1a?test_platform/skylab_test_runner/cros_test_runner_service.proto\"\xaf\x06\n\x15\x43rosTestRunnerRequest\x12<\n\x05\x62uild\x18\x01 \x01(\x0b\x32+.test_platform.skylab_test_runner.BuildModeH\x00\x12T\n\x06server\x18\x02 \x01(\x0b\x32\x42.test_platform.skylab_test_runner.CrosTestRunnerServerStartRequestH\x00\x12\x46\n\x06params\x18\x03 \x01(\x0b\x32\x36.test_platform.skylab_test_runner.CrosTestRunnerParams\x12S\n\rordered_tasks\x18\x04 \x03(\x0b\x32<.test_platform.skylab_test_runner.CrosTestRunnerRequest.Task\x1a\xd3\x03\n\x04Task\x12V\n\x1aordered_container_requests\x18\x01 \x03(\x0b\x32\x32.test_platform.skylab_test_runner.ContainerRequest\x12G\n\tprovision\x18\x02 \x01(\x0b\x32\x32.test_platform.skylab_test_runner.ProvisionRequestH\x00\x12\x44\n\x08pre_test\x18\x03 \x01(\x0b\x32\x30.test_platform.skylab_test_runner.PreTestRequestH\x00\x12=\n\x04test\x18\x04 \x01(\x0b\x32-.test_platform.skylab_test_runner.TestRequestH\x00\x12\x46\n\tpost_test\x18\x05 \x01(\x0b\x32\x31.test_platform.skylab_test_runner.PostTestRequestH\x00\x12\x43\n\x07publish\x18\x06 \x01(\x0b\x32\x30.test_platform.skylab_test_runner.PublishRequestH\x00\x12\x10\n\x08required\x18\x07 \x01(\x08\x42\x06\n\x04taskB\x0f\n\rstart_request\"\x96\x02\n\x14\x43rosTestRunnerParams\x12\x33\n\x0btest_suites\x18\x01 \x03(\x0b\x32\x1e.chromiumos.test.api.TestSuite\x12\x43\n\x12\x63ontainer_metadata\x18\x02 \x01(\x0b\x32\'.chromiumos.build.api.ContainerMetadata\x12T\n\x07keyvals\x18\x03 \x03(\x0b\x32\x43.test_platform.skylab_test_runner.CrosTestRunnerParams.KeyvalsEntry\x1a.\n\x0cKeyvalsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\"@\n\tBuildMode\x12\x17\n\x0fparent_build_id\x18\x01 \x01(\x03\x12\x1a\n\x12parent_request_uid\x18\x02 \x01(\t\"\xa9\x02\n\x10ProvisionRequest\x12<\n\x0fservice_address\x18\x01 \x01(\x0b\x32#.chromiumos.test.lab.api.IpEndpoint\x12\x45\n\x0fstartup_request\x18\x02 \x01(\x0b\x32,.chromiumos.test.api.ProvisionStartupRequest\x12<\n\x0finstall_request\x18\x03 \x01(\x0b\x32#.chromiumos.test.api.InstallRequest\x12\x42\n\x0c\x64ynamic_deps\x18\x04 \x03(\x0b\x32,.test_platform.skylab_test_runner.DynamicDep\x12\x0e\n\x06target\x18\x05 \x01(\t\"\xc2\x01\n\x0ePreTestRequest\x12<\n\x0fservice_address\x18\x01 \x01(\x0b\x32#.chromiumos.test.lab.api.IpEndpoint\x12.\n\x10pre_test_request\x18\x02 \x01(\x0b\x32\x14.google.protobuf.Any\x12\x42\n\x0c\x64ynamic_deps\x18\x03 \x03(\x0b\x32,.test_platform.skylab_test_runner.DynamicDep\"\xcb\x01\n\x0bTestRequest\x12<\n\x0fservice_address\x18\x01 \x01(\x0b\x32#.chromiumos.test.lab.api.IpEndpoint\x12:\n\x0ctest_request\x18\x02 \x01(\x0b\x32$.chromiumos.test.api.CrosTestRequest\x12\x42\n\x0c\x64ynamic_deps\x18\x03 \x03(\x0b\x32,.test_platform.skylab_test_runner.DynamicDep\"\xc4\x01\n\x0fPostTestRequest\x12<\n\x0fservice_address\x18\x01 \x01(\x0b\x32#.chromiumos.test.lab.api.IpEndpoint\x12/\n\x11post_test_request\x18\x02 \x01(\x0b\x32\x14.google.protobuf.Any\x12\x42\n\x0c\x64ynamic_deps\x18\x03 \x03(\x0b\x32,.test_platform.skylab_test_runner.DynamicDep\"\xd0\x01\n\x0ePublishRequest\x12<\n\x0fservice_address\x18\x01 \x01(\x0b\x32#.chromiumos.test.lab.api.IpEndpoint\x12<\n\x0fpublish_request\x18\x02 \x01(\x0b\x32#.chromiumos.test.api.PublishRequest\x12\x42\n\x0c\x64ynamic_deps\x18\x03 \x03(\x0b\x32,.test_platform.skylab_test_runner.DynamicDep\"\xad\x03\n\x10\x43ontainerRequest\x12\x1a\n\x12\x64ynamic_identifier\x18\x01 \x01(\t\x12\x30\n\tcontainer\x18\x02 \x01(\x0b\x32\x1d.chromiumos.test.api.Template\x12\x42\n\x0c\x64ynamic_deps\x18\x03 \x03(\x0b\x32,.test_platform.skylab_test_runner.DynamicDep\x12L\n\x06inputs\x18\x04 \x03(\x0b\x32<.test_platform.skylab_test_runner.ContainerRequest.FileInput\x12\x0f\n\x07network\x18\x05 \x01(\t\x12\x1b\n\x13\x63ontainer_image_key\x18\x06 \x01(\t\x1a\x8a\x01\n\tFileInput\x12\x12\n\nidentifier\x18\x01 \x01(\t\x12%\n\x07\x63ontent\x18\x02 \x01(\x0b\x32\x14.google.protobuf.Any\x12\x42\n\x0c\x64ynamic_deps\x18\x03 \x03(\x0b\x32,.test_platform.skylab_test_runner.DynamicDep\"(\n\nDynamicDep\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\tBLZJgo.chromium.org/chromiumos/infra/proto/go/test_platform/skylab_test_runnerb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'test_platform.skylab_test_runner.cros_test_runner_request_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'ZJgo.chromium.org/chromiumos/infra/proto/go/test_platform/skylab_test_runner'
  _CROSTESTRUNNERPARAMS_KEYVALSENTRY._options = None
  _CROSTESTRUNNERPARAMS_KEYVALSENTRY._serialized_options = b'8\001'
  _CROSTESTRUNNERREQUEST._serialized_start=520
  _CROSTESTRUNNERREQUEST._serialized_end=1335
  _CROSTESTRUNNERREQUEST_TASK._serialized_start=851
  _CROSTESTRUNNERREQUEST_TASK._serialized_end=1318
  _CROSTESTRUNNERPARAMS._serialized_start=1338
  _CROSTESTRUNNERPARAMS._serialized_end=1616
  _CROSTESTRUNNERPARAMS_KEYVALSENTRY._serialized_start=1570
  _CROSTESTRUNNERPARAMS_KEYVALSENTRY._serialized_end=1616
  _BUILDMODE._serialized_start=1618
  _BUILDMODE._serialized_end=1682
  _PROVISIONREQUEST._serialized_start=1685
  _PROVISIONREQUEST._serialized_end=1982
  _PRETESTREQUEST._serialized_start=1985
  _PRETESTREQUEST._serialized_end=2179
  _TESTREQUEST._serialized_start=2182
  _TESTREQUEST._serialized_end=2385
  _POSTTESTREQUEST._serialized_start=2388
  _POSTTESTREQUEST._serialized_end=2584
  _PUBLISHREQUEST._serialized_start=2587
  _PUBLISHREQUEST._serialized_end=2795
  _CONTAINERREQUEST._serialized_start=2798
  _CONTAINERREQUEST._serialized_end=3227
  _CONTAINERREQUEST_FILEINPUT._serialized_start=3089
  _CONTAINERREQUEST_FILEINPUT._serialized_end=3227
  _DYNAMICDEP._serialized_start=3229
  _DYNAMICDEP._serialized_end=3269
# @@protoc_insertion_point(module_scope)
