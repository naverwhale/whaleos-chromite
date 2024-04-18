# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for compdb_no_chroot.py.
"""

import json
import os
from pathlib import Path
import sys

import compdb_no_chroot


sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."),
)
# pylint: disable=wrong-import-position
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib


# pylint: enable=wrong-import-position


EXT_TRUNK_PATH = "/usr/local/google/home/oka/os2"


def custom_which(exe: str) -> str:
    if exe == "armv7a-cros-linux-gnueabihf-clang++":
        return os.path.join("usr/bin", exe)
    raise Exception(f"Unexpected exe {exe}")


class GenerateTest(cros_test_lib.RunCommandTempDirTestCase):
    """Tests generate()"""

    def testAll(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        chroot = chroot_lib.Chroot(
            path=Path(EXT_TRUNK_PATH) / constants.DEFAULT_CHROOT_DIR,
            out_path=Path(EXT_TRUNK_PATH) / constants.DEFAULT_OUT_DIR,
        )

        build_path = chroot.full_path("build")

        testdata = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "compdb_no_chroot_testdata",
        )

        input_dir = os.path.join(testdata, "input")
        expected_dir = os.path.join(testdata, "expected")
        for name in os.listdir(input_dir):
            with open(os.path.join(input_dir, name), "rb") as f:
                given = json.load(f)

            expected_file = os.path.join(expected_dir, name)
            with open(expected_file, encoding="utf-8") as f:
                s = f.read()
                s = s.replace("<BUILD_DIR>", build_path)
                expected = json.loads(s)

            got = compdb_no_chroot.generate(given, EXT_TRUNK_PATH, custom_which)

            try:
                self.assertEqual(got, expected)
            except Exception as e:
                # You can uncomment the following code to update the golden file
                # so that manual modification is not needed.
                #
                # with open(expected_file, "w", encoding="utf-8") as outfile:
                #     s = json.dumps(got, indent=2, sort_keys=True)
                #     s = s.replace(build_path, "<BUILD_DIR>")
                #     outfile.write(s)

                raise e
