# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Image API Service.

The image related API endpoints should generally be found here.
"""

import copy
import functools
import logging
import os
from pathlib import Path
from typing import List, NamedTuple, Set, Union

from chromite.api import controller
from chromite.api import faux
from chromite.api import validate
from chromite.api.controller import controller_util
from chromite.api.gen.chromiumos import common_pb2
from chromite.api.metrics import deserialize_metrics_log
from chromite.lib import build_target_lib
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import image_lib
from chromite.lib import sysroot_lib
from chromite.service import packages as packages_service
from chromite.scripts import pushimage
from chromite.service import image
from chromite.utils import metrics

# The image.proto ImageType enum ids.
_BASE_ID = common_pb2.IMAGE_TYPE_BASE
_DEV_ID = common_pb2.IMAGE_TYPE_DEV
_TEST_ID = common_pb2.IMAGE_TYPE_TEST
_BASE_VM_ID = common_pb2.IMAGE_TYPE_BASE_VM
_TEST_VM_ID = common_pb2.IMAGE_TYPE_TEST_VM
_RECOVERY_ID = common_pb2.IMAGE_TYPE_RECOVERY
_FACTORY_ID = common_pb2.IMAGE_TYPE_FACTORY
_FIRMWARE_ID = common_pb2.IMAGE_TYPE_FIRMWARE
_BASE_GUEST_VM_ID = common_pb2.IMAGE_TYPE_BASE_GUEST_VM
_TEST_GUEST_VM_ID = common_pb2.IMAGE_TYPE_TEST_GUEST_VM

# Dict to allow easily translating names to enum ids and vice versa.
_IMAGE_MAPPING = {
    _BASE_ID: constants.IMAGE_TYPE_BASE,
    constants.IMAGE_TYPE_BASE: _BASE_ID,
    _DEV_ID: constants.IMAGE_TYPE_DEV,
    constants.IMAGE_TYPE_DEV: _DEV_ID,
    _TEST_ID: constants.IMAGE_TYPE_TEST,
    constants.IMAGE_TYPE_TEST: _TEST_ID,
    _RECOVERY_ID: constants.IMAGE_TYPE_RECOVERY,
    constants.IMAGE_TYPE_RECOVERY: _RECOVERY_ID,
    _FACTORY_ID: constants.IMAGE_TYPE_FACTORY_SHIM,
    constants.IMAGE_TYPE_FACTORY_SHIM: _FACTORY_ID,
    _FIRMWARE_ID: constants.IMAGE_TYPE_FIRMWARE,
    constants.IMAGE_TYPE_FIRMWARE: _FIRMWARE_ID,
}

# Dict to describe the prerequisite built images for each VM image type.
_VM_IMAGE_MAPPING = {
    _BASE_VM_ID: _IMAGE_MAPPING[_BASE_ID],
    _TEST_VM_ID: _IMAGE_MAPPING[_TEST_ID],
    _BASE_GUEST_VM_ID: _IMAGE_MAPPING[_BASE_ID],
    _TEST_GUEST_VM_ID: _IMAGE_MAPPING[_TEST_ID],
}

# Dict to describe the prerequisite built images for each mod image type.
_MOD_IMAGE_MAPPING = {
    _RECOVERY_ID: _IMAGE_MAPPING[_BASE_ID],
}

# Supported image types for PushImage.
SUPPORTED_IMAGE_TYPES = {
    common_pb2.IMAGE_TYPE_RECOVERY: constants.IMAGE_TYPE_RECOVERY,
    common_pb2.IMAGE_TYPE_FACTORY: constants.IMAGE_TYPE_FACTORY,
    common_pb2.IMAGE_TYPE_FIRMWARE: constants.IMAGE_TYPE_FIRMWARE,
    common_pb2.IMAGE_TYPE_ACCESSORY_USBPD: constants.IMAGE_TYPE_ACCESSORY_USBPD,
    common_pb2.IMAGE_TYPE_ACCESSORY_RWSIG: constants.IMAGE_TYPE_ACCESSORY_RWSIG,
    common_pb2.IMAGE_TYPE_BASE: constants.IMAGE_TYPE_BASE,
    common_pb2.IMAGE_TYPE_GSC_FIRMWARE: constants.IMAGE_TYPE_GSC_FIRMWARE,
}

# Built image directory symlink names. These names allow specifying a static
# location for creation to simplify later archival stages. In practice, this
# sets the symlink argument to build_packages.
# Core are the build/dev/test images.
# Use "latest" until we do a better job of passing through image directories,
# e.g. for artifacts.
LOCATION_CORE = 'latest'
# The factory_install image.
LOCATION_FACTORY = 'factory_shim'


class ImageTypes(NamedTuple):
  """Parsed image types."""
  images: Set[str]
  vms: Set[int]
  mod_images: Set[int]

  @property
  def core_images(self) -> List[str]:
    """The core images (base/dev/test) as a list."""
    return list(self.images - {_IMAGE_MAPPING[_FACTORY_ID]}) or []

  @property
  def has_factory(self) -> bool:
    """Whether the factory image is present."""
    return _IMAGE_MAPPING[_FACTORY_ID] in self.images

  @property
  def factory(self) -> List[str]:
    """A list with the factory type if set."""
    return [_IMAGE_MAPPING[_FACTORY_ID]] if self.has_factory else []


def _add_image_to_proto(output_proto, path: Union['Path', str], image_type: int,
                        board: str):
  """Quick helper function to add a new image to the output proto."""
  new_image = output_proto.images.add()
  new_image.path = str(path)
  new_image.type = image_type
  new_image.build_target.name = board


def ExampleGetResponse():
  """Give an example response to assemble upstream in caller artifacts."""
  uabs = common_pb2.UploadedArtifactsByService
  cabs = common_pb2.ArtifactsByService
  return uabs.Sysroot(artifacts=[
      uabs.Image.ArtifactPaths(
          artifact_type=cabs.Image.ArtifactType.DLC_IMAGE,
          paths=[
              common_pb2.Path(
                  path='/tmp/dlc/dlc.img', location=common_pb2.Path.OUTSIDE)
          ])
  ])


def GetArtifacts(in_proto: common_pb2.ArtifactsByService.Image,
                 chroot: chroot_lib.Chroot, sysroot_class: sysroot_lib.Sysroot,
                 build_target: build_target_lib.BuildTarget,
                 output_dir) -> list:
  """Builds and copies images to specified output_dir.

  Copies (after optionally bundling) all required images into the output_dir,
  returning a mapping of image type to a list of (output_dir) paths to
  the desired files. Note that currently it is only processing one image (DLC),
  but the future direction is to process all required images. Required images
  are located within output_artifact.artifact_type.

  Args:
    in_proto: Proto request defining reqs.
    chroot: The chroot proto used for these artifacts.
    sysroot_class: The sysroot proto used for these artifacts.
    build_target: The build target used for these artifacts.
    output_dir: The path to write artifacts to.

  Returns:
    A list of dictionary mappings of ArtifactType to list of paths.
  """
  base_path = chroot.full_path(sysroot_class.path)
  board = build_target.name
  factory_shim_location = Path(
      image_lib.GetLatestImageLink(board, pointer=LOCATION_FACTORY)).resolve()

  generated = []
  dlc_func = functools.partial(image.copy_dlc_image, base_path)
  license_func = functools.partial(
      image.copy_license_credits, board, symlink=LOCATION_CORE)
  factory_image_func = functools.partial(
      image.create_factory_image_zip,
      chroot,
      sysroot_class,
      factory_shim_location,
      packages_service.determine_full_version(),
  )
  artifact_types = {
      in_proto.ArtifactType.DLC_IMAGE: dlc_func,
      in_proto.ArtifactType.LICENSE_CREDITS: license_func,
      in_proto.ArtifactType.FACTORY_IMAGE: factory_image_func,
  }

  for output_artifact in in_proto.output_artifacts:
    for artifact_type, func in artifact_types.items():
      if artifact_type in output_artifact.artifact_types:
        result = func(output_dir)
        if result:
          generated.append({
              'paths': [result] if isinstance(result, str) else result,
              'type': artifact_type,
          })

  return generated


def _CreateResponse(_input_proto, output_proto, _config):
  """Set output_proto success field on a successful Create response."""
  output_proto.success = True


@faux.success(_CreateResponse)
@faux.empty_completed_unsuccessfully_error
@validate.require('build_target.name')
@validate.validation_complete
@metrics.collect_metrics
def Create(input_proto, output_proto, _config):
  """Build images.

  Args:
    input_proto (image_pb2.CreateImageRequest): The input message.
    output_proto (image_pb2.CreateImageResult): The output message.
    _config (api_config.ApiConfig): The API call config.
  """
  board = input_proto.build_target.name

  # Build the base image if no images provided.
  to_build = input_proto.image_types or [_BASE_ID]

  image_types = _ParseImagesToCreate(to_build)
  build_config = _ParseCreateBuildConfig(input_proto)
  factory_build_config = copy.copy(build_config)
  build_config.symlink = LOCATION_CORE
  factory_build_config.symlink = LOCATION_FACTORY
  factory_build_config.output_dir_suffix = LOCATION_FACTORY

  # Try building the core and factory images.
  # Sorted isn't really necessary here, but it's much easier to test.
  core_result = image.Build(
      board, sorted(image_types.core_images), config=build_config)
  logging.debug('Core Result Images: %s', core_result.images)

  factory_result = image.Build(
      board, image_types.factory, config=factory_build_config)
  logging.debug('Factory Result Images: %s', factory_result.images)

  # A successful run will have no images missing, will have run at least one
  # of the two image sets, and neither attempt errored. The no error condition
  # should be redundant with no missing images, but is cheap insurance.
  all_built = core_result.all_built and factory_result.all_built
  one_ran = core_result.build_run or factory_result.build_run
  no_errors = not core_result.run_error and not factory_result.run_error
  output_proto.success = success = all_built and one_ran and no_errors

  if success:
    # Success! We need to record the images we built in the output.
    all_images = {**core_result.images, **factory_result.images}
    for img_name, img_path in all_images.items():
      _add_image_to_proto(output_proto, img_path, _IMAGE_MAPPING[img_name],
                          board)

    # Build and record VMs as necessary.
    for vm_type in image_types.vms:
      is_test = vm_type in [_TEST_VM_ID, _TEST_GUEST_VM_ID]
      img_type = _IMAGE_MAPPING[_TEST_ID if is_test else _BASE_ID]
      img_dir = core_result.images[img_type].parent.resolve()
      try:
        if vm_type in [_BASE_GUEST_VM_ID, _TEST_GUEST_VM_ID]:
          vm_path = image.CreateGuestVm(
              board, is_test=is_test, image_dir=img_dir)
        else:
          vm_path = image.CreateVm(
              board,
              disk_layout=build_config.disk_layout,
              is_test=is_test,
              image_dir=img_dir)
      except image.ImageToVmError as e:
        cros_build_lib.Die(e)

      _add_image_to_proto(output_proto, vm_path, vm_type, board)

    # Build and record any mod images.
    for mod_type in image_types.mod_images:
      if mod_type == _RECOVERY_ID:
        base_image_path = core_result.images[constants.IMAGE_TYPE_BASE]
        result = image.BuildRecoveryImage(
            board=board, image_path=base_image_path)
        if result.all_built:
          _add_image_to_proto(output_proto,
                              result.images[_IMAGE_MAPPING[mod_type]], mod_type,
                              board)
        else:
          cros_build_lib.Die('Failed to create recovery image.')
      else:
        cros_build_lib.Die('_RECOVERY_ID is the only mod_image_type.')

    # Read metric events log and pipe them into output_proto.events.
    deserialize_metrics_log(output_proto.events, prefix=board)
    return controller.RETURN_CODE_SUCCESS

  else:
    # Failure, include all of the failed packages in the output when available.
    packages = core_result.failed_packages + factory_result.failed_packages
    if not packages:
      return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY

    for package in packages:
      current = output_proto.failed_packages.add()
      controller_util.serialize_package_info(package, current)

    return controller.RETURN_CODE_UNSUCCESSFUL_RESPONSE_AVAILABLE


def _ParseImagesToCreate(to_build: List[int]) -> ImageTypes:
  """Helper function to parse the image types to build.

  This function expresses the dependencies of each image type and adds
  the requisite image types if they're not explicitly defined.

  Args:
    to_build: The image type list.

  Returns:
    ImageTypes: The parsed images to build.
  """
  image_types = set()
  vm_types = set()
  mod_image_types = set()
  for current in to_build:
    # Find out if it's a special case (vm, img mod), or just any old image.
    if current in _VM_IMAGE_MAPPING:
      vm_types.add(current)
      # Make sure we build the image required to build the VM.
      image_types.add(_VM_IMAGE_MAPPING[current])
    elif current in _MOD_IMAGE_MAPPING:
      mod_image_types.add(current)
      image_types.add(_MOD_IMAGE_MAPPING[current])
    elif current in _IMAGE_MAPPING:
      image_types.add(_IMAGE_MAPPING[current])
    else:
      # Not expected, but at least it will be obvious if this comes up.
      cros_build_lib.Die(
          "The service's known image types do not match those in image.proto. "
          'Unknown Enum ID: %s' % current)

  # We can only build one type of these images at a time since image_to_vm.sh
  # uses the default path if a name is not provided.
  if vm_types.issuperset({_BASE_VM_ID, _TEST_VM_ID}):
    cros_build_lib.Die('Cannot create more than one VM.')

  return ImageTypes(
      images=image_types, vms=vm_types, mod_images=mod_image_types)


def _ParseCreateBuildConfig(input_proto):
  """Helper to parse the image build config for Create."""
  enable_rootfs_verification = not input_proto.disable_rootfs_verification
  version = input_proto.version or None
  disk_layout = input_proto.disk_layout or None
  builder_path = input_proto.builder_path or None
  return image.BuildConfig(
      enable_rootfs_verification=enable_rootfs_verification,
      replace=True,
      version=version,
      disk_layout=disk_layout,
      builder_path=builder_path,
  )


def _SignerTestResponse(_input_proto, output_proto, _config):
  """Set output_proto success field on a successful SignerTest response."""
  output_proto.success = True
  return controller.RETURN_CODE_SUCCESS


@faux.success(_SignerTestResponse)
@faux.empty_completed_unsuccessfully_error
@validate.exists('image.path')
@validate.validation_complete
def SignerTest(input_proto, output_proto, _config):
  """Run image tests.

  Args:
    input_proto (image_pb2.ImageTestRequest): The input message.
    output_proto (image_pb2.ImageTestResult): The output message.
    _config (api_config.ApiConfig): The API call config.
  """
  image_path = input_proto.image.path

  result = image_lib.SecurityTest(image=image_path)
  output_proto.success = result
  if result:
    return controller.RETURN_CODE_SUCCESS
  else:
    return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY


def _TestResponse(_input_proto, output_proto, _config):
  """Set output_proto success field on a successful Test response."""
  output_proto.success = True
  return controller.RETURN_CODE_SUCCESS


@faux.success(_TestResponse)
@faux.empty_completed_unsuccessfully_error
@validate.require('build_target.name', 'result.directory')
@validate.exists('image.path')
def Test(input_proto, output_proto, config):
  """Run image tests.

  Args:
    input_proto (image_pb2.ImageTestRequest): The input message.
    output_proto (image_pb2.ImageTestResult): The output message.
    config (api_config.ApiConfig): The API call config.
  """
  image_path = input_proto.image.path
  board = input_proto.build_target.name
  result_directory = input_proto.result.directory

  if not os.path.isfile(image_path) or not image_path.endswith('.bin'):
    cros_build_lib.Die(
        'The image.path must be an existing image file with a .bin extension.')

  if config.validate_only:
    return controller.RETURN_CODE_VALID_INPUT

  success = image.Test(board, result_directory, image_dir=image_path)
  output_proto.success = success

  if success:
    return controller.RETURN_CODE_SUCCESS
  else:
    return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY


@faux.empty_success
@faux.empty_completed_unsuccessfully_error
@validate.require('gs_image_dir', 'sysroot.build_target.name')
def PushImage(input_proto, _output_proto, config):
  """Push artifacts from the archive bucket to the release bucket.

  Wraps chromite/scripts/pushimage.py.

  Args:
    input_proto (PushImageRequest): Input proto.
    _output_proto (PushImageResponse): Output proto.
    config (api.config.ApiConfig): The API call config.

  Returns:
    A controller return code (e.g. controller.RETURN_CODE_SUCCESS).
  """
  sign_types = []
  if input_proto.sign_types:
    for sign_type in input_proto.sign_types:
      if sign_type not in SUPPORTED_IMAGE_TYPES:
        logging.error('unsupported sign type %g', sign_type)
        return controller.RETURN_CODE_INVALID_INPUT
      sign_types.append(SUPPORTED_IMAGE_TYPES[sign_type])

  # If configured for validation only we're done here.
  if config.validate_only:
    return controller.RETURN_CODE_VALID_INPUT

  kwargs = {}
  if input_proto.profile.name:
    kwargs['profile'] = input_proto.profile.name
  if input_proto.dest_bucket:
    kwargs['dest_bucket'] = input_proto.dest_bucket
  if input_proto.channels:
    kwargs['force_channels'] = [
        common_pb2.Channel.Name(channel).lower()[len('channel_'):]
        for channel in input_proto.channels
    ]
  try:
    pushimage.PushImage(
        input_proto.gs_image_dir,
        input_proto.sysroot.build_target.name,
        dry_run=input_proto.dryrun,
        sign_types=sign_types,
        **kwargs)
    return controller.RETURN_CODE_SUCCESS
  except Exception:
    logging.error('PushImage failed: ', exc_info=True)
    return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY
