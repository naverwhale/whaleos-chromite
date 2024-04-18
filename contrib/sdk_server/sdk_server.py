# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrapper for SDK Server."""

import atexit
import subprocess

from chromite.lib import constants
from chromite.lib import sudo


PROCESSES = []


def run_server():
    """Start grpc server of sdk server."""
    with sudo.SudoKeepAlive():
        script = [
            constants.CHROMITE_DIR / "contrib/sdk_server/grpc_server/server"
        ]
        return subprocess.Popen(script)


def run_app():
    """Start Web app of sdk server."""
    script = [constants.CHROMITE_DIR / "contrib/sdk_server/ui/app"]
    return subprocess.Popen(script)


def clean_up():
    for p in PROCESSES:
        p.kill()
    print("cleaned up!")


def main(argv):
    atexit.register(clean_up)
    server_proc = run_server()
    PROCESSES.append(server_proc)
    try:
        app_proc = run_app()
        PROCESSES.append(app_proc)
    except Exception as e:
        raise e
    try:
        while True:
            pass
    except:
        pass
