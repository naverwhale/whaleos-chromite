# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Artifacts service tests."""

import json
import os
import shutil
from unittest import mock

from chromite.lib import autotest_util
from chromite.lib import build_target_lib
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib import partial_mock
from chromite.lib import portage_util
from chromite.lib import sysroot_lib
from chromite.lib.paygen import partition_lib
from chromite.lib.paygen import paygen_payload_lib
from chromite.lib.paygen import paygen_stateful_payload_lib
from chromite.service import artifacts


class BundleAutotestFilesTest(cros_test_lib.MockTempDirTestCase):
    """Test the Bundle Autotest Files function."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)
        self.output_dir = os.path.join(self.tempdir, "output_dir")
        self.archive_dir = os.path.join(self.tempdir, "archive_base_dir")

        self.chroot = chroot_lib.Chroot(
            self.tempdir / "chroot_dir", out_path=self.tempdir / "out_dir"
        )
        sysroot_path = self.chroot.full_path("sysroot")
        self.sysroot = sysroot_lib.Sysroot("sysroot")
        self.sysroot_dne = sysroot_lib.Sysroot("sysroot_DNE")

        # Make sure we have the valid paths.
        osutils.SafeMakedirs(self.output_dir)
        osutils.SafeMakedirs(sysroot_path)
        osutils.SafeMakedirs(self.chroot.tmp)

    def testInvalidOutputDirectory(self):
        """Test invalid output directory."""
        with self.assertRaises(AssertionError):
            artifacts.BundleAutotestFiles(self.chroot, self.sysroot, None)

    def testInvalidSysroot(self):
        """Test sysroot that does not exist."""
        with self.assertRaises(AssertionError):
            artifacts.BundleAutotestFiles(
                self.chroot, self.sysroot_dne, self.output_dir
            )

    def testArchiveDirectoryDoesNotExist(self):
        """Test archive directory that does not exist causes error."""
        self.assertEqual(
            artifacts.BundleAutotestFiles(
                self.chroot, self.sysroot, self.output_dir
            ),
            {},
        )

    def testSuccess(self):
        """Test a successful call handling."""
        ab_path = self.chroot.full_path(
            self.sysroot.path, constants.AUTOTEST_BUILD_PATH
        )
        osutils.SafeMakedirs(ab_path)

        # Makes all the individual calls to build out each of the tarballs work
        # nicely with a single patch.
        self.PatchObject(
            autotest_util.AutotestTarballBuilder,
            "_BuildTarball",
            side_effect=lambda _, path, **kwargs: osutils.Touch(path),
        )

        result = artifacts.BundleAutotestFiles(
            self.chroot, self.sysroot, self.output_dir
        )

        for archive in result.values():
            self.assertStartsWith(archive, self.output_dir)
            self.assertExists(archive)


class ArchiveChromeEbuildEnvTest(cros_test_lib.MockTempDirTestCase):
    """ArchiveChromeEbuildEnv tests."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)
        # Create the chroot and sysroot instances.
        self.chroot_path = self.tempdir / "chroot_dir"
        self.out_path = self.tempdir / "out_dir"
        self.chroot = chroot_lib.Chroot(
            path=self.chroot_path, out_path=self.out_path
        )
        # NB: sysroot_lib.Sysroot is a bit ambiguous on whether these are full
        # host paths, or chroot-relative paths. But ArchiveChromeEbuildEnv()
        # definitely treas these as full host paths.
        self.sysroot_path = self.chroot.full_path("sysroot_dir")
        self.sysroot = sysroot_lib.Sysroot(self.sysroot_path)

        # Create the output directory.
        self.output_dir = os.path.join(self.tempdir, "output_dir")
        osutils.SafeMakedirs(self.output_dir)

        # The sysroot's /var/db/pkg prefix for the chrome package directories.
        var_db_pkg = os.path.join(self.sysroot_path, portage_util.VDB_PATH)
        # Create the var/db/pkg dir so we have that much for no-chrome tests.
        osutils.SafeMakedirs(var_db_pkg)

        # Two versions of chrome to test the multiple version checks/handling.
        chrome_v1 = "%s-1.0.0-r1" % constants.CHROME_PN
        chrome_v2 = "%s-2.0.0-r1" % constants.CHROME_PN

        # Build the two chrome version paths.
        chrome_cat_dir = os.path.join(var_db_pkg, constants.CHROME_CN)
        self.chrome_v1_dir = os.path.join(chrome_cat_dir, chrome_v1)
        self.chrome_v2_dir = os.path.join(chrome_cat_dir, chrome_v2)

        # Directory tuple for verifying the result archive contents.
        self.expected_archive_contents = cros_test_lib.Directory(
            "./", "environment"
        )

        # Create a environment.bz2 file to put into folders.
        env_file = os.path.join(self.tempdir, "environment")
        osutils.Touch(env_file)
        cros_build_lib.run(["bzip2", env_file])
        self.env_bz2 = "%s.bz2" % env_file

    def _CreateChromeDir(self, path: str, populate: bool = True):
        """Setup a chrome package directory.

        Args:
            path: The full chrome package path.
            populate: Whether to include the environment bz2.
        """
        osutils.SafeMakedirs(path)
        if populate:
            shutil.copy(self.env_bz2, path)

    def testSingleChromeVersion(self):
        """Test a successful single-version run."""
        self._CreateChromeDir(self.chrome_v1_dir)

        created = artifacts.ArchiveChromeEbuildEnv(
            self.sysroot, self.output_dir
        )

        self.assertStartsWith(created, self.output_dir)
        cros_test_lib.VerifyTarball(created, self.expected_archive_contents)

    def testMultipleChromeVersions(self):
        """Test a successful multiple version run."""
        # Create both directories, but don't populate the v1 dir so it'll hit an
        # error if the wrong one is used.
        self._CreateChromeDir(self.chrome_v1_dir, populate=False)
        self._CreateChromeDir(self.chrome_v2_dir)

        created = artifacts.ArchiveChromeEbuildEnv(
            self.sysroot, self.output_dir
        )

        self.assertStartsWith(created, self.output_dir)
        cros_test_lib.VerifyTarball(created, self.expected_archive_contents)

    def testNoChrome(self):
        """Test no version of chrome present."""
        with self.assertRaises(artifacts.NoFilesError):
            artifacts.ArchiveChromeEbuildEnv(self.sysroot, self.output_dir)


class ArchiveImagesTest(cros_test_lib.TempDirTestCase):
    """ArchiveImages tests."""

    def setUp(self):
        self.image_dir = os.path.join(self.tempdir, "images")
        osutils.SafeMakedirs(self.image_dir)
        self.output_dir = os.path.join(self.tempdir, "output")
        osutils.SafeMakedirs(self.output_dir)
        chroot_path = os.path.join(self.tempdir, "chroot")
        self.chroot = chroot_lib.Chroot(
            path=chroot_path, out_path=self.output_dir
        )
        osutils.SafeMakedirs(chroot_path)
        sysroot_path = os.path.join(self.tempdir, "build/board")
        self.sysroot = sysroot_lib.Sysroot(sysroot_path)
        osutils.SafeMakedirs(sysroot_path)

        self.images = []
        for img in artifacts.IMAGE_TARS.keys():
            full_path = os.path.join(self.image_dir, img)
            self.images.append(full_path)
            osutils.Touch(full_path)
            if img in artifacts.IMAGE_ADDITIONAL_SYSROOT_FILES:
                for file in artifacts.IMAGE_ADDITIONAL_SYSROOT_FILES[img]:
                    osutils.Touch(
                        os.path.join(sysroot_path, file), makedirs=True
                    )

        osutils.Touch(os.path.join(self.image_dir, "irrelevant_image.bin"))
        osutils.Touch(os.path.join(self.image_dir, "foo.txt"))
        osutils.Touch(os.path.join(self.image_dir, "bar"))

    def testNoImages(self):
        """Test an empty directory handling."""
        artifacts.ArchiveImages(
            self.chroot, self.sysroot, self.tempdir, self.output_dir
        )
        self.assertFalse(os.listdir(self.output_dir))

    def testAllImages(self):
        """Test each image gets picked up."""
        created = artifacts.ArchiveImages(
            self.chroot, self.sysroot, self.image_dir, self.output_dir
        )
        self.assertCountEqual(list(artifacts.IMAGE_TARS.values()), created)


class CreateChromeRootTest(cros_test_lib.RunCommandTempDirTestCase):
    """CreateChromeRoot tests."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        # Create the build target.
        self.build_target = build_target_lib.BuildTarget("board")

        # Create the chroot.
        self.chroot_dir = self.tempdir / "chroot"
        self.out_dir = self.tempdir / "out"
        self.chroot = chroot_lib.Chroot(
            path=self.chroot_dir, out_path=self.out_dir
        )
        self.chroot_tmp = self.chroot.tmp
        osutils.SafeMakedirs(self.chroot_tmp)

        # Create the output directory.
        self.output_dir = os.path.join(self.tempdir, "output_dir")
        osutils.SafeMakedirs(self.output_dir)

    def testRunCommandError(self):
        """Test handling when the run command call is not successful."""
        self.rc.SetDefaultCmdResult(
            side_effect=cros_build_lib.RunCommandError("Error")
        )

        with self.assertRaises(artifacts.CrosGenerateSysrootError):
            artifacts.CreateChromeRoot(
                self.chroot, self.build_target, self.output_dir
            )

    def testSuccess(self):
        """Test success case."""
        # Separate tempdir for the method itself.
        call_tempdir = os.path.join(self.chroot_tmp, "cgs_call_tempdir")
        osutils.SafeMakedirs(call_tempdir)
        self.PatchObject(
            osutils.TempDir, "__enter__", return_value=call_tempdir
        )

        # Set up files in the tempdir since the command isn't being called to
        # generate anything for it to handle.
        files = ["file1", "file2", "file3"]
        expected_files = [os.path.join(self.output_dir, f) for f in files]
        for f in files:
            osutils.Touch(os.path.join(call_tempdir, f))

        created = artifacts.CreateChromeRoot(
            self.chroot, self.build_target, self.output_dir
        )

        # Just test the command itself and the parameter-based args.
        self.assertCommandContains(
            ["cros_generate_sysroot", "--board", self.build_target.name]
        )
        # Make sure we
        self.assertCountEqual(expected_files, created)
        for f in created:
            self.assertExists(f)


class BundleEBuildLogsTarballTest(cros_test_lib.TempDirTestCase):
    """BundleEBuildLogsTarball tests."""

    @mock.patch(
        "chromite.lib.cros_build_lib.IsInsideChroot", return_value=False
    )
    def testBundleEBuildLogsTarball(self, _):
        """Verifies that the correct EBuild tar files are bundled."""
        board = "samus"
        # Create chroot object and sysroot object
        chroot_path = self.tempdir / "chroot"
        out_path = self.tempdir / "out"
        chroot = chroot_lib.Chroot(path=chroot_path, out_path=out_path)
        sysroot_path = os.path.join("build", board)
        sysroot = sysroot_lib.Sysroot(sysroot_path)

        # Create parent dir for logs
        log_parent_dir = chroot.full_path("build")

        # Names of log files typically found in a build directory.
        log_files = (
            "",
            "x11-libs:libdrm-2.4.81-r24:20170816-175008.log",
            "x11-libs:libpciaccess-0.12.902-r2:20170816-174849.log",
            "x11-libs:libva-1.7.1-r2:20170816-175019.log",
            "x11-libs:libva-intel-driver-1.7.1-r4:20170816-175029.log",
            "x11-libs:libxkbcommon-0.4.3-r2:20170816-174908.log",
            "x11-libs:pango-1.32.5-r1:20170816-174954.log",
            "x11-libs:pixman-0.32.4:20170816-174832.log",
            "x11-misc:xkeyboard-config-2.15-r3:20170816-174908.log",
            "x11-proto:kbproto-1.0.5:20170816-174849.log",
            "x11-proto:xproto-7.0.31:20170816-174849.log",
        )
        tarred_files = [os.path.join("logs", x) for x in log_files]
        log_files_root = os.path.join(
            log_parent_dir, "%s/tmp/portage/logs" % board
        )
        # Generate a representative set of log files produced by a typical
        # build.
        cros_test_lib.CreateOnDiskHierarchy(log_files_root, log_files)

        archive_dir = self.tempdir
        tarball = artifacts.BundleEBuildLogsTarball(
            chroot, sysroot, archive_dir
        )
        self.assertEqual("ebuild_logs.tar.xz", tarball)

        # Verify the tarball contents.
        tarball_fullpath = os.path.join(self.tempdir, tarball)
        cros_test_lib.VerifyTarball(tarball_fullpath, tarred_files)


class BundleChromeOSConfigTest(cros_test_lib.MockTempDirTestCase):
    """BundleChromeOSConfig tests."""

    def setUp(self):
        self.board = "samus"

        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)
        # Create chroot object and sysroot object
        chroot_path = self.tempdir / "chroot"
        out_path = self.tempdir / "out"
        self.chroot = chroot_lib.Chroot(path=chroot_path, out_path=out_path)
        sysroot_path = os.path.join("build", self.board)
        self.sysroot = sysroot_lib.Sysroot(sysroot_path)

        self.archive_dir = self.tempdir

    def testBundleChromeOSConfig(self):
        """Verifies that the correct ChromeOS config file is bundled."""
        # Create parent dir for ChromeOS Config output.
        config_parent_dir = self.chroot.full_path("build")

        # Names of ChromeOS Config files typically found in a build directory.
        config_files = (
            "config.json",
            cros_test_lib.Directory(
                "yaml",
                [
                    "config.c",
                    "config.yaml",
                    "ec_config.c",
                    "ec_config.h",
                    "model.yaml",
                    "private-model.yaml",
                ],
            ),
        )
        config_files_root = os.path.join(
            config_parent_dir, "%s/usr/share/chromeos-config" % self.board
        )
        # Generate a representative set of config files produced by a typical
        # build.
        cros_test_lib.CreateOnDiskHierarchy(config_files_root, config_files)

        # Write a payload to the config.yaml file.
        test_config_payload = {
            "chromeos": {"configs": [{"identity": {"platform-name": "Samus"}}]}
        }
        with open(
            os.path.join(config_files_root, "yaml", "config.yaml"),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(test_config_payload, f)

        config_filename = artifacts.BundleChromeOSConfig(
            self.chroot, self.sysroot, self.archive_dir
        )
        self.assertEqual("config.yaml", config_filename)

        with open(
            os.path.join(self.archive_dir, config_filename),
            "r",
            encoding="utf-8",
        ) as f:
            self.assertEqual(test_config_payload, json.load(f))

    def testNoChromeOSConfigFound(self):
        """Verifies None is returned when no ChromeOS config file is found."""
        self.assertIsNone(
            artifacts.BundleChromeOSConfig(
                self.chroot, self.sysroot, self.archive_dir
            )
        )


class BundleVmFilesTest(cros_test_lib.TempDirTestCase):
    """BundleVmFiles tests."""

    def testBundleVmFiles(self):
        """Verifies that the correct files are bundled"""
        # Create the chroot instance.
        chroot_path = self.tempdir / "chroot"
        out_path = self.tempdir / "out"
        chroot = chroot_lib.Chroot(path=chroot_path, out_path=out_path)

        # Create the test_results_dir
        test_results_dir = "test/results"

        # Create a set of files where some should get bundled up as VM files.
        # Add a suffix (123) to one of the files matching the VM pattern prefix.
        vm_files = ("file1.txt", "file2.txt")

        target_test_dir = os.path.join(chroot_path, test_results_dir)
        cros_test_lib.CreateOnDiskHierarchy(target_test_dir, vm_files)

        # Create the output directory.
        output_dir = self.tempdir / "output_dir"
        osutils.SafeMakedirs(output_dir)

        archives = artifacts.BundleVmFiles(chroot, test_results_dir, output_dir)
        expected_archive_files = []
        self.assertCountEqual(archives, expected_archive_files)


class BuildFirmwareArchiveTest(cros_test_lib.MockTempDirTestCase):
    """BuildFirmwareArchive tests."""

    def testBuildFirmwareArchive(self):
        """Verifies that firmware archiver includes proper files"""
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        # Assorted set of file names, some of which are supposed to be included
        # in the archive.
        fw_files = (
            "dts/emeraldlake2.dts",
            "image-link.rw.bin",
            "nv_image-link.bin",
            "pci8086,0166.rom",
            "seabios.cbfs",
            "u-boot.elf",
            "u-boot_netboot.bin",
            "updater-link.rw.sh",
            "x86-memtest",
        )

        board = "link"

        # Create the chroot and sysroot instances.
        fw_test_root = self.tempdir
        chroot_path = fw_test_root / "chroot"
        out_path = fw_test_root / "out"
        chroot = chroot_lib.Chroot(path=chroot_path, out_path=out_path)
        sysroot = sysroot_lib.Sysroot("/build/link")
        fw_files_root = chroot.full_path("/build/%s/firmware" % board)
        # Generate a representative set of files produced by a typical build.
        cros_test_lib.CreateOnDiskHierarchy(fw_files_root, fw_files)

        # Create an archive from the simulated firmware directory
        tarball = os.path.join(
            fw_test_root,
            artifacts.BuildFirmwareArchive(chroot, sysroot, fw_test_root),
        )

        # Verify the tarball contents.
        cros_test_lib.VerifyTarball(tarball, fw_files)


class BundleFpmcuUnittestsTest(cros_test_lib.MockTempDirTestCase):
    """BundleFpmcuUnittests tests."""

    def testBundleFpmcuUnittests(self):
        """Verifies that the resulting tarball includes proper files"""
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        unittest_files = (
            "bloonchipper/test_rsa.bin",
            "dartmonkey/test_utils.bin",
        )

        board = "hatch"

        chroot_path = self.tempdir / "chroot"
        out_path = self.tempdir / "out"
        chroot = chroot_lib.Chroot(path=chroot_path, out_path=out_path)
        sysroot = sysroot_lib.Sysroot("/build/%s" % board)

        unittest_files_root = chroot.full_path(
            "/build/%s/firmware/chromeos-fpmcu-unittests" % board
        )
        cros_test_lib.CreateOnDiskHierarchy(unittest_files_root, unittest_files)

        tarball = os.path.join(
            self.tempdir,
            artifacts.BundleFpmcuUnittests(chroot, sysroot, self.tempdir),
        )
        cros_test_lib.VerifyTarball(
            tarball, unittest_files + ("bloonchipper/", "dartmonkey/")
        )


class GeneratePayloadsTest(cros_test_lib.MockTempDirTestCase):
    """Test cases for the payload generation functions."""

    def setUp(self):
        self.target_image = os.path.join(
            self.tempdir,
            "link/R37-5952.0.2014_06_12_2302-a1/chromiumos_test_image.bin",
        )
        osutils.Touch(self.target_image, makedirs=True)
        self.sample_dlc_image = os.path.join(
            self.tempdir,
            "link/R37-5952.0.2014_06_12_2302-a1/dlc/sample-dlc/package/dlc.img",
        )
        osutils.Touch(self.sample_dlc_image, makedirs=True)

        self.PatchObject(
            parallel, "RunParallelSteps", lambda x, **kwargs: [a() for a in x]
        )
        self.chroot = chroot_lib.Chroot(
            self.tempdir / "chroot", out_path=self.tempdir / "out"
        )

    def testExtendBuildPaths(self):
        """Verifies that ExtendBuildPaths adds the correct elements."""
        self.assertEqual(
            ["a.bin", "a.bin.json", "a.bin.log"],
            artifacts.ExtendBinPaths("a.bin"),
        )

    def testGenerateFullTestPayloads(self):
        """Verifies correctly generating full payloads."""
        cros_payload_path = os.path.join(
            self.tempdir,
            "chromeos_R37-5952.0.2014_06_12_2302-a1_link_full_dev.bin",
        )
        minios_payload_path = os.path.join(
            self.tempdir,
            "minios_R37-5952.0.2014_06_12_2302-a1_link_full_dev.bin",
        )

        paygen_mock = self.PatchObject(
            paygen_payload_lib,
            "GenerateUpdatePayload",
            side_effect=[
                [cros_payload_path],  # Generate CrOS
                [minios_payload_path],  # Generate MiniOS
            ],
        )

        generated = artifacts.GenerateTestPayloads(
            self.chroot, self.target_image, self.tempdir, full=True
        )

        self.assertEqual(
            generated,
            artifacts.ExtendBinPaths(cros_payload_path)
            + artifacts.ExtendBinPaths(minios_payload_path),
        )
        paygen_mock.assert_has_calls(
            [
                mock.call(self.chroot, self.target_image, cros_payload_path),
                mock.call(
                    self.chroot,
                    self.target_image,
                    minios_payload_path,
                    minios=True,
                ),
            ]
        )

    def testGenerateFullTestPayloadsPartial(self):
        """Verifies partially generating full payloads."""
        cros_payload_path = os.path.join(
            self.tempdir,
            "chromeos_R37-5952.0.2014_06_12_2302-a1_link_full_dev.bin",
        )
        minios_payload_path = os.path.join(
            self.tempdir,
            "minios_R37-5952.0.2014_06_12_2302-a1_link_full_dev.bin",
        )

        paygen_mock = self.PatchObject(
            paygen_payload_lib,
            "GenerateUpdatePayload",
            side_effect=[
                [cros_payload_path],  # Generate CrOS
                [],  # Skip MiniOS
            ],
        )

        generated = artifacts.GenerateTestPayloads(
            self.chroot, self.target_image, self.tempdir, full=True
        )

        self.assertEqual(generated, artifacts.ExtendBinPaths(cros_payload_path))
        paygen_mock.assert_has_calls(
            [
                mock.call(self.chroot, self.target_image, cros_payload_path),
                mock.call(
                    self.chroot,
                    self.target_image,
                    minios_payload_path,
                    minios=True,
                ),
            ]
        )

    def testGenerateFullTestPayloadsSkipped(self):
        """Verifies skipping generating full payloads."""
        cros_payload_path = os.path.join(
            self.tempdir,
            "chromeos_R37-5952.0.2014_06_12_2302-a1_link_full_dev.bin",
        )
        minios_payload_path = os.path.join(
            self.tempdir,
            "minios_R37-5952.0.2014_06_12_2302-a1_link_full_dev.bin",
        )

        paygen_mock = self.PatchObject(
            paygen_payload_lib,
            "GenerateUpdatePayload",
            side_effect=[
                [],  # Skip CrOS
                [],  # Skip MiniOS
            ],
        )

        generated = artifacts.GenerateTestPayloads(
            self.chroot, self.target_image, self.tempdir, full=True
        )

        self.assertEqual(generated, [])
        paygen_mock.assert_has_calls(
            [
                mock.call(self.chroot, self.target_image, cros_payload_path),
                mock.call(
                    self.chroot,
                    self.target_image,
                    minios_payload_path,
                    minios=True,
                ),
            ]
        )

    def testGenerateDeltaTestPayloads(self):
        """Verifies correctly generating delta payloads."""
        cros_payload_path = os.path.join(
            self.tempdir,
            "chromeos_R37-5952.0.2014_06_12_2302-a1_R37-"
            "5952.0.2014_06_12_2302-a1_link_delta_dev.bin",
        )
        minios_payload_path = os.path.join(
            self.tempdir,
            "minios_R37-5952.0.2014_06_12_2302-a1_R37-"
            "5952.0.2014_06_12_2302-a1_link_delta_dev.bin",
        )

        paygen_mock = self.PatchObject(
            paygen_payload_lib,
            "GenerateUpdatePayload",
            side_effect=[
                [cros_payload_path],  # Generate CrOS
                [minios_payload_path],  # Generate MiniOS
            ],
        )

        generated = artifacts.GenerateTestPayloads(
            self.chroot, self.target_image, self.tempdir, delta=True
        )

        self.assertEqual(
            generated,
            artifacts.ExtendBinPaths(cros_payload_path)
            + artifacts.ExtendBinPaths(minios_payload_path),
        )
        paygen_mock.assert_has_calls(
            [
                mock.call(
                    self.chroot,
                    self.target_image,
                    cros_payload_path,
                    src_image=self.target_image,
                ),
                mock.call(
                    self.chroot,
                    self.target_image,
                    minios_payload_path,
                    src_image=self.target_image,
                    minios=True,
                ),
            ]
        )

    def testGenerateDeltaTestPayloadsPartial(self):
        """Verifies partially generating delta payloads."""
        cros_payload_path = os.path.join(
            self.tempdir,
            "chromeos_R37-5952.0.2014_06_12_2302-a1_R37-"
            "5952.0.2014_06_12_2302-a1_link_delta_dev.bin",
        )
        minios_payload_path = os.path.join(
            self.tempdir,
            "minios_R37-5952.0.2014_06_12_2302-a1_R37-"
            "5952.0.2014_06_12_2302-a1_link_delta_dev.bin",
        )

        paygen_mock = self.PatchObject(
            paygen_payload_lib,
            "GenerateUpdatePayload",
            side_effect=[
                [cros_payload_path],  # Generate CrOS
                [],  # Skip MiniOS
            ],
        )

        generated = artifacts.GenerateTestPayloads(
            self.chroot, self.target_image, self.tempdir, delta=True
        )

        self.assertEqual(generated, artifacts.ExtendBinPaths(cros_payload_path))
        paygen_mock.assert_has_calls(
            [
                mock.call(
                    self.chroot,
                    self.target_image,
                    cros_payload_path,
                    src_image=self.target_image,
                ),
                mock.call(
                    self.chroot,
                    self.target_image,
                    minios_payload_path,
                    src_image=self.target_image,
                    minios=True,
                ),
            ]
        )

    def testGenerateDeltaTestPayloadsSkipped(self):
        """Verifies skipping generating delta payloads."""
        cros_payload_path = os.path.join(
            self.tempdir,
            "chromeos_R37-5952.0.2014_06_12_2302-a1_R37-"
            "5952.0.2014_06_12_2302-a1_link_delta_dev.bin",
        )
        minios_payload_path = os.path.join(
            self.tempdir,
            "minios_R37-5952.0.2014_06_12_2302-a1_R37-"
            "5952.0.2014_06_12_2302-a1_link_delta_dev.bin",
        )

        paygen_mock = self.PatchObject(
            paygen_payload_lib,
            "GenerateUpdatePayload",
            side_effect=[
                [],  # Skip CrOS
                [],  # Skip MiniOS
            ],
        )
        generated = artifacts.GenerateTestPayloads(
            self.chroot, self.target_image, self.tempdir, delta=True
        )

        self.assertEqual(generated, [])
        paygen_mock.assert_has_calls(
            [
                mock.call(
                    self.chroot,
                    self.target_image,
                    cros_payload_path,
                    src_image=self.target_image,
                ),
                mock.call(
                    self.chroot,
                    self.target_image,
                    minios_payload_path,
                    src_image=self.target_image,
                    minios=True,
                ),
            ]
        )

    def testGenerateFullStubDlcTestPayloads(self):
        """Verifies correctly generating full payloads for sample-dlc."""
        self.PatchObject(portage_util, "GetBoardUseFlags", return_value=["dlc"])

        cros_payload = os.path.join(
            self.tempdir,
            "chromeos_R37-5952.0.2014_06_12_2302-a1_link_full_dev.bin",
        )
        minios_payload = os.path.join(
            self.tempdir,
            "minios_R37-5952.0.2014_06_12_2302-a1_link_full_dev.bin",
        )
        dlc_payload = os.path.join(
            self.tempdir,
            (
                "dlc_sample-dlc_package_R37-"
                "5952.0.2014_06_12_2302-a1_link_full_dev.bin"
            ),
        )

        paygen_mock = self.PatchObject(
            paygen_payload_lib,
            "GenerateUpdatePayload",
            side_effect=[
                [cros_payload],  # Generate CrOS
                [minios_payload],  # Generate MiniOS
                [dlc_payload],  # Generate DLC
            ],
        )

        generated = artifacts.GenerateTestPayloads(
            self.chroot, self.target_image, self.tempdir, full=True, dlc=True
        )

        self.assertEqual(
            generated,
            artifacts.ExtendBinPaths(cros_payload)
            + artifacts.ExtendBinPaths(minios_payload)
            + artifacts.ExtendBinPaths(dlc_payload),
        )
        paygen_mock.assert_has_calls(
            [
                mock.call(self.chroot, self.target_image, cros_payload),
                mock.call(
                    self.chroot, self.target_image, minios_payload, minios=True
                ),
                mock.call(self.chroot, self.sample_dlc_image, dlc_payload),
            ]
        )

    def testGenerateFullStubDlcTestPayloadsSkipped(self):
        """Verifies skipping generating full payloads for sample-dlc."""
        self.PatchObject(portage_util, "GetBoardUseFlags", return_value=["dlc"])

        cros_payload = os.path.join(
            self.tempdir,
            "chromeos_R37-5952.0.2014_06_12_2302-a1_link_full_dev.bin",
        )
        minios_payload = os.path.join(
            self.tempdir,
            "minios_R37-5952.0.2014_06_12_2302-a1_link_full_dev.bin",
        )
        dlc_payload = os.path.join(
            self.tempdir,
            (
                "dlc_sample-dlc_package_R37-"
                "5952.0.2014_06_12_2302-a1_link_full_dev.bin"
            ),
        )

        # Omitting dlc_payload.
        paygen_mock = self.PatchObject(
            paygen_payload_lib,
            "GenerateUpdatePayload",
            side_effect=[
                [cros_payload],  # Generate CrOS
                [minios_payload],  # Generate MiniOS
                [],  # Skip DLC
            ],
        )

        generated = artifacts.GenerateTestPayloads(
            self.chroot, self.target_image, self.tempdir, full=True, dlc=True
        )

        self.assertEqual(
            generated,
            artifacts.ExtendBinPaths(cros_payload)
            + artifacts.ExtendBinPaths(minios_payload),
        )

        paygen_mock.assert_has_calls(
            [
                mock.call(self.chroot, self.target_image, cros_payload),
                mock.call(
                    self.chroot, self.target_image, minios_payload, minios=True
                ),
                mock.call(self.chroot, self.sample_dlc_image, dlc_payload),
            ]
        )

    def testGenerateDeltaStubDlcTestPayloads(self):
        """Verifies correctly generating delta payloads for sample-dlc."""
        self.PatchObject(portage_util, "GetBoardUseFlags", return_value=["dlc"])

        cros_payload = os.path.join(
            self.tempdir,
            (
                "chromeos_R37-5952.0.2014_06_12_2302-a1_R37-"
                "5952.0.2014_06_12_2302-a1_link_delta_dev.bin"
            ),
        )
        minios_payload = os.path.join(
            self.tempdir,
            (
                "minios_R37-5952.0.2014_06_12_2302-a1_R37-"
                "5952.0.2014_06_12_2302-a1_link_delta_dev.bin"
            ),
        )
        dlc_payload = os.path.join(
            self.tempdir,
            (
                "dlc_sample-dlc_package_R37-5952.0.2014_06_12_2302-a1_R37-"
                "5952.0.2014_06_12_2302-a1_link_delta_dev.bin"
            ),
        )

        paygen_mock = self.PatchObject(
            paygen_payload_lib,
            "GenerateUpdatePayload",
            side_effect=[
                [cros_payload],  # Generate CrOS
                [minios_payload],  # Generate MiniOS
                [dlc_payload],  # Generate DLC
            ],
        )

        generated = artifacts.GenerateTestPayloads(
            self.chroot, self.target_image, self.tempdir, delta=True, dlc=True
        )

        self.assertEqual(
            generated,
            artifacts.ExtendBinPaths(cros_payload)
            + artifacts.ExtendBinPaths(minios_payload)
            + artifacts.ExtendBinPaths(dlc_payload),
        )
        paygen_mock.assert_has_calls(
            [
                mock.call(
                    self.chroot,
                    self.target_image,
                    cros_payload,
                    src_image=self.target_image,
                ),
                mock.call(
                    self.chroot,
                    self.target_image,
                    minios_payload,
                    src_image=self.target_image,
                    minios=True,
                ),
                mock.call(
                    self.chroot,
                    self.sample_dlc_image,
                    dlc_payload,
                    src_image=self.sample_dlc_image,
                ),
            ]
        )

    def testGenerateDeltaStubDlcTestPayloadsSkipped(self):
        """Verifies skipping generating delta payloads for sample-dlc."""
        self.PatchObject(portage_util, "GetBoardUseFlags", return_value=["dlc"])

        cros_payload = os.path.join(
            self.tempdir,
            (
                "chromeos_R37-5952.0.2014_06_12_2302-a1_R37-"
                "5952.0.2014_06_12_2302-a1_link_delta_dev.bin"
            ),
        )
        minios_payload = os.path.join(
            self.tempdir,
            (
                "minios_R37-5952.0.2014_06_12_2302-a1_R37-"
                "5952.0.2014_06_12_2302-a1_link_delta_dev.bin"
            ),
        )
        dlc_payload = os.path.join(
            self.tempdir,
            (
                "dlc_sample-dlc_package_R37-5952.0.2014_06_12_2302-a1_R37-"
                "5952.0.2014_06_12_2302-a1_link_delta_dev.bin"
            ),
        )

        paygen_mock = self.PatchObject(
            paygen_payload_lib,
            "GenerateUpdatePayload",
            side_effect=[
                [cros_payload],  # Generate CrOS
                [minios_payload],  # Generate MiniOS
                [],  # Skip DLC
            ],
        )

        generated = artifacts.GenerateTestPayloads(
            self.chroot, self.target_image, self.tempdir, delta=True, dlc=True
        )

        self.assertEqual(
            generated,
            artifacts.ExtendBinPaths(cros_payload)
            + artifacts.ExtendBinPaths(minios_payload),
        )

        paygen_mock.assert_has_calls(
            [
                mock.call(
                    self.chroot,
                    self.target_image,
                    cros_payload,
                    src_image=self.target_image,
                ),
                mock.call(
                    self.chroot,
                    self.target_image,
                    minios_payload,
                    src_image=self.target_image,
                    minios=True,
                ),
                mock.call(
                    self.chroot,
                    self.sample_dlc_image,
                    dlc_payload,
                    src_image=self.sample_dlc_image,
                ),
            ]
        )

    def testGenerateStatefulTestPayloads(self):
        """Verifies correctly generating stateful payloads."""
        paygen_mock = self.PatchObject(
            paygen_stateful_payload_lib, "GenerateStatefulPayload"
        )
        artifacts.GenerateTestPayloads(
            self.chroot, self.target_image, self.tempdir, stateful=True
        )
        paygen_mock.assert_called_once_with(self.target_image, self.tempdir)

    def testGenerateQuickProvisionPayloads(self):
        """Verifies correct files are created for quick_provision script."""
        extract_kernel_mock = self.PatchObject(partition_lib, "ExtractKernel")
        extract_root_mock = self.PatchObject(partition_lib, "ExtractRoot")
        has_minios_mock = self.PatchObject(
            partition_lib, "HasMiniOSPartitions", return_value=False
        )
        compress_file_mock = self.PatchObject(cros_build_lib, "CompressFile")

        artifacts.GenerateQuickProvisionPayloads(
            self.target_image, self.tempdir
        )

        extract_kernel_mock.assert_called_once_with(
            self.target_image, partial_mock.HasString("kernel.bin")
        )
        extract_root_mock.assert_called_once_with(
            self.target_image,
            partial_mock.HasString("rootfs.bin"),
            truncate=False,
        )
        has_minios_mock.assert_called_once()

        calls = [
            mock.call(
                partial_mock.HasString("kernel.bin"),
                partial_mock.HasString(
                    constants.QUICK_PROVISION_PAYLOAD_KERNEL
                ),
            ),
            mock.call(
                partial_mock.HasString("rootfs.bin"),
                partial_mock.HasString(
                    constants.QUICK_PROVISION_PAYLOAD_ROOTFS
                ),
            ),
        ]
        compress_file_mock.assert_has_calls(calls)

    def testGenerateQuickProvisionPayloadsWithMiniOS(self):
        """Verifies correct files are created for quick_provision script."""
        extract_kernel_mock = self.PatchObject(partition_lib, "ExtractKernel")
        extract_root_mock = self.PatchObject(partition_lib, "ExtractRoot")
        extract_minios_mock = self.PatchObject(partition_lib, "ExtractMiniOS")
        has_minios_mock = self.PatchObject(
            partition_lib, "HasMiniOSPartitions", return_value=True
        )
        compress_file_mock = self.PatchObject(cros_build_lib, "CompressFile")

        artifacts.GenerateQuickProvisionPayloads(
            self.target_image, self.tempdir
        )

        extract_kernel_mock.assert_called_once_with(
            self.target_image, partial_mock.HasString("kernel.bin")
        )
        extract_root_mock.assert_called_once_with(
            self.target_image,
            partial_mock.HasString("rootfs.bin"),
            truncate=False,
        )
        extract_minios_mock.assert_called_once_with(
            self.target_image, partial_mock.HasString("minios.bin")
        )
        has_minios_mock.assert_called_once()

        calls = [
            mock.call(
                partial_mock.HasString("kernel.bin"),
                partial_mock.HasString(
                    constants.QUICK_PROVISION_PAYLOAD_KERNEL
                ),
            ),
            mock.call(
                partial_mock.HasString("rootfs.bin"),
                partial_mock.HasString(
                    constants.QUICK_PROVISION_PAYLOAD_ROOTFS
                ),
            ),
        ]
        compress_file_mock.assert_has_calls(calls)


class BundleTastFilesTest(cros_test_lib.MockTempDirTestCase):
    """BundleTastFiles tests."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        self.chroot = chroot_lib.Chroot(
            path=self.tempdir / "chroot",
            out_path=self.tempdir / "out",
        )
        self.sysroot = sysroot_lib.Sysroot("/build/board")
        self.output_dir = self.tempdir / "output_dir"

        osutils.SafeMakedirs(self.output_dir)

    def testSuccess(self):
        """Successfully create a tast tarball.

        /build/board/build/{libexec/tast,share/tast}/* ->
          libexec/tast/*
          share/tast/*
        """
        sysroot_files = (
            cros_test_lib.Directory("libexec/tast", ("foo", "bar")),
            cros_test_lib.Directory("share/tast", ("baz",)),
        )

        cros_test_lib.CreateOnDiskHierarchy(
            self.chroot.full_path(self.sysroot.JoinPath("build")),
            sysroot_files,
        )

        tarball = artifacts.BundleTastFiles(
            self.chroot, self.sysroot, self.output_dir
        )

        # Verify location and content of the tarball.
        self.assertEqual(
            tarball, str(self.output_dir / artifacts.TAST_BUNDLE_NAME)
        )
        cros_test_lib.VerifyTarball(tarball, sysroot_files)


class BundleGceTarballTest(cros_test_lib.MockTempDirTestCase):
    """BundleGceTarball tests."""

    def setUp(self):
        self.output_dir = os.path.join(self.tempdir, "output_dir")
        self.image_dir = os.path.join(self.tempdir, "image_dir")
        osutils.SafeMakedirs(self.output_dir)
        osutils.SafeMakedirs(self.image_dir)

        self.image_file = os.path.join(self.image_dir, constants.TEST_IMAGE_BIN)
        osutils.Touch(self.image_file)

    def testSuccess(self):
        # Prepare tempdir for use by the function as tarball root.
        call_tempdir = os.path.join(self.tempdir, "call_tempdir")
        osutils.SafeMakedirs(call_tempdir)
        self.PatchObject(
            osutils.TempDir, "__enter__", return_value=call_tempdir
        )

        tarball = artifacts.BundleGceTarball(self.output_dir, self.image_dir)

        # Verify location and content of the tarball.
        self.assertEqual(
            tarball, os.path.join(self.output_dir, constants.TEST_IMAGE_GCE_TAR)
        )
        cros_test_lib.VerifyTarball(tarball, ("disk.raw",))

        # Verify the symlink points the the test image.
        disk_raw = os.path.join(call_tempdir, "disk.raw")
        self.assertEqual(os.readlink(disk_raw), self.image_file)
