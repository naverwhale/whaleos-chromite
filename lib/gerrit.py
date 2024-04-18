# Copyright 2011 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module containing helper class and methods for interacting with Gerrit."""

import logging
import operator
import re
from typing import Tuple

from chromite.lib import config_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import git
from chromite.lib import gob_util
from chromite.lib import parallel
from chromite.lib import patch as cros_patch
from chromite.lib import retry_util


class GerritException(Exception):
    """Base exception, thrown for gerrit failures"""


class QueryHasNoResults(GerritException):
    """Exception thrown when a query returns no results."""


class QueryNotSpecific(GerritException):
    """Thrown when a query needs to identify one CL, but matched multiple."""


class GerritHelper:
    """Helper class to manage interaction with the gerrit-on-borg service."""

    # Maximum number of results to return per query.
    _GERRIT_MAX_QUERY_RETURN = 500

    # Number of processes to run in parallel when fetching from Gerrit. The
    # Gerrit team recommended keeping this small to avoid putting too much
    # load on the server.
    _NUM_PROCESSES = 10

    # Fields that appear in gerrit change query results.
    MORE_CHANGES = "_more_changes"

    def __init__(self, host, remote, print_cmd=True):
        """Initialize.

        Args:
            host: Hostname (without protocol prefix) of the gerrit server.
            remote: The symbolic name of a known remote git host, taken from
                cbuildbot.constants.
            print_cmd: Determines whether all run invocations will be echoed.
                Set to False for quiet operation.
        """
        self.host = host
        self.remote = remote
        self.print_cmd = bool(print_cmd)
        self._version = None

    @classmethod
    def FromRemote(cls, remote, **kwargs):
        site_params = config_lib.GetSiteParams()
        if remote == site_params.INTERNAL_REMOTE:
            host = site_params.INTERNAL_GERRIT_HOST
        elif remote == site_params.EXTERNAL_REMOTE:
            host = site_params.EXTERNAL_GERRIT_HOST
        else:
            raise ValueError("Remote %s not supported." % remote)
        return cls(host, remote, **kwargs)

    @classmethod
    def FromGob(cls, gob, **kwargs):
        """Return a helper for a GoB instance."""
        site_params = config_lib.GetSiteParams()
        host = constants.GOB_HOST % ("%s-review" % gob)
        # TODO(phobbs) this will be wrong when "gob" isn't in GOB_REMOTES.
        # We should get rid of remotes altogether and just use the host.
        return cls(host, site_params.GOB_REMOTES.get(gob, gob), **kwargs)

    def SetPrivate(self, change, private, dryrun=False):
        """Sets the private bit on the given CL.

        Args:
            change: CL number.
            private: bool to indicate what value to set for the private bit.
            dryrun: If True, only print what would have been done.
        """
        if private:
            if dryrun:
                logging.info('Would have made "%s" private', change)
            else:
                gob_util.MarkPrivate(self.host, change)
        else:
            if dryrun:
                logging.info('Would have made "%s" public', change)
            else:
                gob_util.MarkNotPrivate(self.host, change)

    def SetAttentionSet(
        self,
        change: str,
        add: Tuple[str, ...] = (),
        remove: Tuple[str, ...] = (),
        dryrun: bool = False,
        notify: str = "ALL",
        message: str = "gerrit CLI",
    ):
        """Modify the attention set of a gerrit change.

        Args:
            change: ChangeId or change number for a gerrit review.
            add: Sequence of email addresses to add to attention set.
            remove: Sequence of email addresses to remove from attention set.
            dryrun: If True, only print what would have been done.
            notify: A string, parameter controlling gerrit's email generation.
            message: A string, setting the reason for changing the attention
                set.
        """
        if add:
            if dryrun:
                logging.info(
                    'Would have added %s to "%s" attention set', add, change
                )
            else:
                gob_util.AddAttentionSet(
                    self.host, change, add, notify=notify, reason=message
                )
        if remove:
            if dryrun:
                logging.info(
                    'Would have removed %s from "%s" attention set',
                    remove,
                    change,
                )
            else:
                gob_util.RemoveAttentionSet(
                    self.host, change, remove, notify=notify, reason=message
                )

    def SetReviewers(
        self, change, add=(), remove=(), dryrun=False, notify="ALL"
    ):
        """Modify the list of reviewers on a gerrit change.

        Args:
            change: ChangeId or change number for a gerrit review.
            add: Sequence of email addresses of reviewers to add.
            remove: Sequence of email addresses of reviewers to remove.
            dryrun: If True, only print what would have been done.
            notify: A string, parameter controlling gerrit's email generation.
        """
        if add:
            if dryrun:
                logging.info('Would have added %s to "%s"', add, change)
            else:
                gob_util.AddReviewers(self.host, change, add, notify=notify)
        if remove:
            if dryrun:
                logging.info('Would have removed %s to "%s"', remove, change)
            else:
                gob_util.RemoveReviewers(
                    self.host, change, remove, notify=notify
                )

    def SetWorkInProgress(self, change, wip, msg="", dryrun=False):
        """Sets the work in progress bit on the given CL.

        Args:
            change: CL number.
            wip: bool to indicate what value to set for the work in progress
                bit.
            msg: Message to post to the CL.
            dryrun: If True, only print what would have been done.
        """
        if wip:
            if dryrun:
                logging.info('Would have made "%s" work in progress', change)
            else:
                gob_util.MarkWorkInProgress(self.host, change, msg)
        else:
            if dryrun:
                logging.info('Would have made "%s" ready for review', change)
            else:
                gob_util.MarkReadyForReview(self.host, change, msg)

    def GetChangeDetail(self, change_num, verbose=False):
        """Return detailed information about a gerrit change.

        Args:
            change_num: A gerrit change number.
            verbose: Whether to print more properties of the change
        """
        if verbose:
            o_params = (
                "ALL_REVISIONS",
                "ALL_FILES",
                "ALL_COMMITS",
                "DETAILED_LABELS",
                "MESSAGES",
                "DOWNLOAD_COMMANDS",
                "CHECK",
            )
        else:
            o_params = ("CURRENT_REVISION", "CURRENT_COMMIT")

        return gob_util.GetChangeDetail(
            self.host, change_num, o_params=o_params
        )

    def GetRelatedChangesInfo(self, change_num):
        """Returns dict that represents a gerrit API RelatedChangesInfo entity.

        Args:
            change_num: A gerrit change number.

        Returns:
            A dict representing a RelatedChangesInfo entity.
        """

        return gob_util.GetRelatedChanges(self.host, change_num)

    def GrabPatchFromGerrit(self, project, change, commit, must_match=True):
        """Return a cros_patch.GerritPatch representing a gerrit change.

        Args:
            project: The name of the gerrit project for the change.
            change: A ChangeId or gerrit number for the change.
            commit: The git commit hash for a patch associated with the change.
            must_match: Raise an exception if the change is not found.
        """
        query = {"project": project, "commit": commit, "must_match": must_match}
        return self.QuerySingleRecord(change, **query)

    def IsChangeCommitted(self, change, must_match=False):
        """Check whether a gerrit change has been merged.

        Args:
            change: A gerrit change number.
            must_match: Raise an exception if the change is not found.  If this
                is False, then a missing change will return None.
        """
        change = gob_util.GetChange(self.host, change)
        if not change:
            if must_match:
                raise QueryHasNoResults(
                    "Could not query for change %s" % change
                )
            return
        return change.get("status") == "MERGED"

    def GetLatestSHA1ForBranch(self, project, branch):
        """Return the git hash at the tip of a branch."""
        url = "%s://%s/%s" % (gob_util.GIT_PROTOCOL, self.host, project)
        cmd = ["ls-remote", url, "refs/heads/%s" % branch]
        try:
            result = git.RunGit(".", cmd, print_cmd=self.print_cmd)
            if result:
                return result.stdout.split()[0]
        except cros_build_lib.RunCommandError:
            logging.error(
                'Command "%s" failed.',
                cros_build_lib.CmdToStr(cmd),
                exc_info=True,
            )

    def QuerySingleRecord(self, change=None, **kwargs):
        """Free-form query of a gerrit change that expects a single result.

        Args:
            change: A gerrit change number.
            **kwargs:
                dryrun: Don't query the gerrit server; just return None.
                must_match: Raise an exception if the query comes back empty. If
                    this is False, an unsatisfied query will return None. Refer
                    to Query() docstring for remaining arguments.

        Returns:
            If kwargs['raw'] == True, return a python dict representing the
            change; otherwise, return a cros_patch.GerritPatch object.
        """
        query_kwds = kwargs
        dryrun = query_kwds.get("dryrun")
        must_match = query_kwds.pop("must_match", True)
        results = self.Query(change, **query_kwds)
        if dryrun:
            return None
        elif not results:
            if must_match:
                raise QueryHasNoResults("Query %s had no results" % (change,))
            return None
        elif len(results) != 1:
            raise QueryNotSpecific(
                "Query %s returned too many results: %s" % (change, results)
            )
        return results[0]

    def Query(
        self,
        change=None,
        sort=None,
        current_patch=True,
        options=(),
        dryrun=False,
        raw=False,
        start=None,
        bypass_cache=True,
        verbose=False,
        convert_results=True,
        **kwargs,
    ):
        """Free-form query for gerrit changes.

        Args:
            change: ChangeId, git commit hash, or gerrit number for a change.
            sort: A functor to extract a sort key from a cros_patch.GerritChange
                object, for sorting results.  If this is None, results will not
                be sorted.
            current_patch: If True, ask the gerrit server for extra information
                about the latest uploaded patch.
            options: Deprecated.
            dryrun: If True, don't query the gerrit server; return an empty
                list.
            raw: If True, return a list of python dict's representing the query
                results.  Otherwise, return a list of cros_patch.GerritPatch.
            start: Offset in the result set to start at.
            bypass_cache: Query each change to make sure data is up to date.
            verbose: Whether to get all revisions and details about a change.
            convert_results: Whether to convert the results from the new json
                schema to the old SQL schema.
            **kwargs: A dict of query parameters, as described here:
                https://gerrit-review.googlesource.com/Documentation/rest-api-changes.html#list-changes

        Returns:
            A list of python dicts or cros_patch.GerritChange.
        """
        query_kwds = kwargs
        if options:
            raise GerritException(
                '"options" argument unsupported on gerrit-on-borg.'
            )
        url_prefix = gob_util.GetGerritFetchUrl(self.host)
        # All possible params are documented at
        # pylint: disable=C0301
        # https://gerrit-review.googlesource.com/Documentation/rest-api-changes.html#list-changes
        o_params = ["DETAILED_ACCOUNTS", "ALL_REVISIONS", "DETAILED_LABELS"]
        if current_patch:
            o_params.extend(["CURRENT_COMMIT", "CURRENT_REVISION"])
        elif verbose and not convert_results:
            o_params = [
                "ALL_REVISIONS",
                "ALL_FILES",
                "ALL_COMMITS",
                "DETAILED_LABELS",
                "MESSAGES",
                "DOWNLOAD_COMMANDS",
                "CHECK",
            ]

        if change and cros_patch.ParseGerritNumber(change) and not query_kwds:
            if dryrun:
                logging.info(
                    "Would have run gob_util.GetChangeDetail(%s, %s)",
                    self.host,
                    change,
                )
                return []
            change = self.GetChangeDetail(change, verbose=verbose)
            if change is None:
                return []
            patch_dict = cros_patch.GerritPatch.ConvertQueryResults(
                change, self.host
            )
            if raw:
                return [patch_dict]
            return [cros_patch.GerritPatch(patch_dict, self.remote, url_prefix)]

        # TODO: We should allow querying using a cros_patch.PatchQuery
        # object directly.
        if change and cros_patch.ParseSHA1(change):
            # Use commit:sha1 for accurate query results (crbug.com/358381).
            kwargs["commit"] = change
            change = None
        elif change and cros_patch.ParseChangeID(change):
            # Use change:change-id for accurate query results
            # (crbug.com/357876).
            kwargs["change"] = change
            change = None
        elif change and cros_patch.ParseFullChangeID(change):
            change = cros_patch.ParseFullChangeID(change)
            assert change  # Help the type checker.
            kwargs["change"] = change.change_id
            kwargs["project"] = change.project
            kwargs["branch"] = change.branch
            change = None

        if change and query_kwds.get("change"):
            raise GerritException(
                "Bad query params: provided a change-id-like query,"
                ' and a "change" search parameter'
            )

        if dryrun:
            logging.info(
                "Would have run gob_util.QueryChanges(%s, %s, "
                "first_param=%s, limit=%d)",
                self.host,
                repr(query_kwds),
                change,
                self._GERRIT_MAX_QUERY_RETURN,
            )
            return []

        start = 0
        moar = gob_util.QueryChanges(
            self.host,
            query_kwds,
            first_param=change,
            start=start,
            limit=self._GERRIT_MAX_QUERY_RETURN,
            o_params=o_params,
        )
        result = list(moar)
        while moar and self.MORE_CHANGES in moar[-1]:
            start += len(moar)
            moar = gob_util.QueryChanges(
                self.host,
                query_kwds,
                first_param=change,
                start=start,
                limit=self._GERRIT_MAX_QUERY_RETURN,
                o_params=o_params,
            )
            result.extend(moar)

        # NOTE: Query results are served from the gerrit cache, which may be
        # stale. To make sure the patch information is accurate, re-request each
        # query result directly, circumventing the cache.  For reference:
        #   https://code.google.com/p/chromium/issues/detail?id=302072
        if bypass_cache:
            result = self.GetMultipleChangeDetail(
                [x["_number"] for x in result], verbose=verbose
            )
        if convert_results:
            result = [
                cros_patch.GerritPatch.ConvertQueryResults(x, self.host)
                for x in result
            ]
        if sort:
            result = sorted(result, key=operator.itemgetter(sort))
        if raw:
            return result
        return [
            cros_patch.GerritPatch(x, self.remote, url_prefix) for x in result
        ]

    def GetMultipleChangeDetail(self, changes, verbose=False):
        """Query the gerrit server for multiple changes using GetChangeDetail.

        Args:
            changes: A sequence of gerrit change numbers.
            verbose: Whether to return more properties of the change.

        Returns:
            A list of the raw output of GetChangeDetail.
        """
        inputs = [[change] for change in changes]
        return parallel.RunTasksInProcessPool(
            lambda c: self.GetChangeDetail(c, verbose=verbose),
            inputs,
            processes=self._NUM_PROCESSES,
        )

    def QueryMultipleCurrentPatchset(self, changes):
        """Query the gerrit server for multiple changes.

        Args:
            changes: A sequence of gerrit change numbers.

        Returns:
            A list of cros_patch.GerritPatch.
        """
        if not changes:
            return

        url_prefix = gob_util.GetGerritFetchUrl(self.host)
        results = self.GetMultipleChangeDetail(changes)
        for change, change_detail in zip(changes, results):
            if not change_detail:
                raise GerritException(
                    "Change %s not found on server %s." % (change, self.host)
                )
            patch_dict = cros_patch.GerritPatch.ConvertQueryResults(
                change_detail, self.host
            )
            yield change, cros_patch.GerritPatch(
                patch_dict, self.remote, url_prefix
            )

    @staticmethod
    def _to_changenum(change):
        """Unequivocally return a gerrit change number.

        The argument may either be an number, which will be returned unchanged;
        or an instance of GerritPatch, in which case its gerrit number will be
        returned.
        """
        # TODO(davidjames): Deprecate the ability to pass in strings to these
        #   functions -- API users should just pass in a GerritPatch instead or
        #   use the gob_util APIs directly.
        if isinstance(change, cros_patch.GerritPatch):
            return change.gerrit_number

        return change

    def CreateChange(
        self, project: str, branch: str, message: str, publish: bool
    ) -> cros_patch.GerritPatch:
        """Creates an empty change.

        The change will be empty of any file modifications. Use ChangeEdit below
        to add file modifications to the change.

        Args:
            project: The name of the gerrit project for the change.
            branch: Branch for the change.
            message: Initial commit message for the change.
            publish: If True, will publish the CL after uploading. Stays in WIP
                mode otherwise.

        Returns:
            A cros_patch.GerritChange for the created change.
        """
        resp = gob_util.CreateChange(
            self.host, project, branch, message, publish
        )
        patch_dict = cros_patch.GerritPatch.ConvertQueryResults(resp, self.host)
        return cros_patch.GerritPatch(patch_dict, self.remote, "")

    def ChangeEdit(self, change: str, path: str, contents: str) -> None:
        """Attaches file modifications to an open change.

        Args:
            change: A gerrit change number.
            path: Path of the file in the repo to modify.
            contents: New contents of the file.
        """
        gob_util.ChangeEdit(self.host, change, path, contents)
        gob_util.PublishChangeEdit(self.host, change)

    def SetReview(
        self,
        change,
        msg=None,
        labels=None,
        notify="ALL",
        reviewers=None,
        cc=None,
        remove_reviewers=None,
        ready=None,
        wip=None,
        dryrun=False,
    ):
        """Update the review labels on a gerrit change.

        Args:
            change: A gerrit change number.
            msg: A text comment to post to the review.
            labels: A dict of label/value to set on the review.
            notify: A string, parameter controlling gerrit's email generation.
            reviewers: List of people to add as reviewers.
            cc: List of people to add to CC.
            remove_reviewers: List of people to remove (reviewers or CC).
                NB: This is one option due to Gerrit limitations.
            ready: Mark CL as ready.
            wip: Mark CL as work-in-progress.
            dryrun: If True, don't actually update the review.
        """
        if dryrun:
            if msg:
                logging.info(
                    'Would have added message "%s" to change "%s".', msg, change
                )
            if labels:
                for key, val in labels.items():
                    logging.info(
                        'Would have set label "%s" to "%s" for change "%s".',
                        key,
                        val,
                        change,
                    )
            if reviewers:
                logging.info("Would have add %s as reviewers", reviewers)
            if cc:
                logging.info("Would have add %s to CC", cc)
            if remove_reviewers:
                logging.info(
                    "Would have removed %s as reviewer & from CC",
                    remove_reviewers,
                )
            if ready:
                logging.info("Would mark it as ready")
            elif wip:
                logging.info("Would mark it as WIP")
            return
        gob_util.SetReview(
            self.host,
            self._to_changenum(change),
            msg=msg,
            labels=labels,
            notify=notify,
            reviewers=reviewers,
            cc=cc,
            remove_reviewers=remove_reviewers,
            ready=ready,
            wip=wip,
        )

    def SetTopic(self, change, topic, dryrun=False):
        """Update the topic on a gerrit change.

        Args:
            change: A gerrit change number.
            topic: The topic to set the review to.
            dryrun: If True, don't actually set the topic.
        """
        if dryrun:
            logging.info(
                'Would have set topic "%s" for change "%s".', topic, change
            )
            return
        gob_util.SetTopic(self.host, self._to_changenum(change), topic=topic)

    def SetHashtags(self, change, add, remove, dryrun=False):
        """Add/Remove hashtags for a gerrit change.

        Args:
            change: A gerrit change number.
            add: a list of hashtags to add.
            remove: a list of hashtags to remove.
            dryrun: If True, don't actually set the hashtag.
        """
        if dryrun:
            logging.info(
                "Would add %r and remove %r for change %s", add, remove, change
            )
            return
        gob_util.SetHashtags(
            self.host, self._to_changenum(change), add=add, remove=remove
        )

    def RemoveReady(self, change, dryrun=False):
        """Set the 'Commit-Queue' label on a |change| to '0'."""
        if dryrun:
            logging.info("Would have reset Commit-Queue label for %s", change)
            return
        gob_util.ResetReviewLabels(
            self.host,
            self._to_changenum(change),
            label="Commit-Queue",
            notify="OWNER",
        )

    def SubmitChange(self, change, dryrun=False, notify=None):
        """Land (merge) a gerrit change using the JSON API."""
        if dryrun:
            logging.info("Would have submitted change %s", change)
            return
        if isinstance(change, cros_patch.GerritPatch):
            rev = change.sha1
        else:
            rev = None
        gob_util.SubmitChange(
            self.host, self._to_changenum(change), revision=rev, notify=notify
        )

    def ReviewedChange(self, change, dryrun=False):
        """Mark a gerrit change as reviewed."""
        if dryrun:
            logging.info("Would have reviewed change %s", change)
            return
        gob_util.ReviewedChange(self.host, self._to_changenum(change))

    def UnreviewedChange(self, change, dryrun=False):
        """Unmark a gerrit change as reviewed."""
        if dryrun:
            logging.info("Would have unreviewed change %s", change)
            return
        gob_util.UnreviewedChange(self.host, self._to_changenum(change))

    def IgnoreChange(self, change, dryrun=False):
        """Ignore a gerrit change."""
        if dryrun:
            logging.info("Would have ignored change %s", change)
            return
        gob_util.IgnoreChange(self.host, self._to_changenum(change))

    def UnignoreChange(self, change, dryrun=False):
        """Unignore a gerrit change."""
        if dryrun:
            logging.info("Would have unignored change %s", change)
            return
        gob_util.UnignoreChange(self.host, self._to_changenum(change))

    def AbandonChange(self, change, msg="", dryrun=False, notify=None):
        """Mark a gerrit change as 'Abandoned'."""
        if dryrun:
            logging.info("Would have abandoned change %s", change)
            return
        gob_util.AbandonChange(
            self.host, self._to_changenum(change), msg=msg, notify=notify
        )

    def RestoreChange(self, change, dryrun=False):
        """Re-activate a previously abandoned gerrit change."""
        if dryrun:
            logging.info("Would have restored change %s", change)
            return
        gob_util.RestoreChange(self.host, self._to_changenum(change))

    def Delete(self, change, dryrun=False):
        """Delete a gerrit change."""
        if dryrun:
            logging.info("Would have deleted change %s", change)
            return
        gob_util.Delete(self.host, self._to_changenum(change))

    def CherryPick(
        self,
        change,
        branch,
        rev: str = "current",
        msg: str = "",
        allow_conflicts: bool = False,
        dryrun: bool = False,
        notify=None,
    ):
        """Cherry pick a CL to a branch.

        Args:
            change: A gerrit change number.
            branch: The destination branch.
            rev: The specific revision to cherry pick back.
            msg: An additional message to include.
            allow_conflicts: Allow cherry-picks to contain conflicts.
            dryrun: If True, don't actually set the hashtag.
            notify: Who to send notifications to.
        """
        if dryrun:
            logging.info(
                "Would cherry-pick change %s (revision %s) to branch %s",
                change,
                rev,
                branch,
            )
            return
        return gob_util.CherryPick(
            self.host,
            self._to_changenum(change),
            branch,
            rev=rev,
            msg=msg,
            allow_conflicts=allow_conflicts,
            notify=notify,
        )

    def GetAccount(self, account="self"):
        """Get information about the user account."""
        return gob_util.GetAccount(self.host, account=account)

    def _get_changenumber_from_stdout(self, stdout):
        """Retrieve the change number written in the URL of the git stdout."""
        url = git.GetUrlFromRemoteOutput(stdout)
        if not url:
            return None
        match = re.search(r"(?P<changenum>[0-9]+)$", url)
        if match:
            return match["changenum"]
        return None

    def CreateGerritPatch(
        self, cwd, remote, ref, dryrun=False, notify="ALL", **kwargs
    ):
        """Upload a change and retrieve a GerritPatch describing it.

        This requires a copy of the project checked out locally. To create a
        GerritPatch without a local checkout, use CreateChange() below.

        Args:
            cwd: The repository that we are working on.
            remote: The remote to upload changes to.
            ref: The ref where changes will be uploaded to.
            dryrun: If True, then return None.
            notify: A string, parameter controlling gerrit's email generation.
            **kwargs: Keyword arguments to be passed to QuerySingleRecord.

        Returns:
            A GerritPatch object describing the change for the HEAD commit.
        """
        # If dryrun is true then skip all network calls and return None.
        if dryrun:
            logging.info(
                "Would have returned a GerritPatch object describing the"
                "local changes."
            )
            return None

        # Upload the local changes to remote.
        ret = git.RunGit(
            cwd, ["push", remote, f"HEAD:refs/for/{ref}%notify={notify}"]
        )
        change_number = self._get_changenumber_from_stdout(ret.stdout)

        # If we fail to grab a change number from the stdout then fall back to
        # the ChangeID.
        change_number = change_number or git.GetChangeId(cwd)

        def PatchQuery():
            """Retrieve the GerritPatch describing the change."""
            return self.QuerySingleRecord(change=change_number, **kwargs)

        return retry_util.RetryException(
            QueryHasNoResults, 5, PatchQuery, sleep=1
        )


def GetGerritPatchInfo(patches):
    """Query Gerrit server for patch information using string queries.

    Args:
        patches: A list of patch IDs to query. Internal patches start with a
            '*'.

    Returns:
        A list of GerritPatch objects describing each patch.  Only the first
        instance of a requested patch is returned.

    Raises:
        PatchException: if a patch can't be found.
        ValueError: if a query string cannot be converted to a PatchQuery
            object.
    """
    return GetGerritPatchInfoWithPatchQueries(
        [cros_patch.ParsePatchDep(p) for p in patches]
    )


def GetGerritPatchInfoWithPatchQueries(patches):
    """Query Gerrit server for patch information using PatchQuery objects.

    Args:
        patches: A list of PatchQuery objects to query.

    Returns:
        A list of GerritPatch objects describing each patch.  Only the first
        instance of a requested patch is returned.

    Raises:
        PatchException if a patch can't be found.
    """
    site_params = config_lib.GetSiteParams()
    seen = set()
    results = []
    order = {k.ToGerritQueryText(): idx for (idx, k) in enumerate(patches)}
    for remote in site_params.CHANGE_PREFIX.keys():
        helper = GetGerritHelper(remote)
        raw_ids = [x.ToGerritQueryText() for x in patches if x.remote == remote]
        for k, change in helper.QueryMultipleCurrentPatchset(raw_ids):
            # return a unique list, while maintaining the ordering of the first
            # seen instance of each patch.  Do this to ensure whatever ordering
            # the user is trying to enforce, we honor; lest it break on
            # cherry-picking.
            if change.id not in seen:
                results.append((order[k], change))
                seen.add(change.id)

    return [change for _idx, change in sorted(results)]


def GetGerritHelper(remote=None, gob=None, **kwargs):
    """Return a GerritHelper instance for interacting with the given remote."""
    if gob:
        return GerritHelper.FromGob(gob, **kwargs)
    else:
        return GerritHelper.FromRemote(remote, **kwargs)


def GetGerritHelperForChange(change):
    """Return a usable GerritHelper instance for this change.

    If you need a GerritHelper for a specific change, get it via this
    function.
    """
    return GetGerritHelper(change.remote)


def GetCrosInternal(**kwargs):
    """Convenience method for accessing private ChromeOS gerrit."""
    site_params = config_lib.GetSiteParams()
    return GetGerritHelper(site_params.INTERNAL_REMOTE, **kwargs)


def GetCrosExternal(**kwargs):
    """Convenience method for accessing public ChromiumOS gerrit."""
    site_params = config_lib.GetSiteParams()
    return GetGerritHelper(site_params.EXTERNAL_REMOTE, **kwargs)


def GetChangeRef(change_number, patchset=None):
    """Given a change number, return the refs/changes/* space for it.

    Args:
        change_number: The gerrit change number you want a refspec for.
        patchset: If given it must either be an integer or '*'.  When given, the
            returned refspec is for that exact patchset.  If '*' is given, it's
            used for pulling down all patchsets for that change.

    Returns:
        A git refspec.
    """
    change_number = int(change_number)
    s = "refs/changes/%02i/%i" % (change_number % 100, change_number)
    if patchset is not None:
        s += "/%s" % ("*" if patchset == "*" else int(patchset))
    return s
