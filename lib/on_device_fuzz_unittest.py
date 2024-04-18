# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test on_device_fuzz functions."""

from pathlib import Path
from unittest import mock

from chromite.lib import cros_test_lib
from chromite.lib import on_device_fuzz
from chromite.lib import partial_mock


class RemoteDeviceMock(partial_mock.PartialMock):
    """Mocks the RemoteDevice function."""

    TARGET = "chromite.lib.remote_access.RemoteDevice"
    ATTRS = ("Pingable", "IfFileExists", "mkdir", "run")

    def Pingable(self, _):
        return True

    def IfFileExists(self, _):
        return True

    def mkdir(self, *_, **__):
        return None

    def run(self, *_, **__):
        return None


class OnDeviceFuzzTest(cros_test_lib.RunCommandTestCase):
    """Tests on_device_fuzz functions."""

    def test_create_sysroot_tarball(self):
        """Test that we can call create_sysroot_tarball."""
        with mock.patch.object(
            on_device_fuzz, "sysroot_tarball_setup_checks"
        ) as checks:
            packages = ["shill", "typecd", "my_package"]
            output_path = Path("/some/chroot/path/tarball.tar.xz")
            result = on_device_fuzz.create_sysroot_tarball(
                packages, board="amd64-generic", output_path=output_path
            )
            self.assertEqual(result, output_path)
            checks.assert_called_once()

    def test_not_installed_packages(self):
        """Test that we catch packages that are not installed in the chroot."""
        with self.assertRaises(on_device_fuzz.SetupError):
            on_device_fuzz.sysroot_tarball_setup_checks(
                ["does123", "not456", "exist678"], Path("/build/amd64-generic")
            )

    def test_run_fuzzer_executable(self):
        """Test that we can call fuzzer executables on mock devices."""
        mock_device = RemoteDeviceMock()
        on_device_fuzz.run_fuzzer_executable(
            mock_device,
            Path("/path/to/chroot"),
            Path("/some/path/inside/chroot/executable"),
            libfuzzer_options={},
        )
