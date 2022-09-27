# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for file_util."""

import os
from pathlib import Path

from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.utils import file_util


class OpenTests(cros_test_lib.TempDirTestCase):
  """Tests for cros_build_lib.Open."""

  def testFile(self):
    """Read/write a file by path."""
    path = os.path.join(self.tempdir, 'test.txt')
    with file_util.Open(path, mode='w') as fp:
      fp.write('foo')
    with file_util.Open(path, mode='r') as fp:
      self.assertEqual('foo', fp.read())

  def testHandle(self):
    """Read/write a file by an open handle."""
    path = os.path.join(self.tempdir, 'test.txt')
    with open(path, mode='w') as fp:
      with file_util.Open(fp) as fp2:
        fp2.write('foo')
    with open(path, mode='r') as fp:
      with file_util.Open(fp) as fp2:
        self.assertEqual('foo', fp2.read())

  def testPath(self):
    """Read/write a file by Path."""
    path = Path(self.tempdir) / 'test.txt'
    with file_util.Open(path, mode='w') as fp:
      fp.write('foo')
    with file_util.Open(path, mode='r') as fp:
      self.assertEqual('foo', fp.read())
    self.assertEqual('foo', path.read_text())

  def testEncoding(self):
    """Verify we pass kwargs down."""
    path = os.path.join(self.tempdir, 'test.txt')
    with file_util.Open(path, mode='w', encoding='utf-8') as fp:
      fp.write(u'ßomß')
    self.assertEqual(u'ßomß', osutils.ReadFile(path))
