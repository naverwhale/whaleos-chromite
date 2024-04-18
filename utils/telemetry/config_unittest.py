# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the telemetry config."""

import configparser

from chromite.lib import cros_test_lib
from chromite.utils.telemetry import config


class ConfigTest(cros_test_lib.TempDirTestCase):
    """Test Config class."""

    def test_create_missing_config_file(self):
        """Test Config to create missing config file."""

        path = self.tempdir / "telemetry.cfg"
        cfg = config.Config(path)

        self.assertFileContents(
            path, "[root]\nnotice_countdown = 10\n\n[trace]\n\n"
        )
        self.assertFalse(cfg.trace_config.enabled)
        self.assertFalse(cfg.trace_config.has_enabled())
        self.assertEqual("AUTO", cfg.trace_config.enabled_reason)
        self.assertEqual(10, cfg.root_config.notice_countdown)

    def test_load_config_file(self):
        """Test Config to load config file."""

        path = "telemetry.cfg"
        self.WriteTempFile(
            path, "[root]\nnotice_countdown = 3\n\n[trace]\nenabled = True\n\n"
        )

        path = self.tempdir / path
        cfg = config.Config(path)

        self.assertTrue(cfg.trace_config.enabled)
        self.assertEqual(3, cfg.root_config.notice_countdown)

    def test_flush_config_file_with_updates(self):
        """Test Config to write the config changes to file."""

        path = self.tempdir / "telemetry.cfg"
        self.WriteTempFile(
            path, "[root]\nnotice_countdown = 7\n\n[trace]\nenabled = True\n\n"
        )

        cfg = config.Config(path)

        cfg.trace_config.update(enabled=False, reason="AUTO")
        cfg.root_config.update(notice_countdown=9)
        cfg.flush()

        self.assertFileContents(
            path,
            "\n".join(
                [
                    "[root]",
                    "notice_countdown = 9",
                    "",
                    "[trace]",
                    "enabled = False",
                    "enabled_reason = AUTO",
                    "",
                    "",
                ]
            ),
        )


def test_default_trace_config():
    """Test TraceConfig to load default values."""
    cfg = configparser.ConfigParser()
    cfg[config.TRACE_SECTION_KEY] = {}
    trace_config = config.TraceConfig(cfg)

    assert not trace_config.has_enabled()


def test_trace_config_update():
    """Test TraceConfig to update values."""
    cfg = configparser.ConfigParser()
    cfg[config.TRACE_SECTION_KEY] = {config.ENABLED_KEY: True}
    trace_config = config.TraceConfig(cfg)
    trace_config.update(enabled=False, reason="AUTO")
    assert not trace_config.enabled
    assert trace_config.enabled_reason == "AUTO"


def test_trace_config():
    """Test TraceConfig to instantiate from passed dict."""
    cfg = configparser.ConfigParser()
    cfg[config.TRACE_SECTION_KEY] = {config.ENABLED_KEY: True}
    trace_config = config.TraceConfig(cfg)

    assert trace_config.enabled
    assert trace_config.has_enabled()
    assert trace_config.enabled_reason == "AUTO"


def test_default_root_config():
    """Test RootConfig to load default values."""
    cfg = configparser.ConfigParser()
    cfg[config.ROOT_SECTION_KEY] = {}
    root_config = config.RootConfig(cfg)

    assert root_config.notice_countdown == 10


def test_root_config_update():
    """Test RootConfig to update values."""
    cfg = configparser.ConfigParser()
    cfg[config.ROOT_SECTION_KEY] = {config.NOTICE_COUNTDOWN_KEY: True}
    root_config = config.RootConfig(cfg)
    root_config.update(notice_countdown=8)
    assert root_config.notice_countdown == 8


def test_root_config():
    """Test RootConfig to instantiate from passed dict."""
    cfg = configparser.ConfigParser()
    cfg[config.ROOT_SECTION_KEY] = {config.NOTICE_COUNTDOWN_KEY: 9}
    root_config = config.RootConfig(cfg)

    assert root_config.notice_countdown == 9
