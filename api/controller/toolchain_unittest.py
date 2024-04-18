# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for Toolchain-related operations."""

import os

from chromite.api import api_config
from chromite.api import controller
from chromite.api.controller import toolchain
from chromite.api.gen.chromite.api import artifacts_pb2
from chromite.api.gen.chromite.api import sysroot_pb2
from chromite.api.gen.chromite.api import toolchain_pb2
from chromite.api.gen.chromiumos import builder_config_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import toolchain as toolchain_lib
from chromite.lib import toolchain_util
from chromite.service import toolchain as toolchain_service


# pylint: disable=protected-access

BuilderConfig = builder_config_pb2.BuilderConfig


class UpdateEbuildWithAFDOArtifactsTest(
    cros_test_lib.MockTestCase, api_config.ApiConfigMixin
):
    """Unittests for UpdateEbuildWithAFDOArtifacts."""

    @staticmethod
    def mock_die(message, *args):
        raise cros_build_lib.DieSystemExit(message % args)

    def setUp(self):
        self.board = "board"
        self.response = toolchain_pb2.VerifyAFDOArtifactsResponse()
        self.invalid_artifact_type = toolchain_pb2.BENCHMARK_AFDO
        self.PatchObject(cros_build_lib, "Die", new=self.mock_die)

    def _GetRequest(self, build_target=None, artifact_type=None):
        return toolchain_pb2.VerifyAFDOArtifactsRequest(
            build_target={"name": build_target},
            artifact_type=artifact_type,
        )


class PrepareForBuildTest(
    cros_test_lib.MockTempDirTestCase, api_config.ApiConfigMixin
):
    """Unittests for PrepareForBuild."""

    def setUp(self):
        self.response = toolchain_pb2.PrepareForToolchainBuildResponse()
        self.prep = self.PatchObject(
            toolchain_util,
            "PrepareForBuild",
            return_value=toolchain_util.PrepareForBuildReturn.NEEDED,
        )
        self.bundle = self.PatchObject(
            toolchain_util, "BundleArtifacts", return_value=[]
        )
        self.PatchObject(
            toolchain,
            "_TOOLCHAIN_ARTIFACT_HANDLERS",
            {
                BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE: (
                    toolchain._Handlers(
                        "UnverifiedChromeBenchmarkAfdoFile",
                        self.prep,
                        self.bundle,
                    )
                ),
            },
        )

    def _GetRequest(
        self, artifact_types=None, input_artifacts=None, additional_args=None
    ):
        chroot = common_pb2.Chroot(path=str(self.tempdir))
        sysroot = sysroot_pb2.Sysroot(
            path="/build/board",
            build_target=common_pb2.BuildTarget(name="board"),
        )
        return toolchain_pb2.PrepareForToolchainBuildRequest(
            artifact_types=artifact_types,
            chroot=chroot,
            sysroot=sysroot,
            input_artifacts=input_artifacts,
            additional_args=additional_args,
        )

    def testRaisesForUnknown(self):
        request = self._GetRequest([BuilderConfig.Artifacts.IMAGE_ARCHIVES])
        self.assertRaises(
            KeyError,
            toolchain.PrepareForBuild,
            request,
            self.response,
            self.api_config,
        )

    def testAcceptsNone(self):
        request = toolchain_pb2.PrepareForToolchainBuildRequest(
            artifact_types=[
                BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE
            ],
            chroot=None,
            sysroot=None,
        )
        toolchain.PrepareForBuild(request, self.response, self.api_config)
        self.prep.assert_called_once_with(
            "UnverifiedChromeBenchmarkAfdoFile", None, "", "", {}, {}
        )

    def testHandlesUnknownInputArtifacts(self):
        request = toolchain_pb2.PrepareForToolchainBuildRequest(
            artifact_types=[
                BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE
            ],
            chroot=None,
            sysroot=None,
            input_artifacts=[
                BuilderConfig.Artifacts.InputArtifactInfo(
                    input_artifact_type=BuilderConfig.Artifacts.IMAGE_ZIP,
                    input_artifact_gs_locations=["path1"],
                ),
            ],
        )
        toolchain.PrepareForBuild(request, self.response, self.api_config)
        self.prep.assert_called_once_with(
            "UnverifiedChromeBenchmarkAfdoFile", None, "", "", {}, {}
        )

    def testPassesProfileInfo(self):
        # pylint: disable=line-too-long
        request = toolchain_pb2.PrepareForToolchainBuildRequest(
            artifact_types=[
                BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE
            ],
            chroot=None,
            sysroot=None,
            input_artifacts=[
                BuilderConfig.Artifacts.InputArtifactInfo(
                    input_artifact_type=BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE,
                    input_artifact_gs_locations=["path1", "path2"],
                ),
                BuilderConfig.Artifacts.InputArtifactInfo(
                    input_artifact_type=BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE,
                    input_artifact_gs_locations=["path3"],
                ),
            ],
            profile_info=common_pb2.ArtifactProfileInfo(
                chrome_cwp_profile="CWPVERSION",
                arch="amd64",
            ),
        )
        # pylint: enable=line-too-long
        toolchain.PrepareForBuild(request, self.response, self.api_config)
        self.prep.assert_called_once_with(
            "UnverifiedChromeBenchmarkAfdoFile",
            None,
            "",
            "",
            {
                "UnverifiedChromeBenchmarkAfdoFile": [
                    "gs://path1",
                    "gs://path2",
                    "gs://path3",
                ],
            },
            {
                "chrome_cwp_profile": "CWPVERSION",
                "arch": "amd64",
            },
        )

    def testPassesProfileInfoAfdoRelease(self):
        # pylint: disable=line-too-long
        request = toolchain_pb2.PrepareForToolchainBuildRequest(
            artifact_types=[
                BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE
            ],
            chroot=None,
            sysroot=None,
            input_artifacts=[
                BuilderConfig.Artifacts.InputArtifactInfo(
                    input_artifact_type=BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE,
                    input_artifact_gs_locations=["path1", "path2"],
                ),
                BuilderConfig.Artifacts.InputArtifactInfo(
                    input_artifact_type=BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE,
                    input_artifact_gs_locations=["path3"],
                ),
            ],
            profile_info=common_pb2.ArtifactProfileInfo(
                afdo_release=common_pb2.AfdoRelease(
                    chrome_cwp_profile="CWPVERSION",
                    image_build_id=1234,
                ),
                arch="amd64",
            ),
        )
        # pylint: enable=line-too-long
        toolchain.PrepareForBuild(request, self.response, self.api_config)
        self.prep.assert_called_once_with(
            "UnverifiedChromeBenchmarkAfdoFile",
            None,
            "",
            "",
            {
                "UnverifiedChromeBenchmarkAfdoFile": [
                    "gs://path1",
                    "gs://path2",
                    "gs://path3",
                ],
            },
            {
                "chrome_cwp_profile": "CWPVERSION",
                "image_build_id": 1234,
                "arch": "amd64",
            },
        )

    def testHandlesDuplicateInputArtifacts(self):
        # pylint: disable=line-too-long
        request = toolchain_pb2.PrepareForToolchainBuildRequest(
            artifact_types=[
                BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE
            ],
            chroot=None,
            sysroot=None,
            input_artifacts=[
                BuilderConfig.Artifacts.InputArtifactInfo(
                    input_artifact_type=BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE,
                    input_artifact_gs_locations=["path1", "path2"],
                ),
                BuilderConfig.Artifacts.InputArtifactInfo(
                    input_artifact_type=BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE,
                    input_artifact_gs_locations=["path3"],
                ),
            ],
        )
        # pylint: enable=line-too-long
        toolchain.PrepareForBuild(request, self.response, self.api_config)
        self.prep.assert_called_once_with(
            "UnverifiedChromeBenchmarkAfdoFile",
            None,
            "",
            "",
            {
                "UnverifiedChromeBenchmarkAfdoFile": [
                    "gs://path1",
                    "gs://path2",
                    "gs://path3",
                ],
            },
            {},
        )


class BundleToolchainTest(
    cros_test_lib.MockTempDirTestCase, api_config.ApiConfigMixin
):
    """Unittests for BundleToolchain."""

    def setUp(self):
        self.response = toolchain_pb2.BundleToolchainResponse()
        self.prep = self.PatchObject(
            toolchain_util,
            "PrepareForBuild",
            return_value=toolchain_util.PrepareForBuildReturn.NEEDED,
        )
        self.bundle = self.PatchObject(
            toolchain_util, "BundleArtifacts", return_value=[]
        )
        self.PatchObject(
            toolchain,
            "_TOOLCHAIN_ARTIFACT_HANDLERS",
            {
                BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE: (
                    toolchain._Handlers(
                        "UnverifiedChromeBenchmarkAfdoFile",
                        self.prep,
                        self.bundle,
                    )
                ),
            },
        )
        osutils.WriteFile(os.path.join(self.tempdir, "artifact.txt"), "test")
        osutils.Touch(os.path.join(self.tempdir, "empty"))

    def _GetRequest(self, artifact_types=None):
        chroot = common_pb2.Chroot(path=str(self.tempdir))
        sysroot = sysroot_pb2.Sysroot(
            path="/build/board",
            build_target=common_pb2.BuildTarget(name="board"),
        )
        return toolchain_pb2.BundleToolchainRequest(
            chroot=chroot,
            sysroot=sysroot,
            output_dir=str(self.tempdir),
            artifact_types=artifact_types,
        )

    def testRaisesForUnknown(self):
        request = self._GetRequest([BuilderConfig.Artifacts.IMAGE_ARCHIVES])
        self.assertEqual(
            controller.RETURN_CODE_UNRECOVERABLE,
            toolchain.BundleArtifacts(request, self.response, self.api_config),
        )

    def testValidateOnly(self):
        """Sanity check that a validate only call does not execute any logic."""
        request = self._GetRequest(
            [BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE]
        )
        toolchain.BundleArtifacts(
            request, self.response, self.validate_only_config
        )
        self.bundle.assert_not_called()

    def testSetsArtifactsInfo(self):
        artifact_type = (
            BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE
        )
        request = self._GetRequest([artifact_type])
        self.bundle.return_value = ["artifact.txt", "empty", "does_not_exist"]
        toolchain.BundleArtifacts(request, self.response, self.api_config)
        self.assertEqual(1, len(self.response.artifacts_info))
        self.assertEqual(
            self.response.artifacts_info[0],
            toolchain_pb2.ArtifactInfo(
                artifact_type=artifact_type,
                artifacts=[
                    artifacts_pb2.Artifact(path=self.bundle.return_value[0])
                ],
            ),
        )


class GetUpdatedFilesTest(
    cros_test_lib.MockTempDirTestCase, api_config.ApiConfigMixin
):
    """Unittests for GetUpdatedFiles."""

    def setUp(self):
        self.response = toolchain_pb2.GetUpdatedFilesResponse()
        self.artifact_path = "/any/path/to/metadata"
        self.profile_info = common_pb2.ArtifactProfileInfo(
            kernel_version="4.4", arch="amd64"
        )
        self.update = self.PatchObject(
            toolchain_util, "GetUpdatedFiles", return_value=([], "")
        )

    def _GetRequest(self, uploaded_artifacts):
        uploaded = []
        for artifact_type, artifact_path, profile_info in uploaded_artifacts:
            uploaded.append(
                toolchain_pb2.GetUpdatedFilesRequest.UploadedArtifacts(
                    artifact_info=toolchain_pb2.ArtifactInfo(
                        artifact_type=artifact_type,
                        artifacts=[artifacts_pb2.Artifact(path=artifact_path)],
                    ),
                    profile_info=profile_info,
                )
            )
        return toolchain_pb2.GetUpdatedFilesRequest(uploaded_artifacts=uploaded)

    def testRaisesForUnknown(self):
        request = self._GetRequest(
            [
                (
                    BuilderConfig.Artifacts.UNVERIFIED_KERNEL_CWP_AFDO_FILE,
                    self.artifact_path,
                    self.profile_info,
                )
            ]
        )
        self.assertEqual(
            controller.RETURN_CODE_UNRECOVERABLE,
            toolchain.GetUpdatedFiles(request, self.response, self.api_config),
        )

    def testValidateOnly(self):
        """Sanity check that a validate only call does not execute any logic."""
        request = self._GetRequest(
            [
                (
                    BuilderConfig.Artifacts.VERIFIED_KERNEL_CWP_AFDO_FILE,
                    self.artifact_path,
                    self.profile_info,
                )
            ]
        )
        toolchain.GetUpdatedFiles(
            request, self.response, self.validate_only_config
        )

    def testUpdateSuccess(self):
        updated_file = "/path/to/updated_file"
        self.update.return_value = ([updated_file], "Commit Message")
        request = self._GetRequest(
            [
                (
                    BuilderConfig.Artifacts.VERIFIED_KERNEL_CWP_AFDO_FILE,
                    self.artifact_path,
                    self.profile_info,
                )
            ]
        )
        toolchain.GetUpdatedFiles(request, self.response, self.api_config)
        print(self.response.updated_files)
        self.assertEqual(len(self.response.updated_files), 1)
        self.assertEqual(
            self.response.updated_files[0],
            toolchain_pb2.GetUpdatedFilesResponse.UpdatedFile(
                path=updated_file
            ),
        )
        self.assertIn("Commit Message", self.response.commit_message)
        self.assertEqual(len(self.response.commit_footer), 0)


class GetToolchainsForBoardTest(
    cros_test_lib.MockTempDirTestCase, api_config.ApiConfigMixin
):
    """Unittests for GetToolchainsForBoard."""

    def setUp(self):
        self.response = toolchain_pb2.ToolchainsResponse()

    def _GetRequest(self, board="betty-pi-arc"):
        return toolchain_pb2.ToolchainsRequest(board=board)

    def testValidateOnly(self):
        """Verify a validate-only call does not execute any logic."""
        request = self._GetRequest()
        toolchain.GetToolchainsForBoard(
            request, self.response, self.validate_only_config
        )

    def testUpdateSuccess(self):
        toolchain_info = {
            "default-a": {"default": True},
            "default-b": {"default": True},
            "nondefault-a": {"default": False},
            "nondefault-b": {"default": False},
        }
        self.PatchObject(
            toolchain_lib,
            "get_toolchains_for_build_target",
            return_value=toolchain_info,
        )

        request = self._GetRequest()
        toolchain.GetToolchainsForBoard(request, self.response, self.api_config)

        self.assertEqual(
            self.response.default_toolchains, ["default-a", "default-b"]
        )
        self.assertEqual(
            self.response.nondefault_toolchains,
            ["nondefault-a", "nondefault-b"],
        )


class SetupToolchainsTest(
    cros_test_lib.MockTestCase, api_config.ApiConfigMixin
):
    """Unit tests for ToolchainService.SetupToolchains."""

    def setUp(self) -> None:
        self.response = toolchain_pb2.SetupToolchainsResponse()
        self.chroot = common_pb2.Chroot(path="/path/to/chroot")

    def test_outside_chroot(self) -> None:
        """Test the behavior if run from outside the chroot."""
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)
        self.PatchObject(toolchain_service, "setup_toolchains")
        request = toolchain_pb2.SetupToolchainsRequest(chroot=self.chroot)
        with self.assertRaises(cros_build_lib.DieSystemExit):
            toolchain.SetupToolchains(request, self.response, self.api_config)

    def test_with_empty_request(self) -> None:
        """Test the behavior if the request object is empty."""
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)
        service_mock = self.PatchObject(toolchain_service, "setup_toolchains")
        request = toolchain_pb2.SetupToolchainsRequest(chroot=self.chroot)
        toolchain.SetupToolchains(
            request,
            self.response,
            self.api_config,
        )
        service_mock.assert_called_once_with(include_boards=[])

    def test_with_boards(self) -> None:
        """Test the behavior if the request object specifies boards."""
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=True)
        service_mock = self.PatchObject(toolchain_service, "setup_toolchains")
        request = toolchain_pb2.SetupToolchainsRequest(
            chroot=self.chroot,
            boards=[
                common_pb2.BuildTarget(name="amd64-generic"),
                common_pb2.BuildTarget(name="arm-generic"),
            ],
        )
        toolchain.SetupToolchains(
            request,
            self.response,
            self.api_config,
        )
        service_mock.assert_called_once_with(
            include_boards=["amd64-generic", "arm-generic"],
        )
