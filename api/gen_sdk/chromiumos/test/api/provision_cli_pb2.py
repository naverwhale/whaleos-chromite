# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/api/provision_cli.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen_sdk.chromiumos.test.lab.api import dut_pb2 as chromiumos_dot_test_dot_lab_dot_api_dot_dut__pb2
from chromite.api.gen_sdk.chromiumos.test.api import provision_state_pb2 as chromiumos_dot_test_dot_api_dot_provision__state__pb2
from chromite.api.gen_sdk.chromiumos.test.api import provision_service_pb2 as chromiumos_dot_test_dot_api_dot_provision__service__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\'chromiumos/test/api/provision_cli.proto\x12\x13\x63hromiumos.test.api\x1a!chromiumos/test/lab/api/dut.proto\x1a)chromiumos/test/api/provision_state.proto\x1a+chromiumos/test/api/provision_service.proto\"F\n\x11ProvisionCliInput\x12\x31\n\ndut_inputs\x18\x01 \x03(\x0b\x32\x1d.chromiumos.test.api.DutInput\"\xb6\x02\n\x08\x44utInput\x12+\n\x02id\x18\x01 \x01(\x0b\x32\x1f.chromiumos.test.lab.api.Dut.Id\x12<\n\x0fprovision_state\x18\x03 \x01(\x0b\x32#.chromiumos.test.api.ProvisionState\x12>\n\x0b\x64ut_service\x18\x04 \x01(\x0b\x32).chromiumos.test.api.DutInput.DockerImage\x12\x44\n\x11provision_service\x18\x05 \x01(\x0b\x32).chromiumos.test.api.DutInput.DockerImage\x1a\x33\n\x0b\x44ockerImage\x12\x17\n\x0frepository_path\x18\x01 \x01(\t\x12\x0b\n\x03tag\x18\x02 \x01(\tJ\x04\x08\x02\x10\x03\"I\n\x12ProvisionCliOutput\x12\x33\n\x0b\x64ut_outputs\x18\x01 \x03(\x0b\x32\x1e.chromiumos.test.api.DutOutput\"\xb3\x01\n\tDutOutput\x12+\n\x02id\x18\x01 \x01(\x0b\x32\x1f.chromiumos.test.lab.api.Dut.Id\x12\x36\n\x07success\x18\x02 \x01(\x0b\x32#.chromiumos.test.api.InstallSuccessH\x00\x12\x36\n\x07\x66\x61ilure\x18\x03 \x01(\x0b\x32#.chromiumos.test.api.InstallFailureH\x00\x42\t\n\x07outcomeB/Z-go.chromium.org/chromiumos/config/go/test/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.api.provision_cli_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z-go.chromium.org/chromiumos/config/go/test/api'
  _PROVISIONCLIINPUT._serialized_start=187
  _PROVISIONCLIINPUT._serialized_end=257
  _DUTINPUT._serialized_start=260
  _DUTINPUT._serialized_end=570
  _DUTINPUT_DOCKERIMAGE._serialized_start=513
  _DUTINPUT_DOCKERIMAGE._serialized_end=564
  _PROVISIONCLIOUTPUT._serialized_start=572
  _PROVISIONCLIOUTPUT._serialized_end=645
  _DUTOUTPUT._serialized_start=648
  _DUTOUTPUT._serialized_end=827
# @@protoc_insertion_point(module_scope)
