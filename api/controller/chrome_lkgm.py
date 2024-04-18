# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handles ChromeOS LKGM image version detection."""

import os

from chromite.api import faux
from chromite.api import validate
from chromite.lib import chrome_lkgm
from chromite.lib import path_util


def _find_lkgm_success(_input_proto, output_proto, _config_proto):
    """Mock for a success case."""
    output_proto.config_name = "boardname-release"
    output_proto.full_version = "111.0.0.5678"
    output_proto.chromeos_lkgm = "111.0.0.5679"


def _find_lkgm_error(_input_proto, output_proto, _config_proto):
    """Mock for a failed case."""
    output_proto.error = "something went wrong"


@faux.success(_find_lkgm_success)
@faux.error(_find_lkgm_error)
@validate.require("build_target")
@validate.require("fallback_versions")
@validate.validation_complete
def FindLkgm(input_proto, output_proto, _config_proto):
    """Find LKGM or older version of image for a board."""
    checkout = path_util.DetermineCheckout(
        input_proto.chrome_src or os.getcwd()
    )

    f = chrome_lkgm.ChromeOSVersionFinder(
        input_proto.cache_dir or None,
        input_proto.build_target.name,
        fallback_versions=input_proto.fallback_versions,
        chrome_src=input_proto.chrome_src,
        use_external_config=input_proto.use_external_config,
    )
    output_proto.config_name = f.config_name

    try:
        lkgm_version = chrome_lkgm.GetChromeLkgm(input_proto.chrome_src)
    except FileNotFoundError as e:
        output_proto.error = str(e)
        return

    if not lkgm_version:
        output_proto.error = str(
            chrome_lkgm.MissingLkgmFile(checkout.chrome_src_dir)
        )
        return

    output_proto.chromeos_lkgm = lkgm_version
    full_version = f.GetFullVersionFromLatest(lkgm_version)
    if not full_version:
        output_proto.error = "failed to get full version"
        return
    output_proto.full_version = full_version
