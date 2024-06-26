# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromite/api/sdk.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.chromite.api import build_api_pb2 as chromite_dot_api_dot_build__api__pb2
from chromite.api.gen.chromite.api import sysroot_pb2 as chromite_dot_api_dot_sysroot__pb2
from chromite.api.gen.chromiumos import common_pb2 as chromiumos_dot_common__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x16\x63hromite/api/sdk.proto\x12\x0c\x63hromite.api\x1a\x1c\x63hromite/api/build_api.proto\x1a\x1a\x63hromite/api/sysroot.proto\x1a\x17\x63hromiumos/common.proto\" \n\rChrootVersion\x12\x0f\n\x07version\x18\x01 \x01(\r\"\xf5\x01\n\rCreateRequest\x12\x30\n\x05\x66lags\x18\x01 \x01(\x0b\x32!.chromite.api.CreateRequest.Flags\x12\"\n\x06\x63hroot\x18\x02 \x01(\x0b\x32\x12.chromiumos.Chroot\x12\x13\n\x0bsdk_version\x18\x03 \x01(\t\x12\x1b\n\x13skip_chroot_upgrade\x18\x04 \x01(\x08\x12\x16\n\x0e\x63\x63\x61\x63he_disable\x18\x05 \x01(\x08\x1a\x44\n\x05\x46lags\x12\x12\n\nno_replace\x18\x01 \x01(\x08\x12\x11\n\tbootstrap\x18\x02 \x01(\x08\x12\x14\n\x0cno_use_image\x18\x03 \x01(\x08\">\n\x0e\x43reateResponse\x12,\n\x07version\x18\x01 \x01(\x0b\x32\x1b.chromite.api.ChrootVersion\"3\n\rDeleteRequest\x12\"\n\x06\x63hroot\x18\x02 \x01(\x0b\x32\x12.chromiumos.Chroot\"\x10\n\x0e\x44\x65leteResponse\"4\n\x0eUnmountRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\"\x11\n\x0fUnmountResponse\"\x80\x02\n\rUpdateRequest\x12\x30\n\x05\x66lags\x18\x01 \x01(\x0b\x32!.chromite.api.UpdateRequest.Flags\x12\x32\n\x11toolchain_targets\x18\x02 \x03(\x0b\x32\x17.chromiumos.BuildTarget\x12\"\n\x06\x63hroot\x18\x03 \x01(\x0b\x32\x12.chromiumos.Chroot\x12+\n\x0bresult_path\x18\x04 \x01(\x0b\x32\x16.chromiumos.ResultPath\x1a\x38\n\x05\x46lags\x12\x14\n\x0c\x62uild_source\x18\x01 \x01(\x08\x12\x19\n\x11toolchain_changed\x18\x02 \x01(\x08\"|\n\x0eUpdateResponse\x12,\n\x07version\x18\x01 \x01(\x0b\x32\x1b.chromite.api.ChrootVersion\x12<\n\x13\x66\x61iled_package_data\x18\x02 \x03(\x0b\x32\x1f.chromite.api.FailedPackageData\"d\n\x0cUprevRequest\x12\x19\n\x11\x62inhost_gs_bucket\x18\x03 \x01(\t\x12\x0f\n\x07version\x18\x04 \x01(\t\x12\"\n\x1atoolchain_tarball_template\x18\x05 \x01(\tJ\x04\x08\x01\x10\x03\"J\n\rUprevResponse\x12(\n\x0emodified_files\x18\x01 \x03(\x0b\x32\x10.chromiumos.Path\x12\x0f\n\x07version\x18\x02 \x01(\t\"\xb4\x01\n\x0c\x43leanRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\x12\x0c\n\x04safe\x18\x02 \x01(\x08\x12\x0e\n\x06images\x18\x03 \x01(\x08\x12\x10\n\x08sysroots\x18\x04 \x01(\x08\x12\x0b\n\x03tmp\x18\x05 \x01(\x08\x12\r\n\x05\x63\x61\x63he\x18\x06 \x01(\x08\x12\x0c\n\x04logs\x18\x07 \x01(\x08\x12\x10\n\x08workdirs\x18\x08 \x01(\x08\x12\x14\n\x0cincrementals\x18\t \x01(\x08\"\x0f\n\rCleanResponse\"\x1e\n\rSnapshotToken\x12\r\n\x05value\x18\x01 \x01(\t\";\n\x15\x43reateSnapshotRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\"M\n\x16\x43reateSnapshotResponse\x12\x33\n\x0esnapshot_token\x18\x01 \x01(\x0b\x32\x1b.chromite.api.SnapshotToken\"q\n\x16RestoreSnapshotRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\x12\x33\n\x0esnapshot_token\x18\x02 \x01(\x0b\x32\x1b.chromite.api.SnapshotToken\"\x19\n\x17RestoreSnapshotResponse\"4\n\x12UnmountPathRequest\x12\x1e\n\x04path\x18\x01 \x01(\x0b\x32\x10.chromiumos.Path\"\x15\n\x13UnmountPathResponse\"j\n\x15\x42uildPrebuiltsRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\x12-\n\x0c\x62uild_target\x18\x02 \x01(\x0b\x32\x17.chromiumos.BuildTarget\"x\n\x16\x42uildPrebuiltsResponse\x12-\n\x13host_prebuilts_path\x18\x01 \x01(\x0b\x32\x10.chromiumos.Path\x12/\n\x15target_prebuilts_path\x18\x02 \x01(\x0b\x32\x10.chromiumos.Path\"Q\n\x16\x42uildSdkTarballRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\x12\x13\n\x0bsdk_version\x18\x02 \x01(\t\"E\n\x17\x42uildSdkTarballResponse\x12*\n\x10sdk_tarball_path\x18\x01 \x01(\x0b\x32\x10.chromiumos.Path\"\x8a\x01\n\x1c\x43reateManifestFromSdkRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\x12\"\n\x08sdk_path\x18\x02 \x01(\x0b\x32\x10.chromiumos.Path\x12\"\n\x08\x64\x65st_dir\x18\x03 \x01(\x0b\x32\x10.chromiumos.Path\"H\n\x1d\x43reateManifestFromSdkResponse\x12\'\n\rmanifest_path\x18\x01 \x01(\x0b\x32\x10.chromiumos.Path\"z\n\x17\x43reateBinhostCLsRequest\x12\x17\n\x0fprepend_version\x18\x01 \x01(\t\x12\x0f\n\x07version\x18\x02 \x01(\t\x12\x17\n\x0fupload_location\x18\x03 \x01(\t\x12\x1c\n\x14sdk_tarball_template\x18\x04 \x01(\t\"\'\n\x18\x43reateBinhostCLsResponse\x12\x0b\n\x03\x63ls\x18\x01 \x03(\t\"\x86\x01\n\x1dUploadPrebuiltPackagesRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\x12\x17\n\x0fprepend_version\x18\x02 \x01(\t\x12\x0f\n\x07version\x18\x03 \x01(\t\x12\x17\n\x0fupload_location\x18\x04 \x01(\t\" \n\x1eUploadPrebuiltPackagesResponse\"\x93\x01\n\x18\x42uildSdkToolchainRequest\x12\"\n\x06\x63hroot\x18\x01 \x01(\x0b\x32\x12.chromiumos.Chroot\x12&\n\tuse_flags\x18\x02 \x03(\x0b\x32\x13.chromiumos.UseFlag\x12+\n\x0bresult_path\x18\x03 \x01(\x0b\x32\x16.chromiumos.ResultPath\"F\n\x19\x42uildSdkToolchainResponse\x12)\n\x0fgenerated_files\x18\x01 \x03(\x0b\x32\x10.chromiumos.Path2\xc2\n\n\nSdkService\x12\x43\n\x06\x43reate\x12\x1b.chromite.api.CreateRequest\x1a\x1c.chromite.api.CreateResponse\x12\x43\n\x06\x44\x65lete\x12\x1b.chromite.api.DeleteRequest\x1a\x1c.chromite.api.DeleteResponse\x12@\n\x05\x43lean\x12\x1a.chromite.api.CleanRequest\x1a\x1b.chromite.api.CleanResponse\x12\x46\n\x07Unmount\x12\x1c.chromite.api.UnmountRequest\x1a\x1d.chromite.api.UnmountResponse\x12K\n\x06Update\x12\x1b.chromite.api.UpdateRequest\x1a\x1c.chromite.api.UpdateResponse\"\x06\xc2\xed\x1a\x02\x10\x01\x12@\n\x05Uprev\x12\x1a.chromite.api.UprevRequest\x1a\x1b.chromite.api.UprevResponse\x12[\n\x0e\x43reateSnapshot\x12#.chromite.api.CreateSnapshotRequest\x1a$.chromite.api.CreateSnapshotResponse\x12^\n\x0fRestoreSnapshot\x12$.chromite.api.RestoreSnapshotRequest\x1a%.chromite.api.RestoreSnapshotResponse\x12R\n\x0bUnmountPath\x12 .chromite.api.UnmountPathRequest\x1a!.chromite.api.UnmountPathResponse\x12[\n\x0e\x42uildPrebuilts\x12#.chromite.api.BuildPrebuiltsRequest\x1a$.chromite.api.BuildPrebuiltsResponse\x12^\n\x0f\x42uildSdkTarball\x12$.chromite.api.BuildSdkTarballRequest\x1a%.chromite.api.BuildSdkTarballResponse\x12p\n\x15\x43reateManifestFromSdk\x12*.chromite.api.CreateManifestFromSdkRequest\x1a+.chromite.api.CreateManifestFromSdkResponse\x12\x61\n\x10\x43reateBinhostCLs\x12%.chromite.api.CreateBinhostCLsRequest\x1a&.chromite.api.CreateBinhostCLsResponse\x12s\n\x16UploadPrebuiltPackages\x12+.chromite.api.UploadPrebuiltPackagesRequest\x1a,.chromite.api.UploadPrebuiltPackagesResponse\x12l\n\x11\x42uildSdkToolchain\x12&.chromite.api.BuildSdkToolchainRequest\x1a\'.chromite.api.BuildSdkToolchainResponse\"\x06\xc2\xed\x1a\x02\x10\x01\x1a\x0b\xc2\xed\x1a\x07\n\x03sdk\x10\x02\x42\x38Z6go.chromium.org/chromiumos/infra/proto/go/chromite/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromite.api.sdk_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z6go.chromium.org/chromiumos/infra/proto/go/chromite/api'
  _SDKSERVICE._options = None
  _SDKSERVICE._serialized_options = b'\302\355\032\007\n\003sdk\020\002'
  _SDKSERVICE.methods_by_name['Update']._options = None
  _SDKSERVICE.methods_by_name['Update']._serialized_options = b'\302\355\032\002\020\001'
  _SDKSERVICE.methods_by_name['BuildSdkToolchain']._options = None
  _SDKSERVICE.methods_by_name['BuildSdkToolchain']._serialized_options = b'\302\355\032\002\020\001'
  _CHROOTVERSION._serialized_start=123
  _CHROOTVERSION._serialized_end=155
  _CREATEREQUEST._serialized_start=158
  _CREATEREQUEST._serialized_end=403
  _CREATEREQUEST_FLAGS._serialized_start=335
  _CREATEREQUEST_FLAGS._serialized_end=403
  _CREATERESPONSE._serialized_start=405
  _CREATERESPONSE._serialized_end=467
  _DELETEREQUEST._serialized_start=469
  _DELETEREQUEST._serialized_end=520
  _DELETERESPONSE._serialized_start=522
  _DELETERESPONSE._serialized_end=538
  _UNMOUNTREQUEST._serialized_start=540
  _UNMOUNTREQUEST._serialized_end=592
  _UNMOUNTRESPONSE._serialized_start=594
  _UNMOUNTRESPONSE._serialized_end=611
  _UPDATEREQUEST._serialized_start=614
  _UPDATEREQUEST._serialized_end=870
  _UPDATEREQUEST_FLAGS._serialized_start=814
  _UPDATEREQUEST_FLAGS._serialized_end=870
  _UPDATERESPONSE._serialized_start=872
  _UPDATERESPONSE._serialized_end=996
  _UPREVREQUEST._serialized_start=998
  _UPREVREQUEST._serialized_end=1098
  _UPREVRESPONSE._serialized_start=1100
  _UPREVRESPONSE._serialized_end=1174
  _CLEANREQUEST._serialized_start=1177
  _CLEANREQUEST._serialized_end=1357
  _CLEANRESPONSE._serialized_start=1359
  _CLEANRESPONSE._serialized_end=1374
  _SNAPSHOTTOKEN._serialized_start=1376
  _SNAPSHOTTOKEN._serialized_end=1406
  _CREATESNAPSHOTREQUEST._serialized_start=1408
  _CREATESNAPSHOTREQUEST._serialized_end=1467
  _CREATESNAPSHOTRESPONSE._serialized_start=1469
  _CREATESNAPSHOTRESPONSE._serialized_end=1546
  _RESTORESNAPSHOTREQUEST._serialized_start=1548
  _RESTORESNAPSHOTREQUEST._serialized_end=1661
  _RESTORESNAPSHOTRESPONSE._serialized_start=1663
  _RESTORESNAPSHOTRESPONSE._serialized_end=1688
  _UNMOUNTPATHREQUEST._serialized_start=1690
  _UNMOUNTPATHREQUEST._serialized_end=1742
  _UNMOUNTPATHRESPONSE._serialized_start=1744
  _UNMOUNTPATHRESPONSE._serialized_end=1765
  _BUILDPREBUILTSREQUEST._serialized_start=1767
  _BUILDPREBUILTSREQUEST._serialized_end=1873
  _BUILDPREBUILTSRESPONSE._serialized_start=1875
  _BUILDPREBUILTSRESPONSE._serialized_end=1995
  _BUILDSDKTARBALLREQUEST._serialized_start=1997
  _BUILDSDKTARBALLREQUEST._serialized_end=2078
  _BUILDSDKTARBALLRESPONSE._serialized_start=2080
  _BUILDSDKTARBALLRESPONSE._serialized_end=2149
  _CREATEMANIFESTFROMSDKREQUEST._serialized_start=2152
  _CREATEMANIFESTFROMSDKREQUEST._serialized_end=2290
  _CREATEMANIFESTFROMSDKRESPONSE._serialized_start=2292
  _CREATEMANIFESTFROMSDKRESPONSE._serialized_end=2364
  _CREATEBINHOSTCLSREQUEST._serialized_start=2366
  _CREATEBINHOSTCLSREQUEST._serialized_end=2488
  _CREATEBINHOSTCLSRESPONSE._serialized_start=2490
  _CREATEBINHOSTCLSRESPONSE._serialized_end=2529
  _UPLOADPREBUILTPACKAGESREQUEST._serialized_start=2532
  _UPLOADPREBUILTPACKAGESREQUEST._serialized_end=2666
  _UPLOADPREBUILTPACKAGESRESPONSE._serialized_start=2668
  _UPLOADPREBUILTPACKAGESRESPONSE._serialized_end=2700
  _BUILDSDKTOOLCHAINREQUEST._serialized_start=2703
  _BUILDSDKTOOLCHAINREQUEST._serialized_end=2850
  _BUILDSDKTOOLCHAINRESPONSE._serialized_start=2852
  _BUILDSDKTOOLCHAINRESPONSE._serialized_end=2922
  _SDKSERVICE._serialized_start=2925
  _SDKSERVICE._serialized_end=4271
# @@protoc_insertion_point(module_scope)
