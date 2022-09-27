# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for build_minios.py"""

import os
import tempfile
from unittest import mock

from chromite.lib import constants
from chromite.lib import cros_test_lib
from chromite.lib import minios
from chromite.scripts import build_minios


class BuildMiniosTest(cros_test_lib.RunCommandTempDirTestCase):
  """Unit tests for build_minios."""

  def setUp(self):
    self.create_minios_mock_return = '/some/kernel/path'
    self.create_minios_mock = self.PatchObject(
        minios, 'CreateMiniOsKernelImage',
        return_value=self.create_minios_mock_return)

    self.insert_minios_mock = self.PatchObject(
        minios, 'InsertMiniOsKernelImage')

    # Patch to assert against the tempdir that's created under the anchored
    # tempdir created by cros_test_lib.
    self._tempdir = os.path.join(self.tempdir, 'test-dir')
    self.PatchObject(tempfile, 'mkdtemp', return_value=self._tempdir)

  def testDefaultArguments(self):
    """Test that default arguments of build_minios are formatted correct."""
    test_board = 'test-board'
    test_version = '0.0.0.0'
    test_image = '/some/image/path'
    build_minios.main([
        # --board is a required argument.
        '--board', test_board,
        # --version is a required argument.
        '--version', test_version,
        # --image is a required argument.
        '--image', test_image,
    ])

    self.assertEqual(self.create_minios_mock.mock_calls, [mock.call(
        test_board,
        test_version,
        self._tempdir,
        constants.VBOOT_DEVKEYS_DIR,
        constants.RECOVERY_PUBLIC_KEY,
        constants.MINIOS_DATA_PRIVATE_KEY,
        constants.MINIOS_KEYBLOCK,
        None,
    )])

    self.assertEqual(self.insert_minios_mock.mock_calls, [mock.call(
        test_image, self.create_minios_mock_return,
    )])

  def testOverridenArguments(self):
    """Test that overridden arguments of build_minios are formatted correct."""
    test_board = 'test-board'
    test_version = '1.0.0.0'
    test_image = '/some/image/path'
    test_keys_dir = '/some/path/test-keys-dir'
    test_public_key = 'test-public-key'
    test_private_key = 'test-private-key'
    test_keyblock = 'test-keyblock'
    test_serial = 'test-serial'
    build_minios.main([
        # --board is a required argument.
        '--board', test_board,
        # --version is a required argument.
        '--version', test_version,
        # --image is a required argument.
        '--image', test_image,
        '--keys-dir', test_keys_dir,
        '--public-key', test_public_key,
        '--private-key', test_private_key,
        '--keyblock', test_keyblock,
        '--serial', test_serial,
    ])

    self.assertEqual(self.create_minios_mock.mock_calls, [mock.call(
        test_board,
        test_version,
        self._tempdir,
        test_keys_dir,
        test_public_key,
        test_private_key,
        test_keyblock,
        test_serial,
    )])

    self.assertEqual(self.insert_minios_mock.mock_calls, [mock.call(
        test_image, self.create_minios_mock_return,
    )])
