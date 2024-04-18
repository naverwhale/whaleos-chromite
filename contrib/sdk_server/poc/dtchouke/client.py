# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import asyncio
import logging
from typing import List, Optional

import grpc  # pylint: disable=import-error

from chromite.contrib.cros_sdk_server_poc import sdk_server_pb2
from chromite.contrib.cros_sdk_server_poc import sdk_server_pb2_grpc


def SeekUpdate():
    channel = grpc.insecure_channel("localhost:50051")
    stub = sdk_server_pb2_grpc.UpdateServiceStub(channel)
    request = sdk_server_pb2.UpdateRequest()
    response = stub.UpdateChroot(request)
    return response


async def SeekStream() -> None:
    async with grpc.aio.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.StreamServiceStub(channel)
        request = sdk_server_pb2.StreamRequest()

        async for response in stub.GetStream(request):
            logging.info(
                f"Greeter client received from async generator: {response.num}"
            )


def main(argv: Optional[List[str]] = None) -> Optional[int]:
    asyncio.run(SeekStream())
    logging.info(SeekUpdate().version)
