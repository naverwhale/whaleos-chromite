# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/api/dut_attribute.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromiumos.test.api import provision_state_pb2 as chromiumos_dot_test_dot_api_dot_provision__state__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\'chromiumos/test/api/dut_attribute.proto\x12\x13\x63hromiumos.test.api\x1a)chromiumos/test/api/provision_state.proto\"\xdb\x04\n\x0c\x44utAttribute\x12\x30\n\x02id\x18\x01 \x01(\x0b\x32$.chromiumos.test.api.DutAttribute.Id\x12\x0f\n\x07\x61liases\x18\x02 \x03(\t\x12P\n\x12\x66lat_config_source\x18\x03 \x01(\x0b\x32\x32.chromiumos.test.api.DutAttribute.FlatConfigSourceH\x00\x12\x43\n\x0bhwid_source\x18\x04 \x01(\x0b\x32,.chromiumos.test.api.DutAttribute.HwidSourceH\x00\x12\x41\n\ntle_source\x18\x07 \x01(\x0b\x32+.chromiumos.test.api.DutAttribute.TleSourceH\x00\x12\x16\n\x0e\x61llowed_values\x18\x05 \x03(\t\x12\x16\n\x0e\x65xclude_values\x18\x06 \x03(\t\x1a\x13\n\x02Id\x12\r\n\x05value\x18\x01 \x01(\t\x1a\x19\n\tFieldSpec\x12\x0c\n\x04path\x18\x01 \x01(\t\x1aO\n\x10\x46latConfigSource\x12;\n\x06\x66ields\x18\x01 \x03(\x0b\x32+.chromiumos.test.api.DutAttribute.FieldSpec\x1a\x61\n\nHwidSource\x12\x16\n\x0e\x63omponent_type\x18\x01 \x01(\t\x12;\n\x06\x66ields\x18\x02 \x03(\x0b\x32+.chromiumos.test.api.DutAttribute.FieldSpec\x1a\x0b\n\tTleSourceB\r\n\x0b\x64\x61ta_source\"M\n\x10\x44utAttributeList\x12\x39\n\x0e\x64ut_attributes\x18\x01 \x03(\x0b\x32!.chromiumos.test.api.DutAttribute\"Z\n\x0c\x44utCriterion\x12:\n\x0c\x61ttribute_id\x18\x01 \x01(\x0b\x32$.chromiumos.test.api.DutAttribute.Id\x12\x0e\n\x06values\x18\x02 \x03(\t\"\x80\x01\n\tDutTarget\x12\x33\n\x08\x63riteria\x18\x01 \x03(\x0b\x32!.chromiumos.test.api.DutCriterion\x12>\n\x10provision_config\x18\x02 \x01(\x0b\x32$.chromiumos.test.api.ProvisionConfigB/Z-go.chromium.org/chromiumos/config/go/test/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.api.dut_attribute_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z-go.chromium.org/chromiumos/config/go/test/api'
  _DUTATTRIBUTE._serialized_start=108
  _DUTATTRIBUTE._serialized_end=711
  _DUTATTRIBUTE_ID._serialized_start=457
  _DUTATTRIBUTE_ID._serialized_end=476
  _DUTATTRIBUTE_FIELDSPEC._serialized_start=478
  _DUTATTRIBUTE_FIELDSPEC._serialized_end=503
  _DUTATTRIBUTE_FLATCONFIGSOURCE._serialized_start=505
  _DUTATTRIBUTE_FLATCONFIGSOURCE._serialized_end=584
  _DUTATTRIBUTE_HWIDSOURCE._serialized_start=586
  _DUTATTRIBUTE_HWIDSOURCE._serialized_end=683
  _DUTATTRIBUTE_TLESOURCE._serialized_start=685
  _DUTATTRIBUTE_TLESOURCE._serialized_end=696
  _DUTATTRIBUTELIST._serialized_start=713
  _DUTATTRIBUTELIST._serialized_end=790
  _DUTCRITERION._serialized_start=792
  _DUTCRITERION._serialized_end=882
  _DUTTARGET._serialized_start=885
  _DUTTARGET._serialized_end=1013
# @@protoc_insertion_point(module_scope)
