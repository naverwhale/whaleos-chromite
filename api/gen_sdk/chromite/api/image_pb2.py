# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromite/api/image.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen_sdk.chromite.api import build_api_pb2 as chromite_dot_api_dot_build__api__pb2
from chromite.api.gen_sdk.chromite.api import sysroot_pb2 as chromite_dot_api_dot_sysroot__pb2
from chromite.api.gen_sdk.chromiumos import common_pb2 as chromiumos_dot_common__pb2
from chromite.api.gen_sdk.chromiumos import metrics_pb2 as chromiumos_dot_metrics__pb2
from chromite.api.gen_sdk.chromiumos import signing_pb2 as chromiumos_dot_signing__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x18\x63hromite/api/image.proto\x12\x0c\x63hromite.api\x1a\x1c\x63hromite/api/build_api.proto\x1a\x1a\x63hromite/api/sysroot.proto\x1a\x17\x63hromiumos/common.proto\x1a\x18\x63hromiumos/metrics.proto\x1a\x18\x63hromiumos/signing.proto\"o\n\x05Image\x12\x0c\n\x04path\x18\x01 \x01(\t\x12#\n\x04type\x18\x02 \x01(\x0e\x32\x15.chromiumos.ImageType\x12-\n\x0c\x62uild_target\x18\x03 \x01(\x0b\x32\x17.chromiumos.BuildTargetJ\x04\x08\x04\x10\x05\"\x9d\x02\n\x12\x43reateImageRequest\x12-\n\x0c\x62uild_target\x18\x01 \x01(\x0b\x32\x17.chromiumos.BuildTarget\x12*\n\x0bimage_types\x18\x02 \x03(\x0e\x32\x15.chromiumos.ImageType\x12#\n\x1b\x64isable_rootfs_verification\x18\x03 \x01(\x08\x12\x0f\n\x07version\x18\x04 \x01(\t\x12\x13\n\x0b\x64isk_layout\x18\x05 \x01(\t\x12\x14\n\x0c\x62uilder_path\x18\x06 \x01(\t\x12\"\n\x06\x63hroot\x18\x07 \x01(\x0b\x32\x12.chromiumos.Chroot\x12\x18\n\x10\x62\x61se_is_recovery\x18\x08 \x01(\x08\x12\r\n\x05\x62\x61zel\x18\t \x01(\x08\"\xa4\x01\n\x11\x43reateImageResult\x12\x0f\n\x07success\x18\x01 \x01(\x08\x12#\n\x06images\x18\x02 \x03(\x0b\x32\x13.chromite.api.Image\x12\x30\n\x0f\x66\x61iled_packages\x18\x03 \x03(\x0b\x32\x17.chromiumos.PackageInfo\x12\'\n\x06\x65vents\x18\x04 \x03(\x0b\x32\x17.chromiumos.MetricEvent\"\x84\x01\n\x14\x43reateNetbootRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\x12-\n\x0c\x62uild_target\x18\x02 \x01(\x0b\x32\x17.chromiumos.BuildTarget\x12\x19\n\x11\x66\x61\x63tory_shim_path\x18\x03 \x01(\t\"\x17\n\x15\x43reateNetbootResponse\"\xdd\x01\n\x10TestImageRequest\x12\"\n\x05image\x18\x01 \x01(\x0b\x32\x13.chromite.api.Image\x12-\n\x0c\x62uild_target\x18\x02 \x01(\x0b\x32\x17.chromiumos.BuildTarget\x12\x35\n\x06result\x18\x03 \x01(\x0b\x32%.chromite.api.TestImageRequest.Result\x12\"\n\x06\x63hroot\x18\x04 \x01(\x0b\x32\x12.chromiumos.Chroot\x1a\x1b\n\x06Result\x12\x11\n\tdirectory\x18\x01 \x01(\t\"\"\n\x0fTestImageResult\x12\x0f\n\x07success\x18\x01 \x01(\x08\"\xa5\x02\n\x10PushImageRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\x12\x0e\n\x06\x64ryrun\x18\x02 \x01(\x08\x12\x14\n\x0cgs_image_dir\x18\x03 \x01(\t\x12&\n\x07sysroot\x18\x04 \x01(\x0b\x32\x15.chromite.api.Sysroot\x12$\n\x07profile\x18\x05 \x01(\x0b\x32\x13.chromiumos.Profile\x12)\n\nsign_types\x18\x06 \x03(\x0e\x32\x15.chromiumos.ImageType\x12\x13\n\x0b\x64\x65st_bucket\x18\x07 \x01(\t\x12\x12\n\nis_staging\x18\x08 \x01(\x08\x12%\n\x08\x63hannels\x18\t \x03(\x0e\x32\x13.chromiumos.Channel\"\x87\x01\n\x11PushImageResponse\x12\x42\n\x0cinstructions\x18\x01 \x03(\x0b\x32,.chromite.api.PushImageResponse.Instructions\x1a.\n\x0cInstructions\x12\x1e\n\x16instructions_file_path\x18\x01 \x01(\t\"\xb0\x01\n\x10SignImageRequest\x12>\n\x0fsigning_configs\x18\x02 \x01(\x0b\x32%.chromiumos.BuildTargetSigningConfigs\x12\x13\n\x0b\x61rchive_dir\x18\x05 \x01(\t\x12+\n\x0bresult_path\x18\x03 \x01(\x0b\x32\x16.chromiumos.ResultPath\x12\x14\n\x0c\x64ocker_image\x18\x04 \x01(\tJ\x04\x08\x01\x10\x02\"q\n\x11SignImageResponse\x12@\n\x10signed_artifacts\x18\x01 \x01(\x0b\x32&.chromiumos.BuildTargetSignedArtifacts\x12\x1a\n\x12output_archive_dir\x18\x02 \x01(\t2\xfe\x03\n\x0cImageService\x12K\n\x06\x43reate\x12 .chromite.api.CreateImageRequest\x1a\x1f.chromite.api.CreateImageResult\x12X\n\rCreateNetboot\x12\".chromite.api.CreateNetbootRequest\x1a#.chromite.api.CreateNetbootResponse\x12\x45\n\x04Test\x12\x1e.chromite.api.TestImageRequest\x1a\x1d.chromite.api.TestImageResult\x12K\n\nSignerTest\x12\x1e.chromite.api.TestImageRequest\x1a\x1d.chromite.api.TestImageResult\x12L\n\tPushImage\x12\x1e.chromite.api.PushImageRequest\x1a\x1f.chromite.api.PushImageResponse\x12V\n\tSignImage\x12\x1e.chromite.api.SignImageRequest\x1a\x1f.chromite.api.SignImageResponse\"\x08\xc2\xed\x1a\x04\x10\x02 \x02\x1a\r\xc2\xed\x1a\t\n\x05image\x10\x01\x42\x38Z6go.chromium.org/chromiumos/infra/proto/go/chromite/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromite.api.image_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z6go.chromium.org/chromiumos/infra/proto/go/chromite/api'
  _IMAGESERVICE._options = None
  _IMAGESERVICE._serialized_options = b'\302\355\032\t\n\005image\020\001'
  _IMAGESERVICE.methods_by_name['SignImage']._options = None
  _IMAGESERVICE.methods_by_name['SignImage']._serialized_options = b'\302\355\032\004\020\002 \002'
  _IMAGE._serialized_start=177
  _IMAGE._serialized_end=288
  _CREATEIMAGEREQUEST._serialized_start=291
  _CREATEIMAGEREQUEST._serialized_end=576
  _CREATEIMAGERESULT._serialized_start=579
  _CREATEIMAGERESULT._serialized_end=743
  _CREATENETBOOTREQUEST._serialized_start=746
  _CREATENETBOOTREQUEST._serialized_end=878
  _CREATENETBOOTRESPONSE._serialized_start=880
  _CREATENETBOOTRESPONSE._serialized_end=903
  _TESTIMAGEREQUEST._serialized_start=906
  _TESTIMAGEREQUEST._serialized_end=1127
  _TESTIMAGEREQUEST_RESULT._serialized_start=1100
  _TESTIMAGEREQUEST_RESULT._serialized_end=1127
  _TESTIMAGERESULT._serialized_start=1129
  _TESTIMAGERESULT._serialized_end=1163
  _PUSHIMAGEREQUEST._serialized_start=1166
  _PUSHIMAGEREQUEST._serialized_end=1459
  _PUSHIMAGERESPONSE._serialized_start=1462
  _PUSHIMAGERESPONSE._serialized_end=1597
  _PUSHIMAGERESPONSE_INSTRUCTIONS._serialized_start=1551
  _PUSHIMAGERESPONSE_INSTRUCTIONS._serialized_end=1597
  _SIGNIMAGEREQUEST._serialized_start=1600
  _SIGNIMAGEREQUEST._serialized_end=1776
  _SIGNIMAGERESPONSE._serialized_start=1778
  _SIGNIMAGERESPONSE._serialized_end=1891
  _IMAGESERVICE._serialized_start=1894
  _IMAGESERVICE._serialized_end=2404
# @@protoc_insertion_point(module_scope)
