# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for the cache.py module."""

import datetime
import hashlib
import os
from unittest import mock

from chromite.lib import cache
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import gs_unittest
from chromite.lib import osutils
from chromite.lib import partial_mock
from chromite.lib import retry_util


class CacheReferenceTest(cros_test_lib.TestCase):
    """Tests for CacheReference.

    Largely focused on exercising the API other objects expect from it.
    """

    # pylint: disable=protected-access

    def setUp(self):
        # These are the funcs CacheReference expects the cache object to have.
        spec = (
            "GetKeyPath",
            "_Insert",
            "_InsertText",
            "_KeyExists",
            "_LockForKey",
            "_Remove",
        )
        self.cache = mock.Mock(spec=spec)
        self.lock = mock.MagicMock()
        self.lock.path = "some/path"
        self.cache._LockForKey.return_value = self.lock

    def testContext(self):
        """Verify we can use it as a context manager."""
        # We should set the acquire member and grab/release the lock.
        ref = cache.CacheReference(self.cache, "key")
        self.assertFalse(ref.acquired)
        self.assertFalse(self.lock.__enter__.called)
        with ref as newref:
            self.assertEqual(ref, newref)
            self.assertTrue(ref.acquired)
            self.assertTrue(self.lock.__enter__.called)
            self.assertFalse(self.lock.__exit__.called)
        self.assertFalse(ref.acquired)
        self.assertTrue(self.lock.__exit__.called)

    def testPath(self):
        """Verify we get a file path for the ref."""
        self.cache.GetKeyPath.return_value = "/foo/bar"

        ref = cache.CacheReference(self.cache, "key")
        self.assertEqual(ref.path, "/foo/bar")

        self.cache.GetKeyPath.assert_called_once_with("key")

    def testLocking(self):
        """Verify Acquire & Release work as expected."""
        ref = cache.CacheReference(self.cache, "key")

        # Check behavior when the lock is free.
        self.assertRaises(AssertionError, ref.Release)
        self.assertFalse(ref.acquired)

        # Check behavior when the lock is held.
        self.assertEqual(ref.Acquire(), None)
        self.assertRaises(AssertionError, ref.Acquire)
        self.assertTrue(ref.acquired)

        # Check behavior after the lock is freed.
        self.assertEqual(ref.Release(), None)
        self.assertFalse(ref.acquired)

    def testExists(self):
        """Verify Exists works when the entry is not in the cache."""
        ref = cache.CacheReference(self.cache, "key")
        self.cache._KeyExists.return_value = False
        self.assertFalse(ref.Exists())

    def testExistsMissing(self):
        """Verify Exists works when the entry is in the cache."""
        ref = cache.CacheReference(self.cache, "key")
        self.cache._KeyExists.return_value = True
        self.assertTrue(ref.Exists())

    def testAssign(self):
        """Verify Assign works as expected."""
        ref = cache.CacheReference(self.cache, "key")
        ref.Assign("/foo")
        self.cache._Insert.assert_called_once_with("key", "/foo")

    def testAssignText(self):
        """Verify AssignText works as expected."""
        ref = cache.CacheReference(self.cache, "key")
        ref.AssignText("text!")
        self.cache._InsertText.assert_called_once_with("key", "text!")

    def testRemove(self):
        """Verify Remove works as expected."""
        ref = cache.CacheReference(self.cache, "key")
        ref.Remove()
        self.cache._Remove.assert_called_once_with("key")

    def testSetDefault(self):
        """Verify SetDefault works when the entry is not in the cache."""
        ref = cache.CacheReference(self.cache, "key")
        self.cache._KeyExists.return_value = False
        ref.SetDefault("/foo")
        self.cache._Insert.assert_called_once_with("key", "/foo")

    def testSetDefaultExists(self):
        """Verify SetDefault works when the entry is in the cache."""
        ref = cache.CacheReference(self.cache, "key")
        self.cache._KeyExists.return_value = True
        ref.SetDefault("/foo")
        self.assertFalse(self.cache._Insert.called)


class CacheTestCase(cros_test_lib.MockTempDirTestCase):
    """Tests for any type of Cache object."""

    def setUp(self):
        self.gs_mock = self.StartPatcher(gs_unittest.GSContextMock())

    def _testAssign(self):
        """Verify we can assign a file to the cache and get it back out."""
        key = ("foo", "bar")
        data = r"text!\nthere"

        path = os.path.join(self.tempdir, "test-file")
        osutils.WriteFile(path, data)

        with self.cache.Lookup(key) as ref:
            self.assertFalse(ref.Exists())
            ref.Assign(path)
            self.assertTrue(ref.Exists())
            self.assertEqual(osutils.ReadFile(ref.path), data)

        with self.cache.Lookup(key) as ref:
            self.assertTrue(ref.Exists())
            self.assertEqual(osutils.ReadFile(ref.path), data)

    def _testAssignData(self):
        """Verify we can assign data to the cache and get it back out."""
        key = ("foo", "bar")
        data = r"text!\nthere"

        with self.cache.Lookup(key) as ref:
            self.assertFalse(ref.Exists())
            ref.AssignText(data)
            self.assertTrue(ref.Exists())
            self.assertEqual(osutils.ReadFile(ref.path), data)

        with self.cache.Lookup(key) as ref:
            self.assertTrue(ref.Exists())
            self.assertEqual(osutils.ReadFile(ref.path), data)

    def _testRemove(self):
        """Verify we can remove entries from the cache."""
        key = ("foo", "bar")
        data = r"text!\nthere"

        with self.cache.Lookup(key) as ref:
            self.assertFalse(ref.Exists())
            ref.AssignText(data)
            self.assertTrue(ref.Exists())
            ref.Remove()
            self.assertFalse(ref.Exists())


class DiskCacheTest(CacheTestCase):
    """Tests for DiskCache."""

    def setUp(self):
        self.cache = cache.DiskCache(self.tempdir)

    testAssign = CacheTestCase._testAssign
    testAssignData = CacheTestCase._testAssignData
    testRemove = CacheTestCase._testRemove

    def testListKeys(self):
        """Verifies that ListKeys() returns any items present in the cache."""
        osutils.Touch(os.path.join(self.tempdir, "file1"))
        cache.CacheReference(self.cache, ("key1",)).Assign(
            os.path.join(self.tempdir, "file1")
        )
        osutils.Touch(os.path.join(self.tempdir, "file2"))
        cache.CacheReference(self.cache, ("key2",)).Assign(
            os.path.join(self.tempdir, "file2")
        )

        keys = self.cache.ListKeys()
        self.assertEqual(len(keys), 2)
        self.assertIn(("key1",), keys)
        self.assertIn(("key2",), keys)

    def testDeleteStale(self):
        """Verify DeleteStale removes a sufficiently old item in the cache."""
        osutils.Touch(os.path.join(self.tempdir, "file1"))
        cache_ref = cache.CacheReference(self.cache, ("key1",))
        cache_ref.Assign(os.path.join(self.tempdir, "file1"))
        now = datetime.datetime.now()

        # 'Now' will be 10 days in the future, but max_age is 20 days. So no
        # items should be deleted.
        ten_days_ahead = now + datetime.timedelta(days=10)
        with mock.patch("chromite.lib.cache.datetime") as mock_datetime:
            mock_datetime.datetime.now.return_value = ten_days_ahead
            mock_datetime.datetime.fromtimestamp.side_effect = (
                datetime.datetime.fromtimestamp
            )
            mock_datetime.timedelta = datetime.timedelta
            self.cache.DeleteStale(datetime.timedelta(days=20))
        self.assertTrue(cache_ref.Exists())

        # Running it again 30 days in the future should delete everything.
        thirty_days_ahead = now + datetime.timedelta(days=30)
        with mock.patch("chromite.lib.cache.datetime") as mock_datetime:
            mock_datetime.datetime.now.return_value = thirty_days_ahead
            mock_datetime.datetime.fromtimestamp.side_effect = (
                datetime.datetime.fromtimestamp
            )
            mock_datetime.timedelta = datetime.timedelta
            self.cache.DeleteStale(datetime.timedelta(days=20))
        self.assertFalse(cache_ref.Exists())


class RemoteCacheTest(CacheTestCase):
    """Tests for RemoteCache."""

    def setUp(self):
        self.cache = cache.RemoteCache(self.tempdir)

    testAssign = CacheTestCase._testAssign
    testAssignData = CacheTestCase._testAssignData
    testRemove = CacheTestCase._testRemove

    def testFetchFile(self):
        """Verify we handle file:// URLs."""
        key = ("file", "foo")
        data = "daaaaata"

        path = os.path.join(self.tempdir, "test-file")
        url = "file://%s" % path
        osutils.WriteFile(path, data)

        with self.cache.Lookup(key) as ref:
            self.assertFalse(ref.Exists())
            ref.Assign(url)
            self.assertTrue(ref.Exists())
            self.assertEqual(osutils.ReadFile(ref.path), data)

    def testFetchNonGs(self):
        """Verify we fetch remote URLs and save the result."""

        def _Fetch(*args, **_kwargs):
            # Probably shouldn't assume this ordering, but best way for now.
            cmd = args[0]
            local_path = cmd[-1]
            osutils.Touch(local_path)

        self.PatchObject(retry_util, "RunCurl", side_effect=_Fetch)

        schemes = ("ftp", "http", "https")
        for scheme in schemes:
            key = (scheme, "foo")
            url = "%s://some.site.localdomain/file_go_boom" % scheme
            with self.cache.Lookup(key) as ref:
                self.assertFalse(ref.Exists())
                ref.Assign(url)
                self.assertTrue(ref.Exists())

    def testFetchGs(self):
        """Verify we fetch from Google Storage and save the result."""

        # pylint: disable=unused-argument
        def _Fetch(_ctx, cmd, **kwargs):
            # Touch file we tried to copy too.
            osutils.Touch(cmd[-1])

        self.gs_mock.AddCmdResult(
            ["cp", "-v", "--", partial_mock.Ignore(), partial_mock.Ignore()],
            side_effect=_Fetch,
        )

        key = ("gs",)
        url = "gs://some.site.localdomain/file_go_boom"
        with self.cache.Lookup(key) as ref:
            self.assertFalse(ref.Exists())
            ref.Assign(url)
            self.assertTrue(ref.Exists())

    def testFetchFileSha1(self):
        """Verify we validate hash_sha1 when passed."""
        # pylint: disable=protected-access

        local_path = self.tempdir / "local-path"
        data = "daaaaata"
        path = self.tempdir / "test-file"
        url = "file://%s" % path
        osutils.WriteFile(path, data)

        # Valid SHA-1, should not raise.
        self.cache._Fetch(
            url,
            local_path,
            hash_sha1=hashlib.sha1(data.encode("utf-8")).hexdigest(),
        )

        with self.assertRaises(cache.Error):
            self.cache._Fetch(url, local_path, hash_sha1="12345")

    def testFetchFileMode(self):
        """Verify changing the file mode."""
        # pylint: disable=protected-access

        local_path = self.tempdir / "local-path"
        data = "daaaaata"
        path = self.tempdir / "test-file"
        url = "file://%s" % path
        osutils.WriteFile(path, data)

        self.cache._Fetch(url, local_path, mode=0o654)
        self.assertEqual(osutils.ReadFile(local_path), data)
        self.assertEqual(os.stat(local_path).st_mode & 0o777, 0o654)


class TarballCacheTest(CacheTestCase):
    """Tests for TarballCache."""

    def setUp(self):
        self.cache = cache.RemoteCache(self.tempdir)

    testAssign = CacheTestCase._testAssign
    testAssignData = CacheTestCase._testAssignData
    testRemove = CacheTestCase._testRemove


class UntarTest(cros_test_lib.RunCommandTestCase):
    """Tests cache.Untar()."""

    @mock.patch("chromite.lib.cros_build_lib.CompressionDetectType")
    def testNoneCompression(self, mock_compression_type):
        """Tests Untar with an uncompressed tarball."""
        mock_compression_type.return_value = cros_build_lib.CompressionType.NONE
        cache.Untar("/some/tarball.tar.gz", "/")
        self.assertCommandContains(["tar", "-xpf", "/some/tarball.tar.gz"])

    @mock.patch("chromite.lib.cros_build_lib.CompressionDetectType")
    @mock.patch("chromite.lib.cros_build_lib.FindCompressor")
    def testCompression(self, mock_find_compressor, mock_compression_type):
        """Tests Untar with a compressed tarball."""
        mock_compression_type.return_value = "some-compression"
        mock_find_compressor.return_value = "/bin/custom/xz"
        cache.Untar("/some/tarball.tar.xz", "/")
        self.assertCommandContains(
            ["tar", "-I", "/bin/custom/xz", "-xpf", "/some/tarball.tar.xz"]
        )

    @mock.patch("chromite.lib.cros_build_lib.CompressionDetectType")
    @mock.patch("chromite.lib.cros_build_lib.FindCompressor")
    def testPbzip2Compression(
        self, mock_find_compressor, mock_compression_type
    ):
        """Tests decompressing a tarball using pbzip2."""
        mock_compression_type.return_value = "some-compression"
        mock_find_compressor.return_value = "/bin/custom/pbzip2"
        cache.Untar("/some/tarball.tbz2", "/")
        self.assertCommandContains(
            [
                "tar",
                "-I",
                "/bin/custom/pbzip2 --ignore-trailing-garbage=1",
                "-xpf",
                "/some/tarball.tbz2",
            ]
        )


class Sha1FileTest(cros_test_lib.TestCase):
    """Test the Sha1File function."""

    def testEmpty(self):
        """Test Sha1File on a empty file."""
        self.assertEqual(
            cache.Sha1File("/dev/null"),
            # sha1sum /dev/null
            "da39a3ee5e6b4b0d3255bfef95601890afd80709",
        )

    def testLargeFile(self):
        """Test Sha1File on a file that is greater than 4069 bytes."""
        expected_sha1 = hashlib.sha1(
            osutils.ReadFile(__file__, "rb")
        ).hexdigest()
        self.assertEqual(cache.Sha1File(__file__), expected_sha1)
