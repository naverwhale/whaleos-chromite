# Copyright 2013 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module containing the report stages."""

import datetime
import logging
import os
import sys

from chromite.cbuildbot import cbuildbot_alerts
from chromite.cbuildbot import cbuildbot_run
from chromite.cbuildbot import commands
from chromite.cbuildbot.stages import completion_stages
from chromite.cbuildbot.stages import generic_stages
from chromite.lib import build_target_lib
from chromite.lib import cidb
from chromite.lib import config_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import failures_lib
from chromite.lib import goma_lib
from chromite.lib import metadata_lib
from chromite.lib import metrics
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import results_lib
from chromite.lib import retry_stats
from chromite.lib import toolchain
from chromite.lib import uri_lib
from chromite.utils import gs_urls_util
from chromite.utils import hostname_util
from chromite.utils import key_value_store


def WriteBasicMetadata(builder_run):
    """Writes basic metadata that should be known at start of execution.

    This method writes to |build_run|'s metadata instance the basic metadata
    values that should be known at the beginning of the first cbuildbot
    execution, prior to any reexecutions.

    In particular, this method does not write any metadata values that depend
    on the builder config, as the config may be modified by patches that are
    applied before the final reexectuion. (exception: the config's name itself)

    This method is safe to run more than once (for instance, once per cbuildbot
    execution) because it will write the same data each time.

    Args:
        builder_run: The BuilderRun instance for this build.
    """
    start_time = results_lib.Results.start_time
    start_time_stamp = cros_build_lib.UserDateTimeFormat(timeval=start_time)

    metadata = {
        # Data for this build.
        "bot-hostname": hostname_util.get_host_name(fully_qualified=True),
        "build-number": builder_run.buildnumber,
        "builder-name": builder_run.GetBuilderName(),
        "bot-config": builder_run.config["name"],
        "time": {
            "start": start_time_stamp,
        },
        "master_build_id": builder_run.options.master_build_id,
        "suite_scheduling": builder_run.config["suite_scheduling"],
    }

    builder_run.attrs.metadata.UpdateWithDict(metadata)


def WriteTagMetadata(builder_run):
    """Add a 'tags' sub-dict to metadata.

    This is a proof of concept for using tags to help find commonality
    in failures.
    """
    build_identifier, _ = builder_run.GetCIDBHandle()
    build_id = build_identifier.cidb_id

    # Yes, these values match general metadata values, but they are just
    # proof of concept, so far.
    tags = {
        "bot_config": builder_run.config["name"],
        "bot_hostname": hostname_util.get_host_name(fully_qualified=True),
        "build_id": build_id,
        "build_number": builder_run.buildnumber,
        "builder_name": builder_run.GetBuilderName(),
        "buildbot_master_name": os.environ.get("BUILDBOT_MASTERNAME", ""),
        "id": ("Build", build_id),
        "master_build_id": builder_run.options.master_build_id,
        "important": builder_run.config["important"],
    }

    # Guess type of bot.
    tags["bot_type"] = "unknown"
    if ".golo." in tags["bot_hostname"]:
        tags["bot_type"] = "golo"
    else:
        gce_types = ["beefy", "standard", "wimpy"]
        for t in gce_types:
            host_string = "cros-%s" % t
            if host_string in tags["bot_hostname"]:
                tags["bot_type"] = "gce-%s" % t
                break

    # Look up the git version.
    try:
        cmd_result = cros_build_lib.run(
            ["git", "--version"], capture_output=True, encoding="utf-8"
        )
        tags["git_version"] = cmd_result.stdout.strip()
    except cros_build_lib.RunCommandError:
        pass  # If we fail, just don't include the tag.

    # Look up the repo version.
    try:
        cmd_result = cros_build_lib.run(
            ["repo", "--version"], capture_output=True, encoding="utf-8"
        )

        # Convert the following output into 'v1.12.17-cr3':
        #
        # repo version v1.12.17-cr3
        #        (from https://chromium.googlesource.com/external/repo.git)
        # repo launcher version 1.21
        #        (from /usr/local/google/home/dgarrett/sand/depot_tools/repo)
        # git version 2.8.0.rc3.226.g39d4020
        # Python 2.7.6 (default, Jun 22 2015, 17:58:13)
        # [GCC 4.8.2]
        tags["repo_version"] = cmd_result.stdout.splitlines()[0].split(" ")[-1]
    except (cros_build_lib.RunCommandError, IndexError):
        pass  # If we fail, just don't include the tag.

    builder_run.attrs.metadata.UpdateKeyDictWithDict(
        constants.METADATA_TAGS, tags
    )


def _UploadAndLinkGomaLogIfNecessary(
    stage_name, cbb_config_name, goma_dir, goma_tmp_dir
):
    """Uploads the logs for goma, if needed.

    Also create a link to the visualizer.

    If |goma_tmp_dir| is given, |goma_dir| must not be None.

    Args:
        stage_name: Name of the stage where goma is used.
        cbb_config_name: Name of cbb_config used for the build.
        goma_dir: Path to goma installed directory.
        goma_tmp_dir: Goma's working directory.
    """
    if not goma_tmp_dir:
        return

    goma = goma_lib.Goma(goma_dir, goma_tmp_dir=goma_tmp_dir)
    # Just in case, stop the goma. E.g. In case of timeout, we do not want to
    # keep goma compiler_proxy running.
    goma.Stop()
    goma_urls = goma.UploadLogs(cbb_config_name)
    if goma_urls:
        for label, url in goma_urls:
            cbuildbot_alerts.PrintBuildbotLink(
                "%s %s" % (stage_name, label), url
            )


class BuildStartStage(generic_stages.BuilderStage):
    """The first stage to run.

    This stage writes a few basic metadata values that are known at the start of
    build, and inserts the build into the database, if appropriate.
    """

    category = constants.CI_INFRA_STAGE

    def _GetBuildTimeoutSeconds(self):
        """Get the overall build timeout to be published to cidb.

        Returns:
            Timeout in seconds. None if no sensible timeout can be inferred.
        """
        timeout_seconds = self._run.options.timeout
        if self._run.config.master:
            master_timeout = self._run.config.build_timeout
            if timeout_seconds > 0:
                master_timeout = min(master_timeout, timeout_seconds)
            return master_timeout

        return timeout_seconds if timeout_seconds > 0 else None

    @failures_lib.SetFailureType(failures_lib.InfrastructureFailure)
    def PerformStage(self):
        if self._run.config["doc"]:
            cbuildbot_alerts.PrintBuildbotLink(
                "Builder documentation", self._run.config["doc"]
            )

        WriteBasicMetadata(self._run)

        # This is a heuristic value for |important|, since patches that get
        # applied later in the build might change the config. We write it now
        # anyway, because in case the build fails before Sync, it is better to
        # have this heuristic value than None. In BuildReexecutionFinishedStage,
        # we re-write the definitive value.
        self._run.attrs.metadata.UpdateWithDict(
            {"important": self._run.config["important"]}
        )

        d = self._run.attrs.metadata.GetDict()

        # BuildStartStage should only run once per build. But just in case it
        # is somehow running a second time, we do not want to insert an
        # additional database entry. Detect if a database entry has been
        # inserted already and if so quit the stage.
        if "build_id" in d:
            logging.info(
                "Already have build_id %s, not inserting an entry.",
                d["build_id"],
            )
            return

        buildbucket_id = self._run.options.buildbucket_id
        # Note: In other build stages we use self._run.GetCIDBHandle to fetch
        # a cidb handle. However, since we don't yet have a build_id, we can't
        # do that here.
        if self.buildstore.AreClientsReady():
            db_type = cidb.CIDBConnectionFactory.GetCIDBConnectionType()
            try:
                build_id = self.buildstore.InsertBuild(
                    builder_name=d["builder-name"],
                    build_number=d["build-number"],
                    build_config=d["bot-config"],
                    bot_hostname=d["bot-hostname"],
                    master_build_id=d["master_build_id"],
                    timeout_seconds=self._GetBuildTimeoutSeconds(),
                    important=d["important"],
                    buildbucket_id=buildbucket_id,
                    branch=self._run.manifest_branch,
                )
            except Exception as e:
                logging.error(
                    "Error: %s\n If the buildbucket_id to insert is "
                    "duplicated to the buildbucket_id of an old build and "
                    "the old build was canceled because of a waterfall "
                    "master restart, please ignore this error. Else, "
                    "the error needs more investigation. More context: "
                    "crbug.com/679974 and crbug.com/685889",
                    e,
                )
                raise e

            master_bb_id = self._run.options.master_buildbucket_id
            self._run.attrs.metadata.UpdateWithDict(
                {
                    "build_id": build_id,
                    "buildbucket_id": buildbucket_id,
                    "master_buildbucket_id": master_bb_id,
                    "db_type": db_type,
                }
            )
            logging.info(
                "Inserted build_id %s into cidb database type %s.",
                build_id,
                db_type,
            )
            cbuildbot_alerts.PrintBuildbotStepText(
                "database: %s, build_id: %s" % (db_type, build_id)
            )

            master_build_id = d["master_build_id"]
            if master_build_id is not None:
                master_build_status = self.buildstore.GetBuildStatuses(
                    build_ids=[master_build_id]
                )[0]

                if master_build_status["buildbucket_id"]:
                    master_url = uri_lib.ConstructMiloBuildUri(
                        master_build_status["buildbucket_id"]
                    )
                else:
                    master_url = uri_lib.ConstructDashboardUri(
                        master_build_status["waterfall"],
                        master_build_status["builder_name"],
                        master_build_status["build_number"],
                    )
                cbuildbot_alerts.PrintBuildbotLink(
                    "Link to master build", master_url
                )

        # Set annealing snapshot revision build property for Findit integration.
        if self._run.options.cbb_snapshot_revision:
            cbuildbot_alerts.PrintKitchenSetBuildProperty(
                "GOT_REVISION", self._run.options.cbb_snapshot_revision
            )

        # Write the tag metadata last so that a build_id is available.
        WriteTagMetadata(self._run)

    def HandleSkip(self):
        """Ensure that re-executions use the same db instance as initial db."""
        metadata_dict = self._run.attrs.metadata.GetDict()
        if "build_id" in metadata_dict:
            db_type = cidb.CIDBConnectionFactory.GetCIDBConnectionType()
            if not "db_type" in metadata_dict:
                # This will only execute while this CL is in the commit queue.
                # After this CL lands, this block can be removed.
                self._run.attrs.metadata.UpdateWithDict({"db_type": db_type})
                return

            if db_type != metadata_dict["db_type"]:
                cidb.CIDBConnectionFactory.InvalidateCIDBSetup()
                raise AssertionError(
                    "Invalid attempt to switch from database %s to %s."
                    % (metadata_dict["db_type"], db_type)
                )


class SlaveFailureSummaryStage(generic_stages.BuilderStage):
    """Stage which summarizes and links to the failures of slave builds."""

    category = constants.CI_INFRA_STAGE

    @failures_lib.SetFailureType(failures_lib.InfrastructureFailure)
    def PerformStage(self):
        if not self._run.config.master:
            logging.info(
                "This stage is only meaningful for master builds. "
                "Doing nothing."
            )
            return

        if not self.buildstore.AreClientsReady():
            logging.info(
                "No buildstore connection for this build. Doing nothing."
            )
            return

        child_failures = self.buildstore.GetBuildsFailures(
            self.GetScheduledSlaveBuildbucketIds()
        )
        for failure in child_failures:
            if (
                failure.stage_status != constants.BUILDER_STATUS_FAILED
                or failure.build_status == constants.BUILDER_STATUS_INFLIGHT
            ):
                continue
            slave_stage_url = uri_lib.ConstructMiloBuildUri(
                failure.buildbucket_id
            )
            cbuildbot_alerts.PrintBuildbotLink(
                "%s %s" % (failure.build_config, failure.stage_name),
                slave_stage_url,
            )


class BuildReexecutionFinishedStage(
    generic_stages.BuilderStage, generic_stages.ArchivingStageMixin
):
    """The first stage to run after the final cbuildbot reexecution.

    This stage is the first stage run after the final cbuildbot
    bootstrap/reexecution. By the time this stage is run, the sync stages
    are complete and version numbers of chromeos are known (though chrome
    version may not be known until SyncChrome).

    This stage writes metadata values that are first known after the final
    reexecution (such as those that come from the config). This stage also
    updates the build's cidb entry if appropriate.

    Where possible, metadata that is already known at this time should be
    written at this time rather than in ReportStage.
    """

    category = constants.CI_INFRA_STAGE

    @failures_lib.SetFailureType(failures_lib.InfrastructureFailure)
    def PerformStage(self):
        config = self._run.config
        build_root = self._build_root

        # Workspace builders use a different buildroot for overlays.
        if config.workspace_branch and self._run.options.workspace:
            build_root = self._run.options.workspace

        logging.info(
            "Build re-executions have finished. Chromite source "
            "will not be modified for remainder of run."
        )
        logging.info("config['important']=%s", config["important"])
        cbuildbot_alerts.PrintBuildbotStepText(
            "config['important']=%s" % config["important"]
        )

        sdk_verinfo = key_value_store.LoadFile(
            os.path.join(build_root, constants.SDK_VERSION_FILE),
            ignore_missing=True,
        )

        verinfo = self._run.GetVersionInfo()
        platform_tag = getattr(self._run.attrs, "release_tag")
        if not platform_tag:
            platform_tag = verinfo.VersionString()

        version = {
            "full": self._run.GetVersion(),
            "milestone": verinfo.chrome_branch,
            "platform": platform_tag,
        }

        metadata = {
            # Version of the metadata format.
            "metadata-version": "2",
            "boards": config["boards"],
            "child-configs": [],
            "build_type": config["build_type"],
            "important": config["important"],
            # Data for the toolchain used.
            "sdk-version": sdk_verinfo.get("SDK_LATEST_VERSION", "<unknown>"),
            "toolchain-url": sdk_verinfo.get("TC_PATH", "<unknown>"),
        }

        if len(config["boards"]) == 1:
            metadata["toolchain-tuple"] = toolchain.GetToolchainTupleForBoard(
                config["boards"][0], buildroot=build_root
            )

        logging.info("Metadata being written: %s", metadata)
        self._run.attrs.metadata.UpdateWithDict(metadata)

        toolchains = set()
        toolchain_tuples = []
        primary_toolchains = []
        for board in config["boards"]:
            toolchain_tuple = toolchain.GetToolchainTupleForBoard(
                board, buildroot=build_root
            )
            toolchains |= set(toolchain_tuple)
            toolchain_tuples.append(",".join(toolchain_tuple))
            if toolchain_tuple:
                primary_toolchains.append(toolchain_tuple[0])

        # Update 'version' separately to avoid overwriting the existing
        # entries in it (e.g. PFQ builders may have written the Chrome
        # version to uprev).
        logging.info("Metadata 'version' being written: %s", version)
        self._run.attrs.metadata.UpdateKeyDictWithDict("version", version)

        tags = {
            "boards": config["boards"],
            "child_config_names": [],
            "build_type": config["build_type"],
            "important": config["important"],
            # Data for the toolchain used.
            "sdk_version": sdk_verinfo.get("SDK_LATEST_VERSION", "<unknown>"),
            "toolchain_url": sdk_verinfo.get("TC_PATH", "<unknown>"),
            "toolchains": list(toolchains),
            "toolchain_tuples": toolchain_tuples,
            "primary_toolchains": primary_toolchains,
        }
        full_version = self._run.attrs.metadata.GetValue("version")
        tags.update({"version_%s" % v: full_version[v] for v in full_version})
        self._run.attrs.metadata.UpdateKeyDictWithDict(
            constants.METADATA_TAGS, tags
        )

        # Ensure that all boards and child config boards have a per-board
        # metadata subdict.
        for b in config["boards"]:
            self._run.attrs.metadata.UpdateBoardDictWithDict(b, {})

        # Upload build metadata (and write it to database if necessary)
        self.UploadMetadata(filename=constants.PARTIAL_METADATA_JSON)

        # Write child-per-build and board-per-build rows to database
        build_identifier, db = self._run.GetCIDBHandle()
        build_id = build_identifier.cidb_id
        if db:
            # TODO(akeshet): replace this with a GetValue call once
            # crbug.com/406522 is resolved
            per_board_dict = self._run.attrs.metadata.GetDict()[
                "board-metadata"
            ]
            for board, board_metadata in per_board_dict.items():
                self.buildstore.InsertBoardPerBuild(build_id, board)
                if board_metadata:
                    self.buildstore.InsertBoardPerBuild(
                        build_id, board, board_metadata
                    )


class ConfigDumpStage(generic_stages.BuilderStage):
    """Stage that dumps the current build config to the build log.

    This stage runs immediately after BuildReexecutionFinishedStage, at which
    point the build is finalized.
    """

    category = constants.CI_INFRA_STAGE

    @failures_lib.SetFailureType(failures_lib.InfrastructureFailure)
    def PerformStage(self):
        """Dump the running config to info logs."""
        config = self._run.config
        logging.info(
            "The current build config is dumped below:\n%s",
            config_lib.PrettyJsonDict(config),
        )


class ReportStage(
    generic_stages.BuilderStage, generic_stages.ArchivingStageMixin
):
    """Summarize all the builds."""

    _STATS_HISTORY_DAYS = 7
    category = constants.CI_INFRA_STAGE

    def __init__(self, builder_run, buildstore, completion_instance, **kwargs):
        super().__init__(builder_run, buildstore, **kwargs)

        # TODO(mtennant): All these should be retrieved from builder_run
        # instead. Or, more correctly, the info currently retrieved from these
        # stages should be stored and retrieved from builder_run instead.
        self._completion_instance = completion_instance
        self._post_completion = False

    def _LinkArtifacts(self, builder_run):
        """Upload an HTML index and uploaded.json for artifacts.

        If there are no artifacts in the archive then do nothing.

        Args:
            builder_run: BuilderRun object for this run.
        """
        archive = builder_run.GetArchive()
        archive_path = archive.archive_path

        boards = builder_run.config.boards
        if boards:
            board_names = " ".join(boards)
        else:
            boards = [None]
            board_names = "<no board>"

        # See if there are any artifacts found for this run.
        uploaded = os.path.join(archive_path, commands.UPLOADED_LIST_FILENAME)
        if not os.path.exists(uploaded):
            # UPLOADED doesn't exist.  Normal if Archive stage never ran, which
            # is possibly normal.  Regardless, no archive index is needed.
            logging.info(
                "No archived artifacts found for %s run (%s)",
                builder_run.config.name,
                board_names,
            )
            return

        cbuildbot_alerts.PrintKitchenSetBuildProperty(
            "artifact_link", archive.upload_url
        )

        uploaded_json = "uploaded.json"
        commands.GenerateUploadJSON(
            os.path.join(archive_path, uploaded_json), archive_path, uploaded
        )
        commands.UploadArchivedFile(
            archive_path,
            [archive.upload_url],
            uploaded_json,
            debug=self._run.options.debug_forced,
            update_list=True,
            acl=self.acl,
        )

        if builder_run.config.internal:
            # Internal builds simply link to pantheon directories, which require
            # authenticated access that most Googlers should have.
            artifacts_url = archive.download_url

        else:
            # External builds must allow unauthenticated access to build
            # artifacts. GS doesn't let unauthenticated users browse selected
            # locations without being able to browse everything (which would
            # expose secret stuff). So, we upload an index.html file and link to
            # it instead of the directory.
            title = (
                "Artifacts Index: %(board)s / %(version)s (%(config)s config)"
                % {
                    "board": board_names,
                    "config": builder_run.config.name,
                    "version": builder_run.GetVersion(),
                }
            )

            files = osutils.ReadFile(uploaded).splitlines() + [
                ".|Google Storage Index",
                "..|",
            ]

            index = os.path.join(archive_path, "index.html")

            # TODO (sbasi) crbug.com/362776: Rework the way we do uploading to
            # multiple buckets. Currently this can only be done in the Archive
            # Stage therefore index.html will only end up in the normal Chrome
            # OS bucket.
            commands.GenerateHtmlIndex(
                index,
                files,
                title=title,
                url_base=gs_urls_util.GsUrlToHttp(archive.upload_url),
            )
            commands.UploadArchivedFile(
                archive_path,
                [archive.upload_url],
                os.path.basename(index),
                debug=self._run.options.debug_forced,
                acl=self.acl,
            )

            artifacts_url = os.path.join(
                archive.download_url_file, "index.html"
            )

        links_build_description = "%s/%s" % (
            builder_run.config.name,
            archive.version,
        )
        cbuildbot_alerts.PrintBuildbotLink(
            "Artifacts[%s]" % links_build_description, artifacts_url
        )

    def GetReportMetadata(
        self,
        config=None,
        stage=None,
        final_status=None,
        completion_instance=None,
    ):
        """Generate ReportStage metadata.

        Args:
            config: The build config for this run.  Defaults to
                self._run.config.
            stage: The stage name that this metadata file is being uploaded for.
            final_status: Whether the build passed or failed. If None, the build
                will be treated as still running.
            completion_instance: The stage instance that was used to wait for
                slave completion. Used to add slave build information to master
                builder's metadata. If None, no such status information will be
                included. It not None, this should be a derivative of
                MasterSlaveSyncCompletionStage.

        Returns:
            A JSON-able dictionary representation of the metadata object.
        """
        builder_run = self._run
        config = config or builder_run.config

        get_statuses_from_slaves = (
            config["master"]
            and completion_instance
            and isinstance(
                completion_instance,
                completion_stages.MasterSlaveSyncCompletionStage,
            )
        )

        return metadata_lib.CBuildbotMetadata.GetReportMetadataDict(
            builder_run,
            get_statuses_from_slaves,
            config,
            stage,
            final_status,
            completion_instance,
        )

    def ArchiveResults(self, final_status):
        """Archive our build results.

        Args:
            final_status: constants.BUILDER_STATUS_PASSED or
                constants.BUILDER_STATUS_FAILED
        """
        # Make sure local archive directory is prepared, if it was not already.
        if not os.path.exists(self.archive_path):
            self.archive.SetupArchivePath()

        # Upload metadata, and update the pass/fail streak counter for the main
        # run only. These aren't needed for the child builder runs.
        self.UploadMetadata()

        build_identifier, _ = self._run.GetCIDBHandle()
        build_id = build_identifier.cidb_id
        # Iterate through each builder run.
        for builder_run in [self._run]:
            if build_id is not None:
                details_link = uri_lib.ConstructViceroyBuildDetailsUri(build_id)
                cbuildbot_alerts.PrintBuildbotLink(
                    "Build details", details_link
                )

            # Generate links to archived artifacts if there are any.  All the
            # archived artifacts for one run/config are in one location, so the
            # link is only specific to each run/config.  In theory multiple
            # boards could share that archive, but in practice it is usually one
            # board.  A run/config without a board will also usually not have
            # artifacts to archive, but that restriction is not assumed here.
            self._LinkArtifacts(builder_run)

            # Check if the builder_run is tied to any boards and if so get all
            # upload urls.
            if final_status == constants.BUILDER_STATUS_PASSED:
                # Update the LATEST files if the build passed.
                try:
                    upload_urls = self._GetUploadUrls(
                        "LATEST-*", builder_run=builder_run
                    )
                except portage_util.MissingOverlayError as e:
                    # If the build failed prematurely, some overlays might be
                    # missing. Ignore them in this stage.
                    logging.warning(e)
                else:
                    if upload_urls:
                        archive = builder_run.GetArchive()
                        archive.UpdateLatestMarkers(
                            builder_run.manifest_branch,
                            builder_run.options.debug_forced,
                            upload_urls=upload_urls,
                        )

    def PerformStage(self):
        """Perform the actual work for this stage.

        This includes final metadata archival, and update CIDB with our final
        status as well as producing a logged build result summary.
        """
        build_identifier, _ = self._run.GetCIDBHandle()
        build_id = build_identifier.cidb_id
        buildbucket_id = build_identifier.buildbucket_id
        if results_lib.Results.BuildSucceededSoFar(
            self.buildstore, buildbucket_id, self.name
        ):
            final_status = constants.BUILDER_STATUS_PASSED
        else:
            final_status = constants.BUILDER_STATUS_FAILED

        if not hasattr(self._run.attrs, "release_tag"):
            # If, for some reason, sync stage was not completed and
            # release_tag was not set. Set it to None here because
            # ArchiveResults() depends the existence of this attr.
            self._run.attrs.release_tag = None

        # Set up our report metadata.
        self._run.attrs.metadata.UpdateWithDict(
            self.GetReportMetadata(
                final_status=final_status,
                completion_instance=self._completion_instance,
            )
        )

        src_root = self._build_root
        # Workspace builders use a different buildroot for overlays.
        if self._run.config.workspace_branch and self._run.options.workspace:
            src_root = self._run.options.workspace

        # Add tags for the arches and statuses of the build.
        # arches requires crossdev which isn't available at the early part of
        # the build.
        arches = []
        for board in self._run.config["boards"]:
            build_target = build_target_lib.BuildTarget(board)
            toolchains = toolchain.get_toolchains_for_build_target(
                build_target, source_root=src_root
            )
            default = list(
                toolchain.FilterToolchains(toolchains, "default", True)
            )
            if default:
                try:
                    arches.append(toolchain.GetArchForTarget(default[0]))
                except cros_build_lib.RunCommandError as e:
                    logging.warning(
                        "Unable to retrieve arch for board %s default toolchain"
                        " %s: %s",
                        board,
                        default,
                        e,
                    )
        tags = {
            "arches": arches,
            "status": final_status,
        }
        results = self._run.attrs.metadata.GetValue("results")
        for stage in results:
            tags["stage_status:%s" % stage["name"]] = stage["status"]
            tags["stage_summary:%s" % stage["name"]] = stage["summary"]
        self._run.attrs.metadata.UpdateKeyDictWithDict(
            constants.METADATA_TAGS, tags
        )

        # Some operations can only be performed if a valid version is available.
        try:
            self._run.GetVersionInfo()
            self.ArchiveResults(final_status)
            metadata_url = os.path.join(
                self.upload_url, constants.METADATA_JSON
            )
        except cbuildbot_run.VersionNotSetError:
            logging.error(
                "A valid version was never set for this run. "
                "Can not archive results."
            )
            metadata_url = ""

        results_lib.Results.Report(
            sys.stdout, current_version=(self._run.attrs.release_tag or "")
        )

        # Upload goma log if used for BuildPackage and TestSimpleChrome.
        _UploadAndLinkGomaLogIfNecessary(
            "BuildPackages",
            self._run.config.name,
            self._run.options.goma_dir,
            self._run.attrs.metadata.GetValueWithDefault("goma_tmp_dir"),
        )
        _UploadAndLinkGomaLogIfNecessary(
            "TestSimpleChromeWorkflow",
            self._run.config.name,
            self._run.options.goma_dir,
            self._run.attrs.metadata.GetValueWithDefault(
                "goma_tmp_dir_for_simple_chrome"
            ),
        )

        if self.buildstore.AreClientsReady():
            status_for_db = final_status

            # TODO(pprabhu): After BuildData and CBuildbotMetadata are merged,
            # remove this extra temporary object creation.
            # XXX:HACK We're creating a BuildData with an empty URL. Don't try
            # to MarkGathered this object.
            build_data = metadata_lib.BuildData(
                "", self._run.attrs.metadata.GetDict()
            )
            # TODO(akeshet): Find a clearer way to get the "primary upload url"
            # for the metadata.json file. One alternative is
            # _GetUploadUrls(...)[0]. Today it seems that element 0 of its
            # return list is the primary upload url, but there is no guarantee
            # or unit test coverage of that.
            self.buildstore.FinishBuild(
                build_id,
                status=status_for_db,
                summary=build_data.failure_message,
                metadata_url=metadata_url,
            )

            duration = self._GetBuildDuration()

            mon_fields = {
                "status": status_for_db,
                "build_config": self._run.config.name,
                "important": self._run.config.important,
            }
            metrics.Counter(constants.MON_BUILD_COMP_COUNT).increment(
                fields=mon_fields
            )
            metrics.CumulativeSecondsDistribution(
                constants.MON_BUILD_DURATION
            ).add(duration, fields=mon_fields)

            # From this point forward, treat all exceptions as warnings.
            self._post_completion = True

            # Dump report about things we retry.
            retry_stats.ReportStats(sys.stdout)

    def _GetBuildDuration(self):
        """Fetches the duration of this build in seconds, from cidb.

        This method should be called only after the build has been Finished in
        cidb.
        """
        build_identifier, _ = self._run.GetCIDBHandle()
        if self.buildstore.AreClientsReady():
            buildbucket_id = build_identifier.buildbucket_id
            build_info = self.buildstore.GetBuildStatuses(
                buildbucket_ids=[buildbucket_id]
            )[0]
            # If we query from Buildbucket, the build isn't finished yet.
            # So, finish_time is None. Use current time instead.
            if build_info["finish_time"] is None:
                build_info["finish_time"] = datetime.datetime.now()
            duration = (
                build_info["finish_time"] - build_info["start_time"]
            ).total_seconds()
            return duration
        return 0

    def _HandleStageException(self, exc_info):
        """Override and don't set status to FAIL but FORGIVEN instead."""
        if self._post_completion:
            # If we've already reported the stage completion, treat exceptions
            # as warnings so we keep reported success in-line with waterfall
            # displayed results.
            return self._HandleExceptionAsWarning(exc_info)

        return super()._HandleStageException(exc_info)
