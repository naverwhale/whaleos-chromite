# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Proof of concept client code for SDK server implementation options."""

from typing import List, Optional

import grpc  # pylint: disable=import-error

from chromite.api.gen.chromite.api import sdk_pb2
from chromite.contrib.sdk_server.poc.josepp import range_pb2
from chromite.contrib.sdk_server.poc.josepp import range_pb2_grpc
from chromite.contrib.sdk_server.poc.josepp import sdk_pb2_grpc


def update(stub):
    request = sdk_pb2.UpdateRequest()
    response = stub.Update(request)
    print(response.version.version)


def get_range(stub):
    request = range_pb2.RangeRequest()
    request.start = 1
    request.stop = 100
    response = stub.GetRange(request)
    for r in response:
        print(r.value)


def run():
    with grpc.insecure_channel("localhost:50051") as channel:
        sdk_stub = sdk_pb2_grpc.SdkServiceStub(channel)
        update(sdk_stub)

        range_stub = range_pb2_grpc.RangeServiceStub(channel)
        get_range(range_stub)


# pylint: disable=unused-argument
def main(argv: Optional[List[str]] = None) -> Optional[int]:
    run()
