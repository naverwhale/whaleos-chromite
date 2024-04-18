# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Telemetry POC script."""

import argparse
import time
from typing import List, Optional

from chromite.third_party.opentelemetry import trace

from chromite.lib import chromite_config
from chromite.lib import commandline
from chromite.utils import telemetry


def get_parser() -> commandline.ArgumentParser:
    """Build the argument parser."""
    parser = commandline.ArgumentParser(description=__doc__)

    parser.add_argument(
        "-t",
        "--time",
        type=int,
        default=1,
        help="Seconds to sleep.",
    )

    return parser


def parse_arguments(argv: List) -> argparse.Namespace:
    """Parse and validate arguments."""
    parser = get_parser()
    opts = parser.parse_args(argv)

    opts.Freeze()
    return opts


tracer = trace.get_tracer(__name__)


def main(argv: Optional[List[str]]) -> Optional[int]:
    """Main."""
    opts = parse_arguments(argv)

    chromite_config.initialize()
    telemetry.initialize(chromite_config.TELEMETRY_CONFIG, opts.log_telemetry)

    with tracer.start_as_current_span("test") as span:
        time.sleep(opts.time / 2)
        span.add_event(name="mid-sleep-event", attributes={"attr": "val"})
        time.sleep(opts.time / 2)
