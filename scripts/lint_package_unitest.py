# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for lint_package script."""

from chromite.lib import cros_test_lib
from chromite.scripts import lint_package
from chromite.service import toolchain


class TestApplyFixes(cros_test_lib.MockTempDirTestCase):
    """Unit tests for --apply-fixes."""

    def fix_from_offsets(self, start, end, path="", edit=""):
        return toolchain.SuggestedFix(
            edit, toolchain.CodeLocation(path, "", 0, 0, None, None, start, end)
        )

    def fix_to_offsets(self, fix):
        return (fix.location.start_offset, fix.location.end_offset)

    def testHasOverlap(self):
        prior_fixes = [
            self.fix_from_offsets(0, 5),
            self.fix_from_offsets(10, 15),
            self.fix_from_offsets(20, 25),
            self.fix_from_offsets(30, 30),
        ]
        no_overlaps = [
            self.fix_from_offsets(40, 45),
            self.fix_from_offsets(50, 55),
            self.fix_from_offsets(60, 65),
            self.fix_from_offsets(70, 70),
        ]
        overlaps = [
            self.fix_from_offsets(0, 2),
            self.fix_from_offsets(10, 10),
            self.fix_from_offsets(25, 25),
            self.fix_from_offsets(22, 902),
            self.fix_from_offsets(30, 30),
            self.fix_from_offsets(5, 5),
        ]
        prior_fixes_str = str([self.fix_to_offsets(f) for f in prior_fixes])
        for fix in no_overlaps:
            self.assertFalse(
                lint_package.has_overlap(prior_fixes, [fix]),
                "has_overlap returned true unepectedly for "
                f"{self.fix_to_offsets(fix)} in {prior_fixes_str}",
            )
        for fix in overlaps:
            self.assertTrue(
                lint_package.has_overlap(prior_fixes, [fix]),
                "has_overlap returned false unexpectedly for "
                f"{self.fix_to_offsets(fix)} in {prior_fixes_str}",
            )

        self.assertTrue(
            lint_package.has_overlap(prior_fixes, overlaps + no_overlaps)
        )

        self.assertTrue(
            lint_package.has_overlap(prior_fixes, no_overlaps + overlaps)
        )

    def testApplyEdits(self):
        prior_contents = "0123456789" * 5
        edits = [
            self.fix_from_offsets(0, 5, edit="abc"),
            self.fix_from_offsets(8, 9, edit=""),
            self.fix_from_offsets(10, 15, edit="hello world"),
            self.fix_from_offsets(20, 25, edit=""),
            self.fix_from_offsets(30, 30, edit="foo"),
            self.fix_from_offsets(43, 48, edit="spam spam"),
        ]
        expected = (
            "abc5679"
            + "hello world56789"
            + "56789"
            + "foo0123456789"
            + "012spam spam89"
        )
        self.assertEqual(
            lint_package.apply_edits(prior_contents, edits), expected
        )

    def testFilterLints(self):
        names_filters = ["spam", "foo"]
        keep_lints = [
            toolchain.LinterFinding(name, "", [], "", [], None)
            for name in (
                "spam_this",
                "please-spam-me",
                "spam",
                "foo_this",
                "please-foo-me",
                "foo",
                "please-spam-foo-ok?",
            )
        ]
        discard_lints = [
            toolchain.LinterFinding(name, "", [], "", [], None)
            for name in ("abc", "", "hello_world")
        ]

        self.assertListEqual(
            keep_lints, lint_package.filter_lints(keep_lints, names_filters)
        )

        self.assertEqual(
            lint_package.filter_lints(discard_lints, names_filters), []
        )
