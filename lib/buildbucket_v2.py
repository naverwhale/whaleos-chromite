# Copyright 2018 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Chromite Buildbucket V2 client wrapper and helpers.

The client constructor and methods here are tailored to Chromite's
usecases. Other users should, instead, prefer to copy the Python
client out of lib/luci/prpc and third_party/infra_libs/buildbucket.
"""

import ast
import collections
import http.client
import logging
import socket
from ssl import SSLError
from typing import Callable, Optional

from chromite.third_party.google.protobuf import field_mask_pb2
from chromite.third_party.infra_libs.buildbucket.proto import (
    builder_common_pb2,
    builds_service_pb2,
    builds_service_prpc_pb2,
    common_pb2,
)

from chromite.cbuildbot import cbuildbot_alerts
from chromite.lib import constants
from chromite.lib import retry_util
from chromite.lib.luci import utils
from chromite.lib.luci.prpc.client import Client
from chromite.lib.luci.prpc.client import ProtocolError


BBV2_URL_ENDPOINT_PROD = "cr-buildbucket.appspot.com"
BBV2_URL_ENDPOINT_TEST = "cr-buildbucket-test.appspot.com"
BB_STATUS_DICT = {
    # A mapping of Buildbucket V2 statuses to chromite's statuses. For
    # buildbucket reference, see here:
    # https://chromium.googlesource.com/infra/luci/luci-go/+/HEAD/buildbucket/proto/common.proto
    0: "unspecified",
    1: constants.BUILDER_STATUS_PLANNED,
    2: constants.BUILDER_STATUS_INFLIGHT,
    12: constants.BUILDER_STATUS_PASSED,
    20: constants.BUILDER_STATUS_FAILED,
    68: constants.BUILDER_STATUS_ABORTED,
}

# Namedtupe to store buildbucket related info.
BuildbucketInfo = collections.namedtuple(
    "BuildbucketInfo",
    ["buildbucket_id", "retry", "created_ts", "status", "url"],
)


class BuildbucketResponseException(Exception):
    """Exception got from Buildbucket Response."""


class NoBuildbucketBucketFoundException(Exception):
    """Failed to found the corresponding buildbucket bucket."""


class NoBuildbucketClientException(Exception):
    """No Buildbucket client exception."""


def GetScheduledBuildDict(scheduled_slave_list):
    """Parse the build information from the scheduled_slave_list metadata.

    Treats all listed builds as newly-scheduled.

    Args:
        scheduled_slave_list: A list of scheduled builds recorded in the
            orchestrator metadata. In the format of
            [(build_config, buildbucket_id, created_ts)].

    Returns:
        A dict mapping build config name to its buildbucket information
        (in the format of BuildbucketInfo).
    """
    if scheduled_slave_list is None:
        return {}

    buildbucket_info_dict = {}
    for build_config, buildbucket_id, created_ts in scheduled_slave_list:
        if build_config not in buildbucket_info_dict:
            buildbucket_info_dict[build_config] = BuildbucketInfo(
                buildbucket_id, 0, created_ts, None, None
            )
        else:
            old_info = buildbucket_info_dict[build_config]
            # If a slave occurs multiple times, increment retry count and keep
            # the buildbucket_id and created_ts of most recently created one.
            new_retry = old_info.retry + 1
            if created_ts > buildbucket_info_dict[build_config].created_ts:
                buildbucket_info_dict[build_config] = BuildbucketInfo(
                    buildbucket_id, new_retry, created_ts, None, None
                )
            else:
                buildbucket_info_dict[build_config] = BuildbucketInfo(
                    old_info.buildbucket_id,
                    new_retry,
                    old_info.created_ts,
                    None,
                    None,
                )

    return buildbucket_info_dict


def GetBuildInfoDict(metadata, exclude_experimental=True):
    """Get buildbucket_info_dict from metadata.

    Args:
        metadata: Instance of metadata_lib.CBuildbotMetadata.
        exclude_experimental: Whether to exclude the builds which are important
            in the config but are marked as experimental in the tree status.
            Default to True.

    Returns:
        buildbucket_info_dict: A dict mapping build config name to its
            buildbucket information in the format of BuildbucketInfo. Build
            configs that are marked experimental through the tree status will
            not be in the dict. (See GetScheduledBuildDict for details.)
    """
    assert metadata is not None

    scheduled_slaves_list = metadata.GetValueWithDefault(
        constants.METADATA_SCHEDULED_IMPORTANT_SLAVES, []
    )

    if exclude_experimental:
        experimental_builders = metadata.GetValueWithDefault(
            constants.METADATA_EXPERIMENTAL_BUILDERS, []
        )
        scheduled_slaves_list = [
            (config, bb_id, ts)
            for config, bb_id, ts in scheduled_slaves_list
            if config not in experimental_builders
        ]

    return GetScheduledBuildDict(scheduled_slaves_list)


def GetBuildbucketIds(metadata, exclude_experimental=True):
    """Get buildbucket_ids of scheduled slave builds from metadata.

    Args:
        metadata: Instance of metadata_lib.CBuildbotMetadata.
        exclude_experimental: Whether to exclude the builds which are important
            in the config but are marked as experimental in the tree status.
            Default to True.

    Returns:
        A list of buildbucket_ids (string) of slave builds.
    """
    buildbucket_info_dict = GetBuildInfoDict(
        metadata, exclude_experimental=exclude_experimental
    )
    return [
        info_dict.buildbucket_id for info_dict in buildbucket_info_dict.values()
    ]


def FetchCurrentSlaveBuilders(
    config, metadata, builders_array, exclude_experimental=True
):
    """Fetch the current important slave builds.

    Args:
        config: Instance of config_lib.BuildConfig. Config dict of this build.
        metadata: Instance of metadata_lib.CBuildbotMetadata. Metadata of this
            build.
        builders_array: A list of slave build configs to check.
        exclude_experimental: Whether to exclude the builds which are important
            in the config but are marked as experimental in the tree status.
            Default to True.

    Returns:
        An updated list of slave build configs for a orchestrator build.
    """
    if config and metadata:
        scheduled_buildbucket_info_dict = GetBuildInfoDict(
            metadata, exclude_experimental=exclude_experimental
        )
        return list(scheduled_buildbucket_info_dict)
    else:
        return builders_array


def GetStringPairValue(content, path, key, default=None):
    """Get the value of a repeated StringValue pair.

    Get the (nested) value from a nested dict.

    Args:
        content: A dict of (nested) attributes.
        path: String list presenting the (nested) attribute to get.
        key: String representing which key to find.
        default: Default value to return if the attribute doesn't exist.

    Returns:
        The corresponding value if the attribute exists; else, default.
    """
    assert isinstance(path, list), "nested_attr must be a list."

    if content is None:
        return default

    assert isinstance(content, dict), "content must be a dict."

    value = None
    path_value = content
    for attr in path:
        assert isinstance(attr, str), "attribute name must be a string."

        if not isinstance(path_value, dict):
            return default

        path_value = path_value.get(attr, default)

    for sp in path_value:
        dimensions_kv = list(sp.items())
        for i, (k, v) in enumerate(dimensions_kv):
            dimensions_kv[i] = (
                k,
                [
                    v,
                ],
            )
            if v == key:
                if len(dimensions_kv) >= i + 1:
                    return dimensions_kv[i + 1][i + 1]
    return value


def UpdateSelfBuildPropertiesNonBlocking(key, value):
    """Updates the build.output.properties with key:value through a service.

    Butler is a ChOps service that reads in logs and updates Buildbucket of the
    properties. This method has no guarantees on the timeliness of updating
    the property.

    Args:
        key: name of the property.
        value: value of the property.
    """
    if key == "email_notify":
        cbuildbot_alerts.PrintKitchenSetEmailNotifyProperty(key, value)
    else:
        cbuildbot_alerts.PrintKitchenSetBuildProperty(key, value)


def UpdateSelfCommonBuildProperties(
    critical=None,
    cidb_id=None,
    chrome_version=None,
    milestone_version=None,
    platform_version=None,
    full_version=None,
    toolchain_url=None,
    build_type=None,
    unibuild=None,
    suite_scheduling=None,
    killed_child_builds=None,
    board=None,
    main_firmware_version=None,
    ec_firmware_version=None,
    metadata_url=None,
    channels=None,
    email_notify=None,
):
    """Update build.output.properties for the current build.

    Sends the property values to buildbucket via
    UpdateSelfBuildPropertiesNonBlocking. All arguments are optional.

    Args:
        critical: |important| flag of the build.
        cidb_id: CIDB ID of the build.
        chrome_version: version of chrome of the build. E.g., "74.0.3687.0".
        milestone_version: milestone version of  of the build. E.g., "74".
        platform_version: platform version of the build. E.g., "11671.0.0".
        full_version: full version of the build. E.g., "R74-11671.0.0-b3416654".
        toolchain_url: toolchain_url of the build.
        build_type: One of ('full', 'canary', ...).
        unibuild: Boolean indicating whether build is unibuild.
        suite_scheduling:
        killed_child_builds: A list of Buildbucket IDs of child
            builds that were killed by self-destructed orchestrator build.
        board: board of the build.
        main_firmware_version: main firmware version of the build.
        ec_firmware_version: ec_firmware version of the build.
        metadata_url: google storage url to metadata.json of the build.
        channels: list of channels the build are configured for. E.g.,
            [beta,stable].
        email_notify: list of luci-notify email_notify values
            representing the recipients of failure alerts to for this builder.
    """
    if critical is not None:
        critical = 1 if critical in [1, True] else 0
        UpdateSelfBuildPropertiesNonBlocking("critical", critical)
    if cidb_id is not None:
        UpdateSelfBuildPropertiesNonBlocking("cidb_id", cidb_id)
    if chrome_version is not None:
        UpdateSelfBuildPropertiesNonBlocking("chrome_version", chrome_version)
    if milestone_version is not None:
        UpdateSelfBuildPropertiesNonBlocking(
            "milestone_version", milestone_version
        )
    if platform_version is not None:
        UpdateSelfBuildPropertiesNonBlocking(
            "platform_version", platform_version
        )
    if full_version is not None:
        UpdateSelfBuildPropertiesNonBlocking("full_version", full_version)
    if toolchain_url is not None:
        UpdateSelfBuildPropertiesNonBlocking("toolchain_url", toolchain_url)
    if build_type is not None:
        UpdateSelfBuildPropertiesNonBlocking("build_type", build_type)
    if unibuild is not None:
        UpdateSelfBuildPropertiesNonBlocking("unibuild", unibuild)
    if suite_scheduling is not None:
        UpdateSelfBuildPropertiesNonBlocking(
            "suite_scheduling", suite_scheduling
        )
    if killed_child_builds is not None:
        UpdateSelfBuildPropertiesNonBlocking(
            "killed_child_builds", str(killed_child_builds)
        )
    if board is not None:
        UpdateSelfBuildPropertiesNonBlocking("board", board)
    if main_firmware_version is not None:
        UpdateSelfBuildPropertiesNonBlocking(
            "main_firmware_version", main_firmware_version
        )
    if ec_firmware_version is not None:
        UpdateSelfBuildPropertiesNonBlocking(
            "ec_firmware_version", ec_firmware_version
        )
    if metadata_url is not None:
        UpdateSelfBuildPropertiesNonBlocking("metadata_url", metadata_url)
    if channels is not None:
        UpdateSelfBuildPropertiesNonBlocking("channels", channels)
    if email_notify is not None:
        UpdateSelfBuildPropertiesNonBlocking("email_notify", email_notify)


def UpdateBuildMetadata(metadata):
    """Update build.output.properties from a CBuildbotMetadata instance.

    The function further uses UpdateSelfCommonBuildProperties and has hence
    no guarantee of timely updation.

    Args:
        metadata: CBuildbot Metadata instance to update with.
    """
    d = metadata.GetDict()
    versions = d.get("version") or {}
    UpdateSelfCommonBuildProperties(
        chrome_version=versions.get("chrome"),
        milestone_version=versions.get("milestone"),
        platform_version=versions.get("platform"),
        full_version=versions.get("full"),
        toolchain_url=d.get("toolchain-url"),
        build_type=d.get("build_type"),
        critical=d.get("important"),
        unibuild=d.get("unibuild", False),
        suite_scheduling=d.get("suite_scheduling", False),
        channels=d.get("channels", None),
    )


def BuildStepToDict(step, build_values=None):
    """Extract information from a Buildbucket Step instance.

    Reference:
    https://chromium.googlesource.com/infra/luci/luci-go/+/HEAD/buildbucket/proto/step.proto

    Args:
        step: A step_pb2.Step instance from Buildbucket to be extracted.
        build_values: A dictionary of values to be included in the result.

    Returns:
        A dictionary with the following keys: name, status, start_time and
        end_time in addition to the keys in build_values.
    """
    step_info = {"name": step.name}
    if step.status is not None and step.status in BB_STATUS_DICT:
        step_info["status"] = BB_STATUS_DICT[step.status]
    else:
        step_info["status"] = None
    step_info["start_time"] = utils.TimestampToDatetime(step.start_time)
    step_info["finish_time"] = utils.TimestampToDatetime(step.end_time)

    if build_values:
        step_info.update(build_values)
    return step_info


def DateToTimeRange(start_date=None, end_date=None):
    """Convert two datetime.date objects into a TimeRange instance.

    Args:
        start_date: datetime.date instance to mark the start of the TimeRange.
        end_date: datetime.date instance to mark the end of the TimeRange.

    Returns:
        A TimeRange object corresponding to the time interval
        (start_date, end_date).
    """
    if not (start_date or end_date):
        return None
    if start_date:
        start_timestamp = utils.DatetimeToTimestamp(start_date)
    else:
        start_timestamp = None
    if end_date:
        end_timestamp = utils.DatetimeToTimestamp(end_date, end_of_day=True)
    else:
        end_timestamp = None
    return common_pb2.TimeRange(
        start_time=start_timestamp, end_time=end_timestamp
    )


def GetBotId(build):
    """Return the bot id that ran a build, or None.

    Args:
        build: BuildbucketV2 build

    Returns:
        hostname: Swarming hostname
    """
    # This produces a list of bot_ids for each build (or None).
    # I don't think there can ever be more than one entry in the list, but
    # could be zero.
    bot_id = GetStringPairValue(
        build, ["infra", "swarming", "botDimensions"], "id"
    )
    if not bot_id:
        return None

    return bot_id


class BuildbucketV2:
    """Connection to Buildbucket V2 database."""

    def __init__(
        self,
        test_env=False,
        access_token_retriever: Optional[Callable[[], str]] = None,
    ):
        """Constructor for Buildbucket V2 Build client.

        Args:
            test_env: Whether to have the client connect to test URL endpoint
                on GAE.
            access_token_retriever: An optional callable that returns an access
                token.
        """
        if test_env:
            self.client = Client(
                BBV2_URL_ENDPOINT_TEST,
                builds_service_prpc_pb2.BuildsServiceDescription,
            )
        else:
            self.client = Client(
                BBV2_URL_ENDPOINT_PROD,
                builds_service_prpc_pb2.BuildsServiceDescription,
            )

        self._access_token_retriever = access_token_retriever

    # TODO(crbug/1006818): Need to handle ResponseNotReady given by luci prpc.
    @retry_util.WithRetry(max_retry=5, sleep=20.0, exception=SSLError)
    @retry_util.WithRetry(max_retry=5, sleep=20.0, exception=socket.error)
    @retry_util.WithRetry(
        max_retry=5, sleep=20.0, exception=http.client.ResponseNotReady
    )
    def BatchCancelBuilds(
        self, buildbucket_ids, summary_markdown, properties=None
    ):
        """BatchGetBuild repeated GetBuild request with provided ids.

        Args:
            buildbucket_ids: list of ids of the builds in buildbucket.
            summary_markdown: summary of reason for cancel.
            properties: fields to include in the response.

        Returns:
            The corresponding BatchResponse message. See here:
            https://chromium.googlesource.com/infra/luci/luci-go/+/HEAD/buildbucket/proto/builds_service.proto
        """
        batch_requests = []
        for buildbucket_id in buildbucket_ids:
            logging.info("Canceling buildbucket_id: %s", str(buildbucket_id))
            if isinstance(buildbucket_id, str):
                buildbucket_id = int(buildbucket_id)
            batch_requests.append(
                builds_service_pb2.BatchRequest.Request(
                    cancel_build=(
                        builds_service_pb2.CancelBuildRequest(
                            id=buildbucket_id,
                            summary_markdown=summary_markdown,
                            fields=(
                                field_mask_pb2.FieldMask(paths=[properties])
                                if properties
                                else None
                            ),
                        )
                    )
                )
            )
        return self.client.Batch(
            builds_service_pb2.BatchRequest(requests=batch_requests),
            **self._client_kwargs,
        )

    # TODO(crbug/1006818): Need to handle ResponseNotReady given by luci prpc.
    @retry_util.WithRetry(max_retry=5, sleep=20.0, exception=SSLError)
    @retry_util.WithRetry(max_retry=5, sleep=20.0, exception=socket.error)
    @retry_util.WithRetry(
        max_retry=5, sleep=20.0, exception=http.client.ResponseNotReady
    )
    def BatchGetBuilds(self, buildbucket_ids, properties=None):
        """BatchGetBuild repeated GetBuild request with provided ids.

        Args:
            buildbucket_ids: list of ids of the builds in buildbucket.
            properties: fields to include in the response.

        Returns:
            The corresponding BatchResponse message. See here:
            https://chromium.googlesource.com/infra/luci/luci-go/+/HEAD/buildbucket/proto/builds_service.proto
        """
        batch_requests = []
        for buildbucket_id in buildbucket_ids:
            batch_requests.append(
                builds_service_pb2.BatchRequest.Request(
                    get_build=(
                        builds_service_pb2.GetBuildRequest(
                            id=buildbucket_id,
                            fields=(
                                field_mask_pb2.FieldMask(paths=[properties])
                                if properties
                                else None
                            ),
                        )
                    )
                )
            )
        return self.client.Batch(
            builds_service_pb2.BatchRequest(requests=batch_requests),
            **self._client_kwargs,
        )

    # TODO(crbug/1006818): Need to handle ResponseNotReady given by luci prpc.
    @retry_util.WithRetry(max_retry=5, sleep=60.0, exception=SSLError)
    @retry_util.WithRetry(max_retry=5, sleep=60.0, exception=socket.error)
    @retry_util.WithRetry(max_retry=5, sleep=60.0, exception=socket.timeout)
    @retry_util.WithRetry(
        max_retry=5, sleep=60.0, exception=http.client.ResponseNotReady
    )
    def BatchSearchBuilds(self, search_requests):
        """SearchBuild RPC call wrapping function.

        Args:
            search_requests: List of SearchBuildRequests

        Returns:
            The corresponding BatchResponse message. See here:
            https://chromium.googlesource.com/infra/luci/luci-go/+/HEAD/buildbucket/proto/builds_service.proto
        """
        requests = []
        for request in search_requests:
            requests.append(
                builds_service_pb2.BatchRequest.Request(search_builds=request)
            )
        return self.client.Batch(
            builds_service_pb2.BatchRequest(requests=requests),
            **self._client_kwargs,
        )

    # TODO(crbug/1006818): Need to handle ResponseNotReady given by luci prpc.
    @retry_util.WithRetry(max_retry=5, sleep=20.0, exception=SSLError)
    @retry_util.WithRetry(max_retry=5, sleep=20.0, exception=socket.error)
    @retry_util.WithRetry(
        max_retry=5, sleep=20.0, exception=http.client.ResponseNotReady
    )
    def CancelBuild(self, buildbucket_id, summary_markdown, properties=None):
        """CancelBuild call of a specific build with buildbucket_id.

        Args:
            buildbucket_id: id of the build in buildbucket.
            summary_markdown: summary of reason for cancel.
            properties: fields to include in the response.

        Returns:
            The corresponding Build proto. See here:
            https://chromium.googlesource.com/infra/luci/luci-go/+/HEAD/buildbucket/proto/build.proto
        """
        cancel_build_request = builds_service_pb2.CancelBuildRequest(
            id=buildbucket_id,
            summary_markdown=summary_markdown,
            fields=(
                field_mask_pb2.FieldMask(paths=[properties])
                if properties
                else None
            ),
        )
        return self.client.CancelBuild(
            cancel_build_request, **self._client_kwargs
        )

    # TODO(crbug/1006818): Need to handle ResponseNotReady given by luci prpc.
    @retry_util.WithRetry(max_retry=5, sleep=20.0, exception=SSLError)
    @retry_util.WithRetry(max_retry=5, sleep=20.0, exception=socket.error)
    @retry_util.WithRetry(
        max_retry=5, sleep=20.0, exception=http.client.ResponseNotReady
    )
    def GetBuild(self, buildbucket_id, properties=None):
        """GetBuild call of a specific build with buildbucket_id.

        Args:
            buildbucket_id: id of the build in buildbucket.
            properties: list or string of fields to include in the response.

        Returns:
            The corresponding Build proto. See here:
            https://chromium.googlesource.com/infra/luci/luci-go/+/HEAD/buildbucket/proto/build.proto
        """
        field_mask = []
        if isinstance(properties, list):
            field_mask = properties
        elif properties:
            field_mask.append(properties)
        get_build_request = builds_service_pb2.GetBuildRequest(
            id=buildbucket_id,
            fields=(
                field_mask_pb2.FieldMask(paths=field_mask)
                if field_mask
                else None
            ),
        )
        return self.client.GetBuild(get_build_request, **self._client_kwargs)

    # TODO(crbug/1006818): Need to handle ResponseNotReady given by luci prpc.
    @retry_util.WithRetry(max_retry=5, sleep=20.0, exception=SSLError)
    @retry_util.WithRetry(max_retry=5, sleep=20.0, exception=socket.error)
    @retry_util.WithRetry(
        max_retry=5, sleep=20.0, exception=http.client.ResponseNotReady
    )
    def ScheduleBuild(
        self,
        request_id,
        template_build_id=None,
        builder=None,
        properties=None,
        gerrit_changes=None,
        tags=None,
        dimensions=None,
        fields=None,
        critical=True,
    ):
        """ScheduleBuild call of a specific build with buildbucket_id.

        Args:
            request_id: unique string used to prevent duplicates.
            template_build_id: ID of a build to retry.
            builder: Tuple (builder.project, builder.bucket) defines build ACL
            properties: properties key in parameters_json
            gerrit_changes: Repeated GerritChange message type.
            tags: repeated StringPair of Build.tags to associate with build.
            dimensions: RequestedDimension Swarming dimension to override in
                config.
            fields: fields to include in the response.
            critical: bool for build.critical.

        Returns:
            The corresponding Build proto. See here:
            https://chromium.googlesource.com/infra/luci/luci-go/+/HEAD/buildbucket/proto/build.proto
        """
        schedule_build_request = builds_service_pb2.ScheduleBuildRequest(
            request_id=request_id,
            template_build_id=template_build_id if template_build_id else None,
            builder=builder,
            properties=properties if properties else None,
            gerrit_changes=gerrit_changes if gerrit_changes else None,
            tags=tags if tags else None,
            dimensions=dimensions if dimensions else None,
            fields=field_mask_pb2.FieldMask(paths=[fields]) if fields else None,
            critical=common_pb2.YES if critical else common_pb2.NO,
        )
        return self.client.ScheduleBuild(
            schedule_build_request, **self._client_kwargs
        )

    # TODO(crbug/1006818): Need to handle ResponseNotReady given by luci prpc.
    @retry_util.WithRetry(max_retry=5, sleep=20.0, exception=SSLError)
    @retry_util.WithRetry(max_retry=5, sleep=20.0, exception=socket.error)
    @retry_util.WithRetry(
        max_retry=5, sleep=20.0, exception=http.client.ResponseNotReady
    )
    def UpdateBuild(self, build, update_properties, properties=None):
        """GetBuild call of a specific build with buildbucket_id.

        Args:
            build: Buildbucket build to update.
            update_properties: fields to update.
            properties: fields to include in the response.

        Returns:
            The corresponding Build proto. See here:
            https://chromium.googlesource.com/infra/luci/luci-go/+/HEAD/buildbucket/proto/build.proto
        """
        update_build_request = builds_service_pb2.UpdateBuildRequest(
            build=build,
            update_mask=field_mask_pb2.FieldMask(paths=[update_properties]),
            fields=(
                field_mask_pb2.FieldMask(paths=[properties])
                if properties
                else None
            ),
        )
        return self.client.UpdateBuild(
            update_build_request, **self._client_kwargs
        )

    def GetKilledChildBuilds(self, buildbucket_id):
        """Get IDs of all builds killed by self-destructed orchestrator build.

        Args:
            buildbucket_id: Buildbucket ID of the orchestrator build.

        Returns:
            A list of Buildbucket IDs of the child builds that were killed by
            the orchestrator build or None if the query was unsuccessful.
        """
        properties = "output.properties"
        try:
            build_with_properties = self.GetBuild(
                buildbucket_id, properties=properties
            )
        except ProtocolError:
            logging.error(
                "Could not fetch Buildbucket status for %d", buildbucket_id
            )
            return

        if build_with_properties.output.HasField("properties"):
            build_properties = build_with_properties.output.properties
            if (
                "killed_child_builds" in build_properties
                and build_properties["killed_child_builds"] is not None
            ):
                return ast.literal_eval(build_properties["killed_child_builds"])

    def GetBuildStages(self, buildbucket_id):
        """Get all the Recipe steps/CBuildbot stages of a build.

        Args:
            buildbucket_id: ID of the build in buildbucket.

        Returns:
            A dictionary with keys (id, name, status, last_updated,
            start_time, finish_time).
        """
        properties = "steps"
        build_with_steps = self.GetBuild(buildbucket_id, properties=properties)
        build_status = self.GetBuildStatus(buildbucket_id)
        build_values = {"buildbucket_id": buildbucket_id}
        build_values["build_config"] = build_status["build_config"]
        return [
            BuildStepToDict(step, build_values)
            for step in build_with_steps.steps
        ]

    def GetBuildStatus(self, buildbucket_id):
        """Retrieve the build status for build corresponding to buildbucket_id.

        Args:
            buildbucket_id: Buildbucket ID of the build to be queried for.

        Returns:
            A Dictionary with keys (build_config, start_time, finish_time,
            status, platform_version, full_version, milestone_version, critical,
            buildbucket_id, summary, master_build_id, bot_hostname, deadline,
            build_type, metadata_url, toolchain_url, branch).
        """
        CIDB_TO_BB_PROPERTIES_MAP = {
            # A mapping of CIDB property names to their Buildbucket v2
            # equivalents.
            "bot_id": "bot_hostname",
            "cidb_id": "id",
            "cbb_branch": "branch",
            "cbb_config": "build_config",
            "cbb_master_build_id": "master_build_id",
            "chrome_version": "chrome_version",
            "platform_version": "platform_version",
            "full_version": "full_version",
            "milestone_version": "milestone_version",
            "toolchain_url": "toolchain_url",
            "metadata_url": "metadata_url",
            "critical": "important",
            "build_type": "build_type",
            "summary": "summary",
        }
        try:
            properties = "output.properties"
            build_with_properties = self.GetBuild(buildbucket_id, properties)
            build = self.GetBuild(buildbucket_id)
        except ProtocolError:
            logging.error(
                "Could not fetch Buildbucket status for %d", buildbucket_id
            )
            status_shell = {
                "buildbucket_id": buildbucket_id,
                "start_time": None,
                "finish_time": None,
                "status": None,
                "builder_name": None,
                "build_number": None,
                "buildbot_generation": None,
                "waterfall": None,
                "metadata_url": None,
                "deadline": None,
            }
            for _, status_name in CIDB_TO_BB_PROPERTIES_MAP.items():
                status_shell[status_name] = None
            return status_shell

        build_status = {"buildbucket_id": build.id}
        build_status["start_time"] = utils.TimestampToDatetime(build.start_time)
        build_status["finish_time"] = utils.TimestampToDatetime(build.end_time)
        build_status["status"] = build.status

        if build_with_properties.output.HasField("properties"):
            build_properties = build_with_properties.output.properties
            for property_name, status_name in CIDB_TO_BB_PROPERTIES_MAP.items():
                if (
                    property_name in build_properties
                    and build_properties[property_name] is not None
                ):
                    build_status[status_name] = str(
                        build_properties[property_name]
                    )
                else:
                    build_status[status_name] = None
        else:
            logging.error(
                "Could not fetch Buildbucket properties for %d", buildbucket_id
            )
            build_status.update(
                {
                    "builder_name": None,
                    "build_number": None,
                    "buildbot_generation": None,
                    "waterfall": None,
                    "metadata_url": None,
                    "deadline": None,
                }
            )
            for _, status_name in CIDB_TO_BB_PROPERTIES_MAP.items():
                build_status[status_name] = None
            return build_status

        # Including the now-defunct columns of CIDB Table so as to not break
        # logic.
        # TODO(dhanyaganesh): remove these one at a time.
        build_status["builder_name"] = None
        build_status["build_number"] = None
        build_status["buildbot_generation"] = None
        build_status["waterfall"] = None
        build_status["deadline"] = None
        # Post-processing some properties.
        if (
            build_status["status"] is not None
            and build_status["status"] in BB_STATUS_DICT
        ):
            build_status["status"] = BB_STATUS_DICT[build_status["status"]]
        if build_status["important"] == "True":
            build_status["important"] = 1
        for int_property in ["id", "master_build_id", "important"]:
            if build_status[int_property]:
                try:
                    build_status[int_property] = int(build_status[int_property])
                except ValueError:
                    build_status[int_property] = None
        return build_status

    @retry_util.WithRetry(max_retry=3, sleep=0.2, exception=SSLError)
    @retry_util.WithRetry(max_retry=3, sleep=0.2, exception=socket.error)
    def SearchBuild(self, build_predicate, fields=None, page_size=100):
        """SearchBuild RPC call wrapping function.

        Args:
            build_predicate: Message containing builder, gerrit_changes and/or
            git_commits among other things.
            fields: A FieldMask instance to dictate the format of the response.
            page_size: Number of builds to return.

        Returns:
            A SearchBuildResponse instance corresponding to the query.
        """
        assert isinstance(build_predicate, builds_service_pb2.BuildPredicate)
        if fields is not None:
            assert isinstance(fields, field_mask_pb2.FieldMask)
        assert isinstance(page_size, int)
        if fields is None:
            search_build_request = builds_service_pb2.SearchBuildsRequest(
                predicate=build_predicate, page_size=page_size
            )
        else:
            search_build_request = builds_service_pb2.SearchBuildsRequest(
                predicate=build_predicate, fields=fields, page_size=page_size
            )

        return self.client.SearchBuilds(
            search_build_request, **self._client_kwargs
        )

    def GetBuildHistory(
        self,
        build_config,
        num_results,
        ignore_build_id=None,
        start_date=None,
        end_date=None,
        branch=None,
        start_build_id=None,
    ):
        """Returns basic information about most recent builds for build config.

        By default, this function returns the most recent builds. Some arguments
        can restrict the result to older builds.

        Args:
            build_config: config name of the build to get history.
            num_results: Number of builds to search back. Set this to
                CIDBConnection.NUM_RESULTS_NO_LIMIT to request no limit on the
                number of results.
            ignore_build_id: Ignore a specific build. This is most
                useful to ignore the current build when querying recent past
                builds from a build in flight.
            start_date: Get builds that occurred on or after this date.
            end_date: Get builds that occurred on or before this date.
            branch: Return only results for this branch.
            start_build_id: The oldest build for which data should
                be retrieved.

        Returns:
            A sorted list of dicts containing up to |number| dictionaries for
            build statuses in descending order (if |reverse| is True, ascending
            order).
        """
        builder = builder_common_pb2.BuilderID(
            project="chromeos", bucket="general"
        )
        tags = [common_pb2.StringPair(key="cbb_config", value=build_config)]
        create_time = DateToTimeRange(start_date, end_date)
        if ignore_build_id:
            num_results += 1
        if branch:
            tags.append(common_pb2.StringPair(key="cbb_branch", value=branch))
        build = None
        if start_build_id:
            build = builds_service_pb2.BuildRange(
                start_build_id=int(start_build_id)
            )
        build_predicate = builds_service_pb2.BuildPredicate(
            builder=builder, tags=tags, create_time=create_time, build=build
        )
        search_result = self.SearchBuild(build_predicate, page_size=num_results)
        build_ids = [build.id for build in search_result.builds]
        if ignore_build_id:
            if ignore_build_id in build_ids:
                build_ids = [x for x in build_ids if ignore_build_id != x]
            else:
                # If we do not find ignore_build_id, we ignore the last (i.e.
                # oldest) build in order to return num_results elements.
                build_ids = build_ids[:-1]

        return [self.GetBuildStatus(x) for x in build_ids]

    def GetChildStatuses(self, buildbucket_id):
        """Retrieve statuses of all the child builds.

        Args:
            buildbucket_id: buildbucket_id of the orchestrator build.

        Returns:
            A list of dictionary corresponding to each child build with keys
            like start_time, end_time, status, version info, critical,
            build_config, etc.
        """
        builder = builder_common_pb2.BuilderID(
            project="chromeos", bucket="general"
        )
        tag = common_pb2.StringPair(
            key="cbb_master_buildbucket_id", value=str(buildbucket_id)
        )
        build_predicate = builds_service_pb2.BuildPredicate(
            builder=builder, tags=[tag]
        )
        child_builds = self.SearchBuild(build_predicate, page_size=200)
        return [
            self.GetBuildStatus(child_build.id)
            for child_build in child_builds.builds
        ]

    def GetStageFailures(self, buildbucket_id):
        """Report on the failed stages of a build.

        Args:
            buildbucket_id: buildbucket_id of the build to query for.

        Returns:
            A list of dictionary corresponding to each failed stage with
            following keys - stage_name, stage_status, buildbucket_id,
            build_config, build_status, important.
        """
        build_status = self.GetBuildStatus(buildbucket_id)
        stage_status = self.GetBuildStages(buildbucket_id)

        build_info = {
            "build_status": build_status["status"],
            "build_config": build_status["build_config"],
            "important": build_status["important"],
            "buildbucket_id": buildbucket_id,
        }

        stage_failures = []
        for stage in stage_status:
            if stage["status"] == constants.BUILDER_STATUS_FAILED:
                failed_stage_info = {
                    "stage_status": constants.BUILDER_STATUS_FAILED
                }
                failed_stage_info["stage_name"] = stage["name"]
                failed_stage_info.update(build_info)
                stage_failures.append(failed_stage_info)

        return stage_failures

    @property
    def _client_kwargs(self):
        """Returns kwargs to be added to every rpc in the client.

        The client accepts the following arguments to its requests:
        timeout: int
        metadata: Dict[str, Any]
        credentials: Callable[[luci.prpc.client.Request],
            luci.prpc.client.Request]
        """
        kwargs = {}
        if self._access_token_retriever is not None:
            token = self._access_token_retriever()
            kwargs["metadata"] = dict(Authorization=f"Bearer {token}")
            kwargs["credentials"] = lambda req: req._replace(include_auth=False)
        return kwargs
