# Copyright 2016 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for tracking and querying build status."""

import collections
import datetime
import logging

from chromite.lib import buildbucket_v2
from chromite.lib import builder_status_lib
from chromite.lib import constants
from chromite.lib import metrics


BUILD_START_TIMEOUT_MIN = 60


# TODO(nxia): Rename this module to slave_status, since this module is for
# a master build which has slave builds and there is builder_status_lib for
# managing the status of an indivudual build.
class SlaveStatus:
    """Keep track of statuses of all slaves from CIDB and Buildbucket(optional).

    For the master build scheduling slave builds through Buildbucket, it will
    interpret slave statuses by querying CIDB and Buildbucket; otherwise,
    it will only interpret slave statuses by querying CIDB.
    """

    ACCEPTED_STATUSES = (
        constants.BUILDER_STATUS_PASSED,
        constants.BUILDER_STATUS_SKIPPED,
    )

    def __init__(
        self,
        start_time,
        builders_array,
        master_build_identifier,
        buildstore,
        config=None,
        metadata=None,
        buildbucket_client=None,
        version=None,
        dry_run=True,
    ):
        """Initializes a SlaveStatus instance.

        Args:
            start_time: datetime.datetime object of when the build started.
            builders_array: List of the expected slave builds.
            master_build_identifier: The BuildIdentifier instance of the master
                build.
            buildstore: BuildStore instance to make DB calls.
            config: Instance of config_lib.BuildConfig. Config dict of this
                build.
            metadata: Instance of metadata_lib.CBuildbotMetadata. Metadata of
                this build.
            buildbucket_client: Instance of buildbucket_v2.BuildbucketV2 client.
            version: Current manifest version string. See the return type of
                VersionInfo.VersionString().
            dry_run: Boolean indicating whether it's a dry run. Default to True.
        """
        self.start_time = start_time
        self.all_builders = builders_array
        self.master_build_identifier = master_build_identifier
        self.master_build_id = master_build_identifier.cidb_id
        self.buildstore = buildstore
        self.config = config
        self.metadata = metadata
        self.buildbucket_client = buildbucket_client
        self.version = version
        self.dry_run = dry_run

        # A set of completed builds which will not be retried any more.
        self.completed_builds = set()
        # Dict mapping config names of slaves not in self.completed_builds to
        # their new CIDBStatusInfo. Everytime UpdateSlaveStatus is called,
        # new (current) status will be pulled from CIDB.
        self.new_cidb_status_dict = None
        # Dict mapping all slave config names to CIDBStatusInfo.
        self.all_cidb_status_dict = None
        self.missing_builds = None
        self.scheduled_builds = None
        # Dict mapping config names of slaves not in self.completed_builds to
        # their new BuildbucketInfo. Everytime UpdateSlaveStatus is called,
        # new (current) status will be pulled from Buildbucket.
        # TODO(jkop): The code uses 'is not None' checks to determine if it's
        # using Buildbucket. Initialize this to a dict for simplicity when
        # that's been refactored.
        self.new_buildbucket_info_dict = None
        # Dict mapping all slave config names to BuildbucketInfo
        self.all_buildbucket_info_dict = {}
        self.status_buildset_dict = {}

        # Records history (per-tick) of self.completed_builds. Keep only the
        # most recent 2 entries of history. Used only for metrics purposes, not
        # used for any decision logic.
        self._completed_build_history = collections.deque([], 2)

        self.UpdateSlaveStatus()

    def _GetNewSlaveCIDBStatusInfo(
        self, all_cidb_status_dict, completed_builds
    ):
        """Get new build status information for slaves not in completed_builds.

        Args:
            all_cidb_status_dict: A dict mapping all build config names to their
                information fetched from CIDB (in the format of CIDBStatusInfo).
            completed_builds: A set of slave build configs (strings) completed
                before.

        Returns:
            A dict mapping the build config names of slave builds which are not
            in the completed_builds to their CIDBStatusInfos.
        """
        return {
            build_config: status_info
            for build_config, status_info in all_cidb_status_dict.items()
            if build_config not in completed_builds
        }

    def _GetNewSlaveBuildbucketInfo(
        self, all_buildbucket_info_dict, completed_builds
    ):
        """Get new buildbucket info for slave builds not in completed_builds.

        Args:
            all_buildbucket_info_dict: A dict mapping all slave build config
                names to their BuildbucketInfos.
            completed_builds: A set of slave build configs (strings) completed
                before.

        Returns:
            A dict mapping config names of slave builds which are not in the
            completed_builds set to their BuildbucketInfos.
        """
        completed_builds = completed_builds or {}
        return {
            k: v
            for k, v in all_buildbucket_info_dict.items()
            if k not in completed_builds
        }

    def _SetStatusBuildsDict(self):
        """Set status_buildset_dict by sorting builds into their status set."""
        self.status_buildset_dict = {}
        for build, info in self.new_buildbucket_info_dict.items():
            if info.status is not None:
                self.status_buildset_dict.setdefault(info.status, set())
                self.status_buildset_dict[info.status].add(build)

    def UpdateSlaveStatus(self):
        # pylint: disable-next=line-too-long
        """Update slave statuses by querying CIDB and Buildbucket(if supported)."""
        logging.info("Updating slave status...")

        if self.config and self.metadata:
            scheduled_buildbucket_info_dict = buildbucket_v2.GetBuildInfoDict(
                self.metadata
            )
            # It's possible that CQ-master has a list of important slaves
            # configured but doesn't schedule any slaves as no CLs were picked
            # up in SyncStage. These are set to include only important builds.
            self.all_builders = list(scheduled_buildbucket_info_dict)
            # pylint: disable-next=line-too-long
            self.all_buildbucket_info_dict = builder_status_lib.SlaveBuilderStatus.GetAllSlaveBuildbucketInfo(
                self.buildbucket_client, scheduled_buildbucket_info_dict
            )
            self.new_buildbucket_info_dict = self._GetNewSlaveBuildbucketInfo(
                self.all_buildbucket_info_dict, self.completed_builds
            )
            self._SetStatusBuildsDict()

        self.all_cidb_status_dict = (
            builder_status_lib.SlaveBuilderStatus.GetAllSlaveCIDBStatusInfo(
                self.buildstore,
                self.master_build_identifier,
                self.all_buildbucket_info_dict,
            )
        )
        self.new_cidb_status_dict = self._GetNewSlaveCIDBStatusInfo(
            self.all_cidb_status_dict, self.completed_builds
        )

        self.missing_builds = self._GetMissingBuilds()
        self.scheduled_builds = self._GetScheduledBuilds()
        self.completed_builds = self._GetCompletedBuilds()

    def GetBuildbucketBuilds(self, build_status):
        """Get the buildbucket builds which are in the build_status status.

        Args:
            build_status: The status of the builds to get. The status must be a
                member of constants.BUILDBUCKET_BUILDER_STATUSES.

        Returns:
            A set of builds in build_status status.
        """
        if build_status not in constants.BUILDBUCKET_BUILDER_STATUSES:
            raise ValueError(
                "%s is not a member of %s "
                % (build_status, constants.BUILDBUCKET_BUILDER_STATUSES)
            )

        return self.status_buildset_dict.get(build_status, set())

    def _GetExpectedBuilders(self):
        """Returns the list of expected slave build configs.

        Returns:
            A list of build slave config names.
        """
        experimental_builders = []
        if self.metadata:
            experimental_builders = self.metadata.GetValueWithDefault(
                constants.METADATA_EXPERIMENTAL_BUILDERS, []
            )
        return [
            builder
            for builder in self.all_builders
            if builder not in experimental_builders
        ]

    def _GetMissingBuilds(self):
        """Returns the missing builds.

        For builds scheduled by Buildbucket, missing refers to builds without
        'status' from Buildbucket.
        For builds not scheduled by Buildbucket, missing refers builds without
        reporting status to CIDB.

        Returns:
            A set of the config names of missing builds.
        """
        if self.new_buildbucket_info_dict is not None:
            return set(
                build
                for build, info in self.new_buildbucket_info_dict.items()
                if info.status is None
            )
        else:
            return (
                set(self._GetExpectedBuilders())
                - set(self.new_cidb_status_dict)
                - self.completed_builds
            )

    def _GetScheduledBuilds(self):
        """Returns the scheduled builds.

        Returns:
            For builds scheduled by Buildbucket, a set of config names of builds
            with 'SCHEDULED' status in Buildbucket;
            For other builds, None.
        """
        if self.new_buildbucket_info_dict is not None:
            return self.GetBuildbucketBuilds(
                constants.BUILDBUCKET_BUILDER_STATUS_SCHEDULED
            )
        else:
            return None

    def _GetCompletedBuilds(self):
        """Returns the builds that have completed and will not be retried.

        Returns:
            A set of config names of completed and not retriable builds.
        """
        # current completed builds (not in self.completed_builds) from CIDB
        current_completed = set(
            b
            for b, s in self.new_cidb_status_dict.items()
            if s.status in constants.BUILDER_COMPLETED_STATUSES
            and b in self._GetExpectedBuilders()
        )

        if self.new_buildbucket_info_dict is not None:
            # current completed builds (not in self.completed_builds) from
            # Buildbucket
            current_completed_buildbucket = self.GetBuildbucketBuilds(
                constants.BUILDBUCKET_BUILDER_STATUS_SUCCESS
            )
            current_completed = (
                current_completed | current_completed_buildbucket
            )

        for build in current_completed:
            cidb_status = (
                self.new_cidb_status_dict[build].status
                if build in self.new_cidb_status_dict
                else None
            )
            status_output = "Build config %s completed: CIDB status: %s." % (
                build,
                cidb_status,
            )
            if self.new_buildbucket_info_dict is not None:
                status_output += " Buildbucket status %s." % (
                    self.new_buildbucket_info_dict[build].status
                )
            logging.info(status_output)

        completed_builds = self.completed_builds | current_completed

        return completed_builds

    def _Completed(self):
        """Returns a bool if all builds have completed successfully.

        Returns:
            A bool of True if all builds successfully completed, False
            otherwise.
        """
        return len(self.completed_builds) == len(self._GetExpectedBuilders())

    def _GetUncompletedBuilds(self, completed_builds):
        """Get uncompleted important builds.

        Args:
            completed_builds: a set of config names (strings) of completed
                builds.

        Returns:
            A set of config names (strings) of uncompleted important builds.
        """
        return set(self._GetExpectedBuilders()) - completed_builds

    def _GetUncompletedExperimentalBuildbucketIDs(self):
        """Get buildbucket_ids for uncompleted experimental builds.

        Returns:
            A set of Buildbucket IDs (strings) of uncompleted experimental
            builds.
        """
        flagged_experimental_builders = self.metadata.GetValueWithDefault(
            constants.METADATA_EXPERIMENTAL_BUILDERS, []
        )
        experimental_slaves = self.metadata.GetValueWithDefault(
            constants.METADATA_SCHEDULED_EXPERIMENTAL_SLAVES, []
        )
        important_slaves = self.metadata.GetValueWithDefault(
            constants.METADATA_SCHEDULED_IMPORTANT_SLAVES, []
        )
        experimental_slaves += [
            (name, bb_id, time)
            for (name, bb_id, time) in important_slaves
            if name in flagged_experimental_builders
        ]

        all_experimental_bb_info_dict = (
            builder_status_lib.SlaveBuilderStatus.GetAllSlaveBuildbucketInfo(
                self.buildbucket_client,
                buildbucket_v2.GetScheduledBuildDict(experimental_slaves),
            )
        )
        all_experimental_cidb_status_dict = (
            builder_status_lib.SlaveBuilderStatus.GetAllSlaveCIDBStatusInfo(
                self.buildstore,
                self.master_build_identifier,
                all_experimental_bb_info_dict,
            )
        )

        completed_experimental_builds = set(
            name
            for name, info in all_experimental_bb_info_dict.items()
            if info.status == constants.BUILDBUCKET_BUILDER_STATUS_SUCCESS
        )
        completed_experimental_builds |= set(
            name
            for name, info in all_experimental_cidb_status_dict.items()
            if info.status in constants.BUILDER_COMPLETED_STATUSES
        )

        return {
            bb_id
            for (name, bb_id, time) in experimental_slaves
            if name not in completed_experimental_builds
        }

    def _ShouldFailForBuilderStartTimeout(self, current_time):
        """Decides if we should fail if a build hasn't started within 5 mins.

        If a build hasn't started within BUILD_START_TIMEOUT_MIN and the rest of
        the builds have finished, let the caller know that we should fail.

        Args:
            current_time: A datetime.datetime object letting us know the current
                time.

        Returns:
            A bool saying True that we should fail, False otherwise.
        """
        # Check that we're at least past the start timeout.
        builder_start_deadline = datetime.timedelta(
            minutes=BUILD_START_TIMEOUT_MIN
        )
        past_deadline = current_time - self.start_time > builder_start_deadline

        # Check that we have missing builders and logging who they are.
        for builder in self.missing_builds:
            logging.error("No status found for build config %s.", builder)

        if self.new_buildbucket_info_dict is not None:
            # All scheduled builds added in new_buildbucket_info_dict are
            # either in completed status or still in scheduled status.
            other_builders_completed = len(self.scheduled_builds) + len(
                self.completed_builds
            ) == len(self._GetExpectedBuilders())

            for builder in self.scheduled_builds:
                logging.error("Builder not started %s.", builder)

            return (
                past_deadline
                and other_builders_completed
                and self.scheduled_builds
            )
        else:
            # Check that aside from the missing builders the rest have
            # completed.
            other_builders_completed = len(self.missing_builds) + len(
                self.completed_builds
            ) == len(self._GetExpectedBuilders())

            return (
                past_deadline
                and other_builders_completed
                and self.missing_builds
            )

    @staticmethod
    def _LastSlavesToComplete(completed_builds_history):
        """Given a |completed_builds_history|, find the last to complete.

        Returns:
            A set of build_configs that were the last to complete.
        """
        if not completed_builds_history:
            return set()
        elif len(completed_builds_history) == 1:
            return set(completed_builds_history[0])
        else:
            return set(completed_builds_history[-1]) - set(
                completed_builds_history[-2]
            )

    def ShouldWait(self):
        """Decides if we should continue to wait for the builds to finish.

        This will be the retry function for timeout_util.WaitForSuccess,
        basically this function will return False if all builds finished or we
        see a problem with the builds. Otherwise it returns True to continue
        polling for the builds statuses.

        Returns:
            A bool of True if we should continue to wait and False if we should
            not.
        """
        retval, slaves_remain, long_pole = self._ShouldWait()

        # If we're no longer waiting, record last-slave-to-complete metrics.
        if not retval and long_pole:
            m = metrics.CumulativeMetric(constants.MON_LAST_SLAVE)
            slaves = self._LastSlavesToComplete(self._completed_build_history)
            if slaves and self.config:
                increment = 1.0 / len(slaves)
                for s in slaves:
                    m.increment_by(
                        increment,
                        fields={
                            "master_config": self.config.name,
                            "last_slave_config": s,
                            "slaves_remain": slaves_remain,
                        },
                    )

        return retval

    def _ShouldWait(self):
        """Private helper with all the main logic of ShouldWait.

        Returns:
            A tuple of (bool indicating if we should wait,
                        bool indicating if slaves remain,
                        bool indicating if the final slave(s) to complete should
                        be considered the long-pole reason for terminating)
        """
        self._completed_build_history.append(list(self.completed_builds))

        uncompleted_experimental_build_buildbucket_ids = (
            self._GetUncompletedExperimentalBuildbucketIDs()
        )

        # Check if all builders completed.
        if self._Completed():
            buildbucket_client = buildbucket_v2.BuildbucketV2()
            summary_markdown = (
                "Experimental build, cancelled as all others " + "completed."
            )
            logging.info(summary_markdown)
            buildbucket_client.BatchCancelBuilds(
                list(uncompleted_experimental_build_buildbucket_ids),
                summary_markdown,
            )
            return False, False, True

        current_time = datetime.datetime.now()

        uncompleted_important_builds = self._GetUncompletedBuilds(
            self.completed_builds
        )
        uncompleted_important_build_buildbucket_ids = set(
            v.buildbucket_id
            for k, v in self.all_buildbucket_info_dict.items()
            if k in uncompleted_important_builds
        )
        uncompleted_build_buildbucket_ids = list(
            uncompleted_important_build_buildbucket_ids
            | uncompleted_experimental_build_buildbucket_ids
        )

        if self._ShouldFailForBuilderStartTimeout(current_time):
            summary_markdown = (
                "Ending build since at least one builder has "
                + "not started within %d minutes." % BUILD_START_TIMEOUT_MIN
            )
            logging.error(summary_markdown)
            buildbucket_client = buildbucket_v2.BuildbucketV2()
            buildbucket_client.BatchCancelBuilds(
                uncompleted_build_buildbucket_ids,
                summary_markdown,
            )
            return False, False, False

        # We got here which means no problems, we should still wait.
        logging.info(
            "Still waiting for the following builds to complete: %r",
            sorted(set(self._GetExpectedBuilders()) - self.completed_builds),
        )

        return True, True, False
