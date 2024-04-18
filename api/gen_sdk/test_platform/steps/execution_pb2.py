# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: test_platform/steps/execution.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen_sdk.test_platform.common import task_pb2 as test__platform_dot_common_dot_task__pb2
from chromite.api.gen_sdk.test_platform.config import config_pb2 as test__platform_dot_config_dot_config__pb2
from chromite.api.gen_sdk.test_platform import request_pb2 as test__platform_dot_request__pb2
from chromite.api.gen_sdk.test_platform.steps import enumeration_pb2 as test__platform_dot_steps_dot_enumeration__pb2
from chromite.api.gen_sdk.test_platform.steps.execute import build_pb2 as test__platform_dot_steps_dot_execute_dot_build__pb2
from chromite.api.gen_sdk.test_platform import taskstate_pb2 as test__platform_dot_taskstate__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n#test_platform/steps/execution.proto\x12\x13test_platform.steps\x1a\x1ftest_platform/common/task.proto\x1a!test_platform/config/config.proto\x1a\x1btest_platform/request.proto\x1a%test_platform/steps/enumeration.proto\x1a\'test_platform/steps/execute/build.proto\x1a\x1dtest_platform/taskstate.proto\"\xaa\x02\n\x0f\x45xecuteRequests\x12\x35\n\x08requests\x18\x01 \x03(\x0b\x32#.test_platform.steps.ExecuteRequest\x12Q\n\x0ftagged_requests\x18\x02 \x03(\x0b\x32\x38.test_platform.steps.ExecuteRequests.TaggedRequestsEntry\x12\x31\n\x05\x62uild\x18\x03 \x01(\x0b\x32\".test_platform.steps.execute.Build\x1aZ\n\x13TaggedRequestsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\x32\n\x05value\x18\x02 \x01(\x0b\x32#.test_platform.steps.ExecuteRequest:\x02\x38\x01\"\xff\x01\n\x10\x45xecuteResponses\x12\x37\n\tresponses\x18\x01 \x03(\x0b\x32$.test_platform.steps.ExecuteResponse\x12T\n\x10tagged_responses\x18\x02 \x03(\x0b\x32:.test_platform.steps.ExecuteResponses.TaggedResponsesEntry\x1a\\\n\x14TaggedResponsesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\x33\n\x05value\x18\x02 \x01(\x0b\x32$.test_platform.steps.ExecuteResponse:\x02\x38\x01\"\xb4\x01\n\x0e\x45xecuteRequest\x12\x35\n\x0erequest_params\x18\x01 \x01(\x0b\x32\x1d.test_platform.Request.Params\x12=\n\x0b\x65numeration\x18\x02 \x01(\x0b\x32(.test_platform.steps.EnumerationResponse\x12,\n\x06\x63onfig\x18\x03 \x01(\x0b\x32\x1c.test_platform.config.Config\"\xec\x08\n\x0f\x45xecuteResponse\x12I\n\x0ctask_results\x18\x01 \x03(\x0b\x32/.test_platform.steps.ExecuteResponse.TaskResultB\x02\x18\x01\x12U\n\x14\x63onsolidated_results\x18\x03 \x03(\x0b\x32\x37.test_platform.steps.ExecuteResponse.ConsolidatedResult\x12\'\n\x05state\x18\x02 \x01(\x0b\x32\x18.test_platform.TaskState\x1a\xb4\x06\n\nTaskResult\x12\x10\n\x08task_url\x18\x02 \x01(\t\x12\'\n\x05state\x18\x03 \x01(\x0b\x32\x18.test_platform.TaskState\x12\x0c\n\x04name\x18\x04 \x01(\t\x12\x0f\n\x07log_url\x18\x05 \x01(\t\x12\x0f\n\x07\x61ttempt\x18\x06 \x01(\x05\x12R\n\ntest_cases\x18\x07 \x03(\x0b\x32>.test_platform.steps.ExecuteResponse.TaskResult.TestCaseResult\x12T\n\x0cprejob_steps\x18\x08 \x03(\x0b\x32>.test_platform.steps.ExecuteResponse.TaskResult.TestCaseResult\x12\x33\n\x08log_data\x18\t \x01(\x0b\x32!.test_platform.common.TaskLogData\x12q\n\x18rejected_task_dimensions\x18\x0b \x03(\x0b\x32K.test_platform.steps.ExecuteResponse.TaskResult.RejectedTaskDimensionsEntryB\x02\x18\x01\x12\x62\n\x13rejected_dimensions\x18\x0c \x03(\x0b\x32\x45.test_platform.steps.ExecuteResponse.TaskResult.RejectedTaskDimension\x1aq\n\x0eTestCaseResult\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x31\n\x07verdict\x18\x02 \x01(\x0e\x32 .test_platform.TaskState.Verdict\x12\x1e\n\x16human_readable_summary\x18\x03 \x01(\t\x1a=\n\x1bRejectedTaskDimensionsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\x1a\x33\n\x15RejectedTaskDimension\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\tJ\x04\x08\n\x10\x0bR\x18synchronous_log_data_url\x1aW\n\x12\x43onsolidatedResult\x12\x41\n\x08\x61ttempts\x18\x01 \x03(\x0b\x32/.test_platform.steps.ExecuteResponse.TaskResultB?Z=go.chromium.org/chromiumos/infra/proto/go/test_platform/stepsb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'test_platform.steps.execution_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z=go.chromium.org/chromiumos/infra/proto/go/test_platform/steps'
  _EXECUTEREQUESTS_TAGGEDREQUESTSENTRY._options = None
  _EXECUTEREQUESTS_TAGGEDREQUESTSENTRY._serialized_options = b'8\001'
  _EXECUTERESPONSES_TAGGEDRESPONSESENTRY._options = None
  _EXECUTERESPONSES_TAGGEDRESPONSESENTRY._serialized_options = b'8\001'
  _EXECUTERESPONSE_TASKRESULT_REJECTEDTASKDIMENSIONSENTRY._options = None
  _EXECUTERESPONSE_TASKRESULT_REJECTEDTASKDIMENSIONSENTRY._serialized_options = b'8\001'
  _EXECUTERESPONSE_TASKRESULT.fields_by_name['rejected_task_dimensions']._options = None
  _EXECUTERESPONSE_TASKRESULT.fields_by_name['rejected_task_dimensions']._serialized_options = b'\030\001'
  _EXECUTERESPONSE.fields_by_name['task_results']._options = None
  _EXECUTERESPONSE.fields_by_name['task_results']._serialized_options = b'\030\001'
  _EXECUTEREQUESTS._serialized_start=269
  _EXECUTEREQUESTS._serialized_end=567
  _EXECUTEREQUESTS_TAGGEDREQUESTSENTRY._serialized_start=477
  _EXECUTEREQUESTS_TAGGEDREQUESTSENTRY._serialized_end=567
  _EXECUTERESPONSES._serialized_start=570
  _EXECUTERESPONSES._serialized_end=825
  _EXECUTERESPONSES_TAGGEDRESPONSESENTRY._serialized_start=733
  _EXECUTERESPONSES_TAGGEDRESPONSESENTRY._serialized_end=825
  _EXECUTEREQUEST._serialized_start=828
  _EXECUTEREQUEST._serialized_end=1008
  _EXECUTERESPONSE._serialized_start=1011
  _EXECUTERESPONSE._serialized_end=2143
  _EXECUTERESPONSE_TASKRESULT._serialized_start=1234
  _EXECUTERESPONSE_TASKRESULT._serialized_end=2054
  _EXECUTERESPONSE_TASKRESULT_TESTCASERESULT._serialized_start=1793
  _EXECUTERESPONSE_TASKRESULT_TESTCASERESULT._serialized_end=1906
  _EXECUTERESPONSE_TASKRESULT_REJECTEDTASKDIMENSIONSENTRY._serialized_start=1908
  _EXECUTERESPONSE_TASKRESULT_REJECTEDTASKDIMENSIONSENTRY._serialized_end=1969
  _EXECUTERESPONSE_TASKRESULT_REJECTEDTASKDIMENSION._serialized_start=1971
  _EXECUTERESPONSE_TASKRESULT_REJECTEDTASKDIMENSION._serialized_end=2022
  _EXECUTERESPONSE_CONSOLIDATEDRESULT._serialized_start=2056
  _EXECUTERESPONSE_CONSOLIDATEDRESULT._serialized_end=2143
# @@protoc_insertion_point(module_scope)
