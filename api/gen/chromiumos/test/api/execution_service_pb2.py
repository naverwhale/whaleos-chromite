# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/api/execution_service.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.longrunning import operations_pb2 as chromiumos_dot_longrunning_dot_operations__pb2
from chromite.api.gen.chromiumos.test.api import cros_test_cli_pb2 as chromiumos_dot_test_dot_api_dot_cros__test__cli__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n+chromiumos/test/api/execution_service.proto\x12\x13\x63hromiumos.test.api\x1a\'chromiumos/longrunning/operations.proto\x1a\'chromiumos/test/api/cros_test_cli.proto\"\x15\n\x13RunCrosTestMetadata2\x93\x01\n\x10\x45xecutionService\x12\x7f\n\x08RunTests\x12$.chromiumos.test.api.CrosTestRequest\x1a!.chromiumos.longrunning.Operation\"*\xd2\x41\'\n\x10\x43rosTestResponse\x12\x13RunCrosTestMetadataB/Z-go.chromium.org/chromiumos/config/go/test/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.api.execution_service_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z-go.chromium.org/chromiumos/config/go/test/api'
  _EXECUTIONSERVICE.methods_by_name['RunTests']._options = None
  _EXECUTIONSERVICE.methods_by_name['RunTests']._serialized_options = b'\322A\'\n\020CrosTestResponse\022\023RunCrosTestMetadata'
  _RUNCROSTESTMETADATA._serialized_start=150
  _RUNCROSTESTMETADATA._serialized_end=171
  _EXECUTIONSERVICE._serialized_start=174
  _EXECUTIONSERVICE._serialized_end=321
# @@protoc_insertion_point(module_scope)
