# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Timing utility."""

import contextlib
import datetime
import functools
import logging
import time
from typing import Any, Callable, Optional

from chromite.utils import pformat


class Timer:
    """Simple timer class to make timing blocks of code easy.

    It does not have the features of timeit, but can be added anywhere, e.g. to
    time a specific section of a script. The Timer class implements __add__ and
    __truediv__ to allow averaging multiple timers, but the collection must be
    done manually.

    Examples:
        with Timer():
            code_to_be_timed()

        with Timer() as t: ->  str(t) == "{formatted_delta}"
        with Timer('name') as t: -> str(t) == "name: {formatted_delta}"

        To get an average:

        timers = []
        for _ in range(10):
            with Timer() as t:
                code_to_be_timed()
            timers.append(t)
        avg = sum(timers, start=Timer('Average')) / len(times)
        avg.output() -> prints "Average: {formatted_delta}"
    """

    def __init__(self, name: Optional[str] = None):
        """Init.

        Args:
            name: A string to identify the timer.
        """
        self.name = name
        self.start = 0.0
        self.end = 0.0
        self.delta = 0.0

    @property
    def timedelta(self):
        """Convenience method for getting a timedelta object."""
        return datetime.timedelta(seconds=self.delta)

    def __add__(self, other):
        if not isinstance(other, Timer):
            raise NotImplementedError(f"Cannot add {type(other)} to Timer")
        result = Timer(self.name)
        result.delta = self.delta + other.delta

        return result

    def __truediv__(self, other):
        if not isinstance(other, int):
            raise NotImplementedError(
                f"Only int is supported, given {type(other)}"
            )
        result = Timer(self.name)
        result.delta = self.delta / other

        return result

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.end = time.perf_counter()
        self.delta = self.end - self.start

    def __str__(self):
        name = f"{self.name}: " if self.name else ""
        return f"{name}{pformat.timedelta(self.timedelta)}"


def timed(
    name: Optional[str] = None, output: Callable[[str], Any] = logging.info
):
    """Timed decorator to add a timer to a function."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with timer(name or func.__name__, output):
                return func(*args, **kwargs)

        return wrapper

    return decorator


@contextlib.contextmanager
def timer(
    name: Optional[str] = None, output: Callable[[str], Any] = logging.info
):
    """Timer context manager to automatically output results."""
    t = Timer(name)
    try:
        with t:
            yield t
    finally:
        output(str(t))
