# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromite/api/build_api.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import descriptor_pb2 as google_dot_protobuf_dot_descriptor__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1c\x63hromite/api/build_api.proto\x12\x0c\x63hromite.api\x1a google/protobuf/descriptor.proto\"\xe5\x01\n\x16\x42uildApiServiceOptions\x12\x0e\n\x06module\x18\x01 \x02(\t\x12<\n\x15service_chroot_assert\x18\x02 \x01(\x0e\x32\x1d.chromite.api.ChrootAssertion\x12\x38\n\x12service_visibility\x18\x03 \x01(\x0e\x32\x1c.chromite.api.ListVisibility\x12\x43\n\x1aservice_branched_execution\x18\x04 \x01(\x0e\x32\x1f.chromite.api.BranchedExecution\"\xee\x01\n\x15\x42uildApiMethodOptions\x12\x1b\n\x13implementation_name\x18\x01 \x01(\t\x12;\n\x14method_chroot_assert\x18\x02 \x01(\x0e\x32\x1d.chromite.api.ChrootAssertion\x12\x37\n\x11method_visibility\x18\x03 \x01(\x0e\x32\x1c.chromite.api.ListVisibility\x12\x42\n\x19method_branched_execution\x18\x04 \x01(\x0e\x32\x1f.chromite.api.BranchedExecution*<\n\x0f\x43hrootAssertion\x12\x10\n\x0cNO_ASSERTION\x10\x00\x12\n\n\x06INSIDE\x10\x01\x12\x0b\n\x07OUTSIDE\x10\x02*E\n\x0eListVisibility\x12\x14\n\x10LV_NOT_SPECIFIED\x10\x00\x12\x0e\n\nLV_VISIBLE\x10\x01\x12\r\n\tLV_HIDDEN\x10\x02*U\n\x11\x42ranchedExecution\x12\x19\n\x15\x45XECUTE_NOT_SPECIFIED\x10\x00\x12\x14\n\x10\x45XECUTE_BRANCHED\x10\x01\x12\x0f\n\x0b\x45XECUTE_TOT\x10\x02:`\n\x0fservice_options\x12\x1f.google.protobuf.ServiceOptions\x18\xd8\xad\x03 \x01(\x0b\x32$.chromite.api.BuildApiServiceOptions:]\n\x0emethod_options\x12\x1e.google.protobuf.MethodOptions\x18\xd8\xad\x03 \x01(\x0b\x32#.chromite.api.BuildApiMethodOptionsB8Z6go.chromium.org/chromiumos/infra/proto/go/chromite/api')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromite.api.build_api_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:
  google_dot_protobuf_dot_descriptor__pb2.ServiceOptions.RegisterExtension(service_options)
  google_dot_protobuf_dot_descriptor__pb2.MethodOptions.RegisterExtension(method_options)

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z6go.chromium.org/chromiumos/infra/proto/go/chromite/api'
  _CHROOTASSERTION._serialized_start=553
  _CHROOTASSERTION._serialized_end=613
  _LISTVISIBILITY._serialized_start=615
  _LISTVISIBILITY._serialized_end=684
  _BRANCHEDEXECUTION._serialized_start=686
  _BRANCHEDEXECUTION._serialized_end=771
  _BUILDAPISERVICEOPTIONS._serialized_start=81
  _BUILDAPISERVICEOPTIONS._serialized_end=310
  _BUILDAPIMETHODOPTIONS._serialized_start=313
  _BUILDAPIMETHODOPTIONS._serialized_end=551
# @@protoc_insertion_point(module_scope)
