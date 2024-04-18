# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test for chromite qemu logic"""

import filecmp
import glob
import os
import tempfile

from chromite.lib import cros_test_lib
from chromite.lib import qemu


class QemuTests(cros_test_lib.TestCase):
    """Verify Qemu logic works"""

    def testArchDetect(self):
        """Verify we correctly probe each arch"""
        test_dir = os.path.join(
            os.path.realpath(os.path.dirname(__file__)), "datafiles"
        )
        test_files = os.path.join(test_dir, "arch.*.elf")

        for test in glob.glob(test_files):
            test_file = os.path.basename(test)
            exp_arch = test_file.split(".")[1]

            arch = qemu.Qemu.DetectArch(test_file, test_dir)
            if arch is None:
                # See if we have a mask for it.
                # pylint: disable=protected-access
                self.assertNotIn(
                    exp_arch,
                    list(qemu.Qemu._MAGIC_MASK),
                    msg='ELF "%s" did not match "%s", but should have'
                    % (test, exp_arch),
                )
            else:
                self.assertEqual(arch, exp_arch)

    def testArmRegisterStr(self):
        """Make sure the register string is exact.

        We don't check every arch, just one to make sure the general logic is
        OK.
        """
        exp = (
            b":foo:M::"
            b"\x7fELF\x01\x01\x01!\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\x02"
            b"\\x00(\\x00:\xff\xff\xff\xff\xff\xff\xff\\x00\xff\xff\xff\xff\xff"
            b"\xff\xff\xff\xfe\xff\xff\xff:"
            b"/pfx-binfmt-wrapper:POC"
        )
        self.assertEqual(
            exp, qemu.Qemu.GetRegisterBinfmtStr("arm", "foo", "/pfx")
        )

    def testRegisterStrLengths(self):
        """Verify the binfmt register string doesn't exceed kernel limits"""
        # pylint: disable=protected-access
        for arch in qemu.Qemu._MAGIC_MASK.keys():
            name = "qemu-%s" % arch
            interp = "/build/bin/%s" % name
            register = qemu.Qemu.GetRegisterBinfmtStr(arch, name, interp)
            self.assertGreaterEqual(
                256,
                len(register),
                msg='arch "%s" has too long of a register string:'
                " %i: %r" % (arch, len(register), register),
            )

    def testFullInterpPath(self):
        """Sanity check for the interp helper."""
        self.assertNotEqual("", qemu.Qemu.GetFullInterpPath("foo"))

    def testInstall(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = "/usr/bin/qemu-arm"
            dst_dir = os.path.join(tmpdir, "build", "bin")
            dst = os.path.join(dst_dir, "qemu-arm")

            os.makedirs(dst_dir)
            qemu.Qemu(sysroot=tmpdir, arch="arm").Install()
            self.assertTrue(filecmp.cmp(src, dst, shallow=False))

            # Second time shouldn't update anything, but it should still work.
            qemu.Qemu(sysroot=tmpdir, arch="arm").Install()
            self.assertTrue(filecmp.cmp(src, dst, shallow=False))
