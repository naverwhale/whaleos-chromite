# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for merge_logs."""

import datetime

import dateutil.tz  # pylint: disable=import-error

from chromite.lib import cros_test_lib
from chromite.scripts import merge_logs


TZOFFSET = dateutil.tz.tzoffset(None, -25200)


class ParseDateTestBase(cros_test_lib.MockTestCase):
  """Test that ParseDate behaves correctly."""

  def setUp(self):
    now = datetime.datetime(2017, 8, 1, 13, 14, 8, 357309)
    self.now_mock = self.PatchObject(merge_logs, 'Now', return_value=now)


class ParseDateTest(ParseDateTestBase):
  """Test that ParseDate behaves correctly."""

  def testBasicFunctionality(self):
    # ARC
    dt = merge_logs.ParseDate('2017-07-31 07:05:10.257860139-07:00')
    self.assertEqual(dt, datetime.datetime(2017, 7, 31, 7, 5, 10, 257860,
                                           TZOFFSET))

    # CrOS
    dt = merge_logs.ParseDate('2017/07/31 09:18:08.871')
    self.assertEqual(dt, datetime.datetime(2017, 7, 31, 9, 18, 8, 871000,
                                           TZOFFSET))

    # Status Log
    dt = merge_logs.ParseDate('Jul 31 09:17:02')
    self.assertEqual(dt, datetime.datetime(datetime.datetime.now().year, 7, 31,
                                           9, 17, 2, 0, TZOFFSET))

    # Sysinfo
    dt = merge_logs.ParseDate('2017-07-31T09:17:25.907285-07:00')
    self.assertEqual(
        dt, datetime.datetime(2017, 7, 31, 9, 17, 25, 907285, TZOFFSET))

  def testUTC(self):
    dt = merge_logs.ParseDate('2017-07-31T13:55:29.455280+00:00')
    self.assertEqual(dt, datetime.datetime(2017, 7, 31, 13, 55, 29, 455280,
                                           dateutil.tz.tzutc()))

    dt = merge_logs.ParseDate('2017-07-31T09:17:25.907285Z')
    self.assertEqual(
        dt,
        datetime.datetime(2017, 7, 31, 9, 17, 25, 907285, dateutil.tz.tzutc()))


class ParseAutoservDateTest(ParseDateTestBase):
  """Test that ParseAutoservDate behaves correctly."""

  def testBasicFunctionality(self):
    dt = merge_logs.ParseAutoservDate('07/31 09:17:27.919')
    self.assertEqual(dt, datetime.datetime(2017, 7, 31, 9, 17, 27, 919000,
                                           TZOFFSET))


class ParseChromeDateTest(ParseDateTestBase):
  """Test that ParseChromeDate behaves correctly."""

  def testBasicFunctionality(self):
    dt = merge_logs.ParseChromeDate('0731/072833.409065')
    self.assertEqual(dt, datetime.datetime(2017, 7, 31, 7, 28, 33, 409065,
                                           TZOFFSET))


class ParsePowerdDateTest(ParseDateTestBase):
  """Test that ParsePowerdDate behaves correctly."""

  def testBasicFunctionality(self):
    dt = merge_logs.ParsePowerdDate('0731/070232')
    self.assertEqual(dt, datetime.datetime(2017, 7, 31, 7, 2, 32, 0,
                                           TZOFFSET))


class ParseFileContentsTest(ParseDateTestBase):
  """Test that parsers can parse old and new log formats."""

  def testParseSysinfoPatterns(self):
    filename = 'messages'
    content = """2017-07-31T07:05:10.257860-07:00 INFO ag[12]: Memory leak.
2017-07-31T07:05:10.257860Z INFO ag[12]: Memory leak."""

    logs = merge_logs.ParseFileContents(filename, content)
    lines = content.splitlines()
    expected_logs = [
        merge_logs.Log(
            filename=filename,
            date=datetime.datetime(2017, 7, 31, 7, 5, 10, 257860, TZOFFSET),
            log=lines[0]),
        merge_logs.Log(
            filename=filename,
            date=datetime.datetime(2017, 7, 31, 7, 5, 10, 257860,
                                   dateutil.tz.tzutc()),
            log=lines[1])
    ]

    self.assertCountEqual(logs, expected_logs)

  def testParseChromePatterns(self):
    filename = 'ui.LATEST'
    content = """[1694:1694:0731/072833.409065:VERBOSE1:main.cc(480)] Error
2017-01-27T05:34:14.464052Z ERROR chrome[1694:1694]: [main.cc(11)] Error"""

    logs = merge_logs.ParseFileContents(filename, content)
    lines = content.splitlines()
    expected_logs = [
        merge_logs.Log(
            filename=filename,
            date=datetime.datetime(2017, 7, 31, 7, 28, 33, 409065, TZOFFSET),
            log=lines[0]),
        merge_logs.Log(
            filename=filename,
            date=datetime.datetime(2017, 1, 27, 5, 34, 14, 464052,
                                   dateutil.tz.tzutc()),
            log=lines[1])
    ]

    self.assertCountEqual(logs, expected_logs)

  def testParsePowerdPatterns(self):
    filename = 'powerd.LATEST'
    content = """[0731/070232:INFO:main.cc(289)] System uptime: 5s
2017-01-27T05:34:14.464052Z INFO powerd: [main.cc(289)] System uptime: 5s"""

    logs = merge_logs.ParseFileContents(filename, content)

    lines = content.splitlines()
    expected_logs = [
        merge_logs.Log(
            filename=filename,
            date=datetime.datetime(2017, 7, 31, 7, 2, 32, 0, TZOFFSET),
            log=lines[0]),
        merge_logs.Log(
            filename=filename,
            date=datetime.datetime(2017, 1, 27, 5, 34, 14, 464052,
                                   dateutil.tz.tzutc()),
            log=lines[1])
    ]

    self.assertCountEqual(logs, expected_logs)
