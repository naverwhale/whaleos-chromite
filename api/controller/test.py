# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test controller.

Handles all testing related functionality, it is not itself a test.
"""

import functools
import logging
import os
import string
import subprocess
import traceback

from chromite.third_party.google.protobuf import json_format

from chromite.api import controller
from chromite.api import faux
from chromite.api import validate
from chromite.api.controller import controller_util
from chromite.api.gen.chromite.api import test_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.api.gen.chromiumos.build.api import container_metadata_pb2
from chromite.api.metrics import deserialize_metrics_log
from chromite.lib import build_target_lib
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import goma_lib
from chromite.lib import metrics_lib
from chromite.lib import osutils
from chromite.lib import sysroot_lib
from chromite.lib.parser import package_info
from chromite.service import packages as packages_service
from chromite.service import test


@faux.empty_success
@faux.empty_completed_unsuccessfully_error
def DebugInfoTest(input_proto, _output_proto, config):
    """Run the debug info tests."""
    sysroot_path = input_proto.sysroot.path
    target_name = input_proto.sysroot.build_target.name

    if not sysroot_path:
        if target_name:
            sysroot_path = build_target_lib.get_default_sysroot_path(
                target_name
            )
        else:
            cros_build_lib.Die(
                "The sysroot path or the sysroot's build target name "
                "must be provided."
            )

    # We could get away with out this, but it's a cheap check.
    sysroot = sysroot_lib.Sysroot(sysroot_path)
    if not sysroot.Exists():
        cros_build_lib.Die("The provided sysroot does not exist.")

    if config.validate_only:
        return controller.RETURN_CODE_VALID_INPUT

    if test.DebugInfoTest(sysroot_path):
        return controller.RETURN_CODE_SUCCESS
    else:
        return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY


def _BuildTargetUnitTestFailedResponse(_input_proto, output_proto, _config):
    """Add failed packages to a failed response."""
    packages = ["foo/bar", "cat/pkg"]
    for pkg in packages:
        pkg_info = package_info.parse(pkg)
        failed_pkg_data_msg = output_proto.failed_package_data.add()
        controller_util.serialize_package_info(
            pkg_info, failed_pkg_data_msg.name
        )
        failed_pkg_data_msg.log_path.path = "/path/to/%s/log" % pkg


@faux.empty_success
@faux.error(_BuildTargetUnitTestFailedResponse)
@validate.require_each("packages", ["category", "package_name"])
@validate.validation_complete
@metrics_lib.collect_metrics
def BuildTargetUnitTest(input_proto, output_proto, _config):
    """Run a build target's ebuild unit tests."""
    # Method flags.
    # An empty sysroot means build packages was not run. This is used for
    # certain boards that need to use prebuilts (e.g. grunt's unittest-only).
    was_built = not input_proto.flags.empty_sysroot

    # Packages to be tested.
    packages = [
        controller_util.deserialize_package_info(x).atom
        for x in input_proto.packages
    ]

    # Skipped tests.
    blocklist = [
        controller_util.deserialize_package_info(x).atom
        for x in input_proto.package_blocklist
    ]

    # Allow call to filter out non-cros_workon packages from the input packages.
    filter_only_cros_workon = input_proto.flags.filter_only_cros_workon

    # Allow call to succeed if no tests were found.
    testable_packages_optional = input_proto.flags.testable_packages_optional

    build_target = controller_util.ParseBuildTarget(input_proto.build_target)

    code_coverage = input_proto.flags.code_coverage
    rust_code_coverage = input_proto.flags.rust_code_coverage

    bazel = input_proto.flags.bazel

    sysroot = sysroot_lib.Sysroot(build_target.root)

    result = test.BuildTargetUnitTest(
        build_target,
        packages=packages,
        blocklist=blocklist,
        was_built=was_built,
        code_coverage=code_coverage,
        rust_code_coverage=rust_code_coverage,
        testable_packages_optional=testable_packages_optional,
        filter_only_cros_workon=filter_only_cros_workon,
        bazel=bazel,
    )

    if not result.success:
        # Record all failed packages and retrieve log locations.
        controller_util.retrieve_package_log_paths(
            result.failed_pkgs, output_proto, sysroot
        )
        if result.failed_pkgs:
            return controller.RETURN_CODE_UNSUCCESSFUL_RESPONSE_AVAILABLE
        else:
            return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY

    deserialize_metrics_log(output_proto.events, prefix=build_target.name)


SRC_DIR = os.path.join(constants.SOURCE_ROOT, "src")
PLATFORM_DEV_DIR = os.path.join(SRC_DIR, "platform/dev")
TEST_SERVICE_DIR = os.path.join(PLATFORM_DEV_DIR, "src/chromiumos/test")


def _BuildTestServiceContainersResponse(input_proto, output_proto, _config):
    """Fake success response"""
    # pylint: disable=unused-argument
    output_proto.results.append(
        test_pb2.TestServiceContainerBuildResult(
            success=test_pb2.TestServiceContainerBuildResult.Success()
        )
    )


def _BuildTestServiceContainersFailedResponse(
    _input_proto, output_proto, _config
):
    """Fake failure response"""

    # pylint: disable=unused-argument
    output_proto.results.append(
        test_pb2.TestServiceContainerBuildResult(
            failure=test_pb2.TestServiceContainerBuildResult.Failure(
                error_message="fake error"
            )
        )
    )


@validate.constraint("valid docker tag")
def _ValidDockerTag(tag):
    """Check that a string meets requirements for Docker tag naming."""
    # Tags can't start with period or dash
    if tag[0] in ".-":
        return "tag can't begin with '.' or '-'"

    # Tags can only consist of [a-zA-Z0-9-_.]
    allowed_chars = set(string.ascii_letters + string.digits + "-_.")
    invalid_chars = set(tag) - allowed_chars
    if invalid_chars:
        return f'saw one or more invalid characters: [{"".join(invalid_chars)}]'

    # Finally, max tag length is 128 characters
    if len(tag) > 128:
        return "maximum tag length is 128 characters"


@validate.constraint("valid docker label key")
def _ValidDockerLabelKey(key):
    """Check that a string meets requirements for Docker tag naming."""

    # Label keys should start and end with a lowercase letter
    lowercase = set(string.ascii_lowercase)
    if not (key[0] in lowercase and key[-1] in lowercase):
        return "label key doesn't start and end with lowercase letter"

    # Label keys can have lower-case alphanumeric characters, period and dash
    allowed_chars = set(string.ascii_lowercase + string.digits + "-.")
    invalid_chars = set(key) - allowed_chars
    if invalid_chars:
        return f'saw one or more invalid characters: [{"".join(invalid_chars)}]'

    # Repeated . and - aren't allowed
    for char in ".-":
        if char * 2 in key:
            return f"'{char}' can't be repeated in label key"


@faux.success(_BuildTestServiceContainersResponse)
@faux.error(_BuildTestServiceContainersFailedResponse)
@validate.require("build_target.name", "chroot.path", "chroot.out_path")
@validate.check_constraint("tags", _ValidDockerTag)
@validate.check_constraint("labels", _ValidDockerLabelKey)
@validate.validation_complete
def BuildTestServiceContainers(
    input_proto: test_pb2.BuildTestServiceContainersRequest,
    output_proto: test_pb2.BuildTestServiceContainersResponse,
    _config,
):
    """Build docker containers for all test services and push them to gcr.io."""
    build_target = controller_util.ParseBuildTarget(input_proto.build_target)
    chroot = controller_util.ParseChroot(input_proto.chroot)
    sysroot = sysroot_lib.Sysroot(build_target.root)

    tags = ",".join(input_proto.tags)
    labels = (f"{key}={value}" for key, value in input_proto.labels.items())

    build_script = os.path.join(
        TEST_SERVICE_DIR, "python/src/docker_libs/cli/build-dockerimages.py"
    )
    human_name = "Service Builder"

    with osutils.TempDir(prefix="test_container") as tempdir:
        result_file = "metadata.jsonpb"
        output_path = os.path.join(tempdir, result_file)
        # Note that we use an output file instead of stdout to avoid any issues
        # with maintaining stdout hygiene.  Stdout and stderr are combined to
        # form the error log in response to any errors.
        cmd = [
            build_script,
            chroot.path,
            sysroot.path,
            "--out-dir",
            chroot.out_path,
        ]

        if input_proto.HasField("repository"):
            cmd += ["--host", input_proto.repository.hostname]
            cmd += ["--project", input_proto.repository.project]

        cmd += ["--tags", tags]
        cmd += ["--output", output_path]

        # Translate generator to comma separated string.
        ct_labels = ",".join(labels)
        cmd += ["--labels", ct_labels]
        cmd += ["--build_all"]
        cmd += ["--upload"]

        cmd_result = cros_build_lib.run(
            cmd, check=False, stderr=subprocess.STDOUT, stdout=True
        )

        if cmd_result.returncode != 0:
            # When failing, just record a fail response with the builder name.
            logging.debug(
                "%s build failed.\nStdout:\n%s\nStderr:\n%s",
                human_name,
                cmd_result.stdout,
                cmd_result.stderr,
            )
            result = test_pb2.TestServiceContainerBuildResult()
            result.name = human_name
            image_info = container_metadata_pb2.ContainerImageInfo()
            result.failure.CopyFrom(
                test_pb2.TestServiceContainerBuildResult.Failure(
                    error_message=cmd_result.stdout
                )
            )
            output_proto.results.append(result)

        else:
            logging.debug(
                "%s build succeeded.\nStdout:\n%s\nStderr:\n%s",
                human_name,
                cmd_result.stdout,
                cmd_result.stderr,
            )
            files = os.listdir(tempdir)
            # Iterate through the tempdir to output metadata files.
            for file in files:
                if result_file in file:
                    output_path = os.path.join(tempdir, file)

                    # build-dockerimages.py will append the service name to
                    # outputfile with an underscore.
                    human_name = file.split("_")[-1]

                    result = test_pb2.TestServiceContainerBuildResult()
                    result.name = human_name
                    image_info = container_metadata_pb2.ContainerImageInfo()
                    json_format.Parse(osutils.ReadFile(output_path), image_info)
                    result.success.CopyFrom(
                        test_pb2.TestServiceContainerBuildResult.Success(
                            image_info=image_info
                        )
                    )
                    output_proto.results.append(result)


@faux.empty_success
@faux.empty_completed_unsuccessfully_error
@validate.validation_complete
def ChromiteUnitTest(_input_proto, _output_proto, _config):
    """Run the chromite unit tests."""
    if test.ChromiteUnitTest():
        return controller.RETURN_CODE_SUCCESS
    else:
        return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY


@faux.empty_success
@faux.empty_completed_unsuccessfully_error
@validate.validation_complete
def ChromitePytest(_input_proto, _output_proto, _config):
    """Run the chromite unit tests."""
    # TODO(vapier): Delete this stub.
    return controller.RETURN_CODE_SUCCESS


@faux.empty_success
@faux.empty_completed_unsuccessfully_error
@validate.validation_complete
def BazelTest(input_proto, _output_proto, _config):
    """Run the Bazel tests."""
    output_user_root = input_proto.bazel_output_user_root or None
    if test.BazelTest(output_user_root=output_user_root):
        return controller.RETURN_CODE_SUCCESS
    else:
        return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY


@faux.empty_success
@faux.empty_completed_unsuccessfully_error
@validate.validation_complete
def RulesCrosUnitTest(_input_proto, _output_proto, _config):
    """Run the rules_cros unit tests."""
    if test.RulesCrosUnitTest():
        return controller.RETURN_CODE_SUCCESS
    else:
        return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY


@faux.all_empty
@validate.require("sysroot.path", "sysroot.build_target.name", "chrome_root")
@validate.validation_complete
def SimpleChromeWorkflowTest(input_proto, _output_proto, _config):
    """Run SimpleChromeWorkflow tests."""
    if input_proto.goma_config.goma_dir:
        chromeos_goma_dir = input_proto.goma_config.chromeos_goma_dir or None
        goma = goma_lib.Goma(
            input_proto.goma_config.goma_dir,
            stage_name="BuildApiTestSimpleChrome",
            chromeos_goma_dir=chromeos_goma_dir,
        )
    else:
        goma = None
    return test.SimpleChromeWorkflowTest(
        input_proto.sysroot.path,
        input_proto.sysroot.build_target.name,
        input_proto.chrome_root,
        goma,
    )


@faux.all_empty
@validate.require(
    "build_target.name", "vm_path.path", "test_harness", "vm_tests"
)
@validate.validation_complete
def VmTest(input_proto, _output_proto, _config):
    """Run VM tests."""
    build_target_name = input_proto.build_target.name
    vm_path = input_proto.vm_path.path

    test_harness = input_proto.test_harness

    vm_tests = input_proto.vm_tests

    cmd = [
        "cros_run_test",
        "--debug",
        "--no-display",
        "--copy-on-write",
        "--board",
        build_target_name,
        "--image-path",
        vm_path,
        "--%s" % test_pb2.VmTestRequest.TestHarness.Name(test_harness).lower(),
    ]
    cmd.extend(vm_test.pattern for vm_test in vm_tests)

    if input_proto.ssh_options.port:
        cmd.extend(["--ssh-port", str(input_proto.ssh_options.port)])

    if input_proto.ssh_options.private_key_path:
        cmd.extend(
            ["--private-key", input_proto.ssh_options.private_key_path.path]
        )

    # TODO(evanhernandez): Find a nice way to pass test_that-args through
    # the build API. Or obviate them.
    if test_harness == test_pb2.VmTestRequest.AUTOTEST:
        cmd.append("--test_that-args=--allow-chrome-crashes")

    with osutils.TempDir(prefix="vm-test-results.") as results_dir:
        cmd.extend(["--results-dir", results_dir])
        cros_build_lib.run(cmd, kill_timeout=10 * 60)


@faux.all_empty
@validate.validation_complete
def CrosSigningTest(_input_proto, _output_proto, _config):
    """Run the cros-signing unit tests."""
    test_runner = os.path.join(
        constants.SOURCE_ROOT, "cros-signing", "signer", "run_tests.py"
    )
    result = cros_build_lib.run([test_runner], check=False)

    return result.returncode


def GetArtifacts(
    in_proto: common_pb2.ArtifactsByService.Test,
    chroot: chroot_lib.Chroot,
    sysroot_class: sysroot_lib.Sysroot,
    build_target: build_target_lib.BuildTarget,
    output_dir: str,
) -> list:
    """Builds and copies test artifacts to specified output_dir.

    Copies test artifacts to output_dir, returning a list of (output_dir: str)
    paths to the desired files.

    Args:
        in_proto: Proto request defining reqs.
        chroot: The chroot class used for these artifacts.
        sysroot_class: The sysroot class used for these artifacts.
        build_target: The build target used for these artifacts.
        output_dir: The path to write artifacts to.

    Returns:
        A list of dictionary mappings of ArtifactType to list of paths.
    """
    generated = []

    artifact_types = {
        in_proto.ArtifactType.CODE_COVERAGE_LLVM_JSON: functools.partial(
            test.BundleCodeCoverageLlvmJson, build_target.name
        ),
        in_proto.ArtifactType.CODE_COVERAGE_RUST_LLVM_JSON: functools.partial(
            test.BundleCodeCoverageRustLlvmJson, build_target.name
        ),
        in_proto.ArtifactType.HWQUAL: functools.partial(
            test.BundleHwqualTarball,
            build_target.name,
            packages_service.determine_full_version(),
        ),
        in_proto.ArtifactType.CODE_COVERAGE_GOLANG: functools.partial(
            test.BundleCodeCoverageGolang
        ),
    }

    for output_artifact in in_proto.output_artifacts:
        for artifact_type, func in artifact_types.items():
            if artifact_type in output_artifact.artifact_types:
                try:
                    if (
                        artifact_type
                        == in_proto.ArtifactType.CODE_COVERAGE_GOLANG
                    ):
                        paths = func(chroot, output_dir)
                    else:
                        paths = func(chroot, sysroot_class, output_dir)
                except Exception as e:
                    generated.append(
                        {
                            "type": artifact_type,
                            "failed": True,
                            "failure_reason": str(e),
                        }
                    )
                    artifact_name = (
                        common_pb2.ArtifactsByService.Test.ArtifactType.Name(
                            artifact_type
                        )
                    )
                    logging.warning(
                        "%s artifact generation failed with exception %s",
                        artifact_name,
                        e,
                    )
                    logging.warning("traceback:\n%s", traceback.format_exc())
                    continue
                if paths:
                    generated.append(
                        {
                            "paths": [paths]
                            if isinstance(paths, str)
                            else paths,
                            "type": artifact_type,
                        }
                    )

    return generated
