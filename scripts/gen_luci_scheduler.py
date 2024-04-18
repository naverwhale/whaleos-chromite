# Copyright 2018 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=line-too-long

"""Generate LUCI Scheduler config file.

This generates the LUCI Scheduler configuration file for ChromeOS builds based
on the chromeos_config contents.

Changes to chromite/config/luci-scheduler.cfg will be autodeployed:
  https://data.corp.google.com/sites/chromeos_ci_cros_ci_builds/utility/?f=board_name:in:luci-scheduler-updater

Notes:
  Normal builds are scheduled based on the builder values for
  'schedule' and 'triggered_gitiles' in config/chromeos_config.py.
"""

# pylint: enable=line-too-long

import sys

from chromite.lib import commandline
from chromite.lib import config_lib


_CONFIG_HEADER = """# Defines buckets on luci-scheduler.appspot.com.
#
# For schema of this file and documentation see ProjectConfig message in
# https://github.com/luci/luci-go/blob/HEAD/scheduler/appengine/messages/config.proto

# Generated with chromite/scripts/gen_luci_scheduler

# Autodeployed with:
# https://data.corp.google.com/sites/chromeos_ci_cros_ci_builds/utility/?f=board_name:in:luci-scheduler-updater

acl_sets {
  name: "default"
  acls {
    role: READER
    granted_to: "group:googlers"
  }
  acls {
    role: OWNER
    granted_to: "group:project-chromeos-admins"
  }
  acls {
    role: TRIGGERER
    granted_to: "group:mdb/chromeos-build-access"
  }
  acls {
    role: TRIGGERER
    granted_to: "group:project-chromeos-buildbucket-schedulers"
  }
}
"""


def buildJobName(build_config):
    if "schedule_branch" in build_config:
        return "%s-%s" % (build_config.schedule_branch, build_config.name)
    else:
        return build_config.name


def genSchedulerJob(build_config):
    """Generate the luci scheduler job for a given build config.

    Args:
        build_config: config_lib.BuildConfig.

    Returns:
        Multiline string to include in the luci scheduler configuration.
    """
    job_name = buildJobName(build_config)
    if "schedule_branch" in build_config:
        branch = build_config.schedule_branch
    else:
        branch = "main"

    tags = {
        "cbb_branch": branch,
        "cbb_config": build_config.name,
        "cbb_display_label": build_config.display_label,
        "cbb_workspace_branch": build_config.workspace_branch,
        "cbb_goma_client_type": None,
    }

    # Filter out tags with no value set.
    tags = {k: v for k, v in tags.items() if v}

    tag_lines = [
        '    tags: "%s:%s"' % (k, tags[k]) for k in sorted(tags.keys())
    ]
    prop_lines = [
        '    properties: "%s:%s"' % (k, tags[k]) for k in sorted(tags.keys())
    ]

    # TODO: Move --buildbot arg into recipe, and remove from here.
    template = """
job {
  id: "%(job_name)s"
  realm: "cbb-jobs"
  acl_sets: "default"
  schedule: "%(schedule)s"
  buildbucket: {
    server: "cr-buildbucket.appspot.com"
    bucket: "general"
    builder: "%(builder)s"
%(tag_lines)s
%(prop_lines)s
    properties: "cbb_extra_args:[\\"--buildbot\\"]"
  }
}
"""

    return template % {
        "job_name": job_name,
        "builder": build_config.luci_builder,
        "schedule": build_config.schedule,
        "tag_lines": "\n".join(tag_lines),
        "prop_lines": "\n".join(prop_lines),
    }


def genSchedulerTrigger(trigger_name, repo, refs, path_regexps, builds):
    """Generate the luci scheduler job for a given build config.

    Args:
        trigger_name: Name of the trigger as a string.
        repo: Gitiles URL git git repository.
        refs: Iterable of git refs to check. May use regular expressions.
        path_regexps: Iterable of path regular expressions of files to trigger
            on or falsey to trigger on everything.
        builds: Iterable of build config names to trigger.

    Returns:
        Multiline string to include in the luci scheduler configuration.
    """
    template = """
trigger {
  id: "%(trigger_name)s"
  realm: "cbb-jobs"
  acl_sets: "default"
  schedule: "with 5m interval"
  gitiles: {
    repo: "%(repo)s"
%(refs)s%(path_regexps)s
  }
%(triggers)s
}
"""
    if path_regexps:
        path_regexps = "\n" + "\n".join(
            '    path_regexps: "%s"' % r for r in path_regexps
        )
    else:
        path_regexps = ""
    return template % {
        "trigger_name": trigger_name,
        "repo": repo,
        "refs": "\n".join('    refs: "%s"' % r for r in refs),
        "path_regexps": path_regexps,
        "triggers": "\n".join('  triggers: "%s"' % b for b in builds),
    }


def genLuciSchedulerConfig(site_config):
    """Generate a luciSchedulerConfig as a string.

    Args:
        site_config: A config_lib.SiteConfig instance.

    Returns:
        The complete scheduler configuration contents as a string.
    """
    # Trigger collection is used to collect together trigger information, so
    # we can reuse the same trigger for multiple builds as needed.
    # It maps gitiles_key to a set of build_names.
    # A gitiles_key = (gitiles_url, tuple(ref_list))
    trigger_collection = {}

    jobs = []

    # Order the configs consistently.
    configs = [site_config[name] for name in sorted(site_config)]

    for config in configs:
        # Populate jobs.
        if config.schedule:
            jobs.append(genSchedulerJob(config))

        # Populate trigger_collection.
        if config.triggered_gitiles:
            for trigger in config.triggered_gitiles:
                try:
                    gitiles_url, ref_list, path_regexps = trigger
                except ValueError:
                    gitiles_url, ref_list = trigger
                    path_regexps = []
                gitiles_key = (
                    gitiles_url,
                    tuple(ref_list),
                    tuple(path_regexps),
                )
                trigger_collection.setdefault(gitiles_key, set())
                trigger_collection[gitiles_key].add(buildJobName(config))

    # Populate triggers.
    triggers = []
    trigger_counter = 0
    for gitiles_key in sorted(trigger_collection):
        builds = sorted(trigger_collection[gitiles_key])

        trigger_name = "trigger_%s" % trigger_counter
        gitiles_url, refs, path_regexps = gitiles_key
        triggers.append(
            genSchedulerTrigger(
                trigger_name, gitiles_url, refs, path_regexps, builds
            )
        )
        trigger_counter += 1

    return "".join([_CONFIG_HEADER] + triggers + jobs)


def GetParser():
    """Creates the argparse parser."""
    parser = commandline.ArgumentParser(description=__doc__)

    parser.add_argument(
        "-o", "--file_out", type="path", help="Write output to specified file."
    )

    return parser


def main(argv):
    parser = GetParser()
    options = parser.parse_args(argv)
    options.Freeze()

    site_config = config_lib.GetConfig()
    with (
        open(options.file_out, "w", encoding="utf-8")
        if options.file_out
        else sys.stdout
    ) as fh:
        fh.write(genLuciSchedulerConfig(site_config))
