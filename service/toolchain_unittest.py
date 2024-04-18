# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Toolchain service tests."""

import collections
import os
from pathlib import Path
from typing import Dict, List, NamedTuple, Text
from unittest import mock

from chromite.lib import cros_test_lib
from chromite.lib.parser import package_info
from chromite.scripts import tricium_clang_tidy
from chromite.service import toolchain


class MockArtifact(NamedTuple):
    """Data for a Mocked Artifact."""

    linter: Text
    package: Text
    file_name: Text
    contents: Text


class MockBuildLinter(toolchain.BuildLinter):
    """Mocked version of Build Linters class."""

    def __init__(self, tempdir: Text, packages: List[Text] = None):
        super().__init__([], "", validate=False)
        self.tempdir = tempdir
        self.packages = [] if packages is None else packages
        self.package_atoms = packages

        self.artifacts = collections.defaultdict(
            lambda: collections.defaultdict(list)
        )
        self.artifacts_base = os.path.join(self.tempdir, "artifacts")

    def add_artifact(self, artifact: MockArtifact):
        """Adds a mock artifact and writes it to tempdir."""
        tmp_path = os.path.join(
            self.artifacts_base,
            artifact.linter,
            artifact.package,
            artifact.file_name,
        )

        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as tmp_artifact_file:
            tmp_artifact_file.write(artifact.contents)
        self.artifacts[artifact.linter][artifact.package].append(tmp_path)

    def _fetch_from_linting_artifacts(self, subdir) -> Dict[Text, List[Text]]:
        """Get file from emerge artifact directory."""
        artifacts = {}
        for package, package_artifacts in self.artifacts[subdir].items():
            if not self.packages or package in self.package_atoms:
                if package not in artifacts:
                    artifacts[package] = []
                artifacts[package].extend(package_artifacts)
        return artifacts


class BuildLinterTests(cros_test_lib.MockTempDirTestCase):
    """Unit tests for Build Linter Class."""

    def testValidateSysroot(self):
        real_sysroots = ["", "build/foo"]
        fake_sysroots = ["hello/world", "build/bin"]
        nonexistents = ["this_does_not_exist"]

        for sysroot in real_sysroots + fake_sysroots:
            full_sysroot = f"{self.tempdir}/{sysroot}"
            os.makedirs(f"{full_sysroot}/etc", exist_ok=True)

        for sysroot in real_sysroots:
            # Make etc/make.conf.board_setup and try to create a BuildLinter.
            full_sysroot = f"{self.tempdir}/{sysroot}"
            Path(f"{full_sysroot}/etc/make.conf.board_setup").touch()
            try:
                toolchain.BuildLinter([], full_sysroot, validate=True)
            except toolchain.InvalidSysrootError:
                self.fail(
                    f"Sysroot '{sysroot}' incorectly determined to be invalid"
                )

        for sysroot in fake_sysroots + nonexistents:
            # Don't make etc/make.conf.board_setup but try making a BuildLinter.
            full_sysroot = f"{self.tempdir}/{sysroot}"
            with self.assertRaises(toolchain.InvalidSysrootError):
                toolchain.BuildLinter([], full_sysroot, validate=True)

    def checkArtifacts(
        self,
        expected_artifacts: List[MockArtifact],
        retrieved_artifact_paths: Dict[Text, List[Text]],
    ):
        """Asserts that artifact paths match the list of expected results."""

        actual_artifacts = []
        for paths in retrieved_artifact_paths.values():
            actual_artifacts.extend(paths)
        self.assertEqual(len(actual_artifacts), len(expected_artifacts))

        for artifact in expected_artifacts:
            for artifact_path in retrieved_artifact_paths:
                if artifact_path.endswith(
                    f"{artifact.linter}/{artifact.package}/{artifact.file_name}"
                ):
                    with open(
                        artifact_path, "r", encoding="utf-8"
                    ) as artifact_file:
                        contents = artifact_file.read()
                    self.assertEqual(contents, artifact.contents)

    def testMockBuildLinter(self):
        mbl = MockBuildLinter(self.tempdir, ["pkg_1", "pkg_2", "pkg_3"])
        relevant_artifacts = [
            MockArtifact("linter_1", "pkg_1", "out.txt", "Hello world"),
            MockArtifact("linter_1", "pkg_2", "out2.txt", "Hello world 2"),
            MockArtifact("linter_1", "pkg_3", "out.txt", "Hello\nWorld"),
        ]
        irrelevant_artifacts = [
            MockArtifact("linter_2", "pkg_2", "out.txt", "Goodbye World"),
            MockArtifact("linter_1", "pkg_4", "out.txt", "Goodbye world"),
            MockArtifact("linter_2", "pkg_5", "out.txt", "Goodbye world 2"),
            MockArtifact("linter_3", "pkg_6", "out.txt", "Goodbye\nWorld"),
            MockArtifact("linter_4", "pkg_1", "out.txt", "Goodbye\nWorld"),
        ]
        for artifact in relevant_artifacts + irrelevant_artifacts:
            mbl.add_artifact(artifact)

        # pylint: disable=protected-access
        retrieved_artifact_paths = mbl._fetch_from_linting_artifacts("linter_1")

        self.checkArtifacts(relevant_artifacts, retrieved_artifact_paths)

    def testMockBuildLinterNoPackages(self):
        mbl = MockBuildLinter(self.tempdir, [])
        relevant_artifacts = [
            MockArtifact("linter_1", "pkg_1", "out.txt", "Hello world"),
            MockArtifact("linter_1", "pkg_2", "out2.txt", "Hello world 2"),
            MockArtifact("linter_1", "pkg_3", "out.txt", "Hello\nWorld"),
            MockArtifact("linter_1", "pkg_4", "out.txt", "Hello world"),
        ]
        irrelevant_artifacts = [
            MockArtifact("linter_2", "pkg_2", "out.txt", "Goodbye World"),
            MockArtifact("linter_2", "pkg_5", "out.txt", "Goodbye world 2"),
            MockArtifact("linter_3", "pkg_6", "out.txt", "Goodbye\nWorld"),
            MockArtifact("linter_4", "pkg_1", "out.txt", "Goodbye\nWorld"),
        ]
        for artifact in relevant_artifacts + irrelevant_artifacts:
            mbl.add_artifact(artifact)

        # pylint: disable=protected-access
        retrieved_artifact_paths = mbl._fetch_from_linting_artifacts("linter_1")

        self.checkArtifacts(relevant_artifacts, retrieved_artifact_paths)

    def testFetchFromLintingArtifacts(self):
        bl = toolchain.BuildLinter(
            [
                package_info.parse("category0/package0"),
                package_info.parse("category1/package1"),
                package_info.parse("category1/package2"),
                package_info.parse("category2/package3"),
            ],
            self.tempdir,
            validate=False,
        )

        bl_no_pkg = toolchain.BuildLinter([], self.tempdir, validate=False)

        relevant_cases = [
            "category1/package1/linting-output/linter1/a.out",
            "category1/package1/linting-output/linter1/b.json",
            "category1/package1/linting-output/linter1/c",
            "category1/package2/linting-output/linter1/a.out",
            "category1/package2/linting-output/linter1/b.json",
            "category1/package2/linting-output/linter1/c",
            "category2/package3/linting-output/linter1/a.out",
            "category2/package3/linting-output/linter1/b.json",
            "category2/package3/linting-output/linter1/c",
        ]

        irrelevant_cases = [
            "category3/package1/linting-output/linter1/a.out",
            "category4/package2/linting-output/linter1/a.out",
            "category2/package5/linting-output/linter1/a.out",
            "category2/package6/linting-output/linter1/a.out",
            "category1/package1/linting-output/linter2/a.out",
            "category1/package2/linting-output/linter2/a.out",
            "category2/package3/linting-output/linter3/a.out",
            "category2/package4/linting-output/linter4/a.out",
        ]

        root = Path(self.tempdir) / "var/lib/chromeos/package-artifacts"

        expected_results = {
            "category1/package1": [
                f"{str(root)}/category1/package1/linting-output/linter1/a.out",
                f"{str(root)}/category1/package1/linting-output/linter1/b.json",
                f"{str(root)}/category1/package1/linting-output/linter1/c",
            ],
            "category1/package2": [
                f"{str(root)}/category1/package2/linting-output/linter1/a.out",
                f"{str(root)}/category1/package2/linting-output/linter1/b.json",
                f"{str(root)}/category1/package2/linting-output/linter1/c",
            ],
            "category2/package3": [
                f"{str(root)}/category2/package3/linting-output/linter1/a.out",
                f"{str(root)}/category2/package3/linting-output/linter1/b.json",
                f"{str(root)}/category2/package3/linting-output/linter1/c",
            ],
        }

        additional_no_pkg_results = {
            "category3/package1": [
                f"{str(root)}/category3/package1/linting-output/linter1/a.out"
            ],
            "category4/package2": [
                f"{str(root)}/category4/package2/linting-output/linter1/a.out"
            ],
            "category2/package5": [
                f"{str(root)}/category2/package5/linting-output/linter1/a.out"
            ],
            "category2/package6": [
                f"{str(root)}/category2/package6/linting-output/linter1/a.out"
            ],
        }

        expected_no_pkg_results = dict(
            expected_results, **additional_no_pkg_results
        )

        for case in relevant_cases + irrelevant_cases:
            test_path = root / case
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.touch()

        # pylint: disable=protected-access
        actual_results = bl._fetch_from_linting_artifacts("linter1")
        self.assertDictEqual(expected_results, actual_results)

        no_pkg_results = bl_no_pkg._fetch_from_linting_artifacts("linter1")
        self.assertDictEqual(expected_no_pkg_results, no_pkg_results)

    def testGetBoard(self):
        test_data = {
            toolchain.BuildLinter([], "/build/atlas", validate=False): "atlas",
            toolchain.BuildLinter([], "/build/foo", validate=False): "foo",
            toolchain.BuildLinter([], "/build/spam", validate=False): "spam",
            toolchain.BuildLinter([], "/", validate=False): None,
            toolchain.BuildLinter([], "/not_build/spam", validate=False): None,
        }
        for test_bl, expected in test_data.items():
            actual = test_bl.get_board()
            self.assertEqual(expected, actual)

    def testGetEbuildCommand(self):
        test_data = {
            toolchain.BuildLinter(
                [], "/build/atlas", validate=False
            ): "ebuild-atlas",
            toolchain.BuildLinter(
                [], "/build/foo", validate=False
            ): "ebuild-foo",
            toolchain.BuildLinter(
                [], "/build/spam", validate=False
            ): "ebuild-spam",
            toolchain.BuildLinter([], "/", validate=False): "ebuild",
            toolchain.BuildLinter(
                [], "/not_build/spam", validate=False
            ): "ebuild",
        }

        for test_bl, expected in test_data.items():
            actual = test_bl.get_ebuild_command()
            self.assertEqual(expected, actual)

    def testGetPackageForArtifactDir(self):
        bl = toolchain.BuildLinter([], "", validate=False)

        test_cases = [
            ("category1", "package1", "linter1", "category1/package1"),
            ("category1", "package2", "linter2", "category1/package2"),
            ("category2", "package1", "linter3", "category2/package1"),
            ("category3", "package3", "linter4", "category3/package3"),
        ]

        root = Path(self.tempdir) / "var/lib/chromeos/package-artifacts"
        for case in test_cases:
            test_path = root / case[0] / case[1] / "linting-output" / case[2]
            expected_result = case[3]
            # pylint: disable=protected-access
            actual_result = bl._get_package_for_artifact_dir(test_path)
            self.assertEqual(expected_result, actual_result)

    def testFetchTidyLints(self):
        mock_calls = 0
        diagnostics = [
            tricium_clang_tidy.TidyDiagnostic("", 0, "lint1", "body1", [], []),
            tricium_clang_tidy.TidyDiagnostic("", 0, "lint2", "body2", [], []),
            tricium_clang_tidy.TidyDiagnostic("", 0, "lint3", "body3", [], []),
            tricium_clang_tidy.TidyDiagnostic("", 0, "lint4", "body4", [], []),
        ]
        expected_findings = [
            toolchain.LinterFinding(
                name="lint1",
                message="body1",
                locations=tuple(
                    [
                        toolchain.CodeLocation(
                            "", "", 0, 0, None, None, None, None
                        )
                    ]
                ),
                linter="clang_tidy",
                suggested_fixes=tuple(),
                package=package_info.parse("cat/pkg"),
            ),
            toolchain.LinterFinding(
                name="lint2",
                message="body2",
                locations=tuple(
                    [
                        toolchain.CodeLocation(
                            "", "", 0, 0, None, None, None, None
                        )
                    ]
                ),
                linter="clang_tidy",
                suggested_fixes=tuple(),
                package=package_info.parse("cat/pkg"),
            ),
            toolchain.LinterFinding(
                name="lint3",
                message="body3",
                locations=tuple(
                    [
                        toolchain.CodeLocation(
                            "", "", 0, 0, None, None, None, None
                        )
                    ]
                ),
                linter="clang_tidy",
                suggested_fixes=tuple(),
                package=package_info.parse("cat/pkg"),
            ),
            toolchain.LinterFinding(
                name="lint4",
                message="body4",
                locations=tuple(
                    [
                        toolchain.CodeLocation(
                            "", "", 0, 0, None, None, None, None
                        )
                    ]
                ),
                linter="clang_tidy",
                suggested_fixes=tuple(),
                package=package_info.parse("cat/pkg"),
            ),
        ]

        def mock_parse_tidy_invocation(_):
            nonlocal mock_calls
            mock_calls += 1
            if mock_calls == 1:
                meta = tricium_clang_tidy.InvocationMetadata(0, [], "", "", "")
                return meta, diagnostics[:2]
            if mock_calls == 2:
                meta = tricium_clang_tidy.InvocationMetadata(0, [], "", "", "")
                return meta, diagnostics[2:]
            if mock_calls == 3:
                meta = tricium_clang_tidy.InvocationMetadata(0, [], "", "", "")
                return meta, []
            elif mock_calls == 4:
                return tricium_clang_tidy.ExceptionData()
            elif mock_calls == 5:
                meta = tricium_clang_tidy.InvocationMetadata(1, [], "", "", "")
                return meta, diagnostics
            else:
                self.fail("Too many calls to parse_tidy_invocation")

        def mock_filter_findings(_, __, findings):
            if mock_calls == 1:
                self.assertCountEqual(findings, diagnostics[:2])
            elif mock_calls == 2:
                self.assertCountEqual(findings, diagnostics[2:])
            elif mock_calls == 3:
                self.assertEqual(findings, [])
            return findings

        mbl = MockBuildLinter(self.tempdir)

        artifacts = [
            MockArtifact("clang-tidy", "cat/pkg", "a.json", "content"),
            MockArtifact("clang-tidy", "cat/pkg", "b.json", "content"),
            MockArtifact("clang-tidy", "cat/pkg", "c.json", "content"),
            MockArtifact("clang-tidy", "cat/pkg", "d.json", "content"),
            MockArtifact("clang-tidy", "cat/pkg", "e.out", "content"),
        ]

        for artifact in artifacts:
            mbl.add_artifact(artifact)

        tmp_parse_tidy_invocation = tricium_clang_tidy.parse_tidy_invocation
        tricium_clang_tidy.parse_tidy_invocation = mock_parse_tidy_invocation
        tmp_filter_tidy_lints = tricium_clang_tidy.filter_tidy_lints
        tricium_clang_tidy.filter_tidy_lints = mock_filter_findings

        # pylint: disable=protected-access
        lints = mbl._fetch_tidy_lints()

        tricium_clang_tidy.parse_tidy_invocation = tmp_parse_tidy_invocation
        tricium_clang_tidy.filter_tidy_lints = tmp_filter_tidy_lints

        self.assertCountEqual(lints, expected_findings)

    def testParseIWYUFiles(self):
        mbl = MockBuildLinter(self.tempdir)

        artifacts = [
            MockArtifact(
                "iwyu",
                "cat/pkg",
                "iwyu.out",
                (
                    "\n".join(
                        [
                            "(/a/good/file.c has correct #includes/fwd-decls)",
                            "",
                            "/path/to/some/file.c should add these lines:",
                            "#include <missing1.h>  // for func1, func2, func3",
                            "#include <missing2.h>  // for func4, func5, func6",
                            "",
                            "/path/to/some/file.c should remove these lines:",
                            "- #include <unwanted.h>  // lines 11-11",
                            "",
                            "The full include-list for /path/to/some/file.c:",
                            "#include <missing1.h>  // for func1, func2, func3",
                            "#include <missing2.h>  // for func4, func5, func6",
                            "#include <stdint.h>",
                            "#include <stdlib.h>",
                            '#include "lib/foo.h"  // for func7, func8',
                            "---",
                        ]
                    )
                ),
            ),
            MockArtifact(
                "iwyu",
                "cat/pkg",
                "duplicate.out",
                (
                    "\n".join(
                        [
                            "/path/to/some/file.c should add these lines:",
                            "#include <missing1.h>  // for func1, func2, func3",
                            "#include <missing2.h>  // for func4, func5, func6",
                            "",
                            "/path/to/some/file.c should remove these lines:",
                            "- #include <unwanted.h>  // lines 11-11",
                            "",
                            "The full include-list for /path/to/some/file.c:",
                            "#include <missing1.h>  // for func1, func2, func3",
                            "#include <missing2.h>  // for func4, func5, func6",
                            "#include <stdint.h>",
                            "#include <stdlib.h>",
                            '#include "lib/foo.h"  // for func7, func8',
                            "---",
                        ]
                    )
                ),
            ),
            MockArtifact("IWYU", "cat/pkg", "empty.out", ""),
        ]

        expected_findings = [
            toolchain.LinterFinding(
                name="add",
                message="\n".join(
                    [
                        "Include list is missing:",
                        "\t#include <missing1.h>",
                        "Which is required for func1, func2, func3",
                        "",
                        "The full suggested include-list for this file:",
                        "#include <missing1.h>  // for func1, func2, func3",
                        "#include <missing2.h>  // for func4, func5, func6",
                        "#include <stdint.h>",
                        "#include <stdlib.h>",
                        '#include "lib/foo.h"  // for func7, func8',
                        "",
                        "Note: Suggestions from IWYU are not always correct and"
                        " thus require human supervision.",
                    ]
                ),
                locations=(
                    toolchain.CodeLocation(
                        "/path/to/some/file.c",
                        "",
                        line_start=1,
                        line_end=1,
                        col_start=None,
                        col_end=None,
                        start_offset=None,
                        end_offset=None,
                    ),
                ),
                linter="iwyu",
                suggested_fixes=tuple(),
                package=package_info.parse("cat/pkg"),
            ),
            toolchain.LinterFinding(
                name="add",
                message="\n".join(
                    [
                        "Include list is missing:",
                        "\t#include <missing2.h>",
                        "Which is required for func4, func5, func6",
                        "",
                        "The full suggested include-list for this file:",
                        "#include <missing1.h>  // for func1, func2, func3",
                        "#include <missing2.h>  // for func4, func5, func6",
                        "#include <stdint.h>",
                        "#include <stdlib.h>",
                        '#include "lib/foo.h"  // for func7, func8',
                        "",
                        "Note: Suggestions from IWYU are not always correct and"
                        " thus require human supervision.",
                    ]
                ),
                locations=(
                    toolchain.CodeLocation(
                        "/path/to/some/file.c",
                        "",
                        line_start=1,
                        line_end=1,
                        col_start=None,
                        col_end=None,
                        start_offset=None,
                        end_offset=None,
                    ),
                ),
                linter="iwyu",
                suggested_fixes=tuple(),
                package=package_info.parse("cat/pkg"),
            ),
            toolchain.LinterFinding(
                name="remove",
                message="\n".join(
                    [
                        "Remove from include list:",
                        "\t#include <unwanted.h>",
                        "",
                        "The full suggested include-list for this file:",
                        "#include <missing1.h>  // for func1, func2, func3",
                        "#include <missing2.h>  // for func4, func5, func6",
                        "#include <stdint.h>",
                        "#include <stdlib.h>",
                        '#include "lib/foo.h"  // for func7, func8',
                        "",
                        "Note: Suggestions from IWYU are not always correct and"
                        " thus require human supervision.",
                    ]
                ),
                locations=(
                    toolchain.CodeLocation(
                        "/path/to/some/file.c",
                        "",
                        line_start=11,
                        line_end=11,
                        col_start=None,
                        col_end=None,
                        start_offset=None,
                        end_offset=None,
                    ),
                ),
                linter="iwyu",
                suggested_fixes=tuple(),
                package=package_info.parse("cat/pkg"),
            ),
        ]

        for artifact in artifacts:
            mbl.add_artifact(artifact)

        # pylint: disable=protected-access
        parses = mbl._fetch_iwyu_lints()

        self.assertCountEqual(parses, expected_findings)


class TestEmergeAndUploadLints(cros_test_lib.RunCommandTestCase):
    """Unit tests for emerge_and_upload_lints"""

    def setUp(self):
        self.rc.AddCmdResult(
            [
                "lint_package",
                "--fetch-only",
                "--json",
                "--no-clippy",
                "--no-golint",
            ],
            stdout="linting output",
        )

    @mock.patch.object(toolchain.gs.GSContext, "CreateWithContents")
    def testEmergeAndUploadLints(self, copy_mock):
        used_gs_path = toolchain.emerge_and_upload_lints("atlas", 9999)
        target_gs_path = (
            "gs://chromeos-toolchain-artifacts/code-health/9999/atlas.json"
        )

        self.assertEqual(used_gs_path, target_gs_path)
        copy_mock.assert_called_with(target_gs_path, b"linting output")


class TestSetupToolchains(cros_test_lib.RunCommandTestCase):
    """Unit tests for setup_toolchains()."""

    def test_no_kwargs(self) -> None:
        toolchain.setup_toolchains()
        self.assertCommandCalled(
            ["sudo", "--preserve-env", "--", "cros_setup_toolchains"],
            enter_chroot=True,
        )

    def test_multiple_include_boards(self) -> None:
        toolchain.setup_toolchains(["amd64-generic", "arm-generic"])
        self.assertCommandCalled(
            [
                "sudo",
                "--preserve-env",
                "--",
                "cros_setup_toolchains",
                "--include-boards",
                "amd64-generic,arm-generic",
            ],
            enter_chroot=True,
        )
