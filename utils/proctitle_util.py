# Copyright 2014 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrapper module for dealing with setting the process title (seen in `ps`)."""

import os

import __main__ as main


# Import the relevant funcs into our namespace for callers.
try:
    # pylint: disable=unused-import, no-name-in-module
    from setproctitle import getproctitle
    from setproctitle import setproctitle
except ImportError:
    # Module not available -> use basic prctl API.
    from chromite.utils import prctl

    getproctitle = prctl.get_name
    setproctitle = prctl.set_name


# Used with the settitle helper below.
_SCRIPT_NAME = os.path.basename(getattr(main, "__file__", "chromite"))


# Used to distinguish between different runs.
_TITLE_PID = os.getpid()


def settitle(*args):
    """Set the process title to something useful to make `ps` output easy."""
    base = ("%s/%s" % (_SCRIPT_NAME, _TITLE_PID),)
    setproctitle(": ".join(base + args))
