# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Android operations."""

import os
from typing import TYPE_CHECKING

from chromite.api import faux
from chromite.api import validate
from chromite.api.controller import controller_util
from chromite.api.gen.chromite.api import android_pb2
from chromite.lib import constants
from chromite.lib import osutils
from chromite.lib.parser import package_info
from chromite.service import android
from chromite.service import packages

if TYPE_CHECKING:
  from chromite.api import api_config


ANDROIDPIN_MASK_PATH = os.path.join(constants.SOURCE_ROOT,
                                    constants.CHROMIUMOS_OVERLAY_DIR,
                                    'profiles', 'default', 'linux',
                                    'package.mask', 'androidpin')


def _GetLatestBuildResponse(_input_proto, output_proto, _config):
  """Fake GetLatestBuild response."""
  output_proto.android_version = '7123456'


@faux.success(_GetLatestBuildResponse)
@faux.empty_error
@validate.require_any('android_build_branch', 'android_package')
@validate.validation_complete
def GetLatestBuild(input_proto, output_proto, _config):
  branch = (input_proto.android_build_branch or
            android.GetAndroidBranchForPackage(input_proto.android_package))
  build_id, _ = android.GetLatestBuild(branch)
  output_proto.android_version = build_id


def _MarkStableResponse(_input_proto, output_proto, _config):
  """Add fake status to a successful response."""
  output_proto.android_atom.category = 'category'
  output_proto.android_atom.package_name = 'android-package-name'
  output_proto.android_atom.version = '1.2'
  output_proto.status = android_pb2.MARK_STABLE_STATUS_SUCCESS


@faux.success(_MarkStableResponse)
@faux.empty_error
@validate.require('package_name')
@validate.validation_complete
def MarkStable(input_proto: android_pb2.MarkStableRequest,
               output_proto: android_pb2.MarkStableResponse,
               _config: 'api_config.ApiConfig') -> None:
  """Uprev Android, if able.

  Uprev Android, verify that the newly uprevved package can be emerged, and
  return the new package info.

  See AndroidService documentation in api/proto/android.proto.

  Args:
    input_proto: The input proto.
    output_proto: The output proto.
    _config: The call config.
  """
  chroot = controller_util.ParseChroot(input_proto.chroot)
  build_targets = controller_util.ParseBuildTargets(input_proto.build_targets)
  package_name = input_proto.package_name
  android_build_branch = input_proto.android_build_branch
  android_version = input_proto.android_version
  skip_commit = input_proto.skip_commit

  # Assume success.
  output_proto.status = android_pb2.MARK_STABLE_STATUS_SUCCESS
  # TODO(crbug/904939): This should move to service/android.py and the port
  # should be finished.
  try:
    android_atom_to_build = packages.uprev_android(
        android_package=package_name,
        chroot=chroot,
        build_targets=build_targets,
        android_build_branch=android_build_branch,
        android_version=android_version,
        skip_commit=skip_commit,
    )
  except packages.AndroidIsPinnedUprevError as e:
    # If the uprev failed due to a pin, CI needs to unpin and retry.
    android_atom_to_build = e.new_android_atom
    output_proto.status = android_pb2.MARK_STABLE_STATUS_PINNED

  if android_atom_to_build:
    pkg = package_info.parse(android_atom_to_build)
    controller_util.serialize_package_info(pkg, output_proto.android_atom)
  else:
    output_proto.status = android_pb2.MARK_STABLE_STATUS_EARLY_EXIT


# We don't use @faux.success for UnpinVersion because output_proto is unused.
@faux.all_empty
@validate.validation_complete
def UnpinVersion(_input_proto: android_pb2.UnpinVersionRequest,
                 _output_proto: android_pb2.UnpinVersionResponse,
                 _config: 'api_config.ApiConfig') -> None:
  """Unpin the Android version.

  See AndroidService documentation in api/proto/android.proto.

  Args:
    _input_proto: The input proto. (not used.)
    _output_proto: The output proto. (not used.)
    _config: The call config.
  """
  osutils.SafeUnlink(ANDROIDPIN_MASK_PATH)
