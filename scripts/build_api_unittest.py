# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for build_api.py"""

from __future__ import division

from chromite.api import router as router_lib
from chromite.lib import osutils
from chromite.scripts import build_api


def testSmoke(tmp_path, monkeypatch):
    """Basic confidence check"""

    def stub(*_args, **_kwargs):
        return True

    monkeypatch.setattr(router_lib.Router, "Route", stub)

    input_json = tmp_path / "input.json"
    output_json = tmp_path / "output.json"

    osutils.WriteFile(input_json, "{}")

    build_api.main(
        [
            "--input-json",
            str(input_json),
            "--output-json",
            str(output_json),
            "chromite.api.VersionService/Get",
        ]
    )
