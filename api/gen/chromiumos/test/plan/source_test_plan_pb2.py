# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/plan/source_test_plan.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.test.api import test_suite_pb2 as chromiumos_dot_test_dot_api_dot_test__suite__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n+chromiumos/test/plan/source_test_plan.proto\x12\x14\x63hromiumos.test.plan\x1a$chromiumos/test/api/test_suite.proto\"\xe4\x03\n\x0eSourceTestPlan\x12\x14\n\x0cpath_regexps\x18\x02 \x03(\t\x12\x1c\n\x14path_regexp_excludes\x18\x03 \x03(\t\x12[\n\x18test_plan_starlark_files\x18\x0f \x03(\x0b\x32\x39.chromiumos.test.plan.SourceTestPlan.TestPlanStarlarkFile\x1a\xb4\x02\n\x14TestPlanStarlarkFile\x12\x0c\n\x04host\x18\x01 \x01(\t\x12\x0f\n\x07project\x18\x02 \x01(\t\x12\x0c\n\x04path\x18\x03 \x01(\t\x12i\n\x13template_parameters\x18\x04 \x01(\x0b\x32L.chromiumos.test.plan.SourceTestPlan.TestPlanStarlarkFile.TemplateParameters\x1a\x83\x01\n\x12TemplateParameters\x12H\n\x0ctag_criteria\x18\x01 \x01(\x0b\x32\x32.chromiumos.test.api.TestSuite.TestCaseTagCriteria\x12\x12\n\nsuite_name\x18\x02 \x01(\t\x12\x0f\n\x07program\x18\x03 \x01(\tJ\x04\x08\x01\x10\x02J\x04\x08\x04\x10\x0f\x42\x30Z.go.chromium.org/chromiumos/config/go/test/planb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.plan.source_test_plan_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z.go.chromium.org/chromiumos/config/go/test/plan'
  _SOURCETESTPLAN._serialized_start=108
  _SOURCETESTPLAN._serialized_end=592
  _SOURCETESTPLAN_TESTPLANSTARLARKFILE._serialized_start=272
  _SOURCETESTPLAN_TESTPLANSTARLARKFILE._serialized_end=580
  _SOURCETESTPLAN_TESTPLANSTARLARKFILE_TEMPLATEPARAMETERS._serialized_start=449
  _SOURCETESTPLAN_TESTPLANSTARLARKFILE_TEMPLATEPARAMETERS._serialized_end=580
# @@protoc_insertion_point(module_scope)
