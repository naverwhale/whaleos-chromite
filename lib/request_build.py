# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Code related to Remote tryjobs."""

import collections
import uuid

from chromite.lib import buildbucket_v2
from chromite.lib import config_lib
from chromite.lib import constants
from chromite.third_party.google.protobuf.struct_pb2 import Struct
from chromite.third_party.google.protobuf import duration_pb2
from chromite.third_party.infra_libs.buildbucket.proto import build_pb2, builder_pb2, common_pb2


class RemoteRequestFailure(Exception):
  """Thrown when requesting a tryjob fails."""


# Contains the results of a single scheduled build.
ScheduledBuild = collections.namedtuple(
    'ScheduledBuild',
    ('bucket', 'buildbucket_id', 'build_config', 'url', 'created_ts'))


def ChildBuildSet(parent_buildbucket_id):
  """Compute the buildset id for all slaves of a master builder.

  Args:
    parent_buildbucket_id: The buildbucket id of the master build.

  Returns:
    A string to use as a buildset for the slave builders, or None.
  """
  if not parent_buildbucket_id:
    return None

  return 'cros/parent_buildbucket_id/%s' % parent_buildbucket_id

class RequestBuild(object):
  """Request a builder via buildbucket."""
  # Buildbucket_put response must contain 'buildbucket_bucket:bucket]',
  # '[config:config_name] and '[buildbucket_id:id]'.
  BUILDBUCKET_PUT_RESP_FORMAT = (
      'Successfully sent PUT request to '
      '[buildbucket_bucket:%(bucket)s] '
      'with [config:%(build_config)s] [buildbucket_id:%(buildbucket_id)s].')

  def __init__(self,
               build_config,
               luci_builder=None,
               display_label=None,
               branch='master',
               extra_args=None,
               extra_properties=None,
               user_email=None,
               email_template=None,
               master_cidb_id=None,
               master_buildbucket_id=None,
               bucket=constants.INTERNAL_SWARMING_BUILDBUCKET_BUCKET,
               requested_bot=None):
    """Construct the object.

    Args:
      build_config: A build config name to schedule.
      luci_builder: Name of builder to execute the build, or None.
                    For waterfall builds, this is the name of the build column.
                    For swarming builds, this is the LUCI builder name.
      display_label: String describing how build group on waterfall, or None.
      branch: Name of branch to build for.
      extra_args: Command line arguments to pass to cbuildbot in job.
      extra_properties: Additional input properties to add to the request.
      user_email: Email address of person requesting job, or None.
      email_template: Name of the luci-notify template to use. None for
                      default. Ignored if user_email is not set.
      master_cidb_id: CIDB id of scheduling builder, or None.
      master_buildbucket_id: buildbucket id of scheduling builder, or None.
      bucket: Which bucket do we request the build in?
      requested_bot: Name of bot to prefer (for performance), or None.
    """
    self.bucket = bucket
    self.extra_properties = extra_properties or {}

    site_config = config_lib.GetConfig()
    if build_config in site_config:
      # Extract from build_config, if possible.
      self.luci_builder = site_config[build_config].luci_builder
      self.display_label = site_config[build_config].display_label
      self.workspace_branch = site_config[build_config].workspace_branch
      self.goma_client_type = site_config[build_config].goma_client_type
    else:
      # Use generic defaults if needed (lowest priority)
      self.luci_builder = config_lib.LUCI_BUILDER_TRY
      self.display_label = config_lib.DISPLAY_LABEL_TRYJOB
      self.workspace_branch = None
      self.goma_client_type = None

    # But allow an explicit overrides.
    if luci_builder:
      self.luci_builder = luci_builder

    if display_label:
      self.display_label = display_label

    self.build_config = build_config
    self.branch = branch
    self.extra_args = extra_args
    self.user_email = user_email
    self.email_template = email_template or 'default'
    self.master_cidb_id = master_cidb_id
    self.master_buildbucket_id = master_buildbucket_id
    self.requested_bot = requested_bot

  def CreateBuildRequest(self):
    """Generate the details for Buildbucket V2 request.

    Returns:
      Parameters for V2 ScheduleBuild.
    """
    tags = {
        # buildset identifies a group of related builders.
        'buildset': ChildBuildSet(self.master_buildbucket_id),
        'cbb_display_label': self.display_label,
        'cbb_branch': self.branch,
        'cbb_config': self.build_config,
        'cbb_email': self.user_email,
        'cbb_master_build_id': self.master_cidb_id,
        'cbb_master_buildbucket_id': self.master_buildbucket_id,
        'cbb_workspace_branch': self.workspace_branch,
        'cbb_goma_client_type': self.goma_client_type,
    }

    if self.master_cidb_id or self.master_buildbucket_id:
      # Used by dashboards as part of grouping slave builds. Set to False for
      # slave builds, not set otherwise.
      tags['master'] = 'False'

    # Include the extra_properties we might have passed into the tags.
    tags.update(self.extra_properties)

    # Don't include tags with no value, there is no point.
    # Convert tag values to strings.
    #
    # Note that cbb_master_build_id must be a string (not a number) in
    # properties because JSON does not distnguish integers and floats, so
    # nothing guarantees that 0 won't turn into 0.0.
    # Recipe expects it to be a string anyway.
    tags = {k: str(v) for k, v in tags.items() if v}

    properties = Struct()
    properties.update({k: str(v) for k, v in tags.items() if v})
    properties.update({'cbb_extra_args': self.extra_args})
    if self.user_email:
      properties.update({'email_notify': [{
          'email': self.user_email,
          'template': self.email_template,
          }]
      })

    tags_proto = []
    for k, v in sorted(tags.items()):
      if v:
        tags_proto.append(common_pb2.StringPair(key=k,value=v))
    dimensions = []

    # If a specific bot was requested, pass along the request with a
    # 240 second (4 minute) timeout. If the bot isn't available, we
    # will fall back to the general builder restrictions (probably
    # based on role).
    if self.requested_bot:
      dimensions = [common_pb2.RequestedDimension(
        key='id',
        value=self.requested_bot,
        expiration=duration_pb2.Duration(seconds=240))]
    return {
        'request_id': uuid.uuid1(),
        'builder': builder_pb2.BuilderID(project='chromeos',
                                      bucket=self.bucket,
                                      builder=self.luci_builder),
        'properties': properties,
        'tags': tags_proto,
        'dimensions': dimensions if dimensions else None,
    }

  def Submit(self, dryrun=False):
    """Submit the tryjob through Git.

    Args:
      dryrun: Setting to true will run everything except the final submit step.

    Returns:
      A ScheduledBuild instance.
    """
    buildbucket_client = buildbucket_v2.BuildbucketV2()
    request = self.CreateBuildRequest()
    if dryrun:
      return build_pb2.Build(id='1')
    return buildbucket_client.ScheduleBuild(
      request_id=str(request['request_id']),
      builder=request['builder'],
      properties=request['properties'],
      tags=request['tags'],
      dimensions=request['dimensions'])
