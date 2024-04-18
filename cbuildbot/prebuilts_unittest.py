# Copyright 2014 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for prebuilts."""

import os

from chromite.cbuildbot import cbuildbot_unittest
from chromite.cbuildbot import prebuilts
from chromite.cbuildbot.stages import generic_stages_unittest
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils


DEFAULT_CHROME_BRANCH = "27"


# pylint: disable=protected-access
class PrebuiltTest(cros_test_lib.RunCommandTempDirTestCase):
    """Test general cbuildbot command methods."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        self._board = "test-board"
        self._buildroot = self.tempdir
        self._overlays = [
            "%s/src/third_party/chromiumos-overlay" % self._buildroot
        ]
        self._chroot = os.path.join(self._buildroot, "chroot")
        os.makedirs(os.path.join(self._buildroot, ".repo"))

    def testSdkPrebuilts(self):
        """Test UploadPrebuilts for SDK builds."""
        # A magical date for a magical time.
        version = "1994.04.02.000000"

        chroot = chroot_lib.Chroot(
            path=self._buildroot / constants.DEFAULT_CHROOT_DIR,
            out_path=self._buildroot / constants.DEFAULT_OUT_DIR,
        )

        # Fake out toolchains overlay tarballs.
        tarball_dir = chroot.full_path(constants.SDK_OVERLAYS_OUTPUT)
        osutils.SafeMakedirs(tarball_dir)

        toolchain_overlay_tarball_args = []
        # Sample toolchain combos, corresponding to x86-alex and daisy.
        toolchain_combos = (
            ("i686-pc-linux-gnu",),
            ("armv7a-cros-linux-gnueabi", "arm-none-eabi"),
        )
        for toolchains in [
            "-".join(sorted(combo)) for combo in toolchain_combos
        ]:
            tarball = "built-sdk-overlay-toolchains-%s.tar.xz" % toolchains
            tarball_path = os.path.join(tarball_dir, tarball)
            osutils.Touch(tarball_path)
            tarball_arg = "%s:%s" % (toolchains, tarball_path)
            toolchain_overlay_tarball_args.append(
                ["--toolchains-overlay-tarball", tarball_arg]
            )

        # Fake out toolchain tarballs.
        tarball_dir = chroot.full_path(constants.SDK_TOOLCHAINS_OUTPUT)
        osutils.SafeMakedirs(tarball_dir)

        toolchain_tarball_args = []
        for tarball_base in ("i686", "arm-none-eabi"):
            tarball = "%s.tar.xz" % tarball_base
            tarball_path = os.path.join(tarball_dir, tarball)
            osutils.Touch(tarball_path)
            tarball_arg = "%s:%s" % (tarball_base, tarball_path)
            toolchain_tarball_args.append(["--toolchain-tarball", tarball_arg])

        prebuilts.UploadPrebuilts(
            constants.CHROOT_BUILDER_TYPE,
            False,
            buildroot=self._buildroot,
            board=self._board,
            version=version,
        )
        self.assertCommandContains(
            [constants.CHROOT_BUILDER_TYPE, "gs://chromeos-prebuilt"]
        )

        self.assertCommandContains(
            [
                "--toolchains-overlay-upload-path",
                (
                    "1994/04/cros-sdk-overlay-toolchains-%%(toolchains)s-"
                    "%(version)s.tar.xz"
                ),
            ]
        )
        self.assertCommandContains(
            [
                "--toolchain-upload-path",
                "1994/04/%%(target)s-%(version)s.tar.xz",
            ]
        )
        for args in toolchain_overlay_tarball_args + toolchain_tarball_args:
            self.assertCommandContains(args)
        self.assertCommandContains(["--set-version", version])
        self.assertCommandContains(
            [
                "--prepackaged-tarball",
                os.path.join(self._buildroot, constants.SDK_TARBALL_NAME),
            ]
        )


# pylint: disable=too-many-ancestors
class BinhostConfWriterTest(
    generic_stages_unittest.RunCommandAbstractStageTestCase,
    cbuildbot_unittest.SimpleBuilderTestCase,
):
    """Tests for the BinhostConfWriter class."""

    cmd = "upload_prebuilts"
    RELEASE_TAG = "1234.5.6"
    VERSION = "R%s-%s" % (DEFAULT_CHROME_BRANCH, RELEASE_TAG)

    # Our API here is not great when it comes to kwargs passing.
    def _Prepare(
        self, bot_id=None, **kwargs
    ):  # pylint: disable=arguments-differ
        super()._Prepare(bot_id, **kwargs)
        self.cmd = os.path.join(
            self.build_root, constants.CHROMITE_BIN_SUBDIR, "upload_prebuilts"
        )
        self._run.options.prebuilts = True

    def _Run(self, build_config):
        """Prepare and run a BinhostConfWriter.

        Args:
            build_config: Name of build config to run for.
        """
        self._Prepare(build_config)
        confwriter = prebuilts.BinhostConfWriter(self._run)
        confwriter.Perform()

    def ConstructStage(self):
        pass

    def _VerifyResults(self, public_slave_boards=(), private_slave_boards=()):
        """Verify that the expected prebuilt commands were run.

        Do various assertions on the two RunCommands that were run by stage.
        There should be one private (--private) and one public (default) run.

        Args:
            public_slave_boards: List of public slave boards.
            private_slave_boards: List of private slave boards.
        """
        # TODO(mtennant): Add functionality in partial_mock to support more
        # flexible asserting.  For example here, asserting that '--sync-host'
        # appears in the command that did not include '--public'.

        # Some args are expected for any public run.
        if public_slave_boards:
            # It would be nice to confirm that --private is not in command, but
            # note that --sync-host should not appear in the --private command.
            cmd = [self.cmd, "--sync-binhost-conf", "--sync-host"]
            self.assertCommandContains(cmd, expected=True)

        # Some args are expected for any private run.
        if private_slave_boards:
            cmd = [self.cmd, "--sync-binhost-conf", "--private"]
            self.assertCommandContains(cmd, expected=True)

        # Assert public slave boards are mentioned in public run.
        for board in public_slave_boards:
            # This check does not actually confirm that this board was in the
            # public run rather than the private run, unfortunately.
            cmd = [self.cmd, "--slave-board", board]
            self.assertCommandContains(cmd, expected=True)

        # Assert private slave boards are mentioned in private run.
        for board in private_slave_boards:
            cmd = [self.cmd, "--slave-board", board, "--private"]
            self.assertCommandContains(cmd, expected=True)

        # We expect --set-version so long as build config has
        # manifest_version=True.
        self.assertCommandContains(
            [self.cmd, "--set-version", self.VERSION],
            expected=self._run.config.manifest_version,
        )
