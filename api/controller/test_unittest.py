# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The test controller tests."""

import datetime
import os
from typing import Union

from chromite.third_party.google.protobuf import json_format

from chromite.api import api_config
from chromite.api import controller
from chromite.api.controller import controller_util
from chromite.api.controller import test as test_controller
from chromite.api.gen.chromite.api import test_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.api.gen.chromiumos.build.api import container_metadata_pb2
from chromite.lib import build_target_lib
from chromite.lib import chroot_lib
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import sysroot_lib
from chromite.lib.parser import package_info
from chromite.service import test as test_service


class DebugInfoTestTest(
    cros_test_lib.MockTempDirTestCase, api_config.ApiConfigMixin
):
    """Tests for the DebugInfoTest function."""

    def setUp(self):
        self.board = "board"
        self.chroot_path = os.path.join(self.tempdir, "chroot")
        self.sysroot_path = "/build/board"
        self.full_sysroot_path = os.path.join(
            self.chroot_path, self.sysroot_path.lstrip(os.sep)
        )
        osutils.SafeMakedirs(self.full_sysroot_path)

    def _GetInput(self, sysroot_path=None, build_target=None):
        """Helper to build an input message instance."""
        proto = test_pb2.DebugInfoTestRequest()
        if sysroot_path:
            proto.sysroot.path = sysroot_path
        if build_target:
            proto.sysroot.build_target.name = build_target
        return proto

    def _GetOutput(self):
        """Helper to get an empty output message instance."""
        return test_pb2.DebugInfoTestResponse()

    def testValidateOnly(self):
        """Verify a validate-only call does not execute any logic."""
        patch = self.PatchObject(test_service, "DebugInfoTest")
        input_msg = self._GetInput(sysroot_path=self.full_sysroot_path)
        test_controller.DebugInfoTest(
            input_msg, self._GetOutput(), self.validate_only_config
        )
        patch.assert_not_called()

    def testMockError(self):
        """Test mock error call does not execute any logic, returns error."""
        patch = self.PatchObject(test_service, "DebugInfoTest")

        input_msg = self._GetInput(sysroot_path=self.full_sysroot_path)
        rc = test_controller.DebugInfoTest(
            input_msg, self._GetOutput(), self.mock_error_config
        )
        patch.assert_not_called()
        self.assertEqual(controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY, rc)

    def testMockCall(self):
        """Test mock call does not execute any logic, returns success."""
        patch = self.PatchObject(test_service, "DebugInfoTest")

        input_msg = self._GetInput(sysroot_path=self.full_sysroot_path)
        rc = test_controller.DebugInfoTest(
            input_msg, self._GetOutput(), self.mock_call_config
        )
        patch.assert_not_called()
        self.assertEqual(controller.RETURN_CODE_SUCCESS, rc)

    def testNoBuildTargetNoSysrootFails(self):
        """Test missing build target name and sysroot path fails."""
        input_msg = self._GetInput()
        output_msg = self._GetOutput()
        with self.assertRaises(cros_build_lib.DieSystemExit):
            test_controller.DebugInfoTest(
                input_msg, output_msg, self.api_config
            )

    def testDebugInfoTest(self):
        """Call DebugInfoTest with valid sysroot_path."""
        request = self._GetInput(sysroot_path=self.full_sysroot_path)

        test_controller.DebugInfoTest(
            request, self._GetOutput(), self.api_config
        )


class BuildTargetUnitTestTest(
    cros_test_lib.MockTempDirTestCase, api_config.ApiConfigMixin
):
    """Tests for the UnitTest function."""

    def setUp(self):
        # Set up portage log directory.
        self.sysroot = os.path.join(self.tempdir, "build", "board")
        osutils.SafeMakedirs(self.sysroot)
        self.target_sysroot = sysroot_lib.Sysroot(self.sysroot)
        self.portage_dir = os.path.join(self.tempdir, "portage_logdir")
        self.PatchObject(
            sysroot_lib.Sysroot, "portage_logdir", new=self.portage_dir
        )
        osutils.SafeMakedirs(self.portage_dir)

    def _GetInput(
        self,
        board=None,
        chroot_path=None,
        cache_dir=None,
        empty_sysroot=None,
        packages=None,
        blocklist=None,
    ):
        """Helper to build an input message instance."""
        formatted_packages = []
        for pkg in packages or []:
            formatted_packages.append(
                {"category": pkg.category, "package_name": pkg.package}
            )
        formatted_blocklist = []
        for pkg in blocklist or []:
            formatted_blocklist.append(
                {"category": pkg.category, "package_name": pkg.package}
            )

        return test_pb2.BuildTargetUnitTestRequest(
            build_target={"name": board},
            chroot={"path": chroot_path, "cache_dir": cache_dir},
            flags={"empty_sysroot": empty_sysroot},
            packages=formatted_packages,
            package_blocklist=formatted_blocklist,
        )

    def _GetOutput(self):
        """Helper to get an empty output message instance."""
        return test_pb2.BuildTargetUnitTestResponse()

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
        patch = self.PatchObject(test_service, "BuildTargetUnitTest")

        input_msg = self._GetInput(board="board")
        test_controller.BuildTargetUnitTest(
            input_msg, self._GetOutput(), self.validate_only_config
        )
        patch.assert_not_called()

    def testMockCall(self):
        """Test a mock call does not execute logic, returns mocked value."""
        patch = self.PatchObject(test_service, "BuildTargetUnitTest")

        input_msg = self._GetInput(board="board")
        response = self._GetOutput()
        test_controller.BuildTargetUnitTest(
            input_msg, response, self.mock_call_config
        )
        patch.assert_not_called()

    def testMockError(self):
        """Test that a mock error does not execute logic, returns error."""
        patch = self.PatchObject(test_service, "BuildTargetUnitTest")

        input_msg = self._GetInput(board="board")
        response = self._GetOutput()
        rc = test_controller.BuildTargetUnitTest(
            input_msg, response, self.mock_error_config
        )
        patch.assert_not_called()
        self.assertEqual(
            controller.RETURN_CODE_UNSUCCESSFUL_RESPONSE_AVAILABLE, rc
        )
        self.assertTrue(response.failed_package_data)
        self.assertEqual(response.failed_package_data[0].name.category, "foo")
        self.assertEqual(
            response.failed_package_data[0].name.package_name, "bar"
        )
        self.assertEqual(response.failed_package_data[1].name.category, "cat")
        self.assertEqual(
            response.failed_package_data[1].name.package_name, "pkg"
        )

    def testInvalidPackageFails(self):
        """Test missing result path fails."""
        # Missing result_path.
        pkg = package_info.PackageInfo(package="bar")
        input_msg = self._GetInput(board="board", packages=[pkg])
        output_msg = self._GetOutput()
        with self.assertRaises(cros_build_lib.DieSystemExit):
            test_controller.BuildTargetUnitTest(
                input_msg, output_msg, self.api_config
            )

    def testPackageBuildFailure(self):
        """Test handling of raised BuildPackageFailure."""
        tempdir = osutils.TempDir(base_dir=self.tempdir)
        self.PatchObject(osutils, "TempDir", return_value=tempdir)

        pkgs = ["cat/pkg-1.0-r1", "foo/bar-2.0-r1"]
        cpvrs = [package_info.parse(pkg) for pkg in pkgs]
        expected = [("cat", "pkg"), ("foo", "bar")]
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

        result = test_service.BuildTargetUnitTestResult(1, None)
        result.failed_pkgs = [package_info.parse(p) for p in pkgs]
        self.PatchObject(
            test_service, "BuildTargetUnitTest", return_value=result
        )

        input_msg = self._GetInput(board="board")
        output_msg = self._GetOutput()

        rc = test_controller.BuildTargetUnitTest(
            input_msg, output_msg, self.api_config
        )

        self.assertEqual(
            controller.RETURN_CODE_UNSUCCESSFUL_RESPONSE_AVAILABLE, rc
        )
        self.assertTrue(output_msg.failed_package_data)

        failed_with_logs = []
        for data in output_msg.failed_package_data:
            failed_with_logs.append(
                (data.name.category, data.name.package_name)
            )
            package = controller_util.deserialize_package_info(data.name)
            self.assertEqual(data.log_path.path, new_logs[package.cpvr])
        self.assertCountEqual(expected, failed_with_logs)

    def testOtherBuildScriptFailure(self):
        """Test build script failure due to non-package emerge error."""
        tempdir = osutils.TempDir(base_dir=self.tempdir)
        self.PatchObject(osutils, "TempDir", return_value=tempdir)

        result = test_service.BuildTargetUnitTestResult(1, None)
        self.PatchObject(
            test_service, "BuildTargetUnitTest", return_value=result
        )

        pkgs = ["foo/bar", "cat/pkg"]
        blocklist = [package_info.parse(p) for p in pkgs]
        input_msg = self._GetInput(
            board="board", empty_sysroot=True, blocklist=blocklist
        )
        output_msg = self._GetOutput()

        rc = test_controller.BuildTargetUnitTest(
            input_msg, output_msg, self.api_config
        )

        self.assertEqual(controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY, rc)
        self.assertFalse(output_msg.failed_package_data)

    def testBuildTargetUnitTest(self):
        """Test BuildTargetUnitTest successful call."""
        pkgs = ["foo/bar", "cat/pkg"]
        packages = [package_info.SplitCPV(p, strict=False) for p in pkgs]
        input_msg = self._GetInput(board="board", packages=packages)

        result = test_service.BuildTargetUnitTestResult(0, None)
        self.PatchObject(
            test_service, "BuildTargetUnitTest", return_value=result
        )

        response = self._GetOutput()
        test_controller.BuildTargetUnitTest(
            input_msg, response, self.api_config
        )
        self.assertFalse(response.failed_package_data)


class DockerConstraintsTest(cros_test_lib.MockTestCase):
    """Tests for Docker argument constraints."""

    def assertValid(self, output):
        return output is None

    def assertInvalid(self, output):
        return not self.assertValid(output)

    def testValidDockerTag(self):
        """Check logic for validating docker tag format."""
        # pylint: disable=protected-access

        invalid_tags = [
            ".invalid-tag",
            "-invalid-tag",
            "invalid-tag;",
            "invalid" * 100,
        ]

        for tag in invalid_tags:
            self.assertInvalid(test_controller._ValidDockerTag(tag))

        valid_tags = [
            "valid-tag",
            "valid-tag-",
            "valid.tag.",
        ]

        for tag in valid_tags:
            self.assertValid(test_controller._ValidDockerTag(tag))

    def testValidDockerLabelKey(self):
        """Check logic for validating docker label key format."""
        # pylint: disable=protected-access

        invalid_keys = [
            "Invalid-keY",
            "Invalid-key",
            "invalid-keY",
            "iNVALID-KEy",
            "invalid_key",
            "invalid-key;",
        ]

        for key in invalid_keys:
            self.assertInvalid(test_controller._ValidDockerLabelKey(key))

        valid_keys = [
            "chromeos.valid-key",
            "chromeos.valid-key-2",
        ]

        for key in valid_keys:
            self.assertValid(test_controller._ValidDockerLabelKey(key))


class BuildTestServiceContainers(
    cros_test_lib.RunCommandTempDirTestCase, api_config.ApiConfigMixin
):
    """Tests for the BuildTestServiceContainers function."""

    def setUp(self):
        self.request = test_pb2.BuildTestServiceContainersRequest(
            chroot={"path": "/path/to/chroot", "out_path": "/path/to/out"},
            build_target={"name": "build_target"},
            version="R93-14033.0.0",
        )

    def testSuccess(self):
        """Check passing case with mocked cros_build_lib.run."""

        def ContainerMetadata():
            """Return mocked ContainerImageInfo proto"""
            metadata = container_metadata_pb2.ContainerImageInfo()
            metadata.repository.hostname = "gcr.io"
            metadata.repository.project = "chromeos-bot"
            metadata.name = "random-container-name"
            # pylint: disable=line-too-long
            metadata.digest = "09b730f8b6a862f9c2705cb3acf3554563325f5fca5c784bf5c98beb2e56f6db"
            # pylint: enable=line-too-long
            metadata.tags[:] = [
                "staging-cq-amd64-generic.R96-1.2.3",
                "8834106026340379089",
            ]
            return metadata

        def WriteContainerMetadata(path):
            """Write json formatted metadata to the given file."""
            osutils.WriteFile(
                path,
                json_format.MessageToJson(ContainerMetadata()),
            )

        # Write out mocked container metadata to a temporary file.
        output_path = os.path.join(self.tempdir, "metadata.jsonpb")
        self.rc.SetDefaultCmdResult(
            returncode=0,
            side_effect=lambda *_, **__: WriteContainerMetadata(output_path),
        )

        # Patch TempDir so that we always use this test's directory.
        self.PatchObject(
            osutils.TempDir, "__enter__", return_value=self.tempdir
        )

        response = test_pb2.BuildTestServiceContainersResponse()
        test_controller.BuildTestServiceContainers(
            self.request, response, self.api_config
        )

        self.assertTrue(self.rc.called)
        for result in response.results:
            self.assertEqual(result.WhichOneof("result"), "success")
            self.assertEqual(result.success.image_info, ContainerMetadata())

    def testFailure(self):
        """Check failure case with mocked cros_build_lib.run."""
        response = test_pb2.BuildTestServiceContainersResponse()
        test_controller.BuildTestServiceContainers(
            self.request, response, self.api_config
        )
        self.assertTrue(self.rc.called)
        for result in response.results:
            self.assertEqual(result.WhichOneof("result"), "failure")
            self.assertEqual(result.name, "Service Builder")


class ChromiteUnitTestTest(
    cros_test_lib.RunCommandTestCase, api_config.ApiConfigMixin
):
    """Tests for the ChromiteInfoTest function."""

    def setUp(self):
        self.board = "board"
        self.chroot_path = "/path/to/chroot"

    def _GetInput(self, chroot_path=None):
        """Helper to build an input message instance."""
        proto = test_pb2.ChromiteUnitTestRequest(
            chroot={"path": chroot_path},
        )
        return proto

    def _GetOutput(self):
        """Helper to get an empty output message instance."""
        return test_pb2.ChromiteUnitTestResponse()

    def testValidateOnly(self):
        """Verify a validate-only call does not execute any logic."""
        input_msg = self._GetInput(chroot_path=self.chroot_path)
        test_controller.ChromiteUnitTest(
            input_msg, self._GetOutput(), self.validate_only_config
        )
        self.assertFalse(self.rc.called)

    def testMockError(self):
        """Test mock error call does not execute any logic, returns error."""
        input_msg = self._GetInput(chroot_path=self.chroot_path)
        rc = test_controller.ChromiteUnitTest(
            input_msg, self._GetOutput(), self.mock_error_config
        )
        self.assertFalse(self.rc.called)
        self.assertEqual(controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY, rc)

    def testMockCall(self):
        """Test mock call does not execute any logic, returns success."""
        input_msg = self._GetInput(chroot_path=self.chroot_path)
        rc = test_controller.ChromiteUnitTest(
            input_msg, self._GetOutput(), self.mock_call_config
        )
        self.assertFalse(self.rc.called)
        self.assertEqual(controller.RETURN_CODE_SUCCESS, rc)

    def testChromiteUnitTest(self):
        """Call ChromiteUnitTest with mocked cros_build_lib.run."""
        request = self._GetInput(chroot_path=self.chroot_path)
        test_controller.ChromiteUnitTest(
            request, self._GetOutput(), self.api_config
        )
        self.assertEqual(self.rc.call_count, 1)


class BazelTestTest(
    cros_test_lib.RunCommandTestCase, api_config.ApiConfigMixin
):
    """Tests for the BazelTest function."""

    def testBazelTest(self):
        """Call BazelTest with mocked cros_build_lib.run."""
        test_controller.BazelTest(
            test_pb2.BazelTestRequest(),
            test_pb2.BazelTestResponse(),
            self.api_config,
        )
        self.assertEqual(self.rc.call_count, 1)


class CrosSigningTestTest(
    cros_test_lib.RunCommandTestCase, api_config.ApiConfigMixin
):
    """CrosSigningTest tests."""

    def setUp(self):
        self.chroot_path = "/path/to/chroot"

    def _GetInput(self, chroot_path=None):
        """Helper to build an input message instance."""
        proto = test_pb2.CrosSigningTestRequest(
            chroot={"path": chroot_path},
        )
        return proto

    def _GetOutput(self):
        """Helper to get an empty output message instance."""
        return test_pb2.CrosSigningTestResponse()

    def testValidateOnly(self):
        """Verify a validate-only call does not execute any logic."""
        test_controller.CrosSigningTest(None, None, self.validate_only_config)
        self.assertFalse(self.rc.called)

    def testMockCall(self):
        """Test mock call does not execute any logic, returns success."""
        rc = test_controller.CrosSigningTest(None, None, self.mock_call_config)
        self.assertFalse(self.rc.called)
        self.assertEqual(controller.RETURN_CODE_SUCCESS, rc)

    def testCrosSigningTest(self):
        """Call CrosSigningTest with mocked cros_build_lib.run."""
        request = self._GetInput(chroot_path=self.chroot_path)
        test_controller.CrosSigningTest(
            request, self._GetOutput(), self.api_config
        )
        self.assertEqual(self.rc.call_count, 1)


class SimpleChromeWorkflowTestTest(
    cros_test_lib.MockTestCase, api_config.ApiConfigMixin
):
    """Test the SimpleChromeWorkflowTest endpoint."""

    @staticmethod
    def _Output():
        return test_pb2.SimpleChromeWorkflowTestResponse()

    def _Input(
        self,
        sysroot_path=None,
        build_target=None,
        chrome_root=None,
        goma_config=None,
    ):
        proto = test_pb2.SimpleChromeWorkflowTestRequest()
        if sysroot_path:
            proto.sysroot.path = sysroot_path
        if build_target:
            proto.sysroot.build_target.name = build_target
        if chrome_root:
            proto.chrome_root = chrome_root
        if goma_config:
            proto.goma_config = goma_config
        return proto

    def setUp(self):
        self.chrome_path = "path/to/chrome"
        self.sysroot_dir = "build/board"
        self.build_target = "amd64"
        self.mock_simple_chrome_workflow_test = self.PatchObject(
            test_service, "SimpleChromeWorkflowTest"
        )

    def testMissingBuildTarget(self):
        """Test SimpleChromeWorkflowTest dies when build_target not set."""
        input_proto = self._Input(
            build_target=None,
            sysroot_path="/sysroot/dir",
            chrome_root="/chrome/path",
        )
        with self.assertRaises(cros_build_lib.DieSystemExit):
            test_controller.SimpleChromeWorkflowTest(
                input_proto, None, self.api_config
            )

    def testMissingSysrootPath(self):
        """Test SimpleChromeWorkflowTest dies when build_target not set."""
        input_proto = self._Input(
            build_target="board", sysroot_path=None, chrome_root="/chrome/path"
        )
        with self.assertRaises(cros_build_lib.DieSystemExit):
            test_controller.SimpleChromeWorkflowTest(
                input_proto, None, self.api_config
            )

    def testMissingChromeRoot(self):
        """Test SimpleChromeWorkflowTest dies when build_target not set."""
        input_proto = self._Input(
            build_target="board", sysroot_path="/sysroot/dir", chrome_root=None
        )
        with self.assertRaises(cros_build_lib.DieSystemExit):
            test_controller.SimpleChromeWorkflowTest(
                input_proto, None, self.api_config
            )

    def testSimpleChromeWorkflowTest(self):
        """Call SimpleChromeWorkflowTest with valid args and temp dir."""
        request = self._Input(
            sysroot_path="sysroot_path",
            build_target="board",
            chrome_root="/path/to/chrome",
        )
        response = self._Output()

        test_controller.SimpleChromeWorkflowTest(
            request, response, self.api_config
        )
        self.mock_simple_chrome_workflow_test.assert_called()

    def testValidateOnly(self):
        request = self._Input(
            sysroot_path="sysroot_path",
            build_target="board",
            chrome_root="/path/to/chrome",
        )
        test_controller.SimpleChromeWorkflowTest(
            request, self._Output(), self.validate_only_config
        )
        self.mock_simple_chrome_workflow_test.assert_not_called()

    def testMockCall(self):
        """Test mock call does not execute any logic, returns success."""
        patch = self.mock_simple_chrome_workflow_test = self.PatchObject(
            test_service, "SimpleChromeWorkflowTest"
        )

        request = self._Input(
            sysroot_path="sysroot_path",
            build_target="board",
            chrome_root="/path/to/chrome",
        )
        rc = test_controller.SimpleChromeWorkflowTest(
            request, self._Output(), self.mock_call_config
        )
        patch.assert_not_called()
        self.assertEqual(controller.RETURN_CODE_SUCCESS, rc)


class VmTestTest(cros_test_lib.RunCommandTestCase, api_config.ApiConfigMixin):
    """Test the VmTest endpoint."""

    def _GetInput(self, **kwargs):
        values = dict(
            build_target=common_pb2.BuildTarget(name="target"),
            vm_path=common_pb2.Path(
                path="/path/to/image.bin", location=common_pb2.Path.INSIDE
            ),
            test_harness=test_pb2.VmTestRequest.TAST,
            vm_tests=[test_pb2.VmTestRequest.VmTest(pattern="suite")],
            ssh_options=test_pb2.VmTestRequest.SshOptions(
                port=1234,
                private_key_path={
                    "path": "/path/to/id_rsa",
                    "location": common_pb2.Path.INSIDE,
                },
            ),
        )
        values.update(kwargs)
        return test_pb2.VmTestRequest(**values)

    def _Output(self):
        return test_pb2.VmTestResponse()

    def testValidateOnly(self):
        """Verify a validate-only call does not execute any logic."""
        test_controller.VmTest(
            self._GetInput(), None, self.validate_only_config
        )
        self.assertEqual(0, self.rc.call_count)

    def testMockCall(self):
        """Test mock call does not execute any logic."""
        request = self._GetInput()
        response = self._Output()
        # VmTest does not return a value, checking mocked value is flagged by
        # lint.
        test_controller.VmTest(request, response, self.mock_call_config)
        self.assertFalse(self.rc.called)

    def testTastAllOptions(self):
        """Test VmTest for Tast with all options set."""
        test_controller.VmTest(self._GetInput(), None, self.api_config)
        self.assertCommandContains(
            [
                "cros_run_test",
                "--debug",
                "--no-display",
                "--copy-on-write",
                "--board",
                "target",
                "--image-path",
                "/path/to/image.bin",
                "--tast",
                "suite",
                "--ssh-port",
                "1234",
                "--private-key",
                "/path/to/id_rsa",
            ]
        )

    def testAutotestAllOptions(self):
        """Test VmTest for Autotest with all options set."""
        input_proto = self._GetInput(
            test_harness=test_pb2.VmTestRequest.AUTOTEST
        )
        test_controller.VmTest(input_proto, None, self.api_config)
        self.assertCommandContains(
            [
                "cros_run_test",
                "--debug",
                "--no-display",
                "--copy-on-write",
                "--board",
                "target",
                "--image-path",
                "/path/to/image.bin",
                "--autotest",
                "suite",
                "--ssh-port",
                "1234",
                "--private-key",
                "/path/to/id_rsa",
                "--test_that-args=--allow-chrome-crashes",
            ]
        )

    def testMissingBuildTarget(self):
        """Test VmTest dies when build_target not set."""
        input_proto = self._GetInput(build_target=None)
        with self.assertRaises(cros_build_lib.DieSystemExit):
            test_controller.VmTest(input_proto, None, self.api_config)

    def testMissingVmImage(self):
        """Test VmTest dies when vm_image not set."""
        input_proto = self._GetInput(vm_path=None)
        with self.assertRaises(cros_build_lib.DieSystemExit):
            test_controller.VmTest(input_proto, None, self.api_config)

    def testMissingTestHarness(self):
        """Test VmTest dies when test_harness not specified."""
        input_proto = self._GetInput(
            test_harness=test_pb2.VmTestRequest.UNSPECIFIED
        )
        with self.assertRaises(cros_build_lib.DieSystemExit):
            test_controller.VmTest(input_proto, None, self.api_config)

    def testMissingVmTests(self):
        """Test VmTest dies when vm_tests not set."""
        input_proto = self._GetInput(vm_tests=[])
        with self.assertRaises(cros_build_lib.DieSystemExit):
            test_controller.VmTest(input_proto, None, self.api_config)

    def testVmTest(self):
        """Call VmTest with valid args and temp dir."""
        request = self._GetInput()
        response = self._Output()
        test_controller.VmTest(request, response, self.api_config)
        self.assertTrue(self.rc.called)


class GetArtifactsTest(cros_test_lib.MockTempDirTestCase):
    """Test GetArtifacts."""

    CODE_COVERAGE_LLVM_ARTIFACT_TYPE = (
        common_pb2.ArtifactsByService.Test.ArtifactType.CODE_COVERAGE_LLVM_JSON
    )

    # pylint: disable=line-too-long
    _artifact_funcs = {
        common_pb2.ArtifactsByService.Test.ArtifactType.CODE_COVERAGE_LLVM_JSON: test_service.BundleCodeCoverageLlvmJson,
        common_pb2.ArtifactsByService.Test.ArtifactType.CODE_COVERAGE_RUST_LLVM_JSON: test_service.BundleCodeCoverageRustLlvmJson,
        common_pb2.ArtifactsByService.Test.ArtifactType.HWQUAL: test_service.BundleHwqualTarball,
        common_pb2.ArtifactsByService.Test.ArtifactType.CODE_COVERAGE_GOLANG: test_service.BundleCodeCoverageGolang,
    }
    # pylint: enable=line-too-long

    def setUp(self):
        """Set up the class for tests."""
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        self.chroot = chroot_lib.Chroot(
            path=self.tempdir / "chroot",
            out_path=self.tempdir / "out",
        )
        osutils.SafeMakedirs(self.chroot.tmp)

        sysroot_path = self.chroot.full_path("/build/board")
        osutils.SafeMakedirs(sysroot_path)
        self.sysroot = sysroot_lib.Sysroot(sysroot_path)

        self.build_target = build_target_lib.BuildTarget("board")

        self._mocks = {}
        for artifact, func in self._artifact_funcs.items():
            self._mocks[artifact] = self.PatchObject(
                test_service, func.__name__
            )

    def _InputProto(
        self,
        artifact_types=_artifact_funcs.keys(),
    ):
        """Helper to build an input proto instance."""
        return common_pb2.ArtifactsByService.Test(
            output_artifacts=[
                common_pb2.ArtifactsByService.Test.ArtifactInfo(
                    artifact_types=artifact_types
                )
            ]
        )

    def testReturnsEmptyListWhenNoOutputArtifactsProvided(self):
        """Test empty list is returned when there are no output_artifacts."""
        result = test_controller.GetArtifacts(
            common_pb2.ArtifactsByService.Test(output_artifacts=[]),
            self.chroot,
            self.sysroot,
            self.build_target,
            self.tempdir,
        )

        self.assertEqual(len(result), 0)

    def testShouldCallBundleCodeCoverageLlvmJsonForEachValidArtifact(self):
        """Test BundleCodeCoverageLlvmJson is called on each valid artifact."""
        BundleCodeCoverageLlvmJson_mock = self.PatchObject(
            test_service, "BundleCodeCoverageLlvmJson", return_value="test"
        )

        # pylint: disable=line-too-long
        test_controller.GetArtifacts(
            common_pb2.ArtifactsByService.Test(
                output_artifacts=[
                    # Valid
                    common_pb2.ArtifactsByService.Test.ArtifactInfo(
                        artifact_types=[self.CODE_COVERAGE_LLVM_ARTIFACT_TYPE]
                    ),
                    # Invalid
                    common_pb2.ArtifactsByService.Test.ArtifactInfo(
                        artifact_types=[
                            common_pb2.ArtifactsByService.Test.ArtifactType.UNIT_TESTS
                        ]
                    ),
                ]
            ),
            self.chroot,
            self.sysroot,
            self.build_target,
            self.tempdir,
        )
        # pylint: enable=line-too-long

        BundleCodeCoverageLlvmJson_mock.assert_called_once()

    def testShouldReturnValidResult(self):
        """Test result contains paths and code_coverage_llvm_json type."""
        self.PatchObject(
            test_service, "BundleCodeCoverageLlvmJson", return_value="test"
        )

        result = test_controller.GetArtifacts(
            common_pb2.ArtifactsByService.Test(
                output_artifacts=[
                    # Valid
                    common_pb2.ArtifactsByService.Test.ArtifactInfo(
                        artifact_types=[self.CODE_COVERAGE_LLVM_ARTIFACT_TYPE]
                    ),
                ]
            ),
            self.chroot,
            self.sysroot,
            self.build_target,
            self.tempdir,
        )

        self.assertEqual(result[0]["paths"], ["test"])
        self.assertEqual(
            result[0]["type"], self.CODE_COVERAGE_LLVM_ARTIFACT_TYPE
        )

    def testNoArtifacts(self):
        """Test GetArtifacts with no artifact types."""
        in_proto = self._InputProto(artifact_types=[])
        test_controller.GetArtifacts(
            in_proto, None, None, self.build_target, ""
        )

        for _, patch in self._mocks.items():
            patch.assert_not_called()

    def testArtifactsSuccess(self):
        """Test GetArtifacts with all artifact types."""
        test_controller.GetArtifacts(
            self._InputProto(), None, None, self.build_target, ""
        )

        for _, patch in self._mocks.items():
            patch.assert_called_once()

    def testArtifactsException(self):
        """Test with all artifact types when one type throws an exception."""

        self._mocks[
            common_pb2.ArtifactsByService.Test.ArtifactType.CODE_COVERAGE_GOLANG
        ].side_effect = Exception("foo bar")
        generated = test_controller.GetArtifacts(
            self._InputProto(), None, None, self.build_target, ""
        )

        for _, patch in self._mocks.items():
            patch.assert_called_once()

        found_artifact = False
        for data in generated:
            artifact_type = (
                common_pb2.ArtifactsByService.Test.ArtifactType.Name(
                    data["type"]
                )
            )
            if artifact_type == "CODE_COVERAGE_GOLANG":
                found_artifact = True
                self.assertTrue(data["failed"])
                self.assertEqual(data["failure_reason"], "foo bar")
        self.assertTrue(found_artifact)
