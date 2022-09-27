# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for cros_logging."""

import logging
import os
import sys

from chromite.cbuildbot import cbuildbot_alerts
from chromite.lib import cros_logging
from chromite.lib import cros_test_lib


class CrosCloudloggingTest(cros_test_lib.MockOutputTestCase):
  """Test google-cloud-logging interacts with logging as expected."""

  # pylint: disable=protected-access

  def setUp(self):
    self.logger = logging.getLogger()
    sh = logging.StreamHandler(sys.stdout)
    self.logger.addHandler(sh)
    # pylint: disable=protected-access
    cbuildbot_alerts._buildbot_markers_enabled = False
    try:
      import google.cloud.logging  # pylint: disable=import-error,no-name-in-module
    except ImportError:
      self.cloud_logging_import_error = True
      return
    self.cloud_logging_import_error = False
    self.client_mock = self.PatchObject(google.cloud.logging, 'Client')

  def testSetupCloudLogging(self):
    if self.cloud_logging_import_error:
      return
    # Invoke the code that calls logging when env vars are set.
    cros_logging._SetupCloudLogging()

    # Verify that google.cloud.logging.Client() was executed.
    self.client_mock.assert_called_once()

  def testCloudLoggingEnvVariablesAreDefined_notSet(self):
    if self.cloud_logging_import_error:
      return
    with self.OutputCapturer() as output:
      cloud_env_defined = cros_logging._CloudLoggingEnvVariablesAreDefined()
    # If both are not set, there should be no output.
    self.assertEqual(output.GetStdout(), '')
    self.assertEqual(output.GetStderr(), '')
    self.assertFalse(cloud_env_defined)

  def testCloudLoggingEnvVariablesAreDefined_envSet(self):
    if self.cloud_logging_import_error:
      return
    # Set logger to INFO level to check for CHROMITE_CLOUD_LOGGING info message.
    self.logger.setLevel(logging.INFO)
    # Set the env vars
    os.environ['CHROMITE_CLOUD_LOGGING'] = '1'
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/some/path/to/creds.json'
    with self.OutputCapturer() as output:
      cloud_env_defined = cros_logging._CloudLoggingEnvVariablesAreDefined()
    # Verify that both variables are logged.
    self.assertTrue(cloud_env_defined)
    self.assertIn('CHROMITE_CLOUD_LOGGING', output.GetStdout())

  def testCloudLoggingEnvVariablesAreDefined_noAllEnvSet(self):
    if self.cloud_logging_import_error:
      return
    # Set only one env var.
    os.environ['CHROMITE_CLOUD_LOGGING'] = '1'
    with self.OutputCapturer() as output:
      cloud_env_defined = cros_logging._CloudLoggingEnvVariablesAreDefined()
    # If both are not set, there should be no output.
    self.assertIn('GOOGLE_APPLICATION_CREDENTIALS is not', output.GetStdout())
    self.assertEqual(output.GetStderr(), '')
    self.assertFalse(cloud_env_defined)
