# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for Android operations."""

from unittest import mock

from chromite.api import api_config
from chromite.api.controller import android
from chromite.api.gen.chromite.api import android_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import build_target_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.service import android as service_android
from chromite.service import packages


class GetLatestBuildTest(cros_test_lib.MockTestCase, api_config.ApiConfigMixin):
    """Unittests for GetLatestBuild."""

    def setUp(self):
        self._mock = self.PatchObject(service_android, "GetLatestBuild")
        self._mock.return_value = ("7123456", {})
        self._output_proto = android_pb2.GetLatestBuildResponse()

    def _GetRequest(self, android_build_branch=None, android_package=None):
        req = android_pb2.GetLatestBuildRequest()
        if android_build_branch is not None:
            req.android_build_branch = android_build_branch
        if android_package is not None:
            req.android_package = android_package
        return req

    def testValidateOnly(self):
        """Test that a validate only call does not execute any logic."""
        req = self._GetRequest(android_package="android-package")
        android.GetLatestBuild(
            req, self._output_proto, self.validate_only_config
        )
        self._mock.assert_not_called()

    def testMockCall(self):
        """Test a mock call does not execute logic, returns mocked value."""
        req = self._GetRequest(android_package="android-package")
        android.GetLatestBuild(req, self._output_proto, self.mock_call_config)
        self._mock.assert_not_called()
        self.assertEqual(self._output_proto.android_version, "7123456")

    def testFailsIfBranchAndPackageMissing(self):
        """Fails if android_build_branch and android_package are missing."""
        req = self._GetRequest()
        with self.assertRaises(cros_build_lib.DieSystemExit):
            android.GetLatestBuild(req, self._output_proto, self.api_config)
        self._mock.assert_not_called()

    def testFailsIfPackageMissing(self):
        """Fails if android_package is missing."""
        req = self._GetRequest(android_build_branch="android-branch")
        with self.assertRaises(cros_build_lib.DieSystemExit):
            android.GetLatestBuild(req, self._output_proto, self.api_config)
        self._mock.assert_not_called()

    def testPackageSpecified(self):
        """Test calling with Android package specified."""
        req = self._GetRequest(android_package="android-package")
        android.GetLatestBuild(req, self._output_proto, self.api_config)
        self.assertEqual(self._output_proto.android_version, "7123456")

    def testBranchAndPackageSpecified(self):
        """Test calling with both Android branch and package specified."""
        req = self._GetRequest(
            android_build_branch="android-branch",
            android_package="android-package",
        )
        android.GetLatestBuild(req, self._output_proto, self.api_config)
        self._mock.assert_called_once_with(
            "android-package", build_branch="android-branch"
        )
        self.assertEqual(self._output_proto.android_version, "7123456")


class MarkStableTest(cros_test_lib.MockTestCase, api_config.ApiConfigMixin):
    """Unittests for MarkStable."""

    def setUp(self):
        self.uprev = self.PatchObject(packages, "uprev_android")

        self.input_proto = android_pb2.MarkStableRequest()
        self.input_proto.package_name = "android-package-name"
        self.input_proto.android_build_branch = "android_build_branch"
        self.input_proto.android_version = "android-version"
        self.input_proto.build_targets.add().name = "foo"
        self.input_proto.build_targets.add().name = "bar"
        self.input_proto.skip_commit = True
        self.input_proto.ignore_data_collector_artifacts = False

        self.build_targets = [
            build_target_lib.BuildTarget("foo"),
            build_target_lib.BuildTarget("bar"),
        ]

        self.response = android_pb2.MarkStableResponse()

    def testValidateOnly(self):
        """Verify a validate-only call does not execute any logic."""
        android.MarkStable(
            self.input_proto, self.response, self.validate_only_config
        )
        self.uprev.assert_not_called()

    def testMockCall(self):
        """Test a mock call does not execute logic, returns mocked value."""
        android.MarkStable(
            self.input_proto, self.response, self.mock_call_config
        )
        self.uprev.assert_not_called()
        self.assertEqual(
            self.response.status, android_pb2.MARK_STABLE_STATUS_SUCCESS
        )
        self.assertEqual(self.response.android_atom.category, "category")
        self.assertEqual(
            self.response.android_atom.package_name, "android-package-name"
        )
        self.assertEqual(self.response.android_atom.version, "1.2")

    def testFailsIfPackageNameMissing(self):
        """Fails if package_name is missing."""
        self.input_proto.package_name = ""
        with self.assertRaises(cros_build_lib.DieSystemExit):
            android.MarkStable(self.input_proto, self.response, self.api_config)
        self.uprev.assert_not_called()

    def testCallsCommandCorrectly(self):
        """Test that packages.uprev_android is called correctly."""
        self.uprev.return_value = packages.UprevAndroidResult(
            revved=True, android_atom="cat/android-1.2.3"
        )
        atom = common_pb2.PackageInfo()
        atom.category = "cat"
        atom.package_name = "android"
        atom.version = "1.2.3"
        android.MarkStable(self.input_proto, self.response, self.api_config)
        self.uprev.assert_called_once_with(
            android_package=self.input_proto.package_name,
            chroot=mock.ANY,
            build_targets=self.build_targets,
            android_build_branch=self.input_proto.android_build_branch,
            android_version=self.input_proto.android_version,
            skip_commit=self.input_proto.skip_commit,
            ignore_data_collector_artifacts=(
                self.input_proto.ignore_data_collector_artifacts
            ),
        )
        self.assertEqual(self.response.android_atom, atom)
        self.assertEqual(
            self.response.status, android_pb2.MARK_STABLE_STATUS_SUCCESS
        )

    def testHandlesEarlyExit(self):
        """Test that early exit is handled correctly."""
        self.uprev.return_value = packages.UprevAndroidResult(revved=False)
        android.MarkStable(self.input_proto, self.response, self.api_config)
        self.uprev.assert_called_once_with(
            android_package=self.input_proto.package_name,
            chroot=mock.ANY,
            build_targets=self.build_targets,
            android_build_branch=self.input_proto.android_build_branch,
            android_version=self.input_proto.android_version,
            skip_commit=self.input_proto.skip_commit,
            ignore_data_collector_artifacts=(
                self.input_proto.ignore_data_collector_artifacts
            ),
        )
        self.assertEqual(
            self.response.status, android_pb2.MARK_STABLE_STATUS_EARLY_EXIT
        )

    def testHandlesPinnedUprevError(self):
        """Test that pinned error is handled correctly."""
        self.uprev.side_effect = packages.AndroidIsPinnedUprevError(
            "pin/xx-1.1"
        )
        atom = common_pb2.PackageInfo()
        atom.category = "pin"
        atom.package_name = "xx"
        atom.version = "1.1"
        android.MarkStable(self.input_proto, self.response, self.api_config)
        self.uprev.assert_called_once_with(
            android_package=self.input_proto.package_name,
            chroot=mock.ANY,
            build_targets=self.build_targets,
            android_build_branch=self.input_proto.android_build_branch,
            android_version=self.input_proto.android_version,
            skip_commit=self.input_proto.skip_commit,
            ignore_data_collector_artifacts=(
                self.input_proto.ignore_data_collector_artifacts
            ),
        )
        self.assertEqual(self.response.android_atom, atom)
        self.assertEqual(
            self.response.status, android_pb2.MARK_STABLE_STATUS_PINNED
        )


class UnpinVersionTest(cros_test_lib.MockTestCase, api_config.ApiConfigMixin):
    """Unittests for UnpinVersion."""

    def testCallsUnlink(self):
        """SetAndroid calls service with correct args."""
        safeunlink = self.PatchObject(osutils, "SafeUnlink")
        self.PatchObject(constants, "_FindSourceRoot", return_value="SRCROOT")

        # This has the side effect of making sure that input and output proto
        # are not actually used.
        android.UnpinVersion(None, None, self.api_config)
        safeunlink.assert_called_once_with(android.ANDROIDPIN_MASK_PATH)

    def testValidateOnly(self):
        """Verify a validate-only call does not execute any logic."""
        safeunlink = self.PatchObject(osutils, "SafeUnlink")

        android.UnpinVersion(None, None, self.validate_only_config)
        safeunlink.assert_not_called()

    def testMockCall(self):
        """Test that a mock call does not execute logic."""
        safeunlink = self.PatchObject(osutils, "SafeUnlink")

        android.UnpinVersion(None, None, self.mock_call_config)
        safeunlink.assert_not_called()
        # android.UnpinVersion does not modify the response.


class WriteLKGBTest(cros_test_lib.MockTestCase, api_config.ApiConfigMixin):
    """Unittests for WriteLKGB."""

    def setUp(self):
        self._output_proto = android_pb2.WriteLKGBResponse()

        self.PatchObject(
            service_android,
            "GetAndroidBranchForPackage",
            return_value="android-branch",
        )
        self.PatchObject(
            service_android,
            "GetAndroidPackageDir",
            return_value="android-package-dir",
        )

        # Mock milestone for FindRuntimeArtifactsPin().
        self.PatchObject(
            packages,
            "determine_milestone_version",
            return_value="999",
        )

    def testValidateOnly(self):
        """Test that a validate only call does not execute any logic."""
        mock_write_lkgb = self.PatchObject(service_android, "WriteLKGB")

        req = android_pb2.WriteLKGBRequest(
            android_package="android-package", android_version="android-version"
        )
        android.WriteLKGB(req, self._output_proto, self.validate_only_config)

        mock_write_lkgb.assert_not_called()

    def testMockCall(self):
        """Test a mock call does not execute logic, returns mocked value."""
        mock_write_lkgb = self.PatchObject(service_android, "WriteLKGB")

        req = android_pb2.WriteLKGBRequest(
            android_package="android-package", android_version="android-version"
        )
        android.WriteLKGB(req, self._output_proto, self.mock_call_config)

        mock_write_lkgb.assert_not_called()
        self.assertSequenceEqual(
            self._output_proto.modified_files, ["fake_file"]
        )

    def testFailsIfAndroidPackageMissing(self):
        """Fails if android_package is missing."""
        req = android_pb2.WriteLKGBRequest(android_version="android-version")
        with self.assertRaises(cros_build_lib.DieSystemExit):
            android.WriteLKGB(req, self._output_proto, self.api_config)

    def testFailsIfAndroidVersionMissing(self):
        """Fails if android_version is missing."""
        req = android_pb2.WriteLKGBRequest(android_package="android-package")
        with self.assertRaises(cros_build_lib.DieSystemExit):
            android.WriteLKGB(req, self._output_proto, self.api_config)

    def testSuccess(self):
        """Successful request."""
        mock_read_lkgb = self.PatchObject(
            service_android,
            "ReadLKGB",
            return_value=dict(build_id="old-version", branch="android-branch"),
        )
        mock_write_lkgb = self.PatchObject(
            service_android, "WriteLKGB", return_value="mock_file"
        )
        self.PatchObject(
            service_android,
            "FindRuntimeArtifactsPin",
            return_value=None,
        )

        req = android_pb2.WriteLKGBRequest(
            android_package="android-package", android_version="android-version"
        )
        android.WriteLKGB(req, self._output_proto, self.api_config)

        mock_read_lkgb.assert_called_once_with("android-package-dir")
        mock_write_lkgb.assert_called_once_with(
            "android-package-dir",
            dict(build_id="android-version", branch="android-branch"),
        )
        self.assertSequenceEqual(
            self._output_proto.modified_files, ["mock_file"]
        )

    def testSameVersion(self):
        """Nothing is modified if LKGB is already the same version."""
        mock_read_lkgb = self.PatchObject(
            service_android,
            "ReadLKGB",
            return_value=dict(
                build_id="android-version",
                branch="android-branch",
                runtime_artifacts_pin="runtime-artifacts-pin",
            ),
        )
        mock_write_lkgb = self.PatchObject(
            service_android,
            "WriteLKGB",
            side_effect=Exception("shouldn't get called"),
        )
        self.PatchObject(
            service_android,
            "FindRuntimeArtifactsPin",
            return_value="runtime-artifacts-pin",
        )

        req = android_pb2.WriteLKGBRequest(
            android_package="android-package", android_version="android-version"
        )
        android.WriteLKGB(req, self._output_proto, self.api_config)

        mock_read_lkgb.assert_called_once_with("android-package-dir")
        mock_write_lkgb.assert_not_called()
        self.assertSequenceEqual(self._output_proto.modified_files, [])

    def testMissingLKGB(self):
        """Proceed if LKGB file is currently missing."""
        mock_read_lkgb = self.PatchObject(
            service_android,
            "ReadLKGB",
            side_effect=service_android.MissingLKGBError(),
        )
        mock_write_lkgb = self.PatchObject(
            service_android, "WriteLKGB", return_value="mock_file"
        )
        self.PatchObject(
            service_android,
            "FindRuntimeArtifactsPin",
            return_value=None,
        )

        req = android_pb2.WriteLKGBRequest(
            android_package="android-package", android_version="android-version"
        )
        android.WriteLKGB(req, self._output_proto, self.api_config)

        mock_read_lkgb.assert_called_once_with("android-package-dir")
        mock_write_lkgb.assert_called_once_with(
            "android-package-dir",
            dict(build_id="android-version", branch="android-branch"),
        )
        self.assertSequenceEqual(
            self._output_proto.modified_files, ["mock_file"]
        )

    def testInvalidLKGB(self):
        """Proceed if LKGB file currently contains invalid content."""
        mock_read_lkgb = self.PatchObject(
            service_android,
            "ReadLKGB",
            side_effect=service_android.InvalidLKGBError(),
        )
        mock_write_lkgb = self.PatchObject(
            service_android, "WriteLKGB", return_value="mock_file"
        )
        self.PatchObject(
            service_android,
            "FindRuntimeArtifactsPin",
            return_value=None,
        )

        req = android_pb2.WriteLKGBRequest(
            android_package="android-package", android_version="android-version"
        )
        android.WriteLKGB(req, self._output_proto, self.api_config)

        mock_read_lkgb.assert_called_once_with("android-package-dir")
        mock_write_lkgb.assert_called_once_with(
            "android-package-dir",
            dict(build_id="android-version", branch="android-branch"),
        )
        self.assertSequenceEqual(
            self._output_proto.modified_files, ["mock_file"]
        )

    def testNewRuntimeArtifactsPin(self):
        """Proceed if a new runtime artifacts pin is found."""
        mock_read_lkgb = self.PatchObject(
            service_android,
            "ReadLKGB",
            return_value=dict(build_id="android-version"),
        )
        mock_write_lkgb = self.PatchObject(
            service_android,
            "WriteLKGB",
            return_value="mock_file",
        )
        self.PatchObject(
            service_android,
            "FindRuntimeArtifactsPin",
            return_value="runtime-artifacts-pin",
        )

        req = android_pb2.WriteLKGBRequest(
            android_package="android-package", android_version="android-version"
        )
        android.WriteLKGB(req, self._output_proto, self.api_config)

        mock_read_lkgb.assert_called_once_with("android-package-dir")
        mock_write_lkgb.assert_called_once_with(
            "android-package-dir",
            dict(
                build_id="android-version",
                branch="android-branch",
                runtime_artifacts_pin="runtime-artifacts-pin",
            ),
        )
        self.assertSequenceEqual(
            self._output_proto.modified_files, ["mock_file"]
        )
