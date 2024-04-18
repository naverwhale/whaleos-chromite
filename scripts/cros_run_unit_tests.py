# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tool to run ebuild unittests."""

import logging
import multiprocessing
import os

from chromite.third_party.opentelemetry import trace

from chromite.lib import build_target_lib
from chromite.lib import chromite_config
from chromite.lib import chroot_util
from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import workon_helper
from chromite.scripts import cros_extract_deps
from chromite.utils import telemetry


tracer = trace.get_tracer(__name__)


BOARD_VIRTUAL_PACKAGES = (
    constants.TARGET_OS_PKG,
    constants.TARGET_OS_DEV_PKG,
    constants.TARGET_OS_TEST_PKG,
    constants.TARGET_OS_FACTORY_PKG,
)
SDK_VIRTUAL_PACKAGES = (constants.TARGET_SDK,)
IMPLICIT_TEST_DEPS = ("virtual/implicit-system",)


def ParseArgs(argv):
    """Parse arguments.

    Args:
        argv: array of arguments passed to the script.
    """
    parser = commandline.ArgumentParser(description=__doc__)

    target = parser.add_mutually_exclusive_group(required=True)

    target.add_argument("--sysroot", type="path", help="Path to the sysroot.")
    target.add_argument("--board", help="Board name.")
    target.add_argument(
        "--host", action="store_true", help="Run tests for the host SDK."
    )

    parser.add_argument(
        "--emerge-verbose",
        default=False,
        action="store_true",
        help="Output emerge details.",
    )

    parser.add_argument(
        "--pretend",
        default=False,
        action="store_true",
        help="Show the list of packages to be tested and return.",
    )
    parser.add_argument(
        "--noinstalled_only",
        dest="installed",
        default=True,
        action="store_false",
        help=(
            "Test all testable packages, even if they are not "
            "currently installed."
        ),
    )
    parser.add_argument(
        "--package_file",
        type="path",
        help=(
            "Path to a file containing the list of packages "
            "that should be tested."
        ),
    )
    parser.add_argument(
        "--packages", help="Space-separated list of packages to test."
    )
    parser.add_argument(
        "--skip-packages",
        help=(
            "Space-separated list of packages to NOT test even "
            "if they otherwise would have been tested."
        ),
    )
    parser.add_argument(
        "--nowithdebug",
        action="store_true",
        help="Don't build the tests with USE=cros-debug",
    )
    parser.add_argument(
        "--assume-empty-sysroot",
        default=False,
        action="store_true",
        dest="empty_sysroot",
        help=(
            "Set up dependencies and run unit tests for all "
            "packages that could be installed on target board "
            "without assuming that any packages have actually "
            "been merged yet."
        ),
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=multiprocessing.cpu_count(),
        help="The limit for the number of possible concurrent jobs.",
    )
    parser.add_argument(
        "--no-testable-packages-ok",
        default=False,
        action="store_true",
        dest="testable_packages_optional",
        help="If specified, do not fail if no testable packages are found.",
    )
    parser.add_argument(
        "--filter-only-cros-workon",
        default=False,
        action="store_true",
        help=(
            "If specified and packages are given, filters out non-cros_workon "
            "packages."
        ),
    )

    options = parser.parse_args(argv)
    options.Freeze()
    return options


def determine_packages(sysroot, virtual_packages):
    """Returns a set of the dependencies for the given packages"""
    deps, _bdeps = cros_extract_deps.ExtractDeps(
        sysroot, virtual_packages, include_bdepend=False
    )
    return set(
        "%s/%s" % (atom["category"], atom["name"]) for atom in deps.values()
    )


def get_keep_going():
    """Check if should enable keep_going parameter.

    If the 'USE' environment contains 'coverage' then enable keep_going option
    to prevent certain package failure from breaking the whole coverage
    generation workflow, otherwise leave it to default settings
    """
    return "coverage" in os.environ.get("USE", "")


def main(argv):
    opts = ParseArgs(argv)

    cros_build_lib.AssertInsideChroot()

    chromite_config.initialize()
    telemetry.initialize(
        chromite_config.TELEMETRY_CONFIG, log_traces=opts.log_telemetry
    )

    with tracer.start_as_current_span("scripts.cros_run_unit_tests"):
        inner_main(opts)


def inner_main(opts: commandline.ArgumentNamespace):
    """The inner main to run cros unit tests."""

    span = trace.get_current_span()

    sysroot = (
        opts.sysroot or "/"
        if opts.host
        else build_target_lib.get_default_sysroot_path(opts.board)
    )
    skipped_packages = set()
    if opts.skip_packages:
        skipped_packages |= set(opts.skip_packages.split())

    packages = set()
    # The list of packages to test can be passed as a file containing a
    # space-separated list of package names.
    # This is used by the builder to test only the packages that were uprevved.
    if opts.package_file and os.path.exists(opts.package_file):
        packages = set(osutils.ReadFile(opts.package_file).split())

    if opts.packages:
        packages |= set(opts.packages.split())

    # If no packages were specified, use all testable packages.
    if not (opts.packages or opts.package_file) and not opts.empty_sysroot:
        workon = workon_helper.WorkonHelper(sysroot)
        packages = (
            workon.InstalledWorkonAtoms()
            if opts.installed
            else set(workon.ListAtoms(use_all=True))
        )

    if opts.empty_sysroot:
        packages |= determine_packages(
            sysroot,
            SDK_VIRTUAL_PACKAGES if opts.host else BOARD_VIRTUAL_PACKAGES,
        )
        workon = workon_helper.WorkonHelper(sysroot)
        workon_packages = set(workon.ListAtoms(use_all=True))
        packages &= workon_packages

    for cp in packages & skipped_packages:
        logging.info("Skipping package %s.", cp)

    packages = packages - skipped_packages
    pkg_with_test = portage_util.PackagesWithTest(
        sysroot, packages, opts.filter_only_cros_workon
    )

    if packages - pkg_with_test:
        logging.warning(
            "The following packages do not have tests:\n  %s",
            "\n  ".join(sorted(packages - pkg_with_test)),
        )

    span.set_attributes(
        {
            "sysroot": sysroot,
            "packages": pkg_with_test,
            "pretend": opts.pretend,
            "jobs": opts.jobs,
            "empty_sysroot": opts.empty_sysroot,
        }
    )

    if not pkg_with_test:
        if opts.testable_packages_optional:
            logging.warning("No testable packages found!")
            return 0
        logging.error("No testable packages found!")
        return 1

    if opts.pretend:
        print("\n".join(sorted(pkg_with_test)))
        return 0

    env = {}
    if opts.nowithdebug:
        use_flags = os.environ.get("USE", "")
        use_flags += " -cros-debug"
        env["USE"] = use_flags

    features_flags = os.environ.get("FEATURES", "")
    if features_flags:
        env["FEATURES"] = features_flags

    keep_going = get_keep_going()

    metrics_dir = os.environ.get(constants.CROS_METRICS_DIR_ENVVAR)
    if metrics_dir:
        env[constants.CROS_METRICS_DIR_ENVVAR] = metrics_dir

    if opts.empty_sysroot:
        try:
            chroot_util.Emerge(
                list(IMPLICIT_TEST_DEPS),
                sysroot,
                rebuild_deps=False,
                use_binary=False,
            )
            chroot_util.Emerge(
                list(pkg_with_test),
                sysroot,
                rebuild_deps=False,
                use_binary=False,
            )
        except cros_build_lib.RunCommandError:
            logging.error("Failed building dependencies for unittests.")
            span.set_status(trace.StatusCode.ERROR, "FAILED_DEPS_BUILD")
            return 1

    try:
        chroot_util.RunUnittests(
            sysroot,
            pkg_with_test,
            extra_env=env,
            keep_going=keep_going,
            jobs=opts.jobs,
            verbose=opts.emerge_verbose,
        )
    except cros_build_lib.RunCommandError:
        logging.error("Unittests failed.")
        span.set_status(trace.StatusCode.ERROR, "FAILED_UNITTESTS")
        return 1
