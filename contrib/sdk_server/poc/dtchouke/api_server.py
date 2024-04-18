# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import asyncio
from concurrent import futures
import logging
from typing import List, Optional

from chromite.third_party.google.protobuf import json_format
import grpc  # pylint: disable=import-error

from chromite.contrib.cros_sdk_server_poc import sdk_server_pb2
from chromite.contrib.cros_sdk_server_poc import sdk_server_pb2_grpc
from chromite.lib import cros_build_lib
from chromite.lib import osutils


class UpdateService(sdk_server_pb2_grpc.UpdateServiceServicer):
    """Update Endpoint Servicer"""

    def UpdateChroot(self, request, context):
        logging.info("API CALL...")

        # TODO: Convert to list
        script = (
            "~/chromiumos/chromite/bin/build_api "
            "chromite.api.SdkService/Update "
            "--input-json ./input.json "
            "--output-json ./output.json "
            "--debug "
        )

        cros_build_lib.run(script, shell=True)
        contents = osutils.ReadFile("output.json")
        response = sdk_server_pb2.UpdateResponse()
        json_format.Parse(contents, response)
        return response


class StreamService(sdk_server_pb2_grpc.StreamServiceServicer):
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
    sdk_server_pb2_grpc.add_UpdateServiceServicer_to_server(
        updateServicer, server
    )
    sdk_server_pb2_grpc.add_StreamServiceServicer_to_server(
        streamServicer, server
    )
    server.add_insecure_port("[::]:50051")
    await server.start()
    logging.info("CONNECTED")
    await server.wait_for_termination()
    logging.info("TERMINATED!")


def main(argv: Optional[List[str]] = None) -> Optional[int]:
    asyncio.run(serve())
