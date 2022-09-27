# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for trigger_gsc_signing.py."""

import json
import logging
from unittest import mock

from chromite.api.gen.chromiumos import common_pb2
from chromite.api.gen.chromiumos import sign_image_pb2
from chromite.lib import cros_test_lib
from chromite.lib import gs
from chromite.scripts import trigger_gsc_signing as trigger


# pylint: disable=protected-access
@mock.patch.object(gs.GSContext, 'Exists', lambda x, y: True)
class TestLaunchOne(cros_test_lib.RunCommandTempDirTestCase):
  """Tests for the LaunchOne function."""

  def setUp(self):
    self.log_info = self.PatchObject(logging, 'info')
    self.properties = {'keyset': 'test-keyest'}
    self.json_prop = json.dumps(self.properties)

  def testDryRunOnlyLogs(self):
    """Test that dry_run=True results in only a log message."""
    trigger.LaunchOne(True, 'chromeos/packaging/test', self.properties)
    self.assertEqual(0, self.rc.call_count)
    self.log_info.assert_called_once()

  def testCallsRun(self):
    """Test that dry_run=False calls run()."""
    trigger.LaunchOne(False, 'chromeos/packaging/test', self.properties)
    self.log_info.assert_not_called()
    self.assertEqual(
        [mock.call(
            ['bb', 'add', '-p', '@/dev/stdin', 'chromeos/packaging/test'],
            input=self.json_prop, log_output=True)],
        self.rc.call_args_list)


@mock.patch.object(gs.GSContext, 'Exists', lambda x, y: True)
class TestMain(cros_test_lib.RunCommandTempDirTestCase):
  """Tests for the main function."""

  def setUp(self):
    self.log_error = self.PatchObject(logging, 'error')

  def testMinimal(self):
    """Test minimal instructions."""
    launch = self.PatchObject(trigger, 'LaunchOne')
    args = ['--archive', 'gs://test/file.bin', '--keyset', 'test-keyset']
    self.assertEqual(0, trigger.main(args))
    launch.assert_called_once_with(
        False, trigger.GSC_PRODUCTION_JOB, {
            'archive': 'gs://test/file.bin',
            'build_target': {'name': 'unknown'},
            'channel': common_pb2.CHANNEL_UNSPECIFIED,
            'gsc_instructions': {
                'target': sign_image_pb2.GscInstructions.PREPVT},
            'image_type': common_pb2.IMAGE_TYPE_GSC_FIRMWARE,
            'keyset': 'test-keyset',
            'signer_type': sign_image_pb2.SIGNER_PRODUCTION})

  def testPropertiesCorrect(self):
    """Test minimal instructions."""
    launch = self.PatchObject(trigger, 'LaunchOne')
    archive = 'gs://test/file.bin'
    keyset = 'keyset'
    channel = 'canary'
    build_target = 'board'
    target = 'prepvt'
    signer = 'production'
    image = 'image_type_gsc_firmware'

    args = ['--archive', archive, '--keyset', keyset, '--channel', channel,
            '--build-target', build_target, '--target', target,
            '--signer-type', signer]
    self.assertEqual(0, trigger.main(args))
    launch.assert_called_once_with(
        False, trigger.GSC_PRODUCTION_JOB, {
            'archive': archive,
            'build_target': {'name': build_target},
            'channel': trigger._channels[channel],
            'gsc_instructions': {'target': trigger._target_types[target]},
            'image_type': trigger._image_types[image],
            'keyset': keyset,
            'signer_type': trigger._signer_types[signer]})

  def testStaging(self):
    """Test --staging works."""
    launch = self.PatchObject(trigger, 'LaunchOne')
    args = ['--archive', 'gs://test/file.bin', '--keyset', 'test-keyset',
            '--staging']
    self.assertEqual(0, trigger.main(args))
    launch.assert_called_once_with(
        False, trigger.GSC_STAGING_JOB, {
            'archive': 'gs://test/file.bin',
            'build_target': {'name': 'unknown'},
            'channel': common_pb2.CHANNEL_UNSPECIFIED,
            'gsc_instructions': {
                'target': sign_image_pb2.GscInstructions.PREPVT},
            'image_type': common_pb2.IMAGE_TYPE_GSC_FIRMWARE,
            'keyset': 'test-keyset',
            'signer_type': sign_image_pb2.SIGNER_PRODUCTION})

  def testDryRun(self):
    """Test --dry-run works."""
    launch = self.PatchObject(trigger, 'LaunchOne')
    args = ['--archive', 'gs://test/file.bin', '--keyset', 'test-keyset',
            '--dry-run']
    self.assertEqual(0, trigger.main(args))
    launch.assert_called_once_with(
        True, trigger.GSC_PRODUCTION_JOB, {
            'archive': 'gs://test/file.bin',
            'build_target': {'name': 'unknown'},
            'channel': common_pb2.CHANNEL_UNSPECIFIED,
            'gsc_instructions': {
                'target': sign_image_pb2.GscInstructions.PREPVT},
            'image_type': common_pb2.IMAGE_TYPE_GSC_FIRMWARE,
            'keyset': 'test-keyset',
            'signer_type': sign_image_pb2.SIGNER_PRODUCTION})

  def testNodeLockedCatchesBadDeviceId(self):
    """Test --target node_locked catches bad --device-id."""
    launch = self.PatchObject(trigger, 'LaunchOne')
    args = ['--archive', 'gs://test/file.bin', '--keyset', 'test-keyset',
            '--target', 'node_locked', '--device-id', '12345678-9ABCDEFG',
            '--dev01', '-1', '0x1234']
    self.assertEqual(1, trigger.main(args))
    launch.assert_not_called()
    self.assertEqual(1, self.log_error.call_count)

  def testNodeLockedRequiresDeviceId(self):
    """Test --target node_locked requires --device-id."""
    launch = self.PatchObject(trigger, 'LaunchOne')
    args = ['--archive', 'gs://test/file.bin', '--keyset', 'test-keyset',
            '--target', 'node_locked']
    self.assertEqual(1, trigger.main(args))
    launch.assert_not_called()
    self.assertEqual(1, self.log_error.call_count)

  def testDeviceIdRequiresNodeLocked(self):
    """Test --device_id is rejected if not node_locked."""
    launch = self.PatchObject(trigger, 'LaunchOne')
    args = ['--archive', 'gs://test/file.bin', '--keyset', 'test-keyset',
            '--target', 'general_release', '--dev01', '1', '0x1234']
    self.assertEqual(1, trigger.main(args))
    launch.assert_not_called()
    self.assertEqual(1, self.log_error.call_count)

  def testNodeLockedLaunchesMultiple(self):
    """Test --target node_locked launches multiple jobs."""
    # Do not mock LaunchOne, so that we can grab the input= passed to run().
    args = ['--archive', 'gs://test/file.bin', '--keyset', 'test-keyset',
            '--target', 'node_locked', '--dev01', '1', '0x1234',
            '--dev01', '2', '33']
    self.assertEqual(0, trigger.main(args))
    self.log_error.assert_not_called()
    expected_properties = [
        {'archive': 'gs://test/file.bin', 'build_target': {'name': 'unknown'},
         'channel': 0,
         'gsc_instructions': {'target': trigger._target_types['node_locked'],
                               'device_id': '00000001-00001234'},
         'signer_type': sign_image_pb2.SIGNER_PRODUCTION,
         'image_type': common_pb2.IMAGE_TYPE_GSC_FIRMWARE,
         'keyset': 'test-keyset'},
        {'archive': 'gs://test/file.bin', 'build_target': {'name': 'unknown'},
         'channel': 0,
         'gsc_instructions': {'target': trigger._target_types['node_locked'],
                               'device_id': '00000002-00000021'},
         'signer_type': sign_image_pb2.SIGNER_PRODUCTION,
         'image_type': common_pb2.IMAGE_TYPE_GSC_FIRMWARE,
         'keyset': 'test-keyset'}]
    # Check the calls in two parts, since we need to convert the json string
    # back to a dict.
    self.assertEqual(self.rc.call_args_list, [
        mock.call(
            ['bb', 'add', '-p', '@/dev/stdin', trigger.GSC_PRODUCTION_JOB],
            log_output=True, input=mock.ANY) for _ in expected_properties])
    self.assertEqual(
        expected_properties,
        [json.loads(x[1]['input']) for x in self.rc.call_args_list])
