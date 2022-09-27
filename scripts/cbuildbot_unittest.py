# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for the cbuildbot program"""

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.scripts import cbuildbot


# pylint: disable=protected-access


class IsDistributedBuilderTest(cros_test_lib.TestCase):
  """Test for cbuildbot._IsDistributedBuilder."""

  # pylint: disable=protected-access
  def testIsDistributedBuilder(self):
    """Tests for _IsDistributedBuilder() under various configurations."""
    parser = cbuildbot._CreateParser()
    argv = ['--buildroot', '/foo', 'amd64-generic-paladin']
    options = cbuildbot.ParseCommandLine(parser, argv)
    options.buildbot = False

    build_config = dict(manifest_version=False)
    chrome_rev = None

    def _TestConfig(expected):
      self.assertEqual(expected,
                       cbuildbot._IsDistributedBuilder(
                           options=options,
                           chrome_rev=chrome_rev,
                           build_config=build_config))

    # Default options.
    _TestConfig(False)

    build_config['manifest_version'] = True
    # Not running in buildbot mode even though manifest_version=True.
    _TestConfig(False)
    options.buildbot = True
    _TestConfig(True)

    for chrome_rev in (constants.CHROME_REV_TOT,
                       constants.CHROME_REV_LOCAL,
                       constants.CHROME_REV_SPEC):
      _TestConfig(False)


class PostsubmitBuilderTest(cros_test_lib.TestCase):
  """Test for special parameters for ChromeOS Findit Integration."""

  def testBuildPackages(self):
    parser = cbuildbot.CreateParser()
    argv = ['--buildroot', '/foo', '--buildbot',
            '--cbb_snapshot_revision', 'hash1234',
            '--cbb_build_packages', 'pkgA pkgB', 'caroline-postsubmit']
    options = cbuildbot.ParseCommandLine(parser, argv)
    expected = ['pkgA', 'pkgB']
    self.assertEqual(expected, options.cbb_build_packages)
    self.assertEqual('hash1234', options.cbb_snapshot_revision)


class ParseHWTestDUTDimsTest(cros_test_lib.TestCase):
  """Test for ParseHWTestDUTDims function."""

  def testParseInvalidDims(self):
    invalid_dims = ['label-board:foo', 'label-model:bar', 'label-pol:baz',
                    'extra:haha']
    with self.assertRaises(cros_build_lib.DieSystemExit):
      cbuildbot.ParseHWTestDUTDims(invalid_dims)

  def testParseValidDims(self):
    dimsObject = cbuildbot.ParseHWTestDUTDims([
      'label-board:foo', 'label-model:bar', 'label-pool:baz', 'a:b', 'c:d'])
    self.assertEqual(dimsObject.board, 'foo')
    self.assertEqual(dimsObject.model, 'bar')
    self.assertEqual(dimsObject.pool, 'baz')
    self.assertEqual(dimsObject.extra_dims, ['a:b', 'c:d'])

  def testParseNoDims(self):
    self.assertIsNone(cbuildbot.ParseHWTestDUTDims([]))
    self.assertIsNone(cbuildbot.ParseHWTestDUTDims(None))
