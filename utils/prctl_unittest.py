# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for prctl.py module."""

import ctypes
import signal

from chromite.lib import cros_test_lib
from chromite.utils import prctl


class PrctlTests(cros_test_lib.TestCase):
  """Tests for prctl()."""

  def test_pdeathsig(self):
    """Check basic functionality with PDEATHSIG option."""
    # This should be safe to play with as we should exit before the parent.
    self.assertEqual(0, prctl.prctl(prctl.Option.SET_PDEATHSIG, signal.SIGQUIT))
    arg2 = ctypes.c_int()
    self.assertEqual(
        0, prctl.prctl(prctl.Option.GET_PDEATHSIG, ctypes.byref(arg2)))
    self.assertEqual(signal.SIGQUIT, arg2.value)
