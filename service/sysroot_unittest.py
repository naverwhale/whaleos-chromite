# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Sysroot service unittest."""

from operator import attrgetter
import os
import shutil
from unittest import mock

from chromite.lib import binpkg
from chromite.lib import build_target_lib
from chromite.lib import constants
from chromite.lib import chroot_lib
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import sysroot_lib
from chromite.lib.parser import package_info
from chromite.service import sysroot


class SetupBoardRunConfigTest(cros_test_lib.TestCase):
  """Tests for the SetupBoardRunConfig class."""

  def testGetUpdateChrootArgs(self):
    """Test the update chroot args conversion method."""
    # False/0/None tests.
    instance = sysroot.SetupBoardRunConfig(usepkg=False, jobs=None,
                                           update_toolchain=False)
    args = instance.GetUpdateChrootArgs()
    self.assertIn('--nousepkg', args)
    self.assertIn('--skip_toolchain_update', args)
    self.assertNotIn('--usepkg', args)
    self.assertNotIn('--jobs', args)

    instance.jobs = 0
    args = instance.GetUpdateChrootArgs()
    self.assertNotIn('--jobs', args)

    # True/set values tests.
    instance = sysroot.SetupBoardRunConfig(usepkg=True, jobs=1,
                                           update_toolchain=True)
    args = instance.GetUpdateChrootArgs()
    self.assertIn('--usepkg', args)
    self.assertIn('--jobs', args)
    self.assertNotIn('--nousepkg', args)
    self.assertNotIn('--skip_toolchain_update', args)


class SetupBoardTest(cros_test_lib.MockTestCase):
  """Tests for SetupBoard."""

  def setUp(self):
    self.PatchObject(cros_build_lib, 'IsInsideChroot', return_value=True)

  def testFullRun(self):
    """Test a regular full run.

    This method is basically just a sanity check that it's trying to create the
    sysroot and install the toolchain by default.
    """
    target_sysroot = sysroot_lib.Sysroot('/build/board')
    create_mock = self.PatchObject(sysroot, 'Create',
                                   return_value=target_sysroot)
    install_toolchain_mock = self.PatchObject(sysroot, 'InstallToolchain')

    sysroot.SetupBoard(build_target_lib.BuildTarget('board'))

    create_mock.assert_called_once()
    install_toolchain_mock.assert_called_once()

  def testRegenConfigs(self):
    """Test the regen configs install prevention."""
    target_sysroot = sysroot_lib.Sysroot('/build/board')
    create_mock = self.PatchObject(sysroot, 'Create',
                                   return_value=target_sysroot)
    install_toolchain_mock = self.PatchObject(sysroot, 'InstallToolchain')

    target = build_target_lib.BuildTarget('board')
    configs = sysroot.SetupBoardRunConfig(regen_configs=True)

    sysroot.SetupBoard(target, run_configs=configs)

    # Should still try to create the sysroot, but should not try to install
    # the toolchain.
    create_mock.assert_called_once()
    install_toolchain_mock.assert_not_called()


class CreateTest(cros_test_lib.RunCommandTempDirTestCase):
  """Create function tests."""

  def setUp(self):
    # Avoid sudo password prompt for config writing.
    self.PatchObject(os, 'getuid', return_value=0)
    self.PatchObject(os, 'geteuid', return_value=0)

    # It has to be run inside the chroot.
    self.PatchObject(cros_build_lib, 'IsInsideChroot', return_value=True)

    # A board we have a sysroot for already.
    self.board = 'board'
    self.sysroot_path = os.path.join(self.tempdir, 'build', self.board)
    self.build_target = build_target_lib.BuildTarget(
        self.board, build_root=self.sysroot_path)
    # A board we don't have a sysroot for yet.
    self.unbuilt_board = 'board2'
    self.unbuilt_path = os.path.join(self.tempdir, 'build', self.unbuilt_board)
    self.unbuilt_target = build_target_lib.BuildTarget(
        self.unbuilt_board, build_root=self.unbuilt_path)

    # Create the sysroot.
    osutils.SafeMakedirs(self.sysroot_path)

  def testUpdateChroot(self):
    """Test the update_chroot related handling."""
    # Prevent it from doing anything else for this test.
    self.PatchObject(sysroot, '_CreateSysrootSkeleton')
    self.PatchObject(sysroot, '_InstallConfigs')
    self.PatchObject(sysroot, '_InstallPortageConfigs')

    # Make sure we have a board we haven't setup to avoid triggering the
    # existing sysroot logic. That is entirely unrelated to the chroot update.
    target = self.unbuilt_target

    # Test no update case.
    config = sysroot.SetupBoardRunConfig(upgrade_chroot=False)
    get_args_patch = self.PatchObject(config, 'GetUpdateChrootArgs')

    sysroot.Create(target, config, None)

    # The update chroot args not being fetched is a
    # strong enough signal that the update wasn't run.
    get_args_patch.assert_not_called()

    # Test update case.
    script_loc = os.path.join(constants.CROSUTILS_DIR, 'update_chroot')
    config = sysroot.SetupBoardRunConfig(upgrade_chroot=True)

    sysroot.Create(target, config, None)

    self.assertCommandContains([script_loc])

  def testForce(self):
    """Test the force flag."""
    # Prevent it from doing anything else for this test.
    self.PatchObject(sysroot, '_CreateSysrootSkeleton')
    self.PatchObject(sysroot, '_InstallConfigs')
    self.PatchObject(sysroot, '_InstallPortageConfigs')

    delete_patch = self.PatchObject(sysroot_lib.Sysroot, 'Delete')

    config = sysroot.SetupBoardRunConfig(force=False)
    sysroot.Create(self.build_target, config, None)
    delete_patch.assert_not_called()

    config = sysroot.SetupBoardRunConfig(force=True)
    sysroot.Create(self.build_target, config, None)
    delete_patch.assert_called_once()


class CreateSimpleChromeSysrootTest(cros_test_lib.MockTempDirTestCase):
  """Tests for CreateSimpleChromeSysroot."""

  def setUp(self):
    self.run_mock = self.PatchObject(cros_build_lib, 'run', return_value=True)
    self.source_root = os.path.join(self.tempdir, 'source_root')
    osutils.SafeMakedirs(self.source_root)
    self.PatchObject(constants, 'SOURCE_ROOT', new=self.source_root)

    # Create a chroot_path that also includes a chroot tmp dir.
    self.chroot_path = os.path.join(self.tempdir, 'chroot_dir')
    osutils.SafeMakedirs(os.path.join(self.chroot_path, 'tmp'))

    # Create output dir.
    self.output_dir = os.path.join(self.tempdir, 'output_dir')
    osutils.SafeMakedirs(self.output_dir)

    # Create chroot and build_target objs.
    self.chroot = chroot_lib.Chroot(path=self.chroot_path)
    self.build_target = build_target_lib.BuildTarget('target')



  def testCreateSimpleChromeSysroot(self):
    # Mock the artifact copy.
    tar_dest = os.path.join(self.output_dir, constants.CHROME_SYSROOT_TAR)
    self.PatchObject(shutil, 'copy', return_value=tar_dest)
    # Call service, verify arguments passed to run.
    sysroot.CreateSimpleChromeSysroot(self.chroot, None,
                                      self.build_target, self.output_dir)

    self.run_mock.assert_called_with(
        ['cros_generate_sysroot', '--out-dir', mock.ANY, '--board',
         self.build_target.name, '--deps-only', '--package',
         'chromeos-base/chromeos-chrome'], enter_chroot=True,
         cwd=self.source_root, chroot_args=mock.ANY, extra_env=mock.ANY
    )



class ArchiveChromeEbuildEnvTest(cros_test_lib.MockTempDirTestCase):
  """ArchiveChromeEbuildEnv tests."""

  def setUp(self):
    # Create the chroot and sysroot instances.
    self.chroot_path = os.path.join(self.tempdir, 'chroot_dir')
    self.chroot = chroot_lib.Chroot(path=self.chroot_path)
    self.sysroot_path = os.path.join(self.chroot_path, 'sysroot_dir')
    self.sysroot = sysroot_lib.Sysroot(self.sysroot_path)

    # Create the output directory.
    self.output_dir = os.path.join(self.tempdir, 'output_dir')
    osutils.SafeMakedirs(self.output_dir)

    # The sysroot's /var/db/pkg prefix for the chrome package directories.
    var_db_pkg = self.chroot.full_path(self.sysroot_path, portage_util.VDB_PATH)
    # Create the var/db/pkg dir so we have that much for no-chrome tests.
    osutils.SafeMakedirs(var_db_pkg)

    # Two versions of chrome to test the multiple version checks/handling.
    chrome_v1 = '%s-1.0.0-r1' % constants.CHROME_PN
    chrome_v2 = '%s-2.0.0-r1' % constants.CHROME_PN

    # Build the two chrome version paths.
    chrome_cat_dir = os.path.join(var_db_pkg, constants.CHROME_CN)
    self.chrome_v1_dir = os.path.join(chrome_cat_dir, chrome_v1)
    self.chrome_v2_dir = os.path.join(chrome_cat_dir, chrome_v2)

    # Directory tuple for verifying the result archive contents.
    self.expected_archive_contents = cros_test_lib.Directory('./',
                                                             'environment')

    # Create a environment.bz2 file to put into folders.
    env_file = os.path.join(self.tempdir, 'environment')
    osutils.Touch(env_file)
    cros_build_lib.run(['bzip2', env_file])
    self.env_bz2 = '%s.bz2' % env_file

  def _CreateChromeDir(self, path, populate=True):
    """Setup a chrome package directory.

    Args:
      path (str): The full chrome package path.
      populate (bool): Whether to include the environment bz2.
    """
    osutils.SafeMakedirs(path)
    if populate:
      shutil.copy(self.env_bz2, path)

  def testSingleChromeVersion(self):
    """Test a successful single-version run."""
    self._CreateChromeDir(self.chrome_v1_dir)

    created = sysroot.CreateChromeEbuildEnv(
      self.chroot, self.sysroot, None, self.output_dir)

    self.assertStartsWith(created, self.output_dir)
    cros_test_lib.VerifyTarball(created, self.expected_archive_contents)

  def testMultipleChromeVersions(self):
    """Test a successful multiple version run."""
    # Create both directories, but don't populate the v1 dir so it'll hit an
    # error if the wrong one is used.
    self._CreateChromeDir(self.chrome_v1_dir, populate=False)
    self._CreateChromeDir(self.chrome_v2_dir)

    created = sysroot.CreateChromeEbuildEnv(
      self.chroot, self.sysroot, None, self.output_dir)

    self.assertStartsWith(created, self.output_dir)
    cros_test_lib.VerifyTarball(created, self.expected_archive_contents)

  def testNoChrome(self):
    """Test no version of chrome present."""
    self.assertIsNone(
      sysroot.CreateChromeEbuildEnv(self.chroot, self.sysroot, None,
        self.output_dir))


class GenerateArchiveTest(cros_test_lib.MockTempDirTestCase):
  """Tests for GenerateArchive."""

  def setUp(self):
    self.run_mock = self.PatchObject(cros_build_lib, 'run', return_value=True)
    self.chroot_path = os.path.join(self.tempdir, 'chroot_dir')

  def testCreateSimpleChromeSysroot(self):
    # A board for which we will create a simple chrome sysroot.
    target = 'board'
    pkg_list = ['virtual/target-fuzzers']

    # Call service, verify arguments passed to run.
    sysroot.GenerateArchive(self.chroot_path, target, pkg_list)
    self.run_mock.assert_called_with(
        ['cros_generate_sysroot', '--out-file', constants.TARGET_SYSROOT_TAR,
         '--out-dir', mock.ANY, '--board', target,
         '--package', 'virtual/target-fuzzers'],
        cwd=constants.SOURCE_ROOT
    )


class InstallToolchainTest(cros_test_lib.MockTempDirTestCase):
  """Tests for InstallToolchain."""

  def setUp(self):
    self.PatchObject(cros_build_lib, 'IsInsideChroot', return_value=True)
    # A board we have a sysroot for already.
    self.board = 'board'
    self.sysroot_path = os.path.join(self.tempdir, 'build', self.board)
    self.build_target = build_target_lib.BuildTarget(
        self.board, build_root=self.sysroot_path)
    self.sysroot = sysroot_lib.Sysroot(self.sysroot_path)

    # A board we don't have a sysroot for yet.
    self.unbuilt_board = 'board2'
    self.unbuilt_path = os.path.join(self.tempdir, 'build', self.unbuilt_board)
    self.unbuilt_target = build_target_lib.BuildTarget(
        self.unbuilt_board, build_root=self.unbuilt_path)
    self.unbuilt_sysroot = sysroot_lib.Sysroot(self.unbuilt_path)

    osutils.SafeMakedirs(self.sysroot_path)

  def testNoSysroot(self):
    """Test handling of no sysroot."""
    with self.assertRaises(ValueError):
      sysroot.InstallToolchain(self.unbuilt_target, self.unbuilt_sysroot,
                               sysroot.SetupBoardRunConfig())

  def testLocalBuild(self):
    """Test the local build logic."""
    update_patch = self.PatchObject(self.sysroot, 'UpdateToolchain')

    # Test False.
    config = sysroot.SetupBoardRunConfig(usepkg=False, local_build=False)
    sysroot.InstallToolchain(self.build_target, self.sysroot, config)
    update_patch.assert_called_with(self.board, local_init=False)

    # Test usepkg True.
    update_patch.reset_mock()
    config = sysroot.SetupBoardRunConfig(usepkg=True, local_build=False)
    sysroot.InstallToolchain(self.build_target, self.sysroot, config)
    update_patch.assert_called_with(self.board, local_init=True)

    # Test local_build True.
    update_patch.reset_mock()
    config = sysroot.SetupBoardRunConfig(usepkg=False, local_build=True)
    sysroot.InstallToolchain(self.build_target, self.sysroot, config)
    update_patch.assert_called_with(self.board, local_init=True)


class BuildPackagesRunConfigTest(cros_test_lib.TestCase):
  """Tests for the BuildPackagesRunConfig."""

  def AssertHasRequiredArgs(self, args):
    """Tests the default/required args for the builders."""
    self.assertIn('--accept_licenses', args)
    self.assertIn('@CHROMEOS', args)
    self.assertIn('--skip_chroot_upgrade', args)

  def testGetBuildPackagesDefaultArgs(self):
    """Test the build_packages args building for empty/false/0 values."""
    # Test False/None/0 values.
    instance = sysroot.BuildPackagesRunConfig(usepkg=False,
                                              install_debug_symbols=False,
                                              packages=None)

    args = instance.GetBuildPackagesArgs()
    self.AssertHasRequiredArgs(args)
    # Debug symbols not included.
    self.assertNotIn('--withdebugsymbols', args)
    # Source used.
    self.assertIn('--nousepkg', args)
    # Flag removed due to broken logic.  See crbug/1048419.
    self.assertNotIn('--reuse_pkgs_from_local_boards', args)

  def testGetBuildPackagesArgs(self):
    """Test the build_packages args building for non-empty values."""
    packages = ['cat/pkg', 'cat2/pkg2']
    instance = sysroot.BuildPackagesRunConfig(
        usepkg=True,
        install_debug_symbols=True,
        packages=packages,
        setup_board=False,
        dryrun=True)

    args = instance.GetBuildPackagesArgs()
    self.AssertHasRequiredArgs(args)
    # Local build not used.
    self.assertNotIn('--nousepkg', args)
    self.assertNotIn('--reuse_pkgs_from_local_boards', args)
    # Debug symbols included.
    self.assertIn('--withdebugsymbols', args)
    self.assertIn('--skip_setup_board', args)
    # Packages included.
    for package in packages:
      self.assertIn(package, args)
    # Pretend flag included.
    self.assertIn('--pretend', args)

  def testGetBuildPackagesEnv(self):
    """Test the build_packages env."""
    instance = sysroot.BuildPackagesRunConfig()

    # PORTAGE_BINHOST is not set when there are no package_indexes
    self.assertNotIn('PORTAGE_BINHOST', instance.GetEnv())

    # PORTAGE_BINHOST is correctly set when there are package_indexes.
    pkg_indexes = [
        binpkg.PackageIndexInfo(
            build_target=build_target_lib.BuildTarget('board'),
            snapshot_sha='A', location='AAAA'),
        binpkg.PackageIndexInfo(
            build_target=build_target_lib.BuildTarget('board'),
            snapshot_sha='B', location='BBBB')]

    instance = sysroot.BuildPackagesRunConfig(package_indexes=pkg_indexes)

    env = instance.GetEnv()
    self.assertEqual(env.get('PORTAGE_BINHOST'),
                     ' '.join([x.location for x in reversed(pkg_indexes)]))


class BuildPackagesTest(cros_test_lib.RunCommandTestCase):
  """Test BuildPackages function."""

  def setUp(self):
    # Currently just used to keep the parallel emerge status file from being
    # created in the chroot. This probably isn't strictly necessary, but since
    # we can otherwise run this test without a chroot existing at all and
    # without touching the chroot folder, it's better to keep it out of there
    # all together.
    self.PatchObject(cros_build_lib, 'IsInsideChroot', return_value=True)

    self.board = 'board'
    self.target = build_target_lib.BuildTarget(self.board)
    self.sysroot_path = '/sysroot/path'
    self.sysroot = sysroot_lib.Sysroot(self.sysroot_path)

    self.build_packages = os.path.join(constants.CROSUTILS_DIR,
                                       'build_packages')
    self.base_command = [self.build_packages, '--board', self.board,
                         '--board_root', self.sysroot_path]

  def testSuccess(self):
    """Test successful run."""
    config = sysroot.BuildPackagesRunConfig()
    sysroot.BuildPackages(self.target, self.sysroot, config)

    # The rest of the command's args we test in BuildPackagesRunConfigTest,
    # so just make sure we're calling the right command and pass the args not
    # handled by the run config.
    self.assertCommandContains(self.base_command)

  def testPackageFailure(self):
    """Test package failure handling."""
    failed = ['cat/pkg', 'foo/bar']
    cpvs = [package_info.SplitCPV(p, strict=False) for p in failed]
    self.PatchObject(portage_util, 'ParseDieHookStatusFile',
                     return_value=cpvs)

    config = sysroot.BuildPackagesRunConfig()
    command = self.base_command + config.GetBuildPackagesArgs()

    result = cros_build_lib.CommandResult(cmd=command, returncode=1)
    error = cros_build_lib.RunCommandError('Error', result)

    self.rc.AddCmdResult(command, side_effect=error)

    try:
      sysroot.BuildPackages(self.target, self.sysroot, config)
    except sysroot_lib.PackageInstallError as e:
      self.assertEqual(cpvs, e.failed_packages)
      self.assertEqual(result, e.result)
    except Exception as e:
      self.fail('Unexpected exception type: %s' % type(e))
    else:
      self.fail('Expected an exception to be thrown.')


class GatherSymbolFilesTest(cros_test_lib.MockTempDirTestCase):
  """Base class for testing GatherSymbolFiles."""

  SLIM_CONTENT = """
some junk
"""

  FAT_CONTENT = """
STACK CFI 1234
some junk
STACK CFI 1234
"""


  def createSymbolFile(self, filename, content=FAT_CONTENT, size=0):
    """Create a symbol file using content with minimum size."""
    osutils.SafeMakedirs(os.path.dirname(filename))

    # If a file size is given, force that to be the minimum file size. Create
    # a sparse file so large files are practical.
    with open(filename, 'w+b') as f:
      f.truncate(size)
      f.seek(0)
      f.write(content.encode('utf-8'))

  def test_ListOutputOfGatherSymbolFiles(self):
    """Mimic how the controller materializes output of GatherSymbolFiles."""
    # Create directory with some symbol files.
    tar_tmp_dir = os.path.join(self.tempdir, 'tar_tmp')
    output_dir = os.path.join(self.tempdir, 'output')
    input_dir = os.path.join(self.tempdir, 'input')
    osutils.SafeMakedirs(output_dir)
    self.createSymbolFile(os.path.join(input_dir, 'a/b/c/file1.sym'))
    self.createSymbolFile(os.path.join(input_dir, 'a/b/c/d/file2.sym'))
    self.createSymbolFile(os.path.join(input_dir, 'a/file3.sym'))
    self.createSymbolFile(os.path.join(input_dir, 'a/b/c/d/e/file1.sym'))

    # Call sysroot.GatherSymbolFiles to find symbol files under self.tempdir
    # and copy them to output_dir.
    symbol_files = list(sysroot.GatherSymbolFiles(
        tar_tmp_dir, output_dir, [input_dir]))
    self.assertEqual(len(symbol_files), 4)

  def test_GatherSymbolFiles(self):
    """Test that files are found and copied."""
    # Create directory with some symbol files.
    tar_tmp_dir = os.path.join(self.tempdir, 'tar_tmp')
    output_dir = os.path.join(self.tempdir, 'output')
    input_dir = os.path.join(self.tempdir, 'input')
    osutils.SafeMakedirs(output_dir)
    self.createSymbolFile(os.path.join(input_dir, 'a/b/c/file1.sym'))
    self.createSymbolFile(os.path.join(input_dir, 'a/b/c/d/file2.sym'))
    self.createSymbolFile(os.path.join(input_dir, 'a/file3.sym'))
    self.createSymbolFile(os.path.join(input_dir, 'a/b/c/d/e/file1.sym'))

    # Call sysroot.GatherSymbolFiles to find symbol files under self.tempdir
    # and copy them to output_dir.
    symbol_files = list(sysroot.GatherSymbolFiles(
        tar_tmp_dir, output_dir, [input_dir]))

    # Construct the expected symbol files. Note that the SymbolFileTuple
    # field source_file_name is the full path to where a symbol file was found,
    # while relative_path is the relative path (from the search) where
    # it is created in the output directory.
    expected_symbol_files = [
        sysroot.SymbolFileTuple(
            source_file_name=os.path.join(input_dir, 'a/b/c/file1.sym'),
            relative_path='a/b/c/file1.sym'),
        sysroot.SymbolFileTuple(
            source_file_name=os.path.join(input_dir, 'a/b/c/d/file2.sym'),
            relative_path='a/b/c/d/file2.sym'),
        sysroot.SymbolFileTuple(
            source_file_name=os.path.join(input_dir, 'a/file3.sym'),
            relative_path='a/file3.sym'),
        sysroot.SymbolFileTuple(
            source_file_name=os.path.join(input_dir, 'a/b/c/d/e/file1.sym'),
            relative_path='a/b/c/d/e/file1.sym')
    ]

    # Sort symbol_files and expected_output_files by the relative_path
    # attribute.
    symbol_files = sorted(symbol_files, key=attrgetter('relative_path'))
    expected_symbol_files = sorted(expected_symbol_files,
                                   key=attrgetter('relative_path'))
    # Compare the files to the expected files. This verifies the size and
    # contents, and on failure shows the full contents.
    self.assertEqual(symbol_files, expected_symbol_files)

    # Verify that the files in output_dir match the SymbolFile relative_paths.
    files_in_output_dir = self.getFilesWithRelativeDir(output_dir)
    files_in_output_dir.sort()
    symbol_file_relative_paths = [obj.relative_path for obj in symbol_files]
    symbol_file_relative_paths.sort()
    self.assertEqual(files_in_output_dir, symbol_file_relative_paths)

    # Verify that the display_name of each symbol does not contain pathsep.
    symbol_file_relative_paths = [
        os.path.basename(obj.relative_path) for obj in symbol_files
    ]
    for display_name in symbol_file_relative_paths:
      self.assertEqual(-1, display_name.find(os.path.sep))

  def test_GatherSymbolTarFiles(self):
    """Test that symbol files in tar files are extracted."""
    output_dir = os.path.join(self.tempdir, 'output')
    osutils.SafeMakedirs(output_dir)

    # Set up test input directory.
    tarball_dir = os.path.join(self.tempdir, 'some/path')
    files_in_tarball = ['dir1/fileZ.sym', 'dir2/fileY.sym', 'dir2/fileX.sym',
                        'fileA.sym', 'fileB.sym', 'fileC.sym']
    for filename in files_in_tarball:
      self.createSymbolFile(os.path.join(tarball_dir, filename))
    temp_tarball_file_path = os.path.join(self.tempdir, 'symfiles.tar')
    cros_build_lib.CreateTarball(temp_tarball_file_path, tarball_dir)
    # Now that we've created the tarball, remove the .sym files in
    # the tarball dir and move the tarball to that dir.
    for filename in files_in_tarball:
      os.remove(os.path.join(tarball_dir, filename))
    tarball_path = os.path.join(tarball_dir, 'symfiles.tar')
    shutil.move(temp_tarball_file_path, tarball_path)

    # Execute sysroot.GatherSymbolFiles where the path contains the tarball.
    symbol_files = list(sysroot.GatherSymbolFiles(
        tarball_dir, output_dir, [tarball_path]))

    self.assertEqual(len(symbol_files), 6)
    # Verify the symbol_file relative_paths.
    symbol_file_relative_paths = [
        obj.relative_path for obj in symbol_files
    ]
    symbol_file_relative_paths.sort()
    self.assertEqual(symbol_file_relative_paths,
                     ['dir1/fileZ.sym', 'dir2/fileX.sym', 'dir2/fileY.sym',
                      'fileA.sym', 'fileB.sym', 'fileC.sym'])
    # Verify the symbol_file source_file_names.
    symbol_file_source_file_names = [
        obj.source_file_name for obj in symbol_files
    ]
    symbol_file_source_file_names.sort()
    # Note that the expected symbol_file_source_names are the full path to
    # the tarfile followed by the relative path, such as
    # /tmp/chromite.test2ng92vzo/some/path/symfiles.tar/dir1/fileZ.sym
    expected_symbol_file_source_names = [
        os.path.join(tarball_path, 'dir1/fileZ.sym'),
        os.path.join(tarball_path, 'dir2/fileX.sym'),
        os.path.join(tarball_path, 'dir2/fileY.sym'),
        os.path.join(tarball_path, 'fileA.sym'),
        os.path.join(tarball_path, 'fileB.sym'),
        os.path.join(tarball_path, 'fileC.sym')
    ]
    self.assertEqual(symbol_file_source_file_names,
                     expected_symbol_file_source_names)

    # Verify that the files in output_dir match the SymbolFile relative_paths.
    files_in_output_dir = self.getFilesWithRelativeDir(output_dir)
    files_in_output_dir.sort()
    symbol_file_relative_paths = [obj.relative_path for obj in symbol_files]
    symbol_file_relative_paths.sort()
    self.assertEqual(files_in_output_dir, symbol_file_relative_paths)
    # Verify that the display_name of each symbol does not contain pathsep.
    symbol_file_relative_paths = [
        os.path.basename(obj.relative_path) for obj in symbol_files
    ]
    for display_name in symbol_file_relative_paths:
      self.assertEqual(-1, display_name.find(os.path.sep))

  def test_GatherSymbolTarFilesWithNonSymFiles(self):
    """Test that non-symbol files in tar files are not extracted."""
    output_dir = os.path.join(self.tempdir, 'output')
    osutils.SafeMakedirs(output_dir)

    # Set up test input directory.
    tarball_dir = os.path.join(self.tempdir, 'some/path')
    files_in_tarball = ['dir1/fileU.sym', 'dir1/fileU.txt',
                        'fileD.sym', 'fileD.txt']
    for filename in files_in_tarball:
      # we don't care about file contents, so we are using createSymbolFile
      # for files whether they end with .sym or not.
      self.createSymbolFile(os.path.join(tarball_dir, filename))
    temp_tarball_file_path = os.path.join(self.tempdir, 'symfiles.tar')
    cros_build_lib.CreateTarball(temp_tarball_file_path, tarball_dir)
    # Now that we've created the tarball, remove the .sym files in
    # the tarball dir and move the tarball to that dir.
    for filename in files_in_tarball:
      os.remove(os.path.join(tarball_dir, filename))
    tarball_path = os.path.join(tarball_dir, 'symfiles.tar')
    shutil.move(temp_tarball_file_path, tarball_path)

    # Execute sysroot.GatherSymbolFiles where the path contains the tarball.
    symbol_files = list(sysroot.GatherSymbolFiles(
        tarball_dir, output_dir, [tarball_path]))

    # Verify the symbol_file relative_paths only has .sym files.
    symbol_file_relative_paths = [
        obj.relative_path for obj in symbol_files
    ]
    symbol_file_relative_paths.sort()
    self.assertEqual(symbol_file_relative_paths,
                     ['dir1/fileU.sym', 'fileD.sym'])
    for symfile in symbol_file_relative_paths:
      extension = symfile.split('.')[1]
      self.assertEqual(extension, 'sym')

  def test_GatherSymbolFileFullFilePaths(self):
    """Test full filepaths (.sym and .txt) only gather .sym files."""
    tar_tmp_dir = os.path.join(self.tempdir, 'tar_tmp')
    output_dir = os.path.join(self.tempdir, 'output')
    input_dir = os.path.join(self.tempdir, 'input')
    osutils.SafeMakedirs(output_dir)
    # We don't care about contents, so use createSymbolFiles for all files.
    self.createSymbolFile(os.path.join(input_dir, 'a_file.sym'))
    self.createSymbolFile(os.path.join(input_dir, 'a_file.txt'))

    # Call sysroot.GatherSymbolFiles with full paths to files, some of which
    # don't end in .sym, verify that only .sym files get copied to output_dir.
    symbol_files = list(sysroot.GatherSymbolFiles(
        tar_tmp_dir, output_dir,
        [os.path.join(input_dir, 'a_file.sym'),
         os.path.join(input_dir, 'a_file.txt')]))

    # Construct the expected symbol files. Note that the SymbolFileTuple
    # field source_file_name is the full path to where a symbol file was found,
    # while relative_path is the relative path (from the search) where
    # it is created in the output directory.
    expected_symbol_files = [
        sysroot.SymbolFileTuple(
            source_file_name=os.path.join(input_dir, 'a_file.sym'),
            relative_path='a_file.sym')
    ]

    # Compare the files to the expected files. This verifies the size and
    # contents, and on failure shows the full contents.
    self.assertEqual(symbol_files, expected_symbol_files)
    # Verify that only a_file.sym is in the output_dir.
    files_in_output_dir = self.getFilesWithRelativeDir(output_dir)
    self.assertEqual(files_in_output_dir, ['a_file.sym'])

  def getFilesWithRelativeDir(self, dest_dir):
    """Find all files below dest_dir using dir relative to dest_dir."""
    relative_files = []
    for path, __, files in os.walk(dest_dir):
      for filename in files:
        fullpath = os.path.join(path, filename)
        relpath = os.path.relpath(fullpath, dest_dir)
        relative_files.append(relpath)
    return relative_files


class GenerateBreakpadSymbolsTest(cros_test_lib.MockTempDirTestCase):
  """Base class for testing GenerateBreakpadSymbols."""

  def setUp(self):
    self.chroot_dir = os.path.join(self.tempdir, 'chroot_dir')
    osutils.SafeMakedirs(self.chroot_dir)

  def test_generateBreakpadSymbols(self):
    """Verify that calling the service layer invokes the script as expected."""
    chroot = chroot_lib.Chroot(self.chroot_dir)
    build_target = build_target_lib.BuildTarget('board')
    self.PatchObject(cros_build_lib, 'run')

    # Call the method being tested.
    sysroot.GenerateBreakpadSymbols(chroot, build_target, False)

    cros_build_lib.run.assert_called_with(['cros_generate_breakpad_symbols',
                                           '--board=board',
                                           '--jobs', mock.ANY,
                                           '--exclude-dir=firmware'],
                                          enter_chroot=True,
                                          chroot_args=['--chroot', mock.ANY])

  def test_generateBreakpadSymbolsWithDebug(self):
    """Verify that calling with debug invokes the script as expected."""
    chroot = chroot_lib.Chroot(self.chroot_dir)
    build_target = build_target_lib.BuildTarget('board')
    self.PatchObject(cros_build_lib, 'run')

    # Call the method being tested.
    sysroot.GenerateBreakpadSymbols(chroot, build_target, True)

    cros_build_lib.run.assert_called_with(['cros_generate_breakpad_symbols',
                                           '--debug',
                                           '--board=board',
                                           '--jobs', mock.ANY,
                                           '--exclude-dir=firmware'],
                                          enter_chroot=True,
                                          chroot_args=['--chroot', mock.ANY])


class BundleDebugSymbolsTest(cros_test_lib.MockTempDirTestCase):
  """Unittests for BundleDebugSymbols."""

  def setUp(self):
    # Create a chroot_path that also includes a chroot tmp dir.
    self.chroot_path = os.path.join(self.tempdir, 'chroot_dir')
    self.sysroot_path = os.path.join(self.chroot_path, 'build/target')

    # Has to be run outside the chroot.
    self.PatchObject(cros_build_lib, 'IsInsideChroot', return_value=False)

    osutils.SafeMakedirs(self.sysroot_path)
    osutils.SafeMakedirs(os.path.join(self.chroot_path, 'tmp'))


    # Create output dir.
    self.output_dir = os.path.join(self.tempdir, 'output_dir')
    osutils.SafeMakedirs(self.output_dir)

    # Create chroot, sysroot, and build_target objs.
    self.chroot = chroot_lib.Chroot(path=self.chroot_path)
    self.sysroot = sysroot_lib.Sysroot(path=self.sysroot_path)
    self.build_target = build_target_lib.BuildTarget('target')

  def testBundleBreakpadDebugSymbols(self):
    """BundleBreakpadSymbols calls cbuildbot/commands with correct args."""
    # Patch service layer functions.
    generate_breakpad_symbols_patch = self.PatchObject(
        sysroot, 'GenerateBreakpadSymbols',
        return_value=cros_build_lib.CommandResult(returncode=0, output=''))
    gather_symbol_files_patch = self.PatchObject(
        sysroot, 'GatherSymbolFiles',
        return_value=[sysroot.SymbolFileTuple(
            source_file_name='path/to/source/file1.sym',
            relative_path='file1.sym')])

    tar_file = sysroot.BundleBreakpadSymbols(self.chroot, self.sysroot,
                                             self.build_target, self.output_dir)

    # Verify mock objects were called.
    generate_breakpad_symbols_patch.assert_called_with(
        self.chroot, self.build_target, debug=True)
    gather_symbol_files_patch.assert_called()

    # Verify response proto contents and output directory contents.
    self.assertTrue(tar_file.endswith('/output_dir/debug_breakpad.tar.xz'))

  def testBundleDebugSymbols(self):
    """BundleDebugSymbols calls cbuildbot/commands with correct args."""
    # Patch service layer functions.
    self.PatchObject(os.path, 'exists', return_value=True)
    self.PatchObject(os.path, 'isdir', return_value=True)

    create_tarball_patch = self.PatchObject(
        cros_build_lib, 'CreateTarball',
        return_value=cros_build_lib.CommandResult(returncode=0, output=''))

    tar_file = sysroot.BundleDebugSymbols(self.chroot, self.sysroot,
                                          None, self.output_dir)
    create_tarball_patch.assert_called()

    # Verify response contents.
    self.assertTrue(tar_file.endswith('/output_dir/debug.tgz'))
