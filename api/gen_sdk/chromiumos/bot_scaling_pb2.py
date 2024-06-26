# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: chromiumos/bot_scaling.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1c\x63hromiumos/bot_scaling.proto\x12\nchromiumos\"Z\n\x07\x42otType\x12\x10\n\x08\x62ot_size\x18\x01 \x01(\t\x12\x15\n\rcores_per_bot\x18\x02 \x01(\x02\x12\x13\n\x0bhourly_cost\x18\x03 \x01(\x02\x12\x11\n\tmemory_gb\x18\x04 \x01(\x02\"@\n\x11SwarmingDimension\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t\x12\x0e\n\x06values\x18\x03 \x03(\t\"\xad\x06\n\tBotPolicy\x12\x11\n\tbot_group\x18\x01 \x01(\t\x12\x16\n\x0eresource_group\x18\x0b \x01(\t\x12%\n\x08\x62ot_type\x18\x02 \x01(\x0b\x32\x13.chromiumos.BotType\x12\x45\n\x13scaling_restriction\x18\x03 \x01(\x0b\x32(.chromiumos.BotPolicy.ScalingRestriction\x12\x44\n\x13region_restrictions\x18\x04 \x03(\x0b\x32\'.chromiumos.BotPolicy.RegionRestriction\x12:\n\x13swarming_dimensions\x18\x05 \x03(\x0b\x32\x1d.chromiumos.SwarmingDimension\x12/\n\x0bpolicy_mode\x18\x06 \x01(\x0e\x32\x1a.chromiumos.BotPolicy.Mode\x12\x16\n\x0elookback_hours\x18\x07 \x01(\x11\x12:\n\x0cscaling_mode\x18\x08 \x01(\x0e\x32$.chromiumos.BotPolicy.BotScalingMode\x12\x19\n\x11swarming_instance\x18\t \x01(\t\x12\x13\n\x0b\x61pplication\x18\n \x01(\t\x1aw\n\x12ScalingRestriction\x12\x13\n\x0b\x62ot_ceiling\x18\x01 \x01(\x05\x12\x11\n\tbot_floor\x18\x02 \x01(\x05\x12\x10\n\x08min_idle\x18\x03 \x01(\x05\x12\x11\n\tstep_size\x18\x04 \x01(\x05\x12\x14\n\x0c\x62ot_fallback\x18\x05 \x01(\x05\x1a\x43\n\x11RegionRestriction\x12\x0e\n\x06region\x18\x01 \x01(\t\x12\x0e\n\x06prefix\x18\x02 \x01(\t\x12\x0e\n\x06weight\x18\x03 \x01(\x02\"7\n\x04Mode\x12\x10\n\x0cUNKNOWN_MODE\x10\x00\x12\r\n\tMONITORED\x10\x01\x12\x0e\n\nCONFIGURED\x10\x02\"Y\n\x0e\x42otScalingMode\x12\x18\n\x14UNKNOWN_SCALING_MODE\x10\x00\x12\x0b\n\x07STEPPED\x10\x01\x12\n\n\x06\x44\x45MAND\x10\x02\x12\x14\n\x10STEPPED_DECREASE\x10\x03\";\n\x0c\x42otPolicyCfg\x12+\n\x0c\x62ot_policies\x18\x01 \x03(\x0b\x32\x15.chromiumos.BotPolicy\"}\n\x10ReducedBotPolicy\x12\x11\n\tbot_group\x18\x01 \x01(\t\x12%\n\x08\x62ot_type\x18\x02 \x01(\x0b\x32\x13.chromiumos.BotType\x12/\n\x0bpolicy_mode\x18\x03 \x01(\x0e\x32\x1a.chromiumos.BotPolicy.Mode\"I\n\x13ReducedBotPolicyCfg\x12\x32\n\x0c\x62ot_policies\x18\x01 \x03(\x0b\x32\x1c.chromiumos.ReducedBotPolicy\"\xab\x03\n\rScalingAction\x12\x11\n\tbot_group\x18\x01 \x01(\t\x12%\n\x08\x62ot_type\x18\x02 \x01(\x0b\x32\x13.chromiumos.BotType\x12\x38\n\nactionable\x18\x03 \x01(\x0e\x32$.chromiumos.ScalingAction.Actionable\x12\x16\n\x0e\x62ots_requested\x18\x04 \x01(\x05\x12\x42\n\x10regional_actions\x18\x05 \x03(\x0b\x32(.chromiumos.ScalingAction.RegionalAction\x12\x19\n\x11\x65stimated_savings\x18\x06 \x01(\x02\x12\x0f\n\x07\x62ot_min\x18\x07 \x01(\x05\x12\x0f\n\x07\x62ot_max\x18\x08 \x01(\x05\x12\x13\n\x0b\x61pplication\x18\t \x01(\t\x1aH\n\x0eRegionalAction\x12\x0e\n\x06region\x18\x01 \x01(\t\x12\x0e\n\x06prefix\x18\x02 \x01(\t\x12\x16\n\x0e\x62ots_requested\x18\x03 \x01(\x05\".\n\nActionable\x12\x0f\n\x0bUNSPECIFIED\x10\x00\x12\x07\n\x03YES\x10\x01\x12\x06\n\x02NO\x10\x02\"v\n\x13ResourceUtilization\x12\x0e\n\x06region\x18\x01 \x01(\t\x12\x0b\n\x03vms\x18\x02 \x01(\x05\x12\x0c\n\x04\x63pus\x18\x03 \x01(\x02\x12\x11\n\tmemory_gb\x18\x04 \x01(\x02\x12\x0f\n\x07\x64isk_gb\x18\x05 \x01(\x02\x12\x10\n\x08max_cpus\x18\x06 \x01(\x02\"l\n\x16\x41pplicationUtilization\x12\x13\n\x0b\x61pplication\x18\x01 \x01(\t\x12=\n\x14resource_utilization\x18\x02 \x03(\x0b\x32\x1f.chromiumos.ResourceUtilization\"\xca\x01\n\x0eRoboCropAction\x12\x32\n\x0fscaling_actions\x18\x01 \x03(\x0b\x32\x19.chromiumos.ScalingAction\x12=\n\x14resource_utilization\x18\x02 \x03(\x0b\x32\x1f.chromiumos.ResourceUtilization\x12\x45\n\x19\x61ppl_resource_utilization\x18\x03 \x03(\x0b\x32\".chromiumos.ApplicationUtilizationBY\n!com.google.chrome.crosinfra.protoZ4go.chromium.org/chromiumos/infra/proto/go/chromiumosb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'chromiumos.bot_scaling_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'\n!com.google.chrome.crosinfra.protoZ4go.chromium.org/chromiumos/infra/proto/go/chromiumos'
  _BOTTYPE._serialized_start=44
  _BOTTYPE._serialized_end=134
  _SWARMINGDIMENSION._serialized_start=136
  _SWARMINGDIMENSION._serialized_end=200
  _BOTPOLICY._serialized_start=203
  _BOTPOLICY._serialized_end=1016
  _BOTPOLICY_SCALINGRESTRICTION._serialized_start=680
  _BOTPOLICY_SCALINGRESTRICTION._serialized_end=799
  _BOTPOLICY_REGIONRESTRICTION._serialized_start=801
  _BOTPOLICY_REGIONRESTRICTION._serialized_end=868
  _BOTPOLICY_MODE._serialized_start=870
  _BOTPOLICY_MODE._serialized_end=925
  _BOTPOLICY_BOTSCALINGMODE._serialized_start=927
  _BOTPOLICY_BOTSCALINGMODE._serialized_end=1016
  _BOTPOLICYCFG._serialized_start=1018
  _BOTPOLICYCFG._serialized_end=1077
  _REDUCEDBOTPOLICY._serialized_start=1079
  _REDUCEDBOTPOLICY._serialized_end=1204
  _REDUCEDBOTPOLICYCFG._serialized_start=1206
  _REDUCEDBOTPOLICYCFG._serialized_end=1279
  _SCALINGACTION._serialized_start=1282
  _SCALINGACTION._serialized_end=1709
  _SCALINGACTION_REGIONALACTION._serialized_start=1589
  _SCALINGACTION_REGIONALACTION._serialized_end=1661
  _SCALINGACTION_ACTIONABLE._serialized_start=1663
  _SCALINGACTION_ACTIONABLE._serialized_end=1709
  _RESOURCEUTILIZATION._serialized_start=1711
  _RESOURCEUTILIZATION._serialized_end=1829
  _APPLICATIONUTILIZATION._serialized_start=1831
  _APPLICATIONUTILIZATION._serialized_end=1939
  _ROBOCROPACTION._serialized_start=1942
  _ROBOCROPACTION._serialized_end=2144
# @@protoc_insertion_point(module_scope)
