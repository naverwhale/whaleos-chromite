# Copyright 2013 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for requesting information for a gerrit server via https.

https://gerrit-review.googlesource.com/Documentation/rest-api.html
"""

import base64
import datetime
import html.parser
import http.client
import http.cookiejar
import json
import logging
import os
import re
import socket
import sys
from typing import Any, Dict, Optional, Tuple, Union
import urllib.parse
import urllib.request
import warnings

from chromite.third_party import httplib2
from chromite.third_party.oauth2client import gce

from chromite.lib import auth
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import git
from chromite.lib import retry_util
from chromite.lib import timeout_util
from chromite.utils import memoize


_GAE_VERSION = "GAE_VERSION"


class ErrorParser(html.parser.HTMLParser):
    """Class to parse GOB error message reported as HTML.

    Only data inside <div id='af-error-container'> section is retrieved from the
    GOB error message. Retrieved data is processed as follows:

    - newlines are removed
    - each <br> tag is replaced with '\n'
    - each <p> tag is replaced with '\n\n'
    """

    def __init__(self):
        html.parser.HTMLParser.__init__(self)
        self.in_div = False
        self.err_data = ""

    def handle_starttag(self, tag, attrs):
        tag_id = [x[1] for x in attrs if x[0] == "id"]
        if tag == "div" and tag_id and tag_id[0] == "af-error-container":
            self.in_div = True
            return

        if self.in_div:
            if tag == "p":
                self.err_data += "\n\n"
                return

            if tag == "br":
                self.err_data += "\n"
                return

    def handle_endtag(self, tag):
        if tag == "div":
            self.in_div = False

    def handle_data(self, data):
        if self.in_div:
            self.err_data += data.replace("\n", "")

    def ParsedDiv(self):
        return self.err_data.strip()

    def error(self, message):
        # Pylint correctly flags a missing abstract method, but the error is in
        # Python itself.  We can delete this method once we move to Python
        # 3.10+. https://bugs.python.org/issue31844
        pass


@memoize.Memoize
def _GetAppCredentials():
    """Returns the singleton Appengine credentials for gerrit code review."""
    return gce.AppAssertionCredentials(
        scope="https://www.googleapis.com/auth/gerritcodereview"
    )


TRY_LIMIT = 11
SLEEP = 0.5
REQUEST_TIMEOUT_SECONDS = 120  # 2 minutes.

# Controls the transport protocol used to communicate with Gerrit servers using
# git. This is parameterized primarily to enable cros_test_lib.GerritTestCase.
GIT_PROTOCOL = "https"

# The GOB conflict errors which could be ignorable.
GOB_CONFLICT_ERRORS = (
    rb"change is closed",
    rb"Cannot reduce vote on labels for closed change",
)

GOB_CONFLICT_ERRORS_RE = re.compile(
    rb"|".join(GOB_CONFLICT_ERRORS), re.IGNORECASE
)

GOB_ERROR_REASON_CLOSED_CHANGE = "CLOSED CHANGE"


class GOBError(Exception):
    """Exception class for errors communicating with the GOB service."""

    def __init__(self, http_status=None, reason=None):
        self.http_status = http_status
        self.reason = reason

        message = ""
        if http_status is not None:
            message += "(http_status): %d" % (http_status,)
        if reason is not None:
            message += "(reason): %s" % (reason,)
        if not message:
            message = "Unknown error"

        super().__init__(message)


class InternalGOBError(GOBError):
    """Exception class for GOB errors with status >= 500"""


def _QueryString(param_dict, first_param=None):
    """Encodes query parameters in the key:val[+key:val...] format.

    Format specified here:
    https://gerrit-review.googlesource.com/Documentation/rest-api-changes.html#list-changes
    """
    q = [urllib.parse.quote(first_param)] if first_param else []
    q.extend(["%s:%s" % (key, val) for key, val in param_dict.items()])
    return "+".join(q)


def GetCookies(host, path, cookie_paths=None):
    """Returns cookies that should be set on a request.

    Used by CreateHttpReq for any requests that do not already specify a Cookie
    header. All requests made by this library are HTTPS.

    Args:
        host: The hostname of the Gerrit service.
        path: The path on the Gerrit service, already including /a/ if
            applicable.
        cookie_paths: Files to look in for cookies. Defaults to looking in the
            standard places where GoB places cookies.

    Returns:
        A dict of cookie name to value, with no URL encoding applied.
    """
    cookies = {}
    if cookie_paths is None:
        cookie_paths = (constants.GOB_COOKIE_PATH, constants.GITCOOKIES_PATH)
    for cookie_path in cookie_paths:
        if os.path.isfile(cookie_path):
            with open(cookie_path, encoding="utf-8") as f:
                for line in f:
                    fields = line.strip().split("\t")
                    if line.strip().startswith("#") or len(fields) != 7:
                        continue
                    domain, xpath, key, value = (
                        fields[0],
                        fields[2],
                        fields[5],
                        fields[6],
                    )
                    if http.cookiejar.domain_match(
                        host, domain
                    ) and path.startswith(xpath):
                        cookies[key] = value
    return cookies


def CreateHttpReq(
    host: str,
    path: str,
    reqtype: Optional[str] = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Union[bytes, str]] = None,
) -> urllib.request.Request:
    """Returns a https connection request object to a gerrit service."""
    path = "/a/" + path.lstrip("/")
    headers = headers or {}
    if _InAppengine():
        # TODO(phobbs) how can we choose to only run this on GCE / AppEngine?
        credentials = _GetAppCredentials()
        try:
            headers.setdefault(
                "Authorization",
                "Bearer %s" % credentials.get_access_token().access_token,
            )
        except gce.HttpAccessTokenRefreshError as e:
            logging.debug("Failed to retrieve gce access token: %s", e)
        # Not in an Appengine or GCE environment.
        except httplib2.ServerNotFoundError:
            pass

    cookies = GetCookies(host, path)
    if "Cookie" not in headers and cookies:
        headers["Cookie"] = "; ".join(
            "%s=%s" % (n, v) for n, v in cookies.items()
        )
    elif "Authorization" not in headers:
        try:
            git_creds = auth.GitCreds()
        except auth.AccessTokenError:
            git_creds = None
        if git_creds:
            headers.setdefault("Authorization", "Bearer %s" % git_creds)
        else:
            logging.debug(
                "No gitcookies file, Appengine credentials, or LUCI git creds "
                "found."
            )

    if "User-Agent" not in headers:
        # We may not be in a git repository.
        try:
            version = git.GetGitRepoRevision(
                os.path.dirname(os.path.realpath(__file__))
            )
        except cros_build_lib.RunCommandError:
            version = "unknown"
        headers["User-Agent"] = " ".join(
            (
                "chromite.lib.gob_util",
                os.path.basename(sys.argv[0]),
                version,
            )
        )

    if body:
        body = json.JSONEncoder().encode(body).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("%s https://%s%s", reqtype, host, path)
        for key, val in headers.items():
            if key.lower() in ("authorization", "cookie"):
                val = "HIDDEN"
            logging.debug("%s: %s", key, val)
        if body:
            logging.debug(body)
    return urllib.request.Request(
        f"https://{host}{path}", data=body, headers=headers, method=reqtype
    )


def _InAppengine():
    """Returns whether we're in the Appengine environment."""
    return _GAE_VERSION in os.environ


def FetchUrl(
    host,
    path,
    reqtype="GET",
    headers=None,
    body=None,
    expect: Union[int, Tuple[int]] = 200,
    ignore_404=True,
):
    """Fetches the http response from the specified URL.

    Args:
        host: The hostname of the Gerrit service.
        path: The path on the Gerrit service. This will be prefixed with '/a'
            automatically.
        reqtype: The request type. Can be GET or POST.
        headers: A mapping of extra HTTP headers to pass in with the request.
        body: A string of data to send after the headers are finished.
        expect: The status code(s) to expect as "success".  For some requests,
            Gerrit will return 204 to confirm proper processing of the request.
        ignore_404: For many requests, gerrit-on-borg will return 404 if the
            request doesn't match the database contents.  In most such cases, we
            want the API to return None rather than raise an Exception.

    Returns:
        The connection's reply, as bytes.
    """
    if isinstance(expect, int):
        expect = (expect,)

    @timeout_util.TimeoutDecorator(REQUEST_TIMEOUT_SECONDS)
    def _FetchUrlHelper():
        err_prefix = (
            f"A transient error occurred while querying {host}/{path}\n"
        )
        try:
            _request = CreateHttpReq(
                host, path, reqtype=reqtype, headers=headers, body=body
            )
            with urllib.request.urlopen(_request) as response:
                return _ProcessResponse(response, err_prefix)
        except urllib.error.HTTPError as e:
            # Any non-HTTP/2xx status is thrown as an exception even though it's
            # the response.  We handle the actual HTTP codes below.
            return _ProcessResponse(e, err_prefix)
        except socket.error as ex:
            logging.warning("%s%s", err_prefix, str(ex))
            raise

    def _ProcessResponse(
        response: http.client.HTTPResponse, err_prefix: str
    ) -> bytes:
        """Process the Response object.

        Args:
            response: the url response object to parse.
            err_prefix: the prefix to use.

        Returns:
            The server's reply, as bytes.

        Raises:
            GOBError with the failure status code and reason.
        """
        # Normal/good responses.
        response_body = response.read()
        if response.status == 404 and ignore_404:
            return b""
        elif response.status in expect:
            return response_body

        # Bad responses.
        logging.debug("response msg:\n%s", response.msg)
        http_version = "HTTP/%s" % ("1.1" if response.version == 11 else "1.0")
        msg = "%s %s %s\n%s %d %s\nResponse body: %r" % (
            reqtype,
            f"https://{host}/{path}",
            http_version,
            http_version,
            response.status,
            response.reason,
            response_body,
        )

        # Ones we can retry.
        if response.status >= 500:
            # A status >=500 is assumed to be a possible transient error; retry.
            logging.warning("%s%s", err_prefix, msg)
            raise InternalGOBError(
                http_status=response.status, reason=response.reason
            )

        # Ones we cannot retry.
        home = os.environ.get("HOME", "~")
        url = "https://%s/new-password" % host
        if response.status in (302, 303, 307):
            err_prefix = (
                "Redirect found; missing/bad %s/.gitcookies credentials or "
                "permissions (0600)?\n See %s" % (home, url)
            )
        elif response.status in (400,):
            err_prefix = (
                "Permission error; talk to the admins of the GoB instance"
            )
        elif response.status in (401,):
            err_prefix = (
                "Authorization error; missing/bad %s/.gitcookies "
                "credentials or permissions (0600)?\n See %s" % (home, url)
            )
        elif response.status in (422,):
            err_prefix = "Bad request body?"

        logging.warning(err_prefix)

        # If GOB output contained expected error message, reduce log visibility
        # of raw GOB output reported below.
        ep = ErrorParser()
        ep.feed(response_body.decode("utf-8"))
        ep.close()
        parsed_div = ep.ParsedDiv()
        if parsed_div:
            logging.warning("GOB Error:\n%s", parsed_div)
            logging_function = logging.debug
        else:
            logging_function = logging.warning

        logging_function(msg)
        if response.status >= 400:
            # The 'X-ErrorId' header is set only on >= 400 response code.
            logging_function("X-ErrorId: %s", response.getheader("X-ErrorId"))

        if response.status == http.client.CONFLICT:
            # 409 conflict
            if GOB_CONFLICT_ERRORS_RE.search(response_body):
                raise GOBError(
                    http_status=response.status,
                    reason=GOB_ERROR_REASON_CLOSED_CHANGE,
                )
            else:
                raise GOBError(
                    http_status=response.status, reason=response.reason
                )
        else:
            raise GOBError(http_status=response.status, reason=response.reason)

    return retry_util.RetryException(
        (socket.error, InternalGOBError, timeout_util.TimeoutError),
        TRY_LIMIT,
        _FetchUrlHelper,
        sleep=SLEEP,
        backoff_factor=2,
    )


def FetchUrlJson(*args, **kwargs):
    """Fetch the specified URL and parse it as JSON.

    See FetchUrl for arguments.
    """
    fh = FetchUrl(*args, **kwargs)

    # In case ignore_404 is True, we want to return None instead of
    # raising an exception.
    if not fh:
        return None

    # The first line of the response should always be: )]}'
    if not fh.startswith(b")]}'"):
        raise GOBError(
            http_status=200, reason="Unexpected json output: %r" % fh
        )

    _, _, json_data = fh.partition(b"\n")
    return json.loads(json_data)


def QueryChanges(
    host, param_dict, first_param=None, limit=None, o_params=None, start=None
):
    """Queries a gerrit-on-borg server for changes matching query terms.

    Args:
        host: The Gerrit server hostname.
        param_dict: A dictionary of search parameters, as documented here:
            https://gerrit-review.googlesource.com/Documentation/user-search.html
        first_param: A change identifier
        limit: Maximum number of results to return.
        o_params: A list of additional output specifiers, as documented here:
            https://gerrit-review.googlesource.com/Documentation/rest-api-changes.html#list-changes
        start: Offset in the result set to start at.

    Returns:
        A list of json-decoded query results.
    """
    # Note that no attempt is made to escape special characters; YMMV.
    if not param_dict and not first_param:
        raise RuntimeError("QueryChanges requires search parameters")
    path = "changes/?q=%s" % _QueryString(param_dict, first_param)
    if start:
        path = "%s&S=%d" % (path, start)
    if limit:
        path = "%s&n=%d" % (path, limit)
    if o_params:
        path = "%s&%s" % (path, "&".join(["o=%s" % p for p in o_params]))
    # Don't ignore 404; a query should always return a list, even if it's empty.
    return FetchUrlJson(host, path, ignore_404=False)


def MultiQueryChanges(
    host, param_dict, change_list, limit=None, o_params=None, start=None
):
    """Initiate a query composed of multiple sets of query parameters."""
    if not change_list:
        raise RuntimeError(
            "MultiQueryChanges requires a list of change numbers/id's"
        )
    q = ["q=%s" % "+OR+".join(urllib.parse.quote(str(x)) for x in change_list)]
    if param_dict:
        q.append(_QueryString(param_dict))
    if limit:
        q.append("n=%d" % limit)
    if start:
        q.append("S=%s" % start)
    if o_params:
        q.extend(["o=%s" % p for p in o_params])
    path = "changes/?%s" % "&".join(q)
    try:
        result = FetchUrlJson(host, path, ignore_404=False)
    except GOBError as e:
        msg = "%s:\n%s" % (e, path)
        raise GOBError(http_status=e.http_status, reason=msg)
    return result


def GetGerritFetchUrl(host):
    """Returns URL of a gerrit instance to fetch from for gerrit |host| name."""
    return "https://%s/" % host


def GetChangePageUrl(host, change_number):
    """Given a gerrit host name and change number, return change page url."""
    return "https://%s/#/c/%d/" % (host, change_number)


def _GetChangePath(change):
    """Given a change id, return a path prefix for the change."""
    return "changes/%s" % str(change).replace("/", "%2F")


def GetChangeUrl(host, change):
    """Given a gerrit host name and change id, return an url for the change."""
    return "https://%s/a/%s" % (host, _GetChangePath(change))


def GetChange(host, change):
    """Query a gerrit server for information about a single change."""
    return FetchUrlJson(host, _GetChangePath(change))


def GetChangeReview(host, change, revision=None):
    """Get the current review information for a change."""
    if revision is None:
        revision = "current"
    path = "%s/revisions/%s/review" % (_GetChangePath(change), revision)
    return FetchUrlJson(host, path)


def GetChangeCommit(host, change, revision=None):
    """Get the current review information for a change."""
    if revision is None:
        revision = "current"
    path = "%s/revisions/%s/commit" % (_GetChangePath(change), revision)
    return FetchUrlJson(host, path)


def GetChangeCurrentRevision(host, change):
    """Get information about the latest revision for a given change."""
    jmsg = GetChangeReview(host, change)
    if jmsg:
        return jmsg.get("current_revision")


def GetChangeDetail(host, change, o_params=None):
    """Query a gerrit server for extended information about a single change."""
    path = "%s/detail" % _GetChangePath(change)
    if o_params:
        path = "%s?%s" % (path, "&".join(["o=%s" % p for p in o_params]))
    return FetchUrlJson(host, path)


def GetChangeMergeable(host, change, revision=None) -> Optional[Dict[str, Any]]:
    """Query a gerrit server for "mergeable" state."""
    if revision is None:
        revision = "current"
    path = "%s/revisions/%s/mergeable" % (_GetChangePath(change), revision)
    return FetchUrlJson(host, path)


def GetRelatedChanges(host, change, revision=None) -> Optional[Dict[str, Any]]:
    """Get changes that depend on or are dependencies for a given change.

    Args:
        host: The Gerrit host to interact with.
        change: The Gerrit change ID.
        revision: The Gerrit change revision, default is "current".

    Returns:
        A JSON response dict repesenting a RelatedChangesInfo entity.
    """
    if revision is None:
        revision = "current"

    path = "%s/revisions/%s/related" % (_GetChangePath(change), revision)

    return FetchUrlJson(host, path)


def GetChangeReviewers(host, change):
    """Get information about all reviewers attached to a change.

    Args:
        host: The Gerrit host to interact with.
        change: The Gerrit change ID.
    """
    warnings.warn("GetChangeReviewers is deprecated; use GetReviewers instead.")
    GetReviewers(host, change)


def CreateChange(
    host: str, project: str, branch: str, subject: str, publish: bool
) -> Dict[str, Any]:
    """Creates an empty change.

    Args:
        host: The Gerrit host to interact with.
        project: The name of the Gerrit project for the change.
        branch: Branch for the change.
        subject: Initial commit message for the change.
        publish: If True, will publish the CL after uploading. Stays in WIP mode
            otherwise.

    Returns:
        A JSON response dict.
    """
    path = "changes/"
    body = {"project": project, "branch": branch, "subject": subject}
    if not publish:
        body["work_in_progress"] = "true"
        body["notify"] = "NONE"
    return FetchUrlJson(
        host,
        path,
        body=body,
        reqtype="POST",
        expect=(200, 201),
        ignore_404=False,
    )


def ChangeEdit(
    host: str, change: str, filepath: str, contents: str
) -> Dict[str, Any]:
    """Attaches file modifications to an open change.

    Args:
        host: The Gerrit host to interact with.
        change: A Gerrit change number.
        filepath: Path of the file in the repo to modify.
        contents: New contents of the file.

    Returns:
        A JSON response dict.
    """
    path = "%s/edit/%s" % (
        _GetChangePath(change),
        urllib.parse.quote(filepath, ""),
    )
    contents = contents.encode("utf-8")  # string -> bytes
    contents = base64.b64encode(contents)  # bytes -> bytes
    contents = contents.decode("utf-8")  # bytes -> string
    body = {"binary_content": "data:text/plain;base64,%s" % contents}
    return FetchUrlJson(host, path, body=body, reqtype="PUT", expect=204)


def PublishChangeEdit(host: str, change: str) -> Dict[str, Any]:
    """Publishes any open edits in a change.

    Args:
        host: The Gerrit host to interact with.
        change: A Gerrit change number.

    Returns:
        A JSON response dict.
    """
    path = "%s/edit:publish" % _GetChangePath(change)
    body = {"notify": "NONE"}
    return FetchUrlJson(host, path, body=body, reqtype="POST", expect=204)


def ReviewedChange(host, change):
    """Mark a gerrit change as reviewed."""
    path = "%s/reviewed" % _GetChangePath(change)
    return FetchUrlJson(host, path, reqtype="PUT", ignore_404=False)


def UnreviewedChange(host, change):
    """Mark a gerrit change as unreviewed."""
    path = "%s/unreviewed" % _GetChangePath(change)
    return FetchUrlJson(host, path, reqtype="PUT", ignore_404=False)


def IgnoreChange(host, change):
    """Ignore a gerrit change."""
    path = "%s/ignore" % _GetChangePath(change)
    return FetchUrlJson(host, path, reqtype="PUT", ignore_404=False)


def UnignoreChange(host, change):
    """Unignore a gerrit change."""
    path = "%s/unignore" % _GetChangePath(change)
    return FetchUrlJson(host, path, reqtype="PUT", ignore_404=False)


def AbandonChange(host, change, msg="", notify=None):
    """Abandon a gerrit change."""
    path = "%s/abandon" % _GetChangePath(change)
    body = {"message": msg}
    if notify is not None:
        body["notify"] = notify
    return FetchUrlJson(host, path, reqtype="POST", body=body, ignore_404=False)


def RestoreChange(host, change, msg=""):
    """Restore a previously abandoned change."""
    path = "%s/restore" % _GetChangePath(change)
    body = {"message": msg}
    return FetchUrlJson(host, path, reqtype="POST", body=body, ignore_404=False)


def Delete(host, change):
    """Delete a gerrit change."""
    path = _GetChangePath(change)
    FetchUrl(host, path, reqtype="DELETE", expect=204, ignore_404=False)


def CherryPick(
    host,
    change,
    branch,
    rev="current",
    msg="",
    allow_conflicts: bool = False,
    notify=None,
):
    """Cherry pick a change to a branch."""
    path = "%s/revisions/%s/cherrypick" % (_GetChangePath(change), rev)
    body = {
        "destination": branch,
        "message": msg,
        "allow_conflicts": allow_conflicts,
    }
    if notify is not None:
        body["notify"] = notify
    return FetchUrlJson(host, path, reqtype="POST", body=body)


def SubmitChange(host, change, revision=None, wait_for_merge=True, notify=None):
    """Submits a gerrit change via Gerrit."""
    if revision is None:
        revision = "current"
    path = "%s/revisions/%s/submit" % (_GetChangePath(change), revision)
    body = {"wait_for_merge": wait_for_merge}
    if notify is not None:
        body["notify"] = notify
    return FetchUrlJson(host, path, reqtype="POST", body=body, ignore_404=False)


def CheckChange(host, change, sha1=None):
    """Performs consistency checks on the change, and fixes inconsistencies.

    This is useful for forcing Gerrit to check whether a change has already been
    merged into the git repo. Namely, if |sha1| is provided and the change is in
    'NEW' status, Gerrit will check if a change with that |sha1| is in the repo
    and mark the change as 'MERGED' if it exists.

    Args:
        host: The Gerrit host to interact with.
        change: The Gerrit change ID.
        sha1: An optional hint of the commit's SHA1 in Git.
    """
    path = "%s/check" % (_GetChangePath(change),)
    if sha1:
        body, headers = {"expect_merged_as": sha1}, {}
    else:
        body, headers = {}, {"Content-Length": "0"}

    return FetchUrlJson(
        host, path, reqtype="POST", body=body, ignore_404=False, headers=headers
    )


def MarkPrivate(host, change):
    """Marks the given CL as private.

    Args:
        host: The gob host to interact with.
        change: CL number on the given host.
    """
    path = "%s/private" % _GetChangePath(change)
    try:
        FetchUrlJson(host, path, reqtype="POST", ignore_404=False)
    except GOBError as e:
        # 201: created -- change was successfully marked private.
        if e.http_status != 201:
            raise
    else:
        raise GOBError(
            http_status=200,
            reason="Change was already marked private",
        )


def MarkNotPrivate(host, change):
    """Sets the private bit on given CL to False.

    Args:
        host: The gob host to interact with.
        change: CL number on the given host.
    """
    path = "%s/private.delete" % _GetChangePath(change)
    try:
        FetchUrlJson(host, path, reqtype="POST", expect=204, ignore_404=False)
    except GOBError as e:
        if e.http_status == 409:
            raise GOBError(
                http_status=e.http_status,
                reason="Change was already marked not private",
            )
        else:
            raise


def MarkWorkInProgress(host, change, msg=""):
    """Marks the given CL as Work-In-Progress.

    Args:
        host: The gob host to interact with.
        change: CL number on the given host.
        msg: Message to post together with the action.
    """
    path = "%s/wip" % _GetChangePath(change)
    body = {"message": msg}
    return FetchUrlJson(host, path, reqtype="POST", body=body, ignore_404=False)


def MarkReadyForReview(host, change, msg=""):
    """Marks the given CL as Ready-For-Review.

    Args:
        host: The gob host to interact with.
        change: CL number on the given host.
        msg: Message to post together with the action.
    """
    path = "%s/ready" % _GetChangePath(change)
    body = {"message": msg}
    return FetchUrlJson(host, path, reqtype="POST", body=body, ignore_404=False)


def GetAttentionSet(host: str, change: str) -> Optional[Dict[str, Any]]:
    """Get information about the attention set of a change.

    Args:
        host: The Gerrit host to interact with.
        change: The Gerrit change ID.

    Returns:
        A JSON response dict.
    """
    path = "%s/attention" % _GetChangePath(change)
    return FetchUrlJson(host, path)


def AddAttentionSet(
    host: str, change: str, add: Tuple[str, ...], reason: str, notify: str = ""
) -> Optional[Dict[str, Any]]:
    """Add users to the attention set of a change."""
    if not add:
        return
    body = {}
    body["reason"] = reason
    if notify:
        body["notify"] = notify
    path = "%s/attention" % _GetChangePath(change)
    for r in add:
        body["user"] = r
        jmsg = FetchUrlJson(
            host, path, reqtype="POST", body=body, ignore_404=False
        )
    # Return the last response. We've run through at least one request if we got
    # here.
    return jmsg


def RemoveAttentionSet(
    host: str,
    change: str,
    remove: Tuple[str, ...],
    reason: str,
    notify: str = "",
):
    """Remove users from the attention set of a change."""
    if not remove:
        return
    body = {}
    body["reason"] = reason
    if notify:
        body["notify"] = notify
    for r in remove:
        path = "%s/attention/%s/delete" % (_GetChangePath(change), r)
        FetchUrl(host, path, reqtype="POST", body=body, expect=204)


def GetReviewers(host, change):
    """Get information about all reviewers attached to a change.

    Args:
        host: The Gerrit host to interact with.
        change: The Gerrit change ID.
    """
    path = "%s/reviewers" % _GetChangePath(change)
    return FetchUrlJson(host, path)


def AddReviewers(host, change, add=None, notify=None):
    """Add reviewers to a change."""
    if not add:
        return
    if isinstance(add, str):
        add = (add,)
    body = {}
    if notify:
        body["notify"] = notify
    path = "%s/reviewers" % _GetChangePath(change)
    for r in add:
        body["reviewer"] = r
        jmsg = FetchUrlJson(
            host, path, reqtype="POST", body=body, ignore_404=False
        )
    return jmsg


def RemoveReviewers(host, change, remove=None, notify=None):
    """Remove reviewers from a change."""
    if not remove:
        return
    if isinstance(remove, str):
        remove = (remove,)
    body = {}
    if notify:
        body["notify"] = notify
    for r in remove:
        path = "%s/reviewers/%s/delete" % (_GetChangePath(change), r)
        FetchUrl(host, path, reqtype="POST", body=body, expect=204)


def SetReview(
    host,
    change,
    revision=None,
    msg=None,
    labels=None,
    notify=None,
    reviewers=None,
    cc=None,
    remove_reviewers=None,
    ready=None,
    wip=None,
):
    """Set labels and/or add a message to a code review."""
    if revision is None:
        revision = "current"
    # Ignore 'notify' on purpose - it's not empty by default in the caller.
    if not any((msg, labels, reviewers, cc, ready, wip)):
        return
    path = "%s/revisions/%s/review" % (_GetChangePath(change), revision)
    body = {"reviewers": []}
    if msg:
        body["message"] = msg
    if labels:
        body["labels"] = labels
    if notify:
        body["notify"] = notify
    if reviewers:
        body["reviewers"].extend({"reviewer": x} for x in reviewers)
    if cc:
        body["reviewers"].extend({"reviewer": x, "state": "CC"} for x in cc)
    if remove_reviewers:
        body["reviewers"].extend(
            {"reviewer": x, "state": "REMOVED"} for x in remove_reviewers
        )
    if ready is not None:
        body["ready"] = ready
    if wip is not None:
        body["work_in_progress"] = wip
    response = FetchUrlJson(host, path, reqtype="POST", body=body)
    if response is None:
        raise GOBError(
            http_status=404, reason="CL %s not found in %s" % (change, host)
        )
    if labels:
        for key, val in labels.items():
            if (
                "labels" not in response
                or key not in response["labels"]
                or int(response["labels"][key] != int(val))
            ):
                raise GOBError(
                    http_status=200,
                    reason='Unable to set "%s" label on change %s.'
                    % (key, change),
                )


def SetTopic(host, change, topic):
    """Set |topic| for a change. If |topic| is empty, it will be deleted"""
    path = "%s/topic" % _GetChangePath(change)
    body = {"topic": topic}
    return FetchUrlJson(host, path, reqtype="PUT", body=body, ignore_404=False)


def SetHashtags(host, change, add, remove):
    """Adds and / or removes hashtags from a change.

    Args:
        host: Hostname (without protocol prefix) of the gerrit server.
        change: A gerrit change number.
        add: a list of hashtags to be added.
        remove: a list of hashtags to be removed.
    """
    path = "%s/hashtags" % _GetChangePath(change)
    return FetchUrlJson(
        host,
        path,
        reqtype="POST",
        body={"add": add, "remove": remove},
        ignore_404=False,
    )


def ResetReviewLabels(
    host, change, label, value="0", revision=None, message=None, notify=None
):
    """Reset the value of a given label for all reviewers on a change."""
    if revision is None:
        revision = "current"
    # This is tricky when working on the "current" revision, because there's
    # always the risk that the "current" revision will change in between API
    # calls.  So, the code dereferences the "current" revision down to a literal
    # sha1 at the beginning and uses it for all subsequent calls.  As a quick
    # check, the "current" revision is dereferenced again at the end, and if it
    # differs from the previous "current" revision, an exception is raised.
    current = revision == "current"
    jmsg = GetChangeDetail(
        host, change, o_params=["CURRENT_REVISION", "CURRENT_COMMIT"]
    )
    if current:
        revision = jmsg["current_revision"]
    value = str(value)
    path = "%s/revisions/%s/review" % (_GetChangePath(change), revision)
    message = message or (
        "%s label set to %s programmatically by chromite." % (label, value)
    )
    for review in jmsg.get("labels", {}).get(label, {}).get("all", []):
        if str(review.get("value", value)) != value:
            body = {
                "message": message,
                "labels": {label: value},
                "on_behalf_of": review["_account_id"],
            }
            if notify:
                body["notify"] = notify
            response = FetchUrlJson(host, path, reqtype="POST", body=body)
            if str(response["labels"][label]) != value:
                username = review.get("email", jmsg.get("name", ""))
                raise GOBError(
                    http_status=200,
                    reason='Unable to set %s label for user "%s" on change %s.'
                    % (label, username, change),
                )
    if current:
        new_revision = GetChangeCurrentRevision(host, change)
        if not new_revision:
            raise GOBError(
                http_status=200,
                reason='Could not get review information for change "%s"'
                % change,
            )
        elif new_revision != revision:
            raise GOBError(
                http_status=200,
                reason=f'While resetting labels on change "{change}", a new '
                "patchset was uploaded.",
            )


def GetTipOfTrunkRevision(git_url):
    """Returns the current git revision on the default branch."""
    parsed_url = urllib.parse.urlparse(git_url)
    path = parsed_url[2].rstrip("/") + "/+log/HEAD?n=1&format=JSON"
    j = FetchUrlJson(parsed_url[1], path, ignore_404=False)
    if not j:
        raise GOBError(
            reason="Could not find revision information from %s" % git_url
        )
    try:
        return j["log"][0]["commit"]
    except (IndexError, KeyError, TypeError):
        msg = (
            "The json returned by https://%s%s has an unfamiliar structure:\n"
            "%s\n" % (parsed_url[1], path, j)
        )
        raise GOBError(reason=msg)


def GetFileContentsOnHead(git_url: str, filepath: str) -> str:
    """Returns the current contents of a file on the default branch.

    Retrieves the contents from Gitiles via its API, not Gerrit's.

    Args:
        git_url: URL for the repository to get the file contents from.
        filepath: Path of the file in the repository.

    Returns:
        The contents of the file as a string.
    """
    return GetFileContents(git_url, filepath, ref="HEAD")


def GetFileContents(git_url: str, filepath: str, ref="HEAD") -> str:
    """Returns the current contents of a file on the given ref.

    Retrieves the contents from Gitiles via its API, not Gerrit's.

    Args:
        git_url: URL for the repository to get the file contents from.
        filepath: Path of the file in the repository.
        ref: The ref to use, e.g. HEAD or refs/heads/main

    Returns:
        The contents of the file as a string.
    """
    parsed_url = urllib.parse.urlparse(git_url)
    path = parsed_url[2].rstrip("/") + f"/+/{ref}/{filepath}?format=TEXT"
    contents = FetchUrl(parsed_url[1], path, ignore_404=False)
    contents = base64.b64decode(contents)
    return contents.decode("utf-8")


def GetFileContentsFromGerrit(
    host: str, change: str, filepath: str, revision: Optional[str] = None
) -> Optional[str]:
    """Returns the current contents of a file from the Gerrit.

    Args:
        host: The Gerrit host to interact with.
        change: A Gerrit change number.
        filepath: Path of the file in the repo to retrieve.
        revision: The specific revision in the change. Defaults or None to the
            latest revision.

    Returns:
        Contents of the file.
    """
    if revision is None:
        revision = "current"
    path = "%s/revisions/%s/files/%s/content" % (
        _GetChangePath(change),
        revision,
        urllib.parse.quote(filepath, ""),
    )
    contents = FetchUrl(host, path)
    if contents is None:
        return None

    contents = base64.b64decode(contents)  # bytes -> bytes
    contents = contents.decode("utf-8")  # bytes -> string
    return contents


def Rebase(
    host: str, change: str, allow_conflicts: bool = False
) -> Optional[Dict[str, Any]]:
    """Rebase the CL to the main branch.

    Args:
        host: The Gerrit host to interact with.
        change: A Gerrit change number.
        allow_conflicts: True if allowing the merge-conflict after rebasing.

    Returns:
        ChangeInfo of the change after the reading.
    """
    path = "%s/rebase" % (_GetChangePath(change),)
    body = {"allow_conflicts": "true" if allow_conflicts else "false"}
    change_info = FetchUrlJson(host, path, body=body, reqtype="POST")
    if change_info is None:
        return None
    return change_info


def GetCommitDate(git_url, commit):
    """Returns the date of a particular git commit.

    The returned object is naive in the sense that it doesn't carry any timezone
    information - you should assume UTC.

    Args:
        git_url: URL for the repository to get the commit date from.
        commit: A git commit identifier (e.g. a sha1).

    Returns:
        A datetime object.
    """
    parsed_url = urllib.parse.urlparse(git_url)
    path = "%s/+log/%s?n=1&format=JSON" % (parsed_url.path.rstrip("/"), commit)
    j = FetchUrlJson(parsed_url.netloc, path, ignore_404=False)
    if not j:
        raise GOBError(
            reason="Could not find revision information from %s" % git_url
        )
    try:
        commit_timestr = j["log"][0]["committer"]["time"]
    except (IndexError, KeyError, TypeError):
        msg = (
            "The json returned by https://%s%s has an unfamiliar structure:\n"
            "%s\n" % (parsed_url.netloc, path, j)
        )
        raise GOBError(reason=msg)
    try:
        # We're parsing a string of the form 'Tue Dec 02 17:48:06 2014'.
        return datetime.datetime.strptime(
            commit_timestr, constants.GOB_COMMIT_TIME_FORMAT
        )
    except ValueError:
        raise GOBError(
            reason='Failed parsing commit time "%s"' % commit_timestr
        )


def GetAccount(host, account="self"):
    """Get information about the user account."""
    return FetchUrlJson(host, "accounts/%s" % (account,))
