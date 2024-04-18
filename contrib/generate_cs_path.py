# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Use with an IDE to copy a link to the current file/line to your clipboard.

Public and private repos are supported. The internal/public arguments are only
used if the repo is public, private repos always link to the internal code
search.

By default always generates a link to the public code search, but can also
generate links to the internal code search.

Currently only works locally and if using X11.

To allow use over SSH, enable X11 forwarding.
Client side: -X, or add "X11Forwarding yes" to your ~/.ssh/config.
Server side: "X11Forwarding yes" must be in /etc/ssh/sshd_config.

IDE integration instructions. Please add your IDE if it's not listed, or update
the instructions if they're vague or out of date!

For Intellij:
Create a new External Tool (Settings > Tools > External Tools).
Tool Settings:
    Program: ~/chromiumos/chromite/contrib/generate_cs_path
    Arguments: $FilePath$ -l $LineNumber$

For VSCode:
Create a custom task (code.visualstudio.com/docs/editor/tasks#_custom-tasks)
with the command:
    ~/chromiumos/chromite/contrib/generate_cs_path ${file} -l ${lineNumber}
"""

import os
from pathlib import Path
import sys

from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import git


class CodeSearch:
    """format returns a url to the code specified"""

    @classmethod
    def format(cls, attrs, opts, checkout_path, relative_path):
        raise NotImplementedError()


class Gitiles(CodeSearch):
    """format returns a url to the code specified"""

    @classmethod
    def format(cls, attrs, opts, checkout_path, relative_path):
        line = f"#{opts.line}" if opts.line else ""
        return f'{attrs["push_url"]}/+/{attrs["sha"]}/{relative_path}{line}'


class PublicCS(CodeSearch):
    """format returns a url to the code specified"""

    @classmethod
    def format(cls, attrs, opts, checkout_path, relative_path):
        line = f";l={opts.line}" if opts.line else ""
        sha = attrs["sha"] if opts.upstream_sha else "HEAD"
        # HEAD is the ref for the codesearch repo, not the project itself.
        return (
            "https://source.chromium.org/chromiumos/chromiumos/codesearch/+/"
            + f"{sha}:{checkout_path}/{relative_path}{line}"
        )


class InternalCS(CodeSearch):
    """format returns a url to the code specified"""

    @classmethod
    def format(cls, attrs, opts, checkout_path, relative_path):
        line = f";l={opts.line}" if opts.line else ""
        sha = f';rcl={attrs["sha"]}' if opts.upstream_sha else ""
        return (
            "http://cs/chromeos_public/"
            + f"{checkout_path}/{relative_path}{line}{sha}"
        )


class PrivateCS(CodeSearch):
    """format returns a url to the code specified"""

    @classmethod
    def format(cls, attrs, opts, checkout_path, relative_path):
        line = f";l={opts.line}" if opts.line else ""
        sha = f';rcl={attrs["sha"]}' if opts.upstream_sha else ""
        return (
            "http://cs/chromeos_internal/"
            + f"{checkout_path}/{relative_path}{line}{sha}"
        )


def GetParser():
    """Build the argument parser."""
    parser = commandline.ArgumentParser(description=__doc__)

    # Public/internal code search selection arguments.
    type_group = parser.add_mutually_exclusive_group()
    type_group.add_argument(
        "-p",
        "--public",
        dest="public_link",
        action="store_true",
        default=True,
        help="Generate a link to the public code search.",
    )
    type_group.add_argument(
        "-i",
        "--internal",
        dest="public_link",
        action="store_false",
        help="Generate a link to the internal code search.",
    )
    type_group.add_argument(
        "-g",
        "--gitiles",
        action="store_true",
        default=False,
        help="Generate a gitiles link rather than a code search link.",
    )

    parser.add_argument("-l", "--line", type=int, help="Line number.")
    parser.add_argument(
        "--upstream-sha", action="store_true", help="Link to the upstream sha."
    )

    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "-o",
        "--open",
        action="store_true",
        default=False,
        help="Open the link in a browser rather than copying it to the "
        "clipboard.",
    )
    action_group.add_argument(
        "-s",
        "--show",
        action="store_true",
        default=False,
        help="Output the link to stdout rather than copying it to the"
        "clipboard.",
    )

    parser.add_argument("path", type="path", help="Path to a file.")

    return parser


def ParseArguments(argv):
    """Parse and validate arguments."""
    parser = GetParser()
    opts = parser.parse_args(argv)

    opts.path = Path(opts.path).relative_to(constants.SOURCE_ROOT)

    opts.Freeze()
    return opts


def GenerateLink(attrs, opts, checkout_path, relative_path):
    """Generate link to CS based on on parsed arguments and checkout."""
    if opts.gitiles:
        base = Gitiles
    elif attrs.get("remote_alias") == "cros-internal":
        # Private repos not on public CS, so force internal private.
        base = PrivateCS
    elif opts.public_link:
        base = PublicCS
    else:
        base = InternalCS

    return base.format(attrs, opts, checkout_path, relative_path)


def main(argv):
    opts = ParseArguments(argv)

    checkout = git.ManifestCheckout.Cached(opts.path)

    # Find the project.
    checkout_path = None
    attrs = {}
    for checkout_path, attrs in checkout.checkouts_by_path.items():
        try:
            relative_path = opts.path.relative_to(checkout_path)
            break
        except ValueError:
            continue
    else:
        cros_build_lib.Die("No project found for %s.", opts.path)

    if opts.upstream_sha:
        attrs["sha"] = git.RunGit(
            attrs["local_path"], ["rev-parse", attrs["tracking_branch"]]
        ).stdout.strip()
    else:
        attrs["sha"] = git.RunGit(
            attrs["local_path"], ["rev-parse", "HEAD"]
        ).stdout.strip()

    final_link = GenerateLink(attrs, opts, checkout_path, relative_path)

    is_mac_os = sys.platform.startswith("darwin")

    if opts.open:
        cmd = ["open" if is_mac_os else "xdg-open", final_link]
        os.execvp(cmd[0], cmd)
    elif opts.show:
        print(final_link)
    else:
        cmd = ["pbcopy"] if is_mac_os else ["xsel", "--clipboard", "--input"]
        cros_build_lib.run(cmd, input=final_link)
