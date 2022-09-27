# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Sysroot controller."""

import logging
import os

from chromite.api import controller
from chromite.api import faux
from chromite.api import validate
from chromite.api.controller import controller_util
from chromite.api.gen.chromiumos import common_pb2
from chromite.api.metrics import deserialize_metrics_log
from chromite.lib import binpkg
from chromite.lib import build_target_lib
from chromite.lib import chroot_lib
from chromite.lib import cros_build_lib
from chromite.lib import goma_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import sysroot_lib
from chromite.service import sysroot
from chromite.utils import metrics


_ACCEPTED_LICENSES = '@CHROMEOS'


def ExampleGetResponse():
  """Give an example response to assemble upstream in caller artifacts."""
  uabs = common_pb2.UploadedArtifactsByService
  cabs = common_pb2.ArtifactsByService
  return uabs.Sysroot(artifacts=[
     uabs.Sysroot.ArtifactPaths(
          artifact_type=cabs.Sysroot.ArtifactType.SIMPLE_CHROME_SYSROOT,
          paths=[
              common_pb2.Path(
                  path='/tmp/sysroot_chromeos-base_chromeos-chrome.tar.xz',
                  location=common_pb2.Path.OUTSIDE)
          ],
      ),
      uabs.Sysroot.ArtifactPaths(
          artifact_type=cabs.Sysroot.ArtifactType.DEBUG_SYMBOLS,
          paths=[
              common_pb2.Path(
                  path='/tmp/debug.tgz', location=common_pb2.Path.OUTSIDE)
          ],
      ),
      uabs.Sysroot.ArtifactPaths(
          artifact_type=cabs.Sysroot.ArtifactType.BREAKPAD_DEBUG_SYMBOLS,
          paths=[
              common_pb2.Path(
                  path='/tmp/debug_breakpad.tar.xz',
                  location=common_pb2.Path.OUTSIDE)
          ])
  ])


def GetArtifacts(in_proto: common_pb2.ArtifactsByService.Sysroot,
        chroot: chroot_lib.Chroot, sysroot_class: sysroot_lib.Sysroot,
        build_target: build_target_lib.BuildTarget, output_dir: str) -> list:
  """Builds and copies sysroot artifacts to specified output_dir.

  Copies sysroot artifacts to output_dir, returning a list of (output_dir: str)
  paths to the desired files.

  Args:
    in_proto: Proto request defining reqs.
    chroot: The chroot class used for these artifacts.
    sysroot_class: The sysroot class used for these artifacts.
    build_target: The build target used for these artifacts.
    output_dir: The path to write artifacts to.

  Returns:
    A list of dictionary mappings of ArtifactType to list of paths.
  """
  generated = []
  artifact_types = {
    in_proto.ArtifactType.SIMPLE_CHROME_SYSROOT:
        sysroot.CreateSimpleChromeSysroot,
    in_proto.ArtifactType.CHROME_EBUILD_ENV: sysroot.CreateChromeEbuildEnv,
    in_proto.ArtifactType.BREAKPAD_DEBUG_SYMBOLS: sysroot.BundleBreakpadSymbols,
    in_proto.ArtifactType.DEBUG_SYMBOLS: sysroot.BundleDebugSymbols,
  }

  for output_artifact in in_proto.output_artifacts:
    for artifact_type, func in artifact_types.items():
      if artifact_type in output_artifact.artifact_types:
        result = func(chroot, sysroot_class, build_target, output_dir)
        if result:
          generated.append({
              'paths': [result] if isinstance(result, str) else result,
              'type': artifact_type,
          })

  return generated


@faux.all_empty
@validate.require('build_target.name')
@validate.validation_complete
def Create(input_proto, output_proto, _config):
  """Create or replace a sysroot."""
  update_chroot = not input_proto.flags.chroot_current
  replace_sysroot = input_proto.flags.replace

  build_target = controller_util.ParseBuildTarget(input_proto.build_target,
                                                  input_proto.profile)
  package_indexes = [
      binpkg.PackageIndexInfo.from_protobuf(x)
      for x in input_proto.package_indexes
  ]
  run_configs = sysroot.SetupBoardRunConfig(
      force=replace_sysroot, upgrade_chroot=update_chroot,
      package_indexes=package_indexes)

  try:
    created = sysroot.Create(build_target, run_configs,
                             accept_licenses=_ACCEPTED_LICENSES)
  except sysroot.Error as e:
    cros_build_lib.Die(e)

  output_proto.sysroot.path = created.path
  output_proto.sysroot.build_target.name = build_target.name

  return controller.RETURN_CODE_SUCCESS


@faux.all_empty
@validate.require('build_target.name', 'packages')
@validate.require_each('packages', ['category', 'package_name'])
@validate.validation_complete
def GenerateArchive(input_proto, output_proto, _config):
  """Generate a sysroot. Typically used by informational builders."""
  build_target_name = input_proto.build_target.name
  pkg_list = []
  for package in input_proto.packages:
    pkg_list.append('%s/%s' % (package.category, package.package_name))

  with osutils.TempDir(delete=False) as temp_output_dir:
    sysroot_tar_path = sysroot.GenerateArchive(temp_output_dir,
                                               build_target_name,
                                               pkg_list)

  # By assigning this Path variable to the tar path, the tar file will be
  # copied out to the input_proto's ResultPath location.
  output_proto.sysroot_archive.path = sysroot_tar_path
  output_proto.sysroot_archive.location = common_pb2.Path.INSIDE


def _MockFailedPackagesResponse(_input_proto, output_proto, _config):
  """Mock error response that populates failed packages."""
  pkg = output_proto.failed_packages.add()
  pkg.package_name = 'package'
  pkg.category = 'category'
  pkg.version = '1.0.0_rc-r1'

  pkg2 = output_proto.failed_packages.add()
  pkg2.package_name = 'bar'
  pkg2.category = 'foo'
  pkg2.version = '3.7-r99'


@faux.empty_success
@faux.error(_MockFailedPackagesResponse)
@validate.require('sysroot.path', 'sysroot.build_target.name')
@validate.exists('sysroot.path')
@validate.validation_complete
def InstallToolchain(input_proto, output_proto, _config):
  """Install the toolchain into a sysroot."""
  compile_source = (
      input_proto.flags.compile_source or input_proto.flags.toolchain_changed)

  sysroot_path = input_proto.sysroot.path

  build_target = controller_util.ParseBuildTarget(
      input_proto.sysroot.build_target)
  target_sysroot = sysroot_lib.Sysroot(sysroot_path)
  run_configs = sysroot.SetupBoardRunConfig(usepkg=not compile_source)

  _LogBinhost(build_target.name)

  try:
    sysroot.InstallToolchain(build_target, target_sysroot, run_configs)
  except sysroot_lib.ToolchainInstallError as e:
    # Error installing - populate the failed package info.
    for pkg_info in e.failed_toolchain_info:
      package_info_msg = output_proto.failed_packages.add()
      controller_util.serialize_package_info(pkg_info, package_info_msg)

    return controller.RETURN_CODE_UNSUCCESSFUL_RESPONSE_AVAILABLE

  return controller.RETURN_CODE_SUCCESS


@faux.empty_success
@faux.error(_MockFailedPackagesResponse)
@validate.require('sysroot.build_target.name')
@validate.exists('sysroot.path')
@validate.require_each('packages', ['category', 'package_name'])
@validate.require_each('use_flags', ['flag'])
@validate.validation_complete
@metrics.collect_metrics
def InstallPackages(input_proto, output_proto, _config):
  """Install packages into a sysroot, building as necessary and permitted."""
  compile_source = (
      input_proto.flags.compile_source or input_proto.flags.toolchain_changed)
  # Testing if Goma will support unknown compilers now.
  use_goma = input_proto.flags.use_goma

  target_sysroot = sysroot_lib.Sysroot(input_proto.sysroot.path)
  build_target = controller_util.ParseBuildTarget(
      input_proto.sysroot.build_target)

  # Get the package atom for each specified package. The field is optional, so
  # error only when we cannot parse an atom for each of the given packages.
  packages = [controller_util.PackageInfoToCPV(x).cp
              for x in input_proto.packages]

  package_indexes = [
      binpkg.PackageIndexInfo.from_protobuf(x)
      for x in input_proto.package_indexes
  ]

  # Calculate which packages would have been merged, but don't install anything.
  dryrun = input_proto.flags.dryrun

  if not target_sysroot.IsToolchainInstalled():
    cros_build_lib.Die('Toolchain must first be installed.')

  _LogBinhost(build_target.name)

  use_flags = [u.flag for u in input_proto.use_flags]
  build_packages_config = sysroot.BuildPackagesRunConfig(
      usepkg=not compile_source,
      install_debug_symbols=True,
      packages=packages,
      package_indexes=package_indexes,
      use_flags=use_flags,
      use_goma=use_goma,
      incremental_build=False,
      setup_board=False,
      dryrun=dryrun)

  try:
    sysroot.BuildPackages(build_target, target_sysroot, build_packages_config)
  except sysroot_lib.PackageInstallError as e:
    if not e.failed_packages:
      # No packages to report, so just exit with an error code.
      return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY

    # We need to report the failed packages.
    for pkg_info in e.failed_packages:
      package_info_msg = output_proto.failed_packages.add()
      controller_util.serialize_package_info(pkg_info, package_info_msg)

    return controller.RETURN_CODE_UNSUCCESSFUL_RESPONSE_AVAILABLE

  # Return without populating the response if it is a dryrun.
  if dryrun:
    return controller.RETURN_CODE_SUCCESS

  # Copy goma logs to specified directory if there is a goma_config and
  # it contains a log_dir to store artifacts.
  if input_proto.goma_config.log_dir.dir:
    # Get the goma log directory based on the GLOG_log_dir env variable.
    # TODO(crbug.com/1045001): Replace environment variable with query to
    # goma object after goma refactoring allows this.
    log_source_dir = os.getenv('GLOG_log_dir')
    if not log_source_dir:
      cros_build_lib.Die('GLOG_log_dir must be defined.')
    archiver = goma_lib.LogsArchiver(
        log_source_dir,
        dest_dir=input_proto.goma_config.log_dir.dir,
        stats_file=input_proto.goma_config.stats_file,
        counterz_file=input_proto.goma_config.counterz_file)
    archiver_tuple = archiver.Archive()
    if archiver_tuple.stats_file:
      output_proto.goma_artifacts.stats_file = archiver_tuple.stats_file
    if archiver_tuple.counterz_file:
      output_proto.goma_artifacts.counterz_file = archiver_tuple.counterz_file
    output_proto.goma_artifacts.log_files[:] = archiver_tuple.log_files

  # Read metric events log and pipe them into output_proto.events.
  deserialize_metrics_log(output_proto.events, prefix=build_target.name)


def _LogBinhost(board):
  """Log the portage binhost for the given board."""
  binhost = portage_util.PortageqEnvvar('PORTAGE_BINHOST', board=board,
                                        allow_undefined=True)
  if not binhost:
    logging.warning('Portage Binhost not found.')
  else:
    logging.info('Portage Binhost: %s', binhost)
