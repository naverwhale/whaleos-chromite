# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Unittests for Firmware operations."""

import os
from unittest import mock

from chromite.third_party.google.protobuf import json_format

from chromite.api import api_config
from chromite.api.controller import firmware
from chromite.api.gen.chromite.api import firmware_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib


class BuildAllFirmwareTestCase(cros_test_lib.MockTempDirTestCase,
                               api_config.ApiConfigMixin):
  """BuildAllFirmware tests."""

  def setUp(self):
    self.chroot_path = '/path/to/chroot'
    self.cros_build_run_patch = self.PatchObject(
        cros_build_lib,
        'run',
        return_value=cros_build_lib.CommandResult(returncode=0))

  def _GetInput(self,
                chroot_path=None,
                fw_location=common_pb2.PLATFORM_EC,
                code_coverage=False):
    """Helper for creating input message."""
    proto = firmware_pb2.BuildAllFirmwareRequest(
        firmware_location=fw_location,
        chroot={'path': chroot_path},
        code_coverage=code_coverage)
    return proto

  def testBuildAllFirmware(self):
    """Test invocation of endpoint by verifying call to cros_build_lib.run."""
    request = self._GetInput(chroot_path=self.chroot_path, code_coverage=True)
    # TODO(mmortensen): Consider refactoring firmware._call_entry code (perhaps
    # putting the parsing of the output file in a function) so that we don't
    # have to mock something as generic as 'json_format.Parse' to avoid an
    # error on parsing an empty(due to mock call) file.
    json_format_patch = self.PatchObject(json_format, 'Parse')
    response = firmware_pb2.BuildAllFirmwareResponse()
    # Call the method under test.
    firmware.BuildAllFirmware(request, response, self.api_config)
    # Because we mock out the function, we verify that it is called as we
    # expect it to be called.
    called_function = os.path.join(constants.SOURCE_ROOT,
                                   'src/platform/ec/firmware_builder.py')
    self.cros_build_run_patch.assert_called_with(
        [called_function, '--metrics', mock.ANY, '--code-coverage', 'build'],
        check=False)
    # Verify that we try to parse the metrics file.
    json_format_patch.assert_called()

  def testValidateOnly(self):
    """Sanity check that a validate only call does not execute any logic."""
    request = self._GetInput(chroot_path=self.chroot_path, code_coverage=True)
    response = firmware_pb2.BuildAllFirmwareResponse()
    firmware.BuildAllFirmware(request, response, self.validate_only_config)
    self.cros_build_run_patch.assert_not_called()

  def testMockCall(self):
    """Test that a mock call does not execute logic, returns mocked value."""
    request = self._GetInput(chroot_path=self.chroot_path, code_coverage=True)
    response = firmware_pb2.BuildAllFirmwareResponse()
    firmware.BuildAllFirmware(request, response, self.mock_call_config)
    self.cros_build_run_patch.assert_not_called()
    self.assertEqual(len(response.metrics.value), 1)
    self.assertEqual(response.metrics.value[0].target_name, 'foo')
    self.assertEqual(response.metrics.value[0].platform_name, 'bar')
    self.assertEqual(len(response.metrics.value[0].fw_section), 1)
    self.assertEqual(response.metrics.value[0].fw_section[0].region, 'EC_RO')
    self.assertEqual(response.metrics.value[0].fw_section[0].used, 100)
    self.assertEqual(response.metrics.value[0].fw_section[0].total, 150)
