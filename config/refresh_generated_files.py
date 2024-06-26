# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility script to update the generated config files."""

import logging

from chromite.config import chromeos_config
from chromite.format import formatters
from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils


def main(argv):
    # Parse arguments to respect log levels.
    commandline.ArgumentParser().parse_args(argv)

    # Regenerate `config_dump.json`.
    logging.info("Regenerating config_dump.json")
    site_config = chromeos_config.GetConfig()
    site_config.SaveConfigToFile(constants.CHROMEOS_CONFIG_FILE)

    # Regenerate `waterfall_layout_dump.txt`.
    logging.info("Regenerating waterfall_layout_dump.txt")
    cmd = constants.CHROMITE_BIN_DIR / "cros_show_waterfall_layout"
    result = cros_build_lib.run(
        [cmd], capture_output=True, encoding="utf-8", debug_level=logging.DEBUG
    )
    waterfall_data = formatters.whitespace.Data(result.stdout)
    osutils.WriteFile(constants.WATERFALL_CONFIG_FILE, waterfall_data)

    # Regenerate `luci-scheduler.cfg`.
    logging.info("Regenerating luci-scheduler.cfg")
    cmd = constants.CHROMITE_SCRIPTS_DIR / "gen_luci_scheduler"
    luci_result = cros_build_lib.run(
        [cmd], capture_output=True, encoding="utf-8", debug_level=logging.DEBUG
    )
    osutils.WriteFile(constants.LUCI_SCHEDULER_CONFIG_FILE, luci_result.stdout)
