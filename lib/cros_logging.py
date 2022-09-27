# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Module for initialization of cloud logging support."""

import logging
import os


def _SetupCloudLogging():
  """If appropriate environment variables are set, enable cloud logging.

  Cloud logging is only enabled when the environment has
   CHROMITE_CLOUD_LOGGING=1 and GOOGLE_APPLICATION_CREDENTIALS=<local.json>.
  If these are set, then cloud logging is enable, see
  https://cloud.google.com/docs/authentication/getting-started#cloud-console
  """
  try:
    import google.cloud.logging as cloud_logging  # pylint: disable=import-error,no-name-in-module
  except ImportError as e:
    # TODO(mmortensen): Change to python3's ModuleNotFoundError when this
    # code is only used by python3. Beware though with branches and bisection
    # this could need to be ImportError for a long time. ImportError is the
    # parent class of ModuleNotFoundError and works on both python2 and python3.
    logging.error('Could not import google.cloud.logging %s', e)
    return

  client = cloud_logging.Client()
  # Retrieves a Cloud Logging handler based on the environment
  # you're running in and integrates the handler with the
  # Python logging module. By default this captures all logs
  # at INFO level and higher
  client.get_default_handler()
  client.setup_logging()


def _CloudLoggingEnvVariablesAreDefined():
  """Check for cloud-logging ENV variables."""
  cloud_logging_env_value = os.environ.get('CHROMITE_CLOUD_LOGGING')
  google_app_creds_env_value = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
  # If both variables are set, log their values and return True.
  if cloud_logging_env_value == '1' and google_app_creds_env_value:
    logging.info('CHROMITE_CLOUD_LOGGING is %s', cloud_logging_env_value)
    return True
  if cloud_logging_env_value == '1' and not google_app_creds_env_value:
    logging.warning(
        'CHROMITE_CLOUD_LOGGING is set, GOOGLE_APPLICATION_CREDENTIALS is not.')
  return False


if _CloudLoggingEnvVariablesAreDefined():
  _SetupCloudLogging()
