# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for prctl.py module."""

import ctypes
import errno
import signal

import pytest

from chromite.utils import prctl


def test_prctl_raw():
    """Check basic functionality with PDEATHSIG option."""
    orig = prctl.get_pdeathsig()

    # This should be safe to play with as we should exit before the parent.
    assert prctl.prctl(prctl.Option.SET_PDEATHSIG, signal.SIGQUIT) == 0
    arg2 = ctypes.c_int(0)
    assert prctl.prctl(prctl.Option.GET_PDEATHSIG, ctypes.byref(arg2)) == 0
    assert arg2.value == signal.SIGQUIT

    # Restore the setting.
    prctl.set_pdeathsig(orig)


def test_prctl_error():
    """Check PrctlError handling."""
    e = prctl.PrctlError(prctl.Option.SET_PDEATHSIG, -1)
    assert "SET_PDEATHSIG" in str(e)
    assert "SET_PDEATHSIG" in e.msg

    e = prctl.PrctlError(prctl.Option.SET_PDEATHSIG, -1, errno=errno.EINVAL)
    assert "EINVAL" in e.msg
    assert e.errno == errno.EINVAL

    with pytest.raises(prctl.PrctlError) as excinfo:
        prctl.prctl(prctl.Option.SET_PDEATHSIG, 1000)
    assert excinfo.value.option == prctl.Option.SET_PDEATHSIG
    assert excinfo.value.prargs == [1000, 0, 0, 0]


def test_pdeathsig():
    """Check pdeathsig helpers."""
    orig = prctl.get_pdeathsig()
    assert prctl.set_pdeathsig(signal.SIGINT) is None
    assert prctl.get_pdeathsig() == signal.SIGINT
    # Restore the setting.
    prctl.set_pdeathsig(orig)


def test_name():
    """Check (thread) name helpers."""
    assert prctl.set_name("foo") is None
    assert prctl.get_name() == "foo"

    # Check truncation.
    assert prctl.set_name("1234567890" * 3) is None
    assert prctl.get_name() == "123456789012345"


def test_no_new_privs():
    """Check no_new_privs helpers."""
    assert prctl.get_no_new_privs() in (0, 1)

    # Set it to -1 which doesn't block new privs.  We don't want to mess up the
    # general pytest runtime by locking down privs.
    with pytest.raises(prctl.PrctlError):
        prctl.set_no_new_privs(-1)
