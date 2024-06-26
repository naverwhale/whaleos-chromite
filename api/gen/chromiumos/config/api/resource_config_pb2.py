# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/config/api/resource_config.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n+chromiumos/config/api/resource_config.proto\x12\x15\x63hromiumos.config.api\"\xf9\x17\n\x0eResourceConfig\x12H\n\x02\x61\x63\x18\x05 \x01(\x0b\x32<.chromiumos.config.api.ResourceConfig.PowerSourcePreferences\x12H\n\x02\x64\x63\x18\x06 \x01(\x0b\x32<.chromiumos.config.api.ResourceConfig.PowerSourcePreferences\x1a\x16\n\x14\x43onservativeGovernor\x1a\x66\n\x10OndemandGovernor\x12&\n\x0epowersave_bias\x18\x01 \x01(\rR\x0epowersave-bias\x12*\n\x10sampling_rate_ms\x18\x02 \x01(\rR\x10sampling-rate-ms\x1a\x15\n\x13PerformanceGovernor\x1a\x13\n\x11PowersaveGovernor\x1a\x13\n\x11SchedutilGovernor\x1a\x13\n\x11UserspaceGovernor\x1a\xf2\x03\n\x08Governor\x12R\n\x0c\x63onservative\x18\x02 \x01(\x0b\x32:.chromiumos.config.api.ResourceConfig.ConservativeGovernorH\x00\x12J\n\x08ondemand\x18\x01 \x01(\x0b\x32\x36.chromiumos.config.api.ResourceConfig.OndemandGovernorH\x00\x12P\n\x0bperformance\x18\x03 \x01(\x0b\x32\x39.chromiumos.config.api.ResourceConfig.PerformanceGovernorH\x00\x12L\n\tpowersave\x18\x04 \x01(\x0b\x32\x37.chromiumos.config.api.ResourceConfig.PowersaveGovernorH\x00\x12L\n\tschedutil\x18\x05 \x01(\x0b\x32\x37.chromiumos.config.api.ResourceConfig.SchedutilGovernorH\x00\x12L\n\tuserspace\x18\x06 \x01(\x0b\x32\x37.chromiumos.config.api.ResourceConfig.UserspaceGovernorH\x00\x42\n\n\x08governor\x1a\x0c\n\nDefaultEpp\x1a\x10\n\x0ePerformanceEpp\x1a\x17\n\x15\x42\x61lancePerformanceEpp\x1a\x11\n\x0f\x42\x61lancePowerEpp\x1a\n\n\x08PowerEpp\x1a\xc7\x03\n\x1b\x45nergyPerformancePreference\x12\x43\n\x07\x64\x65\x66\x61ult\x18\x01 \x01(\x0b\x32\x30.chromiumos.config.api.ResourceConfig.DefaultEppH\x00\x12K\n\x0bperformance\x18\x02 \x01(\x0b\x32\x34.chromiumos.config.api.ResourceConfig.PerformanceEppH\x00\x12o\n\x13\x62\x61lance_performance\x18\x03 \x01(\x0b\x32;.chromiumos.config.api.ResourceConfig.BalancePerformanceEppH\x00R\x13\x62\x61lance-performance\x12]\n\rbalance_power\x18\x04 \x01(\x0b\x32\x35.chromiumos.config.api.ResourceConfig.BalancePowerEppH\x00R\rbalance-power\x12?\n\x05power\x18\x05 \x01(\x0b\x32..chromiumos.config.api.ResourceConfig.PowerEppH\x00\x42\x05\n\x03\x65pp\x1a\x45\n\x13\x43puOfflineSmallCore\x12.\n\x12min_active_threads\x18\x01 \x01(\rR\x12min-active-threads\x1a?\n\rCpuOfflineSMT\x12.\n\x12min_active_threads\x18\x01 \x01(\rR\x12min-active-threads\x1a@\n\x0e\x43puOfflineHalf\x12.\n\x12min_active_threads\x18\x01 \x01(\rR\x12min-active-threads\x1a\x8c\x02\n\x14\x43puOfflinePreference\x12[\n\nsmall_core\x18\x01 \x01(\x0b\x32\x39.chromiumos.config.api.ResourceConfig.CpuOfflineSmallCoreH\x00R\nsmall-core\x12\x42\n\x03smt\x18\x02 \x01(\x0b\x32\x33.chromiumos.config.api.ResourceConfig.CpuOfflineSMTH\x00\x12\x44\n\x04half\x18\x03 \x01(\x0b\x32\x34.chromiumos.config.api.ResourceConfig.CpuOfflineHalfH\x00\x42\r\n\x0b\x63pu_offline\x1a\x82\x02\n\x10PowerPreferences\x12@\n\x08governor\x18\x01 \x01(\x0b\x32..chromiumos.config.api.ResourceConfig.Governor\x12N\n\x03\x65pp\x18\x02 \x01(\x0b\x32\x41.chromiumos.config.api.ResourceConfig.EnergyPerformancePreference\x12\\\n\x0b\x63pu_offline\x18\x03 \x01(\x0b\x32:.chromiumos.config.api.ResourceConfig.CpuOfflinePreferenceR\x0b\x63pu-offline\x1a\x87\x07\n\x16PowerSourcePreferences\x12t\n\x19\x64\x65\x66\x61ult_power_preferences\x18\x01 \x01(\x0b\x32\x36.chromiumos.config.api.ResourceConfig.PowerPreferencesR\x19\x64\x65\x66\x61ult-power-preferences\x12t\n\x19web_rtc_power_preferences\x18\x02 \x01(\x0b\x32\x36.chromiumos.config.api.ResourceConfig.PowerPreferencesR\x19web-rtc-power-preferences\x12\x80\x01\n\"fullscreen_video_power_preferences\x18\x03 \x01(\x0b\x32\x36.chromiumos.config.api.ResourceConfig.PowerPreferencesR\x1c\x66ullscreen-power-preferences\x12t\n\x19vm_boot_power_preferences\x18\x04 \x01(\x0b\x32\x36.chromiumos.config.api.ResourceConfig.PowerPreferencesR\x19vm-boot-power-preferences\x12\x84\x01\n!borealis_gaming_power_preferences\x18\x05 \x01(\x0b\x32\x36.chromiumos.config.api.ResourceConfig.PowerPreferencesR!borealis-gaming-power-preferences\x12~\n\x1e\x61rcvm_gaming_power_preferences\x18\x06 \x01(\x0b\x32\x36.chromiumos.config.api.ResourceConfig.PowerPreferencesR\x1e\x61rcvm-gaming-power-preferences\x12\x80\x01\n\x1f\x62\x61ttery_saver_power_preferences\x18\x07 \x01(\x0b\x32\x36.chromiumos.config.api.ResourceConfig.PowerPreferencesR\x1f\x62\x61ttery-saver-power-preferencesB*Z(go.chromium.org/chromiumos/config/go/apib\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.config.api.resource_config_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z(go.chromium.org/chromiumos/config/go/api'
  _RESOURCECONFIG._serialized_start=71
  _RESOURCECONFIG._serialized_end=3136
  _RESOURCECONFIG_CONSERVATIVEGOVERNOR._serialized_start=237
  _RESOURCECONFIG_CONSERVATIVEGOVERNOR._serialized_end=259
  _RESOURCECONFIG_ONDEMANDGOVERNOR._serialized_start=261
  _RESOURCECONFIG_ONDEMANDGOVERNOR._serialized_end=363
  _RESOURCECONFIG_PERFORMANCEGOVERNOR._serialized_start=365
  _RESOURCECONFIG_PERFORMANCEGOVERNOR._serialized_end=386
  _RESOURCECONFIG_POWERSAVEGOVERNOR._serialized_start=388
  _RESOURCECONFIG_POWERSAVEGOVERNOR._serialized_end=407
  _RESOURCECONFIG_SCHEDUTILGOVERNOR._serialized_start=409
  _RESOURCECONFIG_SCHEDUTILGOVERNOR._serialized_end=428
  _RESOURCECONFIG_USERSPACEGOVERNOR._serialized_start=430
  _RESOURCECONFIG_USERSPACEGOVERNOR._serialized_end=449
  _RESOURCECONFIG_GOVERNOR._serialized_start=452
  _RESOURCECONFIG_GOVERNOR._serialized_end=950
  _RESOURCECONFIG_DEFAULTEPP._serialized_start=952
  _RESOURCECONFIG_DEFAULTEPP._serialized_end=964
  _RESOURCECONFIG_PERFORMANCEEPP._serialized_start=966
  _RESOURCECONFIG_PERFORMANCEEPP._serialized_end=982
  _RESOURCECONFIG_BALANCEPERFORMANCEEPP._serialized_start=984
  _RESOURCECONFIG_BALANCEPERFORMANCEEPP._serialized_end=1007
  _RESOURCECONFIG_BALANCEPOWEREPP._serialized_start=1009
  _RESOURCECONFIG_BALANCEPOWEREPP._serialized_end=1026
  _RESOURCECONFIG_POWEREPP._serialized_start=1028
  _RESOURCECONFIG_POWEREPP._serialized_end=1038
  _RESOURCECONFIG_ENERGYPERFORMANCEPREFERENCE._serialized_start=1041
  _RESOURCECONFIG_ENERGYPERFORMANCEPREFERENCE._serialized_end=1496
  _RESOURCECONFIG_CPUOFFLINESMALLCORE._serialized_start=1498
  _RESOURCECONFIG_CPUOFFLINESMALLCORE._serialized_end=1567
  _RESOURCECONFIG_CPUOFFLINESMT._serialized_start=1569
  _RESOURCECONFIG_CPUOFFLINESMT._serialized_end=1632
  _RESOURCECONFIG_CPUOFFLINEHALF._serialized_start=1634
  _RESOURCECONFIG_CPUOFFLINEHALF._serialized_end=1698
  _RESOURCECONFIG_CPUOFFLINEPREFERENCE._serialized_start=1701
  _RESOURCECONFIG_CPUOFFLINEPREFERENCE._serialized_end=1969
  _RESOURCECONFIG_POWERPREFERENCES._serialized_start=1972
  _RESOURCECONFIG_POWERPREFERENCES._serialized_end=2230
  _RESOURCECONFIG_POWERSOURCEPREFERENCES._serialized_start=2233
  _RESOURCECONFIG_POWERSOURCEPREFERENCES._serialized_end=3136
# @@protoc_insertion_point(module_scope)
