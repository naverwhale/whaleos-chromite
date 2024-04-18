# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the cros_losetup module."""

import json
from pathlib import Path

import pytest

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import image_lib
from chromite.lib import osutils
from chromite.scripts import cros_losetup


@pytest.fixture(autouse=True)
def is_root_fixture(monkeypatch):
    """We don't want the code re-execing itself using sudo."""
    monkeypatch.setattr(osutils, "IsRootUser", lambda: True)


@pytest.fixture(autouse=True)
def stub_image_lib(monkeypatch):
    """Make sure these APIs aren't used by default."""

    def fail(path):
        raise RuntimeError("test is missing a mock")

    monkeypatch.setattr(image_lib.LoopbackPartitions, "detach_loopback", fail)
    monkeypatch.setattr(image_lib.LoopbackPartitions, "attach_image", fail)


@pytest.fixture(autouse=True)
def path_write_text_fixture(monkeypatch):
    """Make sure we dont write the udev rule during test."""
    monkeypatch.setattr(cros_build_lib, "IsInsideChroot", lambda: True)


def test_parser():
    """Basic tests for the parser interface."""
    parser = cros_losetup.get_parser()

    # Missing subcommand.
    with pytest.raises(SystemExit):
        parser.parse_args([])

    # Unknown subcommand.
    with pytest.raises(SystemExit):
        parser.parse_args(["asdfadsf"])

    # Missing path.
    with pytest.raises(SystemExit):
        parser.parse_args(["attach"])
    with pytest.raises(SystemExit):
        parser.parse_args(["detach"])

    # Valid commands.
    parser.parse_args(["attach", "disk.bin"])
    parser.parse_args(["detach", "/dev/loop0"])


def test_attach(monkeypatch, capsys):
    """Verify attaching runs lower APIs."""
    monkeypatch.setattr(
        image_lib.LoopbackPartitions, "attach_image", lambda x: "/dev/loop0"
    )
    assert cros_losetup.main(["attach", "disk.bin"]) == 0

    # Stdout should be JSON.
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "path" in data
    assert data["path"] == "/dev/loop0"


def test_detach_success(monkeypatch):
    """Verify detaching runs lower APIs."""
    monkeypatch.setattr(
        image_lib.LoopbackPartitions, "detach_loopback", lambda x: True
    )
    assert cros_losetup.main(["detach", "/dev/loop0"]) == 0


def test_detach_failure(monkeypatch):
    """Verify detaching runs lower APIs."""
    monkeypatch.setattr(
        image_lib.LoopbackPartitions, "detach_loopback", lambda x: False
    )
    assert cros_losetup.main(["detach", "/dev/loop0"]) == 1


def test_create_udev_rule(monkeypatch):
    """Test if the udev rule is created with the chromite source directory."""
    with osutils.TempDir() as tempdir:
        _cros_losetup_tmpfile = Path(tempdir) / "udev.rules"
        monkeypatch.setattr(
            cros_losetup, "_UDEV_RULE_FILE", _cros_losetup_tmpfile
        )
        with cros_test_lib.RunCommandMock() as rc:
            rc.SetDefaultCmdResult()
            # Test when we are inside chroot.
            # pylint: disable-msg=protected-access
            cros_losetup._create_udev_loopdev_ignore_rule()
            assert not _cros_losetup_tmpfile.exists()

            # Test when we are outside chroot.
            monkeypatch.setattr(cros_build_lib, "IsInsideChroot", lambda: False)
            cros_losetup._create_udev_loopdev_ignore_rule()
            assert _cros_losetup_tmpfile.read_text(encoding="utf-8") == (
                cros_losetup._UDEV_RULE_TEMPLATE % constants.SOURCE_ROOT
            )
            rc.assertCommandContains(["udevadm", "control", "--reload-rules"])

            # Test when the file already exists, we dont call udev reload-rules.
            call_count = rc.call_count
            cros_losetup._create_udev_loopdev_ignore_rule()
            assert _cros_losetup_tmpfile.read_text(encoding="utf-8") == (
                cros_losetup._UDEV_RULE_TEMPLATE % constants.SOURCE_ROOT
            )
            assert rc.call_count == call_count
