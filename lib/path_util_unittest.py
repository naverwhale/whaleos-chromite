# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the path_util module."""

import itertools
import os
from pathlib import Path
from unittest import mock

from chromite.lib import constants
from chromite.lib import cros_test_lib
from chromite.lib import git
from chromite.lib import osutils
from chromite.lib import partial_mock
from chromite.lib import path_util


FAKE_SOURCE_PATH = "/path/to/source/tree"
FAKE_OUT_PATH = FAKE_SOURCE_PATH / constants.DEFAULT_OUT_DIR
FAKE_REPO_PATH = "/path/to/repo"
CUSTOM_SOURCE_PATH = "/custom/source/path"
CUSTOM_CHROOT_PATH = "/custom/chroot/path"
CUSTOM_OUT_PATH = Path("/custom/out/path")


class DetermineCheckoutTest(cros_test_lib.MockTempDirTestCase):
    """Verify functionality for figuring out what checkout we're in."""

    def setUp(self):
        self.rc_mock = cros_test_lib.RunCommandMock()
        self.StartPatcher(self.rc_mock)
        self.rc_mock.SetDefaultCmdResult()

    def RunTest(
        self, dir_struct, cwd, expected_root, expected_type, expected_src
    ):
        """Run a test with specific parameters and expected results."""
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, dir_struct)
        cwd = os.path.join(self.tempdir, cwd)
        checkout_info = path_util.DetermineCheckout(cwd)
        full_root = expected_root
        if expected_root is not None:
            full_root = os.path.join(self.tempdir, expected_root)
        full_src = expected_src
        if expected_src is not None:
            full_src = os.path.join(self.tempdir, expected_src)

        self.assertEqual(checkout_info.root, full_root)
        self.assertEqual(checkout_info.type, expected_type)
        self.assertEqual(checkout_info.chrome_src_dir, full_src)

    def testGclientRepo(self):
        """Recognizes a GClient repo checkout."""
        dir_struct = [
            "a/.gclient",
            "a/b/.repo/",
            "a/b/c/.gclient",
            "a/b/c/d/somefile",
        ]
        self.RunTest(
            dir_struct,
            "a/b/c",
            "a/b/c",
            path_util.CheckoutType.GCLIENT,
            "a/b/c/src",
        )
        self.RunTest(
            dir_struct,
            "a/b/c/d",
            "a/b/c",
            path_util.CheckoutType.GCLIENT,
            "a/b/c/src",
        )
        self.RunTest(
            dir_struct, "a/b", "a/b", path_util.CheckoutType.REPO, None
        )
        self.RunTest(
            dir_struct, "a", "a", path_util.CheckoutType.GCLIENT, "a/src"
        )

    def testGitUnderGclient(self):
        """Recognizes a chrome git checkout by gclient."""
        self.rc_mock.AddCmdResult(
            partial_mock.In("config"), stdout=constants.CHROMIUM_GOB_URL
        )
        dir_struct = [
            "a/.gclient",
            "a/src/.git/",
        ]
        self.RunTest(
            dir_struct, "a/src", "a", path_util.CheckoutType.GCLIENT, "a/src"
        )

    def testGitUnderRepo(self):
        """Recognizes a chrome git checkout by repo."""
        self.rc_mock.AddCmdResult(
            partial_mock.In("config"), stdout=constants.CHROMIUM_GOB_URL
        )
        dir_struct = [
            "a/.repo/",
            "a/b/.git/",
        ]
        self.RunTest(dir_struct, "a/b", "a", path_util.CheckoutType.REPO, None)

    def testBadGit1(self):
        """.git is not a directory."""
        self.RunTest(
            ["a/.git"], "a", None, path_util.CheckoutType.UNKNOWN, None
        )

    def testBadGit2(self):
        """'git config' returns nothing."""
        self.RunTest(
            ["a/.repo/", "a/b/.git/"],
            "a/b",
            "a",
            path_util.CheckoutType.REPO,
            None,
        )

    def testBadGit3(self):
        """'git config' returns error."""
        self.rc_mock.AddCmdResult(partial_mock.In("config"), returncode=5)
        self.RunTest(
            ["a/.git/"], "a", None, path_util.CheckoutType.UNKNOWN, None
        )


class FindCacheDirTest(cros_test_lib.MockTempDirTestCase):
    """Test cache dir specification and finding functionality."""

    def setUp(self):
        dir_struct = [
            "repo/.repo/",
            "repo/manifest/",
            "gclient/.gclient",
        ]
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, dir_struct)
        self.repo_root = os.path.join(self.tempdir, "repo")
        self.gclient_root = os.path.join(self.tempdir, "gclient")
        self.nocheckout_root = os.path.join(self.tempdir, "nothing")

        self.rc_mock = self.StartPatcher(cros_test_lib.RunCommandMock())
        self.cwd_mock = self.PatchObject(os, "getcwd")

    def testRepoRoot(self):
        """Test when we are inside a repo checkout."""
        self.cwd_mock.return_value = self.repo_root
        self.assertEqual(
            path_util.FindCacheDir(),
            os.path.join(self.repo_root, path_util.GENERAL_CACHE_DIR),
        )

    def testGclientRoot(self):
        """Test when we are inside a gclient checkout."""
        self.cwd_mock.return_value = self.gclient_root
        self.assertEqual(
            path_util.FindCacheDir(),
            os.path.join(
                self.gclient_root, "src", "build", path_util.CHROME_CACHE_DIR
            ),
        )

    def testTempdir(self):
        """Test when we are not in any checkout."""
        self.cwd_mock.return_value = self.nocheckout_root
        self.assertStartsWith(
            path_util.FindCacheDir(), os.path.expanduser("~/")
        )


class TestPathResolver(cros_test_lib.MockTempDirTestCase):
    """Tests of ChrootPathResolver class."""

    def setUp(self):
        self.PatchObject(constants, "SOURCE_ROOT", new=FAKE_SOURCE_PATH)
        self.PatchObject(constants, "DEFAULT_OUT_PATH", new=FAKE_OUT_PATH)
        self.PatchObject(
            path_util, "GetCacheDir", return_value="/path/to/cache"
        )
        self.PatchObject(
            path_util.ChrootPathResolver,
            "_GetCachePath",
            return_value="/path/to/cache",
        )
        self.PatchObject(
            git,
            "FindRepoDir",
            return_value=os.path.join(FAKE_REPO_PATH, ".fake_repo"),
        )
        self.chroot_path = None
        self.out_path = None

    def FakeCwd(self, base_path):
        return os.path.join(base_path, "somewhere/in/there")

    def SetChrootPath(self, source_path, chroot_path=None, out_path=None):
        """Set and fake the chroot path."""
        self.chroot_path = chroot_path or os.path.join(
            source_path, constants.DEFAULT_CHROOT_DIR
        )
        self.out_path = out_path or (source_path / constants.DEFAULT_OUT_DIR)

    @mock.patch(
        "chromite.lib.cros_build_lib.IsInsideChroot", return_value=False
    )
    def testSourcePathInChrootInbound(self, _):
        """Test regular behavior if chroot_path is inside source_path."""

        self.SetChrootPath(constants.SOURCE_ROOT)
        resolver = path_util.ChrootPathResolver(
            source_from_path_repo=False,
            chroot_path=self.chroot_path,
            out_path=self.out_path,
        )

        self.assertEqual(
            os.path.join(self.chroot_path, "some/file"),
            resolver.FromChroot(os.path.join("/some/file")),
        )

        self.assertEqual(
            os.path.join("/other/file"),
            resolver.ToChroot(os.path.join(self.chroot_path, "other/file")),
        )

    @mock.patch("chromite.lib.cros_build_lib.IsInsideChroot", return_value=True)
    def testInsideChroot(self, _):
        """Tests {To,From}Chroot() call from inside the chroot."""
        self.SetChrootPath(constants.SOURCE_ROOT)
        resolver = path_util.ChrootPathResolver()

        self.assertEqual(
            os.path.realpath("some/path"), resolver.ToChroot("some/path")
        )
        self.assertEqual(
            os.path.realpath("/some/path"), resolver.ToChroot("/some/path")
        )
        self.assertEqual(
            os.path.realpath("/tmp/path"), resolver.ToChroot("/tmp/path")
        )
        self.assertEqual(
            os.path.realpath("some/path"), resolver.FromChroot("some/path")
        )
        self.assertEqual(
            os.path.realpath("/some/path"), resolver.FromChroot("/some/path")
        )
        self.assertEqual(
            os.path.realpath("/tmp/path"), resolver.FromChroot("/tmp/path")
        )

    @mock.patch(
        "chromite.lib.cros_build_lib.IsInsideChroot", return_value=False
    )
    def testOutsideChrootInbound(self, _):
        """Tests ToChroot() calls from outside the chroot."""
        for source_path, source_from_path_repo in itertools.product(
            (None, CUSTOM_SOURCE_PATH), (False, True)
        ):
            if source_from_path_repo:
                actual_source_path = FAKE_REPO_PATH
            else:
                actual_source_path = source_path or constants.SOURCE_ROOT

            fake_cwd = self.FakeCwd(actual_source_path)
            self.PatchObject(os, "getcwd", return_value=fake_cwd)
            self.SetChrootPath(actual_source_path)
            resolver = path_util.ChrootPathResolver(
                source_path=source_path,
                source_from_path_repo=source_from_path_repo,
            )
            source_rel_cwd = os.path.relpath(fake_cwd, actual_source_path)

            # Case: path inside the chroot space.
            self.assertEqual(
                "/some/path",
                resolver.ToChroot(os.path.join(self.chroot_path, "some/path")),
            )

            # Case: the cache directory.
            self.assertEqual(
                str(constants.CHROOT_CACHE_ROOT),
                resolver.ToChroot(path_util.GetCacheDir()),
            )

            # Case: path inside the cache directory.
            self.assertEqual(
                os.path.join(constants.CHROOT_CACHE_ROOT, "some/path"),
                resolver.ToChroot(
                    os.path.join(path_util.GetCacheDir(), "some/path")
                ),
            )

            # Case: absolute path inside the source tree.
            if source_from_path_repo:
                self.assertEqual(
                    os.path.join(constants.CHROOT_SOURCE_ROOT, "some/path"),
                    resolver.ToChroot(
                        os.path.join(FAKE_REPO_PATH, "some/path")
                    ),
                )
            else:
                self.assertEqual(
                    os.path.join(constants.CHROOT_SOURCE_ROOT, "some/path"),
                    resolver.ToChroot(
                        os.path.join(actual_source_path, "some/path")
                    ),
                )

            # Case: relative path inside the source tree.
            if source_from_path_repo:
                self.assertEqual(
                    os.path.join(
                        constants.CHROOT_SOURCE_ROOT,
                        source_rel_cwd,
                        "some/path",
                    ),
                    resolver.ToChroot("some/path"),
                )
            else:
                self.assertEqual(
                    os.path.join(
                        constants.CHROOT_SOURCE_ROOT,
                        source_rel_cwd,
                        "some/path",
                    ),
                    resolver.ToChroot("some/path"),
                )

            # Case: unreachable, path with improper source root prefix.
            with self.assertRaises(ValueError):
                resolver.ToChroot(
                    os.path.join(actual_source_path + "-foo", "some/path")
                )

            # Case: unreachable (random).
            with self.assertRaises(ValueError):
                resolver.ToChroot("/some/path")

    @mock.patch(
        "chromite.lib.cros_build_lib.IsInsideChroot", return_value=False
    )
    def testOutsideCustomChrootInbound(self, _):
        """Tests ToChroot() calls from outside a custom chroot."""

        self.SetChrootPath(
            constants.SOURCE_ROOT, CUSTOM_CHROOT_PATH, out_path=CUSTOM_OUT_PATH
        )
        resolver = path_util.ChrootPathResolver(
            chroot_path=CUSTOM_CHROOT_PATH, out_path=CUSTOM_OUT_PATH
        )

        # Case: path inside the chroot space.
        self.assertEqual(
            "/some/path",
            resolver.ToChroot(os.path.join(self.chroot_path, "some/path")),
        )

        # Case: path from source root
        self.assertEqual(
            os.path.join(constants.CHROOT_SOURCE_ROOT, "some/path"),
            resolver.ToChroot(os.path.join(constants.SOURCE_ROOT, "some/path")),
        )

        # Case: not mapped to chroot
        with self.assertRaises(ValueError):
            resolver.ToChroot("/random/file")

    @mock.patch(
        "chromite.lib.cros_build_lib.IsInsideChroot", return_value=False
    )
    def testOutsideChrootOutbound(self, _):
        """Tests FromChroot() calls from outside the chroot."""
        self.PatchObject(
            os, "getcwd", return_value=self.FakeCwd(FAKE_SOURCE_PATH)
        )

        self.SetChrootPath(constants.SOURCE_ROOT)
        resolver = path_util.ChrootPathResolver()

        # Case: source root path.
        self.assertEqual(
            os.path.join(constants.SOURCE_ROOT, "some/path"),
            resolver.FromChroot(
                os.path.join(constants.CHROOT_SOURCE_ROOT, "some/path")
            ),
        )

        # Case: cyclic source/chroot sub-path elimination.
        self.assertEqual(
            os.path.join(constants.SOURCE_ROOT, "some/path"),
            resolver.FromChroot(
                os.path.join(
                    constants.CHROOT_SOURCE_ROOT,
                    constants.DEFAULT_CHROOT_DIR,
                    constants.CHROOT_SOURCE_ROOT.relative_to("/"),
                    constants.DEFAULT_CHROOT_DIR,
                    constants.CHROOT_SOURCE_ROOT.relative_to("/"),
                    "some/path",
                )
            ),
        )

        # Case: the cache directory.
        self.assertEqual(
            path_util.GetCacheDir(),
            resolver.FromChroot(constants.CHROOT_CACHE_ROOT),
        )

        # Case: path inside the cache directory.
        self.assertEqual(
            os.path.join(path_util.GetCacheDir(), "some/path"),
            resolver.FromChroot(
                os.path.join(constants.CHROOT_CACHE_ROOT, "some/path")
            ),
        )

        # Case: non-rooted chroot paths.
        self.assertEqual(
            os.path.join(self.chroot_path, "some/path"),
            resolver.FromChroot("/some/path"),
        )

    @mock.patch(
        "chromite.lib.cros_build_lib.IsInsideChroot", return_value=False
    )
    def testOutsideCustomChrootOutbound(self, _):
        """Tests FromChroot() calls from outside the chroot."""
        self.PatchObject(
            os, "getcwd", return_value=self.FakeCwd(FAKE_SOURCE_PATH)
        )

        self.SetChrootPath(
            constants.SOURCE_ROOT,
            chroot_path=CUSTOM_CHROOT_PATH,
            out_path=CUSTOM_OUT_PATH,
        )
        resolver = path_util.ChrootPathResolver(
            chroot_path=CUSTOM_CHROOT_PATH, out_path=CUSTOM_OUT_PATH
        )

        # Case: source root path.
        self.assertEqual(
            os.path.join(constants.SOURCE_ROOT, "some/path"),
            resolver.FromChroot(
                os.path.join(constants.CHROOT_SOURCE_ROOT, "some/path")
            ),
        )

        # Case: cyclic source/chroot sub-path
        self.assertEqual(
            os.path.join(
                constants.SOURCE_ROOT,
                constants.DEFAULT_CHROOT_DIR,
                constants.CHROOT_SOURCE_ROOT.relative_to("/"),
                constants.DEFAULT_CHROOT_DIR,
                constants.CHROOT_SOURCE_ROOT.relative_to("/"),
                "some/path",
            ),
            resolver.FromChroot(
                os.path.join(
                    constants.CHROOT_SOURCE_ROOT,
                    constants.DEFAULT_CHROOT_DIR,
                    constants.CHROOT_SOURCE_ROOT.relative_to("/"),
                    constants.DEFAULT_CHROOT_DIR,
                    constants.CHROOT_SOURCE_ROOT.relative_to("/"),
                    "some/path",
                )
            ),
        )

        # Case: path inside the cache directory.
        self.assertEqual(
            os.path.join(path_util.GetCacheDir(), "some/path"),
            resolver.FromChroot(
                os.path.join(constants.CHROOT_CACHE_ROOT, "some/path")
            ),
        )

        # Case: non-rooted chroot paths.
        self.assertEqual(
            os.path.join(self.chroot_path, "some/path"),
            resolver.FromChroot("/some/path"),
        )

    @mock.patch(
        "chromite.lib.cros_build_lib.IsInsideChroot", return_value=False
    )
    def testCurrentDir(self, _):
        """Tests chroot translation with the current dir."""
        # Current directory is "out" directory.
        self.SetChrootPath(
            constants.SOURCE_ROOT, CUSTOM_CHROOT_PATH, out_path=Path(".")
        )
        resolver = path_util.ChrootPathResolver(
            chroot_path=self.chroot_path,
            out_path=self.out_path,
        )

        self.assertEqual(
            os.path.realpath("foo"),
            resolver.FromChroot(constants.CHROOT_OUT_ROOT / "foo"),
        )
        self.assertEqual(
            str(constants.CHROOT_OUT_ROOT / "foo"),
            resolver.ToChroot("foo"),
        )

        # Current directory is "chroot" directory.
        self.SetChrootPath(constants.SOURCE_ROOT, ".", out_path=CUSTOM_OUT_PATH)
        resolver = path_util.ChrootPathResolver(
            chroot_path=self.chroot_path,
            out_path=self.out_path,
        )

        self.assertEqual(
            os.path.realpath("."),
            resolver.FromChroot("/"),
        )
        self.assertEqual(
            "/",
            resolver.ToChroot("."),
        )

    @mock.patch(
        "chromite.lib.cros_build_lib.IsInsideChroot", return_value=False
    )
    def testOutsideChrootOutdir(self, _):
        """Tests {To,From}Chroot() call from outside chroot with an out_dir."""
        self.SetChrootPath(constants.SOURCE_ROOT)
        resolver = path_util.ChrootPathResolver()

        self.assertEqual(
            "/build/foo",
            resolver.ToChroot(
                os.path.join(constants.SOURCE_ROOT, "out/build/foo")
            ),
        )
        self.assertEqual(
            os.path.join(constants.SOURCE_ROOT, "out/build/foo"),
            resolver.FromChroot("/build/foo"),
        )
        self.assertEqual(
            "/home/foo",
            resolver.ToChroot(
                os.path.join(constants.SOURCE_ROOT, "out/home/foo")
            ),
        )
        self.assertEqual(
            os.path.join(constants.SOURCE_ROOT, "out/home/foo"),
            resolver.FromChroot("/home/foo"),
        )
        self.assertEqual(
            "/tmp/foo",
            resolver.ToChroot(
                os.path.join(constants.SOURCE_ROOT, "out/tmp/foo")
            ),
        )
        self.assertEqual(
            os.path.join(constants.SOURCE_ROOT, "out/tmp/foo"),
            resolver.FromChroot("/tmp/foo"),
        )
        self.assertEqual(
            os.path.join(constants.SOURCE_ROOT, "out/tmp"),
            resolver.FromChroot("/tmp"),
        )
        self.assertEqual(
            "/tmp",
            resolver.ToChroot(os.path.join(constants.SOURCE_ROOT, "out/tmp")),
        )
        self.assertEqual(
            "/run/lock/foo",
            resolver.ToChroot(
                os.path.join(constants.SOURCE_ROOT, "out/sdk/run/lock/foo")
            ),
        )
        self.assertEqual(
            os.path.join(constants.SOURCE_ROOT, "out/sdk/run/lock/foo"),
            resolver.FromChroot("/run/lock/foo"),
        )
        self.assertEqual(
            "/var/cache/foo",
            resolver.ToChroot(
                os.path.join(constants.SOURCE_ROOT, "out/sdk/cache/foo")
            ),
        )
        self.assertEqual(
            os.path.join(constants.SOURCE_ROOT, "out/sdk/cache/foo"),
            resolver.FromChroot("/var/cache/foo"),
        )
        self.assertEqual(
            "/var/log/foo",
            resolver.ToChroot(
                os.path.join(constants.SOURCE_ROOT, "out/sdk/logs/foo")
            ),
        )
        self.assertEqual(
            os.path.join(constants.SOURCE_ROOT, "out/sdk/logs/foo"),
            resolver.FromChroot("/var/log/foo"),
        )
        self.assertEqual(
            "/var/tmp/foo",
            resolver.ToChroot(
                os.path.join(constants.SOURCE_ROOT, "out/sdk/tmp/foo")
            ),
        )
        self.assertEqual(
            os.path.join(constants.SOURCE_ROOT, "out/sdk/tmp/foo"),
            resolver.FromChroot("/var/tmp/foo"),
        )
        self.assertEqual(
            "/usr/local/bin/emerge-foo",
            resolver.ToChroot(
                os.path.join(constants.SOURCE_ROOT, "out/sdk/bin/emerge-foo")
            ),
        )
        self.assertEqual(
            os.path.join(constants.SOURCE_ROOT, "out/sdk/bin/emerge-foo"),
            resolver.FromChroot("/usr/local/bin/emerge-foo"),
        )
        self.assertEqual(
            os.path.join(constants.SOURCE_ROOT, "out/foo"),
            resolver.FromChroot(os.path.join(constants.CHROOT_OUT_ROOT, "foo")),
        )
        self.assertEqual(
            os.path.join(constants.CHROOT_OUT_ROOT, "foo"),
            resolver.ToChroot(os.path.join(constants.SOURCE_ROOT, "out/foo")),
        )
        self.assertEqual(
            os.path.join(constants.SOURCE_ROOT, "out"),
            resolver.FromChroot(constants.CHROOT_OUT_ROOT),
        )
        self.assertEqual(
            str(constants.CHROOT_OUT_ROOT),
            resolver.ToChroot(os.path.join(constants.SOURCE_ROOT, "out")),
        )

    @mock.patch(
        "chromite.lib.cros_build_lib.IsInsideChroot", return_value=False
    )
    def testBySourcePath(self, _):
        """Provide only source_path=, and derive chroot/ and out/."""
        source_path = CUSTOM_SOURCE_PATH
        resolver = path_util.ChrootPathResolver(
            source_path=source_path, source_from_path_repo=False
        )

        self.assertEqual(
            os.path.join(source_path, constants.DEFAULT_CHROOT_DIR),
            resolver.FromChroot("/"),
        )
        self.assertEqual(
            "/",
            resolver.ToChroot(
                os.path.join(source_path, constants.DEFAULT_CHROOT_DIR)
            ),
        )

        self.assertEqual(
            str(source_path / constants.DEFAULT_OUT_DIR),
            resolver.FromChroot(constants.CHROOT_OUT_ROOT),
        )
        self.assertEqual(
            str(constants.CHROOT_OUT_ROOT),
            resolver.ToChroot(source_path / constants.DEFAULT_OUT_DIR),
        )

    @mock.patch(
        "chromite.lib.cros_build_lib.IsInsideChroot", return_value=False
    )
    def testSymlinkedPath(self, _):
        """Resolve a symlinked path."""
        original_realpath = os.path.realpath
        self.PatchObject(
            os.path,
            "realpath",
            side_effect=lambda path: "/usr/wrongpath/foo"
            if path == "/bin/foo"
            else original_realpath(path),
        )
        # Double check the mock.
        self.assertEqual("/usr/wrongpath/foo", os.path.realpath("/bin/foo"))

        self.SetChrootPath(
            None,
            chroot_path=self.tempdir / "chroot",
            out_path=self.tempdir / "out",
        )
        resolver = path_util.ChrootPathResolver(
            chroot_path=self.chroot_path, out_path=self.out_path
        )

        source = Path(self.chroot_path) / "usr" / "bin" / "foo"
        target = Path(self.chroot_path) / "bin" / "foo"
        osutils.Touch(source, makedirs=True)
        osutils.SafeSymlink("usr/bin", Path(self.chroot_path) / "bin")

        # On inbound, translate symlinks on the host side, before chroot
        # translation.
        self.assertEqual("/usr/bin/foo", resolver.ToChroot(target))
        # On outbound, only translate links after chroot translation.
        self.assertEqual(str(source), resolver.FromChroot("/bin/foo"))

    @mock.patch(
        "chromite.lib.cros_build_lib.IsInsideChroot", return_value=False
    )
    def testNonDefaultChrootPathInsideSourcePath(self, _):
        """Test custom chroot behavior if chroot_path is inside source_path."""

        source_path = constants.SOURCE_ROOT
        self.SetChrootPath(
            source_path,
            chroot_path=os.path.join(source_path, "my-special-custom-chroot"),
        )
        resolver = path_util.ChrootPathResolver(
            chroot_path=self.chroot_path,
            out_path=self.out_path,
        )

        from_chroot = resolver.FromChroot(os.path.join("/some/file"))
        self.assertIn("/my-special-custom-chroot/", from_chroot)
        self.assertEqual(
            os.path.join(self.chroot_path, "some/file"),
            from_chroot,
        )

        self.assertEqual(
            os.path.join("/other/file"),
            resolver.ToChroot(os.path.join(self.chroot_path, "other/file")),
        )


def test_normalize_paths_to_source_root_collapsing_sub_paths():
    """Test normalize removes sub paths."""
    actual_paths = path_util.normalize_paths_to_source_root(
        [
            os.path.join(constants.SOURCE_ROOT, "foo"),
            os.path.join(constants.SOURCE_ROOT, "ab", "cd"),
            os.path.join(constants.SOURCE_ROOT, "foo", "bar"),
        ]
    )
    expected_paths = {"ab/cd", "foo"}
    assert set(actual_paths) == expected_paths

    actual_paths = path_util.normalize_paths_to_source_root(
        [
            os.path.join(constants.SOURCE_ROOT, "foo", "bar"),
            os.path.join(constants.SOURCE_ROOT, "ab", "cd"),
            os.path.join(constants.SOURCE_ROOT, "foo", "bar", ".."),
            os.path.join(constants.SOURCE_ROOT, "ab", "cde"),
        ]
    )
    expected_paths = {"ab/cd", "ab/cde", "foo"}
    assert set(actual_paths) == expected_paths


def test_normalize_paths_to_source_root_formatting_directory_paths(tmp_path):
    """Test normalize correctly handles /path/to/file and /path/to/dir/."""
    foo_dir = tmp_path / "foo"
    foo_dir.mkdir()
    bar_baz_dir = tmp_path / "bar" / "baz"
    bar_baz_dir.mkdir(parents=True)
    ab_dir = tmp_path / "ab"
    ab_dir.mkdir()
    ab_cd_file = ab_dir / "cd"

    osutils.WriteFile(ab_cd_file, "alphabet")

    expected_paths = [
        str(ab_cd_file.relative_to(tmp_path)),
        str(bar_baz_dir.relative_to(tmp_path)),
        str(foo_dir.relative_to(tmp_path)),
    ]

    actual_paths = path_util.normalize_paths_to_source_root(
        [
            str(foo_dir) + "/",
            str(ab_cd_file),
            str(bar_baz_dir) + "/",
        ],
        source_root=tmp_path,
    )
    assert actual_paths == expected_paths


def test_expand_directories_in_git(tmp_path):
    """Test ExpandDirectories when given a dir in a git repo."""
    files_in_dir = [Path("foo.txt"), Path("bar.txt")]

    with mock.patch("chromite.lib.git.FindGitTopLevel", return_value=tmp_path):
        with mock.patch(
            "chromite.lib.git.LsFiles", return_value=files_in_dir
        ) as ls_files:
            result = set(path_util.ExpandDirectories([tmp_path]))

    assert result == set(files_in_dir)
    ls_files.assert_called_once_with(files=[tmp_path], untracked=True)


def test_expand_directories_not_git(tmp_path):
    """Test ExpandDirectories when given a dir outside a git repo."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    files_in_dir = [tmp_path / "foo.txt", subdir / "bar.txt"]
    for f in files_in_dir:
        osutils.Touch(f)

    with mock.patch("chromite.lib.git.FindGitTopLevel", return_value=None):
        result = set(path_util.ExpandDirectories([tmp_path]))

    assert result == set(files_in_dir)


def test_expand_directories_file(tmp_path):
    """Test ExpandDirectories when given a regular file."""
    file_path = tmp_path / "foo.txt"
    osutils.Touch(file_path)

    result = list(path_util.ExpandDirectories([file_path]))

    assert result == [file_path]
