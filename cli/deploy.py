# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Deploy packages onto a target device.

Integration tests for this file can be found at cli/cros/tests/cros_vm_tests.py.
See that file for more information.
"""

from __future__ import division

import bz2
import fnmatch
import functools
import json
import logging
import os
from pathlib import Path
import re
import tempfile
from typing import Dict, List, NamedTuple, Set, Tuple

from chromite.cli import command
from chromite.lib import build_target_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import dlc_lib
from chromite.lib import operation
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import remote_access
from chromite.lib import workon_helper
from chromite.lib.parser import package_info


try:
    import portage
except ImportError:
    if cros_build_lib.IsInsideChroot():
        raise


_DEVICE_BASE_DIR = "/usr/local/tmp/cros-deploy"
# This is defined in src/platform/dev/builder.py
_STRIPPED_PACKAGES_DIR = "stripped-packages"

_MAX_UPDATES_NUM = 10
_MAX_UPDATES_WARNING = (
    "You are about to update a large number of installed packages, which "
    "might take a long time, fail midway, or leave the target in an "
    "inconsistent state. It is highly recommended that you flash a new image "
    "instead."
)

_DLC_ID = "DLC_ID"
_DLC_PACKAGE = "DLC_PACKAGE"
_DLC_ENABLED = "DLC_ENABLED"
_ENVIRONMENT_FILENAME = "environment.bz2"
_DLC_INSTALL_ROOT = "/var/cache/dlc"


class CpvInfo(NamedTuple):
    """Holds a CPV and its associated information that we care about"""

    cpv: Dict[str, package_info.CPV]
    slot: str
    rdep_raw: str
    build_time: int
    use: str


class DeployError(Exception):
    """Thrown when an unrecoverable error is encountered during deploy."""


class BrilloDeployOperation(operation.ProgressBarOperation):
    """ProgressBarOperation specific for brillo deploy."""

    # These two variables are used to validate the output in the VM integration
    # tests. Changes to the output must be reflected here.
    MERGE_EVENTS = (
        "Preparing local packages",
        "NOTICE: Copying binpkgs",
        "NOTICE: Installing",
        "been installed.",
        "Please restart any updated",
    )
    UNMERGE_EVENTS = (
        "NOTICE: Unmerging",
        "been uninstalled.",
        "Please restart any updated",
    )

    def __init__(self, emerge: bool):
        """Construct BrilloDeployOperation object.

        Args:
            emerge: True if emerge, False if unmerge.
        """
        super().__init__()
        if emerge:
            self._events = self.MERGE_EVENTS
        else:
            self._events = self.UNMERGE_EVENTS
        self._total = len(self._events)
        self._completed = 0

    def ParseOutput(self, output=None):
        """Parse the output of brillo deploy to update a progress bar."""
        stdout = self._stdout.read()
        stderr = self._stderr.read()
        output = stdout + stderr
        for event in self._events:
            self._completed += output.count(event)
        self.ProgressBar(self._completed / self._total)


class _InstallPackageScanner:
    """Finds packages that need to be installed on a target device.

    Scans the sysroot bintree, beginning with a user-provided list of packages,
    to find all packages that need to be installed. If so instructed,
    transitively scans forward (mandatory) and backward (optional) dependencies
    as well. A package will be installed if missing on the target (mandatory
    packages only), or it will be updated if its sysroot version and build time
    are different from the target. Common usage:

        pkg_scanner = _InstallPackageScanner(sysroot)
        pkgs = pkg_scanner.Run(...)
    """

    class VartreeError(Exception):
        """An error in the processing of the installed packages tree."""

    class BintreeError(Exception):
        """An error in the processing of the source binpkgs tree."""

    class PkgInfo:
        """A record containing package information."""

        __slots__ = (
            "cpv",
            "build_time",
            "rdeps_raw",
            "use",
            "rdeps",
            "rev_rdeps",
        )

        def __init__(
            self,
            cpv: package_info.CPV,
            build_time: int,
            rdeps_raw: str,
            use: str,
            rdeps: set = None,
            rev_rdeps: set = None,
        ):
            self.cpv = cpv
            self.build_time = build_time
            self.rdeps_raw = rdeps_raw
            self.use = use
            self.rdeps = set() if rdeps is None else rdeps
            self.rev_rdeps = set() if rev_rdeps is None else rev_rdeps

    # Python snippet for dumping vartree info on the target. Instantiate using
    # _GetVartreeSnippet().
    _GET_VARTREE = """
import json
import os
import portage

# Normalize the path to match what portage will index.
target_root = os.path.normpath('%(root)s')
if not target_root.endswith('/'):
  target_root += '/'
trees = portage.create_trees(target_root=target_root, config_root='/')
vartree = trees[target_root]['vartree']
pkg_info = []
for cpv in vartree.dbapi.cpv_all():
  slot, rdep_raw, build_time, use = vartree.dbapi.aux_get(
      cpv, ('SLOT', 'RDEPEND', 'BUILD_TIME', 'USE'))
  pkg_info.append((cpv, slot, rdep_raw, build_time, use))

print(json.dumps(pkg_info))
"""

    def __init__(self, sysroot: str):
        self.sysroot = sysroot
        # Members containing the sysroot (binpkg) and target (installed) package
        # DB.
        self.target_db = None
        self.binpkgs_db = None
        # Members for managing the dependency resolution work queue.
        self.queue = None
        self.seen = None
        self.listed = None

    @staticmethod
    def _GetCP(cpv: package_info.CPV) -> str:
        """Returns the CP value for a given CPV string."""
        attrs = package_info.SplitCPV(cpv, strict=False)
        if not attrs.cp:
            raise ValueError("Cannot get CP value for %s" % cpv)
        return attrs.cp

    @staticmethod
    def _InDB(cp: str, slot: str, db: Dict[str, Dict[str, PkgInfo]]) -> bool:
        """Returns whether CP and slot are found in a database (if provided)."""
        cp_slots = db.get(cp) if db else None
        return cp_slots is not None and (not slot or slot in cp_slots)

    @staticmethod
    def _AtomStr(cp: str, slot: str) -> str:
        """Returns 'CP:slot' if slot is non-empty, else just 'CP'."""
        return "%s:%s" % (cp, slot) if slot else cp

    @classmethod
    def _GetVartreeSnippet(cls, root: str = "/") -> str:
        """Returns a code snippet for dumping the vartree on the target.

        Args:
            root: The installation root.

        Returns:
            The said code snippet (string) with parameters filled in.
        """
        return cls._GET_VARTREE % {"root": root}

    @classmethod
    def _StripDepAtom(
        cls, dep_atom: str, installed_db: Dict[str, Dict[str, PkgInfo]] = None
    ) -> Tuple[str, str]:
        """Strips a dependency atom and returns a (CP, slot) pair."""
        # TODO(garnold) This is a gross simplification of ebuild dependency
        # semantics, stripping and ignoring various qualifiers (versions, slots,
        # USE flag, negation) and will likely need to be fixed. chromium:447366.

        # Ignore unversioned blockers, leaving them for the user to resolve.
        if dep_atom[0] == "!" and dep_atom[1] not in "<=>~":
            return None, None

        cp = dep_atom
        slot = None
        require_installed = False

        # Versioned blockers should be updated, but only if already installed.
        # These are often used for forcing cascaded updates of multiple
        # packages, so we're treating them as ordinary constraints with hopes
        # that it'll lead to the desired result.
        if cp.startswith("!"):
            cp = cp.lstrip("!")
            require_installed = True

        # Remove USE flags.
        if "[" in cp:
            cp = cp[: cp.index("[")] + cp[cp.index("]") + 1 :]

        # Separate the slot qualifier and strip off subslot binding operator
        if ":" in cp:
            cp, slot = cp.split(":")
            for delim in ("=", "*"):
                slot = slot.split(delim, 1)[0]

        # Strip version wildcards (right), comparators (left).
        cp = cp.rstrip("*")
        cp = cp.lstrip("<=>~")

        # Turn into CP form.
        cp = cls._GetCP(cp)

        if require_installed and not cls._InDB(cp, None, installed_db):
            return None, None

        return cp, slot

    @classmethod
    def _ProcessDepStr(
        cls,
        dep_str: str,
        installed_db: Dict[str, Dict[str, PkgInfo]],
        avail_db: Dict[str, Dict[str, PkgInfo]],
    ) -> set:
        """Resolves and returns a list of dependencies from a dependency string.

        This parses a dependency string and returns a list of package names and
        slots. Other atom qualifiers (version, sub-slot, block) are ignored.
        When resolving disjunctive deps, we include all choices that are fully
        present in |installed_db|. If none is present, we choose an arbitrary
        one that is available.

        Args:
            dep_str: A raw dependency string.
            installed_db: A database of installed packages.
            avail_db: A database of packages available for installation.

        Returns:
            A list of pairs (CP, slot).

        Raises:
            ValueError: the dependencies string is malformed.
        """

        def ProcessSubDeps(
            dep_exp: Set[Tuple[str, str]], disjunct: bool
        ) -> Set[Tuple[str, str]]:
            """Parses and processes a dependency (sub)expression."""
            deps = set()
            default_deps = set()
            sub_disjunct = False
            for dep_sub_exp in dep_exp:
                sub_deps = set()

                if isinstance(dep_sub_exp, (list, tuple)):
                    sub_deps = ProcessSubDeps(dep_sub_exp, sub_disjunct)
                    sub_disjunct = False
                elif sub_disjunct:
                    raise ValueError("Malformed disjunctive operation in deps")
                elif dep_sub_exp == "||":
                    sub_disjunct = True
                elif dep_sub_exp.endswith("?"):
                    raise ValueError("Dependencies contain a conditional")
                else:
                    cp, slot = cls._StripDepAtom(dep_sub_exp, installed_db)
                    if cp:
                        sub_deps = set([(cp, slot)])
                    elif disjunct:
                        raise ValueError("Atom in disjunct ignored")

                # Handle sub-deps of a disjunctive expression.
                if disjunct:
                    # Make the first available choice the default, for use in
                    # case that no option is installed.
                    if (
                        not default_deps
                        and avail_db is not None
                        and all(
                            cls._InDB(cp, slot, avail_db)
                            for cp, slot in sub_deps
                        )
                    ):
                        default_deps = sub_deps

                    # If not all sub-deps are installed, then don't consider
                    # them.
                    if not all(
                        cls._InDB(cp, slot, installed_db)
                        for cp, slot in sub_deps
                    ):
                        sub_deps = set()

                deps.update(sub_deps)

            return deps or default_deps

        try:
            return ProcessSubDeps(portage.dep.paren_reduce(dep_str), False)
        except portage.exception.InvalidDependString as e:
            raise ValueError("Invalid dep string: %s" % e)
        except ValueError as e:
            raise ValueError("%s: %s" % (e, dep_str))

    def _BuildDB(
        self,
        cpv_info: List[CpvInfo],
        process_rdeps: bool,
        process_rev_rdeps: bool,
        installed_db: Dict[str, Dict[str, PkgInfo]] = None,
    ) -> Dict[str, Dict[str, PkgInfo]]:
        """Returns a database of packages given a list of CPV info.

        Args:
            cpv_info: A list of CpvInfos containing package CPV and attributes.
            process_rdeps: Whether to populate forward dependencies.
            process_rev_rdeps: Whether to populate reverse dependencies.
            installed_db: A database of installed packages for filtering
                disjunctive choices against; if None, using own built database.

        Returns:
            A map from CP values to another dictionary that maps slots
            to package attribute tuples. Tuples contain a CPV value
            (string), build time (string), runtime dependencies (set),
            and reverse dependencies (set, empty if not populated).

        Raises:
            ValueError: If more than one CPV occupies a single slot.
        """
        db = {}
        logging.debug("Populating package DB...")
        for cpv, slot, rdeps_raw, build_time, use in cpv_info:
            cp = self._GetCP(cpv)
            cp_slots = db.setdefault(cp, {})
            if slot in cp_slots:
                raise ValueError(
                    "More than one package found for %s"
                    % self._AtomStr(cp, slot)
                )
            logging.debug(
                " %s -> %s, built %s, raw rdeps: %s",
                self._AtomStr(cp, slot),
                cpv,
                build_time,
                rdeps_raw,
            )
            cp_slots[slot] = self.PkgInfo(cpv, build_time, rdeps_raw, use)

        avail_db = db
        if installed_db is None:
            installed_db = db
            avail_db = None

        # Add approximate forward dependencies.
        if process_rdeps:
            logging.debug("Populating forward dependencies...")
            for cp, cp_slots in db.items():
                for slot, pkg_info in cp_slots.items():
                    pkg_info.rdeps.update(
                        self._ProcessDepStr(
                            pkg_info.rdeps_raw, installed_db, avail_db
                        )
                    )
                    logging.debug(
                        " %s (%s) processed rdeps: %s",
                        self._AtomStr(cp, slot),
                        pkg_info.cpv,
                        " ".join(
                            [
                                self._AtomStr(rdep_cp, rdep_slot)
                                for rdep_cp, rdep_slot in pkg_info.rdeps
                            ]
                        ),
                    )

        # Add approximate reverse dependencies (optional).
        if process_rev_rdeps:
            logging.debug("Populating reverse dependencies...")
            for cp, cp_slots in db.items():
                for slot, pkg_info in cp_slots.items():
                    for rdep_cp, rdep_slot in pkg_info.rdeps:
                        to_slots = db.get(rdep_cp)
                        if not to_slots:
                            continue

                        for to_slot, to_pkg_info in to_slots.items():
                            if rdep_slot and to_slot != rdep_slot:
                                continue
                            logging.debug(
                                " %s (%s) added as rev rdep for %s (%s)",
                                self._AtomStr(cp, slot),
                                pkg_info.cpv,
                                self._AtomStr(rdep_cp, to_slot),
                                to_pkg_info.cpv,
                            )
                            to_pkg_info.rev_rdeps.add((cp, slot))

        return db

    def _get_portage_interpreter(
        self, device: remote_access.RemoteDevice
    ) -> str:
        """Get the Python interpreter that should be used for Portage.

        Args:
            device: The device to find the interpreter on.

        Returns:
            The executable that should be used for Python.
        """
        result = device.agent.RemoteSh(
            "ls -1 /usr/lib/python-exec/python*/emerge"
        )
        emerge_bins = [Path(x) for x in result.stdout.splitlines()]
        if not emerge_bins:
            raise self.VartreeError(
                "No suitable Python interpreter found for Portage."
            )

        # If Portage is installed for multiple Python versions, prefer the
        # interpreter with the highest version.
        def _parse_version(name):
            match = re.fullmatch(r"python(\d+)\.(\d+)", name)
            if match:
                return tuple(int(x) for x in match.groups())
            return (0, 0)

        return max((x.parent.name for x in emerge_bins), key=_parse_version)

    def _InitTargetVarDB(
        self,
        device: remote_access.RemoteDevice,
        root: str,
        process_rdeps: bool,
        process_rev_rdeps: bool,
    ) -> None:
        """Initializes a dictionary of packages installed on |device|."""
        get_vartree_script = self._GetVartreeSnippet(root)
        python = self._get_portage_interpreter(device)
        try:
            result = device.agent.RemoteSh(
                [python], remote_sudo=True, input=get_vartree_script
            )
        except cros_build_lib.RunCommandError as e:
            logging.error("Cannot get target vartree:\n%s", e.stderr)
            raise

        try:
            self.target_db = self._BuildDB(
                [CpvInfo(*cpv_info) for cpv_info in json.loads(result.stdout)],
                process_rdeps,
                process_rev_rdeps,
            )
        except ValueError as e:
            raise self.VartreeError(str(e))

    def _InitBinpkgDB(self, process_rdeps: bool) -> None:
        """Initializes a dictionary of binpkgs for updating the target."""
        # Get build root trees; portage indexes require a trailing '/'.
        build_root = os.path.join(self.sysroot, "")
        trees = portage.create_trees(
            target_root=build_root, config_root=build_root
        )
        bintree = trees[build_root]["bintree"]
        binpkgs_info = []
        for cpv in bintree.dbapi.cpv_all():
            slot, rdep_raw, build_time, use = bintree.dbapi.aux_get(
                cpv, ["SLOT", "RDEPEND", "BUILD_TIME", "USE"]
            )
            binpkgs_info.append(CpvInfo(cpv, slot, rdep_raw, build_time, use))

        try:
            self.binpkgs_db = self._BuildDB(
                binpkgs_info, process_rdeps, False, installed_db=self.target_db
            )
        except ValueError as e:
            raise self.BintreeError(str(e))

    def _InitDepQueue(self) -> None:
        """Initializes the dependency work queue."""
        self.queue = set()
        self.seen = {}
        self.listed = set()

    def _EnqDep(self, dep: str, listed: bool, optional: bool) -> bool:
        """Enqueues a dependency if not seen before or if set non-optional."""
        if dep in self.seen and (optional or not self.seen[dep]):
            return False

        self.queue.add(dep)
        self.seen[dep] = optional
        if listed:
            self.listed.add(dep)
        return True

    def _DeqDep(self) -> Tuple[str, bool, bool]:
        """Dequeues and returns a dependency, its listed and optional flags.

        This returns listed packages first, if any are present, to ensure that
        we correctly mark them as such when they are first being processed.
        """
        if self.listed:
            dep = self.listed.pop()
            self.queue.remove(dep)
            listed = True
        else:
            dep = self.queue.pop()
            listed = False

        return dep, listed, self.seen[dep]

    def _FindPackageMatches(self, cpv_pattern: str) -> List[Tuple[str, str]]:
        """Returns list of binpkg (CP, slot) pairs that match |cpv_pattern|.

        This is breaking |cpv_pattern| into its C, P and V components, each of
        which may or may not be present or contain wildcards. It then scans the
        binpkgs database to find all atoms that match these components,
        returning a list of CP and slot qualifier. When the pattern does not
        specify a version, or when a CP has only one slot in the binpkgs
        database, we omit the slot qualifier in the result.

        Args:
            cpv_pattern: A CPV pattern, potentially partial and/or having
                wildcards.

        Returns:
            A list of (CPV, slot) pairs of packages in the binpkgs database that
            match the pattern.
        """
        attrs = package_info.SplitCPV(cpv_pattern, strict=False)
        cp_pattern = os.path.join(attrs.category or "*", attrs.package or "*")
        matches = []
        for cp, cp_slots in self.binpkgs_db.items():
            if not fnmatch.fnmatchcase(cp, cp_pattern):
                continue

            # If no version attribute was given or there's only one slot, omit
            # the slot qualifier.
            if not attrs.version or len(cp_slots) == 1:
                matches.append((cp, None))
            else:
                cpv_pattern = "%s-%s" % (cp, attrs.version)
                for slot, pkg_info in cp_slots.items():
                    if fnmatch.fnmatchcase(pkg_info.cpv, cpv_pattern):
                        matches.append((cp, slot))

        return matches

    def _FindPackage(self, pkg: str) -> Tuple[str, str]:
        """Returns the (CP, slot) pair for a package matching |pkg|.

        Args:
            pkg: Path to a binary package or a (partial) package CPV specifier.

        Returns:
            A (CP, slot) pair for the given package; slot may be None
            (unspecified).

        Raises:
            ValueError: if |pkg| is not a binpkg file nor does it match
            something that's in the bintree.
        """
        if pkg.endswith(".tbz2") and os.path.isfile(pkg):
            package = os.path.basename(os.path.splitext(pkg)[0])
            category = os.path.basename(os.path.dirname(pkg))
            return self._GetCP(os.path.join(category, package)), None

        matches = self._FindPackageMatches(pkg)
        if not matches:
            raise ValueError("No package found for %s" % pkg)

        idx = 0
        if len(matches) > 1:
            # Ask user to pick among multiple matches.
            idx = cros_build_lib.GetChoice(
                "Multiple matches found for %s: " % pkg,
                ["%s:%s" % (cp, slot) if slot else cp for cp, slot in matches],
            )

        return matches[idx]

    def _NeedsInstall(
        self, cpv: str, slot: str, build_time: int, optional: bool
    ) -> Tuple[bool, bool, bool]:
        """Returns whether a package needs to be installed on the target.

        Args:
            cpv: Fully qualified CPV (string) of the package.
            slot: Slot identifier (string).
            build_time: The BUILT_TIME value (string) of the binpkg.
            optional: Whether package is optional on the target.

        Returns:
            A tuple (install, update, use_mismatch) indicating whether to
            |install| the package, whether it is an |update| to an existing
            package, and whether the package's USE flags mismatch the existing
            package.

        Raises:
            ValueError: if slot is not provided.
        """
        # If not checking installed packages, always install.
        if not self.target_db:
            return True, False, False

        cp = self._GetCP(cpv)
        target_pkg_info = self.target_db.get(cp, {}).get(slot)
        if target_pkg_info is not None:
            attrs = package_info.SplitCPV(cpv)
            target_attrs = package_info.SplitCPV(target_pkg_info.cpv)

            def _get_attr_mismatch(
                attr_name: str, new_attr: any, target_attr: any
            ) -> Tuple[str, str, str]:
                """Check if the new and target packages differ for an attribute.

                Args:
                    attr_name: The name of the attribute being checked (string).
                    new_attr: The value of the given attribute for the new
                    package (string).
                    target_attr: The value of the given attribute for the target
                    (existing) package (string).

                Returns:
                    A tuple (attr_name, new_attr, target_attr) composed of the
                    args if there is a mismatch, or None if the values match.
                """
                mismatch = new_attr != target_attr
                if mismatch:
                    return attr_name, new_attr, target_attr

            update_info = _get_attr_mismatch(
                "version", attrs.version, target_attrs.version
            ) or _get_attr_mismatch(
                "build time", build_time, target_pkg_info.build_time
            )

            if update_info:
                attr_name, new_attr, target_attr = update_info
                logging.debug(
                    "Updating %s: %s (%s) different on target (%s)",
                    cp,
                    attr_name,
                    new_attr,
                    target_attr,
                )

                binpkg_pkg_info = self.binpkgs_db.get(cp, {}).get(slot)
                use_mismatch = binpkg_pkg_info.use != target_pkg_info.use
                if use_mismatch:
                    logging.warning(
                        "USE flags for package %s do not match (Existing='%s', "
                        "New='%s').",
                        cp,
                        target_pkg_info.use,
                        binpkg_pkg_info.use,
                    )
                return True, True, use_mismatch

            logging.debug(
                "Not updating %s: already up-to-date (%s, built %s)",
                cp,
                target_pkg_info.cpv,
                target_pkg_info.build_time,
            )
            return False, False, False

        if optional:
            logging.debug(
                "Not installing %s: missing on target but optional", cp
            )
            return False, False, False

        logging.debug(
            "Installing %s: missing on target and non-optional (%s)", cp, cpv
        )
        return True, False, False

    def _ProcessDeps(self, deps: List[str], reverse: bool) -> None:
        """Enqueues dependencies for processing.

        Args:
            deps: List of dependencies to enqueue.
            reverse: Whether these are reverse dependencies.
        """
        if not deps:
            return

        logging.debug(
            "Processing %d %s dep(s)...",
            len(deps),
            "reverse" if reverse else "forward",
        )
        num_already_seen = 0
        for dep in deps:
            if self._EnqDep(dep, False, reverse):
                logging.debug(" Queued dep %s", dep)
            else:
                num_already_seen += 1

        if num_already_seen:
            logging.debug("%d dep(s) already seen", num_already_seen)

    def _ComputeInstalls(
        self, process_rdeps: bool, process_rev_rdeps: bool
    ) -> Tuple[Dict[str, package_info.CPV], bool]:
        """Returns a dict of packages that need to be installed on the target.

        Args:
            process_rdeps: Whether to trace forward dependencies.
            process_rev_rdeps: Whether to trace backward dependencies as well.

        Returns:
            A tuple (installs, warnings_shown) where |installs| is a dictionary
            mapping CP values (string) to tuples containing a CPV (string), a
            slot (string), a boolean indicating whether the package was
            initially listed in the queue, and a boolean indicating whether this
            is an update to an existing package, and |warnings_shown| is a
            boolean indicating whether warnings were shown that might require a
            prompt whether to continue.
        """
        installs = {}
        warnings_shown = False
        while self.queue:
            dep, listed, optional = self._DeqDep()
            cp, required_slot = dep
            if cp in installs:
                logging.debug("Already updating %s", cp)
                continue

            cp_slots = self.binpkgs_db.get(cp, {})
            logging.debug(
                "Checking packages matching %s%s%s...",
                cp,
                " (slot: %s)" % required_slot if required_slot else "",
                " (optional)" if optional else "",
            )
            num_processed = 0
            for slot, pkg_info in cp_slots.items():
                if required_slot and "/" not in slot:
                    logging.debug(
                        " Dropping subslot from required_slot (%s) "
                        "because package does not have a subslot (%s)",
                        required_slot,
                        slot,
                    )
                    required_slot = required_slot.split("/", 1)[0]

                if not required_slot:
                    logging.debug(" Including because no required_slot")
                elif slot == required_slot:
                    logging.debug(
                        " Including because slot (%s) == required_slot (%s)",
                        slot,
                        required_slot,
                    )
                else:
                    logging.debug(
                        " Skipping because slot (%s) != required_slot (%s)",
                        slot,
                        required_slot,
                    )
                    continue

                num_processed += 1
                logging.debug(" Checking %s...", pkg_info.cpv)

                install, update, use_mismatch = self._NeedsInstall(
                    pkg_info.cpv, slot, pkg_info.build_time, optional
                )
                if not install:
                    continue

                installs[cp] = (pkg_info.cpv, slot, listed, update)
                warnings_shown |= use_mismatch

                # Add forward and backward runtime dependencies to queue.
                if process_rdeps:
                    self._ProcessDeps(pkg_info.rdeps, False)
                if process_rev_rdeps:
                    target_pkg_info = self.target_db.get(cp, {}).get(slot)
                    if target_pkg_info:
                        self._ProcessDeps(target_pkg_info.rev_rdeps, True)

            if num_processed == 0:
                logging.warning(
                    "No qualified bintree package corresponding to %s", cp
                )

        return installs, warnings_shown

    def _SortInstalls(self, installs: List[str]) -> List[str]:
        """Returns a sorted list of packages to install.

        Performs a topological sort based on dependencies found in the binary
        package database.

        Args:
            installs: Dictionary of packages to install indexed by CP.

        Returns:
            A list of package CPVs (string).

        Raises:
            ValueError: If dependency graph contains a cycle.
        """
        not_visited = set(installs.keys())
        curr_path = []
        sorted_installs = []

        def SortFrom(cp: str) -> None:
            """Traverses deps recursively, emitting nodes in reverse order."""
            cpv, slot, _, _ = installs[cp]
            if cpv in curr_path:
                raise ValueError(
                    "Dependencies contain a cycle: %s -> %s"
                    % (" -> ".join(curr_path[curr_path.index(cpv) :]), cpv)
                )
            curr_path.append(cpv)
            for rdep_cp, _ in self.binpkgs_db[cp][slot].rdeps:
                if rdep_cp in not_visited:
                    not_visited.remove(rdep_cp)
                    SortFrom(rdep_cp)

            sorted_installs.append(cpv)
            curr_path.pop()

        # So long as there's more packages, keep expanding dependency paths.
        while not_visited:
            SortFrom(not_visited.pop())

        return sorted_installs

    def _EnqListedPkg(self, pkg: str) -> bool:
        """Finds and enqueues a listed package."""
        cp, slot = self._FindPackage(pkg)
        if cp not in self.binpkgs_db:
            raise self.BintreeError(
                "Package %s not found in binpkgs tree" % pkg
            )
        self._EnqDep((cp, slot), True, False)

    def _EnqInstalledPkgs(self) -> None:
        """Enqueues all available binary packages that are already installed."""
        for cp, cp_slots in self.binpkgs_db.items():
            target_cp_slots = self.target_db.get(cp)
            if target_cp_slots:
                for slot in cp_slots.keys():
                    if slot in target_cp_slots:
                        self._EnqDep((cp, slot), True, False)

    def Run(
        self,
        device: remote_access.RemoteDevice,
        root: str,
        listed_pkgs: List[str],
        update: bool,
        process_rdeps: bool,
        process_rev_rdeps: bool,
    ) -> Tuple[List[str], List[str], int, Dict[str, str], bool]:
        """Computes the list of packages that need to be installed on a target.

        Args:
            device: Target handler object.
            root: Package installation root.
            listed_pkgs: Package names/files listed by the user.
            update: Whether to read the target's installed package database.
            process_rdeps: Whether to trace forward dependencies.
            process_rev_rdeps: Whether to trace backward dependencies as well.

        Returns:
            A tuple (sorted, listed, num_updates, install_attrs, warnings_shown)
            where |sorted| is a list of package CPVs (string) to install on the
            target in an order that satisfies their inter-dependencies, |listed|
            the subset that was requested by the user, and |num_updates|
            the number of packages being installed over preexisting
            versions. Note that installation order should be reversed for
            removal, |install_attrs| is a dictionary mapping a package
            CPV (string) to some of its extracted environment attributes, and
            |warnings_shown| is a boolean indicating whether warnings were shown
            that might require a prompt whether to continue.
        """
        if process_rev_rdeps and not process_rdeps:
            raise ValueError(
                "Must processing forward deps when processing rev deps"
            )
        if process_rdeps and not update:
            raise ValueError(
                "Must check installed packages when processing deps"
            )

        if update:
            logging.info("Initializing target intalled packages database...")
            self._InitTargetVarDB(
                device, root, process_rdeps, process_rev_rdeps
            )

        logging.info("Initializing binary packages database...")
        self._InitBinpkgDB(process_rdeps)

        logging.info("Finding listed package(s)...")
        self._InitDepQueue()
        for pkg in listed_pkgs:
            if pkg == "@installed":
                if not update:
                    raise ValueError(
                        "Must check installed packages when updating all of "
                        "them."
                    )
                self._EnqInstalledPkgs()
            else:
                self._EnqListedPkg(pkg)

        logging.info("Computing set of packages to install...")
        installs, warnings_shown = self._ComputeInstalls(
            process_rdeps, process_rev_rdeps
        )

        num_updates = 0
        listed_installs = []
        for cpv, _, listed, isupdate in installs.values():
            if listed:
                listed_installs.append(cpv)
            if isupdate:
                num_updates += 1

        logging.info(
            "Processed %d package(s), %d will be installed, %d are "
            "updating existing packages",
            len(self.seen),
            len(installs),
            num_updates,
        )

        sorted_installs = self._SortInstalls(installs)

        install_attrs = {}
        for pkg in sorted_installs:
            pkg_path = os.path.join(root, portage_util.VDB_PATH, pkg)
            dlc_id, dlc_package = _GetDLCInfo(device, pkg_path, from_dut=True)
            install_attrs[pkg] = {}
            if dlc_id and dlc_package:
                install_attrs[pkg][_DLC_ID] = dlc_id

        return (
            sorted_installs,
            listed_installs,
            num_updates,
            install_attrs,
            warnings_shown,
        )


def _Emerge(
    device: remote_access.RemoteDevice,
    pkg_paths: List[str],
    root: str,
    extra_args: List[str] = None,
) -> str:
    """Copies |pkg_paths| to |device| and emerges them.

    Args:
        device: A ChromiumOSDevice object.
        pkg_paths: Local paths to binary packages.
        root: Package installation root path.
        extra_args: Extra arguments to pass to emerge.

    Raises:
        DeployError: Unrecoverable error during emerge.
    """

    def path_to_name(pkg_path):
        return os.path.basename(pkg_path)

    def path_to_category(pkg_path):
        return os.path.basename(os.path.dirname(pkg_path))

    pkg_names = ", ".join(path_to_name(x) for x in pkg_paths)

    pkgroot = os.path.join(device.work_dir, "packages")
    portage_tmpdir = os.path.join(device.work_dir, "portage-tmp")
    # Clean out the dirs first if we had a previous emerge on the device so as
    # to free up space for this emerge.  The last emerge gets implicitly cleaned
    # up when the device connection deletes its work_dir.
    device.run(
        f"cd {device.work_dir} && "
        f"rm -rf packages portage-tmp && "
        f"mkdir -p portage-tmp packages && "
        f"cd packages && "
        f'mkdir -p {" ".join(set(path_to_category(x) for x in pkg_paths))}',
        shell=True,
        remote_sudo=True,
    )

    logging.info("Use portage temp dir %s", portage_tmpdir)

    # This message is read by BrilloDeployOperation.
    logging.notice("Copying binpkgs to device.")
    for pkg_path in pkg_paths:
        pkg_name = path_to_name(pkg_path)
        logging.info("Copying %s", pkg_name)
        pkg_dir = os.path.join(pkgroot, path_to_category(pkg_path))
        device.CopyToDevice(
            pkg_path, pkg_dir, mode="rsync", remote_sudo=True, compress=False
        )

    # This message is read by BrilloDeployOperation.
    logging.notice("Installing: %s", pkg_names)

    # We set PORTAGE_CONFIGROOT to '/usr/local' because by default all
    # chromeos-base packages will be skipped due to the configuration
    # in /etc/protage/make.profile/package.provided. However, there is
    # a known bug that /usr/local/etc/portage is not setup properly
    # (crbug.com/312041). This does not affect `cros deploy` because
    # we do not use the preset PKGDIR.
    extra_env = {
        "FEATURES": "-sandbox",
        "PKGDIR": pkgroot,
        "PORTAGE_CONFIGROOT": "/usr/local",
        "PORTAGE_TMPDIR": portage_tmpdir,
        "PORTDIR": device.work_dir,
        "CONFIG_PROTECT": "-*",
    }

    # --ignore-built-slot-operator-deps because we don't rebuild everything. It
    # can cause errors, but that's expected with cros deploy since it's just a
    # best effort to prevent developers avoid rebuilding an image every time.
    cmd = [
        "emerge",
        "--usepkg",
        "--ignore-built-slot-operator-deps=y",
        "--root",
        root,
    ] + [os.path.join(pkgroot, *x.split("/")[-2:]) for x in pkg_paths]
    if extra_args:
        cmd.append(extra_args)

    logging.warning(
        "Ignoring slot dependencies! This may break things! e.g. "
        "packages built against the old version may not be able to "
        "load the new .so. This is expected, and you will just need "
        "to build and flash a new image if you have problems."
    )
    try:
        result = device.run(
            cmd,
            extra_env=extra_env,
            remote_sudo=True,
            capture_output=True,
            debug_level=logging.INFO,
        )

        pattern = (
            "A requested package will not be merged because "
            "it is listed in package.provided"
        )
        output = result.stderr.replace("\n", " ").replace("\r", "")
        if pattern in output:
            error = (
                "Package failed to emerge: %s\n"
                "Remove %s from /etc/portage/make.profile/"
                "package.provided/chromeos-base.packages\n"
                "(also see crbug.com/920140 for more context)\n"
                % (pattern, pkg_name)
            )
            cros_build_lib.Die(error)
    except Exception:
        logging.error("Failed to emerge packages %s", pkg_names)
        raise
    else:
        # This message is read by BrilloDeployOperation.
        logging.notice("Packages have been installed.")


def _RestoreSELinuxContext(
    device: remote_access.RemoteDevice, pkgpath: str, root: str
) -> None:
    """Restore SELinux context for files in a given package.

    This reads the tarball from pkgpath, and calls restorecon on device to
    restore SELinux context for files listed in the tarball, assuming those
    files are installed to /

    Args:
        device: a ChromiumOSDevice object
        pkgpath: path to tarball
        root: Package installation root path.
    """
    pkgroot = os.path.join(device.work_dir, "packages")
    pkg_dirname = os.path.basename(os.path.dirname(pkgpath))
    pkgpath_device = os.path.join(
        pkgroot, pkg_dirname, os.path.basename(pkgpath)
    )
    # Testing shows restorecon splits on newlines instead of spaces.
    device.run(
        [
            "cd",
            root,
            "&&",
            "tar",
            "tf",
            pkgpath_device,
            "|",
            "restorecon",
            "-i",
            "-f",
            "-",
        ],
        remote_sudo=True,
    )


def _GetPackagesByCPV(
    cpvs: List[package_info.CPV], strip: bool, sysroot: str
) -> List[str]:
    """Returns paths to binary packages corresponding to |cpvs|.

    Args:
        cpvs: List of CPV components given by package_info.SplitCPV().
        strip: True to run strip_package.
        sysroot: Sysroot path.

    Returns:
        List of paths corresponding to |cpvs|.

    Raises:
        DeployError: If a package is missing.
    """
    packages_dir = None
    if strip:
        try:
            cros_build_lib.run(
                [
                    constants.CHROMITE_SCRIPTS_DIR / "strip_package",
                    "--sysroot",
                    sysroot,
                ]
                + [cpv.cpf for cpv in cpvs]
            )
            packages_dir = _STRIPPED_PACKAGES_DIR
        except cros_build_lib.RunCommandError:
            logging.error(
                "Cannot strip packages %s", " ".join([str(cpv) for cpv in cpvs])
            )
            raise

    paths = []
    for cpv in cpvs:
        path = portage_util.GetBinaryPackagePath(
            cpv.category,
            cpv.package,
            cpv.version,
            sysroot=sysroot,
            packages_dir=packages_dir,
        )
        if not path:
            raise DeployError("Missing package %s." % cpv)
        paths.append(path)

    return paths


def _GetPackagesPaths(pkgs: List[str], strip: bool, sysroot: str) -> List[str]:
    """Returns paths to binary |pkgs|.

    Args:
        pkgs: List of package CPVs string.
        strip: Whether or not to run strip_package for CPV packages.
        sysroot: The sysroot path.

    Returns:
        List of paths corresponding to |pkgs|.
    """
    cpvs = [package_info.SplitCPV(p) for p in pkgs]
    return _GetPackagesByCPV(cpvs, strip, sysroot)


def _Unmerge(
    device: remote_access.RemoteDevice, pkgs: List[str], root: str
) -> None:
    """Unmerges |pkgs| on |device|.

    Args:
        device: A RemoteDevice object.
        pkgs: Package names.
        root: Package installation root path.
    """
    pkg_names = ", ".join(os.path.basename(x) for x in pkgs)
    # This message is read by BrilloDeployOperation.
    logging.notice("Unmerging %s.", pkg_names)
    cmd = ["qmerge", "--yes"]
    # Check if qmerge is available on the device. If not, use emerge.
    if device.run(["qmerge", "--version"], check=False).returncode != 0:
        cmd = ["emerge"]

    cmd += ["--unmerge", "--root", root]
    cmd.extend("f={x}" for x in pkgs)
    try:
        # Always showing the emerge output for clarity.
        device.run(
            cmd,
            capture_output=False,
            remote_sudo=True,
            debug_level=logging.INFO,
        )
    except Exception:
        logging.error("Failed to unmerge packages %s", pkg_names)
        raise
    else:
        # This message is read by BrilloDeployOperation.
        logging.notice("Packages have been uninstalled.")


def _ConfirmDeploy(num_updates: int) -> bool:
    """Returns whether we can continue deployment."""
    if num_updates > _MAX_UPDATES_NUM:
        logging.warning(_MAX_UPDATES_WARNING)
        return cros_build_lib.BooleanPrompt(default=False)

    return True


def _ConfirmUpdateDespiteWarnings() -> bool:
    """Returns whether we can continue updating despite warnings."""
    logging.warning("Continue despite prior warnings?")
    return cros_build_lib.BooleanPrompt(default=False)


def _EmergePackages(
    pkgs: List[str],
    device: remote_access.RemoteDevice,
    strip: bool,
    sysroot: str,
    root: str,
    board: str,
    emerge_args: List[str],
) -> None:
    """Call _Emerge for each package in pkgs."""
    if device.IsSELinuxAvailable():
        enforced = device.IsSELinuxEnforced()
        if enforced:
            device.run(["setenforce", "0"])
    else:
        enforced = False

    dlc_deployed = False
    # This message is read by BrilloDeployOperation.
    logging.info("Preparing local packages for transfer.")
    pkg_paths = _GetPackagesPaths(pkgs, strip, sysroot)
    # Install all the packages in one pass so inter-package blockers work.
    _Emerge(device, pkg_paths, root, extra_args=emerge_args)
    logging.info("Updating SELinux settings & DLC images.")
    for pkg_path in pkg_paths:
        if device.IsSELinuxAvailable():
            _RestoreSELinuxContext(device, pkg_path, root)

        dlc_id, dlc_package = _GetDLCInfo(device, pkg_path, from_dut=False)
        if dlc_id and dlc_package:
            _DeployDLCImage(device, sysroot, board, dlc_id, dlc_package)
            dlc_deployed = True

    if dlc_deployed:
        # Clean up empty directories created by emerging DLCs.
        device.run(
            [
                "test",
                "-d",
                "/build/rootfs",
                "&&",
                "rmdir",
                "--ignore-fail-on-non-empty",
                "/build/rootfs",
                "/build",
            ],
            check=False,
        )

    if enforced:
        device.run(["setenforce", "1"])

    # Restart dlcservice so it picks up the newly installed DLC modules (in case
    # we installed new DLC images).
    if dlc_deployed:
        device.run(["restart", "dlcservice"])


def _UnmergePackages(
    pkgs: List[str],
    device: remote_access.RemoteDevice,
    root: str,
    pkgs_attrs: Dict[str, List[str]],
) -> str:
    """Call _Unmege for each package in pkgs."""
    dlc_uninstalled = False
    _Unmerge(device, pkgs, root)
    logging.info("Cleaning up DLC images.")
    for pkg in pkgs:
        if _UninstallDLCImage(device, pkgs_attrs[pkg]):
            dlc_uninstalled = True

    # Restart dlcservice so it picks up the uninstalled DLC modules (in case we
    # uninstalled DLC images).
    if dlc_uninstalled:
        device.run(["restart", "dlcservice"])


def _UninstallDLCImage(
    device: remote_access.RemoteDevice, pkg_attrs: Dict[str, List[str]]
):
    """Uninstall a DLC image."""
    if _DLC_ID in pkg_attrs:
        dlc_id = pkg_attrs[_DLC_ID]
        logging.notice("Uninstalling DLC image for %s", dlc_id)

        device.run(["dlcservice_util", "--uninstall", "--id=%s" % dlc_id])
        return True
    else:
        logging.debug("DLC_ID not found in package")
        return False


def _DeployDLCImage(
    device: remote_access.RemoteDevice,
    sysroot: str,
    board: str,
    dlc_id: str,
    dlc_package: str,
):
    """Deploy (install and mount) a DLC image.

    Args:
        device: A device object.
        sysroot: The sysroot path.
        board: Board to use.
        dlc_id: The DLC ID.
        dlc_package: The DLC package name.
    """
    # Requires `sudo_rm` because installations of files are running with sudo.
    with osutils.TempDir(sudo_rm=True) as tempdir:
        temp_rootfs = Path(tempdir)
        # Build the DLC image if the image is outdated or doesn't exist.
        dlc_lib.InstallDlcImages(
            sysroot=sysroot, rootfs=temp_rootfs, dlc_id=dlc_id, board=board
        )

        logging.debug("Uninstall DLC %s if it is installed.", dlc_id)
        try:
            device.run(["dlcservice_util", "--uninstall", "--id=%s" % dlc_id])
        except cros_build_lib.RunCommandError as e:
            logging.info(
                "Failed to uninstall DLC:%s. Continue anyway.", e.stderr
            )
        except Exception:
            logging.error("Failed to uninstall DLC.")
            raise

        src_dlc_dir = os.path.join(
            sysroot,
            dlc_lib.DLC_BUILD_DIR,
            ".",
            dlc_id,
        )
        if not os.path.exists(src_dlc_dir):
            src_dlc_dir = os.path.join(
                sysroot,
                dlc_lib.DLC_BUILD_DIR_SCALED,
                ".",
                dlc_id,
            )

        # Deploy the metadata entry to compressed metadata on device.
        logging.notice("Setting the DLC metadata for %s", dlc_id)
        metadata = dlc_lib.DlcMetadata.LoadSrcMetadata(src_dlc_dir)
        device.run(
            [dlc_lib.DLC_METADATA_UTIL, "--set", f"--id={dlc_id}"],
            input=json.dumps(metadata),
            check=False,
        )

        # Copy metadata to device.
        # TODO(b/290961240): To be removed once the transition to compressed
        # metadata is complete.
        dest_meta_dir = Path("/") / dlc_lib.DLC_META_DIR / dlc_id / dlc_package
        src_meta_dir = os.path.join(
            src_dlc_dir,
            dlc_package,
            dlc_lib.DLC_TMP_META_DIR,
        )
        device.CopyToDevice(
            src_meta_dir + "/",
            dest_meta_dir,
            mode="rsync",
            recursive=True,
            remote_sudo=True,
            mkpath=True,
        )

        logging.notice("Deploy the DLC image for %s", dlc_id)
        dlc_img_path_src = os.path.join(
            src_dlc_dir,
            dlc_package,
            dlc_lib.DLC_IMAGE,
        )

        # Copy the image to the deploy directory on device and let
        # dlcservice load it to the DLC slots.
        dlc_deploy_dir = os.path.join(
            constants.STATEFUL_DIR, dlc_lib.DLC_DEPLOY_DIR
        )
        device.CopyToDevice(
            dlc_img_path_src,
            dlc_deploy_dir,
            mode="rsync",
            chmod="u+rwX,go+rX,go-w",
            chown="dlcservice:dlcservice",
            relative=True,
        )
        # Stop and start dlcservice to reload the metadata and to make sure the
        # dlcservice is running.
        device.run(["stop", "dlcservice"], check=False)
        device.run(["start", "dlcservice"])
        try:
            device.run(["dlcservice_util", "--deploy", f"--id={dlc_id}"])
        except cros_build_lib.RunCommandError as e:
            # Keep this as a fallback, so that non-LVM DLC deploy still works on
            # previous builds that not yet have `--deploy` option in
            # dlcservice_util.
            # TODO(b/277155797): Drop the fallback after M118 reaches stable.
            logging.warning(
                "The device is unable to handle deploying DLC=%s due to %s, "
                "setting up the DLC slots from the host side.",
                dlc_id,
                e,
            )
            dlc_deployed_img = os.path.join(
                dlc_deploy_dir, dlc_id, dlc_package, dlc_lib.DLC_IMAGE
            )
            dlc_img_path_dest = [
                os.path.join(_DLC_INSTALL_ROOT, dlc_id, dlc_package, slot)
                for slot in ("dlc_a", "dlc_b")
            ]
            # Create directories for DLC images.
            device.mkdir(dlc_img_path_dest)
            # Copy images to the destination directories.
            for dest in dlc_img_path_dest:
                device.run(
                    [
                        "cp",
                        dlc_deployed_img,
                        os.path.join(dest, dlc_lib.DLC_IMAGE),
                    ]
                )

            # Set the proper perms and ownership so dlcservice can access the
            # image.
            device.run(["chmod", "-R", "u+rwX,go+rX,go-w", _DLC_INSTALL_ROOT])
            device.run(
                ["chown", "-R", "dlcservice:dlcservice", _DLC_INSTALL_ROOT]
            )

        # TODO(kimjae): Make this generic so it recomputes all the DLCs + copies
        #   over a fresh list of dm-verity digests instead of appending and
        #   keeping the stale digests when developers are testing.

        # Copy the LoadPin dm-verity digests to device.
        _DeployDLCLoadPin(temp_rootfs, device)


def _DeployDLCLoadPin(
    rootfs: os.PathLike, device: remote_access.RemoteDevice
) -> None:
    """Deploy DLC LoadPin from temp rootfs to device.

    Args:
        rootfs: Path to rootfs.
        device: A device object.
    """
    loadpin = dlc_lib.DLC_LOADPIN_TRUSTED_VERITY_DIGESTS
    dst_loadpin = Path("/") / dlc_lib.DLC_META_DIR / loadpin
    src_loadpin = rootfs / dlc_lib.DLC_META_DIR / loadpin
    if src_loadpin.exists():
        digests = set(osutils.ReadFile(src_loadpin).splitlines())
        digests.discard(dlc_lib.DLC_LOADPIN_FILE_HEADER)
        try:
            device_digests = set(device.CatFile(dst_loadpin).splitlines())
            device_digests.discard(dlc_lib.DLC_LOADPIN_FILE_HEADER)
            digests.update(device_digests)
        except remote_access.CatFileError:
            pass

        with tempfile.NamedTemporaryFile(dir=rootfs) as f:
            osutils.WriteFile(f.name, dlc_lib.DLC_LOADPIN_FILE_HEADER + "\n")
            osutils.WriteFile(f.name, "\n".join(digests) + "\n", mode="a")
            device.CopyToDevice(
                f.name, dst_loadpin, mode="rsync", remote_sudo=True
            )


def _GetDLCInfo(
    device: remote_access.RemoteDevice, pkg_path: str, from_dut: bool
) -> Tuple[str, str]:
    """Returns information of a DLC given its package path.

    Args:
        device: commandline.Device object; None to use the default device.
        pkg_path: path to the package.
        from_dut: True if extracting DLC info from DUT, False if extracting DLC
            info from host.

    Returns:
        A tuple (dlc_id, dlc_package).
    """
    environment_content = ""
    if from_dut:
        # On DUT, |pkg_path| is the directory which contains environment file.
        environment_path = os.path.join(pkg_path, _ENVIRONMENT_FILENAME)
        try:
            environment_data = device.CatFile(
                environment_path, max_size=None, encoding=None
            )
        except remote_access.CatFileError:
            # The package is not installed on DUT yet. Skip extracting info.
            return None, None
    else:
        # On host, pkg_path is tbz2 file which contains environment file.
        # Extract the metadata of the package file.
        data = portage.xpak.tbz2(pkg_path).get_data()
        environment_data = data[_ENVIRONMENT_FILENAME.encode("utf-8")]

    # Extract the environment metadata.
    environment_content = bz2.decompress(environment_data)

    with tempfile.NamedTemporaryFile() as f:
        # Dumps content into a file so we can use osutils.SourceEnvironment.
        path = os.path.realpath(f.name)
        osutils.WriteFile(path, environment_content, mode="wb")
        content = osutils.SourceEnvironment(
            path, (_DLC_ID, _DLC_PACKAGE, _DLC_ENABLED)
        )

        dlc_enabled = content.get(_DLC_ENABLED)
        if dlc_enabled is not None and (
            dlc_enabled is False or str(dlc_enabled) == "false"
        ):
            logging.info("Installing DLC in rootfs.")
            return None, None
        return content.get(_DLC_ID), content.get(_DLC_PACKAGE)


def Deploy(
    device: remote_access.RemoteDevice,
    packages: List[str],
    board: str = None,
    emerge: bool = True,
    update: bool = False,
    deep: bool = False,
    deep_rev: bool = False,
    clean_binpkg: bool = True,
    root: str = "/",
    strip: bool = True,
    emerge_args: List[str] = None,
    ssh_private_key: str = None,
    ping: bool = True,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """Deploys packages to a device.

    Args:
        device: commandline.Device object; None to use the default device.
        packages: List of packages (strings) to deploy to device.
        board: Board to use; None to automatically detect.
        emerge: True to emerge package, False to unmerge.
        update: Check installed version on device.
        deep: Install dependencies also. Implies |update|.
        deep_rev: Install reverse dependencies. Implies |deep|.
        clean_binpkg: Clean outdated binary packages.
        root: Package installation root path.
        strip: Run strip_package to filter out preset paths in the package.
        emerge_args: Extra arguments to pass to emerge.
        ssh_private_key: Path to an SSH private key file; None to use test keys.
        ping: True to ping the device before trying to connect.
        force: Ignore confidence checks and prompts.
        dry_run: Print deployment plan but do not deploy anything.

    Raises:
        ValueError: Invalid parameter or parameter combination.
        DeployError: Unrecoverable failure during deploy.
    """
    if deep_rev:
        deep = True
    if deep:
        update = True

    if not packages:
        raise DeployError("No packages provided, nothing to deploy.")

    if update and not emerge:
        raise ValueError("Cannot update and unmerge.")

    if device:
        hostname, username, port = device.hostname, device.username, device.port
    else:
        hostname, username, port = None, None, None

    lsb_release = None
    sysroot = None
    try:
        # Somewhat confusing to clobber, but here we are.
        # pylint: disable=redefined-argument-from-local
        with remote_access.ChromiumOSDeviceHandler(
            hostname,
            port=port,
            username=username,
            private_key=ssh_private_key,
            base_dir=_DEVICE_BASE_DIR,
            ping=ping,
        ) as device:
            lsb_release = device.lsb_release

            board = cros_build_lib.GetBoard(
                device_board=device.board, override_board=board
            )
            if not force and board != device.board:
                raise DeployError(
                    "Device (%s) is incompatible with board %s. Use "
                    "--force to deploy anyway." % (device.board, board)
                )

            sysroot = build_target_lib.get_default_sysroot_path(board)

            # Don't bother trying to clean for unmerges.  We won't use the local
            # db, and it just slows things down for the user.
            if emerge and clean_binpkg:
                logging.notice(
                    "Cleaning outdated binary packages from %s", sysroot
                )
                portage_util.CleanOutdatedBinaryPackages(sysroot)

            # Remount rootfs as writable if necessary.
            if not device.MountRootfsReadWrite():
                raise DeployError(
                    "Cannot remount rootfs as read-write. Exiting."
                )

            # Obtain list of packages to upgrade/remove.
            pkg_scanner = _InstallPackageScanner(sysroot)
            (
                pkgs,
                listed,
                num_updates,
                pkgs_attrs,
                warnings_shown,
            ) = pkg_scanner.Run(device, root, packages, update, deep, deep_rev)
            if emerge:
                action_str = "emerge"
            else:
                pkgs.reverse()
                action_str = "unmerge"

            if not pkgs:
                logging.notice("No packages to %s", action_str)
                return

            # Warn when the user installs & didn't `cros workon start`.
            if emerge:
                all_workon = workon_helper.WorkonHelper(sysroot).ListAtoms(
                    use_all=True
                )
                worked_on_cps = workon_helper.WorkonHelper(sysroot).ListAtoms()
                for package in listed:
                    cp = package_info.SplitCPV(package).cp
                    if cp in all_workon and cp not in worked_on_cps:
                        logging.warning(
                            "Are you intentionally deploying unmodified "
                            "packages, or did you forget to run "
                            "`cros workon --board=$BOARD start %s`?",
                            cp,
                        )

            logging.notice("These are the packages to %s:", action_str)
            for i, pkg in enumerate(pkgs):
                logging.notice(
                    "%s %d) %s", "*" if pkg in listed else " ", i + 1, pkg
                )

            if dry_run or not _ConfirmDeploy(num_updates):
                return

            if (
                warnings_shown
                and not force
                and not _ConfirmUpdateDespiteWarnings()
            ):
                return

            # Select function (emerge or unmerge) and bind args.
            if emerge:
                func = functools.partial(
                    _EmergePackages,
                    pkgs,
                    device,
                    strip,
                    sysroot,
                    root,
                    board,
                    emerge_args,
                )
            else:
                func = functools.partial(
                    _UnmergePackages, pkgs, device, root, pkgs_attrs
                )

            # Call the function with the progress bar or with normal output.
            if command.UseProgressBar():
                op = BrilloDeployOperation(emerge)
                op.Run(func, log_level=logging.DEBUG)
            else:
                func()

            if device.IsSELinuxAvailable():
                if sum(x.count("selinux-policy") for x in pkgs):
                    logging.warning(
                        "Deploying SELinux policy will not take effect until "
                        "reboot. SELinux policy is loaded by init. Also, "
                        "changing the security contexts (labels) of a file "
                        "will require building a new image and flashing the "
                        "image onto the device."
                    )

            # This message is read by BrilloDeployOperation.
            logging.warning(
                "Please restart any updated services on the device, "
                "or just reboot it."
            )
    except Exception:
        if lsb_release:
            lsb_entries = sorted(lsb_release.items())
            logging.info(
                "Following are the LSB version details of the device:\n%s",
                "\n".join("%s=%s" % (k, v) for k, v in lsb_entries),
            )
        raise
