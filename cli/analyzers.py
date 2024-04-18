# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Shared helpers for cros analyzer commands (fix, lint, format)."""

from abc import ABC
import logging
import os
from pathlib import Path
from typing import List

from chromite.cli import command
from chromite.lib import commandline
from chromite.lib import git


def GetFilesFromCommit(commit: str) -> List[str]:
    """Returns files changed in the provided git `commit` as absolute paths."""
    repo_root_path = git.FindGitTopLevel(None)
    files_in_repo = git.RunGit(
        repo_root_path,
        ["diff-tree", "--no-commit-id", "--name-only", "-r", commit],
    ).stdout.splitlines()
    return [os.path.join(repo_root_path, p) for p in files_in_repo]


def HasUncommittedChanges(files: List[str]) -> bool:
    """Returns whether there are uncommitted changes on any of the `files`.

    `files` can be absolute or relative to the current working directory. If a
    file is passed that is outside the git repository corresponding to the
    current working directory, an exception will be thrown.
    """
    working_status = git.RunGit(
        None, ["status", "--porcelain=v1", *files]
    ).stdout.splitlines()
    if working_status:
        logging.warning("%s", "\n".join(working_status))
    return bool(working_status)


class AnalyzerCommand(ABC, command.CliCommand):
    """Shared argument parsing for cros analyzers (fix, lint, format)."""

    # Additional aliases to offer for the "--inplace" option.
    inplace_option_aliases = []

    # Whether to include options that only make sense for analyzers that can
    # modify the files being checked.
    can_modify_files = False

    # CliCommand overrides.
    use_filter_options = True

    @classmethod
    def AddParser(cls, parser):
        super().AddParser(parser)
        if cls.can_modify_files:
            parser.add_argument(
                "--check",
                dest="dryrun",
                action="store_true",
                help="Display files with errors & exit non-zero",
            )
            parser.add_argument(
                "--diff",
                action="store_true",
                help="Display diff instead of fixed content",
            )
            parser.add_argument(
                *(["-i", "--inplace"] + cls.inplace_option_aliases),
                dest="inplace",
                default=None,
                action="store_true",
                help="Fix files inplace (default)",
            )
            # NB: This must come after --inplace due to dest= being the same,
            # and so --inplace's default= is used.
            parser.add_argument(
                "--stdout",
                dest="inplace",
                action="store_false",
                help="Write to stdout",
            )

        parser.add_argument(
            "-j",
            "--jobs",
            type=int,
            default=None,
            help="Number of files to process in parallel.",
        )

        parser.add_argument(
            "--commit",
            type=str,
            help=(
                "Use files from git commit instead of on disk. If no files are"
                " provided, the list will be obtained from git diff-tree."
            ),
        )
        parser.add_argument(
            "--head",
            "--HEAD",
            dest="commit",
            action="store_const",
            const="HEAD",
            help="Alias for --commit HEAD.",
        )
        parser.add_argument(
            "files",
            nargs="*",
            type=Path,
            help=(
                "Files to fix. Directories will be expanded, and if in a git"
                " repository, the .gitignore will be respected."
            ),
        )

    @classmethod
    def ProcessOptions(
        cls,
        parser: commandline.ArgumentParser,
        options: commandline.ArgumentNamespace,
    ) -> None:
        """Validate & post-process options before freezing."""
        if cls.can_modify_files:
            if cls.use_dryrun_options and options.dryrun:
                if options.inplace:
                    # A dry-run should never alter files in-place.
                    logging.warning("Ignoring inplace option for dry-run.")
                options.inplace = False
            if options.inplace is None:
                options.inplace = True

        # Whether a committed change is being analyzed. Note "pre-submit" is a
        # special commit passed by `pre-upload.py --pre-submit` asking to check
        # changes only staged for a commit, but not yet committed.
        is_committed = options.commit and options.commit != "pre-submit"

        if is_committed and not options.files:
            options.files = GetFilesFromCommit(options.commit)

        if cls.can_modify_files and is_committed and options.inplace:
            # If a commit is provided, bail when using inplace if any of the
            # files have uncommitted changes. This is because the input to the
            # analyzer will not consider any working state changes, so they will
            # likely be lost. In future this may be supported by attempting to
            # stash and rebase changes. See also b/290714959.
            if HasUncommittedChanges(options.files):
                parser.error("In-place may clobber uncommitted changes.")

        if not options.files:
            # Running with no arguments is allowed to make the repo upload hook
            # simple, but print a warning so that if someone runs this manually
            # they are aware that nothing was changed.
            logging.warning("No files provided.  Doing nothing.")
