# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Completer functions to use with --b, --board, --build-target."""

import os
from pathlib import Path
import re
from typing import Iterator, List

from chromite.lib import constants
from chromite.lib import path_util
from chromite.lib import portage_util


def build_target(
    prefix, action, parser, parsed_args  # pylint: disable=unused-argument
) -> List[str]:
    """List all possible build targets."""
    RE_NAME = re.compile(r"^overlay-(.*?)(-private)?$")
    overlay_paths = portage_util.FindOverlays(constants.BOTH_OVERLAYS)
    overlays = [os.path.basename(x) for x in overlay_paths]
    build_targets = set()
    for overlay in overlays:
        m = RE_NAME.match(overlay)
        if (
            m
            and not m.group(1).startswith("variant-")
            and m.group(1).startswith(prefix)
        ):
            build_targets.add(m.group(1))
    return sorted(build_targets)


def built_build_target(
    prefix, action, parser, parsed_args  # pylint: disable=unused-argument
) -> Iterator[str]:
    """List build targets with a sysroot."""
    p = f"{prefix}*/etc/portage"
    yield from (
        x.parent.parent.name
        for x in Path(
            path_util.FromChrootPath(path_util.FromChrootPath("/build"))
        ).glob(p)
    )
