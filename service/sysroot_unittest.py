# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Sysroot service unittest."""

import contextlib
import datetime
import operator
import os
from pathlib import Path
import shutil
from typing import Optional, Union
from unittest import mock

from chromite.third_party.opentelemetry import context as otel_context
from chromite.third_party.opentelemetry import trace
import pytest

from chromite.lib import binpkg
from chromite.lib import build_target_lib
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cpupower_helper
from chromite.lib import cros_build_lib
from chromite.lib import cros_sdk_lib
from chromite.lib import cros_test_lib
from chromite.lib import goma_lib
from chromite.lib import gs
from chromite.lib import osutils
from chromite.lib import partial_mock
from chromite.lib import portage_util
from chromite.lib import remoteexec_util
from chromite.lib import sysroot_lib
from chromite.lib.parser import package_info
from chromite.service import sdk
from chromite.service import sysroot
from chromite.utils import os_util


class SetupBoardRunConfigTest(cros_test_lib.TestCase):
    """Tests for the SetupBoardRunConfig class."""

    def testGetUpdateChrootArgs(self):
        """Test the update chroot args conversion method."""
        # False/0/None tests.
        instance = sysroot.SetupBoardRunConfig(
            usepkg=False, jobs=None, update_toolchain=False, backtrack=1
        )
        args = instance.GetUpdateChrootArgs("board").GetArgList()
        self.assertIn("--backtrack=1", args)
        self.assertIn("--nousepkg", args)
        self.assertIn("--skip_toolchain_update", args)
        self.assertNotIn("--usepkg", args)
        self.assertFalse(any(x.startswith("--jobs") for x in args))

        # True/set values tests.
        instance = sysroot.SetupBoardRunConfig(
            usepkg=True, jobs=1, update_toolchain=True
        )
        args = instance.GetUpdateChrootArgs("board").GetArgList()
        self.assertIn("--usepkg", args)
        self.assertIn("--jobs=1", args)
        self.assertNotIn("--nousepkg", args)
        self.assertNotIn("--skip_toolchain_update", args)


class SetupBoardTest(cros_test_lib.MockTestCase):
    """Tests for SetupBoard."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)

    def testFullRun(self):
        """Test a regular full run.

        This method just checks that it's trying to create the sysroot and
        install the toolchain by default.
        """
        target_sysroot = sysroot_lib.Sysroot("/build/board")
        create_mock = self.PatchObject(
            sysroot, "Create", return_value=target_sysroot
        )
        install_toolchain_mock = self.PatchObject(sysroot, "InstallToolchain")

        sysroot.SetupBoard(build_target_lib.BuildTarget("board"))

        create_mock.assert_called_once()
        install_toolchain_mock.assert_called_once()

    def testRegenConfigs(self):
        """Test the regen configs install prevention."""
        target_sysroot = sysroot_lib.Sysroot("/build/board")
        create_mock = self.PatchObject(
            sysroot, "Create", return_value=target_sysroot
        )
        install_toolchain_mock = self.PatchObject(sysroot, "InstallToolchain")

        target = build_target_lib.BuildTarget("board")
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
        self.PatchObject(os_util, "is_root_user", return_value=True)

        # It has to be run inside the chroot.
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)

        # Don't write to the chroot.
        self.PatchObject(cros_sdk_lib.ChrootUpdater, "ApplyUpdates")

        # A board we have a sysroot for already.
        self.board = "board"
        self.sysroot_path = os.path.join(self.tempdir, "build", self.board)
        self.build_target = build_target_lib.BuildTarget(
            self.board, build_root=self.sysroot_path
        )
        # A board we don't have a sysroot for yet.
        self.unbuilt_board = "board2"
        self.unbuilt_path = os.path.join(
            self.tempdir, "build", self.unbuilt_board
        )
        self.unbuilt_target = build_target_lib.BuildTarget(
            self.unbuilt_board, build_root=self.unbuilt_path
        )

        # Create the sysroot.
        osutils.SafeMakedirs(self.sysroot_path)

    def testUpdateChroot(self):
        """Test the update_chroot related handling."""
        # Prevent it from doing anything else for this test.
        self.PatchObject(sysroot, "_CreateSysrootSkeleton")
        self.PatchObject(sysroot, "_InstallConfigs")
        self.PatchObject(sysroot, "_InstallPortageConfigs")
        self.PatchObject(
            cros_sdk_lib,
            "ChrootReadWrite",
            side_effect=contextlib.contextmanager(lambda path="": (yield)),
        )

        # Make sure we have a board we haven't setup to avoid triggering the
        # existing sysroot logic. That is entirely unrelated to the chroot
        # update.
        target = self.unbuilt_target

        # Test no update case.
        config = sysroot.SetupBoardRunConfig(upgrade_chroot=False)
        get_args_patch = self.PatchObject(config, "GetUpdateChrootArgs")

        sysroot.Create(target, config, None)

        # The update chroot args not being fetched is a
        # strong enough signal that the update wasn't run.
        get_args_patch.assert_not_called()

        # Test update case.
        script_loc = constants.CROSUTILS_DIR / "update_chroot.sh"
        config = sysroot.SetupBoardRunConfig(upgrade_chroot=True)

        sysroot.Create(target, config, None)

        self.assertCommandContains([script_loc])

    def test_update_chroot_failure(self):
        """Test failure handling when update chroot fails."""
        failed_pkgs = [
            package_info.parse("foo/bar-1.2-r3"),
            package_info.parse("cat/pkg-1.2-r3"),
        ]
        result = sdk.UpdateResult(return_code=1, failed_pkgs=failed_pkgs)
        self.PatchObject(sdk, "Update", return_value=result)

        try:
            sysroot.Create(
                self.unbuilt_target, sysroot.SetupBoardRunConfig(), None
            )
            self.fail("Should have raised an UpdateChrootError.")
        except sysroot.UpdateChrootError as e:
            self.assertSequenceEqual(
                sorted(failed_pkgs), sorted(e.failed_packages)
            )

    def testForce(self):
        """Test the force flag."""
        # Prevent it from doing anything else for this test.
        self.PatchObject(sysroot, "_CreateSysrootSkeleton")
        self.PatchObject(sysroot, "_InstallConfigs")
        self.PatchObject(sysroot, "_InstallPortageConfigs")
        self.PatchObject(
            cros_sdk_lib,
            "ChrootReadWrite",
            side_effect=contextlib.contextmanager(lambda path="": (yield)),
        )

        delete_patch = self.PatchObject(sysroot_lib.Sysroot, "Delete")

        config = sysroot.SetupBoardRunConfig(force=False)
        sysroot.Create(self.build_target, config, None)
        delete_patch.assert_not_called()

        config = sysroot.SetupBoardRunConfig(force=True)
        sysroot.Create(self.build_target, config, None)
        delete_patch.assert_called_once()


class CreateSimpleChromeSysrootTest(cros_test_lib.RunCommandTempDirTestCase):
    """Tests for CreateSimpleChromeSysroot."""

    def setUp(self):
        self.source_root = os.path.join(self.tempdir, "source_root")
        osutils.SafeMakedirs(self.source_root)
        self.PatchObject(constants, "SOURCE_ROOT", new=self.source_root)

        # Configure {chroot,out}_path.
        self.chroot_path = os.path.join(self.tempdir, "chroot_dir")
        self.out_path = self.tempdir / "out_dir"

        # Create output dir.
        self.output_dir = os.path.join(self.tempdir, "output_dir")
        osutils.SafeMakedirs(self.output_dir)

        # Create chroot and build_target objs.
        self.chroot = chroot_lib.Chroot(
            path=self.chroot_path, out_path=self.out_path
        )
        self.build_target = build_target_lib.BuildTarget("target")

        # Create the tmp dir.
        osutils.SafeMakedirs(self.chroot.tmp)

    def testCreateSimpleChromeSysroot(self):
        # Mock the artifact copy.
        tar_dest = os.path.join(self.output_dir, constants.CHROME_SYSROOT_TAR)
        self.PatchObject(shutil, "copy", return_value=tar_dest)
        # Call service, verify arguments passed to run.
        sysroot.CreateSimpleChromeSysroot(
            self.chroot, None, self.build_target, self.output_dir
        )

        self.rc.assertCommandCalled(
            [
                "cros_generate_sysroot",
                "--out-dir",
                mock.ANY,
                "--board",
                self.build_target.name,
                "--package",
                "chromeos-base/chromeos-chrome",
                "--out-file",
                "sysroot_chromeos-base_chromeos-chrome.tar.xz",
                "--deps-only",
            ],
            enter_chroot=True,
            cwd=self.source_root,
            chroot_args=mock.ANY,
            extra_env=mock.ANY,
        )


class CreateFuzzerSysrootTest(cros_test_lib.RunCommandTempDirTestCase):
    """Tests for CreateFuzzerSysroot."""

    def setUp(self):
        self.source_root = os.path.join(self.tempdir, "source_root")
        osutils.SafeMakedirs(self.source_root)
        self.PatchObject(constants, "SOURCE_ROOT", new=self.source_root)

        # Configure {chroot,out}_path.
        self.chroot_path = os.path.join(self.tempdir, "chroot_dir")
        self.out_path = self.tempdir / "out_dir"

        # Create output dir.
        self.output_dir = os.path.join(self.tempdir, "output_dir")
        osutils.SafeMakedirs(self.output_dir)

        # Create chroot and build_target objs.
        self.chroot = chroot_lib.Chroot(
            path=self.chroot_path, out_path=self.out_path
        )
        self.build_target = build_target_lib.BuildTarget("target")

        # Create the tmp dir.
        osutils.SafeMakedirs(self.chroot.tmp)

    def testCreateFuzzerSysroot(self):
        """Test the CreateFuzzerSysroot function under normal operation."""
        # Mock the artifact copy.
        tar_dest = os.path.join(self.output_dir, constants.CHROME_SYSROOT_TAR)
        self.PatchObject(shutil, "copy", return_value=tar_dest)
        # Call service, verify arguments passed to run.
        sysroot.CreateFuzzerSysroot(
            self.chroot, None, self.build_target, self.output_dir
        )

        self.rc.assertCommandCalled(
            [
                "cros_generate_sysroot",
                "--out-dir",
                mock.ANY,
                "--board",
                self.build_target.name,
                "--package",
                "virtual/target-fuzzers",
                "--out-file",
                "sysroot_virtual_target-os.tar.xz",
            ],
            enter_chroot=True,
            cwd=self.source_root,
            chroot_args=mock.ANY,
            extra_env=mock.ANY,
        )


class ArchiveChromeEbuildEnvTest(cros_test_lib.MockTempDirTestCase):
    """ArchiveChromeEbuildEnv tests."""

    def setUp(self):
        # Create the chroot and sysroot instances.
        self.chroot_path = os.path.join(self.tempdir, "chroot_dir")
        self.out_path = self.tempdir / "out_dir"
        self.chroot = chroot_lib.Chroot(
            path=self.chroot_path, out_path=self.out_path
        )
        self.sysroot_path = os.path.join(self.chroot_path, "sysroot_dir")
        self.sysroot = sysroot_lib.Sysroot(self.sysroot_path)

        # Create the output directory.
        self.output_dir = os.path.join(self.tempdir, "output_dir")
        osutils.SafeMakedirs(self.output_dir)

        # The sysroot's /var/db/pkg prefix for the chrome package directories.
        var_db_pkg = self.chroot.full_path(
            self.sysroot_path, portage_util.VDB_PATH
        )
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

        created = sysroot.CreateChromeEbuildEnv(
            self.chroot, self.sysroot, None, self.output_dir
        )

        self.assertStartsWith(created, self.output_dir)
        cros_test_lib.VerifyTarball(created, self.expected_archive_contents)

    def testMultipleChromeVersions(self):
        """Test a successful multiple version run."""
        # Create both directories, but don't populate the v1 dir so it'll hit an
        # error if the wrong one is used.
        self._CreateChromeDir(self.chrome_v1_dir, populate=False)
        self._CreateChromeDir(self.chrome_v2_dir)

        created = sysroot.CreateChromeEbuildEnv(
            self.chroot, self.sysroot, None, self.output_dir
        )

        self.assertStartsWith(created, self.output_dir)
        cros_test_lib.VerifyTarball(created, self.expected_archive_contents)

    def testNoChrome(self):
        """Test no version of chrome present."""
        self.assertIsNone(
            sysroot.CreateChromeEbuildEnv(
                self.chroot, self.sysroot, None, self.output_dir
            )
        )


class GenerateArchiveTest(cros_test_lib.RunCommandTempDirTestCase):
    """Tests for GenerateArchive."""

    def setUp(self):
        self.chroot_path = os.path.join(self.tempdir, "chroot_dir")

    def testCreateSimpleChromeSysroot(self):
        # A board for which we will create a simple chrome sysroot.
        target = "board"
        pkg_list = ["virtual/target-fuzzers"]

        # Call service, verify arguments passed to run.
        sysroot.GenerateArchive(self.chroot_path, target, pkg_list)
        self.rc.assertCommandCalled(
            [
                "cros_generate_sysroot",
                "--out-file",
                constants.TARGET_SYSROOT_TAR,
                "--out-dir",
                mock.ANY,
                "--board",
                target,
                "--package",
                "virtual/target-fuzzers",
            ],
            cwd=constants.SOURCE_ROOT,
        )


class InstallToolchainTest(cros_test_lib.MockTempDirTestCase):
    """Tests for InstallToolchain."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)
        # A board we have a sysroot for already.
        self.board = "board"
        self.sysroot_path = os.path.join(self.tempdir, "build", self.board)
        self.build_target = build_target_lib.BuildTarget(
            self.board, build_root=self.sysroot_path
        )
        self.sysroot = sysroot_lib.Sysroot(self.sysroot_path)

        # A board we don't have a sysroot for yet.
        self.unbuilt_board = "board2"
        self.unbuilt_path = os.path.join(
            self.tempdir, "build", self.unbuilt_board
        )
        self.unbuilt_target = build_target_lib.BuildTarget(
            self.unbuilt_board, build_root=self.unbuilt_path
        )
        self.unbuilt_sysroot = sysroot_lib.Sysroot(self.unbuilt_path)

        osutils.SafeMakedirs(self.sysroot_path)

    def testNoSysroot(self):
        """Test handling of no sysroot."""
        with self.assertRaises(ValueError):
            sysroot.InstallToolchain(
                self.unbuilt_target,
                self.unbuilt_sysroot,
                sysroot.SetupBoardRunConfig(),
            )

    def testLocalBuild(self):
        """Test the local build logic."""
        update_patch = self.PatchObject(self.sysroot, "UpdateToolchain")

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


class BuildPackagesRunConfigTest(
    cros_test_lib.RunCommandTestCase, cros_test_lib.LoggingTestCase
):
    """Tests for the BuildPackagesRunConfig."""

    def testGetBuildPackagesExtraEnv(self):
        """Test the `cros build-packages` extra env."""
        # Test the default config.
        instance = sysroot.BuildPackagesRunConfig()

        extra_env = instance.GetExtraEnv()

        self.assertNotIn("USE_GOMA", extra_env)
        self.assertNotIn("USE_REMOTEEXEC", extra_env)

        # Test when use_flags are specified.
        use_flags = ["flag1", "flag2"]
        instance = sysroot.BuildPackagesRunConfig(use_flags=use_flags)

        extra_env = instance.GetExtraEnv()

        self.assertEqual(extra_env.get("USE"), instance.GetUseFlags())

    def testGetPackages(self):
        """Test getting packages for the config."""
        # Test the default config.
        instance = sysroot.BuildPackagesRunConfig()

        packages = instance.GetPackages()

        self.assertIn("virtual/target-os", packages)
        self.assertIn("virtual/target-os-dev", packages)
        self.assertIn("virtual/target-os-factory", packages)
        self.assertIn("virtual/target-os-test", packages)
        self.assertIn("chromeos-base/autotest-all", packages)

        # Test when packages are specified.
        test_packages = ["test/package"]
        instance = sysroot.BuildPackagesRunConfig(packages=test_packages)

        packages = instance.GetPackages()

        self.assertEqual(packages, test_packages)

    def testGetForceLocalBuildPackages(self):
        """Test getting force local build packages for the config."""
        test_sysroot_path = "/sysroot/path"
        test_sysroot = sysroot_lib.Sysroot(test_sysroot_path)
        get_reverse_dependencies_mock = self.PatchObject(
            portage_util, "GetReverseDependencies"
        )

        # Test the default config.
        instance = sysroot.BuildPackagesRunConfig()
        self.rc.AddCmdResult(
            ["cros_list_modified_packages", "--sysroot", test_sysroot.path],
            stdout="",
        )

        packages = instance.GetForceLocalBuildPackages(test_sysroot)

        # Test when there are cros_workon packages and reverse dependencies
        # but skipping base install packages and their reverse dependencies.
        instance = sysroot.BuildPackagesRunConfig(incremental_build=False)
        test_cros_list_modified_packages_output = (
            "test/package1 test/package2\n"
        )
        self.rc.AddCmdResult(
            ["cros_list_modified_packages", "--sysroot", test_sysroot.path],
            stdout=test_cros_list_modified_packages_output,
        )
        test_reverse_dependencies = [
            package_info.parse("test/package3-1.0"),
            package_info.parse("test/package4-2.0-r1"),
        ]
        get_reverse_dependencies_mock.return_value = test_reverse_dependencies

        packages = instance.GetForceLocalBuildPackages(test_sysroot)

        self.assertIn("test/package1", packages)
        self.assertIn("test/package2", packages)
        self.assertIn("test/package3", packages)
        self.assertIn("test/package4", packages)

        # Test base install packages and their reverse dependency packages
        # but skipping cros workon packages and their reverse dependencies.
        instance = sysroot.BuildPackagesRunConfig(workon=False)
        test_emerge_output = """\
[binary N] test/package1 ... to /build/sysroot/
[ebuild r U] chromeos-base/tast-build-deps ... to /build/sysroot/
[binary U] chromeos-base/chromeos-chrome ... /build/sysroot/"""
        self.rc.AddCmdResult(
            partial_mock.ListRegex(
                f"parallel_emerge --sysroot={test_sysroot.path}"
            ),
            stdout=test_emerge_output,
        )
        test_reverse_dependencies = [
            package_info.parse("virtual/package3-1.0"),
            package_info.parse("test/package4-2.0-r1"),
        ]
        get_reverse_dependencies_mock.return_value = test_reverse_dependencies

        packages = instance.GetForceLocalBuildPackages(test_sysroot)

        self.assertIn("chromeos-base/tast-build-deps", packages)
        self.assertIn("test/package4", packages)

        # Test base install packages and their reverse dependencies are skipped
        # when --no-withrevdeps is specified.
        instance = sysroot.BuildPackagesRunConfig(incremental_build=False)

        with cros_test_lib.LoggingCapturer() as logs:
            instance.GetForceLocalBuildPackages(test_sysroot)

            self.AssertLogsContain(
                logs,
                "Starting reverse dependency calculations...",
                inverted=True,
            )

        # Test base install packages and their reverse dependencies are skipped
        # when --cleanbuild is specified and the sysroot does not exist.
        instance = sysroot.BuildPackagesRunConfig(clean_build=True)

        with cros_test_lib.LoggingCapturer() as logs:
            instance.GetForceLocalBuildPackages(test_sysroot)

            self.AssertLogsContain(
                logs,
                "Starting reverse dependency calculations...",
                inverted=True,
            )

    def testGetEmergeFlags(self):
        """Test building the emerge flags."""
        # Test the default config.
        instance = sysroot.BuildPackagesRunConfig()

        flags = instance.GetEmergeFlags()

        self.assertIn("--with-test-deps", flags)
        self.assertIn("--getbinpkg", flags)
        self.assertIn("--with-bdeps", flags)
        self.assertIn("--usepkg", flags)

        # Test when use_any_chrome is specified.
        instance = sysroot.BuildPackagesRunConfig(use_any_chrome=True)

        flags = instance.GetEmergeFlags()

        self.assertIn(
            "--force-remote-binary=chromeos-base/chromeos-chrome", flags
        )
        self.assertIn("--force-remote-binary=chromeos-base/chrome-icu", flags)

        # Test when usepkgonly is specified.
        instance = sysroot.BuildPackagesRunConfig(usepkgonly=True)

        flags = instance.GetEmergeFlags()

        self.assertIn("--usepkgonly", flags)

        # Test when jobs is specified.
        instance = sysroot.BuildPackagesRunConfig(jobs=10)

        flags = instance.GetEmergeFlags()

        self.assertIn("--jobs=10", flags)


class BuildPackagesTest(
    cros_test_lib.RunCommandTestCase, cros_test_lib.LoggingTestCase
):
    """Test BuildPackages function."""

    @pytest.fixture(autouse=True)
    def ignore_telemetry_collection(self, monkeypatch):
        """Mock OpenTelemetry library functions as necessary."""
        # pylint: disable=unnecessary-lambda
        monkeypatch.setattr(
            otel_context, "get_current", lambda: otel_context.Context()
        )
        monkeypatch.setattr(
            trace,
            "get_current_span",
            lambda: trace.NonRecordingSpan(otel_context.get_current()),
        )

    def setUp(self):
        # Currently just used to keep the parallel emerge status file from being
        # created in the chroot. This probably isn't strictly necessary, but
        # since we can otherwise run this test without a chroot existing at all
        # and without touching the chroot folder, it's better to keep it out of
        # there all together.
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)

        self.board = "board"
        self.target = build_target_lib.BuildTarget(self.board)
        self.sysroot = sysroot_lib.Sysroot(self.target.root)
        self.build_target_name_mock = self.PatchObject(
            sysroot_lib.Sysroot, "build_target_name", return_value=self.board
        )

        self.base_command = [
            constants.CHROMITE_BIN_DIR / "parallel_emerge",
            f"--sysroot={self.sysroot.path}",
            f"--root={self.sysroot.path}",
        ]

        # Prevent the test from switching the cpu governor.
        self.PatchObject(cpupower_helper, "ModifyCpuGovernor")
        # Prevent the test from remove files in the system.
        self.PatchObject(cros_build_lib, "ClearShadowLocks")
        self.portageq_envvar_mock = self.PatchObject(
            portage_util, "PortageqEnvvar", return_value="gs://fake/binhost"
        )
        self.PatchObject(portage_util, "RegenDependencyCache")
        self.installed_packages_mock = self.PatchObject(
            portage_util.PortageDB, "InstalledPackages"
        )
        self.clean_outdated_binpkgs_mock = self.PatchObject(
            portage_util, "CleanOutdatedBinaryPackages"
        )
        # Prevent the test from performing gsutil actions.
        self.get_creation_time_since_mock = self.PatchObject(
            gs.GSContext,
            "GetCreationTimeSince",
            return_value=datetime.timedelta(days=10),
        )
        self.PatchObject(gs.GSContext, "InitializeCache")

    def testSuccess(self):
        """Test successful run."""
        config = sysroot.BuildPackagesRunConfig()
        self.PatchObject(
            config, "GetForceLocalBuildPackages", return_value=["test/package1"]
        )
        sdk_pkgs = " ".join(
            sysroot._CRITICAL_SDK_PACKAGES  # pylint: disable=protected-access
        )

        with cros_test_lib.LoggingCapturer() as logs:
            sysroot.BuildPackages(self.target, self.sysroot, config)

            # The rest of the command's args we test in
            # BuildPackagesRunConfigTest, so just make sure we're calling the
            # right command and pass the args not handled by the run config.
            self.assertCommandContains(self.base_command)
            self.assertCommandContains(
                [
                    "--reinstall-atoms=test/package1",
                    "--usepkg-exclude=test/package1",
                ]
            )
            self.assertCommandContains(
                [
                    f"--useoldpkg-atoms={sdk_pkgs}",
                    f"--rebuild-exclude={sdk_pkgs}",
                ]
            )

            # Verify the extra environment variables are passed correctly.
            self.assertCommandContains([f"PKGDIR={self.sysroot.path}/packages"])

            # Check and the logs contain the expected output.
            self.AssertLogsContain(logs, "PORTAGE_BINHOST")
            self.AssertLogsContain(logs, "Rebuilding Portage cache.")
            self.AssertLogsContain(logs, "Cleaning stale binpkgs.")
            self.AssertLogsContain(logs, "Merging board packages now.")

    def testLogBinhostAgeThresholds(self):
        """Test the log output from _LogBinhostAge with different thresholds."""
        config = sysroot.BuildPackagesRunConfig()

        with cros_test_lib.LoggingCapturer() as logs:
            # check for when the binhost was created within the threshold
            sysroot.BuildPackages(self.target, self.sysroot, config)
            self.get_creation_time_since_mock.assert_called_with(
                path="gs://fake/binhost/Packages", since_date=mock.ANY
            )
            self.AssertLogsContain(
                logs,
                "PORTAGE_BINHOST gs://fake/binhost was created 10 days ago.",
            )

            # check for when the binhost was created outside of the threshold
            self.get_creation_time_since_mock.return_value = datetime.timedelta(
                days=31
            )
            sysroot.BuildPackages(self.target, self.sysroot, config)
            self.AssertLogsContain(
                logs,
                "PORTAGE_BINHOST gs://fake/binhost was created more"
                " than 30 days ago. Please repo sync for the latest build"
                " artifacts.",
            )
            self.AssertLogsContain(
                logs,
                "PORTAGE_BINHOST gs://fake/binhost was created 31 days ago.",
            )

    def testLogBinHostAgeUrls(self):
        """Test the log output from _LogBinhostAge with different binhosts."""
        config = sysroot.BuildPackagesRunConfig()

        with cros_test_lib.LoggingCapturer() as logs:
            # check that the gs url is formatted correctly when the binhost
            # has a trailing slash
            self.portageq_envvar_mock.return_value = "gs://fake/binhost/"
            sysroot.BuildPackages(self.target, self.sysroot, config)
            self.get_creation_time_since_mock.assert_called_with(
                path="gs://fake/binhost/Packages", since_date=mock.ANY
            )
            self.AssertLogsContain(
                logs,
                "PORTAGE_BINHOST gs://fake/binhost/ was created 10 days ago.",
            )

            # check for when there is a GSNoSuchKey error for a malformed
            # binhost url
            self.get_creation_time_since_mock.side_effect = gs.GSNoSuchKey(
                "Err"
            )
            sysroot.BuildPackages(self.target, self.sysroot, config)
            self.AssertLogsContain(
                logs,
                "PORTAGE_BINHOST gs://fake/binhost/",
            )
            self.AssertLogsContain(
                logs,
                "Error getting the binhost age",
            )

    def testPackageIndexes(self):
        """Test that package_indexes are passed to portage."""
        pkg_indexes = [
            binpkg.PackageIndexInfo(
                build_target=build_target_lib.BuildTarget("board"),
                snapshot_sha="A",
                location="gs://AAAA",
            ),
            binpkg.PackageIndexInfo(
                build_target=build_target_lib.BuildTarget("board"),
                snapshot_sha="B",
                location="gs://BBBB",
            ),
            binpkg.PackageIndexInfo(
                build_target=build_target_lib.BuildTarget("board"),
                snapshot_sha="C",
                location="gs://fake/binhost",
            ),
        ]
        config = sysroot.BuildPackagesRunConfig(package_indexes=pkg_indexes)

        sysroot.BuildPackages(self.target, self.sysroot, config)

        self.assertCommandContains(
            ["PORTAGE_BINHOST=gs://fake/binhost gs://AAAA gs://BBBB"]
        )

    def testEcleanBinpkgs(self):
        """Test that eclean is called with the expected packages."""

        def assert_file_contents(
            sysroot_path: Union[str, os.PathLike],
            deep: bool,
            exclusion_file: Optional[Union[str, os.PathLike]] = None,
        ):
            if exclusion_file:
                contents = osutils.ReadFile(exclusion_file)
                self.assertEqual("cross-dev/package", contents)

            self.assertEqual(self.sysroot.path, sysroot_path)
            self.assertTrue(deep)

        self.PatchObject(os.path, "exists", return_value=True)
        self.installed_packages_mock.return_value = [
            portage_util.InstalledPackage(None, "", "test", "package-1.0"),
            portage_util.InstalledPackage(None, "", "cross-dev", "package-1.0"),
        ]
        self.clean_outdated_binpkgs_mock.side_effect = assert_file_contents
        config = sysroot.BuildPackagesRunConfig()

        sysroot.BuildPackages(self.target, self.sysroot, config)

    def testInstallDebugSymbols(self):
        """Test cros_install_debug_syms is called with the expected args."""
        config = sysroot.BuildPackagesRunConfig(install_debug_symbols=True)

        with cros_test_lib.LoggingCapturer() as logs:
            sysroot.BuildPackages(self.target, self.sysroot, config)

            self.assertCommandContains(
                [
                    constants.CHROMITE_BIN_DIR / "cros_install_debug_syms",
                    f"--board={self.build_target_name_mock}",
                    "--all",
                ]
            )
            self.AssertLogsContain(logs, "Fetching the debug symbols.")

    def testPackageFailure(self):
        """Test package failure handling."""
        failed = ["cat/pkg", "foo/bar"]
        cpvs = [package_info.SplitCPV(p, strict=False) for p in failed]
        self.PatchObject(
            portage_util, "ParseDieHookStatusFile", return_value=cpvs
        )
        config = sysroot.BuildPackagesRunConfig()

        self.rc.AddCmdResult(
            partial_mock.ListRegex("emerge.*--useoldpkg-atoms"), returncode=1
        )
        with self.assertRaises(sysroot_lib.PackageInstallError) as e:
            sysroot.BuildPackages(self.target, self.sysroot, config)
        self.assertEqual(cpvs, e.exception.failed_packages)
        self.assertCommandContains(self.base_command)


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

        # If a file size is given, force that to be the minimum file size.
        # Create a sparse file so large files are practical.
        with open(filename, "w+b") as f:
            f.truncate(size)
            f.seek(0)
            f.write(content.encode("utf-8"))

    def test_ListOutputOfGatherSymbolFiles(self):
        """Mimic how the controller materializes output of GatherSymbolFiles."""
        # Create directory with some symbol files.
        tar_tmp_dir = os.path.join(self.tempdir, "tar_tmp")
        output_dir = os.path.join(self.tempdir, "output")
        input_dir = os.path.join(self.tempdir, "input")
        osutils.SafeMakedirs(output_dir)
        self.createSymbolFile(os.path.join(input_dir, "a/b/c/file1.sym"))
        self.createSymbolFile(os.path.join(input_dir, "a/b/c/d/file2.sym"))
        self.createSymbolFile(os.path.join(input_dir, "a/file3.sym"))
        self.createSymbolFile(os.path.join(input_dir, "a/b/c/d/e/file1.sym"))

        # Call sysroot.GatherSymbolFiles to find symbol files under self.tempdir
        # and copy them to output_dir.
        symbol_files = list(
            sysroot.GatherSymbolFiles(tar_tmp_dir, output_dir, [input_dir])
        )
        self.assertEqual(len(symbol_files), 4)

    def test_GatherSymbolFiles(self):
        """Test that files are found and copied."""
        # Create directory with some symbol files.
        tar_tmp_dir = os.path.join(self.tempdir, "tar_tmp")
        output_dir = os.path.join(self.tempdir, "output")
        input_dir = os.path.join(self.tempdir, "input")
        osutils.SafeMakedirs(output_dir)
        self.createSymbolFile(os.path.join(input_dir, "a/b/c/file1.sym"))
        self.createSymbolFile(os.path.join(input_dir, "a/b/c/d/file2.sym"))
        self.createSymbolFile(os.path.join(input_dir, "a/file3.sym"))
        self.createSymbolFile(os.path.join(input_dir, "a/b/c/d/e/file1.sym"))

        # Call sysroot.GatherSymbolFiles to find symbol files under self.tempdir
        # and copy them to output_dir.
        symbol_files = list(
            sysroot.GatherSymbolFiles(tar_tmp_dir, output_dir, [input_dir])
        )

        # Construct the expected symbol files. Note that the SymbolFileTuple
        # field source_file_name is the full path to where a symbol file was
        # found, while relative_path is the relative path (from the search)
        # where it is created in the output directory.
        expected_symbol_files = [
            sysroot.SymbolFileTuple(
                source_file_name=os.path.join(input_dir, "a/b/c/file1.sym"),
                relative_path="a/b/c/file1.sym",
            ),
            sysroot.SymbolFileTuple(
                source_file_name=os.path.join(input_dir, "a/b/c/d/file2.sym"),
                relative_path="a/b/c/d/file2.sym",
            ),
            sysroot.SymbolFileTuple(
                source_file_name=os.path.join(input_dir, "a/file3.sym"),
                relative_path="a/file3.sym",
            ),
            sysroot.SymbolFileTuple(
                source_file_name=os.path.join(input_dir, "a/b/c/d/e/file1.sym"),
                relative_path="a/b/c/d/e/file1.sym",
            ),
        ]

        # Sort symbol_files and expected_output_files by the relative_path
        # attribute.
        symbol_files = sorted(
            symbol_files, key=operator.attrgetter("relative_path")
        )
        expected_symbol_files = sorted(
            expected_symbol_files, key=operator.attrgetter("relative_path")
        )
        # Compare the files to the expected files. This verifies the size and
        # contents, and on failure shows the full contents.
        self.assertEqual(symbol_files, expected_symbol_files)

        # Verify that the files in output_dir match the SymbolFile
        # relative_paths.
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
        output_dir = os.path.join(self.tempdir, "output")
        osutils.SafeMakedirs(output_dir)

        # Set up test input directory.
        tarball_dir = os.path.join(self.tempdir, "some/path")
        files_in_tarball = [
            "dir1/fileZ.sym",
            "dir2/fileY.sym",
            "dir2/fileX.sym",
            "fileA.sym",
            "fileB.sym",
            "fileC.sym",
        ]
        for filename in files_in_tarball:
            self.createSymbolFile(os.path.join(tarball_dir, filename))
        temp_tarball_file_path = os.path.join(self.tempdir, "symfiles.tar")
        cros_build_lib.CreateTarball(temp_tarball_file_path, tarball_dir)
        # Now that we've created the tarball, remove the .sym files in
        # the tarball dir and move the tarball to that dir.
        for filename in files_in_tarball:
            os.remove(os.path.join(tarball_dir, filename))
        tarball_path = os.path.join(tarball_dir, "symfiles.tar")
        shutil.move(temp_tarball_file_path, tarball_path)

        # Execute sysroot.GatherSymbolFiles where the path contains the tarball.
        symbol_files = list(
            sysroot.GatherSymbolFiles(tarball_dir, output_dir, [tarball_path])
        )

        self.assertEqual(len(symbol_files), 6)
        # Verify the symbol_file relative_paths.
        symbol_file_relative_paths = [obj.relative_path for obj in symbol_files]
        symbol_file_relative_paths.sort()
        self.assertEqual(
            symbol_file_relative_paths,
            [
                "dir1/fileZ.sym",
                "dir2/fileX.sym",
                "dir2/fileY.sym",
                "fileA.sym",
                "fileB.sym",
                "fileC.sym",
            ],
        )
        # Verify the symbol_file source_file_names.
        symbol_file_source_file_names = [
            obj.source_file_name for obj in symbol_files
        ]
        symbol_file_source_file_names.sort()
        # Note that the expected symbol_file_source_names are the full path to
        # the tarfile followed by the relative path, such as
        # /tmp/chromite.test2ng92vzo/some/path/symfiles.tar/dir1/fileZ.sym
        expected_symbol_file_source_names = [
            os.path.join(tarball_path, "dir1/fileZ.sym"),
            os.path.join(tarball_path, "dir2/fileX.sym"),
            os.path.join(tarball_path, "dir2/fileY.sym"),
            os.path.join(tarball_path, "fileA.sym"),
            os.path.join(tarball_path, "fileB.sym"),
            os.path.join(tarball_path, "fileC.sym"),
        ]
        self.assertEqual(
            symbol_file_source_file_names, expected_symbol_file_source_names
        )

        # Verify that the files in output_dir match the SymbolFile
        # relative_paths.
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
        output_dir = os.path.join(self.tempdir, "output")
        osutils.SafeMakedirs(output_dir)

        # Set up test input directory.
        tarball_dir = os.path.join(self.tempdir, "some/path")
        files_in_tarball = [
            "dir1/fileU.sym",
            "dir1/fileU.txt",
            "fileD.sym",
            "fileD.txt",
        ]
        for filename in files_in_tarball:
            # we don't care about file contents, so we are using
            # createSymbolFile for files whether they end with .sym or not.
            self.createSymbolFile(os.path.join(tarball_dir, filename))
        temp_tarball_file_path = os.path.join(self.tempdir, "symfiles.tar")
        cros_build_lib.CreateTarball(temp_tarball_file_path, tarball_dir)
        # Now that we've created the tarball, remove the .sym files in
        # the tarball dir and move the tarball to that dir.
        for filename in files_in_tarball:
            os.remove(os.path.join(tarball_dir, filename))
        tarball_path = os.path.join(tarball_dir, "symfiles.tar")
        shutil.move(temp_tarball_file_path, tarball_path)

        # Execute sysroot.GatherSymbolFiles where the path contains the tarball.
        symbol_files = list(
            sysroot.GatherSymbolFiles(tarball_dir, output_dir, [tarball_path])
        )

        # Verify the symbol_file relative_paths only has .sym files.
        symbol_file_relative_paths = [obj.relative_path for obj in symbol_files]
        symbol_file_relative_paths.sort()
        self.assertEqual(
            symbol_file_relative_paths, ["dir1/fileU.sym", "fileD.sym"]
        )
        for symfile in symbol_file_relative_paths:
            extension = symfile.split(".")[1]
            self.assertEqual(extension, "sym")

    def test_GatherSymbolFileFullFilePaths(self):
        """Test full filepaths (.sym and .txt) only gather .sym files."""
        tar_tmp_dir = os.path.join(self.tempdir, "tar_tmp")
        output_dir = os.path.join(self.tempdir, "output")
        input_dir = os.path.join(self.tempdir, "input")
        osutils.SafeMakedirs(output_dir)
        # We don't care about contents, so use createSymbolFiles for all files.
        self.createSymbolFile(os.path.join(input_dir, "a_file.sym"))
        self.createSymbolFile(os.path.join(input_dir, "a_file.txt"))

        # Call sysroot.GatherSymbolFiles with full paths to files, some of which
        # don't end in .sym, verify that only .sym files get copied to
        # output_dir.
        symbol_files = list(
            sysroot.GatherSymbolFiles(
                tar_tmp_dir,
                output_dir,
                [
                    os.path.join(input_dir, "a_file.sym"),
                    os.path.join(input_dir, "a_file.txt"),
                ],
            )
        )

        # Construct the expected symbol files. Note that the SymbolFileTuple
        # field source_file_name is the full path to where a symbol file was
        # found, while relative_path is the relative path (from the search)
        # where it is created in the output directory.
        expected_symbol_files = [
            sysroot.SymbolFileTuple(
                source_file_name=os.path.join(input_dir, "a_file.sym"),
                relative_path="a_file.sym",
            )
        ]

        # Compare the files to the expected files. This verifies the size and
        # contents, and on failure shows the full contents.
        self.assertEqual(symbol_files, expected_symbol_files)
        # Verify that only a_file.sym is in the output_dir.
        files_in_output_dir = self.getFilesWithRelativeDir(output_dir)
        self.assertEqual(files_in_output_dir, ["a_file.sym"])

    def getFilesWithRelativeDir(self, dest_dir):
        """Find all files below dest_dir using dir relative to dest_dir."""
        relative_files = []
        for path, __, files in os.walk(dest_dir):
            for filename in files:
                fullpath = os.path.join(path, filename)
                relpath = os.path.relpath(fullpath, dest_dir)
                relative_files.append(relpath)
        return relative_files


class GenerateBreakpadSymbolsTest(cros_test_lib.RunCommandTempDirTestCase):
    """Base class for testing GenerateBreakpadSymbols."""

    def setUp(self):
        self.chroot_dir = os.path.join(self.tempdir, "chroot_dir")
        osutils.SafeMakedirs(self.chroot_dir)

    def test_generateBreakpadSymbols(self):
        """Verify calling the service layer invokes the script as expected."""
        chroot = chroot_lib.Chroot(self.chroot_dir)
        build_target = build_target_lib.BuildTarget("board")

        # Call the method being tested.
        sysroot.GenerateBreakpadSymbols(chroot, build_target, False, False, [])

        self.rc.assertCommandContains(
            [
                "cros_generate_breakpad_symbols",
                "--board=board",
                "--jobs",
                mock.ANY,
                "--exclude-dir=firmware",
            ],
            enter_chroot=True,
            chroot_args=["--chroot", mock.ANY],
        )

    def test_generateBreakpadSymbolsWithDebug(self):
        """Verify that calling with debug invokes the script as expected."""
        chroot = chroot_lib.Chroot(self.chroot_dir)
        build_target = build_target_lib.BuildTarget("board")

        # Call the method being tested.
        sysroot.GenerateBreakpadSymbols(chroot, build_target, True, False, [])

        self.rc.assertCommandContains(
            [
                "cros_generate_breakpad_symbols",
                "--debug",
                "--board=board",
                "--jobs",
                mock.ANY,
                "--exclude-dir=firmware",
            ],
            enter_chroot=True,
            chroot_args=["--chroot", mock.ANY],
        )

    def test_generateBreakpadSymbolsWithIgnoreErrors(self):
        """Verify that calling with debug invokes the script as expected."""
        chroot = chroot_lib.Chroot(self.chroot_dir)
        build_target = build_target_lib.BuildTarget("board")

        # Call the method being tested.
        sysroot.GenerateBreakpadSymbols(chroot, build_target, False, True, [])

        self.rc.assertCommandContains(
            [
                "cros_generate_breakpad_symbols",
                "--ignore_errors",
                "--board=board",
                "--jobs",
                mock.ANY,
                "--exclude-dir=firmware",
            ],
            enter_chroot=True,
            chroot_args=["--chroot", mock.ANY],
        )

    def test_generateBreakpadSymbolsWithIgnoreIgnoreExpectedFiles(self):
        """Verify that calling with debug invokes the script as expected."""
        chroot = chroot_lib.Chroot(self.chroot_dir)
        build_target = build_target_lib.BuildTarget("board")

        # Call the method being tested.
        sysroot.GenerateBreakpadSymbols(
            chroot, build_target, False, False, ["ASH_CHROME", "LIBC"]
        )

        self.rc.assertCommandContains(
            [
                "cros_generate_breakpad_symbols",
                "--ignore_expected_file=ASH_CHROME",
                "--ignore_expected_file=LIBC",
                "--board=board",
                "--jobs",
                mock.ANY,
                "--exclude-dir=firmware",
            ],
            enter_chroot=True,
            chroot_args=["--chroot", mock.ANY],
        )


class BundleDebugSymbolsTest(cros_test_lib.MockTempDirTestCase):
    """Unittests for BundleDebugSymbols."""

    def setUp(self):
        # Configure {chroot,out,syroot}_path.
        self.chroot_path = os.path.join(self.tempdir, "chroot_dir")
        self.out_path = self.tempdir / "out_dir"
        self.sysroot_path = os.path.join(self.chroot_path, "build/target")

        # Has to be run outside the chroot.
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        osutils.SafeMakedirs(self.sysroot_path)

        # Create output dir.
        self.output_dir = os.path.join(self.tempdir, "output_dir")
        osutils.SafeMakedirs(self.output_dir)

        # Create chroot, sysroot, and build_target objs.
        self.chroot = chroot_lib.Chroot(
            path=self.chroot_path, out_path=self.out_path
        )
        self.sysroot = sysroot_lib.Sysroot(path=self.sysroot_path)
        self.build_target = build_target_lib.BuildTarget("target")

        # Create the tmp dir.
        osutils.SafeMakedirs(self.chroot.tmp)

    def testBundleBreakpadDebugSymbols(self):
        """BundleBreakpadSymbols calls cbuildbot/commands with correct args."""
        # Patch service layer functions.
        generate_breakpad_symbols_patch = self.PatchObject(
            sysroot,
            "GenerateBreakpadSymbols",
            return_value=cros_build_lib.CompletedProcess(
                returncode=0, stdout=""
            ),
        )
        gather_symbol_files_patch = self.PatchObject(
            sysroot,
            "GatherSymbolFiles",
            return_value=[
                sysroot.SymbolFileTuple(
                    source_file_name="path/to/source/file1.sym",
                    relative_path="file1.sym",
                )
            ],
        )

        tar_file = sysroot.BundleBreakpadSymbols(
            self.chroot,
            self.sysroot,
            self.build_target,
            self.output_dir,
            False,
            ["ASH_CHROME"],
        )

        # Verify mock objects were called.
        generate_breakpad_symbols_patch.assert_called_with(
            self.chroot,
            self.build_target,
            debug=True,
            ignore_errors=False,
            ignore_expected_files=["ASH_CHROME"],
        )
        gather_symbol_files_patch.assert_called()

        # Verify response proto contents and output directory contents.
        self.assertIsNotNone(tar_file)
        self.assertTrue(tar_file.endswith("/output_dir/debug_breakpad.tar.xz"))

    def testBundleDebugSymbols(self):
        """BundleDebugSymbols calls cbuildbot/commands with correct args."""
        # Patch service layer functions.
        self.PatchObject(os.path, "exists", return_value=True)
        self.PatchObject(os.path, "isdir", return_value=True)

        create_tarball_patch = self.PatchObject(
            cros_build_lib,
            "CreateTarball",
            return_value=cros_build_lib.CompletedProcess(
                returncode=0, stdout=""
            ),
        )

        tar_file = sysroot.BundleDebugSymbols(
            self.chroot,
            self.sysroot,
            build_target_lib.BuildTarget(None),
            self.output_dir,
        )
        create_tarball_patch.assert_called()

        # Verify response contents.
        self.assertIsNotNone(tar_file)
        self.assertTrue(tar_file.endswith("/output_dir/debug.tgz"))


def test_CollectBazelPerformanceArtifacts(monkeypatch, tmp_path):
    """CollectBazelPerformanceArtifacts copies the known set of files."""
    # Configure {chroot,out,syroot}_path.
    tempdir = tmp_path
    chroot_path = tempdir / "chroot_dir"
    out_path = tempdir / "out_dir"
    sysroot_path = chroot_path / "build" / "target"

    # Simulate being outside the chroot.
    monkeypatch.setattr(cros_build_lib, "IsInsideChroot", lambda: False)

    osutils.SafeMakedirs(sysroot_path)

    # Create output dir.
    output_dir = os.path.join(tempdir, "output_dir")
    osutils.SafeMakedirs(output_dir)

    # Create chroot, sysroot, and build_target objs.
    chroot = chroot_lib.Chroot(path=chroot_path, out_path=out_path)
    target_sysroot = sysroot_lib.Sysroot(path=sysroot_path)
    build_target = build_target_lib.BuildTarget("target")

    # Create Bazel performance files for testing
    sysroot_bazel_files = (
        sysroot.BAZEL_APPCRYPTNSS_COMMAND_PROFILE_FILE,
        sysroot.BAZEL_APPCRYPTNSS_EXEC_LOG_FILE,
        sysroot.BAZEL_ALLPACKAGES_COMMAND_PROFILE_FILE,
        sysroot.BAZEL_ALLPACKAGES_EXEC_LOG_FILE,
    )
    created_files = [
        chroot.full_path(artifact) for artifact in sysroot_bazel_files
    ]
    for created_file in created_files:
        osutils.Touch(created_file, makedirs=True)

    expected_files = [
        tempdir / os.path.basename(file) for file in sysroot_bazel_files
    ]

    # Collect the files and confirm we got what we expected
    archived_files = sysroot.CollectBazelPerformanceArtifacts(
        chroot,
        target_sysroot,
        build_target,
        tempdir,
    )
    for expected_file in expected_files:
        assert str(expected_file) in archived_files
        assert expected_file.exists()


class RemoteExecutionTest(cros_test_lib.MockLoggingTestCase):
    """Unittests for remote execution context manager."""

    def setUp(self):
        self.goma_mock = self.PatchObject(goma_lib, "Goma", autospec=True)
        self.goma_instance = self.goma_mock.return_value
        self.remoteexec_mock = self.PatchObject(remoteexec_util, "Remoteexec")
        self.remoteexec_instance = self.remoteexec_mock.return_value

    def testGomaDir(self):
        """Test the case where GOMA env variable is defined."""
        os.environ.update(
            {
                "GOMA_DIR": "goma/path",
                "GOMA_TMP_DIR": "goma/tmp/dir",
                "GLOG_log_dir": "glog/log/dir",
            }
        )

        with sysroot.RemoteExecution(use_goma=True, use_remoteexec=False):
            self.goma_mock.assert_called_once_with(
                Path("goma/path"),
                "goma/tmp/dir",
                stage_name="BuildPackages",
                log_dir="glog/log/dir",
            )
        self.goma_instance.Restart.assert_called_once()
        self.goma_instance.Stop.assert_called_once()
        self.remoteexec_mock.assert_not_called()

    def testGomaHomeDir(self):
        """Test the case where Home Path is used."""
        self.PatchObject(Path, "home", return_value=Path("home"))

        with sysroot.RemoteExecution(use_goma=True, use_remoteexec=False):
            self.goma_mock.assert_called_once_with(
                Path("home/goma"),
                None,
                stage_name="BuildPackages",
                log_dir=None,
            )
        self.goma_instance.Restart.assert_called_once()
        self.goma_instance.Stop.assert_called_once()
        self.remoteexec_mock.assert_not_called()

    def testGomaException(self):
        """Test the case where GOMA interface raises exception."""
        self.goma_mock.side_effect = ValueError()

        with cros_test_lib.LoggingCapturer() as log:
            with sysroot.RemoteExecution(use_goma=True, use_remoteexec=False):
                self.AssertLogsMatch(log, ".*initialization error.*")
        self.goma_instance.Restart.assert_not_called()
        self.goma_instance.Stop.assert_not_called()
        self.remoteexec_mock.assert_not_called()

    def testRemoteExec(self):
        """Test the case where remoteexec env variables are defined."""
        os.environ.update(
            {
                "RECLIENT_DIR": "reclient/path",
                "REPROXY_CFG": "reclient_cfg",
            }
        )

        with sysroot.RemoteExecution(use_goma=False, use_remoteexec=True):
            self.remoteexec_mock.assert_called_once_with(
                "reclient/path", "reclient_cfg"
            )
        self.remoteexec_instance.Start.assert_called_once()
        self.remoteexec_instance.Stop.assert_called_once()
        self.goma_mock.assert_not_called()

    def testRemoteExecNoEnv(self):
        """Test the case where remoteexec env variables are not defined."""
        with sysroot.RemoteExecution(use_goma=False, use_remoteexec=True):
            pass
        self.remoteexec_mock.assert_not_called()
        self.goma_mock.assert_not_called()

    def testRemoteExecException(self):
        """Test the case where remoteexec raises exception."""
        os.environ.update(
            {
                "RECLIENT_DIR": "reclient/path",
                "REPROXY_CFG": "reclient_cfg",
            }
        )
        self.remoteexec_mock.side_effect = ValueError()

        with cros_test_lib.LoggingCapturer() as log:
            with sysroot.RemoteExecution(use_goma=False, use_remoteexec=True):
                self.AssertLogsMatch(log, ".*initialization error.*")
        self.remoteexec_instance.Start.assert_not_called()
        self.remoteexec_instance.Stop.assert_not_called()
        self.goma_mock.assert_not_called()

    def testNoRemoteExec(self):
        """Test the case where no remoteexec is requested with env variable."""
        os.environ.update(
            {
                "RECLIENT_DIR": "reclient/path",
                "REPROXY_CFG": "reclient_cfg",
                "GOMA_DIR": "goma/path",
            }
        )

        with sysroot.RemoteExecution(use_goma=False, use_remoteexec=False):
            pass
        self.remoteexec_mock.assert_not_called()
        self.goma_mock.assert_not_called()

    def testNoRemoteExecNoEnv(self):
        """Test case where no remoteexec is requested without env variable."""
        with sysroot.RemoteExecution(use_goma=False, use_remoteexec=False):
            pass
        self.remoteexec_mock.assert_not_called()
        self.goma_mock.assert_not_called()


class ArchiveSysrootTest(cros_test_lib.TempDirTestCase):
    """ArchiveSysroot tests."""

    def setUp(self):
        chroot_path = self.tempdir / "chroot"
        self.chroot = chroot_lib.Chroot(path=chroot_path)
        sysroot_path = chroot_path / "build" / "testBoard"
        self.sysroot = sysroot_lib.Sysroot(sysroot_path)
        self.dir_structure = [
            cros_test_lib.Directory(".", []),
            cros_test_lib.Directory("test", ["foo.bar"]),
        ]

    def testArchiveSysroot(self):
        """Archive a sample folder and verify its contents."""
        cros_test_lib.CreateOnDiskHierarchy(
            self.chroot.full_path(self.sysroot.path), self.dir_structure
        )

        archive_file = sysroot.ArchiveSysroot(
            self.chroot,
            self.sysroot,
            build_target_lib.BuildTarget("testBoard"),
            self.tempdir,
        )
        self.assertTrue(Path(archive_file).exists())
        self.assertEqual(
            archive_file, self.tempdir / sysroot.SYSROOT_ARCHIVE_FILE
        )
        cros_test_lib.VerifyTarball(archive_file, self.dir_structure)

    def testArchiveSysrootFailure(self):
        """Archive a sample folder that doesnt exists."""
        archive_file = sysroot.ArchiveSysroot(
            self.chroot,
            self.sysroot,
            build_target_lib.BuildTarget("testBoard"),
            self.tempdir,
        )
        self.assertIsNone(archive_file)
