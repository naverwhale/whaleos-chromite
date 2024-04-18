# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for the code_coverage_util.py module."""

import json
import os
from typing import List

from chromite.lib import constants
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.utils import code_coverage_util


FILE_CONTENT_USE_CASE_1 = """
// comment_1

#include<abc>
int main(){
/*
* comments_2
*/
  int a = 1+3;
  /* comment_3 */
  // comment_4

    return a;
}
"""

USE_CASE_1_EXPECTED_SEGMENTS = [
    [5, 1, 0, True, True, False],
    [5, 12, 0, False, False, False],
    [9, 1, 0, True, True, False],
    [9, 15, 0, False, False, False],
    [13, 1, 0, True, True, False],
    [13, 14, 0, False, False, False],
]

FILE_CONTENT_USE_CASE_2 = """int main(){
    return 0;
}
"""

USE_CASE_2_EXPECTED_SEGMENTS = [
    [1, 1, 0, True, True, False],
    [2, 14, 0, False, False, False],
]

FILE_CONTENT_USE_CASE_3 = """
// only comment

/* in the */

/**
* file
**/
"""

FILE_CONTENT_USE_CASE_4 = ""

FILE_CONTENT_USE_CASE_5 = "int main(){ }"
HEADER_FILE_CONTENT_USE_CASE_5 = "namespace AwesomeNamespace {}"

USE_CASE_1_FILE_NAME = "USE_CASE_1.cc"
USE_CASE_2_FILE_NAME = "USE_CASE_2.cc"
USE_CASE_3_FILE_NAME = "USE_CASE_3.cc"
USE_CASE_4_FILE_NAME = "USE_CASE_4.cc"
USE_CASE_5_FILE_NAME = "USE_CASE_5.cc"
USE_CASE_5_HEADER_FILE_NAME = "USE_CASE_5.h"
PYTHON_FILE_NAME = "USE_CASE_3.py"
SHILL_FILE = "src/platform2/shill/net/shill_time.cc"
GESTURES_FILE = "src/platform/gestures/include/activity_log.h"
SOURCE = "SOURCE"
MOCK_ZERO_COVERAGE = "MockZeroCoverage"


def extractCovDataForFile(file_name: str, coverage_data: List):
    """Extreact cov data from file"""
    filter_result = [
        coverage
        for coverage in coverage_data
        if coverage["filename"].find(file_name) != -1
    ]
    if not filter_result:
        return None
    return filter_result[0]


class GetLlvmJsonCoverageDataIfValidTest(cros_test_lib.TempDirTestCase):
    """Unit tests for GetLlvmJsonCoverageDataIfValid"""

    def testIgnoresIfFileIsNotCoverageJsonFileName(self):
        """Verify that files not named coverage.json are ignored."""
        file = os.path.join(self.tempdir, "file.json")
        osutils.WriteFile(file, "Test")
        result = code_coverage_util.GetLlvmJsonCoverageDataIfValid(file)
        self.assertIsNone(result)

    def testIgnoresIfNotAFile(self):
        """Verify non-files are ignored."""
        result = code_coverage_util.GetLlvmJsonCoverageDataIfValid(
            "coverage.json"
        )
        self.assertIsNone(result)

    def testIgnoresIfFileIsNotValidJson(self):
        """Verify files with invalid JSON are ignored."""
        file = os.path.join(self.tempdir, "coverage.json")
        osutils.WriteFile(file, "Test")
        result = code_coverage_util.GetLlvmJsonCoverageDataIfValid(file)
        self.assertIsNone(result)

    def testReturnsDataWhenInProperFormat(self):
        """Verify files in the right structure have their contents returned."""
        file = os.path.join(self.tempdir, "coverage.json")
        content = json.dumps(
            {
                "data": [{"files": [{"filename": "abc"}]}],
                "version": "1",
                "type": "llvm.coverage.json.export",
            }
        )
        osutils.WriteFile(file, content)
        result = code_coverage_util.GetLlvmJsonCoverageDataIfValid(file)
        self.assertIsNotNone(result)


class GenerateZeroCoverageLlvmTest(cros_test_lib.TempDirTestCase):
    """Unit tests for GenerateZeroCoverageLlvm"""

    def testGenerateZeroCoverageLlvmSuccess(self):
        """Verify zero code coverage is being generated for all src files."""

        path_to_src_directory = os.path.join(self.tempdir, "src")
        osutils.SafeMakedirs(path_to_src_directory)

        codeBase = [
            {
                "file": USE_CASE_1_FILE_NAME,
                "content": FILE_CONTENT_USE_CASE_1,
            },
            {
                "file": USE_CASE_2_FILE_NAME,
                "content": FILE_CONTENT_USE_CASE_2,
            },
            {
                "file": USE_CASE_3_FILE_NAME,
                "content": FILE_CONTENT_USE_CASE_3,
            },
            {
                "file": USE_CASE_4_FILE_NAME,
                "content": FILE_CONTENT_USE_CASE_4,
            },
            {
                "file": PYTHON_FILE_NAME,
                "content": "awesome python code",
            },
            {
                "file": USE_CASE_5_FILE_NAME,
                "content": FILE_CONTENT_USE_CASE_5,
            },
        ]
        for code in codeBase:
            file = os.path.join(path_to_src_directory, code["file"])
            osutils.WriteFile(file, code["content"])

        osutils.SafeMakedirs(os.path.join(self.tempdir, "zero-coverage"))

        coverageJson = code_coverage_util.GenerateZeroCoverageLlvm(
            path_to_src_directories=[path_to_src_directory],
            src_file_extensions=(
                constants.ZERO_COVERAGE_FILE_EXTENSIONS_TO_PROCESS["CPP"]
            ),
            exclude_line_prefixes=constants.ZERO_COVERAGE_EXCLUDE_LINE_PREFIXES[
                "CPP"
            ],
            exclude_files=["/build/code_coverage/" + USE_CASE_5_FILE_NAME],
            exclude_files_suffixes=(),
            src_prefix_path=self.tempdir,
        )

        coverage_data = coverageJson["data"][0]["files"]

        self.assertEqual(3, len(coverage_data))

        usecase_1_cov_data = extractCovDataForFile(
            USE_CASE_1_FILE_NAME, coverage_data
        )
        usecase_2_cov_data = extractCovDataForFile(
            USE_CASE_2_FILE_NAME, coverage_data
        )
        usecase_3_cov_data = extractCovDataForFile(
            USE_CASE_3_FILE_NAME, coverage_data
        )
        usecase_4_cov_data = extractCovDataForFile(
            USE_CASE_4_FILE_NAME, coverage_data
        )
        usecase_5_cov_data = extractCovDataForFile(
            USE_CASE_5_FILE_NAME, coverage_data
        )

        self.assertIsNotNone(
            usecase_1_cov_data, "Zero cov should be generated for usercase 1"
        )
        self.assertIsNotNone(
            usecase_2_cov_data, "Zero cov should be generated for usercase 2"
        )
        self.assertIsNotNone(
            usecase_3_cov_data, "Zero cov should be generated for usercase 3"
        )
        self.assertIsNone(
            usecase_4_cov_data,
            "Zero cov should not be generated for use case 4",
        )
        self.assertIsNone(
            usecase_5_cov_data,
            "Zero cov should not be generated for excluded file",
        )
        self.assertEqual(
            usecase_1_cov_data["segments"], USE_CASE_1_EXPECTED_SEGMENTS
        )
        self.assertEqual(
            usecase_2_cov_data["segments"], USE_CASE_2_EXPECTED_SEGMENTS
        )
        self.assertEqual(usecase_3_cov_data["segments"], [])

        self.assertEqual(
            usecase_1_cov_data["filename"], "src/" + USE_CASE_1_FILE_NAME
        )
        self.assertEqual(
            usecase_2_cov_data["filename"], "src/" + USE_CASE_2_FILE_NAME
        )
        self.assertEqual(
            usecase_3_cov_data["filename"], "src/" + USE_CASE_3_FILE_NAME
        )
        self.assertEqual(usecase_1_cov_data[SOURCE], MOCK_ZERO_COVERAGE)

    def testCreateLlvmCoverageJson(self):
        """Verify that CreateLlvmCoverageJson is returning coverage json."""

        coverage_json = code_coverage_util.CreateLlvmCoverageJson(
            [{"filename": "abc"}]
        )
        self.assertEqual("llvm.coverage.json.export", coverage_json["type"])
        self.assertEqual("2.0.1", coverage_json["version"])
        self.assertEqual(1, len(coverage_json["data"][0]["files"]))

    def testMergeLLVMCoverageJson1(self):
        """Test MergeLLVMCoverageJson when coverage_json_1 is empty."""
        coverage_json_2 = code_coverage_util.CreateLlvmCoverageJson(
            [{"filename": "abc"}]
        )
        coverage_json = code_coverage_util.MergeLLVMCoverageJson(
            None, coverage_json_2
        )
        self.assertEqual(1, len(coverage_json["data"][0]["files"]))

    def testMergeLLVMCoverageJson2(self):
        """Test MergeLLVMCoverageJson when coverage_json_2 is empty."""
        coverage_json_1 = code_coverage_util.CreateLlvmCoverageJson(
            [{"filename": "abc"}]
        )
        coverage_json = code_coverage_util.MergeLLVMCoverageJson(
            coverage_json_1, None
        )
        self.assertEqual(1, len(coverage_json["data"][0]["files"]))

    def testMergeLLVMCoverageJson3(self):
        """Test MergeLLVMCoverageJson when both are non empty."""
        coverage_json_1 = code_coverage_util.CreateLlvmCoverageJson(
            [{"filename": "abc1"}]
        )
        coverage_json_2 = code_coverage_util.CreateLlvmCoverageJson(
            [{"filename": "abc2"}]
        )
        coverage_json = code_coverage_util.MergeLLVMCoverageJson(
            coverage_json_1, coverage_json_2
        )
        self.assertEqual(2, len(coverage_json["data"][0]["files"]))

    def testExtractFilenames(self):
        """Verify ExtractFilenames is extracting all file names."""

        coverage_json = code_coverage_util.CreateLlvmCoverageJson(
            [{"filename": "abc1"}, {"filename": "abc2"}]
        )
        filenames = code_coverage_util.ExtractFilenames(coverage_json)
        self.assertEqual(2, len(filenames))
        self.assertEqual({"abc1", "abc2"}, set(filenames))

    def testGetLLVMCoverageWithFilesExcluded(self):
        """Verify GetLLVMCoverageWithFilesExcluded is removing expected files"""

        coverage_json = code_coverage_util.CreateLlvmCoverageJson(
            [
                {"filename": "abc1.test.c"},
                {"filename": "abc2.test.cc"},
                {"filename": "abc2.tests.c"},
                {"filename": "a_unit_tests.cc"},
                {"filename": "abc2.test.cpp"},
                {"filename": "unittests.cpp"},
                {"filename": "src_code.cpp"},
            ]
        )
        coverage_json = code_coverage_util.GetLLVMCoverageWithFilesExcluded(
            coverage_json, constants.ZERO_COVERAGE_EXCLUDE_FILES_SUFFIXES
        )
        filenames = code_coverage_util.ExtractFilenames(coverage_json)

        self.assertEqual(1, len(filenames))
        self.assertEqual("src_code.cpp", filenames[0])

    def testHeaderFilesExcluded(self):
        """Verify that header files are properly excluded"""

        path_to_src_directory = os.path.join(self.tempdir, "src")
        osutils.SafeMakedirs(path_to_src_directory)

        codeBase = [
            {
                "file": USE_CASE_1_FILE_NAME,
                "content": FILE_CONTENT_USE_CASE_1,
            },
            {
                "file": USE_CASE_5_FILE_NAME,
                "content": FILE_CONTENT_USE_CASE_5,
            },
            {
                "file": USE_CASE_5_HEADER_FILE_NAME,
                "content": HEADER_FILE_CONTENT_USE_CASE_5,
            },
        ]
        for code in codeBase:
            file = os.path.join(path_to_src_directory, code["file"])
            osutils.WriteFile(file, code["content"])

        osutils.SafeMakedirs(os.path.join(self.tempdir, "zero-coverage"))

        coverageJson = code_coverage_util.GenerateZeroCoverageLlvm(
            path_to_src_directories=[path_to_src_directory],
            src_file_extensions=(
                constants.ZERO_COVERAGE_FILE_EXTENSIONS_TO_PROCESS["CPP"]
            ),
            exclude_line_prefixes=constants.ZERO_COVERAGE_EXCLUDE_LINE_PREFIXES[
                "CPP"
            ],
            exclude_files=["/build/code_coverage/" + USE_CASE_5_FILE_NAME],
            exclude_files_suffixes=(),
            src_prefix_path=self.tempdir,
        )

        coverage_data = coverageJson["data"][0]["files"]

        self.assertEqual(1, len(coverage_data))

        usecase_1_cov_data = extractCovDataForFile(
            USE_CASE_1_FILE_NAME, coverage_data
        )
        usecase_5_cov_data = extractCovDataForFile(
            USE_CASE_5_FILE_NAME, coverage_data
        )
        usecase_5_header_cov_data = extractCovDataForFile(
            USE_CASE_5_HEADER_FILE_NAME, coverage_data
        )

        self.assertIsNotNone(
            usecase_1_cov_data, "Zero cov should be generated for usercase 1"
        )

        self.assertIsNone(
            usecase_5_cov_data,
            "Zero cov should not be generated for excluded src file",
        )
        self.assertIsNone(
            usecase_5_header_cov_data,
            str("Zero cov should not be generated for header file"),
        )


class CleanLlvmFileNamesTest(cros_test_lib.TempDirTestCase):
    """Unit tests for  CleanLlvmFileNames"""

    def testGatherPathMappingInvalidPathMappingEntry(self):
        """Verify thrown exception on invalid path mapping entry"""

        with self.assertRaises(Exception) as context:
            path_mapping_json = {"version": 1, "mapping": [{}]}
            path = os.path.join(self.tempdir, "src_to_build_dest_map.json")

            osutils.WriteFile(
                path, json.dumps(path_mapping_json), makedirs=True
            )
            code_coverage_util.GatherPathMapping(self.tempdir)

        self.assertTrue("Missing required keys" in str(context.exception))

    def testGatherPathMapping(self):
        """Verify path mapping is properly read"""

        path_mapping_json = {
            "version": 1,
            "mapping": [
                {
                    "src_path": "src/third_party/../platform2",
                    "build_dest_path": (
                        "/build/nami/../tmp2/tmp/portage/chromeos-base/"
                        "shill-net-0.0.1-r1072/work/"
                        "shill-net-0.0.1"
                    ),
                }
            ],
        }

        path = os.path.join(self.tempdir, "src_to_build_dest_map.json")

        osutils.WriteFile(path, json.dumps(path_mapping_json), makedirs=True)
        result = code_coverage_util.GatherPathMapping(self.tempdir)
        self.assertEqual(len(result), 2)
        result1 = [x for x in result if x["src_path"] == "src/platform2"][0]
        result2 = [x for x in result if x["src_path"] == ""][0]
        self.assertEqual(
            (
                "/build/tmp2/tmp/portage/chromeos-base/"
                "shill-net-0.0.1-r1072/work/shill-net-0.0.1"
            ),
            result1["build_dest_path"],
        )
        self.assertEqual("/mnt/host/source/", result2["build_dest_path"])

    def testCleanLlvmFileNamesSuccess(self):
        """Verify cleaned file paths are correct"""

        coverage_json = code_coverage_util.CreateLlvmCoverageJson(
            [
                {
                    "filename": (
                        "/build/brya/tmp/portage/chromeos-base/"
                        "shill-net-0.0.1-r1072/work/shill-net-0.0.1/"
                        "shill/net/shill_time.cc"
                    )
                },
                {
                    "filename": (
                        "/build/brya/tmp/portage/chromeos-base/"
                        "gestures-0.0.1-r623/work/gestures"
                        "/include/activity_log.h"
                    )
                },
                {
                    "filename": (
                        "/build/brya/usr/lib/cros_rust_registry/"
                        "store/time-0.3.14/[REGISTRY]/time-0.3.14"
                        "/src/time.rs"
                    )
                },
            ]
        )
        source_root = self.tempdir

        shill_file = os.path.join(source_root, SHILL_FILE)
        gestures_file = os.path.join(source_root, GESTURES_FILE)

        osutils.WriteFile(shill_file, "Awesome shill code.", makedirs=True)
        osutils.WriteFile(
            gestures_file, "Awesome gestures code.", makedirs=True
        )

        path_mapping_list = [
            {
                "src_path": "src/platform2",
                "build_dest_path": (
                    "/build/brya/tmp/portage/chromeos-base/"
                    "shill-net-0.0.1-r1072/work/shill-net-0.0.1"
                ),
            },
            {
                "src_path": "src/platform/gestures",
                "build_dest_path": (
                    "/build/brya/tmp/portage/chromeos-base"
                    "/gestures-0.0.1-r623/work/gestures"
                ),
            },
        ]

        cleaned_json = code_coverage_util.CleanLlvmFileNames(
            coverage_json,
            source_root,
            path_mapping_list,
            constants.CODE_COVERAGE_EXCLUDE_DIRS,
        )

        coverage_data = cleaned_json["data"][0]["files"]
        self.assertEqual(len(coverage_data), 2)
        cleaned_shill_time_file = extractCovDataForFile(
            SHILL_FILE, coverage_data
        )
        cleaned_gestures_time_file = extractCovDataForFile(
            GESTURES_FILE, coverage_data
        )

        self.assertEqual(cleaned_gestures_time_file["filename"], GESTURES_FILE)
        self.assertEqual(cleaned_shill_time_file["filename"], SHILL_FILE)
