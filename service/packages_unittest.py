# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Packages service tests."""

import io
import json
import os
import re
from unittest import mock

from chromite.third_party.google.protobuf import field_mask_pb2
from chromite.third_party.google.protobuf import json_format
import pytest

import chromite as cr
from chromite.api.gen.config import replication_config_pb2
from chromite.lib import build_target_lib
from chromite.lib import chromeos_version
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import dependency_graph
from chromite.lib import depgraph
from chromite.lib import osutils
from chromite.lib import partial_mock
from chromite.lib import portage_util
from chromite.lib import uprev_lib
from chromite.lib.parser import package_info
from chromite.service import android
from chromite.service import dependency
from chromite.service import packages


D = cros_test_lib.Directory
FILE_TYPE_JSON = replication_config_pb2.FILE_TYPE_JSON
FileReplicationRule = replication_config_pb2.FileReplicationRule
REPLICATION_TYPE_FILTER = replication_config_pb2.REPLICATION_TYPE_FILTER
ReplicationConfig = replication_config_pb2.ReplicationConfig


class UprevAndroidTest(cros_test_lib.RunCommandTestCase):
    """Uprev android tests."""

    def _mock_successful_uprev(self):
        self.rc.AddCmdResult(
            partial_mock.In("cros_mark_android_as_stable"),
            stdout=(
                '{"revved": true,'
                ' "android_atom": "android/android-1.0",'
                ' "modified_files": ["file1", "file2"]}'
            ),
        )

    def test_success(self):
        """Test successful run handling."""
        self._mock_successful_uprev()
        build_targets = [
            build_target_lib.BuildTarget(t) for t in ["foo", "bar"]
        ]

        result = packages.uprev_android(
            "android/package", chroot_lib.Chroot(), build_targets=build_targets
        )
        self.assertCommandContains(
            [
                "cros_mark_android_as_stable",
                "--android_package=android/package",
                "--boards=foo bar",
            ]
        )
        self.assertCommandContains(["emerge-foo"])
        self.assertCommandContains(["emerge-bar"])

        self.assertTrue(result.revved)
        self.assertEqual(result.android_atom, "android/android-1.0")
        self.assertListEqual(result.modified_files, ["file1", "file2"])

    def test_android_build_branch(self):
        """Test specifying android_build_branch option."""
        self._mock_successful_uprev()

        packages.uprev_android(
            "android/package",
            chroot_lib.Chroot(),
            android_build_branch="android-build-branch",
        )
        self.assertCommandContains(
            [
                "cros_mark_android_as_stable",
                "--android_package=android/package",
                "--android_build_branch=android-build-branch",
            ]
        )

    def test_android_version(self):
        """Test specifying android_version option."""
        self._mock_successful_uprev()

        packages.uprev_android(
            "android/package", chroot_lib.Chroot(), android_version="7123456"
        )
        self.assertCommandContains(
            [
                "cros_mark_android_as_stable",
                "--android_package=android/package",
                "--force_version=7123456",
            ]
        )

    def test_skip_commit(self):
        """Test specifying skip_commit option."""
        self._mock_successful_uprev()

        packages.uprev_android(
            "android/package", chroot_lib.Chroot(), skip_commit=True
        )
        self.assertCommandContains(
            [
                "cros_mark_android_as_stable",
                "--android_package=android/package",
                "--skip_commit",
            ]
        )

    def test_no_uprev(self):
        """Test no uprev handling."""
        self.rc.AddCmdResult(
            partial_mock.In("cros_mark_android_as_stable"),
            stdout='{"revved": false}',
        )
        build_targets = [
            build_target_lib.BuildTarget(t) for t in ["foo", "bar"]
        ]
        result = packages.uprev_android(
            "android/package", chroot_lib.Chroot(), build_targets=build_targets
        )

        self.assertCommandContains(
            ["cros_mark_android_as_stable", "--boards=foo bar"]
        )
        self.assertCommandContains(["emerge-foo"], expected=False)
        self.assertCommandContains(["emerge-bar"], expected=False)

        self.assertFalse(result.revved)

    def test_ignore_junk_in_stdout(self):
        """Test when stdout contains junk messages."""
        self.rc.AddCmdResult(
            partial_mock.In("cros_mark_android_as_stable"),
            stdout='foo\nbar\n{"revved": false}\n',
        )
        result = packages.uprev_android("android/package", chroot_lib.Chroot())

        self.assertFalse(result.revved)


class UprevAndroidLKGBTest(cros_test_lib.MockTestCase):
    """Tests for uprevving Android with LKGB."""

    def test_registered_handlers(self):
        """Test that each Android package has an uprev handler registered."""
        mock_handler = self.PatchObject(packages, "uprev_android_lkgb")

        for android_package in android.GetAllAndroidPackages():
            cpv = package_info.SplitCPV(
                "chromeos-base/" + android_package, strict=False
            )
            build_targets = [build_target_lib.BuildTarget("foo")]
            chroot = chroot_lib.Chroot()

            packages.uprev_versioned_package(cpv, build_targets, [], chroot)

            mock_handler.assert_called_once_with(
                android_package, build_targets, chroot
            )
            mock_handler.reset_mock()

    def test_success(self):
        """Test a successful uprev."""
        self.PatchObject(android, "OVERLAY_DIR", new="overlay-dir")
        self.PatchObject(
            android, "ReadLKGB", return_value=dict(build_id="android-lkgb")
        )
        self.PatchObject(
            packages,
            "uprev_android",
            return_value=packages.UprevAndroidResult(
                revved=True,
                android_atom="android-atom",
                modified_files=["file1", "file2"],
            ),
        )

        result = packages.uprev_android_lkgb(
            "android-package", [], chroot_lib.Chroot()
        )

        self.assertListEqual(
            result.modified,
            [
                uprev_lib.UprevVersionedPackageModifications(
                    "android-lkgb",
                    [
                        os.path.join("overlay-dir", "file1"),
                        os.path.join("overlay-dir", "file2"),
                    ],
                )
            ],
        )

    def test_no_rev(self):
        """Test when nothing revved."""
        self.PatchObject(
            android, "ReadLKGB", return_value=dict(build_id="android-lkgb")
        )
        self.PatchObject(
            packages,
            "uprev_android",
            return_value=packages.UprevAndroidResult(revved=False),
        )

        result = packages.uprev_android_lkgb(
            "android-package", [], chroot_lib.Chroot()
        )

        self.assertListEqual(result.modified, [])


class UprevECUtilsTest(cros_test_lib.MockTestCase):
    """Tests for upreving ecutils."""

    def test_success(self):
        """Test a successful uprev."""

        def fakeRunTasks(func, inputs):
            results = []
            for args in inputs:
                results.append(func(*args))
            return results

        self.PatchObject(
            packages.uprev_lib.parallel,
            "RunTasksInProcessPool",
            side_effect=fakeRunTasks,
        )
        mock_devutils = mock.MagicMock(name="dev-utils")
        mock_ecutils = mock.MagicMock(name="ec-utils")
        mock_ecutilstest = mock.MagicMock(name="ec-utils-test")
        self.PatchObject(
            packages.uprev_lib.portage_util,
            "GetOverlayEBuilds",
            return_value=[
                mock_devutils,
                mock_ecutils,
                mock_ecutilstest,
            ],
        )
        mock_overlay_mgr = mock.MagicMock(name="overlay-manager")
        mock_overlay_mgr.modified_ebuilds = ["file1", "file2"]
        self.PatchObject(
            packages.uprev_lib,
            "UprevOverlayManager",
            return_value=mock_overlay_mgr,
        )

        for package in [
            "chromeos-base/ec-devutils",
            "chromeos-base/ec-utils",
            "chromeos-base/ec-utils-test",
        ]:
            cpv = package_info.SplitCPV(package, strict=False)
            assert cpv is not None
            build_targets = [build_target_lib.BuildTarget("foo")]
            refs = [
                uprev_lib.GitRef(
                    path="/platform/ec",
                    ref="main",
                    revision="123",
                )
            ]
            chroot = chroot_lib.Chroot()

            result = packages.uprev_versioned_package(
                cpv, build_targets, refs, chroot
            )

            self.assertEqual(1, len(result.modified))
            self.assertEqual("123", result.modified[0].new_version)
            self.assertListEqual(result.modified[0].files, ["file1", "file2"])

            mock_overlay_mgr.uprev.assert_called_with(
                package_list=[
                    package,
                ],
                force=True,
            )


class UprevBuildTargetsTest(cros_test_lib.RunCommandTestCase):
    """uprev_build_targets tests."""

    def test_invalid_type_fails(self):
        """Test invalid type fails."""
        with self.assertRaises(AssertionError):
            packages.uprev_build_targets(
                [build_target_lib.BuildTarget("foo")], "invalid"
            )

    def test_none_type_fails(self):
        """Test None type fails."""
        with self.assertRaises(AssertionError):
            packages.uprev_build_targets(
                [build_target_lib.BuildTarget("foo")], None
            )


class PatchEbuildVarsTest(cros_test_lib.MockTestCase):
    """patch_ebuild_vars test."""

    def setUp(self):
        self.mock_input = self.PatchObject(packages.fileinput, "input")
        self.mock_stdout_write = self.PatchObject(packages.sys.stdout, "write")
        self.ebuild_path = "/path/to/ebuild"
        self.old_var_value = "R100-5678.0.123456789"
        self.new_var_value = "R102-5678.0.234566789"

    def test_patch_ebuild_vars_var_only(self):
        """patch_ebuild_vars changes ^var=value$."""
        ebuild_contents = (
            "This line does not change.\n"
            'AFDO_PROFILE_VERSION="{var_value}"\n'
            "\n"
            "# The line with AFDO_PROFILE_VERSION is also unchanged."
        )
        # Ebuild contains old_var_value.
        self.mock_input.return_value = io.StringIO(
            ebuild_contents.format(var_value=self.old_var_value)
        )
        expected_calls = []
        # Expect the line with new_var_value.
        for line in io.StringIO(
            ebuild_contents.format(var_value=self.new_var_value)
        ):
            expected_calls.append(mock.call(line))

        packages.patch_ebuild_vars(
            self.ebuild_path, {"AFDO_PROFILE_VERSION": self.new_var_value}
        )

        self.mock_stdout_write.assert_has_calls(expected_calls)

    def test_patch_ebuild_vars_ignore_export(self):
        """patch_ebuild_vars changes ^export var=value$ and keeps export."""
        ebuild_contents = (
            "This line does not change.\n"
            'export AFDO_PROFILE_VERSION="{var_value}"\n'
            "# This line is also unchanged."
        )
        # Ebuild contains old_var_value.
        self.mock_input.return_value = io.StringIO(
            ebuild_contents.format(var_value=self.old_var_value)
        )
        expected_calls = []
        # Expect the line with new_var_value.
        for line in io.StringIO(
            ebuild_contents.format(var_value=self.new_var_value)
        ):
            expected_calls.append(mock.call(line))

        packages.patch_ebuild_vars(
            self.ebuild_path, {"AFDO_PROFILE_VERSION": self.new_var_value}
        )

        self.mock_stdout_write.assert_has_calls(expected_calls)

    def test_patch_ebuild_vars_partial_match(self):
        """patch_ebuild_vars ignores ^{prefix}var=value$."""
        ebuild_contents = (
            'This and the line below do not change.\nNEW_AFDO="{var_value}"'
        )
        # Ebuild contains old_var_value.
        self.mock_input.return_value = io.StringIO(
            ebuild_contents.format(var_value=self.old_var_value)
        )
        expected_calls = []
        # Expect the line with UNCHANGED old_var_value.
        for line in io.StringIO(
            ebuild_contents.format(var_value=self.old_var_value)
        ):
            expected_calls.append(mock.call(line))

        # Note that the var name partially matches the ebuild var and hence it
        # has to be ignored.
        packages.patch_ebuild_vars(
            self.ebuild_path, {"AFDO": self.new_var_value}
        )

        self.mock_stdout_write.assert_has_calls(expected_calls)

    def test_patch_ebuild_vars_no_vars(self):
        """patch_ebuild_vars keeps ebuild intact if there are no vars."""
        ebuild_contents = (
            "This line does not change.\n"
            "The line with AFDO_PROFILE_VERSION is also unchanged."
        )
        self.mock_input.return_value = io.StringIO(ebuild_contents)
        expected_calls = []
        for line in io.StringIO(ebuild_contents):
            expected_calls.append(mock.call(line))

        packages.patch_ebuild_vars(
            self.ebuild_path, {"AFDO_PROFILE_VERSION": self.new_var_value}
        )

        self.mock_stdout_write.assert_has_calls(expected_calls)


class UprevsVersionedPackageTest(cros_test_lib.MockTestCase):
    """uprevs_versioned_package decorator test."""

    @packages.uprevs_versioned_package("category/package")
    def uprev_category_package(self, *args, **kwargs):
        """Registered function for testing."""

    def test_calls_function(self):
        """Test calling a registered function."""
        self.PatchObject(self, "uprev_category_package")

        cpv = package_info.SplitCPV("category/package", strict=False)
        packages.uprev_versioned_package(cpv, [], [], chroot_lib.Chroot())

        # TODO(crbug/1065172): Invalid assertion that was previously mocked.
        # patch.assert_called()

    def test_unregistered_package(self):
        """Test calling with an unregistered package."""
        cpv = package_info.SplitCPV("does-not/exist", strict=False)

        with self.assertRaises(packages.UnknownPackageError):
            packages.uprev_versioned_package(cpv, [], [], chroot_lib.Chroot())


class UprevEbuildFromPinTest(cros_test_lib.RunCommandTempDirTestCase):
    """Tests uprev_ebuild_from_pin function"""

    package = "category/package"
    version = "1.2.3"
    new_version = "1.2.4"
    ebuild_template = "package-%s-r1.ebuild"
    ebuild = ebuild_template % version
    unstable_ebuild = "package-9999.ebuild"
    manifest = "Manifest"

    def test_uprev_ebuild(self):
        """Tests uprev of ebuild with version path"""
        file_layout = (
            D(self.package, [self.ebuild, self.unstable_ebuild, self.manifest]),
        )
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, file_layout)

        package_path = os.path.join(self.tempdir, self.package)

        ebuild_path = os.path.join(package_path, self.ebuild)
        self.WriteTempFile(ebuild_path, 'KEYWORDS="*"\n')

        result = uprev_lib.uprev_ebuild_from_pin(
            package_path, self.new_version, chroot=chroot_lib.Chroot()
        )
        self.assertEqual(
            len(result.modified),
            1,
            "unexpected number of results: %s" % len(result.modified),
        )

        mod = result.modified[0]
        self.assertEqual(
            mod.new_version,
            self.new_version + "-r1",
            "unexpected version number: %s" % mod.new_version,
        )

        old_ebuild_path = os.path.join(
            package_path, self.ebuild_template % self.version
        )
        new_ebuild_path = os.path.join(
            package_path, self.ebuild_template % self.new_version
        )
        manifest_path = os.path.join(package_path, "Manifest")

        expected_modified_files = [
            old_ebuild_path,
            new_ebuild_path,
            manifest_path,
        ]
        self.assertCountEqual(mod.files, expected_modified_files)

        self.assertCommandContains(["ebuild", "manifest"])

    def test_uprev_ebuild_same_version(self):
        """Tests uprev of ebuild with version path with unchanged version.

        This should result in bumping the revision number.
        """
        file_layout = (
            D(self.package, [self.ebuild, self.unstable_ebuild, self.manifest]),
        )
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, file_layout)

        package_path = os.path.join(self.tempdir, self.package)

        ebuild_path = os.path.join(package_path, self.ebuild)
        self.WriteTempFile(ebuild_path, 'KEYWORDS="*"\n')

        result = uprev_lib.uprev_ebuild_from_pin(
            package_path, self.version, chroot=chroot_lib.Chroot()
        )
        self.assertEqual(
            len(result.modified),
            1,
            "unexpected number of results: %s" % len(result.modified),
        )

        mod = result.modified[0]
        self.assertEqual(
            mod.new_version,
            self.version + "-r2",
            "unexpected version number: %s" % mod.new_version,
        )

        old_ebuild_path = os.path.join(
            package_path, self.ebuild_template % self.version
        )
        new_ebuild_path = os.path.join(
            package_path, "package-%s-r2.ebuild" % self.version
        )
        manifest_path = os.path.join(package_path, "Manifest")

        expected_modified_files = [
            old_ebuild_path,
            new_ebuild_path,
            manifest_path,
        ]
        self.assertCountEqual(mod.files, expected_modified_files)

        self.assertCommandContains(["ebuild", "manifest"])

    def test_no_ebuild(self):
        """Tests assertion is raised if package has no ebuilds"""
        file_layout = (D(self.package, [self.manifest]),)
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, file_layout)

        package_path = os.path.join(self.tempdir, self.package)

        with self.assertRaises(uprev_lib.EbuildUprevError):
            uprev_lib.uprev_ebuild_from_pin(
                package_path, self.new_version, chroot=chroot_lib.Chroot()
            )

    def test_multiple_stable_ebuilds(self):
        """Tests assertion is raised if multiple stable ebuilds are present"""
        file_layout = (
            D(
                self.package,
                [self.ebuild, self.ebuild_template % "1.2.1", self.manifest],
            ),
        )
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, file_layout)

        package_path = os.path.join(self.tempdir, self.package)

        ebuild_path = os.path.join(package_path, self.ebuild)
        self.WriteTempFile(ebuild_path, 'KEYWORDS="*"\n')

        ebuild_path = os.path.join(package_path, self.ebuild_template % "1.2.1")
        self.WriteTempFile(ebuild_path, 'KEYWORDS="*"\n')

        with self.assertRaises(uprev_lib.EbuildUprevError):
            uprev_lib.uprev_ebuild_from_pin(
                package_path, self.new_version, chroot=chroot_lib.Chroot()
            )

    def test_multiple_unstable_ebuilds(self):
        """Tests assertion is raised if multiple unstable ebuilds are present"""
        file_layout = (
            D(
                self.package,
                [self.ebuild, self.ebuild_template % "1.2.1", self.manifest],
            ),
        )
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, file_layout)

        package_path = os.path.join(self.tempdir, self.package)

        with self.assertRaises(uprev_lib.EbuildUprevError):
            uprev_lib.uprev_ebuild_from_pin(
                package_path, self.new_version, chroot=chroot_lib.Chroot()
            )


class ReplicatePrivateConfigTest(cros_test_lib.RunCommandTempDirTestCase):
    """replicate_private_config tests."""

    def setUp(self):
        # Set up fake public and private chromeos-config overlays.
        private_package_root = (
            "src/private-overlays/overlay-coral-private/chromeos-base/"
            "chromeos-config-bsp"
        )
        self.public_package_root = (
            "src/overlays/overlay-coral/chromeos-base/chromeos-config-bsp"
        )
        file_layout = (
            D(
                os.path.join(private_package_root, "files"),
                ["build_config.json"],
            ),
            D(private_package_root, ["replication_config.jsonpb"]),
            D(
                os.path.join(self.public_package_root, "files"),
                ["build_config.json"],
            ),
        )

        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, file_layout)

        # Private config contains 'a' and 'b' fields.
        self.private_config_path = os.path.join(
            private_package_root, "files", "build_config.json"
        )
        self.WriteTempFile(
            self.private_config_path,
            json.dumps({"chromeos": {"configs": [{"a": 3, "b": 2}]}}),
        )

        # Public config only contains the 'a' field. Note that the value of 'a'
        # is 1 in the public config; it will get updated to 3 when the private
        # config is replicated.
        self.public_config_path = os.path.join(
            self.public_package_root, "files", "build_config.json"
        )
        self.WriteTempFile(
            self.public_config_path,
            json.dumps({"chromeos": {"configs": [{"a": 1}]}}),
        )

        # Put a ReplicationConfig JSONPB in the private package. Note that it
        # specifies only the 'a' field is replicated.
        self.replication_config_path = os.path.join(
            self.tempdir, private_package_root, "replication_config.jsonpb"
        )
        replication_config = ReplicationConfig(
            file_replication_rules=[
                FileReplicationRule(
                    source_path=self.private_config_path,
                    destination_path=self.public_config_path,
                    file_type=FILE_TYPE_JSON,
                    replication_type=REPLICATION_TYPE_FILTER,
                    destination_fields=field_mask_pb2.FieldMask(paths=["a"]),
                )
            ]
        )

        osutils.WriteFile(
            self.replication_config_path,
            json_format.MessageToJson(replication_config),
        )
        self.PatchObject(constants, "SOURCE_ROOT", new=self.tempdir)

        self.rc.SetDefaultCmdResult(side_effect=self._write_generated_c_files)

    def _write_generated_c_files(self, *_args, **_kwargs):
        """Write fake generated C files to the public output dir.

        Note that this function accepts args and kwargs so it can be used as a
        side effect.
        """
        output_dir = os.path.join(self.public_package_root, "files")
        self.WriteTempFile(os.path.join(output_dir, "config.c"), "")
        self.WriteTempFile(os.path.join(output_dir, "ec_config.c"), "")
        self.WriteTempFile(os.path.join(output_dir, "ec_config.h"), "")

    def _write_incorrect_generated_c_files(self, *_args, **_kwargs):
        """Similar to _write_generated_c_files, with an expected file missing.

        Note that this function accepts args and kwargs so it can be used as a
        side effect.
        """
        output_dir = os.path.join(self.public_package_root, "files")
        self.WriteTempFile(os.path.join(output_dir, "config.c"), "")
        self.WriteTempFile(os.path.join(output_dir, "ec_config.c"), "")

    def test_replicate_private_config(self):
        """Basic replication test."""
        refs = [
            uprev_lib.GitRef(
                path="/chromeos/overlays/overlay-coral-private",
                ref="main",
                revision="123",
            )
        ]
        chroot = chroot_lib.Chroot()
        result = packages.replicate_private_config(
            _build_targets=None, refs=refs, chroot=chroot
        )

        self.assertCommandContains(
            [
                "cros_config_schema",
                "-m",
                os.path.join(
                    constants.CHROOT_SOURCE_ROOT, self.public_config_path
                ),
                "-g",
                os.path.join(
                    constants.CHROOT_SOURCE_ROOT,
                    self.public_package_root,
                    "files",
                ),
                "-f",
                '"TRUE"',
            ],
            enter_chroot=True,
            chroot_args=chroot.get_enter_args(),
        )

        self.assertEqual(len(result.modified), 1)
        # The public build_config.json and generated C files were modified.
        expected_modified_files = [
            os.path.join(self.tempdir, self.public_config_path),
            os.path.join(
                self.tempdir, self.public_package_root, "files", "config.c"
            ),
            os.path.join(
                self.tempdir, self.public_package_root, "files", "ec_config.c"
            ),
            os.path.join(
                self.tempdir, self.public_package_root, "files", "ec_config.h"
            ),
        ]
        self.assertEqual(result.modified[0].files, expected_modified_files)
        self.assertEqual(result.modified[0].new_version, "123")

        # The update from the private build_config.json was copied to the
        # public. Note that only the 'a' field is present, as per
        # destination_fields.
        self.assertEqual(
            json.loads(self.ReadTempFile(self.public_config_path)),
            {"chromeos": {"configs": [{"a": 3}]}},
        )

    def test_replicate_private_config_no_build_config(self):
        """If there is no build config, don't generate C files."""
        # Modify the replication config to write to "other_config.json" instead
        # of "build_config.json"
        modified_destination_path = self.public_config_path.replace(
            "build_config", "other_config"
        )
        replication_config = ReplicationConfig(
            file_replication_rules=[
                FileReplicationRule(
                    source_path=self.private_config_path,
                    destination_path=modified_destination_path,
                    file_type=FILE_TYPE_JSON,
                    replication_type=REPLICATION_TYPE_FILTER,
                    destination_fields=field_mask_pb2.FieldMask(paths=["a"]),
                )
            ]
        )
        osutils.WriteFile(
            self.replication_config_path,
            json_format.MessageToJson(replication_config),
        )

        refs = [
            uprev_lib.GitRef(
                path="/chromeos/overlays/overlay-coral-private",
                ref="main",
                revision="123",
            )
        ]
        result = packages.replicate_private_config(
            _build_targets=None, refs=refs, chroot=chroot_lib.Chroot()
        )

        self.assertEqual(len(result.modified), 1)
        self.assertEqual(
            result.modified[0].files,
            [os.path.join(self.tempdir, modified_destination_path)],
        )

    def test_replicate_private_config_multiple_build_configs(self):
        """An error is thrown if there is more than one build config."""
        replication_config = ReplicationConfig(
            file_replication_rules=[
                FileReplicationRule(
                    source_path=self.private_config_path,
                    destination_path=self.public_config_path,
                    file_type=FILE_TYPE_JSON,
                    replication_type=REPLICATION_TYPE_FILTER,
                    destination_fields=field_mask_pb2.FieldMask(paths=["a"]),
                ),
                FileReplicationRule(
                    source_path=self.private_config_path,
                    destination_path=self.public_config_path,
                    file_type=FILE_TYPE_JSON,
                    replication_type=REPLICATION_TYPE_FILTER,
                    destination_fields=field_mask_pb2.FieldMask(paths=["a"]),
                ),
            ]
        )

        osutils.WriteFile(
            self.replication_config_path,
            json_format.MessageToJson(replication_config),
        )

        refs = [
            uprev_lib.GitRef(
                path="/chromeos/overlays/overlay-coral-private",
                ref="main",
                revision="123",
            )
        ]
        with self.assertRaisesRegex(
            ValueError,
            "Expected at most one build_config.json destination path.",
        ):
            packages.replicate_private_config(
                _build_targets=None, refs=refs, chroot=chroot_lib.Chroot()
            )

    def test_replicate_private_config_generated_files_incorrect(self):
        """An error is thrown if generated C files are missing."""
        self.rc.SetDefaultCmdResult(
            side_effect=self._write_incorrect_generated_c_files
        )

        refs = [
            uprev_lib.GitRef(
                path="/chromeos/overlays/overlay-coral-private",
                ref="main",
                revision="123",
            )
        ]
        chroot = chroot_lib.Chroot()

        with self.assertRaisesRegex(
            packages.GeneratedCrosConfigFilesError,
            "Expected to find generated C files",
        ):
            packages.replicate_private_config(
                _build_targets=None, refs=refs, chroot=chroot
            )

    def test_replicate_private_config_wrong_number_of_refs(self):
        """An error is thrown if there is not exactly one ref."""
        with self.assertRaisesRegex(ValueError, "Expected exactly one ref"):
            packages.replicate_private_config(
                _build_targets=None, refs=[], chroot=None
            )

        with self.assertRaisesRegex(ValueError, "Expected exactly one ref"):
            refs = [
                uprev_lib.GitRef(path="a", ref="main", revision="1"),
                uprev_lib.GitRef(path="a", ref="main", revision="2"),
            ]
            packages.replicate_private_config(
                _build_targets=None, refs=refs, chroot=None
            )

    def test_replicate_private_config_replication_config_missing(self):
        """An error is thrown if there is not a replication config."""
        os.remove(self.replication_config_path)
        with self.assertRaisesRegex(
            ValueError,
            "Expected ReplicationConfig missing at %s"
            % self.replication_config_path,
        ):
            refs = [
                uprev_lib.GitRef(
                    path="/chromeos/overlays/overlay-coral-private",
                    ref="main",
                    revision="123",
                )
            ]
            packages.replicate_private_config(
                _build_targets=None, refs=refs, chroot=None
            )

    def test_replicate_private_config_wrong_git_ref_path(self):
        """Git ref that doesn't point to a private overlay throws error."""
        with self.assertRaisesRegex(
            ValueError, "ref.path must match the pattern"
        ):
            refs = [uprev_lib.GitRef(path="a/b/c", ref="main", revision="123")]
            packages.replicate_private_config(
                _build_targets=None, refs=refs, chroot=None
            )


class GetBestVisibleTest(cros_test_lib.MockTestCase):
    """get_best_visible tests."""

    def test_empty_atom_fails(self):
        """Test empty atom raises an error."""
        with self.assertRaises(AssertionError):
            packages.get_best_visible("")


class HasPrebuiltTest(cros_test_lib.MockTestCase):
    """has_prebuilt tests."""

    def test_empty_atom_fails(self):
        """Test an empty atom results in an error."""
        with self.assertRaises(AssertionError):
            packages.has_prebuilt("")

    def test_use_flags(self):
        """Test use flags get propagated correctly."""
        # We don't really care about the result, just the env handling.
        patch = self.PatchObject(portage_util, "HasPrebuilt", return_value=True)
        # Ignore any flags that may be in the environment.
        self.PatchObject(os.environ, "get", return_value="")

        packages.has_prebuilt("cat/pkg-1.2.3", useflags="useflag")
        patch.assert_called_with(
            "cat/pkg-1.2.3", board=None, extra_env={"USE": "useflag"}
        )

    def test_env_use_flags(self):
        """Test env use flags get propagated correctly with passed useflags."""
        # We don't really care about the result, just the env handling.
        patch = self.PatchObject(portage_util, "HasPrebuilt", return_value=True)
        # Add some flags to the environment.
        existing_flags = "already set flags"
        self.PatchObject(os.environ, "get", return_value=existing_flags)

        new_flags = "useflag"
        packages.has_prebuilt("cat/pkg-1.2.3", useflags=new_flags)
        expected = "%s %s" % (existing_flags, new_flags)
        patch.assert_called_with(
            "cat/pkg-1.2.3", board=None, extra_env={"USE": expected}
        )


class AndroidVersionsTest(cros_test_lib.MockTestCase):
    """Tests getting android versions."""

    def setUp(self):
        package_result = [
            "chromeos-base/android-container-nyc-4717008-r1",
            "chromeos-base/update_engine-0.0.3-r3408",
        ]
        self.PatchObject(
            portage_util, "GetPackageDependencies", return_value=package_result
        )
        self.board = "board"
        self.PatchObject(
            portage_util,
            "FindEbuildForBoardPackage",
            return_value="chromeos-base/android-container-nyc",
        )
        FakeEnvironment = {
            "ARM_TARGET": "3-linux-target",
        }
        self.PatchObject(
            osutils, "SourceEnvironment", return_value=FakeEnvironment
        )

        # Clear the LRU cache for the function. We mock the function that
        # provides the data this function processes to produce its result, so we
        # need to clear it manually.
        packages.determine_android_package.cache_clear()

    def test_determine_android_version(self):
        """Tests that a valid android version is returned."""
        version = packages.determine_android_version(self.board)
        self.assertEqual(version, "4717008")

    def test_determine_android_version_when_not_present(self):
        """Test None is returned for version when android is not present."""
        package_result = ["chromeos-base/update_engine-0.0.3-r3408"]
        self.PatchObject(
            portage_util, "GetPackageDependencies", return_value=package_result
        )
        version = packages.determine_android_version(self.board)
        self.assertEqual(version, None)

    def test_determine_android_branch(self):
        """Tests that a valid android branch is returned."""
        branch = packages.determine_android_branch(self.board)
        self.assertEqual(branch, "3")

    def test_determine_android_branch_64bit_targets(self):
        """Tests a valid android branch is returned with only 64bit targets."""
        self.PatchObject(
            osutils,
            "SourceEnvironment",
            return_value={"ARM64_TARGET": "3-linux-target"},
        )
        branch = packages.determine_android_branch(self.board)
        self.assertEqual(branch, "3")

    def test_determine_android_branch_when_not_present(self):
        """Tests a None is returned for branch when android is not present."""
        package_result = ["chromeos-base/update_engine-0.0.3-r3408"]
        self.PatchObject(
            portage_util, "GetPackageDependencies", return_value=package_result
        )
        branch = packages.determine_android_branch(self.board)
        self.assertEqual(branch, None)

    def test_determine_android_target(self):
        """Tests that a valid android target is returned."""
        target = packages.determine_android_target(self.board)
        self.assertEqual(target, "cheets")

    def test_determine_android_target_when_not_present(self):
        """Tests a None is returned for target when android is not present."""
        package_result = ["chromeos-base/update_engine-0.0.3-r3408"]
        self.PatchObject(
            portage_util, "GetPackageDependencies", return_value=package_result
        )
        target = packages.determine_android_target(self.board)
        self.assertEqual(target, None)

    def test_determine_android_version_handle_exception(self):
        """Tests handling RunCommandError inside determine_android_version."""
        # Mock what happens when portage returns that bubbles up (via
        # RunCommand) inside portage_util.GetPackageDependencies.
        self.PatchObject(
            portage_util,
            "GetPackageDependencies",
            side_effect=cros_build_lib.RunCommandError("error"),
        )
        target = packages.determine_android_version(self.board)
        self.assertEqual(target, None)

    def test_determine_android_package_handle_exception(self):
        """Tests handling RunCommandError inside determine_android_package."""
        # Mock what happens when portage returns that bubbles up (via
        # RunCommand) inside portage_util.GetPackageDependencies.
        self.PatchObject(
            portage_util,
            "GetPackageDependencies",
            side_effect=cros_build_lib.RunCommandError("error"),
        )
        target = packages.determine_android_package(self.board)
        self.assertEqual(target, None)

    def test_determine_android_package_callers_handle_exception(self):
        """Tests RunCommandError caught by determine_android_package callers."""
        # Mock what happens when portage returns that bubbles up (via
        # RunCommand) inside portage_util.GetPackageDependencies.
        self.PatchObject(
            portage_util,
            "GetPackageDependencies",
            side_effect=cros_build_lib.RunCommandError("error"),
        )
        # Verify that target is None, as expected.
        target = packages.determine_android_package(self.board)
        self.assertEqual(target, None)
        # determine_android_branch calls determine_android_package
        branch = packages.determine_android_branch(self.board)
        self.assertEqual(branch, None)
        # determine_android_target calls determine_android_package
        target = packages.determine_android_target(self.board)
        self.assertEqual(target, None)


@pytest.mark.usefixtures("testcase_caplog", "testcase_monkeypatch")
class FindFingerprintsTest(cros_test_lib.RunCommandTempDirTestCase):
    """Tests for find_fingerprints."""

    def setUp(self):
        self.board = "test-board"
        # Create cheets-fingerprints.txt based on tempdir/src...
        self.fingerprint_contents = (
            "google/test-board/test-board_cheets"
            ":9/R99-12345.0.9999/123456:user/release-keys"
        )
        fingerprint_path = os.path.join(
            self.tempdir,
            "src/build/images/test-board/latest/cheets-fingerprint.txt",
        )
        self.chroot = chroot_lib.Chroot(
            path=self.tempdir / "chroot", out_path=self.tempdir / "out"
        )
        osutils.WriteFile(
            fingerprint_path, self.fingerprint_contents, makedirs=True
        )

    def test_find_fingerprints_with_test_path(self):
        """Tests get_firmware_versions with mocked output."""
        self.monkeypatch.setattr(constants, "SOURCE_ROOT", self.tempdir)
        build_target = build_target_lib.BuildTarget(self.board)
        result = packages.find_fingerprints(build_target)
        self.assertEqual(result, [self.fingerprint_contents])
        self.assertIn("Reading fingerprint file", self.caplog.text)

    def test_find_fingerprints(self):
        """Tests get_firmware_versions with mocked output."""
        # Use board name whose path for fingerprint file does not exist.
        # Verify that fingerprint file is not found and None is returned.
        build_target = build_target_lib.BuildTarget("wrong-boardname")
        self.monkeypatch.setattr(constants, "SOURCE_ROOT", self.tempdir)
        result = packages.find_fingerprints(build_target)
        self.assertEqual(result, [])
        self.assertIn("Fingerprint file not found", self.caplog.text)


class GetAllFirmwareVersionsTest(cros_test_lib.RunCommandTempDirTestCase):
    """Tests for get_firmware_versions."""

    def setUp(self):
        self.board = "test-board"
        # pylint: disable=line-too-long
        self.rc.SetDefaultCmdResult(
            stdout="""

flashrom(8): 68935ee2fcfcffa47af81b966269cd2b */build/reef/usr/sbin/flashrom
             ELF 64-bit LSB executable, x86-64, version 1 (SYSV), statically linked, for GNU/Linux 2.6.32, BuildID[sha1]=e102cc98d45300b50088999d53775acbeff407dc, stripped
             0.9.9  : bbb2d6a : Jul 28 2017 15:12:34 UTC

Model:        reef
BIOS image:   1b535280fe688ac284d95276492b06f6 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/reef/image.bin
BIOS version: Google_Reef.9042.87.1
BIOS (RW) image:   0ef265eb8f2d228c09f75b011adbdcbb */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/reef/image.binrw
BIOS (RW) version: Google_Reef.9042.110.0
EC image:     2e8b4b5fa73cc5dbca4496de97a917a9 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/reef/ec.bin
EC version:   reef_v1.1.5900-ab1ee51
EC (RW) version: reef_v1.1.5909-bd1f0c9

Model:        pyro
BIOS image:   9e62447ebf22a724a4a835018ab6234e */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/pyro/image.bin
BIOS version: Google_Pyro.9042.87.1
BIOS (RW) image:   1897457303c85de99f3e98b2eaa0eccc */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/pyro/image.binrw
BIOS (RW) version: Google_Pyro.9042.110.0
EC image:     44b93ed591733519e752e05aa0529eb5 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/pyro/ec.bin
EC version:   pyro_v1.1.5900-ab1ee51
EC (RW) version: pyro_v1.1.5909-bd1f0c9

Model:        snappy
BIOS image:   3ab63ff080596bd7de4e7619f003bb64 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/snappy/image.bin
BIOS version: Google_Snappy.9042.110.0
EC image:     c4db159e84428391d2ee25368c5fe5b6 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/snappy/ec.bin
EC version:   snappy_v1.1.5909-bd1f0c9

Model:        sand
BIOS image:   387da034a4f0a3f53e278ebfdcc2a412 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/sand/image.bin
BIOS version: Google_Sand.9042.110.0
EC image:     411562e0589dacec131f5fdfbe95a561 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/sand/ec.bin
EC version:   sand_v1.1.5909-bd1f0c9

Model:        electro
BIOS image:   1b535280fe688ac284d95276492b06f6 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/reef/image.bin
BIOS version: Google_Reef.9042.87.1
BIOS (RW) image:   0ef265eb8f2d228c09f75b011adbdcbb */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/reef/image.binrw
BIOS (RW) version: Google_Reef.9042.110.0
EC image:     2e8b4b5fa73cc5dbca4496de97a917a9 */build/reef/tmp/portage/chromeos-base/chromeos-firmware-reef-0.0.1-r79/temp/tmp7rHApL.pack_firmware-99001/models/reef/ec.bin
EC version:   reef_v1.1.5900-ab1ee51
EC (RW) version: reef_v1.1.5909-bd1f0c9

Package Content:
612e7bb6ed1fb0a05abf2ebdc834c18b *./updater4.sh
0eafbee07282315829d0f42135ec7c0c *./gbb_utility
6074e3ca424cb30a67c378c1d9681f9c *./mosys
68935ee2fcfcffa47af81b966269cd2b *./flashrom
0eafbee07282315829d0f42135ec7c0c *./dump_fmap
490c95d6123c208d20d84d7c16857c7c *./crosfw.sh
60899148600b8673ddb711faa55aee40 *./common.sh
3c3a99346d1ca1273cbcd86c104851ff *./shflags
de7ce035e1f82a89f8909d888ee402c0 *./crosutil.sh
f9334372bdb9036ba09a6fd9bf30e7a2 *./crossystem
22257a8d5f0adc1f50a1916c3a4a35dd *./models/reef/ec.bin
faf12dbb7cdaf21ce153bdffb67841fd *./models/reef/bios.bin
c9bbb417b7921b85a7ed999ee42f550e *./models/reef/setvars.sh
29823d46f1ec1491ecacd7b830fd2686 *./models/pyro/ec.bin
2320463aba8b22eb5ea836f094d281b3 *./models/pyro/bios.bin
81614833ad77c9cd093360ba7bea76b8 *./models/pyro/setvars.sh
411562e0589dacec131f5fdfbe95a561 *./models/sand/ec.bin
387da034a4f0a3f53e278ebfdcc2a412 *./models/sand/bios.bin
fcd8cb0ac0e2ed6be220aaae435d43ff *./models/sand/setvars.sh
c4db159e84428391d2ee25368c5fe5b6 *./models/snappy/ec.bin
3ab63ff080596bd7de4e7619f003bb64 *./models/snappy/bios.bin
fe5d699f2e9e4a7de031497953313dbd *./models/snappy/setvars.sh
79aabd7cd8a215a54234c53d7bb2e6fb *./vpd
"""
        )
        # pylint: enable=line-too-long

    def test_get_firmware_versions(self):
        """Tests get_firmware_versions with mocked output."""
        build_target = build_target_lib.BuildTarget(self.board)
        result = packages.get_all_firmware_versions(build_target)
        self.assertEqual(len(result), 5)
        self.assertEqual(
            result["reef"],
            packages.FirmwareVersions(
                "reef",
                "Google_Reef.9042.87.1",
                "Google_Reef.9042.110.0",
                "reef_v1.1.5900-ab1ee51",
                "reef_v1.1.5909-bd1f0c9",
            ),
        )
        self.assertEqual(
            result["pyro"],
            packages.FirmwareVersions(
                "pyro",
                "Google_Pyro.9042.87.1",
                "Google_Pyro.9042.110.0",
                "pyro_v1.1.5900-ab1ee51",
                "pyro_v1.1.5909-bd1f0c9",
            ),
        )
        self.assertEqual(
            result["snappy"],
            packages.FirmwareVersions(
                "snappy",
                "Google_Snappy.9042.110.0",
                None,
                "snappy_v1.1.5909-bd1f0c9",
                None,
            ),
        )
        self.assertEqual(
            result["sand"],
            packages.FirmwareVersions(
                "sand",
                "Google_Sand.9042.110.0",
                None,
                "sand_v1.1.5909-bd1f0c9",
                None,
            ),
        )
        self.assertEqual(
            result["electro"],
            packages.FirmwareVersions(
                "electro",
                "Google_Reef.9042.87.1",
                "Google_Reef.9042.110.0",
                "reef_v1.1.5900-ab1ee51",
                "reef_v1.1.5909-bd1f0c9",
            ),
        )

    def test_get_firmware_versions_error(self):
        """Tests get_firmware_versions with no output."""
        # Throw an exception when running the command.
        self.rc.SetDefaultCmdResult(returncode=1)
        build_target = build_target_lib.BuildTarget(self.board)
        result = packages.get_all_firmware_versions(build_target)
        self.assertEqual(result, {})


class GetFirmwareVersionsTest(cros_test_lib.RunCommandTempDirTestCase):
    """Tests for get_firmware_versions."""

    def setUp(self):
        self.board = "test-board"
        # pylint: disable=line-too-long
        self.rc.SetDefaultCmdResult(
            stdout="""

flashrom(8): a8f99c2e61e7dc09c4b25ef5a76ef692 */build/kevin/usr/sbin/flashrom
             ELF 32-bit LSB executable, ARM, EABI5 version 1 (SYSV), statically linked, for GNU/Linux 2.d
             0.9.4  : 860875a : Apr 10 2017 23:54:29 UTC

BIOS image:   6b5b855a0b8fd1657546d1402c15b206 *chromeos-firmware-kevin-0.0.1/.dist/kevin_fw_8785.178.0.n
BIOS version: Google_Kevin.8785.178.0
EC image:     1ebfa9518e6cac0558a80b7ab2f5b489 *chromeos-firmware-kevin-0.0.1/.dist/kevin_ec_8785.178.0.n
EC version:kevin_v1.10.184-459421c

Package Content:
a8f99c2e61e7dc09c4b25ef5a76ef692 *./flashrom
3c3a99346d1ca1273cbcd86c104851ff *./shflags
457a8dc8546764affc9700f8da328d23 *./dump_fmap
c392980ddb542639edf44a965a59361a *./updater5.sh
490c95d6123c208d20d84d7c16857c7c *./crosfw.sh
6b5b855a0b8fd1657546d1402c15b206 *./bios.bin
7b5bef0d2da90c23ff2e157250edf0fa *./crosutil.sh
d78722e4f1a0dc2d8c3d6b0bc7010ae3 *./crossystem
457a8dc8546764affc9700f8da328d23 *./gbb_utility
1ebfa9518e6cac0558a80b7ab2f5b489 *./ec.bin
c98ca54db130886142ad582a58e90ddc *./common.sh
5ba978bdec0f696f47f0f0de90936880 *./mosys
312e8ee6122057f2a246d7bcf1572f49 *./vpd
"""
        )
        # pylint: enable=line-too-long

    def test_get_firmware_versions(self):
        """Tests get_firmware_versions with mocked output."""
        build_target = build_target_lib.BuildTarget(self.board)
        result = packages.get_firmware_versions(build_target)
        versions = packages.FirmwareVersions(
            None,
            "Google_Kevin.8785.178.0",
            None,
            "kevin_v1.10.184-459421c",
            None,
        )
        self.assertEqual(result, versions)


class DetermineKernelVersionTest(cros_test_lib.RunCommandTempDirTestCase):
    """Tests for determine_kernel_version."""

    def setUp(self):
        self.board = "test-board"
        self.build_target = build_target_lib.BuildTarget(self.board)

    def test_determine_kernel_version(self):
        """Tests that a valid kernel version is returned."""
        kernel_candidates = [
            "sys-kernel/chromeos-kernel-experimental-4.18_rc2-r23",
            "sys-kernel/chromeos-kernel-4_4-4.4.223-r2209",
            "sys-kernel/chromeos-kernel-5_15-5.15.65-r869",
            "sys-kernel/upstream-kernel-next-9999",
            "sys-kernel/socfpga-kernel-4.20-r34",
        ]
        self.PatchObject(
            portage_util,
            "GetFlattenedDepsForPackage",
            return_value=kernel_candidates,
        )

        installed_pkgs = [
            "sys-kernel/linux-firmware-0.0.1-r594",
            "sys-kernel/chromeos-kernel-4_4-4.4.223-r2209",
            "virtual/linux-sources-1-r30",
        ]
        self.PatchObject(
            portage_util,
            "GetPackageDependencies",
            return_value=installed_pkgs,
        )

        result = packages.determine_kernel_version(self.build_target)
        self.assertEqual(result, "4.4.223-r2209")

    def test_determine_kernel_version_ignores_exact_duplicates(self):
        """Tests that multiple results for candidates is ignored."""
        # Depgraph is evaluated for version as well as revision, so graph will
        # return all results twice.
        kernel_candidates = [
            "sys-kernel/chromeos-kernel-experimental-4.18_rc2-r23",
            "sys-kernel/chromeos-kernel-4_4-4.4.223-r2209",
            "sys-kernel/chromeos-kernel-5_15-5.15.65-r869",
            "sys-kernel/upstream-kernel-next-9999",
            "sys-kernel/socfpga-kernel-4.20-r34",
            "sys-kernel/chromeos-kernel-experimental-4.18_rc2-r23",
            "sys-kernel/chromeos-kernel-4_4-4.4.223-r2209",
            "sys-kernel/chromeos-kernel-5_15-5.15.65-r869",
            "sys-kernel/upstream-kernel-next-9999",
            "sys-kernel/socfpga-kernel-4.20-r34",
        ]
        self.PatchObject(
            portage_util,
            "GetFlattenedDepsForPackage",
            return_value=kernel_candidates,
        )

        installed_pkgs = [
            "sys-kernel/linux-firmware-0.0.1-r594",
            "sys-kernel/chromeos-kernel-4_4-4.4.223-r2209",
            "virtual/linux-sources-1-r30",
        ]
        self.PatchObject(
            portage_util,
            "GetPackageDependencies",
            return_value=installed_pkgs,
        )

        result = packages.determine_kernel_version(self.build_target)
        self.assertEqual(result, "4.4.223-r2209")

    def test_determine_kernel_version_ignores_virtual_package(self):
        """Tests that top-level package is ignored as potential kernel pkg."""
        # Depgraph results include the named package at level 0 as well as its
        # first-order dependencies, so verify that the virtual package is not
        # included as a kernel package.
        kernel_candidates = [
            "virtual/linux-sources-1",
            "sys-kernel/chromeos-kernel-experimental-4.18_rc2-r23",
            "sys-kernel/chromeos-kernel-4_4-4.4.223-r2209",
            "sys-kernel/chromeos-kernel-5_15-5.15.65-r869",
            "sys-kernel/upstream-kernel-next-9999",
            "sys-kernel/socfpga-kernel-4.20-r34",
            "virtual/linux-sources-1-r30",
            "sys-kernel/chromeos-kernel-experimental-4.18_rc2-r23",
            "sys-kernel/chromeos-kernel-4_4-4.4.223-r2209",
            "sys-kernel/chromeos-kernel-5_15-5.15.65-r869",
            "sys-kernel/upstream-kernel-next-9999",
            "sys-kernel/socfpga-kernel-4.20-r34",
        ]
        self.PatchObject(
            portage_util,
            "GetFlattenedDepsForPackage",
            return_value=kernel_candidates,
        )

        installed_pkgs = [
            "sys-kernel/linux-firmware-0.0.1-r594",
            "sys-kernel/chromeos-kernel-4_4-4.4.223-r2209",
            "virtual/linux-sources-1-r30",
        ]
        self.PatchObject(
            portage_util,
            "GetPackageDependencies",
            return_value=installed_pkgs,
        )

        result = packages.determine_kernel_version(self.build_target)
        self.assertEqual(result, "4.4.223-r2209")

    def test_determine_kernel_version_too_many(self):
        """Tests that an exception is thrown with too many matching packages."""
        package_result = [
            "sys-kernel/chromeos-kernel-experimental-4.18_rc2-r23",
            "sys-kernel/chromeos-kernel-4_4-4.4.223-r2209",
            "sys-kernel/chromeos-kernel-5_15-5.15.65-r869",
            "sys-kernel/upstream-kernel-next-9999",
            "sys-kernel/socfpga-kernel-4.20-r34",
        ]
        self.PatchObject(
            portage_util,
            "GetFlattenedDepsForPackage",
            return_value=package_result,
        )

        installed_pkgs = [
            "sys-kernel/linux-firmware-0.0.1-r594",
            "sys-kernel/chromeos-kernel-4_4-4.4.223-r2209",
            "sys-kernel/chromeos-kernel-5_15-5.15.65-r869",
            "virtual/linux-sources-1-r30",
        ]
        self.PatchObject(
            portage_util,
            "GetPackageDependencies",
            return_value=installed_pkgs,
        )

        with self.assertRaises(packages.KernelVersionError):
            packages.determine_kernel_version(self.build_target)

    def test_determine_kernel_version_no_kernel_match(self):
        """Tests that an exception is thrown with 0-sized intersection."""
        package_result = [
            "sys-kernel/chromeos-kernel-experimental-4.18_rc2-r23",
            "sys-kernel/chromeos-kernel-4_4-4.4.223-r2209",
            "sys-kernel/chromeos-kernel-5_15-5.15.65-r869",
            "sys-kernel/upstream-kernel-next-9999",
        ]
        self.PatchObject(
            portage_util,
            "GetFlattenedDepsForPackage",
            return_value=package_result,
        )

        installed_pkgs = [
            "sys-kernel/linux-firmware-0.0.1-r594",
            "sys-kernel/socfpga-kernel-4.20-r34",
            "virtual/linux-sources-1-r30",
        ]
        self.PatchObject(
            portage_util,
            "GetPackageDependencies",
            return_value=installed_pkgs,
        )

        with self.assertRaises(packages.KernelVersionError):
            packages.determine_kernel_version(self.build_target)

    def test_determine_kernel_version_exception(self):
        """Tests that portage_util exceptions result in returning empty str."""
        self.PatchObject(
            portage_util,
            "GetFlattenedDepsForPackage",
            side_effect=cros_build_lib.RunCommandError("error"),
        )
        result = packages.determine_kernel_version(self.build_target)
        self.assertEqual(result, "")


class ChromeVersionsTest(cros_test_lib.MockTestCase):
    """Tests getting chrome version."""

    def setUp(self):
        self.build_target = build_target_lib.BuildTarget("board")

    def test_determine_chrome_version(self):
        """Tests that a valid chrome version is returned."""
        # Mock PortageqBestVisible to return a valid chrome version string.
        r1_cpf = "chromeos-base/chromeos-chrome-78.0.3900.0_rc-r1"
        r1_cpv = package_info.SplitCPV(r1_cpf)
        self.PatchObject(
            portage_util, "PortageqBestVisible", return_value=r1_cpv
        )

        chrome_version = packages.determine_package_version(
            constants.CHROME_CP, self.build_target
        )
        version_numbers = chrome_version.split(".")
        self.assertEqual(len(version_numbers), 4)
        self.assertEqual(int(version_numbers[0]), 78)

    def test_determine_chrome_version_handle_exception(self):
        # Mock what happens when portage throws an exception that bubbles up
        # (via RunCommand)inside portage_util.PortageqBestVisible.
        self.PatchObject(
            portage_util,
            "PortageqBestVisible",
            side_effect=cros_build_lib.RunCommandError("error"),
        )
        target = packages.determine_package_version(
            constants.CHROME_CP, self.build_target
        )
        self.assertEqual(target, None)


class PlatformVersionsTest(cros_test_lib.MockTestCase):
    """Tests getting platform version."""

    def test_determine_platform_version(self):
        """Test checking that a valid platform version is returned."""
        platform_version = packages.determine_platform_version()
        # The returned platform version is something like 12603.0.0.
        version_string_list = platform_version.split(".")
        self.assertEqual(len(version_string_list), 3)
        # We don't want to check an exact version, but the first number should
        # be non-zero.
        self.assertGreaterEqual(int(version_string_list[0]), 1)

    def test_determine_milestone_version(self):
        """Test checking that a valid milestone version is returned."""
        milestone_version = packages.determine_milestone_version()
        # Milestone version should be non-zero
        self.assertGreaterEqual(int(milestone_version), 1)

    def test_determine_full_version(self):
        """Test checking that a valid full version is returned."""
        full_version = packages.determine_full_version()
        pattern = r"^R(\d+)-(\d+.\d+.\d+(-rc\d+)*)"
        m = re.match(pattern, full_version)
        self.assertTrue(m)
        milestone_version = m.group(1)
        self.assertGreaterEqual(int(milestone_version), 1)

    def test_versions_based_on_mock(self):
        # Create a test version_info object, and then mock VersionInfo.from_repo
        # return it.
        test_platform_version = "12575.0.0"
        test_chrome_branch = "75"
        version_info_mock = chromeos_version.VersionInfo(test_platform_version)
        version_info_mock.chrome_branch = test_chrome_branch
        self.PatchObject(
            chromeos_version.VersionInfo,
            "from_repo",
            return_value=version_info_mock,
        )
        test_full_version = (
            "R" + test_chrome_branch + "-" + test_platform_version
        )
        platform_version = packages.determine_platform_version()
        milestone_version = packages.determine_milestone_version()
        full_version = packages.determine_full_version()
        self.assertEqual(platform_version, test_platform_version)
        self.assertEqual(milestone_version, test_chrome_branch)
        self.assertEqual(full_version, test_full_version)


# Each of the columns in the following table is a separate dimension along
# which Chrome uprev test cases can vary in behavior. The full test space would
# be the Cartesian product of the possible values of each column.
# 'CHROME_EBUILD' refers to the relationship between the version of the existing
# Chrome ebuild vs. the requested uprev version. 'FOLLOWER_EBUILDS' refers to
# the same relationship but for the packages defined in OTHER_CHROME_PACKAGES.
# 'EBUILDS MODIFIED' refers to whether any of the existing 9999 ebuilds have
# modified contents relative to their corresponding stable ebuilds.
#
# CHROME_EBUILD            FOLLOWER_EBUILDS           EBUILDS_MODIFIED
#
# HIGHER                   HIGHER                     YES
# SAME                     SAME                       NO
# LOWER                    LOWER
#                          DOESN'T EXIST YET

# These test cases cover both CHROME & FOLLOWER ebuilds being identically
# higher, lower, or the same versions, with no modified ebuilds.
UPREV_VERSION_CASES = (
    # Uprev.
    pytest.param(
        "80.0.8080.0",
        "81.0.8181.0",
        # One added and one deleted for chrome and each "other" package.
        2 * (1 + len(constants.OTHER_CHROME_PACKAGES)),
        False,
        id="newer_chrome_version",
    ),
    # Revbump.
    pytest.param(
        "80.0.8080.0",
        "80.0.8080.0",
        2,
        True,
        id="chrome_revbump",
    ),
    # No files should be changed in these cases.
    pytest.param(
        "80.0.8080.0",
        "80.0.8080.0",
        0,
        False,
        id="same_chrome_version",
    ),
    pytest.param(
        "80.0.8080.0",
        "79.0.7979.0",
        0,
        False,
        id="older_chrome_version",
    ),
)


@pytest.mark.parametrize(
    "old_version, new_version, expected_count, modify_unstable",
    UPREV_VERSION_CASES,
)
def test_uprev_chrome_all_files_already_exist(
    old_version,
    new_version,
    expected_count,
    modify_unstable,
    monkeypatch,
    overlay_stack,
):
    """Test Chrome uprevs work as expected when all packages already exist."""
    (overlay,) = overlay_stack(1)
    monkeypatch.setattr(uprev_lib, "_CHROME_OVERLAY_PATH", overlay.path)

    unstable_chrome = cr.test.Package(
        "chromeos-base", "chromeos-chrome", version="9999", keywords="~*"
    )
    if modify_unstable:
        # Add some field not set in stable.
        unstable_chrome.depend = "foo/bar"

    stable_chrome = cr.test.Package(
        "chromeos-base", "chromeos-chrome", version=f"{old_version}_rc-r1"
    )

    overlay.add_package(unstable_chrome)
    overlay.add_package(stable_chrome)

    for pkg_str in constants.OTHER_CHROME_PACKAGES:
        category, pkg_name = pkg_str.split("/")
        unstable_pkg = cr.test.Package(
            category, pkg_name, version="9999", keywords="~*"
        )
        stable_pkg = cr.test.Package(
            category, pkg_name, version=f"{old_version}_rc-r1"
        )

        overlay.add_package(unstable_pkg)
        overlay.add_package(stable_pkg)

    git_refs = [
        uprev_lib.GitRef(
            path="/foo", ref=f"refs/tags/{new_version}", revision="stubcommit"
        )
    ]
    res = packages.uprev_chrome_from_ref(None, git_refs, None)

    modified_file_count = sum(len(m.files) for m in res.modified)
    assert modified_file_count == expected_count


@pytest.mark.usefixtures("testcase_monkeypatch")
class GetModelsTest(cros_test_lib.RunCommandTempDirTestCase):
    """Tests for get_models."""

    def setUp(self):
        self.board = "test-board"
        self.rc.SetDefaultCmdResult(stdout="pyro\nreef\nsnappy\n")
        self.monkeypatch.setattr(constants, "SOURCE_ROOT", self.tempdir)
        build_bin = os.path.join(
            self.tempdir, constants.DEFAULT_CHROOT_DIR, "usr", "bin"
        )
        osutils.Touch(
            os.path.join(build_bin, "cros_config_host"), makedirs=True
        )

    def testGetModels(self):
        """Test get_models."""
        build_target = build_target_lib.BuildTarget(self.board)
        result = packages.get_models(build_target)
        self.assertEqual(result, ["pyro", "reef", "snappy"])


class GetKeyIdTest(cros_test_lib.MockTestCase):
    """Tests for get_key_id."""

    def setUp(self):
        self.board = "test-board"
        self.build_target = build_target_lib.BuildTarget(self.board)

    def testGetKeyId(self):
        """Test get_key_id when _run_cros_config_host returns a key."""
        self.PatchObject(
            packages, "_run_cros_config_host", return_value=["key"]
        )
        result = packages.get_key_id(self.build_target, "model")
        self.assertEqual(result, "key")

    def testGetKeyIdNoKey(self):
        """Test get_key_id when None should be returned."""
        self.PatchObject(
            packages, "_run_cros_config_host", return_value=["key1", "key2"]
        )
        result = packages.get_key_id(self.build_target, "model")
        self.assertEqual(result, None)


class GetLatestVersionTest(cros_test_lib.TestCase):
    """Tests for get_latest_version_from_refs."""

    def setUp(self):
        self.prefix = "refs/tags/drivefs_"
        # The tag ref template.
        ref_tpl = self.prefix + "%s"

        self.latest = "44.0.20"
        self.versions = ["42.0.1", self.latest, "44.0.19", "39.0.15"]
        self.latest_ref = uprev_lib.GitRef(
            "/path", ref_tpl % self.latest, "abc123"
        )
        self.refs = [
            uprev_lib.GitRef("/path", ref_tpl % v, "abc123")
            for v in self.versions
        ]

    def test_single_ref(self):
        """Test a single ref is supplied."""
        # pylint: disable=protected-access
        self.assertEqual(
            self.latest,
            packages._get_latest_version_from_refs(
                self.prefix, [self.latest_ref]
            ),
        )

    def test_multiple_ref_versions(self):
        """Test multiple refs supplied."""
        # pylint: disable=protected-access
        self.assertEqual(
            self.latest,
            packages._get_latest_version_from_refs(self.prefix, self.refs),
        )

    def test_no_refs_returns_none(self):
        """Test no refs supplied."""
        # pylint: disable=protected-access
        self.assertEqual(
            packages._get_latest_version_from_refs(self.prefix, []), None
        )

    def test_ref_prefix(self):
        """Test refs with a different prefix isn't used"""
        # pylint: disable=protected-access
        # Add refs/tags/foo_100.0.0 to the refs, which should be ignored in
        # _get_latest_version_from_refs because the prefix doesn't match, even
        # if its version number is larger.
        refs = self.refs + [
            uprev_lib.GitRef("/path", "refs/tags/foo_100.0.0", "abc123")
        ]
        self.assertEqual(
            self.latest,
            packages._get_latest_version_from_refs(self.prefix, refs),
        )


class NeedsChromeSourceTest(cros_test_lib.MockTestCase):
    """Tests for needs_chrome_source."""

    def _build_graph(self, with_chrome: bool, with_followers: bool):
        root = "/build/build_target"
        foo_bar = package_info.parse("foo/bar-1")
        chrome = package_info.parse(f"{constants.CHROME_CP}-1.2.3.4")
        followers = [
            package_info.parse(f"{pkg}-1.2.3.4")
            for pkg in constants.OTHER_CHROME_PACKAGES
        ]
        nodes = [dependency_graph.PackageNode(foo_bar, root)]
        root_pkgs = ["foo/bar-1"]
        if with_chrome:
            nodes.append(dependency_graph.PackageNode(chrome, root))
            root_pkgs.append(chrome.cpvr)
        if with_followers:
            nodes.extend(
                [dependency_graph.PackageNode(f, root) for f in followers]
            )
            root_pkgs.extend([f.cpvr for f in followers])

        return dependency_graph.DependencyGraph(nodes, root, root_pkgs)

    def test_needs_all(self):
        """Verify we need source when we have no prebuilts."""
        graph = self._build_graph(with_chrome=True, with_followers=True)
        self.PatchObject(
            depgraph, "get_sysroot_dependency_graph", return_value=graph
        )
        self.PatchObject(packages, "has_prebuilt", return_value=False)
        self.PatchObject(
            packages,
            "uprev_chrome",
            return_value=uprev_lib.UprevVersionedPackageResult(),
        )

        build_target = build_target_lib.BuildTarget("build_target")

        result = packages.needs_chrome_source(build_target)

        self.assertTrue(result.needs_chrome_source)
        self.assertTrue(result.builds_chrome)
        self.assertTrue(result.packages)
        self.assertEqual(
            len(result.packages), len(constants.OTHER_CHROME_PACKAGES) + 1
        )
        self.assertTrue(result.missing_chrome_prebuilt)
        self.assertTrue(result.missing_follower_prebuilt)
        self.assertFalse(result.local_uprev)

    def test_needs_none(self):
        """Verify not building any chrome packages prevents needing it."""
        graph = self._build_graph(with_chrome=False, with_followers=False)
        self.PatchObject(
            depgraph, "get_sysroot_dependency_graph", return_value=graph
        )
        self.PatchObject(packages, "has_prebuilt", return_value=False)
        self.PatchObject(
            packages,
            "uprev_chrome",
            return_value=uprev_lib.UprevVersionedPackageResult(),
        )

        build_target = build_target_lib.BuildTarget("build_target")

        result = packages.needs_chrome_source(build_target)

        self.assertFalse(result.needs_chrome_source)
        self.assertFalse(result.builds_chrome)
        self.assertFalse(result.packages)
        self.assertFalse(result.missing_chrome_prebuilt)
        self.assertFalse(result.missing_follower_prebuilt)
        self.assertFalse(result.local_uprev)

    def test_needs_chrome_only(self):
        """Verify only chrome triggers needs chrome source."""
        graph = self._build_graph(with_chrome=True, with_followers=False)
        self.PatchObject(
            depgraph, "get_sysroot_dependency_graph", return_value=graph
        )
        self.PatchObject(packages, "has_prebuilt", return_value=False)
        self.PatchObject(
            packages,
            "uprev_chrome",
            return_value=uprev_lib.UprevVersionedPackageResult(),
        )

        build_target = build_target_lib.BuildTarget("build_target")

        result = packages.needs_chrome_source(build_target)

        self.assertTrue(result.needs_chrome_source)
        self.assertTrue(result.builds_chrome)
        self.assertTrue(result.packages)
        self.assertEqual(
            {p.atom for p in result.packages}, {constants.CHROME_CP}
        )
        self.assertTrue(result.missing_chrome_prebuilt)
        self.assertFalse(result.missing_follower_prebuilt)
        self.assertFalse(result.local_uprev)

    def test_needs_followers_only(self):
        """Verify only chrome followers triggers needs chrome source."""
        graph = self._build_graph(with_chrome=False, with_followers=True)
        self.PatchObject(
            depgraph, "get_sysroot_dependency_graph", return_value=graph
        )
        self.PatchObject(packages, "has_prebuilt", return_value=False)
        self.PatchObject(
            packages,
            "uprev_chrome",
            return_value=uprev_lib.UprevVersionedPackageResult(),
        )

        build_target = build_target_lib.BuildTarget("build_target")

        result = packages.needs_chrome_source(build_target)

        self.assertTrue(result.needs_chrome_source)
        self.assertFalse(result.builds_chrome)
        self.assertTrue(result.packages)
        self.assertEqual(
            {p.atom for p in result.packages},
            set(constants.OTHER_CHROME_PACKAGES),
        )
        self.assertFalse(result.missing_chrome_prebuilt)
        self.assertTrue(result.missing_follower_prebuilt)
        self.assertFalse(result.local_uprev)

    def test_has_prebuilts(self):
        """Test prebuilts prevent us from needing chrome source."""
        graph = self._build_graph(with_chrome=True, with_followers=True)
        self.PatchObject(
            depgraph, "get_sysroot_dependency_graph", return_value=graph
        )
        self.PatchObject(packages, "has_prebuilt", return_value=True)
        self.PatchObject(
            packages,
            "uprev_chrome",
            return_value=uprev_lib.UprevVersionedPackageResult(),
        )

        build_target = build_target_lib.BuildTarget("build_target")

        result = packages.needs_chrome_source(build_target)

        self.assertFalse(result.needs_chrome_source)
        self.assertTrue(result.builds_chrome)
        self.assertFalse(result.packages)
        self.assertFalse(result.missing_chrome_prebuilt)
        self.assertFalse(result.missing_follower_prebuilt)
        self.assertFalse(result.local_uprev)

    def test_compile_source(self):
        """Test compile source ignores prebuilts."""
        graph = self._build_graph(with_chrome=True, with_followers=True)
        self.PatchObject(
            depgraph, "get_sysroot_dependency_graph", return_value=graph
        )
        self.PatchObject(packages, "has_prebuilt", return_value=True)
        self.PatchObject(
            packages,
            "uprev_chrome",
            return_value=uprev_lib.UprevVersionedPackageResult(),
        )

        build_target = build_target_lib.BuildTarget("build_target")

        result = packages.needs_chrome_source(build_target, compile_source=True)

        self.assertTrue(result.needs_chrome_source)
        self.assertTrue(result.builds_chrome)
        self.assertTrue(result.packages)
        self.assertEqual(
            len(result.packages), len(constants.OTHER_CHROME_PACKAGES) + 1
        )
        self.assertTrue(result.missing_chrome_prebuilt)
        self.assertTrue(result.missing_follower_prebuilt)
        self.assertFalse(result.local_uprev)

    def test_local_uprev(self):
        """Test compile source ignores prebuilts."""
        graph = self._build_graph(with_chrome=True, with_followers=True)
        self.PatchObject(
            depgraph, "get_sysroot_dependency_graph", return_value=graph
        )
        self.PatchObject(packages, "has_prebuilt", return_value=False)

        uprev_result = uprev_lib.UprevVersionedPackageResult()
        uprev_result.add_result("1.2.3.4", ["/tmp/foo"])
        self.PatchObject(packages, "uprev_chrome", return_value=uprev_result)

        build_target = build_target_lib.BuildTarget("build_target")

        result = packages.needs_chrome_source(build_target, compile_source=True)

        self.assertTrue(result.needs_chrome_source)
        self.assertTrue(result.builds_chrome)
        self.assertTrue(result.packages)
        self.assertEqual(
            len(result.packages), len(constants.OTHER_CHROME_PACKAGES) + 1
        )
        self.assertTrue(result.missing_chrome_prebuilt)
        self.assertTrue(result.missing_follower_prebuilt)
        self.assertTrue(result.local_uprev)


class GetTargetVersionTest(cros_test_lib.RunCommandTestCase):
    """Tests for get_target_version."""

    def setUp(self):
        self.build_target = build_target_lib.BuildTarget("build_target")

    def test_default_empty(self):
        """Default behavior with mostly stub empty data."""

        def GetBuildDependency(sysroot_path, board, mock_packages):
            assert sysroot_path == self.build_target.root
            assert board == self.build_target.name
            assert list(mock_packages) == [
                package_info.parse(constants.TARGET_OS_PKG)
            ]
            return {"package_deps": []}, {}

        self.PatchObject(
            dependency, "GetBuildDependency", side_effect=GetBuildDependency
        )
        ret = packages.get_target_versions(self.build_target)
        assert ret.android_version is None
        assert ret.android_branch is None
        assert ret.android_target is None
        assert ret.chrome_version is None
        assert isinstance(ret.platform_version, str)
        assert isinstance(ret.milestone_version, str)
        assert isinstance(ret.full_version, str)
        assert ret.lacros_version is None


class UprevDrivefsTest(cros_test_lib.MockTestCase):
    """Tests for uprev_drivefs."""

    def setUp(self):
        self.refs = [
            uprev_lib.GitRef(
                path="/chromeos/platform/drivefs-google3/",
                ref="refs/tags/drivefs_45.0.2",
                revision="123",
            )
        ]
        self.MOCK_DRIVEFS_EBUILD_PATH = "drivefs.45.0.2-r1.ebuild"

    def revisionBumpOutcome(self, ebuild_path):
        return uprev_lib.UprevResult(
            uprev_lib.Outcome.REVISION_BUMP, [ebuild_path]
        )

    def majorBumpOutcome(self, ebuild_path):
        return uprev_lib.UprevResult(
            uprev_lib.Outcome.VERSION_BUMP, [ebuild_path]
        )

    def sameVersionOutcome(self):
        return uprev_lib.UprevResult(uprev_lib.Outcome.SAME_VERSION_EXISTS)

    def test_latest_version_returns_none(self):
        """Test no refs were supplied"""
        output = packages.uprev_drivefs(None, [], chroot_lib.Chroot())
        self.assertFalse(output.uprevved)

    def test_drivefs_uprev_fails(self):
        """Test a single ref is supplied."""
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[None, None],
        )
        output = packages.uprev_drivefs(None, self.refs, chroot_lib.Chroot())
        self.assertFalse(output.uprevved)

    def test_same_version_exists(self):
        """Test the same version exists uprev should not happen."""
        drivefs_outcome = self.sameVersionOutcome()
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[drivefs_outcome],
        )
        output = packages.uprev_drivefs(None, self.refs, chroot_lib.Chroot())
        self.assertFalse(output.uprevved)

    def test_revision_bump_both_packages(self):
        """Test both packages uprev, should succeed."""
        drivefs_outcome = self.revisionBumpOutcome(
            self.MOCK_DRIVEFS_EBUILD_PATH
        )
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[drivefs_outcome],
        )
        output = packages.uprev_drivefs(None, self.refs, chroot_lib.Chroot())
        self.assertTrue(output.uprevved)

    def test_major_bump_both_packages(self):
        """Test both packages uprev, should succeed."""
        drivefs_outcome = self.majorBumpOutcome(self.MOCK_DRIVEFS_EBUILD_PATH)
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[drivefs_outcome],
        )
        output = packages.uprev_drivefs(None, self.refs, chroot_lib.Chroot())
        self.assertTrue(output.uprevved)


class UprevKernelAfdo(cros_test_lib.RunCommandTempDirTestCase):
    """Tests for uprev_kernel_afdo."""

    def setUp(self):
        # patch_ebuild_vars is tested separately.
        self.mock_patch = self.PatchObject(packages, "patch_ebuild_vars")
        self.PatchObject(constants, "SOURCE_ROOT", new=self.tempdir)
        self.metadata_dir = os.path.join(
            "src",
            "third_party",
            "toolchain-utils",
            "afdo_metadata",
        )
        osutils.SafeMakedirs(os.path.join(self.tempdir, self.metadata_dir))

    def test_uprev_kernel_afdo_version(self):
        """Test kernel afdo version uprev."""
        json_files = {
            "kernel_afdo.json": (
                "{\n"
                '  "chromeos-kernel-5_4": {\n'
                '    "name": "R106-12345.0-0123456789"\n'
                "  }\n"
                "}"
            ),
            "kernel_arm_afdo.json": (
                "{\n"
                '  "chromeos-kernel-5_15": {\n'
                '    "name": "R107-67890.0-0123456789"\n'
                "  }\n"
                "}"
            ),
        }
        for f, contents in json_files.items():
            self.WriteTempFile(os.path.join(self.metadata_dir, f), contents)

        returned_output = packages.uprev_kernel_afdo(
            None, [], chroot_lib.Chroot()
        )

        package_root = os.path.join(
            constants.SOURCE_ROOT,
            constants.CHROMIUMOS_OVERLAY_DIR,
            "sys-kernel",
        )
        expect_result = [
            uprev_lib.UprevVersionedPackageModifications(
                new_version="R106-12345.0-0123456789",
                files=[
                    os.path.join(
                        package_root,
                        "chromeos-kernel-5_4",
                        "chromeos-kernel-5_4-9999.ebuild",
                    ),
                    os.path.join(
                        package_root, "chromeos-kernel-5_4", "Manifest"
                    ),
                ],
            ),
            uprev_lib.UprevVersionedPackageModifications(
                new_version="R107-67890.0-0123456789",
                files=[
                    os.path.join(
                        package_root,
                        "chromeos-kernel-5_15",
                        "chromeos-kernel-5_15-9999.ebuild",
                    ),
                    os.path.join(
                        package_root, "chromeos-kernel-5_15", "Manifest"
                    ),
                ],
            ),
        ]
        self.assertTrue(returned_output.uprevved)
        self.assertEqual(returned_output.modified, expect_result)

    def test_uprev_kernel_afdo_empty_json(self):
        """Test kernel afdo version unchanged."""
        json_files = {
            "kernel_afdo.json": "{}",
            "kernel_arm_afdo.json": "{}",
        }
        for f, contents in json_files.items():
            self.WriteTempFile(os.path.join(self.metadata_dir, f), contents)

        returned_output = packages.uprev_kernel_afdo(
            None, [], chroot_lib.Chroot()
        )
        self.assertFalse(returned_output.uprevved)

    def test_uprev_kernel_afdo_empty_file(self):
        """Test malformed json raises."""
        json_files = {
            "kernel_afdo.json": "",
            "kernel_arm_afdo.json": "",
        }
        for f, contents in json_files.items():
            self.WriteTempFile(os.path.join(self.metadata_dir, f), contents)

        with self.assertRaisesRegex(
            json.decoder.JSONDecodeError, "Expecting value"
        ):
            packages.uprev_kernel_afdo(None, [], chroot_lib.Chroot())

    def test_uprev_kernel_afdo_manifest_raises(self):
        """Test manifest update raises."""
        json_files = {
            "kernel_afdo.json": (
                "{\n"
                '  "chromeos-kernel-5_4": {\n'
                '    "name": "R106-12345.0-0123456789"\n'
                "  }\n"
                "}"
            ),
        }
        for f, contents in json_files.items():
            self.WriteTempFile(os.path.join(self.metadata_dir, f), contents)
        # run() raises exception.
        self.rc.SetDefaultCmdResult(
            side_effect=cros_build_lib.RunCommandError("error")
        )

        with self.assertRaises(uprev_lib.EbuildManifestError):
            packages.uprev_kernel_afdo(None, [], chroot_lib.Chroot())


# TODO(chenghaoyang): Shouldn't use uprev_workon_ebuild_to_version.
class UprevPerfettoTest(cros_test_lib.MockTestCase):
    """Tests for uprev_perfetto."""

    def setUp(self):
        self.refs = [
            uprev_lib.GitRef(path="/foo", ref="refs/tags/v12.0", revision="123")
        ]
        self.MOCK_PERFETTO_EBUILD_PATH = "perfetto-12.0-r1.ebuild"
        self.MOCK_PERFETTO_PROTO_EBUILD_PATH = "perfetto-protos-12.0-r1.ebuild"

    def revisionBumpOutcome(self):
        return [
            uprev_lib.UprevResult(
                uprev_lib.Outcome.REVISION_BUMP,
                [self.MOCK_PERFETTO_EBUILD_PATH],
            ),
            uprev_lib.UprevResult(
                uprev_lib.Outcome.REVISION_BUMP,
                [self.MOCK_PERFETTO_PROTO_EBUILD_PATH],
            ),
        ]

    def majorBumpOutcome(self):
        return [
            uprev_lib.UprevResult(
                uprev_lib.Outcome.VERSION_BUMP, [self.MOCK_PERFETTO_EBUILD_PATH]
            ),
            uprev_lib.UprevResult(
                uprev_lib.Outcome.VERSION_BUMP,
                [self.MOCK_PERFETTO_PROTO_EBUILD_PATH],
            ),
        ]

    def newerVersionOutcome(self):
        return uprev_lib.UprevResult(uprev_lib.Outcome.NEWER_VERSION_EXISTS)

    def sameVersionOutcome(self):
        return uprev_lib.UprevResult(uprev_lib.Outcome.SAME_VERSION_EXISTS)

    def test_latest_version_returns_none(self):
        """Test no refs were supplied"""
        output = packages.uprev_perfetto(None, [], chroot_lib.Chroot())
        self.assertFalse(output.uprevved)

    def test_perfetto_uprev_fails(self):
        """Test a single ref is supplied."""
        self.PatchObject(
            uprev_lib, "uprev_workon_ebuild_to_version", side_effect=[None]
        )
        output = packages.uprev_perfetto(None, self.refs, chroot_lib.Chroot())
        self.assertFalse(output.uprevved)

    def test_newer_version_exists(self):
        """Test the newer version exists uprev should not happen."""
        perfetto_outcome = self.newerVersionOutcome()
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[perfetto_outcome],
        )
        output = packages.uprev_perfetto(None, self.refs, chroot_lib.Chroot())
        self.assertFalse(output.uprevved)

    def test_same_version_exists(self):
        """Test the same version exists uprev should not happen."""
        perfetto_outcome = self.sameVersionOutcome()
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[perfetto_outcome],
        )
        output = packages.uprev_perfetto(None, self.refs, chroot_lib.Chroot())
        self.assertFalse(output.uprevved)

    def test_revision_bump_perfetto_package(self):
        """Test perfetto package uprev."""
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=self.revisionBumpOutcome(),
        )
        output = packages.uprev_perfetto(None, self.refs, chroot_lib.Chroot())
        self.assertTrue(output.uprevved)
        self.assertEqual(
            output.modified[0].files, [self.MOCK_PERFETTO_EBUILD_PATH]
        )
        self.assertEqual(
            output.modified[1].files, [self.MOCK_PERFETTO_PROTO_EBUILD_PATH]
        )

    def test_major_bump_perfetto_package(self):
        """Test perfetto package uprev."""
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=self.majorBumpOutcome(),
        )
        output = packages.uprev_perfetto(None, self.refs, chroot_lib.Chroot())
        self.assertTrue(output.uprevved)
        self.assertEqual(
            output.modified[0].files, [self.MOCK_PERFETTO_EBUILD_PATH]
        )
        self.assertEqual(
            output.modified[1].files, [self.MOCK_PERFETTO_PROTO_EBUILD_PATH]
        )

    def test_revision_bump_trunk(self):
        """Test revision bump on receiving non-versioned trunk refs."""
        refs = [
            uprev_lib.GitRef(
                path="/foo", ref="refs/heads/main", revision="0123456789abcdef"
            )
        ]
        self.PatchObject(
            uprev_lib, "get_stable_ebuild_version", return_value="12.0"
        )
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=self.revisionBumpOutcome(),
        )
        output = packages.uprev_perfetto(None, refs, chroot_lib.Chroot())

        self.assertTrue(output.uprevved)
        self.assertEqual(
            output.modified[0].files, [self.MOCK_PERFETTO_EBUILD_PATH]
        )
        self.assertEqual(output.modified[0].new_version, "12.0-012345678")
        self.assertEqual(
            output.modified[1].files, [self.MOCK_PERFETTO_PROTO_EBUILD_PATH]
        )
        self.assertEqual(output.modified[1].new_version, "12.0-012345678")


class UprevLacrosTest(cros_test_lib.MockTestCase):
    """Tests for uprev_lacros"""

    def setUp(self):
        self.refs = [
            uprev_lib.GitRef(
                path="/lacros", ref="refs/heads/main", revision="123.456.789.0"
            )
        ]
        self.MOCK_LACROS_EBUILD_PATH = "chromeos-lacros-123.456.789.0-r1.ebuild"

    def revisionBumpOutcome(self, ebuild_path):
        return uprev_lib.UprevResult(
            uprev_lib.Outcome.REVISION_BUMP, [ebuild_path]
        )

    def majorBumpOutcome(self, ebuild_path):
        return uprev_lib.UprevResult(
            uprev_lib.Outcome.VERSION_BUMP, [ebuild_path]
        )

    def newerVersionOutcome(self, ebuild_path):
        return uprev_lib.UprevResult(
            uprev_lib.Outcome.NEWER_VERSION_EXISTS, [ebuild_path]
        )

    def sameVersionOutcome(self, ebuild_path):
        return uprev_lib.UprevResult(
            uprev_lib.Outcome.SAME_VERSION_EXISTS, [ebuild_path]
        )

    def newEbuildCreatedOutcome(self, ebuild_path):
        return uprev_lib.UprevResult(
            uprev_lib.Outcome.NEW_EBUILD_CREATED, [ebuild_path]
        )

    def test_lacros_uprev_fails(self):
        """Test a lacros package uprev with no triggers"""
        self.PatchObject(
            uprev_lib, "uprev_workon_ebuild_to_version", side_effect=[None]
        )
        with self.assertRaises(IndexError):
            packages.uprev_lacros(None, [], chroot_lib.Chroot())

    def test_lacros_uprev_revision_bump(self):
        """Test lacros package uprev."""
        lacros_outcome = self.revisionBumpOutcome(self.MOCK_LACROS_EBUILD_PATH)
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[lacros_outcome],
        )
        output = packages.uprev_lacros(None, self.refs, chroot_lib.Chroot())
        self.assertTrue(output.uprevved)

    def test_lacros_uprev_version_bump(self):
        """Test lacros package uprev."""
        lacros_outcome = self.majorBumpOutcome(self.MOCK_LACROS_EBUILD_PATH)
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[lacros_outcome],
        )
        output = packages.uprev_lacros(None, self.refs, chroot_lib.Chroot())
        self.assertTrue(output.uprevved)

    def test_lacros_uprev_new_ebuild_created(self):
        """Test lacros package uprev."""
        lacros_outcome = self.newEbuildCreatedOutcome(
            self.MOCK_LACROS_EBUILD_PATH
        )
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[lacros_outcome],
        )
        output = packages.uprev_lacros(None, self.refs, chroot_lib.Chroot())
        self.assertTrue(output.uprevved)

    def test_lacros_uprev_newer_version_exist(self):
        """Test the newer version exists uprev should not happen."""
        lacros_outcome = self.newerVersionOutcome(self.MOCK_LACROS_EBUILD_PATH)
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[lacros_outcome],
        )
        output = packages.uprev_lacros(None, self.refs, chroot_lib.Chroot())
        self.assertFalse(output.uprevved)

    def test_lacros_uprev_same_version_exist(self):
        """Test the same version exists uprev should not happen."""
        lacros_outcome = self.sameVersionOutcome(self.MOCK_LACROS_EBUILD_PATH)
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[lacros_outcome],
        )
        output = packages.uprev_lacros(None, self.refs, chroot_lib.Chroot())
        self.assertFalse(output.uprevved)


class UprevLacrosInParallelTest(cros_test_lib.MockTestCase):
    """Tests for uprev_lacros"""

    def setUp(self):
        self.refs = [
            uprev_lib.GitRef(
                path="/lacros", revision="abc123", ref="refs/tags/123.456.789.0"
            )
        ]
        self.MOCK_LACROS_EBUILD_PATH = "chromeos-lacros-123.456.789.0-r1.ebuild"

    def revisionBumpOutcome(self, ebuild_path):
        return uprev_lib.UprevResult(
            uprev_lib.Outcome.REVISION_BUMP, [ebuild_path]
        )

    def majorBumpOutcome(self, ebuild_path):
        return uprev_lib.UprevResult(
            uprev_lib.Outcome.VERSION_BUMP, [ebuild_path]
        )

    def newerVersionOutcome(self, ebuild_path):
        return uprev_lib.UprevResult(
            uprev_lib.Outcome.NEWER_VERSION_EXISTS, [ebuild_path]
        )

    def sameVersionOutcome(self, ebuild_path):
        return uprev_lib.UprevResult(
            uprev_lib.Outcome.SAME_VERSION_EXISTS, [ebuild_path]
        )

    def newEbuildCreatedOutcome(self, ebuild_path):
        return uprev_lib.UprevResult(
            uprev_lib.Outcome.NEW_EBUILD_CREATED, [ebuild_path]
        )

    def test_lacros_uprev_fails(self):
        """Test a lacros package uprev with no triggers"""
        self.PatchObject(
            uprev_lib, "uprev_workon_ebuild_to_version", side_effect=[None]
        )
        with self.assertRaises(uprev_lib.NoRefsError):
            packages.uprev_lacros_in_parallel(None, [], chroot_lib.Chroot())

    def test_lacros_uprev_revision_bump(self):
        """Test lacros package uprev."""
        lacros_outcome = self.revisionBumpOutcome(self.MOCK_LACROS_EBUILD_PATH)
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[lacros_outcome],
        )
        output = packages.uprev_lacros_in_parallel(
            None, self.refs, chroot_lib.Chroot()
        )
        self.assertTrue(output.uprevved)

    def test_lacros_uprev_version_bump(self):
        """Test lacros package uprev."""
        lacros_outcome = self.majorBumpOutcome(self.MOCK_LACROS_EBUILD_PATH)
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[lacros_outcome],
        )
        output = packages.uprev_lacros_in_parallel(
            None, self.refs, chroot_lib.Chroot()
        )
        self.assertTrue(output.uprevved)

    def test_lacros_uprev_new_ebuild_created(self):
        """Test lacros package uprev."""
        lacros_outcome = self.newEbuildCreatedOutcome(
            self.MOCK_LACROS_EBUILD_PATH
        )
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[lacros_outcome],
        )
        output = packages.uprev_lacros_in_parallel(
            None, self.refs, chroot_lib.Chroot()
        )
        self.assertTrue(output.uprevved)

    def test_lacros_uprev_newer_version_exist(self):
        """Test the newer version exists uprev should not happen."""
        lacros_outcome = self.newerVersionOutcome(self.MOCK_LACROS_EBUILD_PATH)
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[lacros_outcome],
        )
        output = packages.uprev_lacros_in_parallel(
            None, self.refs, chroot_lib.Chroot()
        )
        self.assertFalse(output.uprevved)

    def test_lacros_uprev_same_version_exist(self):
        """Test the same version exists uprev should not happen."""
        lacros_outcome = self.sameVersionOutcome(self.MOCK_LACROS_EBUILD_PATH)
        self.PatchObject(
            uprev_lib,
            "uprev_workon_ebuild_to_version",
            side_effect=[lacros_outcome],
        )
        output = packages.uprev_lacros_in_parallel(
            None, self.refs, chroot_lib.Chroot()
        )
        self.assertFalse(output.uprevved)


class UprevStarbaseArtifactsTest(cros_test_lib.RunCommandTempDirTestCase):
    """Tests of uprev of starbase artifacts ebuild."""

    package_name = "chromeos-base/starbase-artifacts"
    version = "2.4.6"
    revision = "111"
    ebuild_name_format = "starbase-artifacts-%s%s.ebuild"
    old_ebuild_name = ebuild_name_format % (version, f"-r{revision}")
    ebuild_content_format = """# Buildable ebuild
foo
bar
baz
SRC_URI="${DISTFILES}/%s"
zab
rab
oof
"""

    def test_uprev(self):
        """Test that the ebuild is modified and uprevved."""

        # Create ebuild directory.
        directory_tree = (
            D(self.package_name, [self.old_ebuild_name, "Manifest"]),
        )
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, directory_tree)
        package_path = os.path.join(self.tempdir, self.package_name)
        old_ebuild_path = os.path.join(package_path, self.old_ebuild_name)
        old_ebuild_content = self.ebuild_content_format % "to-be-clobbered"

        # Create mock ebuild to be uprevved.
        self.WriteTempFile(old_ebuild_path, old_ebuild_content)
        gcs_name = "starbase-artifacts-20230101-r42-rc123"
        manifest_path = os.path.join(package_path, "Manifest")

        # Run the function under test.
        modified = packages.starbase_find_and_uprev(
            package_path,
            gcs_name,
            chroot_lib.Chroot(),
        )

        # Check that the expected files were modified.
        new_rev = f"-r{str(int(self.revision) + 1)}"
        new_ebuild_name = self.ebuild_name_format % (self.version, new_rev)
        new_ebuild_path = os.path.join(package_path, new_ebuild_name)
        releaseless_ebuild_name = self.ebuild_name_format % (self.version, "")
        releaseless_ebuild_path = os.path.join(
            package_path, releaseless_ebuild_name
        )

        self.assertEqual(modified[0], manifest_path)
        self.assertEqual(modified[1], releaseless_ebuild_path)
        self.assertEqual(modified[2], old_ebuild_path)
        self.assertEqual(modified[3], new_ebuild_path)

        tarfile_name = f"{gcs_name}/starbase_client_tarfile.tar.zst"
        # Check that the new ebuild file contains the expected content.
        new_ebuild_content = self.ebuild_content_format % tarfile_name
        found_content = osutils.ReadFile(new_ebuild_path)
        self.assertEqual(new_ebuild_content, found_content)
