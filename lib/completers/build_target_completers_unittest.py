# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for build_target_completers."""

from pathlib import Path

from chromite.lib import constants
from chromite.lib import path_util
from chromite.lib import portage_util
from chromite.lib.completers import build_target_completers


def test_build_target(monkeypatch):
    """Test that expected build targets are returned from overlays."""

    def mock_find_overlays(overlay_type, *_args, **_kwargs):
        assert overlay_type == constants.BOTH_OVERLAYS
        return [
            "/overlays/overlay-overlay1",
            "/overlays/overlay-overlay2",
            "/overlays/overlay-variant-overlay3",
            "/overlays/overlay-overlay2-private",
            "/overlays/overlay-test",
            "/overlays/project-testproject",
        ]

    monkeypatch.setattr(portage_util, "FindOverlays", mock_find_overlays)
    expected_build_targets = ["overlay1", "overlay2"]

    build_targets = build_target_completers.build_target(
        "overlay", None, None, None
    )

    assert build_targets == expected_build_targets


def test_built_build_target(monkeypatch, tmp_path):
    """Test that only built build targets are returned."""

    def mock_path(path, *_args, **_kwargs):
        assert path == Path(path_util.FromChrootPath("/build"))
        return [
            Path(tmp_path) / "sysroot1" / "etc" / "portage",
            Path(tmp_path) / "sysroot2" / "etc" / "portage",
        ]

    monkeypatch.setattr(Path, "glob", mock_path)
    expected_built_build_targets = ["sysroot1", "sysroot2"]

    built_build_targets = list(
        build_target_completers.built_build_target("", None, None, None)
    )

    assert built_build_targets == expected_built_build_targets
