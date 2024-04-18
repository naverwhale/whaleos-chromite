# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Metrics for general consumption.

See infra/proto/metrics.proto for a description of the type of record that this
module will be creating.
"""

import collections
import logging

from chromite.lib import metrics_lib


def deserialize_metrics_log(output_events, prefix=None):
    """Read the current metrics events, adding to output_events.

    This layer facilitates converting between the internal
    chromite.utils.metrics representation of metric events and the
    infra/proto/src/chromiumos/metrics.proto output type.

    Args:
        output_events: A chromiumos.MetricEvent protobuf message.
        prefix: A string to prepend to all metric event names.
    """
    counters = collections.defaultdict(int)
    counter_times = {}
    timers = {}

    def make_name(name):
        """Prepend a closed-over prefix to the given name."""
        if prefix:
            return "%s.%s" % (prefix, name)
        else:
            return name

    # Reduce over the input events to append output_events.
    for input_event in metrics_lib.read_metrics_events():
        if input_event.op == metrics_lib.OP_START_TIMER:
            timers[input_event.arg] = (
                input_event.name,
                input_event.timestamp_epoch_millis,
            )
        elif input_event.op == metrics_lib.OP_STOP_TIMER:
            # TODO(b/187788898): Drop the None fallback.
            timer = timers.pop(input_event.arg, None)
            if timer is None:
                logging.error(
                    "%s: stop timer recorded, but missing start timer!?",
                    input_event.arg,
                )
            if timer:
                assert input_event.name == timer[0]
                output_event = output_events.add()
                output_event.name = make_name(timer[0])
                output_event.timestamp_milliseconds = (
                    input_event.timestamp_epoch_millis
                )
                output_event.duration_milliseconds = (
                    output_event.timestamp_milliseconds - timer[1]
                )
        elif input_event.op == metrics_lib.OP_NAMED_EVENT:
            output_event = output_events.add()
            output_event.name = make_name(input_event.name)
            output_event.timestamp_milliseconds = (
                input_event.timestamp_epoch_millis
            )
        elif input_event.op == metrics_lib.OP_GAUGE:
            output_event = output_events.add()
            output_event.name = make_name(input_event.name)
            output_event.timestamp_milliseconds = (
                input_event.timestamp_epoch_millis
            )
            output_event.gauge = input_event.arg
        elif input_event.op == metrics_lib.OP_INCREMENT_COUNTER:
            counters[input_event.name] += input_event.arg
            counter_times[input_event.name] = max(
                input_event.timestamp_epoch_millis,
                counter_times.get(input_event.name, 0),
            )
        elif input_event.op == metrics_lib.OP_DECREMENT_COUNTER:
            counters[input_event.name] -= input_event.arg
            counter_times[input_event.name] = max(
                input_event.timestamp_epoch_millis,
                counter_times.get(input_event.name, 0),
            )
        else:
            raise ValueError(
                'unexpected op "%s" found in metric event: %s'
                % (input_event.op, input_event)
            )

    for counter, value in counters.items():
        output_event = output_events.add()
        output_event.name = make_name(counter)
        output_event.gauge = value
        output_event.timestamp_milliseconds = counter_times[counter]

    # Check for any unhandled timers.
    # TODO(b/187788898): Turn this back into an assert.
    if timers:
        logging.error("excess timer metric data left over: %s", timers)
