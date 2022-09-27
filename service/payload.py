# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The payload API is the entry point for payload functionality."""

from copy import deepcopy
import os
import re

from chromite.lib import chroot_util
from chromite.lib.paygen import gspaths
from chromite.lib.paygen import paygen_payload_lib

from chromite.api.gen.chromiumos import common_pb2
from chromite.api.gen.chromite.api import payload_pb2


class Error(Exception):
  """Base module error."""


class ImageTypeUnknownError(Error):
  """An error raised when image type is unknown."""


class ImageMismatchError(Error):
  """An error raised when src and tgt aren't compatible."""


class PayloadConfig(object):
  """Value object to hold the GeneratePayload configuration options."""

  def __init__(self,
               tgt_image=None,
               src_image=None,
               dest_bucket=None,
               verify=True,
               keyset=None,
               upload=True,
               cache_dir=None):
    """Init method, sets up all the paths and configuration.

    Args:
      tgt_image (UnsignedImage, SignedImage, or DLCImage):
          Proto for destination image.
      src_image (UnsignedImage, SignedImage, DLCImage, or None):
          Proto for source image.
      dest_bucket (str): Destination bucket to place the final artifacts in.
      verify (bool): If delta is made, verify the integrity of the payload.
      keyset (str): The key to sign the image with.
      upload (bool): Whether the payload generation results should be uploaded.
      cache_dir (str): The cache dir for paygen to use or None for default.
    """

    # Set when we call GeneratePayload on this object.
    self.paygen = None
    self.tgt_image = tgt_image
    self.src_image = src_image
    self.dest_bucket = dest_bucket
    self.verify = verify
    self.keyset = keyset
    self.upload = upload
    self.delta_type = 'delta' if self.src_image else 'full'
    self.image_type = _ImageTypeToStr(tgt_image.image_type)
    self.cache_dir = cache_dir

    # This block ensures that we have paths to the correct perm of images.
    src_image_path = None
    if isinstance(self.tgt_image, payload_pb2.UnsignedImage):
      tgt_image_path = _GenUnsignedGSPath(self.tgt_image, self.image_type)
    elif isinstance(self.tgt_image, payload_pb2.SignedImage):
      tgt_image_path = _GenSignedGSPath(self.tgt_image, self.image_type)
    elif isinstance(self.tgt_image, payload_pb2.DLCImage):
      tgt_image_path = _GenDLCImageGSPath(self.tgt_image)
    if self.delta_type == 'delta':
      if isinstance(self.tgt_image, payload_pb2.UnsignedImage):
        src_image_path = _GenUnsignedGSPath(self.src_image, self.image_type)
      if isinstance(self.tgt_image, payload_pb2.SignedImage):
        src_image_path = _GenSignedGSPath(self.src_image, self.image_type)
      elif isinstance(self.tgt_image, payload_pb2.DLCImage):
        src_image_path = _GenDLCImageGSPath(self.src_image)


    # Set your output location.
    if self.upload:
      payload_build = deepcopy(tgt_image_path.build)
      payload_build.bucket = dest_bucket
      payload_output_uri = gspaths.ChromeosReleases.PayloadUri(
          build=payload_build,
          random_str=None,
          key=self.keyset,
          src_version=src_image_path.build.version if src_image else None,
      )
    else:
      payload_output_uri = None

    self.payload = gspaths.Payload(
        tgt_image=tgt_image_path, src_image=src_image_path,
        uri=payload_output_uri)


  def GeneratePayload(self):
    """Do payload generation (& maybe sign) on Google Storage CrOS images.

    Returns:
      A tuple of (string, string) containing:
          The location of the local generated artifact.
            (e.g. /tmp/wdjaio/delta.bin)
          The remote location that the payload was uploaded or None.
            (e.g. 'gs://cr/beta-channel/coral/12345.0.1/payloads/...')
    """
    should_sign = self.keyset != ''

    # Leave the generated artifact local. This is ok because if we're testing
    # it's likely we want the artifact anyway, and in production this is ran on
    # single shot bots in the context of an overlayfs and will get cleaned up
    # anyway.
    with chroot_util.TempDirInChroot(delete=False) as temp_dir:
      self.paygen = paygen_payload_lib.PaygenPayload(
          self.payload,
          temp_dir,
          sign=should_sign,
          verify=self.verify,
          upload=self.upload,
          cache_dir=self.cache_dir)

      # We run and expect failures to raise, so if we get passed
      # self.paygen.Run() then it's safe to assume the bin is in place.
      local_path = os.path.join(temp_dir, 'delta.bin')
      remote_uri = self.paygen.Run()
      return (local_path, remote_uri)


class GeneratePayloadResult(object):
  """Value object to report GeneratePayload results."""

  def __init__(self, return_code):
    """Initialize a GeneratePayloadResult.

    Args:
      return_code (bool): The return code of the GeneratePayload operation.
    """
    self.success = return_code == 0


def _ImageTypeToStr(image_type_n):
  """The numeral image type enum in proto to lowercase string."""
  ret = common_pb2.ImageType.Name(image_type_n).lower()
  return re.sub('^image_type_', '', ret)


def _GenSignedGSPath(image, image_type):
  """Take a SignedImage_pb2 and return a gspaths.Image.

  Args:
    image (SignedImage_pb2): The build to create the gspath from.
    image_type (string): The image type, either "recovery" or "base".

  Returns:
    A gspaths.Image instance.
  """
  build = gspaths.Build(board=image.build.build_target.name,
                        version=image.build.version,
                        channel=image.build.channel,
                        bucket=image.build.bucket)

  build_uri = gspaths.ChromeosReleases.ImageUri(
      build, image.key, image_type)

  build.uri = build_uri

  return gspaths.Image(build=build,
                       image_type=image_type,
                       uri=build_uri)


def _GenUnsignedGSPath(image, image_type):
  """Take an UnsignedImage_pb2 and return a gspaths.UnsignedImageArchive.

  Args:
    image (UnsignedImage_pb2): The build to create the gspath from.
    image_type (string): The image type, either "recovery" or "test".

  Returns:
    A gspaths.UnsignedImageArchive instance.
  """
  build = gspaths.Build(board=image.build.build_target.name,
                        version=image.build.version,
                        channel=image.build.channel,
                        bucket=image.build.bucket)

  build_uri = gspaths.ChromeosReleases.UnsignedImageUri(
      build, image.milestone, image_type)

  build.uri = build_uri

  return gspaths.UnsignedImageArchive(build=build,
                                      milestone=image.milestone,
                                      image_type=image_type,
                                      uri=build_uri)


def _GenDLCImageGSPath(image):
  """Take a DLCImage_pb2 and return a gspaths.DLCImage.

  Args:
    image (DLCImage_pb2): The dlc image to create the gspath from.

  Returns:
    A gspaths.DLCImage instance.
  """
  build = gspaths.Build(
      board=image.build.build_target.name,
      version=image.build.version,
      channel=image.build.channel,
      bucket=image.build.bucket)

  dlc_image_uri = gspaths.ChromeosReleases.DLCImageUri(build, image.dlc_id,
                                                       image.dlc_package,
                                                       image.dlc_image)

  return gspaths.DLCImage(
      build=build,
      image_type=image.image_type,
      key='',
      uri=dlc_image_uri,
      dlc_id=image.dlc_id,
      dlc_package=image.dlc_package,
      dlc_image=image.dlc_image)
