# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""CR and CQ +2 copybot project commits for downstreaming.

See go/copybot

For Zephyr Downstreaming Rotation: go/zephyr-downstreaming-guide
For coreboot Downstreaming Rotation: go/coreboot:downstreaming
"""

import argparse
from collections import defaultdict
import logging
import re
from typing import Callable, Dict, List, NamedTuple, Tuple

from chromite.contrib.copybot_downstream_config import downstream_argparser
from chromite.lib import config_lib
from chromite.lib import gerrit


# Gerrit will merge a max of 240 dependencies. Leave some room
# for dependencies from the platform/ec repo.
MAX_GERRIT_CHANGES = 225
REVIEWER_KEY_TEXT = "Original-Reviewed-by"
AUTHOR_KEY_TEXT = "Original-Signed-off-by"
COPYBOT_SERVICE_ACCOUNT = (
    "chromeos-ci-prod@chromeos-bot.iam.gserviceaccount.com"
)

CONTRIBUTOR_FILTERS = {
    "authors": AUTHOR_KEY_TEXT,
    "reviewers": REVIEWER_KEY_TEXT,
}


class PathDomains(NamedTuple):
    """A filepath and the domains that must review it."""

    path: str
    domains: List[str]


class CopybotDownstream:
    """Defines the functionality of the downstreaming review process."""

    def __init__(self, opts: argparse.Namespace):
        """Initialize the CopybotDownstream Object.

        Args:
            opts: argparse object with the desired arguments
                project: Name of the project to be acted on.
                dry_run: If True dry-run this pass without acting on gerrit
                cq_dry_run: If True, use CQ+1 instead of CQ+2
                limit: Limit the number of CL's to be downstreamed
                stop_at: Stop at the specified change(CL Number)
                ignore_warnings: Ignore warnings and submit changes
                include_dependencies: Apply CR/CQ to dependencies found
        """
        self.gerrit_helper = gerrit.GetGerritHelper(
            config_lib.GetSiteParams().EXTERNAL_REMOTE
        )

        # Map of functions to be called when the project in the key is
        # encountered.
        #
        # List of tuples(function, list of arguments) where the format of the
        # list can vary across functions.
        #
        # Functions should take a CL and perform any additional checks required
        # by the project prior to downstreaming.
        #
        #    Args:
        #        gerrit CL dict for use in parsing
        #        dynamic args for use in parsing
        #    Returns:
        #        List of warning strings to be printed for this CL
        self.project = opts.project
        self.dry_run = opts.dry_run
        self.cq_dry_run = opts.cq_dry_run
        self.stop_at = opts.stop_at
        self.ignore_warnings = opts.ignore_warnings
        # dict of dicts containing CL info returned by gerrit.
        #   Key - CL Number
        #   Value - Gerrit dictionary data
        self.cl_info = {}
        if not opts.limit or opts.limit > MAX_GERRIT_CHANGES:
            logging.info(
                "Limiting to maximum Gerrit changes (%d)", MAX_GERRIT_CHANGES
            )
            opts.limit = MAX_GERRIT_CHANGES
        self.limit = opts.limit
        default_check_funcs = [
            [self.check_commit_message, ["\nC[Qq]-Depend:.*"]],
            [self.check_hashtags, ["copybot-skip"]],
        ]
        self.check_funcs = default_check_funcs + self._project_check_funcs()

    def _project_check_funcs(self) -> List[List[Tuple[Callable, List]]]:
        """Return a list of checkers specific to this project config.

        Since this is the general-case class, there are no project-specific
        checkers. Subclasses should override this function to define their
        specific needs.
        """
        return []

    def project_passed_downstreamer_review_paths_check(
        self, cl: Dict, paths: List[str]
    ) -> List[str]:
        """Check paths that require further downstreamer review.

        * Require additional review from any paths specified by paths.

        Args:
            cl: gerrit CL dict for use in parsing.
            paths: paths to check for this project.

        Returns:
            warning_strings a list of strings to be printed for this CL.
            * This must match the expected prototype used in check_funcs.
        """
        warning_strings = []
        revision = cl["revisions"][cl["current_revision"]]
        for path in paths:
            if any(path in s for s in revision["files"]):
                warning_strings.append(
                    f"Found filepath({path}) which requires downstreamer review"
                )
        return warning_strings

    def _extract_footer_value(self, commit_line: str, key: str) -> str:
        """Extract a footer value from a commit line.

        Examples:
            commit_line: "Original-Reviewed-by:sundar@google.com"
            key: "Original-Reviewed-by"
            returns: "sundar@google.com"

            commit_line: "Original-Signed-off-by:sundar@google.com"
            key: "Original-Signed-off-by"
            returns: "sundar@google.com"
        """
        m = re.fullmatch(f"{key}:(.*)", commit_line)
        if not m:
            return ""
        return m.group(1).strip()

    def _get_contributors_from_commit_msg(
        self, message: List[str], filters: Dict
    ) -> Dict:
        """Extract contributor values from a commit message

        Args:
            message: List of strings representing a commit message where
                one line is one member of the list.
            filters: Dict of filters to be applied for contributor types.

        Returns:
            Dict
                key: contributor type
                value : List[str] Contributor
        """
        contributors = defaultdict(list)
        for line in message.splitlines():
            for contributor_type in filters:
                contributor_text = self._extract_footer_value(
                    line, filters[contributor_type]
                )
                if contributor_text:
                    contributors[contributor_type].append(contributor_text)
        return contributors

    def project_passed_domain_restricted_paths_check(
        self, cl: Dict, paths_domains: List[PathDomains]
    ) -> List[str]:
        """Check paths that require further downstreamer review.

        * Require additional review if changes to paths specified by paths
            are not reviewed by anyone in the domain list specified by paths.

        Args:
            cl: gerrit CL dict for use in parsing.
            paths_domains: list of tuples(path, restricted_domains), where path
                is the path to be restricted, and restricted_domains is a list
                of domains that should have been a part of the review.

        Returns:
            warning_strings a list of strings to be printed for this CL.
            * This must match the expected prototype used in check_funcs.
        """
        warning_strings = []
        revision = cl["revisions"][cl["current_revision"]]
        contributors = self._get_contributors_from_commit_msg(
            revision["commit"]["message"], CONTRIBUTOR_FILTERS
        )

        for path, domains in paths_domains:
            if not any(path in rev_file for rev_file in revision["files"]):
                continue
            domain_review_found = any(
                (domain in author or domain in reviewer)
                for reviewer in contributors["reviewers"]
                for author in contributors["authors"]
                for domain in domains
            )
            if not domain_review_found:
                warning_strings.append(
                    f"Found modification in filepath({path}) which requires"
                    f" downstreamer review from domain(s) {domains}"
                )
            elif len(contributors["authors"]) > 1:
                warning_strings.append(
                    f"Found CL with multiple authors, the final author may not"
                    f" satisfy domain checks {contributors['authors']}"
                )
        return warning_strings

    def check_commit_message(self, cl: Dict, args: List[str]) -> List[str]:
        """Check commit message for keywords.

        * Throw warning if keywords found in commit message.
            This can be useful for banned words as well as logistical issues
                such as CL's with CQ-Depend.

        Args:
            cl: gerrit CL dict for use in parsing.
            args: list of keywords to flag.

        Returns:
            warning_strings a list of strings to be printed for this CL.
            * This must match the expected prototype used in check_funcs.
        """
        warning_strings = []
        for banned_term in args:
            if re.search(
                banned_term,
                cl["revisions"][cl["current_revision"]]["commit"]["message"],
            ):
                printable_term = "".join(banned_term.splitlines())
                warning_strings.append(f"Found {printable_term} in change!")
        return warning_strings

    def check_hashtags(self, cl: Dict, args: List[str]) -> List[str]:
        """Check hashtags for keywords.

        * Throw warning if keywords found in hashtags..

        Args:
            cl: gerrit CL dict for use in parsing.
            args: list of keywords to flag.

        Returns:
            warning_strings a list of strings to be printed for this CL.
            * This must match the expected prototype used in checks.
        """
        warning_strings = []
        for banned_hashtag in args:
            if banned_hashtag in cl["hashtags"]:
                warning_strings.append(
                    f"Change marked with hashtag {banned_hashtag}"
                )
        return warning_strings

    def _get_relation_chain_and_info(self) -> Tuple[List[str], Dict]:
        """Gets an ordered list of CLs to downstream and detailed info on each.

        Also applies the limit set in self.opts.

        Returns:
            A list of Gerrit CL numbers to downstream
            A dictionary of CL detailed info with CL number as key
        """
        all_cls = self.gerrit_helper.Query(
            hashtag=f"{self.project}-downstream",
            status="open",
            raw=True,
            verbose=True,
            convert_results=False,
        )

        logging.debug(
            "CLs found in search (%d total): %s",
            len(all_cls),
            [cl["_number"] for cl in all_cls],
        )

        # Build a set of all CL numbers
        cl_numbers_set = {cl["_number"] for cl in all_cls}

        # Check if any CLs are NOT owned by the Copybot user
        for cl in all_cls:
            if cl["owner"]["email"] != COPYBOT_SERVICE_ACCOUNT:
                raise RuntimeError(
                    f"CL {cl['_number']} is not owned by the Copybot service "
                    "account. Please investigate and re-run script."
                )

        # Take an arbitrary CL number and query its related CLs, which should
        # yield the downstreaming relation chain, including itself. Reverse this
        # list so index 0 is the bottom of the stack (most-depended-upon CL).
        logging.debug(
            "Using %s as arbitrary starting point", all_cls[0]["_number"]
        )
        relation_chain = self._get_related_cls(all_cls[0]["_number"])
        relation_chain.reverse()

        # Remove all in this chain from the set. If it doesn't exist, ignore
        # but log it
        for cl_num in relation_chain:
            if cl_num not in cl_numbers_set:
                logging.warning(
                    "CL %s is in relation chain but wasn't in initial search "
                    "results",
                    cl_num,
                )
            cl_numbers_set.discard(cl_num)

        if len(cl_numbers_set) > 0:
            # If this is true, there are CL(s) present that are not part of the
            # relation chain. This is weird. Report an error and stop.

            raise RuntimeError(
                "Found CL(s) that belong to a different relation chain: "
                f"{sorted(cl_numbers_set)}"
            )

        if self.limit:
            # Applying the limit here saves a lot of Gerrit API calls
            logging.debug(
                "CLs before applying limit (%d total): %s",
                len(relation_chain),
                relation_chain,
            )

            relation_chain = relation_chain[: self.limit]

        # Get info on all CLs in relation chain
        cl_info = {
            cl_num: self.gerrit_helper.GetChangeDetail(cl_num, verbose=True)
            for cl_num in relation_chain
        }

        return relation_chain, cl_info

    def _check_cl(
        self,
        downstream_candidate_cl: Dict,
    ) -> List[str]:
        """Check whether the given CL is OK to downstream.

        Args:
            downstream_candidate_cl: dict representing the CL that we want to
                downstream.

        Returns:
            warnings: A list of warning strings stating problems with the CL.
            If empty, that means there are no problems.
        """
        warnings = []
        logging.debug("Checking %s", downstream_candidate_cl["_number"])
        for func, extra_args in self.check_funcs:
            tmp_warnings = func(downstream_candidate_cl, extra_args)
            if tmp_warnings:
                warnings.extend(tmp_warnings)

        return warnings

    def _filter_cls(self, cls_to_downstream: List[str]) -> List[Dict]:
        """Filter full CL list based on:

            The limit.
            CL the chain should stop at.
            copybot-skip hashtag.

        Args:
            cls_to_downstream: Ordered list of all candidate CL numbers to be
                downstreamed.

        Returns:
            cls_to_downstream: Ordered list of filtered CL numbers to be
            downstreamed.
        """
        filtered_cls = []
        for change_num in cls_to_downstream:
            if self.stop_at and self.stop_at == change_num:
                logging.info(
                    "Matched change: %s, stop processing other changes",
                    change_num,
                )
                break
            if self.check_hashtags(self.cl_info[change_num], ["copybot-skip"]):
                continue
            filtered_cls.append(change_num)
        return filtered_cls

    def _get_related_cls(self, change_number: str) -> List[str]:
        """Get the list of related CLs for the passed in CL number.

        Args:
            change_number: CL to find relationships of.

        Returns:
            List of strings containing related CL numbers.
        """
        return [
            x["_change_number"]
            for x in self.gerrit_helper.GetRelatedChangesInfo(change_number)[
                "changes"
            ]
            if x["status"] == "NEW"
        ]

    def _act_on_cls(self, cls_to_downstream: List[str]) -> None:
        """Perform Gerrit updates on the CLs to downstream.

        Args:
            cls_to_downstream: Ordered list of all CL candidates to be
                downstreamed.
        """
        # TODO(b/278748163): Investigate bulk changes instead.
        for i, change_num in enumerate(cls_to_downstream):
            logging.info(
                "Downstreaming %s: %d/%d",
                change_num,
                i + 1,
                len(cls_to_downstream),
            )

            self.gerrit_helper.SetReviewers(
                change=change_num, dryrun=self.dry_run, notify="NONE"
            )
            self.gerrit_helper.SetReview(
                change=change_num,
                dryrun=self.dry_run,
                # Add Verified label because client POST removes it.
                labels={
                    "Verified": "1",
                    "Code-Review": "2",
                    "Commit-Queue": "1" if self.cq_dry_run else "2",
                },
            )

    def _handle_checks_results(self, all_warnings: List[str]) -> int:
        """Perform Gerrit updates on the CLs to downstream.

        Args:
            all_warnings: A dictionary of lists of warning strings stating
                problems with these CLs.
                Key: CL number with warnings
                Value: List of warnings (str) found in the CL associated with
                    the key. If empty, that means there are no problems.

        Returns:
            0 if warnings are acceptable/ignored.
            1 if the script should exit due to warnings.
        """
        if all_warnings:
            for cl_num, warnings in all_warnings.items():
                logging.warning(
                    "http://crrev/c/%s Found warnings in change:\n\t%s",
                    cl_num,
                    "\n\t".join(warning for warning in warnings),
                )
            if not self.ignore_warnings:
                logging.error(
                    "Warnings detected in this run.  Please address"
                    " them.\n\t\tTo ignore the listed warnings, rerun with"
                    " --ignore-warnings"
                )
                return 1
        return 0

    def cmd_downstream(self):
        """Downstream copybot project CLs."""

        cls_to_downstream, self.cl_info = self._get_relation_chain_and_info()

        if len(cls_to_downstream) == 0:
            logging.info("No %s CLs to downstream!", self.project)
            return 0

        all_warnings = defaultdict(list)

        for change_num, change in self.cl_info.items():
            warnings = self._check_cl(change)
            if warnings:
                all_warnings[change_num] = warnings

        result = self._handle_checks_results(all_warnings)
        if result != 0:
            return result

        logging.debug(
            "cls_to_downstream before filtering (%d total): %s",
            len(cls_to_downstream),
            cls_to_downstream,
        )

        cls_to_downstream = self._filter_cls(cls_to_downstream)
        logging.info(
            "Downstreaming the following CLs (%d total):\n%s",
            len(cls_to_downstream),
            "\n".join(str(change_num) for change_num in cls_to_downstream),
        )

        self._act_on_cls(cls_to_downstream)

        logging.info("All finished! Remember to monitor the CQ!")
        return 0

    def cmd_clear_attention(self):
        """Remove user from attention set on merged CLs."""

        cls_to_modify = self.gerrit_helper.Query(
            hashtag=f"{self.project}-downstream",
            status="merged",
            attention="me",
            raw=True,
        )
        cls_to_modify.sort(key=lambda patch: patch["number"])

        if self.limit:
            cls_to_modify = cls_to_modify[: self.limit]

        counter = 0
        for cl in cls_to_modify:
            logging.info(
                "Updating attention set on CL %s (%d/%d)",
                cl["number"],
                counter + 1,
                len(cls_to_modify),
            )

            self.gerrit_helper.SetAttentionSet(
                change=cl["number"],
                remove=("me",),
                dryrun=self.dry_run,
                notify="NONE",
            )
            counter += 1

            if self.stop_at and self.stop_at == cl["number"]:
                break

        logging.info("Total CLs affected: %d", counter)
        return 0

    def run(self, cmd):
        if cmd is None:
            return self.cmd_downstream()
        if cmd == "clear_attention":
            return self.cmd_clear_attention()

        logging.error("Unknown subcommand %s", cmd)
        return 1


def main(args):
    """Main entry point for CLI."""
    parser = downstream_argparser.generate_copybot_arg_parser()
    opts = parser.parse_args(args)
    CopybotDownstream(opts).run(opts.cmd)
