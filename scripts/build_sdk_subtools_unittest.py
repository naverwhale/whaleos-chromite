# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for build_sdk_subtools."""

from pathlib import Path
from unittest import mock

import pytest

from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.scripts import build_sdk_subtools
from chromite.service import sdk_subtools


# The argument passed to cros_sdk to ensure the correct SDK is being used.
SDK_CHROOT_ARG = Path("/mnt/host/source/out/build/amd64-subtools-host")


@pytest.fixture(name="outside_chroot")
def outside_chroot_fixture():
    """Mocks IsInsideChroot to be False."""
    with mock.patch.object(
        cros_build_lib, "IsInsideChroot", return_value=False
    ) as outside_chroot:
        yield outside_chroot


@pytest.fixture(name="mock_emerge")
def mock_emerge_fixture():
    """Stubs the build_sdk_subtools emerge helper and sets it up to run."""
    with mock.patch.multiple(
        "chromite.service.sdk_subtools",
        _run_system_emerge=mock.DEFAULT,
        is_inside_subtools_chroot=mock.DEFAULT,
    ) as mocks:
        mocks["is_inside_subtools_chroot"].return_value = True
        yield mocks["_run_system_emerge"]


@pytest.fixture(name="mock_exporter", autouse=True)
def mock_exporter_fixture():
    """Stubs the exporter for InstalledSubtools to avoid side-effects."""
    with mock.patch(
        "chromite.lib.subtool_lib.InstalledSubtools"
    ) as installed, mock.patch(
        "chromite.lib.subtool_lib.BundledSubtools"
    ) as bundled:
        yield {"installed": installed, "bundled": bundled}


@pytest.fixture(autouse=True)
def build_sdk_subtools_consistency_check():
    """Die quickly if the version file is left over in the test SDK.

    This can happen if the build API entrypoint was tested on the local machine.
    Tests in this file will fail in confusing ways if this is ever the case.
    """
    version_file = sdk_subtools.SUBTOOLS_CHROOT_VERSION_FILE
    assert (
        not version_file.exists()
    ), f"{version_file} exists in the chroot (stray?)."


def test_must_run_outside_sdk(caplog) -> None:
    """Tests build_sdk_subtools complains if run in the chroot."""
    with pytest.raises(cros_build_lib.DieSystemExit) as error_info:
        build_sdk_subtools.main()
    assert error_info.value.code == 1
    assert "build_sdk_subtools must be run outside the chroot" in caplog.text


def test_cros_sdk(run_mock, outside_chroot) -> None:
    """Tests the steps leading up to the cros_sdk invocation."""
    # Fake a failure from cros_sdk to ensure it propagates.
    run_mock.SetDefaultCmdResult(returncode=42)

    assert build_sdk_subtools.main() == 42
    assert outside_chroot.called
    assert run_mock.call_count == 1
    assert run_mock.call_args_list[0].args[0] == [
        "cros_sdk",
        "--chroot",
        SDK_CHROOT_ARG,
        "--create",
        "--skip-chroot-upgrade",
    ]


def test_cros_sdk_clean(run_mock, outside_chroot) -> None:
    """Tests steps leading up to the cros_sdk invocation with --clean."""
    run_mock.SetDefaultCmdResult(returncode=42)

    assert build_sdk_subtools.main(["--clean"]) == 42
    assert outside_chroot.called
    assert run_mock.call_count == 1
    cros_sdk_cmd = run_mock.call_args_list[0].args[0]
    assert cros_sdk_cmd[0] == "cros_sdk"
    assert "--delete" in cros_sdk_cmd


def test_cros_sdk_output_dir(run_mock, outside_chroot) -> None:
    """Tests steps leading up to the cros_sdk invocation with --output-dir."""
    run_mock.SetDefaultCmdResult(returncode=42)

    assert build_sdk_subtools.main(["--output-dir", "/foo"]) == 42
    assert outside_chroot.called
    cros_sdk_cmd = run_mock.call_args_list[0].args[0]
    chroot_arg_index = cros_sdk_cmd.index(Path("/mnt/host/source/out/foo"))
    assert cros_sdk_cmd[0] == "cros_sdk"
    assert cros_sdk_cmd[chroot_arg_index - 1] == "--chroot"


def test_chroot_required_after_cros_sdk(run_mock, outside_chroot) -> None:
    """Tests that build_sdk_subtools will ask for chroot when setup."""
    with pytest.raises(commandline.ChrootRequiredError) as error_info:
        build_sdk_subtools.main(["--no-setup-chroot"])

    assert run_mock.call_count == 0
    assert outside_chroot.called
    assert error_info.value.cmd == ["build_sdk_subtools", "--no-setup-chroot"]
    assert error_info.value.chroot_args == [
        "--chroot",
        SDK_CHROOT_ARG,
    ]


def test_chroots_into_output_dir(run_mock, outside_chroot) -> None:
    """Tests that --output-dir is consumed properly after setup."""
    with pytest.raises(commandline.ChrootRequiredError) as error_info:
        build_sdk_subtools.main(["--no-setup-chroot", "--output-dir", "/foo"])

    assert run_mock.call_count == 0
    assert outside_chroot.called
    assert error_info.value.chroot_args == [
        "--chroot",
        Path("/mnt/host/source/out/foo"),
    ]


def test_setup_sdk_invocation(run_mock, outside_chroot) -> None:
    """Tests the SDK setup invocation, before it becomes a subtools chroot."""
    # Fake success from cros_sdk, failure from setup_base_sdk().
    run_mock.SetDefaultCmdResult(returncode=0)
    run_mock.AddCmdResult(
        ["sudo", "--", "build_sdk_subtools", "--relaunch-for-setup"],
        returncode=42,
    )

    assert build_sdk_subtools.main() == 42
    assert run_mock.call_count == 2
    assert outside_chroot.called

    sudo_run_cmd = run_mock.call_args_list[1]

    assert sudo_run_cmd.args[0] == [
        "sudo",
        "--",
        "build_sdk_subtools",
        "--relaunch-for-setup",
    ]
    assert sudo_run_cmd.kwargs["enter_chroot"] is True
    assert sudo_run_cmd.kwargs["chroot_args"] == [
        "--chroot",
        SDK_CHROOT_ARG,
    ]
    # Stop here: Actually running `--relaunch-for-setup` principally wants to
    # mutate the SDK state as root, which is too messy as a unit test.


def test_default_package(mock_emerge) -> None:
    """Tests a default virtual package is provided to update packages."""
    assert build_sdk_subtools.main() == 0
    assert mock_emerge.call_count == 1
    emerge_cmd = mock_emerge.call_args.args[0]
    assert Path("/mnt/host/source/chromite/bin/parallel_emerge") in emerge_cmd
    assert emerge_cmd[-1] == "virtual/target-sdk-subtools"


def test_provided_package(mock_emerge) -> None:
    """Tests the default package can be passed in from command line."""
    assert build_sdk_subtools.main(["vim"]) == 0
    assert mock_emerge.call_args.args[0][-1] == "vim"


def test_skip_package_update(mock_emerge) -> None:
    """Tests --skip-package-update will not try to emerge anything."""
    assert build_sdk_subtools.main(["--no-update-packages"]) == 0
    assert mock_emerge.call_count == 0


def test_invokes_uploader(mock_emerge, mock_exporter) -> None:
    """The exporter is invoked to bundle, but to upload [] by default."""
    assert build_sdk_subtools.main([]) == 0
    assert mock_emerge.call_count == 1
    assert mock_exporter["installed"].called
    installed_subtools = mock_exporter["installed"].return_value
    assert installed_subtools.bundle_all.called
    installed_subtools.prepare_uploads.assert_called_once_with([])


def test_upload_option(mock_emerge, mock_exporter) -> None:
    """Tests that the exporter is invoked with provided uploads."""
    cmdline = ["--upload", "subtool1", "subtool2", "--", "dev-some/package"]
    assert build_sdk_subtools.main(cmdline) == 0
    assert mock_emerge.call_args.args[0][-1] == "dev-some/package"
    installed_subtools = mock_exporter["installed"].return_value
    installed_subtools.prepare_uploads.assert_called_once_with(
        ["subtool1", "subtool2"]
    )


def test_production_option(mock_emerge, mock_exporter) -> None:
    """Tests that --production is passed to the uploader."""
    assert build_sdk_subtools.main(["--production"]) == 0
    assert mock_emerge.call_count == 1
    mock_exporter["bundled"].return_value.upload.assert_called_once_with(True)
