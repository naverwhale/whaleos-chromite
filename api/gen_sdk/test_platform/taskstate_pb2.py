# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: test_platform/taskstate.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1dtest_platform/taskstate.proto\x12\rtest_platform\"\xc0\x04\n\tTaskState\x12\x36\n\nlife_cycle\x18\x01 \x01(\x0e\x32\".test_platform.TaskState.LifeCycle\x12\x31\n\x07verdict\x18\x02 \x01(\x0e\x32 .test_platform.TaskState.Verdict\"\x87\x01\n\rLifeCycleMask\x12\x1f\n\x1bLIFE_CYCLE_MASK_UNSPECIFIED\x10\x00\x12\x1b\n\x17LIFE_CYCLE_MASK_STARTED\x10\x10\x12\x1d\n\x19LIFE_CYCLE_MASK_COMPLETED\x10 \x12\x19\n\x15LIFE_CYCLE_MASK_FINAL\x10@\"\xbc\x01\n\tLifeCycle\x12\x1a\n\x16LIFE_CYCLE_UNSPECIFIED\x10\x00\x12\x16\n\x12LIFE_CYCLE_PENDING\x10\x01\x12\x16\n\x12LIFE_CYCLE_RUNNING\x10\x10\x12\x18\n\x14LIFE_CYCLE_COMPLETED\x10p\x12\x18\n\x14LIFE_CYCLE_CANCELLED\x10\x41\x12\x17\n\x13LIFE_CYCLE_REJECTED\x10\x42\x12\x16\n\x12LIFE_CYCLE_ABORTED\x10P\"\x7f\n\x07Verdict\x12\x17\n\x13VERDICT_UNSPECIFIED\x10\x00\x12\x12\n\x0eVERDICT_PASSED\x10\x01\x12\x12\n\x0eVERDICT_FAILED\x10\x02\x12\x16\n\x12VERDICT_NO_VERDICT\x10\x03\x12\x1b\n\x17VERDICT_PASSED_ON_RETRY\x10\x04\x42\x39Z7go.chromium.org/chromiumos/infra/proto/go/test_platformb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'test_platform.taskstate_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z7go.chromium.org/chromiumos/infra/proto/go/test_platform'
  _TASKSTATE._serialized_start=49
  _TASKSTATE._serialized_end=625
  _TASKSTATE_LIFECYCLEMASK._serialized_start=170
  _TASKSTATE_LIFECYCLEMASK._serialized_end=305
  _TASKSTATE_LIFECYCLE._serialized_start=308
  _TASKSTATE_LIFECYCLE._serialized_end=496
  _TASKSTATE_VERDICT._serialized_start=498
  _TASKSTATE_VERDICT._serialized_end=625
# @@protoc_insertion_point(module_scope)
