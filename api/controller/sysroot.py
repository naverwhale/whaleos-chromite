# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Sysroot controller."""

import logging
import os
from pathlib import Path
import traceback

from chromite.api import controller
from chromite.api import faux
from chromite.api import metrics
from chromite.api import validate
from chromite.api.controller import controller_util
from chromite.api.gen.chromite.api import sysroot_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import build_target_lib
from chromite.lib import chroot_lib
from chromite.lib import cros_build_lib
from chromite.lib import goma_lib
from chromite.lib import metrics_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import remoteexec_lib
from chromite.lib import sysroot_lib
from chromite.service import sysroot


_ACCEPTED_LICENSES = "@CHROMEOS"

DEFAULT_BACKTRACK = 30


def _GetGomaLogDirectory():
    """Get goma's log directory based on the env variables.

    Returns:
        a string of a directory name where goma's log may exist, or None if no
        potential directories exist.
    """
    # TODO(crbug.com/1045001): Replace environment variable with query to
    # goma object after goma refactoring allows this.
    candidates = [
        "GLOG_log_dir",
        "GOOGLE_LOG_DIR",
        "TEST_TMPDIR",
        "TMPDIR",
        "TMP",
    ]
    for candidate in candidates:
        value = os.environ.get(candidate)
        if value and os.path.isdir(value):
            return value

    # "/tmp" will always exist.
    return "/tmp"


def ExampleGetResponse():
    """Give an example response to assemble upstream in caller artifacts."""
    uabs = common_pb2.UploadedArtifactsByService
    cabs = common_pb2.ArtifactsByService
    return uabs.Sysroot(
        artifacts=[
            uabs.Sysroot.ArtifactPaths(
                artifact_type=cabs.Sysroot.ArtifactType.SIMPLE_CHROME_SYSROOT,
                paths=[
                    common_pb2.Path(
                        path=(
                            "/tmp/sysroot_chromeos-base_chromeos-chrome.tar.xz"
                        ),
                        location=common_pb2.Path.OUTSIDE,
                    )
                ],
            ),
            uabs.Sysroot.ArtifactPaths(
                artifact_type=cabs.Sysroot.ArtifactType.DEBUG_SYMBOLS,
                paths=[
                    common_pb2.Path(
                        path="/tmp/debug.tgz", location=common_pb2.Path.OUTSIDE
                    )
                ],
            ),
            uabs.Sysroot.ArtifactPaths(
                artifact_type=cabs.Sysroot.ArtifactType.BREAKPAD_DEBUG_SYMBOLS,
                paths=[
                    common_pb2.Path(
                        path="/tmp/debug_breakpad.tar.xz",
                        location=common_pb2.Path.OUTSIDE,
                    )
                ],
            ),
        ]
    )


def GetArtifacts(
    in_proto: common_pb2.ArtifactsByService.Sysroot,
    chroot: chroot_lib.Chroot,
    sysroot_class: sysroot_lib.Sysroot,
    build_target: build_target_lib.BuildTarget,
    output_dir: str,
) -> list:
    """Builds and copies sysroot artifacts to specified output_dir.

    Copies sysroot artifacts to output_dir, returning a list of
    (output_dir: str) paths to the desired files.

    Args:
        in_proto: Proto request defining reqs.
        chroot: The chroot class used for these artifacts.
        sysroot_class: The sysroot class used for these artifacts.
        build_target: The build target used for these artifacts.
        output_dir: The path to write artifacts to.

    Returns:
        A list of dictionary mappings of ArtifactType to list of paths.
    """

    def _BundleBreakpadSymbols(chroot, sysroot_class, build_target, output_dir):
        # pylint: disable=line-too-long
        ignore_breakpad_symbol_generation_expected_files = [
            common_pb2.ArtifactsByService.Sysroot.BreakpadSymbolGenerationExpectedFile.Name(
                x
            )
            for x in in_proto.ignore_breakpad_symbol_generation_expected_files
            if x
            != common_pb2.ArtifactsByService.Sysroot.BreakpadSymbolGenerationExpectedFile.EXPECTED_FILE_UNSET
            and x
            in common_pb2.ArtifactsByService.Sysroot.BreakpadSymbolGenerationExpectedFile.values()
        ]
        # pylint: enable=line-too-long

        ignore_breakpad_symbol_generation_expected_files = [
            x[len("EXPECTED_FILE_") :]
            for x in ignore_breakpad_symbol_generation_expected_files
        ]

        return sysroot.BundleBreakpadSymbols(
            chroot,
            sysroot_class,
            build_target,
            output_dir,
            in_proto.ignore_breakpad_symbol_generation_errors,
            ignore_breakpad_symbol_generation_expected_files,
        )

    generated = []
    # pylint: disable=line-too-long
    artifact_types = {
        in_proto.ArtifactType.SIMPLE_CHROME_SYSROOT: sysroot.CreateSimpleChromeSysroot,
        in_proto.ArtifactType.CHROME_EBUILD_ENV: sysroot.CreateChromeEbuildEnv,
        in_proto.ArtifactType.BREAKPAD_DEBUG_SYMBOLS: _BundleBreakpadSymbols,
        in_proto.ArtifactType.DEBUG_SYMBOLS: sysroot.BundleDebugSymbols,
        in_proto.ArtifactType.FUZZER_SYSROOT: sysroot.CreateFuzzerSysroot,
        in_proto.ArtifactType.SYSROOT_ARCHIVE: sysroot.ArchiveSysroot,
        in_proto.ArtifactType.BAZEL_PERFORMANCE_ARTIFACTS: sysroot.CollectBazelPerformanceArtifacts,
    }
    # pylint: enable=line-too-long

    for output_artifact in in_proto.output_artifacts:
        for artifact_type, func in artifact_types.items():
            if artifact_type in output_artifact.artifact_types:
                try:
                    result = func(
                        chroot, sysroot_class, build_target, output_dir
                    )
                except Exception as e:
                    generated.append(
                        {
                            "type": artifact_type,
                            "failed": True,
                            "failure_reason": str(e),
                        }
                    )
                    artifact_name = (
                        common_pb2.ArtifactsByService.Sysroot.ArtifactType.Name(
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
                if result:
                    generated.append(
                        {
                            "paths": [str(result)]
                            if isinstance(result, (os.PathLike, str))
                            else result,
                            "type": artifact_type,
                        }
                    )

    return generated


@faux.all_empty
@validate.require("build_target.name")
@validate.validation_complete
def Create(input_proto, output_proto, _config):
    """Create or replace a sysroot."""
    update_chroot = not input_proto.flags.chroot_current
    replace_sysroot = input_proto.flags.replace
    use_cq_prebuilts = input_proto.flags.use_cq_prebuilts

    build_target = controller_util.ParseBuildTarget(
        input_proto.build_target, input_proto.profile
    )
    package_indexes = [
        controller_util.deserialize_package_index_info(x)
        for x in input_proto.package_indexes
    ]
    run_configs = sysroot.SetupBoardRunConfig(
        force=replace_sysroot,
        upgrade_chroot=update_chroot,
        package_indexes=package_indexes,
        use_cq_prebuilts=use_cq_prebuilts,
        backtrack=DEFAULT_BACKTRACK,
    )

    try:
        created = sysroot.Create(
            build_target, run_configs, accept_licenses=_ACCEPTED_LICENSES
        )
    except sysroot.Error as e:
        cros_build_lib.Die(e)

    output_proto.sysroot.path = created.path
    output_proto.sysroot.build_target.name = build_target.name

    return controller.RETURN_CODE_SUCCESS


@faux.all_empty
@validate.require("build_target.name", "packages")
@validate.require_each("packages", ["category", "package_name"])
@validate.validation_complete
def GenerateArchive(input_proto, output_proto, _config):
    """Generate a sysroot. Typically used by informational builders."""
    build_target_name = input_proto.build_target.name
    pkg_list = []
    for package in input_proto.packages:
        pkg_list.append("%s/%s" % (package.category, package.package_name))

    with osutils.TempDir(delete=False) as temp_output_dir:
        sysroot_tar_path = sysroot.GenerateArchive(
            temp_output_dir, build_target_name, pkg_list
        )

    # By assigning this Path variable to the tar path, the tar file will be
    # copied out to the input_proto's ResultPath location.
    output_proto.sysroot_archive.path = sysroot_tar_path
    output_proto.sysroot_archive.location = common_pb2.Path.INSIDE


def _MockFailedPackagesResponse(_input_proto, output_proto, _config):
    """Mock error response that populates failed packages."""
    fail = output_proto.failed_package_data.add()
    fail.name.package_name = "package"
    fail.name.category = "category"
    fail.name.version = "1.0.0_rc-r1"
    fail.log_path.path = (
        "/path/to/package:category-1.0.0_rc-r1:20210609-1337.log"
    )
    fail.log_path.location = common_pb2.Path.INSIDE

    fail2 = output_proto.failed_package_data.add()
    fail2.name.package_name = "bar"
    fail2.name.category = "foo"
    fail2.name.version = "3.7-r99"
    fail2.log_path.path = "/path/to/foo:bar-3.7-r99:20210609-1620.log"
    fail2.log_path.location = common_pb2.Path.INSIDE


@faux.empty_success
@faux.error(_MockFailedPackagesResponse)
@validate.require("sysroot.path", "sysroot.build_target.name")
@validate.exists("sysroot.path")
@validate.validation_complete
def InstallToolchain(input_proto, output_proto, _config):
    """Install the toolchain into a sysroot."""
    compile_source = (
        input_proto.flags.compile_source or input_proto.flags.toolchain_changed
    )

    sysroot_path = input_proto.sysroot.path

    build_target = controller_util.ParseBuildTarget(
        input_proto.sysroot.build_target
    )
    target_sysroot = sysroot_lib.Sysroot(sysroot_path)
    run_configs = sysroot.SetupBoardRunConfig(usepkg=not compile_source)

    _LogBinhost(build_target.name)

    try:
        sysroot.InstallToolchain(build_target, target_sysroot, run_configs)
    except sysroot_lib.ToolchainInstallError as e:
        controller_util.retrieve_package_log_paths(
            e.failed_toolchain_info, output_proto, target_sysroot
        )

        return controller.RETURN_CODE_UNSUCCESSFUL_RESPONSE_AVAILABLE

    return controller.RETURN_CODE_SUCCESS


@faux.empty_success
@faux.error(_MockFailedPackagesResponse)
@validate.require("sysroot.build_target.name")
@validate.exists("sysroot.path")
@validate.require_each("packages", ["category", "package_name"])
@validate.require_each("use_flags", ["flag"])
@validate.validation_complete
@metrics_lib.collect_metrics
def InstallPackages(
    input_proto: sysroot_pb2.InstallPackagesRequest,
    output_proto: sysroot_pb2.InstallPackagesResponse,
    _config: "api_config.ApiConfig",
):
    """Install packages into a sysroot, building as necessary and permitted."""
    compile_source = (
        input_proto.flags.compile_source or input_proto.flags.toolchain_changed
    )

    use_remoteexec = bool(
        input_proto.remoteexec_config.reproxy_cfg_file
        and input_proto.remoteexec_config.reclient_dir
    )

    # Testing if Goma will support unknown compilers now.
    use_goma = input_proto.flags.use_goma and not use_remoteexec

    target_sysroot = sysroot_lib.Sysroot(input_proto.sysroot.path)
    build_target = controller_util.ParseBuildTarget(
        input_proto.sysroot.build_target
    )

    # Get the package atom for each specified package. The field is optional, so
    # error only when we cannot parse an atom for each of the given packages.
    packages = [
        controller_util.deserialize_package_info(x).atom
        for x in input_proto.packages
    ]

    package_indexes = [
        controller_util.deserialize_package_index_info(x)
        for x in input_proto.package_indexes
    ]

    # Calculate which packages would have been merged, but don't install
    # anything.
    dryrun = input_proto.flags.dryrun

    # Allow cros workon packages to build from the unstable ebuilds.
    workon = input_proto.flags.workon

    # Use Bazel to build packages.
    bazel = input_proto.flags.bazel

    # Lite build restricts the set of packages that will be built.
    bazel_lite = (
        input_proto.bazel_targets == sysroot_pb2.InstallPackagesRequest.LITE
    )

    if not target_sysroot.IsToolchainInstalled():
        cros_build_lib.Die("Toolchain must first be installed.")

    _LogBinhost(build_target.name)

    use_flags = [u.flag for u in input_proto.use_flags]
    build_packages_config = sysroot.BuildPackagesRunConfig(
        use_any_chrome=False,
        usepkg=not compile_source,
        install_debug_symbols=True,
        packages=packages,
        package_indexes=package_indexes,
        use_flags=use_flags,
        use_goma=use_goma,
        use_remoteexec=use_remoteexec,
        incremental_build=False,
        dryrun=dryrun,
        backtrack=DEFAULT_BACKTRACK,
        workon=workon,
        bazel=bazel,
        bazel_lite=bazel_lite,
    )

    try:
        sysroot.BuildPackages(
            build_target, target_sysroot, build_packages_config
        )
    except sysroot_lib.PackageInstallError as e:
        if not e.failed_packages:
            # No packages to report, so just exit with an error code.
            return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY

        controller_util.retrieve_package_log_paths(
            e.failed_packages, output_proto, target_sysroot
        )

        return controller.RETURN_CODE_UNSUCCESSFUL_RESPONSE_AVAILABLE
    finally:
        # Copy goma logs to specified directory if there is a goma_config and
        # it contains a log_dir to store artifacts.
        if input_proto.goma_config.log_dir.dir:
            log_source_dir = _GetGomaLogDirectory()
            archiver = goma_lib.LogsArchiver(
                log_source_dir,
                dest_dir=input_proto.goma_config.log_dir.dir,
                stats_file=input_proto.goma_config.stats_file,
                counterz_file=input_proto.goma_config.counterz_file,
            )
            archiver_tuple = archiver.Archive()
            if archiver_tuple.stats_file:
                output_proto.goma_artifacts.stats_file = (
                    archiver_tuple.stats_file
                )
            if archiver_tuple.counterz_file:
                output_proto.goma_artifacts.counterz_file = (
                    archiver_tuple.counterz_file
                )
            output_proto.goma_artifacts.log_files[:] = archiver_tuple.log_files

        if input_proto.remoteexec_config.log_dir.dir:
            archiver = remoteexec_lib.LogsArchiver(
                dest_dir=Path(input_proto.remoteexec_config.log_dir.dir),
            )
            archived_logs = archiver.archive()
            output_proto.remoteexec_artifacts.log_files[:] = [
                str(x) for x in archived_logs
            ]

    # Return without populating the response if it is a dryrun.
    if dryrun:
        return controller.RETURN_CODE_SUCCESS

    # Read metric events log and pipe them into output_proto.events.
    metrics.deserialize_metrics_log(
        output_proto.events, prefix=build_target.name
    )


def _LogBinhost(board):
    """Log the portage binhost for the given board."""
    binhost = portage_util.PortageqEnvvar(
        "PORTAGE_BINHOST", board=board, allow_undefined=True
    )
    if not binhost:
        logging.warning("Portage Binhost not found.")
    else:
        logging.info("Portage Binhost: %s", binhost)
