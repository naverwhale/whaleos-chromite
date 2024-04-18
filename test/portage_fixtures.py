# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Configuration and fixtures for pytest.

See the following doc link for an explanation of conftest.py and how it is used
by pytest:
https://docs.pytest.org/en/latest/fixture.html#conftest-py-sharing-fixture-functions
"""

import pytest

import chromite as cr


@pytest.fixture
def overlay_stack(tmp_path_factory):
    """Factory for stacked Portage overlays.

    The factory function takes an integer argument and returns an iterator of
    that many overlays, each of which has all prior overlays as parents.
    """

    def make_overlay_stack(height):
        if not height <= len(cr.test.Overlay.HIERARCHY_NAMES):
            raise ValueError(
                "Overlay stacks taller than %s are not supported. Received: %s"
                % (len(cr.test.Overlay.HIERARCHY_NAMES), height)
            )

        overlays = []

        for i in range(height):
            overlays.append(
                cr.test.Overlay(
                    root_path=tmp_path_factory.mktemp(
                        "overlay-" + cr.test.Overlay.HIERARCHY_NAMES[i]
                    ),
                    name=cr.test.Overlay.HIERARCHY_NAMES[i],
                    parent_overlays=overlays,
                )
            )
            yield overlays[i]

    return make_overlay_stack


# pylint: disable=redefined-outer-name
@pytest.fixture
def simple_sysroot(overlay_stack, tmp_path):
    """Create the simplest possible sysroot."""
    # pylint: disable=redefined-outer-name
    (overlay,) = overlay_stack(1)
    profile = overlay.create_profile()
    return cr.test.Sysroot(tmp_path, profile, [overlay])
