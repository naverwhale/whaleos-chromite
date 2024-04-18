# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for cros_generate_dlc_artifacts."""

from unittest import mock

import pytest

from chromite.lib import dlc_lib
from chromite.scripts import cros_generate_dlc_artifacts


@pytest.mark.parametrize("dry_run", ((False), (True)))
def test_upload_dlc_artifacts(dry_run):
    """Tests out UploadDlcArtifacts with dry_run option"""
    artifact_mock = mock.Mock()
    cros_generate_dlc_artifacts.UploadDlcArtifacts(
        artifact_mock, dry_run=dry_run
    )
    artifact_mock.Upload.assert_called_with(dry_run=dry_run)


@pytest.mark.parametrize("dlc_id", ("some-dlc-id",))
@pytest.mark.parametrize("preallocated_blocks", (123,))
@pytest.mark.parametrize("name", ((""), ("<some-name>")))
@pytest.mark.parametrize("description", ((""), ("<some-description>")))
@pytest.mark.parametrize("version", ("<some-version>",))
@pytest.mark.parametrize("powerwash_safety", (True, False))
@mock.patch.object(dlc_lib, "EbuildParams")
def test_generate_dlc_params(
    mock_ebuild_params,
    dlc_id,
    preallocated_blocks,
    name,
    description,
    version,
    powerwash_safety,
    tmp_path,
):
    """Tests out GenerateDlcParams"""
    tmpfile = tmp_path / "license"
    tmpfile.touch()
    argv = [
        "--src-dir",
        ".",
        "--license",
        str(tmpfile),
        *(["--id", f"{dlc_id}"] if dlc_id else []),
        *(
            ["--preallocated-blocks", f"{preallocated_blocks}"]
            if preallocated_blocks
            else []
        ),
        *(["--name", f"{name}"] if name else []),
        *(["--description", f"{description}"] if description else []),
        *(["--version", f"{version}"] if version else []),
        "--powerwash-safety" if powerwash_safety else "--no-powerwash-safety",
    ]
    opts = cros_generate_dlc_artifacts.ParseArguments(argv)
    cros_generate_dlc_artifacts.GenerateDlcParams(opts)
    mock_ebuild_params.assert_called_with(
        dlc_id=dlc_id,
        dlc_package="package",
        fs_type=dlc_lib.SQUASHFS_TYPE,
        pre_allocated_blocks=preallocated_blocks,
        version=version,
        name=name,
        description=description,
        preload=False,
        used_by="",
        mount_file_required=False,
        fullnamerev="",
        scaled=True,
        loadpin_verity_digest=False,
        powerwash_safe=powerwash_safety,
        use_logical_volume=True,
    )
