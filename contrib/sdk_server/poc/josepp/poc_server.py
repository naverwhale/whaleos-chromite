# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Proof of concept client code for SDK server implementation options."""

from concurrent import futures
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import List, Optional

import grpc  # pylint: disable=import-error

from chromite.api.gen.chromite.api import sdk_pb2
from chromite.contrib.sdk_server.poc.josepp import range_pb2
from chromite.contrib.sdk_server.poc.josepp import range_pb2_grpc
from chromite.contrib.sdk_server.poc.josepp import sdk_pb2_grpc
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.service import sdk


USE_API = True


class SdkServiceServicer(sdk_pb2_grpc.SdkServiceServicer):
    """Implements Update endpoint for SDK service"""

    def Update(self, request, context):
        if USE_API:
            return self.UpdateWithBuildAPI(request, context)
        else:
            return self.UpdateWithController(request, context)

    # pylint: disable=unused-argument
    def UpdateWithBuildAPI(self, request, context):
        """Performs Chroot Update by calling build_api script"""

        # build_api requires protos in files
        with NamedTemporaryFile() as proto_in, NamedTemporaryFile() as proto_out:
            proto_in.write(request.SerializeToString())

            in_path = str(Path(proto_in.name))
            out_path = str(Path(proto_out.name))

            cros_build_lib.run(
                [
                    constants.CHROMITE_BIN_DIR / "build_api",
                    "chromite.api.SdkService/Update",
                    "--input-binary=" + in_path,
                    "--output-binary=" + out_path,
                ]
            )

            response = sdk_pb2.UpdateResponse()
            response.ParseFromString(proto_out.read())

            return response

    # pylint: disable=unused-argument
    def UpdateWithController(self, request, context):
        """Re-implements build_api controller layer to perform Chroot Update"""

        input_proto = request
        output_proto = sdk_pb2.UpdateResponse()

        build_source = input_proto.flags.build_source
        targets = [target.name for target in input_proto.toolchain_targets]
        toolchain_changed = input_proto.flags.toolchain_changed

        args = sdk.UpdateArguments(
            build_source=build_source,
            toolchain_targets=targets,
            toolchain_changed=toolchain_changed,
        )

        version = sdk.Update(args)

        if version:
            output_proto.version.version = version
        else:
            cros_build_lib.Die(
                "No chroot version could be found. There was likely an"
                "error creating the chroot that was not detected."
            )

        return output_proto


class RangeServiceServicer(range_pb2_grpc.RangeServiceServicer):
    """Implements example service with streaming endpoint."""

    def GetRange(self, request, context):
        """Example RPC streaming endpoint."""

        for i in range(request.start, request.stop):
            r = range_pb2.RangeResponse()
            r.value = i
            yield r


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # Future method of adding SDK and new chroot-only services to one server
    sdk_pb2_grpc.add_SdkServiceServicer_to_server(SdkServiceServicer(), server)
    range_pb2_grpc.add_RangeServiceServicer_to_server(
        RangeServiceServicer(), server
    )

    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()


# pylint: disable=unused-argument
def main(argv: Optional[List[str]] = None) -> Optional[int]:
    serve()
