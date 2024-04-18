# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for sdk server RPCs."""

import os
import tempfile

import pytest

from chromite.lib import constants


try:
    from chromite.contrib.sdk_server.grpc_server import sdk_server_defs_grpc
    from chromite.contrib.sdk_server.grpc_server import sdk_server_pb2
    from chromite.contrib.sdk_server.grpc_server.chromiumos import common_pb2

    _MODULE_NOT_FOUND = False
except ModuleNotFoundError:
    _MODULE_NOT_FOUND = True

_NO_CHROOT = not os.path.exists(constants.DEFAULT_CHROOT_PATH)
SKIP_REASON = "Appropriate module not imported or Chroot may not exist"
SKIP = _NO_CHROOT or _MODULE_NOT_FOUND


class PopenMock:
    def __init__(self, returncode=0):
        self.stdout = tempfile.NamedTemporaryFile(delete=False)
        self.stdout.write(b"we are testing stdout!")
        self.stdout.seek(0)

        self.stderr = tempfile.NamedTemporaryFile(delete=False)
        self.stderr.write(b"we are testing stderr!")
        self.stderr.seek(0)

        self.returncode = returncode

    def communicate(self):
        pass

    def clean_up(self):
        self.stdout.close()
        self.stderr.close()


# @pytest.mark.skipif(SKIP, reason=SKIP_REASON)
# def replace_sdk():
#     """Tests replace_sdk rpc."""
#     chroot = sdk_server_defs_grpc.SdkChroot()
#     request = sdk_server_pb2.CreateSdkRequest()
#     internal_req = sdk_pb2.CreateRequest()
#     internal_req.flags.no_replace = Falses
#     request.request.CopyFrom(internal_req)
#     for response in chroot.create_sdk(request, None):
#         assert isinstance(response, sdk_server_pb2.CreateSdkResponse)

# @pytest.mark.skipif(SKIP, reason=SKIP_REASON)
# def delete_sdk():
#     """Tests delete_sdk rpc."""
#     chroot =sdk_server_defs_grpc.SdkChroot()
#     request = sdk_server_pb2.DeleteSdkRequest()
#     internal_req = sdk_pb2.DeleteRequest()
#     request.request.CopyFrom(internal_req)
#     for response in chroot.delete_sdk(request, None):
#         assert isinstance(response, sdk_server_pb2.CreateSdkResponse)

# @pytest.mark.skipif(SKIP, reason=SKIP_REASON)
# def test_create_sdk():
#     """Tests create_sdk rpc."""
#     chroot =sdk_server_defs_grpc.SdkChroot()
#     request = sdk_server_pb2.CreateSdkRequest()
#     internal_req = sdk_pb2.CreateRequest()
#     internal_req.flags.no_replace = True
#     request.request.CopyFrom(internal_req)
#     for response in chroot.create_sdk(request, None):
#         assert isinstance(response, sdk_server_pb2.CreateSdkResponse)

# @pytest.mark.skipif(SKIP, reason=SKIP_REASON)
# def test_build_packages():
#     """Tests build_packages rpc."""
#     chroot =sdk_server_defs_grpc.SdkChroot()
#     request = sdk_server_pb2.BuildPackagesRequest()

#     create_internal_req = sysroot_pb2.SysrootCreateRequest()
#     request.create_req.CopyFrom(create_internal_req)

#     toolchain_internal_req = sysroot_pb2.InstallToolchainRequest()
#     request.toolchain_req.CopyFrom(toolchain_internal_req)

#     packages_internal_req = sysroot_pb2.InstallPackagesRequest()
#     request.packages_req.CopyFrom(packages_internal_req)

#     for response in chroot.build_packages(request, None):
#         assert isinstance(response, sdk_server_pb2.BuildPackagesResponse)

# @pytest.mark.skipif(SKIP, reason=SKIP_REASON)
# def test_build_image():
#     """Tests build_image rpc."""
#     chroot =sdk_server_defs_grpc.SdkChroot()
#     request = sdk_server_pb2.BuildImageRequest()
#     internal_req = image_pb2.CreateImageRequest()
#     request.request.CopyFrom(internal_req)

#     for response in chroot.build_image(request, None):
#         assert isinstance(response, sdk_server_pb2.BuildImageResponse)


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
def test_workon_info():
    """Tests cros_workon_info rpc."""
    chroot = sdk_server_defs_grpc.SdkChroot()
    target = common_pb2.BuildTarget(name="amd64-generic")
    target_package = common_pb2.PackageInfo(
        package_name="x11-themes/cros-adapta"
    )
    request = sdk_server_pb2.WorkonInfoRequest(
        package_info=target_package, build_target=target
    )

    response = chroot.cros_workon_info(request, None)
    assert isinstance(response, sdk_server_pb2.WorkonInfoResponse)


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
def test_workon_list():
    """Tests cros_workon_list rpc."""
    chroot = sdk_server_defs_grpc.SdkChroot()
    target = common_pb2.BuildTarget(name="amd64-generic")
    request = sdk_server_pb2.WorkonListRequest(build_target=target)
    response = chroot.cros_workon_list(request, None)
    assert isinstance(response, sdk_server_pb2.WorkonListResponse)


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
def test_workon_start():
    """Tests cros_workon_start rpc."""
    chroot = sdk_server_defs_grpc.SdkChroot()
    target = common_pb2.BuildTarget(name="amd64-generic")
    target_package = common_pb2.PackageInfo(
        package_name="x11-themes/cros-adapta"
    )
    request = sdk_server_pb2.WorkonStartRequest(
        package_info=target_package, build_target=target
    )
    response = chroot.cros_workon_start(request, None)
    assert isinstance(response, sdk_server_pb2.WorkonStartResponse)


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
def test_workon_stop():
    """Tests cros_workon_stop rpc."""
    chroot = sdk_server_defs_grpc.SdkChroot()
    target = common_pb2.BuildTarget(name="amd64-generic")
    target_package = common_pb2.PackageInfo(
        package_name="x11-themes/cros-adapta"
    )
    request = sdk_server_pb2.WorkonStopRequest(
        package_info=target_package, build_target=target
    )
    response = chroot.cros_workon_stop(request, None)
    assert isinstance(response, sdk_server_pb2.WorkonStopResponse)


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
def test_chroot_info():
    """Tests chroot info rpc."""
    chroot = sdk_server_defs_grpc.SdkChroot()
    request = sdk_server_pb2.ChrootInfoRequest()
    response = chroot.chroot_info(request, None)
    assert isinstance(response, sdk_server_pb2.ChrootInfoResponse)


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
def test_all_packages():
    """Tests all_packages rpc."""
    chroot = sdk_server_defs_grpc.SdkChroot()
    target = common_pb2.BuildTarget(name="amd64-generic")
    request = sdk_server_pb2.AllPackagesRequest(build_target=target)
    response = chroot.all_packages(request, None)
    assert isinstance(response, sdk_server_pb2.AllPackagesResponse)


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
def test_repo_status():
    """Tests repo_status rpc."""
    chroot = sdk_server_defs_grpc.SdkChroot()
    request = sdk_server_pb2.RepoStatusRequest()
    response = chroot.repo_status(request, None)
    assert isinstance(response, sdk_server_pb2.RepoStatusResponse)


# @pytest.mark.skipif(SKIP, reason=SKIP_REASON)
# def test_repo_sync():
#     """Tests repo_sync rpc."""
#     chroot =sdk_server_defs_grpc.SdkChroot()
#     request = sdk_server_pb2.RepoSyncRequest()
#     for response in chroot.repo_sync(request, None):
#         assert isinstance(response, sdk_server_pb2.RepoSyncResponse)


# @mock.patch('sdk_server_defs_grpc.AsyncRun')
# @mock.patch("subprocess.Popen")
@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
def test_update_chroot(monkeypatch):
    """Tests update_chroot rpc."""
    chroot = sdk_server_defs_grpc.SdkChroot()
    monkeypatch.setattr(
        chroot, "_run_endpoint", lambda *args, **kwargs: PopenMock()
    )
    # func.return_value = mock.MagicMock(return_value=PopenMock())
    # subprocess.Popen = mock.MagicMock(return_value=subprocess.Popen(["echo", "hello"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT))
    # func.return_value = subprocess.Popen(["echo", "hello"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # func.return_value = PopenMock()

    request = sdk_server_pb2.UpdateChrootRequest()
    for response in chroot.update_chroot(request, None):
        assert isinstance(response, sdk_server_pb2.UpdateChrootResponse)

    # TODO: add another case where PopenMock.returncode != 0


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
def test_query_boards():
    """Tests query_boards rpc."""
    chroot = sdk_server_defs_grpc.SdkChroot()
    request = sdk_server_pb2.QueryBoardsRequest()
    response = chroot.query_boards(request, None)
    assert isinstance(response, sdk_server_pb2.QueryBoardsResponse)


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
def test_current_boards():
    """Tests current_boards rpc."""
    chroot = sdk_server_defs_grpc.SdkChroot()
    request = sdk_server_pb2.CurrentBoardsRequest()
    response = chroot.current_boards(request, None)
    assert isinstance(response, sdk_server_pb2.CurrentBoardsResponse)
