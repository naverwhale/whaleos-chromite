# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Logic to handle uprevving packages."""

import collections
import enum
import filecmp
import functools
import logging
import os
import re
from typing import (
    Collection,
    Iterable,
    List,
    Optional,
    Tuple,
    TYPE_CHECKING,
    Union,
)

from chromite.lib import chromeos_version
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import git
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib import portage_util
from chromite.utils import pms


if TYPE_CHECKING:
    import pathlib

    from chromite.lib import build_target_lib

CHROME_VERSION_REGEX = r"\d+\.\d+\.\d+\.\d+"

_CHROME_OVERLAY_PATH = os.path.join(
    constants.SOURCE_ROOT, constants.CHROMIUMOS_OVERLAY_DIR
)

GitRef = collections.namedtuple("GitRef", ["path", "ref", "revision"])

# An alias of constants.SOURCE_ROOT. Can be mocked in unit tests.
SRC_ROOT = constants.SOURCE_ROOT


class Error(Exception):
    """Base error class for the module."""


class UnstableEbuildNotWorkonError(Error):
    """When an unstable ebuild doesn't inherit cros-workon."""


class TooManyStableEbuildsError(Error):
    """When too many stable ebuilds are found."""


class EbuildUprevError(Error):
    """An error occurred while uprevving packages."""


class EbuildManifestError(Error):
    """Error when running ebuild manifest."""


class NoEbuildsError(Error, ValueError):
    """When no ebuilds are provided."""


class NoRefsError(Error, ValueError):
    """When no git refs are given to fetch a version from."""


class NoUnstableEbuildError(Error):
    """When no unstable ebuild can be found."""


class NoVersionsError(Error, ValueError):
    """When no versions are provided."""


class ChromeEBuild(portage_util.EBuild):
    """Thin subclass of EBuild that adds a few small helpers."""

    chrome_version_re = re.compile(r".*-(%s|9999).*" % CHROME_VERSION_REGEX)
    chrome_version = ""

    def __init__(self, path):
        portage_util.EBuild.__init__(self, path)
        re_match = self.chrome_version_re.match(self.ebuild_path_no_revision)
        if re_match:
            self.chrome_version = re_match.group(1)

    def __str__(self):
        return self.ebuild_path

    @property
    def is_unstable(self) -> bool:
        """Check if the Chrome ebuild is unstable."""
        return not self.is_stable


def get_version_from_refs(refs: List[GitRef]) -> str:
    """Get the version to use from the list of provided tags.

    Version strings are of format "78.0.3876.1".

    Args:
        refs: The tags to parse for the best version.

    Returns:
        str: The version to use.

    Raises:
        Exception: if no unstable ebuild exists for Chrome.
    """
    if not refs:
        raise NoRefsError("|refs| must not be empty.")

    # Each tag is a version string, e.g. "78.0.3876.1", so extract the
    # tag name from the ref, e.g. "refs/tags/78.0.3876.1".
    versions = [ref.ref.split("/")[-1] for ref in refs]
    return best_version(versions)


def best_version(versions: Collection[str]) -> str:
    """Find the best Chrome version."""
    # Convert each version from a string like "78.0.3876.1" to a list of ints
    # to compare them, find the most recent (max), and then reconstruct the
    # version string.
    if not versions:
        raise NoVersionsError("|versions| must not be empty.")

    version = max([int(part) for part in v.split(".")] for v in versions)
    return ".".join(str(part) for part in version)


def best_chrome_ebuild(ebuilds: List[ChromeEBuild]) -> ChromeEBuild:
    """Determine the best/newest chrome ebuild from a list of ebuilds."""
    if not ebuilds:
        raise NoEbuildsError("|ebuilds| must not be empty.")

    version = best_version([ebuild.chrome_version for ebuild in ebuilds])
    candidates = [
        ebuild for ebuild in ebuilds if ebuild.chrome_version == version
    ]

    if len(candidates) == 1:
        # Only one, return it.
        return candidates[0]

    # Compare revisions to break a tie.
    best = candidates[0]
    for candidate in candidates[1:]:
        if best.current_revision < candidate.current_revision:
            best = candidate

    return best


def get_stable_chrome_version() -> str:
    """Get the Chrome version from the latest, stable chrome ebuild."""
    return _get_best_stable_chrome_ebuild().chrome_version


def _get_best_stable_chrome_ebuild() -> ChromeEBuild:
    """Find the stable chrome ebuild with the highest version."""
    package_dir = os.path.join(_CHROME_OVERLAY_PATH, constants.CHROME_CP)
    _unstable_ebuild, stable_ebuilds = find_chrome_ebuilds(package_dir)
    return _get_best_stable_chrome_ebuild_from_ebuilds(stable_ebuilds)


def _get_best_stable_chrome_ebuild_from_ebuilds(
    stable_ebuilds: List[ChromeEBuild],
) -> Optional[ChromeEBuild]:
    """Get the highest versioned chrome ebuild from a list of stable ebuilds."""
    candidates = []
    # This is an artifact from the old process.
    chrome_branch_re = re.compile(r"%s.*_rc.*" % CHROME_VERSION_REGEX)
    for ebuild in stable_ebuilds:
        if chrome_branch_re.search(ebuild.version):
            candidates.append(ebuild)

    if not candidates:
        return None

    return best_chrome_ebuild(candidates)


def find_chrome_ebuilds(
    package_dir: str,
) -> Tuple[ChromeEBuild, List[ChromeEBuild]]:
    """Return a tuple of chrome's unstable ebuild and stable ebuilds.

    Args:
        package_dir: The path to where the package ebuild is stored.

    Returns:
        Tuple [unstable_ebuild, stable_ebuilds].

    Raises:
        Exception: if no unstable ebuild exists for Chrome.
    """
    stable_ebuilds = []
    unstable_ebuilds = []

    for ebuild_path in portage_util.EBuild.List(package_dir):
        ebuild = ChromeEBuild(ebuild_path)
        if not ebuild.chrome_version:
            logging.warning("Poorly formatted ebuild found at %s", ebuild_path)
            continue

        if ebuild.is_unstable:
            unstable_ebuilds.append(ebuild)
        else:
            stable_ebuilds.append(ebuild)

    # Apply some basic checks.
    if not unstable_ebuilds:
        raise NoUnstableEbuildError("Missing 9999 ebuild for %s" % package_dir)
    if not stable_ebuilds:
        logging.warning("Missing stable ebuild for %s", package_dir)

    return best_chrome_ebuild(unstable_ebuilds), stable_ebuilds


@enum.unique
class Outcome(enum.Enum):
    """An enum representing the possible outcomes of a package uprev attempt.

    Variants:
        NEWER_VERSION_EXISTS: An ebuild with a higher version than the requested
            version already exists, so no change occurred.
        SAME_VERSION_EXISTS: An ebuild with the same version as the requested
            version already exists and the stable & unstable ebuilds are
            identical, so no change occurred.
        REVISION_BUMP: An ebuild with the same version as the requested version
            already exists but the contents of the stable & unstable ebuilds
            differ, so the stable ebuild was updated and the revision number was
            increased.
        VERSION_BUMP: The requested uprev version was greater than that of any
            stable ebuild that exists, so a new stable ebuild was created at the
            requested version.
        NEW_EBUILD_CREATED: No stable ebuild for this package existed yet, so a
            new stable ebuild was created at the requested version.
    """

    NEWER_VERSION_EXISTS = enum.auto()
    SAME_VERSION_EXISTS = enum.auto()
    REVISION_BUMP = enum.auto()
    VERSION_BUMP = enum.auto()
    NEW_EBUILD_CREATED = enum.auto()


class UprevResult:
    """The result of a package uprev attempt.

    This object is truthy if files were altered by the uprev and falsey if no
    files were changed.

    Attributes:
        outcome: An instance of Outcome documenting what change took place.
        changed_files: A list of the paths of the files that were altered by
            this uprev attempt.
    """

    outcome: Outcome
    changed_files: List[str]

    def __init__(
        self, outcome: Outcome, changed_files: Optional[Iterable[str]] = None
    ):
        self.outcome = outcome

        if isinstance(changed_files, str):
            raise TypeError(
                "changed_files must be a list of str, not a bare str."
            )
        self.changed_files = list(changed_files or [])

    def __bool__(self):
        """Returns True if a file was modified (uprev or revbump)."""
        return (
            self.new_ebuild_created or self.revision_bump or self.version_bump
        )

    # Properties corresponding directly to a specific outcome check.
    @property
    def new_ebuild_created(self) -> bool:
        """True when the result was a new ebuild created."""
        return self.outcome is Outcome.NEW_EBUILD_CREATED

    @property
    def newer_version_exists(self) -> bool:
        """True when existing stable version is newer than the given version."""
        return self.outcome is Outcome.NEWER_VERSION_EXISTS

    @property
    def revision_bump(self) -> bool:
        """True when the result was a revbump."""
        return self.outcome is Outcome.REVISION_BUMP

    @property
    def same_version_exists(self) -> bool:
        """True when the prospective version already exists."""
        return self.outcome is Outcome.SAME_VERSION_EXISTS

    @property
    def version_bump(self) -> bool:
        """True when the result was a version bump."""
        return self.outcome is Outcome.VERSION_BUMP

    # Composite properties to simplify checks.
    @property
    def stable_version(self) -> bool:
        """True when the supplied and stable version matched."""
        return self.revision_bump or self.same_version_exists


class UprevChromeManager:
    """Class to handle uprevving chrome and its related packages."""

    def __init__(
        self,
        version: str,
        build_targets: List["build_target_lib.BuildTarget"] = None,
        overlay_dir: str = None,
        chroot: chroot_lib.Chroot = None,
    ):
        self._version = version
        self._build_targets = build_targets or []
        self._new_ebuild_files = []
        self._removed_ebuild_files = []
        self._overlay_dir = str(overlay_dir or _CHROME_OVERLAY_PATH)
        self._chroot = chroot

    @property
    def modified_ebuilds(self) -> List[str]:
        """The list of ebuilds modified during the uprev."""
        return self._new_ebuild_files + self._removed_ebuild_files

    def uprev(self, package: str) -> UprevResult:
        """Uprev a chrome package."""
        package_dir = os.path.join(self._overlay_dir, package)
        package_name = os.path.basename(package)

        # Find the unstable (9999) ebuild and any existing stable ebuilds.
        unstable_ebuild, stable_ebuilds = find_chrome_ebuilds(package_dir)
        # Find the best stable candidate to uprev -- the one that will be
        # replaced.
        should_uprev, candidate = self._find_chrome_uprev_candidate(
            stable_ebuilds
        )

        if not should_uprev and candidate:
            return UprevResult(Outcome.NEWER_VERSION_EXISTS)

        result = self._mark_as_stable(
            candidate, unstable_ebuild, package_name, package_dir
        )

        # If result is falsey then no files changed, and we don't need to do any
        # clean-up.
        if not result:
            return result

        self._new_ebuild_files.extend(result.changed_files)
        logging.debug(
            "Modified ebuild(s) for %s: %s", package, result.changed_files
        )
        if candidate and not candidate.IsSticky():
            osutils.SafeUnlink(candidate.ebuild_path)
            self._removed_ebuild_files.append(candidate.ebuild_path)

        return result

    def _find_chrome_uprev_candidate(
        self, stable_ebuilds: List[ChromeEBuild]
    ) -> Tuple[bool, Optional[ChromeEBuild]]:
        """Find the ebuild to replace.

        Args:
            stable_ebuilds: All stable ebuilds that were found.

        Returns:
            A (okay_to_uprev, best_stable_candidate) tuple.
            okay_to_uprev: A bool indicating that an uprev should proceed. False
                if a newer stable ebuild than the requested version exists.
            best_stable_candidate: The highest version stable ebuild that
                exists, or None if no stable ebuilds exist.
        """
        candidate = _get_best_stable_chrome_ebuild_from_ebuilds(stable_ebuilds)
        if not candidate:
            return True, None

        # A candidate is only a valid uprev candidate if its Chrome version
        # is no better than the target version. We can uprev equal versions
        # (i.e. a revision bump), but not older. E.g.:
        # Case 1 - Uprev: self._version = 78.0.0.0, Candidate = 77.0.0.0
        # Case 2 - Uprev: self._version = 78.0.0.0, Candidate = 78.0.0.0
        # Case 3 - Skip:  self._version = 78.0.0.0, Candidate = 79.0.0.0
        version = best_version([self._version, candidate.chrome_version])
        if self._version == version:
            # Cases 1 and 2.
            return (True, candidate)

        logging.warning(
            "A chrome ebuild candidate with a higher version than the "
            "requested uprev version was found."
        )
        logging.debug("Requested uprev version: %s", self._version)
        logging.debug("Candidate version found: %s", candidate.chrome_version)
        return (False, candidate)

    def _mark_as_stable(
        self,
        stable_candidate: Optional[ChromeEBuild],
        unstable_ebuild: ChromeEBuild,
        package_name: str,
        package_dir: str,
    ) -> UprevResult:
        """Uprevs the chrome ebuild specified by chrome_rev.

        This is the main function that uprevs the chrome_rev from a stable
        candidate to its new version.

        Args:
            stable_candidate: ebuild that corresponds to the stable ebuild we
                are revving from.  If None, builds a new ebuild given the
                version and logic for chrome_rev type with revision set to 1.
            unstable_ebuild: ebuild corresponding to the unstable ebuild for
                chrome.
            package_name: package name.
            package_dir: Path to the chromeos-chrome package dir.

        Returns:
            Full portage version atom (including rc's, etc) that was revved.
        """

        def _is_new_ebuild_redundant(
            uprevved_ebuild: ChromeEBuild, stable_ebuild: Optional[ChromeEBuild]
        ) -> bool:
            """Returns True if the new ebuild is redundant.

            This is True if the current stable ebuild is the exact same copy of
            the new one.
            """
            if (
                stable_ebuild
                and stable_candidate.chrome_version
                == uprevved_ebuild.chrome_version
            ):
                return filecmp.cmp(
                    uprevved_ebuild.ebuild_path,
                    stable_ebuild.ebuild_path,
                    shallow=False,
                )
            else:
                return False

        # Case where we have the last stable candidate with same version just
        # rev.
        if (
            stable_candidate
            and stable_candidate.chrome_version == self._version
        ):
            new_ebuild_path = "%s-r%d.ebuild" % (
                stable_candidate.ebuild_path_no_revision,
                stable_candidate.current_revision + 1,
            )
            rev_bump = True
        else:
            pf = "%s-%s_rc-r1" % (package_name, self._version)
            new_ebuild_path = os.path.join(package_dir, "%s.ebuild" % pf)
            rev_bump = False

        portage_util.EBuild.MarkAsStable(
            unstable_ebuild.ebuild_path, new_ebuild_path, {}
        )
        new_ebuild = ChromeEBuild(new_ebuild_path)

        # Determine whether this is ebuild is redundant.
        if _is_new_ebuild_redundant(new_ebuild, stable_candidate):
            msg = (
                "Previous ebuild with same version found and ebuild is "
                "redundant."
            )
            logging.info(msg)
            os.unlink(new_ebuild_path)
            return UprevResult(Outcome.SAME_VERSION_EXISTS)

        if rev_bump:
            return UprevResult(Outcome.REVISION_BUMP, [new_ebuild.ebuild_path])
        elif stable_candidate:
            # If a stable ebuild already existed and rev_bump is False, then a
            # stable ebuild with a new major version has been generated.
            return UprevResult(Outcome.VERSION_BUMP, [new_ebuild.ebuild_path])
        else:
            # If no stable ebuild existed, then we've created the first stable
            # ebuild for this package.
            return UprevResult(
                Outcome.NEW_EBUILD_CREATED, [new_ebuild.ebuild_path]
            )

    def _clean_stale_package(self, package):
        clean_stale_packages(
            [package], self._build_targets, chroot=self._chroot
        )


class UprevOverlayManager:
    """Class to handle the uprev process for a set of overlays.

    This handles the standard uprev process that covers most packages. There are
    also specialized uprev processes for a few specific packages not handled by
    this class, e.g. chrome and android.

    TODO (saklein): The manifest object for this class is used deep in the
        portage_util uprev process. Look into whether it's possible to redo it
        so the manifest isn't required.
    """

    def __init__(
        self,
        overlays: List[str],
        manifest: git.ManifestCheckout,
        build_targets: List["build_target_lib.BuildTarget"] = None,
        chroot: chroot_lib.Chroot = None,
        output_dir: str = None,
    ):
        """Init function.

        Args:
            overlays: The overlays to search for ebuilds.
            manifest: The manifest object.
            build_targets: The build targets to clean in |chroot|, if desired.
                No effect unless |chroot| is provided.
            chroot: The chroot to clean, if desired.
            output_dir: The path to optionally dump result files.
        """
        self.overlays = overlays
        self.manifest = manifest
        self.build_targets = build_targets or []
        self.chroot = chroot
        self.output_dir = output_dir

        self._revved_packages = None
        self._new_package_atoms = None
        self._new_ebuild_files = None
        self._removed_ebuild_files = None
        self._overlay_ebuilds = None

        # We cleaned up self-referential ebuilds by this version, but don't
        # enforce the check on older ones to avoid breaking factory/firmware
        # branches.
        root_version = chromeos_version.VersionInfo.from_repo(
            constants.SOURCE_ROOT
        )
        no_self_repos_version = chromeos_version.VersionInfo("13099.0.0")
        self._reject_self_repo = root_version >= no_self_repos_version

    @property
    def modified_ebuilds(self) -> List[str]:
        """Get the list of ebuilds modified by the uprev."""
        if self._new_ebuild_files is not None:
            return self._new_ebuild_files + self._removed_ebuild_files
        else:
            return []

    @property
    def revved_packages(self) -> List[str]:
        """Get the list of packages uprevved by the uprev."""
        return self._revved_packages or []

    def uprev(
        self, package_list: List[str] = None, force: bool = False
    ) -> None:
        """Uprev ebuilds.

        Uprev ebuilds for the packages in package_list. If package_list is not
        specified, uprevs all ebuilds for overlays in self.overlays.

        Args:
            package_list: A list of packages to uprev.
            force: Boolean indicating whether to consider deny-listed ebuilds.
        """
        # Use all found packages if an explicit package_list is not given.
        use_all = not bool(package_list)
        self._populate_overlay_ebuilds(
            use_all=use_all, package_list=package_list, force=force
        )

        with parallel.Manager() as manager:
            # Contains the list of packages we actually revved.
            self._revved_packages = manager.list()
            # The new package atoms for cleanup.
            self._new_package_atoms = manager.list()
            # The list of added ebuild files.
            self._new_ebuild_files = manager.list()
            # The list of removed ebuild files.
            self._removed_ebuild_files = manager.list()

            inputs = [[overlay] for overlay in self.overlays]
            parallel.RunTasksInProcessPool(self._uprev_overlay, inputs)

            self._revved_packages = list(self._revved_packages)
            self._new_package_atoms = list(self._new_package_atoms)
            self._new_ebuild_files = list(self._new_ebuild_files)
            self._removed_ebuild_files = list(self._removed_ebuild_files)

        self._clean_stale_packages()

        if self.output_dir and os.path.exists(self.output_dir):
            # Write out dumps of the results. This is largely meant for
            # validating results.
            osutils.WriteFile(
                os.path.join(self.output_dir, "revved_packages"),
                "\n".join(self._revved_packages),
            )
            osutils.WriteFile(
                os.path.join(self.output_dir, "new_package_atoms"),
                "\n".join(self._new_package_atoms),
            )
            osutils.WriteFile(
                os.path.join(self.output_dir, "new_ebuild_files"),
                "\n".join(self._new_ebuild_files),
            )
            osutils.WriteFile(
                os.path.join(self.output_dir, "removed_ebuild_files"),
                "\n".join(self._removed_ebuild_files),
            )

    def _uprev_overlay(self, overlay: str) -> None:
        """Execute uprevs for an overlay.

        Args:
            overlay: The overlay to uprev.
        """
        if not os.path.isdir(overlay):
            logging.warning("Skipping %s, which is not a directory.", overlay)
            return

        ebuilds = self._overlay_ebuilds.get(overlay, [])
        if not ebuilds:
            return

        inputs = [[overlay, ebuild] for ebuild in ebuilds]
        parallel.RunTasksInProcessPool(self._uprev_ebuild, inputs)

    def _uprev_ebuild(self, overlay: str, ebuild: portage_util.EBuild) -> None:
        """Work on a single ebuild.

        Args:
            overlay: The overlay the ebuild belongs to.
            ebuild: The ebuild to work on.
        """
        logging.debug(
            "Working on %s, info %s", ebuild.package, ebuild.cros_workon_vars
        )
        try:
            result = ebuild.RevWorkOnEBuild(
                os.path.join(constants.SOURCE_ROOT, "src"),
                self.manifest,
                reject_self_repo=self._reject_self_repo,
            )
        except (
            portage_util.InvalidUprevSourceError,
            portage_util.EbuildVersionError,
        ) as e:
            logging.error(
                "An error occurred while uprevving %s: %s", ebuild.package, e
            )
            raise
        except OSError:
            logging.warning(
                "Cannot rev %s\n"
                "Note you will have to go into %s "
                "and reset the git repo yourself.",
                ebuild.package,
                overlay,
            )
            raise

        if result:
            new_package, ebuild_path_to_add, ebuild_path_to_remove = result

            if ebuild_path_to_add:
                self._new_ebuild_files.append(ebuild_path_to_add)
            if ebuild_path_to_remove:
                osutils.SafeUnlink(ebuild_path_to_remove)
                self._removed_ebuild_files.append(ebuild_path_to_remove)

            self._revved_packages.append(new_package)
            self._new_package_atoms.append("=%s" % new_package)

    def _populate_overlay_ebuilds(
        self,
        use_all: bool = True,
        package_list: List[str] = None,
        force: bool = False,
    ) -> None:
        """Populates the overlay to ebuilds mapping.

        Populate self._overlay_ebuilds for all overlays in self.overlays unless
        otherwise specified by package_list.

        Args:
            use_all: Whether to include all ebuilds in the specified
                directories. If true, then we gather all packages in the
                directories regardless of whether they are in our set of
                packages.
            package_list: A set of the packages we want to gather. If
                use_all is True, this argument is ignored, and should be None.
            force: Boolean indicating whether to consider deny-listed ebuilds.
        """
        # See crrev.com/c/1257944 for origins of this.
        root_version = chromeos_version.VersionInfo.from_repo(
            constants.SOURCE_ROOT
        )
        subdir_removal = chromeos_version.VersionInfo("10363.0.0")
        require_subdir_support = root_version < subdir_removal

        if not package_list:
            package_list = []

        overlay_ebuilds = {}
        inputs = [
            [overlay, use_all, package_list, force, require_subdir_support]
            for overlay in self.overlays
        ]
        result = parallel.RunTasksInProcessPool(
            portage_util.GetOverlayEBuilds, inputs
        )
        for idx, ebuilds in enumerate(result):
            overlay_ebuilds[self.overlays[idx]] = ebuilds

        self._overlay_ebuilds = overlay_ebuilds

    def _clean_stale_packages(self) -> None:
        """Cleans up stale package info from a previous build."""
        clean_stale_packages(
            self._new_package_atoms, self.build_targets, chroot=self.chroot
        )


def clean_stale_packages(
    new_package_atoms,
    build_targets: List["build_target_lib.BuildTarget"],
    chroot: chroot_lib.Chroot = None,
) -> None:
    """Cleans up stale package info from a previous build."""
    if new_package_atoms:
        logging.info("Cleaning up stale packages %s.", new_package_atoms)

    chroot = chroot or chroot_lib.Chroot()

    if cros_build_lib.IsOutsideChroot() and not chroot.exists():
        logging.warning("Unable to clean packages. No chroot to enter.")
        return

    # First unmerge all the packages for a board, then eclean it.
    # We need these two steps to run in order (unmerge/eclean),
    # but we can let all the boards run in parallel.
    def _do_clean_stale_packages(board):
        if board:
            suffix = "-" + board
            runcmd = cros_build_lib.run
        else:
            suffix = ""
            runcmd = cros_build_lib.sudo_run

        if cros_build_lib.IsOutsideChroot():
            # Setup runcmd with the chroot arguments once.
            runcmd = functools.partial(
                runcmd, enter_chroot=True, chroot_args=chroot.get_enter_args()
            )

        emerge, eclean = "emerge" + suffix, "eclean" + suffix
        if not osutils.FindMissingBinaries([emerge, eclean]):
            if new_package_atoms:
                # If nothing was found to be unmerged, emerge will exit(1).
                result = runcmd(
                    [emerge, "-q", "--unmerge"] + new_package_atoms,
                    extra_env={"CLEAN_DELAY": "0"},
                    check=False,
                    cwd=constants.SOURCE_ROOT,
                )
                if result.returncode not in (0, 1):
                    raise cros_build_lib.RunCommandError(
                        "unexpected error", result
                    )

            runcmd(
                [eclean, "-d", "packages"],
                cwd=constants.SOURCE_ROOT,
                capture_output=True,
            )

    tasks = []
    for build_target in build_targets:
        tasks.append([build_target.name])
    tasks.append([None])

    parallel.RunTasksInProcessPool(_do_clean_stale_packages, tasks)


UprevVersionedPackageModifications = collections.namedtuple(
    "UprevVersionedPackageModifications", ("new_version", "files")
)


class UprevVersionedPackageResult:
    """Data object for uprev_versioned_package."""

    def __init__(self):
        self.modified = []

    def __bool__(self):
        return self.uprevved

    def add_result(self, new_version, modified_files):
        """Adds version/ebuilds tuple to result.

        Args:
            new_version: New version number of package.
            modified_files: List of files modified for the given version.
        """
        result = UprevVersionedPackageModifications(new_version, modified_files)
        self.modified.append(result)
        return self

    def extend(self, other: "UprevVersionedPackageResult"):
        """Adds another result from an existing result."""
        self.modified.extend(other.modified)
        return self

    def __iadd__(
        self, other: "UprevVersionedPackageResult"
    ) -> "UprevVersionedPackageResult":
        """Adds another result from an existing result."""
        self.extend(other)
        return self

    def __add__(
        self, other: "UprevVersionedPackageResult"
    ) -> "UprevVersionedPackageResult":
        """Adds two result objects to create a new one."""
        return UprevVersionedPackageResult().extend(self).extend(other)

    @property
    def uprevved(self):
        """Check if there was an uprev."""
        return bool(self.modified)


def _get_ebuilds(
    package_path: str,
) -> Tuple[portage_util.EBuild, portage_util.EBuild]:
    """Get stable and unstable ebuilds for a given package path.

    Args:
        package_path: The path of the package relative to the src root. This
            path should contain an unstable 9999 ebuild and optionally a stable
            ebuild.

    Returns:
        The stable and unstable ebuilds.

    Raises:
        NoUnstableEbuildError: if the package path doesn't contain an unstable
            ebuild.
        TooManyStableEbuildsError: if the package path contains more than 1
            stable ebuild.
    """
    package_path = str(package_path)
    package = os.path.basename(package_path)

    package_src_path = os.path.join(SRC_ROOT, package_path)
    ebuild_paths = list(portage_util.EBuild.List(package_src_path))
    stable_ebuild = None
    unstable_ebuild = None
    for path in ebuild_paths:
        ebuild = portage_util.EBuild(path)
        if ebuild.is_stable:
            stable_ebuild = ebuild
        else:
            unstable_ebuild = ebuild

    if len(ebuild_paths) > 2:
        raise TooManyStableEbuildsError(
            f"Found too many ebuilds for {package}: "
            "expected one stable and one unstable"
        )
    if unstable_ebuild is None:
        raise NoUnstableEbuildError(f"No unstable ebuild found for {package}")

    return stable_ebuild, unstable_ebuild


def get_stable_ebuild_version(
    package_path: Union[str, "pathlib.Path"],
) -> str:
    """Get the version number (without revision) of a stable ebuild.

    Args:
        package_path: The path of the package relative to the src root. This
            path should contain a stable ebuild.
    """
    stable_ebuild, _ = _get_ebuilds(str(package_path))

    if stable_ebuild is None:
        return None
    return stable_ebuild.version_no_rev


def uprev_ebuild_from_pin(
    package_path: str, version_no_rev: str, chroot: chroot_lib.Chroot
) -> UprevVersionedPackageResult:
    """Changes the package ebuild's version to match the version pin file.

    Args:
        package_path: The path of the package relative to the src root. This
            path should contain a stable and an unstable ebuild with the same
            name as the package.
        version_no_rev: The version string to uprev to (excluding revision). The
            ebuild's version will be directly set to this number.
        chroot: specify a chroot to enter.

    Returns:
        The uprev result.
    """
    package = os.path.basename(package_path)
    package_src_path = os.path.join(constants.SOURCE_ROOT, package_path)

    stable_ebuild = None
    unstable_ebuild = None
    try:
        stable_ebuild, unstable_ebuild = _get_ebuilds(package_path)
    except Error as e:
        raise EbuildUprevError(str(e))

    if stable_ebuild is None:
        raise EbuildUprevError("No stable ebuild found for %s" % package)

    # If the new version is the same as the old version, bump the revision
    # number, otherwise reset it to 1
    if version_no_rev == stable_ebuild.version_no_rev:
        version = "%s-r%d" % (
            version_no_rev,
            stable_ebuild.current_revision + 1,
        )
    else:
        version = version_no_rev + "-r1"

    new_ebuild_path = os.path.join(
        package_path, "%s-%s.ebuild" % (package, version)
    )
    new_ebuild_src_path = os.path.join(constants.SOURCE_ROOT, new_ebuild_path)
    manifest_src_path = os.path.join(package_src_path, "Manifest")

    portage_util.EBuild.MarkAsStable(
        unstable_ebuild.ebuild_path, new_ebuild_src_path, {}
    )
    osutils.SafeUnlink(stable_ebuild.ebuild_path)

    try:
        portage_util.UpdateEbuildManifest(new_ebuild_src_path, chroot=chroot)
    except cros_build_lib.RunCommandError as e:
        raise EbuildManifestError(
            "Unable to update manifest for %s: %s" % (package, e.stderr)
        )

    result = UprevVersionedPackageResult()
    result.add_result(
        version,
        [new_ebuild_src_path, stable_ebuild.ebuild_path, manifest_src_path],
    )
    return result


def uprev_workon_ebuild_to_version(
    package_path: Union[str, "pathlib.Path"],
    target_version: str,
    chroot: chroot_lib.Chroot,
    *,
    allow_downrev: bool = True,
    ref: str = "HEAD",
) -> UprevResult:
    """Uprev a cros-workon ebuild to a specified version.

    Args:
        package_path: The path of the package relative to the src root. This
            path should contain an unstable 9999 ebuild that inherits from
            cros-workon.
        target_version: The version to use for the stable ebuild to be
            generated. Should not contain a revision number.
        chroot: The path to the chroot to enter, if not the default.
        allow_downrev: Whether the downrev should be proceed. If not and the
            target version is older than the existing version, abort this
            downrev.
        ref: The target version's ref tag in the git repository to be used.
    """
    package_path = str(package_path)
    package = os.path.basename(package_path)

    package_src_path = os.path.join(SRC_ROOT, package_path)

    stable_ebuild = None
    unstable_ebuild = None
    try:
        stable_ebuild, unstable_ebuild = _get_ebuilds(package_path)
    except Error as e:
        raise EbuildUprevError(str(e))

    if not unstable_ebuild.is_workon:
        raise EbuildUprevError(
            "A workon ebuild was expected "
            f"but {unstable_ebuild.ebuild_path} is not workon."
        )

    outcome = None
    if stable_ebuild is None:
        outcome = outcome or Outcome.NEW_EBUILD_CREATED

    # If downrev is not allowed, and the new version is older than the existing
    # version, early return without uprevving.
    if (
        not allow_downrev
        and stable_ebuild
        and pms.version_lt(target_version, stable_ebuild.version_no_rev)
    ):
        return UprevResult(outcome=Outcome.NEWER_VERSION_EXISTS)

    # If the new version is the same as the old version, bump the revision
    # number, otherwise reset it to 1.
    if stable_ebuild and target_version == stable_ebuild.version_no_rev:
        output_version = (
            f"{target_version}-r{stable_ebuild.current_revision + 1}"
        )
        outcome = outcome or Outcome.REVISION_BUMP
    else:
        output_version = f"{target_version}-r1"
        outcome = outcome or Outcome.VERSION_BUMP

    new_ebuild_path = os.path.join(
        package_path, f"{package}-{output_version}.ebuild"
    )
    new_ebuild_src_path = os.path.join(SRC_ROOT, new_ebuild_path)
    manifest_src_path = os.path.join(package_src_path, "Manifest")

    # Go through the normal uprev process for a cros-workon ebuild, by
    # calculating and writing out the commit & tree IDs for the projects and
    # subtrees specified in the unstable ebuild.
    manifest = git.ManifestCheckout.Cached(constants.SOURCE_ROOT)
    info = unstable_ebuild.GetSourceInfo(
        os.path.join(constants.SOURCE_ROOT, "src"), manifest
    )
    commit_ids = [unstable_ebuild.GetCommitId(x, ref) for x in info.srcdirs]
    if not commit_ids:
        raise EbuildUprevError("No commit_ids found for %s" % info.srcdirs)

    tree_ids = [unstable_ebuild.GetTreeId(x, ref) for x in info.subtrees]
    tree_ids = [tree_id for tree_id in tree_ids if tree_id]
    if not tree_ids:
        raise EbuildUprevError("No tree_ids found for %s" % info.subtrees)

    variables = dict(
        CROS_WORKON_COMMIT=unstable_ebuild.FormatBashArray(commit_ids),
        CROS_WORKON_TREE=unstable_ebuild.FormatBashArray(tree_ids),
    )

    portage_util.EBuild.MarkAsStable(
        unstable_ebuild.ebuild_path, new_ebuild_src_path, variables
    )

    # If the newly generated stable ebuild is identical to the previous one,
    # early return without incrementing the revision number.
    if (
        stable_ebuild
        and target_version == stable_ebuild.version_no_rev
        and filecmp.cmp(
            new_ebuild_src_path, stable_ebuild.ebuild_path, shallow=False
        )
    ):
        return UprevResult(outcome=Outcome.SAME_VERSION_EXISTS)

    if stable_ebuild is not None:
        osutils.SafeUnlink(stable_ebuild.ebuild_path)

    try:
        portage_util.UpdateEbuildManifest(new_ebuild_src_path, chroot=chroot)
    except cros_build_lib.RunCommandError as e:
        raise EbuildManifestError(
            f"Unable to update manifest for {package}: {e.stderr}"
        )

    changed_files = [new_ebuild_src_path]
    if os.path.exists(manifest_src_path):
        changed_files.append(manifest_src_path)

    result = UprevResult(outcome=outcome, changed_files=changed_files)

    if stable_ebuild is not None:
        result.changed_files.append(stable_ebuild.ebuild_path)

    return result
