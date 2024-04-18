# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for the api/metrics library."""

from unittest import mock

from chromite.api import metrics as api_metrics
from chromite.api.gen.chromite.api import build_api_test_pb2
from chromite.lib import cros_test_lib
from chromite.lib import metrics_lib


class MetricsTest(cros_test_lib.TestCase):
    """Test Metrics deserialization functionality at the API layer."""

    def testDeserializeTimer(self):
        """Test timer math and deserialization into proto objects."""
        response = build_api_test_pb2.TestResultMessage()
        mock_events = [
            metrics_lib.MetricEvent(
                600, "a.b", metrics_lib.OP_START_TIMER, arg="100"
            ),
            metrics_lib.MetricEvent(
                1000, "a.b", metrics_lib.OP_STOP_TIMER, arg="100"
            ),
        ]
        with mock.patch(
            "chromite.api.metrics.metrics_lib.read_metrics_events",
            return_value=mock_events,
        ):
            api_metrics.deserialize_metrics_log(response.events)
            self.assertEqual(len(response.events), 1)
            self.assertEqual(response.events[0].name, "a.b")
            self.assertEqual(response.events[0].timestamp_milliseconds, 1000)
            self.assertEqual(
                response.events[0].duration_milliseconds, 1000 - 600
            )

    def testDeserializeNamedEvent(self):
        """Test deserialization of a named event.

        This test also includes a prefix to test for proper prepending.
        """
        response = build_api_test_pb2.TestResultMessage()
        mock_events = [
            metrics_lib.MetricEvent(
                1000, "a.named_event", metrics_lib.OP_NAMED_EVENT, arg=None
            ),
        ]
        with mock.patch(
            "chromite.api.metrics.metrics_lib.read_metrics_events",
            return_value=mock_events,
        ):
            api_metrics.deserialize_metrics_log(
                response.events, prefix="prefix"
            )
            self.assertEqual(len(response.events), 1)
            self.assertEqual(response.events[0].name, "prefix.a.named_event")
            self.assertEqual(response.events[0].timestamp_milliseconds, 1000)
            self.assertFalse(response.events[0].duration_milliseconds)

    def testDeserializeGauge(self):
        """Test deserialization of a gauge."""
        response = build_api_test_pb2.TestResultMessage()
        mock_events = [
            metrics_lib.MetricEvent(
                1000, "a.gauge", metrics_lib.OP_GAUGE, arg=17
            ),
        ]
        with mock.patch(
            "chromite.api.metrics.metrics_lib.read_metrics_events",
            return_value=mock_events,
        ):
            api_metrics.deserialize_metrics_log(response.events)
            self.assertEqual(len(response.events), 1)
            self.assertEqual(response.events[0].name, "a.gauge")
            self.assertEqual(response.events[0].timestamp_milliseconds, 1000)
            self.assertEqual(response.events[0].gauge, 17)

    def testDeserializeCounter(self):
        """Test deserialization of a counter."""
        response = build_api_test_pb2.TestResultMessage()
        mock_events = [
            metrics_lib.MetricEvent(
                1000, "a.counter", metrics_lib.OP_INCREMENT_COUNTER, arg=1
            ),
            metrics_lib.MetricEvent(
                1001, "a.counter", metrics_lib.OP_INCREMENT_COUNTER, arg=2
            ),
            metrics_lib.MetricEvent(
                1002, "a.counter", metrics_lib.OP_INCREMENT_COUNTER, arg=3
            ),
            metrics_lib.MetricEvent(
                1003, "a.counter", metrics_lib.OP_DECREMENT_COUNTER, arg=4
            ),
        ]
        with mock.patch(
            "chromite.api.metrics.metrics_lib.read_metrics_events",
            return_value=mock_events,
        ):
            api_metrics.deserialize_metrics_log(response.events)
            self.assertEqual(len(response.events), 1)
            self.assertEqual(response.events[0].name, "a.counter")
            self.assertEqual(response.events[0].timestamp_milliseconds, 1003)
            self.assertEqual(response.events[0].gauge, 2)
