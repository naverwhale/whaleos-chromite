# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for the sdk_subtools api layer."""

import os
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Union
from unittest import mock

import pytest

from chromite.api import api_config
from chromite.api.controller import sdk_subtools
from chromite.api.gen.chromite.api import sdk_subtools_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import cros_build_lib
from chromite.lib import sysroot_lib
from chromite.lib.parser import package_info


def make_request(
    chroot_path: Union[str, os.PathLike, None] = "fake_chroot_path"
) -> sdk_subtools_pb2.BuildSdkSubtoolsRequest:
    """Helper to build a build request message."""
    request = sdk_subtools_pb2.BuildSdkSubtoolsRequest()
    if chroot_path is not None:
        request.chroot.path = os.fspath(chroot_path)
    return request


def build_sdk_subtools(
    request: sdk_subtools_pb2.BuildSdkSubtoolsRequest,
    call_type: Optional[int] = api_config.ApiConfig.CALL_TYPE_EXECUTE,
) -> sdk_subtools_pb2.BuildSdkSubtoolsResponse:
    """Invokes sdk_subtools.BuildSdkSubtools and returns the response proto."""
    config = api_config.ApiConfig(call_type)
    response = sdk_subtools_pb2.BuildSdkSubtoolsResponse()
    sdk_subtools.BuildSdkSubtools(request, response, config)
    return response


def make_upload_request(
    bundle_paths: Optional[List[str]] = None,
) -> sdk_subtools_pb2.UploadSdkSubtoolsRequest:
    """Helper to build an upload request message."""
    request = sdk_subtools_pb2.UploadSdkSubtoolsRequest()
    if bundle_paths is None:
        bundle_paths = ["/path/to/bundle"]
    request.bundle_paths.extend(
        common_pb2.Path(path=p, location=common_pb2.Path.OUTSIDE)
        for p in bundle_paths
    )
    return request


def upload_sdk_subtools(
    request: sdk_subtools_pb2.UploadSdkSubtoolsRequest,
    call_type: Optional[int] = api_config.ApiConfig.CALL_TYPE_EXECUTE,
) -> sdk_subtools_pb2.UploadSdkSubtoolsResponse:
    """Invokes sdk_subtools.UploadSdkSubtools and returns the response proto."""
    config = api_config.ApiConfig(call_type)
    response = sdk_subtools_pb2.UploadSdkSubtoolsResponse()
    sdk_subtools.UploadSdkSubtools(request, response, config)
    return response


MockService = Dict[str, mock.MagicMock]


@pytest.fixture(name="mock_service")
def mock_service_fixture() -> Iterator[MockService]:
    """Mocks the sdk_subtools service layer with mocks."""
    with mock.patch.multiple(
        "chromite.service.sdk_subtools",
        setup_base_sdk=mock.DEFAULT,
        update_packages=mock.DEFAULT,
        bundle_and_prepare_upload=mock.DEFAULT,
        upload_prepared_bundles=mock.DEFAULT,
    ) as dict_of_mocks:
        # Default to a "successful" return with an empty list of bundle paths.
        dict_of_mocks["bundle_and_prepare_upload"].return_value = ([], None)
        yield dict_of_mocks


def test_build_validate_only(mock_service: MockService) -> None:
    """Verify a validate-only call does not execute any logic."""
    build_sdk_subtools(
        make_request(), api_config.ApiConfig.CALL_TYPE_VALIDATE_ONLY
    )
    for f in mock_service.values():
        f.assert_not_called()


def test_build_mock_call(mock_service: MockService) -> None:
    """Consistency check that a mock call does not execute any logic."""
    build_sdk_subtools(
        make_request(), api_config.ApiConfig.CALL_TYPE_MOCK_SUCCESS
    )
    for f in mock_service.values():
        f.assert_not_called()


def test_build_success_no_bundles(mock_service: MockService) -> None:
    """Test a successful call with zero bundles available."""
    response = build_sdk_subtools(make_request())
    mock_service["setup_base_sdk"].assert_called_once()
    mock_service["update_packages"].assert_called_once()
    mock_service["bundle_and_prepare_upload"].assert_called_once()
    assert not response.failed_package_data


def test_build_success_two_bundles(mock_service: MockService) -> None:
    """Test a successful call with two bundles available."""
    bundles = [
        Path("/var/tmp/cros-subtools/shellcheck"),
        Path("/var/tmp/cros-subtools/rustfmt"),
    ]
    mock_service["bundle_and_prepare_upload"].return_value = (bundles, None)
    response = build_sdk_subtools(make_request())
    assert [(p.path, p.location) for p in response.bundle_paths] == [
        ("/var/tmp/cros-subtools/shellcheck", common_pb2.Path.INSIDE),
        ("/var/tmp/cros-subtools/rustfmt", common_pb2.Path.INSIDE),
    ]


def test_package_update_failure(mock_service: MockService) -> None:
    """Test output handling when package update fails."""
    mock_service[
        "update_packages"
    ].side_effect = sysroot_lib.PackageInstallError(
        "mock failure",
        cros_build_lib.CompletedProcess(),
        packages=[package_info.parse("some-category/some-package-0.42-r43")],
    )
    response = build_sdk_subtools(make_request())
    mock_service["setup_base_sdk"].assert_called_once()
    mock_service["update_packages"].assert_called_once()
    mock_service["bundle_and_prepare_upload"].assert_not_called()
    assert len(response.failed_package_data) == 1
    assert response.failed_package_data[0].name.package_name == "some-package"
    assert response.failed_package_data[0].name.category == "some-category"
    assert response.failed_package_data[0].name.version == "0.42-r43"


def test_upload_validate_only(mock_service: MockService) -> None:
    """Verify a validate-only call does not execute any logic."""
    upload_sdk_subtools(
        make_upload_request(), api_config.ApiConfig.CALL_TYPE_VALIDATE_ONLY
    )
    for f in mock_service.values():
        f.assert_not_called()


def test_upload_mock_call(mock_service: MockService) -> None:
    """Consistency check that a mock call does not execute any logic."""
    upload_sdk_subtools(
        make_upload_request(), api_config.ApiConfig.CALL_TYPE_MOCK_SUCCESS
    )
    for f in mock_service.values():
        f.assert_not_called()


def test_upload_success(mock_service: MockService) -> None:
    """Test a successful call to upload."""
    upload_sdk_subtools(make_upload_request())
    mock_service["upload_prepared_bundles"].assert_called_once_with(
        False, [Path("/path/to/bundle")]
    )


def test_upload_to_production(mock_service: MockService) -> None:
    """Test a successful call to upload with use_production set."""
    request = make_upload_request()
    request.use_production = True
    upload_sdk_subtools(request)
    mock_service["upload_prepared_bundles"].assert_called_once_with(
        True, [Path("/path/to/bundle")]
    )
