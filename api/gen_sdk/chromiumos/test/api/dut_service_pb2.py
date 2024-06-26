# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/test/api/dut_service.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen_sdk.chromiumos.config.api import device_config_id_pb2 as chromiumos_dot_config_dot_api_dot_device__config__id__pb2
from chromite.api.gen_sdk.chromiumos.longrunning import operations_pb2 as chromiumos_dot_longrunning_dot_operations__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n%chromiumos/test/api/dut_service.proto\x12\x13\x63hromiumos.test.api\x1a,chromiumos/config/api/device_config_id.proto\x1a\'chromiumos/longrunning/operations.proto\"\xaa\x01\n\x12\x45xecCommandRequest\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x0f\n\x07\x63ommand\x18\x02 \x01(\t\x12\x0c\n\x04\x61rgs\x18\x03 \x03(\t\x12\r\n\x05stdin\x18\x04 \x01(\x0c\x12+\n\x06stdout\x18\x05 \x01(\x0e\x32\x1b.chromiumos.test.api.Output\x12+\n\x06stderr\x18\x06 \x01(\x0e\x32\x1b.chromiumos.test.api.Output\"\xd1\x01\n\x13\x45xecCommandResponse\x12\x44\n\texit_info\x18\x01 \x01(\x0b\x32\x31.chromiumos.test.api.ExecCommandResponse.ExitInfo\x12\x0e\n\x06stdout\x18\x02 \x01(\x0c\x12\x0e\n\x06stderr\x18\x03 \x01(\x0c\x1aT\n\x08\x45xitInfo\x12\x0e\n\x06status\x18\x01 \x01(\x05\x12\x10\n\x08signaled\x18\x02 \x01(\x08\x12\x0f\n\x07started\x18\x03 \x01(\x08\x12\x15\n\rerror_message\x18\x04 \x01(\t\" \n\x10\x46\x65tchFileRequest\x12\x0c\n\x04\x66ile\x18\x01 \x01(\t\"\x14\n\x04\x46ile\x12\x0c\n\x04\x66ile\x18\x01 \x01(\x0c\"/\n\x13\x46\x65tchCrashesRequest\x12\x12\n\nfetch_core\x18\x02 \x01(\x08J\x04\x08\x01\x10\x02\"\xa1\x01\n\x14\x46\x65tchCrashesResponse\x12\x10\n\x08\x63rash_id\x18\x01 \x01(\x03\x12/\n\x05\x63rash\x18\x02 \x01(\x0b\x32\x1e.chromiumos.test.api.CrashInfoH\x00\x12.\n\x04\x62lob\x18\x03 \x01(\x0b\x32\x1e.chromiumos.test.api.CrashBlobH\x00\x12\x0e\n\x04\x63ore\x18\x04 \x01(\x0cH\x00\x42\x06\n\x04\x64\x61ta\"\xb3\x01\n\tCrashInfo\x12\x11\n\texec_name\x18\x01 \x01(\t\x12\x0c\n\x04prod\x18\x02 \x01(\t\x12\x0b\n\x03ver\x18\x03 \x01(\t\x12\x0b\n\x03sig\x18\x04 \x01(\t\x12$\n\x1cin_progress_integration_test\x18\x05 \x01(\t\x12\x11\n\tcollector\x18\x06 \x01(\t\x12\x32\n\x06\x66ields\x18\x07 \x03(\x0b\x32\".chromiumos.test.api.CrashMetadata\"*\n\rCrashMetadata\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\x0c\n\x04text\x18\x02 \x01(\t\"8\n\tCrashBlob\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\x0c\n\x04\x62lob\x18\x02 \x01(\x0c\x12\x10\n\x08\x66ilename\x18\x03 \x01(\t\"\x97\x01\n\x0eRestartRequest\x12\x0c\n\x04\x61rgs\x18\x01 \x03(\t\x12\x41\n\x05retry\x18\x02 \x01(\x0b\x32\x32.chromiumos.test.api.RestartRequest.ReconnectRetry\x1a\x34\n\x0eReconnectRetry\x12\r\n\x05times\x18\x01 \x01(\x05\x12\x13\n\x0binterval_ms\x18\x02 \x01(\x03\"!\n\x0fRestartResponse\x12\x0e\n\x06output\x18\x01 \x01(\t\"\x11\n\x0fRestartMetadata\"\xf3\x04\n\x0c\x43\x61\x63heRequest\x12;\n\x04\x66ile\x18\x01 \x01(\x0b\x32+.chromiumos.test.api.CacheRequest.LocalFileH\x00\x12\x36\n\x04pipe\x18\x02 \x01(\x0b\x32&.chromiumos.test.api.CacheRequest.PipeH\x00\x12;\n\x07gs_file\x18\x03 \x01(\x0b\x32(.chromiumos.test.api.CacheRequest.GSFileH\x01\x12\x42\n\x0bgs_zip_file\x18\x04 \x01(\x0b\x32+.chromiumos.test.api.CacheRequest.GSZipFileH\x01\x12\x42\n\x0bgs_tar_file\x18\x05 \x01(\x0b\x32+.chromiumos.test.api.CacheRequest.GSTARFileH\x01\x12\x36\n\x05retry\x18\x06 \x01(\x0b\x32\'.chromiumos.test.api.CacheRequest.Retry\x1a\x19\n\tLocalFile\x12\x0c\n\x04path\x18\x01 \x01(\t\x1a\x18\n\x04Pipe\x12\x10\n\x08\x63ommands\x18\x01 \x01(\t\x1a\x1d\n\x06GSFile\x12\x13\n\x0bsource_path\x18\x01 \x01(\t\x1a \n\tGSZipFile\x12\x13\n\x0bsource_path\x18\x01 \x01(\t\x1a\x35\n\tGSTARFile\x12\x13\n\x0bsource_path\x18\x01 \x01(\t\x12\x13\n\x0bsource_file\x18\x02 \x01(\t\x1a+\n\x05Retry\x12\r\n\x05times\x18\x01 \x01(\x05\x12\x13\n\x0binterval_ms\x18\x02 \x01(\x03\x42\r\n\x0b\x64\x65stinationB\x08\n\x06source\"\xc4\x01\n\rCacheResponse\x12=\n\x07success\x18\x01 \x01(\x0b\x32*.chromiumos.test.api.CacheResponse.SuccessH\x00\x12=\n\x07\x66\x61ilure\x18\x02 \x01(\x0b\x32*.chromiumos.test.api.CacheResponse.FailureH\x00\x1a\t\n\x07Success\x1a \n\x07\x46\x61ilure\x12\x15\n\rerror_message\x18\x01 \x01(\tB\x08\n\x06result\"\x0f\n\rCacheMetadata\"\x17\n\x15\x46orceReconnectRequest\"\xdf\x01\n\x16\x46orceReconnectResponse\x12\x46\n\x07success\x18\x01 \x01(\x0b\x32\x33.chromiumos.test.api.ForceReconnectResponse.SuccessH\x00\x12\x46\n\x07\x66\x61ilure\x18\x02 \x01(\x0b\x32\x33.chromiumos.test.api.ForceReconnectResponse.FailureH\x00\x1a\t\n\x07Success\x1a \n\x07\x46\x61ilure\x12\x15\n\rerror_message\x18\x01 \x01(\tB\x08\n\x06result\"\x18\n\x16\x46orceReconnectMetadata\"\x1d\n\x1b\x44\x65tectDeviceConfigIdRequest\"\xc1\x02\n\x1c\x44\x65tectDeviceConfigIdResponse\x12L\n\x07success\x18\x01 \x01(\x0b\x32\x39.chromiumos.test.api.DetectDeviceConfigIdResponse.SuccessH\x00\x12L\n\x07\x66\x61ilure\x18\x02 \x01(\x0b\x32\x39.chromiumos.test.api.DetectDeviceConfigIdResponse.FailureH\x00\x1aY\n\x07Success\x12N\n\x14\x64\x65tected_scan_config\x18\x01 \x01(\x0b\x32\x30.chromiumos.config.api.DeviceConfigId.ScanConfig\x1a \n\x07\x46\x61ilure\x12\x15\n\rerror_message\x18\x01 \x01(\tB\x08\n\x06result*,\n\x06Output\x12\x0f\n\x0bOUTPUT_PIPE\x10\x00\x12\x11\n\rOUTPUT_STDOUT\x10\x01\x32\xaa\x06\n\nDutService\x12\x62\n\x0b\x45xecCommand\x12\'.chromiumos.test.api.ExecCommandRequest\x1a(.chromiumos.test.api.ExecCommandResponse0\x01\x12\x65\n\x0c\x46\x65tchCrashes\x12(.chromiumos.test.api.FetchCrashesRequest\x1a).chromiumos.test.api.FetchCrashesResponse0\x01\x12x\n\x07Restart\x12#.chromiumos.test.api.RestartRequest\x1a!.chromiumos.longrunning.Operation\"%\xd2\x41\"\n\x0fRestartResponse\x12\x0fRestartMetadata\x12}\n\x14\x44\x65tectDeviceConfigId\x12\x30.chromiumos.test.api.DetectDeviceConfigIdRequest\x1a\x31.chromiumos.test.api.DetectDeviceConfigIdResponse0\x01\x12O\n\tFetchFile\x12%.chromiumos.test.api.FetchFileRequest\x1a\x19.chromiumos.test.api.File0\x01\x12p\n\x05\x43\x61\x63he\x12!.chromiumos.test.api.CacheRequest\x1a!.chromiumos.longrunning.Operation\"!\xd2\x41\x1e\n\rCacheResponse\x12\rCacheMetadata\x12\x94\x01\n\x0e\x46orceReconnect\x12*.chromiumos.test.api.ForceReconnectRequest\x1a!.chromiumos.longrunning.Operation\"3\xd2\x41\x30\n\x16\x46orceReconnectResponse\x12\x16\x46orceReconnectMetadataB/Z-go.chromium.org/chromiumos/config/go/test/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.test.api.dut_service_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z-go.chromium.org/chromiumos/config/go/test/api'
  _DUTSERVICE.methods_by_name['Restart']._options = None
  _DUTSERVICE.methods_by_name['Restart']._serialized_options = b'\322A\"\n\017RestartResponse\022\017RestartMetadata'
  _DUTSERVICE.methods_by_name['Cache']._options = None
  _DUTSERVICE.methods_by_name['Cache']._serialized_options = b'\322A\036\n\rCacheResponse\022\rCacheMetadata'
  _DUTSERVICE.methods_by_name['ForceReconnect']._options = None
  _DUTSERVICE.methods_by_name['ForceReconnect']._serialized_options = b'\322A0\n\026ForceReconnectResponse\022\026ForceReconnectMetadata'
  _OUTPUT._serialized_start=2773
  _OUTPUT._serialized_end=2817
  _EXECCOMMANDREQUEST._serialized_start=150
  _EXECCOMMANDREQUEST._serialized_end=320
  _EXECCOMMANDRESPONSE._serialized_start=323
  _EXECCOMMANDRESPONSE._serialized_end=532
  _EXECCOMMANDRESPONSE_EXITINFO._serialized_start=448
  _EXECCOMMANDRESPONSE_EXITINFO._serialized_end=532
  _FETCHFILEREQUEST._serialized_start=534
  _FETCHFILEREQUEST._serialized_end=566
  _FILE._serialized_start=568
  _FILE._serialized_end=588
  _FETCHCRASHESREQUEST._serialized_start=590
  _FETCHCRASHESREQUEST._serialized_end=637
  _FETCHCRASHESRESPONSE._serialized_start=640
  _FETCHCRASHESRESPONSE._serialized_end=801
  _CRASHINFO._serialized_start=804
  _CRASHINFO._serialized_end=983
  _CRASHMETADATA._serialized_start=985
  _CRASHMETADATA._serialized_end=1027
  _CRASHBLOB._serialized_start=1029
  _CRASHBLOB._serialized_end=1085
  _RESTARTREQUEST._serialized_start=1088
  _RESTARTREQUEST._serialized_end=1239
  _RESTARTREQUEST_RECONNECTRETRY._serialized_start=1187
  _RESTARTREQUEST_RECONNECTRETRY._serialized_end=1239
  _RESTARTRESPONSE._serialized_start=1241
  _RESTARTRESPONSE._serialized_end=1274
  _RESTARTMETADATA._serialized_start=1276
  _RESTARTMETADATA._serialized_end=1293
  _CACHEREQUEST._serialized_start=1296
  _CACHEREQUEST._serialized_end=1923
  _CACHEREQUEST_LOCALFILE._serialized_start=1682
  _CACHEREQUEST_LOCALFILE._serialized_end=1707
  _CACHEREQUEST_PIPE._serialized_start=1709
  _CACHEREQUEST_PIPE._serialized_end=1733
  _CACHEREQUEST_GSFILE._serialized_start=1735
  _CACHEREQUEST_GSFILE._serialized_end=1764
  _CACHEREQUEST_GSZIPFILE._serialized_start=1766
  _CACHEREQUEST_GSZIPFILE._serialized_end=1798
  _CACHEREQUEST_GSTARFILE._serialized_start=1800
  _CACHEREQUEST_GSTARFILE._serialized_end=1853
  _CACHEREQUEST_RETRY._serialized_start=1855
  _CACHEREQUEST_RETRY._serialized_end=1898
  _CACHERESPONSE._serialized_start=1926
  _CACHERESPONSE._serialized_end=2122
  _CACHERESPONSE_SUCCESS._serialized_start=2069
  _CACHERESPONSE_SUCCESS._serialized_end=2078
  _CACHERESPONSE_FAILURE._serialized_start=2080
  _CACHERESPONSE_FAILURE._serialized_end=2112
  _CACHEMETADATA._serialized_start=2124
  _CACHEMETADATA._serialized_end=2139
  _FORCERECONNECTREQUEST._serialized_start=2141
  _FORCERECONNECTREQUEST._serialized_end=2164
  _FORCERECONNECTRESPONSE._serialized_start=2167
  _FORCERECONNECTRESPONSE._serialized_end=2390
  _FORCERECONNECTRESPONSE_SUCCESS._serialized_start=2069
  _FORCERECONNECTRESPONSE_SUCCESS._serialized_end=2078
  _FORCERECONNECTRESPONSE_FAILURE._serialized_start=2080
  _FORCERECONNECTRESPONSE_FAILURE._serialized_end=2112
  _FORCERECONNECTMETADATA._serialized_start=2392
  _FORCERECONNECTMETADATA._serialized_end=2416
  _DETECTDEVICECONFIGIDREQUEST._serialized_start=2418
  _DETECTDEVICECONFIGIDREQUEST._serialized_end=2447
  _DETECTDEVICECONFIGIDRESPONSE._serialized_start=2450
  _DETECTDEVICECONFIGIDRESPONSE._serialized_end=2771
  _DETECTDEVICECONFIGIDRESPONSE_SUCCESS._serialized_start=2638
  _DETECTDEVICECONFIGIDRESPONSE_SUCCESS._serialized_end=2727
  _DETECTDEVICECONFIGIDRESPONSE_FAILURE._serialized_start=2080
  _DETECTDEVICECONFIGIDRESPONSE_FAILURE._serialized_end=2112
  _DUTSERVICE._serialized_start=2820
  _DUTSERVICE._serialized_end=3630
# @@protoc_insertion_point(module_scope)
