# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Toolchain-related operations."""

import collections
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from chromite.api import controller
from chromite.api import faux
from chromite.api import validate
from chromite.api.controller import controller_util
from chromite.api.gen.chromite.api import artifacts_pb2
from chromite.api.gen.chromite.api import toolchain_pb2
from chromite.api.gen.chromiumos import builder_config_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import build_target_lib
from chromite.lib import cros_build_lib
from chromite.lib import toolchain as toolchain_lib
from chromite.lib import toolchain_util
from chromite.service import toolchain


if TYPE_CHECKING:
    from chromite.api import api_config


PrepareForBuildResponse = artifacts_pb2.PrepareForBuildResponse
BuilderConfig = builder_config_pb2.BuilderConfig
PackageInfo = common_pb2.PackageInfo

# TODO(b/229665884): Move the implementation details for most/all endpoints to:
#   chromite/services/toolchain.py
# This migration has been done for linting endpoints but not yet for others.

_Handlers = collections.namedtuple("_Handlers", ["name", "prepare", "bundle"])
_TOOLCHAIN_ARTIFACT_HANDLERS = {
    BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_AFDO_FILE: _Handlers(
        "UnverifiedChromeBenchmarkAfdoFile",
        toolchain_util.PrepareForBuild,
        toolchain_util.BundleArtifacts,
    ),
    BuilderConfig.Artifacts.CHROME_DEBUG_BINARY: _Handlers(
        "ChromeDebugBinary",
        toolchain_util.PrepareForBuild,
        toolchain_util.BundleArtifacts,
    ),
    BuilderConfig.Artifacts.UNVERIFIED_CHROME_BENCHMARK_PERF_FILE: _Handlers(
        "UnverifiedChromeBenchmarkPerfFile",
        toolchain_util.PrepareForBuild,
        toolchain_util.BundleArtifacts,
    ),
    BuilderConfig.Artifacts.VERIFIED_CHROME_BENCHMARK_AFDO_FILE: _Handlers(
        "VerifiedChromeBenchmarkAfdoFile",
        toolchain_util.PrepareForBuild,
        toolchain_util.BundleArtifacts,
    ),
    BuilderConfig.Artifacts.UNVERIFIED_KERNEL_CWP_AFDO_FILE: _Handlers(
        "UnverifiedKernelCwpAfdoFile",
        toolchain_util.PrepareForBuild,
        toolchain_util.BundleArtifacts,
    ),
    BuilderConfig.Artifacts.VERIFIED_KERNEL_CWP_AFDO_FILE: _Handlers(
        "VerifiedKernelCwpAfdoFile",
        toolchain_util.PrepareForBuild,
        toolchain_util.BundleArtifacts,
    ),
    BuilderConfig.Artifacts.UNVERIFIED_CHROME_CWP_AFDO_FILE: _Handlers(
        "UnverifiedChromeCwpAfdoFile",
        toolchain_util.PrepareForBuild,
        toolchain_util.BundleArtifacts,
    ),
    BuilderConfig.Artifacts.VERIFIED_CHROME_CWP_AFDO_FILE: _Handlers(
        "VerifiedChromeCwpAfdoFile",
        toolchain_util.PrepareForBuild,
        toolchain_util.BundleArtifacts,
    ),
    BuilderConfig.Artifacts.VERIFIED_RELEASE_AFDO_FILE: _Handlers(
        "VerifiedReleaseAfdoFile",
        toolchain_util.PrepareForBuild,
        toolchain_util.BundleArtifacts,
    ),
    BuilderConfig.Artifacts.TOOLCHAIN_WARNING_LOGS: _Handlers(
        "ToolchainWarningLogs",
        toolchain_util.PrepareForBuild,
        toolchain_util.BundleArtifacts,
    ),
    BuilderConfig.Artifacts.CHROME_AFDO_PROFILE_FOR_ANDROID_LINUX: _Handlers(
        "ChromeAFDOProfileForAndroidLinux",
        toolchain_util.PrepareForBuild,
        toolchain_util.BundleArtifacts,
    ),
    BuilderConfig.Artifacts.CLANG_CRASH_DIAGNOSES: _Handlers(
        "ClangCrashDiagnoses",
        toolchain_util.PrepareForBuild,
        toolchain_util.BundleArtifacts,
    ),
    BuilderConfig.Artifacts.COMPILER_RUSAGE_LOG: _Handlers(
        "CompilerRusageLogs",
        toolchain_util.PrepareForBuild,
        toolchain_util.BundleArtifacts,
    ),
}

# pylint: disable=line-too-long
_TOOLCHAIN_COMMIT_HANDLERS = {
    BuilderConfig.Artifacts.VERIFIED_KERNEL_CWP_AFDO_FILE: "VerifiedKernelCwpAfdoFile"
}
# pylint: enable=line-too-long


# TODO(crbug/1031213): When @faux is expanded to have more than success/failure,
# this should be changed.
@faux.all_empty
@validate.require("artifact_types")
# Note: chroot and sysroot are unspecified the first time that the build_target
# recipe calls PrepareForBuild.  The second time, they are specified.  No
# validation check because "all" values are valid.
@validate.validation_complete
def PrepareForBuild(
    input_proto: "toolchain_pb2.PrepareForToolchainBuildRequest",
    output_proto: "toolchain_pb2.PrepareForToolchainBuildResponse",
    _config: "api_config.ApiConfig",
):
    """Prepare to build toolchain artifacts.

    The handlers (from _TOOLCHAIN_ARTIFACT_HANDLERS above) are called with:
        artifact_name (str): name of the artifact type.
        chroot (chroot_lib.Chroot): chroot.  Will be None if the chroot has not
            yet been created.
        sysroot_path (str): sysroot path inside the chroot (e.g., /build/atlas).
            Will be an empty string if the sysroot has not yet been created.
        build_target_name (str): name of the build target (e.g., atlas). Will be
            an empty string if the sysroot has not yet been created.
        input_artifacts ({(str) name:[str gs_locations]}): locations for
            possible input artifacts.  The handler is expected to know which
            keys it should be using, and ignore any keys that it does not
            understand.
        profile_info ({(str) name: (str) value}) Dictionary containing profile
            information.

    They locate and modify any ebuilds and/or source required for the artifact
    being created, then return a value from
    toolchain_util.PrepareForBuildReturn.

    This function sets output_proto.build_relevance to the result.

    Args:
        input_proto: The input proto
        output_proto: The output proto
        _config): The API call config.
    """
    if input_proto.chroot.path:
        chroot = controller_util.ParseChroot(input_proto.chroot)
    else:
        chroot = None

    input_artifacts = collections.defaultdict(list)
    for art in input_proto.input_artifacts:
        item = _TOOLCHAIN_ARTIFACT_HANDLERS.get(art.input_artifact_type)
        if item:
            input_artifacts[item.name].extend(
                ["gs://%s" % str(x) for x in art.input_artifact_gs_locations]
            )

    profile_info = _GetProfileInfoDict(input_proto.profile_info)

    results = set()
    sysroot_path = input_proto.sysroot.path
    build_target = input_proto.sysroot.build_target.name
    for artifact_type in input_proto.artifact_types:
        # Unknown artifact_types are an error.
        handler = _TOOLCHAIN_ARTIFACT_HANDLERS[artifact_type]
        if handler.prepare:
            results.add(
                handler.prepare(
                    handler.name,
                    chroot,
                    sysroot_path,
                    build_target,
                    input_artifacts,
                    profile_info,
                )
            )

    # Translate the returns from the handlers we called.
    #   If any NEEDED => NEEDED
    #   elif any UNKNOWN => UNKNOWN
    #   elif any POINTLESS => POINTLESS
    #   else UNKNOWN.
    if toolchain_util.PrepareForBuildReturn.NEEDED in results:
        output_proto.build_relevance = PrepareForBuildResponse.NEEDED
    elif toolchain_util.PrepareForBuildReturn.UNKNOWN in results:
        output_proto.build_relevance = PrepareForBuildResponse.UNKNOWN
    elif toolchain_util.PrepareForBuildReturn.POINTLESS in results:
        output_proto.build_relevance = PrepareForBuildResponse.POINTLESS
    else:
        output_proto.build_relevance = PrepareForBuildResponse.UNKNOWN
    return controller.RETURN_CODE_SUCCESS


# TODO(crbug/1031213): When @faux is expanded to have more than success/failure,
# this should be changed.
@faux.all_empty
@validate.require("chroot.path", "output_dir", "artifact_types")
@validate.exists("output_dir")
@validate.validation_complete
def BundleArtifacts(
    input_proto: "toolchain_pb2.BundleToolchainRequest",
    output_proto: "toolchain_pb2.BundleToolchainResponse",
    _config: "api_config.ApiConfig",
):
    """Bundle valid toolchain artifacts.

    The handlers (from _TOOLCHAIN_ARTIFACT_HANDLERS above) are called with:
        artifact_name (str): name of the artifact type
        chroot (chroot_lib.Chroot): chroot
        sysroot_path (str): sysroot path inside the chroot (e.g., /build/atlas),
            or None.
        chrome_root (str): path to chrome root. (e.g., /b/s/w/ir/k/chrome)
        build_target_name (str): name of the build target (e.g. atlas), or None.
        output_dir (str): absolute path where artifacts are being bundled.
            (e.g., /b/s/w/ir/k/recipe_cleanup/artifactssptfMU)
        profile_info ({(str) name: (str) value}) Dictionary containing profile
            information.

    Note: the actual upload to GS is done by CI, not here.

    Args:
        input_proto: The input proto
        output_proto: The output proto
        _config: The API call config.
    """
    chroot = controller_util.ParseChroot(input_proto.chroot)

    profile_info = _GetProfileInfoDict(input_proto.profile_info)

    output_path = Path(input_proto.output_dir)

    for artifact_type in input_proto.artifact_types:
        if artifact_type not in _TOOLCHAIN_ARTIFACT_HANDLERS:
            logging.error("%s not understood", artifact_type)
            return controller.RETURN_CODE_UNRECOVERABLE

        handler = _TOOLCHAIN_ARTIFACT_HANDLERS[artifact_type]
        if not handler or not handler.bundle:
            logging.warning(
                "%s does not have a handler with a bundle function.",
                artifact_type,
            )
            continue

        artifacts = handler.bundle(
            handler.name,
            chroot,
            input_proto.sysroot.path,
            input_proto.sysroot.build_target.name,
            input_proto.output_dir,
            profile_info,
        )
        if not artifacts:
            continue

        # Filter out artifacts that do not exist or are empty.
        usable_artifacts = []
        for artifact in artifacts:
            artifact_path = output_path / artifact
            if not artifact_path.exists():
                logging.warning("%s is not in the output directory.", artifact)
            elif not artifact_path.stat().st_size:
                logging.warning("%s is empty.", artifact)
            else:
                usable_artifacts.append(artifact)

        if not usable_artifacts:
            logging.warning(
                "No usable artifacts for artifact type %s", artifact_type
            )
            continue

        # Add all usable artifacts.
        art_info = output_proto.artifacts_info.add()
        art_info.artifact_type = artifact_type
        for artifact in usable_artifacts:
            art_info.artifacts.add().path = artifact


def _GetUpdatedFilesResponse(_input_proto, output_proto, _config):
    """Add successful status to the faux response."""
    file_info = output_proto.updated_files.add()
    file_info.path = "/any/modified/file"
    output_proto.commit_message = "Commit message"


@faux.empty_error
@faux.success(_GetUpdatedFilesResponse)
@validate.require("uploaded_artifacts")
@validate.validation_complete
def GetUpdatedFiles(
    input_proto: "toolchain_pb2.GetUpdatedFilesRequest",
    output_proto: "toolchain_pb2.GetUpdatedFilesResponse",
    _config: "api_config.ApiConfig",
):
    """Use uploaded artifacts to update some updates in a chromeos checkout.

    The function will call toolchain_util.GetUpdatedFiles using the type of
    uploaded artifacts to make some changes in a checkout, and return the list
    of change files together with commit message.
        updated_artifacts: A list of UpdatedArtifacts type which contains a
            tuple of artifact info and profile info.
    Note: the actual creation of the commit is done by CI, not here.

    Args:
        input_proto: The input proto
        output_proto: The output proto
        _config: The API call config.
    """
    commit_message = ""
    for artifact in input_proto.uploaded_artifacts:
        artifact_type = artifact.artifact_info.artifact_type
        if artifact_type not in _TOOLCHAIN_COMMIT_HANDLERS:
            logging.error("%s not understood", artifact_type)
            return controller.RETURN_CODE_UNRECOVERABLE
        artifact_name = _TOOLCHAIN_COMMIT_HANDLERS[artifact_type]
        if artifact_name:
            assert (
                len(artifact.artifact_info.artifacts) == 1
            ), "Only one file to update per each artifact"
            updated_files, message = toolchain_util.GetUpdatedFiles(
                artifact_name,
                artifact.artifact_info.artifacts[0].path,
                _GetProfileInfoDict(artifact.profile_info),
            )
            for f in updated_files:
                file_info = output_proto.updated_files.add()
                file_info.path = f

            commit_message += message + "\n"
        output_proto.commit_message = commit_message
        # No commit footer is added for now. Can add more here if needed


def _GetProfileInfoDict(profile_info: "toolchain_pb2.ArtifactProfileInfo"):
    """Convert profile_info to a dict.

    Args:
        profile_info: The artifact profile_info.

    Returns:
        A dictionary containing profile info.
    """
    ret = {}
    which = profile_info.WhichOneof("artifact_profile_info")
    if which:
        value = getattr(profile_info, which)
        # If it is a message, then use the contents of the message.  This works
        # as long as simple types do not have a 'DESCRIPTOR' attribute. (And
        # protobuf messages do.)
        if getattr(value, "DESCRIPTOR", None):
            ret.update({k.name: v for k, v in value.ListFields()})
        else:
            ret[which] = value
    arch = getattr(profile_info, "arch", None)
    if arch:
        ret["arch"] = arch
    return ret


LINTER_CODES = {
    "clang_tidy": toolchain_pb2.LinterFinding.CLANG_TIDY,
    "cargo_clippy": toolchain_pb2.LinterFinding.CARGO_CLIPPY,
    "go_lint": toolchain_pb2.LinterFinding.GO_LINT,
}


@validate.require("sysroot.build_target.name")
@validate.require("start_time")
@validate.validation_complete
def EmergeAndUploadLints(
    input_proto: toolchain_pb2.DashboardLintRequest,
    output_proto: toolchain_pb2.DashboardLintResponse,
    _config,
):
    """Lint all platform2 packages and uploads lints to GS"""
    board = input_proto.sysroot.build_target.name
    output_proto.gs_path = toolchain.emerge_and_upload_lints(
        board, input_proto.start_time
    )


@faux.all_empty
@validate.exists("sysroot.path")
@validate.require("packages")
@validate.validation_complete
def EmergeWithLinting(
    input_proto: "toolchain_pb2.LinterRequest",
    output_proto: "toolchain_pb2.LinterResponse",
    _config: "api_config.ApiConfig",
):
    """Emerge packages with linter features enabled and retrieves all findings.

    Args:
        input_proto: The input proto with package and sysroot info.
        output_proto: The output proto where findings are stored.
        _config: The API call config (unused).
    """
    packages = [
        controller_util.deserialize_package_info(package)
        for package in input_proto.packages
    ]

    build_linter = toolchain.BuildLinter(
        packages,
        input_proto.sysroot.path,
        differential=input_proto.filter_modified,
    )

    use_clippy = (
        toolchain_pb2.LinterFinding.CARGO_CLIPPY
        not in input_proto.disabled_linters
    )
    use_tidy = (
        toolchain_pb2.LinterFinding.CLANG_TIDY
        not in input_proto.disabled_linters
    )
    use_golint = (
        toolchain_pb2.LinterFinding.GO_LINT not in input_proto.disabled_linters
    )
    use_iwyu = (
        toolchain_pb2.LinterFinding.IWYU not in input_proto.disabled_linters
    )

    findings = build_linter.emerge_with_linting(
        use_clippy=use_clippy,
        use_tidy=use_tidy,
        use_golint=use_golint,
        use_iwyu=use_iwyu,
    )

    for finding in findings:
        locations = []
        for location in finding.locations:
            locations.append(
                toolchain_pb2.LinterFindingLocation(
                    filepath=location.filepath,
                    line_start=location.line_start,
                    line_end=location.line_end,
                )
            )

        pkg = PackageInfo()
        if finding.package:
            pkg.category = finding.package.category
            pkg.package_name = finding.package.package
            pkg.version = finding.package.version
        output_proto.findings.append(
            toolchain_pb2.LinterFinding(
                message=finding.message,
                locations=locations,
                linter=LINTER_CODES[finding.linter],
                package=pkg,
            )
        )


@faux.all_empty
@validate.require("board")
@validate.validation_complete
def GetToolchainsForBoard(
    input_proto: "toolchain_pb2.ToolchainsRequest",
    output_proto: "toolchain_pb2.ToolchainsReponse",
    _config: "api_config.ApiConfig",
):
    """Get the default and non-default toolchains for a board.

    Args:
        input_proto: The input proto with board and sysroot info.
        output_proto: The output proto where findings are stored.
        _config: The API call config (unused).
    """
    build_target = build_target_lib.BuildTarget(input_proto.board)
    toolchains = toolchain_lib.get_toolchains_for_build_target(build_target)
    output_proto.default_toolchains.extend(
        list(toolchain_lib.FilterToolchains(toolchains, "default", True))
    )
    output_proto.nondefault_toolchains.extend(
        list(toolchain_lib.FilterToolchains(toolchains, "default", False))
    )


@faux.all_empty
@validate.validation_complete
def SetupToolchains(
    input_proto: "toolchain_pb2.SetupToolchainsRequest",
    output_proto: "toolchain_pb2.SetupToolchainsResponse",
    config: "api_config.ApiConfig",
):
    """Run `cros_setup_toolchains`."""
    del output_proto, config  # Unused.
    cros_build_lib.AssertInsideChroot()
    include_boards = [bt.name for bt in input_proto.boards]
    toolchain.setup_toolchains(include_boards=include_boards)
