# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Timing utility."""

import datetime
import functools
import logging
import time
from typing import Any, Callable, Optional

from chromite.utils import pformat


class Timer(object):
  """Simple timer class to make timing blocks of code easy.

  It does not have the features of timeit, but can be added anywhere, e.g. to
  time a specific section of a script. The Timer class implements __add__ and
  __truediv__ to allow averaging multiple timers, but the collection must be
  done manually.

  Examples:
    with Timer():
      code_to_be_timed()

    with Timer(): -> logs "{formatted_delta}" at info level
    with Timer('name'): -> logs "name: {formatted_delta}" at info
    with Timer('name', print): -> prints "name: {formatted_delta}"

    If you don't want it to output itself on exit, you can do it manually,
    e.g. to get an average:

    timers = []
    for _ in range(10):
      with Timer(output=None) as t:
        ...
      timers.append(t)
    avg = sum(timers, start=Timer('Average')) / len(times)
    avg.output() -> prints "Average: {formatted_delta}"
  """

  def __init__(self,
               name: Optional[str] = None,
               output: Optional[Callable[[str], Any]] = logging.info):
    """Init.

    Args:
      name: A string to identify the timer, especially when using multiple.
      output: A function that takes only a string to output it somewhere.
    """
    self.name = name
    # Make output always callable, but do nothing when no output.
    self.output = lambda: output(str(self)) if output else None
    self.start = 0.0
    self.end = 0.0
    self.delta = 0.0

  def __add__(self, other):
    if not isinstance(other, Timer):
      raise NotImplementedError(f'Cannot add {type(other)} to Timer')
    result = Timer(self.name, self.output)
    result.delta = self.delta + other.delta

    return result

  def __truediv__(self, other):
    if not isinstance(other, int):
      raise NotImplementedError(f'Only int is supported, given {type(other)}')
    result = Timer(self.name, self.output)
    result.delta = self.delta / other

    return result

  def __enter__(self):
    self.start = time.perf_counter()
    return self

  def __exit__(self, *args):
    self.end = time.perf_counter()
    self.delta = self.end - self.start
    self.output()

  def __str__(self):
    name = f'{self.name}: ' if self.name else ''
    return f'{name}{pformat.timedelta(datetime.timedelta(seconds=self.delta))}'


def timer(name: Optional[str] = None,
          output: Callable[[str], Any] = logging.info):
  """Timer decorator."""

  def decorator(func):

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
      with Timer(name, output):
        return func(*args, **kwargs)

    return wrapper

  return decorator
