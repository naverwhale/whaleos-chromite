# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""field_handler module tests."""

import os
from pathlib import Path
from typing import Optional

from chromite.api import field_handler
from chromite.api.gen.chromite.api import build_api_test_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import chroot_lib
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import remoteexec_util


class ChrootHandlerTest(cros_test_lib.TestCase):
    """ChrootHandler tests."""

    def setUp(self):
        self.path = "/chroot/dir"
        self.cache_dir = "/cache/dir"
        self.chrome_dir = "/chrome/dir"
        self.env = {"FEATURES": "thing", "CHROME_ORIGIN": "LOCAL_SOURCE"}
        self.expected_chroot = chroot_lib.Chroot(
            path=self.path,
            cache_dir=self.cache_dir,
            chrome_root=self.chrome_dir,
            env=self.env,
        )

    def test_parse_chroot_success(self):
        """Test successful Chroot message parse."""
        chroot_msg = common_pb2.Chroot()
        chroot_msg.path = self.path
        chroot_msg.cache_dir = self.cache_dir
        chroot_msg.chrome_dir = self.chrome_dir
        chroot_msg.env.features.add().feature = "thing"

        chroot_handler = field_handler.ChrootHandler(clear_field=False)
        parsed_chroot = chroot_handler.parse_chroot(chroot_msg)

        self.assertEqual(self.expected_chroot, parsed_chroot)

    def test_handle_success(self):
        """Test a successful Chroot message parse from a parent message."""
        message = build_api_test_pb2.TestRequestMessage()
        message.chroot.path = self.path
        message.chroot.cache_dir = self.cache_dir
        message.chroot.chrome_dir = self.chrome_dir
        message.chroot.env.features.add().feature = "thing"

        # First a no-clear parse.
        chroot_handler = field_handler.ChrootHandler(clear_field=False)
        chroot = chroot_handler.handle(message)

        self.assertEqual(self.expected_chroot, chroot)
        self.assertEqual(message.chroot.path, self.path)

        # A clear field parse.
        clear_chroot_handler = field_handler.ChrootHandler(clear_field=True)
        chroot = clear_chroot_handler.handle(message)

        self.assertEqual(self.expected_chroot, chroot)
        self.assertFalse(message.chroot.path)

    def test_handle_empty_chroot_message(self):
        """Test handling of an empty chroot message."""
        message = build_api_test_pb2.TestRequestMessage()
        empty_chroot = chroot_lib.Chroot()

        chroot_handler = field_handler.ChrootHandler(clear_field=False)
        chroot = chroot_handler.handle(message)

        self.assertEqual(empty_chroot, chroot)

    def test_handle_no_chroot_message(self):
        """Test handling of a message with no Chroot field."""
        message = build_api_test_pb2.MultiFieldMessage()

        # Double-check we didn't grow a Chroot field.
        for descriptor in message.DESCRIPTOR.fields:
            field = getattr(message, descriptor.name)
            self.assertFalse(isinstance(field, common_pb2.Chroot))

        with self.assertRaises(field_handler.MissingChrootMessage):
            field_handler.handle_chroot(message, clear_field=False)


class HandleRemoteexec(cros_test_lib.TempDirTestCase):
    """Tests for handling remoteexec."""

    def test_handle_remoteexec(self):
        """Test handling remoteexec when there is a RemoteexecConfig."""
        reclient_dir = os.path.join(self.tempdir, "cipd/rbe")
        reproxy_cfg_file = os.path.join(
            self.tempdir, "reclient_cfgs/reproxy_config.cfg"
        )

        osutils.SafeMakedirs(reclient_dir)
        osutils.Touch(reproxy_cfg_file, makedirs=True)
        remoteexec_config = common_pb2.RemoteexecConfig(
            reclient_dir=reclient_dir, reproxy_cfg_file=reproxy_cfg_file
        )
        message = build_api_test_pb2.TestRequestMessage(
            remoteexec_config=remoteexec_config
        )

        expected = remoteexec_util.Remoteexec(reclient_dir, reproxy_cfg_file)
        self.assertEqual(expected, field_handler.handle_remoteexec(message))

    def test_handle_remoteexec_no_config(self):
        """Test handling remoteexec when there is no RmoteexecConfig."""
        message = build_api_test_pb2.TestRequestMessage()
        self.assertIsNone(field_handler.handle_remoteexec(message))


class CopyPathInTest(cros_test_lib.MockTempDirTestCase):
    """PathHandler tests."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        self.chroot = chroot_lib.Chroot(
            path=self.tempdir / "chroot",
            out_path=self.tempdir / "out",
        )

        self.source_dir = os.path.join(self.chroot.path, "source")
        self.dest_dir = os.path.join(self.chroot.path, "destination")
        osutils.SafeMakedirs(self.source_dir)
        osutils.SafeMakedirs(self.dest_dir)
        osutils.SafeMakedirs(self.chroot.out_path)

        self.source_file1 = os.path.join(self.source_dir, "file1")
        self.file1_contents = "file 1"
        osutils.WriteFile(self.source_file1, self.file1_contents)

        self.file2_contents = "some data"
        self.source_file2 = os.path.join(self.source_dir, "file2")
        osutils.WriteFile(self.source_file2, self.file2_contents)

    def _path_checks(self, source_file, dest_file, contents=None):
        """Set of common checks for the copied files/directories."""
        # Message should now reflect the new path.
        self.assertNotEqual(source_file, dest_file)
        # The new path should be in the destination directory.
        self.assertStartsWith(dest_file, self.dest_dir)
        # The new file should exist.
        self.assertExists(dest_file)

        if contents:
            # The contents should be the same as the source file.
            self.assertFileContents(dest_file, contents)

    def test_handle_file(self):
        """Test handling of a single file."""
        message = build_api_test_pb2.TestRequestMessage()
        message.path.path = self.source_file1
        message.path.location = common_pb2.Path.OUTSIDE

        with field_handler.copy_paths_in(message, self.dest_dir, delete=True):
            new_path = message.path.path
            self._path_checks(self.source_file1, new_path, self.file1_contents)

        # The file should have been deleted on exit with delete=True.
        self.assertNotExists(new_path)
        # The original should still exist.
        self.assertExists(self.source_file1)
        # The path should get reset.
        self.assertEqual(message.path.path, self.source_file1)

    def test_handle_files(self):
        """Test handling of multiple files."""
        message = build_api_test_pb2.TestRequestMessage()
        message.path.path = self.source_file1
        message.path.location = common_pb2.Path.OUTSIDE
        message.another_path.path = self.source_file2
        message.another_path.location = common_pb2.Path.OUTSIDE

        with field_handler.copy_paths_in(message, self.dest_dir, delete=False):
            new_path1 = message.path.path
            new_path2 = message.another_path.path

            self._path_checks(self.source_file1, new_path1, self.file1_contents)
            self._path_checks(self.source_file2, new_path2, self.file2_contents)

        # The files should still exist with delete=False.
        self.assertExists(new_path1)
        self.assertExists(new_path2)

    def test_handle_nested_file(self):
        """Test the nested path handling."""
        message = build_api_test_pb2.TestRequestMessage()
        message.nested_path.path.path = self.source_file1
        message.nested_path.path.location = common_pb2.Path.OUTSIDE

        with field_handler.copy_paths_in(message, self.dest_dir):
            new_path = message.nested_path.path.path
            self._path_checks(self.source_file1, new_path, self.file1_contents)

    def test_handle_directory(self):
        """Test handling of a directory."""
        message = build_api_test_pb2.TestRequestMessage()
        message.path.path = self.source_dir
        message.path.location = common_pb2.Path.OUTSIDE

        with field_handler.copy_paths_in(message, self.dest_dir):
            new_path = message.path.path

            self._path_checks(self.source_dir, self.dest_dir)
            # Make sure both directories have the same files.
            self.assertCountEqual(
                os.listdir(self.source_dir), os.listdir(new_path)
            )

    def test_direction(self):
        """Test the direction argument preventing copies."""
        message = build_api_test_pb2.TestRequestMessage()
        message.path.path = self.source_file1
        message.path.location = common_pb2.Path.INSIDE

        with field_handler.copy_paths_in(message, self.dest_dir, delete=True):
            self.assertEqual(self.source_file1, message.path.path)

        # It should not be deleting the file when it doesn't need to copy it
        # even with delete=True.
        self.assertExists(self.source_file1)

    def test_inside_chroot(self):
        """Test the transfer inside chroot handling."""
        message = build_api_test_pb2.TestRequestMessage()
        message.path.path = self.source_dir
        message.path.location = common_pb2.Path.OUTSIDE

        with field_handler.copy_paths_in(
            message, self.dest_dir, chroot=self.chroot
        ):
            new_path = message.path.path
            # The prefix should be removed.
            self.assertFalse(new_path.startswith(str(self.tempdir)))


class SyncDirsTest(cros_test_lib.MockTempDirTestCase):
    """Tests for sync_dirs."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        D = cros_test_lib.Directory
        filesystem = (
            D(
                "sources",
                (
                    D("single_file", ("single_file.txt",)),
                    D(
                        "nested_directories",
                        (
                            "basedir_file.log",
                            D(
                                "nested1",
                                (
                                    "nested1.txt",
                                    D("nested2", ("nested2.txt",)),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, filesystem)

        self.chroot = chroot_lib.Chroot(
            path=self.tempdir / "chroot",
            out_path=self.tempdir / "out",
        )
        self.destination = os.path.join(self.chroot.tmp, "tempdir")
        osutils.SafeMakedirs(self.chroot.path)
        osutils.SafeMakedirs(self.destination)
        self.inside_path = "/tmp/tempdir"

        self.single_file_src = os.path.join(
            self.tempdir, "sources", "single_file"
        )
        self.sf_src_file = os.path.join(self.single_file_src, "single_file.txt")
        self.sf_dest_file = os.path.join(self.destination, "single_file.txt")

        self.nested_dirs_src = os.path.join(
            self.tempdir, "sources", "nested_directories"
        )
        self.nested_src_files = (
            os.path.join(self.nested_dirs_src, "basedir_file.log"),
            os.path.join(self.nested_dirs_src, "nested1", "nested1.txt"),
            os.path.join(
                self.nested_dirs_src, "nested1", "nested2", "nested2.txt"
            ),
        )
        self.nested_dest_files = (
            os.path.join(self.destination, "basedir_file.log"),
            os.path.join(self.destination, "nested1", "nested1.txt"),
            os.path.join(self.destination, "nested1", "nested2", "nested2.txt"),
        )

        self.message = build_api_test_pb2.TestRequestMessage()

    def _assertExist(self, files):
        for f in files:
            self.assertExists(f)

    def _assertNotExist(self, files):
        for f in files:
            self.assertNotExists(f)

    def testSingleFileTransfer(self):
        """Single source file syncs."""
        self.message.synced_dir.dir = self.single_file_src

        # Verify source files exist and destination files do not.
        self.assertExists(self.sf_src_file)
        self.assertNotExists(self.sf_dest_file)

        with field_handler.sync_dirs(
            self.message, self.destination, self.chroot
        ):
            # Verify the prefix is getting correctly stripped.
            self.assertEqual(self.message.synced_dir.dir, self.inside_path)
            # Verify the files have all been correctly copied in.
            self.assertExists(self.sf_dest_file)

        self.assertEqual(self.message.synced_dir.dir, self.single_file_src)
        # Verify the files have all been copied out.
        self.assertExists(self.sf_src_file)

    def testNestedFileSync(self):
        """Nested directories and files sync."""
        self.message.synced_dir.dir = self.nested_dirs_src

        self._assertExist(self.nested_src_files)
        self._assertNotExist(self.nested_dest_files)

        with field_handler.sync_dirs(
            self.message, self.destination, self.chroot
        ):
            self.assertEqual(self.message.synced_dir.dir, self.inside_path)
            self._assertExist(self.nested_dest_files)

        self.assertEqual(self.message.synced_dir.dir, self.nested_dirs_src)
        self._assertExist(self.nested_src_files)

    def testDeletion(self):
        """Test file deletions are exported correctly."""
        self.message.synced_dir.dir = self.nested_dirs_src

        deleted_src = os.path.join(
            self.nested_dirs_src, "nested1", "nested1.txt"
        )
        deleted_dest = os.path.join(self.destination, "nested1", "nested1.txt")

        self._assertExist(self.nested_src_files)
        self._assertNotExist(self.nested_dest_files)

        with field_handler.sync_dirs(
            self.message, self.destination, self.chroot
        ):
            self._assertExist(self.nested_dest_files)
            osutils.SafeUnlink(deleted_dest)

        self._assertExist(set(self.nested_src_files) - {deleted_src})
        self.assertNotExists(deleted_src)

    def testCreation(self):
        """Test file creations are exported correctly."""
        self.message.synced_dir.dir = self.nested_dirs_src

        new_src = os.path.join(self.nested_dirs_src, "new_dir", "new_file")
        new_dest = os.path.join(self.destination, "new_dir", "new_file")

        self._assertExist(self.nested_src_files)
        self._assertNotExist(self.nested_dest_files)

        with field_handler.sync_dirs(
            self.message, self.destination, self.chroot
        ):
            self._assertExist(self.nested_dest_files)
            osutils.Touch(new_dest, makedirs=True)

        self._assertExist(self.nested_src_files)
        self.assertExists(new_src)

    def testModification(self):
        """Test file modifications are exported correctly."""
        self.message.synced_dir.dir = self.single_file_src

        self.assertExists(self.sf_src_file)
        self.assertNotExists(self.sf_dest_file)

        self.assertEqual("", osutils.ReadFile(self.sf_src_file))
        file_content = "Content!"

        with field_handler.sync_dirs(
            self.message, self.destination, self.chroot
        ):
            self.assertExists(self.sf_dest_file)
            osutils.WriteFile(self.sf_dest_file, file_content)

        self.assertExists(self.sf_src_file)
        self.assertEqual(file_content, osutils.ReadFile(self.sf_src_file))


class ExtractResultsTestBase(cros_test_lib.MockTempDirTestCase):
    """Base class to set up tests for extract_results."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        # Setup the directories.
        self.chroot_dir = os.path.join(self.tempdir, "chroot")
        self.source_dir = "/source"
        self.chroot_source = os.path.join(
            self.chroot_dir, self.source_dir.lstrip(os.sep)
        )
        self.source_dir2 = "/source2"
        self.chroot_source2 = os.path.join(
            self.chroot_dir, self.source_dir2.lstrip(os.sep)
        )
        self.dest_dir = os.path.join(self.tempdir, "destination")
        osutils.SafeMakedirs(self.chroot_source)
        osutils.SafeMakedirs(self.chroot_source2)
        osutils.SafeMakedirs(self.dest_dir)

        # Two files in the same directory inside the chroot.
        self.source_file1 = os.path.join(self.chroot_source, "file1")
        self.source_file1_inside = os.path.join(self.source_dir, "file1")
        self.file1_contents = "file 1"
        osutils.WriteFile(self.source_file1, self.file1_contents)

        self.file2_contents = "some data"
        self.source_file2 = os.path.join(self.chroot_source, "file2")
        self.source_file2_inside = os.path.join(self.source_dir, "file2")
        osutils.WriteFile(self.source_file2, self.file2_contents)

        # Third file in a different location.
        self.file3_contents = "another file"
        self.source_file3 = os.path.join(self.chroot_source2, "file3")
        self.source_file3_inside = os.path.join(self.source_dir2, "file3")
        osutils.WriteFile(self.source_file3, self.file3_contents)

        self.request = build_api_test_pb2.TestRequestMessage()
        self.request.result_path.path.path = self.dest_dir
        self.request.result_path.path.location = common_pb2.Path.OUTSIDE
        self.response = build_api_test_pb2.TestResultMessage()
        self.chroot = chroot_lib.Chroot(
            path=self.chroot_dir, out_path=self.tempdir / "out"
        )
        osutils.SafeMakedirs(self.chroot.tmp)


class ExtractResultsTest(ExtractResultsTestBase):
    """Tests for extract_results."""

    def _path_checks(self, path, destination, contents=None):
        self.assertTrue(path)
        self.assertStartsWith(path, destination)
        self.assertExists(path)
        if contents:
            self.assertFileContents(path, contents)

    def test_empty_result_path(self):
        """Test an empty result path.

        Destination should be unchanged, and response message left as-is /
        unfilled.
        """
        self.request.result_path.path.path = ""
        self.response.artifact.path = self.source_file1_inside
        self.response.artifact.location = common_pb2.Path.INSIDE

        field_handler.extract_results(self.request, self.response, self.chroot)

        self.assertEqual([], list(Path(self.dest_dir).iterdir()))
        self.assertEqual(self.source_file1_inside, self.response.artifact.path)
        self.assertEqual(
            common_pb2.Path.INSIDE, self.response.artifact.location
        )

    def test_single_file(self):
        """Test a single file.

        Verify:
        /path/to/chroot/file -> /path/to/destination/file
        """
        self.response.artifact.path = self.source_file1_inside
        self.response.artifact.location = common_pb2.Path.INSIDE

        field_handler.extract_results(self.request, self.response, self.chroot)

        self._path_checks(
            self.response.artifact.path,
            self.dest_dir,
            contents=self.file1_contents,
        )

    def test_tmp_file(self):
        """Test a file in chroot's /tmp."""
        contents = "tmpfile contents"
        tmpfile = os.path.join(self.chroot.tmp, "file")
        tmpfile_inside = "/tmp/file"
        osutils.WriteFile(tmpfile, contents)

        self.response.artifact.path = tmpfile_inside
        self.response.artifact.location = common_pb2.Path.INSIDE

        field_handler.extract_results(self.request, self.response, self.chroot)

        self._path_checks(
            self.response.artifact.path,
            self.dest_dir,
            contents=contents,
        )

    def test_single_directory(self):
        """Test a single directory.

        Verify:
        /path/to/chroot/directory/* -> /path/to/destination/directory/*
        """
        self.response.artifact.path = self.source_dir
        self.response.artifact.location = common_pb2.Path.INSIDE

        field_handler.extract_results(self.request, self.response, self.chroot)

        self._path_checks(self.response.artifact.path, self.dest_dir)
        self.assertCountEqual(
            os.listdir(self.chroot_source),
            os.listdir(self.response.artifact.path),
        )

    def test_multiple_files(self):
        """Test multiple files.

        Verify:
        /path/to/chroot/some/path/file1 -> /path/to/destination/file1
        /path/to/chroot/different/path/file2 -> /path/to/destination/file2
        etc.
        """
        self.response.artifact.path = self.source_file1_inside
        self.response.artifact.location = common_pb2.Path.INSIDE
        self.response.nested_artifact.path.path = self.source_file2_inside
        self.response.nested_artifact.path.location = common_pb2.Path.INSIDE

        artifact3 = self.response.artifacts.add()
        artifact3.path = self.source_file3_inside
        artifact3.location = common_pb2.Path.INSIDE

        field_handler.extract_results(self.request, self.response, self.chroot)

        self._path_checks(
            self.response.artifact.path,
            self.dest_dir,
            contents=self.file1_contents,
        )
        self._path_checks(
            self.response.nested_artifact.path.path,
            self.dest_dir,
            contents=self.file2_contents,
        )

        self.assertEqual(1, len(self.response.artifacts))
        for artifact in self.response.artifacts:
            self._path_checks(
                artifact.path, self.dest_dir, contents=self.file3_contents
            )

    def test_multiple_directories(self):
        """Test multiple directories.

        Verify:
        /path/to/chroot/some/directory -> /path/to/destination/directory
        /path/to/chroot/another/directory2 -> /path/to/destination/directory2
        etc.
        """
        self.response.artifact.path = self.source_dir
        self.response.artifact.location = common_pb2.Path.INSIDE
        self.response.nested_artifact.path.path = self.source_dir2
        self.response.nested_artifact.path.location = common_pb2.Path.INSIDE

        field_handler.extract_results(self.request, self.response, self.chroot)

        self._path_checks(self.response.artifact.path, self.dest_dir)
        self._path_checks(
            self.response.nested_artifact.path.path, self.dest_dir
        )

        expected = os.listdir(self.chroot_source)
        expected.extend(os.listdir(self.chroot_source2))
        self.assertCountEqual(expected, os.listdir(self.response.artifact.path))


class TransferResultsTest(ExtractResultsTestBase):
    """Tests extract_results when ResultPath.transfer is TRANSFER_TRANSLATE."""

    def setUp(self) -> None:
        self.request.result_path.path.path = ""
        self.request.result_path.transfer = (
            common_pb2.ResultPath.TRANSFER_TRANSLATE
        )

    def extract_results(
        self, check_exists: Optional[bool] = True
    ) -> common_pb2.Path:
        """Helper to extract_results() with data member proto messages."""
        field_handler.extract_results(self.request, self.response, self.chroot)

        # Validate the output path on the response when no error raised.
        self.assertTrue(self.response.artifact.path)
        if check_exists:
            self.assertExists(self.response.artifact.path)
        return self.response.artifact

    def test_non_empty_result_path(self) -> None:
        """Ensure exception raised if ResultPath proto has a destination."""
        self.request.result_path.path.path = "/tmp"
        with self.assertRaises(field_handler.InvalidResultPathError):
            self.extract_results()

    def test_file_inside(self) -> None:
        """Test path translation of a single file inside the chroot."""
        self.response.artifact.path = self.source_file1_inside
        self.response.artifact.location = common_pb2.Path.INSIDE

        path = self.extract_results()

        self.assertEqual(path.path, self.source_file1)
        self.assertEqual(path.location, common_pb2.Path.OUTSIDE)

    def test_file_outside(self) -> None:
        """Test outside paths are unchanged."""
        self.response.artifact.path = self.source_file1
        self.response.artifact.location = common_pb2.Path.OUTSIDE

        path = self.extract_results()

        self.assertEqual(path.path, self.source_file1)
        self.assertEqual(path.location, common_pb2.Path.OUTSIDE)

    def test_dir_in_stateful_output_dir(self) -> None:
        """Test a folder in a stateful out dir is mapped."""
        osutils.SafeMakedirs(os.path.join(self.chroot_dir, "var", "tmp", "foo"))
        self.response.artifact.path = "/var/tmp/foo"
        self.response.artifact.location = common_pb2.Path.INSIDE

        # The bind mounts don't exist in the test harness temp dir, so the file
        # will not actually exist at the remapped path.
        path = self.extract_results(check_exists=False)

        self.assertEqual(
            path.path, os.path.join(self.tempdir, "out", "sdk", "tmp", "foo")
        )
        self.assertEqual(path.location, common_pb2.Path.OUTSIDE)
