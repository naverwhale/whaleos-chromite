# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for remoteexec_util.py"""

from pathlib import Path

from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import remoteexec_util


class TestRemoteexecUtil(
    cros_test_lib.MockTempDirTestCase, cros_test_lib.RunCommandTestCase
):
    """Tests for remoteexec_util."""

    def setUp(self):
        self.reclient_dir = self.tempdir / "cipd" / "rbe"
        self.reproxy_cfg_file = (
            self.tempdir / "reclient_cfgs" / "reproxy_config.cfg"
        )

        osutils.SafeMakedirs(self.reclient_dir)
        osutils.SafeMakedirs(self.reproxy_cfg_file)

        self.remote = remoteexec_util.Remoteexec(
            self.reclient_dir, self.reproxy_cfg_file
        )

    def testExtraEnvCustomChroot(self):
        """Test that the extra chroot envs for remoteexec are correct."""
        chroot_env = self.remote.GetChrootExtraEnv()
        self.assertEndsWith(chroot_env["RECLIENT_DIR"], "/reclient")
        self.assertEndsWith(chroot_env["REPROXY_CFG"], "/reproxy_chroot.cfg")

    def testInvalidArg(self):
        """Test the remoteexec with invalid argument."""
        with self.assertRaises(ValueError):
            remoteexec_util.Remoteexec(
                Path("/some/path"), self.reproxy_cfg_file
            )
        with self.assertRaises(ValueError):
            remoteexec_util.Remoteexec(self.reclient_dir, "some_conf_file")

    def testRemoteExecCommand(self):
        """Test the remoteexec command interface."""
        bootstrap_cmd = self.reclient_dir / "bootstrap"
        reproxy_cmd = self.reclient_dir / "reproxy"

        self.remote.Start()
        self.assertCommandCalled(
            [
                bootstrap_cmd,
                "--cfg",
                self.reproxy_cfg_file,
                "--re_proxy",
                reproxy_cmd,
            ]
        )
        self.remote.Stop()
        self.assertCommandCalled(
            [
                bootstrap_cmd,
                "--cfg",
                self.reproxy_cfg_file,
                "--re_proxy",
                reproxy_cmd,
                "--shutdown",
            ]
        )
