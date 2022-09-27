# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import functools
import logging
import sys

assert sys.version_info >= (3, 6), 'Chromite requires Python 3.6+'

# Set a custom logging class inside this module that provides the NOTICE level.
NOTICE = 25


class ChromiteLogger(logging.getLoggerClass()):
  """Logger subclass that provides the additional `notice` level."""

  def __init__(self, name: str, level: int = logging.NOTSET):
    super().__init__(name, level=level)
    logging.addLevelName(NOTICE, 'NOTICE')

  def notice(self, msg, *args, **kwargs):
    if self.isEnabledFor(NOTICE):
      self._log(NOTICE, msg, args, **kwargs)


logging.setLoggerClass(ChromiteLogger)

# Monkeypatching these attributes onto the logging module can be removed once
# all logging calls in chromite are done via methods on a Logger instance, e.g.
# `log = logging.getLogger(); log.notice(...)`, rather than the top-level helper
# functions such as `logging.notice(...)` directly.
logging.notice = functools.partial(logging.log, NOTICE)
logging.NOTICE = NOTICE
logging.addLevelName(logging.NOTICE, 'NOTICE')
