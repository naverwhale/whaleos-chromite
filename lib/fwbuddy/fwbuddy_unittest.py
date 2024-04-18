# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for fwbuddy.py."""

# This is to prevent pylint from complaining about us including, but not
# using the `setup` fixture.
# pylint: disable=unused-argument


import builtins

import pytest

from chromite.lib import cros_test_lib
from chromite.lib import gs
from chromite.lib.fwbuddy import fwbuddy


GENERIC_VALID_URI = (
    "fwbuddy://dedede/galnat360/galtic/R99-123.456.0/signed/serial"
)


@pytest.fixture(name="setup")
def fixture_setup(monkeypatch):
    monkeypatch.setattr(gs.GSContext, "LS", lambda *_,: ["some/path"])
    monkeypatch.setattr(gs.GSContext, "Copy", lambda *_,: None)
    monkeypatch.setattr(gs.GSContext, "CheckPathAccess", lambda *_,: None)
    monkeypatch.setattr(fwbuddy.FwBuddy, "setup", lambda *_,: None)
    monkeypatch.setattr(fwbuddy.FwBuddy, "cleanup", lambda *_,: None)


def test_usage_string(setup):
    """Test that all of the URI fields are include in the usage doc."""
    for field in fwbuddy.FIELD_DOCS:
        assert field in fwbuddy.USAGE


def test_parse_uri(setup):
    """Tests that we can properly convert a uri string into a URI object"""
    assert fwbuddy.parse_uri(GENERIC_VALID_URI) == fwbuddy.URI(
        board="dedede",
        model="galnat360",
        firmware_name="galtic",
        version="R99-123.456.0",
        image_type="signed",
        firmware_type="serial",
    )

    assert fwbuddy.parse_uri(
        "fwbuddy://dedede/galnat360/galtic/R99-123.456.0/signed"
    ) == fwbuddy.URI(
        board="dedede",
        model="galnat360",
        firmware_name="galtic",
        version="R99-123.456.0",
        image_type="signed",
        firmware_type=None,
    )

    # Missing image_type
    with pytest.raises(fwbuddy.FwBuddyException):
        fwbuddy.parse_uri("fwbuddy://dedede/galtic/R99-123.456.0")

    # Wrong header
    with pytest.raises(fwbuddy.FwBuddyException):
        fwbuddy.parse_uri(
            "fwbozo://dedede/galnat360/galtic/R99-123.456.0/unsigned"
        )


def test_parse_release_string(setup):
    """Tests that versions can be parsed into Release Objects"""
    assert fwbuddy.Release(
        "99", "123", "456", "0"
    ) == fwbuddy.parse_release_string("R99-123.456.0")

    assert fwbuddy.Release(
        "99", "123", "456", "0"
    ) == fwbuddy.parse_release_string("r99-123.456.0")

    assert fwbuddy.Release(
        "*", "123", "456", "0"
    ) == fwbuddy.parse_release_string("R*-123.456.0")

    with pytest.raises(fwbuddy.FwBuddyException):
        fwbuddy.parse_release_string("99-123.456.0")
    with pytest.raises(fwbuddy.FwBuddyException):
        fwbuddy.parse_release_string("R99-123.456")


def test_generate_unsigned_gspaths(setup):
    """Tests that we can generate unsigned gspaths using our schemas."""

    fw_image = fwbuddy.FwImage(
        board="dedede",
        model="",
        firmware_name="galtic",
        release=fwbuddy.parse_release_string("R89-13606.459.0"),
        branch="firmware-dedede-13606.B",
        image_type="unsigned",
        firmware_type="",
    )

    expected_gspaths = [
        (
            "gs://chromeos-image-archive/firmware-dedede-13606.B-branch-"
            "firmware/R89-13606.459.0/firmware_from_source.tar.bz2"
        ),
        (
            "gs://chromeos-image-archive/firmware-dedede-13606.B-branch-"
            "firmware/R89-13606.459.0/dedede/firmware_from_source.tar.bz2"
        ),
        (
            "gs://chromeos-image-archive/dedede-firmware/R89-13606.459.0/"
            "firmware_from_source.tar.bz2"
        ),
        (
            "gs://chromeos-image-archive/firmware-dedede-13606.B-branch-"
            "firmware/R89-13606.459.0/firmware_from_source.tar.bz2"
        ),
        (
            "gs://chromeos-image-archive/firmware-dedede-13606.B-branch-"
            "firmware/R89-13606.459.0/dedede/firmware_from_source.tar.bz2"
        ),
    ]

    # This could be neater if https://github.com/pytest-dev/pytest/issues/10032
    # is fixed.
    result = fwbuddy.generate_gspaths(fw_image)
    result.sort()
    expected_gspaths.sort()

    assert result == expected_gspaths


def test_lookup_branch(setup, run_mock):
    """Tests that we correctly parse the SQL output from the branch lookup"""
    csv = "branch_name\nfirmware-icarus-12574.B\n"
    run_mock.SetDefaultCmdResult(stdout=csv)
    f = fwbuddy.FwBuddy(GENERIC_VALID_URI)
    assert f.lookup_branch() == "firmware-icarus-12574.B"


def test_lookup_branch_fails(setup, run_mock):
    """Tests that we return None when our dremel command fails to run"""
    run_mock.SetDefaultCmdResult(returncode=1)
    f = fwbuddy.FwBuddy(GENERIC_VALID_URI)
    assert f.lookup_branch() is None


def test_generate_signed_gspaths(setup):
    """Tests that we can generate signed gspaths using our schemas."""
    fw_image = fwbuddy.FwImage(
        board="dedede",
        model="",
        firmware_name="galtic",
        release=fwbuddy.parse_release_string("R89-13606.459.0"),
        branch="",
        image_type="signed",
        firmware_type="",
    )

    expected_gspaths = [
        "gs://chromeos-releases/canary-channel/dedede/13606.459.0/ChromeOS-"
        "firmware-R89-13606.459.0-dedede.tar.bz2"
    ]

    assert fwbuddy.generate_gspaths(fw_image) == expected_gspaths


def test_determine_gspath(setup, monkeypatch):
    f = fwbuddy.FwBuddy(GENERIC_VALID_URI)
    assert f.determine_gspath() == "some/path"

    monkeypatch.setattr(fwbuddy, "generate_gspaths", lambda *_,: [])
    with pytest.raises(fwbuddy.FwBuddyException):
        f.determine_gspath()


def test_download(setup):
    f = fwbuddy.FwBuddy(GENERIC_VALID_URI)
    f.download()
    assert f.archive_path == f"{fwbuddy.TMP_STORAGE_FOLDER}/path"


def test_extract(setup, run_mock: cros_test_lib.RunCommandMock):
    run_mock.SetDefaultCmdResult(0)
    # Ap image path extraction with firmware_type
    f = fwbuddy.FwBuddy(GENERIC_VALID_URI)
    f.archive_path = "/unused"
    f.extract("tmp")
    assert f.ap_path == "tmp/image-galtic.serial.bin"

    # AP and EC image path extraction
    f = fwbuddy.FwBuddy(
        "fwbuddy://dedede/galnat360/galtic/R99-123.456.0/signed"
    )
    f.archive_path = "/unused"
    f.extract("tmp")
    assert f.ap_path == "tmp/image-galtic.bin"
    assert f.ec_path == "tmp/galtic/ec.bin"

    # Some error while extracting archive contents.
    run_mock.SetDefaultCmdResult(1, stderr="some error")
    with pytest.raises(fwbuddy.FwBuddyException):
        f.extract()


def test_export_firmware_image(setup, run_mock: cros_test_lib.RunCommandMock):
    run_mock.SetDefaultCmdResult(0)
    f = fwbuddy.FwBuddy(GENERIC_VALID_URI)
    f.archive_path = "/unused"
    # Unsupported chip
    f.extract("tmp")
    with pytest.raises(fwbuddy.FwBuddyException):
        f.export_firmware_image("tmp", "JUNK_CHIP")

    # Export without extraction
    f.ec_path = None
    with pytest.raises(fwbuddy.FwBuddyException):
        f.export_firmware_image("tmp", "EC")

    # Some failure while exporting
    f.extract("tmp")
    run_mock.SetDefaultCmdResult(1)
    with pytest.raises(fwbuddy.FwBuddyException):
        f.export_firmware_image("tmp", "EC")


def test_parse_chip(setup):
    assert "ec" == fwbuddy.parse_chip("EC")
    assert "ap" == fwbuddy.parse_chip("ap")
    assert None is fwbuddy.parse_chip(None)

    with pytest.raises(fwbuddy.FwBuddyException):
        fwbuddy.parse_chip("junk")


def test_parse_firmware_type(setup):
    assert "serial" == fwbuddy.parse_firmware_type("SERIAL")
    assert None is fwbuddy.parse_firmware_type(None)
    with pytest.raises(fwbuddy.FwBuddyException):
        fwbuddy.parse_firmware_type("junk")


def test_get_uri_interactive(setup, monkeypatch):
    """Test that we can build an fwbuddy URI from an interactive prompt."""
    num = 0

    def increment_num():
        nonlocal num
        num += 1
        return num

    monkeypatch.setattr(
        builtins, "input", lambda *args, **kwargs: f"{increment_num()}"
    )

    assert fwbuddy.get_uri_interactive() == "fwbuddy://1/2/3/4/5/6/"


def test_interactive_mode(setup, monkeypatch):
    """Test that we can trigger interactive mode"""
    mock_input = GENERIC_VALID_URI
    monkeypatch.setattr(
        fwbuddy,
        "get_uri_interactive",
        lambda *args, **kwargs: f"{mock_input}",
    )
    f = fwbuddy.FwBuddy("fwbuddy://")
    assert f.fw_image.board == "dedede"
