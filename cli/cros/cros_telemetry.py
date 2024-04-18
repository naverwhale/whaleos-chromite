# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""cros telemetry: Manage telemetry options."""

import logging

from chromite.cli import command
from chromite.lib import chromite_config
from chromite.utils.telemetry import config


@command.command_decorator("telemetry")
class TelemetryCommand(command.CliCommand):
    """Manage telemetry related options."""

    @classmethod
    def AddParser(cls, parser):
        super(cls, TelemetryCommand).AddParser(parser)
        opts = parser.add_mutually_exclusive_group(required=True)
        opts.add_argument(
            "--enable",
            help="Enable telemetry collection.",
            action="store_true",
        )
        opts.add_argument(
            "--disable",
            help="Disable telemetry collection.",
            action="store_true",
        )
        opts.add_argument(
            "--show",
            help="Show telemetry related information.",
            action="store_true",
        )

    def _UpdateTelemetry(self, enable: bool):
        chromite_config.initialize()
        cfg = config.Config(chromite_config.TELEMETRY_CONFIG)
        cfg.trace_config.update(enabled=enable, reason="USER")
        cfg.flush()

    def _ShowTelemetry(self):
        chromite_config.initialize()
        cfg = config.Config(chromite_config.TELEMETRY_CONFIG)

        if cfg.trace_config.has_enabled():
            print(f"enabled = {cfg.trace_config.enabled}")
            print(f"enabled_reason = {cfg.trace_config.enabled_reason}")
        else:
            print(f"notice_countdown = {cfg.root_config.notice_countdown}")

    def Run(self):
        """Run cros telemetry."""

        if self.options.enable:
            self._UpdateTelemetry(enable=True)
            logging.notice("Telemetry enabled successfully.")

        if self.options.disable:
            self._UpdateTelemetry(enable=False)
            logging.notice("Telemetry disabled successfully.")

        if self.options.show:
            self._ShowTelemetry()
