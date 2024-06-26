# Copyright 2016 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Puppet metrics"""

from __future__ import absolute_import

import logging
import time

import yaml  # pylint: disable=import-error

from chromite.lib import metrics


logger = logging.getLogger(__name__)

LAST_RUN_FILE = "/var/lib/cros_puppet/state/last_run_summary.yaml"

_config_version_metric = metrics.GaugeMetric(
    "puppet/version/config",
    description=(
        "The version of the puppet configuration."
        "  By default this is the time that the configuration was parsed"
    ),
)
_puppet_version_metric = metrics.StringMetric(
    "puppet/version/puppet", description="Version of puppet client installed."
)
_events_metric = metrics.GaugeMetric(
    "puppet/events",
    description=(
        "Number of changes the puppet client made to the system in its"
        " last run, by success or failure"
    ),
)
_resources_metric = metrics.GaugeMetric(
    "puppet/resources",
    description=(
        "Number of resources known by the puppet client in its last run"
    ),
)
_times_metric = metrics.FloatMetric(
    "puppet/times",
    description="Time taken to perform various parts of the last puppet run",
)
_age_metric = metrics.FloatMetric(
    "puppet/age", description="Time since last run"
)


class _PuppetRunSummary:
    """Puppet run summary information."""

    def __init__(self, f):
        """Instantiate instance.

        Args:
            f: file object to read summary from
        """
        self._data = yaml.safe_load(f)

    @property
    def _versions(self):
        """Return mapping of version information."""
        return self._data.get("version", {})

    @property
    def config_version(self):
        """Return config version as int."""
        return self._versions.get("config", -1)

    @property
    def puppet_version(self):
        """Return Puppet version as string."""
        return self._versions.get("puppet", "")

    @property
    def events(self):
        """Return mapping of events information."""
        events = self._data.get("events", {})
        events.pop("total", None)
        return events

    @property
    def resources(self):
        """Return mapping of resources information."""
        resources = self._data.get("resources", {})
        total = resources.pop("total", 0)
        resources["other"] = max(0, total - sum(resources.values()))
        return resources

    @property
    def times(self):
        """Return mapping of time information."""
        times = self._data.get("time", {}).copy()
        times.pop("last_run", None)
        total = times.pop("total", 0)
        times["other"] = max(0, total - sum(times.values()))
        return times

    @property
    def last_run_time(self):
        """Return last run time as UNIX seconds or None."""
        times = self._data.get("time", {})
        return times.get("last_run")


def collect_puppet_summary():
    """Send Puppet run summary metrics."""
    try:
        with open(LAST_RUN_FILE, encoding="utf-8") as f:
            summary = _PuppetRunSummary(f)
    except Exception as e:
        logger.warning("Error loading Puppet run summary: %s", e)
    else:
        _config_version_metric.set(summary.config_version)
        _puppet_version_metric.set(str(summary.puppet_version))

        for key, value in summary.events.items():
            _events_metric.set(value, {"result": key})

        for key, value in summary.resources.items():
            _resources_metric.set(value, {"action": key})

        for key, value in summary.times.items():
            _times_metric.set(value, {"step": key})

        if summary.last_run_time is not None:
            _age_metric.set(time.time() - summary.last_run_time)
