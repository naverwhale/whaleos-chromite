# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for Firmware operations."""

import os
from unittest import mock

from chromite.api import api_config
from chromite.api.controller import firmware
from chromite.api.gen.chromite.api import firmware_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import constants
from chromite.lib import cros_test_lib


class BuildAllFirmwareTestCase(
    cros_test_lib.RunCommandTempDirTestCase, api_config.ApiConfigMixin
):
    """BuildAllFirmware tests."""

    def setUp(self):
        self.chroot_path = "/path/to/chroot"

    def _GetInput(
        self,
        chroot_path=None,
        fw_location=common_pb2.PLATFORM_EC,
        code_coverage=False,
    ):
        """Helper for creating input message."""
        proto = firmware_pb2.BuildAllFirmwareRequest(
            firmware_location=fw_location,
            chroot={"path": chroot_path},
            code_coverage=code_coverage,
        )
        return proto

    def testBuildAllFirmware(self):
        """Test endpoint by verifying call to cros_build_lib.run."""
        for fw_loc in common_pb2.FwLocation.values():
            fw_path = firmware.get_fw_loc(fw_loc)
            if not fw_path:
                continue
            request = self._GetInput(
                chroot_path=self.chroot_path,
                fw_location=fw_loc,
                code_coverage=True,
            )
            response = firmware_pb2.BuildAllFirmwareResponse()
            # Call the method under test.
            firmware.BuildAllFirmware(request, response, self.api_config)
            # Because we mock out the function, we verify that it is called as
            # we expect it to be called.
            called_function = os.path.join(
                constants.SOURCE_ROOT, fw_path, "firmware_builder.py"
            )
            self.rc.assertCommandCalled(
                [
                    called_function,
                    "--metrics",
                    mock.ANY,
                    "--code-coverage",
                    "build",
                ],
                check=False,
            )

    def testValidateOnly(self):
        """Verify a validate-only call does not execute any logic."""
        for fw_loc in common_pb2.FwLocation.values():
            if not firmware.get_fw_loc(fw_loc):
                continue
            request = self._GetInput(
                chroot_path=self.chroot_path,
                fw_location=fw_loc,
                code_coverage=True,
            )
            response = firmware_pb2.BuildAllFirmwareResponse()
            firmware.BuildAllFirmware(
                request, response, self.validate_only_config
            )
            self.assertFalse(self.rc.called)

    def testMockCall(self):
        """Test a mock call does not execute logic, returns mocked value."""
        for fw_loc in common_pb2.FwLocation.values():
            if not firmware.get_fw_loc(fw_loc):
                continue
            request = self._GetInput(
                chroot_path=self.chroot_path,
                fw_location=fw_loc,
                code_coverage=True,
            )
            response = firmware_pb2.BuildAllFirmwareResponse()
            firmware.BuildAllFirmware(request, response, self.mock_call_config)
            self.assertFalse(self.rc.called)
            self.assertEqual(len(response.metrics.value), 1)
            self.assertEqual(response.metrics.value[0].target_name, "foo")
            self.assertEqual(response.metrics.value[0].platform_name, "bar")
            self.assertEqual(len(response.metrics.value[0].fw_section), 1)
            self.assertEqual(
                response.metrics.value[0].fw_section[0].region, "EC_RO"
            )
            self.assertEqual(response.metrics.value[0].fw_section[0].used, 100)
            self.assertEqual(response.metrics.value[0].fw_section[0].total, 150)
