# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for the lib/metrics_lib module."""

import os
from unittest import mock

from chromite.lib import cros_test_lib
from chromite.lib import metrics_lib


class MetricsTest(cros_test_lib.TestCase):
    """Tests for metrics_lib."""

    def testEndToEnd(self):
        """Test the normal usage pattern, end-to-end."""
        # We should start in a clean, unmeasured state.
        self.assertFalse(os.environ.get(metrics_lib.UTILS_METRICS_LOG_ENVVAR))

        with mock.patch(
            "chromite.lib.metrics_lib.current_milli_time"
        ) as mock_time:
            mock_time.side_effect = [128000, 256000, 512300]

            events = []

            # Create a fake usage site of the metrics.
            @metrics_lib.collect_metrics
            def measure_things():
                # Now, in here, we should have set up this env-var. This is a
                # bit of invasive white-box testing.
                self.assertTrue(
                    os.environ.get(metrics_lib.UTILS_METRICS_LOG_ENVVAR)
                )

                # Now, with our pretend timer, let's record some events.
                with metrics_lib.timer("test.timer"):
                    metrics_lib.event("test.named_event")

                for event in metrics_lib.read_metrics_events():
                    events.append(event)

            # Run the fake scenario.
            measure_things()

            self.assertEqual(len(events), 3)
            self.assertEqual(events[0].timestamp_epoch_millis, 128000)
            self.assertEqual(events[0].op, metrics_lib.OP_START_TIMER)
            self.assertEqual(events[0].name, "test.timer")

            self.assertEqual(events[1].timestamp_epoch_millis, 256000)
            self.assertEqual(events[1].op, metrics_lib.OP_NAMED_EVENT)
            self.assertEqual(events[1].name, "test.named_event")

            self.assertEqual(events[2].timestamp_epoch_millis, 512300)
            self.assertEqual(events[2].op, metrics_lib.OP_STOP_TIMER)
            self.assertEqual(events[2].name, "test.timer")
