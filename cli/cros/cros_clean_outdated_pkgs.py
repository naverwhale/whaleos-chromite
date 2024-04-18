# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""cros clean-outdated-pkgs purges outdated and unsatisfiable packages."""

import itertools
import logging
import multiprocessing
import os
from pathlib import Path
from typing import Dict, List, Optional, Set

from chromite.cli import command
from chromite.lib import build_target_lib
from chromite.lib import chromite_config
from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib.parser import package_info
from chromite.lib.parser import pms_dependency
from chromite.scripts import cros_setup_toolchains
from chromite.utils import pms


IGNORED_REPOSITORIES = frozenset(["crossdev", "toolchains"])

# TODO: better detect all packages that are part of "system profile" or are
# otherwise crucial, and must never be removed, like bash, portage or awk.
# Note that this list works by substring matching, so "dev-lang/python" also
# matches "dev-lang/python-exec-conf".
# This list only applies to SDK packages.
SYSTEM_PACKAGES = {
    # Do not delete sudo.
    "app-admin/sudo",
    # Compression utils/algos used by portage.
    "app-arch/",
    # CAs must be installed to establish a secure connection.
    "app-misc/ca-certificates",
    # ELF utils used by portage.
    "app-misc/pax-utils",
    # Do not delete eclean and friends.
    "app-portage/gentoolkit",
    # Do not delete shells.
    "app-shells/",
    # Packages listed in virtual/target-sdk-nobdeps aren't reinstalled.
    "dev-embedded/coreboot-sdk",
    "dev-embedded/ti50-sdk",
    # Python is required for our scripts.
    "dev-lang/python",
    # Basic crypto primitives used by python, curl, etc… to download binpkgs
    # from the network.
    "dev-libs/openssl",
    # Used by Python to parse XML files.
    "dev-libs/expat",
    # Used by curl.
    "net-libs/nghttp2",
    # Needed by compiler & friends (for math).
    "dev-libs/gmp",
    # Needed by compiler & friends (for math).
    "dev-libs/mpc",
    # Needed by compiler & friends (for math).
    "dev-libs/mpfr",
    # Needed by compiler (llvm).
    "dev-libs/libedit",
    # Needed by compiler (llvm).
    "dev-libs/libffi",
    # Used by libselinux which is used by a lot of system tools (e.g. tar &
    # coreutils).
    "dev-libs/libpcre2",
    # Needed by compiler (llvm).
    "dev-libs/libxml2",
    # Portage requires git to install packages.
    "dev-vcs/",
    # net-dns packages needed for DNS resolution.
    "net-dns/c-ares",
    "net-dns/libidn2",
    # net-misc includes SSH, curl, etc. Could potentially exclude less.
    "net-misc/",
    # sys-* categories are generally system-important. Could be potentially
    # broken down into individual packages.
    "sys-apps/",
    "sys-devel/",
    "sys-libs/",
    # Portage uses `ps`.
    "sys-process/procps",
    # Many CrOS packages use chromite-sdk but do not depend on it.
    "chromeos-base/chromite-sdk",
}
# pylint: disable=protected-access

PORTAGE_UTILS_VERSION = "0.96"


class OverlayPathFinder:
    """Finds an overlay of specific repository."""

    def __init__(self, board: str):
        list_of_overlay_paths = portage_util.FindOverlays("both", board)

        self.overlay_to_path = {}
        for overlay_path in list_of_overlay_paths:
            overlay_name = portage_util.GetOverlayName(overlay_path)
            self.overlay_to_path[overlay_name] = overlay_path

    def repo_to_path(self, repo: str) -> Path:
        """Returns Path to a given portage repository."""
        return self.overlay_to_path[repo]


def is_dep_satisfiable(dep: str, root_path: str, board: str) -> bool:
    """Returns True if 'dep' can be satisfied with available packages."""
    result = portage_util._Equery(
        "list",
        # -po to list packages in overlays and main portage tree.
        "-po",
        dep,
        sysroot=root_path,
        board=board,
        check=False,
    )
    return result.returncode == 0


@command.command_decorator("clean-outdated-pkgs")
class CleanOutdatedCommand(command.CliCommand):
    """Runs various portage-related functions."""

    @classmethod
    def ProcessOptions(cls, parser, options):
        """Post process options."""
        if options.auto is not None:
            return

        if not options.board and not options.host:
            parser.error("--host or --board=BOARD required")

    def find_outdated_packages(
        self, board: str, pkgs: List[portage_util.InstalledPackage]
    ) -> Set[str]:
        """Returns CPVs of installed packages that don't have an ebuild."""
        overlay_paths = OverlayPathFinder(board)
        outdated_CPs = []
        for pkg in pkgs:
            # We usually want to ignore toolchain packages.
            if not self.options.toolchain:
                if pkg.repository in IGNORED_REPOSITORIES:
                    continue
                if (
                    pkg.package_info.cp in cros_setup_toolchains.HOST_PACKAGES
                    or pkg.package_info.cp
                    in cros_setup_toolchains.HOST_POST_CROSS_PACKAGES
                ):
                    continue

            # Find the folder with ebuilds.

            try:
                path_to_overlay = Path(
                    overlay_paths.repo_to_path(pkg.repository)
                )
            except KeyError:
                logging.debug(
                    "Cannot find overlay %s. Deleting package %s/%s.",
                    pkg.repository,
                    pkg.category,
                    pkg.package,
                )
                outdated_CPs.append(pkg.package_info.cpf)
                continue
            package_src_path = path_to_overlay / pkg.category / pkg.package

            versions_available_as_ebuild = []
            ebuild_paths = []
            # Enumerate all available ebuilds, if they still exist.
            if not package_src_path.is_dir():
                logging.debug(
                    "Cannot find package %s/%s in overlay %s. Deleting.",
                    pkg.category,
                    pkg.package,
                    pkg.repository,
                )
                installed_version = None
                outdated_CPs.append(pkg.package_info.cpf)
            else:
                ebuild_paths = list(portage_util.EBuild.List(package_src_path))
                installed_version = pkg.version
                for path in ebuild_paths:
                    cpv = "/".join(path.split(".ebuild")[0].split("/")[-2:])
                    p = package_info.parse(cpv)
                    versions_available_as_ebuild.append(p.vr)

            if (
                installed_version not in versions_available_as_ebuild
                or not versions_available_as_ebuild
            ):
                outdated_CPs.append(pkg.package_info.cpf)

        location = "SDK"
        if board:
            location = board
        logging.notice("Installed packages in %s: %s", location, len(pkgs))
        logging.notice(
            "Outdated packages in %s: %s", location, len(outdated_CPs)
        )
        logging.debug("Outdated packages in %s: %s", location, outdated_CPs)

        return list(set(outdated_CPs))

    def find_slot_conflicted_packages(
        self,
        root_path: os.PathLike,
        board: Optional[str],
        pkgs: List[portage_util.InstalledPackage],
    ) -> Set[str]:
        # Look at all InstalledPackages' DEPENDs with slots and find
        # unstatisfiable ones. We can look at all depends, but that is
        # slower, and should not be necessary, given that we just synced
        # the tree. The reason we're looking is the damned := operator,
        # that binds the packages to whatever slot dep had at build
        # time.
        def has_slot_dep(dep: str) -> bool:
            # Returns True if dep has a SLOT depenendcy that isn't "allow any".
            return ":" in dep and ":*" not in dep

        def remove_use_flags_from_deps(deps: List[str]) -> List[str]:
            # Removes USE flags from deps in list of deps.
            return [dep.split("[")[0] for dep in deps]

        def remove_slotless_deps(deps: List[str]) -> List[str]:
            # Removes slotless deps from the list.
            return [dep for dep in deps if has_slot_dep(dep)]

        def remove_negative_deps(deps: List[str]) -> List[str]:
            # Removes deps that start with '!' from the list.
            return [dep for dep in deps if not dep.startswith("!")]

        def flatten_deps(deps: List[str]) -> List[str]:
            # Flattens the list without splitting strings
            return itertools.chain.from_iterable(
                itertools.repeat(dep, 1) if isinstance(dep, str) else dep
                for dep in deps
            )

        # Assume all version-related deps are satisfied, which they should be,
        # if user rebased every repo after repo sync.

        # Collect slot dependencies of all packages to resolve them efficiently.
        all_slot_deps = set()
        for pkg in pkgs:
            # We usually want to ignore toolchain packages.
            if not self.options.toolchain:
                if pkg.repository in IGNORED_REPOSITORIES:
                    continue
                if (
                    pkg.package_info.cp in cros_setup_toolchains.HOST_PACKAGES
                    or pkg.package_info.cp
                    in cros_setup_toolchains.HOST_POST_CROSS_PACKAGES
                ):
                    continue
            # TODO: do I want RDEPEND, BDEPEND?
            depend = pkg._ReadField("DEPEND")
            if not depend:
                continue

            def anyof_reduce_gatherer(choices: List[str]) -> str:
                """Reduce func for dep parser to gather dependencies."""
                # If there is a slotless dep -> pick it, so it can be ignored
                # later.
                if not choices:
                    logging.fatal(
                        "anyof_reduce called on empty list: %s", choices
                    )
                    return None
                for choice in choices:
                    if not has_slot_dep(choice):
                        return choice

                # If all deps have slots -> return all of them, so they can be
                # processed.
                return tuple(choices)

            parsed_deps = pms_dependency.parse(depend).reduce(
                use_flags=None,
                anyof_reduce=anyof_reduce_gatherer,
                flatten_allof=True,
            )

            parsed_deps = flatten_deps(parsed_deps)

            parsed_deps = remove_negative_deps(parsed_deps)

            parsed_deps = remove_slotless_deps(parsed_deps)

            if not self.options.include_use:
                parsed_deps = remove_use_flags_from_deps(parsed_deps)

            all_slot_deps.update(parsed_deps)
        logging.debug("All relevant slot depdendencies: %s", all_slot_deps)

        # Determine if dependencies are satisfiable in parallel.
        slot_dep_sat: Dict[str, bool] = {}
        deps_list = list(all_slot_deps)
        with multiprocessing.Pool(processes=os.cpu_count()) as pool:
            args_list = []
            for dep in deps_list:
                args_list.append((dep, root_path, board))
            results = pool.starmap(is_dep_satisfiable, args_list)

        if len(results) != len(args_list):
            logging.fatal(
                "expected a result for each dep (%s total). got: %s",
                len(args_list),
                len(results),
            )

        for i, dep in enumerate(deps_list):
            slot_dep_sat[dep] = results[i]

        logging.debug(
            "Solutions of all relevant slot dependencies: %s", slot_dep_sat
        )

        # Now use the compiled slot_dep_sat to find packages that can't be
        # satisfied.
        def is_depend_slot_satisfiable(depend: str) -> bool:
            def anyof_reduce(choices: List[str]) -> str:
                """Reduce func for dep parser."""
                if not choices:
                    logging.fatal(
                        "anyof_reduce called on empty list: %s", choices
                    )
                    return None

                # Pick either a slotless dep, if available.
                for choice in choices:
                    if not has_slot_dep(choice):
                        return choice

                choices = remove_negative_deps(choices)

                if not self.options.include_use:
                    choices = remove_use_flags_from_deps(choices)

                # Pick a satisfiable dep.
                for choice in choices:
                    if slot_dep_sat[choice]:
                        return choice

                # If no deps are satisifable -> return first.
                return choices[0]

            parsed_deps = pms_dependency.parse(depend).reduce(
                use_flags=None, anyof_reduce=anyof_reduce, flatten_allof=True
            )
            parsed_deps = flatten_deps(parsed_deps)

            parsed_deps = remove_negative_deps(parsed_deps)

            parsed_deps = remove_slotless_deps(parsed_deps)

            if not self.options.include_use:
                parsed_deps = remove_use_flags_from_deps(parsed_deps)

            for dep in parsed_deps:
                if not slot_dep_sat[dep]:
                    return False
            return True

        conflicted_pkgs: List[str] = []
        for pkg in pkgs:
            # We usually want to ignore toolchain packages.
            if not self.options.toolchain:
                if pkg.repository in IGNORED_REPOSITORIES:
                    continue
                if (
                    pkg.package_info.cp in cros_setup_toolchains.HOST_PACKAGES
                    or pkg.package_info.cp
                    in cros_setup_toolchains.HOST_POST_CROSS_PACKAGES
                ):
                    continue

            depend = pkg._ReadField("DEPEND")
            if not depend:
                continue
            if not is_depend_slot_satisfiable(depend):
                logging.debug(
                    "Package %s unable to satisfy its DEPEND: %s",
                    pkg.package_info.cpf,
                    depend,
                )
                conflicted_pkgs.append(pkg.package_info.cpf)

        return list(set(conflicted_pkgs))

    def filter_packages_to_purge(
        self, board: Optional[str], pkgs: Set[str]
    ) -> Set[str]:
        if not board:
            # Only filter system packages for SDK.
            pkgs_before = len(pkgs)
            for ignored_pkg in SYSTEM_PACKAGES:
                pkgs = [pkg for pkg in pkgs if ignored_pkg not in pkg]
            pkgs_after = len(pkgs)
            if pkgs_before > pkgs_after:
                logging.notice(
                    "%s outdated system-critical packages were not deleted",
                    pkgs_before - pkgs_after,
                )

        if self.options.keep_chrome_packages:
            # Filter out Chrome packages, if asked, for both SDK and DUT.
            pkgs_before = len(pkgs)
            for chrome_pkg in constants.ALL_CHROME_PACKAGES:
                pkgs = [pkg for pkg in pkgs if chrome_pkg not in pkg]

            pkgs_after = len(pkgs)
            if pkgs_before > pkgs_after:
                logging.notice(
                    "%s outdated Chrome packages were not deleted",
                    pkgs_before - pkgs_after,
                )
        return pkgs

    def purge_packages(self, board: Optional[str], pkgs: Set[str]):
        if not pkgs:
            logging.notice("No packages to purge")
            return

        unmerge_cmd = [
            cros_build_lib.GetSysrootToolPath(
                build_target_lib.get_default_sysroot_path(board), "qmerge"
            ),
            "--unmerge",
            "--quiet",
        ]

        if not self.options.ask:
            unmerge_cmd += ["--yes"]

        pkgs = [f"={pkg}" for pkg in pkgs]
        unmerge_cmd += pkgs

        try:
            cros_build_lib.sudo_run(unmerge_cmd)
        except cros_build_lib.RunCommandError as e:
            cros_build_lib.Die(e)

    def ensure_pkg_min_version(
        self,
        portage_db: portage_util.PortageDB,
        pkg_cp: str,
        min_version: str,
    ):
        """Upgrade |pkg_cp| to |min_version|; exit the program if failed."""

        def pkg_is_at_min_version():
            for pkg in portage_db.InstalledPackages():
                if pkg.package_info.cp == pkg_cp:
                    if pms.version_ge(pkg.package_info.version, min_version):
                        return True
            return False

        if pkg_is_at_min_version():
            return

        upgrade_pkg_cmd = [
            "emerge",
            "--update",
            "--quiet",
            f">={pkg_cp}-{min_version}",
        ]
        try:
            cros_build_lib.sudo_run(upgrade_pkg_cmd)
        except cros_build_lib.RunCommandError:
            cros_build_lib.Die(
                "Failed to upgrade %s to version >= %s. Try `repo sync`.",
                pkg_cp,
                min_version,
            )

        if pkg_is_at_min_version():
            return

        cros_build_lib.Die(
            "Failed to upgrade %s to version >= %s. Try `repo sync`.",
            pkg_cp,
            min_version,
        )

    def ensure_portage_utils_version(self, ver: str):
        """Ensure portage-utils version |ver| is installed."""
        self.ensure_pkg_min_version(
            portage_util.PortageDB(
                build_target_lib.get_default_sysroot_path(None)
            ),
            "app-portage/portage-utils",
            ver,
        )

    def control_automatic(self, enable_automation: bool) -> None:
        # Since this config will be used by a shell and a python script,
        # use a presence/absence of a file to control.
        if enable_automation:
            osutils.SafeUnlink(chromite_config.AUTO_COP_CONFIG_OFF, sudo=True)
            logging.debug("Clearing %s", chromite_config.AUTO_COP_CONFIG_OFF)
            logging.notice(
                "From now on, clean-outdated-pkgs will be run "
                "automatically during update_chroot and build_packages."
            )
        else:
            chromite_config.initialize()
            chromite_config.AUTO_COP_CONFIG_OFF.touch()
            logging.debug("Creating %s", chromite_config.AUTO_COP_CONFIG_OFF)
            logging.notice(
                "From now on, clean-outdated-pkgs will NOT be run "
                "automatically during update_chroot and build_packages."
            )

    def Run(self):
        """Perform the command."""
        commandline.RunInsideChroot(self)

        if self.options.auto is not None:
            self.control_automatic(self.options.auto)
            return

        # Require qmerge from app-portage/portage-utils of min version.
        self.ensure_portage_utils_version(PORTAGE_UTILS_VERSION)

        if self.options.host:
            root_path = build_target_lib.get_default_sysroot_path(None)
            db = portage_util.PortageDB(root_path)

            outdated_pkgs = self.find_outdated_packages(
                None, db.InstalledPackages()
            )
            outdated_pkgs = self.filter_packages_to_purge(None, outdated_pkgs)
            if outdated_pkgs:
                self.purge_packages(board=None, pkgs=outdated_pkgs)
                # Reinstall portage-utils in case it was removed.
                self.ensure_portage_utils_version(PORTAGE_UTILS_VERSION)

            if outdated_pkgs or self.options.force_slot_fix:
                logging.notice("Looking for unsatisfiable packages.")
                slot_conflict_pkgs = self.find_slot_conflicted_packages(
                    root_path, None, db.InstalledPackages()
                )
                slot_conflict_pkgs = self.filter_packages_to_purge(
                    None, slot_conflict_pkgs
                )
                if slot_conflict_pkgs:
                    logging.notice(
                        "Packages with slot conflict in SDK: %s",
                        len(slot_conflict_pkgs),
                    )
                    self.purge_packages(board=None, pkgs=slot_conflict_pkgs)
                    # Reinstall portage-utils in case it was removed.
                    self.ensure_portage_utils_version(PORTAGE_UTILS_VERSION)

        if self.options.board:
            root_path = build_target_lib.get_default_sysroot_path(
                self.options.board
            )
            db = portage_util.PortageDB(root_path)

            outdated_pkgs = self.find_outdated_packages(
                self.options.board, db.InstalledPackages()
            )
            outdated_pkgs = self.filter_packages_to_purge(
                self.options.board, outdated_pkgs
            )
            if outdated_pkgs:
                self.purge_packages(
                    board=self.options.board, pkgs=outdated_pkgs
                )

            if outdated_pkgs or self.options.force_slot_fix:
                logging.notice("Looking for unsatisfiable packages.")
                slot_conflict_pkgs = self.find_slot_conflicted_packages(
                    root_path, self.options.board, db.InstalledPackages()
                )
                slot_conflict_pkgs = self.filter_packages_to_purge(
                    self.options.board, slot_conflict_pkgs
                )
                if slot_conflict_pkgs:
                    logging.notice(
                        "Packages with slot conflict in %s: %s",
                        self.options.board,
                        len(slot_conflict_pkgs),
                    )
                    self.purge_packages(
                        board=self.options.board, pkgs=slot_conflict_pkgs
                    )

    @classmethod
    def AddParser(cls, parser: commandline.ArgumentParser):
        """Add parser arguments."""
        super().AddParser(parser)

        parser.add_argument(
            "-b", "--board", "--build-target", default=None, help="Board name."
        )
        auto_parser = parser.add_mutually_exclusive_group(required=False)
        auto_parser.add_argument(
            "--auto", dest="auto", default=None, action="store_true"
        )
        auto_parser.add_argument("--no-auto", dest="auto", action="store_false")

        parser.add_argument(
            "--host",
            default=False,
            action="store_true",
            help="Whether to sync host packages.",
        )
        parser.add_argument(
            "--toolchain",
            default=False,
            action="store_true",
            help="Whether to sync toolchain packages to ebuilds.",
        )
        parser.add_argument(
            "--ask",
            default=False,
            action="store_true",
            help="Ask for confirmation before deleting packages.",
        )
        parser.add_argument(
            "--force-slot-fix",
            default=False,
            action="store_true",
            help="""
        Forces slot conflict fix, which usually runs automatically when
        necessary. You might need to use this if you Ctrl+C\'d the script.
        """,
        )
        parser.add_argument(
            "--keep-chrome-packages",
            default=False,
            action="store_true",
            help="""
        Forbids purging of chrome packages.
        """,
        )
        parser.add_argument(
            "--include-use",
            default=False,
            action="store_true",
            help="""
        Purge packages with incompatible USE flag dependencies.
        """,
        )  # TODO: should this flag only apply to DUT?
        parser.epilog = """
cros clean-outdated-pkgs purges packages that do not have an ebuild with the
same version, then fixes slot conflicts.
Subsequent build_packages will reinstall these packages without conflicts.

WARNING: outdated packages that were emerged manually will be permanently
removed.
"""
