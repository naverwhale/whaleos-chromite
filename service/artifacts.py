# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Artifacts service.

This service houses the high level business logic for all created artifacts.
"""

import collections
import glob
import logging
import os
import shutil
from typing import Dict, List, Optional, TYPE_CHECKING

from chromite.lib import autotest_util
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import toolchain_util
from chromite.lib.paygen import partition_lib
from chromite.lib.paygen import paygen_payload_lib
from chromite.lib.paygen import paygen_stateful_payload_lib

if TYPE_CHECKING:
  from chromite.lib import chroot_lib
  from chromite.lib import sysroot_lib
  from chromite.lib import build_target_lib

# Archive type constants.
ARCHIVE_CONTROL_FILES = 'control'
ARCHIVE_PACKAGES = 'packages'
ARCHIVE_SERVER_PACKAGES = 'server_packages'
ARCHIVE_TEST_SUITES = 'test_suites'

CPE_WARNINGS_FILE_TEMPLATE = 'cpe-warnings-chromeos-%s.txt'
CPE_RESULT_FILE_TEMPLATE = 'cpe-chromeos-%s.txt'

# The individual image archives for ArchiveImages.
IMAGE_TARS = {
    constants.BASE_IMAGE_BIN: constants.BASE_IMAGE_TAR,
    constants.TEST_IMAGE_BIN: constants.TEST_IMAGE_TAR,
    constants.RECOVERY_IMAGE_BIN: constants.RECOVERY_IMAGE_TAR,
    constants.TEST_GUEST_VM_DIR: constants.TEST_GUEST_VM_TAR,
    constants.BASE_GUEST_VM_DIR: constants.BASE_GUEST_VM_TAR,
    constants.KERNEL_IMAGE_BIN: constants.KERNEL_IMAGE_TAR,
}

TAST_BUNDLE_NAME = 'tast_bundles.tar.bz2'
TAST_COMPRESSOR = cros_build_lib.COMP_BZIP2

CpeResult = collections.namedtuple('CpeResult', ['report', 'warnings'])


class Error(Exception):
  """Base module error."""


class ArchiveBaseDirNotFound(Error):
  """Raised when the archive base directory does not exist.

  This error most likely indicates the board was not built.
  """


class CrosGenerateSysrootError(Error):
  """Error when running CrosGenerateSysroot."""


class NoFilesError(Error):
  """When there are no files to archive."""


def BuildFirmwareArchive(chroot: 'chroot_lib.Chroot',
                         sysroot: 'sysroot_lib.Sysroot',
                         output_directory: str) -> Optional[str]:
  """Build firmware_from_source.tar.bz2 in chroot's sysroot firmware directory.

  Args:
    chroot: The chroot to be used.
    sysroot: The sysroot whose artifacts are being archived.
    output_directory: The path were the completed archives should be put.

  Returns:
    The archive file path if created, None otherwise.
  """
  firmware_root = os.path.join(chroot.path, sysroot.path.lstrip(os.sep),
                               'firmware')
  if not os.path.exists(firmware_root):
    return None

  # Private fingerprint libraries should not be uploaded.
  private_fingerprint_dirs = glob.glob(
      os.path.join(firmware_root, '**/ec-private/fingerprint'),
      recursive=True)

  source_list = []
  for directory, _, filenames in os.walk(firmware_root):
    if any(directory.startswith(e) for e in private_fingerprint_dirs):
      continue
    for filename in filenames:
      source_list.append(os.path.relpath(
          os.path.join(directory, filename), firmware_root))

  if not source_list:
    return None

  archive_file = os.path.join(output_directory, constants.FIRMWARE_ARCHIVE_NAME)
  cros_build_lib.CreateTarball(
      archive_file, firmware_root, compression=cros_build_lib.COMP_BZIP2,
      chroot=chroot.path, inputs=source_list)

  return archive_file

def BundleFpmcuUnittests(chroot: 'chroot_lib.Chroot',
                         sysroot: 'sysroot_lib.Sysroot',
                         output_directory: 'str') -> Optional[str]:
  """Create artifact tarball for fingerprint MCU on-device unittests.

  Args:
    chroot: The chroot containing the sysroot.
    sysroot: The sysroot whose artifacts are being archived.
    output_directory: The path were the completed archives should be put.

  Returns:
    The archive file path if created, None otherwise.
  """
  fpmcu_unittests_root = os.path.join(chroot.path, sysroot.path.lstrip(os.sep),
                                      'firmware', 'chromeos-fpmcu-unittests')
  files = [os.path.relpath(f, fpmcu_unittests_root)
           for f in glob.iglob(os.path.join(fpmcu_unittests_root, '*'))]
  if not files:
    return None

  archive_file = os.path.join(output_directory,
                              constants.FPMCU_UNITTESTS_ARCHIVE_NAME)
  cros_build_lib.CreateTarball(
      archive_file, fpmcu_unittests_root, compression=cros_build_lib.COMP_BZIP2,
      chroot=chroot.path, inputs=files)

  return archive_file


def BundleAutotestFiles(chroot: 'chroot_lib.Chroot',
                        sysroot: 'sysroot_lib.Sysroot',
                        output_directory: str) -> Dict[str, str]:
  """Create the Autotest Hardware Test archives.

  Args:
    chroot: The chroot containing the sysroot.
    sysroot: The sysroot whose artifacts are being archived.
    output_directory: The path were the completed archives should be put.

  Returns:
    The paths of the files created in |output_directory| by their type.
  """
  assert sysroot.Exists(chroot=chroot)
  assert output_directory

  logging.debug('Inside artifacts_service BundleAutotestFiles (%s %s %s)',
                chroot.path, sysroot.path, output_directory)
  # archive_basedir is the base directory where the archive commands are run.
  # We want the folder containing the board's autotest folder.
  archive_basedir = chroot.full_path(sysroot.path,
                                     constants.AUTOTEST_BUILD_PATH)
  archive_basedir = os.path.dirname(archive_basedir)

  if not os.path.exists(archive_basedir):
    return {}

  builder = autotest_util.AutotestTarballBuilder(archive_basedir,
                                                 output_directory)
  results = {
      ARCHIVE_CONTROL_FILES: builder.BuildAutotestControlFilesTarball(),
      ARCHIVE_PACKAGES: builder.BuildAutotestPackagesTarball(),
      ARCHIVE_SERVER_PACKAGES: builder.BuildAutotestServerPackageTarball(),
      ARCHIVE_TEST_SUITES: builder.BuildAutotestTestSuitesTarball(),
  }

  # Strip the list down to just the successfully created archives.
  return {k: v for k, v in results.items() if v}


def BundleEBuildLogsTarball(chroot: 'chroot_lib.Chroot',
                            sysroot: 'sysroot_lib.Sysroot',
                            archive_dir: str) -> Optional[str]:
  """Builds a tarball containing ebuild logs.

  Args:
    chroot: The chroot to be used.
    sysroot: Sysroot whose images are being fetched.
    archive_dir: The directory to drop the tarball in.

  Returns:
    The file name of the output tarball, None if no package found.
  """
  tarball_paths = []
  logs_path = chroot.full_path(sysroot.path, 'tmp/portage')

  if not os.path.isdir(logs_path):
    return None

  if not os.path.exists(os.path.join(logs_path, 'logs')):
    return None

  tarball_paths.append('logs')
  tarball_output = os.path.join(archive_dir, 'ebuild_logs.tar.xz')
  try:
    cros_build_lib.CreateTarball(
        tarball_output, cwd=logs_path, chroot=chroot.path, inputs=tarball_paths)
  except cros_build_lib.TarballError:
    logging.warning('Unable to create logs tarball; ignoring until '
                    'https://crbug.com/999933 is sorted out.')
    return None
  return os.path.basename(tarball_output)


def BundleChromeOSConfig(chroot: 'chroot_lib.Chroot',
                         sysroot: 'sysroot_lib.Sysroot',
                         archive_dir: str) -> Optional[str]:
  """Outputs the ChromeOS Config payload.

  Args:
    chroot: The chroot to be used.
    sysroot: Sysroot whose config is being fetched.
    archive_dir: The directory to drop the config in.

  Returns:
    The file name of the output config, None if no config found.
  """
  config_path = chroot.full_path(sysroot.path,
                                 'usr/share/chromeos-config/yaml/config.yaml')

  if not os.path.exists(config_path):
    return None

  config_output = os.path.join(archive_dir, 'config.yaml')
  shutil.copy(config_path, config_output)
  return os.path.basename(config_output)


def BundleSimpleChromeArtifacts(chroot: 'chroot_lib.Chroot',
                                sysroot: 'sysroot_lib.Sysroot',
                                build_target: 'build_target_lib.BuildTarget',
                                output_dir: str) -> List[str]:
  """Gather all of the simple chrome artifacts.

  Args:
    chroot: The chroot to be used.
    sysroot: The sysroot.
    build_target: The sysroot's build target.
    output_dir: Where all result files should be stored.
  """
  files = []
  files.extend(CreateChromeRoot(chroot, build_target, output_dir))
  files.append(ArchiveChromeEbuildEnv(sysroot, output_dir))

  return files


def BundleVmFiles(chroot: 'chroot_lib.Chroot', test_results_dir: str,
                  output_dir: str) -> List[str]:
  """Gather all of the VM files.

  Args:
    chroot: The chroot to be used.
    test_results_dir: Test directory relative to chroot.
    output_dir: Where all result files should be stored.
  """
  image_dir = chroot.full_path(test_results_dir)
  archives = ArchiveFilesFromImageDir(image_dir, output_dir)
  return archives


# TODO(mmortensen): Refactor ArchiveFilesFromImageDir to be part of a library
# module. I tried moving it to lib/vm.py but this causes a circular dependency.
def ArchiveFilesFromImageDir(images_dir: str, archive_path: str) -> List[str]:
  """Archives the files into tarballs if they match a prefix from prefix_list.

  Create and return a list of tarballs from the images_dir of files that match
  VM disk and memory prefixes.

  Args:
    images_dir: The directory containing the images to archive.
    archive_path: The directory where the archives should be created.

  Returns:
    The paths to the tarballs.
  """
  images = []

  tar_files = []
  for image_path in images:
    image_rel_path = os.path.relpath(image_path, images_dir)
    image_parent_dir = os.path.dirname(image_path)
    image_file = os.path.basename(image_path)
    tarball_path = os.path.join(archive_path,
                                '%s.tar' % image_rel_path.replace('/', '_'))
    # Note that tar will chdir to |image_parent_dir|, so that |image_file|
    # is at the top-level of the tar file.
    cros_build_lib.CreateTarball(
        tarball_path,
        image_parent_dir,
        compression=cros_build_lib.COMP_BZIP2,
        inputs=[image_file])
    tar_files.append(tarball_path)

  return tar_files


def ArchiveChromeEbuildEnv(sysroot: 'sysroot_lib.Sysroot',
                           output_dir: str) -> str:
  """Generate Chrome ebuild environment.

  Args:
    sysroot: The sysroot where the original environment archive can be found.
    output_dir: Where the result should be stored.

  Returns:
    The path to the archive.

  Raises:
    NoFilesException: When the package cannot be found.
  """
  pkg_dir = os.path.join(sysroot.path, portage_util.VDB_PATH)
  files = glob.glob(os.path.join(pkg_dir, constants.CHROME_CP) + '-*')
  if not files:
    raise NoFilesError('Failed to find package %s' % constants.CHROME_CP)

  if len(files) > 1:
    logging.warning('Expected one package for %s, found %d',
                    constants.CHROME_CP, len(files))

  chrome_dir = sorted(files)[-1]
  env_bzip = os.path.join(chrome_dir, 'environment.bz2')
  result_path = os.path.join(output_dir, constants.CHROME_ENV_TAR)
  with osutils.TempDir() as tempdir:
    # Convert from bzip2 to tar format.
    bzip2 = cros_build_lib.FindCompressor(cros_build_lib.COMP_BZIP2)
    tempdir_tar_path = os.path.join(tempdir, constants.CHROME_ENV_FILE)
    cros_build_lib.run([bzip2, '-d', env_bzip, '-c'],
                       stdout=tempdir_tar_path)

    cros_build_lib.CreateTarball(result_path, tempdir)

  return result_path


def ArchiveImages(image_dir: str, output_dir: str) -> List[str]:
  """Create a .tar.xz archive for each image that has been created.

  Args:
    image_dir: The directory where the images are located.
    output_dir: The location where the archives should be created.

  Returns:
    The list of created file names.
  """
  files = os.listdir(image_dir)

  archives = []
  # Filter down to the ones that exist first.
  images = {img: tar for img, tar in IMAGE_TARS.items() if img in files}
  for img, tar in images.items():
    tarball_path = os.path.join(output_dir, tar)
    cros_build_lib.CreateTarball(tarball_path, image_dir, inputs=(img,),
                                 print_cmd=False)
    archives.append(tar)

  return archives


def BundleImageZip(output_dir: str, image_dir: str) -> str:
  """Bundle image.zip.

  Args:
    output_dir: The location outside the chroot where the files should be
      stored.
    image_dir: The directory containing the image.
  """

  filename = 'image.zip'
  zipfile = os.path.join(output_dir, filename)
  cros_build_lib.run(['zip', zipfile, '-r', '.'],
                     cwd=image_dir, capture_output=True)
  return filename


def CreateChromeRoot(chroot: 'chroot_lib.Chroot',
                     build_target: 'build_target_lib.BuildTarget',
                     output_dir: str) -> List[str]:
  """Create the chrome sysroot.

  Args:
    chroot: The chroot in which the sysroot should be built.
    build_target: The build target.
    output_dir: The location outside the chroot where the files should be
      stored.

  Returns:
    The list of created files.

  Raises:
    CrosGenerateSysrootError: When cros_generate_sysroot does not complete
      successfully.
  """
  chroot_args = chroot.get_enter_args()

  extra_env = {'USE': 'chrome_internal'}
  with chroot.tempdir() as tempdir:
    in_chroot_path = os.path.relpath(tempdir, chroot.path)
    cmd = ['cros_generate_sysroot', '--out-dir', in_chroot_path, '--board',
           build_target.name, '--deps-only', '--package', constants.CHROME_CP]

    try:
      cros_build_lib.run(cmd, enter_chroot=True, extra_env=extra_env,
                         chroot_args=chroot_args)
    except cros_build_lib.RunCommandError as e:
      raise CrosGenerateSysrootError(
          'Error encountered when running cros_generate_sysroot: %s' % e, e)

    files = []
    for path in osutils.DirectoryIterator(tempdir):
      if os.path.isfile(path):
        rel_path = os.path.relpath(path, tempdir)
        files.append(os.path.join(output_dir, rel_path))
    osutils.CopyDirContents(tempdir, output_dir, allow_nonempty=True)

    return files


def BundleTestUpdatePayloads(image_path: str, output_dir: str) -> List[str]:
  """Generate the test update payloads.

  Args:
    image_path: The full path to an image file.
    output_dir: The path where the payloads should be generated.

  Returns:
    The list of generated payloads.
  """
  payloads = GenerateTestPayloads(image_path, output_dir, full=True,
                                  stateful=True, delta=True, dlc=True)
  payloads.extend(GenerateQuickProvisionPayloads(image_path, output_dir))

  return payloads


def GenerateTestPayloads(target_image_path: str,
                         archive_dir: str,
                         full: bool = False,
                         delta: bool = False,
                         stateful: bool = False,
                         dlc: bool = False) -> List[str]:
  """Generates the payloads for hw testing.

  Args:
    target_image_path: The path to the image to generate payloads to.
    archive_dir: Where to store payloads we generated.
    full: Generate full payloads.
    delta: Generate delta payloads.
    stateful: Generate stateful payload.
    dlc: Generate sample-dlc payload if available.

  Returns:
    The list of payloads that were generated.
  """
  real_target = os.path.realpath(target_image_path)
  # The path to the target should look something like this:
  # .../link/R37-5952.0.2014_06_12_2302-a1/chromiumos_test_image.bin
  board, os_version = real_target.split('/')[-3:-1]
  prefix = 'chromeos'
  suffix = 'dev.bin'
  generated = []

  if full:
    # Names for full payloads look something like this:
    # chromeos_R37-5952.0.2014_06_12_2302-a1_link_full_dev.bin
    name = '_'.join([prefix, os_version, board, 'full', suffix])
    payload_path = os.path.join(archive_dir, name)
    paygen_payload_lib.GenerateUpdatePayload(target_image_path, payload_path)
    generated.append(payload_path)

  if delta:
    # Names for delta payloads look something like this:
    # chromeos_R37-5952.0.2014_06_12_2302-a1_R37-
    # 5952.0.2014_06_12_2302-a1_link_delta_dev.bin
    name = '_'.join([prefix, os_version, os_version, board, 'delta', suffix])
    payload_path = os.path.join(archive_dir, name)
    paygen_payload_lib.GenerateUpdatePayload(
        target_image_path, payload_path, src_image=target_image_path)
    generated.append(payload_path)

  if dlc and 'dlc_test' in portage_util.GetBoardUseFlags(board):
    dlc_prefix = 'dlc'
    dlc_id = 'sample-dlc'
    dlc_package = 'package'
    sample_dlc_image = os.path.join(os.path.dirname(target_image_path),
                                    dlc_prefix, dlc_id, dlc_package, 'dlc.img')

    if full:
      # Names for full sample-dlc payloads look something like this:
      # dlc_sample-dlc_package_R37-5952.0.2014_06_12_2302-a1_link_full_dev.bin
      name = '_'.join([dlc_prefix, dlc_id, dlc_package, os_version, board,
                       'full', suffix])
      payload_path = os.path.join(archive_dir, name)
      paygen_payload_lib.GenerateUpdatePayload(sample_dlc_image, payload_path)
      generated.append(payload_path)

    if delta:
      # Names for delta payloads look something like this:
      # dlc_sample-dlc_package_R37-5952.0.2014_06_12_2302-a1_R37-
      # 5952.0.2014_06_12_2302-a1_link_delta_dev.bin
      name = '_'.join([dlc_prefix, dlc_id, dlc_package, os_version, os_version,
                       board, 'delta', suffix])
      payload_path = os.path.join(archive_dir, name)
      paygen_payload_lib.GenerateUpdatePayload(sample_dlc_image, payload_path,
                                               src_image=sample_dlc_image)
      generated.append(payload_path)

  if stateful:
    generated.append(
        paygen_stateful_payload_lib.GenerateStatefulPayload(target_image_path,
                                                            archive_dir))

  return generated


def GenerateQuickProvisionPayloads(target_image_path: str,
                                   archive_dir: str) -> List[str]:
  """Generates payloads needed for quick_provision script.

  Args:
    target_image_path: The path to the image to extract the partitions.
    archive_dir: Where to store partitions when generated.

  Returns:
    The artifacts that were produced.
  """
  payloads = []
  with osutils.TempDir() as temp_dir:
    # These partitions are mainly used by quick_provision.
    kernel_part = 'kernel.bin'
    rootfs_part = 'rootfs.bin'
    partition_lib.ExtractKernel(
        target_image_path, os.path.join(temp_dir, kernel_part))
    partition_lib.ExtractRoot(target_image_path,
                              os.path.join(temp_dir, rootfs_part),
                              truncate=False)

    # Partition to payload mapping.
    mapping = {
        kernel_part: constants.QUICK_PROVISION_PAYLOAD_KERNEL,
        rootfs_part: constants.QUICK_PROVISION_PAYLOAD_ROOTFS,
    }

    if partition_lib.HasMiniOSPartitions(target_image_path):
      minios_part = 'minios.bin'
      partition_lib.ExtractMiniOS(
          target_image_path, os.path.join(temp_dir, minios_part))
      mapping[minios_part] = constants.QUICK_PROVISION_PAYLOAD_MINIOS

    for partition, payload in mapping.items():
      source = os.path.join(temp_dir, partition)
      dest = os.path.join(archive_dir, payload)
      cros_build_lib.CompressFile(source, dest)
      payloads.append(dest)

  return payloads


def BundleAFDOGenerationArtifacts(is_orderfile: bool,
                                  chroot: 'chroot_lib.Chroot', chrome_root: str,
                                  build_target: 'build_target_lib.BuildTarget',
                                  output_dir: str) -> List[str]:
  """Generate artifacts for toolchain-related AFDO artifacts.

  Args:
    is_orderfile: The generation is for orderfile (True) or for AFDO (False).
    chroot: The chroot in which the sysroot should be built.
    chrome_root: Path to Chrome root.
    build_target: The build target.
    output_dir: The location outside the chroot where the files should be
      stored.

  Returns:
    The list of tarballs of artifacts.
  """
  chroot_args = chroot.get_enter_args()
  with chroot.tempdir() as tempdir:
    if is_orderfile:
      generate_orderfile = toolchain_util.GenerateChromeOrderfile(
          board=build_target.name,
          output_dir=tempdir,
          chrome_root=chrome_root,
          chroot_path=chroot.path,
          chroot_args=chroot_args)

      generate_orderfile.Perform()
    else:
      generate_afdo = toolchain_util.GenerateBenchmarkAFDOProfile(
          board=build_target.name,
          output_dir=tempdir,
          chroot_path=chroot.path,
          chroot_args=chroot_args)

      generate_afdo.Perform()

    files = []
    for path in osutils.DirectoryIterator(tempdir):
      if os.path.isfile(path):
        rel_path = os.path.relpath(path, tempdir)
        files.append(os.path.join(output_dir, rel_path))
    osutils.CopyDirContents(tempdir, output_dir, allow_nonempty=True)

    return files


def BundleTastFiles(chroot: 'chroot_lib.Chroot', sysroot: 'sysroot_lib.Sysroot',
                    output_dir: str) -> Optional[str]:
  """Tar up the Tast private test bundles.

  Args:
    chroot: Chroot containing the sysroot.
    sysroot: Sysroot whose files are being archived.
    output_dir: Location for storing the result tarball.

  Returns:
    Path of the generated tarball, or None if there is no private test bundles.
  """
  cwd = os.path.join(chroot.path, sysroot.path.lstrip(os.sep), 'build')

  dirs = []
  for d in ('libexec/tast', 'share/tast'):
    if os.path.exists(os.path.join(cwd, d)):
      dirs.append(d)
  if not dirs:
    return None

  tarball = os.path.join(output_dir, TAST_BUNDLE_NAME)
  cros_build_lib.CreateTarball(tarball, cwd, compression=TAST_COMPRESSOR,
                               chroot=chroot.path, inputs=dirs)

  return tarball

def GenerateCpeReport(chroot: 'chroot_lib.Chroot',
                      sysroot: 'sysroot_lib.Sysroot',
                      output_dir: str) -> CpeResult:
  """Generate CPE export.

  Args:
    chroot: The chroot where the command is being run.
    sysroot: The sysroot whose dependencies are being reported.
    output_dir: The path where the output files should be written.

  Returns:
    CpeResult: The CPE result instance with the full paths to the report and
      warnings files.
  """
  # Call cros_extract_deps to create the report that the export produced.
  # We'll assume the basename for the board name to match how these were built
  # out in the old system.
  # TODO(saklein): Can we remove the board name from the report file names?
  build_target = os.path.basename(sysroot.path)
  report_path = os.path.join(output_dir,
                             CPE_RESULT_FILE_TEMPLATE % build_target)

  # Build the command and its args.
  cmd = [
      'cros_extract_deps', '--sysroot', sysroot.path, '--format', 'cpe',
      'virtual/target-os', '--output-path', report_path
  ]

  logging.info('Beginning CPE Export.')
  result = cros_build_lib.run(
      cmd,
      capture_output=True,
      enter_chroot=True,
      chroot_args=chroot.get_enter_args())
  logging.info('CPE Export Complete.')

  # Write out the warnings the export produced.
  warnings_path = os.path.join(output_dir,
                               CPE_WARNINGS_FILE_TEMPLATE % build_target)

  osutils.WriteFile(warnings_path, result.stderr, mode='wb')

  return CpeResult(report=report_path, warnings=warnings_path)

def BundleGceTarball(output_dir: str, image_dir: str) -> str:
  """Bundle the test image into a tarball suitable for importing into GCE.

  Args:
    output_dir: The location outside the chroot where the files should be
      stored.
    image_dir: The directory containing the image.

  Returns:
    Path to the generated tarball.
  """
  test_image = os.path.join(image_dir, constants.TEST_IMAGE_BIN)
  tarball = os.path.join(output_dir, constants.TEST_IMAGE_GCE_TAR)

  with osutils.TempDir() as tempdir:
    disk_raw = os.path.join(tempdir, 'disk.raw')
    osutils.SafeSymlink(test_image, disk_raw)
    cros_build_lib.CreateTarball(
        tarball, tempdir, compression=cros_build_lib.COMP_GZIP,
        inputs=('disk.raw',), extra_args=['--dereference', '--format=oldgnu'])

  return tarball
