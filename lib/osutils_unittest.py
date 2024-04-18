# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for the osutils.py module (imagine that!)."""

import collections
import ctypes
import errno
import filecmp
import glob
import grp
import itertools
import os
from pathlib import Path
import pwd
import re
import stat
import sys
import tempfile
import time
from unittest import mock

from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import partial_mock


class TestOsutils(cros_test_lib.TempDirTestCase):
    """General unittests for the osutils module."""

    def testIsSubPath(self):
        self.assertTrue(osutils.IsSubPath("/a", "/"))
        self.assertTrue(osutils.IsSubPath("/", "/"))

        self.assertTrue(osutils.IsSubPath("/a", "/a"))
        self.assertTrue(osutils.IsSubPath("/a", "/a/"))

        self.assertTrue(osutils.IsSubPath("/a/b", "/a"))
        self.assertTrue(osutils.IsSubPath("/a/b", "/a/"))

        self.assertTrue(osutils.IsSubPath("/a/b/e", "/a/b/c/../../b"))

        self.assertFalse(osutils.IsSubPath("/ab", "/a/b"))
        self.assertFalse(osutils.IsSubPath("/a/bcde", "/a/b"))

    def testAllocateNewFile(self):
        """Verify we can allocate a file of a certain length."""
        filename = self.tempdir / "foo"
        size = 1234
        osutils.AllocateFile(filename, size)

        self.assertExists(filename)
        self.assertEqual(size, os.path.getsize(filename))

    def testAllocateExistingFile(self):
        """Verify we can allocate an existing file of a certain length."""
        file = self.tempdir / "foo"
        file.write_text("abcd", encoding="utf-8")

        size = 1234
        osutils.AllocateFile(file, size)
        self.assertEqual(size, os.path.getsize(file))

        # Content should be reset.
        self.assertEqual(osutils.ReadFile(file, "rb", size=4), b"\0\0\0\0")

    def testReadWriteFile(self):
        """Verify we can write data to a file, and then read it back."""
        filename = os.path.join(self.tempdir, "foo")
        data = "alsdkfjasldkfjaskdlfjasdf"
        self.assertIsNone(osutils.WriteFile(filename, data))
        self.assertEqual(osutils.ReadFile(filename), data)

    def testReadWritePath(self):
        """Verify we can write data to a Path, and then read it back."""
        filename = self.tempdir / "foo"
        data = "alsdkfjasldkfjaskdlfjasdf"
        self.assertIsNone(osutils.WriteFile(filename, data))
        self.assertEqual(osutils.ReadFile(filename), data)

    def testReadBinary(self):
        """Verify we can read data as binary."""
        filename = os.path.join(self.tempdir, "foo")
        data = b"alsdkfjasldkfjaskdlfjasdf"
        self.assertIsNone(osutils.WriteFile(filename, data, mode="wb"))
        self.assertEqual(osutils.ReadFile(filename, mode="rb"), data)

    def testReadSize(self):
        """Verify we can read partial data."""
        filename = self.tempdir / "foo"
        data = b"alsdkfjasldkfjaskdlfjasdf"
        filename.write_bytes(data)
        self.assertEqual(osutils.ReadFile(filename, mode="rb", size=3), b"als")
        self.assertEqual(osutils.ReadFile(filename, mode="r", size=3), "als")

    def testReadSeek(self):
        """Verify we can read data from the middle."""
        filename = self.tempdir / "foo"
        data = b"alsdkfjasldkfjaskdlfjasdf"
        sdata = data.decode("utf-8")
        filename.write_bytes(data)
        self.assertEqual(
            osutils.ReadFile(filename, mode="rb", seek=3), data[3:]
        )
        self.assertEqual(
            osutils.ReadFile(filename, mode="r", seek=3), sdata[3:]
        )

    def testReadSeekSize(self):
        """Verify we can read partial data from the middle."""
        filename = self.tempdir / "foo"
        data = b"alsdkfjasldkfjaskdlfjasdf"
        filename.write_bytes(data)
        self.assertEqual(
            osutils.ReadFile(filename, mode="rb", seek=3, size=3), b"dkf"
        )
        self.assertEqual(
            osutils.ReadFile(filename, mode="r", seek=3, size=3), "dkf"
        )

    def testWriteFileStringIter(self):
        """Verify that we can write an iterable of strings."""
        filename = os.path.join(self.tempdir, "foo")
        data = ["a", "cd", "ef"]
        self.assertIsNone(osutils.WriteFile(filename, data))
        self.assertEqual(osutils.ReadFile(filename), "".join(data))

    def testWriteFileBytesIter(self):
        """Verify that we can write an iterable of bytes."""
        filename = os.path.join(self.tempdir, "foo")
        data = [b"ab", b"cd", b"ef"]
        self.assertIsNone(osutils.WriteFile(filename, data, mode="wb"))
        self.assertEqual(osutils.ReadFile(filename, mode="rb"), b"".join(data))

    def testReadBytes(self):
        """Verify we can read data as binary via ReadBytes."""
        filename = os.path.join(self.tempdir, "foo")
        data = b"0123456789"
        self.assertIsNone(osutils.WriteFile(filename, data, mode="wb"))
        self.assertEqual(osutils.ReadBytes(filename, 7 - 3, 3), b"3456")

    def testReadText(self):
        """Verify we can read data as text via ReadText."""
        filename = os.path.join(self.tempdir, "foo")
        data = b"0123456789"
        self.assertIsNone(osutils.WriteFile(filename, data, mode="wb"))
        self.assertEqual(osutils.ReadText(filename, 7 - 3, 3), "3456")

    def testReadSudo(self):
        """Verify we can read data as root (in a world-readable dir)."""
        # First read a non-root file.
        filename = self.tempdir / "foo"
        data = b"alsdkfjasldkfjaskdlfjasdf"
        sdata = data.decode("utf-8")
        filename.write_bytes(data)
        self.assertEqual(osutils.ReadFile(filename, mode="r", sudo=True), sdata)
        self.assertEqual(osutils.ReadFile(filename, mode="rb", sudo=True), data)

        with osutils.TempDir(sudo_rm=True) as tempdir:
            # Create a file only root can read.
            filename = os.path.join(tempdir, "file")
            osutils.WriteFile(filename, data, mode="wb", chmod=0o600, sudo=True)

            # Read a root file w/out sudo should fail.
            self.assertRaises(IOError, osutils.ReadFile, filename)
            # Read a root file w/sudo as text.
            self.assertEqual(
                osutils.ReadFile(filename, mode="r", sudo=True), sdata
            )
            # Read a root file w/sudo as bytes.
            self.assertEqual(
                osutils.ReadFile(filename, mode="rb", sudo=True), data
            )
            # Read a root file w/partial reads.
            self.assertEqual(
                osutils.ReadFile(filename, mode="r", sudo=True, size=3),
                sdata[:3],
            )
            self.assertEqual(
                osutils.ReadFile(filename, mode="rb", sudo=True, size=3),
                data[:3],
            )
            # Read a root file w/seeks & partial reads.
            self.assertEqual(
                osutils.ReadFile(filename, mode="r", sudo=True, seek=3, size=3),
                sdata[3:6],
            )
            self.assertEqual(
                osutils.ReadFile(
                    filename, mode="rb", sudo=True, seek=3, size=3
                ),
                data[3:6],
            )

    def testReadSudoSubdir(self):
        """Verify we can read data as root in a subdir."""
        data = b"alsdkfjasldkfjaskdlfjasdf"
        sdata = data.decode("utf-8")

        with osutils.TempDir(sudo_rm=True) as tempdir:
            # Create a file only root can read.
            tempdir = Path(tempdir)
            subdir = tempdir / "subdir"
            self.assertTrue(osutils.SafeMakedirs(subdir, mode=0o700, sudo=True))
            filename = subdir / "file"
            osutils.WriteFile(filename, data, mode="wb", chmod=0o600, sudo=True)

            # Read a root file w/out sudo should fail.
            self.assertRaises(IOError, osutils.ReadFile, filename)
            # Read a root file w/sudo as text.
            self.assertEqual(
                osutils.ReadFile(filename, mode="r", sudo=True), sdata
            )
            # Read a root file w/sudo as bytes.
            self.assertEqual(
                osutils.ReadFile(filename, mode="rb", sudo=True), data
            )

    def testSudoWrite(self):
        """Verify that we can write a file as sudo."""
        with osutils.TempDir(sudo_rm=True) as tempdir:
            root_owned_dir = Path(tempdir) / "foo"
            self.assertTrue(osutils.SafeMakedirs(root_owned_dir, sudo=True))

            for atomic, path_to_test in itertools.product(
                (True, False),
                (os.path.join(root_owned_dir, "bar"), root_owned_dir / "bar"),
            ):
                self.assertRaises(
                    IOError, osutils.WriteFile, path_to_test, "data"
                )

                osutils.WriteFile(
                    path_to_test, "test", atomic=atomic, sudo=True
                )
                self.assertEqual("test", osutils.ReadFile(path_to_test))
                self.assertEqual(0, os.stat(path_to_test).st_uid)
                osutils.SafeUnlink(path_to_test, sudo=True)

    def testSudoWriteAppendNew(self):
        """Verify that we can write a new file as sudo when appending."""
        with osutils.TempDir(sudo_rm=True) as tempdir:
            path = os.path.join(tempdir, "foo")
            osutils.WriteFile(path, "two", mode="a", sudo=True)
            self.assertEqual("two", osutils.ReadFile(path))

    def testSudoWriteAppendExisting(self):
        """Verify that we can write a file as sudo when appending."""
        with osutils.TempDir(sudo_rm=True) as tempdir:
            path = os.path.join(tempdir, "foo")
            osutils.WriteFile(path, "one", sudo=True)
            self.assertRaises(IOError, osutils.WriteFile, path, "data")
            osutils.WriteFile(path, "two", mode="a", sudo=True)
            self.assertEqual("onetwo", osutils.ReadFile(path))

    def testSudoReadNoTrunc(self):
        """Verify that we can write a new file as sudo when r+."""

        def testit(path, sudo):
            osutils.WriteFile(path, "two")
            self.assertEqual("two", osutils.ReadFile(path))
            osutils.WriteFile(path, "X", mode="r+", sudo=sudo)
            self.assertEqual("Xwo", osutils.ReadFile(path))

        # Make sure that r+ works as we think it does.
        path = os.path.join(self.tempdir, "foo")
        testit(path, False)

        # Now run it again with sudo.
        with osutils.TempDir(sudo_rm=True) as tempdir:
            path = os.path.join(tempdir, "foo")
            testit(path, True)

    def testReadFileNonExistent(self):
        """Verify what happens if you ReadFile a file that isn't there."""
        filename = os.path.join(self.tempdir, "bogus")
        with self.assertRaises(IOError):
            osutils.ReadFile(filename)

    def testWriteChmod(self):
        """Verify writing files with perms works."""

        def getmode(path):
            return os.stat(path).st_mode & 0o7777

        def assertMode(path, mode):
            self.assertEqual(getmode(path), mode)

        for path in (os.path.join(self.tempdir, "file"), self.tempdir / "file"):
            osutils.WriteFile(path, "asdf")
            assertMode(path, 0o644)

            osutils.WriteFile(path, "asdf", chmod=0o666)
            assertMode(path, 0o666)

            osutils.WriteFile(path, "asdf", atomic=True, chmod=0o664)
            assertMode(path, 0o664)

            osutils.WriteFile(path, "asdf", sudo=True, chmod=0o755)
            assertMode(path, 0o755)

            osutils.WriteFile(path, "asdf", sudo=True, atomic=True, chmod=0o775)
            assertMode(path, 0o775)

            osutils.SafeUnlink(path, sudo=True)

    def testSafeSymlink(self):
        """Test that we can create symlinks."""
        with osutils.TempDir(sudo_rm=True) as tempdir:
            file_a = os.path.join(tempdir, "a")
            osutils.WriteFile(file_a, "a")

            file_b = os.path.join(tempdir, "b")
            osutils.WriteFile(file_b, "b")

            user_dir = os.path.join(tempdir, "bar")
            user_link = os.path.join(user_dir, "link")
            osutils.SafeMakedirs(user_dir)

            root_dir = os.path.join(tempdir, "foo")
            root_link = os.path.join(root_dir, "link")
            osutils.SafeMakedirs(root_dir, sudo=True)

            # We can create and override links owned by a non-root user.
            osutils.SafeSymlink(file_a, user_link)
            self.assertEqual("a", osutils.ReadFile(user_link))

            osutils.SafeSymlink(file_b, user_link)
            self.assertEqual("b", osutils.ReadFile(user_link))

            # Handle Path objects.
            osutils.SafeSymlink(Path(file_a), Path(user_link))
            self.assertEqual("a", osutils.ReadFile(user_link))

            osutils.SafeSymlink(Path(file_b), Path(user_link))
            self.assertEqual("b", osutils.ReadFile(user_link))

            # We can create and override links owned by root.
            osutils.SafeSymlink(file_a, root_link, sudo=True)
            self.assertEqual("a", osutils.ReadFile(root_link))

            osutils.SafeSymlink(file_b, root_link, sudo=True)
            self.assertEqual("b", osutils.ReadFile(root_link))

            # Handle Path objects.
            osutils.SafeSymlink(Path(file_a), Path(root_link), sudo=True)
            self.assertEqual("a", osutils.ReadFile(root_link))

            osutils.SafeSymlink(Path(file_b), Path(root_link), sudo=True)
            self.assertEqual("b", osutils.ReadFile(root_link))

    def testSafeUnlink(self):
        """Test unlinking files work (existing or not)."""

        def f(sudo=False, as_path=False):
            with osutils.TempDir(sudo_rm=sudo) as dirname:
                path = os.path.join(dirname, "foon")
                if as_path:
                    path = Path(path)
                osutils.Touch(path, makedirs=True)
                self.assertExists(path)
                if sudo:
                    osutils.Chown(
                        dirname, user="root", group="root", recursive=False
                    )
                    self.assertRaises(EnvironmentError, os.unlink, path)
                self.assertTrue(osutils.SafeUnlink(path, sudo=sudo))
                self.assertNotExists(path)
                self.assertFalse(osutils.SafeUnlink(path))
                self.assertNotExists(path)

        f(False)
        f(True)
        f(False, True)
        f(True, True)

    def testSafeUnlinkSudoInaccessible(self):
        """Test unlinking files work in a dir only root can read."""
        with osutils.TempDir(sudo_rm=True) as dirname:
            path = os.path.join(dirname, "exists")
            osutils.Touch(path, mode=0o000)
            os.chmod(dirname, 0o000)
            self.assertRaises(EnvironmentError, os.unlink, path)
            self.assertTrue(osutils.SafeUnlink(path, sudo=True))
            self.assertFalse(osutils.SafeUnlink(path, sudo=True))

            os.chmod(dirname, 0o700)
            self.assertNotExists(path)

    def testSafeMakedirs(self):
        """Test creating directory trees work (existing or not)."""
        path = os.path.join(self.tempdir, "a", "b", "c", "d", "e")
        self.assertTrue(osutils.SafeMakedirs(path))
        self.assertExists(path)
        self.assertFalse(osutils.SafeMakedirs(path))
        self.assertExists(path)

    def testSafeMakedirsWithPathObject(self):
        """Test creating directory trees work (existing or not) on |Path|s."""
        path = self.tempdir / "a" / "b" / "c" / "d" / "e"
        self.assertTrue(osutils.SafeMakedirs(path))
        self.assertExists(path)
        self.assertFalse(osutils.SafeMakedirs(path))
        self.assertExists(path)

    def testSafeMakedirsMode(self):
        """Test that mode is honored."""
        path = os.path.join(self.tempdir, "a", "b", "c", "d", "e")
        self.assertTrue(osutils.SafeMakedirs(path, mode=0o775))
        self.assertEqual(0o775, stat.S_IMODE(os.stat(path).st_mode))
        self.assertFalse(osutils.SafeMakedirs(path, mode=0o777))
        self.assertEqual(0o777, stat.S_IMODE(os.stat(path).st_mode))
        cros_build_lib.sudo_run(["chown", "root:root", path], print_cmd=False)
        # Tries, but fails to change the mode.
        self.assertFalse(osutils.SafeMakedirs(path, 0o755))
        self.assertEqual(0o777, stat.S_IMODE(os.stat(path).st_mode))

    def testSafeMakedirs_error(self):
        """Check error paths."""
        with self.assertRaises(OSError):
            osutils.SafeMakedirs("/foo/bar/cow/moo/wee")
            ret = cros_build_lib.run(
                ["ls", "-Rla", "/foo"], check=False, capture_output=True
            )
            print(
                "ls output of /foo:\n{{{%s}}}" % (ret.stdout,), file=sys.stderr
            )
        self.assertRaises(OSError, osutils.SafeMakedirs, "")

    def testSafeMakedirsSudo(self):
        """Test creating directory trees work as root (existing or not)."""
        self.ExpectRootOwnedFiles()
        path = os.path.join(self.tempdir, "a", "b", "c", "d", "e")
        self.assertTrue(osutils.SafeMakedirs(path, sudo=True))
        self.assertExists(path)
        self.assertFalse(osutils.SafeMakedirs(path, sudo=True))
        self.assertExists(path)
        self.assertEqual(os.stat(path).st_uid, 0)

    def testSafeMakedirsNoSudoRootOwnedDirs(self):
        """Test that we can recover some root owned directories."""
        self.ExpectRootOwnedFiles()
        root_owned_prefix = os.path.join(self.tempdir, "root_owned_prefix")
        root_owned_dir = os.path.join(root_owned_prefix, "root_owned_dir")
        non_root_dir = os.path.join(root_owned_prefix, "non_root_dir")
        self.assertTrue(osutils.SafeMakedirs(root_owned_dir, sudo=True))
        self.assertExists(root_owned_prefix)
        self.assertEqual(os.stat(root_owned_prefix).st_uid, 0)
        self.assertExists(root_owned_dir)
        self.assertEqual(os.stat(root_owned_dir).st_uid, 0)

        # Test that we can reclaim a root-owned dir.
        # Note, return value is False because the directory already exists.
        self.assertFalse(osutils.SafeMakedirsNonRoot(root_owned_dir))
        self.assertNotEqual(os.stat(root_owned_dir).st_uid, 0)

        # Test that we can create a non-root directory in a root-path.
        self.assertTrue(osutils.SafeMakedirsNonRoot(non_root_dir))
        self.assertNotEqual(os.stat(non_root_dir).st_uid, 0)

    def testRmDir(self):
        """Test that removing dirs work."""
        main_path = os.path.join(self.tempdir, "a", "b", "c", "d", "e")
        paths_to_test = [main_path, Path(main_path)]

        for path in paths_to_test:
            self.assertRaises(EnvironmentError, osutils.RmDir, path)
            osutils.SafeMakedirs(path)
            osutils.RmDir(path)
            osutils.RmDir(path, ignore_missing=True)
            self.assertRaises(EnvironmentError, osutils.RmDir, path)

            osutils.SafeMakedirs(path)
            osutils.RmDir(path)
            self.assertNotExists(path)

    def testRmDirSudo(self):
        """Test that removing dirs via sudo works."""
        subpath = os.path.join(self.tempdir, "a")
        main_path = os.path.join(subpath, "b", "c", "d", "e")
        paths_to_test = [main_path, Path(main_path)]

        for path in paths_to_test:
            self.assertTrue(osutils.SafeMakedirs(path, sudo=True))
            self.assertRaises(OSError, osutils.RmDir, path)
            osutils.RmDir(subpath, sudo=True)
            self.assertRaises(
                cros_build_lib.RunCommandError,
                osutils.RmDir,
                subpath,
                sudo=True,
            )

    def testTouchFile(self):
        """Test that we can touch files."""
        path = os.path.join(self.tempdir, "touchit")
        self.assertNotExists(path)
        osutils.Touch(path)
        self.assertExists(path)
        self.assertEqual(os.path.getsize(path), 0)

    def testTouchReadOnlyFile(self):
        """Test that we can touch read-only files that we own."""
        path = self.tempdir / "touchit"
        nowish = time.time() - 60
        path.touch(mode=0o600)
        # Set the times to very old.
        os.utime(path, (1, 1))
        assert os.path.getmtime(path) < 10
        # This should still update the times even though it's read-only.
        osutils.Touch(path)
        assert os.path.getmtime(path) >= nowish

    def testTouchFileSubDir(self):
        """Test that we can touch files in non-existent subdirs."""
        path = os.path.join(self.tempdir, "a", "b", "c", "touchit")
        self.assertNotExists(os.path.dirname(path))
        osutils.Touch(path, makedirs=True)
        self.assertExists(path)
        self.assertEqual(os.path.getsize(path), 0)

    def testChmod(self):
        """Test Chmod."""

        def getmode(path):
            return os.stat(path).st_mode & 0o7777

        path = os.path.join(self.tempdir, "chmodtests")
        osutils.Touch(path)

        osutils.Chmod(path, 0o700)
        self.assertEqual(getmode(path), 0o700)

        osutils.Chmod(Path(path), 0o644)
        self.assertEqual(getmode(path), 0o644)

        osutils.Chown(path, user="root", group="root")
        osutils.Chmod(path, 0o660, sudo=True)
        self.assertEqual(getmode(path), 0o660)
        osutils.Chmod(Path(path), 0o661, sudo=True)
        self.assertEqual(getmode(path), 0o661)

        self.assertRaises(OSError, osutils.Chmod, path, 0o600)

    def testChown(self):
        """Test chown."""

        # Helpers to get the user and group name of the given path's owner.
        def User(path):
            return pwd.getpwuid(os.stat(path).st_uid).pw_name

        def Group(path):
            return grp.getgrgid(os.stat(path).st_gid).gr_name

        filename = os.path.join(self.tempdir, "chowntests")
        osutils.Touch(filename)

        user = User(filename)
        group = Group(filename)

        new_user = new_group = "root"

        # Change only the user.
        osutils.Chown(filename, user=new_user)
        self.assertEqual(new_user, User(filename))
        self.assertEqual(new_group, Group(filename))

        # Change both user and group.
        osutils.Chown(filename, user=user, group=group)
        self.assertEqual(user, User(filename))
        self.assertEqual(group, Group(filename))

        # With Path object.
        osutils.Chown(Path(filename), user=new_user, group=new_group)
        self.assertEqual(new_user, User(filename))
        self.assertEqual(new_group, Group(filename))
        osutils.Chown(Path(filename), user=user, group=group)
        self.assertEqual(user, User(filename))
        self.assertEqual(group, Group(filename))

        # User and group ids as the arguments.
        osutils.Chown(filename, user=0, group=0)
        self.assertEqual(new_user, User(filename))
        self.assertEqual(new_group, Group(filename))

        # Recursive.
        dirname = os.path.join(self.tempdir, "chowntestsdir")
        osutils.SafeMakedirs(dirname)
        filename = os.path.join(dirname, "chowntestsfile")
        osutils.Touch(filename)
        # Chown without recursive.
        osutils.Chown(dirname, user=new_user, group=new_group)
        self.assertEqual(new_user, User(dirname))
        self.assertEqual(new_group, Group(dirname))
        self.assertEqual(user, User(filename))
        self.assertEqual(group, Group(filename))
        # Chown with recursive.
        osutils.Chown(dirname, user=new_user, group=new_group, recursive=True)
        self.assertEqual(new_user, User(filename))
        self.assertEqual(new_group, Group(filename))
        osutils.Chown(dirname, user=user, group=group, recursive=True)
        self.assertEqual(user, User(dirname))
        self.assertEqual(group, Group(dirname))
        self.assertEqual(user, User(filename))
        self.assertEqual(group, Group(filename))


class TestEmptyDir(cros_test_lib.TempDirTestCase):
    """Test osutils.EmptyDir."""

    def setUp(self):
        self.subdir = os.path.join(self.tempdir, "a")
        self.nestedfile = os.path.join(self.subdir, "b", "c", "d", "e")
        self.topfile = os.path.join(self.tempdir, "file")

    def testEmptyDir(self):
        """Empty an empty directory."""
        osutils.EmptyDir(self.tempdir)
        osutils.EmptyDir(self.tempdir, ignore_missing=True, sudo=True)

    def testNonExistentDir(self):
        """Non-existent directory."""
        # Ignore_missing=False
        with self.assertRaises(osutils.EmptyDirNonExistentException):
            osutils.EmptyDir(self.subdir)

        # Ignore missing=True
        osutils.EmptyDir(self.subdir, ignore_missing=True)

    def testEmptyWithContentsMinFlags(self):
        """Test ability to empty actual directory contents."""
        osutils.Touch(self.nestedfile, makedirs=True)
        osutils.Touch(self.topfile, makedirs=True)

        osutils.EmptyDir(self.tempdir)

        self.assertExists(self.tempdir)
        self.assertNotExists(self.subdir)
        self.assertNotExists(self.topfile)

    def testEmptyWithContentsMaxFlags(self):
        """Test ability to empty actual directory contents."""
        osutils.Touch(self.nestedfile, makedirs=True)
        osutils.Touch(self.topfile, makedirs=True)

        osutils.EmptyDir(self.tempdir, ignore_missing=True, sudo=True)

        self.assertExists(self.tempdir)
        self.assertNotExists(self.subdir)
        self.assertNotExists(self.topfile)

    def testEmptyWithRootOwnedContents(self):
        """Test handling of root owned sub directories."""
        # Root owned contents.
        osutils.SafeMakedirs(self.nestedfile, sudo=True)

        # Fails without sudo=True
        with self.assertRaises(OSError):
            osutils.EmptyDir(self.tempdir)
        self.assertExists(self.nestedfile)

        # Works with sudo=True
        osutils.EmptyDir(self.tempdir, sudo=True)
        self.assertExists(self.tempdir)
        self.assertNotExists(self.subdir)

    def testExclude(self):
        """Test ability to empty actual directory contents.

        Also ensure that the excludes argument can really be just an iterable.
        """
        files = {
            "keep": True,
            "keepdir/foo": True,
            "keepdir/bar": True,
            "remove": False,
            "removedir/foo": False,
            "removedir/bar": False,
        }

        excludes = ["keep", "keepdir", "bogus"]

        # Perform exclusion of non-existent files.
        osutils.EmptyDir(self.tempdir, exclude=iter(excludes))

        # Create files.
        for f in files.keys():
            osutils.Touch(os.path.join(self.tempdir, f), makedirs=True)

        # Empty with excludes.
        osutils.EmptyDir(self.tempdir, exclude=iter(excludes))

        # Verify that the results are what we expect.
        for f, expected in files.items():
            f = os.path.join(self.tempdir, f)
            self.assertEqual(os.path.exists(f), expected, "Unexpected: %s" % f)
        self.assertExists(os.path.join(self.tempdir, "keepdir"))
        self.assertNotExists(os.path.join(self.tempdir, "removedir"))


class TestProcess(cros_test_lib.RunCommandTestCase):
    """Tests for osutils.IsChildProcess."""

    def testIsChildProcess(self):
        """Test IsChildProcess with no name."""
        mock_pstree_output = "a(1)-+-b(2)\n\t|-c(3)\n\t|-foo(4)-bar(5)"
        self.rc.AddCmdResult(partial_mock.Ignore(), stdout=mock_pstree_output)
        self.assertTrue(osutils.IsChildProcess(4))
        self.assertTrue(osutils.IsChildProcess(4, name="foo"))
        self.assertFalse(osutils.IsChildProcess(5, name="foo"))


class TempDirTests(cros_test_lib.TestCase):
    """Unittests of osutils.TempDir.

    Unlike other test classes in this file, TempDirTestCase isn't used as a base
    class, because that is the functionality under test.
    """

    PREFIX = "chromite.test.osutils.TempDirTests"

    class HelperException(Exception):
        """Exception for tests to raise to test exception handling."""

    class HelperExceptionInner(Exception):
        """Exception for tests to raise to test exception handling."""

    def testBasicSuccessEmpty(self):
        """Test we create and cleanup an empty tempdir."""
        with osutils.TempDir(prefix=self.PREFIX) as td:
            tempdir = td
            # Show the temp directory exists and is empty.
            self.assertTrue(os.path.isdir(tempdir))
            self.assertEqual(os.listdir(tempdir), [])

        # Show the temp directory no longer exists.
        self.assertNotExists(tempdir)

    def testBasicSuccessNotEmpty(self):
        """Test we cleanup tempdir with stuff in it."""
        with osutils.TempDir(prefix=self.PREFIX) as td:
            tempdir = td
            # Show the temp directory exists and is empty.
            self.assertTrue(os.path.isdir(tempdir))
            self.assertEqual(os.listdir(tempdir), [])

            # Create an empty file.
            osutils.Touch(os.path.join(tempdir, "foo.txt"))

            # Create nested sub directories.
            subdir = os.path.join(tempdir, "foo", "bar", "taco")
            os.makedirs(subdir)
            osutils.Touch(os.path.join(subdir, "sauce.txt"))

        # Show the temp directory no longer exists.
        self.assertNotExists(tempdir)

    def testErrorCleanup(self):
        """Test we cleanup, even if an exception is raised."""
        try:
            with osutils.TempDir(prefix=self.PREFIX) as td:
                tempdir = td
                raise TempDirTests.HelperException()
        except TempDirTests.HelperException:
            pass

        # Show the temp directory no longer exists.
        self.assertNotExists(tempdir)

    def testCleanupExceptionContextException(self):
        """Test an exception during cleanup if the context DID raise."""
        was_raised = False
        tempdir_obj = osutils.TempDir(prefix=self.PREFIX)

        with mock.patch.object(
            osutils,
            "_TempDirTearDown",
            side_effect=TempDirTests.HelperException,
        ):
            try:
                with tempdir_obj as td:
                    tempdir = td
                    raise TempDirTests.HelperExceptionInner()
            except TempDirTests.HelperExceptionInner:
                was_raised = True

        # Show that the exception exited the context.
        self.assertTrue(was_raised)

        # Verify the tempdir object no longer contains a reference to the
        # tempdir.
        self.assertIsNone(tempdir_obj.tempdir)

        # Cleanup the dir leaked by our mock exception.
        os.rmdir(tempdir)

    def testCleanupExceptionNoContextException(self):
        """Test an exception during cleanup if the context did NOT raise."""
        was_raised = False
        tempdir_obj = osutils.TempDir(prefix=self.PREFIX)

        with mock.patch.object(
            osutils,
            "_TempDirTearDown",
            side_effect=TempDirTests.HelperException,
        ):
            try:
                with tempdir_obj as td:
                    tempdir = td
            except TempDirTests.HelperException:
                was_raised = True

        # Show that the exception exited the context.
        self.assertTrue(was_raised)

        # Verify the tempdir object no longer contains a reference to the
        # tempdir.
        self.assertIsNone(tempdir_obj.tempdir)

        # Cleanup the dir leaked by our mock exception.
        os.rmdir(tempdir)

    def testSkipCleanup(self):
        """Test that we leave behind tempdirs when requested."""
        tempdir_obj = osutils.TempDir(prefix=self.PREFIX, delete=False)
        tempdir = tempdir_obj.tempdir
        tempdir_obj.Cleanup()
        # Ensure we cleaned up ...
        self.assertIsNone(tempdir_obj.tempdir)
        # ... but leaked the directory.
        self.assertExists(tempdir)
        # Now really cleanup the directory leaked by the test.
        os.rmdir(tempdir)

    def testSkipCleanupGlobal(self):
        """Test that we reset global tempdir as expected even with skip."""
        with osutils.TempDir(prefix=self.PREFIX, set_global=True) as tempdir:
            tempdir_before = tempfile.gettempdir()
            tempdir_obj = osutils.TempDir(
                prefix=self.PREFIX, set_global=True, delete=False
            )
            tempdir_inside = tempfile.gettempdir()
            tempdir_obj.Cleanup()
            tempdir_after = tempfile.gettempdir()

        # We shouldn't leak the outer directory.
        self.assertNotExists(tempdir)
        self.assertEqual(tempdir_before, tempdir_after)
        # This is a strict substring check.
        self.assertLess(tempdir_before, tempdir_inside)


class MountTests(cros_test_lib.TestCase):
    """Unittests for osutils mounting and umounting helpers."""

    def testMountTmpfsDir(self):
        """Verify mounting a tmpfs works"""
        cleaned = False
        with osutils.TempDir(prefix="chromite.test.osutils") as tempdir:
            st_before = os.stat(tempdir)
            try:
                # Mount the dir and verify it worked.
                osutils.MountTmpfsDir(tempdir)
                st_after = os.stat(tempdir)
                self.assertNotEqual(st_before.st_dev, st_after.st_dev)

                # Unmount the dir and verify it worked.
                osutils.UmountDir(tempdir)
                cleaned = True

                # Finally make sure it's cleaned up.
                self.assertNotExists(tempdir)
            finally:
                if not cleaned:
                    cros_build_lib.sudo_run(
                        ["umount", "-lf", tempdir], check=False
                    )

    def testUnmountTree(self):
        with osutils.TempDir(prefix="chromite.test.osutils") as tempdir:
            # Mount the dir and verify it worked.
            st_before = os.stat(tempdir)
            osutils.MountTmpfsDir(tempdir)
            st_after = os.stat(tempdir)
            self.assertNotEqual(st_before.st_dev, st_after.st_dev)

            # Mount an inner dir the same way.
            tempdir2 = os.path.join(tempdir, "inner")
            osutils.SafeMakedirsNonRoot(tempdir2)
            st_before2 = os.stat(tempdir2)
            osutils.MountTmpfsDir(tempdir2)
            st_after2 = os.stat(tempdir2)
            self.assertNotEqual(st_before2.st_dev, st_after2.st_dev)

            # Unmount the whole tree and verify it worked.
            osutils.UmountTree(tempdir)
            st_umount = os.stat(tempdir)
            self.assertNotExists(tempdir2)
            self.assertEqual(st_before.st_dev, st_umount.st_dev)


class IteratePathsTest(cros_test_lib.TestCase):
    """Test iterating through all segments of a path."""

    def testType(self):
        """Check that return value is an iterator."""
        self.assertIsInstance(
            osutils.IteratePaths("/"), collections.abc.Iterator
        )

    def testRoot(self):
        """Test iterating from root directory."""
        inp = "/"
        exp = [Path("/")]
        self.assertEqual(list(osutils.IteratePaths(inp)), exp)

    def testOneDir(self):
        """Test iterating from a directory in a root directory."""
        inp = "/abc"
        exp = [Path("/"), Path("/abc")]
        self.assertEqual(list(osutils.IteratePaths(inp)), exp)

    def testTwoDirs(self):
        """Test iterating two dirs down."""
        inp = "/abc/def"
        exp = [Path("/"), Path("/abc"), Path("/abc/def")]
        self.assertEqual(list(osutils.IteratePaths(inp)), exp)

    def testNormalize(self):
        """Test argument being normalized."""
        cases = [
            ("//", [Path("/")]),
            ("///", [Path("/")]),
            ("/abc/", [Path("/"), Path("/abc")]),
            ("/abc//def", [Path("/"), Path("/abc"), Path("/abc/def")]),
        ]
        for inp, exp in cases:
            self.assertEqual(list(osutils.IteratePaths(inp)), exp)


class IteratePathParentsTest(cros_test_lib.TestCase):
    """Test parent directory iteration functionality."""

    def _RunForPath(self, path, expected):
        result_components = []
        for p in osutils.IteratePathParents(path):
            result_components.append(os.path.basename(p))

        result_components.reverse()
        if expected is not None:
            self.assertEqual(expected, result_components)

    def testIt(self):
        """Run the test vectors."""
        vectors = {
            "/": [""],
            "/path/to/nowhere": ["", "path", "to", "nowhere"],
            "/path/./to": ["", "path", "to"],
            "//path/to": ["", "path", "to"],
            "path/to": None,
            "": None,
        }
        for p, e in vectors.items():
            self._RunForPath(p, e)


class FindInPathParentsTest(cros_test_lib.TempDirTestCase):
    """Test FindInPathParents functionality."""

    D = cros_test_lib.Directory

    DIR_STRUCT = [D("a", [D(".repo", []), D("b", [D("c", [])])])]

    START_PATH = os.path.join("a", "b", "c")

    def setUp(self):
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, self.DIR_STRUCT)

    def testFoundStr(self):
        """Target (str) is found."""
        found = osutils.FindInPathParents(
            ".repo", os.path.join(self.tempdir, self.START_PATH)
        )
        self.assertEqual(found, os.path.join(self.tempdir, "a", ".repo"))

    def testFoundPath(self):
        """Target (Path) is found."""
        found = osutils.FindInPathParents(
            ".repo", self.tempdir / self.START_PATH
        )
        self.assertEqual(found, self.tempdir / "a" / ".repo")

    def testNotFoundStr(self):
        """Target is not found."""
        found = osutils.FindInPathParents(
            "does.not/exist", os.path.join(self.tempdir, self.START_PATH)
        )
        self.assertIsNone(found)

    def testNotFoundPath(self):
        """Target is not found."""
        found = osutils.FindInPathParents(
            "does.not/exist", self.tempdir / self.START_PATH
        )
        self.assertIsNone(found)


class SourceEnvironmentTest(cros_test_lib.TempDirTestCase):
    """Test osutil's environmental variable related methods."""

    ENV_ALLOWLIST = {
        "ENV1": "monkeys like bananas",
        "ENV3": "merci",
        "ENV6": "",
    }

    ENV_OTHER = {
        "ENV2": "bananas are yellow",
        "ENV4": "de rien",
    }

    ENV = """
declare -x ENV1="monkeys like bananas"
declare -x ENV2="bananas are yellow"
declare -x ENV3="merci"
declare -x ENV4="de rien"
declare -x ENV6=''
declare -x ENVA=('a b c' 'd' 'e 1234 %')
"""

    ENV_MULTILINE = """
declare -x ENVM="gentil
mechant"
"""

    def setUp(self):
        self.env_file = os.path.join(self.tempdir, "environment")
        self.env_file_multiline = os.path.join(self.tempdir, "multiline")
        osutils.WriteFile(self.env_file, self.ENV)
        osutils.WriteFile(self.env_file_multiline, self.ENV_MULTILINE)

    def testAllowList(self):
        env_dict = osutils.SourceEnvironment(
            self.env_file, ("ENV1", "ENV3", "ENV5", "ENV6")
        )
        self.assertEqual(env_dict, self.ENV_ALLOWLIST)

    def testArrays(self):
        env_dict = osutils.SourceEnvironment(self.env_file, ("ENVA",))
        self.assertEqual(env_dict, {"ENVA": "a b c,d,e 1234 %"})

        env_dict = osutils.SourceEnvironment(self.env_file, ("ENVA",), ifs=" ")
        self.assertEqual(env_dict, {"ENVA": "a b c d e 1234 %"})

        env_dict = osutils.SourceEnvironment(
            self.env_file_multiline, ("ENVM",), multiline=True
        )
        self.assertEqual(env_dict, {"ENVM": "gentil\nmechant"})


class DeviceInfoTests(cros_test_lib.RunCommandTestCase):
    """Tests methods retrieving information about devices."""

    FULL_OUTPUT = """
NAME="sda" RM="0" TYPE="disk" SIZE="128G" HOTPLUG="0"
NAME="sda1" RM="1" TYPE="part" SIZE="100G" HOTPLUG="1"
NAME="sda2" RM="1" TYPE="part" SIZE="28G" HOTPLUG="1"
NAME="sdc" RM="1" TYPE="disk" SIZE="7.4G" HOTPLUG="1"
NAME="sdc1" RM="1" TYPE="part" SIZE="1G" HOTPLUG="1"
NAME="sdc2" RM="1" TYPE="part" SIZE="6.4G" HOTPLUG="1"
"""

    PARTIAL_OUTPUT = """
NAME="sdc" RM="1" TYPE="disk" SIZE="7.4G" HOTPLUG="0"
NAME="sdc1" RM="1" TYPE="part" SIZE="1G" HOTPLUG="0"
NAME="sdc2" RM="1" TYPE="part" SIZE="6.4G" HOTPLUG="0"
"""

    def testListBlockDevices(self):
        """Tests that we can list all block devices correctly."""
        self.rc.AddCmdResult(partial_mock.Ignore(), stdout=self.FULL_OUTPUT)
        devices = osutils.ListBlockDevices()
        self.assertEqual(devices[0].NAME, "sda")
        self.assertEqual(devices[0].RM, "0")
        self.assertEqual(devices[0].TYPE, "disk")
        self.assertEqual(devices[0].SIZE, "128G")
        self.assertEqual(devices[0].HOTPLUG, "0")
        self.assertEqual(devices[3].NAME, "sdc")
        self.assertEqual(devices[3].RM, "1")
        self.assertEqual(devices[3].TYPE, "disk")
        self.assertEqual(devices[3].SIZE, "7.4G")
        self.assertEqual(devices[3].HOTPLUG, "1")

    def testGetDeviceSize(self):
        """Tests that we can get the size of a device."""
        self.rc.AddCmdResult(partial_mock.Ignore(), stdout=self.PARTIAL_OUTPUT)
        self.assertEqual(osutils.GetDeviceSize("/dev/sdc"), "7.4G")


class ChdirTests(cros_test_lib.MockTempDirTestCase):
    """Tests for ChdirContext."""

    def testChdir(self):
        current_dir = Path.cwd()
        self.assertNotEqual(self.tempdir, current_dir)
        with osutils.ChdirContext(self.tempdir):
            self.assertEqual(self.tempdir, Path.cwd())
        self.assertEqual(current_dir, Path.cwd())


class MountOverlayTest(cros_test_lib.MockTempDirTestCase):
    """Tests MountOverlayContext."""

    def setUp(self):
        self.upperdir = os.path.join(self.tempdir, "first_level", "upperdir")
        self.lowerdir = os.path.join(self.tempdir, "lowerdir")
        self.mergeddir = os.path.join(self.tempdir, "mergeddir")

        for path in [self.upperdir, self.lowerdir, self.mergeddir]:
            osutils.Touch(path, makedirs=True)

    def testMountWriteUnmountRead(self):
        mount_call = self.PatchObject(osutils, "MountDir")
        umount_call = self.PatchObject(osutils, "UmountDir")
        for cleanup in (True, False):
            with osutils.MountOverlayContext(
                self.lowerdir, self.upperdir, self.mergeddir, cleanup=cleanup
            ):
                mount_call.assert_any_call(
                    "overlay",
                    self.mergeddir,
                    fs_type="overlay",
                    makedirs=False,
                    mount_opts=(
                        "lowerdir=%s" % self.lowerdir,
                        "upperdir=%s" % self.upperdir,
                        mock.ANY,
                    ),
                    quiet=mock.ANY,
                )
            umount_call.assert_any_call(self.mergeddir, cleanup=cleanup)

    def testMountFailFallback(self):
        """Verify mount failure with overlay fs_type falls back to overlayfs."""

        def _FailOverlay(*_args, **kwargs):
            if kwargs["fs_type"] == "overlay":
                raise cros_build_lib.RunCommandError(
                    "Phony failure",
                    cros_build_lib.CompletedProcess(["MounDir"], returncode=32),
                )

        mount_call = self.PatchObject(osutils, "MountDir")
        mount_call.side_effect = _FailOverlay
        umount_call = self.PatchObject(osutils, "UmountDir")
        for cleanup in (True, False):
            with osutils.MountOverlayContext(
                self.lowerdir, self.upperdir, self.mergeddir, cleanup=cleanup
            ):
                mount_call.assert_any_call(
                    "overlay",
                    self.mergeddir,
                    fs_type="overlay",
                    makedirs=False,
                    mount_opts=(
                        "lowerdir=%s" % self.lowerdir,
                        "upperdir=%s" % self.upperdir,
                        mock.ANY,
                    ),
                    quiet=mock.ANY,
                )
                mount_call.assert_any_call(
                    "overlayfs",
                    self.mergeddir,
                    fs_type="overlayfs",
                    makedirs=False,
                    mount_opts=(
                        "lowerdir=%s" % self.lowerdir,
                        "upperdir=%s" % self.upperdir,
                    ),
                    quiet=mock.ANY,
                )
            umount_call.assert_any_call(self.mergeddir, cleanup=cleanup)

    def testNoValidWorkdirFallback(self):
        """Test that we fallback to overlayfs when no valid workdir is found."""

        def _FailFileSystemCheck(_path1, _path2):
            return False

        check_filesystem = self.PatchObject(osutils, "_SameFileSystem")
        check_filesystem.side_effect = _FailFileSystemCheck
        mount_call = self.PatchObject(osutils, "MountDir")
        umount_call = self.PatchObject(osutils, "UmountDir")

        for cleanup in (True, False):
            with osutils.MountOverlayContext(
                self.lowerdir, self.upperdir, self.mergeddir, cleanup=cleanup
            ):
                mount_call.assert_any_call(
                    "overlayfs",
                    self.mergeddir,
                    fs_type="overlayfs",
                    makedirs=False,
                    mount_opts=(
                        "lowerdir=%s" % self.lowerdir,
                        "upperdir=%s" % self.upperdir,
                    ),
                    quiet=mock.ANY,
                )
            umount_call.assert_any_call(self.mergeddir, cleanup=cleanup)


class IterateMountPointsTests(cros_test_lib.MockTempDirTestCase):
    """Test for IterateMountPoints function."""

    def setUp(self):
        self.proc_mount = os.path.join(self.tempdir, "mounts")
        osutils.WriteFile(
            self.proc_mount,
            r"""/dev/loop0 /mnt/dir_8 ext4 rw,relatime,data=ordered 0 0
/dev/loop2 /mnt/dir_1 ext4 rw,relatime,data=ordered 0 0
/dev/loop1 /mnt/dir_12 vfat rw 0 0
/dev/loop4 /mnt/dir_3 ext4 ro,relatime 0 0
weird\040system /mnt/weirdo unknown ro 0 0
tmpfs /mnt/spaced\040dir tmpfs ro 0 0
tmpfs /mnt/\134 tmpfs ro 0 0
/dev/mapper/some-root / ext4 rw,relatime,errors=remount-ro 0 0
/dev/mapper/some-root / ext4 ro,relatime,errors=remount-ro 0 0
""",
        )

    def testOkay(self):
        """Test IterateMountPoints() with some basic entries."""
        r = list(osutils.IterateMountPoints(self.proc_mount))
        assert len(r) == 9
        assert r[0].source == "/dev/loop0"
        assert r[1].destination == "/mnt/dir_1"
        assert r[2].filesystem == "vfat"
        assert r[3].options == "ro,relatime"

    def testEscape(self):
        """Test IterateMountPoints() with some escaped characters."""
        r = list(osutils.IterateMountPoints(self.proc_mount))
        assert r[4].source == "weird system"
        assert r[5].destination == "/mnt/spaced dir"
        assert r[6].destination == "/mnt/\\"

    def testIsMounted(self):
        """Test IsMounted() on a variety of mtab entries."""
        self.PatchObject(osutils.IsMounted, "__defaults__", (self.proc_mount,))

        assert osutils.IsMounted("/mnt/dir_1")
        assert osutils.IsMounted("/mnt/dir_3")
        assert osutils.IsMounted("/mnt/dir_8")
        assert osutils.IsMounted("/mnt/dir_12")
        assert osutils.IsMounted("/mnt/weirdo")
        assert osutils.IsMounted("/mnt/spaced dir")
        assert osutils.IsMounted("/mnt/\\")
        assert osutils.IsMounted("/")
        assert not osutils.IsMounted("/mnt/spaced")
        assert not osutils.IsMounted("dir")
        assert not osutils.IsMounted("")

    def testIsMountedReadOnly(self):
        """Test IsMountedReadOnly() on a variety of mtab entries."""
        self.PatchObject(
            osutils.IsMountedReadOnly, "__defaults__", (self.proc_mount,)
        )

        assert not osutils.IsMountedReadOnly("/mnt/dir_1")
        assert osutils.IsMountedReadOnly("/mnt/dir_3")
        assert not osutils.IsMountedReadOnly("/mnt/dir_8")
        assert not osutils.IsMountedReadOnly("/mnt/dir_12")
        assert osutils.IsMountedReadOnly("/mnt/weirdo")
        assert osutils.IsMountedReadOnly("/mnt/spaced dir")
        assert osutils.IsMountedReadOnly("/mnt/\\")
        assert osutils.IsMountedReadOnly("/")
        assert not osutils.IsMountedReadOnly("/mnt/spaced")
        assert not osutils.IsMountedReadOnly("dir")
        assert not osutils.IsMountedReadOnly("")

    def testIsMountedReadonlyEmpty(self):
        """Test IsMountedReadOnly() on an empty mtab."""
        mounts = self.tempdir / "empty"
        mounts.touch()

        for mount in ("", "/", "/mnt/dir_1"):
            assert not osutils.IsMountedReadOnly(mount, proc_file=mounts)


class ResolveSymlinkInRootTest(cros_test_lib.TempDirTestCase):
    """Tests for ResolveSymlinkInRoot."""

    def setUp(self):
        # Create symlinks in tempdir so they are cleaned up automatically.
        os.chdir(self.tempdir)

    def testRelativeLink(self):
        os.symlink("target", "link")
        self.assertEqual(
            osutils.ResolveSymlinkInRoot("link", "/root"), "target"
        )

    def testRelativeLinkPath(self):
        """Verify Path objects work."""
        os.symlink("target", "link")
        self.assertEqual(
            osutils.ResolveSymlinkInRoot(Path("link"), Path("/root")), "target"
        )

    def testAbsoluteLink(self):
        os.symlink("/target", "link")
        self.assertEqual(
            osutils.ResolveSymlinkInRoot("link", "/root"), "/root/target"
        )

    def testRecursion(self):
        os.symlink("target", "link1")
        os.symlink("link1", "link2")
        self.assertEqual(
            osutils.ResolveSymlinkInRoot("link2", "/root"), "target"
        )

    def testRecursionWithAbsoluteLink(self):
        os.symlink("target", "link1")
        os.symlink("/link1", "link2")
        self.assertEqual(osutils.ResolveSymlinkInRoot("link2", "."), "./target")


class ResolveSymlinkTest(cros_test_lib.TempDirTestCase):
    """Tests for ResolveSymlink."""

    def setUp(self):
        self.file_path = self.tempdir / "file"
        self.dir_path = self.tempdir / "directory"
        osutils.Touch(self.file_path)
        osutils.SafeMakedirs(self.dir_path)

        os.chdir(self.tempdir)
        osutils.SafeSymlink(self.file_path, "abs_file_symlink")
        osutils.SafeSymlink("./file", "rel_file_symlink")
        osutils.SafeSymlink(self.dir_path, "abs_dir_symlink")
        osutils.SafeSymlink("./directory", "rel_dir_symlink")

        self.abs_file_symlink = self.tempdir / "abs_file_symlink"
        self.rel_file_symlink = self.tempdir / "rel_file_symlink"
        self.abs_dir_symlink = self.tempdir / "abs_dir_symlink"
        self.rel_dir_symlink = self.tempdir / "rel_dir_symlink"

    def testAbsoluteResolution(self):
        """Test absolute path resolutions using Path objects."""
        self.assertEqual(
            self.file_path, osutils.ResolveSymlink(self.abs_file_symlink)
        )
        self.assertEqual(
            self.dir_path, osutils.ResolveSymlink(self.abs_dir_symlink)
        )

    def testAbsoluteResolutionStr(self):
        """Test absolute path resolutions using strings."""
        self.assertEqual(
            str(self.file_path),
            osutils.ResolveSymlink(str(self.abs_file_symlink)),
        )
        self.assertEqual(
            str(self.dir_path),
            osutils.ResolveSymlink(str(self.abs_dir_symlink)),
        )

    def testRelativeResolution(self):
        """Test relative path resolutions using Path objects."""
        self.assertEqual(
            self.file_path, osutils.ResolveSymlink(self.rel_file_symlink)
        )
        self.assertEqual(
            self.dir_path, osutils.ResolveSymlink(self.rel_dir_symlink)
        )

    def testRelativeResolutionStr(self):
        """Test relative path resolutions using strings."""
        self.assertEqual(
            str(self.file_path),
            osutils.ResolveSymlink(str(self.rel_file_symlink)),
        )
        self.assertEqual(
            str(self.dir_path),
            osutils.ResolveSymlink(str(self.rel_dir_symlink)),
        )


class IsInsideVmTest(cros_test_lib.MockTempDirTestCase):
    """Test osutils.IsInsideVmTest function."""

    def setUp(self):
        self.model_file = os.path.join(self.tempdir, "sda", "device", "model")
        osutils.SafeMakedirs(os.path.dirname(self.model_file))
        self.mock_glob = self.PatchObject(
            glob, "glob", return_value=[self.model_file]
        )

    def testIsInsideVm(self):
        osutils.WriteFile(self.model_file, "VBOX")
        self.assertTrue(osutils.IsInsideVm())
        self.assertEqual(
            self.mock_glob.call_args[0][0], "/sys/block/*/device/model"
        )

        osutils.WriteFile(self.model_file, "VMware")
        self.assertTrue(osutils.IsInsideVm())

    def testIsNotInsideVm(self):
        osutils.WriteFile(self.model_file, "ST1000DM000-1CH1")
        self.assertFalse(osutils.IsInsideVm())


class MoveDirContentsTestCase(cros_test_lib.MockTempDirTestCase):
    """Test MoveDirContents."""

    def setUp(self):
        self.from_dir = self.tempdir / "from"
        self.to_dir = self.tempdir / "to"
        osutils.SafeMakedirs(self.from_dir)
        osutils.SafeMakedirs(self.to_dir)

    def _crossdevice_rename(self, src, dst):
        raise OSError(errno.EXDEV, "fake cross-device rename failure")

    def testMoveEmptyDir(self):
        """Move empty from directory."""
        osutils.MoveDirContents(self.from_dir, self.to_dir)
        self.assertExists(self.from_dir)
        osutils.MoveDirContents(
            self.from_dir, self.to_dir, remove_from_dir=True
        )
        self.assertNotExists(self.from_dir)
        self.assertListEqual(os.listdir(self.to_dir), [])

    def testMoveFiles(self):
        """Move files from source to destination."""
        osutils.WriteFile(self.from_dir / "a.txt", "aaa")
        osutils.WriteFile(self.from_dir / "b.txt", "bbb")
        osutils.WriteFile(self.from_dir / ".hidden", "hiden")

        osutils.MoveDirContents(self.from_dir, self.to_dir)
        self.assertFileContents(self.to_dir / "a.txt", "aaa")
        self.assertFileContents(self.to_dir / "b.txt", "bbb")
        self.assertFileContents(self.to_dir / ".hidden", "hiden")
        self.assertExists(self.from_dir)
        self.assertNotExists(self.from_dir / "a.txt")
        self.assertNotExists(self.from_dir / "b.txt")
        self.assertNotExists(self.from_dir / ".hidden")

    def testMoveFilesAndDelete(self):
        """Move files from source to destination and delete source."""
        osutils.WriteFile(self.from_dir / "a.txt", "aaa")
        osutils.WriteFile(self.from_dir / "b.txt", "bbb")
        osutils.MoveDirContents(
            self.from_dir, self.to_dir, remove_from_dir=True
        )
        self.assertNotExists(self.from_dir)

    def testNonEmptyDestination(self):
        """Move files from source to destination, which has contents."""
        osutils.WriteFile(self.to_dir / "a.txt", "aaa")
        osutils.WriteFile(self.to_dir / "b.txt", "bbb")
        with self.assertRaises(osutils.BadPathsException):
            osutils.MoveDirContents(self.from_dir, self.to_dir)
        osutils.MoveDirContents(self.from_dir, self.to_dir, allow_nonempty=True)

    def testMoveDir(self):
        """Move files and directory from source to destination."""
        osutils.WriteFile(self.from_dir / "a.txt", "aaa")
        osutils.SafeMakedirs(self.from_dir / "b")
        osutils.WriteFile(self.from_dir / "b" / "b.txt", "bbb")

        osutils.MoveDirContents(self.from_dir, self.to_dir)
        self.assertFileContents(self.to_dir / "a.txt", "aaa")
        self.assertFileContents(self.to_dir / "b" / "b.txt", "bbb")
        self.assertExists(self.from_dir)
        self.assertNotExists(self.from_dir / "b" / "b.txt")

    def testSymlink(self):
        """Move symlink from source to destination."""
        osutils.WriteFile(self.tempdir / "a.txt", "aaa")
        (self.from_dir / "sym.txt").symlink_to(self.tempdir / "a.txt")
        osutils.MoveDirContents(self.from_dir, self.to_dir)
        self.assertTrue((self.to_dir / "sym.txt").is_symlink())
        self.assertEqual(
            os.readlink(self.to_dir / "sym.txt"), str(self.tempdir / "a.txt")
        )

    def testSymlinkTargetDoesntExist(self):
        """Move symlink from source to destination when target doesn't exist."""
        (self.from_dir / "sym.txt").symlink_to(self.tempdir / "a.txt")
        self.assertNotExists(self.tempdir / "a.txt")

        osutils.MoveDirContents(self.from_dir, self.to_dir)

        self.assertTrue((self.to_dir / "sym.txt").is_symlink())
        self.assertNotExists(self.tempdir / "a.txt")
        self.assertEqual(
            os.readlink(self.to_dir / "sym.txt"), str(self.tempdir / "a.txt")
        )

    def testSymlinkTargetDoesntExistCrossDevice(self):
        """Move symlink from source to destination, cross-device.

        Cover a few cases when we can't do easy os.rename(), such as when
        moving across filesystem boundaries.
        """
        # Mock os.rename() to fail, so shutil will fall back to copy
        # operations.
        _ = self.PatchObject(os, "rename", side_effect=self._crossdevice_rename)

        (self.from_dir / "sym.txt").symlink_to(self.tempdir / "a.txt")
        (self.to_dir / "sym.txt").symlink_to(self.tempdir / "b.txt")
        self.assertNotExists(self.tempdir / "a.txt")
        self.assertNotExists(self.tempdir / "b.txt")

        osutils.MoveDirContents(self.from_dir, self.to_dir, allow_nonempty=True)

        self.assertTrue((self.to_dir / "sym.txt").is_symlink())
        self.assertNotExists(self.tempdir / "a.txt")
        self.assertEqual(
            os.readlink(self.to_dir / "sym.txt"),
            str(self.tempdir / "a.txt"),
        )

    def testMoveDirCrossDevice(self):
        """Move dir across filesystem boundaries."""
        # Mock os.rename() to fail, so shutil will fall back to copy
        # operations.
        _ = self.PatchObject(os, "rename", side_effect=self._crossdevice_rename)

        osutils.SafeMakedirs(self.from_dir / "b")
        osutils.WriteFile(self.from_dir / "b" / "a.txt", "aaa")
        osutils.WriteFile(self.from_dir / "b" / "b.txt", "bbb")

        osutils.MoveDirContents(self.from_dir, self.to_dir)
        self.assertFileContents(self.to_dir / "b" / "a.txt", "aaa")
        self.assertFileContents(self.to_dir / "b" / "b.txt", "bbb")
        self.assertExists(self.from_dir)
        self.assertNotExists(self.from_dir / "b" / "a.txt")
        self.assertNotExists(self.from_dir / "b" / "b.txt")

    def testOverWriteFiles(self):
        """Move files with same name from source to destination."""
        # test dotfiles in top and multiple level directories.
        D = cros_test_lib.Directory
        src_layout = (
            D("a", ["a.txt"]),
            D("b", ["b.txt"]),
            "top.txt",
            ".hidden",
        )
        dest_layout = (
            D("a", ["a.txt", ".hidden", "b.txt"]),
            "top.txt",
            ".hidden",
            # test a directory in source directory having a file with same name
            # in destination.
            "b",
        )
        cros_test_lib.CreateOnDiskHierarchy(self.from_dir, src_layout)
        cros_test_lib.CreateOnDiskHierarchy(self.to_dir, dest_layout)
        osutils.WriteFile(self.from_dir / "top.txt", "aaa")
        osutils.WriteFile(self.from_dir / ".hidden", "hidden")
        osutils.WriteFile(self.from_dir / "a" / "a.txt", "aaa")

        osutils.MoveDirContents(self.from_dir, self.to_dir, allow_nonempty=True)
        self.assertFileContents(self.to_dir / "top.txt", "aaa")
        self.assertFileContents(self.to_dir / ".hidden", "hidden")
        self.assertFileContents(self.to_dir / "a" / "a.txt", "aaa")
        self.assertExists(self.to_dir / "a" / ".hidden")
        self.assertExists(self.to_dir / "a" / "b.txt")
        self.assertTrue((self.to_dir / "b").is_dir())
        self.assertExists(self.to_dir / "b" / "b.txt")

    def testOverlaidDirs(self):
        """Move files with overlapping directories."""
        D = cros_test_lib.Directory
        src_layout = (
            D("a", ["foo.txt"]),
            D("b", []),
        )
        dest_layout = (D("a", ["bar.txt"]),)
        cros_test_lib.CreateOnDiskHierarchy(self.from_dir, src_layout)
        cros_test_lib.CreateOnDiskHierarchy(self.to_dir, dest_layout)

        osutils.MoveDirContents(self.from_dir, self.to_dir, allow_nonempty=True)

        self.assertNotExists(self.from_dir / "a")
        self.assertNotExists(self.from_dir / "b")
        self.assertExists(self.to_dir / "a" / "foo.txt")
        self.assertExists(self.to_dir / "a" / "bar.txt")
        self.assertExists(self.to_dir / "b")

    def testSameDirectory(self):
        """Test source and destination directory are the same."""
        osutils.MoveDirContents(self.from_dir, self.from_dir)
        self.assertExists(self.from_dir)
        osutils.MoveDirContents(
            self.from_dir, self.from_dir, remove_from_dir=True
        )
        self.assertExists(self.from_dir)

    def testMissingDirectory(self):
        """Test source and destination directory missing case."""
        osutils.RmDir(self.from_dir)
        with self.assertRaises(osutils.BadPathsException):
            osutils.MoveDirContents(self.from_dir, self.to_dir)
        osutils.RmDir(self.to_dir)
        osutils.SafeMakedirs(self.from_dir)
        with self.assertRaises(osutils.BadPathsException):
            osutils.MoveDirContents(self.from_dir, self.to_dir)


class CopyDirContentsTestCase(cros_test_lib.TempDirTestCase):
    """Test CopyDirContents."""

    def testCopyEmptyDir(self):
        """Copy "empty" contents from a dir."""
        in_dir = os.path.join(self.tempdir, "input")
        out_dir = os.path.join(self.tempdir, "output")
        osutils.SafeMakedirsNonRoot(in_dir)
        osutils.SafeMakedirsNonRoot(out_dir)
        osutils.CopyDirContents(in_dir, out_dir)

    def testCopyFiles(self):
        """Copy from a dir that contains files."""
        in_dir = os.path.join(self.tempdir, "input")
        out_dir = os.path.join(self.tempdir, "output")
        osutils.SafeMakedirsNonRoot(in_dir)
        osutils.WriteFile(os.path.join(in_dir, "a.txt"), "aaa")
        osutils.WriteFile(os.path.join(in_dir, "b.txt"), "bbb")
        osutils.SafeMakedirsNonRoot(out_dir)
        osutils.CopyDirContents(in_dir, out_dir)
        self.assertEqual(
            osutils.ReadFile(os.path.join(out_dir, "a.txt")).strip(), "aaa"
        )
        self.assertEqual(
            osutils.ReadFile(os.path.join(out_dir, "b.txt")).strip(), "bbb"
        )

    def testCopyTree(self):
        """Copy from a dir that contains files."""
        in_dir = os.path.join(self.tempdir, "input")
        out_dir = os.path.join(self.tempdir, "output")
        osutils.SafeMakedirsNonRoot(in_dir)
        osutils.SafeMakedirsNonRoot(os.path.join(in_dir, "a"))
        osutils.WriteFile(os.path.join(in_dir, "a", "b.txt"), "bbb")
        osutils.SafeMakedirsNonRoot(out_dir)
        osutils.CopyDirContents(in_dir, out_dir)
        self.assertEqual(
            osutils.ReadFile(os.path.join(out_dir, "a", "b.txt")).strip(), "bbb"
        )

    def testSourceDirDoesNotExistRaises(self):
        """Coping from a non-existent source dir raises."""
        in_dir = os.path.join(self.tempdir, "input")
        out_dir = os.path.join(self.tempdir, "output")
        osutils.SafeMakedirsNonRoot(out_dir)
        with self.assertRaises(osutils.BadPathsException):
            osutils.CopyDirContents(in_dir, out_dir)

    def testDestinationDirDoesNotExistRaises(self):
        """Coping to a non-existent destination dir raises."""
        in_dir = os.path.join(self.tempdir, "input")
        out_dir = os.path.join(self.tempdir, "output")
        osutils.SafeMakedirsNonRoot(in_dir)
        with self.assertRaises(osutils.BadPathsException):
            osutils.CopyDirContents(in_dir, out_dir)

    def testDestinationDirNonEmptyRaises(self):
        """Coping to a non-empty destination dir raises."""
        in_dir = os.path.join(self.tempdir, "input")
        out_dir = os.path.join(self.tempdir, "output")
        osutils.SafeMakedirsNonRoot(in_dir)
        osutils.SafeMakedirsNonRoot(out_dir)
        osutils.SafeMakedirsNonRoot(os.path.join(out_dir, "blah"))
        with self.assertRaises(osutils.BadPathsException):
            osutils.CopyDirContents(in_dir, out_dir)

    def testDestinationDirNonEmptyAllowNonEmptySet(self):
        """Copying to a non-empty destination with allow_nonempty succeeds."""
        in_dir = os.path.join(self.tempdir, "input")
        out_dir = os.path.join(self.tempdir, "output")
        osutils.SafeMakedirsNonRoot(in_dir)
        osutils.SafeMakedirsNonRoot(out_dir)
        osutils.SafeMakedirsNonRoot(os.path.join(out_dir, "blah"))
        osutils.CopyDirContents(in_dir, out_dir, allow_nonempty=True)

    def testCopyingSymlinks(self):
        in_dir = os.path.join(self.tempdir, "input")
        in_dir_link = os.path.join(in_dir, "link")
        in_dir_symlinks_dir = os.path.join(in_dir, "holding_symlink")
        in_dir_symlinks_dir_link = os.path.join(in_dir_symlinks_dir, "link")

        out_dir = os.path.join(self.tempdir, "output")
        out_dir_link = os.path.join(out_dir, "link")
        out_dir_symlinks_dir = os.path.join(out_dir, "holding_symlink")
        out_dir_symlinks_dir_link = os.path.join(out_dir_symlinks_dir, "link")

        # Create directories and symlinks appropriately.
        osutils.SafeMakedirsNonRoot(in_dir)
        osutils.SafeMakedirsNonRoot(in_dir_symlinks_dir)
        os.symlink(self.tempdir, in_dir_link)
        os.symlink(self.tempdir, in_dir_symlinks_dir_link)

        osutils.SafeMakedirsNonRoot(out_dir)

        # Actual execution.
        osutils.CopyDirContents(in_dir, out_dir, symlinks=True)

        # Assertions.
        self.assertTrue(os.path.islink(out_dir_link))
        self.assertTrue(os.path.islink(out_dir_symlinks_dir_link))

    def testNotCopyingSymlinks(self):
        # Create temporary to symlink against.
        tmp_file = os.path.join(self.tempdir, "a.txt")
        osutils.WriteFile(tmp_file, "aaa")
        tmp_subdir = os.path.join(self.tempdir, "tmp")
        osutils.SafeMakedirsNonRoot(tmp_subdir)
        tmp_subdir_file = os.path.join(tmp_subdir, "b.txt")
        osutils.WriteFile(tmp_subdir_file, "bbb")

        in_dir = os.path.join(self.tempdir, "input")
        in_dir_link = os.path.join(in_dir, "link")
        in_dir_symlinks_dir = os.path.join(in_dir, "holding_symlink")
        in_dir_symlinks_dir_link = os.path.join(in_dir_symlinks_dir, "link")

        out_dir = os.path.join(self.tempdir, "output")
        out_dir_file = os.path.join(out_dir, "link")
        out_dir_symlinks_dir = os.path.join(out_dir, "holding_symlink")
        out_dir_symlinks_dir_subdir = os.path.join(out_dir_symlinks_dir, "link")

        # Create directories and symlinks appropriately.
        osutils.SafeMakedirsNonRoot(in_dir)
        osutils.SafeMakedirsNonRoot(in_dir_symlinks_dir)
        os.symlink(tmp_file, in_dir_link)
        os.symlink(tmp_subdir, in_dir_symlinks_dir_link)

        osutils.SafeMakedirsNonRoot(out_dir)

        # Actual execution.
        osutils.CopyDirContents(in_dir, out_dir, symlinks=False)

        # Assertions.
        self.assertFalse(os.path.islink(out_dir_file))
        self.assertFalse(os.path.islink(out_dir_symlinks_dir_subdir))
        self.assertTrue(filecmp.cmp(out_dir_file, tmp_file))
        self.assertTrue(
            filecmp.cmp(
                os.path.join(out_dir_symlinks_dir_subdir, "b.txt"),
                tmp_subdir_file,
            )
        )

    def testCopyingSymlinksAndFilesWithPathArgs(self):
        """Copying given |Path| arguments works properly for symlinks+files."""
        in_dir = self.tempdir / "input"
        osutils.SafeMakedirs(in_dir)

        tmp_file = in_dir / "a.txt"
        tmp_file.write_text("aaa", encoding="utf-8")
        tmp_file_link = tmp_file.with_suffix(".link")
        tmp_file_link.symlink_to(tmp_file)

        out_dir = self.tempdir / "output"
        osutils.SafeMakedirs(out_dir)
        osutils.CopyDirContents(in_dir, out_dir, symlinks=True)

        out_tmp_file = out_dir / tmp_file.name
        self.assertEqual(out_tmp_file.read_text(encoding="utf-8"), "aaa")
        out_tmp_file_link = out_dir / tmp_file_link.name
        self.assertEqual(Path(os.readlink(out_tmp_file_link)), tmp_file)

    def testCopyingSubDirWithPathArgs(self):
        """Copying given |Path| arguments works properly for subdirectories."""
        in_dir = self.tempdir / "input"
        osutils.SafeMakedirs(in_dir)

        tmp_file = in_dir / "subdir" / "a.txt"
        osutils.SafeMakedirs(tmp_file.parent)

        tmp_file.write_text("aaa", encoding="utf-8")

        out_dir = self.tempdir / "output"
        osutils.SafeMakedirs(out_dir)
        osutils.CopyDirContents(in_dir, out_dir, symlinks=True)

        out_tmp_file = out_dir / "subdir" / tmp_file.name
        self.assertEqual(out_tmp_file.read_text(encoding="utf-8"), "aaa")


class WhichTests(cros_test_lib.TempDirTestCase):
    """Test Which."""

    def setUp(self):
        self.prog_path = os.path.join(self.tempdir, "prog")
        osutils.Touch(self.prog_path, mode=0o755)
        self.text_path = os.path.join(self.tempdir, "text")
        osutils.Touch(self.text_path, mode=0o644)

        # A random path for us to validate.
        os.environ["PATH"] = "/:%s" % (self.tempdir,)

    def testPath(self):
        """Check $PATH/path handling."""
        self.assertEqual(self.prog_path, osutils.Which("prog"))

        os.environ["PATH"] = ""
        self.assertEqual(None, osutils.Which("prog"))

        self.assertEqual(
            self.prog_path, osutils.Which("prog", path=self.tempdir)
        )

    def testMode(self):
        """Check mode handling."""
        self.assertEqual(self.prog_path, osutils.Which("prog"))
        self.assertEqual(self.prog_path, osutils.Which("prog", mode=os.X_OK))
        self.assertEqual(self.prog_path, osutils.Which("prog", mode=os.R_OK))
        self.assertEqual(None, osutils.Which("text"))
        self.assertEqual(None, osutils.Which("text", mode=os.X_OK))
        self.assertEqual(self.text_path, osutils.Which("text", mode=os.F_OK))

    def testRoot(self):
        """Check root handling."""
        self.assertEqual(None, osutils.Which("prog", root="/........."))
        self.assertEqual(
            self.prog_path, osutils.Which("prog", path="/", root=self.tempdir)
        )


class UmaskTests(cros_test_lib.TestCase):
    """Test Umask."""

    @staticmethod
    def getUmask():
        """Return the current umask setting."""
        # Testing this is messy because there is no syscall to look this up
        # without side-effects.  os.umask sets & queries at once.
        m = re.search(
            r"^Umask:\s+([0-7]+)",
            osutils.ReadFile("/proc/self/status"),
            flags=re.M,
        )
        assert m is not None
        return int(m.group(1), 8)

    def testBasic(self):
        """Verify umask is saved & restored."""
        os.umask(0o222)
        with osutils.UmaskContext(0o123) as old:
            assert self.getUmask() == 0o123
        assert self.getUmask() == old
        assert old == 0o222


class TestSyncStorage(cros_test_lib.TestCase):
    """Test sync_storage helper."""

    def testNoArgs(self):
        """Verify default behavior."""
        assert osutils.sync_storage()

    def testSudo(self):
        """Verify sudo behavior."""
        assert osutils.sync_storage(sudo=True)
        assert osutils.sync_storage(Path.cwd(), sudo=True)

    def testPath(self):
        """Verify with path."""
        assert osutils.sync_storage(Path.cwd())

    def testMissingPath(self):
        """Verify with path that doesn't work."""
        assert not osutils.sync_storage("alskdjfalskdjflasjdflasjdf")

    def testPathData(self):
        """Verify syncing path data."""
        assert osutils.sync_storage(".", data_only=True)

    def testPathDataNoPath(self):
        """Verify syncing data w/out path."""
        with self.assertRaises(ValueError):
            osutils.sync_storage(data_only=True)

    def testPathFilesystem(self):
        """Verify syncing path filesystem."""
        assert osutils.sync_storage(".", filesystem=True)


class TestMockCmdSyncStorage(cros_test_lib.RunCommandTestCase):
    """Test sync_storage helper with a mock run command."""

    def testSync(self):
        """Verify basic `sync` call."""
        assert osutils.sync_storage()
        assert osutils.sync_storage(sudo=True)
        self.assertEqual(self.rc.call_count, 0)

    def testSyncData(self):
        """Verify basic `sync` call."""
        assert osutils.sync_storage(".", data_only=True, sudo=True)
        self.rc.assertCommandContains(["sync", "--data", "."])

    def testSyncFilesystem(self):
        """Verify basic `sync` call."""
        assert osutils.sync_storage(".", filesystem=True, sudo=True)
        self.rc.assertCommandContains(["sync", "--file-system", "."])

    def testSyncFile(self):
        """Verify basic `sync` call."""
        assert osutils.sync_storage(".", sudo=True)
        self.rc.assertCommandContains(["sync", "."])


class TestMockSyncStorage(cros_test_lib.TestCase):
    """Test sync_storage helper with a mock C library."""

    def testSync(self):
        """Verify we call libc.sync()."""
        m = mock.MagicMock()
        with mock.patch.object(ctypes, "CDLL", return_value=m):
            osutils.sync_storage()
        m.sync.assert_called_once()

    def testFDataSync(self):
        """Verify we call libc.fdatasync()."""
        m = mock.MagicMock()
        with mock.patch.object(ctypes, "CDLL", return_value=m):
            osutils.sync_storage(".", data_only=True)
        m.fdatasync.assert_called_once()

    def testSyncfs(self):
        """Verify we call libc.syncfs()."""
        m = mock.MagicMock()
        with mock.patch.object(ctypes, "CDLL", return_value=m):
            osutils.sync_storage(".", filesystem=True)
        m.syncfs.assert_called_once()

    def testFsync(self):
        """Verify we call libc.fsync()."""
        m = mock.MagicMock()
        with mock.patch.object(ctypes, "CDLL", return_value=m):
            osutils.sync_storage(".")
        m.fsync.assert_called_once()
