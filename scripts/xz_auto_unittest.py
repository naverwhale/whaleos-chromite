# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for xz_auto.py."""

import os
from pathlib import Path
import unittest
from unittest import mock

from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.scripts import xz_auto


DIR = Path(__file__).resolve().parent


def FindXzAutoLocation():
    """Figures out where the xz_auto binary is."""
    return DIR / "xz_auto"


class XzAutoTests(cros_test_lib.MockTempDirTestCase):
    """Various tests for xz_auto."""

    TEST_FILE_CONTENTS = (b"", b"some random file contents")

    def DisablePixzForCurrentTest(self):
        """Disables the use of pixz for the current test."""
        # This will be cleaned up by cros_test_lib, so no need to addCleanup.
        os.environ[xz_auto.PIXZ_DISABLE_VAR] = "1"

    def testPixzArgParsingSeemsToWork(self):
        """Tests our detection of file names in pixz commandlines."""
        self.assertEqual(
            xz_auto.ParsePixzArgs(["to_compress.txt"]),
            ([], "to_compress.txt", None),
        )
        self.assertEqual(
            xz_auto.ParsePixzArgs(["to_compress.txt", "compressed.txt"]),
            ([], "to_compress.txt", "compressed.txt"),
        )
        self.assertEqual(
            xz_auto.ParsePixzArgs(
                ["to_compress.txt", "-c", "compressed.txt", "-9"]
            ),
            (["-c", "-9"], "to_compress.txt", "compressed.txt"),
        )
        self.assertEqual(
            xz_auto.ParsePixzArgs(
                ["-t", "to_compress.txt", "-c", "compressed.txt", "-p", "2"]
            ),
            (["-t", "-c", "-p", "2"], "to_compress.txt", "compressed.txt"),
        )
        self.assertEqual(
            xz_auto.ParsePixzArgs(
                ["-tcp2", "to_compress.txt", "compressed.txt"]
            ),
            (["-t", "-c", "-p", "2"], "to_compress.txt", "compressed.txt"),
        )

    @unittest.skipIf(not xz_auto.HasPixz(), "need pixz for this test")
    @mock.patch.object(xz_auto, "Execvp")
    def testPixzCommandCreationSelectsPixzIfAvailable(self, execvp_mock):
        """Tests that we actually execute pixz when we intend to."""

        class ExecvpStopError(Exception):
            """Convenient way to halt execution."""

        def execvp_side_effect(argv):
            """Does testing of our execvp calls."""
            self.assertEqual(argv[0], "pixz")
            raise ExecvpStopError()

        execvp_mock.side_effect = execvp_side_effect
        with self.assertRaises(ExecvpStopError):
            xz_auto.ExecCompressCommand(stdout=False, argv=[])

        with self.assertRaises(ExecvpStopError):
            xz_auto.ExecDecompressCommand(stdout=False, argv=[])

    def _TestFileCompressionImpl(self, test_empty_file=True):
        """Tests that compressing a file with xz_auto WAI."""
        xz_auto_script = str(FindXzAutoLocation())

        test_file_contents = self.TEST_FILE_CONTENTS
        if not test_empty_file:
            test_file_contents = (x for x in test_file_contents if x)

        for file_contents in test_file_contents:
            file_location = os.path.join(self.tempdir, "file.txt")
            osutils.WriteFile(file_location, file_contents, mode="wb")

            cros_build_lib.run(
                [
                    xz_auto_script,
                    file_location,
                ],
            )

            xz_location = file_location + ".xz"
            self.assertExists(xz_location)
            self.assertNotExists(file_location)
            cros_build_lib.run(
                [
                    xz_auto_script,
                    "--decompress",
                    xz_location,
                ]
            )
            self.assertNotExists(xz_location)
            self.assertExists(file_location)
            self.assertEqual(
                osutils.ReadFile(file_location, mode="rb"),
                file_contents,
            )

    def _TestStdoutCompressionImpl(self):
        """Tests that compressing stdstreams with xz_auto WAI."""
        xz_auto_script = str(FindXzAutoLocation())
        for file_contents in self.TEST_FILE_CONTENTS:
            run_result = cros_build_lib.run(
                [
                    xz_auto_script,
                    "-c",
                ],
                capture_output=True,
                input=file_contents,
            )

            compressed_file = run_result.stdout
            self.assertNotEqual(compressed_file, file_contents)

            run_result = cros_build_lib.run(
                [
                    xz_auto_script,
                    "--decompress",
                    "-c",
                ],
                input=compressed_file,
                capture_output=True,
            )
            uncompressed_file = run_result.stdout
            self.assertEqual(file_contents, uncompressed_file)

    def _TestStdoutCompressionFromFileImpl(self):
        """Tests that compression of a file & outputting to stdout works.

        Pixz has some semi-weird behavior here (b/202735786).
        """
        xz_auto_script = str(FindXzAutoLocation())
        for file_contents in self.TEST_FILE_CONTENTS:
            file_location = os.path.join(self.tempdir, "file.txt")
            osutils.WriteFile(file_location, file_contents, mode="wb")

            run_result = cros_build_lib.run(
                [
                    xz_auto_script,
                    "-c",
                    file_location,
                ],
                capture_output=True,
            )

            compressed_file = run_result.stdout
            self.assertExists(file_location)
            self.assertNotEqual(compressed_file, file_contents)

            run_result = cros_build_lib.run(
                [
                    xz_auto_script,
                    "--decompress",
                    "-c",
                ],
                capture_output=True,
                input=compressed_file,
            )
            uncompressed_file = run_result.stdout
            self.assertEqual(file_contents, uncompressed_file)

    @unittest.skipIf(not xz_auto.HasPixz(), "need pixz for this test")
    def testFileCompressionWithPixzWorks(self):
        """Tests that compressing a file with pixz WAI."""
        self._TestFileCompressionImpl()

        # We fall back to `xz` with small files. Make sure we actually cover the
        # pixz case, too. We disable testing of empty inputs, since pixz breaks
        # with those.
        #
        # cros_test_lib will clean this var up at the end of the test.
        os.environ[xz_auto.XZ_DISABLE_VAR] = "1"
        self._TestFileCompressionImpl(test_empty_file=False)

    @unittest.skipIf(not xz_auto.HasPixz(), "need pixz for this test")
    def testStdoutCompressionWithPixzWorks(self):
        """Tests that compressing `stdout` with pixz WAI."""
        self._TestStdoutCompressionImpl()

    @unittest.skipIf(not xz_auto.HasPixz(), "need pixz for this test")
    def testStdoutCompressionFromFileWithPixzWorks(self):
        """Tests that compressing from a file to stdout with pixz WAI."""
        self._TestStdoutCompressionFromFileImpl()

    def testFileCompressionWithXzWorks(self):
        """Tests that compressing a file with pixz WAI."""
        self.DisablePixzForCurrentTest()
        self._TestFileCompressionImpl()

    def testStdoutCompressionWithXzWorks(self):
        """Tests that compressing `stdout` with pixz WAI."""
        self.DisablePixzForCurrentTest()
        self._TestStdoutCompressionImpl()

    def testStdoutCompressionFromFileWithXzWorks(self):
        """Tests that compressing from a file to stdout WAI."""
        self.DisablePixzForCurrentTest()
        self._TestStdoutCompressionFromFileImpl()
