# Copyright 2014 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for the functions in test_image."""

import os
import tempfile
import unittest

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import image_lib
from chromite.lib import image_test_lib
from chromite.lib import osutils
from chromite.scripts import test_image


class TestImageTest(cros_test_lib.MockTempDirTestCase):
    """Common class for tests ImageTest.

    This sets up proper directory with test image. The image file is zero-byte.
    """

    def setUp(self):
        # Create empty image file.
        self.image_file = os.path.join(
            self.tempdir, constants.BASE_IMAGE_NAME + ".bin"
        )
        osutils.AllocateFile(self.image_file, 1024 * 1024)
        # In case sfdisk is in /sbin, search that too.
        cros_build_lib.run(
            ["sfdisk", self.image_file],
            extra_env={"PATH": "/sbin:/usr/sbin:%s" % os.environ["PATH"]},
            input="label: dos",
        )
        fake_partitions = (
            image_lib.PartitionInfo(1, 0, 0, "fs", "STATE"),
            image_lib.PartitionInfo(2, 0, 0, "fs", "KERN-A"),
            image_lib.PartitionInfo(3, 0, 0, "fs", "ROOT-A"),
        )
        self.PatchObject(
            image_lib,
            "GetImageDiskPartitionInfo",
            autospec=True,
            return_value=fake_partitions,
        )
        self.PatchObject(image_lib.LoopbackPartitions, "_Mount", autospec=True)
        self.PatchObject(
            image_lib.LoopbackPartitions, "_Unmount", autospec=True
        )
        self.PatchObject(image_lib.LoopbackPartitions, "Attach", autospec=True)


class FindImageTest(TestImageTest):
    """Test FindImage() function."""

    def _testFindOkay(self, image_path):
        res = test_image.FindImage(image_path)
        self.assertEqual(
            res, os.path.join(self.tempdir, constants.BASE_IMAGE_NAME + ".bin")
        )

    def testFindWithDirectory(self):
        self._testFindOkay(self.tempdir)

    def testFindWithFile(self):
        self._testFindOkay(self.image_file)

    def testFindWithInvalid(self):
        self.assertRaises(
            ValueError, test_image.FindImage, os.path.join(self.tempdir, "404")
        )

    def testFindWithInvalidDirectory(self):
        os.unlink(self.image_file)
        self.assertRaises(
            ValueError, test_image.FindImage, os.path.join(self.tempdir)
        )


class MainTest(TestImageTest):
    """Test the main invocation of the script."""

    def testChdir(self):
        """Verify the CWD is in a temp directory."""

        class CwdTest(image_test_lib.ImageTestCase):
            """A stub test class to verify current working directory."""

            _expected_dir = None

            def SetCwd(self, cwd):
                self._expected_dir = cwd

            def testExpectedCwd(self):
                self.assertEqual(self._expected_dir, os.getcwd())

        self.assertNotEqual("/tmp", os.getcwd())
        os.chdir("/tmp")

        test = CwdTest("testExpectedCwd")
        suite = image_test_lib.ImageTestSuite()
        suite.addTest(test)
        self.PatchObject(
            unittest.TestLoader,
            "loadTestsFromName",
            autospec=True,
            return_value=suite,
        )

        # Set up the expected directory.
        expected_dir = os.path.join(self.tempdir, "my-subdir")
        os.mkdir(expected_dir)
        test.SetCwd(expected_dir)
        self.PatchObject(
            tempfile, "mkdtemp", autospec=True, return_value=expected_dir
        )

        argv = [str(self.tempdir)]
        self.assertEqual(0, test_image.main(argv))
        self.assertEqual("/tmp", os.getcwd())

    def testBoardAndDirectory(self):
        """Verify "--board", "--test_results_root" are passed to the tests."""

        class AttributeTest(image_test_lib.ImageTestCase):
            """Stub test class to hold board and directory."""

            def testOkay(self):
                pass

        test = AttributeTest("testOkay")
        suite = image_test_lib.ImageTestSuite()
        suite.addTest(test)
        self.PatchObject(
            unittest.TestLoader,
            "loadTestsFromName",
            autospec=True,
            return_value=suite,
        )
        argv = [
            "--board",
            "my-board",
            "--test_results_root",
            "your-root",
            str(self.tempdir),
        ]
        test_image.main(argv)
        # pylint: disable=protected-access
        self.assertEqual("my-board", test._board)
        # pylint: disable=protected-access
        self.assertEqual("your-root", os.path.basename(test._result_dir))
