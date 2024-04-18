# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Image API unittests."""

import errno
import glob
import os
from pathlib import Path

from chromite.api.gen.chromiumos import signing_pb2
from chromite.lib import build_target_lib
from chromite.lib import chromeos_version
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import dlc_lib
from chromite.lib import image_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import sysroot_lib
from chromite.lib.parser import package_info
from chromite.service import image


class BuildImageTest(
    cros_test_lib.RunCommandTempDirTestCase, cros_test_lib.LoggingTestCase
):
    """Build Image tests."""

    def setUp(self):
        osutils.Touch(
            os.path.join(self.tempdir, image.PARALLEL_EMERGE_STATUS_FILE_NAME)
        )
        self.PatchObject(
            osutils.TempDir, "__enter__", return_value=self.tempdir
        )
        self.PatchObject(portage_util, "GetBoardUseFlags", return_value=[])
        self.PatchObject(
            chromeos_version,
            "VersionInfo",
            return_value=chromeos_version.VersionInfo(
                version_string="1.2.3", chrome_branch="4"
            ),
        )
        self.config = image.BuildConfig(
            build_root=self.tempdir / "build",
            output_root=self.tempdir / "output",
            replace=True,
            build_attempt=1,
        )
        (
            self.build_dir,
            self.output_dir,
            self.image_dir,
        ) = image_lib.CreateBuildDir(
            self.config.build_root,
            self.config.output_root,
            "4",
            "1.2.3",
            "board",
            "latest",
            replace=True,
            build_attempt=1,
        )
        self.MoveDir_mock = self.PatchObject(osutils, "MoveDirContents")

    def testBuildBoardHandling(self):
        """Test the argument handling."""
        # No board should raise an error.
        with self.assertRaises(image.InvalidArgumentError):
            image.Build(None, [constants.IMAGE_TYPE_BASE])

        with self.assertRaises(image.InvalidArgumentError):
            image.Build("", [constants.IMAGE_TYPE_BASE])

    def testBuildImageTypes(self):
        """Test the image type handling."""
        result = image.Build("board", [])
        assert result.all_built and not result.build_run

        # Should be using the argument when passed.
        image.Build("board", [constants.IMAGE_TYPE_DEV], config=self.config)
        self.assertCommandContains(
            [constants.IMAGE_TYPE_TO_NAME[constants.IMAGE_TYPE_DEV]]
        )

        # Multiple should all be passed.
        multi = [
            constants.IMAGE_TYPE_BASE,
            constants.IMAGE_TYPE_DEV,
            constants.IMAGE_TYPE_TEST,
        ]
        image.Build("board", multi, config=self.config)
        for x in multi:
            self.assertCommandContains([constants.IMAGE_TYPE_TO_NAME[x]])

        # Building RECOVERY only should cause base to be built.
        image.Build(
            "board", [constants.IMAGE_TYPE_RECOVERY], config=self.config
        )
        self.assertCommandContains(
            [constants.IMAGE_TYPE_TO_NAME[constants.IMAGE_TYPE_BASE]]
        )

    def testInvalidBuildImageTypes(self):
        """Test the image type handling with invalid input."""
        build_result = image.Build(
            "board", [constants.IMAGE_TYPE_BASE, constants.FACTORY_IMAGE_BIN]
        )
        self.assertEqual(build_result.return_code, errno.EINVAL)

    def testClearShadowLocks(self):
        """Test that stale shadow-utils locks are cleared."""
        clear_shadow_locks_mock = self.PatchObject(
            cros_build_lib, "ClearShadowLocks"
        )
        test_board = "board"

        image.Build(test_board, [constants.IMAGE_TYPE_BASE])

        clear_shadow_locks_mock.assert_called_once_with(
            build_target_lib.get_default_sysroot_path(test_board)
        )

    def testBuildDir(self):
        """Test the case if build directory exists."""
        config = image.BuildConfig(
            build_root=self.tempdir / "build",
            output_root=self.tempdir / "build",
        )
        build_result = image.Build(
            "board", [constants.IMAGE_TYPE_DEV], config=config
        )
        build_result = image.Build(
            "board", [constants.IMAGE_TYPE_DEV], config=config
        )
        self.assertEqual(build_result.return_code, errno.EEXIST)

    def testDlcCommand(self):
        """Test if DLC installation is called."""
        image.Build("board", [constants.IMAGE_TYPE_DEV], config=self.config)
        self.assertCommandContains(
            [
                "build_dlc",
                "--sysroot",
                build_target_lib.get_default_sysroot_path("board"),
                "--install-root-dir",
                self.output_dir / "dlc",
                "--board",
                "board",
            ]
        )

    def testMoveDir(self):
        """Test if MoveDirContents is called."""
        image.Build("board", [constants.IMAGE_TYPE_DEV], config=self.config)
        self.MoveDir_mock.assert_called_once_with(
            self.build_dir,
            self.output_dir,
            remove_from_dir=True,
            allow_nonempty=True,
        )

    def testSummary(self):
        """Test if summary text is printed correctly."""
        base_image_path = os.path.relpath(
            self.output_dir / constants.BASE_IMAGE_BIN
        )
        dev_image_path = os.path.relpath(
            self.output_dir / constants.DEV_IMAGE_BIN
        )
        test_image_path = os.path.relpath(
            self.output_dir / constants.TEST_IMAGE_BIN
        )

        with cros_test_lib.LoggingCapturer() as logs:
            image.Build(
                "board",
                [
                    constants.IMAGE_TYPE_BASE,
                    constants.IMAGE_TYPE_DEV,
                    constants.IMAGE_TYPE_TEST,
                ],
                config=self.config,
            )
            # pylint: disable=protected-access
            # Base Image summary text.
            self.AssertLogsContain(
                logs,
                (
                    f"{image._IMAGE_TYPE_DESCRIPTION[constants.BASE_IMAGE_BIN]}"
                    f" image created as {constants.BASE_IMAGE_BIN}"
                ),
            )
            self.AssertLogsContain(logs, f"cros flash usb:// {base_image_path}")
            self.AssertLogsContain(
                logs, f"cros flash ${{DUT_IP}} {base_image_path}"
            )
            self.AssertLogsContain(
                logs,
                f"cros vm --start --image-path={base_image_path} --board=board",
                inverted=True,
            )
            # Dev Image summary text.
            self.AssertLogsContain(
                logs,
                (
                    f"{image._IMAGE_TYPE_DESCRIPTION[constants.DEV_IMAGE_BIN]} "
                    f"image created as {constants.DEV_IMAGE_BIN}"
                ),
            )
            self.AssertLogsContain(logs, f"cros flash usb:// {dev_image_path}")
            self.AssertLogsContain(
                logs, f"cros flash ${{DUT_IP}} {dev_image_path}"
            )
            self.AssertLogsContain(
                logs,
                f"cros vm --start --image-path={dev_image_path} --board=board",
            )
            # Test Image summary text.
            self.AssertLogsContain(
                logs,
                (
                    f"{image._IMAGE_TYPE_DESCRIPTION[constants.TEST_IMAGE_BIN]}"
                    f" image created as {constants.TEST_IMAGE_BIN}"
                ),
            )
            self.AssertLogsContain(logs, f"cros flash usb:// {test_image_path}")
            self.AssertLogsContain(
                logs, f"cros flash ${{DUT_IP}} {test_image_path}"
            )
            self.AssertLogsContain(
                logs,
                f"cros vm --start --image-path={test_image_path} --board=board",
            )


class BuildImageCommandTest(cros_test_lib.MockTestCase):
    """BuildConfig tests."""

    def testBuildImageCommand(self):
        """GetArguments tests."""
        cmd = image.GetBuildImageCommand(
            image.BuildConfig(), [constants.BASE_IMAGE_BIN], "testBoard"
        )
        expected = {
            constants.CROSUTILS_DIR / "build_image.sh",
            "--script-is-run-only-by-chromite-and-not-users",
            "--board",
            "testBoard",
        }
        self.assertTrue(expected.issubset(set(cmd)))

        # Make sure each arg produces the correct argument individually.
        cmd = image.GetBuildImageCommand(
            image.BuildConfig(builder_path="test_builder_path"),
            [constants.BASE_IMAGE_BIN],
            "testBoard",
        )
        expected = {
            "--builder_path",
            "testBoard",
        }
        self.assertTrue(expected.issubset(set(cmd)))

        # disk_layout
        cmd = image.GetBuildImageCommand(
            image.BuildConfig(disk_layout="disk"),
            [constants.BASE_IMAGE_BIN],
            "testBoard",
        )
        expected = {
            "--disk_layout",
            "disk",
        }
        self.assertTrue(expected.issubset(set(cmd)))

        # enable_rootfs_verification
        self.assertIn(
            "--noenable_rootfs_verification",
            image.GetBuildImageCommand(
                image.BuildConfig(enable_rootfs_verification=False),
                [constants.BASE_IMAGE_BIN],
                "testBoard",
            ),
        )

        # adjust_partition
        cmd = image.GetBuildImageCommand(
            image.BuildConfig(adjust_partition="ROOT-A:+1G"),
            [constants.BASE_IMAGE_BIN],
            "testBoard",
        )
        expected = {
            "--adjust_part",
            "ROOT-A:+1G",
        }
        self.assertTrue(expected.issubset(set(cmd)))

        # boot_args
        config = image.BuildConfig(boot_args="initrd")
        cmd = image.GetBuildImageCommand(
            config, [constants.BASE_IMAGE_BIN], "testBoard"
        )
        expected = {
            "--boot_args",
            "initrd",
        }
        self.assertTrue(expected.issubset(set(cmd)))

        cmd = image.GetBuildImageCommand(
            config, [constants.FACTORY_IMAGE_BIN], "testBoard"
        )
        expected = {
            "--boot_args",
            "initrd cros_factory_install",
        }
        self.assertTrue(expected.issubset(set(cmd)))

        # enable_serial
        cmd = image.GetBuildImageCommand(
            image.BuildConfig(enable_serial="ttyS1"),
            [constants.BASE_IMAGE_BIN],
            "testBoard",
        )
        expected = {
            "--enable_serial",
            "ttyS1",
        }
        self.assertTrue(expected.issubset(set(cmd)))

        # kernel_loglevel
        cmd = image.GetBuildImageCommand(
            image.BuildConfig(kernel_loglevel=4),
            [constants.BASE_IMAGE_BIN],
            "testBoard",
        )
        expected = {
            "--loglevel",
            "4",
        }
        self.assertTrue(expected.issubset(set(cmd)))

        # jobs
        cmd = image.GetBuildImageCommand(
            image.BuildConfig(jobs=40), [constants.BASE_IMAGE_BIN], "testBoard"
        )
        expected = {
            "--jobs",
            "40",
        }
        self.assertTrue(expected.issubset(set(cmd)))

        # image_name
        config = image.BuildConfig()
        for image_name in constants.IMAGE_NAME_TO_TYPE.keys():
            self.assertIn(
                image_name,
                image.GetBuildImageCommand(config, [image_name], "testBoard"),
            )


class CreateVmTest(cros_test_lib.RunCommandTestCase):
    """Create VM tests."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)

    def testNoBoardFails(self):
        """Should fail when not given a valid board-ish value."""
        with self.assertRaises(AssertionError):
            image.CreateVm("")

    def testBoardArgument(self):
        """Test the board argument."""
        image.CreateVm("board")
        self.assertCommandContains(["--board", "board"])

    def testTestImage(self):
        """Test the application of the --test_image argument."""
        image.CreateVm("board", is_test=True)
        self.assertCommandContains(["--test_image"])

    def testNonTestImage(self):
        """Test the non-application of the --test_image argument."""
        image.CreateVm("board", is_test=False)
        self.assertCommandContains(["--test_image"], expected=False)

    def testDiskLayout(self):
        """Test the application of the --disk_layout argument."""
        image.CreateVm("board", disk_layout="5000PB")
        self.assertCommandContains(["--disk_layout", "5000PB"])

    def testCommandError(self):
        """Test handling of an error when running the command."""
        self.rc.SetDefaultCmdResult(returncode=1)
        with self.assertRaises(image.ImageToVmError):
            image.CreateVm("board")

    def testResultPath(self):
        """Test the path building."""
        self.PatchObject(image_lib, "GetLatestImageLink", return_value="/tmp")
        self.assertEqual(
            os.path.join("/tmp", constants.VM_IMAGE_BIN),
            image.CreateVm("board"),
        )


class CreateGuestVmTest(cros_test_lib.RunCommandTestCase):
    """Create guest VM tests."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)

    def testNoImageDirFails(self):
        """Should fail when not given a valid image directory value."""
        with self.assertRaises(AssertionError):
            image.CreateGuestVm(image_dir="")

    def testBaseImage(self):
        """Test finding the base-image variant."""
        image.CreateGuestVm(image_dir="/tmp")
        self.assertCommandContains(
            [os.path.join("/tmp", constants.BASE_IMAGE_BIN)]
        )

    def testTestImage(self):
        """Test finding the test-image variant."""
        image.CreateGuestVm(image_dir="/tmp", is_test=True)
        self.assertCommandContains(
            [os.path.join("/tmp", constants.TEST_IMAGE_BIN)]
        )

    def testCommandError(self):
        """Test handling of an error when running the command."""
        self.rc.SetDefaultCmdResult(returncode=1)
        with self.assertRaises(image.ImageToVmError):
            image.CreateGuestVm(image_dir="/tmp")

    def testResultPath(self):
        """Test the path building."""
        self.assertEqual(
            os.path.join("/tmp", constants.BASE_GUEST_VM_DIR),
            image.CreateGuestVm(image_dir="/tmp"),
        )


class CopyBaseToRecoveryTest(cros_test_lib.MockTempDirTestCase):
    """Tests the CopyBaseToRecovery method."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)
        self.PatchObject(Path, "exists", return_value=True)
        self.base_image = self.tempdir / constants.BASE_IMAGE_BIN
        self.recovery_image = self.tempdir / constants.RECOVERY_IMAGE_BIN

    def testCopyRecoveryImage(self):
        self.base_image.touch()
        result = image.CopyBaseToRecovery("board", self.base_image)

        self.assertEqual(result.return_code, 0)
        self.assertEqual(
            result.images[constants.IMAGE_TYPE_RECOVERY], self.recovery_image
        )
        self.assertExists(self.recovery_image)

    def testCopyRecoveryImageInvalid(self):
        result = image.CopyBaseToRecovery("board", self.base_image)

        self.assertNotEqual(result.return_code, 0)
        self.assertNotExists(self.recovery_image)


class BuildRecoveryTest(cros_test_lib.RunCommandTestCase):
    """Create recovery image tests."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)

    def testNoBoardFails(self):
        """Should fail when not given a valid board-ish value."""
        with self.assertRaises(image.InvalidArgumentError):
            image.BuildRecoveryImage("")

    def testBoardArgument(self):
        """Test the board argument."""
        image.BuildRecoveryImage("board")
        self.assertCommandContains(["--board", "board"])


class ImageTestTest(cros_test_lib.RunCommandTempDirTestCase):
    """Image Test tests."""

    def setUp(self):
        """Setup the filesystem."""
        self.board = "board"
        self.chroot_container = os.path.join(self.tempdir, "outside")
        self.outside_result_dir = os.path.join(self.chroot_container, "results")
        self.inside_result_dir_inside = "/inside/results_inside"
        self.inside_result_dir_outside = os.path.join(
            self.chroot_container, "inside/results_inside"
        )
        self.image_dir_inside = "/inside/build/board/latest"
        self.image_dir_outside = os.path.join(
            self.chroot_container, "inside/build/board/latest"
        )

        D = cros_test_lib.Directory
        filesystem = (
            D(
                "outside",
                (
                    D("results", ()),
                    D(
                        "inside",
                        (
                            D("results_inside", ()),
                            D(
                                "build",
                                (
                                    D(
                                        "board",
                                        (
                                            D(
                                                "latest",
                                                (
                                                    "%s.bin"
                                                    % constants.BASE_IMAGE_NAME,
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )

        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, filesystem)

    def testTestFailsInvalidArguments(self):
        """Test invalid arguments are correctly failed."""
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        with self.assertRaises(image.InvalidArgumentError):
            image.Test(None, None)
        with self.assertRaises(image.InvalidArgumentError):
            image.Test("", "")
        with self.assertRaises(image.InvalidArgumentError):
            image.Test(None, self.outside_result_dir)
        with self.assertRaises(image.InvalidArgumentError):
            image.Test(self.board, None)
        with self.assertRaises(image.ChrootError):
            image.Test(self.board, self.outside_result_dir)

    def testTestInsideChrootAllProvided(self):
        """Test behavior when inside the chroot and all paths provided."""
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)
        image.Test(
            self.board, self.outside_result_dir, image_dir=self.image_dir_inside
        )

        # Inside chroot shouldn't need to do any path manipulations, so we
        # should see exactly what we called it with.
        self.assertCommandContains(
            [
                "--board",
                self.board,
                "--test_results_root",
                self.outside_result_dir,
                self.image_dir_inside,
            ]
        )

    def testTestInsideChrootNoImageDir(self):
        """Test image dir generation inside the chroot."""
        mocked_dir = "/foo/bar"
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)
        self.PatchObject(
            image_lib, "GetLatestImageLink", return_value=mocked_dir
        )
        image.Test(self.board, self.outside_result_dir)

        self.assertCommandContains(
            [
                "--board",
                self.board,
                "--test_results_root",
                self.outside_result_dir,
                mocked_dir,
            ]
        )


class TestCreateFactoryImageZip(cros_test_lib.MockTempDirTestCase):
    """Unittests for create_factory_image_zip."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        # Create a chroot_path.
        self.chroot_path = os.path.join(self.tempdir, "chroot_dir")
        self.out_path = self.tempdir / "out_dir"
        self.chroot = chroot_lib.Chroot(
            path=self.chroot_path, out_path=self.out_path
        )
        self.sysroot_path = os.path.join("build", "target")
        self.sysroot = sysroot_lib.Sysroot(path=self.sysroot_path)

        # Create appropriate sysroot structure.
        osutils.SafeMakedirs(self.chroot.full_path(self.sysroot_path))
        factory_bundle_path = self.chroot.full_path(
            self.sysroot.path, "usr", "local", "factory", "bundle"
        )
        osutils.SafeMakedirs(factory_bundle_path)
        osutils.Touch(os.path.join(factory_bundle_path, "bundle_foo"))

        # Create factory shim directory.
        self.factory_shim_path = os.path.join(self.tempdir, "factory_shim_dir")
        osutils.SafeMakedirs(self.factory_shim_path)
        osutils.Touch(
            os.path.join(self.factory_shim_path, "factory_install.bin")
        )
        osutils.Touch(os.path.join(self.factory_shim_path, "partition"))
        osutils.SafeMakedirs(os.path.join(self.factory_shim_path, "netboot"))
        osutils.Touch(os.path.join(self.factory_shim_path, "netboot", "bar"))

        # Create output dir.
        self.output_dir = os.path.join(self.tempdir, "output_dir")
        osutils.SafeMakedirs(self.output_dir)

    def test(self):
        """create_factory_image_zip calls cbuildbot/commands correctly."""
        version = "1.2.3.4"
        output_file = image.create_factory_image_zip(
            self.chroot,
            self.sysroot,
            Path(self.factory_shim_path),
            version,
            self.output_dir,
        )

        # Check that all expected files are present.
        zip_contents = cros_build_lib.run(
            ["zipinfo", "-1", output_file], cwd=self.output_dir, stdout=True
        )
        zip_files = sorted(
            zip_contents.stdout.decode("UTF-8").strip().split("\n")
        )
        expected_files = sorted(
            [
                "factory_shim_dir/netboot/",
                "factory_shim_dir/netboot/bar",
                "factory_shim_dir/factory_install.bin",
                "factory_shim_dir/partition",
                "bundle_foo",
                "BUILD_VERSION",
            ]
        )
        self.assertListEqual(zip_files, expected_files)

        # Check contents of BUILD_VERSION.
        cmd = ["unzip", "-p", output_file, "BUILD_VERSION"]
        version_file = cros_build_lib.run(cmd, cwd=self.output_dir, stdout=True)
        self.assertEqual(version_file.stdout.decode("UTF-8").strip(), version)


class TestCreateStrippedPackagesTar(cros_test_lib.MockTempDirTestCase):
    """Unittests for create_stripped_packages_tar."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)
        # Create a chroot_path.
        self.chroot_path = os.path.join(self.tempdir, "chroot_dir")
        self.out_path = self.tempdir / "out_dir"
        self.chroot = chroot_lib.Chroot(
            path=self.chroot_path, out_path=self.out_path
        )

        # Create build target.
        self.build_target = build_target_lib.BuildTarget(
            "target", build_root="/build/target"
        )

        # Create output dir.
        self.output_dir = os.path.join(self.tempdir, "output_dir")
        osutils.SafeMakedirs(self.output_dir)

    def test(self):
        """Test generation of stripped package tarball using globs."""
        self.PatchObject(
            portage_util,
            "FindPackageNameMatches",
            side_effect=[
                [package_info.SplitCPV("chromeos-base/chrome-1-r0")],
                [
                    package_info.SplitCPV("sys-kernel/kernel-1-r0"),
                    package_info.SplitCPV("sys-kernel/kernel-2-r0"),
                ],
            ],
        )
        # Drop "stripped packages".
        pkg_dir = self.chroot.full_path(
            self.build_target.root, "stripped-packages"
        )
        osutils.Touch(
            os.path.join(pkg_dir, "chromeos-base", "chrome-1-r0.tbz2"),
            makedirs=True,
        )
        sys_kernel = os.path.join(pkg_dir, "sys-kernel")
        osutils.Touch(
            os.path.join(sys_kernel, "kernel-1-r0.tbz2"), makedirs=True
        )
        osutils.Touch(
            os.path.join(sys_kernel, "kernel-1-r01.tbz2"), makedirs=True
        )
        osutils.Touch(
            os.path.join(sys_kernel, "kernel-2-r0.tbz1"), makedirs=True
        )
        osutils.Touch(
            os.path.join(sys_kernel, "kernel-2-r0.tbz2"), makedirs=True
        )
        stripped_files_list = [
            os.path.join(
                "stripped-packages", "chromeos-base", "chrome-1-r0.tbz2"
            ),
            os.path.join("stripped-packages", "sys-kernel", "kernel-1-r0.tbz2"),
            os.path.join("stripped-packages", "sys-kernel", "kernel-2-r0.tbz2"),
        ]

        tar_mock = self.PatchObject(cros_build_lib, "CreateTarball")
        rc = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc.SetDefaultCmdResult()
        image.create_stripped_packages_tar(
            self.chroot, self.build_target, self.output_dir
        )
        tar_mock.assert_called_once_with(
            tarball_path=os.path.join(self.output_dir, "stripped-packages.tar"),
            cwd=self.chroot.full_path(self.build_target.root),
            compression=cros_build_lib.CompressionType.NONE,
            chroot=self.chroot,
            inputs=stripped_files_list,
        )


class TestCreateNetbootKernel(cros_test_lib.MockTempDirTestCase):
    """Unittests for create_netboot_kernel."""

    def test(self):
        """Test netboot kernel creation."""
        board = "atlas"
        image_dir = "/path/to/factory_install/"

        rc = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc.SetDefaultCmdResult()

        image.create_netboot_kernel(board, image_dir)
        rc.assertCommandContains(
            [
                "./make_netboot.sh",
                f"--board={board}",
                f"--image_dir={image_dir}",
            ]
        )


class TestCreateImageScriptsArchive(cros_test_lib.MockTempDirTestCase):
    """Unittests for create_image_scripts_archive."""

    def test(self):
        """Test image scripts archive creation."""
        build_target = build_target_lib.BuildTarget(
            "target",
        )
        output_dir = "/path/to/output/dir/"
        image_dir = self.tempdir

        self.PatchObject(
            image_lib, "GetLatestImageLink", return_value=str(image_dir)
        )

        glob_mock = self.PatchObject(
            glob,
            "glob",
            return_value=[
                os.path.join(image_dir, "bar.sh"),
                os.path.join(image_dir, "baz.sh"),
            ],
        )

        tar_mock = self.PatchObject(cros_build_lib, "CreateTarball")
        image.create_image_scripts_archive(build_target, output_dir)
        glob_mock.assert_called_once()
        tar_mock.assert_called_once_with(
            os.path.join(output_dir, "image_scripts.tar.xz"),
            str(image_dir),
            inputs=["bar.sh", "baz.sh"],
        )


class TestGenerateDlcArtifactsMetadataList(cros_test_lib.MockTempDirTestCase):
    """Unittests for generate_dlc_artifacts_metadata_list."""

    DLC_1_ID = "dlc-1-id"
    DLC_1_IMAGELOADER_JSON_DATA = """{
  "critical-update": false,
  "days-to-purge": 0,
  "description": "",
  "factory-install": false,
  "fs-type": "squashfs",
  "id": "",
  "image-sha256-hash": "88d54cb6b5bba15a71ffda3ca75446eb453bf7fe393e3595d3bc52beb3b61711",
  "image-type": "dlc",
  "is-removable": true,
  "loadpin-verity-digest": false,
  "manifest-version": 1,
  "mount-file-required": false,
  "name": "",
  "package": "package",
  "powerwash-safe": false,
  "pre-allocated-size": "8388608",
  "preload-allowed": false,
  "reserved": false,
  "scaled": true,
  "size": "4243456",
  "table-sha256-hash": "5dafa30c89cef2f7f78c6b73117e234acbb9919ec3a5250d9c0a966cac09adae",
  "use-logical-volume": true,
  "used-by": "",
  "version": "1.0.0"
}"""

    DLC_2_ID = "dlc-2-id"
    DLC_2_IMAGELOADER_JSON_DATA = """{
  "critical-update": false,
  "days-to-purge": 0,
  "description": "",
  "factory-install": false,
  "fs-type": "squashfs",
  "id": "",
  "image-sha256-hash": "123400000000000000000000000000000000000000000000000000000000beef",
  "image-type": "dlc",
  "is-removable": true,
  "loadpin-verity-digest": false,
  "manifest-version": 1,
  "mount-file-required": false,
  "name": "",
  "package": "package",
  "powerwash-safe": false,
  "pre-allocated-size": "8388608",
  "preload-allowed": false,
  "reserved": false,
  "scaled": true,
  "size": "4243456",
  "table-sha256-hash": "000000000000000000000000000000000000000000000000000000000000beef",
  "use-logical-volume": true,
  "used-by": "",
  "version": "1.0.0"
}"""

    def createDlcArtifacts(
        self, dlc_id: str, uri_prefix_data: str, imageloader_json_data: str
    ):
        """Creates the DLC artifacts under temporary build root.

        Args:
            dlc_id: The DLC ID.
            uri_prefix_data: The test URI prefix path data.
            imageloader_json_data: The test imageloader JSON data.
        """
        artifacts_meta_dir = os.path.join(
            self.tempdir, dlc_lib.DLC_BUILD_DIR_ARTIFACTS_META
        )
        osutils.WriteFile(
            os.path.join(
                artifacts_meta_dir,
                dlc_id,
                dlc_lib.DLC_PACKAGE,
                dlc_lib.URI_PREFIX,
            ),
            uri_prefix_data,
            makedirs=True,
        )
        osutils.WriteFile(
            os.path.join(
                artifacts_meta_dir,
                dlc_id,
                dlc_lib.DLC_PACKAGE,
                dlc_lib.IMAGELOADER_JSON,
            ),
            imageloader_json_data,
        )

    def testGenerateDlcArtifactsMetadataList(self):
        self.createDlcArtifacts(
            TestGenerateDlcArtifactsMetadataList.DLC_1_ID,
            "gs://some/uri/prefix/for/dlc-1",
            TestGenerateDlcArtifactsMetadataList.DLC_1_IMAGELOADER_JSON_DATA,
        )
        self.createDlcArtifacts(
            TestGenerateDlcArtifactsMetadataList.DLC_2_ID,
            "gs://some/uri/prefix/for/dlc-2",
            TestGenerateDlcArtifactsMetadataList.DLC_2_IMAGELOADER_JSON_DATA,
        )
        sort_fnc = lambda x: x.image_hash
        self.assertEqual(
            sorted(
                image.generate_dlc_artifacts_metadata_list(self.tempdir),
                key=sort_fnc,
            ),
            sorted(
                [
                    # pylint: disable=line-too-long
                    image.DlcArtifactsMetadata(
                        image_hash="88d54cb6b5bba15a71ffda3ca75446eb453bf7fe393e3595d3bc52beb3b61711",
                        image_name=dlc_lib.DLC_IMAGE,
                        uri_path="gs://some/uri/prefix/for/dlc-1",
                        identifier=TestGenerateDlcArtifactsMetadataList.DLC_1_ID,
                    ),
                    # pylint: disable=line-too-long
                    image.DlcArtifactsMetadata(
                        image_hash="123400000000000000000000000000000000000000000000000000000000beef",
                        image_name=dlc_lib.DLC_IMAGE,
                        uri_path="gs://some/uri/prefix/for/dlc-2",
                        identifier=TestGenerateDlcArtifactsMetadataList.DLC_2_ID,
                    ),
                ],
                key=sort_fnc,
            ),
        )

    def testGenerateDlcArtifactsMetadataListExcludesMissingUriPrefixFile(self):
        self.createDlcArtifacts(
            TestGenerateDlcArtifactsMetadataList.DLC_1_ID,
            "gs://some/uri/prefix/for/dlc-1",
            TestGenerateDlcArtifactsMetadataList.DLC_1_IMAGELOADER_JSON_DATA,
        )
        os.path.join(self.tempdir, dlc_lib.DLC_BUILD_DIR_ARTIFACTS_META)
        osutils.SafeUnlink(
            os.path.join(
                self.tempdir,
                dlc_lib.DLC_BUILD_DIR_ARTIFACTS_META,
                TestGenerateDlcArtifactsMetadataList.DLC_1_ID,
                dlc_lib.DLC_PACKAGE,
                dlc_lib.URI_PREFIX,
            )
        )
        self.assertEqual(
            image.generate_dlc_artifacts_metadata_list(self.tempdir),
            [],
        )

    def testGenerateDlcArtifactsMetadataListExcludesMissingImageloaderJsonFile(
        self,
    ):
        self.createDlcArtifacts(
            TestGenerateDlcArtifactsMetadataList.DLC_1_ID,
            "gs://some/uri/prefix/for/dlc-1",
            TestGenerateDlcArtifactsMetadataList.DLC_1_IMAGELOADER_JSON_DATA,
        )
        os.path.join(self.tempdir, dlc_lib.DLC_BUILD_DIR_ARTIFACTS_META)
        osutils.SafeUnlink(
            os.path.join(
                self.tempdir,
                dlc_lib.DLC_BUILD_DIR_ARTIFACTS_META,
                TestGenerateDlcArtifactsMetadataList.DLC_1_ID,
                dlc_lib.DLC_PACKAGE,
                dlc_lib.IMAGELOADER_JSON,
            )
        )
        self.assertEqual(
            image.generate_dlc_artifacts_metadata_list(self.tempdir),
            [],
        )

    def testGenerateDlcArtifactsMetadataListExcludesMalformedDlcs(self):
        self.createDlcArtifacts(
            TestGenerateDlcArtifactsMetadataList.DLC_1_ID,
            "gs://some/uri/prefix/for/dlc-1",
            "",
        )
        self.createDlcArtifacts(
            TestGenerateDlcArtifactsMetadataList.DLC_2_ID,
            "gs://some/uri/prefix/for/dlc-2",
            TestGenerateDlcArtifactsMetadataList.DLC_2_IMAGELOADER_JSON_DATA,
        )
        self.assertEqual(
            image.generate_dlc_artifacts_metadata_list(self.tempdir),
            [
                # pylint: disable=line-too-long
                image.DlcArtifactsMetadata(
                    image_hash="123400000000000000000000000000000000000000000000000000000000beef",
                    image_name=dlc_lib.DLC_IMAGE,
                    uri_path="gs://some/uri/prefix/for/dlc-2",
                    identifier=TestGenerateDlcArtifactsMetadataList.DLC_2_ID,
                ),
            ],
        )

    def testGenerateDlcArtifactsMetadataListEmptyArtifactsMetadataDirectory(
        self,
    ):
        self.assertEqual(
            image.generate_dlc_artifacts_metadata_list(self.tempdir), []
        )


class TestCopyDlcImages(cros_test_lib.MockTempDirTestCase):
    """Unittests for copy_dlc_image."""

    def touchDlc(
        self,
        dlc_id: str,
        dlc_package: str = dlc_lib.DLC_PACKAGE,
        dlc_artifact: str = dlc_lib.DLC_IMAGE,
        dlc_build_dir: str = dlc_lib.DLC_BUILD_DIR,
        metadata: bool = True,
    ):
        """Touches the DLC artifact with the given args.

        Args:
            dlc_id: The DLC ID.
            dlc_package: The DLC package.
            dlc_artifact: The DLC artifact.
            dlc_build_dir: The DLC build dir.
            metadata: True to create metadata.
        """
        build_dir = os.path.join(self.tempdir, dlc_build_dir)
        osutils.Touch(
            os.path.join(build_dir, dlc_id, dlc_package, dlc_artifact),
            makedirs=True,
        )
        if metadata:
            osutils.Touch(
                os.path.join(
                    build_dir,
                    dlc_id,
                    dlc_package,
                    dlc_lib.DLC_TMP_META_DIR,
                    dlc_lib.IMAGELOADER_JSON,
                ),
                makedirs=True,
            )

    def testOnlyLegacyDLCs(self):
        """Test copy of DLC artifacts for legacy."""
        good_dlc_ids = ("dlc-a", "dlc-b")
        for dlc_id in good_dlc_ids:
            self.touchDlc(dlc_id)
            self.touchDlc(dlc_id, dlc_artifact="foobar-file")

        dlc_bad_id = "dlc_bad_id"
        self.touchDlc(dlc_bad_id)

        dlc_bad_package = "dlc-bad-package"
        self.touchDlc(dlc_bad_package, dlc_package="packit")

        dlc_bad_artifact = "dlc-bad-artifact"
        self.touchDlc(dlc_bad_artifact, dlc_artifact="some-file")

        dlc_bad_artifact_with_dir = "dlc-bad-artifact-with-dir"
        self.touchDlc(
            dlc_bad_artifact_with_dir, dlc_artifact="some-dir/some-file"
        )

        output_path = os.path.join(self.tempdir, "_output")
        dst_paths = image.copy_dlc_image(self.tempdir, output_path)
        self.assertEqual(len(dst_paths), 2)
        # pylint: disable=unsubscriptable-object
        path = dst_paths[0]
        self.assertEqual(sorted(os.listdir(path)), list(good_dlc_ids))
        self.assertEqual(os.path.basename(path), dlc_lib.DLC_DIR)

        for dlc_id in good_dlc_ids:
            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        path, dlc_id, dlc_lib.DLC_PACKAGE, dlc_lib.DLC_IMAGE
                    )
                )
            )
            self.assertFalse(
                os.path.exists(
                    os.path.join(
                        path, dlc_id, dlc_lib.DLC_PACKAGE, "foobar-file"
                    )
                )
            )
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    path, dlc_bad_id, dlc_lib.DLC_PACKAGE, dlc_lib.DLC_IMAGE
                )
            )
        )
        self.assertFalse(
            os.path.exists(
                os.path.join(path, dlc_bad_package, "packit", dlc_lib.DLC_IMAGE)
            )
        )
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    path, dlc_bad_artifact, dlc_lib.DLC_PACKAGE, "some-file"
                )
            )
        )
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    path,
                    dlc_bad_artifact_with_dir,
                    dlc_lib.DLC_PACKAGE,
                    "some-dir/some-file",
                )
            )
        )

    def testOnlyScaledDLCs(self):
        """Test copy of DLC artifacts for only scaled."""
        good_dlc_ids = ("dlc-a", "dlc-b")
        for dlc_id in good_dlc_ids:
            self.touchDlc(dlc_id, dlc_build_dir=dlc_lib.DLC_BUILD_DIR_SCALED)

        dlc_bad_id = "dlc_bad_id"
        self.touchDlc(dlc_bad_id, dlc_build_dir=dlc_lib.DLC_BUILD_DIR_SCALED)

        dlc_bad_package = "dlc-bad-package"
        self.touchDlc(
            dlc_bad_package,
            dlc_package="packit",
            dlc_build_dir=dlc_lib.DLC_BUILD_DIR_SCALED,
        )

        dlc_bad_artifact = "dlc-bad-artifact"
        self.touchDlc(
            dlc_bad_artifact,
            dlc_artifact="some-file",
            dlc_build_dir=dlc_lib.DLC_BUILD_DIR_SCALED,
        )

        dlc_bad_artifact_with_dir = "dlc-bad-artifact-with-dir"
        self.touchDlc(
            dlc_bad_artifact_with_dir,
            dlc_artifact="some-dir/some-file",
            dlc_build_dir=dlc_lib.DLC_BUILD_DIR_SCALED,
        )

        dst_paths = image.copy_dlc_image(self.tempdir, self.tempdir)
        self.assertEqual(len(dst_paths), 2)
        # pylint: disable=unsubscriptable-object
        path = dst_paths[0]
        self.assertEqual(sorted(os.listdir(path)), list(good_dlc_ids))
        self.assertEqual(os.path.basename(path), dlc_lib.DLC_DIR_SCALED)

        for dlc_id in good_dlc_ids:
            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        path, dlc_id, dlc_lib.DLC_PACKAGE, dlc_lib.DLC_IMAGE
                    )
                )
            )
            self.assertFalse(
                os.path.exists(
                    os.path.join(
                        path, dlc_id, dlc_lib.DLC_PACKAGE, "foobar-file"
                    )
                )
            )
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    path, dlc_bad_id, dlc_lib.DLC_PACKAGE, dlc_lib.DLC_IMAGE
                )
            )
        )
        self.assertFalse(
            os.path.exists(
                os.path.join(path, dlc_bad_package, "packit", dlc_lib.DLC_IMAGE)
            )
        )
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    path, dlc_bad_artifact, dlc_lib.DLC_PACKAGE, "some-file"
                )
            )
        )
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    path,
                    dlc_bad_artifact_with_dir,
                    dlc_lib.DLC_PACKAGE,
                    "some-dir/some-file",
                )
            )
        )

    def testAllDLCs(self):
        """Test copy of DLC artifacts of all types."""
        good_dlc_ids = ("dlc-a", "dlc-b")
        for dlc_id in good_dlc_ids:
            self.touchDlc(dlc_id)
            self.touchDlc(dlc_id, dlc_build_dir=dlc_lib.DLC_BUILD_DIR_SCALED)

        dlc_bad_id = "dlc_bad_id"
        self.touchDlc(dlc_bad_id)
        self.touchDlc(dlc_bad_id, dlc_build_dir=dlc_lib.DLC_BUILD_DIR_SCALED)

        dlc_bad_package = "dlc-bad-package"
        self.touchDlc(dlc_bad_package, dlc_package="packit")
        self.touchDlc(
            dlc_bad_package,
            dlc_package="packit",
            dlc_build_dir=dlc_lib.DLC_BUILD_DIR_SCALED,
        )

        dlc_bad_artifact = "dlc-bad-artifact"
        self.touchDlc(dlc_bad_artifact, dlc_artifact="some-file")
        self.touchDlc(
            dlc_bad_artifact,
            dlc_artifact="some-file",
            dlc_build_dir=dlc_lib.DLC_BUILD_DIR_SCALED,
        )

        dlc_bad_artifact_with_dir = "dlc-bad-artifact-with-dir"
        self.touchDlc(
            dlc_bad_artifact_with_dir, dlc_artifact="some-dir/some-file"
        )
        self.touchDlc(
            dlc_bad_artifact_with_dir,
            dlc_artifact="some-dir/some-file",
            dlc_build_dir=dlc_lib.DLC_BUILD_DIR_SCALED,
        )

        dst_paths = image.copy_dlc_image(self.tempdir, self.tempdir)
        self.assertEqual(len(dst_paths), 4)
        # pylint: disable=unsubscriptable-object
        path0 = dst_paths[0]
        self.assertEqual(sorted(os.listdir(path0)), list(good_dlc_ids))
        self.assertEqual(os.path.basename(path0), dlc_lib.DLC_DIR)
        # pylint: disable=unsubscriptable-object
        path1 = dst_paths[2]
        self.assertEqual(sorted(os.listdir(path1)), list(good_dlc_ids))
        self.assertEqual(os.path.basename(path1), dlc_lib.DLC_DIR_SCALED)

        for data_path in (dst_paths[1], dst_paths[3]):
            for dlc_id in good_dlc_ids:
                self.assertTrue(
                    os.path.exists(
                        os.path.join(
                            data_path,
                            dlc_id,
                            dlc_lib.DLC_PACKAGE,
                            dlc_lib.IMAGELOADER_JSON,
                        )
                    )
                )

            # Even bad ones that have metadata should copy over.
            self.assertFalse(
                os.path.exists(
                    os.path.join(
                        data_path,
                        dlc_bad_id,
                        dlc_lib.DLC_PACKAGE,
                        dlc_lib.IMAGELOADER_JSON,
                    )
                )
            )

        for path in (path0, path1):
            for dlc_id in good_dlc_ids:
                self.assertTrue(
                    os.path.exists(
                        os.path.join(
                            path, dlc_id, dlc_lib.DLC_PACKAGE, dlc_lib.DLC_IMAGE
                        )
                    )
                )
                self.assertFalse(
                    os.path.exists(
                        os.path.join(
                            path, dlc_id, dlc_lib.DLC_PACKAGE, "foobar-file"
                        )
                    )
                )
            self.assertFalse(
                os.path.exists(
                    os.path.join(
                        path, dlc_bad_id, dlc_lib.DLC_PACKAGE, dlc_lib.DLC_IMAGE
                    )
                )
            )
            self.assertFalse(
                os.path.exists(
                    os.path.join(
                        path, dlc_bad_package, "packit", dlc_lib.DLC_IMAGE
                    )
                )
            )
            self.assertFalse(
                os.path.exists(
                    os.path.join(
                        path, dlc_bad_artifact, dlc_lib.DLC_PACKAGE, "some-file"
                    )
                )
            )
            self.assertFalse(
                os.path.exists(
                    os.path.join(
                        path,
                        dlc_bad_artifact_with_dir,
                        dlc_lib.DLC_PACKAGE,
                        "some-dir/some-file",
                    )
                )
            )


class TestSignImage(cros_test_lib.MockTempDirTestCase):
    """Unittests for SignImage."""

    def test(self):
        """Test sign image."""
        self.PatchObject(
            osutils.TempDir, "__enter__", return_value=self.tempdir
        )
        result_dir = os.path.join(self.tempdir, "out")
        os.mkdir(result_dir)
        # Write temp file as if it were written by docker, we'll make sure
        # we're reading and returning it correctly.
        expected_signed_artifacts = signing_pb2.BuildTargetSignedArtifacts(
            archive_artifacts=[
                signing_pb2.ArchiveArtifacts(
                    input_archive_name="foo",
                )
            ]
        )
        osutils.WriteFile(
            os.path.join(result_dir, "out_proto.bin"),
            expected_signed_artifacts.SerializeToString(),
            mode="wb",
        )

        rc = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc.SetDefaultCmdResult()

        os.environ["LUCI_CONTEXT"] = "/tmp/foo/bar/luci_context.1234"
        os.environ["GCE_METADATA_HOST"] = "127.0.0.1:12345"
        os.environ["GCE_METADATA_IP"] = "127.0.0.1:12345"
        os.environ["GCE_METADATA_ROOT"] = "127.0.0.1:12345"

        signed_artifacts = image.SignImage(
            signing_pb2.BuildTargetSigningConfigs(),
            "/tmp/temp-dir-archives/",
            result_dir,
            "signing:latest",
        )
        rc.assertCommandContains(
            ["docker", "inspect", "--type=image", "signing:latest"]
        )
        rc.assertCommandContains(
            [
                "docker",
                "run",
                "--privileged",
                "--network",
                "host",
                "-v",
                "/dev:/dev",
                "-v",
                f"{self.tempdir}:/in",
                "-v",
                "/tmp/temp-dir-archives/:/archive_dir",
                "-v",
                f"{result_dir}:/out",
                "-v",
                "/tmp/foo/bar/luci_context.1234:/tmp/luci/luci_context.1234",
                "-e",
                "LUCI_CONTEXT=/tmp/luci/luci_context.1234",
                "-e",
                "GCE_METADATA_HOST=127.0.0.1:12345",
                "-e",
                "GCE_METADATA_IP=127.0.0.1:12345",
                "-e",
                "GCE_METADATA_ROOT=127.0.0.1:12345",
                "signing:latest",
                "-i",
                "/in/proto.bin",
                "--archive-dir",
                "/archive_dir",
                "-o",
                "/out",
                "-p",
                "out_proto.bin",
            ]
        )
        self.assertEqual(signed_artifacts, expected_signed_artifacts)

    def testMissingEnv(self):
        """Test sign image."""
        self.PatchObject(
            osutils.TempDir, "__enter__", return_value=self.tempdir
        )
        result_dir = os.path.join(self.tempdir, "out")
        os.mkdir(result_dir)
        # Write temp file as if it were written by docker, we'll make sure
        # we're reading and returning it correctly.
        expected_signed_artifacts = signing_pb2.BuildTargetSignedArtifacts(
            archive_artifacts=[
                signing_pb2.ArchiveArtifacts(
                    input_archive_name="foo",
                )
            ]
        )
        osutils.WriteFile(
            os.path.join(result_dir, "out_proto.bin"),
            expected_signed_artifacts.SerializeToString(),
            mode="wb",
        )

        rc = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc.SetDefaultCmdResult()

        os.environ["LUCI_CONTEXT"] = "/tmp/foo/bar/luci_context.1234"
        os.environ["GCE_METADATA_HOST"] = "127.0.0.1:12345"
        os.environ["GCE_METADATA_ROOT"] = "127.0.0.1:12345"

        with self.assertRaises(image.InvalidArgumentError):
            image.SignImage(
                signing_pb2.BuildTargetSigningConfigs(),
                "/tmp/temp-dir-archives/",
                result_dir,
                "signing:latest",
            )
