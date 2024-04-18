# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Deps analysis service."""

import functools
import itertools
import os
from pathlib import Path
from typing import (
    Collection,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
    TYPE_CHECKING,
)

from chromite.lib import build_target_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import dependency_lib
from chromite.lib import portage_util
from chromite.scripts import cros_extract_deps


if cros_build_lib.IsInsideChroot():
    from chromite.lib import depgraph

if TYPE_CHECKING:
    from chromite.lib.dependency_graph import PackageNode
    from chromite.lib.parser.package_info import PackageInfo


class Error(Exception):
    """Base error class for the module."""


def GenerateSourcePathMapping(
    packages: List[str],
    sysroot_path: Optional[str] = None,
    board: Optional[str] = None,
    sdk: bool = False,
) -> Mapping[str, List[str]]:
    """Returns a map from each package to the source paths it depends on.

    A source path is considered dependency of a package if modifying files in
    that path might change the content of the resulting package.

    Notes:
        1) This method errs on the side of returning unneeded dependent paths.
            i.e: for a given package X, some of its dependency source paths may
            contain files which doesn't affect the content of X.

            On the other hand, any missing dependency source paths for package
            X is considered a bug.
        2) This only outputs the direct dependency source paths for a given
            package and does not takes include the dependency source paths of
            dependency packages.
            e.g: if package A depends on B (DEPEND=B), then results of computing
            dependency source paths of A doesn't include dependency source paths
            of B.

    Args:
        packages: The list of packages CPV names (str)
        sysroot_path: The path to the sysroot. Optional if |board| set and using
            default sysroot. If the packages are board agnostic, you can set
            |sdk| instead. Must not be set when using |sdk|.
        board: The name of the board. Optional if |sysroot| is set and in the
            default location. If the packages are board agnostic, you can set
            |sdk| instead. Must not be set when using |sdk|.
        sdk: Use the SDK's overlays instead of a board's overlays to find
            packages. This is effectively the set of shared, public overlays.

    Returns:
        Map from each package to the source path (relative to the repo checkout
        root, i.e: ~/chromiumos/ in your cros_sdk) it depends on.
        For each source path which is a directory, the string is ended with a
        trailing '/'.
    """
    assert not sdk or (
        board is None and sysroot_path is None
    ), "Cannot specify |board| or |sysroot_path| when setting |sdk|."

    if sdk:
        # Use the SDK info.
        sysroot_path = build_target_lib.get_sdk_sysroot_path()
    elif not sysroot_path:
        # Get the default sysroot for the board.
        sysroot_path = build_target_lib.get_default_sysroot_path(board)
    elif (
        sysroot_path
        and not board
        and sysroot_path != build_target_lib.get_sdk_sysroot_path()
    ):
        # Get the board name from the sysroot path unless it's the SDK's
        # sysroot.
        board = os.path.basename(sysroot_path)

    # We should definitely have a sysroot at this point.
    assert sysroot_path
    return dependency_lib.get_source_path_mapping(packages, sysroot_path, board)


# TODO(b/187794810): Update this type annotation to use TypedDict once we have
#                    Python 3.8 or newer.


@functools.lru_cache()
def GetBuildDependency(
    sysroot_path: Optional[str],
    board: Optional[str] = None,
    packages: Optional[Collection["PackageInfo"]] = None,
) -> Tuple[dict, dict]:
    """Return the build dependency and package -> source path map for |board|.

    Args:
        sysroot_path: The path to the sysroot, or None if no sysroot is being
            used.
        board: The name of the board whose artifacts are being created, or None
            if no sysroot is being used.
        packages: The packages that need to be built, or empty / None to use the
            default list.

    Returns:
        JSON build dependencies report for the given board which includes:
            - Package level deps graph from portage
            - Map from each package to the source path
            (relative to the repo checkout root, i.e: ~/chromiumos/ in your
            cros_sdk) it depends on
    """
    if not sysroot_path:
        sysroot_path = build_target_lib.get_default_sysroot_path(board)

    results = {
        "sysroot_path": sysroot_path,
        "target_board": board,
        "package_deps": {},
        "source_path_mapping": {},
    }

    sdk_sysroot = build_target_lib.get_sdk_sysroot_path()
    sdk_results = {
        "sysroot_path": sdk_sysroot,
        "target_board": "sdk",
        "package_deps": {},
        "source_path_mapping": {},
    }

    if sysroot_path != sdk_sysroot:
        board_packages = []
        if packages:
            board_packages.extend([pkg.cp for pkg in packages])
        else:
            board_packages.extend(
                [
                    constants.TARGET_OS_PKG,
                    constants.TARGET_OS_DEV_PKG,
                    constants.TARGET_OS_TEST_PKG,
                    constants.TARGET_OS_FACTORY_PKG,
                    constants.TARGET_OS_FACTORY_SHIM_PKG,
                ]
            )
            # Since we don’t have a clear mapping from autotests to git repos
            # and/or portage packages, we assume every board run all autotests.
            board_packages += ["chromeos-base/autotest-all"]

        board_deps, board_bdeps = cros_extract_deps.ExtractDeps(
            sysroot=sysroot_path,
            package_list=board_packages,
            include_bdepend=False,
            backtrack=False,
        )

        results["package_deps"].update(board_deps)
        results["package_deps"].update(board_bdeps)
        sdk_results["package_deps"].update(board_bdeps)

    indep_packages = [
        "virtual/target-sdk",
        "virtual/target-sdk-post-cross",
    ]

    indep_deps, _ = cros_extract_deps.ExtractDeps(
        sysroot=sdk_results["sysroot_path"], package_list=indep_packages
    )

    indep_map = GenerateSourcePathMapping(list(indep_deps), sdk=True)
    results["package_deps"].update(indep_deps)
    results["source_path_mapping"].update(indep_map)

    sdk_results["package_deps"].update(indep_deps)
    sdk_results["source_path_mapping"].update(indep_map)

    if sysroot_path != sdk_sysroot:
        bdep_map = GenerateSourcePathMapping(list(board_bdeps), sdk=True)
        board_map = GenerateSourcePathMapping(
            list(board_deps), sysroot_path, board
        )
        results["source_path_mapping"].update(bdep_map)
        results["source_path_mapping"].update(board_map)
        sdk_results["source_path_mapping"].update(bdep_map)

    return results, sdk_results


def determine_package_relevance(
    dep_src_paths: List[str], src_paths: Optional[List[str]] = None
) -> bool:
    """Determine if the package is relevant to the given source paths.

    A package is relevant if any of its dependent source paths is in the given
    list of source paths. If no source paths are given, the default is True.

    Args:
        dep_src_paths: List of source paths the package depends on.
        src_paths: List of source paths of interest.
    """
    if not src_paths:
        return True
    for src_path in (Path(x) for x in src_paths):
        for dep_src_path in (Path(x) for x in dep_src_paths):
            try:
                # Will throw an error if src_path isn't under dep_src_path.
                src_path.relative_to(dep_src_path)
                return True
            except ValueError:
                pass
    return False


def GetDependencies(
    sysroot_path: str,
    src_paths: Optional[Collection[str]] = None,
    packages: Optional[Collection[str]] = None,
    include_rev_dependencies: bool = False,
    include_affected_pkgs: bool = False,
) -> Set["PackageInfo"]:
    """Return the packages dependent on the given source paths for |board|.

    Args:
        sysroot_path: The path to the sysroot.
        src_paths: List of paths for which to get a list of dependent packages.
            If empty / None returns all package dependencies.
        packages: The packages that need to be built, or empty / None to use the
            default list.
        include_rev_dependencies: Whether to include the reverse dependencies of
            relevant packages.
        include_affected_pkgs: Whether to include packages that may be affected
            by changes to the given path/packages.

    Returns:
        The relevant package dependencies based on the given list of packages
        and src_paths.
    """
    cros_build_lib.AssertInsideChroot()
    dep_graph = depgraph.get_sysroot_dependency_graph(
        sysroot_path, packages, with_src_paths=True
    )

    if not src_paths:
        return set(x.pkg_info for x in dep_graph.get_nodes())

    dep_nodes = dep_graph.get_relevant_nodes(src_paths=src_paths)
    rev_dep_nodes: List["PackageNode"] = []
    affected_nodes = []
    for dep in dep_nodes:
        if include_rev_dependencies:
            rev_dep_nodes.extend(dep.reverse_dependencies)
        if include_affected_pkgs:
            # Include the revdeps affected by this package.
            affected_nodes.extend(dep.affected_dependencies)

    return set(x.pkg_info for x in dep_nodes + rev_dep_nodes + affected_nodes)


def DetermineToolchainSourcePaths() -> List[str]:
    """Returns a list of all source paths relevant to toolchain packages.

    A package is a 'toolchain package' if it is listed as a direct dependency
    of virtual/toolchain-packages. This function deliberately does not return
    deeper transitive dependencies so that only direct changes to toolchain
    packages trigger the expensive full re-compilation required to test
    toolchain changes. Eclasses & overlays are not returned as relevant paths
    for the same reason.

    Returned paths are relative to the root of the project checkout.

    Returns:
        A list of paths considered relevant to toolchain packages.
    """
    source_paths = set()
    toolchain_pkgs = portage_util.GetFlattenedDepsForPackage(
        "virtual/toolchain-packages", depth=1
    )
    mapping = dependency_lib.get_source_path_mapping(
        toolchain_pkgs,
        build_target_lib.get_sdk_sysroot_path(),
        None,
        include_eclass=False,
        include_overlay=False,
    )

    source_paths.update(itertools.chain.from_iterable(mapping.values()))

    return list(source_paths)
