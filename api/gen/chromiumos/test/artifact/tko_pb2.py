# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/artifact/tko.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\"chromiumos/test/artifact/tko.proto\x12\x18\x63hromiumos.test.artifact\"\xbb\x08\n\x03Job\x12\x0b\n\x03\x64ir\x18\x01 \x02(\t\x12\x31\n\x05tests\x18\x02 \x03(\x0b\x32\".chromiumos.test.artifact.Job.Test\x12\x0c\n\x04user\x18\x03 \x02(\t\x12\r\n\x05label\x18\x04 \x02(\t\x12\x0b\n\x03tag\x18\x05 \x02(\t\x12\x13\n\x0bqueued_time\x18\x06 \x02(\x03\x12\x14\n\x0cstarted_time\x18\x07 \x02(\x03\x12\x15\n\rfinished_time\x18\x08 \x02(\x03\x12\x0f\n\x07machine\x18\t \x02(\t\x12\x15\n\rmachine_owner\x18\n \x02(\t\x12\x15\n\rmachine_group\x18\x0b \x02(\t\x12\x12\n\naborted_by\x18\x0c \x02(\t\x12\x12\n\naborted_on\x18\r \x02(\x03\x12\x12\n\nafe_job_id\x18\x0e \x02(\t\x12\x39\n\x0bkeyval_dict\x18\x0f \x03(\x0b\x32$.chromiumos.test.artifact.Job.KeyVal\x12\x19\n\x11\x61\x66\x65_parent_job_id\x18\x10 \x01(\t\x12\x0f\n\x07job_idx\x18\x11 \x01(\x03\x12\x15\n\rbuild_version\x18\x12 \x01(\t\x12\r\n\x05suite\x18\x13 \x01(\t\x12\r\n\x05\x62oard\x18\x14 \x01(\t\x12\x12\n\ndlm_sku_id\x18\x15 \x01(\t\x12\x0c\n\x04hwid\x18\x16 \x01(\t\x12\x10\n\x08uploader\x18\x17 \x01(\t\x1a%\n\x06KeyVal\x12\x0c\n\x04name\x18\x01 \x02(\t\x12\r\n\x05value\x18\x02 \x02(\t\x1a+\n\x06Kernel\x12\x0c\n\x04\x62\x61se\x18\x01 \x02(\t\x12\x13\n\x0bkernel_hash\x18\x02 \x02(\t\x1a\x90\x01\n\tIteration\x12\r\n\x05index\x18\x01 \x02(\x03\x12\x39\n\x0b\x61ttr_keyval\x18\x02 \x03(\x0b\x32$.chromiumos.test.artifact.Job.KeyVal\x12\x39\n\x0bperf_keyval\x18\x03 \x03(\x0b\x32$.chromiumos.test.artifact.Job.KeyVal\x1a\xd5\x02\n\x04Test\x12\x0e\n\x06subdir\x18\x01 \x02(\t\x12\x10\n\x08testname\x18\x02 \x02(\t\x12\x0e\n\x06status\x18\x03 \x02(\t\x12\x0e\n\x06reason\x18\x04 \x02(\t\x12\x34\n\x06kernel\x18\x05 \x02(\x0b\x32$.chromiumos.test.artifact.Job.Kernel\x12\x0f\n\x07machine\x18\x06 \x02(\t\x12\x14\n\x0cstarted_time\x18\x07 \x02(\x03\x12\x15\n\rfinished_time\x18\x08 \x02(\x03\x12;\n\niterations\x18\t \x03(\x0b\x32\'.chromiumos.test.artifact.Job.Iteration\x12\x38\n\nattributes\x18\n \x03(\x0b\x32$.chromiumos.test.artifact.Job.KeyVal\x12\x0e\n\x06labels\x18\x0b \x03(\t\x12\x10\n\x08test_idx\x18\x0c \x01(\x03\x42\x34Z2go.chromium.org/chromiumos/config/go/test/artifact')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.artifact.tko_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z2go.chromium.org/chromiumos/config/go/test/artifact'
  _JOB._serialized_start=65
  _JOB._serialized_end=1148
  _JOB_KEYVAL._serialized_start=575
  _JOB_KEYVAL._serialized_end=612
  _JOB_KERNEL._serialized_start=614
  _JOB_KERNEL._serialized_end=657
  _JOB_ITERATION._serialized_start=660
  _JOB_ITERATION._serialized_end=804
  _JOB_TEST._serialized_start=807
  _JOB_TEST._serialized_end=1148
# @@protoc_insertion_point(module_scope)
