# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for workon_helper."""

import collections
import os
from pathlib import Path
from typing import Iterable

from chromite.lib import build_target_lib
from chromite.lib import cros_test_lib
from chromite.lib import dependency_graph
from chromite.lib import depgraph
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import sysroot_lib
from chromite.lib import unittest_lib
from chromite.lib import workon_helper
from chromite.lib.parser import package_info
from chromite.utils import os_util


BOARD = "this_is_a_board_name"

WORKON_PACKAGE_NAME = "my-package"
WORKON_ONLY_ATOM = f"sys-apps/{WORKON_PACKAGE_NAME}"
VERSIONED_WORKON_ATOM = "sys-apps/versioned-package"
NOT_WORKON_ATOM = "sys-apps/not-workon-package"

HOST_ATOM = "host-apps/my-package"

WORKED_ON_PATTERN = "=%s-9999"
MASKED_PATTERN = "<%s-9999"

OVERLAY_ROOT_DIR = "overlays"
BOARD_OVERLAY_DIR = "overlay-" + BOARD
HOST_OVERLAY_DIR = "overlay-host"


InstalledPackageMock = collections.namedtuple(
    "InstalledPackage", ("category", "package")
)


class WorkonHelperTest(cros_test_lib.MockTempDirTestCase):
    """Tests for chromite.lib.workon_helper."""

    def _MakeFakeEbuild(self, overlay, atom, version, is_workon=True):
        """Makes fake ebuilds with minimal real content.

        Args:
            overlay: overlay to put this ebuild in.
            atom: 'category/package' string in the familiar portage sense.
            version: version suffix for the ebuild (e.g. '9999').
            is_workon: True iff this should be a workon-able package (i.e.
                inherits cros-workon).
        """
        category, package = atom.split("/", 1)
        ebuild_path = os.path.join(
            self._mock_srcdir,
            OVERLAY_ROOT_DIR,
            overlay,
            category,
            package,
            "%s-%s.ebuild" % (package, version),
        )
        content = 'KEYWORDS="~*"\n'
        if is_workon:
            content += "inherit cros-workon\n"
        osutils.WriteFile(ebuild_path, content, makedirs=True)
        if atom not in self._valid_atoms:
            self._valid_atoms[atom] = ebuild_path

    def _MockFindOverlays(self, sysroot):
        """Mocked out version of portage_util.FindOverlays().

        Args:
            sysroot: path to sysroot.

        Returns:
            List of paths to overlays.
        """
        if sysroot == "/":
            return [os.path.join(self._overlay_root, HOST_OVERLAY_DIR)]
        return [os.path.join(self._overlay_root, BOARD_OVERLAY_DIR)]

    def _MockFindEbuildForPackage(self, package, _board=None, **_kwargs):
        """Mocked out version of portage_util.FindEbuildForPackage().

        Args:
            package: complete atom string.
            _board: ignored, see documentation in portage_util.  We
                intentionally create atoms with different names for hosts/boards
                so that we can ignore this distinction here.
            _kwargs: ignored, see documentation in portage_util.

        Returns:
            An ebuild if we have previously created this atom.
        """
        return self._valid_atoms.get(package, None)

    def setUp(self):
        """Set up a test environment."""
        self._valid_atoms = {}
        self._mock_srcdir = os.path.join(self.tempdir, "src")
        workon_dir = workon_helper.GetWorkonPath(source_root=self._mock_srcdir)
        self._sysroot = os.path.join(self.tempdir, "sysroot")
        osutils.SafeMakedirs(self._sysroot)
        osutils.SafeMakedirs(self._mock_srcdir)
        for system in ("host", BOARD):
            osutils.Touch(os.path.join(workon_dir, system), makedirs=True)
            osutils.Touch(
                os.path.join(workon_dir, system + ".mask"), makedirs=True
            )
        self._overlay_root = os.path.join(self._mock_srcdir, OVERLAY_ROOT_DIR)
        # Make a bunch of packages to work on.
        self._MakeFakeEbuild(BOARD_OVERLAY_DIR, WORKON_ONLY_ATOM, "9999")
        self._MakeFakeEbuild(BOARD_OVERLAY_DIR, VERSIONED_WORKON_ATOM, "9999")
        self._MakeFakeEbuild(
            BOARD_OVERLAY_DIR, VERSIONED_WORKON_ATOM, "0.0.1-r1"
        )
        self._MakeFakeEbuild(
            BOARD_OVERLAY_DIR, NOT_WORKON_ATOM, "0.0.1-r1", is_workon=False
        )
        self._MakeFakeEbuild(HOST_OVERLAY_DIR, HOST_ATOM, "9999")
        # Patch the modules interfaces to the rest of the world.
        self.PatchObject(
            portage_util, "FindEbuildForPackage", self._MockFindEbuildForPackage
        )

        # Assume only versioned-packages is installed.
        self.PatchObject(
            portage_util.PortageDB,
            "InstalledPackages",
            return_value=[
                InstalledPackageMock("sys-apps", "versioned-package")
            ],
        )
        # Turn off behavior related to adding repositories to minilayouts.
        # TODO(b/208444115): Add tests for the full workflow. Ideally will be
        #  able to create a manifest and ebuilds usable with `ebuild info`.
        self.PatchObject(
            workon_helper.WorkonHelper, "_AddProjectsToPartialManifests"
        )
        self.PatchObject(
            portage_util,
            "GetRepositoryForEbuild",
            return_value=(
                portage_util.RepositoryInfoTuple(
                    srcdir=self._mock_srcdir, project="workon-project"
                ),
            ),
        )
        pkgs = [
            package_info.parse(f"{WORKON_ONLY_ATOM}-9999"),
            package_info.parse(f"{VERSIONED_WORKON_ATOM}-0.0.1-r1"),
            package_info.parse(f"{NOT_WORKON_ATOM}-0.0.1-r1"),
        ]
        nodes = [
            dependency_graph.PackageNode(
                x, self._sysroot, src_paths=[self._valid_atoms[x.atom]]
            )
            for x in pkgs
        ]
        graph = dependency_graph.DependencyGraph(nodes, self._sysroot, pkgs)
        self.PatchObject(
            depgraph, "get_build_target_dependency_graph", return_value=graph
        )
        # We do a lot of work as root. Pretend to be root so that we never have
        # to call sudo.
        self.PatchObject(os_util, "is_root_user", return_value=True)

    def CreateHelper(self, host=False):
        """Creates and returns a WorkonHelper object.

        Args:
            host: If True, create the WorkonHelper for the host.
        """
        if host:
            overlay = os.path.join(self._overlay_root, HOST_OVERLAY_DIR)
            name = "host"
            self.PatchObject(
                build_target_lib,
                "get_default_sysroot_path",
                return_value=self._sysroot,
            )
        else:
            overlay = os.path.join(self._overlay_root, BOARD_OVERLAY_DIR)
            name = BOARD

        # Setup the sysroots.
        sysroot_lib.Sysroot(self._sysroot).WriteConfig(
            'ARCH="amd64"\nPORTDIR_OVERLAY="%s"' % overlay
        )
        # make.conf needs to exist to correctly read back config.
        unittest_lib.create_stub_make_conf(self._sysroot)

        # Create helpers for the host or board.
        return workon_helper.WorkonHelper(
            self._sysroot, name, src_root=self._mock_srcdir
        )

    def assertWorkingOn(self, atoms, system=BOARD):
        """Assert that the workon/mask files mention the given atoms.

        Args:
            atoms: list of atom strings (e.g. ['sys-apps/dbus', 'foo-cat/bar']).
            system: string system to consider (either 'host' or a board name).
        """
        workon_path = workon_helper.GetWorkonPath(
            source_root=self._mock_srcdir, sub_path=system
        )
        mask_path = workon_path + ".mask"

        if atoms:
            self.assertEqual(
                sorted([WORKED_ON_PATTERN % atom for atom in atoms]),
                sorted(osutils.ReadFile(workon_path).splitlines()),
            )
            self.assertEqual(
                sorted([MASKED_PATTERN % atom for atom in atoms]),
                sorted(osutils.ReadFile(mask_path).splitlines()),
            )
        else:
            self.assertNotExists(workon_path)
            self.assertNotExists(mask_path)

    def testGetWorkonAtomToFailForMissingPackage(self):
        """Check that package exists."""
        expected_msg = "error looking up package doesnot/exist"
        with self.assertRaisesRegex(workon_helper.WorkonError, expected_msg):
            helper = self.CreateHelper()
            helper.GetWorkonAtom("doesnot/exist")

    def testGetWorkonAtomToFailForNonWorkonPackage(self):
        """Check that package is workon."""
        expected_msg = (
            f"run 'cros workon --board {BOARD} start"
            f" {VERSIONED_WORKON_ATOM}' first!"
        )
        with self.assertRaisesRegex(workon_helper.WorkonError, expected_msg):
            helper = self.CreateHelper()
            helper.GetWorkonAtom(VERSIONED_WORKON_ATOM)

    def testGetWorkonAtomToReturnAtomForPackage(self):
        """Return canonical atom for the workon package."""
        helper = self.CreateHelper()
        helper.StartWorkingOnPackages([WORKON_ONLY_ATOM])

        atom = helper.GetWorkonAtom(WORKON_PACKAGE_NAME)
        self.assertEqual(atom, WORKON_ONLY_ATOM)

    def testInstallShouldFailForHostSysroot(self):
        """Check that the target is not host before install."""
        expected_msg = "cannot run for host. expecting board target."
        with self.assertRaisesRegex(workon_helper.WorkonError, expected_msg):
            helper = self.CreateHelper(host=True)
            helper.InstallPackage(WORKON_ONLY_ATOM)

    def testInstallShouldFailForMissingPackage(self):
        """Check if the package exists before install."""
        expected_msg = "error looking up package doesnot/exist"
        with self.assertRaisesRegex(workon_helper.WorkonError, expected_msg):
            helper = self.CreateHelper()
            helper.InstallPackage("doesnot/exist")

    def testInstallShouldFailForNotWorkonPackage(self):
        """Check if the package is workon before install."""
        expected_msg = (
            f"run 'cros workon --board {BOARD} start"
            f" {VERSIONED_WORKON_ATOM}' first!"
        )
        with self.assertRaisesRegex(workon_helper.WorkonError, expected_msg):
            helper = self.CreateHelper()
            helper.InstallPackage(VERSIONED_WORKON_ATOM)

    def testInstallToRunEmergeForWorkonPackage(self):
        """Install should run the correct emerge."""
        helper = self.CreateHelper()
        helper.StartWorkingOnPackages([WORKON_ONLY_ATOM])

        rc_mock = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc_mock.SetDefaultCmdResult()
        helper.InstallPackage(WORKON_ONLY_ATOM)

        rc_mock.assertCommandCalled(
            [f"emerge-{BOARD}", "--nodeps", WORKON_ONLY_ATOM], print_cmd=True
        )

    def testBuildShouldFailForHostSysroot(self):
        """Check that the target is not host before build."""
        expected_msg = "cannot run for host. expecting board target."
        with self.assertRaisesRegex(workon_helper.WorkonError, expected_msg):
            helper = self.CreateHelper(host=True)
            helper.BuildPackage(WORKON_ONLY_ATOM)

    def testBuildShouldFailForMissingPackage(self):
        """Check if the package exists before build."""
        expected_msg = "error looking up package doesnot/exist"
        with self.assertRaisesRegex(workon_helper.WorkonError, expected_msg):
            helper = self.CreateHelper()
            helper.BuildPackage("doesnot/exist")

    def testBuildShouldFailForNotWorkonPackage(self):
        """Check if the package is workon before build."""
        expected_msg = (
            f"run 'cros workon --board {BOARD} start"
            f" {VERSIONED_WORKON_ATOM}' first!"
        )
        with self.assertRaisesRegex(workon_helper.WorkonError, expected_msg):
            helper = self.CreateHelper()
            helper.BuildPackage(VERSIONED_WORKON_ATOM)

    def testBuildPackageToRunEbuildTestWithClean(self):
        """Check that build runs clean test."""
        helper = self.CreateHelper()
        helper.StartWorkingOnPackages([WORKON_ONLY_ATOM])

        tested_marker = (
            Path(self._sysroot)
            / "tmp"
            / "portage"
            / f"{WORKON_ONLY_ATOM}-9999"
            / ".tested"
        )
        osutils.Touch(tested_marker, makedirs=True)

        rc_mock = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc_mock.SetDefaultCmdResult()

        helper.BuildPackage(
            WORKON_ONLY_ATOM,
            clean=True,
            test=True,
        )

        rc_mock.assertCommandCalled(
            [
                f"ebuild-{BOARD}",
                os.path.join(
                    self._overlay_root,
                    BOARD_OVERLAY_DIR,
                    WORKON_ONLY_ATOM,
                    "my-package-9999.ebuild",
                ),
                "clean",
                "test",
            ],
            print_cmd=True,
            extra_env={
                "FEATURES": "-noauto test",
                "SANDBOX_WRITE": "~/chromiumos",
                "CROS_WORKON_INPLACE": "1",
            },
        )
        self.assertNotExists(tested_marker)

    def testBuildPackageToRunEbuildCompileWithClean(self):
        """Check that build runs compile."""
        helper = self.CreateHelper()
        helper.StartWorkingOnPackages([WORKON_ONLY_ATOM])

        compiled_marker = (
            Path(self._sysroot)
            / "tmp"
            / "portage"
            / f"{WORKON_ONLY_ATOM}-9999"
            / ".compiled"
        )
        osutils.Touch(compiled_marker, makedirs=True)

        rc_mock = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc_mock.SetDefaultCmdResult()

        helper.BuildPackage(WORKON_ONLY_ATOM, clean=True, test=False)

        rc_mock.assertCommandCalled(
            [
                f"ebuild-{BOARD}",
                os.path.join(
                    self._overlay_root,
                    BOARD_OVERLAY_DIR,
                    WORKON_ONLY_ATOM,
                    "my-package-9999.ebuild",
                ),
                "clean",
                "compile",
            ],
            print_cmd=True,
            extra_env={
                "FEATURES": "-noauto",
                "SANDBOX_WRITE": "~/chromiumos",
                "CROS_WORKON_INPLACE": "1",
            },
        )

    def testBuildPackageCompileToCleanIfWorkdirIsNotSymlink(self):
        """Check that compile runs with clean if workdir is not symlink."""
        helper = self.CreateHelper()
        helper.StartWorkingOnPackages([WORKON_ONLY_ATOM])

        workpath = (
            Path(self._sysroot) / "tmp" / "portage" / f"{WORKON_ONLY_ATOM}-9999"
        )
        (workpath / "work" / WORKON_ONLY_ATOM).mkdir(parents=True)

        rc_mock = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc_mock.SetDefaultCmdResult()

        helper.BuildPackage(WORKON_ONLY_ATOM, clean=False, test=False)

        rc_mock.assertCommandCalled(
            [
                f"ebuild-{BOARD}",
                os.path.join(
                    self._overlay_root,
                    BOARD_OVERLAY_DIR,
                    WORKON_ONLY_ATOM,
                    "my-package-9999.ebuild",
                ),
                "clean",
                "compile",
            ],
            print_cmd=True,
            extra_env={
                "FEATURES": "-noauto",
                "SANDBOX_WRITE": "~/chromiumos",
                "CROS_WORKON_INPLACE": "1",
            },
        )

    def testScrubShouldFailForHostSysroot(self):
        """Check that the target is not host before scrub."""
        expected_msg = "cannot run for host. expecting board target."
        with self.assertRaisesRegex(workon_helper.WorkonError, expected_msg):
            helper = self.CreateHelper(host=True)
            helper.ScrubPackage(WORKON_ONLY_ATOM)

    def testScrubShouldFailForMissingPackage(self):
        """Check if the package exists for scrub."""
        expected_msg = "error looking up package doesnot/exist"
        with self.assertRaisesRegex(workon_helper.WorkonError, expected_msg):
            helper = self.CreateHelper()
            helper.ScrubPackage("doesnot/exist")

    def testScrubShouldFailForNotWorkonPackage(self):
        """Check if the package is workon for scrub."""
        expected_msg = (
            f"run 'cros workon --board {BOARD} start"
            f" {VERSIONED_WORKON_ATOM}' first!"
        )
        with self.assertRaisesRegex(workon_helper.WorkonError, expected_msg):
            helper = self.CreateHelper()
            helper.ScrubPackage(VERSIONED_WORKON_ATOM)

    def testScrubShouldCleanAtomSourceDirectory(self):
        """Check if the package is workon."""
        helper = self.CreateHelper()
        helper.StartWorkingOnPackages([WORKON_ONLY_ATOM])

        rc_mock = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc_mock.AddCmdResult(["git", "clean", "-dxf"], stdout="")

        helper.ScrubPackage(WORKON_ONLY_ATOM)

        rc_mock.assertCommandCalled(
            ["git", "clean", "-dxf"], cwd=self._mock_srcdir, print_cmd=False
        )

    def testShouldDetectBoardNotSetUp(self):
        """Check that we complain if a board has not been previously setup."""
        with self.assertRaises(workon_helper.WorkonError):
            h = workon_helper.WorkonHelper(
                os.path.join(self.tempdir, "nonexistent"),
                "this-board-is-not-setup.",
                src_root=self._mock_srcdir,
            )
            h.StartWorkingOnPackages(["sys-apps/dbus"])

    def testShouldRegenerateSymlinks(self):
        """Check that the symlinks are regenerated when using a new sysroot."""
        # pylint: disable=protected-access
        helper = self.CreateHelper()
        workon_link = helper._masked_symlink
        self.assertNotExists(helper._unmasked_symlink)

        # The link exists after starting a package.
        helper.StartWorkingOnPackages([WORKON_ONLY_ATOM])
        self.assertExists(workon_link)
        self.assertNotExists(helper._unmasked_symlink)

        # The link exists after recreating a sysroot.
        osutils.RmDir(self._sysroot)
        osutils.SafeMakedirs(self._sysroot)
        helper = self.CreateHelper()
        self.assertExists(workon_link)
        self.assertNotExists(helper._unmasked_symlink)

        # The link exists when no packages are worked on.
        helper.StartWorkingOnPackages([WORKON_ONLY_ATOM])
        self.assertExists(workon_link)
        self.assertNotExists(helper._unmasked_symlink)

    def testCanStartSingleAtom(self):
        """Check that we can mark a single atom as being worked on."""
        helper = self.CreateHelper()
        helper.StartWorkingOnPackages([WORKON_ONLY_ATOM])
        self.assertWorkingOn([WORKON_ONLY_ATOM])

    def testCanStartMultipleAtoms(self):
        """Check that we can mark a multiple atoms as being worked on."""
        helper = self.CreateHelper()
        expected_atoms = (WORKON_ONLY_ATOM, VERSIONED_WORKON_ATOM)
        helper.StartWorkingOnPackages(expected_atoms)
        self.assertWorkingOn(expected_atoms)

    def testCanStartAtomsWithAll(self):
        """Check that we can mark all possible workon atoms as started."""
        helper = self.CreateHelper()
        expected_atoms = (WORKON_ONLY_ATOM, VERSIONED_WORKON_ATOM)
        helper.StartWorkingOnPackages([], use_all=True)
        self.assertWorkingOn(expected_atoms)

    def testCanStartAtomsWithWorkonOnly(self):
        """Check that we can start atoms that have only a cros-workon ebuild."""
        helper = self.CreateHelper()
        expected_atoms = (WORKON_ONLY_ATOM,)
        helper.StartWorkingOnPackages([], use_workon_only=True)
        self.assertWorkingOn(expected_atoms)

    def testCannotStartAtomTwice(self):
        """Check that starting an atom twice has no effect."""
        helper = self.CreateHelper()
        helper.StartWorkingOnPackages([WORKON_ONLY_ATOM])
        helper.StartWorkingOnPackages([WORKON_ONLY_ATOM])
        self.assertWorkingOn([WORKON_ONLY_ATOM])

    def testCanStopSingleAtom(self):
        """Check that we can stop a previously started atom."""
        helper = self.CreateHelper()
        helper.StartWorkingOnPackages([WORKON_ONLY_ATOM])
        self.assertWorkingOn([WORKON_ONLY_ATOM])
        helper.StopWorkingOnPackages([WORKON_ONLY_ATOM])
        self.assertWorkingOn([])

    def testCanStopMultipleAtoms(self):
        """Check that we can stop multiple previously worked on atoms."""
        helper = self.CreateHelper()
        expected_atoms = (WORKON_ONLY_ATOM, VERSIONED_WORKON_ATOM)
        helper.StartWorkingOnPackages(expected_atoms)
        self.assertWorkingOn(expected_atoms)
        helper.StopWorkingOnPackages([WORKON_ONLY_ATOM])
        self.assertWorkingOn([VERSIONED_WORKON_ATOM])
        helper.StopWorkingOnPackages([VERSIONED_WORKON_ATOM])
        self.assertWorkingOn([])
        # Now do it all at once.
        helper.StartWorkingOnPackages(expected_atoms)
        self.assertWorkingOn(expected_atoms)
        helper.StopWorkingOnPackages(expected_atoms)
        self.assertWorkingOn([])

    def testCanStopAtomsWithAll(self):
        """Check that we can stop all worked on atoms."""
        helper = self.CreateHelper()
        expected_atoms = (WORKON_ONLY_ATOM, VERSIONED_WORKON_ATOM)
        helper.StartWorkingOnPackages(expected_atoms)
        helper.StopWorkingOnPackages([], use_all=True)
        self.assertWorkingOn([])

    def testCanStopAtomsWithWorkonOnly(self):
        """Check that we can stop all workon only atoms."""
        helper = self.CreateHelper()
        expected_atoms = (WORKON_ONLY_ATOM, VERSIONED_WORKON_ATOM)
        helper.StartWorkingOnPackages(expected_atoms)
        helper.StopWorkingOnPackages([], use_workon_only=True)
        self.assertWorkingOn([VERSIONED_WORKON_ATOM])

    def testShouldDetectUnknownAtom(self):
        """Check that we reject requests to work on unknown atoms."""
        with self.assertRaises(workon_helper.WorkonError):
            helper = self.CreateHelper()
            helper.StopWorkingOnPackages(["sys-apps/not-a-thing"])

    def testCanListAllWorkedOnAtoms(self):
        """Check that we can list all worked on atoms across boards."""
        helper = self.CreateHelper()
        self.assertEqual(
            {},
            workon_helper.ListAllWorkedOnAtoms(src_root=self._mock_srcdir),
        )
        helper.StartWorkingOnPackages([WORKON_ONLY_ATOM])
        self.assertEqual(
            {BOARD: [WORKON_ONLY_ATOM]},
            workon_helper.ListAllWorkedOnAtoms(src_root=self._mock_srcdir),
        )
        host_helper = self.CreateHelper(host=True)
        host_helper.StartWorkingOnPackages([HOST_ATOM])
        self.assertEqual(
            {BOARD: [WORKON_ONLY_ATOM], "host": [HOST_ATOM]},
            workon_helper.ListAllWorkedOnAtoms(src_root=self._mock_srcdir),
        )

    def testCanListWorkedOnAtoms(self):
        """Check that we can list the atoms we're currently working on."""
        helper = self.CreateHelper()
        self.assertEqual(helper.ListAtoms(), [])
        helper.StartWorkingOnPackages([WORKON_ONLY_ATOM])
        self.assertEqual(helper.ListAtoms(), [WORKON_ONLY_ATOM])

    def testCanListAtomsWithAll(self):
        """Check that we can list all possible atoms to work on."""
        helper = self.CreateHelper()
        self.assertEqual(
            sorted(helper.ListAtoms(use_all=True)),
            sorted([WORKON_ONLY_ATOM, VERSIONED_WORKON_ATOM]),
        )

    def testCanListAtomsWithWorkonOnly(self):
        """Check that we can list all workon only atoms."""
        helper = self.CreateHelper()
        self.assertEqual(
            helper.ListAtoms(use_workon_only=True), [WORKON_ONLY_ATOM]
        )

    def testCanRunCommand(self):
        """Test that we can run a command in package source directories."""
        helper = self.CreateHelper()
        file_name = "foo"
        file_path = os.path.join(self._mock_srcdir, file_name)
        self.assertNotExists(file_path)
        helper.RunCommandInPackages([WORKON_ONLY_ATOM], ["touch", file_name])
        self.assertExists(file_path)

    def testInstalledWorkonAtoms(self):
        """Verify we can list all the cros workon atoms that are installed."""
        helper = self.CreateHelper()
        self.assertEqual(
            set([VERSIONED_WORKON_ATOM]), helper.InstalledWorkonAtoms()
        )


class WorkonScopeTest(cros_test_lib.MockTestCase):
    """Tests for chromite.lib.workon_helper.WorkonScope."""

    def setUp(self):
        """Set up a test environment."""
        self.bt = build_target_lib.BuildTarget(BOARD)

        self.workon = []

        def mock_start(pkgs: Iterable[str]):
            self.workon = set(self.workon).union(set(pkgs))

        def mock_stop(pkgs: Iterable[str]):
            self.workon = set(self.workon).difference(set(pkgs))

        def mock_list():
            return self.workon

        self.start_patch = self.PatchObject(
            workon_helper.WorkonHelper,
            "StartWorkingOnPackages",
            side_effect=mock_start,
        )
        self.stop_patch = self.PatchObject(
            workon_helper.WorkonHelper,
            "StopWorkingOnPackages",
            side_effect=mock_stop,
        )
        self.PatchObject(
            workon_helper.WorkonHelper, "ListAtoms", side_effect=mock_list
        )

    def testCMStartsAndStopsWithNoInitialPackages(self):
        """Verify the context manager works with no supplied package list."""
        with workon_helper.WorkonScope(self.bt):
            self.start_patch.assert_not_called()
        self.stop_patch.assert_not_called()

    def testCMStartsAndStopsPackages(self):
        """Verify the context manager usage starts and stops workon state."""
        with workon_helper.WorkonScope(self.bt, [WORKON_ONLY_ATOM]):
            self.start_patch.assert_called_once_with([WORKON_ONLY_ATOM])
        self.stop_patch.assert_called_once_with([WORKON_ONLY_ATOM])

    def testRetainsExistingWorkons(self):
        """Verify the context manager does not stop previously started pkgs."""
        self.workon = [WORKON_ONLY_ATOM]
        with workon_helper.WorkonScope(self.bt, [WORKON_ONLY_ATOM]):
            self.start_patch.assert_called_once_with([WORKON_ONLY_ATOM])
        self.stop_patch.assert_not_called()

    def testStartsStandaloneAtom(self):
        """Verify the helper .start() method (non-CM usage) starts workon."""
        helper = workon_helper.WorkonScope(self.bt)
        self.start_patch.assert_not_called()
        helper.start([WORKON_ONLY_ATOM])
        self.start_patch.assert_called_once_with([WORKON_ONLY_ATOM])
        self.stop_patch.assert_not_called()

    def testStopsStandaloneAtom(self):
        """Verify the helper .stop() method (non-CM usage) stops workon."""
        helper = workon_helper.WorkonScope(self.bt)
        self.stop_patch.assert_not_called()
        helper.stop([WORKON_ONLY_ATOM])
        self.stop_patch.assert_called_once_with([WORKON_ONLY_ATOM])
        self.start_patch.assert_not_called()

    def testRaisesExceptionForNonexistentBoard(self):
        """CM usage should perform start & stop, plus raise exception."""
        se = workon_helper.WorkonError()
        self.start_patch = self.PatchObject(
            workon_helper.WorkonHelper, "StartWorkingOnPackages", side_effect=se
        )
        with self.assertRaises(workon_helper.WorkonError):
            with workon_helper.WorkonScope(self.bt, [WORKON_ONLY_ATOM]):
                self.start_patch.assert_called_once_with([WORKON_ONLY_ATOM])
            self.stop_patch.assert_called_once_with([WORKON_ONLY_ATOM])

    def testFailedCleanupEmitsLog(self):
        """Failure in stop() call should emit a critical-level log message."""
        se = workon_helper.WorkonError()
        self.stop_patch = self.PatchObject(
            workon_helper.WorkonHelper, "StopWorkingOnPackages", side_effect=se
        )
        with self.assertLogs(level="CRITICAL") as log_cm:
            with workon_helper.WorkonScope(self.bt, [WORKON_ONLY_ATOM]):
                self.start_patch.assert_called_once_with([WORKON_ONLY_ATOM])
            self.stop_patch.assert_called_once_with([WORKON_ONLY_ATOM])
        self.assertRegex(
            " ".join(log_cm.output), "Unable to stop started packages."
        )

    def testManuallyStartedPackageIsStopped(self):
        with workon_helper.WorkonScope(self.bt, [WORKON_ONLY_ATOM]) as helper:
            helper.start([VERSIONED_WORKON_ATOM])
            self.start_patch.assert_any_call([WORKON_ONLY_ATOM])
            self.start_patch.assert_any_call([VERSIONED_WORKON_ATOM])
        self.stop_patch.assert_called_once_with(
            [WORKON_ONLY_ATOM, VERSIONED_WORKON_ATOM]
        )

    def testManuallyStoppedPackageIsRestarted(self):
        self.workon = [WORKON_ONLY_ATOM]
        with workon_helper.WorkonScope(self.bt) as helper:
            helper.stop([WORKON_ONLY_ATOM])
            self.stop_patch.assert_called_once_with([WORKON_ONLY_ATOM])
        self.start_patch.assert_called_once_with([WORKON_ONLY_ATOM])
