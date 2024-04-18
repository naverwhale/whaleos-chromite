# Copyright 2017 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for cros_sdk."""

import os
import re
import sys
from typing import List, Optional
from unittest import mock

import pytest  # type: ignore

from chromite.lib import chromite_config
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import retry_util
from chromite.scripts import cros_sdk


class CrosSdkUtilsTest(cros_test_lib.MockTempDirTestCase):
    """Tests for misc util funcs."""

    def testGetArchStageTarballs(self):
        """Basic test of GetArchStageTarballs."""
        self.assertCountEqual(
            [
                "https://storage.googleapis.com/chromiumos-sdk/"
                "cros-sdk-123.tar.xz",
            ],
            cros_sdk.GetArchStageTarballs("123"),
        )

    def testFetchRemoteTarballsEmpty(self):
        """Test FetchRemoteTarballs with no results."""
        m = self.PatchObject(retry_util, "RunCurl")
        with self.assertRaises(ValueError):
            cros_sdk.FetchRemoteTarballs(self.tempdir, [])
        m.return_value = cros_build_lib.CompletedProcess(stdout=b"Foo: bar\n")
        with self.assertRaises(ValueError):
            cros_sdk.FetchRemoteTarballs(self.tempdir, ["gs://x.tar"])

    def testFetchRemoteTarballsSuccess(self):
        """Test FetchRemoteTarballs with a successful download."""
        curl = cros_build_lib.CompletedProcess(
            stdout=(b"HTTP/1.0 200\n" b"Foo: bar\n" b"Content-Length: 100\n")
        )
        self.PatchObject(retry_util, "RunCurl", return_value=curl)
        self.assertEqual(
            os.path.join(self.tempdir, "tar"),
            cros_sdk.FetchRemoteTarballs(self.tempdir, ["gs://x/tar"]),
        )


class CrosSdkParserCommandLineTest(cros_test_lib.MockTestCase):
    """Tests involving the CLI."""

    # pylint: disable=protected-access

    # A typical sys.argv[0] that cros_sdk sees.
    ARGV0 = "/home/chronos/chromiumos/chromite/bin/cros_sdk"

    def setUp(self):
        self.parser, _ = cros_sdk._CreateParser("1", "2")

    def testSudoCommand(self):
        """Verify basic sudo command building works."""
        # Stabilize the env for testing.
        for v in (
            constants.CHROOT_ENVIRONMENT_ALLOWLIST + constants.ENV_PASSTHRU
        ):
            os.environ[v] = "value"
        os.environ["PATH"] = "path"

        cmd = cros_sdk._SudoCommand()
        assert cmd[0] == "sudo"
        assert "CHROMEOS_SUDO_PATH=path" in cmd
        rlimits = [x for x in cmd if x.startswith("CHROMEOS_SUDO_RLIMITS=")]
        assert len(rlimits) == 1

        # Spot check some pass thru vars.
        assert "GIT_AUTHOR_EMAIL=value" in cmd
        assert "https_proxy=value" in cmd

        # Make sure we only pass vars after `sudo`.
        for i in range(1, len(cmd)):
            assert "=" in cmd[i]
            v = cmd[i].split("=", 1)[0]
            assert re.match(r"^[A-Za-z0-9_]+$", v) is not None

    def testReexecCommand(self):
        """Verify reexec command line building."""
        # Stub sudo logic since we tested it above already.
        self.PatchObject(cros_sdk, "_SudoCommand", return_value=["sudo"])
        opts = self.parser.parse_args([])
        new_cmd = cros_sdk._BuildReExecCommand([self.ARGV0], opts)
        assert new_cmd == ["sudo", "--", sys.executable, self.ARGV0]

    def testReexecCommandStrace(self):
        """Verify reexec command line building w/strace."""
        # Stub sudo logic since we tested it above already.
        self.PatchObject(cros_sdk, "_SudoCommand", return_value=["sudo"])

        # Strace args passed, but not enabled.
        opts = self.parser.parse_args(["--strace-arguments=-s4096 -v"])
        new_cmd = cros_sdk._BuildReExecCommand([self.ARGV0], opts)
        assert new_cmd == ["sudo", "--", sys.executable, self.ARGV0]

        # Strace enabled.
        opts = self.parser.parse_args(["--strace"])
        new_cmd = cros_sdk._BuildReExecCommand([self.ARGV0], opts)
        assert new_cmd == [
            "sudo",
            "--",
            "strace",
            "--",
            sys.executable,
            self.ARGV0,
        ]

        # Strace enabled w/args.
        opts = self.parser.parse_args(
            ["--strace", "--strace-arguments=-s4096 -v"]
        )
        new_cmd = cros_sdk._BuildReExecCommand([self.ARGV0], opts)
        assert new_cmd == [
            "sudo",
            "--",
            "strace",
            "-s4096",
            "-v",
            "--",
            sys.executable,
            self.ARGV0,
        ]


# pylint: disable=protected-access


def test_freeze_options():
    """Test that we can't change options after finalization."""
    parser, commands = cros_sdk._CreateParser("1", "2")
    options = parser.parse_args([])
    cros_sdk._FinalizeOptions(parser, options, commands)

    with pytest.raises(Exception):
        options.enter = True
        options.enter = False


def test_bootstrap_alias():
    """Test the bootstrap/create alias."""
    parser, commands = cros_sdk._CreateParser("1", "2")
    options = parser.parse_args(["--bootstrap"])
    cros_sdk._FinalizeOptions(parser, options, commands)
    assert options.create


def test_replace_alias():
    """Test the replace -> delete/create alias."""
    parser, commands = cros_sdk._CreateParser("1", "2")
    options = parser.parse_args(["--replace"])
    cros_sdk._FinalizeOptions(parser, options, commands)
    assert options.delete
    assert options.create


def test_implied_download():
    """Test that create implies download."""
    parser, commands = cros_sdk._CreateParser("1", "2")
    options = parser.parse_args(["--create"])
    cros_sdk._FinalizeOptions(parser, options, commands)
    assert options.download


@pytest.mark.parametrize(
    "arglist",
    (
        [],
        ["--enter"],
        ["--working-dir", "."],
        ["--goma-dir", ".", "emerge", "baz"],
    ),
)
def test_implied_enter(arglist: List[str]):
    """Test for implicit --enter."""
    parser, commands = cros_sdk._CreateParser("1", "2")
    options = parser.parse_args(arglist)
    cros_sdk._FinalizeOptions(parser, options, commands)
    assert options.enter


@pytest.mark.parametrize(
    "command",
    (
        "--create",
        "--bootstrap",
        "--replace",
        "--delete",
        "--download",
    ),
)
def test_commands(command: str):
    """Test options that don't imply --enter."""
    parser, commands = cros_sdk._CreateParser("1", "2")
    options = parser.parse_args([command])
    cros_sdk._FinalizeOptions(parser, options, commands)
    assert not options.enter


@pytest.mark.parametrize(
    "arglist",
    (
        ["--delete", "--enter"],
        ["--force"],  # without --delete
        ["--read-only-sticky"],  # without --[no-]read-only
    ),
)
def test_conflicting_args(arglist: List[str]):
    """Test args that conflict raise an error."""
    parser, commands = cros_sdk._CreateParser("1", "2")
    options = parser.parse_args(arglist)
    with pytest.raises(SystemExit):
        cros_sdk._FinalizeOptions(parser, options, commands)


def test_reclient_args(tmp_path):
    """Test mismatched reclient/reproxy args."""
    reclient_dir = tmp_path
    cfg_file = tmp_path / "foo"
    cfg_file.touch()

    for arglist in (
        ["--reclient-dir", str(reclient_dir)],  # without --reproxy-cfg-file
        ["--reproxy-cfg-file", str(cfg_file)],  # without --reclient-dir
    ):
        parser, commands = cros_sdk._CreateParser("1", "2")
        options = parser.parse_args(arglist)
        with pytest.raises(SystemExit):
            cros_sdk._FinalizeOptions(parser, options, commands)


def test_chroot_ready():
    """Ensure no implicit create when chroot is ready."""
    parser, commands = cros_sdk._CreateParser("1", "2")
    options = parser.parse_args([])

    with mock.patch(
        "chromite.lib.cros_sdk_lib.IsChrootReady", return_value=True
    ):
        cros_sdk._FinalizeOptions(parser, options, commands)

    assert not options.create
    assert options.enter


def test_chroot_not_ready():
    """Test implicit create when chroot isn't ready."""
    parser, commands = cros_sdk._CreateParser("1", "2")
    options = parser.parse_args([])

    with mock.patch(
        "chromite.lib.cros_sdk_lib.IsChrootReady", return_value=False
    ):
        cros_sdk._FinalizeOptions(parser, options, commands)

    assert options.create
    assert options.enter


@pytest.mark.parametrize(
    ["arglist", "confcontents", "expect_ro"],
    [
        ([], None, False),  # no args; no conf; default read-only=False
        ([], "1", True),  # no args; conf is "1"; read-only=True
        (
            [],
            "garbage",
            True,
        ),  # no args; conf is garbage, but contents are ignored
        (["--read-only"], "1", True),  # --read-only arg always wins
        (["--read-only"], "garbage", True),  # --read-only arg always wins
        (
            ["--no-read-only"],
            "garbage",
            False,
        ),  # --no-read-only arg always wins
        (["--no-read-only"], "1", False),  # --no-read-only arg always wins
        ([], "    0   \n", True),  # conf contents are ignored
    ],
)
def test_readonly_configuration(
    monkeypatch,
    tmp_path,
    arglist: List[str],
    confcontents: Optional[str],
    expect_ro: bool,
):
    """Test read-only configuration file and flags."""
    conf_file = tmp_path / "readonlyconf"
    if confcontents is not None:
        conf_file.write_text(confcontents)
    monkeypatch.setattr(
        chromite_config, "SDK_READONLY_STICKY_CONFIG", conf_file
    )

    parser, commands = cros_sdk._CreateParser("1", "2")
    options = parser.parse_args(arglist)
    cros_sdk._FinalizeOptions(parser, options, commands)
    assert options.read_only == expect_ro


@pytest.mark.parametrize(
    ["orig_contents", "arglist", "expect_conf_exists"],
    (
        (None, [], False),
        (None, ["--read-only"], False),
        (None, ["--no-read-only"], False),
        ("0", ["--read-only"], True),
        ("1", ["--no-read-only"], True),
        (None, ["--read-only", "--read-only-sticky"], True),
        (None, ["--no-read-only", "--read-only-sticky"], False),
        ("0", ["--read-only", "--read-only-sticky"], True),
        ("1", ["--no-read-only", "--read-only-sticky"], False),
    ),
)
def test_readonly_sticky(
    monkeypatch,
    tmp_path,
    orig_contents: Optional[str],
    arglist: List[str],
    expect_conf_exists: bool,
):
    """Test that we write expected read-only-sticky contents.

    orig_contents: Optional pre-existing contents of the configuration file.
    arglist: The cros_sdk argument list to test.
    expect_conf_exists: Whether we expect the conf file to exist.
    """
    conf_file = tmp_path / "readonlyconf"
    if orig_contents is not None:
        conf_file.write_text(orig_contents)
    monkeypatch.setattr(
        chromite_config, "SDK_READONLY_STICKY_CONFIG", conf_file
    )

    parser, commands = cros_sdk._CreateParser("1", "2")
    options = parser.parse_args(arglist)
    cros_sdk._FinalizeOptions(parser, options, commands)

    assert conf_file.exists() == expect_conf_exists
