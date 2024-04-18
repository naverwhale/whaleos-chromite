# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Routines and classes for working with Portage overlays and ebuilds."""

import collections
import errno
import functools
import glob
import itertools
import json
import logging
import os
from pathlib import Path
import re
import shutil
from typing import (
    Dict,
    Iterable,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Tuple,
    Union,
)

from chromite.lib import build_query
from chromite.lib import build_target_lib
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import failures_lib
from chromite.lib import git
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib.parser import package_info
from chromite.lib.parser import pms_dependency
from chromite.utils import key_value_store
from chromite.utils import pms


# Type used for buildroot arguments. Typically this comes from constants such as
# constants.SOURCE_ROOT, but can also be passed as a string (e.g.
# cbuildbot/stages/generic_stages.py). Note this must be hashable for use with
# functools.lru_cache (cannot be os.PathLike).
# TODO(build): Replace BuildrootType with just `Path`.
BuildrootType = Union[Path, str]


# The parsed output of running `ebuild <ebuild path> info`.
RepositoryInfoTuple = collections.namedtuple(
    "RepositoryInfoTuple", ("srcdir", "project")
)

_PRIVATE_PREFIX = "%(buildroot)s/src/private-overlays"

# This regex matches a category name.
_category_re = re.compile(r"^(?P<category>\w[\w\+\.\-]*)$", re.VERBOSE)

# This regex matches blank lines, commented lines, and the EAPI line.
_blank_or_eapi_re = re.compile(r"^\s*(?:#|EAPI=|$)")

# This regex is used to extract test names from IUSE_TESTS
_autotest_re = re.compile(r"\+tests_(\w+)", re.VERBOSE)

# Where portage stores metadata about installed packages.
VDB_PATH = "var/db/pkg"

WORKON_EBUILD_VERSION = "9999"
WORKON_EBUILD_SUFFIX = "-%s.ebuild" % WORKON_EBUILD_VERSION

# A structure to hold computed values of CROS_WORKON_*.
CrosWorkonVars = collections.namedtuple(
    "CrosWorkonVars",
    (
        "localname",
        "project",
        "subdir",
        "always_live",
        "commit",
        "rev_subdirs",
        "subtrees",
    ),
)

# EBuild source information computed from CrosWorkonVars.
SourceInfo = collections.namedtuple(
    "SourceInfo",
    (
        # List of project names.
        "projects",
        # List of source git directory paths. They are guaranteed to exist,
        # be a directory.
        "srcdirs",
        # Obsolete concept of subdirs, present for old branch support.
        "subdirs",
        # List of source paths under subdirs. Their existence is ensured by
        # cros-workon.eclass. They can be directories or regular files.
        "subtrees",
    ),
)


class Error(Exception):
    """Base exception class for portage_util."""


class EbuildVersionError(Error):
    """Error for when an invalid version is generated for an ebuild."""


class InvalidUprevSourceError(Error):
    """Error for when an uprev source is invalid."""


class MissingOverlayError(Error):
    """This exception indicates that a needed overlay is missing."""


class NoVisiblePackageError(Error):
    """Error when there is no package matching an atom."""


class SourceDirectoryDoesNotExistError(Error, FileNotFoundError):
    """Error when at least one of an ebuild's sources does not exist."""


@functools.lru_cache(maxsize=None)
def _GetKnownOverlays(buildroot: BuildrootType) -> Dict[str, Dict]:
    """Return the list of overlays for a buildroot irrespective of board.

    Find all the overlays for a buildroot and cache the result since finding the
    overlays is the same no matter the board given for _ListOverlays.

    Args:
        buildroot: Source root to find overlays.

    Returns:
        List of overlays.
    """
    paths = (
        "projects",
        "src/overlays",
        "src/private-overlays",
        "src/third_party",
    )
    overlays: Dict[str, Dict] = {}
    for path in paths:
        path = os.path.join(buildroot, path, "*")
        for overlay in sorted(glob.glob(path)):
            name = GetOverlayName(overlay)
            if name is None:
                continue

            # Sanity check the sets of repos.
            if name in overlays:
                raise RuntimeError(
                    'multiple repos with same name "%s": %s and %s'
                    % (name, overlays[name]["path"], overlay)
                )

            try:
                masters = key_value_store.LoadFile(
                    os.path.join(overlay, "metadata", "layout.conf")
                )["masters"].split()
            except (KeyError, IOError):
                masters = []
            overlays[name] = {
                "masters": masters,
                "path": overlay,
            }
    return overlays


@functools.lru_cache(maxsize=None)
def _ListOverlays(
    board: Optional[str] = None,
    buildroot: BuildrootType = constants.SOURCE_ROOT,
) -> List:
    """Return the list of overlays to use for a given buildbot.

    Always returns all overlays in parent -> child order, and does not
    perform any filtering.

    Args:
        board: Board to look at.
        buildroot: Source root to find overlays.
    """
    # Load all the known overlays so we can extract the details below.
    overlays = _GetKnownOverlays(buildroot)

    # Easy enough -- dump them all.
    if board is None:
        return sorted([x["path"] for x in overlays.values()])

    # Build up the list of repos we need.
    ret = []
    seen = set()

    def _AddRepo(repo: str, optional: bool = False) -> bool:
        """Recursively add |repo|'s masters from |overlays| to |ret|.

        Args:
            repo: The repo name to look up.
            optional: If |repo| does not exist, return False, else raise an
                MissingOverlayError.

        Returns:
            True if |repo| was found.
        """
        if repo not in overlays:
            if optional:
                return False
            else:
                raise MissingOverlayError("%s was not found" % repo)

        for master in overlays[repo]["masters"] + [repo]:
            if master not in seen:
                seen.add(master)
                _AddRepo(master)
                ret.append(overlays[master]["path"])
                if not master.endswith("-private"):
                    _AddRepo("%s-private" % master, True)
        return True

    # Legacy: load the global configs.  In the future, this should be found
    # via the overlay's masters.
    _AddRepo("chromeos", optional=True)
    path = os.path.join(
        buildroot, "src", "private-overlays", "chromeos-*-overlay"
    )
    ret += sorted(glob.glob(path))

    # Locate the board repo by name.
    # Load the public & private versions if available.
    found_pub = _AddRepo(board, optional=True)
    found_priv = _AddRepo("%s-private" % board, optional=True)

    # If neither public nor private board was found, die.
    if not found_pub and not found_priv:
        raise MissingOverlayError("board overlay not found: %s" % board)

    return ret


def FindOverlays(
    overlay_type: str,
    board: Optional[str] = None,
    buildroot: BuildrootType = constants.SOURCE_ROOT,
) -> List:
    """Return the list of overlays to use for a given buildbot.

    The returned list of overlays will be in parent -> child order.

    Args:
        overlay_type: A string describing which overlays you want.
            'private': Just the private overlays.
            'public': Just the public overlays.
            'both': Both the public and private overlays.
        board: Board to look at.
        buildroot: Source root to find overlays.
    """
    overlays = _ListOverlays(board=board, buildroot=buildroot)
    private_prefix = _PRIVATE_PREFIX % dict(buildroot=buildroot)
    if overlay_type == constants.PRIVATE_OVERLAYS:
        return [x for x in overlays if x.startswith(private_prefix)]
    elif overlay_type == constants.PUBLIC_OVERLAYS:
        return [x for x in overlays if not x.startswith(private_prefix)]
    elif overlay_type == constants.BOTH_OVERLAYS:
        return overlays
    else:
        assert overlay_type is None
        return []


def FindOverlaysForBoards(overlay_type: str, boards: List[str]) -> List[str]:
    """Convenience function to find the overlays for multiple boards.

    Unlike FindOverlays, there is no guarantee about the overlay ordering.
    Produces a unique list of overlays.

    Args:
        overlay_type: Type of overlays to search. See FindOverlays.
        boards: The list of boards to compile a the overlays for.

    Returns:
        The list of unique overlays from all boards.
    """
    overlays = set()
    for board in boards:
        board_overlays = FindOverlays(overlay_type, board=board)
        overlays |= set(board_overlays)

    return list(overlays)


def FindOverlayFile(
    filename: str,
    overlay_type: str = constants.BOTH_OVERLAYS,
    board: Optional[str] = None,
    buildroot: BuildrootType = constants.SOURCE_ROOT,
) -> Optional[str]:
    """Attempt to find a file in the overlay directories.

    Searches through this board's overlays for the specified file. The
    overlays are searched in child -> parent order.

    Args:
        filename: Path to search for inside the overlay.
        overlay_type: A string describing which overlays you want.
            'private': Just the private overlays.
            'public': Just the public overlays.
            'both': Both the public and private overlays.
        board: Board to look at.
        buildroot: Source root to find overlays.

    Returns:
        Path to the first file found in the search. None if the file is not
        found.
    """
    for overlay in reversed(FindOverlays(overlay_type, board, buildroot)):
        if os.path.isfile(os.path.join(overlay, filename)):
            return os.path.join(overlay, filename)
    return None


def ReadOverlayFile(
    filename: str,
    overlay_type: str = constants.BOTH_OVERLAYS,
    board: Optional[str] = None,
    buildroot: BuildrootType = constants.SOURCE_ROOT,
) -> Optional[str]:
    """Attempt to open a file in the overlay directories.

    Searches through this board's overlays for the specified file. The
    overlays are searched in child -> parent order.

    Args:
        filename: Path to open inside the overlay.
        overlay_type: A string describing which overlays you want.
            'private': Just the private overlays.
            'public': Just the public overlays.
            'both': Both the public and private overlays.
        board: Board to look at.
        buildroot: Source root to find overlays.

    Returns:
        The contents of the file, or None if no files could be opened.
    """
    file_found = FindOverlayFile(filename, overlay_type, board, buildroot)
    if file_found is None:
        return None
    return osutils.ReadText(file_found)


@functools.lru_cache(maxsize=None)
def GetOverlayName(overlay: str) -> Optional[str]:
    """Get the self-declared repo name for the |overlay| path."""
    try:
        return key_value_store.LoadFile(
            os.path.join(overlay, "metadata", "layout.conf")
        )["repo-name"]
    except (KeyError, IOError):
        # Not all layout.conf files have a repo-name, so don't make a fuss.
        try:
            with open(
                os.path.join(overlay, "profiles", "repo_name"), encoding="utf-8"
            ) as f:
                return f.readline().rstrip()
        except IOError:
            # Not all overlays have a repo_name, so don't make a fuss.
            return None


def _GetSysrootTool(
    tool: str,
    board: Optional[str] = None,
    sysroot: Optional[Union[str, os.PathLike]] = None,
) -> str:
    """Return the |tool| to use for a sysroot/board/host."""
    # If there is no board or sysroot, return the host tool.
    if sysroot is None and board is None:
        return tool

    # Prefer the sysroot tool if it exists.
    if sysroot is None:
        sysroot = build_target_lib.get_default_sysroot_path(board)
    tool_path = cros_build_lib.GetSysrootToolPath(sysroot, tool)
    if os.path.exists(tool_path):
        return tool_path

    # Fallback to the general PATH wrappers if possible.
    return tool if board is None else f"{tool}-{board}"


class EBuildVersionFormatError(Error):
    """Exception for bad ebuild version string format."""

    def __init__(self, filename):
        self.filename = filename
        message = (
            "Ebuild file name %s does not match expected format." % filename
        )
        super().__init__(message)


class EbuildFormatIncorrectError(Error):
    """Exception for bad ebuild format."""

    def __init__(self, filename, message):
        message = "Ebuild %s has invalid format: %s " % (filename, message)
        super().__init__(message)


# Container for Classify return values.
EBuildClassifyAttributes = collections.namedtuple(
    "EBuildClassifyAttributes",
    ("is_workon", "is_stable", "is_manually_uprevved", "has_test"),
)


class EBuild:
    """Wrapper class for information about an ebuild."""

    VERBOSE = False
    _PACKAGE_VERSION_PATTERN = re.compile(
        r".*-(([0-9][0-9a-z_.]*)(-r[0-9]+)?)[.]ebuild"
    )
    _WORKON_COMMIT_PATTERN = re.compile(r"^CROS_WORKON_COMMIT=")

    # TODO(crbug.com/1125947): Drop CROS_WORKON_BLACKLIST.  We can do this once
    # we no longer support branches <R89 / 13623.0.0.
    _RE_MANUAL_UPREV = re.compile(
        r"""^CROS_WORKON_(MANUAL_UPREV|BLACKLIST)=(['"])?1\2?$"""
    )

    # These eclass files imply that src_test is defined for an ebuild.
    _ECLASS_IMPLIES_TEST = {
        "cros-common.mk",
        "cros-ec",  # defines src_test
        "cros-firmware",
        "cros-go",  # defines src_test
        "cros-rust",  # defines src_test
        "tast-bundle",  # inherits cros-go
    }

    @classmethod
    def _RunGit(cls, cwd, command, **kwargs):
        result = git.RunGit(cwd, command, print_cmd=cls.VERBOSE, **kwargs)
        return None if result is None else result.stdout

    def IsSticky(self) -> bool:
        """Returns True if the ebuild is sticky."""
        return self.is_stable and self.current_revision == 0

    @classmethod
    def UpdateEBuild(
        cls,
        ebuild_path: str,
        variables: Dict,
        make_stable: bool = True,
    ) -> None:
        """Static function that updates WORKON information in the ebuild.

        Args:
            ebuild_path: The path of the ebuild.
            variables: Dictionary of variables to update in ebuild.
            make_stable: Actually make the ebuild stable.
        """
        written = False
        old_lines = osutils.ReadText(ebuild_path).splitlines()
        new_lines = []
        for line in old_lines:
            # Always add variables at the top of the ebuild, before the first
            # nonblank line other than the EAPI line.
            if not written and not _blank_or_eapi_re.match(line):
                for key, value in sorted(variables.items()):
                    assert key is not None and value is not None
                    new_lines.append("%s=%s" % (key, value))
                written = True

            # Mark KEYWORDS as stable by removing ~'s.
            if line.startswith("KEYWORDS=") and make_stable:
                new_lines.append(line.replace("~", ""))
                continue

            varname, eq, _ = line.partition("=")
            if (
                not (eq == "=" and varname.strip() in variables)
                or "portage_util: no edit" in line
            ):
                # Don't write out the old value of the variable.
                new_lines.append(line)

        osutils.WriteFile(ebuild_path, "\n".join(new_lines) + "\n")

    @classmethod
    def MarkAsStable(
        cls,
        unstable_ebuild_path: str,
        new_stable_ebuild_path: str,
        variables: Dict,
        make_stable: bool = True,
    ):
        """Static function that creates a revved stable ebuild.

        This function assumes you have already figured out the name of the new
        stable ebuild path and then creates that file from the given unstable
        ebuild and marks it as stable.  If the commit_value is set, it also
        set the commit_keyword=commit_value pair in the ebuild.

        Args:
            unstable_ebuild_path: The path to the unstable ebuild.
            new_stable_ebuild_path: The path you want to use for the new stable
                ebuild.
            variables: Dictionary of variables to update in ebuild.
            make_stable: Actually make the ebuild stable.
        """
        shutil.copyfile(unstable_ebuild_path, new_stable_ebuild_path)
        EBuild.UpdateEBuild(new_stable_ebuild_path, variables, make_stable)

    @classmethod
    def CommitChange(cls, message: str, overlay: Union[str, os.PathLike]):
        """Commits current changes in git locally with given commit message.

        Args:
            message: the commit string to write when committing to git.
            overlay: directory in which to commit the changes.

        Raises:
            RunCommandError: Error occurred while committing.
        """
        logging.info("Committing changes with commit message: %s", message)
        git_commit_cmd = ["commit", "-a", "-m", message]
        cls._RunGit(overlay, git_commit_cmd)

    def __init__(self, path, subdir_support=False):
        """Sets up data about an ebuild from its path.

        Args:
            path: Path to the ebuild.
            subdir_support: Support obsolete CROS_WORKON_SUBDIR.  Intended for
                branches older than 10363.0.0.
        """
        self.subdir_support = subdir_support

        self.overlay, self.category, self.pkgname, filename = path.rsplit(
            "/", 3
        )
        m = self._PACKAGE_VERSION_PATTERN.match(filename)
        if not m:
            raise EBuildVersionFormatError(filename)
        self.version, self.version_no_rev, revision = m.groups()
        if revision is not None:
            self.current_revision = int(revision.replace("-r", ""))
        else:
            self.current_revision = 0
        self.package = "%s/%s" % (self.category, self.pkgname)

        self._ebuild_path_no_version = os.path.join(
            os.path.dirname(path), self.pkgname
        )
        self.ebuild_path_no_revision = "%s-%s" % (
            self._ebuild_path_no_version,
            self.version_no_rev,
        )
        self._unstable_ebuild_path = "%s%s" % (
            self._ebuild_path_no_version,
            WORKON_EBUILD_SUFFIX,
        )
        self.ebuild_path = path

        self.is_workon = False
        self.is_stable = False
        self.is_manually_uprevved = False
        self.has_test = False
        self._ReadEBuild(path)

        # Grab the latest project settings.
        new_vars = None
        if self._unstable_ebuild_path != self.ebuild_path and os.path.exists(
            self._unstable_ebuild_path
        ):
            try:
                new_vars = EBuild.GetCrosWorkonVars(
                    self._unstable_ebuild_path, self.pkgname
                )
            except EbuildFormatIncorrectError as e:
                logging.warning("%s: %s", self._unstable_ebuild_path, e)

        # Grab the current project settings.
        try:
            old_vars = EBuild.GetCrosWorkonVars(self.ebuild_path, self.pkgname)
        except EbuildFormatIncorrectError:
            old_vars = None

        # Merge the two settings.
        self.cros_workon_vars = old_vars
        if new_vars is not None and old_vars is not None:
            merged_vars = new_vars._replace(commit=old_vars.commit)
            # If the project settings have changed, throw away existing vars
            # (use new_vars).
            if merged_vars != old_vars:
                self.cros_workon_vars = new_vars

    @staticmethod
    def Classify(ebuild_path):
        """Return the workon, stable, and manually uprev status for the ebuild.

        workon is determined by whether the ebuild inherits from the
        'cros-workon' eclass. stable is determined by whether there's a '~'
        in the KEYWORDS setting in the ebuild. An ebuild is only manually
        uprevved if a line in it starts with 'CROS_WORKON_MANUAL_UPREV='.
        """
        is_workon = False
        is_stable = False
        is_manually_uprevved = False
        has_test = False
        restrict_tests = False
        with open(ebuild_path, mode="rb") as fp:
            for i, line in enumerate(fp):
                # If the file has bad encodings, produce a helpful diagnostic
                # for the user.  The default encoding exception lacks direct
                # file context.
                try:
                    line = line.decode("utf-8")
                except UnicodeDecodeError:
                    logging.exception(
                        "%s: line %i: invalid UTF-8: %s", ebuild_path, i, line
                    )
                    raise

                if line.startswith("inherit "):
                    eclasses = set(line.split())
                    if "cros-workon" in eclasses:
                        is_workon = True
                    if EBuild._ECLASS_IMPLIES_TEST & eclasses:
                        has_test = True
                elif line.startswith("KEYWORDS="):
                    # Strip off the comments, then extract the value of the
                    # variable, then strip off any quotes.
                    line = line.split("#", 1)[0].split("=", 1)[1].strip("\"'")
                    for keyword in line.split():
                        if not keyword.startswith("~") and keyword != "-*":
                            is_stable = True
                elif EBuild._RE_MANUAL_UPREV.match(line.strip()):
                    is_manually_uprevved = True
                elif (
                    line.startswith("src_test()")
                    or line.startswith("platform_pkg_test()")
                    or line.startswith("multilib_src_test()")
                ):
                    has_test = True
                elif line.startswith("RESTRICT=") and "test" in line:
                    restrict_tests = True
        return EBuildClassifyAttributes(
            is_workon,
            is_stable,
            is_manually_uprevved,
            has_test and not restrict_tests,
        )

    def _ReadEBuild(self, path):
        """Determine is_workon, is_stable and is_manually_uprevved settings.

        These are determined using the static Classify function.
        """
        (
            self.is_workon,
            self.is_stable,
            self.is_manually_uprevved,
            self.has_test,
        ) = EBuild.Classify(path)

    @staticmethod
    def _GetAutotestTestsFromSettings(settings) -> List[str]:
        """Return a list of test names, when given a settings dictionary.

        Args:
            settings: A dictionary containing ebuild variables contents.

        Returns:
            A list of test name strings.
        """
        # We do a bit of string wrangling to extract directory names from test
        # names. First, get rid of special characters.
        test_list: List[str] = []
        raw_tests_str = settings["IUSE_TESTS"]
        if not raw_tests_str:
            return test_list

        test_list.extend(_autotest_re.findall(raw_tests_str))
        return test_list

    @staticmethod
    def GetAutotestSubdirsToRev(ebuild_path, srcdir) -> List[str]:
        """Return list of subdirs to be watched while deciding whether to uprev.

        This logic is specific to autotest related ebuilds, that derive from the
        autotest eclass.

        Args:
            ebuild_path: Path to the ebuild file (e.g
                autotest-tests-graphics-9999.ebuild).
            srcdir: The path of the source for the test.

        Returns:
            A list of strings mentioning directory paths.
        """
        results: List[str] = []
        test_vars = ("IUSE_TESTS",)

        if not ebuild_path or not srcdir:
            return results

        # TODO(pmalani): Can we get this from get_test_list in autotest.eclass ?
        settings = osutils.SourceEnvironment(
            ebuild_path, test_vars, env=None, multiline=True
        )
        if "IUSE_TESTS" not in settings:
            return results

        test_list = EBuild._GetAutotestTestsFromSettings(settings)

        location = ["client", "server"]
        test_type = ["tests", "site_tests"]

        # Check the existence of every directory combination of location and
        # test_type for each test.
        # This is a re-implementation of the same logic in autotest_src_prepare
        # in the chromiumos-overlay/eclass/autotest.eclass.
        for cur_test in test_list:
            for x, y in list(itertools.product(location, test_type)):
                a = os.path.join(srcdir, x, y, cur_test)
                if os.path.isdir(a):
                    results.append(os.path.join(x, y, cur_test))

        return results

    @staticmethod
    def GetCrosWorkonVars(ebuild_path: Union[str, os.PathLike], pkg_name: str):
        """Return the finalized values of CROS_WORKON vars in an ebuild script.

        Args:
            ebuild_path: Path to the ebuild file (e.g: platform2-9999.ebuild).
            pkg_name: The package name (e.g.: platform2).

        Returns:
            A CrosWorkonVars tuple.
        """
        cros_workon_vars = EBuild._ReadCrosWorkonVars(ebuild_path, pkg_name)
        return EBuild._FinalizeCrosWorkonVars(cros_workon_vars, ebuild_path)

    @staticmethod
    def _ReadCrosWorkonVars(
        ebuild_path: Union[str, os.PathLike],
        pkg_name: str,
    ) -> CrosWorkonVars:
        """Return the raw values of CROS_WORKON vars in an ebuild script.

        Args:
            ebuild_path: Path to the ebuild file (e.g: platform2-9999.ebuild).
            pkg_name: The package name (e.g.: platform2).

        Returns:
            A CrosWorkonVars tuple.
        """
        workon_vars = (
            "CROS_WORKON_LOCALNAME",
            "CROS_WORKON_PROJECT",
            "CROS_WORKON_SUBDIR",  # Obsolete, used for older branches.
            "CROS_WORKON_ALWAYS_LIVE",
            "CROS_WORKON_COMMIT",
            "CROS_WORKON_SUBDIRS_TO_REV",
            "CROS_WORKON_SUBTREE",
        )
        env = {
            "CROS_WORKON_LOCALNAME": pkg_name,
            "CROS_WORKON_ALWAYS_LIVE": "",
        }
        settings = osutils.SourceEnvironment(ebuild_path, workon_vars, env=env)
        # Try to detect problems extracting the variables by checking whether
        # CROS_WORKON_PROJECT is set. If it isn't, something went wrong,
        # possibly because we're simplistically sourcing the ebuild without most
        # of portage being available. That still breaks this script and needs to
        # be flagged as an error. We won't catch problems setting
        # CROS_WORKON_LOCALNAME or if CROS_WORKON_PROJECT is set to the wrong
        # thing, but at least this covers some types of failures.
        projects = []
        subdirs = []
        rev_subdirs = []
        if "CROS_WORKON_PROJECT" in settings:
            projects = settings["CROS_WORKON_PROJECT"].split(",")
        if "CROS_WORKON_SUBDIR" in settings:
            subdirs = settings["CROS_WORKON_SUBDIR"].split(",")
        if "CROS_WORKON_SUBDIRS_TO_REV" in settings:
            rev_subdirs = settings["CROS_WORKON_SUBDIRS_TO_REV"].split(",")

        if not projects:
            raise EbuildFormatIncorrectError(
                ebuild_path,
                "Unable to determine CROS_WORKON_PROJECT values.",
            )

        localnames = settings["CROS_WORKON_LOCALNAME"].split(",")
        live = settings["CROS_WORKON_ALWAYS_LIVE"]
        commit = settings.get("CROS_WORKON_COMMIT")
        subtrees = [
            tuple(subtree.split() or [""])
            for subtree in settings.get("CROS_WORKON_SUBTREE", "").split(",")
        ]
        if len(projects) > 1 and rev_subdirs:
            raise EbuildFormatIncorrectError(
                ebuild_path,
                "Must not define CROS_WORKON_SUBDIRS_TO_REV if defining "
                "multiple cros_workon projects or source paths.",
            )

        return CrosWorkonVars(
            localname=localnames,
            project=projects,
            subdir=subdirs,
            always_live=live,
            commit=commit,
            rev_subdirs=rev_subdirs,
            subtrees=subtrees,
        )

    @staticmethod
    def _FinalizeCrosWorkonVars(
        cros_workon_vars: CrosWorkonVars,
        ebuild_path: Union[str, os.PathLike],
    ):
        """Finalize CrosWorkonVars tuple.

        It is allowed to set different number of entries in CROS_WORKON array
        variables. In that case, this function completes those variable so that
        all variables have the same number of entries.

        Args:
            cros_workon_vars: A CrosWorkonVars tuple.
            ebuild_path: Path to the ebuild file (e.g: platform2-9999.ebuild).

        Returns:
            A completed CrosWorkonVars tuple.
        """
        localnames = cros_workon_vars.localname
        projects = cros_workon_vars.project
        subdirs = cros_workon_vars.subdir
        subtrees = cros_workon_vars.subtrees

        # Sanity checks and completion.
        num_projects = len(projects)

        # Each project specification has to have the same amount of items.
        if num_projects != len(localnames):
            raise EbuildFormatIncorrectError(
                ebuild_path,
                "Number of _PROJECT and _LOCALNAME items don't match.",
            )

        if subdirs:
            if len(subdirs) != len(projects):
                raise EbuildFormatIncorrectError(
                    ebuild_path,
                    "_SUBDIR is defined inconsistently with _PROJECT (%d vs %d)"
                    % (len(subdirs), len(projects)),
                )
        else:
            subdirs = [""] * len(projects)

        # We better have at least one PROJECT at this point.
        if num_projects == 0:
            raise EbuildFormatIncorrectError(
                ebuild_path, "No _PROJECT value found."
            )

        # Subtree must be either 1 or len(project).
        if num_projects != len(subtrees):
            if len(subtrees) > 1:
                raise EbuildFormatIncorrectError(
                    ebuild_path, "Incorrect number of _SUBTREE items."
                )
            # Multiply by num_projects. Note that subtrees is a list of tuples,
            # and there should be at least one element.
            subtrees *= num_projects

        return cros_workon_vars._replace(
            localname=localnames,
            project=projects,
            subdir=subdirs,
            subtrees=subtrees,
        )

    def GetSourceInfo(self, srcroot, manifest, reject_self_repo=True):
        """Get source information for this ebuild.

        Args:
            srcroot: Full path to the "src" subdirectory in the source
                repository.
            manifest: git.ManifestCheckout object.
            reject_self_repo: Whether to abort if the ebuild lives in the same
                git repo as it is tracking for uprevs.

        Returns:
            EBuild.SourceInfo namedtuple.

        Raises:
            raise Error if there are errors with extracting/validating data
            required for constructing SourceInfo.
        """
        if self.cros_workon_vars is None:
            if self.is_workon:
                raise Error(f"{self.ebuild_path} missing workon vars")
            return SourceInfo(projects=[], srcdirs=[], subdirs=[], subtrees=[])

        localnames = self.cros_workon_vars.localname
        projects = self.cros_workon_vars.project
        subdirs = self.cros_workon_vars.subdir
        always_live = self.cros_workon_vars.always_live
        subtrees = self.cros_workon_vars.subtrees

        if always_live:
            return SourceInfo(projects=[], srcdirs=[], subdirs=[], subtrees=[])

        # Calculate srcdir (used for core packages).
        if self.category in ("chromeos-base", "brillo-base"):
            dir_ = ""
        else:
            dir_ = "third_party"

        # See what git repo the ebuild lives in to make sure the ebuild isn't
        # tracking the same repo.  https://crbug.com/1050663
        # We set strict=False if we're running under pytest because it's valid
        # for ebuilds created in tests to not live in a git tree.
        under_test = os.environ.get("CHROMITE_INSIDE_PYTEST") == "1"
        ebuild_git_tree = manifest.FindCheckoutFromPath(
            self.ebuild_path, strict=not under_test
        )
        if ebuild_git_tree:
            ebuild_git_tree_path = ebuild_git_tree.get("local_path")
        else:
            ebuild_git_tree_path = None

        subdir_paths = []
        subtree_paths = []
        for local, project, subdir, subtree in zip(
            localnames, projects, subdirs, subtrees
        ):
            subdir_path = os.path.realpath(os.path.join(srcroot, dir_, local))
            if dir_ == "" and not os.path.isdir(subdir_path):
                subdir_path = os.path.realpath(
                    os.path.join(srcroot, "platform", local)
                )

            if self.subdir_support and subdir:
                subdir_path = os.path.join(subdir_path, subdir)

            # Verify that we're grabbing the commit id from the right
            # project name.
            real_project = manifest.FindCheckoutFromPath(subdir_path)["name"]
            if project != real_project:
                raise Error(
                    "Project name mismatch for %s (found %s, expected %s)"
                    % (subdir_path, real_project, project)
                )

            if subdir_path == ebuild_git_tree_path:
                msg = (
                    "%s: ebuilds may not live in & track the same source "
                    "repository (%s); use the empty-project instead"
                    % (self.ebuild_path, subdir_path)
                )
                if reject_self_repo:
                    raise Error(msg)
                else:
                    logging.warning("Ignoring error: %s", msg)
            subdir_paths.append(subdir_path)
            subtree_paths.extend(
                os.path.join(subdir_path, s) if s else subdir_path
                for s in subtree
            )

        return SourceInfo(
            projects=projects,
            srcdirs=subdir_paths,
            subdirs=[],
            subtrees=subtree_paths,
        )

    def GetCommitId(self, srcdir, ref: str = "HEAD"):
        """Get the commit id for this ebuild.

        Returns:
            Commit id (string) for this ebuild.

        Raises:
            raise Error if git fails to return the HEAD commit id.
        """
        if not os.path.exists(srcdir):
            raise SourceDirectoryDoesNotExistError(
                "Source repository %s for project %s does not exist."
                % (srcdir, self.pkgname)
            )
        output = self._RunGit(srcdir, ["rev-parse", "%s^{commit}" % ref])
        if not output:
            raise Error("Cannot determine %s commit for %s" % (ref, srcdir))
        return output.rstrip()

    def GetTreeId(self, path, ref: str = "HEAD"):
        """Get the SHA1 of the source tree for this ebuild.

        Unlike the commit hash, the SHA1 of the source tree is unaffected by the
        history of the repository, or by commit messages.

        Given path can point a regular file, not a directory. If it does not
        exist, None is returned.

        Raises:
            raise Error if git fails to determine the HEAD tree hash.
        """
        if not os.path.exists(path):
            return None
        if os.path.isdir(path):
            basedir = path
            relpath = ""
        else:
            basedir = os.path.dirname(path)
            relpath = os.path.basename(path)
        output = self._RunGit(basedir, ["rev-parse", ref + ":./%s" % relpath])
        if not output:
            raise Error("Cannot determine %s tree hash for %s" % (ref, path))
        return output.rstrip()

    def GetVersion(self, srcroot, manifest, default):
        """Get the base version number for this ebuild.

        The version is provided by the ebuild through a specific script in
        the $FILESDIR (chromeos-version.sh).

        Raises:
            raise Error when chromeos-version.sh script fails to return the raw
            version number.
        """
        vers_script = os.path.join(
            os.path.dirname(self._ebuild_path_no_version),
            "files",
            "chromeos-version.sh",
        )

        if not os.path.exists(vers_script):
            return default

        if not self.is_workon:
            raise EbuildFormatIncorrectError(
                self._ebuild_path_no_version,
                "Package has a chromeos-version.sh script but is not "
                "workon-able.",
            )

        srcdirs = self.GetSourceInfo(srcroot, manifest).srcdirs

        # The chromeos-version script will output a usable raw version number,
        # or nothing in case of error or no available version
        result = cros_build_lib.run(
            ["bash", "-x", vers_script] + srcdirs,
            capture_output=True,
            check=False,
            encoding="utf-8",
        )

        output = result.stdout.strip()
        if result.returncode or not output:
            raise Error(
                "Package %s has a chromeos-version.sh script but failed:\n"
                "return code = %s\nstdout = %s\nstderr = %s\n"
                % (
                    self.pkgname,
                    result.returncode,
                    result.stdout,
                    result.stderr,
                )
            )

        # Sanity check: disallow versions that will be larger than the 9999
        # ebuild used by cros-workon.
        main_pv = output.split(".", 1)[0]
        try:
            main_pv = int(main_pv)
        except ValueError:
            raise ValueError(
                "%s: PV returned is invalid: %s" % (vers_script, output)
            )
        if main_pv >= int(WORKON_EBUILD_VERSION):
            raise ValueError(
                "%s: cros-workon packages must have a PV < %s; not %s"
                % (vers_script, WORKON_EBUILD_VERSION, output)
            )

        # Sanity check: We should be able to parse a CPV string with the
        # produced version number.
        verify_pkg_str = f"foo/bar-{output}"
        verify_pkg = package_info.parse(verify_pkg_str)
        if verify_pkg.cpvr != verify_pkg_str:
            raise EbuildVersionError(
                "PV returned does not match the version spec: %s" % output
            )

        return output

    @staticmethod
    def FormatBashArray(unformatted_list):
        """Returns a python list in a bash array format.

        If the list only has one item, format as simple quoted value.
        That is both backwards-compatible and more readable.

        Args:
            unformatted_list: an iterable to format as a bash array. This
                variable has to be sanitized first, as we don't do any safeties.

        Returns:
            A text string that can be used by bash as array declaration.
        """
        if len(unformatted_list) > 1:
            return '("%s")' % '" "'.join(unformatted_list)
        else:
            return '"%s"' % unformatted_list[0]

    def RevWorkOnEBuild(
        self, srcroot, manifest, reject_self_repo=True, new_version=None
    ):
        """Revs a workon ebuild given the git commit hash.

        By default, this class overwrites a new ebuild given the normal
        ebuild rev'ing logic.

        Args:
            srcroot: full path to the 'src' subdirectory in the source
                repository.
            manifest: git.ManifestCheckout object.
            reject_self_repo: Whether to abort if the ebuild lives in the same
                git repo as it is tracking for uprevs.
            new_version: The new version number for this ebuild. No revision
                number.

        Returns:
            If the revved package is different than the old ebuild, return a
            tuple of (full revved package name (including the version number),
            new stable ebuild path to add to git, old ebuild path to remove from
            git (if any)). Otherwise, return None.

        Raises:
            OSError: Error occurred while creating a new ebuild.
            IOError: Error occurred while writing to the new revved ebuild file.
        """
        if new_version is not None:
            if not pms.version_valid(new_version):
                raise ValueError(f"Invalid version {new_version}")
            if re.search(r"-r[0-9]+$", new_version):
                raise ValueError(
                    f"Revision is not allowed, given {new_version}"
                )

        if self.is_stable:
            starting_pv = self.version_no_rev
        else:
            # If given unstable ebuild, use preferred version rather than 9999.
            starting_pv = "0.0.1"

        try:
            stable_version_no_rev = self.GetVersion(
                srcroot, manifest, starting_pv
            )
        except Exception as e:
            logging.critical("%s: uprev failed: %s", self.ebuild_path, e)
            raise

        old_version = "%s-r%d" % (stable_version_no_rev, self.current_revision)
        old_stable_ebuild_path = "%s-%s.ebuild" % (
            self._ebuild_path_no_version,
            old_version,
        )

        revision = (
            1
            if new_version is not None and new_version != stable_version_no_rev
            else self.current_revision + 1
        )
        version = f"{new_version or stable_version_no_rev}-r{revision}"
        new_stable_ebuild_path = "%s-%s.ebuild" % (
            self._ebuild_path_no_version,
            version,
        )

        info = self.GetSourceInfo(
            srcroot, manifest, reject_self_repo=reject_self_repo
        )
        srcdirs = info.srcdirs
        subtrees = info.subtrees
        commit_ids = [self.GetCommitId(x) for x in srcdirs]
        if not commit_ids:
            raise InvalidUprevSourceError(
                "No commit_ids found for %s" % srcdirs
            )
        tree_ids = [self.GetTreeId(x) for x in subtrees]
        # Make sure they are all valid (e.g. a deleted repo).
        tree_ids = [tree_id for tree_id in tree_ids if tree_id]
        if not tree_ids:
            raise InvalidUprevSourceError("No tree_ids found for %s" % subtrees)
        variables = dict(
            CROS_WORKON_COMMIT=self.FormatBashArray(commit_ids),
            CROS_WORKON_TREE=self.FormatBashArray(tree_ids),
        )

        # We use |self._unstable_ebuild_path| because that will contain the
        # newest changes to the ebuild (and potentially changes to test subdirs
        # themselves).
        subdirs_to_rev = self.GetAutotestSubdirsToRev(
            self._unstable_ebuild_path, srcdirs[0]
        )
        old_subdirs_to_rev = self.GetAutotestSubdirsToRev(
            self.ebuild_path, srcdirs[0]
        )
        test_dirs_changed = False
        if sorted(subdirs_to_rev) != sorted(old_subdirs_to_rev):
            logging.info(
                "The list of subdirs in the ebuild %s has changed, uprevving.",
                self.pkgname,
            )
            test_dirs_changed = True

        def _CheckForChanges():
            # It is possible for chromeos-version.sh to have changed leading to
            # a non-existent old_stable_ebuild_path. If this is the case, a
            # change happened so perform the uprev.
            if not os.path.exists(old_stable_ebuild_path):
                return True

            old_stable_commit = self._RunGit(
                self.overlay,
                ["log", "--pretty=%H", "-n1", "--", old_stable_ebuild_path],
            ).rstrip()
            output = self._RunGit(
                self.overlay,
                [
                    "log",
                    "%s..HEAD" % old_stable_commit,
                    "--",
                    self._unstable_ebuild_path,
                    os.path.join(os.path.dirname(self.ebuild_path), "files"),
                ],
            )
            return bool(output)

        unstable_ebuild_or_files_changed = _CheckForChanges()

        # If there has been any change in the tests list, choose to uprev.
        if (
            not test_dirs_changed
            and not unstable_ebuild_or_files_changed
            and not self._ShouldRevEBuild(commit_ids, srcdirs, subdirs_to_rev)
        ):
            logging.info(
                "Skipping uprev of ebuild %s, none of the rev_subdirs have "
                "been modified, no files/, nor has the -9999 ebuild.",
                self.pkgname,
            )
            return

        logging.info(
            "Determining whether to create new ebuild %s",
            new_stable_ebuild_path,
        )

        assert os.path.exists(self._unstable_ebuild_path), (
            "Missing unstable ebuild: %s" % self._unstable_ebuild_path
        )

        self.MarkAsStable(
            self._unstable_ebuild_path, new_stable_ebuild_path, variables
        )

        old_ebuild_path = self.ebuild_path
        if (
            EBuild._AlmostSameEBuilds(old_ebuild_path, new_stable_ebuild_path)
            and not unstable_ebuild_or_files_changed
        ):
            logging.info(
                "Old and new ebuild %s are exactly identical; skipping uprev",
                new_stable_ebuild_path,
            )
            os.unlink(new_stable_ebuild_path)
            return
        else:
            logging.info(
                "Creating new stable ebuild %s", new_stable_ebuild_path
            )
            logging.info(
                "New ebuild commit id: %s", self.FormatBashArray(commit_ids)
            )
            ebuild_path_to_remove = old_ebuild_path if self.is_stable else None
            return (
                "%s-%s" % (self.package, version),
                new_stable_ebuild_path,
                ebuild_path_to_remove,
            )

    def _ShouldRevEBuild(self, commit_ids, srcdirs, subdirs_to_rev):
        """Determine whether we should attempt to rev |ebuild|.

        If CROS_WORKON_SUBDIRS_TO_REV is not defined for |ebuild|, and
        subdirs_to_rev is empty, this function trivially returns True.

        Args:
            commit_ids: Commit ID of the tip of tree for the source dir.
            srcdirs: Source directory where the git repo is located.
            subdirs_to_rev: Test subdirectories which have to be checked for
                modifications since the last stable commit hash.

        Returns:
            True is an Uprev is needed, False otherwise.
        """
        if not self.cros_workon_vars:
            return True
        if not self.cros_workon_vars.commit:
            return True
        if len(commit_ids) != 1:
            return True
        if len(srcdirs) != 1:
            return True
        if not subdirs_to_rev and not self.cros_workon_vars.rev_subdirs:
            return True

        current_commit_hash = commit_ids[0]
        stable_commit_hash = self.cros_workon_vars.commit
        srcdir = srcdirs[0]
        logrange = "%s..%s" % (stable_commit_hash, current_commit_hash)
        dirs = []
        dirs.extend(self.cros_workon_vars.rev_subdirs)
        dirs.extend(subdirs_to_rev)
        if dirs:
            # Any change to the unstable ebuild must generate an uprev. If there
            # are no dirs then this happens automatically (since the git log has
            # no file list). Otherwise, we must ensure that it works here.
            dirs.append("*9999.ebuild")
        git_args = ["log", "--oneline", logrange, "--"] + dirs

        try:
            output = EBuild._RunGit(srcdir, git_args)
        except cros_build_lib.RunCommandError as ex:
            logging.warning(str(ex))
            return True

        if output:
            logging.info(
                " Rev: Determined that one+ of the ebuild %s rev_subdirs "
                "was touched %s",
                self.pkgname,
                list(subdirs_to_rev),
            )
            return True
        else:
            logging.info(
                "Skip: Determined that none of the ebuild %s rev_subdirs "
                "was touched %s",
                self.pkgname,
                list(subdirs_to_rev),
            )
            return False

    @classmethod
    def GitRepoHasChanges(cls, directory):
        """Returns True if there are changes in the given directory."""
        # Refresh the index first. This squashes just metadata changes.
        cls._RunGit(directory, ["update-index", "-q", "--refresh"])
        output = cls._RunGit(directory, ["diff-index", "--name-only", "HEAD"])
        return output not in [None, ""]

    @classmethod
    def _AlmostSameEBuilds(cls, ebuild_path1, ebuild_path2):
        """Checks if two ebuilds are the same except CROS_WORKON_COMMIT line.

        Even if CROS_WORKON_COMMIT is different, as long as CROS_WORKON_TREE is
        the same, we can guarantee the source tree is identical.
        """
        return cls._LoadEBuildForComparison(
            ebuild_path1
        ) == cls._LoadEBuildForComparison(ebuild_path2)

    @classmethod
    def _LoadEBuildForComparison(cls, ebuild_path):
        """Loads an ebuild file dropping CROS_WORKON_COMMIT line."""
        lines = osutils.ReadText(ebuild_path).splitlines()
        return "\n".join(
            line
            for line in lines
            if not cls._WORKON_COMMIT_PATTERN.search(line)
        )

    @classmethod
    def List(cls, package_dir: Union[str, os.PathLike]):
        """Generate the path to each ebuild in |package_dir|.

        Args:
            package_dir: The package directory.
        """
        for entry in os.listdir(package_dir):
            if entry.endswith(".ebuild"):
                yield os.path.join(package_dir, entry)


class PortageDBError(Error):
    """Generic PortageDB error."""


class PortageDB:
    """Wrapper class to access the portage database located in var/db/pkg."""

    _ebuilds: Dict[str, "InstalledPackage"]

    def __init__(
        self,
        root: Union[os.PathLike, str] = "/",
        vdb: Optional[os.PathLike] = None,
        package_install_path: Optional[os.PathLike] = None,
    ):
        """Initialize the internal structure for the database in the given root.

        Args:
            root: The path to the root to inspect, for example "/build/foo".
            vdb: Known path to package database in the partition. Defaults to
                VDB_PATH.
            package_install_path: The subdirectory path from the root where
                installed files are stored. e.g. for stateful partitions on test
                images, 'dev_image'.
        """
        self.root = root
        self.package_install_path = os.path.join(
            root, package_install_path or ""
        )
        self.db_path = os.path.join(root, vdb or VDB_PATH)
        self._ebuilds = {}

    def GetInstalledPackage(self, category, pv):
        """Get the InstalledPackage instance for the passed package.

        Args:
            category: The category of the package. For example "chromeos-base".
            pv: The package name with the version (and revision) of the
                installed package. For example "libchrome-271506-r5".

        Returns:
            An InstalledPackage instance for the requested package or None if
            the requested package is not found.
        """
        pkg_key = "%s/%s" % (category, pv)
        if pkg_key in self._ebuilds:
            return self._ebuilds[pkg_key]

        # Create a new InstalledPackage instance and cache it.
        pkgdir = os.path.join(self.db_path, category, pv)
        try:
            pkg = InstalledPackage(self, pkgdir, category, pv)
        except PortageDBError:
            return None
        self._ebuilds[pkg_key] = pkg
        return pkg

    def InstalledPackages(self):
        """Lists all portage packages in the database.

        Returns:
            A list of InstalledPackage instances for each package in the
            database.
        """
        ebuild_pattern = os.path.join(self.db_path, "*/*/*.ebuild")
        packages = []

        for path in glob.glob(ebuild_pattern):
            category, pf, packagecheck = SplitEbuildPath(path)
            if not _category_re.match(category):
                continue
            if pf != packagecheck:
                continue
            pkg_key = "%s/%s" % (category, pf)
            if pkg_key not in self._ebuilds:
                self._ebuilds[pkg_key] = InstalledPackage(
                    self, os.path.join(self.db_path, category, pf), category, pf
                )
            packages.append(self._ebuilds[pkg_key])

        return packages


class InstalledPackage:
    """Wrapper class for information about an installed package.

    This class accesses the information provided by var/db/pkg for an installed
    ebuild, such as the list of files installed by this package.
    """

    # "type" constants for the ListContents() return value.
    OBJ = "obj"
    SYM = "sym"
    DIR = "dir"

    def __init__(self, portage_db, pkgdir, category=None, pf=None):
        """Initialize the installed ebuild wrapper.

        Args:
            portage_db: The PortageDB instance where the ebuild is installed.
                This is used to query the database about other installed
                ebuilds, for example, the ones listed in DEPEND, but otherwise
                it isn't used.
            pkgdir: The directory where the installed package resides. This
                could be for example a directory like "var/db/pkg/category/pf"
                or the "build-info" directory in the portage temporary directory
                where the package is being built.
            category: The category of the package. If omitted, it will be loaded
                from the package contents.
            pf: The package and version of the package. If omitted, it will be
                loaded from the package contents. This avoids unnecessary lookup
                when this value is known.

        Raises:
            PortageDBError if the pkgdir doesn't contain a valid package.
        """
        self._portage_db = portage_db
        self.pkgdir = pkgdir
        self._fields = {}
        # Prepopulate the field cache with the category and pf (if provided).
        if not category is None:
            self._fields["CATEGORY"] = category
        if not pf is None:
            self._fields["PF"] = pf

        if self.pf is None:
            raise PortageDBError(
                "Package doesn't contain package-version value."
            )

        # Check that the ebuild is present.
        ebuild_path = os.path.join(self.pkgdir, "%s.ebuild" % self.pf)
        if not os.path.exists(ebuild_path):
            raise PortageDBError(
                "Package doesn't contain an ebuild file; expected "
                f"{ebuild_path}."
            )

        split_pv = package_info.parse(self.pf)
        if not split_pv.pv:
            raise PortageDBError(
                'Package and version "%s" doesn\'t have a valid format.'
                % self.pf
            )
        self.package = split_pv.package
        self.version = split_pv.vr
        self._pkg_info = None

    def _ReadField(self, field_name):
        """Reads the contents of the file in the installed package directory.

        Args:
            field_name: The name of the field to read, for example, 'SLOT' or
                'LICENSE'.

        Returns:
            A string with the contents of the file. The contents of the file are
            cached in _fields. If the file doesn't exists returns None.
        """
        if field_name not in self._fields:
            try:
                value = osutils.ReadText(
                    os.path.join(self.pkgdir, field_name)
                ).strip()
            except IOError as e:
                if e.errno != errno.ENOENT:
                    raise
                value = None
            self._fields[field_name] = value
        return self._fields[field_name]

    def _read_depend_field(self, field_name: str) -> pms_dependency.RootNode:
        """Read a dependency field.

        NB: We don't reduce for the caller.  While the package manager will
        flatten USE conditionals like flag?(), it retains ||().  This has been
        a bit of a debate upstream as to what's "correct", but it's hard for the
        PM to guess what the ebuild ended up actually using at build time, and
        what it plans on doing at runtime.  We too will defer the flattening to
        the caller to try and evaluate what's best.

        A lazy implementation would just call `.reduce()` on the result and hope
        for the best, and most of the time it probably would be correct.  Either
        way, it really needs the complete installed state (e.g. PortageDB) to be
        able to produce a better answer.
        """
        value = self._ReadField(field_name)
        if not value:
            # Returning an empty node rather than None makes callers easier to
            # implement, and we probably will never care about "file exists at
            # all" vs "file existed but was empty".
            return pms_dependency.RootNode()
        return pms_dependency.parse(value)

    @property
    def category(self):
        return self._ReadField("CATEGORY")

    @property
    def homepage(self):
        return self._ReadField("HOMEPAGE")

    @property
    def license(self):
        return self._ReadField("LICENSE")

    @property
    def requires(self):
        return self._ReadField("REQUIRES")

    @property
    def pf(self):
        return self._ReadField("PF")

    @property
    def repository(self):
        return self._ReadField("repository")

    @property
    def size(self):
        return self._ReadField("SIZE")

    @property
    def needed(self):
        """Returns a mapping of files to the libraries they need."""
        needed = self._ReadField("NEEDED")
        if needed is None:
            return needed
        # Example:
        #   /usr/sbin/bootlockboxd libmetrics.so,libhwsec.so,...
        #   /usr/sbin/bootlockboxtool libbootlockbox-client.so,...
        #   ...
        mapping = {}
        for line in needed.split("\n"):
            parts = line.split(" ", 1)
            if len(parts) > 1:
                mapping[parts[0]] = parts[1].split(",") if parts[1] else []
        return mapping

    @property
    def package_info(self):
        if not self._pkg_info:
            self._pkg_info = package_info.parse(f"{self.category}/{self.pf}")

        return self._pkg_info

    @property
    def depend(self) -> pms_dependency.RootNode:
        """The packages we built against."""
        return self._read_depend_field("DEPEND")

    @property
    def rdepend(self) -> pms_dependency.RootNode:
        """The packages we need to run with."""
        return self._read_depend_field("RDEPEND")

    @property
    def bdepend(self) -> pms_dependency.RootNode:
        """The packages we compiled with."""
        return self._read_depend_field("BDEPEND")

    def ListContents(self):
        """List of files and directories installed by this package.

        Returns:
            A list of tuples (file_type, path) where the file_type is a string
            determining the type of the installed file: InstalledPackage.OBJ
            (regular files), InstalledPackage.SYM (symlinks) or
            InstalledPackage.DIR (directory), and path is the relative path of
            the file to the root like 'usr/bin/ls'.
        """
        path = os.path.join(self.pkgdir, "CONTENTS")
        if not os.path.exists(path):
            return []

        result = []
        # TODO(b/236161656): Fix.
        # pylint: disable-next=consider-using-with
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            # Line format is: "type file_path [more space-separated fields]".
            # Discard any other line without at least the first two fields. The
            # remaining fields depend on the type.
            typ, data = line.split(" ", 1)
            if typ == self.OBJ:
                file_path, _file_hash, _mtime = data.rsplit(" ", 2)
            elif typ == self.DIR:
                file_path = data
            elif typ == self.SYM:
                file_path, _ = data.split(" -> ", 1)
            else:
                # Unknown type.
                continue
            result.append((typ, file_path.lstrip("/")))

        return result


def BestEBuild(ebuilds: List[EBuild]) -> Optional[EBuild]:
    """Returns the newest EBuild from a list of EBuild objects."""
    # pylint: disable-next=import-error
    from portage.versions import vercmp  # type: ignore

    if not ebuilds:
        return None
    winner = ebuilds[0]
    for ebuild in ebuilds[1:]:
        if vercmp(winner.version, ebuild.version) < 0:
            winner = ebuild
    return winner


def _FindUprevCandidates(
    files: Iterable[str],
    allow_manual_uprev: bool,
    subdir_support: bool,
):
    """Return the uprev candidate ebuild from a specified list of files.

    Usually an uprev candidate is a the stable ebuild in a cros_workon
    directory.  However, if no such stable ebuild exists (someone just
    checked in the 9999 ebuild), this is the unstable ebuild.

    If the package isn't a cros_workon package, return None.

    Args:
        files: List of files in a package directory.
        allow_manual_uprev: If False, discard manually uprevved packages.
        subdir_support: Support obsolete CROS_WORKON_SUBDIR.  Intended for
            branches older than 10363.0.0.

    Raises:
        raise Error if there is error with validating the ebuild files.
    """
    stable_ebuilds = []
    unstable_ebuilds = []
    # Track if we found an unstable ebuild that is a manual uprev. This is to
    # allow adding CROS_WORKON_MANUAL_UPREV to only the unstable ebuild without
    # causing an error to be thrown here.
    unstable_manual_uprev = False
    for path in files:
        if not path.endswith(".ebuild") or os.path.islink(path):
            continue
        ebuild = EBuild(path, subdir_support)
        if not ebuild.is_workon:
            continue
        elif ebuild.is_manually_uprevved and not allow_manual_uprev:
            if not ebuild.is_stable:
                unstable_manual_uprev = True
            continue

        if ebuild.is_stable:
            if ebuild.version == WORKON_EBUILD_VERSION:
                raise Error(
                    "KEYWORDS in %s ebuild should not be stable %s"
                    % (WORKON_EBUILD_VERSION, path)
                )
            stable_ebuilds.append(ebuild)
        else:
            unstable_ebuilds.append(ebuild)

    # If both ebuild lists are empty, the passed in file list was for
    # a non-workon package.
    if not unstable_ebuilds:
        if stable_ebuilds and not unstable_manual_uprev:
            path = os.path.dirname(stable_ebuilds[0].ebuild_path)
            raise Error(
                "Missing %s ebuild in %s" % (WORKON_EBUILD_VERSION, path)
            )
        return None

    path = os.path.dirname(unstable_ebuilds[0].ebuild_path)
    assert len(unstable_ebuilds) <= 1, (
        "Found multiple unstable ebuilds in %s" % path
    )

    if not stable_ebuilds:
        logging.warning("Missing stable ebuild in %s", path)
        return unstable_ebuilds[0]

    if len(stable_ebuilds) == 1:
        return stable_ebuilds[0]

    stable_versions = set(ebuild.version_no_rev for ebuild in stable_ebuilds)
    if len(stable_versions) > 1:
        package = stable_ebuilds[0].package
        message = "Found multiple stable ebuild versions in %s:" % path
        for version in stable_versions:
            message += "\n    %s-%s" % (package, version)
        raise Error(message)

    uprev_ebuild = max(stable_ebuilds, key=lambda eb: eb.current_revision)
    for ebuild in stable_ebuilds:
        if ebuild != uprev_ebuild:
            logging.warning(
                "Ignoring stable ebuild revision %s in %s", ebuild.version, path
            )
    return uprev_ebuild


def GetOverlayEBuilds(
    overlay, use_all, packages, allow_manual_uprev=False, subdir_support=False
):
    """Get ebuilds from the specified overlay.

    Args:
        overlay: The path of the overlay to get ebuilds.
        use_all: Whether to include all ebuilds in the specified directories. If
            true, then we gather all packages in the directories regardless of
            whether they are in our set of packages.
        packages: A set of the packages we want to gather.  If use_all is True,
            this argument is ignored, and should be None.
        allow_manual_uprev: Whether to consider manually uprevved ebuilds.
        subdir_support: Support obsolete CROS_WORKON_SUBDIR.  Intended for
            branches older than 10363.0.0.

    Returns:
        A list of ebuilds of the overlay.
    """
    ebuilds = []
    for package_dir, _dirs, files in os.walk(overlay):
        # If we were given a list of packages to uprev, only consider the files
        # whose potential CP match.
        # This allows us to manually uprev a specific ebuild without throwing
        # errors on every badly formatted manually uprevved ebuild.
        package_name = os.path.basename(package_dir)
        category = os.path.basename(os.path.dirname(package_dir))

        # If the --all option isn't used, we only want to update packages that
        # are in packages.
        if not (use_all or os.path.join(category, package_name) in packages):
            continue

        paths = [os.path.join(package_dir, path) for path in files]
        ebuild = _FindUprevCandidates(paths, allow_manual_uprev, subdir_support)

        # Add stable ebuild.
        if ebuild:
            ebuilds.append(ebuild)

    return ebuilds


def _Egencache(
    repo_name: str,
    repos_conf: Optional[str] = None,
    chroot: Optional[chroot_lib.Chroot] = None,
    log_output: bool = True,
) -> cros_build_lib.CompletedProcess:
    """Execute egencache for repo_name inside the chroot.

    Args:
        repo_name: Name of the repo for the overlay.
        repos_conf: Alternative repos.conf file.
        chroot: Chroot to run in.
        log_output: Log output of cros_build_run commands.

    Returns:
        A cros_build_lib.CompletedProcess object.
    """
    cmd = [
        "egencache",
        "--update",
        "--repo",
        repo_name,
        "--jobs",
        str(os.cpu_count()),
    ]
    if repos_conf:
        cmd += ["--repos-conf", repos_conf]
    chroot = chroot or chroot_lib.Chroot()
    return chroot.run(cmd, log_output=log_output)


def generate_repositories_configuration(
    chroot: Optional[chroot_lib.Chroot] = None,
) -> str:
    """Make a repositories configuration with all overlays for egencache.

    Generate the repositories configuration containing every overlay in the same
    format as repos.conf so egencache can produce an md5-cache for every overlay
    The repositories configuration can be accepted as a string in egencache.

    Returns:
        The string of the new repositories configuration.
    """
    repos_config = ""
    overlays = FindOverlays(constants.BOTH_OVERLAYS)
    for overlay_path in overlays:
        overlay_name = GetOverlayName(overlay_path)
        if chroot:
            overlay_path = chroot.chroot_path(overlay_path)
        repos_config += f"[{overlay_name}]\nlocation = {overlay_path}\n"
    return repos_config


def RegenCache(
    overlay: str,
    commit_changes: bool = True,
    chroot: Optional[chroot_lib.Chroot] = None,
    repos_conf: Optional[str] = None,
) -> Optional[str]:
    """Regenerate the cache of the specified overlay.

    Args:
        overlay: The tree to regenerate the cache for.
        commit_changes: Whether to commit the changes.
        chroot: A chroot to enter.
        repos_conf: Alternative repos.conf file.

    Returns:
        The overlay when there are outstanding changes, or None when there were
        no updates or all updates were committed. This is meant to be a simple,
        parallel_lib friendly means of identifying which overlays have been
        changed.
    """
    repo_name = GetOverlayName(overlay)
    if not repo_name:
        return None

    layout = key_value_store.LoadFile(
        os.path.join(overlay, "metadata", "layout.conf"),
        ignore_missing=True,
    )
    if layout.get("cache-format") != "md5-dict":
        return None

    if chroot and repos_conf:
        repos_conf = chroot.chroot_path(repos_conf)

    # Regen for the whole repo.
    _Egencache(repo_name, repos_conf=repos_conf, chroot=chroot)
    # If there was nothing new generated, then let's just bail.
    result = git.RunGit(overlay, ["status", "-s", "metadata/"])
    if not result.stdout:
        return None

    if not commit_changes:
        return overlay

    # Explicitly add any new files to the index.
    git.RunGit(overlay, ["add", "metadata/"])
    # Explicitly tell git to also include rm-ed files.
    git.RunGit(overlay, ["commit", "-m", "regen cache", "metadata/"])
    return None


def RegenDependencyCache(
    board: Optional[str] = None,
    sysroot: Optional[Union[str, os.PathLike]] = None,
    jobs: Optional[int] = None,
) -> None:
    """Regenerate the dependency cache in parallel.

    Use emerge --regen instead of egencache to regenerate metadata caches for
    all overlays (egencache only updates the cache for specific overlays).

    Args:
        board: The board to inspect.
        sysroot: The root directory being inspected.
        jobs: The number of regeneration jobs to run in parallel.

    Raises:
        cros_build_lib.RunCommandError
    """
    logging.info("Rebuilding Portage dependency cache.")
    cmd = ["parallel_emerge", "--regen", "--quiet"]

    if board:
        cmd.append(f"--board={board}")
    if sysroot:
        cmd.append(f"--sysroot={sysroot}")
    if jobs:
        cmd.append(f"--jobs={jobs}")

    cros_build_lib.run(cmd, enter_chroot=True)


def ParseBashArray(value):
    """Parse a valid bash array into python list."""
    # The syntax for bash arrays is nontrivial, so let's use bash to do the
    # heavy lifting for us.
    sep = ","
    # Because %s may contain bash comments (#), put a clever newline in the way.
    cmd = 'ARR=%s\nIFS=%s; echo -n "${ARR[*]}"' % (value, sep)
    return cros_build_lib.run(
        cmd, print_cmd=False, shell=True, capture_output=True, encoding="utf-8"
    ).stdout.split(sep)


def WorkonEBuildGeneratorForDirectory(base_dir, subdir_support=False):
    """Yields cros_workon EBuilds in |base_dir|.

    Args:
        base_dir: Path to the base directory.
        subdir_support: Support obsolete CROS_WORKON_SUBDIR.  Intended for
            branches older than 10363.0.0.

    Yields:
        A cros_workon EBuild instance.
    """
    for root, _, files in os.walk(base_dir):
        for filename in files:
            # Only look at *-9999.ebuild files.
            if filename.endswith(WORKON_EBUILD_SUFFIX):
                full_path = os.path.join(root, filename)
                ebuild = EBuild(full_path, subdir_support)
                if not ebuild.is_workon:
                    continue
                yield ebuild


def WorkonEBuildGenerator(buildroot, overlay_type):
    """Scans all overlays and yields cros_workon EBuilds.

    Args:
        buildroot: Path to source root to find overlays.
        overlay_type: The type of overlay to use (one of
            constants.VALID_OVERLAYS).

    Yields:
        A cros_workon EBuild instance.
    """
    # Get the list of all overlays.
    overlays = FindOverlays(overlay_type, buildroot=buildroot)
    # Iterate through overlays and gather all workon ebuilds
    for overlay in overlays:
        for ebuild in WorkonEBuildGeneratorForDirectory(overlay):
            yield ebuild


def GetWorkonProjectMap(overlay, subdirectories):
    """Get a mapping of cros_workon ebuilds to projects and source paths.

    Args:
        overlay: Overlay to look at.
        subdirectories: List of subdirectories to look in on the overlay.

    Yields:
        Tuples containing (filename, projects) for cros-workon ebuilds
        in the given overlay under the given subdirectories.
    """
    # Search ebuilds for project names, ignoring non-existent directories.
    # Also filter out ebuilds which are not cros_workon.
    for subdir in subdirectories:
        base_dir = os.path.join(overlay, subdir)
        for ebuild in WorkonEBuildGeneratorForDirectory(base_dir):
            full_path = ebuild.ebuild_path
            workon_vars = ebuild.cros_workon_vars
            relpath = os.path.relpath(full_path, start=overlay)
            yield relpath, workon_vars.project


def EbuildToCP(path):
    """Return the category/path string from an ebuild path.

    Args:
        path: Path to an ebuild.

    Returns:
        '$CATEGORY/$PN' (e.g. 'sys-apps/dbus')
    """
    return os.path.join(*SplitEbuildPath(path)[0:2])


def SplitEbuildPath(path):
    """Split an ebuild path into its components.

    Given a specified ebuild filename, returns $CATEGORY, $PN, $P. It does not
    perform any check on ebuild name elements or their validity, merely splits
    a filename, absolute or relative, and returns the last 3 components.

    Examples:
        For /any/path/chromeos-base/power_manager/power_manager-9999.ebuild,
        returns ('chromeos-base', 'power_manager', 'power_manager-9999').

    Args:
        path: Path to the ebuild.

    Returns:
        $CATEGORY, $PN, $P
    """
    return os.path.splitext(path)[0].rsplit("/", 3)[-3:]


def FindWorkonProjects(packages):
    """Find the projects associated with the specified cros_workon packages.

    Args:
        packages: List of cros_workon packages.

    Returns:
        The set of projects associated with the specified cros_workon packages.
    """
    all_projects = set()
    buildroot, both = constants.SOURCE_ROOT, constants.BOTH_OVERLAYS
    for overlay in FindOverlays(both, buildroot=buildroot):
        for _, projects in GetWorkonProjectMap(overlay, packages):
            all_projects.update(projects)
    return all_projects


def ListInstalledPackages(sysroot):
    """[DEPRECATED] Lists all portage packages in a given portage-managed root.

    Assumes the existence of a /var/db/pkg package database.

    This function is DEPRECATED, please use PortageDB.InstalledPackages instead.

    Args:
        sysroot: The root directory being inspected.

    Returns:
        A list of (cp,v) tuples in the given sysroot.
    """
    return [
        ("%s/%s" % (pkg.category, pkg.package), pkg.version)
        for pkg in PortageDB(sysroot).InstalledPackages()
    ]


def IsPackageInstalled(package, sysroot="/"):
    """Return whether a portage package is in a given portage-managed root.

    Args:
        package: The CP to look for.
        sysroot: The root being inspected.
    """
    for key, _version in ListInstalledPackages(sysroot):
        if key == package:
            return True

    return False


def _Equery(
    module: str,
    *args: str,
    board: Optional[str] = None,
    sysroot: Optional[str] = None,
    chroot: Optional[chroot_lib.Chroot] = None,
    quiet: bool = True,
    extra_env: Optional[Dict[str, str]] = None,
    check: bool = True,
) -> cros_build_lib.CompletedProcess:
    """Executes equery commands.

    Args:
        module: The equery module to run.
        *args: Arguments to the equery module.
        board: The board to inspect.
        sysroot: The root directory being inspected.
        chroot: The chroot to work with.
        quiet: Whether to run the module in quiet mode.  This is module
            specific, so consult the documentation for behavior.
        extra_env: Extra environment settings to pass down.
        check: Whether to throw an exception if the command fails.

    Returns:
        A cros_build_lib.CompletedProcess object.
    """
    chroot = chroot or chroot_lib.Chroot()
    # There is no situation where we want color or pipe detection.
    cmd = [_GetSysrootTool("equery", board, sysroot), "--no-color", "--no-pipe"]
    if quiet:
        cmd += ["--quiet"]
    cmd += [module]
    cmd += args

    return chroot.run(
        cmd,
        debug_level=logging.DEBUG,
        capture_output=True,
        extra_env=extra_env,
        check=check,
        encoding="utf-8",
    )


def _EqueryList(
    pkg_str: str,
    board: Optional[str] = None,
    chroot: Optional[chroot_lib.Chroot] = None,
) -> cros_build_lib.CompletedProcess:
    """Executes equery list command.

    Args:
        pkg_str: The package name with optional category, version, and slot.
        board: The board to inspect.
        chroot: The chroot to work with.

    Returns:
        A cros_build_lib.CompletedProcess object.
    """
    return _Equery(
        "list",
        pkg_str,
        board=board,
        chroot=chroot,
        check=False,
    )


def FindPackageNameMatches(
    pkg_str: str,
    board: Optional[str] = None,
    chroot: Optional[chroot_lib.Chroot] = None,
) -> List[package_info.PackageInfo]:
    """Finds a list of installed packages matching |pkg_str|.

    Args:
        pkg_str: The package name with optional category, version, and slot.
        board: The board to inspect.
        chroot: The chroot to work with.

    Returns:
        An iterable of matched PackageInfo objects.
    """
    result = _EqueryList(pkg_str, board=board, chroot=chroot)

    matches = []
    if result.returncode == 0:
        matches = [package_info.parse(x) for x in result.stdout.splitlines()]

    return matches


def FindPackageNamesForFiles(*args: str) -> List[package_info.PackageInfo]:
    """Finds the list of packages that own the files in |args|.

    Returns:
        An iterable of matched PackageInfo objects.
    """
    result = _Equery("belongs", quiet=True, check=False, *args)
    return [package_info.parse(x) for x in result.stdout.strip().splitlines()]


def FindEbuildForBoardPackage(
    pkg_str: str, board: str, buildroot: BuildrootType = constants.SOURCE_ROOT
):
    """Returns a path to an ebuild for a particular board."""
    cmd = [f"equery-{board}", "which", pkg_str]
    return cros_build_lib.run(
        cmd,
        cwd=buildroot,
        enter_chroot=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout.strip()


def _EqueryWhich(
    packages_list: List[str],
    sysroot: str,
    chroot: Optional[chroot_lib.Chroot] = None,
    include_masked: bool = False,
    extra_env: Optional[Dict[str, str]] = None,
    check: bool = False,
) -> cros_build_lib.CompletedProcess:
    """Executes an equery command, returns the result of the cmd.

    Args:
        packages_list: The list of package (string) names with optional
            category, version, and slot.
        sysroot: The root directory being inspected.
        chroot: The chroot to work with.
        include_masked: True iff we should include masked ebuilds in our query.
        extra_env: optional dictionary of extra string/string pairs to use as
            the environment of equery command.
        check: If False, do not raise an exception when run returns a non-zero
            exit code. If any package does not exist causing the run to fail, we
            will return information for none of the packages, i.e: return an
            empty dictionary.

    Returns:
        result (cros_build_lib.CompletedProcess)
    """
    args = []
    if include_masked:
        args += ["--include-masked"]
    args += packages_list
    return _Equery(
        "which",
        *args,
        sysroot=sysroot,
        chroot=chroot,
        quiet=False,
        extra_env=extra_env,
        check=check,
    )


def FindEbuildsForPackages(
    packages_list,
    sysroot,
    chroot: Optional[chroot_lib.Chroot] = None,
    include_masked=False,
    extra_env=None,
    check=False,
):
    """Returns paths to the ebuilds for the packages in |packages_list|.

    Args:
        packages_list: The list of package (string) names with optional
            category, version, and slot.
        sysroot: The root directory being inspected.
        chroot: The chroot to work with.
        include_masked: True iff we should include masked ebuilds in our query.
        extra_env: optional dictionary of extra string/string pairs to use as
            the environment of equery command.
        check: If False, do not raise an exception when run returns a non-zero
            exit code. If any package does not exist causing the run to fail, we
            will return information for none of the packages, i.e: return an
            empty dictionary.

    Returns:
        A map from packages in |packages_list| to their corresponding ebuilds.
    """
    if not packages_list:
        return {}

    result = _EqueryWhich(
        packages_list,
        sysroot,
        chroot=chroot,
        include_masked=include_masked,
        extra_env=extra_env,
        check=check,
    )
    if result.returncode:
        return {}

    ebuilds_results = result.stdout.strip().splitlines()
    # Asserting the directory name of the ebuild matches the package name.
    mismatches = []
    ret = dict(zip(packages_list, ebuilds_results))
    for full_package_name, ebuild_path in ret.items():
        cpv = package_info.parse(full_package_name)
        path_category, path_package_name, _ = SplitEbuildPath(ebuild_path)
        if not (
            (cpv.category is None or path_category == cpv.category)
            and cpv.package.startswith(path_package_name)
        ):
            mismatches.append(
                "%s doesn't match %s" % (ebuild_path, full_package_name)
            )

    assert not mismatches, (
        "Detected mismatches between the package & corresponding ebuilds: %s"
        % "\n".join(mismatches)
    )

    return ret


def FindEbuildForPackage(
    pkg_str,
    sysroot,
    chroot: Optional[chroot_lib.Chroot] = None,
    include_masked=False,
    extra_env=None,
    check=False,
):
    """Returns a path to an ebuild responsible for package matching |pkg_str|.

    Args:
        pkg_str: The package name with optional category, version, and slot.
        sysroot: The root directory being inspected.
        chroot: The chroot to work with.
        include_masked: True iff we should include masked ebuilds in our query.
        extra_env: optional dictionary of extra string/string pairs to use as
            the environment of equery command.
        check: If False, do not raise an exception when run returns a non-zero
            exit code. Instead, return None.

    Returns:
        Path to ebuild for this package.
    """
    ebuilds_map = FindEbuildsForPackages(
        [pkg_str],
        sysroot,
        chroot=chroot,
        include_masked=include_masked,
        extra_env=extra_env,
        check=check,
    )
    if not ebuilds_map:
        return None
    return ebuilds_map[pkg_str]


def FindEbuildsForOverlays(
    overlays: List[Union[str, os.PathLike]]
) -> Iterator[Path]:
    """Get paths to ebuilds using the given overlay paths.

    Args:
        overlays: A list of overlay paths to get ebuilds for.

    Returns:
        A generator of paths to ebuild files.
    """
    return itertools.chain.from_iterable(
        Path(x).rglob("*.ebuild") for x in overlays
    )


def _EqueryDepgraph(
    pkg_str: str,
    sysroot: str,
    board: Optional[str],
    chroot: Optional[chroot_lib.Chroot] = None,
    depth: int = 0,
) -> cros_build_lib.CompletedProcess:
    """Executes equery depgraph to find dependencies.

    Args:
        pkg_str: The package name with optional category, version, and slot.
        sysroot: The root directory being inspected.
        board: The board to inspect.
        chroot: The chroot to work with.
        depth: The depth of the transitive dependency tree to explore. 0 for
            unlimited.

    Returns:
        result (cros_build_lib.CompletedProcess)
    """
    return _Equery(
        "depgraph",
        f"--depth={depth}",
        pkg_str,
        sysroot=sysroot,
        board=board,
        chroot=chroot,
    )


def GetFlattenedDepsForPackage(
    pkg_str, sysroot="/", board: Optional[str] = "", depth=0
):
    """Returns a depth-limited list of the dependencies for a given package.

    Args:
        pkg_str: The package name with optional category, version, and slot.
        sysroot: The root directory being inspected.
        board: The board being inspected.
        depth: The depth of the transitive dependency tree to explore. 0 for
            unlimited.

    Returns:
        List[str]: A list of the dependencies of the package. Includes the
        package itself.
    """
    if not pkg_str:
        raise ValueError("pkg_str must be non-empty")

    result = _EqueryDepgraph(pkg_str, sysroot, board, depth=depth)

    return _ParseDepTreeOutput(result.stdout)


def _ParseDepTreeOutput(equery_output):
    """Parses the output of `equery -CQn depgraph` in to a list of package CPVs.

    Args:
        equery_output: A string containing the output of the `equery depgraph`
            command as formatted by the -C/--nocolor and -q/--quiet command line
            options. The contents should roughly resemble:
            ```
            app-editors/vim-8.1.1486:
            [  0]  app-editors/vim-8.1.1486
            [  1]  app-eselect/eselect-vi-1.1.9
            ```

    Returns:
        List[str]: A list of package CPVs parsed from the command output.
    """
    equery_output_regex = r"\[[\d ]+\]\s*([^\s]+)"
    return re.findall(equery_output_regex, equery_output)


def GetReverseDependencies(
    packages: List[str],
    sysroot: Union[str, os.PathLike] = "/",
    chroot: Optional[chroot_lib.Chroot] = None,
    indirect: bool = False,
) -> List[Optional[package_info.PackageInfo]]:
    """List all reverse dependencies for the given list of packages.

    Args:
        packages: Packages with optional category, version, and slot.
        sysroot: The root directory being inspected.
        chroot: The chroot to work with.
        indirect: If True, search for both the direct and indirect dependencies
            on the specified packages.

    Returns:
        List[package_info.PackageInfo]: Packages that depend on the given
        packages.

    Raises:
        ValueError when no packages are provided.
        cros_build_lib.RunCommandError when the equery depends command errors.
    """
    if not packages:
        raise ValueError("Must provide at least one package.")

    sysroot = Path(sysroot)

    args = []
    if indirect:
        args += ["--indirect"]
    args += packages

    result = _Equery(
        "depends",
        *args,
        sysroot=str(sysroot),
        chroot=chroot,
        check=False,
    )
    return [package_info.parse(x) for x in result.stdout.strip().splitlines()]


def _Qlist(
    args: List[str],
    board: Optional[str] = None,
    buildroot: BuildrootType = constants.SOURCE_ROOT,
) -> cros_build_lib.CompletedProcess:
    """Run qlist with the given args.

    Args:
        args: The qlist arguments.
        board: The board to inspect.
        buildroot: Source root to find overlays.

    Returns:
        The command result.
    """
    cmd = [_GetSysrootTool("qlist", board=board)]
    # Simplify output.
    cmd += ["-Cq"]
    cmd += args

    return cros_build_lib.run(
        cmd,
        enter_chroot=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        cwd=buildroot,
    )


def GetInstalledPackageUseFlags(
    pkg_str, board=None, buildroot=constants.SOURCE_ROOT
):
    """Gets the list of USE flags for installed packages matching |pkg_str|.

    Args:
        pkg_str: The package name with optional category, version, and slot.
        board: The board to inspect.
        buildroot: Source root to find overlays.

    Returns:
        A dictionary with the key being a package CP and the value being the
        list of USE flags for that package.
    """
    result = _Qlist(["-U", pkg_str], board, buildroot)
    use_flags = {}
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            tokens = line.split()
            use_flags[tokens[0]] = tokens[1:]

    return use_flags


def GetBinaryPackageDir(sysroot="/", packages_dir=None):
    """Returns the binary package directory of |sysroot|."""
    dir_name = packages_dir if packages_dir else "packages"
    return os.path.join(sysroot, dir_name)


def GetBinaryPackagePath(c, p, v, sysroot="/", packages_dir=None):
    """Returns the path to the binary package.

    Args:
        c: category.
        p: package.
        v: version.
        sysroot: The root being inspected.
        packages_dir: Name of the packages directory in |sysroot|.

    Returns:
        The path to the binary package.
    """
    pkgdir = GetBinaryPackageDir(sysroot=sysroot, packages_dir=packages_dir)
    path = os.path.join(pkgdir, c, "%s-%s.tbz2" % (p, v))
    if not os.path.exists(path):
        raise ValueError("Cannot find the binary package %s!" % path)

    return path


def GetBoardUseFlags(board: str) -> List[str]:
    """Returns a list of USE flags in effect for a board."""
    return sorted(
        build_query.Query(build_query.Board)
        .filter(lambda x: x.name == board)
        .one()
        .use_flags
    )


def _EmergeBoard(
    package: str,
    board: Optional[str] = None,
    sysroot: Optional[Union[str, os.PathLike]] = None,
    buildroot: BuildrootType = constants.SOURCE_ROOT,
    set_empty_root: bool = False,
) -> cros_build_lib.CompletedProcess:
    """Call emerge board to get dependences of package.

    Args:
        board: The board to inspect.
        sysroot: The root directory being inspected.
        package: The package name with optional category, version, and slot.
        buildroot: Source root to find overlays.
        set_empty_root: Set the --root argument to /mnt/empty. This is a
            workaround for an issue for portage versions before 2.3.75.

    Returns:
        result (cros_build_lib.CompletedProcess)
    """
    emerge = _GetSysrootTool("emerge", board=board, sysroot=sysroot)
    cmd = [emerge, "-p", "--cols", "--quiet", "-e"]
    if set_empty_root:
        cmd += ["--root", "/mnt/empty"]
    cmd.append(package)

    return cros_build_lib.run(
        cmd,
        cwd=buildroot,
        enter_chroot=True,
        capture_output=True,
        encoding="utf-8",
    )


def GetPackageDependencies(
    package: str,
    board: Optional[str] = None,
    sysroot: Optional[Union[str, os.PathLike]] = None,
    buildroot: BuildrootType = constants.SOURCE_ROOT,
    set_empty_root: bool = False,
) -> List[str]:
    """Returns the depgraph list of packages for a board and package."""
    output = _EmergeBoard(
        package, board, sysroot, buildroot, set_empty_root
    ).stdout.splitlines()
    packages = []
    for line in output:
        # The first column is ' NRfUD '
        columns = line[7:].split()
        try:
            package = columns[0] + "-" + columns[1]
            packages.append(package)
        except IndexError:
            logging.error("Wrong format of output: \n%r", output)
            raise

    return packages


def GetRepositoryFromEbuildInfo(info):
    """Parse output of the result of `ebuild <ebuild_path> info`

    This command should return output that looks a lot like:
     CROS_WORKON_SRCDIR=("/mnt/host/source/src/platform2")
     CROS_WORKON_PROJECT=("chromiumos/platform2")
    """
    srcdir_match = re.search(
        r'^CROS_WORKON_SRCDIR=(\(".*"\))$', info, re.MULTILINE
    )
    project_match = re.search(
        r'^CROS_WORKON_PROJECT=(\(".*"\))$', info, re.MULTILINE
    )
    if not srcdir_match or not project_match:
        return None

    srcdirs = ParseBashArray(srcdir_match.group(1))
    projects = ParseBashArray(project_match.group(1))
    if len(srcdirs) != len(projects):
        return None

    return [
        RepositoryInfoTuple(srcdir, project)
        for srcdir, project in zip(srcdirs, projects)
    ]


def _EbuildInfo(
    ebuild_path: str, sysroot: str
) -> cros_build_lib.CompletedProcess:
    """Get ebuild info for <ebuild_path>.

    Args:
        ebuild_path: string full path to ebuild file.
        sysroot: The root directory being inspected.

    Returns:
        result (cros_build_lib.CompletedProcess)
    """
    cmd = (_GetSysrootTool("ebuild", sysroot=sysroot), ebuild_path, "info")
    return cros_build_lib.dbg_run(
        cmd, capture_output=True, check=False, encoding="utf-8"
    )


def GetRepositoryForEbuild(ebuild_path, sysroot):
    """Get parsed output of `ebuild <ebuild_path> info`

    ebuild ... info runs the pkg_info step of an ebuild.
    cros-workon.eclass defines that step and prints both variables.

    Args:
        ebuild_path: string full path to ebuild file.
        sysroot: The root directory being inspected.

    Returns:
        list of RepositoryInfoTuples.
    """
    result = _EbuildInfo(ebuild_path, sysroot)
    return GetRepositoryFromEbuildInfo(result.stdout)


def CleanOutdatedBinaryPackages(
    sysroot: Union[str, os.PathLike],
    deep: bool = True,
    exclusion_file: Optional[Union[str, os.PathLike]] = None,
) -> cros_build_lib.CompletedProcess:
    """Cleans outdated binary packages from |sysroot|.

    Args:
        sysroot: The root directory being inspected.
        deep: If set to True, keep minimal files for reinstallation by examining
            vartree for installed packages. If set to False, use porttree, which
            contains every ebuild in the tree, to determine which binpkgs to
            clean.
        exclusion_file: Path to the exclusion file.

    Returns:
        result (cros_build_lib.CompletedProcess)

    Raises:
        cros_build_lib.RunCommandError
    """
    sysroot = Path(sysroot)
    if exclusion_file:
        exclusion_file = Path(exclusion_file)

    cmd = [_GetSysrootTool("eclean", sysroot=str(sysroot))]
    if deep:
        cmd += ["-d"]
    if exclusion_file:
        cmd += ["-e", str(exclusion_file)]
    cmd += ["packages"]
    return cros_build_lib.run(cmd)


def _CheckHasTest(cp, sysroot, require_workon: bool = False):
    """Checks if the ebuild for |cp| has tests.

    Args:
        cp: A portage package in the form category/package_name.
        sysroot: Path to the sysroot.
        require_workon: Whether to only test workon packages.

    Returns:
        |cp| if the ebuild for |cp| defines a test stanza, None otherwise.

    Raises:
        raise failures_lib.PackageBuildFailure if FindEbuildForPackage
        raises a RunCommandError
    """
    try:
        path = FindEbuildForPackage(cp, sysroot, check=True)
    except cros_build_lib.RunCommandError as e:
        logging.error("FindEbuildForPackage error %s", e)
        raise failures_lib.PackageBuildFailure(e, "equery", [cp])
    ebuild = EBuild(path, False)
    if require_workon and not ebuild.is_workon:
        return None
    elif ebuild.has_test:
        return cp
    return None


def PackagesWithTest(sysroot, packages, require_workon: bool = False):
    """Returns the subset of |packages| that have unit tests.

    Args:
        sysroot: Path to the sysroot.
        packages: List of packages to filter.
        require_workon: Whether to only test workon packages.

    Returns:
        The subset of |packages| that defines unit tests.
    """
    inputs = [(cp, sysroot, require_workon) for cp in packages]
    pkg_with_test = set(parallel.RunTasksInProcessPool(_CheckHasTest, inputs))

    # CheckHasTest will return None for packages that do not have tests. We can
    # discard that value.
    pkg_with_test.discard(None)
    return pkg_with_test


def ParseDieHookStatusFile(metrics_dir: str) -> List[package_info.PackageInfo]:
    """Parse the status file generated by the failed packages die_hook

    Args:
        metrics_dir: The value of CROS_METRICS_DIR, which is where the status
            file is expected to have been generated.

    Returns:
        Packages that failed in the build attempt.
    """
    file_path = os.path.join(metrics_dir, constants.DIE_HOOK_STATUS_FILE_NAME)
    if not os.path.exists(file_path):
        return []

    with open(file_path, encoding="utf-8") as failed_pkgs_file:
        failed_pkgs = []
        for line in failed_pkgs_file:
            cpv, _phase = line.split()
            failed_pkgs.append(package_info.parse(cpv))
        return failed_pkgs


def HasPrebuilt(atom, board=None, extra_env=None):
    """Check if the atom's best visible version has a prebuilt available."""
    cmd = [
        os.path.join(
            constants.CHROOT_SOURCE_ROOT, "chromite", "scripts", "has_prebuilt"
        ),
        atom,
    ]
    if board:
        cmd += ["--build-target", board]

    if logging.getLogger().isEnabledFor(logging.DEBUG):
        cmd += ["--debug"]

    with osutils.TempDir() as tempdir:
        output_file = os.path.join(tempdir, "has_prebuilt.json")
        cmd += ["--output", output_file]
        result = cros_build_lib.run(
            cmd, enter_chroot=True, extra_env=extra_env, check=False
        )

        if result.returncode:
            logging.warning(
                "Error when checking for prebuilts: %s", result.stderr
            )
            return False

        raw = osutils.ReadText(output_file)
        logging.debug("Raw result: %s", raw)
        prebuilts = json.loads(raw)

    if atom not in prebuilts:
        logging.warning("%s not found in has_prebuilt output.", atom)
        return False

    return prebuilts[atom]


class PortageqError(Error):
    """Portageq command error."""


def _Portageq(
    command: List[str],
    board: Optional[str] = None,
    sysroot: Optional[str] = None,
    chroot: Optional[chroot_lib.Chroot] = None,
    **kwargs,
) -> cros_build_lib.CompletedProcess:
    """Run a portageq command.

    Args:
        command: Portageq command to run excluding portageq.
        board: Specific board to query.
        sysroot: The sysroot to query.
        chroot: Chroot to work with.
        **kwargs: Additional run arguments.

    Returns:
        cros_build_lib.CompletedProcess

    Raises:
        cros_build_lib.RunCommandError
    """
    if "capture_output" not in kwargs:
        kwargs.setdefault("stdout", True)
        kwargs.setdefault("stderr", True)
    kwargs.setdefault("cwd", constants.SOURCE_ROOT)
    kwargs.setdefault("debug_level", logging.DEBUG)
    kwargs.setdefault("encoding", "utf-8")

    chroot = chroot or chroot_lib.Chroot()
    portageq = _GetSysrootTool("portageq", board, sysroot)
    return chroot.run([portageq] + command, **kwargs)


def PortageqBestVisible(
    atom: str,
    board: Optional[str] = None,
    sysroot: Optional[str] = None,
    pkg_type: str = "ebuild",
    cwd: Optional[str] = None,
    chroot: Optional[chroot_lib.Chroot] = None,
) -> package_info.PackageInfo:
    """Get the best visible ebuild CPV for the given atom.

    Args:
        atom: Portage atom.
        board: Board to look at. By default, look in chroot.
        sysroot: The sysroot to query.
        pkg_type: Package type (ebuild, binary, or installed).
        cwd: Path to use for the working directory for run.
        chroot: Chroot to work with.

    Returns:
        The parsed package information, which may be empty.

    Raises:
        NoVisiblePackageError when no version of the package can be found.
    """
    if sysroot is None:
        sysroot = build_target_lib.get_default_sysroot_path(board)
    cmd = ["best_visible", sysroot, pkg_type, atom]
    try:
        result = _Portageq(
            cmd, board=board, sysroot=sysroot, cwd=cwd, chroot=chroot
        )
    except cros_build_lib.RunCommandError as e:
        logging.error(e)
        raise NoVisiblePackageError(
            f'No best visible package for "{atom}" could be found.'
        ) from e

    return package_info.parse(result.stdout.strip())


def PortageqEnvvar(
    variable,
    board=None,
    sysroot=None,
    allow_undefined=False,
    chroot: Optional[chroot_lib.Chroot] = None,
):
    """Run portageq envvar for a single variable.

    Like PortageqEnvvars, but returns the value of the single variable rather
    than a mapping.

    Args:
        variable: str - The variable to retrieve.
        board: str|None - See PortageqEnvvars.
        sysroot: The sysroot to query.
        allow_undefined: bool - See PortageqEnvvars.
        chroot: Chroot to work with.

    Returns:
        str - The value retrieved from portageq envvar.

    Raises:
        See PortageqEnvvars.
        TypeError when variable is not a valid type.
        ValueError when variable is empty.
    """
    if not isinstance(variable, str):
        raise TypeError("Variable must be a string.")
    elif not variable:
        raise ValueError("Variable must not be empty.")

    result = PortageqEnvvars(
        [variable],
        board=board,
        sysroot=sysroot,
        allow_undefined=allow_undefined,
        chroot=chroot,
    )
    return result.get(variable)


def PortageqEnvvars(
    variables: List[str],
    board: Optional[str] = None,
    sysroot: Optional[str] = None,
    allow_undefined: bool = False,
    chroot: Optional[chroot_lib.Chroot] = None,
) -> Dict[str, str]:
    """Run portageq envvar for the given variables.

    Args:
        variables: Variables to query.
        board: Specific board to query.
        sysroot: The sysroot to query.
        allow_undefined: True to quietly allow empty strings when the variable
            is undefined. False to raise an error.
        chroot: Chroot to work with.

    Returns:
        Variable to envvar value mapping for each of the |variables|.

    Raises:
        TypeError if variables is a string.
        PortageqError when a variable is undefined and not allowed to be.
        cros_build_lib.RunCommandError when the command does not run
        successfully.
    """
    if isinstance(variables, str):
        raise TypeError(
            "Variables must not be a string. "
            "See PortageqEnvvar for single variable support."
        )

    if not variables:
        return {}

    try:
        result = _Portageq(
            ["envvar", "-v"] + variables,
            board=board,
            sysroot=sysroot,
            chroot=chroot,
        )
        output = result.stdout
    except cros_build_lib.RunCommandError as e:
        if e.returncode != 1:
            # Actual error running command, raise.
            raise e
        elif not allow_undefined:
            # Error for undefined variable.
            raise PortageqError(f"One or more variables undefined: {e.stdout}")
        else:
            # Undefined variable but letting it slide.
            output = e.stdout

    return key_value_store.LoadData(output, multiline=True)


def PortageqHasVersion(
    category_package: str,
    board: Optional[str] = None,
    sysroot: Optional[str] = None,
    chroot: Optional[chroot_lib.Chroot] = None,
) -> bool:
    """Run portageq has_version.

    Args:
        category_package: The atom whose version is to be verified.
        board: Specific board to query.
        sysroot: Root directory to consider.
        chroot: Chroot to work with.

    Returns:
        bool

    Raises:
        cros_build_lib.RunCommandError when the command fails to run.
    """
    if sysroot is None:
        sysroot = build_target_lib.get_default_sysroot_path(board)
    # Exit codes 0/1+ indicate "have"/"don't have".
    # Normalize them into True/False values.
    result = _Portageq(
        ["has_version", os.path.abspath(sysroot), category_package],
        board=board,
        sysroot=sysroot,
        check=False,
        chroot=chroot,
    )
    return not result.returncode


def PortageqMatch(
    atom: str,
    board: Optional[str] = None,
    sysroot: Optional[str] = None,
    chroot: Optional[chroot_lib.Chroot] = None,
):
    """Run portageq match.

    Find the full category/package-version for the specified atom.

    Args:
        atom: Portage atom.
        board: Specific board to query.
        sysroot: The sysroot to query.
        chroot: Chroot to work with.

    Returns:
        package_info.PackageInfo|None
    """
    if sysroot is None:
        sysroot = build_target_lib.get_default_sysroot_path(board)
    result = _Portageq(
        ["match", sysroot, atom], board=board, sysroot=sysroot, chroot=chroot
    )
    return package_info.parse(result.stdout.strip()) if result.stdout else None


class PackageNotFoundError(Error):
    """Error indicating that the package asked for was not found."""


def GenerateInstalledPackages(db, root, packages):
    """Generate a sequence of installed package objects from package names."""
    for package in packages:
        category, pv = package.split("/")
        installed_package = db.GetInstalledPackage(category, pv)
        if not installed_package:
            raise PackageNotFoundError(
                "Unable to locate package %s in %s" % (package, root)
            )
        yield installed_package


class PackageSizes(NamedTuple):
    """Size of an installed package on disk."""

    apparent_size: int
    disk_utilization_size: int


def GeneratePackageSizes(db, root, installed_packages):
    """Collect package sizes and generate package size pairs.

    Yields:
        (str, int): A pair of cpv and total package size.
    """
    visited_cpvs = set()
    for installed_package in installed_packages:
        package_cpv = "%s/%s/%s" % (
            installed_package.category,
            installed_package.package,
            installed_package.version,
        )

        assert package_cpv not in visited_cpvs
        visited_cpvs.add(package_cpv)

        if not installed_package:
            raise PackageNotFoundError(
                "Unable to locate installed_package %s in %s"
                % (package_cpv, root)
            )
        package_filesize = CalculatePackageSize(
            installed_package.ListContents(), db.package_install_path
        )
        logging.debug(
            "%s installed_package size is %d",
            package_cpv,
            package_filesize.apparent_size,
        )
        yield package_cpv, package_filesize.apparent_size


def CalculatePackageSize(
    files_in_package: Iterable[Tuple[str, str]],
    package_install_path: os.PathLike,
) -> PackageSizes:
    """Given a fileset for a Portage package, calculate the package size.

    This function provides the size of the given package on disk in both
    apparent size and disk utilization. It is provided in bytes (not blocks).

    By implication, these two figures may be different when files are very
    small, or when the apparent size is much larger than allocated blocks on
    disk (as is the case with sparse files).

    This function also only calculates the size of package files which are
    actual OBJ-type files listed in the CONTENTS file for the package in the
    package db. As such, the storage needs for any existing symlinks or relevant
    inodes is not accounted for in this function.

    Args:
        files_in_package: A list of file information for all files installed by
            a single package.
        package_install_path: The path prefix for the installation location.

    Returns:
        A PackageSizes object containing the calculated apparent size and disk
        utilization.
    """
    total_apparent_size = 0
    total_disk_utilization = 0
    for content_type, path in files_in_package:
        if content_type == InstalledPackage.OBJ:
            filename = os.path.join(package_install_path, path)
            try:
                file_details = os.lstat(filename)
                apparent_size = file_details.st_size
                disk_utilization = file_details.st_blocks * 512
            except FileNotFoundError as e:
                logging.warning(
                    "unable to compute the size of %s because the file "
                    "doesn't exist (skipping): %s",
                    filename,
                    e,
                )
                continue
            except PermissionError as e:
                logging.warning(
                    "cannot compute size of %s due to inadequate "
                    "permissions (skipping): %s",
                    filename,
                    e,
                )
                continue
            except OSError as e:
                logging.warning(
                    "unable to compute the size of %s (skipping): %s",
                    filename,
                    e,
                )
                continue
            logging.debug(
                "apparent size of %s = %d bytes, du = %d bytes",
                filename,
                apparent_size,
                disk_utilization,
            )
            total_apparent_size += apparent_size
            total_disk_utilization += disk_utilization
    return PackageSizes(
        apparent_size=total_apparent_size,
        disk_utilization_size=total_disk_utilization,
    )


def UpdateEbuildManifest(
    ebuild_path: Union[str, os.PathLike],
    chroot: chroot_lib.Chroot,
) -> cros_build_lib.CompletedProcess:
    """Updates the ebuild manifest for the provided ebuild path.

    Args:
        ebuild_path: The outside-chroot absolute path to the ebuild.
        chroot: The chroot to enter.

    Returns:
        The command result.
    """

    chroot_ebuild_path = chroot.chroot_path(ebuild_path)
    command = ["ebuild", chroot_ebuild_path, "manifest", "--force"]
    return chroot.run(command)
