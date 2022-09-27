# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Compile the Build API's proto.

Install proto using CIPD to ensure a consistent protoc version.
"""

import enum
import logging
import os
import tempfile

from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import git
from chromite.lib import osutils


_CIPD_ROOT = os.path.join(constants.CHROMITE_DIR, '.cipd_bin')

# Chromite's protobuf library version (third_party/google/protobuf).
PROTOC_VERSION = '3.13.0'


class Error(Exception):
  """Base error class for the module."""


class GenerationError(Error):
  """A failure we can't recover from."""


@enum.unique
class ProtocVersion(enum.Enum):
  """Enum for possible protoc versions."""
  # The SDK version of the bindings use the protoc in the SDK, and so is
  # compatible with the protobuf library in the SDK, i.e. the one installed
  # via the ebuild.
  SDK = enum.auto()
  # The Chromite version of the bindings uses a protoc binary downloaded from
  # CIPD that matches the version of the protobuf library in
  # chromite/third_party/google/protobuf.
  CHROMITE = enum.auto()


def _get_gen_dir(protoc_version: ProtocVersion):
  """Get the chromite/api directory path."""
  if protoc_version is ProtocVersion.SDK:
    return os.path.join(constants.CHROMITE_DIR, 'api', 'gen_sdk')
  else:
    return os.path.join(constants.CHROMITE_DIR, 'api', 'gen')


def _get_protoc_command(protoc_version: ProtocVersion):
  """Get the protoc command for the target protoc."""
  if protoc_version is ProtocVersion.SDK:
    return 'protoc'
  else:
    return os.path.join(_CIPD_ROOT, 'protoc')


def _get_proto_dir(_protoc_version):
  """Get the proto directory for the target protoc."""
  return os.path.join(constants.CHROMITE_DIR, 'infra', 'proto')


def _InstallProtoc(protoc_version: ProtocVersion):
  """Install protoc from CIPD."""
  if protoc_version is not ProtocVersion.CHROMITE:
    return

  logging.info('Installing protoc.')
  cmd = ['cipd', 'ensure']
  # Clean up the output.
  cmd.extend(['-log-level', 'warning'])
  # Set the install location.
  cmd.extend(['-root', _CIPD_ROOT])

  ensure_content = ('infra/tools/protoc/${platform} '
                    'protobuf_version:v%s' % PROTOC_VERSION)
  with osutils.TempDir() as tempdir:
    ensure_file = os.path.join(tempdir, 'cipd_ensure_file')
    osutils.WriteFile(ensure_file, ensure_content)

    cmd.extend(['-ensure-file', ensure_file])

    cros_build_lib.run(cmd, cwd=constants.CHROMITE_DIR, print_cmd=False)


def _CleanTargetDirectory(directory: str):
  """Remove any existing generated files in the directory.

  This clean only removes the generated files to avoid accidentally destroying
  __init__.py customizations down the line. That will leave otherwise empty
  directories in place if things get moved. Neither case is relevant at the
  time of writing, but lingering empty directories seemed better than
  diagnosing accidental __init__.py changes.

  Args:
    directory: Path to be cleaned up.
  """
  logging.info('Cleaning old files from %s.', directory)
  for dirpath, _dirnames, filenames in os.walk(directory):
    old = [os.path.join(dirpath, f) for f in filenames if f.endswith('_pb2.py')]
    # Remove empty init files to clean up otherwise empty directories.
    if '__init__.py' in filenames:
      init = os.path.join(dirpath, '__init__.py')
      if not osutils.ReadFile(init):
        old.append(init)

    for current in old:
      osutils.SafeUnlink(current)


def _GenerateFiles(source: str, output: str, protoc_version: ProtocVersion):
  """Generate the proto files from the |source| tree into |output|.

  Args:
    source: Path to the proto source root directory.
    output: Path to the output root directory.
    protoc_version: Which protoc to use.
  """
  logging.info('Generating files to %s.', output)
  osutils.SafeMakedirs(output)

  targets = []

  chromeos_config_path = os.path.realpath(
      os.path.join(constants.SOURCE_ROOT, 'src/config'))

  with tempfile.TemporaryDirectory() as tempdir:
    if not os.path.exists(chromeos_config_path):
      chromeos_config_path = os.path.join(tempdir, 'config')

      logging.info('Creating shallow clone of chromiumos/config')
      git.Clone(chromeos_config_path,
                '%s/chromiumos/config' % constants.EXTERNAL_GOB_URL,
                depth=1
      )

    # Only compile the subset we need for the API.
    subdirs = [
        os.path.join(source, 'chromite'),
        os.path.join(source, 'chromiumos'),
        os.path.join(source, 'client'),
        os.path.join(source, 'config'),
        os.path.join(source, 'test_platform'),
        os.path.join(source, 'device'),
        os.path.join(chromeos_config_path, 'proto/chromiumos'),
    ]
    for basedir in subdirs:
      for dirpath, _dirnames, filenames in os.walk(basedir):
        for filename in filenames:
          if filename.endswith('.proto'):
            # We have a match, add the file.
            targets.append(os.path.join(dirpath, filename))

    cmd = [
        _get_protoc_command(protoc_version),
        '-I',
        os.path.join(chromeos_config_path, 'proto'),
        '--python_out',
        output,
        '--proto_path',
        source,
    ]
    cmd.extend(targets)

    result = cros_build_lib.run(
        cmd,
        cwd=source,
        print_cmd=False,
        check=False,
        enter_chroot=protoc_version is ProtocVersion.SDK)

    if result.returncode:
      raise GenerationError('Error compiling the proto. See the output for a '
                            'message.')


def _InstallMissingInits(directory):
  """Add any __init__.py files not present in the generated protobuf folders."""
  logging.info('Adding missing __init__.py files in %s.', directory)
  for dirpath, _dirnames, filenames in os.walk(directory):
    if '__init__.py' not in filenames:
      osutils.Touch(os.path.join(dirpath, '__init__.py'))


def _PostprocessFiles(directory: str, protoc_version: ProtocVersion):
  """Do postprocessing on the generated files.

  Args:
    directory: The root directory containing the generated files that are
      to be processed.
    protoc_version: Which protoc is being used to generate the files.
  """
  logging.info('Postprocessing: Fix imports in %s.', directory)
  # We are using a negative address here (the /address/! portion of the sed
  # command) to make sure we don't change any imports from protobuf itself.
  address = '^from google.protobuf'
  # Find: 'from x import y_pb2 as x_dot_y_pb2'.
  # "\(^google.protobuf[^ ]*\)" matches the module we're importing from.
  #   - \( and \) are for groups in sed.
  #   - ^google.protobuf prevents changing the import for protobuf's files.
  #   - [^ ] = Not a space. The [:space:] character set is too broad, but would
  #       technically work too.
  find = r'^from \([^ ]*\) import \([^ ]*\)_pb2 as \([^ ]*\)$'
  # Substitute: 'from chromite.api.gen[_sdk].x import y_pb2 as x_dot_y_pb2'.
  if protoc_version is ProtocVersion.SDK:
    sub = 'from chromite.api.gen_sdk.\\1 import \\2_pb2 as \\3'
  else:
    sub = 'from chromite.api.gen.\\1 import \\2_pb2 as \\3'

  from_sed = [
      'sed', '-i',
      '/%(address)s/!s/%(find)s/%(sub)s/g' % {
          'address': address,
          'find': find,
          'sub': sub
      }
  ]

  seds = [from_sed]
  if protoc_version is ProtocVersion.CHROMITE:
    # We also need to change the google.protobuf imports to point directly
    # at the chromite.third_party version of the library.
    # The SDK version of the proto is meant to be used with the protobuf
    # libraries installed in the SDK, so leave those as google.protobuf.
    g_p_address = '^from google.protobuf'
    g_p_find = r'from \([^ ]*\) import \(.*\)$'
    g_p_sub = 'from chromite.third_party.\\1 import \\2'
    google_protobuf_sed = [
        'sed', '-i',
        '/%(address)s/s/%(find)s/%(sub)s/g' % {
            'address': g_p_address,
            'find': g_p_find,
            'sub': g_p_sub
        }
    ]
    seds.append(google_protobuf_sed)

  for dirpath, _dirnames, filenames in os.walk(directory):
    # Update the imports in the generated files.
    pb2 = [os.path.join(dirpath, f) for f in filenames if f.endswith('_pb2.py')]
    if pb2:
      for sed in seds:
        cmd = sed + pb2
        cros_build_lib.run(cmd, print_cmd=False)


def CompileProto(output: str, protoc_version: ProtocVersion):
  """Compile the Build API protobuf files.

  By default this will compile from infra/proto/src to api/gen. The output
  directory may be changed, but the imports will always be treated as if it is
  in the default location.

  Args:
    output: The output directory.
    protoc_version: Which protoc to use for the compile.
  """
  source = os.path.join(_get_proto_dir(protoc_version), 'src')
  protoc_version = protoc_version or ProtocVersion.CHROMITE

  _InstallProtoc(protoc_version)
  _CleanTargetDirectory(output)
  _GenerateFiles(source, output, protoc_version)
  _InstallMissingInits(output)
  _PostprocessFiles(output, protoc_version)


def GetParser():
  """Build the argument parser."""
  parser = commandline.ArgumentParser(description=__doc__)
  standard_group = parser.add_argument_group(
      'Committed Bindings',
      description='Options for generating the bindings in chromite/api/.')
  standard_group.add_argument(
      '--chromite',
      dest='protoc_version',
      action='append_const',
      const=ProtocVersion.CHROMITE,
      help='Generate only the chromite bindings. Generates all by default. The '
           'chromite bindings are compatible with the version of protobuf in '
           'chromite/third_party.')
  standard_group.add_argument(
      '--sdk',
      dest='protoc_version',
      action='append_const',
      const=ProtocVersion.SDK,
      help='Generate only the SDK bindings. Generates all by default. The SDK '
           'bindings are compiled by protoc in the SDK, and is compatible '
           'with the version of protobuf in the SDK (i.e. the one installed by '
           'the ebuild).')

  dest_group = parser.add_argument_group(
      'Out of Tree Bindings',
      description='Options for generating bindings in a custom location.')
  dest_group.add_argument(
      '--destination',
      type='path',
      help='A directory where a single version of the proto should be '
           'generated. When not given, the proto generates in all default '
           'locations instead.')
  dest_group.add_argument(
      '--dest-sdk',
      action='store_const',
      dest='dest_protoc',
      default=ProtocVersion.CHROMITE,
      const=ProtocVersion.SDK,
      help='Generate the SDK version of the protos in --destination instead of '
           'the chromite version.')
  return parser


def _ParseArguments(argv):
  """Parse and validate arguments."""
  parser = GetParser()
  opts = parser.parse_args(argv)

  if not opts.protoc_version:
    opts.protoc_version = [ProtocVersion.CHROMITE, ProtocVersion.SDK]

  opts.Freeze()
  return opts


def main(argv):
  opts = _ParseArguments(argv)

  if opts.destination:
    # Destination set, only compile a single version in the destination.
    try:
      CompileProto(output=opts.destination, protoc_version=opts.dest_protoc)
    except Error as e:
      cros_build_lib.Die('Error compiling bindings to destination: %s', str(e))
    else:
      return 0

  if ProtocVersion.CHROMITE in opts.protoc_version:
    # Compile the chromite bindings.
    try:
      CompileProto(
          output=_get_gen_dir(ProtocVersion.CHROMITE),
          protoc_version=ProtocVersion.CHROMITE)
    except Error as e:
      cros_build_lib.Die('Error compiling chromite bindings: %s', str(e))

  if ProtocVersion.SDK in opts.protoc_version:
    # Compile the SDK bindings.
    if not cros_build_lib.IsInsideChroot():
      # Rerun inside of the SDK instead of trying to map all of the paths.
      cmd = [
          os.path.join(constants.CHROOT_SOURCE_ROOT, 'chromite', 'api',
                       'compile_build_api_proto'),
          '--sdk',
      ]
      result = cros_build_lib.run(
          cmd, print_cmd=False, enter_chroot=True, check=False)
      return result.returncode
    else:
      try:
        CompileProto(
            output=_get_gen_dir(ProtocVersion.SDK),
            protoc_version=ProtocVersion.SDK)
      except Error as e:
        cros_build_lib.Die('Error compiling SDK bindings: %s', str(e))
