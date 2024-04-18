# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Show the builder layout for CrOS waterfalls."""

from chromite.lib import commandline
from chromite.lib import config_lib


def _ParseArguments(argv):
    parser = commandline.ArgumentParser(description=__doc__)

    opts = parser.parse_args(argv)
    opts.Freeze()
    return opts


def displayConfigs(label, configs):
    print("== %s ==" % label)

    for config in sorted(configs, key=lambda c: c.name):
        print("  %s" % config.name)
        if config.slave_configs:
            for sc in sorted(config.slave_configs):
                print("    %s" % sc)

    print()


def main(argv):
    _ = _ParseArguments(argv)

    site_config = config_lib.GetConfig()

    # Organize the builds as:
    #  {Display Label: [build_config]}

    labeled_builds = {}
    for config in site_config.values():
        if config.schedule:
            labeled_builds.setdefault(config.display_label, []).append(config)

    for label in sorted(labeled_builds.keys()):
        displayConfigs(label, labeled_builds[label])

    # Force the tryjob section to be last.
    displayConfigs(
        "tryjob",
        [c for c in site_config.values() if config_lib.isTryjobConfig(c)],
    )
