# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for SDK Server Flask App."""

from unittest import mock

import pytest
from pytest import fixture


# Tests require multiple dependencies CQ will not be able to resolve (and
# that aren't in Chromite's runtests vpython).
all_routes = []
try:
    # pylint: disable=import-error
    from chromite.contrib.sdk_server.grpc_server import client as sdk_client
    from chromite.contrib.sdk_server.grpc_server import sdk_server_pb2
    from chromite.contrib.sdk_server.grpc_server.chromite.api import image_pb2
    from chromite.contrib.sdk_server.grpc_server.chromite.api import sdk_pb2
    from chromite.contrib.sdk_server.grpc_server.chromiumos import common_pb2
    from chromite.contrib.sdk_server.ui import app as sdk_app

    # Allows parametrization of GET redirect tests for all routes.
    for route in sdk_app.app.url_map.iter_rules():
        if route.endpoint not in ["index", "static"]:
            all_routes += [route.rule]

    importsFailed = False
except ImportError:
    importsFailed = True

SKIP_REASON = "Requires Flask and gRPC server code."
parametrize = pytest.mark.parametrize


@fixture()
def app():
    """Yields clean app from main Flask file in testing mode."""

    app = sdk_app.app
    app.config.update(
        {
            "TESTING": True,
        }
    )

    yield app


@fixture()
def client(app):
    """Yields unaltered app test client for requests/responses."""

    return app.test_client()


def logGenerator(response):
    """Yields a few responses with logging info."""

    # Returns a generator of the desired response type with logging
    # info for testing endpoints which stream data.
    def gen():
        for i in range(5):
            yield response(logging_info=str(i))

    return gen()


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
def test_page_loads(client):
    """Tests basic app loading by checking for title in index head."""

    response = client.get("/")
    assert b"<title>SDK Server</title>" in response.data


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
def test_chroot_info(client):
    """Tests chroot-info parses response correctly."""

    chroot_info_response = sdk_server_pb2.ChrootInfoResponse(
        date_created="January 1, 1970",
        version=sdk_pb2.ChrootVersion(version=999),
        valid_version=True,
        path=common_pb2.Path(path="/path/to/chroot"),
    )

    chroot_info_json = {
        "dateCreated": "January 1, 1970",
        "path": {"path": "/path/to/chroot"},
        "validVersion": True,
        "version": {"version": 999},
    }

    sdk_client.chroot_info = mock.MagicMock(return_value=chroot_info_response)
    response = client.post("/chroot-info")

    sdk_client.chroot_info.assert_called_once()
    assert response.json == chroot_info_json
    assert len(response.history) == 0
    assert response.status_code == 200


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
def test_workon_start(client):
    """Tests workon-start runs properly."""

    sdk_client.cros_workon_start = mock.MagicMock()

    response = client.post(
        "/workon-start", json={"board": "board", "package": "package"}
    )

    sdk_client.cros_workon_start.assert_called_once()
    assert response.status_code == 204


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
def test_workon_stop(client):
    """Tests workon-stop runs properly."""

    sdk_client.cros_workon_stop = mock.MagicMock()

    response = client.post(
        "/workon-stop", json={"board": "board", "package": "package"}
    )

    sdk_client.cros_workon_stop.assert_called_once()
    assert response.status_code == 204


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
def test_repo_refresh(client):
    """Tests repo-refresh properly parses repo status text."""

    info_text = [
        "project chromite/                       branch sdk_frontend",
        "--	contrib/app.py",
        "-m	lib/luci/prpc/test/test.proto",
        "-m	lib/paygen/testdata/paygen.json",
    ]

    mocked_return = sdk_server_pb2.RepoStatusResponse(info=info_text)
    sdk_client.repo_status = mock.MagicMock(return_value=mocked_return)

    return_json = {
        "project": "chromite/",
        "branch": "sdk_frontend",
        "files": [
            {"file": "contrib/app.py", "head": "-", "working": "-"},
            {
                "file": "lib/luci/prpc/test/test.proto",
                "head": "-",
                "working": "m",
            },
            {
                "file": "lib/paygen/testdata/paygen.json",
                "head": "-",
                "working": "m",
            },
        ],
    }
    empty_req = sdk_server_pb2.RepoStatusRequest()
    response = client.post("/repo-refresh")

    sdk_client.repo_status.assert_called_once_with(empty_req)
    assert response.json == return_json
    assert response.status_code == 200
    assert len(response.history) == 0


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
def test_repo_sync(client):
    """Test repo sync is called and streams logs."""

    logGen = logGenerator(sdk_server_pb2.RepoSyncResponse)

    sdk_client.repo_sync = mock.MagicMock(return_value=logGen)
    empty_req = sdk_server_pb2.RepoSyncRequest()

    response = client.post("/repo-sync")

    sdk_client.repo_sync.assert_called_once_with(empty_req)
    assert response.data == b"01234"
    assert response.status_code == 200
    assert len(response.history) == 0


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
def test_get_packages_all(client):
    """Tests get-packages properly formats packages/images for all board."""

    im1 = image_pb2.Image(path="/path/to/image1", type=2)
    im2 = image_pb2.Image(path="/path/to/image2", type=6)

    board1 = common_pb2.BuildTarget(name="amd64-generic")
    board2 = common_pb2.BuildTarget(name="betty")

    bi1 = sdk_server_pb2.BoardImages(
        build_target=board1, images=[im1, im2], latest=im2
    )

    bi2 = sdk_server_pb2.BoardImages(
        build_target=board2,
    )

    cb_response = sdk_server_pb2.CurrentBoardsResponse(board_images=[bi1, bi2])

    sdk_client.current_boards = mock.MagicMock(return_value=cb_response)

    packages = sdk_server_pb2.WorkonListResponse(
        package_info=[
            common_pb2.PackageInfo(package_name="media-libs/libsync"),
            common_pb2.PackageInfo(package_name="sys-libs/lithium"),
            common_pb2.PackageInfo(package_name="chromeos-base/glib-bridge"),
        ]
    )
    sdk_client.cros_workon_list = mock.MagicMock(return_value=packages)

    info = sdk_server_pb2.WorkonInfoResponse(info="name repo1,repo2 source")
    sdk_client.cros_workon_info = mock.MagicMock(return_value=info)

    response = client.post("/get-packages", json={"board": ""})
    package_json = [
        {
            "name": "media-libs/libsync",
            "repo": ["repo1", "repo2"],
            "source": ["source"],
        },
        {
            "name": "sys-libs/lithium",
            "repo": ["repo1", "repo2"],
            "source": ["source"],
        },
        {
            "name": "chromeos-base/glib-bridge",
            "repo": ["repo1", "repo2"],
            "source": ["source"],
        },
    ]
    get_packages_json = {
        "amd64-generic": {
            "images": [
                {
                    "latest": False,
                    "path": "/path/to/image1",
                    "type": "IMAGE_TYPE_DEV",
                },
                {
                    "latest": True,
                    "path": "/path/to/image2",
                    "type": "IMAGE_TYPE_RECOVERY",
                },
            ],
            "packages": package_json,
        },
        "betty": {"images": [], "packages": package_json},
    }

    sdk_client.current_boards.assert_called_once()

    assert sdk_client.cros_workon_list.call_count == 2
    assert sdk_client.cros_workon_info.call_count == 6
    assert response.json == get_packages_json
    assert len(response.history) == 0


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
def test_get_packages_with_board(client):
    """Tests get-packages works when request contains a board argument."""

    sdk_client.current_boards = mock.MagicMock()

    packages = sdk_server_pb2.WorkonListResponse(
        package_info=[
            common_pb2.PackageInfo(package_name="media-libs/libsync"),
            common_pb2.PackageInfo(package_name="sys-libs/lithium"),
            common_pb2.PackageInfo(package_name="chromeos-base/glib-bridge"),
        ]
    )
    sdk_client.cros_workon_list = mock.MagicMock(return_value=packages)

    info = sdk_server_pb2.WorkonInfoResponse(info="name repo1,repo2 source")
    sdk_client.cros_workon_info = mock.MagicMock(return_value=info)

    response = client.post("/get-packages", json={"board": "amd64-generic"})
    package_json = [
        {
            "name": "media-libs/libsync",
            "repo": ["repo1", "repo2"],
            "source": ["source"],
        },
        {
            "name": "sys-libs/lithium",
            "repo": ["repo1", "repo2"],
            "source": ["source"],
        },
        {
            "name": "chromeos-base/glib-bridge",
            "repo": ["repo1", "repo2"],
            "source": ["source"],
        },
    ]
    get_packages_json = {
        "amd64-generic": {"images": [], "packages": package_json}
    }

    sdk_client.current_boards.assert_not_called()

    assert sdk_client.cros_workon_list.call_count == 1
    assert sdk_client.cros_workon_info.call_count == 3
    assert response.json == get_packages_json
    assert len(response.history) == 0


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
def test_update_chroot(client):
    """Tests update-chroot properly calls endpoint."""

    logGen = logGenerator(sdk_server_pb2.UpdateChrootResponse)
    req = {
        "buildSource": True,
        "toolchainChanged": True,
        "toolchainTargets": ["t1", "t2", "t3"],
    }

    sdk_client.update_chroot = mock.MagicMock(return_value=logGen)

    response = client.post("/update-chroot", json=req)

    sdk_client.update_chroot.assert_called_once()
    assert len(response.history) == 0
    assert response.data == b"01234"


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
def test_replace_chroot(client):
    """Tests replace-chroot properly calls endpoint."""

    logGen = logGenerator(sdk_server_pb2.ReplaceSdkResponse)
    req = {"bootstrap": True, "noUseImage": True, "version": "1.0.0"}

    sdk_client.replace_sdk = mock.MagicMock(return_value=logGen)

    response = client.post("/replace-chroot", json=req)

    sdk_client.replace_sdk.assert_called_once()
    assert len(response.history) == 0
    assert response.data == b"01234"


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
def test_build_packages_no_package(client):
    """Tests build-packages properly calls endpoint when given no package."""

    logGen = logGenerator(sdk_server_pb2.BuildPackagesResponse)
    req = {
        "chrootCurrent": True,
        "replace": True,
        "toolchainChanged": True,
        "CQPrebuilts": True,
        "buildTarget": "Target",
        "compileSource": True,
        "dryrun": True,
        "workon": True,
    }

    sdk_client.build_packages = mock.MagicMock(return_value=logGen)

    response = client.post("/build-packages", json=req)

    sdk_client.build_packages.assert_called_once()
    assert len(response.history) == 0
    assert response.data == b"01234"


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
def test_build_packages_with_package(client):
    """Tests build-packages properly calls endpoint when given a package."""

    logGen = logGenerator(sdk_server_pb2.BuildPackagesResponse)
    req = {
        "chrootCurrent": True,
        "replace": True,
        "toolchainChanged": True,
        "CQPrebuilts": True,
        "buildTarget": "Target",
        "compileSource": True,
        "dryrun": True,
        "workon": True,
        "package": "media-libs/libsync",
    }

    sdk_client.build_packages = mock.MagicMock(return_value=logGen)

    response = client.post("/build-packages", json=req)

    sdk_client.build_packages.assert_called_once()
    assert len(response.history) == 0
    assert response.data == b"01234"


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
def test_build_image(client):
    """Tests build-image properly calls endpoint."""

    logGen = logGenerator(sdk_server_pb2.BuildImageResponse)
    req = {
        "buildTarget": "Target",
        "imageTypes": ["IMAGE_TYPE_FACTORY", "IMAGE_TYPE_HPS_FIRMWARE"],
        "disableRootfsVerification": True,
        "version": "1.0.0",
        "diskLayout": "",
        "builderPath": "",
        "baseIsRecovery": True,
    }

    sdk_client.build_image = mock.MagicMock(return_value=logGen)

    response = client.post("/build-image", json=req)

    sdk_client.build_image.assert_called_once()
    assert len(response.history) == 0
    assert response.data == b"01234"


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
def test_custom_endpoint(client):
    """Tests custom properly calls custom endpoint."""

    logGen = logGenerator(sdk_server_pb2.CustomResponse)
    req = {
        "endpoint": "some.service/endpoint",
        "request": "proto request for endpoint",
    }

    sdk_client.custom_endpoint = mock.MagicMock(return_value=logGen)

    response = client.post("/custom", json=req)

    sdk_client.custom_endpoint.assert_called_once()
    assert len(response.history) == 0
    assert response.data == b"01234"


@pytest.mark.skipif(importsFailed, reason=SKIP_REASON)
@parametrize("route", all_routes)
def test_get_redirect(client, route):
    """Tests that all routes redirect to index on a GET request."""

    response = client.get(route, follow_redirects=True)

    assert len(response.history) == 1
    assert response.request.path == "/"
