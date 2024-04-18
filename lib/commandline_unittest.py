# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the commandline module."""

import argparse
import datetime
import enum
import logging
import os
import pickle
import signal
import sys
from typing import Callable, List, Optional

import pytest

from chromite.cli import command
from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.utils import gs_urls_util


class TestShutDownException(cros_test_lib.TestCase):
    """Test that ShutDownException can be pickled."""

    def testShutDownException(self):
        """Test that ShutDownException can be pickled."""
        # pylint: disable=protected-access
        ex = commandline._ShutDownException(signal.SIGTERM, "Received SIGTERM")
        ex2 = pickle.loads(pickle.dumps(ex))
        self.assertEqual(ex.signal, ex2.signal)
        self.assertEqual(str(ex), str(ex2))


class TimedeltaTest(cros_test_lib.TestCase):
    """Test type=timedelta is supported correctly."""

    def setUp(self):
        """Create a parser for testing."""
        self.parser = commandline.ArgumentParser()
        self.parser.add_argument(
            "--timedelta",
            type="timedelta",
            help="Some timedelta help message.",
        )

    def testInvalidTimedelta(self):
        """Test invalid timedelta values. (invalid)"""
        with self.assertRaises(SystemExit):
            self.parser.parse_args(["--timedelta", "foobar"])

    def testNegativeTimedelta(self):
        """Test negative integer timedelta values. (invalid)"""
        with self.assertRaises(SystemExit):
            self.parser.parse_args(["--timedelta", "-1"])

    def testPositiveTimedelta(self):
        """Test positive integer timedelta values. (valid)"""
        opts = self.parser.parse_args(["--timedelta", "1"])
        self.assertEqual(opts.timedelta, datetime.timedelta(seconds=1))
        opts = self.parser.parse_args(["--timedelta", "0"])
        self.assertEqual(opts.timedelta, datetime.timedelta(seconds=0))


class GSPathTest(cros_test_lib.OutputTestCase):
    """Test type=gs_path normalization functionality."""

    GS_REL_PATH = "bucket/path/to/artifacts"

    @staticmethod
    def _ParseCommandLine(argv):
        parser = commandline.ArgumentParser()
        parser.add_argument(
            "-g",
            "--gs-path",
            type="gs_path",
            help="GS path that contains the chrome to deploy.",
        )
        return parser.parse_args(argv)

    def _RunGSPathTestCase(self, raw, parsed):
        options = self._ParseCommandLine(["--gs-path", raw])
        self.assertEqual(options.gs_path, parsed)

    def testNoGSPathCorrectionNeeded(self):
        """Test case where GS path correction is not needed."""
        gs_path = "%s/%s" % (gs_urls_util.BASE_GS_URL, self.GS_REL_PATH)
        self._RunGSPathTestCase(gs_path, gs_path)

    def testTrailingSlashRemoval(self):
        """Test case where GS path ends with /."""
        gs_path = "%s/%s/" % (gs_urls_util.BASE_GS_URL, self.GS_REL_PATH)
        self._RunGSPathTestCase(gs_path, gs_path.rstrip("/"))

    def testDuplicateSlashesRemoved(self):
        """Test case where GS path contains many / in a row."""
        self._RunGSPathTestCase(
            "%s/a/dir/with//////////slashes" % gs_urls_util.BASE_GS_URL,
            "%s/a/dir/with/slashes" % gs_urls_util.BASE_GS_URL,
        )

    def testRelativePathsRemoved(self):
        """Test case where GS path contain /../ logic."""
        self._RunGSPathTestCase(
            "%s/a/dir/up/here/.././../now/down/there"
            % gs_urls_util.BASE_GS_URL,
            "%s/a/dir/now/down/there" % gs_urls_util.BASE_GS_URL,
        )

    def testCorrectionNeeded(self):
        """Test case where GS path correction is needed."""
        self._RunGSPathTestCase(
            "%s/%s/" % (gs_urls_util.PRIVATE_BASE_HTTPS_URL, self.GS_REL_PATH),
            "%s/%s" % (gs_urls_util.BASE_GS_URL, self.GS_REL_PATH),
        )

    def testInvalidPath(self):
        """Path cannot be normalized."""
        with self.OutputCapturer():
            self.assertRaises2(
                SystemExit,
                self._RunGSPathTestCase,
                "http://badhost.com/path",
                "",
                check_attrs={"code": 2},
            )


class BoolTest(cros_test_lib.TestCase):
    """Test type='bool' functionality."""

    @staticmethod
    def _ParseCommandLine(argv):
        parser = commandline.ArgumentParser()
        parser.add_argument(
            "-e", "--enable", type="bool", help="Boolean Argument."
        )
        return parser.parse_args(argv)

    def _RunBoolTestCase(self, enable, expected):
        options = self._ParseCommandLine(["--enable", enable])
        self.assertEqual(options.enable, expected)

    def testBoolTrue(self):
        """Test case setting the value to true."""
        self._RunBoolTestCase("True", True)
        self._RunBoolTestCase("1", True)
        self._RunBoolTestCase("true", True)
        self._RunBoolTestCase("yes", True)
        self._RunBoolTestCase("TrUe", True)

    def testBoolFalse(self):
        """Test case setting the value to false."""
        self._RunBoolTestCase("False", False)
        self._RunBoolTestCase("0", False)
        self._RunBoolTestCase("false", False)
        self._RunBoolTestCase("no", False)
        self._RunBoolTestCase("FaLse", False)


class StandardBoolTest(cros_test_lib.TestCase):
    """Test add_bool_argument functionality."""

    def setUp(self):
        self.parser = commandline.ArgumentParser()
        # Use names "DT" (default-true), "DF" (default-false), and "DN"
        # (default-None). Abbreviated because the test is hard to read if
        # boolean strings are everywhere.
        self.parser.add_bool_argument("--dt-var", True, "Yes DT", "No DT")
        self.parser.add_bool_argument("--df-var", False, "Yes DF", "No DF")
        self.parser.add_bool_argument("--dn-var", None, "Yes DN", "No DN")

    def add_flag(self, flag: str) -> Callable:
        """Returns a closure that adds a bool argument using `flag`."""

        def invoke() -> None:
            self.parser.add_bool_argument(flag, True, "", "")

        return invoke

    def testNormalUsage(self):
        """Test end-to-end usage with 2 args with different defaults."""

        def verify(
            argv: List[str], dt: bool, df: bool, dn: Optional[bool] = None
        ):
            options = self.parser.parse_args(argv)
            self.assertEqual(options.dt_var, dt)
            self.assertEqual(options.df_var, df)
            self.assertEqual(options.dn_var, dn)

        verify([], dt=True, df=False, dn=None)

        verify(["--df-var"], dt=True, df=True)
        verify(["--no-df-var"], dt=True, df=False)
        verify(["--df-var", "--no-df-var"], dt=True, df=False)

        verify(["--dt-var"], dt=True, df=False)
        verify(["--no-dt-var"], dt=False, df=False)
        verify(["--dt-var", "--no-dt-var"], dt=False, df=False)

        verify(["--dn-var"], dt=True, df=False, dn=True)
        verify(["--no-dn-var"], dt=True, df=False, dn=False)

    def testHelpStrings(self):
        """Test help strings are set correctly."""
        help_string = self.parser.format_help()
        self.assertIn("Yes DT (DEFAULT)\n", help_string)
        self.assertIn("No DT\n", help_string)
        self.assertIn("Yes DF\n", help_string)
        self.assertIn("No DF (DEFAULT)\n", help_string)
        # Default=None is treated as not having a default.
        self.assertIn("Yes DN\n", help_string)
        self.assertIn("No DN\n", help_string)

    def testNoPrefixRaises(self):
        """Ensure flags that are not prefixed with `--` raise ValueError."""
        self.assertRaises(ValueError, self.add_flag("-f"))
        self.assertRaises(ValueError, self.add_flag("f"))
        self.add_flag("--f")()  # OK.

    def testUnderscoreRaises(self):
        """Ensure flags incorrectly using snake_case raise ValueError."""
        self.assertRaises(ValueError, self.add_flag("--my_flag"))
        self.add_flag("--my-flag")()  # OK.

    def testTypeEqualsBoolRaises(self):
        """Ensure unquoted `type=bool` is rejected by regular add_argument."""
        with self.assertRaises(ValueError) as context:
            self.parser.add_argument("--verbose", type=bool)
        self.assertIn("Use `add_bool_argument()`", str(context.exception))


class DeviceParseTest(cros_test_lib.OutputTestCase):
    """Test device parsing functionality."""

    _ALL_SCHEMES = (
        commandline.DEVICE_SCHEME_FILE,
        commandline.DEVICE_SCHEME_SERVO,
        commandline.DEVICE_SCHEME_SSH,
        commandline.DEVICE_SCHEME_USB,
    )

    def _CheckDeviceParse(
        self,
        device_input: str,
        scheme: str,
        username: Optional[str] = None,
        hostname: Optional[str] = None,
        port: Optional[int] = None,
        path: Optional[str] = None,
        serial: Optional[str] = None,
    ):
        """Checks that parsing a device input gives the expected result.

        Args:
            device_input: Input specifying a device.
            scheme: Expected scheme.
            username: Expected username.
            hostname: Expected hostname.
            port: Expected port.
            path: Expected path.
            serial: Expected serial number.
        """
        parser = commandline.ArgumentParser()
        parser.add_argument("device", type=commandline.DeviceParser(scheme))
        device = parser.parse_args([device_input]).device
        self.assertEqual(device.scheme, scheme)
        self.assertEqual(device.username, username)
        self.assertEqual(device.hostname, hostname)
        self.assertEqual(device.port, port)
        self.assertEqual(device.path, path)
        self.assertEqual(device.serial_number, serial)

    def _CheckDeviceParseFails(self, device_input, schemes=_ALL_SCHEMES):
        """Checks that parsing a device input fails.

        Args:
            device_input: String input specifying a device.
            schemes: A scheme or list of allowed schemes, by default allows all.
        """
        parser = commandline.ArgumentParser()
        parser.add_argument("device", type=commandline.DeviceParser(schemes))
        with self.OutputCapturer():
            self.assertRaises2(SystemExit, parser.parse_args, [device_input])

    def testNoDevice(self):
        """Verify that an empty device specification fails."""
        self._CheckDeviceParseFails("")

    def testSshScheme(self):
        """Verify that SSH scheme-only device specification fails."""
        self._CheckDeviceParseFails("ssh://")

    def testInvalidSshScheme(self):
        """Verify that invalid ssh specification fails."""
        self._CheckDeviceParseFails("sssssh://localhost:22")

    def testSshHostname(self):
        """Test SSH hostname-only device specification."""
        self._CheckDeviceParse(
            "192.168.1.200",
            scheme=commandline.DEVICE_SCHEME_SSH,
            hostname="192.168.1.200",
        )

    def testSshHostnamePort(self):
        """Test SSH hostname and port device specification."""
        self._CheckDeviceParse(
            "192.168.1.200:9999",
            scheme=commandline.DEVICE_SCHEME_SSH,
            hostname="192.168.1.200",
            port=9999,
        )

    def testSshUsernameHostname(self):
        """Test SSH username and hostname device specification."""
        self._CheckDeviceParse(
            "me@foo_host",
            scheme=commandline.DEVICE_SCHEME_SSH,
            username="me",
            hostname="foo_host",
        )

    def testSshUsernameHostnamePort(self):
        """Test SSH username, hostname, and port device specification."""
        self._CheckDeviceParse(
            "me@foo_host:4500",
            scheme=commandline.DEVICE_SCHEME_SSH,
            username="me",
            hostname="foo_host",
            port=4500,
        )

    def testSshSchemeUsernameHostnamePort(self):
        """Test SSH, username, hostname, and port device specification."""
        self._CheckDeviceParse(
            "ssh://me@foo_host:4500",
            scheme=commandline.DEVICE_SCHEME_SSH,
            username="me",
            hostname="foo_host",
            port=4500,
        )

    def testSshIpv6NoBrackets(self):
        """Test SSH with IPv6 address, no brackets.

        Should fail with user-friendly message.
        """
        with cros_test_lib.LoggingCapturer() as logcap:
            self._CheckDeviceParseFails("ssh://::1:2222")
            assert logcap.LogsContain("To write an IPv6 address")

    def testSshIpv6WithBrackets(self):
        """Test SSH with an IPv6 address, all proper with the brackets."""
        self._CheckDeviceParse(
            "ssh://[::1]:2222",
            scheme=commandline.DEVICE_SCHEME_SSH,
            hostname="::1",
            port=2222,
        )

    def testEmptyServoScheme(self):
        """Test empty servo scheme."""
        # Everything should be None so the underlying programs (e.g.
        # dut-control) can use their defaults.
        self._CheckDeviceParseFails("servo:")

    def testServoPort(self):
        """Test valid servo port values."""
        self._CheckDeviceParse(
            "servo:port", scheme=commandline.DEVICE_SCHEME_SERVO, port=None
        )
        self._CheckDeviceParse(
            "servo:port:1", scheme=commandline.DEVICE_SCHEME_SERVO, port=1
        )
        self._CheckDeviceParse(
            "servo:port:12345",
            scheme=commandline.DEVICE_SCHEME_SERVO,
            port=12345,
        )
        self._CheckDeviceParse(
            "servo:port:65535",
            scheme=commandline.DEVICE_SCHEME_SERVO,
            port=65535,
        )

    def testInvalidServoPort(self):
        """Invalid port provided."""
        self._CheckDeviceParseFails("servo:port:0")
        self._CheckDeviceParseFails("servo:port:65536")
        # Some serial numbers.
        self._CheckDeviceParseFails("servo:port:C1234567890")
        self._CheckDeviceParseFails("servo:port:123456-12345")

    def testServoSerialNumber(self):
        """Test servo serial number."""
        # Some known serial number formats.
        self._CheckDeviceParse(
            "servo:serial:C1234567890",
            scheme=commandline.DEVICE_SCHEME_SERVO,
            serial="C1234567890",
        )
        self._CheckDeviceParse(
            "servo:serial:123456-12345",
            scheme=commandline.DEVICE_SCHEME_SERVO,
            serial="123456-12345",
        )
        # Make sure we don't fall back to a port when it looks like one.
        self._CheckDeviceParse(
            "servo:serial:12345",
            scheme=commandline.DEVICE_SCHEME_SERVO,
            serial="12345",
        )

    def testInvalidServoSerialNumber(self):
        """Invalid serial number value provided."""
        self._CheckDeviceParseFails("servo:serial:")

    def testUsbScheme(self):
        """Test USB scheme-only device specification."""
        self._CheckDeviceParse("usb://", scheme=commandline.DEVICE_SCHEME_USB)

    def testUsbSchemePath(self):
        """Test USB scheme and path device specification."""
        self._CheckDeviceParse(
            "usb://path/to/my/device",
            scheme=commandline.DEVICE_SCHEME_USB,
            path="path/to/my/device",
        )

    def testFileScheme(self):
        """Verify that file scheme-only device specification fails."""
        self._CheckDeviceParseFails("file://")

    def testFileSchemePath(self):
        """Test file scheme and path device specification."""
        self._CheckDeviceParse(
            "file://foo/bar",
            scheme=commandline.DEVICE_SCHEME_FILE,
            path="foo/bar",
        )

    def testAbsolutePath(self):
        """Verify that an absolute path defaults to file scheme."""
        self._CheckDeviceParse(
            "/path/to/my/device",
            scheme=commandline.DEVICE_SCHEME_FILE,
            path="/path/to/my/device",
        )

    def testUnsupportedScheme(self):
        """Verify that an unsupported scheme fails."""
        self._CheckDeviceParseFails(
            "ssh://192.168.1.200", schemes=commandline.DEVICE_SCHEME_USB
        )
        self._CheckDeviceParseFails(
            "usb://path/to/my/device",
            schemes=[
                commandline.DEVICE_SCHEME_SSH,
                commandline.DEVICE_SCHEME_FILE,
            ],
        )

    def testUnknownScheme(self):
        """Verify that an unknown scheme fails."""
        self._CheckDeviceParseFails("ftp://192.168.1.200")

    def testSchemeCaseInsensitive(self):
        """Verify that schemes are case-insensitive."""
        self._CheckDeviceParse(
            "SSH://foo_host",
            scheme=commandline.DEVICE_SCHEME_SSH,
            hostname="foo_host",
        )


class AppendOptionTest(cros_test_lib.TestCase):
    """Verify append_option/append_option_value actions."""

    def setUp(self):
        """Create a standard parser for the tests."""
        self.parser = commandline.ArgumentParser()
        self.parser.add_argument("--flag", action="append_option")
        self.parser.add_argument("--value", action="append_option_value")
        self.parser.add_argument(
            "-x", "--shared_flag", dest="shared", action="append_option"
        )
        self.parser.add_argument(
            "-y", "--shared_value", dest="shared", action="append_option_value"
        )

    def testNone(self):
        """Test results when no arguments are passed in."""
        result = self.parser.parse_args([])
        self.assertGreaterEqual(
            vars(result).items(),
            {"flag": None, "value": None, "shared": None}.items(),
        )

    def testSingles(self):
        """Test results when no argument is used more than once."""
        result = self.parser.parse_args(
            [
                "--flag",
                "--value",
                "foo",
                "--shared_flag",
                "--shared_value",
                "bar",
            ]
        )

        self.assertGreaterEqual(
            vars(result).items(),
            {
                "flag": ["--flag"],
                "value": ["--value", "foo"],
                "shared": ["--shared_flag", "--shared_value", "bar"],
            }.items(),
        )

    def testMultiples(self):
        """Test results when no arguments are used more than once."""
        result = self.parser.parse_args(
            [
                "--flag",
                "--value",
                "v1",
                "-x",
                "-y",
                "s1",
                "--shared_flag",
                "--shared_value",
                "s2",
                "--flag",
                "--value",
                "v2",
            ]
        )

        self.assertGreaterEqual(
            vars(result).items(),
            {
                "flag": ["--flag", "--flag"],
                "value": ["--value", "v1", "--value", "v2"],
                "shared": [
                    "-x",
                    "-y",
                    "s1",
                    "--shared_flag",
                    "--shared_value",
                    "s2",
                ],
            }.items(),
        )


class Size(enum.Enum):
    """Example enum for test cases."""

    SMALL = 0
    MEDIUM = 1
    LARGE = 2


class EnumActionTest(cros_test_lib.TestCase):
    """Verify action="enum" functionality."""

    def setUp(self):
        """Create a parser to use for tests."""
        self.parser = commandline.ArgumentParser()
        self.parser.add_argument("--size", action="enum", enum=Size)

    def testParseValid(self):
        """Test the usual, valid inputs."""
        opts = self.parser.parse_args(["--size", "small"])
        self.assertEqual(opts.size, Size.SMALL)

        opts = self.parser.parse_args(["--size", "medium"])
        self.assertEqual(opts.size, Size.MEDIUM)

        opts = self.parser.parse_args(["--size", "large"])
        self.assertEqual(opts.size, Size.LARGE)

    def testParseInvalidCase(self):
        """Test the enum given in all uppercase (should be lowercase)."""
        with self.assertRaises(SystemExit) as e:
            self.parser.parse_args(["--size", "SMALL"])
            self.assertNotEqual(e.status, 0)

    def testParseInvalid(self):
        """Test when something else completely unexpected is given."""
        with self.assertRaises(SystemExit) as e:
            self.parser.parse_args(["--size", "extra_medium"])
            self.assertNotEqual(e.status, 0)


class SplitExtendActionTest(cros_test_lib.TestCase):
    """Verify _SplitExtendAction/split_extend action."""

    def _CheckArgs(self, cliargs, expected):
        """Check |cliargs| produces |expected|."""
        parser = commandline.ArgumentParser()
        parser.add_argument("-x", action="split_extend", default=[])
        opts = parser.parse_args(
            cros_build_lib.iflatten_instance(["-x", x] for x in cliargs)
        )
        self.assertEqual(opts.x, expected)

    def testDefaultNone(self):
        """Verify default=None works."""
        parser = commandline.ArgumentParser()
        parser.add_argument("-x", action="split_extend", default=None)

        opts = parser.parse_args([])
        self.assertIs(opts.x, None)

        opts = parser.parse_args(["-x", ""])
        self.assertEqual(opts.x, [])

        opts = parser.parse_args(["-x", "f"])
        self.assertEqual(opts.x, ["f"])

    def testNoArgs(self):
        """This is more of a confidence check for resting state."""
        self._CheckArgs([], [])

    def testEmptyArg(self):
        """Make sure '' produces nothing."""
        self._CheckArgs(["", ""], [])

    def testEmptyWhitespaceArg(self):
        """Make sure whitespace produces nothing."""
        self._CheckArgs([" ", "\t", "  \t   "], [])

    def testSingleSingleArg(self):
        """Verify splitting one arg works."""
        self._CheckArgs(["a"], ["a"])

    def testMultipleSingleArg(self):
        """Verify splitting one arg works."""
        self._CheckArgs(["a b  c\td "], ["a", "b", "c", "d"])

    def testMultipleMultipleArgs(self):
        """Verify splitting multiple args works."""
        self._CheckArgs(["a b  c", "", "x", " k "], ["a", "b", "c", "x", "k"])


class CacheTest(cros_test_lib.MockTempDirTestCase):
    """Test cache dir default / override functionality."""

    CACHE_DIR = "/fake/cache/dir"

    def setUp(self):
        self.PatchObject(commandline.ArgumentParser, "ConfigureCacheDir")
        dir_struct = [
            "repo/.repo/",
        ]
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, dir_struct)
        self.repo_root = os.path.join(self.tempdir, "repo")
        self.cwd_mock = self.PatchObject(os, "getcwd")
        self.parser = commandline.ArgumentParser(caching=True)

    def _CheckCall(self, cwd_retval, args_to_parse, expected, assert_func):
        self.cwd_mock.return_value = cwd_retval
        self.parser.parse_args(args_to_parse)
        cache_dir_mock = self.parser.ConfigureCacheDir
        self.assertEqual(1, cache_dir_mock.call_count)
        assert_func(cache_dir_mock.call_args[0][0], expected)

    def testRepoRootNoOverride(self):
        """Test default cache location when in a repo checkout."""
        self._CheckCall(
            self.repo_root, [], self.repo_root, self.assertStartsWith
        )

    def testRepoRootWithOverride(self):
        """User provided cache location overrides repo checkout default."""
        self._CheckCall(
            self.repo_root,
            ["--cache-dir", self.CACHE_DIR],
            self.CACHE_DIR,
            self.assertEqual,
        )


class PathFilterTest(cros_test_lib.TestCase):
    """Test path filter with --exclude, --include."""

    def testFilter(self):
        """Tests basic filtering."""
        parser = commandline.ArgumentParser(filter=True)
        options = parser.parse_args(["--include=a.out", "--exclude=*.out"])
        self.assertEqual(options.filter.filter(["a.out", "b.out"]), ["a.out"])

    def testFilterWithoutOptions(self):
        """Tests filtering when no flags are passed."""
        parser = commandline.ArgumentParser(filter=True)
        options = parser.parse_args([])
        self.assertIsNotNone(options.filter)
        self.assertEqual(
            options.filter.filter(["a.out", "b.out"]), ["a.out", "b.out"]
        )


class ParseArgsTest(cros_test_lib.TestCase):
    """Test parse_args behavior of our custom argument parsing classes."""

    def _CreateOptionParser(self, cls):
        """Create a class of optparse.OptionParser with prepared config.

        Args:
            cls: Some subclass of optparse.OptionParser.

        Returns:
            The created OptionParser object.
        """
        usage = "usage: some usage"
        parser = cls(usage=usage)

        # Add some options.
        parser.add_option(
            "-x", "--xxx", action="store_true", default=False, help="Gimme an X"
        )
        parser.add_option(
            "-y", "--yyy", action="store_true", default=False, help="Gimme a Y"
        )
        parser.add_option(
            "-a", "--aaa", type="string", default="Allan", help="Gimme an A"
        )
        parser.add_option(
            "-b", "--bbb", type="string", default="Barry", help="Gimme a B"
        )
        parser.add_option(
            "-c", "--ccc", type="string", default="Connor", help="Gimme a C"
        )

        return parser

    def _CreateArgumentParser(self, cls):
        """Create a class of argparse.ArgumentParser with prepared config.

        Args:
            cls: Some subclass of argparse.ArgumentParser.

        Returns:
            The created ArgumentParser object.
        """
        usage = "usage: some usage"
        parser = cls(usage=usage)

        # Add some options.
        parser.add_argument(
            "-x", "--xxx", action="store_true", default=False, help="Gimme an X"
        )
        parser.add_argument(
            "-y", "--yyy", action="store_true", default=False, help="Gimme a Y"
        )
        parser.add_argument(
            "-a", "--aaa", type=str, default="Allan", help="Gimme an A"
        )
        parser.add_argument(
            "-b", "--bbb", type=str, default="Barry", help="Gimme a B"
        )
        parser.add_argument(
            "-c", "--ccc", type=str, default="Connor", help="Gimme a C"
        )
        parser.add_argument("args", type=str, nargs="*", help="args")

        return parser

    def _TestParser(self, parser):
        """Test the given parser with a prepared argv."""
        argv = ["-x", "--bbb", "Bobby", "-c", "Connor", "foobar"]

        parsed = parser.parse_args(argv)

        if isinstance(parser, commandline.FilteringParser):
            # optparse returns options and args separately.
            options, args = parsed
            self.assertEqual(["foobar"], args)
        else:
            # argparse returns just options.  Options configured above to have
            # the args stored at option "args".
            options = parsed
            self.assertEqual(["foobar"], parsed.args)

        self.assertTrue(options.xxx)
        self.assertFalse(options.yyy)

        self.assertEqual("Allan", options.aaa)
        self.assertEqual("Bobby", options.bbb)
        self.assertEqual("Connor", options.ccc)

        self.assertRaises(AttributeError, getattr, options, "xyz")

        # Now try altering option values.
        options.aaa = "Arick"
        self.assertEqual("Arick", options.aaa)

        # Now freeze the options and try altering again.
        options.Freeze()
        self.assertRaises(
            commandline.attrs_freezer.Error, setattr, options, "aaa", "Arnold"
        )
        self.assertEqual("Arick", options.aaa)

    def testFilterParser(self):
        self._TestParser(self._CreateOptionParser(commandline.FilteringParser))

    def testArgumentParser(self):
        self._TestParser(self._CreateArgumentParser(commandline.ArgumentParser))

    def testDisableCommonLogging(self):
        """Verify we can elide common logging options."""
        parser = commandline.ArgumentParser(logging=False)

        # Sanity check it first.
        opts = parser.parse_args([])
        self.assertFalse(hasattr(opts, "log_level"))

        # Now add our own logging options.  If the options were added,
        # argparse would throw duplicate flag errors for us.
        parser.add_argument("--log-level")
        parser.add_argument("--nocolor")

    def testCommonBaseDefaults(self):
        """Make sure common options work with just a base parser."""
        parser = commandline.ArgumentParser(
            logging=True, default_log_level="info"
        )

        # Make sure the default works.
        opts = parser.parse_args([])
        self.assertEqual(opts.log_level, "info")
        self.assertEqual(opts.color, None)

        # Then we can set up our own values.
        opts = parser.parse_args(["--nocolor", "--log-level=notice"])
        self.assertEqual(opts.log_level, "notice")
        self.assertEqual(opts.color, False)

    def testCommonBaseAndSubDefaults(self):
        """Make sure common options work between base & sub parsers."""
        parser = commandline.ArgumentParser(
            logging=True, default_log_level="info"
        )

        sub_parsers = parser.add_subparsers(title="Subs")
        sub_parsers.add_parser("cmd1")
        sub_parsers.add_parser("cmd2")

        # Make sure the default works.
        opts = parser.parse_args(["cmd1"])
        self.assertEqual(opts.log_level, "info")
        self.assertEqual(opts.color, None)

        # Make sure options passed to base parser work.
        opts = parser.parse_args(["--nocolor", "--log-level=notice", "cmd2"])
        self.assertEqual(opts.log_level, "notice")
        self.assertEqual(opts.color, False)

        # Make sure options passed to sub parser work.
        opts = parser.parse_args(["cmd2", "--nocolor", "--log-level=notice"])
        self.assertEqual(opts.log_level, "notice")
        self.assertEqual(opts.color, False)


class ScriptWrapperMainTest(cros_test_lib.MockTestCase):
    """Test the behavior of the ScriptWrapperMain function."""

    def setUp(self):
        self.PatchObject(sys, "exit")
        self.lastTargetFound = None

    SYS_ARGV = ["/cmd", "/cmd", "arg1", "arg2"]
    CMD_ARGS = ["/cmd", "arg1", "arg2"]
    # The exact flags here don't matter as we don't invoke the underlying
    # script. Let's pick something specifically invalid just in case we do.
    CHROOT_ARGS = ["--some-option", "foo"]

    def testRestartInChrootPreserveArgs(self):
        """Verify args to ScriptWrapperMain are passed through to chroot."""
        # Setup Mocks/Fakes
        rc = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc.SetDefaultCmdResult()

        def findTarget(target):
            """ScriptWrapperMain needs a function to find a function to run."""

            def raiseChrootRequiredError(args):
                raise commandline.ChrootRequiredError(args)

            self.lastTargetFound = target
            return raiseChrootRequiredError

        # Run Test
        commandline.ScriptWrapperMain(findTarget, self.SYS_ARGV)

        # Verify Results
        rc.assertCommandContains(enter_chroot=True)
        rc.assertCommandContains(self.CMD_ARGS)
        self.assertEqual("/cmd", self.lastTargetFound)

    def testRestartInChrootWithChrootArgs(self):
        """Verify args and chroot args from exception are used."""
        # Setup Mocks/Fakes
        rc = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc.SetDefaultCmdResult()

        def findTarget(_):
            """ScriptWrapperMain needs a function to find a function to run."""

            def raiseChrootRequiredError(_args):
                raise commandline.ChrootRequiredError(
                    self.CMD_ARGS, self.CHROOT_ARGS
                )

            return raiseChrootRequiredError

        # Run Test
        commandline.ScriptWrapperMain(findTarget, ["unrelated"])

        # Verify Results
        rc.assertCommandContains(enter_chroot=True)
        rc.assertCommandContains(self.CMD_ARGS)
        rc.assertCommandContains(chroot_args=self.CHROOT_ARGS)


class TestRunInsideChroot(cros_test_lib.MockTestCase):
    """Test commandline.RunInsideChroot()."""

    def setUp(self):
        self.orig_argv = sys.argv
        sys.argv = ["/cmd", "arg1", "arg2"]

        self.mockFromHostToChrootPath = self.PatchObject(
            path_util, "ToChrootPath", return_value="/inside/cmd"
        )

        # Return values for these two should be set by each test.
        self.mock_inside_chroot = self.PatchObject(
            cros_build_lib, "IsInsideChroot"
        )

        # Mocked CliCommand object to pass to RunInsideChroot.
        self.cmd = command.CliCommand(argparse.Namespace())
        self.cmd.options.log_level = "info"

        def _inside_args_patch(*_args):
            argv = sys.argv[:]
            if argv[-1] == "arg3":
                argv[-1] = "newarg3"
            return argv

        self.PatchObject(self.cmd, "TranslateToChrootArgv", _inside_args_patch)

    def tearDown(self):
        sys.argv = self.orig_argv

    def _VerifyRunInsideChroot(
        self,
        expected_cmd,
        expected_chroot_args=None,
        log_level_args=None,
        **kwargs,
    ):
        """Run RunInsideChroot, and verify it raises with expected values.

        Args:
            expected_cmd: Command that should be executed inside the chroot.
            expected_chroot_args: Args that should be passed as chroot args.
            log_level_args: Args that set the log level of cros_sdk.
            **kwargs: Additional args to pass to RunInsideChroot().
        """
        with self.assertRaises(commandline.ChrootRequiredError) as cm:
            commandline.RunInsideChroot(self.cmd, **kwargs)

        if log_level_args is None:
            if self.cmd is not None:
                log_level_args = ["--log-level", self.cmd.options.log_level]
            else:
                log_level_args = []

        if expected_chroot_args is not None:
            log_level_args.extend(expected_chroot_args)
            expected_chroot_args = log_level_args
        else:
            expected_chroot_args = log_level_args

        self.assertEqual(expected_cmd, cm.exception.cmd)
        self.assertEqual(expected_chroot_args, cm.exception.chroot_args)

    def testRunInsideChroot(self):
        """Test we can restart inside the chroot."""
        self.mock_inside_chroot.return_value = False
        self._VerifyRunInsideChroot(["/inside/cmd", "arg1", "arg2"])

    def testRunInsideChrootWithoutCommand(self):
        """Verify RunInsideChroot can get by without the |command| parameter."""
        self.mock_inside_chroot.return_value = False
        self.cmd = None
        self._VerifyRunInsideChroot(["/inside/cmd", "arg1", "arg2"])

    def testRunInsideChrootLogLevel(self):
        """Test chroot restart with properly inherited log-level."""
        self.cmd.options.log_level = "notice"
        self.mock_inside_chroot.return_value = False
        self._VerifyRunInsideChroot(
            ["/inside/cmd", "arg1", "arg2"],
            log_level_args=["--log-level", "notice"],
        )

    def testRunInsideChrootAlreadyInside(self):
        """Test we don't restart inside the chroot if we are already there."""
        self.mock_inside_chroot.return_value = True

        # Since we are in the chroot, it should return, doing nothing.
        commandline.RunInsideChroot(self.cmd)

    def testTranslateToChrootArgv(self):
        """Test we can restart inside the chroot."""
        self.mock_inside_chroot.return_value = False
        sys.argv.append("arg3")
        self._VerifyRunInsideChroot(["/inside/cmd", "arg1", "arg2", "newarg3"])


class TestRunAsRootUser(cros_test_lib.MockTestCase):
    """Test commandline.RunAsRootUser()."""

    def setUp(self):
        self.is_root_user_mock = self.PatchObject(
            osutils, "IsRootUser", return_value=True
        )
        self.execvp_mock = self.PatchObject(os, "execvp")

    def testInvalidInput(self):
        """Test an error is raised when no command is given."""
        with self.assertRaises(ValueError):
            commandline.RunAsRootUser([])

    def testRootUser(self):
        """Test that the function returns when is root user."""
        commandline.RunAsRootUser(["test_cmd"])

        self.execvp_mock.assert_not_called()

    def testPreserveEnv(self):
        """Test that the environment is preserved."""
        self.is_root_user_mock.return_value = False

        commandline.RunAsRootUser(["test_cmd"], preserve_env=True)

        self.execvp_mock.assert_called_once_with(
            "sudo",
            [
                "sudo",
                "--preserve-env",
                f'HOME={os.environ["HOME"]}',
                f'PATH={os.environ["PATH"]}',
                "--",
                "test_cmd",
            ],
        )

    def testCommandCreation(self):
        """Test that the command is created with the appropriate envvars."""
        self.is_root_user_mock.return_value = False

        commandline.RunAsRootUser(["test_cmd"])

        self.execvp_mock.assert_called_once_with(
            "sudo",
            [
                "sudo",
                f'HOME={os.environ["HOME"]}',
                f'PATH={os.environ["PATH"]}',
                "--",
                "test_cmd",
            ],
        )


class DeprecatedActionTest(cros_test_lib.MockTestCase):
    """Test the _DeprecatedAction integration."""

    def setUp(self):
        self.warning_patch = self.PatchObject(logging, "warning")

        # Setup arguments for a handful of actions.
        self.argument_parser = commandline.ArgumentParser()
        self.argument_parser.add_argument("--store")
        self.argument_parser.add_argument("--store-true", action="store_true")
        self.argument_parser.add_argument("--append", action="append", type=int)
        self.argument_parser.add_argument(
            "--dep-store", deprecated="Deprecated store"
        )
        self.argument_parser.add_argument(
            "--dep-store-true",
            action="store_true",
            deprecated="Deprecated store true",
        )
        self.argument_parser.add_argument(
            "--dep-append",
            action="append",
            type=int,
            deprecated="Deprecated append",
        )

        self.not_deprecated = [
            "--store",
            "a",
            "--store-true",
            "--append",
            "1",
            "--append",
            "2",
        ]
        self.deprecated = [
            "--dep-store",
            "b",
            "--dep-store-true",
            "--dep-append",
            "3",
            "--dep-append",
            "4",
        ]
        self.mixed = self.not_deprecated + self.deprecated

        self.store_expected = "a"
        self.append_expected = [1, 2]
        self.dep_store_expected = "b"
        self.dep_append_expected = [3, 4]

    def testNonDeprecatedParsing(self):
        """Test normal parsing is not affected."""
        opts = self.argument_parser.parse_args(self.not_deprecated)

        self.assertFalse(self.warning_patch.called)

        self.assertEqual(self.store_expected, opts.store)
        self.assertTrue(opts.store_true)
        self.assertEqual(self.append_expected, opts.append)

        self.assertIsNone(opts.dep_store)
        self.assertFalse(opts.dep_store_true)
        self.assertIsNone(opts.dep_append)

    def testDeprecatedParsing(self):
        """Test deprecated parsing logs the warning but parses normally."""
        opts = self.argument_parser.parse_args(self.deprecated)

        self.assertTrue(self.warning_patch.called)

        self.assertIsNone(opts.store)
        self.assertFalse(opts.store_true)
        self.assertIsNone(opts.append)

        self.assertEqual(self.dep_store_expected, opts.dep_store)
        self.assertTrue(opts.dep_store_true)
        self.assertEqual(self.dep_append_expected, opts.dep_append)

    def testMixedParsing(self):
        """Test parsing a mix of arguments."""
        opts = self.argument_parser.parse_args(self.mixed)

        self.assertTrue(self.warning_patch.called)

        self.assertEqual(self.store_expected, opts.store)
        self.assertTrue(opts.store_true)
        self.assertEqual(self.append_expected, opts.append)

        self.assertEqual(self.dep_store_expected, opts.dep_store)
        self.assertTrue(opts.dep_store_true)
        self.assertEqual(self.dep_append_expected, opts.dep_append)


class PathExistsTest(cros_test_lib.TempDirTestCase):
    """Test type=path_exists, dir_exists, and file_exists functionality."""

    def setUp(self):
        cros_test_lib.CreateOnDiskHierarchy(
            self.tempdir,
            (
                "directory/file1",
                "directory/file2",
                "directory/file3",
                "other/",
            ),
        )
        self.dir_path = self.tempdir / "directory"
        self.file_path = self.dir_path / "file1"
        self.link_path = self.tempdir / "other" / "link"
        osutils.SafeSymlink(self.file_path, self.link_path)

    def _ParsePathExists(self, path):
        parser = commandline.ArgumentParser()
        parser.add_argument("--path", type="path_exists")
        return parser.parse_args(["--path", str(path)])

    def _ParseDirectoryExists(self, path):
        parser = commandline.ArgumentParser()
        parser.add_argument("--dir", type="dir_exists")
        return parser.parse_args(["--dir", str(path)])

    def _ParseFileExists(self, path):
        parser = commandline.ArgumentParser()
        parser.add_argument("--file", type="file_exists")
        return parser.parse_args(["--file", str(path)])

    def testExistingPath(self):
        """Test that the path exists."""
        options = self._ParsePathExists(self.file_path)
        self.assertEqual(options.path, self.file_path)

    def testExistingSymlinkPath(self):
        """Test that a path with symlink exists."""
        options = self._ParsePathExists(self.link_path)
        self.assertEqual(options.path, self.file_path)
        self.assertNotEqual(options.path, self.link_path)

    def testMultipleExistingPaths(self):
        """Test that action='append' can be used with type='path_exists'."""
        parser = commandline.ArgumentParser()
        parser.add_argument("--path", action="append", type="path_exists")
        options = parser.parse_args(
            [
                "--path",
                str(self.file_path),
                "--path",
                str(self.dir_path / "file2"),
                "--path",
                str(self.dir_path / "file3"),
            ]
        )
        self.assertEqual(len(options.path), 3)
        self.assertIn(self.file_path, options.path)

    def testExistingFile(self):
        """Test that the path exists and is a file."""
        options = self._ParseFileExists(self.file_path)
        self.assertEqual(options.file, self.file_path)

    def testExistingDirectory(self):
        """Test that the path exists and is a directory."""
        options = self._ParseDirectoryExists(self.dir_path)
        self.assertEqual(options.dir, self.dir_path)

    def testNonExistingPath(self):
        """Test that an error occurs when the path does not exist."""
        self.assertRaises2(SystemExit, self._ParsePathExists, "no/such/path")

    def testNonExistingDirectory(self):
        """Test that an error occurs when a directory path does not exist."""
        self.assertRaises2(
            SystemExit, self._ParseDirectoryExists, "no/such/directory/"
        )

    def testNonExistingFile(self):
        """Test that an error occurs when a file path does not exist."""
        self.assertRaises2(SystemExit, self._ParseFileExists, "no/such/file")

    def testExistingPathIsNotDirectory(self):
        """Verify an error occurs when an existing path is not a directory."""
        self.assertRaises2(
            SystemExit, self._ParseDirectoryExists, self.file_path
        )

    def testExistingPathIsNotFile(self):
        """Test that an error occurs when an existing path is not a file."""
        self.assertRaises2(SystemExit, self._ParseFileExists, self.dir_path)


class DryRunTests(cros_test_lib.TestCase):
    """Check --dry-run integration."""

    def testNoDryRun(self):
        """Do not include --dry-run by default."""
        parser = commandline.ArgumentParser()
        opts = parser.parse_args([])
        self.assertFalse(hasattr(opts, "dryrun"))
        self.assertRaises2(SystemExit, parser.parse_args, ["--dry-run"])

    def testDryRun(self):
        """Verify --dry-run is included when requested."""
        parser = commandline.ArgumentParser(dryrun=True)
        opts = parser.parse_args([])
        self.assertFalse(opts.dryrun)
        opts = parser.parse_args(["-n"])
        self.assertTrue(opts.dryrun)
        opts = parser.parse_args(["--dry-run"])
        self.assertTrue(opts.dryrun)


# Split parameters into sep var to make test output easier to read.
_PARSE_EMAIL_TEST_CASES = (
    ("f@example.com", True),
    ("vapier@google.com", True),
    ("vapier@chromium.org", True),
    ("", False),
    ("f", False),
    ("f@f", False),
    ("f@f.f", False),
    ("example.com", False),
    ("@example.com", False),
    ("!@example.com", False),
    ("user@example.coooooooooooooooooom", False),
)


@pytest.mark.parametrize("email, valid", _PARSE_EMAIL_TEST_CASES)
def test_parse_email(email: str, valid: bool) -> None:
    """Verify argparse type='email'."""
    parser = commandline.ArgumentParser()
    parser.add_argument("-e", type="email")

    if valid:
        commandline.ParseEmail(email)
        parser.parse_args(["-e", email])
    else:
        with pytest.raises(ValueError):
            commandline.ParseEmail(email)

        with pytest.raises(SystemExit) as excinfo:
            parser.parse_args(["-e", email])
        assert excinfo.value.code != 0
