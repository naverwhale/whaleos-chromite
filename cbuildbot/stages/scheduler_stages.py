# Copyright 2016 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module containing the scheduler stages."""

import logging
import time

from chromite.cbuildbot import cbuildbot_alerts
from chromite.cbuildbot.stages import generic_stages
from chromite.lib import build_requests
from chromite.lib import buildbucket_v2
from chromite.lib import constants
from chromite.lib import failures_lib
from chromite.lib import request_build


class ScheduleSlavesStage(generic_stages.BuilderStage):
    """Stage that schedules slaves for the master build."""

    category = constants.CI_INFRA_STAGE

    def __init__(self, builder_run, buildstore, sync_stage, **kwargs):
        super().__init__(builder_run, buildstore, **kwargs)
        self.sync_stage = sync_stage
        self.buildbucket_client = buildbucket_v2.BuildbucketV2()

    def _CreateScheduledBuild(
        self,
        build_name,
        build_config,
        master_build_id,
        master_buildbucket_id,
        requested_bot=None,
    ):
        cbb_extra_args = ["--buildbot"]
        if master_buildbucket_id is not None:
            cbb_extra_args.append("--master-buildbucket-id")
            cbb_extra_args.append(master_buildbucket_id)
        # Adding cbb_snapshot_revision to child builders to force child builders
        # to sync to annealing snapshot revision.
        if self._run.options.cbb_snapshot_revision:
            logging.info(
                "Adding --cbb_snapshot_revision=%s for %s",
                self._run.options.cbb_snapshot_revision,
                build_config.name,
            )
            cbb_extra_args.append("--cbb_snapshot_revision")
            cbb_extra_args.append(self._run.options.cbb_snapshot_revision)

        # Add the version string to bb_extra_properties so it can be read for
        # running builds.
        extra_properties = {}
        extra_properties["full_version"] = self._run.GetVersion()

        return request_build.RequestBuild(
            build_config=build_name,
            display_label=build_config.display_label,
            branch=self._run.manifest_branch,
            master_cidb_id=master_build_id,
            master_buildbucket_id=master_buildbucket_id,
            extra_args=cbb_extra_args,
            extra_properties=extra_properties,
            requested_bot=requested_bot,
        )

    def PostSlaveBuildToBuildbucket(
        self,
        build_name,
        build_config,
        master_build_id,
        master_buildbucket_id,
        dryrun=False,
    ):
        """Scehdule a build within Buildbucket.

        Args:
            build_name: Slave build name to schedule.
            build_config: Slave build config.
            master_build_id: CIDB id of the master scheduling the slave build.
            master_buildbucket_id: buildbucket id of the master scheduling the
                slave build.
            dryrun: Whether a dryrun, default to False.

        Returns:
            Tuple:
            buildbucket_id
            created_ts
        """
        request = self._CreateScheduledBuild(
            build_name, build_config, master_build_id, master_buildbucket_id
        ).CreateBuildRequest()

        if dryrun:
            return (str(master_build_id), "1")

        result = self.buildbucket_client.ScheduleBuild(
            request_id=str(request["request_id"]),
            builder=request["builder"],
            properties=request["properties"],
            tags=request["tags"],
            dimensions=request["dimensions"],
        )

        logging.info(
            "Build_name %s buildbucket_id %s created_timestamp %s",
            build_name,
            result.id,
            result.create_time.ToJsonString(),
        )
        cbuildbot_alerts.PrintBuildbotLink(
            build_name, f"{constants.CHROMEOS_MILO_HOST}{result.id}"
        )

        return (result.id, result.create_time.ToJsonString())

    def ScheduleSlaveBuildsViaBuildbucket(
        self, important_only=False, dryrun=False
    ):
        """Schedule slave builds by sending PUT requests to Buildbucket.

        Args:
            important_only: Whether only schedule important slave builds,
                default to False.
            dryrun: Whether a dryrun, default to False.
        """
        if self.buildbucket_client is None:
            logging.info("No buildbucket_client. Skip scheduling slaves.")
            return

        build_identifier, _ = self._run.GetCIDBHandle()
        build_id = build_identifier.cidb_id
        if build_id is None:
            logging.info("No build id. Skip scheduling slaves.")
            return

        # May be None. This is okay.
        master_buildbucket_id = self._run.options.buildbucket_id

        if self._run.options.cbb_snapshot_revision:
            logging.info(
                "Parent has cbb_snapshot_rev=%s",
                self._run.options.cbb_snapshot_revision,
            )

        scheduled_important_slave_builds = []
        scheduled_experimental_slave_builds = []
        unscheduled_slave_builds = []
        scheduled_build_reqs = []

        # Get all active slave build configs.
        slave_config_map = self._GetSlaveConfigMap(important_only)
        for slave_config_name, slave_config in sorted(slave_config_map.items()):
            if slave_config_name.endswith("-release"):
                logging.info(
                    "Child %s not in LEGACY_RELEASE_ALLOWLIST (b/238925754),"
                    " skipping...",
                    slave_config_name,
                )
                continue
            try:
                if dryrun:
                    buildbucket_id = "1"
                    created_ts = "1"
                else:
                    (
                        buildbucket_id,
                        created_ts,
                    ) = self.PostSlaveBuildToBuildbucket(
                        slave_config_name,
                        slave_config,
                        build_id,
                        master_buildbucket_id,
                        dryrun=dryrun,
                    )
                request_reason = None

                if slave_config.important:
                    scheduled_important_slave_builds.append(
                        (slave_config_name, buildbucket_id, created_ts)
                    )
                    request_reason = build_requests.REASON_IMPORTANT_CQ_SLAVE
                else:
                    scheduled_experimental_slave_builds.append(
                        (slave_config_name, buildbucket_id, created_ts)
                    )
                    request_reason = build_requests.REASON_EXPERIMENTAL_CQ_SLAVE

                scheduled_build_reqs.append(
                    build_requests.BuildRequest(
                        None,
                        build_id,
                        slave_config_name,
                        None,
                        buildbucket_id,
                        request_reason,
                        None,
                    )
                )
            except buildbucket_v2.BuildbucketResponseException as e:
                # Use 16-digit ts to be consistent with the created_ts from
                # Buildbucket
                current_ts = int(round(time.time() * 1000000))
                unscheduled_slave_builds.append(
                    (slave_config_name, None, current_ts)
                )
                if important_only or slave_config.important:
                    raise
                else:
                    logging.warning(
                        "Failed to schedule %s current timestamp %s: %s",
                        slave_config_name,
                        current_ts,
                        e,
                    )

        self._run.attrs.metadata.ExtendKeyListWithList(
            constants.METADATA_SCHEDULED_IMPORTANT_SLAVES,
            scheduled_important_slave_builds,
        )
        self._run.attrs.metadata.ExtendKeyListWithList(
            constants.METADATA_SCHEDULED_EXPERIMENTAL_SLAVES,
            scheduled_experimental_slave_builds,
        )
        self._run.attrs.metadata.ExtendKeyListWithList(
            constants.METADATA_UNSCHEDULED_SLAVES, unscheduled_slave_builds
        )

    @failures_lib.SetFailureType(failures_lib.InfrastructureFailure)
    def PerformStage(self):
        self.ScheduleSlaveBuildsViaBuildbucket(
            important_only=False, dryrun=self._run.options.debug
        )
