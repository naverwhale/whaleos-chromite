# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A command line interface to Gerrit-on-borg instances.

Internal Note:
To expose a function directly to the command line interface, name your function
with the prefix "UserAct".
"""

import argparse
import collections
import configparser
import enum
import functools
import inspect
import json
import logging
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
from typing import List, Set, Tuple

from chromite.lib import chromite_config
from chromite.lib import commandline
from chromite.lib import config_lib
from chromite.lib import cros_build_lib
from chromite.lib import gerrit
from chromite.lib import gob_util
from chromite.lib import parallel
from chromite.lib import patch
from chromite.lib import retry_util
from chromite.lib import terminal
from chromite.lib import uri_lib
from chromite.utils import memoize
from chromite.utils import pformat


class Config:
    """Manage the user's gerrit config settings.

    This is entirely unique to this gerrit command.  Inspiration for naming and
    layout is taken from ~/.gitconfig settings.
    """

    def __init__(self, path: Path = chromite_config.GERRIT_CONFIG):
        self.cfg = configparser.ConfigParser(interpolation=None)
        if path.exists():
            self.cfg.read(chromite_config.GERRIT_CONFIG)

    def expand_alias(self, action):
        """Expand any aliases."""
        alias = self.cfg.get("alias", action, fallback=None)
        if alias is not None:
            return shlex.split(alias)
        return action


class UserAction:
    """Base class for all custom user actions."""

    # The name of the command the user types in.
    COMMAND = None

    # Should output be paged?
    USE_PAGER = False

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""

    @staticmethod
    def __call__(opts):
        """Implement the action."""
        raise RuntimeError(
            "Internal error: action missing __call__ implementation"
        )


# How many connections we'll use in parallel.  We don't want this to be too high
# so we don't go over our per-user quota.  Pick 10 somewhat arbitrarily as that
# seems to be good enough for users.
CONNECTION_LIMIT = 10


COLOR = None

# Map the internal names to the ones we normally show on the web ui.
GERRIT_APPROVAL_MAP = {
    "COMR": [
        "CQ",
        "Commit Queue   ",
    ],
    "CRVW": [
        "CR",
        "Code Review    ",
    ],
    "SUBM": [
        "S ",
        "Submitted      ",
    ],
    "VRIF": [
        "V ",
        "Verified       ",
    ],
    "LCQ": [
        "L ",
        "Legacy         ",
    ],
}

# Order is important -- matches the web ui.  This also controls the short
# entries that we summarize in non-verbose mode.
GERRIT_SUMMARY_CATS = (
    "CR",
    "CQ",
    "V",
)

# Shorter strings for CL status messages.
GERRIT_SUMMARY_MAP = {
    "ABANDONED": "ABD",
    "MERGED": "MRG",
    "NEW": "NEW",
    "WIP": "WIP",
}


class OutputFormat(enum.Enum):
    """Type for the requested output format.

    AUTO: Automatically determine the format based on what the user
      might want.  This is PRETTY if attached to a terminal, RAW
      otherwise.
    RAW: Output CLs one per line, suitable for mild scripting.
    JSON: JSON-encoded output, suitable for spicy scripting.
    MARKDOWN: Suitable for posting in a bug or CL comment.
    PRETTY: Suitable for viewing in a color terminal.
    """

    AUTO = 0
    AUTOMATIC = AUTO
    RAW = 1
    JSON = 2
    MARKDOWN = 3
    PRETTY = 4


def red(s):
    return COLOR.Color(terminal.Color.RED, s)


def green(s):
    return COLOR.Color(terminal.Color.GREEN, s)


def blue(s):
    return COLOR.Color(terminal.Color.BLUE, s)


def _run_parallel_tasks(task, jobs: int, *args):
    """Small wrapper around BackgroundTaskRunner to enforce job count."""

    # When we run in parallel, we can hit the max requests limit.
    def check_exc(e):
        if not isinstance(e, gob_util.GOBError):
            raise e
        return e.http_status == 429

    @retry_util.WithRetry(5, handler=check_exc, sleep=1, backoff_factor=2)
    def retry(*args):
        try:
            task(*args)
        except gob_util.GOBError as e:
            if e.http_status != 429:
                logging.warning("%s: skipping due: %s", args, e)
            else:
                raise

    with parallel.BackgroundTaskRunner(retry, processes=jobs) as q:
        for arg in args:
            q.put([arg])


def limits(cls):
    """Given a dict of fields, calculate the longest string lengths

    This allows you to easily format the output of many results so that the
    various cols all line up correctly.
    """
    lims = {}
    for cl in cls:
        for k in cl.keys():
            # Use %s rather than str() to avoid codec issues.
            # We also do this so we can format integers.
            lims[k] = max(lims.get(k, 0), len("%s" % cl[k]))
    return lims


def process_add_remove_lists(items: List[str]) -> Tuple[Set[str], Set[str]]:
    """Split |items| into "add" and "remove" lists.

    Invalid items will cause the program to exit with an error message.

    Args:
        items: Items that begin with "~" or "-" mean "remove" while others are
            "add".

    Returns:
        A tuple of sets: all the items to add and all the items to remove.
        NB: The leading "~" & "-" will automatically be stripped.
    """
    add_list, remove_list, invalid_list = set(), set(), set()
    for item in items:
        if not item:
            invalid_list.add(item)
            continue

        remove = False
        if item[0] in ("~", "-"):
            remove = True
            item = item[1:]

        if remove:
            remove_list.add(item)
            add_list.discard(item)
        else:
            add_list.add(item)
            remove_list.discard(item)

    if invalid_list:
        cros_build_lib.Die("Invalid arguments: %s", ", ".join(invalid_list))

    return (add_list, remove_list)


# TODO: This func really needs to be merged into the core gerrit logic.
def GetGerrit(opts, cl=None):
    """Auto pick the right gerrit instance based on the |cl|

    Args:
        opts: The general options object.
        cl: A CL taking one of the forms: 1234 *1234 chromium:1234

    Returns:
        A tuple of a gerrit object and a sanitized CL #.
    """
    gob = opts.gob
    if cl is not None:
        if cl.startswith("*") or cl.startswith("chrome-internal:"):
            gob = config_lib.GetSiteParams().INTERNAL_GOB_INSTANCE
            if cl.startswith("*"):
                cl = cl[1:]
            else:
                cl = cl[16:]
        elif ":" in cl:
            gob, cl = cl.split(":", 1)

    if not gob in opts.gerrit:
        opts.gerrit[gob] = gerrit.GetGerritHelper(gob=gob, print_cmd=opts.debug)

    return (opts.gerrit[gob], cl)


def GetApprovalSummary(_opts, cls):
    """Return a dict of the most important approvals"""
    approvs = {x: "" for x in GERRIT_SUMMARY_CATS}
    for approver in cls.get("currentPatchSet", {}).get("approvals", []):
        cats = GERRIT_APPROVAL_MAP.get(approver["type"])
        if not cats:
            logging.warning(
                "unknown gerrit approval type: %s", approver["type"]
            )
            continue
        cat = cats[0].strip()
        val = int(approver["value"])
        if not cat in approvs:
            # Ignore the extended categories in the summary view.
            continue
        elif approvs[cat] == "":
            approvs[cat] = val
        elif val < 0:
            approvs[cat] = min(approvs[cat], val)
        else:
            approvs[cat] = max(approvs[cat], val)
    return approvs


def PrettyPrintCl(opts, cl, lims=None, show_approvals=True):
    """Pretty print a single result"""
    if lims is None:
        lims = {"url": 0, "project": 0}

    status = ""

    if opts.verbose:
        status += "%s " % (cl["status"],)
    else:
        status += "%s " % (GERRIT_SUMMARY_MAP.get(cl["status"], cl["status"]),)

    if show_approvals and not opts.verbose:
        approvs = GetApprovalSummary(opts, cl)
        for cat in GERRIT_SUMMARY_CATS:
            if approvs[cat] in ("", 0):
                functor = lambda x: x
            elif approvs[cat] < 0:
                functor = red
            else:
                functor = green
            status += functor("%s:%2s " % (cat, approvs[cat]))

    if opts.format is OutputFormat.MARKDOWN:
        print("* %s - %s" % (uri_lib.ShortenUri(cl["url"]), cl["subject"]))
    else:
        print(
            "%s %s%-*s %s"
            % (
                blue("%-*s" % (lims["url"], cl["url"])),
                status,
                lims["project"],
                cl["project"],
                cl["subject"],
            )
        )

    if show_approvals and opts.verbose:
        for approver in cl["currentPatchSet"].get("approvals", []):
            functor = red if int(approver["value"]) < 0 else green
            n = functor("%2s" % approver["value"])
            t = GERRIT_APPROVAL_MAP.get(
                approver["type"], [approver["type"], approver["type"]]
            )[1]
            print("      %s %s %s" % (n, t, approver["by"]["email"]))


def PrintCls(opts, cls, lims=None, show_approvals=True):
    """Print all results based on the requested format."""
    if opts.format is OutputFormat.RAW:
        site_params = config_lib.GetSiteParams()
        pfx = ""
        # Special case internal Chrome GoB as that is what most devs use.
        # They can always redirect the list elsewhere via the -g option.
        if opts.gob == site_params.INTERNAL_GOB_INSTANCE:
            pfx = site_params.INTERNAL_CHANGE_PREFIX
        for cl in cls:
            print("%s%s" % (pfx, cl["number"]))

    elif opts.format is OutputFormat.JSON:
        json.dump(cls, sys.stdout)

    else:
        if lims is None:
            lims = limits(cls)

        for cl in cls:
            PrettyPrintCl(opts, cl, lims=lims, show_approvals=show_approvals)


def _Query(opts, query, raw=True, helper=None):
    """Queries Gerrit with a query string built from the commandline options"""
    if opts.branch is not None:
        query += " branch:%s" % opts.branch
    if opts.project is not None:
        query += " project: %s" % opts.project
    if opts.topic is not None:
        query += " topic: %s" % opts.topic

    if helper is None:
        helper, _ = GetGerrit(opts)
    return helper.Query(query, raw=raw, bypass_cache=False)


def FilteredQuery(opts, query, helper=None):
    """Query gerrit and filter/clean up the results"""
    ret = []

    logging.debug("Running query: %s", query)
    for cl in _Query(opts, query, raw=True, helper=helper):
        # Gerrit likes to return a stats record too.
        if not "project" in cl:
            continue

        # Strip off common leading names since the result is still
        # unique over the whole tree.
        if not opts.verbose:
            for pfx in (
                "aosp",
                "chromeos",
                "chromiumos",
                "external",
                "overlays",
                "platform",
                "third_party",
            ):
                if cl["project"].startswith("%s/" % pfx):
                    cl["project"] = cl["project"][len(pfx) + 1 :]

            cl["url"] = uri_lib.ShortenUri(cl["url"])

        ret.append(cl)

    if opts.sort == "unsorted":
        return ret
    if opts.sort == "number":
        key = lambda x: int(x[opts.sort])
    else:
        key = lambda x: x[opts.sort]
    return sorted(ret, key=key)


class _ActionSearchQuery(UserAction):
    """Base class for actions that perform searches."""

    USE_PAGER = True

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        parser.add_argument(
            "--sort",
            default="number",
            help='Key to sort on (number, project); use "unsorted" to disable',
        )
        parser.add_argument(
            "-b", "--branch", help="Limit output to the specific branch"
        )
        parser.add_argument(
            "-p", "--project", help="Limit output to the specific project"
        )
        parser.add_argument(
            "-t", "--topic", help="Limit output to the specific topic"
        )


class ActionTodo(_ActionSearchQuery):
    """List CLs needing your review"""

    COMMAND = "todo"

    @staticmethod
    def __call__(opts):
        """Implement the action."""
        cls = FilteredQuery(opts, "attention:self")
        PrintCls(opts, cls)


class ActionSearch(_ActionSearchQuery):
    """List CLs matching the search query"""

    COMMAND = "search"

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        _ActionSearchQuery.init_subparser(parser)
        parser.add_argument("query", help="The search query")

    @staticmethod
    def __call__(opts):
        """Implement the action."""
        cls = FilteredQuery(opts, opts.query)
        PrintCls(opts, cls)


class ActionMine(_ActionSearchQuery):
    """List your CLs with review statuses"""

    COMMAND = "mine"

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        _ActionSearchQuery.init_subparser(parser)
        parser.add_argument(
            "--draft",
            default=False,
            action="store_true",
            help="Show draft changes",
        )

    @staticmethod
    def __call__(opts):
        """Implement the action."""
        if opts.draft:
            rule = "is:draft"
        else:
            rule = "status:new"
        cls = FilteredQuery(opts, "owner:self %s" % (rule,))
        PrintCls(opts, cls)


def _BreadthFirstSearch(to_visit, children, visited_key=lambda x: x):
    """Runs breadth first search starting from the nodes in |to_visit|

    Args:
        to_visit: the starting nodes
        children: a function which takes a node and returns the adjacent nodes
        visited_key: a function for deduplicating node visits. Defaults to the
            identity function (lambda x: x)

    Returns:
        A list of nodes which are reachable from any node in |to_visit| by
        calling
        |children| any number of times.
    """
    to_visit = list(to_visit)
    seen = set(visited_key(x) for x in to_visit)
    for node in to_visit:
        for child in children(node):
            key = visited_key(child)
            if key not in seen:
                seen.add(key)
                to_visit.append(child)
    return to_visit


class ActionDeps(_ActionSearchQuery):
    """List CLs matching a query, and transitive dependencies of those CLs."""

    COMMAND = "deps"

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        _ActionSearchQuery.init_subparser(parser)
        parser.add_argument("query", help="The search query")

    def __call__(self, opts):
        """Implement the action."""
        cls = _Query(opts, opts.query, raw=False)

        @memoize.Memoize
        def _QueryChange(cl, helper=None):
            return _Query(opts, cl, raw=False, helper=helper)

        transitives = _BreadthFirstSearch(
            cls,
            functools.partial(self._Children, opts, _QueryChange),
            visited_key=lambda cl: cl.PatchLink(),
        )

        # This is a hack to avoid losing GoB host for each CL.  The PrintCls
        # function assumes the GoB host specified by the user is the only one
        # that is ever used, but the deps command walks across hosts.
        if opts.format is OutputFormat.RAW:
            print("\n".join(x.PatchLink() for x in transitives))
        else:
            transitives_raw = [cl.patch_dict for cl in transitives]
            PrintCls(opts, transitives_raw)

    @staticmethod
    def _ProcessDeps(opts, querier, cl, deps):
        """Yields matching dependencies for a patch"""
        # We need to query the change to guarantee that we have a .gerrit_number
        for dep in deps:
            if not dep.remote in opts.gerrit:
                opts.gerrit[dep.remote] = gerrit.GetGerritHelper(
                    remote=dep.remote, print_cmd=opts.debug
                )
            helper = opts.gerrit[dep.remote]

            # TODO(phobbs) this should maybe catch network errors.
            changes = querier(dep.ToGerritQueryText(), helper=helper)

            # Our query might have matched more than one result. This can come
            # up when Cq-Depend uses a Gerrit Change-Id, but that Change-Id
            # shows up across multiple repos/branches. We blindly check all of
            # them in the hopes that all open ones are what the user wants, but
            # then again the Cq-Depend syntax itself is unable to differentiate.
            # *shrug*
            if len(changes) > 1:
                logging.warning(
                    "CL %s has an ambiguous CQ dependency %s",
                    cl,
                    dep.ToGerritQueryText(),
                )
            for change in changes:
                if change.status == "NEW":
                    yield change

    @classmethod
    def _Children(cls, opts, querier, cl):
        """Yields the Gerrit and Cq-Depend dependencies of a patch."""
        yield from cls._ProcessDeps(opts, querier, cl, cl.GerritDependencies())
        yield from cls._ProcessDeps(
            opts, querier, cl, patch.GetPaladinDeps(cl.commit_message)
        )


class ActionInspect(_ActionSearchQuery):
    """Show the details of one or more CLs"""

    COMMAND = "inspect"

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        _ActionSearchQuery.init_subparser(parser)
        parser.add_argument(
            "cls", nargs="+", metavar="CL", help="The CL(s) to update"
        )

    @staticmethod
    def __call__(opts):
        """Implement the action."""
        cls = []
        for arg in opts.cls:
            helper, cl = GetGerrit(opts, arg)
            change = FilteredQuery(opts, "change:%s" % cl, helper=helper)
            if change:
                cls.extend(change)
            else:
                logging.warning("no results found for CL %s", arg)
        PrintCls(opts, cls)


class _ActionLabeler(UserAction):
    """Base helper for setting labels."""

    LABEL = None
    VALUES = None

    @classmethod
    def init_subparser(cls, parser):
        """Add arguments to this action's subparser."""
        parser.add_argument(
            "-m",
            "--msg",
            "--message",
            metavar="MESSAGE",
            help="Optional message to include",
        )
        parser.add_argument(
            "cls", nargs="+", metavar="CL", help="The CL(s) to update"
        )
        parser.add_argument(
            "value",
            nargs=1,
            metavar="value",
            choices=cls.VALUES,
            help="The label value; one of [%(choices)s]",
        )

    @classmethod
    def __call__(cls, opts):
        """Implement the action."""

        # Convert user-friendly command line option into a gerrit parameter.
        def task(arg):
            helper, cl = GetGerrit(opts, arg)
            helper.SetReview(
                cl,
                labels={cls.LABEL: opts.value[0]},
                msg=opts.msg,
                dryrun=opts.dryrun,
                notify=opts.notify,
            )

        _run_parallel_tasks(task, opts.jobs, *opts.cls)


class ActionLabelAutoSubmit(_ActionLabeler):
    """Change the Auto-Submit label"""

    COMMAND = "label-as"
    LABEL = "Auto-Submit"
    VALUES = ("0", "1")


class ActionLabelCodeReview(_ActionLabeler):
    """Change the Code-Review label (1=LGTM 2=LGTM+Approved)"""

    COMMAND = "label-cr"
    LABEL = "Code-Review"
    VALUES = ("-2", "-1", "0", "1", "2")


class ActionLabelVerified(_ActionLabeler):
    """Change the Verified label"""

    COMMAND = "label-v"
    LABEL = "Verified"
    VALUES = ("-1", "0", "1")


class ActionLabelCommitQueue(_ActionLabeler):
    """Change the Commit-Queue label (1=dry-run 2=commit)"""

    COMMAND = "label-cq"
    LABEL = "Commit-Queue"
    VALUES = ("0", "1", "2")


class ActionLabelOwnersOverride(_ActionLabeler):
    """Change the Owners-Override label (1=Override)"""

    COMMAND = "label-oo"
    LABEL = "Owners-Override"
    VALUES = ("0", "1")


class _ActionSimpleParallelCLs(UserAction):
    """Base helper for actions that only accept CLs."""

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        parser.add_argument(
            "cls", nargs="+", metavar="CL", help="The CL(s) to update"
        )

    def __call__(self, opts):
        """Implement the action."""

        def task(arg):
            helper, cl = GetGerrit(opts, arg)
            self._process_one(helper, cl, opts)

        _run_parallel_tasks(task, opts.jobs, *opts.cls)


class ActionSubmit(_ActionSimpleParallelCLs):
    """Submit CLs"""

    COMMAND = "submit"

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        helper.SubmitChange(cl, dryrun=opts.dryrun, notify=opts.notify)


class ActionAbandon(_ActionSimpleParallelCLs):
    """Abandon CLs"""

    COMMAND = "abandon"

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        parser.add_argument(
            "-m",
            "--msg",
            "--message",
            metavar="MESSAGE",
            help="Include a message",
        )
        _ActionSimpleParallelCLs.init_subparser(parser)

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        helper.AbandonChange(
            cl, msg=opts.msg, dryrun=opts.dryrun, notify=opts.notify
        )


class ActionRestore(_ActionSimpleParallelCLs):
    """Restore CLs that were abandoned"""

    COMMAND = "restore"

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        helper.RestoreChange(cl, dryrun=opts.dryrun)


class ActionWorkInProgress(_ActionSimpleParallelCLs):
    """Mark CLs as work in progress"""

    COMMAND = "wip"

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        helper.SetWorkInProgress(cl, True, dryrun=opts.dryrun)


class ActionReadyForReview(_ActionSimpleParallelCLs):
    """Mark CLs as ready for review"""

    COMMAND = "ready"

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        helper.SetWorkInProgress(cl, False, dryrun=opts.dryrun)


class ActionReviewers(UserAction):
    """Add/remove reviewers' emails for a CL (prepend with '~' to remove)"""

    COMMAND = "reviewers"

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        parser.add_argument("cl", metavar="CL", help="The CL to update")
        parser.add_argument(
            "reviewers",
            type="email",
            nargs="+",
            help="The reviewers to add/remove",
        )

    @staticmethod
    def __call__(opts):
        """Implement the action."""
        add_list, remove_list = process_add_remove_lists(opts.reviewers)

        if add_list or remove_list:
            helper, cl = GetGerrit(opts, opts.cl)
            helper.SetReviewers(
                cl,
                add=add_list,
                remove=remove_list,
                dryrun=opts.dryrun,
                notify=opts.notify,
            )


class ActionAttentionSet(UserAction):
    """Add/remove emails from the attention set (prepend with '~' to remove)"""

    COMMAND = "attention"

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        parser.add_argument(
            "-m",
            "--msg",
            "--message",
            metavar="MESSAGE",
            help="Optional message to include",
            default="gerrit CLI",
        )
        parser.add_argument("cl", metavar="CL", help="The CL to update")
        parser.add_argument(
            "users",
            type="email",
            nargs="+",
            help="The users to add/remove from attention set",
        )

    @staticmethod
    def __call__(opts):
        """Implement the action."""
        add_list, remove_list = process_add_remove_lists(opts.users)

        if add_list or remove_list:
            helper, cl = GetGerrit(opts, opts.cl)
            helper.SetAttentionSet(
                cl,
                add=add_list,
                remove=remove_list,
                dryrun=opts.dryrun,
                notify=opts.notify,
                message=opts.msg,
            )


class ActionMessage(_ActionSimpleParallelCLs):
    """Add a message to a CL"""

    COMMAND = "message"

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        _ActionSimpleParallelCLs.init_subparser(parser)
        parser.add_argument("message", help="The message to post")

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        helper.SetReview(cl, msg=opts.message, dryrun=opts.dryrun)


class ActionTopic(_ActionSimpleParallelCLs):
    """Set a topic for one or more CLs"""

    COMMAND = "topic"

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        _ActionSimpleParallelCLs.init_subparser(parser)
        parser.add_argument("topic", help="The topic to set")

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        helper.SetTopic(cl, opts.topic, dryrun=opts.dryrun)


class ActionPrivate(_ActionSimpleParallelCLs):
    """Mark CLs private"""

    COMMAND = "private"

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        helper.SetPrivate(cl, True, dryrun=opts.dryrun)


class ActionPublic(_ActionSimpleParallelCLs):
    """Mark CLs public"""

    COMMAND = "public"

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        helper.SetPrivate(cl, False, dryrun=opts.dryrun)


class ActionSethashtags(UserAction):
    """Add/remove hashtags on a CL (prepend with '~' to remove)"""

    COMMAND = "hashtags"

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        parser.add_argument("cl", metavar="CL", help="The CL to update")
        parser.add_argument(
            "hashtags", nargs="+", help="The hashtags to add/remove"
        )

    @staticmethod
    def __call__(opts):
        """Implement the action."""
        add, remove = process_add_remove_lists(opts.hashtags)
        helper, cl = GetGerrit(opts, opts.cl)
        helper.SetHashtags(cl, list(add), list(remove), dryrun=opts.dryrun)


class ActionDelete(_ActionSimpleParallelCLs):
    """Delete CLs"""

    COMMAND = "delete"

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        helper.Delete(cl, dryrun=opts.dryrun)


class ActionReviewed(_ActionSimpleParallelCLs):
    """Mark CLs as reviewed"""

    COMMAND = "reviewed"

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        helper.ReviewedChange(cl, dryrun=opts.dryrun)


class ActionUnreviewed(_ActionSimpleParallelCLs):
    """Mark CLs as unreviewed"""

    COMMAND = "unreviewed"

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        helper.UnreviewedChange(cl, dryrun=opts.dryrun)


class ActionIgnore(_ActionSimpleParallelCLs):
    """Ignore CLs (suppress notifications/dashboard/etc...)"""

    COMMAND = "ignore"

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        helper.IgnoreChange(cl, dryrun=opts.dryrun)


class ActionUnignore(_ActionSimpleParallelCLs):
    """Unignore CLs (enable notifications/dashboard/etc...)"""

    COMMAND = "unignore"

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        helper.UnignoreChange(cl, dryrun=opts.dryrun)


class ActionCherryPick(UserAction):
    """Cherry-pick CLs to branches."""

    COMMAND = "cherry-pick"

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        # Should we add an option to walk Cq-Depend and try to cherry-pick them?
        parser.add_argument(
            "--rev",
            "--revision",
            default="current",
            help="A specific revision or patchset",
        )
        parser.add_argument(
            "-m",
            "--msg",
            "--message",
            metavar="MESSAGE",
            help="Include a message",
        )
        parser.add_argument(
            "--branches",
            "--branch",
            "--br",
            action="split_extend",
            default=[],
            required=True,
            help="The destination branches",
        )
        parser.add_argument(
            "--allow-conflicts",
            action="store_true",
            help="Cherry-pick the CL with conflicts.",
        )
        parser.add_argument(
            "cls", nargs="+", metavar="CL", help="The CLs to cherry-pick"
        )

    @staticmethod
    def __call__(opts):
        """Implement the action."""

        # Process branches in parallel, but CLs in serial in case of CL stacks.
        def task(branch):
            for arg in opts.cls:
                helper, cl = GetGerrit(opts, arg)
                ret = helper.CherryPick(
                    cl,
                    branch,
                    rev=opts.rev,
                    msg=opts.msg,
                    allow_conflicts=opts.allow_conflicts,
                    dryrun=opts.dryrun,
                    notify=opts.notify,
                )
                logging.debug("Response: %s", ret)
                if opts.format is OutputFormat.RAW:
                    print(ret["_number"])
                else:
                    uri = f'https://{helper.host}/c/{ret["_number"]}'
                    print(uri_lib.ShortenUri(uri))

        _run_parallel_tasks(task, opts.jobs, *opts.branches)


class ActionReview(_ActionSimpleParallelCLs):
    """Review CLs with multiple settings

    The reviewers & cc options can remove people by prepending '~' or '-'.
    Note: If you want to move someone (reviewer->CC or CC->reviewer), you don't
    have to remove them first, you only need to specify the final state.

    The label option supports extended/multiple syntax for easy use. The --label
    option may be specified multiple times (as settings are merges), and
    multiple labels are allowed in a single argument.  Each label has the form:
      <long or short name><=+-><value>

    Common arguments:
       Commit-Queue=0  Commit-Queue-1  Commit-Queue+2  CQ+2
       'V+1 CQ+2'
       'AS=1 V=1'
    """

    COMMAND = "review"

    class _SetLabel(argparse.Action):
        """Argparse action for setting labels."""

        LABEL_MAP = {
            "AS": "Auto-Submit",
            "CQ": "Commit-Queue",
            "CR": "Code-Review",
            "V": "Verified",
        }

        def __call__(self, parser, namespace, values, option_string=None):
            labels = getattr(namespace, self.dest)
            for request in values.split():
                if "=" in request:
                    # Handle Verified=1 form.
                    short, value = request.split("=", 1)
                elif "+" in request:
                    # Handle Verified+1 form.
                    short, value = request.split("+", 1)
                elif "-" in request:
                    # Handle Verified-1 form.
                    short, value = request.split("-", 1)
                    value = "-%s" % (value,)
                else:
                    parser.error(
                        'Invalid label setting "%s". Must be Commit-Queue=1 or '
                        "CQ+1 or CR-1." % (request,)
                    )

                # Convert possible short label names like "V" to "Verified".
                label = self.LABEL_MAP.get(short)
                if not label:
                    label = short

                # We allow existing label requests to be overridden.
                labels[label] = value

    @classmethod
    def init_subparser(cls, parser):
        """Add arguments to this action's subparser."""
        parser.add_argument(
            "-m",
            "--msg",
            "--message",
            metavar="MESSAGE",
            help="Include a message",
        )
        parser.add_argument(
            "-l",
            "--label",
            dest="labels",
            action=cls._SetLabel,
            default={},
            help="Set a label with a value",
        )
        parser.add_argument(
            "--ready",
            default=None,
            action="store_true",
            help="Set CL status to ready-for-review",
        )
        parser.add_argument(
            "--wip",
            default=None,
            action="store_true",
            help="Set CL status to WIP",
        )
        parser.add_argument(
            "--reviewers",
            "--re",
            action="append",
            type="email",
            default=[],
            help="Reviewers to add/remove",
        )
        parser.add_argument(
            "--cc",
            action="append",
            type="email",
            default=[],
            help="People to add/remove in CC",
        )
        _ActionSimpleParallelCLs.init_subparser(parser)

    @staticmethod
    def _process_one(helper, cl, opts):
        """Use |helper| to process the single |cl|."""
        add_reviewers, remove_reviewers = process_add_remove_lists(
            opts.reviewers
        )
        add_cc, remove_cc = process_add_remove_lists(opts.cc)

        # Gerrit allows people to only be in one state: CC or Reviewer.  If a
        # person is in CC and you want to move them to reviewer, you can't
        # remove them from CC and add to reviewer, you have to change their
        # state.  Help users who do `--cc ~u@c --re u@c` by filtering out all
        # the remove requests if there is an add request too.  This doesn't
        # quite respect all the possible CLI option orders, but it's probably
        # good enough for now in practice.  For example, mixing of CC & reviewer
        # and adds & removes gets complicated.
        for add in add_cc:
            if add in remove_reviewers:
                remove_reviewers.remove(add)
        for add in add_reviewers:
            if add in remove_cc:
                remove_cc.remove(add)

        helper.SetReview(
            cl,
            msg=opts.msg,
            labels=opts.labels,
            dryrun=opts.dryrun,
            notify=opts.notify,
            reviewers=add_reviewers,
            cc=add_cc,
            remove_reviewers=remove_reviewers | remove_cc,
            ready=opts.ready,
            wip=opts.wip,
        )


class ActionAccount(_ActionSimpleParallelCLs):
    """Get user account information"""

    COMMAND = "account"
    USE_PAGER = True

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        parser.add_argument(
            "accounts",
            nargs="*",
            default=["self"],
            help="The accounts to query",
        )

    @classmethod
    def __call__(cls, opts):
        """Implement the action."""
        helper, _ = GetGerrit(opts)

        def print_one(header, data):
            print(f"### {header}")
            compact = opts.format is OutputFormat.JSON
            print(pformat.json(data, compact=compact).rstrip())

        def task(arg):
            detail = gob_util.FetchUrlJson(
                helper.host, f"accounts/{arg}/detail"
            )
            if not detail:
                print(f"{arg}: account not found")
            else:
                print_one("detail", detail)
                for field in (
                    "external.ids",
                    "groups",
                    "capabilities",
                    "preferences",
                    "sshkeys",
                    "gpgkeys",
                ):
                    data = gob_util.FetchUrlJson(
                        helper.host, f"accounts/{arg}/{field}"
                    )
                    print_one(field, data)

        _run_parallel_tasks(task, opts.jobs, *opts.accounts)


class ActionConfig(UserAction):
    """Manage the gerrit tool's own config file

    Gerrit may be customized via ~/.config/chromite/gerrit.cfg.
    It is an ini file like ~/.gitconfig.  See `man git-config` for basic format.

    # Set up subcommand aliases.
    [alias]
        common-search = search 'is:open project:something/i/care/about'
    """

    COMMAND = "config"

    @staticmethod
    def __call__(opts):
        """Implement the action."""
        # For now, this is a place holder for raising visibility for the config
        # file and its associated help text documentation.
        opts.parser.parse_args(["config", "--help"])


class ActionHelp(UserAction):
    """An alias to --help for CLI symmetry"""

    COMMAND = "help"
    USE_PAGER = True

    @staticmethod
    def init_subparser(parser):
        """Add arguments to this action's subparser."""
        parser.add_argument(
            "command", nargs="?", help="The command to display."
        )

    @staticmethod
    def __call__(opts):
        """Implement the action."""
        # Show global help.
        if not opts.command:
            opts.parser.print_help()
            return

        opts.parser.parse_args([opts.command, "--help"])


class ActionHelpAll(UserAction):
    """Show all actions help output at once."""

    COMMAND = "help-all"
    USE_PAGER = True

    @staticmethod
    def __call__(opts):
        """Implement the action."""
        first = True
        for action in _GetActions():
            if first:
                first = False
            else:
                print("\n\n")

            try:
                opts.parser.parse_args([action, "--help"])
            except SystemExit:
                pass


@memoize.Memoize
def _GetActions():
    """Get all the possible actions we support.

    Returns:
        An ordered dictionary mapping the user subcommand (e.g. "foo") to the
        function that implements that command (e.g. UserActFoo).
    """
    VALID_NAME = re.compile(r"^[a-z][a-z-]*[a-z]$")

    actions = {}
    for cls in globals().values():
        if (
            not inspect.isclass(cls)
            or not issubclass(cls, UserAction)
            or not getattr(cls, "COMMAND", None)
        ):
            continue

        # Sanity check names for devs adding new commands.  Should be quick.
        cmd = cls.COMMAND
        assert VALID_NAME.match(cmd), '"%s" must match [a-z-]+' % (cmd,)
        assert cmd not in actions, 'multiple "%s" commands found' % (cmd,)

        actions[cmd] = cls

    return collections.OrderedDict(sorted(actions.items()))


def _GetActionUsages():
    """Formats a one-line usage and doc message for each action."""
    actions = _GetActions()

    cmds = list(actions.keys())
    functions = list(actions.values())
    usages = [getattr(x, "usage", "") for x in functions]
    docs = [x.__doc__.splitlines()[0] for x in functions]

    cmd_indent = len(max(cmds, key=len))
    usage_indent = len(max(usages, key=len))
    return "\n".join(
        "  %-*s %-*s : %s" % (cmd_indent, cmd, usage_indent, usage, doc)
        for cmd, usage, doc in zip(cmds, usages, docs)
    )


def _AddCommonOptions(parser, subparser):
    """Add options that should work before & after the subcommand.

    Make it easy to do `gerrit --dry-run foo` and `gerrit foo --dry-run`.
    """
    parser.add_common_argument_to_group(
        subparser,
        "--ne",
        "--no-emails",
        dest="notify",
        default="ALL",
        action="store_const",
        const="NONE",
        help="Do not send e-mail notifications",
    )
    parser.add_common_argument_to_group(
        subparser,
        "-n",
        "--dry-run",
        dest="dryrun",
        default=False,
        action="store_true",
        help="Show what would be done, but do not make changes",
    )
    parser.add_common_argument_to_group(
        subparser,
        "-j",
        "--jobs",
        type=int,
        default=CONNECTION_LIMIT,
        help=(
            "Number of connections to run in parallel. "
            f"(default: {CONNECTION_LIMIT})"
        ),
    )


def GetBaseParser() -> commandline.ArgumentParser:
    """Returns the common parser (i.e. no subparsers added)."""
    description = """\
There is no support for doing line-by-line code review via the command line.
This helps you manage various bits and CL status.

For general Gerrit documentation, see:
  https://gerrit-review.googlesource.com/Documentation/
The Searching Changes page covers the search query syntax:
  https://gerrit-review.googlesource.com/Documentation/user-search.html

Example:
  $ gerrit todo              # List all the CLs that await your review.
  $ gerrit mine              # List all of your open CLs.
  $ gerrit inspect 28123     # Inspect CL 28123 on the public gerrit.
  $ gerrit inspect *28123    # Inspect CL 28123 on the internal gerrit.
  $ gerrit label-v 28123 1   # Mark CL 28123 as verified (+1).
  $ gerrit reviewers 28123 foo@chromium.org    # Add foo@ as a reviewer on CL \
28123.
  $ gerrit reviewers 28123 ~foo@chromium.org   # Remove foo@ as a reviewer on \
CL 28123.
Scripting:
  $ gerrit label-cq `gerrit --raw mine` 1      # Mark *ALL* of your public CLs \
with Commit-Queue=1.
  $ gerrit label-cq `gerrit --raw -i mine` 1   # Mark *ALL* of your internal \
CLs with Commit-Queue=1.
  $ gerrit --json search 'attention:self'      # Dump all pending CLs in JSON.

Actions:
"""
    description += _GetActionUsages()

    site_params = config_lib.GetSiteParams()
    parser = commandline.ArgumentParser(
        description=description,
        default_log_level="notice",
        epilog="For subcommand help, use `gerrit help <command>`.",
    )

    group = parser.add_argument_group("Server options")
    group.add_argument(
        "-i",
        "--internal",
        dest="gob",
        action="store_const",
        default=site_params.EXTERNAL_GOB_INSTANCE,
        const=site_params.INTERNAL_GOB_INSTANCE,
        help="Query internal Chrome Gerrit instance",
    )
    group.add_argument(
        "-g",
        "--gob",
        default=site_params.EXTERNAL_GOB_INSTANCE,
        help="Gerrit (on borg) instance to query (default: %(default)s)",
    )

    group = parser.add_argument_group("CL options")
    _AddCommonOptions(parser, group)

    group = parser.add_mutually_exclusive_group()
    parser.set_defaults(format=OutputFormat.AUTO)
    group.add_argument(
        "--format",
        action="enum",
        enum=OutputFormat,
        help="Output format to use.",
    )
    group.add_argument(
        "--raw",
        action="store_const",
        dest="format",
        const=OutputFormat.RAW,
        help="Alias for --format=raw.",
    )
    group.add_argument(
        "--json",
        action="store_const",
        dest="format",
        const=OutputFormat.JSON,
        help="Alias for --format=json.",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--pager",
        action="store_true",
        default=sys.stdout.isatty(),
        help="Enable pager.",
    )
    group.add_argument(
        "--no-pager", action="store_false", dest="pager", help="Disable pager."
    )
    return parser


def GetParser(
    parser: commandline.ArgumentParser = None,
) -> commandline.ArgumentParser:
    """Returns the full parser to use for this module."""
    if parser is None:
        parser = GetBaseParser()

    actions = _GetActions()

    # Subparsers are required by default under Python 2.  Python 3 changed to
    # not required, but didn't include a required option until 3.7.  Setting
    # the required member works in all versions (and setting dest name).
    subparsers = parser.add_subparsers(dest="action")
    subparsers.required = True
    for cmd, cls in actions.items():
        # Format the full docstring by removing the file level indentation.
        description = re.sub(r"^  ", "", cls.__doc__, flags=re.M)
        subparser = subparsers.add_parser(cmd, description=description)
        _AddCommonOptions(parser, subparser)
        cls.init_subparser(subparser)

    return parser


def start_pager():
    """Re-spawn ourselves attached to a pager."""
    pager = os.environ.get("PAGER", "less")
    os.environ.setdefault("LESS", "FRX")
    with subprocess.Popen(
        # sys.argv can have some edge cases: we may not necessarily use
        # sys.executable if the script is executed as "python path/to/script".
        # If we upgrade to Python 3.10+, this should be changed to sys.orig_argv
        # for full accuracy.
        sys.argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={"GERRIT_RESPAWN_FOR_PAGER": "1", **os.environ},
    ) as gerrit_proc:
        with subprocess.Popen(
            pager,
            shell=True,
            stdin=gerrit_proc.stdout,
        ) as pager_proc:
            # Send SIGINT to just the gerrit process, not the pager too.
            def _sighandler(signum, _frame):
                gerrit_proc.send_signal(signum)

            signal.signal(signal.SIGINT, _sighandler)

            pager_proc.communicate()
            # If the pager exits, and the gerrit process is still running, we
            # must terminate it.
            if gerrit_proc.poll() is None:
                gerrit_proc.terminate()
            sys.exit(gerrit_proc.wait())


def main(argv):
    base_parser = GetBaseParser()
    opts, subargs = base_parser.parse_known_args(argv)

    config = Config()
    if subargs:
        # If the action is an alias to an expanded value, we need to mutate the
        # argv and reparse things.
        action = config.expand_alias(subargs[0])
        if action != subargs[0]:
            pos = argv.index(subargs[0])
            argv = argv[:pos] + action + argv[pos + 1 :]

    parser = GetParser(parser=base_parser)
    opts = parser.parse_args(argv)

    # If we're running as a re-spawn for the pager, from this point on
    # we'll pretend we're attached to a TTY.  This will give us colored
    # output when requested.
    if os.environ.pop("GERRIT_RESPAWN_FOR_PAGER", None) is not None:
        opts.pager = False
        sys.stdout.isatty = lambda: True

    # In case the action wants to throw a parser error.
    opts.parser = parser

    # A cache of gerrit helpers we'll load on demand.
    opts.gerrit = {}

    if opts.format is OutputFormat.AUTO:
        if sys.stdout.isatty():
            opts.format = OutputFormat.PRETTY
        else:
            opts.format = OutputFormat.RAW

    opts.Freeze()

    # pylint: disable=global-statement
    global COLOR
    COLOR = terminal.Color(enabled=opts.color)

    # Now look up the requested user action and run it.
    actions = _GetActions()
    action_class = actions[opts.action]
    if action_class.USE_PAGER and opts.pager:
        start_pager()
    obj = action_class()
    try:
        obj(opts)
    except (
        cros_build_lib.RunCommandError,
        gerrit.GerritException,
        gob_util.GOBError,
    ) as e:
        cros_build_lib.Die(e)
