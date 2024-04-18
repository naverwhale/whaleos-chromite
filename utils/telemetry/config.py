# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides telemetry configuration utilities."""

import configparser
import os
from typing import Literal


ROOT_SECTION_KEY = "root"
NOTICE_COUNTDOWN_KEY = "notice_countdown"
ENABLED_KEY = "enabled"
ENABLED_REASON_KEY = "enabled_reason"
TRACE_SECTION_KEY = "trace"
DEFAULT_CONFIG = {
    ROOT_SECTION_KEY: {NOTICE_COUNTDOWN_KEY: 10},
    TRACE_SECTION_KEY: {},
}


class TraceConfig:
    """Tracing specific config in Telemetry config."""

    def __init__(self, config):
        self._config = config

    def update(self, enabled: bool, reason: Literal["AUTO", "USER"]):
        """Update the config."""
        self._config.set(TRACE_SECTION_KEY, ENABLED_KEY, str(enabled))
        self._config.set(TRACE_SECTION_KEY, ENABLED_REASON_KEY, reason)

    def has_enabled(self) -> bool:
        """Checks if the enabled property exists in config."""

        return ENABLED_KEY in self._config[TRACE_SECTION_KEY]

    @property
    def enabled(self) -> bool:
        """Value of trace.enabled property in telemetry.cfg."""

        return self._config[TRACE_SECTION_KEY].getboolean(ENABLED_KEY, False)

    @property
    def enabled_reason(self) -> Literal["AUTO", "USER"]:
        """Value of trace.enabled_reason property in telemetry.cfg."""

        return self._config[TRACE_SECTION_KEY].get(ENABLED_REASON_KEY, "AUTO")


class RootConfig:
    """Root configs in Telemetry config."""

    def __init__(self, config):
        self._config = config

    def update(self, notice_countdown: int):
        """Update the config."""
        self._config.set(
            ROOT_SECTION_KEY, NOTICE_COUNTDOWN_KEY, str(notice_countdown)
        )

    @property
    def notice_countdown(self) -> int:
        """Value for root.notice_countdown property in telemetry.cfg."""

        return self._config[ROOT_SECTION_KEY].getint(NOTICE_COUNTDOWN_KEY, 10)


class Config:
    """Telemetry configuration."""

    def __init__(self, path: os.PathLike):
        self._path = path
        self._config = configparser.ConfigParser()

        self._config.read_dict(DEFAULT_CONFIG)
        if not os.path.exists(path):
            self.flush()
        else:
            with open(path, "r", encoding="utf-8") as configfile:
                self._config.read_file(configfile)

        self._trace_config = TraceConfig(self._config)
        self._root_config = RootConfig(self._config)

    def flush(self):
        """Flushes the current config to confi file."""
        with open(self._path, "w", encoding="utf-8") as configfile:
            self._config.write(configfile)

    @property
    def root_config(self) -> RootConfig:
        """The root config in telemetry."""

        return self._root_config

    @property
    def trace_config(self) -> TraceConfig:
        """The trace config in telemetry."""

        return self._trace_config
