# Copyright 2018 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Compile the Build API's proto.

Install proto using CIPD to ensure a consistent protoc version.
"""

import enum
import logging
from pathlib import Path
import tempfile
from typing import Iterable, Optional

from chromite.lib import cipd
from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import git
from chromite.lib import osutils


# Chromite's protobuf library version (third_party/google/protobuf).
PROTOC_VERSION = "21.9"

# Protobuf dropped the major version number after 3.20, jumping to 21.0. But
# some places (e.g., in protobuf/__init__.py) refer to this as 4.21.0.
PROTOC_MAJOR_VERSION = "4"

_CIPD_PACKAGE = "infra/3pp/tools/protoc/linux-amd64"
_CIPD_PACKAGE_VERSION = f"version:2@{PROTOC_VERSION}"
_CHROMEOS_CONFIG_PATH = constants.SOURCE_ROOT / "src" / "config"


class Error(Exception):
    """Base error class for the module."""


class GenerationError(Error):
    """A failure we can't recover from."""


@enum.unique
class ProtocVersion(enum.Enum):
    """Enum for possible protoc versions."""

    # The SDK version of the bindings use the protoc in the SDK, and so is
    # compatible with the protobuf library in the SDK, i.e. the one installed
    # via the ebuild.
    SDK = enum.auto()
    # The Chromite version of the bindings uses a protoc binary downloaded from
    # CIPD that matches the version of the protobuf library in
    # chromite/third_party/google/protobuf.
    CHROMITE = enum.auto()
    # Type annotations for the chromite bindings.
    CHROMITE_PYI = enum.auto()

    def get_gen_dir(self) -> Path:
        """Get the chromite/api directory path."""
        if self is ProtocVersion.SDK:
            return constants.CHROMITE_DIR / "api" / "gen_sdk"
        return constants.CHROMITE_DIR / "api" / "gen"

    def get_proto_dir(self) -> Path:
        """Get the proto directory for the target protoc."""
        return constants.CHROMITE_DIR / "infra" / "proto"

    def get_protoc_command(self, cipd_root: Optional[Path] = None) -> Path:
        """Get protoc command path."""
        if self is ProtocVersion.SDK:
            return Path("protoc")
        assert cipd_root
        return cipd_root / "bin" / "protoc"

    def get_suffix(self) -> str:
        """Get the file suffix of generated output."""
        return "pyi" if self is ProtocVersion.CHROMITE_PYI else "py"


@enum.unique
class SubdirectorySet(enum.Enum):
    """Enum for the subsets of the proto to compile."""

    ALL = enum.auto()
    DEFAULT = enum.auto()

    def get_source_dirs(
        self, source: Path, chromeos_config_path: Path
    ) -> Iterable[Path]:
        """Get the directories for the given subdirectory set."""
        if self is self.ALL:
            return [
                source,
                chromeos_config_path / "proto" / "chromiumos",
            ]

        subdirs = [
            source / "analysis_service",
            source / "chromite",
            source / "chromiumos",
            source / "config",
            source / "test_platform",
            source / "device",
            chromeos_config_path / "proto" / "chromiumos",
        ]
        return subdirs


def check_upstream_changes(repo: Path) -> None:
    """Ensures the checked-out branch at `repo` includes the upstream HEAD."""
    branch = git.GetCurrentBranch(repo)
    if branch:
        upstream = git.GetTrackingBranchViaGitConfig(
            repo, branch, for_checkout=False
        )
        if not upstream:
            cros_build_lib.Die("Failed to get upstream for %s.", repo)
    else:
        # Detached head.
        branch = "HEAD"
        upstream = git.RemoteRef("cros", "refs/heads/main")
    remote_head = git.RunGit(
        repo,
        ["ls-remote", upstream.remote, upstream.ref],
    ).stdout.split(maxsplit=1)[0]
    logging.notice(
        "Ensuring proto dir %s contains %s from %s",
        repo.relative_to(constants.SOURCE_ROOT),
        upstream.ref,
        upstream.remote,
    )
    branches = git.RunGit(
        repo,
        ["branch", "--contains", remote_head, branch],
        print_cmd=True,
        check=False,
    )
    # Git emits the branch name if the commit is in the history. Otherwise, the
    # commit is either not found (git exits with an error - 129), or missing
    # from the branch. In either case, there is no output to stdout.
    if not branches.stdout:
        cros_build_lib.Die(
            "The checked-out branch (%s) at %s is missing the remote head.\n"
            "Please repo sync (and rebase), or skip this check by passing"
            " --no-check-upstream-proto-changes-included.",
            branch,
            repo,
        )


def InstallProtoc(protoc_version: ProtocVersion) -> Path:
    """Install protoc from CIPD."""
    if protoc_version is ProtocVersion.SDK:
        cipd_root = None
    else:
        cipd_root = Path(
            cipd.InstallPackage(
                cipd.GetCIPDFromCache(), _CIPD_PACKAGE, _CIPD_PACKAGE_VERSION
            )
        )
    return protoc_version.get_protoc_command(cipd_root)


def _CleanTargetDirectory(directory: Path, protoc_version: ProtocVersion):
    """Remove any existing generated files in the directory.

    This clean only removes the generated files to avoid accidentally destroying
    __init__.py customizations down the line. That will leave otherwise empty
    directories in place if things get moved. Neither case is relevant at the
    time of writing, but lingering empty directories seemed better than
    diagnosing accidental __init__.py changes.

    Args:
        directory: Path to be cleaned up.
        protoc_version: The type of generated files to be cleaned.
    """
    logging.info("Cleaning old files from %s.", directory)
    for current in directory.rglob(f"*_pb2.{protoc_version.get_suffix()}"):
        # Remove old generated files.
        current.unlink()

    # Note the generator does not currently make __init__.pyi files but, if it
    # did, we'd want them to be cleaned up here.
    for current in directory.rglob(f"__init__.{protoc_version.get_suffix()}"):
        # Remove empty init files to clean up otherwise empty directories.
        if not current.stat().st_size:
            current.unlink()


def _GenerateFiles(
    source: Path,
    output: Path,
    protoc_version: ProtocVersion,
    dir_subset: SubdirectorySet,
    protoc_bin_path: Path,
):
    """Generate the proto files from the |source| tree into |output|.

    Args:
        source: Path to the proto source root directory.
        output: Path to the output root directory.
        protoc_version: Which protoc to use.
        dir_subset: The subset of the proto to compile.
        protoc_bin_path: The protoc command to use.
    """
    logging.info("Generating %s files to %s.", protoc_version, output)
    osutils.SafeMakedirs(output)

    targets = []

    chromeos_config_path = _CHROMEOS_CONFIG_PATH

    with tempfile.TemporaryDirectory() as tempdir:
        if not chromeos_config_path.exists():
            chromeos_config_path = Path(tempdir) / "config"

            logging.info("Creating shallow clone of chromiumos/config")
            git.Clone(
                chromeos_config_path,
                "%s/chromiumos/config" % constants.EXTERNAL_GOB_URL,
                depth=1,
            )

        for src_dir in dir_subset.get_source_dirs(source, chromeos_config_path):
            targets.extend(list(src_dir.rglob("*.proto")))

        output_type = (
            "pyi" if protoc_version is ProtocVersion.CHROMITE_PYI else "python"
        )
        cmd = [
            protoc_bin_path,
            "-I",
            chromeos_config_path / "proto",
            f"--{output_type}_out",
            output,
            "--proto_path",
            source,
        ]
        cmd.extend(targets)

        result = cros_build_lib.dbg_run(
            cmd,
            cwd=source,
            check=False,
            enter_chroot=protoc_version is ProtocVersion.SDK,
        )

        if result.returncode:
            raise GenerationError(
                "Error compiling the proto. See the output for a " "message."
            )


def _InstallMissingInits(directory: Path, protoc_version: ProtocVersion):
    """Add missing __init__.py files in the generated protobuf folders."""
    if protoc_version is ProtocVersion.CHROMITE_PYI:
        # For pyi, rely on module markers left behind by CHROMITE flows to avoid
        # additional clutter.
        return

    logging.info("Adding missing __init__.py files in %s.", directory)
    # glob ** returns only directories.
    for current in directory.rglob("**"):
        (current / "__init__.py").touch()


def _PostprocessFiles(directory: Path, protoc_version: ProtocVersion):
    """Do postprocessing on the generated files.

    Args:
        directory: The root directory containing the generated files that are
            to be processed.
        protoc_version: Which protoc is being used to generate the files.
    """
    logging.info("Postprocessing: Fix imports in %s.", directory)
    # We are using a negative address here (the /address/! portion of the sed
    # command) to make sure we don't change any imports from protobuf itself.
    address = "^from google.protobuf"
    # Find: 'from x import y_pb2 as x_dot_y_pb2'.
    # "\(^google.protobuf[^ ]*\)" matches the module we're importing from.
    #   - \( and \) are for groups in sed.
    #   - ^google.protobuf prevents changing the import for protobuf's files.
    #   - [^ ] = Not a space. The [:space:] character set is too broad, but
    #       would technically work too.
    find = r"^from \([^ ]*\) import \([^ ]*\)_pb2 as \([^ ]*\)$"
    # Substitute: 'from chromite.api.gen[_sdk].x import y_pb2 as x_dot_y_pb2'.
    if protoc_version is ProtocVersion.SDK:
        sub = "from chromite.api.gen_sdk.\\1 import \\2_pb2 as \\3"
    else:
        sub = "from chromite.api.gen.\\1 import \\2_pb2 as \\3"

    seds = [f"/{address}/!s/{find}/{sub}/g"]

    if protoc_version is ProtocVersion.CHROMITE:
        # We also need to change the google.protobuf imports to point directly
        # at the chromite.third_party version of the library.
        # The SDK version of the proto is meant to be used with the protobuf
        # libraries installed in the SDK, so leave those as google.protobuf.
        # For CHROMITE_PYI, types for the protobuf imports come from type stubs,
        # which won't map if the imports are renamed to third_party.
        g_p_address = "^from google.protobuf"
        g_p_find = r"from \([^ ]*\) import \(.*\)$"
        g_p_sub = "from chromite.third_party.\\1 import \\2"
        seds.append(f"/{g_p_address}/s/{g_p_find}/{g_p_sub}/")

    if protoc_version is ProtocVersion.CHROMITE_PYI:
        # Workaround https://github.com/protocolbuffers/protobuf/issues/11402
        # until cl/560557754 in in the protoc version used.
        untyped_empty_slot_list = "s/\\(^ *__slots__ = \\)\\[]/\\1()/"

        # Suppress errors on GRPC options field numbers using ClassVar outside
        # of a class body. See b/297782342.
        ignore_class_var_in_file_scope = (
            "s/^[A-Z_]*: _ClassVar\\[int]/&  # type: ignore/"
        )
        seds.extend((untyped_empty_slot_list, ignore_class_var_in_file_scope))

    pb2 = list(directory.rglob(f"*_pb2.{protoc_version.get_suffix()}"))
    if pb2:
        cros_build_lib.dbg_run(["sed", "-i", ";".join(seds)] + pb2)


def CompileProto(
    protoc_version: ProtocVersion,
    output: Optional[Path] = None,
    dir_subset: SubdirectorySet = SubdirectorySet.DEFAULT,
    postprocess: bool = True,
):
    """Compile the Build API protobuf files.

    By default, this will compile from infra/proto/src to api/gen. The output
    directory may be changed, but the imports will always be treated as if it is
    in the default location.

    Args:
        output: The output directory.
        protoc_version: Which protoc to use for the compilation.
        dir_subset: What proto to compile.
        postprocess: Whether to run the postprocess step.
    """
    source = protoc_version.get_proto_dir() / "src"
    if not output:
        output = protoc_version.get_gen_dir()

    protoc_bin_path = InstallProtoc(protoc_version)
    _CleanTargetDirectory(output, protoc_version)
    _GenerateFiles(source, output, protoc_version, dir_subset, protoc_bin_path)
    _InstallMissingInits(output, protoc_version)
    if postprocess:
        _PostprocessFiles(output, protoc_version)


def GetParser():
    """Build the argument parser."""
    parser = commandline.ArgumentParser(description=__doc__)
    parser.add_bool_argument(
        "--check-upstream-proto-changes-included",
        True,
        "Check whether the checked-out proto branch includes changes"
        " from refs/heads/main on the remote.",
        "Skip the check that validates whether upstream proto changes"
        " are included in the current branch.",
    )
    standard_group = parser.add_argument_group(
        "Committed Bindings",
        description="Options for generating the bindings in chromite/api/.",
    )
    standard_group.add_argument(
        "--chromite",
        dest="protoc_version",
        action="append_const",
        const=ProtocVersion.CHROMITE,
        help="Generate only the chromite bindings. Generates all by default. "
        "The chromite bindings are compatible with the version of protobuf "
        "in chromite/third_party.",
    )
    standard_group.add_argument(
        "--pyi",
        dest="protoc_version",
        action="append_const",
        const=ProtocVersion.CHROMITE_PYI,
        help="Generate only the pyi type annotations.",
    )
    standard_group.add_argument(
        "--sdk",
        dest="protoc_version",
        action="append_const",
        const=ProtocVersion.SDK,
        help="Generate only the SDK bindings. Generates all by default. The "
        "SDK bindings are compiled by protoc in the SDK, and is compatible "
        "with the version of protobuf in the SDK (i.e. the one installed by "
        "the ebuild).",
    )

    dest_group = parser.add_argument_group(
        "Out of Tree Bindings",
        description="Options for generating bindings in a custom location.",
    )
    dest_group.add_argument(
        "--destination",
        type="path",
        help="A directory where a single version of the proto should be "
        "generated. When not given, the proto generates in all default "
        "locations instead.",
    )
    dest_group.add_argument(
        "--dest-sdk",
        action="store_const",
        dest="dest_protoc",
        default=ProtocVersion.CHROMITE,
        const=ProtocVersion.SDK,
        help="Generate the SDK version of the protos in --destination instead "
        "of the chromite version.",
    )
    dest_group.add_argument(
        "--all-proto",
        action="store_const",
        dest="dir_subset",
        default=SubdirectorySet.DEFAULT,
        const=SubdirectorySet.ALL,
        help="Compile ALL proto instead of just the subset needed for the API. "
        "Only considered when generating out of tree bindings.",
    )
    dest_group.add_argument(
        "--skip-postprocessing",
        action="store_false",
        dest="postprocess",
        default=True,
        help="Skip postprocessing files.",
    )
    return parser


def _ParseArguments(argv):
    """Parse and validate arguments."""
    parser = GetParser()
    opts = parser.parse_args(argv)

    if not opts.protoc_version:
        opts.protoc_version = [
            ProtocVersion.CHROMITE,
            ProtocVersion.SDK,
            ProtocVersion.CHROMITE_PYI,
        ]

    if opts.destination:
        opts.destination = Path(opts.destination)

    opts.Freeze()
    return opts


def main(argv):
    opts = _ParseArguments(argv)

    if opts.destination:
        # Destination set, only compile a single version in the destination.
        try:
            CompileProto(
                protoc_version=opts.dest_protoc,
                output=opts.destination,
                dir_subset=opts.dir_subset,
                postprocess=opts.postprocess,
            )
        except Error as e:
            cros_build_lib.Die("Error compiling bindings to destination: %s", e)
        else:
            return 0

    if ProtocVersion.CHROMITE in opts.protoc_version:
        # Validate here to avoid checking again inside the chroot.
        if opts.check_upstream_proto_changes_included:
            check_upstream_changes(ProtocVersion.CHROMITE.get_proto_dir())
            if _CHROMEOS_CONFIG_PATH.exists():
                check_upstream_changes(_CHROMEOS_CONFIG_PATH)

        # Compile the chromite bindings.
        try:
            CompileProto(protoc_version=ProtocVersion.CHROMITE)
        except Error as e:
            cros_build_lib.Die("Error compiling chromite bindings: %s", e)

    if ProtocVersion.CHROMITE_PYI in opts.protoc_version:
        try:
            CompileProto(protoc_version=ProtocVersion.CHROMITE_PYI)
        except Error as e:
            cros_build_lib.Die("Error compiling type annotations: %s", e)

    if ProtocVersion.SDK in opts.protoc_version:
        # Compile the SDK bindings.
        if not cros_build_lib.IsInsideChroot():
            # Rerun inside the SDK instead of trying to map all the paths.
            cmd = [
                (
                    constants.CHROOT_SOURCE_ROOT
                    / "chromite"
                    / "api"
                    / "compile_build_api_proto"
                ),
                "--sdk",
            ]
            result = cros_build_lib.dbg_run(cmd, enter_chroot=True, check=False)
            return result.returncode
        else:
            try:
                CompileProto(protoc_version=ProtocVersion.SDK)
            except Error as e:
                cros_build_lib.Die("Error compiling SDK bindings: %s", e)
