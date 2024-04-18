# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Generate artifacts for E2E coverage.

E2E coverage captures the code being run in E2E tests. Capture all the artifacts
of all chromeos packages so that we can generate a complete coverage report of
all our E2E tests.
"""

import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional

from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib


# This profdata file is generated using clang and llvm toolchain from a minimal
# test.cc file. The contents of the test.cc file do not matter and it is only
# used to generate LLVM sections in generated test.profdata file. It is not
# dependent on the underlying architecture or target. This profdata file is
# checked against an actual object file generated during emerge by llvm-cov
# to identify source lines that should be covered for code coverage.
# This was generated using:
# echo 'int main(){}' | clang -x c \
#   -fprofile-instr-generate -fcoverage-mapping -o test
# LLVM_PROFILE_FILE="test.profraw" ./test
# llvm-profdata merge -sparse test.profraw -o test.profdata
_TEST_PROFDATA_PATH = "scripts/testdata/test.profdata"
_COVERAGE_FILENAME = "coverage.json"


def generate_kernel_artifacts(kernel_home: Path) -> Dict[str, str]:
    """Generate all the kernel artifacts.

    Args:
        kernel_home: Location for all kernel binaries.

    Returns:
        Dict containing the name and the corresponding gcov output.
    """
    data = {}
    for file in kernel_home.glob("**/*.gcno"):
        # The aim here is to get instrumented (valid code) lines in a kernel
        # source which uses gcov format. Foc these, llvm-cov needs to be passed
        # a source file with the gcno file. But since we're not looking for
        # actual coverage, we just use minimal test.cc(which won't match any of
        # source lines), and llvm-cov sees all lines in the gcno file as
        # uncovered. E2E coverage reporting will use this information to
        # understand which lines need to have coverage when the E2E test runs.
        cmd = [
            "llvm-cov",
            "gcov",
            "-t",
            f"--gcno={file}",
            "/dev/null",
        ]
        result = cros_build_lib.dbg_run(
            cmd, capture_output=True, encoding="utf-8"
        )
        name = f"{file.parent.name}_{file.stem}.gcov"
        data[name] = result.stdout

    return data


def generate_llvm_artifacts(object_files: List[str]) -> str:
    """Generate the llvm artifacts needed.

    Args:
        object_files: List of object files containing the LLVM sections.

    Returns:
        Coverage JSON containing all info.
    """
    if not object_files:
        logging.info("No LLVM section object files found.")
        return None

    cmd = [
        "llvm-cov",
        "export",
        "--skip-expansions",
    ]

    cmd.extend(f"--object={x}" for x in object_files)

    # The aim here is to get instrumented (valid code) lines in a source file.
    # llvm-cov needs to be passed a profile file, but since we're not looking
    # for actual coverage, we just use one from our minimal test.cc
    # (which won't match any of those lines), and llvm-cov sees all lines in
    # the executed object_files as not covered.
    # E2E coverage reporting will use this information to understand which
    # lines need to have coverage when the E2E test runs.
    pfdata = constants.CHROMITE_DIR / _TEST_PROFDATA_PATH
    cmd.append(f"-instr-profile={pfdata}")
    result = cros_build_lib.dbg_run(cmd, capture_output=True, encoding="utf-8")

    return result.stdout


def _get_parser() -> commandline.ArgumentParser:
    """Build the argument parser.

    Returns:
        ArgumentParser defining all the flags.
    """
    parser = commandline.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--object-files",
        action="append",
        type="file_exists",
        help="The object files that contain LLVM sections.",
    )
    parser.add_argument(
        "--output-dir",
        type="dir_exists",
        help="The dir to write the artifacts to.",
    )
    parser.add_argument(
        "--kernel-home",
        type="dir_exists",
        help="The directory for kernel files.",
    )

    return parser


def parse_arguments(argv: Optional[List[str]]) -> argparse.Namespace:
    """Parse and validate arguments.

    Args:
        argv: The command line to parse.

    Returns:
        Object holding attribute values.
    """
    parser = _get_parser()
    return parser.parse_args(argv)


def main(argv: Optional[List[str]]) -> Optional[int]:
    """Main."""
    opts = parse_arguments(argv)
    opts.Freeze()
    if opts.object_files:
        data = generate_llvm_artifacts(opts.object_files)
        (opts.output_dir / _COVERAGE_FILENAME).write_text(
            data, encoding="utf-8"
        )

    if opts.kernel_home:
        data = generate_kernel_artifacts(opts.kernel_home)
        for filename, content in data.items():
            (opts.output_dir / filename).write_text(content, encoding="utf-8")
