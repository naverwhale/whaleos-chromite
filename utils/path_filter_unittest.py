# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for the path_filter.py module."""

import pathlib

from chromite.lib import cros_test_lib
from chromite.utils import path_filter


class PathFilterTest(cros_test_lib.TestCase):
    """Test the PathFilter class."""

    def testDefaultInclude(self):
        """Files are included when no rules matched."""
        f = path_filter.PathFilter([])
        self.assertTrue(f.match("README.md"))
        self.assertEqual(f.filter(["README.md"]), ["README.md"])

    def testSingleExclude(self):
        """Single rule for extension exclusion."""
        f = path_filter.PathFilter(
            [
                path_filter.exclude("*.ext"),
            ]
        )
        self.assertFalse(f.match("a.ext"))
        self.assertFalse(f.match("a/b.ext"))
        self.assertTrue(f.match("a.other"))
        self.assertEqual(
            f.filter(
                [
                    "a.ext",
                    "a/b.ext",
                    "a.other",
                ]
            ),
            ["a.other"],
        )

    def testExcludeMarkdownFilesOutOfDocsDirectory(self):
        """An example with multiple rules."""
        f = path_filter.PathFilter(
            [
                path_filter.include("docs/*.md"),
                path_filter.exclude("*.md"),
            ]
        )
        self.assertFalse(f.match("README.md"))
        self.assertFalse(f.match("a/README.md"))
        self.assertTrue(f.match("docs/README.md"))
        self.assertFalse(f.match("a/docs/README.md"))
        self.assertEqual(
            f.filter(
                [
                    "README.md",
                    "a/README.md",
                    "docs/README.md",
                    "a/docs/README.md",
                ]
            ),
            ["docs/README.md"],
        )

    def testExcludeBasenameExact(self):
        """Exclude an exact path, should only match the full path."""
        f = path_filter.PathFilter(
            [
                path_filter.exclude("BUILD.gn"),
            ]
        )
        self.assertFalse(f.match("BUILD.gn"))
        self.assertTrue(f.match("a/BUILD.gn"))
        self.assertTrue(f.match("a/../BUILD.gn"))
        self.assertTrue(f.match("./BUILD.gn"))
        self.assertEqual(
            f.filter(
                [
                    "BUILD.gn",
                    "a/BUILD.gn",
                    "a/../BUILD.gn",
                    "./BUILD.gn",
                ],
            ),
            [
                "a/BUILD.gn",
                "a/../BUILD.gn",
                "./BUILD.gn",
            ],
        )

    def testExcludeBasenameAnywhere(self):
        """Exclude a basename anywhere."""
        f = path_filter.PathFilter(
            [
                path_filter.exclude("BUILD.gn"),
                path_filter.exclude("*/BUILD.gn"),
            ]
        )
        self.assertFalse(f.match("BUILD.gn"))
        self.assertFalse(f.match("a/BUILD.gn"))
        self.assertFalse(f.match("a/../BUILD.gn"))
        self.assertFalse(f.match("./BUILD.gn"))
        self.assertEqual(
            f.filter(
                [
                    "BUILD.gn",
                    "a/BUILD.gn",
                    "a/../BUILD.gn",
                    "./BUILD.gn",
                ]
            ),
            [],
        )

    def testPathlib(self):
        """Test handling of pathlib.Path."""
        f = path_filter.PathFilter(
            [
                path_filter.exclude("*.ext"),
            ]
        )
        self.assertFalse(f.match(pathlib.Path("a.ext")))
        self.assertFalse(f.match(pathlib.Path("a/b.ext")))
