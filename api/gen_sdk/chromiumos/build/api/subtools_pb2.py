# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/build/api/subtools.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n#chromiumos/build/api/subtools.proto\x12\x14\x63hromiumos.build.api\"\xb3\x03\n\x0eSubtoolPackage\x12\x0c\n\x04name\x18\x01 \x01(\t\x12=\n\x04type\x18\x02 \x01(\x0e\x32/.chromiumos.build.api.SubtoolPackage.ExportType\x12\x11\n\tmax_files\x18\x03 \x01(\x05\x12\x18\n\x0b\x63ipd_prefix\x18\x04 \x01(\tH\x00\x88\x01\x01\x12?\n\x05paths\x18\x05 \x03(\x0b\x32\x30.chromiumos.build.api.SubtoolPackage.PathMapping\x1a\x9e\x01\n\x0bPathMapping\x12\r\n\x05input\x18\x01 \x01(\t\x12\x11\n\x04\x64\x65st\x18\x02 \x01(\tH\x00\x88\x01\x01\x12\x1f\n\x12strip_prefix_regex\x18\x03 \x01(\tH\x01\x88\x01\x01\x12\x1a\n\rebuild_filter\x18\x04 \x01(\tH\x02\x88\x01\x01\x42\x07\n\x05_destB\x15\n\x13_strip_prefix_regexB\x10\n\x0e_ebuild_filter\"5\n\nExportType\x12\x16\n\x12\x45XPORT_UNSPECIFIED\x10\x00\x12\x0f\n\x0b\x45XPORT_CIPD\x10\x01\x42\x0e\n\x0c_cipd_prefixB0Z.go.chromium.org/chromiumos/config/go/build/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.build.api.subtools_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z.go.chromium.org/chromiumos/config/go/build/api'
  _SUBTOOLPACKAGE._serialized_start=62
  _SUBTOOLPACKAGE._serialized_end=497
  _SUBTOOLPACKAGE_PATHMAPPING._serialized_start=268
  _SUBTOOLPACKAGE_PATHMAPPING._serialized_end=426
  _SUBTOOLPACKAGE_EXPORTTYPE._serialized_start=428
  _SUBTOOLPACKAGE_EXPORTTYPE._serialized_end=481
# @@protoc_insertion_point(module_scope)