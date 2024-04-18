# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test suite for pprint.py"""

import datetime
import io
import os

from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.utils import pformat


class TestPPrintTimedelta(cros_test_lib.TestCase):
    """Tests PPrintTimedelta."""

    def testDays(self):
        delta = datetime.timedelta(days=1, hours=2, minutes=3, seconds=4)
        pretty_delta = pformat.timedelta(delta)
        self.assertEqual(pretty_delta, "1d2h3m4.000s")

    def testSeconds(self):
        delta = datetime.timedelta(seconds=12, microseconds=345678)
        pretty_delta = pformat.timedelta(delta)
        self.assertEqual(pretty_delta, "12.345s")

    def testManySeconds(self):
        delta = datetime.timedelta(seconds=200000)
        pretty_delta = pformat.timedelta(delta)
        self.assertEqual(pretty_delta, "2d7h33m20.000s")

    def testOnlyDaysAndSeconds(self):
        delta = datetime.timedelta(days=1, seconds=23)
        pretty_delta = pformat.timedelta(delta)
        self.assertEqual(pretty_delta, "1d23.000s")


class TestJson(cros_test_lib.TempDirTestCase):
    """Tests pformat.json."""

    TESTS = (
        ([1, 2], "[\n  1,\n  2\n]\n", "[1,2]"),
        (
            {"z": 1, "a": "カ"},
            '{\n  "a": "カ",\n  "z": 1\n}\n',
            '{"a":"カ","z":1}',
        ),
    )

    def testStrHuman(self):
        """Test returning a string for humans."""
        for obj, exp, _ in self.TESTS:
            result = pformat.json(obj)
            self.assertEqual(exp, result)

    def testStrCompact(self):
        """Test returning a string for machines."""
        for obj, _, exp in self.TESTS:
            result = pformat.json(obj, compact=True)
            self.assertEqual(exp, result)

    def testFileHuman(self):
        """Test writing a file for humans."""
        for obj, exp, _ in self.TESTS:
            fp = io.StringIO()
            self.assertIsNone(pformat.json(obj, fp=fp))
            self.assertEqual(exp, fp.getvalue())

    def testFileCompact(self):
        """Test writing a file for machines."""
        for obj, _, exp in self.TESTS:
            fp = io.StringIO()
            self.assertIsNone(pformat.json(obj, fp=fp, compact=True))
            self.assertEqual(exp, fp.getvalue())

    def testStrPathHuman(self):
        """Test writing a string path for humans."""
        for obj, exp, _ in self.TESTS:
            path = os.path.join(self.tempdir, "x")
            self.assertIsNone(pformat.json(obj, fp=path))
            self.assertEqual(exp, osutils.ReadFile(path))

    def testStringPathCompact(self):
        """Test writing a string path for machines."""
        for obj, _, exp in self.TESTS:
            path = os.path.join(self.tempdir, "x")
            self.assertIsNone(pformat.json(obj, fp=path, compact=True))
            self.assertEqual(exp, osutils.ReadFile(path))


class TestSize(cros_test_lib.TestCase):
    """Tests pformat.size."""

    def testBytes(self):
        self.assertEqual(pformat.size(100), "100B")

    def testKilobytes(self):
        self.assertEqual(pformat.size(340216), "332.2KiB")

    def testMegabytes(self):
        self.assertEqual(pformat.size(1930135), "1.8MiB")

    def testGigabytes(self):
        self.assertEqual(pformat.size(30040023123), "28.0GiB")
