# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for lazy_loader."""

import pickle

from chromite.lib import osutils
from chromite.utils import lazy_loader


# pylint: disable=protected-access


def test_lazy_load_call():
    """Verify we can call functions."""
    mod = lazy_loader.ForFunctions("chromite.lib.osutils")
    # Read this unittest file and make sure the content is correct.
    data = mod.ReadFile(__file__)
    # Check for a known string in this source file.
    assert "__FOO__" in data
    # Verify a string doesn't exist in this source file.  Look for a literal tab
    # using an escape sequence which won't be a literal tab.
    assert "\t" not in data


def test_pickle():
    """Test picklability needed for multiprocessing."""
    data = osutils.ReadFile(__file__)
    mod = lazy_loader.ForFunctions("chromite.lib.osutils")

    # Pickle before use -- no module loaded.
    assert mod._mod is None
    pickled = pickle.dumps(mod)
    unpickled = pickle.loads(pickled)
    assert data == mod.ReadFile(__file__) == unpickled.ReadFile(__file__)

    # Pickle after use -- module is loaded.
    assert mod._mod is not None
    pickled = pickle.dumps(mod)
    unpickled = pickle.loads(pickled)
    assert unpickled._mod is not None
    assert data == mod.ReadFile(__file__) == unpickled.ReadFile(__file__)
