# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for sdk_builder."""

from pathlib import Path

from chromite.lib import chromeos_version
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import sdk_builder_lib


class BuildSdkTarballTest(cros_test_lib.MockTempDirTestCase):
    """Tests for BuildSdkTarball."""

    def testSuccess(self):
        cleaned_paths = set()
        tarball_path = [None]

        def _mock_cleanup(path: Path):
            cleaned_paths.add(path)

        def _mock_tar(tarball: Path, sdk: Path):
            self.assertIn(sdk, cleaned_paths)
            tarball_path[0] = tarball

        self.PatchObject(
            sdk_builder_lib,
            "CleanupMakeConfBoardSetup",
            side_effect=_mock_cleanup,
        )
        mock_tar = self.PatchObject(
            sdk_builder_lib, "CreateTarballForSdk", side_effect=_mock_tar
        )

        sdk_path = self.tempdir / "build" / "amd64-host"
        sdk_path.mkdir(exist_ok=True, parents=True)
        self.ExpectRootOwnedFiles()
        returned_tarball_path = sdk_builder_lib.BuildSdkTarball(
            sdk_path,
            "FAKE_VERSION",
        )
        mock_tar.assert_called_once_with(returned_tarball_path, sdk_path)


class CleanupMakeConfBoardSetupTest(cros_test_lib.MockTestCase):
    """Tests for CleanupMakeConfBoardSetup."""

    def testRemovesRootAndPkgConfig(self):
        BEFORE = """\
BOARD_OVERLAY="/mnt/host/source/src/private-overlays/chromeos-overlay"
BOARD_USE="amd64-host"
PKG_CONFIG="/build/amd64-host/build/bin/pkg-config"
PORTDIR_OVERLAY="/mnt/host/source/src/third_party/eclass-overlay"
ROOT="/build/amd64-host/"
"""
        EXPECTED = """\
BOARD_OVERLAY="/mnt/host/source/src/private-overlays/chromeos-overlay"
BOARD_USE="amd64-host"
PORTDIR_OVERLAY="/mnt/host/source/src/third_party/eclass-overlay"
"""
        self.PatchObject(
            sdk_builder_lib.osutils, "ReadFile", return_value=BEFORE
        )
        mock_write = self.PatchObject(sdk_builder_lib.osutils, "WriteFile")
        sdk_builder_lib.CleanupMakeConfBoardSetup(Path("/fictional"))
        mock_write.assert_called_once_with(
            Path("/fictional/etc/make.conf.board_setup"), EXPECTED, sudo=True
        )


class CreateTarballForSdkTest(cros_test_lib.TempDirTestCase):
    """Tests for CreateTarballForSdk."""

    def testSuccess(self):
        """Test CreateTarballForSdk.

        Test that CreateTarballForSdk packages up the expected files with
        the expected paths and permissions, and does not package up
        files that should be excluded.
        """
        # Create a fake chroot layout with some files in it.
        board_location = self.tempdir / "chroot/build/amd64-host"
        tarball_path = self.tempdir / "src/sdk.tar.xz"
        for x in ["bin", "tmp", "usr/lib", "usr/lib/debug"]:
            (board_location / x).mkdir(parents=True)
        (board_location / "bin/example").write_text(
            "example file\n", encoding="utf-8"
        )
        (board_location / "bin/example").chmod(0o755)
        (board_location / "tmp/tempfile").write_text(
            "temp file\n", encoding="utf-8"
        )
        (board_location / "usr/lib/debug/libxyz.so.dwp").write_bytes(
            b"\1\2\3\0"
        )
        tarball_path.parent.mkdir(parents=True)

        # Check that we successfully create the tarball.
        self.assertFalse(tarball_path.exists())
        sdk_builder_lib.CreateTarballForSdk(tarball_path, board_location)
        self.assertTrue(tarball_path.exists())

        # Check the contents of the tarball.
        t = self.tempdir / "extracted"
        t.mkdir(parents=True)
        cros_build_lib.ExtractTarball(tarball_path, t)
        self.assertEqual(
            (t / "bin/example").read_text(encoding="utf-8"), "example file\n"
        )
        self.assertEqual((t / "bin/example").stat().st_mode & 0o755, 0o755)
        self.assertTrue((t / "usr/lib").exists())
        self.assertFalse((t / "tmp/tempfile").exists())
        self.assertFalse((t / "usr/lib/debug/libxyz.so.dwp").exists())


def test_os_release(tmp_path_cleanup_sudo):
    output_path = tmp_path_cleanup_sudo / "os-release"
    version_info = chromeos_version.VersionInfo(
        version_string="12345.67.0",
        chrome_branch="123",
    )
    sdk_builder_lib.write_os_release(output_path, version_info, "FAKE_VERSION")
    contents = output_path.read_text(encoding="utf-8")
    assert (
        contents
        == """\
BUILD_ID=FAKE_VERSION
ID=cros_sdk
ID_LIKE=gentoo
NAME='CrOS SDK'
VERSION=123
VERSION_ID=12345.67.0
"""
    )
