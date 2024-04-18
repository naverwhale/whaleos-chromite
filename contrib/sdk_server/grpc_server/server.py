# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The definition of the grpc server for sdk server."""

import asyncio
import atexit
from concurrent import futures
from typing import List, Optional

import grpc  # pylint: disable=import-error

from chromite.contrib.sdk_server.grpc_server import sdk_server_defs_grpc
from chromite.contrib.sdk_server.grpc_server import sdk_server_pb2_grpc
from chromite.lib import sudo


async def serve() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=None))
    servicer = sdk_server_defs_grpc.SdkChroot()
    sdk_server_pb2_grpc.add_sdk_server_serviceServicer_to_server(
        servicer, server
    )

    server.add_insecure_port("[::]:50051")
    server.start()

    def stop_server():
        server.stop(5)

    atexit.register(stop_server)
    server.wait_for_termination(timeout=None)


def run():
    with sudo.SudoKeepAlive():
        asyncio.run(serve())


def main(argv: Optional[List[str]] = None) -> Optional[int]:
    run()
