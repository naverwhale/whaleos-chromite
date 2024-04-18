# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrapper for board specific portage commands.

This script is meant to be used in generated wrapper scripts, not used directly.
"""

import os
from pathlib import Path
from typing import Iterable, List, Optional

from chromite.third_party.opentelemetry import trace

from chromite.lib import build_query
from chromite.lib import chromite_config
from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import sysroot_lib
from chromite.lib.parser import package_info
from chromite.utils import telemetry


tracer = trace.get_tracer(__name__)


def get_parser() -> commandline.ArgumentParser:
    """Build the argument parser."""
    parser = commandline.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--build-target",
        required=True,
        help="The build target name.",
    )
    parser.add_argument(
        "--sysroot",
        type="path",
        required=True,
        help="The path to the sysroot for which the command will be created.",
    )
    parser.add_argument(
        "--chost",
        required=True,
        help="The CHOST value for the sysroot.",
    )
    parser.add_argument(
        "command",
        nargs="+",
        help="The command to run.",
    )

    return parser


def parse_arguments(argv: List[str]) -> commandline.ArgumentNamespace:
    """Parse and validate arguments."""
    parser = get_parser()
    opts = parser.parse_args(argv)

    opts.Freeze()
    return opts


def parse_pkgs(command: List[str], build_target_name: str) -> Iterable[str]:
    """Parse packages from a command."""
    pkg_fragments = set()
    for arg in command[1:]:
        if arg.startswith("-"):
            # Skip --arguments.
            continue

        try:
            pkg = package_info.parse(arg)
        except ValueError:
            # e.g. /some/path.
            continue

        if pkg.cpvr or pkg.atom:
            # We have at least an atom, that's good enough.
            yield pkg.cpvr or pkg.atom
        else:
            # The fragment gets parsed as the package name.
            pkg_fragments.add(pkg.package)

    if pkg_fragments:
        ebuilds = build_query.Query(build_query.Ebuild, board=build_target_name)
        for ebuild in ebuilds:
            if ebuild.package_info.package in pkg_fragments:
                yield ebuild.package_info.cpvr


# TODO: Find a better name and a reusable location for this.
def sudo_run_cmd_with_failed_pkg_parsing(command, extra_env):
    """Wrapper for sudo_run that adds CROS_METRICS_DIR usage."""
    extra_env = extra_env.copy()
    with osutils.TempDir() as tempdir:
        extra_env[constants.CROS_METRICS_DIR_ENVVAR] = tempdir
        try:
            return cros_build_lib.sudo_run(
                command,
                print_cmd=False,
                preserve_env=True,
                extra_env=extra_env,
            )
        except cros_build_lib.RunCommandError as e:
            raise sysroot_lib.PackageInstallError(
                "Merging board packages failed",
                e.result,
                exception=e,
                packages=portage_util.ParseDieHookStatusFile(tempdir),
            ) from e


@tracer.start_as_current_span("portage_cmd_wrapper.execute")
def execute(opts: commandline.ArgumentNamespace) -> int:
    """Execute the command."""
    span = trace.get_current_span()
    span.update_name(f"portage_cmd_wrapper.{opts.command[0]}.execute")

    extra_env = {
        "CHOST": opts.chost,
        "PORTAGE_CONFIGROOT": opts.sysroot,
        "SYSROOT": opts.sysroot,
        "ROOT": opts.sysroot,
        "PORTAGE_USERNAME": (
            os.environ.get("PORTAGE_USERNAME") or Path("~").expanduser().name
        ),
    }

    # If we try to use sudo when the sandbox is active, we get ugly warnings
    # that just confuse developers.
    if os.environ.get("SANDBOX_ON") == "1":
        os.environ["SANDBOX_ON"] = "0"
    os.environ.pop("LD_PRELOAD", None)

    with tracer.start_as_current_span("portage_cmd_wrapper.parse_pkgs"):
        pkgs = list(parse_pkgs(opts.command, opts.build_target))

    span.set_attributes(
        {
            "executable": opts.command[0],
            "command": opts.command,
            "build_target": opts.build_target,
            "extra_env": [f"{k}={v}" for k, v in extra_env.items()],
            "packages": pkgs,
        }
    )

    result = sudo_run_cmd_with_failed_pkg_parsing(opts.command, extra_env)
    return result.returncode


def main(argv: Optional[List[str]]) -> Optional[int]:
    """Main."""
    commandline.RunInsideChroot()

    opts = parse_arguments(argv)

    chromite_config.initialize()
    telemetry.initialize(
        chromite_config.TELEMETRY_CONFIG, log_traces=opts.log_telemetry
    )

    try:
        return execute(opts)
    except cros_build_lib.RunCommandError as e:
        return e.returncode
    except KeyboardInterrupt:
        # No stack trace.
        return 1
