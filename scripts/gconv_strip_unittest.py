# Copyright 2018 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test gconv_strip.

To run these tests, do the following inside the chroot:
$ pytest -c /dev/null scripts/gconv_strip_unittest.py

Explicitly using an empty pytest config is necessary because chromite's
pytest.ini assumes pytest-xdist is installed, which it is not inside the chroot.
"""

import glob
import os

from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.scripts import gconv_strip


pytestmark = cros_test_lib.pytestmark_inside_only


class GconvStripTest(cros_test_lib.MockTempDirTestCase):
    """Tests for gconv_strip script."""

    def testMultipleStringMatch(self):
        self.assertEqual(
            gconv_strip.MultipleStringMatch(
                [b"hell", b"a", b"z", b"k", b"spec"],
                b"hello_from a very special place",
            ),
            [True, True, False, False, True],
        )

    def testModuleRewrite(self):
        tmp_gconv_module = os.path.join(self.tempdir, "gconv-modules")

        data = """
#      from          to            module         cost
alias  FOO           charset_foo
alias  BAR           charset_bar
module charset_foo   charset_bar   UNUSED_MODULE

#      from          to            module         cost
alias  CHAR_A        charset_A
alias  EUROPE        charset_B
module charset_A     charset_B     USED_MODULE
module charset_foo   charset_A     USED_MODULE
"""
        osutils.WriteFile(tmp_gconv_module, data)

        gmods = gconv_strip.GconvModules(
            tmp_gconv_module, os.path.dirname(tmp_gconv_module)
        )
        self.assertEqual(
            gmods.Load(),
            [
                "BAR",
                "CHAR_A",
                "EUROPE",
                "FOO",
                "charset_A",
                "charset_B",
                "charset_bar",
                "charset_foo",
            ],
        )
        self.PatchObject(gconv_strip.lddtree, "ParseELF", return_value={})

        class _StubStat:
            """Fake for lstat."""

            st_size = 0

        self.PatchObject(gconv_strip.os, "lstat", return_value=_StubStat)
        self.PatchObject(gconv_strip.os, "unlink")
        gmods.Rewrite(["charset_A", "charset_B"], dryrun=False)

        expected = """
#      from          to            module         cost
alias  FOO           charset_foo

#      from          to            module         cost
alias  CHAR_A        charset_A
alias  EUROPE        charset_B
module charset_A     charset_B     USED_MODULE
module charset_foo   charset_A     USED_MODULE
"""

        content = osutils.ReadFile(tmp_gconv_module)
        self.assertEqual(content, expected)

    def testGconvStrip(self):
        """Tests GconvStrip end-to-end.

        Creates a fake root directory with fake gconv modules, and expects the
        non-sticky modules to be deleted.
        """
        modules_dir = os.path.join(self.tempdir, "usr", "lib64", "gconv")
        extras_dir = os.path.join(modules_dir, "gconv-modules.d")
        os.makedirs(extras_dir)
        tmp_gconv_modules = os.path.join(modules_dir, "gconv-modules")
        tmp_gconv_extras = os.path.join(extras_dir, "gconv-modules-extras.conf")

        gconv_data = """
#       from                    to                      module          cost
alias   UTF32//                 UTF-32//
module  UTF-32//                INTERNAL                UTF-32          1
module  INTERNAL                UTF-32//                UTF-32          1

#       from                    to                      module          cost
alias   UTF7//                  UTF-7//
module  UTF-7//                 INTERNAL                UTF-7           1
module  INTERNAL                UTF-7//                 UTF-7           1
"""
        gconv_extras_data = """
#       from                    to                      module          cost
alias   UTF16//                 UTF-16//
module  UTF-16//                INTERNAL                UTF-16          1
module  INTERNAL                UTF-16//                UTF-16          1

#       from                    to                      module          cost
alias   EUCTW//                 EUC-TW//
alias   OSF0005000a//           EUC-TW//
module  EUC-TW//                INTERNAL                EUC-TW          1
module  INTERNAL                EUC-TW//                EUC-TW          1
"""
        osutils.WriteFile(tmp_gconv_modules, gconv_data)
        osutils.WriteFile(tmp_gconv_extras, gconv_extras_data)
        for module in ["UTF-32.so", "UTF-7.so", "UTF-16.so", "EUC-TW.so"]:
            osutils.Touch(os.path.join(modules_dir, module))

        self.PatchObject(gconv_strip.lddtree, "ParseELF", return_value={})

        class _StubOpts:
            """Stub for GconvStrip args."""

            def __init__(self, root):
                self.root = root
                self.dryrun = False

        gconv_strip.GconvStrip(_StubOpts(self.tempdir))

        expected_gconv_data = """
#       from                    to                      module          cost
alias   UTF32//                 UTF-32//
module  UTF-32//                INTERNAL                UTF-32          1
module  INTERNAL                UTF-32//                UTF-32          1

#       from                    to                      module          cost
"""
        expected_gconv_extras_data = """
#       from                    to                      module          cost
alias   UTF16//                 UTF-16//
module  UTF-16//                INTERNAL                UTF-16          1
module  INTERNAL                UTF-16//                UTF-16          1

#       from                    to                      module          cost
"""
        expected_modules = ["UTF-16.so", "UTF-32.so"]
        actual_gconv_data = osutils.ReadFile(tmp_gconv_modules)
        actual_gconv_extras_data = osutils.ReadFile(tmp_gconv_extras)
        actual_modules = glob.glob(os.path.join(modules_dir, "*.so"))
        actual_modules_names = sorted(
            os.path.basename(x) for x in actual_modules
        )
        self.assertEqual(actual_gconv_data, expected_gconv_data)
        self.assertEqual(actual_gconv_extras_data, expected_gconv_extras_data)
        self.assertEqual(actual_modules_names, expected_modules)
