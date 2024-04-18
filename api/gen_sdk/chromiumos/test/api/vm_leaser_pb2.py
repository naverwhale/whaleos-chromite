# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/api/vm_leaser.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import duration_pb2 as google_dot_protobuf_dot_duration__pb2
from google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n#chromiumos/test/api/vm_leaser.proto\x12\x13\x63hromiumos.test.api\x1a\x1egoogle/protobuf/duration.proto\x1a\x1fgoogle/protobuf/timestamp.proto\"\xea\x02\n\x0eLeaseVMRequest\x12\x17\n\x0fidempotency_key\x18\x01 \x01(\t\x12\x14\n\x0con_behalf_of\x18\x02 \x01(\t\x12\x10\n\x08quota_id\x18\x03 \x01(\t\x12\x31\n\x0elease_duration\x18\x04 \x01(\x0b\x32\x19.google.protobuf.Duration\x12\x36\n\thost_reqs\x18\x05 \x01(\x0b\x32#.chromiumos.test.api.VMRequirements\x12<\n\x0etesting_client\x18\x06 \x01(\x0e\x32$.chromiumos.test.api.VMTestingClient\x12?\n\x06labels\x18\x07 \x03(\x0b\x32/.chromiumos.test.api.LeaseVMRequest.LabelsEntry\x1a-\n\x0bLabelsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\"\xbf\x02\n\x0eVMRequirements\x12\x11\n\tgce_image\x18\x01 \x01(\t\x12\x12\n\ngce_region\x18\x02 \x01(\t\x12\x13\n\x0bgce_project\x18\x03 \x01(\t\x12\x13\n\x0bgce_network\x18\x04 \x01(\t\x12\x12\n\ngce_subnet\x18\x05 \x01(\t\x12#\n\x1bsubnet_mode_network_enabled\x18\x0b \x01(\x08\x12\x18\n\x10gce_machine_type\x18\x06 \x01(\t\x12\x11\n\tgce_scope\x18\x07 \x01(\t\x12\x16\n\x0egce_ip_address\x18\x08 \x01(\t\x12\x15\n\rgce_disk_size\x18\n \x01(\x03\x12\x1c\n\x14gce_min_cpu_platform\x18\x0c \x01(\t\x12)\n\x04type\x18\t \x01(\x0e\x32\x1b.chromiumos.test.api.VMType\"\xb5\x01\n\x02VM\x12\n\n\x02id\x18\x01 \x01(\t\x12/\n\x07\x61\x64\x64ress\x18\x02 \x01(\x0b\x32\x1e.chromiumos.test.api.VMAddress\x12)\n\x04type\x18\x03 \x01(\x0e\x32\x1b.chromiumos.test.api.VMType\x12\x12\n\ngce_region\x18\x04 \x01(\t\x12\x33\n\x0f\x65xpiration_time\x18\x05 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\"\'\n\tVMAddress\x12\x0c\n\x04host\x18\x01 \x01(\t\x12\x0c\n\x04port\x18\x02 \x01(\x05\"}\n\x0fLeaseVMResponse\x12\x10\n\x08lease_id\x18\x01 \x01(\t\x12#\n\x02vm\x18\x02 \x01(\x0b\x32\x17.chromiumos.test.api.VM\x12\x33\n\x0f\x65xpiration_time\x18\x03 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\"Z\n\x12\x45xtendLeaseRequest\x12\x10\n\x08lease_id\x18\x01 \x01(\t\x12\x32\n\x0f\x65xtend_duration\x18\x02 \x01(\x0b\x32\x19.google.protobuf.Duration\"\\\n\x13\x45xtendLeaseResponse\x12\x10\n\x08lease_id\x18\x01 \x01(\t\x12\x33\n\x0f\x65xpiration_time\x18\x02 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\"M\n\x10ReleaseVMRequest\x12\x10\n\x08lease_id\x18\x01 \x01(\t\x12\x13\n\x0bgce_project\x18\x02 \x01(\t\x12\x12\n\ngce_region\x18\x03 \x01(\t\"%\n\x11ReleaseVMResponse\x12\x10\n\x08lease_id\x18\x01 \x01(\t\"Z\n\x11ListLeasesRequest\x12\x0e\n\x06parent\x18\x01 \x01(\t\x12\x11\n\tpage_size\x18\x02 \x01(\x05\x12\x12\n\npage_token\x18\x03 \x01(\t\x12\x0e\n\x06\x66ilter\x18\x04 \x01(\t\"S\n\x12ListLeasesResponse\x12$\n\x03vms\x18\x01 \x03(\x0b\x32\x17.chromiumos.test.api.VM\x12\x17\n\x0fnext_page_token\x18\x02 \x01(\t\"(\n\x12ImportImageRequest\x12\x12\n\nimage_path\x18\x01 \x01(\t\")\n\x13ImportImageResponse\x12\x12\n\nimage_name\x18\x01 \x01(\t*E\n\x06VMType\x12\x17\n\x13VM_TYPE_UNSPECIFIED\x10\x00\x12\x0f\n\x0bVM_TYPE_DUT\x10\x01\x12\x11\n\rVM_TYPE_DRONE\x10\x02*u\n\x0fVMTestingClient\x12!\n\x1dVM_TESTING_CLIENT_UNSPECIFIED\x10\x00\x12\x1e\n\x1aVM_TESTING_CLIENT_CHROMEOS\x10\x01\x12\x1f\n\x1bVM_TESTING_CLIENT_CROSFLEET\x10\x02\x32\xf0\x03\n\x0fVMLeaserService\x12V\n\x07LeaseVM\x12#.chromiumos.test.api.LeaseVMRequest\x1a$.chromiumos.test.api.LeaseVMResponse\"\x00\x12\\\n\tReleaseVM\x12%.chromiumos.test.api.ReleaseVMRequest\x1a&.chromiumos.test.api.ReleaseVMResponse\"\x00\x12\x62\n\x0b\x45xtendLease\x12\'.chromiumos.test.api.ExtendLeaseRequest\x1a(.chromiumos.test.api.ExtendLeaseResponse\"\x00\x12_\n\nListLeases\x12&.chromiumos.test.api.ListLeasesRequest\x1a\'.chromiumos.test.api.ListLeasesResponse\"\x00\x12\x62\n\x0bImportImage\x12\'.chromiumos.test.api.ImportImageRequest\x1a(.chromiumos.test.api.ImportImageResponse\"\x00\x42/Z-go.chromium.org/chromiumos/config/go/test/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.api.vm_leaser_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z-go.chromium.org/chromiumos/config/go/test/api'
  _LEASEVMREQUEST_LABELSENTRY._options = None
  _LEASEVMREQUEST_LABELSENTRY._serialized_options = b'8\001'
  _VMTYPE._serialized_start=1730
  _VMTYPE._serialized_end=1799
  _VMTESTINGCLIENT._serialized_start=1801
  _VMTESTINGCLIENT._serialized_end=1918
  _LEASEVMREQUEST._serialized_start=126
  _LEASEVMREQUEST._serialized_end=488
  _LEASEVMREQUEST_LABELSENTRY._serialized_start=443
  _LEASEVMREQUEST_LABELSENTRY._serialized_end=488
  _VMREQUIREMENTS._serialized_start=491
  _VMREQUIREMENTS._serialized_end=810
  _VM._serialized_start=813
  _VM._serialized_end=994
  _VMADDRESS._serialized_start=996
  _VMADDRESS._serialized_end=1035
  _LEASEVMRESPONSE._serialized_start=1037
  _LEASEVMRESPONSE._serialized_end=1162
  _EXTENDLEASEREQUEST._serialized_start=1164
  _EXTENDLEASEREQUEST._serialized_end=1254
  _EXTENDLEASERESPONSE._serialized_start=1256
  _EXTENDLEASERESPONSE._serialized_end=1348
  _RELEASEVMREQUEST._serialized_start=1350
  _RELEASEVMREQUEST._serialized_end=1427
  _RELEASEVMRESPONSE._serialized_start=1429
  _RELEASEVMRESPONSE._serialized_end=1466
  _LISTLEASESREQUEST._serialized_start=1468
  _LISTLEASESREQUEST._serialized_end=1558
  _LISTLEASESRESPONSE._serialized_start=1560
  _LISTLEASESRESPONSE._serialized_end=1643
  _IMPORTIMAGEREQUEST._serialized_start=1645
  _IMPORTIMAGEREQUEST._serialized_end=1685
  _IMPORTIMAGERESPONSE._serialized_start=1687
  _IMPORTIMAGERESPONSE._serialized_end=1728
  _VMLEASERSERVICE._serialized_start=1921
  _VMLEASERSERVICE._serialized_end=2417
# @@protoc_insertion_point(module_scope)
