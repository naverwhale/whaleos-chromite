# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test fetch_cipd."""

from chromite.lib import cros_test_lib
from chromite.scripts import fetch_cipd


class FetchCipdTest(cros_test_lib.TestCase):
  """Tests for fetch_cipd script."""

  def testParseCipdUri(self):
    uri = 'cipd://chromiumos/infra/tclint/linux-amd64:abcdefghijklm'
    path, version = fetch_cipd.ParseCipdUri(uri)
    self.assertEqual('chromiumos/infra/tclint/linux-amd64', path)
    self.assertEqual('abcdefghijklm', version)

  def testParseCipdUriWrongScheme(self):
    uri = 'gs://chromiumos/infra/tclint/linux-amd64:abcdefghijklm'
    with self.assertRaises(ValueError):
      fetch_cipd.ParseCipdUri(uri)

  def testParseCipdUriNoVersion(self):
    uri = 'cipd://chromiumos/infra/tclint/linux-amd64'
    with self.assertRaises(ValueError):
      fetch_cipd.ParseCipdUri(uri)
