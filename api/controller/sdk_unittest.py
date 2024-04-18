# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""SDK tests."""

import datetime
import os
from pathlib import Path
from typing import List, Optional, Union
from unittest import mock

from chromite.api import api_config
from chromite.api import controller
from chromite.api.controller import controller_util
from chromite.api.controller import sdk as sdk_controller
from chromite.api.gen.chromite.api import sdk_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import sysroot_lib
from chromite.lib.parser import package_info
from chromite.service import sdk as sdk_service


class SdkCreateTest(cros_test_lib.MockTestCase, api_config.ApiConfigMixin):
    """Create tests."""

    def setUp(self):
        """Setup method."""
        # We need to run the command outside the chroot.
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)
        self.response = sdk_pb2.CreateResponse()

    def _GetRequest(
        self,
        no_replace=False,
        bootstrap=False,
        cache_path=None,
        chroot_path=None,
        sdk_version=None,
        skip_chroot_upgrade=False,
        ccache_disable=False,
    ):
        """Helper to build a create request message."""
        request = sdk_pb2.CreateRequest()
        request.flags.no_replace = no_replace
        request.flags.bootstrap = bootstrap

        if cache_path:
            request.chroot.cache_dir = cache_path
        if chroot_path:
            request.chroot.path = chroot_path
        if sdk_version:
            request.sdk_version = sdk_version
        if skip_chroot_upgrade:
            request.skip_chroot_upgrade = skip_chroot_upgrade
        if ccache_disable:
            request.ccache_disable = ccache_disable

        return request

    def testValidateOnly(self):
        """Verify a validate-only call does not execute any logic."""
        patch = self.PatchObject(sdk_service, "Create")

        sdk_controller.Create(
            self._GetRequest(), self.response, self.validate_only_config
        )
        patch.assert_not_called()

    def testMockCall(self):
        """Sanity check that a mock call does not execute any logic."""
        patch = self.PatchObject(sdk_service, "Create")

        rc = sdk_controller.Create(
            self._GetRequest(), self.response, self.mock_call_config
        )
        patch.assert_not_called()
        self.assertFalse(rc)
        self.assertTrue(self.response.version.version)

    def testSuccess(self):
        """Test the successful call output handling."""
        self.PatchObject(sdk_service, "Create", return_value=1)

        request = self._GetRequest()

        sdk_controller.Create(request, self.response, self.api_config)

        self.assertEqual(1, self.response.version.version)

    def testFalseArguments(self):
        """Test False argument handling."""
        # Create the patches.
        self.PatchObject(sdk_service, "Create", return_value=1)
        args_patch = self.PatchObject(sdk_service, "CreateArguments")

        # Flag translation tests.
        # Test all false values in the message.
        request = self._GetRequest(
            no_replace=False,
            bootstrap=False,
        )
        sdk_controller.Create(request, self.response, self.api_config)
        args_patch.assert_called_with(
            replace=True,
            bootstrap=False,
            chroot=mock.ANY,
            sdk_version=mock.ANY,
            skip_chroot_upgrade=mock.ANY,
            ccache_disable=mock.ANY,
        )

    def testTrueArguments(self):
        """Test True arguments handling."""
        # Create the patches.
        self.PatchObject(sdk_service, "Create", return_value=1)
        args_patch = self.PatchObject(sdk_service, "CreateArguments")

        # Test all True values in the message.
        request = self._GetRequest(
            no_replace=True,
            bootstrap=True,
            sdk_version="foo",
            skip_chroot_upgrade=True,
            ccache_disable=True,
        )
        sdk_controller.Create(request, self.response, self.api_config)
        args_patch.assert_called_with(
            replace=False,
            bootstrap=True,
            chroot=mock.ANY,
            sdk_version="foo",
            skip_chroot_upgrade=True,
            ccache_disable=True,
        )


class SdkCleanTest(cros_test_lib.MockTestCase, api_config.ApiConfigMixin):
    """Clean tests."""

    def setUp(self):
        """Setup method."""
        # We need to run the command outside the chroot.
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)
        self.response = sdk_pb2.CleanResponse()

    def _GetRequest(self, chroot_path=None, incrementals=False):
        """Helper to build a clean request message."""
        request = sdk_pb2.CleanRequest()
        if chroot_path:
            request.chroot.path = chroot_path

        request.incrementals = incrementals

        return request

    def testMockCall(self):
        """Sanity check that a mock call does not execute any logic."""
        patch = self.PatchObject(sdk_service, "Clean")

        rc = sdk_controller.Clean(
            self._GetRequest(), self.response, self.mock_call_config
        )
        patch.assert_not_called()
        self.assertFalse(rc)

    def testSuccess(self):
        """Test the successful call by verifying service invocation."""
        patch = self.PatchObject(sdk_service, "Clean", return_value=0)

        request = self._GetRequest(incrementals=True)

        sdk_controller.Clean(request, self.response, self.api_config)
        patch.assert_called_once_with(
            mock.ANY,
            safe=False,
            images=False,
            sysroots=False,
            tmp=False,
            cache=False,
            logs=False,
            workdirs=False,
            incrementals=True,
        )

    def testDefaults(self):
        """Test the successful call by verifying service invocation."""
        patch = self.PatchObject(sdk_service, "Clean", return_value=0)

        request = self._GetRequest()

        sdk_controller.Clean(request, self.response, self.api_config)
        patch.assert_called_once_with(mock.ANY, safe=True, sysroots=True)


class SdkDeleteTest(cros_test_lib.MockTestCase, api_config.ApiConfigMixin):
    """Delete tests."""

    def setUp(self):
        """Setup method."""
        # We need to run the command outside the chroot.
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)
        self.response = sdk_pb2.DeleteResponse()

    def _GetRequest(self, chroot_path=None):
        """Helper to build a delete request message."""
        request = sdk_pb2.DeleteRequest()
        if chroot_path:
            request.chroot.path = chroot_path

        return request

    def testValidateOnly(self):
        """Verify a validate-only call does not execute any logic."""
        patch = self.PatchObject(sdk_service, "Delete")

        sdk_controller.Delete(
            self._GetRequest(), self.response, self.validate_only_config
        )
        patch.assert_not_called()

    def testMockCall(self):
        """Sanity check that a mock call does not execute any logic."""
        patch = self.PatchObject(sdk_service, "Delete")

        rc = sdk_controller.Delete(
            self._GetRequest(), self.response, self.mock_call_config
        )
        patch.assert_not_called()
        self.assertFalse(rc)

    def testSuccess(self):
        """Test the successful call by verifying service invocation."""
        patch = self.PatchObject(sdk_service, "Delete", return_value=1)

        request = self._GetRequest()

        sdk_controller.Delete(request, self.response, self.api_config)
        # Verify that by default sdk_service.Delete is called with force=True.
        patch.assert_called_once_with(mock.ANY, force=True)


class SdkUnmountTest(cros_test_lib.MockTestCase, api_config.ApiConfigMixin):
    """SDK Unmount tests."""

    def testNoop(self):
        """Unmount is a deprecated noop."""
        request = sdk_pb2.UnmountRequest()
        response = sdk_pb2.UnmountResponse()
        rc = sdk_controller.Unmount(request, response, self.api_config)
        self.assertFalse(rc)


class SdkUnmountPathTest(cros_test_lib.MockTestCase, api_config.ApiConfigMixin):
    """Update tests."""

    def setUp(self):
        """Setup method."""
        self.response = sdk_pb2.UnmountPathResponse()

    def _UnmountPathRequest(self, path=None):
        """Helper to build a delete request message."""
        request = sdk_pb2.UnmountPathRequest()
        if path:
            request.path.path = path
        return request

    def testValidateOnly(self):
        """Verify a validate-only call does not execute any logic."""
        patch = self.PatchObject(sdk_service, "UnmountPath")

        sdk_controller.UnmountPath(
            self._UnmountPathRequest("/test/path"),
            self.response,
            self.validate_only_config,
        )
        patch.assert_not_called()

    def testMockCall(self):
        """Sanity check that a mock call does not execute any logic."""
        patch = self.PatchObject(sdk_service, "UnmountPath")

        rc = sdk_controller.UnmountPath(
            self._UnmountPathRequest(), self.response, self.mock_call_config
        )
        patch.assert_not_called()
        self.assertFalse(rc)

    def testSuccess(self):
        """Test the successful call by verifying service invocation."""
        patch = self.PatchObject(sdk_service, "UnmountPath", return_value=1)

        request = self._UnmountPathRequest("/test/path")
        sdk_controller.UnmountPath(request, self.response, self.api_config)
        patch.assert_called_once_with("/test/path")


class SdkUpdateTest(
    cros_test_lib.MockTempDirTestCase, api_config.ApiConfigMixin
):
    """Update tests."""

    def setUp(self):
        """Setup method."""
        # We need to run the command inside the chroot.
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)

        self.portage_dir = os.path.join(self.tempdir, "portage_logdir")
        self.PatchObject(
            sysroot_lib.Sysroot, "portage_logdir", new=self.portage_dir
        )
        osutils.SafeMakedirs(self.portage_dir)

        self.response = sdk_pb2.UpdateResponse()

    def _GetRequest(self, build_source=False, targets=None):
        """Helper to simplify building a request instance."""
        request = sdk_pb2.UpdateRequest()
        request.flags.build_source = build_source

        for target in targets or []:
            added = request.toolchain_targets.add()
            added.name = target

        return request

    def _CreatePortageLogFile(
        self,
        log_path: Union[str, os.PathLike],
        pkg_info: package_info.PackageInfo,
        timestamp: datetime.datetime,
    ) -> str:
        """Creates a log file to test for individual packages built by Portage.

        Args:
            log_path: The PORTAGE_LOGDIR path.
            pkg_info: name components for log file.
            timestamp: Timestamp used to name the file.
        """
        path = os.path.join(
            log_path,
            f"{pkg_info.category}:{pkg_info.pvr}:"
            f'{timestamp.strftime("%Y%m%d-%H%M%S")}.log',
        )
        osutils.WriteFile(
            path,
            f"Test log file for package {pkg_info.category}/"
            f"{pkg_info.package} written to {path}",
        )
        return path

    def testValidateOnly(self):
        """Verify a validate-only call does not execute any logic."""
        patch = self.PatchObject(sdk_service, "Update")

        sdk_controller.Update(
            self._GetRequest(), self.response, self.validate_only_config
        )
        patch.assert_not_called()

    def testMockCall(self):
        """Sanity check that a mock call does not execute any logic."""
        patch = self.PatchObject(sdk_service, "Update")

        rc = sdk_controller.Create(
            self._GetRequest(), self.response, self.mock_call_config
        )
        patch.assert_not_called()
        self.assertFalse(rc)
        self.assertTrue(self.response.version.version)

    def testSuccess(self):
        """Successful call output handling test."""
        expected_version = 1
        expected_return = sdk_service.UpdateResult(
            return_code=0, version=expected_version
        )
        self.PatchObject(sdk_service, "Update", return_value=expected_return)
        request = self._GetRequest()

        sdk_controller.Update(request, self.response, self.api_config)

        self.assertEqual(expected_version, self.response.version.version)

    def testNonPackageFailure(self):
        """Test output handling when the call fails."""
        expected_return = sdk_service.UpdateResult(return_code=1)
        self.PatchObject(sdk_service, "Update", return_value=expected_return)

        rc = sdk_controller.Update(
            self._GetRequest(), self.response, self.api_config
        )
        self.assertEqual(controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY, rc)

    def testPackageFailure(self):
        """Test output handling when the call fails with a package failure."""
        pkgs = ["cat/pkg-1.0-r1", "foo/bar-2.0-r1"]
        cpvrs = [package_info.parse(pkg) for pkg in pkgs]
        new_logs = {}
        for i, pkg in enumerate(pkgs):
            self._CreatePortageLogFile(
                self.portage_dir,
                cpvrs[i],
                datetime.datetime(2021, 6, 9, 13, 37, 0),
            )
            new_logs[pkg] = self._CreatePortageLogFile(
                self.portage_dir,
                cpvrs[i],
                datetime.datetime(2021, 6, 9, 16, 20, 0),
            )

        expected_return = sdk_service.UpdateResult(
            return_code=1,
            failed_pkgs=cpvrs,
        )
        self.PatchObject(sdk_service, "Update", return_value=expected_return)

        rc = sdk_controller.Update(
            self._GetRequest(), self.response, self.api_config
        )
        self.assertEqual(
            controller.RETURN_CODE_UNSUCCESSFUL_RESPONSE_AVAILABLE, rc
        )
        self.assertTrue(self.response.failed_package_data)

        expected_failed_pkgs = [("cat", "pkg"), ("foo", "bar")]
        failed_pkgs = []
        for data in self.response.failed_package_data:
            failed_pkgs.append((data.name.category, data.name.package_name))
            package = controller_util.deserialize_package_info(data.name)
            self.assertEqual(data.log_path.path, new_logs[package.cpvr])
        self.assertCountEqual(expected_failed_pkgs, failed_pkgs)

    def testArgumentHandling(self):
        """Test the proto argument handling."""
        expected_return = sdk_service.UpdateResult(return_code=0, version=1)
        args = sdk_service.UpdateArguments()
        self.PatchObject(sdk_service, "Update", return_value=expected_return)
        args_patch = self.PatchObject(
            sdk_service, "UpdateArguments", return_value=args
        )

        # No boards and flags False.
        request = self._GetRequest(build_source=False)
        sdk_controller.Update(request, self.response, self.api_config)
        args_patch.assert_called_with(
            build_source=False, toolchain_targets=[], toolchain_changed=False
        )

        # Multiple boards and flags True.
        targets = ["board1", "board2"]
        request = self._GetRequest(build_source=True, targets=targets)
        sdk_controller.Update(request, self.response, self.api_config)
        args_patch.assert_called_with(
            build_source=True,
            toolchain_targets=targets,
            toolchain_changed=False,
        )


class CreateManifestFromSdkTest(
    cros_test_lib.MockTestCase, api_config.ApiConfigMixin
):
    """Test the SdkService/CreateManifestFromSdk endpoint."""

    _sdk_path = "/build/my_sdk"
    _dest_dir = "/build"
    _manifest_path = "/build/my_sdk.Manifest"

    def _NewRequest(self, inside: bool) -> sdk_pb2.CreateManifestFromSdkRequest:
        return sdk_pb2.CreateManifestFromSdkRequest(
            chroot=common_pb2.Chroot(
                path=self.chroot.path, out_path=str(self.chroot.out_path)
            ),
            sdk_path=common_pb2.Path(
                path=self._sdk_path,
                location=common_pb2.Path.Location.INSIDE
                if inside
                else common_pb2.Path.Location.OUTSIDE,
            ),
            dest_dir=common_pb2.Path(
                path=self._dest_dir,
                location=common_pb2.Path.Location.OUTSIDE,
            ),
        )

    def _NewResponse(self) -> sdk_pb2.CreateManifestFromSdkResponse:
        return sdk_pb2.CreateManifestFromSdkResponse()

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        self.chroot = chroot_lib.Chroot(
            path=Path("/path/to/chroot"),
            out_path=Path("/path/to/out"),
        )

    def testValidateOnly(self):
        """Check that a validate only call does not execute any logic."""
        impl_patch = self.PatchObject(sdk_service, "CreateManifestFromSdk")
        sdk_controller.CreateManifestFromSdk(
            self._NewRequest(False),
            self._NewResponse(),
            self.validate_only_config,
        )
        impl_patch.assert_not_called()

    def testOutside(self):
        """Check that a call with an outside path succeeds."""
        impl_patch = self.PatchObject(
            sdk_service,
            "CreateManifestFromSdk",
            return_value=Path(self._manifest_path),
        )
        request = self._NewRequest(inside=False)
        response = self._NewResponse()
        sdk_controller.CreateManifestFromSdk(
            request,
            response,
            self.api_config,
        )
        impl_patch.assert_called_with(
            Path(self._sdk_path),
            Path(self._dest_dir),
        )
        self.assertEqual(
            response.manifest_path.location, common_pb2.Path.Location.OUTSIDE
        )
        self.assertEqual(response.manifest_path.path, self._manifest_path)

    def testInside(self):
        """Check that an inside path parses correctly and the call succeeds."""
        impl_patch = self.PatchObject(
            sdk_service,
            "CreateManifestFromSdk",
            return_value=Path(self._manifest_path),
        )
        request = self._NewRequest(inside=True)
        response = self._NewResponse()
        sdk_controller.CreateManifestFromSdk(
            request,
            response,
            self.api_config,
        )
        impl_patch.assert_called_with(
            Path(self.chroot.full_path(self._sdk_path)),
            Path(self._dest_dir),
        )
        self.assertEqual(
            response.manifest_path.location, common_pb2.Path.Location.OUTSIDE
        )
        self.assertEqual(response.manifest_path.path, self._manifest_path)


class BuildSdkToolchainTest(
    cros_test_lib.MockTestCase, api_config.ApiConfigMixin
):
    """Test the SdkService/BuildSdkToolchain endpoint."""

    def setUp(self):
        """Set up the test case."""
        self._chroot_path = "/path/to/chroot"
        self._result_dir = "/out/toolchain-pkgs/"
        self._response = sdk_pb2.BuildSdkToolchainResponse()
        self._generated_filenames = (
            "armv7a-cros-linux-gnueabihf.tar.xz",
            "x86_64-cros-linux-gnu.tar.xz",
        )
        self._paths_for_generated_files = [
            common_pb2.Path(
                path=os.path.join(constants.SDK_TOOLCHAINS_OUTPUT, fname),
                location=common_pb2.Path.Location.INSIDE,
            )
            for fname in self._generated_filenames
        ]

    def _NewRequest(
        self,
        chroot_path: Optional[str] = None,
        use_flags: Optional[List[str]] = None,
    ) -> sdk_pb2.BuildSdkToolchainRequest:
        """Return a new BuildSdkToolchainRequest message."""
        request = sdk_pb2.BuildSdkToolchainRequest(
            result_path=common_pb2.ResultPath(
                path=common_pb2.Path(
                    path=self._result_dir,
                    location=common_pb2.Path.Location.OUTSIDE,
                )
            )
        )
        if chroot_path:
            request.chroot.path = chroot_path
        if use_flags:
            request.use_flags.extend(
                common_pb2.UseFlag(flag=flag) for flag in use_flags
            )
        return request

    def _NewResponse(
        self, generated_filenames: Optional[List[str]] = None
    ) -> sdk_pb2.BuildSdkToolchainResponse:
        """Return a new BuildSdkToolchainResponse message."""
        response = sdk_pb2.BuildSdkToolchainResponse()
        if generated_filenames:
            response.generated_files.extend(
                common_pb2.Path(
                    path=os.path.join(self._result_dir, fname),
                    location=common_pb2.Path.Location.OUTSIDE,
                )
                for fname in generated_filenames
            )
        return response

    def testValidateOnly(self):
        """Check that a validate only call does not execute any logic."""
        impl_patch = self.PatchObject(sdk_service, "BuildSdkToolchain")
        sdk_controller.BuildSdkToolchain(
            self._NewRequest(), self._NewResponse(), self.validate_only_config
        )
        impl_patch.assert_not_called()

    def testSuccess(self):
        """Check that a normal call defers to the SDK service as expected."""
        impl_patch = self.PatchObject(sdk_service, "BuildSdkToolchain")
        request = self._NewRequest(use_flags=[])
        response = self._NewResponse()
        sdk_controller.BuildSdkToolchain(
            request,
            response,
            self.api_config,
        )
        # Can't use assert_called_with, since the chroot objects are equal but
        # not identical.
        impl_patch.assert_called_once()
        self.assertEqual(impl_patch.call_args.kwargs["extra_env"], {})

    def testSuccessWithUseFlags(self):
        """Check that a call with USE flags works as expected."""
        impl_patch = self.PatchObject(sdk_service, "BuildSdkToolchain")
        request = self._NewRequest(use_flags=["llvm-next", "another-flag"])
        response = self._NewResponse()
        sdk_controller.BuildSdkToolchain(
            request,
            response,
            self.api_config,
        )
        # Can't use assert_called_with, since the chroot objects are equal but
        # not identical.
        impl_patch.assert_called_once()
        self.assertEqual(
            impl_patch.call_args.kwargs["extra_env"],
            {"USE": "llvm-next another-flag"},
        )


class uprev_test(cros_test_lib.MockTestCase, api_config.ApiConfigMixin):
    """Test case for SdkService/Uprev() endpoint."""

    _binhost_gs_bucket = "gs://chromiumos-prebuilts/"
    _latest_uprev_target_version = "2023.02.19.112358"

    def setUp(self):
        """Set up the test case."""
        self.PatchObject(
            sdk_service,
            "get_latest_uprev_target_version",
            return_value=self._latest_uprev_target_version,
        )
        self._uprev_patch = self.PatchObject(
            sdk_service,
            "uprev_sdk_and_prebuilts",
        )

    def NewRequest(
        self, version: str = "", toolchain_tarball_template: str = ""
    ):
        """Return a new UprevRequest with standard inputs."""
        return sdk_pb2.UprevRequest(
            binhost_gs_bucket=self._binhost_gs_bucket,
            version=version,
            toolchain_tarball_template=toolchain_tarball_template,
        )

    @staticmethod
    def NewResponse() -> sdk_pb2.UprevResponse:
        """Return a new empty UprevResponse."""
        return sdk_pb2.UprevResponse()

    def testWithVersion(self):
        """Test the endpoint with `version` specified.

        In this case, we expect that sdk_controller.Uprev is called with the
        version specified in the UprevRequest.
        """
        specified_version = "1970.01.01.000000"
        toolchain_tarball_template = "path/to/%(version)s/toolchain"
        request = self.NewRequest(
            version=specified_version,
            toolchain_tarball_template=toolchain_tarball_template,
        )
        response = self.NewResponse()
        sdk_controller.Uprev(request, response, self.api_config)
        self._uprev_patch.assert_called_with(
            binhost_gs_bucket=self._binhost_gs_bucket,
            sdk_version=specified_version,
            toolchain_tarball_template=toolchain_tarball_template,
        )

    def testWithoutVersion(self):
        """Test the endpoint with `version` not specified.

        In this case, we expect that sdk_controller.Uprev is called with the
        latest uprev target version, based on the remote file in gs://. This is
        fetched via sdk_controller.GetLatestUprevTargetVersionVersion
        (mocked here in setUp()).
        """
        toolchain_tarball_template = "path/to/%(version)s/toolchain"
        request = self.NewRequest(
            toolchain_tarball_template=toolchain_tarball_template
        )
        response = self.NewResponse()
        sdk_controller.Uprev(request, response, self.api_config)
        self._uprev_patch.assert_called_with(
            binhost_gs_bucket=self._binhost_gs_bucket,
            sdk_version=self._latest_uprev_target_version,
            toolchain_tarball_template=toolchain_tarball_template,
        )

    def testWithoutToolchainTarballTemplate(self):
        """Test the endpoint with `toolchain_tarball_template` not specified."""
        request = self.NewRequest(version="1234")
        response = self.NewResponse()
        with self.assertRaises(cros_build_lib.DieSystemExit):
            sdk_controller.Uprev(request, response, self.api_config)
