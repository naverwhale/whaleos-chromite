# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module tests the cros build command."""

from unittest import mock

from chromite.cli import command_unittest
from chromite.cli.cros import cros_telemetry
from chromite.lib import chromite_config
from chromite.lib import cros_test_lib
from chromite.utils import telemetry


pytestmark = cros_test_lib.pytestmark_inside_only


class MockTelemetryCommand(command_unittest.MockCommand):
    """Mock out the telemetry command."""

    TARGET = "chromite.cli.cros.cros_telemetry.TelemetryCommand"
    TARGET_CLASS = cros_telemetry.TelemetryCommand


class TelemetryCommandTest(cros_test_lib.MockTempDirTestCase):
    """Test class for our TelemetryCommand class."""

    def testEnableTelemetry(self):
        """Test that telemetry is marked as enabled in cfg."""

        file = self.tempdir / "telemetry.cfg"

        config_initialize_mock = self.PatchObject(chromite_config, "initialize")
        with mock.patch("chromite.lib.chromite_config.TELEMETRY_CONFIG", file):
            cmd = MockTelemetryCommand(["--enable"])
            cmd.inst.Run()

        cfg = telemetry.config.Config(path=file)
        self.assertTrue(config_initialize_mock.called)
        self.assertTrue(cfg.trace_config.has_enabled())
        self.assertTrue(cfg.trace_config.enabled)
        self.assertEqual("USER", cfg.trace_config.enabled_reason)

    def testDisableTelemetry(self):
        """Test that telemetry is marked as disabled in cfg."""

        file = self.tempdir / "telemetry.cfg"

        config_initialize_mock = self.PatchObject(chromite_config, "initialize")
        with mock.patch("chromite.lib.chromite_config.TELEMETRY_CONFIG", file):
            cmd = MockTelemetryCommand(["--disable"])
            cmd.inst.Run()

        cfg = telemetry.config.Config(path=file)
        self.assertTrue(config_initialize_mock.called)
        self.assertTrue(cfg.trace_config.has_enabled())
        self.assertFalse(cfg.trace_config.enabled)
        self.assertEqual("USER", cfg.trace_config.enabled_reason)
