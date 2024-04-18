# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Spider to get all the use flags for all the profiles."""

from chromite.contrib.portage_explorer import spiderlib
from chromite.lib import constants
from chromite.lib import cros_build_lib


def execute(output: spiderlib.SpiderOutput):
    """Get use flags set for a profile from its make.defaults.

    Get the use flags from a profile's make.defaults and sort them by name.

    Args:
        output: SpiderOutput representing the final output from all the spiders.
    """
    for overlay in output.overlays:
        for profile in overlay.profiles:
            make_defaults_path = (
                constants.SOURCE_ROOT / profile.path / "make.defaults"
            )
            if make_defaults_path.exists():
                command = (
                    f"source {cros_build_lib.ShellQuote(make_defaults_path)};"
                    "echo ${USE}"
                )
                source_use = cros_build_lib.dbg_run(
                    command, shell=True, capture_output=True, encoding="utf-8"
                )
                flag_output = source_use.stdout.split()
                use_flags = {}
                for flag in flag_output:
                    flag_name = flag.strip("-")
                    use_flags[flag_name] = not flag.startswith("-")
                for flag_name in sorted(use_flags):
                    profile.use_flags.append(
                        spiderlib.ProfileUse(
                            flag_name, spiderlib.UseState(use_flags[flag_name])
                        )
                    )
