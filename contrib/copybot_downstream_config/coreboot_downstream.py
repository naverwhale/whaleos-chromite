# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""CR and CQ +2 copybot project commits for downstreaming.

See go/copybot

For coreboot Downstreaming Rotation: go/coreboot:downstreaming
"""

from typing import Callable, List, Tuple

from chromite.contrib import copybot_downstream
from chromite.contrib.copybot_downstream_config import downstream_argparser


COREBOOT_DOWNSTREAMER_REVIEW_PATHS = [
    "src/security/vboot",
    "util/bincfg",
    "util/abuild",
    "util/crossgcc",
]

COREBOOT_DOMAIN_RESTRICTED_PATHS = [
    [
        "src/soc/amd",
        ["@amd.com", "@amd.corp-partner.google.com", "@google.com"],
    ],
    [
        "src/soc/intel",
        ["@intel.com", "@intel.corp-partner.google.com", "@google.com"],
    ],
    [
        "src/soc/mediatek",
        ["@mediatek.com", "@mediatek.corp-partner.google.com", "@google.com"],
    ],
    [
        "src/soc/qualcomm",
        ["@qualcomm.com", "@qualcomm.corp-partner.google.com", "@google.com"],
    ],
    ["src/mainboard/google", ["@google.com"]],
]


class CorebootDownstream(copybot_downstream.CopybotDownstream):
    """Class for extending copybot downstreaming class for coreboot."""

    def _project_check_funcs(self) -> List[List[Tuple[Callable, List]]]:
        """Return a list of checkers specific to Coreboot."""
        return [
            [
                self.project_passed_downstreamer_review_paths_check,
                COREBOOT_DOWNSTREAMER_REVIEW_PATHS,
            ],
            [
                self.project_passed_domain_restricted_paths_check,
                COREBOOT_DOMAIN_RESTRICTED_PATHS,
            ],
        ]


def main(args):
    """Main entry point for CLI."""
    parser = downstream_argparser.generate_copybot_arg_parser("coreboot")
    opts = parser.parse_args(args)
    CorebootDownstream(opts).run(opts.cmd)
