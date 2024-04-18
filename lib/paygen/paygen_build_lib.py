# Copyright 2013 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""PayGen - Automatic Payload Generation.

This library processes a single build at a time, and decides which payloads
need to be generated. It then calls paygen_payload to generate each payload.

This library is reponsible for locking builds during processing, and checking
and setting flags to show that a build has been processed.
"""

from chromite.lib.paygen import gspaths


class Error(Exception):
    """Exception base class for this module."""


def DefaultPayloadUri(payload, random_str=None):
    """Compute the default output URI for a payload.

    For a glob that matches all potential URIs for this
    payload, pass in a random_str of '*'.

    Args:
        payload: gspaths.Payload instance.
        random_str: A hook to force a specific random_str. None means generate
            it.

    Returns:
        Default URI for the payload.
    """
    src_version = None
    if payload.src_image:
        src_version = payload.src_image.build.version

    if gspaths.IsDLCImage(payload.tgt_image):
        # Signed DLC payload.
        return gspaths.ChromeosReleases.DLCPayloadUri(
            payload.build,
            random_str=random_str,
            dlc_id=payload.tgt_image.dlc_id,
            dlc_package=payload.tgt_image.dlc_package,
            image_channel=payload.tgt_image.image_channel,
            image_version=payload.tgt_image.image_version,
            src_version=src_version,
        )
    elif gspaths.IsMiniOSImage(payload.tgt_image):
        # Signed MiniOS payload.
        return gspaths.ChromeosReleases.MiniOSPayloadUri(
            payload.build,
            random_str=random_str,
            key=payload.tgt_image.key,
            image_channel=payload.tgt_image.image_channel,
            image_version=payload.tgt_image.image_version,
            src_version=src_version,
        )
    elif gspaths.IsImage(payload.tgt_image):
        # Signed payload.
        return gspaths.ChromeosReleases.PayloadUri(
            payload.build,
            random_str=random_str,
            key=payload.tgt_image.key,
            image_channel=payload.tgt_image.image_channel,
            image_version=payload.tgt_image.image_version,
            src_version=src_version,
        )
    elif gspaths.IsUnsignedMiniOSImageArchive(payload.tgt_image):
        # Unsigned test MiniOS payload.
        return gspaths.ChromeosReleases.MiniOSPayloadUri(
            payload.build, random_str=random_str, src_version=src_version
        )
    elif gspaths.IsUnsignedImageArchive(payload.tgt_image):
        # Unsigned test payload.
        return gspaths.ChromeosReleases.PayloadUri(
            payload.build, random_str=random_str, src_version=src_version
        )
    else:
        raise Error("Unknown image type %s" % type(payload.tgt_image))
