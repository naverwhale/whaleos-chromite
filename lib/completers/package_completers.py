# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Completer functions to use with -p, --packages."""

import argparse
from pathlib import Path
from typing import Iterator, List

from chromite.lib import build_target_lib
from chromite.lib import portage_util
from chromite.lib import sysroot_lib


def package(
    prefix, action, parser, parsed_args  # pylint: disable=unused-argument
) -> List[str]:
    """List all packages with the package version."""
    packages = (
        portage_util.SplitEbuildPath(x) for x in _get_ebuilds(parsed_args)
    )
    return [f"{cat}/{pv}" for (cat, _, pv) in packages]


def package_atom(
    prefix, action, parser, parsed_args  # pylint: disable=unused-argument
) -> List[str]:
    """List all packages without the package version."""
    return [portage_util.EbuildToCP(x) for x in _get_ebuilds(parsed_args)]


def _get_sysroot(parsed_args: argparse.Namespace) -> sysroot_lib.Sysroot:
    """Get the sysroot using the parsed arguments.

    Check to see if the parsed arguments contain arguments that can be used to
    determine the sysroot path. The sysroot can be specified when there's also
    a build target argument and should take precedence. --board/--build_target
    are the old/new names for the same thing so should never both be defined.
    """
    sysroot_path = build_target_lib.get_sdk_sysroot_path()
    if hasattr(parsed_args, "sysroot") and parsed_args.sysroot:
        sysroot_path = parsed_args.sysroot
    elif hasattr(parsed_args, "board") and parsed_args.board:
        sysroot_path = build_target_lib.get_default_sysroot_path(
            parsed_args.board
        )
    elif hasattr(parsed_args, "build_target") and parsed_args.build_target:
        sysroot_path = build_target_lib.get_default_sysroot_path(
            parsed_args.build_target
        )
    return sysroot_lib.Sysroot(sysroot_path)


def _get_ebuilds(parsed_args: argparse.Namespace) -> Iterator[Path]:
    """Get ebuild files using the parsed arguments."""
    sysroot = _get_sysroot(parsed_args)
    overlay_paths = sysroot.get_overlays()
    yield from portage_util.FindEbuildsForOverlays(overlay_paths)
