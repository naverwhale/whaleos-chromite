# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: test_platform/multibot/leader_transitions.proto
"""Generated protocol buffer code."""
from chromite.third_party.google.protobuf.internal import builder as _builder
from chromite.third_party.google.protobuf import descriptor as _descriptor
from chromite.third_party.google.protobuf import descriptor_pool as _descriptor_pool
from chromite.third_party.google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from chromite.api.gen.test_platform.multibot import common_pb2 as test__platform_dot_multibot_dot_common__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n/test_platform/multibot/leader_transitions.proto\x12\x16test_platform.multibot\x1a#test_platform/multibot/common.proto\"\xf1\x02\n\x17LeaderTransitionMessage\x12N\n\tnew_state\x18\x01 \x01(\x0e\x32;.test_platform.multibot.LeaderTransitionMessage.LeaderState\x12\x42\n\x12\x66ollower_gathering\x18\x02 \x01(\x0b\x32&.test_platform.multibot.FollowersState\"\xc1\x01\n\x0bLeaderState\x12\x13\n\x0fSTATE_UNDEFINED\x10\x00\x12\x14\n\x10STATE_SCHEDULING\x10\x10\x12\x18\n\x14STATE_RUNNING_PREJOB\x10 \x12\x1f\n\x1bSTATE_WAITING_FOR_FOLLOWERS\x10\x30\x12\x1d\n\x19STATE_NOTIFYING_FOLLOWERS\x10@\x12\x19\n\x15STATE_RUNNING_PAYLOAD\x10P\x12\x12\n\x0eSTATE_CLEANING\x10`\"o\n\x0e\x46ollowersState\x12\x1d\n\x15waiting_for_followers\x18\x01 \x01(\x05\x12>\n\x0f\x66ollowers_heard\x18\x02 \x01(\x0b\x32%.test_platform.multibot.HostInfoStoreBBZ@go.chromium.org/chromiumos/infra/proto/go/test_platform/multibotb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'test_platform.multibot.leader_transitions_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z@go.chromium.org/chromiumos/infra/proto/go/test_platform/multibot'
  _LEADERTRANSITIONMESSAGE._serialized_start=113
  _LEADERTRANSITIONMESSAGE._serialized_end=482
  _LEADERTRANSITIONMESSAGE_LEADERSTATE._serialized_start=289
  _LEADERTRANSITIONMESSAGE_LEADERSTATE._serialized_end=482
  _FOLLOWERSSTATE._serialized_start=484
  _FOLLOWERSSTATE._serialized_end=595
# @@protoc_insertion_point(module_scope)
