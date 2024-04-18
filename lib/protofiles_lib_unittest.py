# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the protofiles_lib module."""

from pathlib import Path

from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import protofiles_lib


class TestUprev(cros_test_lib.MockTempDirTestCase):
    """Test Uprev method."""

    def testSuccess(self):
        cros_path = self.tempdir
        package_path = (
            cros_path
            / "third_party/chromiumos-overlay/chromeos-base"
            / "protofiles"
        )
        # Create an initial ebuild file.
        ebuild_path = package_path / "protofiles-0.0.118.ebuild"
        ebuild_content = """CROS_WORKON_COMMIT=(
    "8e541f07f697cfb8efe47560ae810b4cb3628cce" # policy
    "4fdad30678093c984bd8b21258bbd0b2c993f60f" # private_membership
    "e2594b65e49b64b7fe100f7fd439ec93ff937a3d" # shell-encryption
)
CROS_WORKON_TREE=(
    "3c03e07aa0cb784fbcc63010ea32bf5cf856045e" # policy
    "fd684cbf81f159c94dde7ffa9ec4d8dac993d17c" # private_membership
    "3304467e89364e7636f4e213777926bfacf9d34a" # shell-encryption
)
"""
        osutils.Touch(ebuild_path, True)
        osutils.WriteFile(ebuild_path, ebuild_content, "w")
        # Create an initial version file.
        version_path = package_path / "files/VERSION"
        version_content = """MAJOR=120
MINOR=0
BUILD=6091
PATCH=0
"""
        osutils.Touch(version_path, True)
        osutils.WriteFile(version_path, version_content, "w")
        # Mock fetchers.
        protofiles_lib_obj = protofiles_lib.ProtofilesLib()
        fetch_latest_commit_hashes_return_value = {
            Path("policy"): "e2594b65e49b64b7fe100f7fd439ec93ff937a3d",
            Path(
                "private_membership"
            ): "8e541f07f697cfb8efe47560ae810b4cb3628cce",
            Path(
                "shell-encryption"
            ): "4fdad30678093c984bd8b21258bbd0b2c993f60f",
        }
        self.PatchObject(
            protofiles_lib_obj,
            "_FetchLatestCommitHashes",
            return_value=fetch_latest_commit_hashes_return_value,
        )
        fetch_chrome_version_return_value = b"""MAJOR=120
MINOR=0
BUILD=6095
PATCH=0
"""
        self.PatchObject(
            protofiles_lib_obj,
            "_FetchChromeVersion",
            return_value={fetch_chrome_version_return_value},
        )

        protofiles_lib_obj.Uprev(cros_path)

        new_ebuild_path = package_path / "protofiles-0.0.119.ebuild"
        self.assertExists(new_ebuild_path)
        self.assertNotExists(ebuild_path)
        expected_ebuild_content = """CROS_WORKON_COMMIT=(
    "e2594b65e49b64b7fe100f7fd439ec93ff937a3d" # policy
    "8e541f07f697cfb8efe47560ae810b4cb3628cce" # private_membership
    "4fdad30678093c984bd8b21258bbd0b2c993f60f" # shell-encryption
)
CROS_WORKON_TREE=(
    "e2594b65e49b64b7fe100f7fd439ec93ff937a3d" # policy
    "8e541f07f697cfb8efe47560ae810b4cb3628cce" # private_membership
    "4fdad30678093c984bd8b21258bbd0b2c993f60f" # shell-encryption
)
"""
        expected_version_content = str(
            fetch_chrome_version_return_value, "utf-8"
        )
        modified_ebuild_content = osutils.ReadFile(new_ebuild_path)
        modified_version_content = osutils.ReadFile(version_path)
        self.assertEqual(modified_ebuild_content, expected_ebuild_content)
        self.assertEqual(modified_version_content, expected_version_content)
