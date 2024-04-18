# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import asyncio
from concurrent import futures
import logging
from typing import List, Optional

import grpc  # pylint: disable=import-error

from chromite.api.api_config import ApiConfig
from chromite.api.controller import sdk as sdk_controller
from chromite.api.gen.chromite.api import sdk_pb2
from chromite.contrib.cros_sdk_server_poc import sdk_server_pb2
from chromite.contrib.cros_sdk_server_poc import sdk_server_pb2_grpc as pb2_grpc


class UpdateService(pb2_grpc.UpdateServiceServicer):
    """Update Endpoint Servicer"""

    def UpdateChroot(self, request, context):
        logging.info("API CALL...")
        controllerResponse = sdk_pb2.UpdateResponse()
        sdk_controller.Update(
            sdk_pb2.UpdateRequest(), controllerResponse, ApiConfig()
        )
        version = sdk_server_pb2.ChrootVersion()
        version.version = controllerResponse.version.version
        return sdk_server_pb2.UpdateResponse(version=version)


class StreamService(pb2_grpc.StreamServiceServicer):
    """Streaming Endpoint Servicer"""

    async def GetStream(self, request, context):
        logging.info("API CALL...")
        for i in range(300):
            yield sdk_server_pb2.StreamResponse(num=i)


async def serve() -> None:
    logging.info("STARTING UP...")
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=None))
    updateServicer = UpdateService()
    streamServicer = StreamService()
    pb2_grpc.add_UpdateServiceServicer_to_server(updateServicer, server)
    pb2_grpc.add_StreamServiceServicer_to_server(streamServicer, server)
    server.add_insecure_port("[::]:50051")
    await server.start()
    logging.info("CONNECTED")
    await server.wait_for_termination()
    logging.info("TERMINATED!")


def main(argv: Optional[List[str]] = None) -> Optional[int]:
    asyncio.run(serve())
