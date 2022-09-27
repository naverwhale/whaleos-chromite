# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Image API unittests."""

import os
from pathlib import Path

from chromite.lib import constants
from chromite.lib import chroot_lib
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import image_lib
from chromite.lib import osutils
from chromite.lib import sysroot_lib
from chromite.service import image


class BuildImageTest(cros_test_lib.RunCommandTempDirTestCase):
  """Build Image tests."""

  def setUp(self):
    osutils.Touch(os.path.join(self.tempdir,
                               image.PARALLEL_EMERGE_STATUS_FILE_NAME))
    self.PatchObject(osutils.TempDir, '__enter__', return_value=self.tempdir)

  def testInsideChrootCommand(self):
    """Test the build_image command when called from inside the chroot."""
    self.PatchObject(cros_build_lib, 'IsInsideChroot', return_value=True)
    image.Build('board', [constants.IMAGE_TYPE_BASE])
    self.assertCommandContains(
        [os.path.join(constants.CROSUTILS_DIR, 'build_image')])

  def testOutsideChrootCommand(self):
    """Test the build_image command when called from outside the chroot."""
    self.PatchObject(cros_build_lib, 'IsInsideChroot', return_value=False)
    image.Build('board', [constants.IMAGE_TYPE_BASE])
    self.assertCommandContains(['./build_image'])

  def testBuildBoardHandling(self):
    """Test the argument handling."""
    # No board should raise an error.
    with self.assertRaises(image.InvalidArgumentError):
      image.Build(None, [constants.IMAGE_TYPE_BASE])

    with self.assertRaises(image.InvalidArgumentError):
      image.Build('', [constants.IMAGE_TYPE_BASE])

    # Should be using the passed board.
    image.Build('board', [constants.IMAGE_TYPE_BASE])
    self.assertCommandContains(['--board', 'board'])

  def testBuildImageTypes(self):
    """Test the image type handling."""
    result = image.Build('board', [])
    assert result.all_built and not result.build_run

    # Should be using the argument when passed.
    image.Build('board', [constants.IMAGE_TYPE_DEV])
    self.assertCommandContains([constants.IMAGE_TYPE_DEV])

    # Multiple should all be passed.
    multi = [constants.IMAGE_TYPE_BASE, constants.IMAGE_TYPE_DEV,
             constants.IMAGE_TYPE_TEST]
    image.Build('board', multi)
    self.assertCommandContains(multi)

    # Building RECOVERY only should cause base to be built.
    image.Build('board', [constants.IMAGE_TYPE_RECOVERY])
    self.assertCommandContains([constants.IMAGE_TYPE_BASE])


class BuildConfigTest(cros_test_lib.MockTestCase):
  """BuildConfig tests."""

  def testGetArguments(self):
    """GetArguments tests."""
    config = image.BuildConfig()
    self.assertEqual([], config.GetArguments())

    # Make sure each arg produces the correct argument individually.
    config.builder_path = 'test'
    self.assertEqual(['--builder_path', 'test'], config.GetArguments())
    config.builder_path = None

    config.disk_layout = 'disk'
    self.assertEqual(['--disk_layout', 'disk'], config.GetArguments())
    config.disk_layout = None

    config.enable_rootfs_verification = False
    self.assertEqual(['--noenable_rootfs_verification'], config.GetArguments())
    config.enable_rootfs_verification = True

    config.replace = True
    self.assertEqual(['--replace'], config.GetArguments())
    config.replace = False

    config.version = 'version'
    self.assertEqual(['--version', 'version'], config.GetArguments())
    config.version = None


class CreateVmTest(cros_test_lib.RunCommandTestCase):
  """Create VM tests."""

  def setUp(self):
    self.PatchObject(cros_build_lib, 'IsInsideChroot', return_value=True)

  def testNoBoardFails(self):
    """Should fail when not given a valid board-ish value."""
    with self.assertRaises(AssertionError):
      image.CreateVm('')

  def testBoardArgument(self):
    """Test the board argument."""
    image.CreateVm('board')
    self.assertCommandContains(['--board', 'board'])

  def testTestImage(self):
    """Test the application of the --test_image argument."""
    image.CreateVm('board', is_test=True)
    self.assertCommandContains(['--test_image'])

  def testNonTestImage(self):
    """Test the non-application of the --test_image argument."""
    image.CreateVm('board', is_test=False)
    self.assertCommandContains(['--test_image'], expected=False)

  def testDiskLayout(self):
    """Test the application of the --disk_layout argument."""
    image.CreateVm('board', disk_layout='5000PB')
    self.assertCommandContains(['--disk_layout', '5000PB'])

  def testCommandError(self):
    """Test handling of an error when running the command."""
    self.rc.SetDefaultCmdResult(returncode=1)
    with self.assertRaises(image.ImageToVmError):
      image.CreateVm('board')

  def testResultPath(self):
    """Test the path building."""
    self.PatchObject(image_lib, 'GetLatestImageLink', return_value='/tmp')
    self.assertEqual(os.path.join('/tmp', constants.VM_IMAGE_BIN),
                     image.CreateVm('board'))


class BuildRecoveryTest(cros_test_lib.RunCommandTestCase):
  """Create recovery image tests."""

  def setUp(self):
    self.PatchObject(cros_build_lib, 'IsInsideChroot', return_value=True)

  def testNoBoardFails(self):
    """Should fail when not given a valid board-ish value."""
    with self.assertRaises(image.InvalidArgumentError):
      image.BuildRecoveryImage('')

  def testBoardArgument(self):
    """Test the board argument."""
    image.BuildRecoveryImage('board')
    self.assertCommandContains(['--board', 'board'])


class ImageTestTest(cros_test_lib.RunCommandTempDirTestCase):
  """Image Test tests."""

  def setUp(self):
    """Setup the filesystem."""
    self.board = 'board'
    self.chroot_container = os.path.join(self.tempdir, 'outside')
    self.outside_result_dir = os.path.join(self.chroot_container, 'results')
    self.inside_result_dir_inside = '/inside/results_inside'
    self.inside_result_dir_outside = os.path.join(self.chroot_container,
                                                  'inside/results_inside')
    self.image_dir_inside = '/inside/build/board/latest'
    self.image_dir_outside = os.path.join(self.chroot_container,
                                          'inside/build/board/latest')

    D = cros_test_lib.Directory
    filesystem = (
        D('outside', (
            D('results', ()),
            D('inside', (
                D('results_inside', ()),
                D('build', (
                    D('board', (
                        D('latest', ('%s.bin' % constants.BASE_IMAGE_NAME,)),
                    )),
                )),
            )),
        )),
    )

    cros_test_lib.CreateOnDiskHierarchy(self.tempdir, filesystem)

  def testTestFailsInvalidArguments(self):
    """Test invalid arguments are correctly failed."""
    with self.assertRaises(image.InvalidArgumentError):
      image.Test(None, None)
    with self.assertRaises(image.InvalidArgumentError):
      image.Test('', '')
    with self.assertRaises(image.InvalidArgumentError):
      image.Test(None, self.outside_result_dir)
    with self.assertRaises(image.InvalidArgumentError):
      image.Test(self.board, None)

  def testTestInsideChrootAllProvided(self):
    """Test behavior when inside the chroot and all paths provided."""
    self.PatchObject(cros_build_lib, 'IsInsideChroot', return_value=True)
    image.Test(self.board, self.outside_result_dir,
               image_dir=self.image_dir_inside)

    # Inside chroot shouldn't need to do any path manipulations, so we should
    # see exactly what we called it with.
    self.assertCommandContains(['--board', self.board,
                                '--test_results_root', self.outside_result_dir,
                                self.image_dir_inside])

  def testTestInsideChrootNoImageDir(self):
    """Test image dir generation inside the chroot."""
    mocked_dir = '/foo/bar'
    self.PatchObject(cros_build_lib, 'IsInsideChroot', return_value=True)
    self.PatchObject(image_lib, 'GetLatestImageLink', return_value=mocked_dir)
    image.Test(self.board, self.outside_result_dir)

    self.assertCommandContains(['--board', self.board,
                                '--test_results_root', self.outside_result_dir,
                                mocked_dir])

class TestCreateFactoryImageZip(cros_test_lib.MockTempDirTestCase):
  """Unittests for create_factory_image_zip."""

  def setUp(self):
    # Create a chroot_path.
    self.chroot_path = os.path.join(self.tempdir, 'chroot_dir')
    self.chroot = chroot_lib.Chroot(path=self.chroot_path)
    self.sysroot_path = os.path.join(self.chroot_path, 'build', 'target')
    self.sysroot = sysroot_lib.Sysroot(path=self.sysroot_path)

    # Create appropriate sysroot structure.
    osutils.SafeMakedirs(self.sysroot_path)
    factory_bundle_path = self.chroot.full_path(self.sysroot.path, 'usr',
      'local','factory', 'bundle')
    osutils.SafeMakedirs(factory_bundle_path)
    osutils.Touch(os.path.join(factory_bundle_path, 'bundle_foo'))

    # Create factory shim directory.
    self.factory_shim_path = os.path.join(self.tempdir, 'factory_shim_dir')
    osutils.SafeMakedirs(self.factory_shim_path)
    osutils.Touch(os.path.join(self.factory_shim_path, 'factory_install.bin'))
    osutils.Touch(os.path.join(self.factory_shim_path, 'partition'))
    osutils.SafeMakedirs(os.path.join(self.factory_shim_path, 'netboot'))
    osutils.Touch(os.path.join(self.factory_shim_path, 'netboot', 'bar'))

    # Create output dir.
    self.output_dir = os.path.join(self.tempdir, 'output_dir')
    osutils.SafeMakedirs(self.output_dir)

  def test(self):
    """create_factory_image_zip calls cbuildbot/commands with correct args."""
    version = '1.2.3.4'
    output_file = image.create_factory_image_zip(self.chroot, self.sysroot,
      Path(self.factory_shim_path), version, self.output_dir)

    # Check that all expected files are present.
    zip_contents = cros_build_lib.run(['zipinfo', '-1', output_file],
                                      cwd=self.output_dir,  stdout=True)
    zip_files = sorted(zip_contents.output.decode('UTF-8').strip().split('\n'))
    expected_files = sorted([
      'factory_shim_dir/netboot/',
      'factory_shim_dir/netboot/bar',
      'factory_shim_dir/factory_install.bin',
      'factory_shim_dir/partition',
      'bundle_foo',
      'BUILD_VERSION',
    ])
    self.assertListEqual(zip_files, expected_files)

    # Check contents of BUILD_VERSION.
    cmd = ['unzip', '-p', output_file, 'BUILD_VERSION']
    version_file = cros_build_lib.run(cmd, cwd=self.output_dir,  stdout=True)
    self.assertEqual(version_file.output.decode('UTF-8').strip(), version)
