# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test creation of ~/.config/chromite and dir permissions."""

import os

import pytest

from chromite.lib import chromite_config
from chromite.lib import osutils


@pytest.fixture(name="chromite_config_dir")
def chromite_config_dir_fixture(monkeypatch, tmp_path):
    d = tmp_path / ".config" / "chromite"
    monkeypatch.setattr(chromite_config, "DIR", d)

    for cfg_name, cfg_file in chromite_config.ALL_CONFIGS.items():
        monkeypatch.setattr(chromite_config, cfg_name, d / cfg_file)

    yield d


def test_chromite_config_created(chromite_config_dir):
    chromite_config.initialize()
    assert os.path.exists(chromite_config_dir)


def test_chromite_config_chowns_to_non_root(chromite_config_dir):
    osutils.SafeMakedirs(chromite_config_dir, sudo=True, user="root")
    assert chromite_config_dir.owner() == "root"

    chromite_config.initialize()
    assert chromite_config_dir.owner() != "root"
