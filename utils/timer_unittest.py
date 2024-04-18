# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for timer."""

import re
import time
from unittest import mock

import pytest

from chromite.utils import timer


DELTA = 1.0


@pytest.fixture(autouse=True)
def time_mock_fixture(monkeypatch):
    last_t = 0.0

    def time_mock():
        nonlocal last_t
        last_t += DELTA
        return last_t

    monkeypatch.setattr(time, "perf_counter", time_mock)


def test_timer_delta(caplog):
    """Test basic usage of a Timer."""
    with timer.timer() as t:
        pass
    assert re.search(f"{DELTA}[0-9]*s", caplog.text) is not None
    assert t.delta == DELTA
    assert t.timedelta.total_seconds() == DELTA


def test_timer_average():
    """Test the timer __add__ and __truediv__ functions."""
    timers = []
    range_len = 10
    for x in range(range_len):
        with timer.Timer(str(x)) as t:
            pass
        timers.append(t)

    assert sum(timers, start=timer.Timer()).delta == DELTA * range_len
    assert (sum(timers, start=timer.Timer()) / len(timers)).delta == DELTA


def test_timer_decorator():
    """Test the timed decorator."""
    name = "name"
    output_fn_called = False

    # Output function to check the value.
    def output_fn(value):
        nonlocal output_fn_called
        output_fn_called = True
        assert re.match(f"{name}: {DELTA}[0-9]*s", value) is not None

    # The decorated function.
    @timer.timed(name, output_fn)
    def timed_fn():
        pass

    # Run the function to trigger the test.
    timed_fn()

    assert output_fn_called


def test_timer_decorator_with_exception_calls_output():
    """Test the timed decorator with exception handling."""
    name = "test_name"
    output_fn = mock.MagicMock()

    # The decorated function.
    @timer.timer(name, output_fn)
    def timed_fn():
        raise Exception("test exception")

    # Run the function to trigger the test.
    with pytest.raises(Exception):
        timed_fn()

    output_fn.assert_called_once()
