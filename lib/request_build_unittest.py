# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for request_build.py."""

from chromite.third_party.google.protobuf.struct_pb2 import Struct

from chromite.lib import buildbucket_v2
from chromite.lib import config_lib
from chromite.lib import constants
from chromite.lib import cros_test_lib
from chromite.lib import request_build
from chromite.third_party.infra_libs.buildbucket.proto import build_pb2, builder_pb2, common_pb2


# Tests need internal access.
# pylint: disable=protected-access


class RequestBuildHelperTestsBase(cros_test_lib.MockTestCase):
  """Tests for RequestBuild."""
  BRANCH = 'test-branch'
  PATCHES = ('5555', '6666')
  BUILD_CONFIG_MIN = 'amd64-generic-paladin-tryjob'
  BUILD_CONFIG_MAX = 'amd64-generic-paladin'
  UNKNOWN_CONFIG = 'unknown-config'
  LUCI_BUILDER = 'luci_build'
  DISPLAY_LABEL = 'display'
  PASS_THROUGH_ARGS = ['funky', 'cold', 'medina']
  TEST_EMAIL = 'explicit_email'
  TEST_TEMPLATE = 'explicit_template'
  MASTER_CIDB_ID = 'master_cidb_id'
  MASTER_BUILDBUCKET_ID = 'master_bb_id'
  TEST_BUCKET = 'luci.chromeos.general'  # Use Prod bucket for network test.
  EXTRA_PROPERTIES = {'full_version': 'R84-13099.77.0'}

  def _CreateJobMin(self):
    return request_build.RequestBuild(build_config=self.BUILD_CONFIG_MIN)

  def _CreateJobMax(self):
    return request_build.RequestBuild(
        build_config=self.BUILD_CONFIG_MAX,
        luci_builder=self.LUCI_BUILDER,
        display_label=self.DISPLAY_LABEL,
        branch=self.BRANCH,
        extra_args=self.PASS_THROUGH_ARGS,
        extra_properties=self.EXTRA_PROPERTIES,
        user_email=self.TEST_EMAIL,
        email_template=self.TEST_TEMPLATE,
        master_cidb_id=self.MASTER_CIDB_ID,
        master_buildbucket_id=self.MASTER_BUILDBUCKET_ID,
        bucket=self.TEST_BUCKET,
        requested_bot='botname')

  def _CreateJobUnknown(self):
    return request_build.RequestBuild(
        build_config=self.UNKNOWN_CONFIG,
        display_label=self.DISPLAY_LABEL,
        branch='master',
        extra_args=[],
        user_email='default_email',
        master_buildbucket_id=None)


class RequestBuildHelperTestsMock(RequestBuildHelperTestsBase):
  """Perform real buildbucket requests against a fake instance."""

  def setUp(self):
    # This mocks out the class, then creates a return_value for a function on
    # instances of it. We do this instead of just mocking out the function to
    # ensure not real network requests are made in other parts of the class.
    client_mock = self.PatchObject(buildbucket_v2, 'BuildbucketV2')
    client_mock().ScheduleBuilder.return_value = build_pb2.Build(
        id=12345,
    )

  def testMinCreateRequestBody(self):
    """Verify our request body with min options."""
    job = self._CreateJobMin()

    self.assertEqual(job.bucket, constants.INTERNAL_SWARMING_BUILDBUCKET_BUCKET)
    self.assertEqual(job.luci_builder, config_lib.LUCI_BUILDER_TRY)
    self.assertEqual(job.display_label, config_lib.DISPLAY_LABEL_TRYJOB)

    body = job.CreateBuildRequest()

    self.assertEqual(builder_pb2.BuilderID(
        project='chromeos',
        bucket=constants.INTERNAL_SWARMING_BUILDBUCKET_BUCKET,
        builder=config_lib.LUCI_BUILDER_TRY),
        body['builder'])
    self.assertEqual(
        [common_pb2.StringPair(
             key='cbb_branch',
             value='master'),
         common_pb2.StringPair(
             key='cbb_config',
             value='amd64-generic-paladin-tryjob'),
         common_pb2.StringPair(
             key='cbb_display_label',
             value='tryjob'),
        ], body['tags'])

  def testMaxRequestBody(self):
    """Verify our request body with max options."""
    job = self._CreateJobMax()

    self.assertEqual(job.bucket, self.TEST_BUCKET)
    self.assertEqual(job.luci_builder, self.LUCI_BUILDER)
    self.assertEqual(job.display_label, 'display')

    body = job.CreateBuildRequest()

    self.assertEqual(builder_pb2.BuilderID(
        project='chromeos',
        bucket=self.TEST_BUCKET,
        builder=self.LUCI_BUILDER),
        body['builder'])

    self.assertEqual(
        [common_pb2.StringPair(
            key='buildset',
            value='cros/parent_buildbucket_id/master_bb_id'),
         common_pb2.StringPair(
             key='cbb_branch',
             value='test-branch'),
         common_pb2.StringPair(
             key='cbb_config',
             value='amd64-generic-paladin'),
         common_pb2.StringPair(
             key='cbb_display_label',
             value='display'),
         common_pb2.StringPair(
             key='cbb_email',
             value='explicit_email'),
         common_pb2.StringPair(
             key='cbb_master_build_id',
             value='master_cidb_id'),
         common_pb2.StringPair(
             key='cbb_master_buildbucket_id',
             value='master_bb_id'),
         common_pb2.StringPair(
             key='full_version',
             value='R84-13099.77.0'),
         common_pb2.StringPair(
             key='master',
             value='False'),
        ],
        body['tags'],
    )
    props = {
        u'buildset': u'cros/parent_buildbucket_id/master_bb_id',
        u'cbb_branch': u'test-branch',
        u'cbb_config': u'amd64-generic-paladin',
        u'cbb_display_label': u'display',
        u'cbb_email': u'explicit_email',
        u'cbb_master_build_id': u'master_cidb_id',
        u'cbb_master_buildbucket_id': u'master_bb_id',
        u'full_version': u'R84-13099.77.0',
        u'master': u'False',
    }
    test_properties = Struct()
    test_properties.update({k: str(v) for k, v in props.items() if v})
    test_properties.update({'cbb_extra_args': [u'funky', u'cold', u'medina']})
    test_properties.update({'email_notify': [{
          'email': 'explicit_email',
          'template': 'explicit_template',
          }]
    })
    self.assertEqual(
        test_properties,
        body['properties'],
    )

  def testUnknownRequestBody(self):
    """Verify our request body with max options."""
    job = self._CreateJobUnknown()
    body = job.CreateBuildRequest()

    self.assertEqual(builder_pb2.BuilderID(
        project='chromeos',
        bucket=constants.INTERNAL_SWARMING_BUILDBUCKET_BUCKET,
        builder=config_lib.LUCI_BUILDER_TRY),
        body['builder'])
    self.assertEqual(
        [common_pb2.StringPair(
            key='cbb_branch',
            value='master'),
         common_pb2.StringPair(
             key='cbb_config',
             value='unknown-config'),
         common_pb2.StringPair(
             key='cbb_display_label',
             value='display'),
         common_pb2.StringPair(
             key='cbb_email',
             value='default_email'),
        ],
        body['tags'],
    )
    props = {
            u'cbb_display_label': u'display',
            u'cbb_branch': u'master',
            u'cbb_config': u'unknown-config',
            u'cbb_email': u'default_email',
    }
    test_properties = Struct()
    test_properties.update({k: str(v) for k, v in props.items() if v})
    test_properties.update({'cbb_extra_args': job.extra_args})
    test_properties.update({'email_notify': [{
          'email': 'default_email',
          'template': 'default',
          }]
    })
    self.assertEqual(body['properties'], test_properties)

  def testLogGeneration(self):
    """Validate an import log message."""
    sb = request_build.ScheduledBuild(
        'bucket', 'buildbucket_id', 'build_config', 'url', 'created_ts')

    msg = request_build.RequestBuild.BUILDBUCKET_PUT_RESP_FORMAT % sb._asdict()

    expected = ('Successfully sent PUT request to [buildbucket_bucket:bucket] '
                'with [config:build_config] [buildbucket_id:buildbucket_id].')

    # This test both validates that we can generate the log message, and that
    # it's format hasn't changed. Since there are scripts that parse it via
    # regex, the later is important.
    self.assertEqual(msg, expected)


class RequestBuildHelperTestsNetork(RequestBuildHelperTestsBase):
  """Perform real buildbucket requests against a test instance."""
  def verifyBuildbucketRequest(self,
                               buildbucket_id,
                               expected_bucket,
                               expected_tags,
                               expected_properties):
    """Verify the contents of a push to the TEST buildbucket instance.

    Args:
      buildbucket_id: Id to verify.
      expected_bucket: Bucket the push was supposed to go to as a string.
      expected_tags: List of buildbucket tags.
      expected_properties: List of buildbucket properties.
    """
    client = buildbucket_v2.BuildbucketV2(test_env=True)
    request = client.GetBuild(buildbucket_id)

    self.assertEqual(request.id, buildbucket_id)
    self.assertEqual(request.builder.bucket, expected_bucket)
    self.assertCountEqual(request.tags, expected_tags)
    self.assertCountEqual(request.properties, expected_properties)

  @cros_test_lib.pytestmark_network_test
  def testMinTestBucket(self):
    """Talk to a test buildbucket instance with min job settings."""
    job = self._CreateJobMin()
    request = job.CreateBuildRequest()
    client = buildbucket_v2.BuildbucketV2(test_env=True)
    result = client.ScheduleBuild(
        request_id=request.request_id,
        builder=request.builder,
        properties=request.properties,
        tags=request.tags,
        dimensions=request.dimensions,
    )
    props = {
        u'builder_name': u'Try',
        u'properties': {
          u'cbb_branch': u'master',
          u'cbb_config': u'amd64-generic-paladin-tryjob',
          u'cbb_display_label': u'tryjob',
          u'cbb_extra_args': [],
        },
    }
    expected_properties = Struct()
    expected_properties.update({k: str(v) for k, v in props.items() if v})

    self.verifyBuildbucketRequest(
        result.id,
        'luci.chromeos.general',
        [common_pb2.StringPair(
             key='cbb_branch',
             value='master'),
         common_pb2.StringPair(
             key='cbb_config',
             value='amd64-generic-paladin-tryjob'),
         common_pb2.StringPair(
             key='cbb_display_label',
             value='tryjob'),
        ],
        expected_properties)

  @cros_test_lib.pytestmark_network_test
  def testMaxTestBucket(self):
    """Talk to a test buildbucket instance with max job settings."""
    job = self._CreateJobMax()
    request = job.CreateBuildRequest()
    client = buildbucket_v2.BuildbucketV2(test_env=True)
    result = client.ScheduleBuild(
        request_id=request.request_id,
        builder=request.builder,
        properties=request.properties,
        tags=request.tags,
        dimensions=request.dimensions,
    )
    props = {
        u'buildset': u'cros/parent_buildbucket_id/master_bb_id',
        u'cbb_branch': u'test-branch',
        u'cbb_config': u'amd64-generic-paladin',
        u'cbb_display_label': u'display',
        u'cbb_email': u'explicit_email',
        u'cbb_extra_args': [u'funky', u'cold', u'medina'],
        u'cbb_master_build_id': u'master_cidb_id',
        u'cbb_master_buildbucket_id': u'master_bb_id',
        u'master': u'False',
    }
    expected_properties = Struct()
    expected_properties.update({k: str(v) for k, v in props.items() if v})

    self.verifyBuildbucketRequest(
        result.id,
        self.TEST_BUCKET,
        [common_pb2.StringPair(
            key='buildset',
            value='cros/parent_buildbucket_id/master_bb_id'),
         common_pb2.StringPair(
             key='cbb_branch',
             value='test-branch'),
         common_pb2.StringPair(
             key='cbb_config',
             value='amd64-generic-paladin'),
         common_pb2.StringPair(
             key='cbb_display_label',
             value='display'),
         common_pb2.StringPair(
             key='cbb_email',
             value='explicit_email'),
         common_pb2.StringPair(
             key='cbb_master_build_id',
             value='master_cidb_id'),
         common_pb2.StringPair(
             key='cbb_master_buildbucket_id',
             value='master_bb_id'),
         common_pb2.StringPair(
             key='full_version',
             value='R84-13099.77.0'),
         common_pb2.StringPair(
             key='master',
             value='False'),
        ],
        expected_properties)
