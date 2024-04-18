# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The payload API is the entry point for payload functionality."""

import copy
import re
from typing import Dict, Optional, Tuple, Union

from chromite.api.gen.chromite.api import payload_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import chroot_lib
from chromite.lib.paygen import gspaths
from chromite.lib.paygen import paygen_build_lib
from chromite.lib.paygen import paygen_payload_lib


class Error(Exception):
    """Base module error."""


class ImageTypeUnknownError(Error):
    """An error raised when image type is unknown."""


class ImageMismatchError(Error):
    """An error raised when src and tgt aren't compatible."""


class PayloadConfig:
    """Value object to hold the GeneratePayload configuration options."""

    def __init__(
        self,
        chroot: chroot_lib.Chroot,
        tgt_image: Optional[
            Union[
                payload_pb2.UnsignedImage,
                payload_pb2.SignedImage,
                payload_pb2.DLCImage,
            ]
        ] = None,
        src_image: Optional[
            Union[
                payload_pb2.UnsignedImage,
                payload_pb2.SignedImage,
                payload_pb2.DLCImage,
            ]
        ] = None,
        dest_bucket: Optional[str] = None,
        minios: bool = False,
        verify: bool = True,
        upload: bool = True,
        cache_dir: Optional[str] = None,
        use_local_signing: bool = False,
        signing_docker_image: str = None,
    ):
        """Init method, sets up all the paths and configuration.

        Args:
            chroot: Chroot to work with.
            tgt_image: Proto for destination image.
            src_image: Proto for source image.
            dest_bucket: Destination bucket to place the final artifacts in.
            minios: Whether the payload is for the image's miniOS partition.
            verify: If delta is made, verify the integrity of the payload.
            upload: Whether the payload generation results should be uploaded.
            cache_dir: The cache dir for paygen to use or None for default.
            use_local_signing: Whether to use local signing.
            signing_docker_image: Docker image to use for local signing.
        """

        # Set when we call GeneratePayload on this object.
        self.paygen = None
        self.chroot = chroot
        self.tgt_image = tgt_image
        self.src_image = src_image
        self.dest_bucket = dest_bucket
        self.minios = minios
        self.verify = verify
        self.upload = upload
        self.delta_type = "delta" if self.src_image else "full"
        self.image_type = _ImageTypeToStr(tgt_image.image_type)
        self.cache_dir = cache_dir
        self.use_local_signing = use_local_signing
        self.signing_docker_image = signing_docker_image

        if self.use_local_signing and not self.signing_docker_image:
            raise ValueError(
                "local signing enabled but no docker image specified"
            )

        # This block ensures that we have paths to the correct perm of images.
        src_image_path = None
        if isinstance(self.tgt_image, payload_pb2.UnsignedImage):
            tgt_image_path = _GenUnsignedGSPath(
                self.tgt_image, self.image_type, self.minios
            )
        elif isinstance(self.tgt_image, payload_pb2.SignedImage):
            tgt_image_path = _GenSignedGSPath(
                self.tgt_image, self.image_type, self.minios
            )
        elif isinstance(self.tgt_image, payload_pb2.DLCImage):
            tgt_image_path = _GenDLCImageGSPath(self.tgt_image)
        if self.delta_type == "delta":
            if isinstance(self.tgt_image, payload_pb2.UnsignedImage):
                src_image_path = _GenUnsignedGSPath(
                    self.src_image, self.image_type, self.minios
                )
            if isinstance(self.tgt_image, payload_pb2.SignedImage):
                src_image_path = _GenSignedGSPath(
                    self.src_image, self.image_type, self.minios
                )
            elif isinstance(self.tgt_image, payload_pb2.DLCImage):
                src_image_path = _GenDLCImageGSPath(self.src_image)

        payload_build = copy.deepcopy(tgt_image_path.build)
        payload_build.bucket = dest_bucket

        self.payload = gspaths.Payload(
            build=payload_build,
            tgt_image=tgt_image_path,
            src_image=src_image_path,
            minios=self.minios,
            uri=None,
        )

        if self.upload:
            self.payload.uri = paygen_build_lib.DefaultPayloadUri(self.payload)

    def GeneratePayload(self) -> Dict[int, Tuple[str, str]]:
        """Do payload generation (& maybe sign) on Google Storage CrOS images.

        Returns:
            A dict containing tuples of the following format:
                The location of the local generated artifact.
                    (e.g. /tmp/wdjaio/delta.bin)
                The remote location that the payload was uploaded or None.
                    (e.g. 'gs://cr/beta-channel/coral/12345.0.1/payloads/...')
            Keyed by a version number.

        Raises:
            paygen_payload_lib.PayloadGenerationSkippedException: If paygen was
                skipped for any reason.
        """
        # Leave the generated artifact local. This is ok because if we're
        # testing it's likely we want the artifact anyway, and in production
        # this is ran on single shot bots in the context of an overlayfs and
        # will get cleaned up anyway.
        with self.chroot.tempdir(delete=False) as temp_dir:
            signer = paygen_payload_lib.PaygenSigner(
                chroot=self.chroot,
                work_dir=temp_dir,
                payload_build=self.payload.build,
                local_signing=self.use_local_signing,
                docker_image=self.signing_docker_image,
            )
            self.paygen = paygen_payload_lib.PaygenPayload(
                self.chroot,
                self.payload,
                temp_dir,
                signer=signer,
                verify=self.verify,
                upload=self.upload,
                cache_dir=self.cache_dir,
            )

            # The return from paygen will look like:
            # {
            #     1: (local_path, remote_uri),
            #     2: (local_path, remote_uri),
            #     ...
            # }
            return self.paygen.Run()


def _ImageTypeToStr(image_type_n: int) -> str:
    """The numeral image type enum in proto to lowercase string."""
    ret = common_pb2.ImageType.Name(image_type_n).lower()
    return re.sub("^image_type_", "", ret)


def _GenSignedGSPath(
    image: payload_pb2.SignedImage, image_type: str, minios: bool
) -> gspaths.Image:
    """Take a SignedImage_pb2 and return a gspaths.Image.

    Args:
        image: The build to create the gspath from.
        image_type: The image type, either "recovery" or "base".
        minios: Whether or not it's a miniOS image.

    Returns:
        A gspaths.Image instance.
    """
    build = gspaths.Build(
        board=image.build.build_target.name,
        version=image.build.version,
        channel=image.build.channel,
        bucket=image.build.bucket,
    )

    build_uri = gspaths.ChromeosReleases.ImageUri(build, image.key, image_type)

    build.uri = build_uri

    if minios:
        return gspaths.MiniOSImage(
            build=build, image_type=image_type, key=image.key, uri=build_uri
        )
    else:
        return gspaths.Image(
            build=build, image_type=image_type, key=image.key, uri=build_uri
        )


def _GenUnsignedGSPath(
    image: payload_pb2.UnsignedImage, image_type: str, minios: bool
) -> gspaths.UnsignedImageArchive:
    """Take an UnsignedImage_pb2 and return a gspaths.UnsignedImageArchive.

    Args:
        image: The build to create the gspath from.
        image_type: The image type, either "recovery" or "test".
        minios: Whether or not it's a miniOS image.

    Returns:
        A gspaths.UnsignedImageArchive instance.
    """
    build = gspaths.Build(
        board=image.build.build_target.name,
        version=image.build.version,
        channel=image.build.channel,
        bucket=image.build.bucket,
    )

    build_uri = gspaths.ChromeosReleases.UnsignedImageUri(
        build, image.milestone, image_type
    )

    build.uri = build_uri

    if minios:
        return gspaths.UnsignedMiniOSImageArchive(
            build=build,
            milestone=image.milestone,
            image_type=image_type,
            uri=build_uri,
        )
    else:
        return gspaths.UnsignedImageArchive(
            build=build,
            milestone=image.milestone,
            image_type=image_type,
            uri=build_uri,
        )


def _GenDLCImageGSPath(image: payload_pb2.DLCImage) -> gspaths.DLCImage:
    """Take a DLCImage_pb2 and return a gspaths.DLCImage.

    Args:
        image: The dlc image to create the gspath from.

    Returns:
        A gspaths.DLCImage instance.
    """
    build = gspaths.Build(
        board=image.build.build_target.name,
        version=image.build.version,
        channel=image.build.channel,
        bucket=image.build.bucket,
    )

    dlc_image_uri = gspaths.ChromeosReleases.DLCImageUri(
        build, image.dlc_id, image.dlc_package, image.dlc_image
    )

    return gspaths.DLCImage(
        build=build,
        image_type=image.image_type,
        key="",
        uri=dlc_image_uri,
        dlc_id=image.dlc_id,
        dlc_package=image.dlc_package,
        dlc_image=image.dlc_image,
    )
