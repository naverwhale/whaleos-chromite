# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests the chroot_util module."""

import itertools

from chromite.lib import chroot_util
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.utils import os_util


pytestmark = cros_test_lib.pytestmark_inside_only

if cros_build_lib.IsInsideChroot():
    from chromite.scripts import cros_list_modified_packages


class ChrootUtilTest(cros_test_lib.RunCommandTempDirTestCase):
    """Test class for the chroot_util functions."""

    def testEmerge(self):
        """Tests correct invocation of emerge."""
        packages = ["foo-app/bar", "sys-baz/clap"]
        self.PatchObject(
            cros_list_modified_packages,
            "ListModifiedWorkonPackages",
            return_value=[packages[0]],
        )

        toolchain_packages = [
            "sys-devel/binutils",
            "sys-devel/gcc",
            "sys-kernel/linux-headers",
            "sys-libs/glibc",
            "sys-devel/gdb",
        ]
        self.PatchObject(
            chroot_util,
            "_GetToolchainPackages",
            return_value=toolchain_packages,
        )
        toolchain_package_list = " ".join(toolchain_packages)

        input_values = [
            ["/", "/build/thesysrootname"],  # sysroot
            [True, False],  # with_deps
            [True, False],  # rebuild_deps
            [True, False],  # use_binary
            [0, 1, 2, 3],  # jobs
            [True, False],  # debug_output
        ]
        inputs = itertools.product(*input_values)
        for (
            sysroot,
            with_deps,
            rebuild_deps,
            use_binary,
            jobs,
            debug_output,
        ) in inputs:
            chroot_util.Emerge(
                packages,
                sysroot=sysroot,
                with_deps=with_deps,
                rebuild_deps=rebuild_deps,
                use_binary=use_binary,
                jobs=jobs,
                debug_output=debug_output,
            )
            cmd = self.rc.call_args_list[-1][0][-1]
            self.assertEqual(
                sysroot != "/", any(str(p).startswith("--sysroot") for p in cmd)
            )
            self.assertEqual(with_deps, "--deep" in cmd)
            self.assertEqual(not with_deps, "--nodeps" in cmd)
            self.assertEqual(rebuild_deps, "--rebuild-if-unbuilt" in cmd)
            self.assertEqual(use_binary, "-g" in cmd)
            self.assertEqual(use_binary, "--with-bdeps=y" in cmd)
            self.assertEqual(
                use_binary and sysroot == "/",
                "--useoldpkg-atoms=%s" % toolchain_package_list in cmd,
            )
            self.assertEqual(bool(jobs), "--jobs=%d" % jobs in cmd)
            self.assertEqual(debug_output, "--show-output" in cmd)

    def testRunUnittests(self):
        """Tests running unit tests invoking emerge with provided flags"""

        self.PatchObject(os_util, "is_root_user", return_value=True)
        chroot_util.RunUnittests(
            sysroot="/sysroot/",
            packages=["package1", "package2"],
            extra_env={
                "USE": "chrome_internal coverage",
                "FEATURES": "noclean",
            },
            keep_going=True,
        )
        self.rc.assertCommandCalled(
            [
                constants.CHROMITE_BIN_DIR / "parallel_emerge",
                "--sysroot=/sysroot/",
                "--keep-going=y",
                "package1",
                "package2",
            ],
            extra_env={
                "USE": "chrome_internal coverage",
                "FEATURES": "noclean test",
                "PKGDIR": "/sysroot/tmp/test-packages",
            },
        )
