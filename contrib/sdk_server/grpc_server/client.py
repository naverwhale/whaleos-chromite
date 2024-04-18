# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Definitions of sdk server client functions.

These functions send requests to the sdk server
"""

from typing import Generator, List, Optional

import grpc  # pylint: disable=import-error

from chromite.contrib.sdk_server.grpc_server import sdk_server_pb2
from chromite.contrib.sdk_server.grpc_server import sdk_server_pb2_grpc


def cros_workon_info(
    request: sdk_server_pb2.WorkonInfoRequest,
) -> sdk_server_pb2.WorkonInfoResponse:
    """sends grpc request for cros workon info to sdk server."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        response = stub.cros_workon_info(request)
        return response


def cros_workon_list(
    request: sdk_server_pb2.WorkonListRequest,
) -> sdk_server_pb2.WorkonListResponse:
    """sends grpc request for cros workon list to sdk server."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        response = stub.cros_workon_list(request)
        return response


def cros_workon_start(
    request: sdk_server_pb2.WorkonStartRequest,
) -> sdk_server_pb2.WorkonStartResponse:
    """sends grpc request for cros workon start to sdk server."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        response = stub.cros_workon_start(request)
        return response


def cros_workon_stop(
    request: sdk_server_pb2.WorkonStopRequest,
) -> sdk_server_pb2.WorkonStopResponse:
    """sends grpc request for cros workon stop to sdk server."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        response = stub.cros_workon_stop(request)
        return response


def chroot_info(
    request: sdk_server_pb2.ChrootInfoRequest,
) -> sdk_server_pb2.ChrootInfoResponse:
    """sends grpc request for the chroot path to sdk server."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        response = stub.chroot_info(request)
        return response


def all_packages(
    request: sdk_server_pb2.AllPackagesRequest,
) -> sdk_server_pb2.AllPackagesResponse:
    """sends grpc request for cros workon --all list to sdk server."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        response = stub.all_packages(request)
        return response


def repo_sync(
    request: sdk_server_pb2.RepoSyncRequest,
) -> sdk_server_pb2.RepoSyncResponse:
    """sends grpc request for repo sync to sdk server."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        for response in stub.repo_sync(request):
            yield response


def repo_status(
    request: sdk_server_pb2.RepoStatusRequest,
) -> sdk_server_pb2.RepoStatusResponse:
    """sends grpc request for repo status to sdk server."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        response = stub.repo_status(request)
        return response


def update_chroot(request: sdk_server_pb2.UpdateChrootRequest):
    """sends grpc request for update chroot to sdk server."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        finalResp = None
        for response in stub.update_chroot(request):
            finalResp = response
            yield response

        yield finalResp


def create_sdk(
    request: sdk_server_pb2.CreateSdkRequest,
) -> Generator[sdk_server_pb2.CreateSdkResponse, None, None]:
    """sends grpc request to sdk server for BAPI create sdk endpoint."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        finalResp = None
        for response in stub.create_sdk(request):
            finalResp = response
            yield response

        yield finalResp


def replace_sdk(
    request: sdk_server_pb2.ReplaceSdkRequest,
) -> Generator[sdk_server_pb2.ReplaceSdkResponse, None, None]:
    """sends grpc request to sdk server for BAPI update sdk endpoint.

    See: update sdk endpoint is the create sdk endpoint with no_replace = False
    """
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)

        finalResp = None
        for response in stub.replace_sdk(request):
            finalResp = response
            yield response

        yield finalResp


def delete_sdk(
    request: sdk_server_pb2.DeleteSdkRequest,
) -> Generator[sdk_server_pb2.DeleteSdkResponse, None, None]:
    """sends grpc request to sdk server for BAPI delete sdk endpoint."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        finalResp = None
        for response in stub.delete_sdk(request):
            finalResp = response
            yield response

        yield finalResp


def build_packages(request: sdk_server_pb2.BuildPackagesRequest):
    """sends grpc request to sdk server for BAPI build packages.

    Calls the following endpoints:
        Sysroot create
        install toolcahin
        build packages
    """
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        finalResp = None
        for response in stub.build_packages(request):
            finalResp = response
            yield response

        yield finalResp


def build_image(
    request: sdk_server_pb2.BuildImageRequest,
) -> Generator[sdk_server_pb2.BuildImageResponse, None, None]:
    """sends grpc request to sdk server for BAPI build image endpoint."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)

        finalResp = None
        for response in stub.build_image(request):
            finalResp = response
            yield response

        yield finalResp


def query_boards(
    request: sdk_server_pb2.QueryBoardsRequest,
) -> sdk_server_pb2.QueryBoardsResponse:
    """runs cros query boards."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        response = stub.query_boards(request)
        return response


def current_boards(
    request: sdk_server_pb2.CurrentBoardsRequest,
) -> sdk_server_pb2.CurrentBoardsResponse:
    """returns list of boards in chroot at /build."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        response = stub.current_boards(request)
        return response


def get_logs(request: sdk_server_pb2.LogsRequest):
    """Sends request to get grpc server logs."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        response = stub.get_logs(request)
        return response


def clear_logs(request: sdk_server_pb2.ClearLogsRequest):
    """Sends request to clear grpc server logs."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        response = stub.clear_logs(request)
        return response


def get_methods(request: sdk_server_pb2.MethodsRequest):
    """Sends grpc request to run the BAPI MethodGet endpoint."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        response = stub.get_methods(request)
        return response


def custom_endpoint(request: sdk_server_pb2.CustomRequest):
    """Sends grpc request to run a chosen BAPI endpoint."""
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = sdk_server_pb2_grpc.sdk_server_serviceStub(channel)
        finalResp = None
        for response in stub.custom_endpoint(request):
            finalResp = response
            yield response

        yield finalResp


def main(argv: Optional[List[str]] = None) -> Optional[int]:
    pass
