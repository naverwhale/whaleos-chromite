# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for the sdk_subtools service layer."""

import unittest

import pytest

from chromite.lib import cros_test_lib
from chromite.lib import partial_mock
from chromite.lib import sysroot_lib
from chromite.service import sdk_subtools


@unittest.mock.patch(
    "chromite.service.sdk_subtools.is_inside_subtools_chroot", return_value=True
)
def test_install_packages(_, run_mock: cros_test_lib.RunCommandMock) -> None:
    """Test that arguments are passed correctly to emerge."""
    run_mock.SetDefaultCmdResult(0)
    sdk_subtools.update_packages(["some-category/package-name"])
    cmd = run_mock.call_args_list[0][0][0]
    assert cmd[0] == "sudo"
    assert cmd[-1] == "some-category/package-name"
    run_mock.assertCommandContains(
        [f"--rebuild-exclude={' '.join(sdk_subtools.EXCLUDE_PACKAGES)}"]
    )


@unittest.mock.patch(
    "chromite.service.sdk_subtools.is_inside_subtools_chroot", return_value=True
)
def test_install_packages_failure(
    _, run_mock: cros_test_lib.RunCommandMock
) -> None:
    """Test that PackageInstallError is raised on emerge failure."""
    run_mock.AddCmdResult(
        partial_mock.InOrder(
            [
                "/mnt/host/source/chromite/bin/parallel_emerge",
                "some-category/package-name",
            ]
        ),
        returncode=42,
    )
    with pytest.raises(sysroot_lib.PackageInstallError) as error_info:
        sdk_subtools.update_packages(["some-category/package-name"])

    assert error_info.value.result.returncode == 42
