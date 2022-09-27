# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Update the CHROMEOS_LKGM file in a chromium repository.

This script will first query Gerrit for an already-open CL updating the
CHROMEOS_LKGM file to the given version. If one exists, it will submit that
CL to the CQ. Else it will upload a new CL and quit _without_ submitting
it to the CQ.
"""

import distutils.version  # pylint: disable=import-error,no-name-in-module
import logging
import os
import urllib.parse

from chromite.cbuildbot import manifest_version
from chromite.lib import chrome_committer
from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import gerrit
from chromite.lib import osutils


class LKGMNotValid(chrome_committer.CommitError):
  """Raised if the LKGM version is unset or not newer than the current value."""


class LKGMFileNotFound(chrome_committer.CommitError):
  """Raised if the LKGM file is not found."""


class ChromeLKGMCommitter(object):
  """Committer object responsible for obtaining a new LKGM and committing it."""

  # The list of trybots we require LKGM updates to run and pass on before
  # landing. Since they're internal trybots, the CQ won't automatically trigger
  # them, so we have to explicitly tell it to.
  _PRESUBMIT_BOTS = [
      'chromeos-betty-pi-arc-chrome',
      'chromeos-eve-chrome',
      'chromeos-kevin-chrome',
      'lacros-amd64-generic-chrome',
  ]
  # Files needed in a local checkout to successfully update the LKGM. The OWNERS
  # file allows the --tbr-owners mechanism to select an appropriate OWNER to
  # TBR. TRANSLATION_OWNERS is necesssary to parse CHROMEOS_OWNERS file since
  # it has the reference.
  _NEEDED_FILES = [
      constants.PATH_TO_CHROME_CHROMEOS_OWNERS,
      constants.PATH_TO_CHROME_LKGM,
      'tools/translation/TRANSLATION_OWNERS',
  ]
  # First line of the commit message for all LKGM CLs.
  _COMMIT_MSG_HEADER = 'LKGM %(lkgm)s for chromeos.'

  def __init__(self, user_email, workdir, lkgm, dryrun=False,
               buildbucket_id=None):
    self._dryrun = dryrun
    self._buildbucket_id = buildbucket_id
    self._committer = chrome_committer.ChromeCommitter(user_email, workdir)
    self._gerrit_helper = gerrit.GetCrosExternal()

    # Strip any chrome branch from the lkgm version.
    self._lkgm = manifest_version.VersionInfo(lkgm).VersionString()
    self._commit_msg_header = self._COMMIT_MSG_HEADER % {'lkgm': self._lkgm}
    self._old_lkgm = None

    if not self._lkgm:
      raise LKGMNotValid('LKGM not provided.')
    logging.info('lkgm=%s', lkgm)

  def Run(self):
    self.CloseOldLKGMRolls()
    already_open_lkgm_cl = self.FindAlreadyOpenLKGMRoll()
    if already_open_lkgm_cl:
      self.SubmitToCQ(already_open_lkgm_cl)
    else:
      self._committer.Cleanup()
      self._committer.Checkout(self._NEEDED_FILES)
      self.UpdateLKGM()
      self.CommitNewLKGM()
      self._committer.Upload()

  def CheckoutChrome(self):
    """Checks out chrome into tmp checkout_dir."""
    self._committer.Checkout(self._NEEDED_FILES)

  @property
  def lkgm_file(self):
    return self._committer.FullPath(constants.PATH_TO_CHROME_LKGM)

  def CloseOldLKGMRolls(self):
    """Closes all open LKGM roll CLs that were last modified >24 hours ago.

    Any roll that hasn't passed the CQ in 24 hours is likely broken and can be
    discarded.
    """
    query_params = {
        'project': constants.CHROMIUM_SRC_PROJECT,
        'branch': 'main',
        'file': constants.PATH_TO_CHROME_LKGM,
        'age': '2d',
        'status': 'open',
        # Use 'owner' rather than 'uploader' or 'author' since those last two
        # can be overwritten when the gardener resolves a merge-conflict and
        # uploads a new patchset.
        'owner': self._committer.author,
    }
    open_issues = self._gerrit_helper.Query(**query_params)
    if not open_issues:
      logging.info('No old LKGM rolls detected.')
      return
    for open_issue in open_issues:
      if self._dryrun:
        logging.info(
            'Would have closed old LKGM roll crrev.com/c/%s',
            open_issue.gerrit_number)
      else:
        logging.info(
            'Closing old LKGM roll crrev.com/c/%s', open_issue.gerrit_number)
        self._gerrit_helper.AbandonChange(
            open_issue, msg='Superceded by LKGM %s' % self._lkgm)

  def FindAlreadyOpenLKGMRoll(self):
    """Queries Gerrit for a CL that already rolls the LKGM to our version.

    For a given LKGM, both the master-full and master-release builders provide
    SDKs needed by Chrome-infra. These two builders aren't synchronized, so
    one can finish hours before the other. To avoid updating the LKGM in Chrome
    before they're both finished, we take a two-stage approach:
    1. Whichever builder finishes first uploads the LKGM CL.
    2. Whichever builder finishes last submits that CL to the CQ.

    This method queries Gerrit to find the CL for step #2.

    Returns:
      Returns a patch.GerritPatch for the CL if it exists, None otherwise.
    """
    query_params = {
        'project': constants.CHROMIUM_SRC_PROJECT,
        'branch': 'main',
        'file': constants.PATH_TO_CHROME_LKGM,
        'status': 'open',
        # Use 'owner' rather than 'uploader' or 'author' since those last two
        # can be overwritten when the gardener resolves a merge-conflict and
        # uploads a new patchset.
        'owner': self._committer.author,
        # The value of the LKGM is included in the first line of the commit
        # message. So including that in our query should only return CLs that
        # roll to our LKGM.
        'message': urllib.parse.quote(self._commit_msg_header),
    }
    issues = self._gerrit_helper.Query(**query_params)
    if len(issues) > 1:
      # This shouldn't happen?
      raise LKGMNotValid('More than one roll CL open for LKGM %s'% self._lkgm)
    return issues[0] if issues else None

  def SubmitToCQ(self, already_open_lkgm_cl):
    """Sends the already_open_lkgm_cl to the CQ."""
    labels = {'Commit-Queue': 2}
    if self._dryrun:
      logging.info('Would have applied CQ+2 to %s', already_open_lkgm_cl)
    else:
      logging.info('Applying CQ+2 to %s', already_open_lkgm_cl)
      self._gerrit_helper.SetReview(already_open_lkgm_cl, labels=labels)

  def UpdateLKGM(self):
    """Updates the LKGM file with the new version."""
    lkgm_file = self.lkgm_file
    if not os.path.exists(lkgm_file):
      raise LKGMFileNotFound('%s is an invalid file' % lkgm_file)

    self._old_lkgm = osutils.ReadFile(lkgm_file)

    lv = distutils.version.LooseVersion
    if self._old_lkgm is not None and lv(self._lkgm) <= lv(self._old_lkgm):
      raise LKGMNotValid(
          'LKGM version (%s) is not newer than current version (%s).' %
          (self._lkgm, self._old_lkgm))

    logging.info('Updating LKGM version: %s (was %s),',
                 self._lkgm, self._old_lkgm)
    osutils.WriteFile(lkgm_file, self._lkgm)

  def ComposeCommitMsg(self):
    """Constructs and returns the commit message for the LKGM update."""
    commit_msg_template = (
        '%(header)s\n'
        '%(build_link)s'
        '\n%(cq_includes)s')
    cq_includes = ''
    for bot in self._PRESUBMIT_BOTS:
      cq_includes += 'CQ_INCLUDE_TRYBOTS=luci.chrome.try:%s\n' % bot
    build_link = ''
    if self._buildbucket_id:
      build_link = '\nUploaded by https://ci.chromium.org/b/%s\n' % (
          self._buildbucket_id)
    return commit_msg_template % dict(
        header=self._commit_msg_header, cq_includes=cq_includes,
        build_link=build_link)

  def CommitNewLKGM(self):
    """Commits the new LKGM file using our template commit message."""
    self._committer.Commit([constants.PATH_TO_CHROME_LKGM],
                           self.ComposeCommitMsg())


def GetOpts(argv):
  """Returns a dictionary of parsed options.

  Args:
    argv: raw command line.

  Returns:
    Dictionary of parsed options.
  """
  committer_parser = chrome_committer.ChromeCommitter.GetParser()
  parser = commandline.ArgumentParser(description=__doc__,
                                      parents=[committer_parser],
                                      add_help=False, logging=False)
  parser.add_argument('--lkgm', required=True,
                      help='LKGM version to update to.')
  parser.add_argument('--buildbucket-id',
                      help='Buildbucket ID of the build that ran this script. '
                           'Will be linked in the commit message if specified.')
  return parser.parse_args(argv)

def main(argv):
  opts = GetOpts(argv)
  committer = ChromeLKGMCommitter(opts.user_email, opts.workdir,
                                  opts.lkgm, opts.dryrun, opts.buildbucket_id)
  committer.Run()
  return 0
