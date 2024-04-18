# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Check whether a package links libraries not in RDEPEND.

If no argument is provided it will check all installed packages. It takes the
BOARD environment variable into account.

Example:
    package_has_missing_deps.py --board=amd64-generic --match \
        chromeos-base/cryptohome
"""

from __future__ import annotations

import argparse
import collections
import enum
import logging
import os
from pathlib import Path
import pprint
import re
import sys
from typing import (
    Generic,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Set,
    TypeVar,
    Union,
)

from chromite.lib import build_target_lib
from chromite.lib import chroot_lib
from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import portage_util
from chromite.lib.parser import package_info
from chromite.utils import pformat


VIRTUALS = {
    "virtual/acl": ("sys-apps/acl", "media-libs/img-ddk-bin"),
    "virtual/arc-opengles": (
        "media-libs/arc-img-ddk",
        "media-libs/arc-mesa-img",
        "media-libs/arc-mali-drivers",
        "media-libs/arc-mali-drivers-bifrost",
        "media-libs/arc-mali-drivers-bifrost-bin",
        "media-libs/arc-mali-drivers-valhall",
        "media-libs/arc-mali-drivers-valhall-bin",
        "media-libs/arc-mesa",
        "media-libs/arc-mesa-amd",
        "media-libs/arc-mesa-freedreno",
        "media-libs/arc-mesa-iris",
        "media-libs/arc-mesa-virgl",
        "x11-drivers/opengles-headers",
    ),
    "virtual/cros-camera-hal": (
        "media-libs/cros-camera-hal-intel-ipu3",
        "media-libs/cros-camera-hal-intel-ipu6",
        "media-libs/cros-camera-hal-mtk",
        "media-libs/cros-camera-hal-qti",
        "media-libs/cros-camera-hal-rockchip-isp1",
        "media-libs/cros-camera-hal-usb",
        "media-libs/qti-7c-camera-tuning",
    ),
    "virtual/img-ddk": ("media-libs/img-ddk", "media-libs/img-ddk-bin"),
    "virtual/jpeg": ("media-libs/libjpeg-turbo", "media-libs/jpeg"),
    "virtual/krb5": ("app-crypt/mit-krb5", "app-crypt/heimdal"),
    "virtual/libcrypt": ("sys-libs/libxcrypt",),
    "virtual/libelf": ("dev-libs/elfutils", "sys-freebsd/freebsd-lib"),
    "virtual/libiconv": ("dev-libs/libiconv",),
    "virtual/libintl": ("dev-libs/libintl",),
    "virtual/libgudev": (
        "dev-libs/libgudev",
        "sys-apps/systemd",
        "sys-fs/eudev",
        "sys-fs/udev",
    ),
    "virtual/libudev": (
        "sys-apps/systemd-utils",
        "sys-fs/udev",
        "sys-fs/eudev",
        "sys-apps/systemd",
    ),
    "virtual/libusb": ("dev-libs/libusb", "sys-freebsd/freebsd-lib"),
    "virtual/opengles": (
        "media-libs/img-ddk",
        "media-libs/img-ddk-bin",
        "media-libs/libglvnd",
        "media-libs/mali-drivers-bin",
        "media-libs/mali-drivers-bifrost",
        "media-libs/mali-drivers-bifrost-bin",
        "media-libs/mali-drivers-valhall",
        "media-libs/mali-drivers-valhall-bin",
        "media-libs/mesa",
        "media-libs/mesa-amd",
        "media-libs/mesa-freedreno",
        "media-libs/mesa-iris",
        "media-libs/mesa-llvmpipe",
        "media-libs/mesa-panfrost",
        "media-libs/mesa-reven",
        "x11-drivers/opengles-headers",
    ),
    "virtual/vulkan-icd": (
        "media-libs/img-ddk",
        "media-libs/img-ddk-bin",
        "media-libs/mali-drivers-bifrost",
        "media-libs/mali-drivers-bifrost-bin",
        "media-libs/mali-drivers-valhall",
        "media-libs/mali-drivers-valhall-bin",
        "media-libs/mesa",
        "media-libs/mesa-freedreno",
        "media-libs/mesa-iris",
        "media-libs/mesa-llvmpipe",
        "media-libs/mesa-radv",
        "media-libs/vulkan-loader",
    ),
}


class OutputFormat(enum.Enum):
    """Type for the requested output format."""

    # Automatically determine the format based on what the user might want.
    # This is PRETTY if attached to a terminal, RAW otherwise.
    AUTO = enum.auto()
    AUTOMATIC = AUTO
    # Output packages one per line, suitable for mild scripting.
    RAW = enum.auto()
    # Suitable for viewing in a color terminal.
    PRETTY = enum.auto()


T = TypeVar("T")


class ResultSet(Generic[T], NamedTuple):
    """Represent separate but related sets for the build target and sdk."""

    target: Set[T]
    sdk: Set[T]


class MissingDependencyDetails(NamedTuple):
    """Information about a package with missing dependencies."""

    package: str
    unsatisfied_libs: List[str]
    unsatisfied_sdk_libs: List[str]
    depend: List[str]
    bdepend: List[str]


def is_sdk_path(path: str) -> bool:
    """Match paths for files built for the SDK/builder."""
    return bool(
        re.match(
            "|".join(
                (
                    r"/usr/src/chromeos-kernel-[^/]+/build",
                    r"/build/bin",
                    r"/build/libexec",
                )
            ),
            path,
        )
    )


def is_guest_os_path(path: str) -> bool:
    """Match paths belonging to a guest OS."""
    return bool(
        re.match(
            r"/opt/google/(?:vms|containers)",
            path,
        )
    )


class DotSoResolver:
    """Provides shared library related dependency operations."""

    def __init__(
        self,
        board: Optional[str] = None,
        root: Union[os.PathLike, str] = "/",
        chroot: Optional[chroot_lib.Chroot] = None,
    ):
        self.board = board
        self.chroot = chroot if chroot else chroot_lib.Chroot()

        self.sdk_db = portage_util.PortageDB()
        self._sdk_db_packges = None
        self.db = self.sdk_db if root == "/" else portage_util.PortageDB(root)
        self._db_packges = None
        self.provided_libs_cache = {}

        # Lazy initialize since it might not be needed.
        self.lib_to_package_map = None
        self.sdk_lib_to_package_map = None

    @property
    def sdk_db_packages(self):
        """Cache sdk_db.InstalledPackages().

        We won't be modifying it, so it's safe for us to reuse the results.
        """
        if self._sdk_db_packges is None:
            self._sdk_db_packges = self.sdk_db.InstalledPackages()
        return self._sdk_db_packges

    @property
    def db_packages(self):
        """Cache db.InstalledPackages().

        We won't be modifying it, so it's safe for us to reuse the results.
        """
        if self._db_packges is None:
            self._db_packges = self.db.InstalledPackages()
        return self._db_packges

    def get_packages(
        self, query: str, from_sdk=False
    ) -> Iterable[portage_util.InstalledPackage]:
        """Find matching InstalledPackage(s) for the |query|."""
        packages = self.sdk_db_packages if from_sdk else self.db_packages
        info = package_info.parse(query)
        for package in packages:
            if info.package != package.package:
                continue
            if info.category != package.category:
                continue
            dep_info = package.package_info
            if info.revision and info.revision != dep_info.revision:
                continue
            if info.pv and info.pv != dep_info.pv:
                continue
            logging.debug("query: %s: matched %s", query, dep_info.cpvr)
            yield package

    # TODO Re-enable the lint after we upgrade to Python 3.9 or later.
    # pylint: disable-next=unsubscriptable-object
    def get_required_libs(self, package) -> ResultSet[str]:
        """Return sets of required .so files for the target and the SDK."""
        sdk = set()
        target = set()
        needed = package.needed
        if needed is not None:
            for file, libs in needed.items():
                if is_sdk_path(file):
                    sdk.update(libs)
                elif not is_guest_os_path(file):
                    target.update(libs)
        return ResultSet(target, sdk)

    # TODO Re-enable the lint after we upgrade to Python 3.9 or later.
    # pylint: disable-next=unsubscriptable-object
    def get_deps(
        self, package: portage_util.InstalledPackage
    ) -> ResultSet[portage_util.InstalledPackage]:
        """Returns two lists of dependencies.

        This expands the virtuals listed in VIRTUALS.
        """
        cpvr = f"{package.category}/{package.pf}"

        # Handling ||() nodes is difficult.  Be lazy and expand all of them.
        # We could compare against the installed db to try and find a match,
        # but this seems easiest for now as our PortageDB API doesn't support
        # these kind of primitives yet.
        def _anyof_reduce(choices: List[str]) -> str:
            """Reduce ||() nodes."""

            def _flatten(eles):
                for e in eles:
                    if isinstance(e, tuple):
                        yield from _flatten(e)
                    else:
                        yield e

            citer = _flatten(choices)
            ret = next(citer)
            package_dependencies.extend(citer)
            return ret

        package_dependencies = []
        package_dependencies.extend(
            package.depend.reduce(anyof_reduce=_anyof_reduce)
        )
        package_dependencies.extend(
            package.rdepend.reduce(anyof_reduce=_anyof_reduce)
        )
        package_build_dependencies = []
        package_build_dependencies.extend(
            package.bdepend.reduce(anyof_reduce=_anyof_reduce)
        )

        def _clean_deps(raw_deps: List[str], from_sdk=False) -> Set[str]:
            deps = set()
            expanded = []
            for fulldep in raw_deps:
                # Preclean the atom.  We can only handle basic forms like
                # CATEGORY/PF, not the full dependency specification.  See the
                # ebuild(5) man page for more details.
                dep = fulldep

                # Ignore blockers.
                if dep.startswith("!"):
                    logging.debug("%s: ignoring blocker: %s", cpvr, dep)
                    continue

                # Rip off the SLOT spec.
                dep = dep.split(":", 1)[0]
                # Rip off any USE flag constraints.
                dep = dep.split("[", 1)[0]
                # Trim leading & trailing version ranges.
                dep = dep.lstrip("<>=~").rstrip("*")

                logging.debug(
                    "%s: found package dependency: %s -> %s", cpvr, fulldep, dep
                )

                info = package_info.parse(dep)
                if not info:
                    continue

                cp = info.cp
                if cp in VIRTUALS:
                    expanded += VIRTUALS[cp]
                    continue

                pkgs = (
                    self.sdk_db if from_sdk else self.db
                ).GetInstalledPackage(info.category, info.pvr)
                if not pkgs:
                    pkgs = list(self.get_packages(info.atom, from_sdk))
                else:
                    pkgs = [pkgs]

                if pkgs:
                    deps.update(pkgs)
                else:
                    logging.warning(
                        "%s: could not find installed %s", cpvr, dep
                    )

            for dep in expanded:
                deps.update(self.get_packages(dep))

            return deps

        return ResultSet(
            target=_clean_deps(package_dependencies),
            sdk=_clean_deps(package_build_dependencies, from_sdk=True),
        )

    def get_implicit_libs(self):
        """Return a set of .so files that are provided by the system."""
        # libstdc++ comes from the toolchain so always ignore it.
        implicit_libs = {"libstdc++.so", "libstdc++.so.6"}
        for dep, from_sdk in (
            ("cross-aarch64-cros-linux-gnu/glibc", True),
            ("cross-armv7a-cros-linux-gnueabihf/glibc", True),
            ("cross-i686-cros-linux-gnu/glibc", True),
            ("cross-x86_64-cros-linux-gnu/glibc", True),
            ("sys-libs/glibc", False),
            ("sys-libs/libcxx", False),
            ("sys-libs/llvm-libunwind", False),
        ):
            for pkg in self.get_packages(dep, from_sdk):
                implicit_libs.update(self.provided_libs(pkg))
        return implicit_libs

    def provided_libs(self, package: portage_util.InstalledPackage) -> Set[str]:
        """Return a set of .so files provided by |package|."""
        cpvr = f"{package.category}/{package.pf}"
        if cpvr in self.provided_libs_cache:
            return self.provided_libs_cache[cpvr]

        libs = set()
        contents = package.ListContents()
        # Keep only the .so files
        for typ, path in contents:
            if typ == package.DIR:
                continue
            filename = os.path.basename(path)
            if filename.endswith(".so") or (
                ".so." in filename and not filename.endswith(".debug")
            ):
                libs.add(filename)
        self.provided_libs_cache[cpvr] = libs
        return libs

    def cache_libs_from_build(
        self, package: portage_util.InstalledPackage, image_dir: Path
    ):
        """Populate the provided_libs_cache for the package from the image dir.

        When using build-info, CONTENTS might not be available yet. so provide
        alternative using the destination directory of the ebuild.
        """

        cpvr = f"{package.category}/{package.pf}"
        libs = set()
        for _, _, files in os.walk(image_dir):
            for file in files:
                if file.endswith(".so") or (
                    ".so." in file and not file.endswith(".debug")
                ):
                    libs.add(os.path.basename(file))
        self.provided_libs_cache[cpvr] = libs

    # TODO Re-enable the lint after we upgrade to Python 3.9 or later.
    # pylint: disable-next=unsubscriptable-object
    def get_provided_from_all_deps(
        self, package: portage_util.InstalledPackage
    ) -> ResultSet[str]:
        """Return sets of .so files provided by the immediate dependencies."""

        def _expand_to_libs(
            packages: Set[portage_util.InstalledPackage],
        ) -> Set[str]:
            provided_libs = set()
            # |package| may not actually be installed yet so manually add it too
            # since a package can depend on its own libs.
            provided_libs.update(self.provided_libs(package))
            for pkg in packages:
                logging.debug(
                    "%s: loading libs from dependency %s",
                    package.package_info.cpvr,
                    pkg.package_info.cpvr,
                )
                provided_libs.update(self.provided_libs(pkg))
            return provided_libs

        deps, sdk_deps = self.get_deps(package)
        return ResultSet(
            target=_expand_to_libs(deps), sdk=_expand_to_libs(sdk_deps)
        )

    def lib_to_package(
        self, lib_filename: str = None, from_sdk=False
    ) -> Set[str]:
        """Return a set of packages that contain the library."""
        lookup = (
            self.sdk_lib_to_package_map if from_sdk else self.lib_to_package_map
        )
        if lookup is None:
            lookup = collections.defaultdict(set)
            for pkg in (
                self.sdk_db.InstalledPackages()
                if from_sdk
                else self.db.InstalledPackages()
            ):
                cpvr = f"{pkg.category}/{pkg.pf}"
                # Packages with bundled libs for internal use and/or standaline
                # binary packages.
                if f"{pkg.category}/{pkg.package}" in (
                    "app-emulation/qemu",
                    "chromeos-base/aosp-frameworks-ml-nn-vts",
                    "chromeos-base/factory",
                    "chromeos-base/signingtools-bin",
                    "sys-devel/gcc-bin",
                ):
                    continue
                for lib in set(self.provided_libs(pkg)):
                    lookup[lib].add(cpvr)
            if self.board is None:
                self.sdk_lib_to_package_map = lookup
                self.lib_to_package_map = lookup
            elif from_sdk:
                self.sdk_lib_to_package_map = lookup
            else:
                self.lib_to_package_map = lookup

        if not lib_filename:
            return set()
        try:
            return lookup[lib_filename]
        except KeyError:
            return set()


def get_parser() -> commandline.ArgumentParser:
    """Build the argument parser."""
    parser = commandline.ArgumentParser(description=__doc__)

    parser.add_argument("package", nargs="*", help="package atom")

    parser.add_argument(
        "-b",
        "--board",
        "--build-target",
        default=cros_build_lib.GetDefaultBoard(),
        help="ChromeOS board (Uses the SDK if not specified)",
    )

    parser.add_argument(
        "--no-default-board",
        dest="board",
        const=None,
        action="store_const",
        help="Ignore the default board",
    )

    parser.add_argument(
        "-i",
        "--build-info",
        default=None,
        type=Path,
        help="Path to build-info folder post src_install",
    )

    parser.add_argument(
        "-x",
        "--image",
        default=None,
        type=Path,
        help="Path to image folder post src_install (${D} if unspecified)",
    )

    parser.add_argument(
        "--match",
        default=False,
        action="store_true",
        help="Try to match missing libraries",
    )

    parser.add_argument(
        "-j",
        "--jobs",
        default=None,
        type=int,
        help="Number of parallel processes",
    )

    parser.set_defaults(format=OutputFormat.AUTO)
    parser.add_argument(
        "--format",
        action="enum",
        enum=OutputFormat,
        help="Output format to use.",
    )

    return parser


def parse_arguments(argv: List[str]) -> argparse.Namespace:
    """Parse and validate arguments."""
    parser = get_parser()
    opts = parser.parse_args(argv)
    if opts.build_info and opts.package:
        parser.error("Do not specify a package when setting --board-info")
    if opts.image and not opts.build_info:
        parser.error("--image requires --board-info")
    if opts.build_info or len(opts.package) == 1:
        opts.jobs = 1
    if opts.format is OutputFormat.AUTO:
        if sys.stdout.isatty():
            opts.format = OutputFormat.PRETTY
        else:
            opts.format = OutputFormat.RAW
    return opts


def check_package(
    package: portage_util.InstalledPackage,
    implicit: Set[str],
    resolver: DotSoResolver,
    match: bool,
) -> Optional[MissingDependencyDetails]:
    """Returns false if the package has missing dependencies"""
    if not package:
        print("Package not installed")
        return None

    provided, sdk_provided = resolver.get_provided_from_all_deps(package)
    logging.debug("provided: %s", pprint.pformat(sorted(provided)))

    available = provided.union(implicit)
    sdk_available = sdk_provided.union(implicit)
    required, sdk_required = resolver.get_required_libs(package)
    logging.debug("required: %s", pprint.pformat(sorted(required)))
    unsatisfied = sorted(required - available)
    sdk_unsatisfied = sorted(sdk_required - sdk_available)
    details = {
        "package": package.package_info.cpvr,
        "unsatisfied_libs": unsatisfied,
        "unsatisfied_sdk_libs": sdk_unsatisfied,
        "depend": [],
        "bdepend": [],
    }
    if match:
        missing = set()
        for lib in unsatisfied:
            missing.update(resolver.lib_to_package(lib, from_sdk=False))
        details["depend"] = sorted(missing)

        missing = set()
        for lib in sdk_unsatisfied:
            missing.update(resolver.lib_to_package(lib, from_sdk=True))
        details["bdepend"] = sorted(missing)
    return (
        MissingDependencyDetails(**details)
        if unsatisfied or sdk_unsatisfied
        else None
    )


def pretty_print(details: MissingDependencyDetails):
    """Handle --format=pretty"""
    if details.unsatisfied_libs:
        print(
            f"'{details.package}': Package is linked against libraries that "
            "are not listed as dependencies in the ebuild:"
        )
        pprint.pprint(details.unsatisfied_libs)
    if details.depend:
        print(
            f"'{details.package}': needs the following added to DEPEND/RDEPEND:"
        )
        pprint.pprint(details.depend)
    if details.unsatisfied_sdk_libs:
        print(
            f"'{details.package}': Package is linked against sdk libraries "
            "that are not listed as build dependencies in the ebuild:"
        )
        pprint.pprint(details.unsatisfied_sdk_libs)
    if details.bdepend:
        print(f"'{details.package}': needs the following added to BDEPEND:")
        pprint.pprint(details.bdepend)


def raw_print(details: MissingDependencyDetails):
    """Handle --format=raw"""
    pformat.json(details._asdict(), fp=sys.stdout, compact=True)
    print()


def main(argv: Optional[List[str]]):
    """Main."""
    commandline.RunInsideChroot()
    opts = parse_arguments(argv)
    opts.Freeze()

    board = opts.board
    root = build_target_lib.get_default_sysroot_path(board)
    if board:
        os.environ["PORTAGE_CONFIGROOT"] = root
        os.environ["SYSROOT"] = root
        os.environ["ROOT"] = root

    failed = False
    resolver = DotSoResolver(board, root)

    if not opts.package:
        if opts.build_info:
            pkg = portage_util.InstalledPackage(resolver.db, opts.build_info)
            image_path = opts.image or os.environ.get("D")
            if image_path:
                resolver.cache_libs_from_build(pkg, Path(image_path))
            packages = [pkg]
        else:
            packages = resolver.db.InstalledPackages()
    else:
        packages = []
        for pkg in opts.package:
            packages.extend(resolver.get_packages(pkg))

    implicit = resolver.get_implicit_libs()

    if opts.match:
        # Pre initialize the map before starting jobs.
        resolver.lib_to_package()
    for package in packages:
        details = check_package(
            package,
            implicit,
            resolver,
            opts.match,
        )
        if details:
            failed = True
            if opts.format == OutputFormat.PRETTY:
                pretty_print(details)
            else:
                raw_print(details)

    if failed:
        if opts.format == OutputFormat.PRETTY:
            print(
                """\
For more information about DEPEND vs. RDEPEND in ebuilds see:
https://chromium.googlesource.com/chromiumos/docs/+/HEAD/portage/\
ebuild_faq.md#dependency-types"""
            )
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
