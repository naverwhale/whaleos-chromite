# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility functions that are useful for controllers."""
import logging

from chromite.api.gen.chromite.api import sysroot_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.cbuildbot import goma_util
from chromite.lib import build_target_lib
from chromite.lib import constants
from chromite.lib.parser import package_info
from chromite.lib import chroot_lib
from chromite.lib import sysroot_lib

class Error(Exception):
  """Base error class for the module."""


class InvalidMessageError(Error):
  """Invalid message."""


def ParseChroot(chroot_message):
  """Create a chroot object from the chroot message.

  Args:
    chroot_message (common_pb2.Chroot): The chroot message.

  Returns:
    Chroot: The parsed chroot object.

  Raises:
    AssertionError: When the message is not a Chroot message.
  """
  assert isinstance(chroot_message, common_pb2.Chroot)

  path = chroot_message.path or constants.DEFAULT_CHROOT_PATH
  cache_dir = chroot_message.cache_dir
  chrome_root = chroot_message.chrome_dir

  use_flags = [u.flag for u in chroot_message.env.use_flags]
  features = [f.feature for f in chroot_message.env.features]

  env = {}
  if use_flags:
    env['USE'] = ' '.join(use_flags)

  # Make sure it'll use the local source to build chrome when we have it.
  if chrome_root:
    env['CHROME_ORIGIN'] = 'LOCAL_SOURCE'

  if features:
    env['FEATURES'] = ' '.join(features)

  chroot = chroot_lib.Chroot(
      path=path, cache_dir=cache_dir, chrome_root=chrome_root, env=env)

  return chroot


def ParseSysroot(sysroot_message):
  """Create a sysroot object from the sysroot message.

  Args:
    sysroot_message (commmon_pb2.Sysroot): The sysroot message.

  Returns:
    Sysroot: The parsed sysroot object.

  Raises:
    AssertionError: When the message is not a Sysroot message.
  """
  assert isinstance(sysroot_message, sysroot_pb2.Sysroot)

  return sysroot_lib.Sysroot(sysroot_message.path)


def ParseGomaConfig(goma_message, chroot_path):
  """Parse a goma config message."""
  assert isinstance(goma_message, common_pb2.GomaConfig)

  if not goma_message.goma_dir:
    return None

  # Parse the goma config.
  chromeos_goma_dir = goma_message.chromeos_goma_dir or None
  if goma_message.goma_approach == common_pb2.GomaConfig.RBE_STAGING:
    goma_approach = goma_util.GomaApproach('?staging',
                                           'staging-goma.chromium.org', True)
  elif goma_message.goma_approach == common_pb2.GomaConfig.RBE_PROD:
    goma_approach = goma_util.GomaApproach('?prod', 'goma.chromium.org', True)
  else:
    goma_approach = goma_util.GomaApproach('?cros', 'goma.chromium.org', True)

  # Note that we are not specifying the goma log_dir so that goma will create
  # and use a tmp dir for the logs.
  stats_filename = goma_message.stats_file or None
  counterz_filename = goma_message.counterz_file or None

  return goma_util.Goma(goma_message.goma_dir,
                        goma_message.goma_client_json,
                        stage_name='BuildAPI',
                        chromeos_goma_dir=chromeos_goma_dir,
                        chroot_dir=chroot_path,
                        goma_approach=goma_approach,
                        stats_filename=stats_filename,
                        counterz_filename=counterz_filename)


def ParseBuildTarget(build_target_message, profile_message=None):
  """Create a BuildTarget object from a build_target message.

  Args:
    build_target_message (common_pb2.BuildTarget): The BuildTarget message.
    profile_message (sysroot_pb2.Profile|None): The profile message.

  Returns:
    BuildTarget: The parsed instance.

  Raises:
    AssertionError: When the field is not a BuildTarget message.
  """
  assert isinstance(build_target_message, common_pb2.BuildTarget)
  assert (profile_message is None or
          isinstance(profile_message, sysroot_pb2.Profile))

  profile_name = profile_message.name if profile_message else None
  return build_target_lib.BuildTarget(
      build_target_message.name, profile=profile_name)


def ParseBuildTargets(repeated_build_target_field):
  """Create a BuildTarget for each entry in the repeated field.

  Args:
    repeated_build_target_field: The repeated BuildTarget field.

  Returns:
    list[BuildTarget]: The parsed BuildTargets.

  Raises:
    AssertionError: When the field contains non-BuildTarget messages.
  """
  return [ParseBuildTarget(target) for target in repeated_build_target_field]


def serialize_package_info(pkg_info: package_info.PackageInfo,
                           pkg_info_msg: common_pb2.PackageInfo):
  """Serialize a PackageInfo object to a PackageInfo proto."""
  if not isinstance(pkg_info, package_info.PackageInfo):
    # Allows us to swap everything to serialize_package_info, and search the
    # logs for usages that aren't passing though a PackageInfo yet.
    logging.warning(
        'serialize_package_info: Got a %s instead of a PackageInfo.',
        type(pkg_info))
    pkg_info = package_info.parse(pkg_info)
  pkg_info_msg.package_name = pkg_info.package
  if pkg_info.category:
    pkg_info_msg.category = pkg_info.category
  if pkg_info.vr:
    pkg_info_msg.version = pkg_info.vr


def deserialize_package_info(pkg_info_msg):
  """Deserialize a PackageInfo message to a PackageInfo object."""
  return package_info.parse(PackageInfoToString(pkg_info_msg))


def PackageInfoToCPV(package_info_msg):
  """Helper to translate a PackageInfo message into a CPV."""
  if not package_info_msg or not package_info_msg.package_name:
    return None

  return package_info.SplitCPV(PackageInfoToString(package_info_msg),
                               strict=False)


def PackageInfoToString(package_info_msg):
  # Combine the components into the full CPV string that SplitCPV parses.
  # TODO: Use the lib.parser.package_info.PackageInfo class instead.
  if not package_info_msg.package_name:
    raise ValueError('Invalid PackageInfo message.')

  c = ('%s/' % package_info_msg.category) if package_info_msg.category else ''
  p = package_info_msg.package_name
  v = ('-%s' % package_info_msg.version) if package_info_msg.version else ''
  return '%s%s%s' % (c, p, v)


def CPVToString(cpv):
  """Get the most useful string representation from a CPV.

  Args:
    cpv (package_info.CPV): The CPV object.

  Returns:
    str

  Raises:
    ValueError - when the CPV has no useful fields set.
  """
  if cpv.cpf:
    return cpv.cpf
  elif cpv.cpv:
    return cpv.cpv
  elif cpv.cp:
    return cpv.cp
  elif cpv.package:
    return cpv.package
  else:
    raise ValueError('Invalid CPV provided.')
