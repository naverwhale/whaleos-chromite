# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Firmware builder controller.

Handle all firmware builder related functionality.  Currently no service module
exists: all of the work is done here.
"""

import os
import tempfile

from chromite.third_party.google.protobuf import json_format

from chromite.api import controller
from chromite.api import faux
from chromite.api import validate
from chromite.api.gen.chromite.api import firmware_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils


def _call_entry(fw_loc, metric_proto, subcmd, *args, **kwargs):
  """Calls into firmware_builder.py with the specified subcmd."""

  if fw_loc == common_pb2.PLATFORM_EC:
    fw_path = 'src/platform/ec/'
  elif fw_loc == common_pb2.PLATFORM_ZEPHYR:
    fw_path = 'src/platform/ec/zephyr/'
  elif fw_loc == common_pb2.PLATFORM_TI50:
    fw_path = 'src/platform/ti50/common/'
  else:
    cros_build_lib.Die(f'Unknown firmware location {fw_loc}.')

  entry_point = os.path.join(constants.SOURCE_ROOT, fw_path,
                             'firmware_builder.py')

  with tempfile.NamedTemporaryFile() as tmpfile:
    cmd = [entry_point, '--metrics', tmpfile.name] + list(args)
    for key, value in kwargs.items():
      cmd += [f'--{key.replace("_", "-")}', value]
    cmd += [subcmd]

    result = cros_build_lib.run(cmd, check=False)
    with open(tmpfile.name, 'r') as f:
      response = f.read()

  if metric_proto:
    # Parse the entire metric file as our metric proto (as a passthru).
    # TODO(b/177907747): BundleFirmwareArtifacts doesn't use this (yet?), but
    # firmware_builder.py requires it.
    json_format.Parse(response, metric_proto)

  if result.returncode == 0:
    return controller.RETURN_CODE_SUCCESS
  else:
    return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY


def _BuildAllTotFirmwareResponse(_input_proto, output_proto, _config):
  """Add a fw region metric to a successful response."""

  metric = output_proto.success.value.add()
  metric.target_name = 'foo'
  metric.platform_name = 'bar'
  fw_section = metric.fw_section.add()
  fw_section.region = 'EC_RO'
  fw_section.used = 100
  fw_section.total = 150


@faux.success(_BuildAllTotFirmwareResponse)
@faux.empty_completed_unsuccessfully_error
@validate.require('firmware_location')
@validate.validation_complete
def BuildAllTotFirmware(input_proto, output_proto, _config):
  """Build all of the firmware targets at the specified location."""

  args = ['--code-coverage'] if input_proto.code_coverage else []
  return _call_entry(input_proto.firmware_location, output_proto.metrics,
                     'build', *args)


def _TestAllTotFirmwareResponse(_input_proto, output_proto, _config):
  """Add a fw region metric to a successful response."""

  metric = output_proto.success.value.add()
  metric.name = 'foo-test'


@faux.success(_TestAllTotFirmwareResponse)
@faux.empty_completed_unsuccessfully_error
@validate.require('firmware_location')
@validate.validation_complete
def TestAllTotFirmware(input_proto, output_proto, _config):
  """Runs all of the firmware tests at the specified location."""

  args = ['--code-coverage'] if input_proto.code_coverage else []
  return _call_entry(input_proto.firmware_location, output_proto.metrics,
                     'test', *args)


def _BuildAllFirmwareResponse(_input_proto, output_proto, _config):
  """Add a fw region metric to a successful response."""

  metric = output_proto.metrics.value.add()
  metric.target_name = 'foo'
  metric.platform_name = 'bar'
  fw_section = metric.fw_section.add()
  fw_section.region = 'EC_RO'
  fw_section.used = 100
  fw_section.total = 150


@faux.success(_BuildAllFirmwareResponse)
@faux.empty_completed_unsuccessfully_error
@validate.require('firmware_location')
@validate.validation_complete
def BuildAllFirmware(input_proto, output_proto, _config):
  """Build all of the firmware targets at the specified location."""

  args = ['--code-coverage'] if input_proto.code_coverage else []
  return _call_entry(input_proto.firmware_location, output_proto.metrics,
                     'build', *args)


def _TestAllFirmwareResponse(_input_proto, output_proto, _config):
  """Add a fw region metric to a successful response."""

  metric = output_proto.success.value.add()
  metric.name = 'foo-test'


@faux.success(_TestAllFirmwareResponse)
@faux.empty_completed_unsuccessfully_error
@validate.require('firmware_location')
@validate.validation_complete
def TestAllFirmware(input_proto, output_proto, _config):
  """Runs all of the firmware tests at the specified location."""

  args = ['--code-coverage'] if input_proto.code_coverage else []
  return _call_entry(input_proto.firmware_location, output_proto.metrics,
                     'test', *args)


def _BundleFirmwareArtifactsResponse(_input_proto, output_proto, _config):
  """Add a fw region metric to a successful response."""

  metric = output_proto.success.value.add()
  metric.name = 'foo-test'


@faux.success(_BundleFirmwareArtifactsResponse)
@faux.empty_completed_unsuccessfully_error
@validate.validation_complete
def BundleFirmwareArtifacts(input_proto, output_proto, _config):
  """Runs all of the firmware tests at the specified location."""

  if len(input_proto.artifacts.output_artifacts) > 1:
    raise ValueError('Must have exactly one output_artifact entry')

  with osutils.TempDir(delete=False) as tmpdir:
    info = input_proto.artifacts.output_artifacts[0]
    metadata_path = os.path.join(tmpdir, 'firmware_metadata.jsonpb')
    args = []
    if input_proto.artifacts.FIRMWARE_LCOV in info.artifact_types:
      args += ['--code-coverage']
    resp = _call_entry(
        info.location,
        None,
        'bundle',
        *args,
        output_dir=tmpdir,
        metadata=metadata_path)
    file_paths = []
    if os.path.exists(metadata_path):
      with open(metadata_path, 'r') as f:
        metadata = json_format.Parse(f.read(),
                                     firmware_pb2.FirmwareArtifactInfo())
    else:
      metadata = firmware_pb2.FirmwareArtifactInfo()
    if input_proto.artifacts.FIRMWARE_TARBALL_INFO in info.artifact_types:
      output_proto.artifacts.artifacts.add(
          artifact_type=input_proto.artifacts.FIRMWARE_TARBALL_INFO,
          location=info.location, paths=[
              common_pb2.Path(
                  path=metadata_path, location=common_pb2.Path.INSIDE)
          ])

    full_path = lambda x: common_pb2.Path(
        path=os.path.join(tmpdir, x.file_name),
        location=common_pb2.Path.INSIDE)

    for typ, name in (
        (input_proto.artifacts.FIRMWARE_TARBALL, 'tarball_info'),
        (input_proto.artifacts.FIRMWARE_LCOV, 'lcov_info')):
      file_paths = [
          full_path(x) for x in metadata.objects
          if x.WhichOneof('firmware_object_info') == name
      ]
      if (file_paths and typ in info.artifact_types):
        output_proto.artifacts.artifacts.add(
            artifact_type=typ, paths=file_paths, location=info.location)

    return resp
