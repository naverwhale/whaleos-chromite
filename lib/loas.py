# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Manage Google Low Overhead Authentication Service (LOAS) tasks.

This is used by scripts that run outside of the chroot and require access to
Google production resources.

If you don't know what any of this means, then you don't need this module :).
"""

import datetime
import logging
import socket
import subprocess

from chromite.lib import alerts
from chromite.lib import cros_build_lib


class LoasError(Exception):
  """Raised when a LOAS error occurs"""


class Loas(object):
  """Class for holding all the various LOAS cruft."""

  def __init__(self, user, email_notify, email_server=None):
    """Initialize.

    Args:
      user: The LOAS account to check.
      email_notify: The people to notify when the cert is going to expire.
      email_server: The e-mail server to use when notifying.
    """
    self.user = user
    self.email_notify = email_notify
    self.email_server = email_server
    self.enroll_msg = 'become -t -c "gcert --loas2" %s@%s' % (
        self.user, socket.getfqdn())
    self.last_notification = (
        datetime.date.today() - datetime.timedelta(weeks=10))

  def Check(self):
    logging.debug('Checking LOAS credentials for %s', self.user)
    cmd = ['runloas', '/usr/bin/loas_check']

    # Error message to print when loas credential check fails. This usually
    # is the result of production credentials expiring for accessing
    # Keystore for the unwrapping private key.
    loas_error = 'loas_check for %s failed! Did you run: %s' % (
        self.user, self.enroll_msg)
    try:
      cros_build_lib.sudo_run(cmd, user=self.user)
    except cros_build_lib.RunCommandError as e:
      raise LoasError('%s\n%s' % (e.msg, loas_error))

  def Status(self):
    # Only bother checking once a day.  Our certs are valid in the
    # range of weeks, so there's no need to constantly do this.
    if (datetime.date.today() <
        self.last_notification + datetime.timedelta(days=1)):
      return

    # Let the tool tell us whether things will fail soon.
    cmd = ['gcertstatus', '--check_loas2', '--nocheck_ssh',
           f'--check_remaining={7 * 24}h']
    result = cros_build_lib.sudo_run(cmd,
                                     user=self.user,
                                     check=False,
                                     stdout=True,
                                     stderr=subprocess.STDOUT,
                                     encoding='utf-8')

    # Send out one notification a day if there's a week or less left
    # before our creds expire.
    if result.returncode:
      alerts.SendEmail(
          'Loas certs expiring soon!',
          self.email_notify,
          server=self.email_server,
          message='Please run:\n %s\n\n%s\n%s' % (
              self.enroll_msg, result.output, result.error))
      self.last_notification = datetime.date.today()
    else:
      # We won't expire for a while, so stop the periodic polling.
      self.last_notification = (
          datetime.date.today() + datetime.timedelta(days=7))
