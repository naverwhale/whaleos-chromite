# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: test_platform/skylab_test_runner/steps/test_execution.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.test_platform.skylab_test_runner import config_pb2 as test__platform_dot_skylab__test__runner_dot_config__pb2
from chromite.api.gen.test_platform.skylab_test_runner import request_pb2 as test__platform_dot_skylab__test__runner_dot_request__pb2
from chromite.api.gen.test_platform.skylab_test_runner import cft_request_pb2 as test__platform_dot_skylab__test__runner_dot_cft__request__pb2
from chromite.api.gen.test_platform.skylab_test_runner import common_config_pb2 as test__platform_dot_skylab__test__runner_dot_common__config__pb2
from chromite.api.gen.test_platform.skylab_test_runner import cros_test_runner_request_pb2 as test__platform_dot_skylab__test__runner_dot_cros__test__runner__request__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n;test_platform/skylab_test_runner/steps/test_execution.proto\x12&test_platform.skylab_test_runner.steps\x1a-test_platform/skylab_test_runner/config.proto\x1a.test_platform/skylab_test_runner/request.proto\x1a\x32test_platform/skylab_test_runner/cft_request.proto\x1a\x34test_platform/skylab_test_runner/common_config.proto\x1a?test_platform/skylab_test_runner/cros_test_runner_request.proto\"\xf5\x02\n\x0fRunTestsRequest\x12:\n\x07request\x18\x01 \x01(\x0b\x32).test_platform.skylab_test_runner.Request\x12\x38\n\x06\x63onfig\x18\x02 \x01(\x0b\x32(.test_platform.skylab_test_runner.Config\x12J\n\x10\x63\x66t_test_request\x18\x03 \x01(\x0b\x32\x30.test_platform.skylab_test_runner.CFTTestRequest\x12\x45\n\rcommon_config\x18\x04 \x01(\x0b\x32..test_platform.skylab_test_runner.CommonConfig\x12Y\n\x18\x63ros_test_runner_request\x18\x05 \x01(\x0b\x32\x37.test_platform.skylab_test_runner.CrosTestRunnerRequest\"`\n\x10RunTestsResponse\x12\x1e\n\x16\x65rror_summary_markdown\x18\x01 \x01(\t\x12,\n\x11\x63ompressed_result\x18\x02 \x01(\tR\x11\x63ompressed_resultBRZPgo.chromium.org/chromiumos/infra/proto/go/test_platform/skylab_test_runner/stepsb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'test_platform.skylab_test_runner.steps.test_execution_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'ZPgo.chromium.org/chromiumos/infra/proto/go/test_platform/skylab_test_runner/steps'
  _RUNTESTSREQUEST._serialized_start=370
  _RUNTESTSREQUEST._serialized_end=743
  _RUNTESTSRESPONSE._serialized_start=745
  _RUNTESTSRESPONSE._serialized_end=841
# @@protoc_insertion_point(module_scope)
