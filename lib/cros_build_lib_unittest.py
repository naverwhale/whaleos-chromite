# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the cros_build_lib module."""

import builtins
import contextlib
import datetime
import difflib
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
from unittest import mock

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils


class RunCommandErrorStrTest(cros_test_lib.TestCase):
    """Test that RunCommandError __str__ works as expected."""

    def testNonUTF8Characters(self):
        """Test that non-UTF8 characters do not kill __str__"""
        result = cros_build_lib.run(["ls", "/does/not/exist"], check=False)
        rce = cros_build_lib.RunCommandError("\x81", result)
        str(rce)


class CmdToStrTest(cros_test_lib.TestCase):
    """Test the CmdToStr function."""

    def setUp(self):
        self.differ = difflib.Differ()

    def _assertEqual(self, func, test_input, test_output, result):
        """Like assertEqual but with built-in diff support."""
        msg = "Expected %s to translate %r to %r, but got %r" % (
            func,
            test_input,
            test_output,
            result,
        )
        self.assertEqual(test_output, result, msg)

    def _testData(self, functor, tests, check_type=True):
        """Process an iterable of test data."""
        for test_output, test_input in tests:
            result = functor(test_input)
            self._assertEqual(functor.__name__, test_input, test_output, result)

            if check_type:
                # Also make sure the result is a string, otherwise the %r output
                # will include a "u" prefix and that is not good for logging.
                self.assertEqual(type(test_output), str)

    def testShellQuote(self):
        """Basic ShellQuote tests."""
        # Tuples of (expected output string, input data).
        tests_quote = (
            ("''", ""),
            ("a", "a"),
            ("'a b c'", "a b c"),
            ("'a\tb'", "a\tb"),
            ("'a\nb'", "a\nb"),
            ("'/a$file'", "/a$file"),
            ("'/a#file'", "/a#file"),
            ("""'b"c'""", 'b"c'),
            ("'a@()b'", "a@()b"),
            ("j%k", "j%k"),
            (r'''"s'a\$va\\rs"''', r"s'a$va\rs"),
            (r'''"\\'\\\""''', r'''\'\"'''),
            (r'''"'\\\$"''', r"""'\$"""),
        )

        bytes_quote = (
            # Since we allow passing bytes down, quote them too.
            ("bytes", b"bytes"),
            ("'by tes'", b"by tes"),
            ("bytes", "bytes"),
            ("'by tes'", "by tes"),
        )

        # Expected input output specific to ShellUnquote. This string cannot be
        # produced by ShellQuote but is still a valid bash escaped string.
        tests_unquote = ((r"""\$""", r'''"\\$"'''),)

        def aux(s):
            return cros_build_lib.ShellUnquote(cros_build_lib.ShellQuote(s))

        # We can only go one way bytes->string.
        self._testData(cros_build_lib.ShellQuote, bytes_quote)
        self._testData(aux, [(x, x) for x, _ in bytes_quote], False)

        self._testData(cros_build_lib.ShellQuote, tests_quote)
        self._testData(cros_build_lib.ShellUnquote, tests_unquote)

        # Test that the operations are reversible.
        self._testData(aux, [(x, x) for x, _ in tests_quote], False)
        self._testData(aux, [(x, x) for _, x in tests_quote], False)

    def testShellQuoteOjbects(self):
        """Test objects passed to ShellQuote."""
        self.assertEqual("/", cros_build_lib.ShellQuote(Path("/")))
        self.assertEqual("None", cros_build_lib.ShellQuote(None))
        self.assertNotEqual("", cros_build_lib.ShellQuote)

    def testCmdToStr(self):
        # Dict of expected output strings to input lists.
        tests = (
            (r"a b", ["a", "b"]),
            (r"'a b' c", ["a b", "c"]),
            (r'''a "b'c"''', ["a", "b'c"]),
            (r'''a "/'\$b" 'a b c' "xy'z"''', ["a", "/'$b", "a b c", "xy'z"]),
            ("", []),
            ("a b c", [b"a", "b", "c"]),
            ("bad None cmd", ["bad", None, "cmd"]),
        )
        self._testData(cros_build_lib.CmdToStr, tests)


class TestCalledProcessError(cros_test_lib.TestCase):
    """Test CalledProcessError API."""

    def testOutputStdout(self):
        """Make sure .output is removed and .stdout works."""
        e = cros_build_lib.CalledProcessError(
            0, ["true"], stdout="STDOUT", stderr="STDERR"
        )
        with self.assertRaises(AttributeError):
            assert e.output is None
        assert e.stdout == "STDOUT"
        assert e.stderr == "STDERR"

        e.stdout = "STDout"
        e.stderr = "STDerr"
        with self.assertRaises(AttributeError):
            assert e.output is None
        assert e.stdout == "STDout"
        assert e.stderr == "STDerr"


class TestRunCommandNoMock(cros_test_lib.TestCase):
    """Class that tests run by not mocking subprocess.Popen"""

    def testErrorCodeNotRaisesError(self):
        """Don't raise exception when command returns non-zero exit code."""
        result = cros_build_lib.run(["ls", "/does/not/exist"], check=False)
        self.assertTrue(result.returncode != 0)

    def testMissingCommandRaisesError(self):
        """Raise error when command is not found."""
        self.assertRaises(
            cros_build_lib.RunCommandError,
            cros_build_lib.run,
            ["/does/not/exist"],
            check=True,
        )
        self.assertRaises(
            cros_build_lib.RunCommandError,
            cros_build_lib.run,
            ["/does/not/exist"],
            check=False,
        )

    def testDryRun(self):
        """Verify dryrun doesn't run the real command."""
        # Check exit & output when not captured.
        result = cros_build_lib.run(["false"], dryrun=True)
        self.assertEqual(0, result.returncode)
        self.assertEqual(None, result.stdout)
        self.assertEqual(None, result.stderr)

        # Check captured binary output.
        result = cros_build_lib.run(
            ["echo", "hi"], dryrun=True, capture_output=True
        )
        self.assertEqual(0, result.returncode)
        self.assertEqual(b"", result.stdout)
        self.assertEqual(b"", result.stderr)

        # Check captured text output.
        result = cros_build_lib.run(
            ["echo", "hi"], dryrun=True, capture_output=True, encoding="utf-8"
        )
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertEqual("", result.stderr)

        # Check captured merged output.
        result = cros_build_lib.run(
            ["echo", "hi"], dryrun=True, stdout=True, stderr=subprocess.STDOUT
        )
        self.assertEqual(0, result.returncode)
        self.assertEqual(b"", result.stdout)
        self.assertEqual(None, result.stderr)

    def testInputBytes(self):
        """Verify input argument when it is bytes."""
        for data in (b"", b"foo", b"bar\nhigh"):
            result = cros_build_lib.run(
                ["cat"], input=data, capture_output=True
            )
            self.assertEqual(result.stdout, data)

    def testInputBytesEncoding(self):
        """Verify bytes input argument when encoding is set."""
        for data in (b"", b"foo", b"bar\nhigh"):
            result = cros_build_lib.run(
                ["cat"], input=data, encoding="utf-8", capture_output=True
            )
            self.assertEqual(result.stdout, data.decode("utf-8"))

    def testInputString(self):
        """Verify input argument when it is a string."""
        for data in ("", "foo", "bar\nhigh"):
            result = cros_build_lib.run(
                ["cat"], input=data, capture_output=True
            )
            self.assertEqual(result.stdout, data.encode("utf-8"))

    def testInputStringEncoding(self):
        """Verify bytes input argument when encoding is set."""
        for data in ("", "foo", "bar\nhigh"):
            result = cros_build_lib.run(
                ["cat"], input=data, encoding="utf-8", capture_output=True
            )
            self.assertEqual(result.stdout, data)

    def testInputFileObject(self):
        """Verify input argument when it is a file object."""
        result = cros_build_lib.run(
            ["cat"],
            # TODO(b/236161656): Fix.
            # pylint: disable-next=consider-using-with
            input=open("/dev/null", encoding="utf-8"),
            capture_output=True,
        )
        self.assertEqual(result.stdout, b"")

        with open(__file__, encoding="utf-8") as f:
            result = cros_build_lib.run(["cat"], input=f, capture_output=True)
            self.assertEqual(
                result.stdout, osutils.ReadFile(__file__, mode="rb")
            )

    def testInputFileDescriptor(self):
        """Verify input argument when it is a file descriptor."""
        with open("/dev/null", encoding="utf-8") as f:
            result = cros_build_lib.run(
                ["cat"], input=f.fileno(), capture_output=True
            )
            self.assertEqual(result.stdout, b"")

        with open(__file__, encoding="utf-8") as f:
            result = cros_build_lib.run(
                ["cat"], input=f.fileno(), capture_output=True
            )
            self.assertEqual(
                result.stdout, osutils.ReadFile(__file__, mode="rb")
            )

    def testMixedEncodingCommand(self):
        """Verify cmd can mix bytes & strings."""
        result = cros_build_lib.run(
            [b"echo", "hi", "ß"], capture_output=True, encoding="utf-8"
        )
        self.assertEqual(result.stdout, "hi ß\n")

    def testEncodingBinaryOutput(self):
        """Verify encoding=None output handling."""
        result = cros_build_lib.run(
            b"echo o\xff ut; echo e\xff rr >&2", shell=True, capture_output=True
        )
        self.assertEqual(result.stdout, b"o\xff ut\n")
        self.assertEqual(result.stderr, b"e\xff rr\n")

    def testEncodingUtf8Output(self):
        """Verify encoding='utf-8' output handling."""
        result = cros_build_lib.run(
            ["echo", "ß"], capture_output=True, encoding="utf-8"
        )
        self.assertEqual(result.stdout, "ß\n")

    def testEncodingStrictInvalidUtf8Output(self):
        """Verify encoding='utf-8' output with invalid content."""
        with self.assertRaises(UnicodeDecodeError):
            cros_build_lib.run(
                ["echo", b"\xff"], capture_output=True, encoding="utf-8"
            )
        with self.assertRaises(UnicodeDecodeError):
            cros_build_lib.run(
                ["echo", b"\xff"],
                capture_output=True,
                encoding="utf-8",
                errors="strict",
            )

    def testEncodingReplaceInvalidUtf8Output(self):
        """Verify invalid content's encoding='utf-8' errors='replace' output."""
        result = cros_build_lib.run(
            ["echo", b"S\xffE"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(result.stdout, "S\ufffdE\n")

    def testCommandArgsValidTypes(self):
        """Verify command args can be of known types."""
        # Support bytes, strings, and Path objects.
        result = cros_build_lib.run(
            ["echo", b"bytes", Path("path")], capture_output=True
        )
        self.assertEqual(result.stdout, b"bytes path\n")

    def testCommandArgsInvalidTypes(self):
        """Verify command args with invalid types are rejected."""
        with self.assertRaises(TypeError):
            cros_build_lib.run(["echo", 1234], capture_output=True)

    def testExecutable(self):
        """Verify executable arg is handled correctly."""
        # This should run the echo program.
        result = cros_build_lib.run(
            ["asdf", "1234"],
            executable=shutil.which("echo"),
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(result.stdout, "1234\n")

        # The shell should see the custom argv[0].
        result = cros_build_lib.run(
            ["-asdf", "-c", 'printf %s "$0"'],
            executable=shutil.which("sh"),
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(result.stdout, "-asdf")


def _ForceLoggingLevel(functor):
    def inner(*args, **kwargs):
        logger = logging.getLogger()
        current = logger.getEffectiveLevel()
        try:
            logger.setLevel(logging.INFO)
            return functor(*args, **kwargs)
        finally:
            logger.setLevel(current)

    return inner


class TestRunCommand(cros_test_lib.MockTestCase):
    """Tests of run functionality."""

    def setUp(self):
        # These ENV variables affect run behavior, hide them.
        self._old_envs = {
            e: os.environ.pop(e)
            for e in constants.ENV_PASSTHRU
            if e in os.environ
        }

        # Get the original value for SIGINT so our signal() mock can return the
        # correct thing.
        self._old_sigint = signal.getsignal(signal.SIGINT)

        # Mock the return value of Popen().
        self.stdin = None
        self.stderr = b"test error"
        self.stdout = b"test output"
        self.proc_mock = mock.MagicMock(
            returncode=0, communicate=self._Communicate
        )
        self.popen_mock = self.PatchObject(
            cros_build_lib, "_Popen", return_value=self.proc_mock
        )

        self.signal_mock = self.PatchObject(signal, "signal")
        self.getsignal_mock = self.PatchObject(signal, "getsignal")

    def tearDown(self):
        # Restore hidden ENVs.
        os.environ.update(self._old_envs)

    def _Communicate(self, stdin):
        """Used by mocked _Popen for communicate method.

        This allows us to capture what was passed on input.
        """
        self.stdin = stdin
        return self.stdout, self.stderr

    @contextlib.contextmanager
    def _MockChecker(self, cmd, **kwargs):
        """Verify the mocks we set up"""
        ignore_sigint = kwargs.pop("ignore_sigint", False)

        # Make some arbitrary functors we can pretend are signal handlers.
        # Note that these are intentionally defined on the fly via lambda-
        # this is to ensure that they're unique to each run.
        sigint_suppress = lambda signum, frame: None
        sigint_suppress.__name__ = "sig_ign_sigint"
        normal_sigint = lambda signum, frame: None
        normal_sigint.__name__ = "sigint"
        normal_sigterm = lambda signum, frame: None
        normal_sigterm.__name__ = "sigterm"

        # Set up complicated mock for signal.signal().
        def _SignalChecker(sig, _action):
            """Return the right signal values so we can check the calls."""
            if sig == signal.SIGINT:
                return sigint_suppress if ignore_sigint else normal_sigint
            elif sig == signal.SIGTERM:
                return normal_sigterm
            else:
                raise ValueError("unknown sig %i" % sig)

        self.signal_mock.side_effect = _SignalChecker

        # Set up complicated mock for signal.getsignal().
        def _GetsignalChecker(sig):
            """Return the right signal values so we can check the calls."""
            if sig == signal.SIGINT:
                return sigint_suppress if ignore_sigint else normal_sigint
            elif sig == signal.SIGTERM:
                return normal_sigterm
            else:
                raise ValueError("unknown sig %i" % sig)

        self.getsignal_mock.side_effect = _GetsignalChecker

        # Let the body of code run, then check the signal behavior afterwards.
        # We don't get visibility into signal ordering vs command execution,
        # but it's kind of hard to mess up that, so we won't bother.
        yield

        class RejectSigIgn:
            """Make sure the signal action is not SIG_IGN."""

            def __eq__(self, other):
                return other != signal.SIG_IGN

        # Verify the signals checked/setup are correct.
        if ignore_sigint:
            self.signal_mock.assert_has_calls(
                [
                    mock.call(signal.SIGINT, signal.SIG_IGN),
                    mock.call(signal.SIGTERM, RejectSigIgn()),
                    mock.call(signal.SIGINT, sigint_suppress),
                    mock.call(signal.SIGTERM, normal_sigterm),
                ]
            )
        else:
            self.signal_mock.assert_has_calls(
                [
                    mock.call(signal.SIGINT, RejectSigIgn()),
                    mock.call(signal.SIGTERM, RejectSigIgn()),
                    mock.call(signal.SIGINT, normal_sigint),
                    mock.call(signal.SIGTERM, normal_sigterm),
                ]
            )
        self.assertEqual(self.getsignal_mock.call_count, 2)

        # Verify various args are passed down to the real command.
        pargs = self.popen_mock.call_args[0][0]
        self.assertEqual(cmd, pargs)

        # Verify various kwargs are passed down to the real command.
        pkwargs = self.popen_mock.call_args[1]
        for key in ("cwd", "stdin", "stdout", "stderr"):
            kwargs.setdefault(key, None)
        kwargs.setdefault("shell", False)
        kwargs.setdefault("env", mock.ANY)
        kwargs["close_fds"] = True
        self.longMessage = True
        # TODO(b/236161656): Fix.
        # pylint: disable-next=consider-using-dict-items
        for key in kwargs.keys():
            self.assertEqual(
                kwargs[key], pkwargs[key], msg="kwargs[%s] mismatch" % key
            )

    def _AssertCrEqual(self, expected, actual):
        """Helper method to compare two CompletedProcess objects.

        This is needed since assertEqual does not know how to compare two
        CompletedProcess objects.

        Args:
            expected: a CompletedProcess object, expected result.
            actual: a CompletedProcess object, actual result.
        """
        self.assertEqual(expected.args, actual.args)
        self.assertEqual(expected.stderr, actual.stderr)
        self.assertEqual(expected.stdout, actual.stdout)
        self.assertEqual(expected.returncode, actual.returncode)

    @_ForceLoggingLevel
    def _TestCmd(self, cmd, real_cmd, sp_kv=None, rc_kv=None, sudo=False):
        """Factor out common setup logic for testing run().

        Args:
            cmd: a string or an array of strings that will be passed to run.
            real_cmd: the real command we expect run to call (might be modified
                to have enter_chroot).
            sp_kv: key-value pairs passed to subprocess.Popen().
            rc_kv: key-value pairs passed to run().
            sudo: use sudo_run() rather than run().
        """
        if sp_kv is None:
            sp_kv = {}
        if rc_kv is None:
            rc_kv = {}

        stdout = None
        stderr = None
        if rc_kv.get("stdout") or rc_kv.get("capture_output"):
            stdout = self.stdout
        if rc_kv.get("stderr") or rc_kv.get("capture_output"):
            stderr = self.stderr

        expected_result = cros_build_lib.CompletedProcess(
            args=real_cmd,
            stdout=stdout,
            stderr=stderr,
            returncode=self.proc_mock.returncode,
        )

        arg_dict = {}
        for attr in (
            "close_fds",
            "cwd",
            "env",
            "stdin",
            "stdout",
            "stderr",
            "shell",
        ):
            if attr in sp_kv:
                arg_dict[attr] = sp_kv[attr]
            else:
                if attr == "close_fds":
                    arg_dict[attr] = True
                elif attr == "shell":
                    arg_dict[attr] = False
                else:
                    arg_dict[attr] = None

        if sudo:
            runcmd = cros_build_lib.sudo_run
        else:
            runcmd = cros_build_lib.run
        with self._MockChecker(
            real_cmd, ignore_sigint=rc_kv.get("ignore_sigint"), **sp_kv
        ):
            actual_result = runcmd(cmd, **rc_kv)

        # If run was called with encoding, we need to encode the result
        # before making a comparison below, as the underlying data we are
        # passing to _Popen is stored as bytes.
        if "encoding" in rc_kv:
            encoding = rc_kv["encoding"]
            if actual_result.stdout is not None:
                actual_result.stdout = actual_result.stdout.encode(encoding)
            if actual_result.stderr is not None:
                actual_result.stderr = actual_result.stderr.encode(encoding)

        self._AssertCrEqual(expected_result, actual_result)

    def testReturnCodeZeroWithArrayCmd(self, ignore_sigint=False):
        """--enter_chroot=False and --cmd is an array of strings.

        Parameterized so this can also be used by some other tests w/ alternate
        params to run().

        Args:
            ignore_sigint: If True, we'll tell run to ignore sigint.
        """
        self.proc_mock.returncode = 0
        cmd_list = ["foo", "bar", "roger"]
        self._TestCmd(
            cmd_list, cmd_list, rc_kv=dict(ignore_sigint=ignore_sigint)
        )

    def testSignalRestoreNormalCase(self):
        """Test run() properly sets/restores sigint.  Normal case."""
        self.testReturnCodeZeroWithArrayCmd(ignore_sigint=True)

    def testReturnCodeZeroWithArrayCmdEnterChroot(self):
        """--enter_chroot=True and --cmd is an array of strings."""
        self.proc_mock.returncode = 0
        cmd_list = ["foo", "bar", "roger"]
        real_cmd = cmd_list
        if not cros_build_lib.IsInsideChroot():
            real_cmd = ["cros_sdk", "--"] + cmd_list
        self._TestCmd(cmd_list, real_cmd, rc_kv=dict(enter_chroot=True))

    @_ForceLoggingLevel
    def testCommandFailureRaisesError(self, ignore_sigint=False):
        """Verify error raised by communicate() is caught.

        Parameterized so this can also be used by some other tests w/ alternate
        params to run().

        Args:
            ignore_sigint: If True, we'll tell run to ignore sigint.
        """
        cmd = "test cmd"
        self.proc_mock.returncode = 1
        with self._MockChecker(
            ["/bin/bash", "-c", cmd], ignore_sigint=ignore_sigint
        ):
            self.assertRaises(
                cros_build_lib.RunCommandError,
                cros_build_lib.run,
                cmd,
                shell=True,
                ignore_sigint=ignore_sigint,
                check=True,
            )

    @_ForceLoggingLevel
    def testSubprocessCommunicateExceptionRaisesError(
        self, ignore_sigint=False
    ):
        """Verify error raised by communicate() is caught.

        Parameterized so this can also be used by some other tests w/ alternate
        params to run().

        Args:
            ignore_sigint: If True, we'll tell run to ignore sigint.
        """
        cmd = ["test", "cmd"]
        self.proc_mock.communicate = mock.MagicMock(side_effect=ValueError)
        with self._MockChecker(cmd, ignore_sigint=ignore_sigint):
            self.assertRaises(
                ValueError, cros_build_lib.run, cmd, ignore_sigint=ignore_sigint
            )

    def testSignalRestoreExceptionCase(self):
        """Test run() properly sets/restores sigint.  Exception case."""
        self.testSubprocessCommunicateExceptionRaisesError(ignore_sigint=True)

    def testEnvWorks(self):
        """Test run(..., env=xyz) works."""
        # We'll put this bogus environment together, just to make sure
        # subprocess.Popen gets passed it.
        rc_env = {"Tom": "Jerry", "Itchy": "Scratchy"}
        sp_env = dict(rc_env, LC_MESSAGES="C")

        # This is a simple case, copied from testReturnCodeZeroWithArrayCmd()
        self.proc_mock.returncode = 0
        cmd_list = ["foo", "bar", "roger"]

        # Run.  We expect the env= to be passed through from sp
        # (subprocess.Popen) to rc (run).
        self._TestCmd(
            cmd_list, cmd_list, sp_kv=dict(env=sp_env), rc_kv=dict(env=rc_env)
        )

    def testExtraEnvOnlyWorks(self):
        """Test run(..., extra_env=xyz) works."""
        # We'll put this bogus environment together, just to make sure
        # subprocess.Popen gets passed it.
        extra_env = {"Pinky": "Brain"}
        ## This is a little bit circular, since the same logic is used to
        ## compute the value inside, but at least it checks that this happens.
        total_env = os.environ.copy()
        # The core run code forces this too.
        total_env["LC_MESSAGES"] = "C"
        total_env.update(extra_env)

        # This is a simple case, copied from testReturnCodeZeroWithArrayCmd()
        self.proc_mock.returncode = 0
        cmd_list = ["foo", "bar", "roger"]

        # Run.  We expect the env= to be passed through from sp
        # (subprocess.Popen) to rc (run).
        self._TestCmd(
            cmd_list,
            cmd_list,
            sp_kv=dict(env=total_env),
            rc_kv=dict(extra_env=extra_env),
        )

    def testExtraEnvTooWorks(self):
        """Test run(..., env=xy, extra_env=z) works."""
        # We'll put this bogus environment together, just to make sure
        # subprocess.Popen gets passed it.
        env = {"Tom": "Jerry", "Itchy": "Scratchy"}
        extra_env = {"Pinky": "Brain"}
        total_env = {
            "Tom": "Jerry",
            "Itchy": "Scratchy",
            "Pinky": "Brain",
            "LC_MESSAGES": "C",
        }

        # This is a simple case, copied from testReturnCodeZeroWithArrayCmd()
        self.proc_mock.returncode = 0
        cmd_list = ["foo", "bar", "roger"]

        # Run.  We expect the env= to be passed through from sp
        # (subprocess.Popen) to rc (run).
        self._TestCmd(
            cmd_list,
            cmd_list,
            sp_kv=dict(env=total_env),
            rc_kv=dict(env=env, extra_env=extra_env),
        )

    @mock.patch(
        "chromite.lib.cros_build_lib.IsInsideChroot", return_value=False
    )
    def testChrootExtraEnvWorks(self, _inchroot_mock):
        """Test run(..., enter_chroot=True, env=xy, extra_env=z) works."""
        # We'll put this bogus environment together, just to make sure
        # subprocess.Popen gets passed it.
        env = {"Tom": "Jerry", "Itchy": "Scratchy"}
        extra_env = {"Pinky": "Brain"}
        total_env = {
            "Tom": "Jerry",
            "Itchy": "Scratchy",
            "Pinky": "Brain",
            "LC_MESSAGES": "C",
        }

        # This is a simple case, copied from testReturnCodeZeroWithArrayCmd()
        self.proc_mock.returncode = 0
        cmd_list = ["foo", "bar", "roger"]

        # Run.  We expect the env= to be passed through from sp
        # (subprocess.Popen) to rc (run).
        self._TestCmd(
            cmd_list,
            ["cros_sdk", "Pinky=Brain", "--"] + cmd_list,
            sp_kv=dict(env=total_env),
            rc_kv=dict(env=env, extra_env=extra_env, enter_chroot=True),
        )

    def testExceptionEquality(self):
        """Verify equality methods for RunCommandError"""

        c1 = cros_build_lib.CompletedProcess(["ls", "arg"], returncode=1)
        c2 = cros_build_lib.CompletedProcess(["ls", "arg1"], returncode=1)
        c3 = cros_build_lib.CompletedProcess(["ls", "arg"], returncode=2)
        e1 = cros_build_lib.RunCommandError("Message 1", c1)
        e2 = cros_build_lib.RunCommandError("Message 1", c1)
        e_diff_msg = cros_build_lib.RunCommandError("Message 2", c1)
        e_diff_cmd = cros_build_lib.RunCommandError("Message 1", c2)
        e_diff_code = cros_build_lib.RunCommandError("Message 1", c3)

        self.assertEqual(e1, e2)
        self.assertNotEqual(e1, e_diff_msg)
        self.assertNotEqual(e1, e_diff_cmd)
        self.assertNotEqual(e1, e_diff_code)

    def testSudoRunCommand(self):
        """Test sudo_run(...) works."""
        cmd_list = ["foo", "bar", "roger"]
        sudo_list = ["sudo", "--"] + cmd_list
        self.proc_mock.returncode = 0
        self._TestCmd(cmd_list, sudo_list, sudo=True)

    def testSudoRunCommandShell(self):
        """Test sudo_run(..., shell=True) works."""
        cmd = "foo bar roger"
        sudo_list = ["sudo", "--", "/bin/bash", "-c", cmd]
        self.proc_mock.returncode = 0
        self._TestCmd(cmd, sudo_list, sudo=True, rc_kv=dict(shell=True))

    def testSudoRunCommandEnv(self):
        """Test sudo_run(..., extra_env=z) works."""
        cmd_list = ["foo", "bar", "roger"]
        sudo_list = ["sudo", "shucky=ducky", "--"] + cmd_list
        extra_env = {"shucky": "ducky"}
        self.proc_mock.returncode = 0
        self._TestCmd(
            cmd_list, sudo_list, sudo=True, rc_kv=dict(extra_env=extra_env)
        )

    def testSudoRunCommandUser(self):
        """Test sudo_run(..., user='...') works."""
        cmd_list = ["foo", "bar", "roger"]
        sudo_list = ["sudo", "-u", "MMMMMonster", "--"] + cmd_list
        self.proc_mock.returncode = 0
        self._TestCmd(
            cmd_list, sudo_list, sudo=True, rc_kv=dict(user="MMMMMonster")
        )

    def testSudoRunCommandUserShell(self):
        """Test sudo_run(..., user='...', shell=True) works."""
        cmd = "foo bar roger"
        sudo_list = ["sudo", "-u", "MMMMMonster", "--", "/bin/bash", "-c", cmd]
        self.proc_mock.returncode = 0
        self._TestCmd(
            cmd,
            sudo_list,
            sudo=True,
            rc_kv=dict(user="MMMMMonster", shell=True),
        )

    def testInputBytes(self):
        """Test that we can always pass non-UTF-8 bytes as input."""
        cmd_list = ["foo", "bar", "roger"]
        bytes_input = b"\xff"
        self.proc_mock.returncode = 0
        self._TestCmd(
            cmd_list,
            cmd_list,
            sp_kv={"stdin": subprocess.PIPE},
            rc_kv={"input": bytes_input, "encoding": "utf-8"},
        )
        self.assertEqual(self.stdin, bytes_input)

    def testInputString(self):
        """Test that we encode UTF-8 strings passed on input."""
        cmd_list = ["foo", "bar", "roger"]
        unicode_input = "💩"
        self.proc_mock.returncode = 0
        self._TestCmd(
            cmd_list,
            cmd_list,
            sp_kv={"stdin": subprocess.PIPE},
            rc_kv={"input": unicode_input, "encoding": "utf-8"},
        )
        self.assertEqual(self.stdin, unicode_input.encode("utf-8"))

    def testInputStringNoEncoding(self):
        """Verify we encode UTF-8 input strings w/out passing encoding."""
        cmd_list = ["foo", "bar", "roger"]
        unicode_input = "💩"
        self.proc_mock.returncode = 0
        self._TestCmd(
            cmd_list,
            cmd_list,
            sp_kv={"stdin": subprocess.PIPE},
            rc_kv={"input": unicode_input},
        )
        self.assertEqual(self.stdin, unicode_input.encode("utf-8"))


# TODO(crbug.com/1072139): Migrate tests to use 'legacy_capture_output' fixture
#                          once this module is Python 3-only.
class TestRunCommandOutput(
    cros_test_lib.TempDirTestCase, cros_test_lib.OutputTestCase
):
    """Tests of run output options."""

    @_ForceLoggingLevel
    def testLogStdoutToFile(self):
        log = os.path.join(self.tempdir, "output")
        ret = cros_build_lib.run(["echo", "monkeys"], stdout=log)
        self.assertEqual(osutils.ReadFile(log), "monkeys\n")
        self.assertIs(ret.stdout, None)
        self.assertIs(ret.stderr, None)

        os.unlink(log)
        ret = cros_build_lib.run(
            ["sh", "-c", "echo monkeys3 >&2"], stdout=log, stderr=True
        )
        self.assertEqual(ret.stderr, b"monkeys3\n")
        self.assertExists(log)
        self.assertEqual(os.path.getsize(log), 0)

        os.unlink(log)
        ret = cros_build_lib.run(
            ["sh", "-c", "echo monkeys4; echo monkeys5 >&2"],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        self.assertIs(ret.stdout, None)
        self.assertIs(ret.stderr, None)
        self.assertEqual(osutils.ReadFile(log), "monkeys4\nmonkeys5\n")

    @_ForceLoggingLevel
    def testLogStderrToFile(self):
        log = os.path.join(self.tempdir, "output")
        ret = cros_build_lib.run(["sh", "-c", "echo monkeys >&2"], stderr=log)
        self.assertEqual(osutils.ReadFile(log), "monkeys\n")
        self.assertIs(ret.stdout, None)
        self.assertIs(ret.stderr, None)

    @_ForceLoggingLevel
    def testLogStdoutToFileWithOrWithoutAppend(self):
        log = os.path.join(self.tempdir, "output")
        ret = cros_build_lib.run(["echo", "monkeys"], stdout=log)
        self.assertEqual(osutils.ReadFile(log), "monkeys\n")
        self.assertIs(ret.stdout, None)
        self.assertIs(ret.stderr, None)

        # Without append
        ret = cros_build_lib.run(["echo", "monkeys2"], stdout=log)
        self.assertEqual(osutils.ReadFile(log), "monkeys2\n")
        self.assertIs(ret.stdout, None)
        self.assertIs(ret.stderr, None)

        # With append
        ret = cros_build_lib.run(
            ["echo", "monkeys3"], append_to_file=True, stdout=log
        )
        self.assertEqual(osutils.ReadFile(log), "monkeys2\nmonkeys3\n")
        self.assertIs(ret.stdout, None)
        self.assertIs(ret.stderr, None)

    def testOutputPath(self):
        """Check stdout=/stderr= works with Path objects."""
        stdout = self.tempdir / "stdout"
        stderr = self.tempdir / "stderr"
        cros_build_lib.run(
            ["sh", "-c", "echo out; echo err >&2"],
            stdout=stdout,
            stderr=stderr,
        )
        self.assertEqual(stdout.read_bytes(), b"out\n")
        self.assertEqual(stderr.read_bytes(), b"err\n")

    def testOutputFileHandle(self):
        """Verify writing to existing file handles."""
        stdout = os.path.join(self.tempdir, "stdout")
        stderr = os.path.join(self.tempdir, "stderr")
        with open(stdout, "wb") as outfp:
            with open(stderr, "wb") as errfp:
                cros_build_lib.run(
                    ["sh", "-c", "echo out; echo err >&2"],
                    stdout=outfp,
                    stderr=errfp,
                )
        self.assertEqual("out\n", osutils.ReadFile(stdout))
        self.assertEqual("err\n", osutils.ReadFile(stderr))

    # TODO(crbug.com/1072139): Re-enable this test and migrate away from using
    #                          OutputCapturer once this module is Python 3 only.
    @cros_test_lib.pytestmark_skip
    def testRunCommandAtNoticeLevel(self):
        """Ensure that run prints output when mute_output is False."""
        # Needed by cros_sdk and brillo/cros chroot.
        with self.OutputCapturer():
            cros_build_lib.run(
                ["echo", "foo"],
                check=False,
                print_cmd=False,
                debug_level=logging.NOTICE,
            )
        self.AssertOutputContainsLine("foo")

    def testRunCommandRedirectStdoutStderrOnCommandError(self):
        """Tests that stderr is captured when run raises."""
        with self.assertRaises(cros_build_lib.RunCommandError) as cm:
            cros_build_lib.run(["cat", "/"], stderr=True)
        self.assertIsNotNone(cm.exception.stderr)
        self.assertNotEqual("", cm.exception.stderr)

    def _CaptureLogOutput(self, cmd, **kwargs):
        """Capture logging output of run."""
        log = os.path.join(self.tempdir, "output")
        fh = logging.FileHandler(log)
        fh.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(fh)
        cros_build_lib.run(cmd, **kwargs)
        logging.getLogger().removeHandler(fh)
        output = osutils.ReadFile(log)
        fh.close()
        return output

    @_ForceLoggingLevel
    def testLogOutput(self):
        """Normal log_output, stdout followed by stderr."""
        cmd = "echo Greece; echo Italy >&2; echo Spain"
        log_output = (
            "run: /bin/bash -c "
            "'echo Greece; echo Italy >&2; echo Spain'\n"
            "(stdout):\nGreece\nSpain\n\n(stderr):\nItaly\n\n"
        )
        output = self._CaptureLogOutput(
            cmd, shell=True, log_output=True, encoding="utf-8"
        )
        self.assertEqual(output, log_output)


class HelperMethodSimpleTests(cros_test_lib.OutputTestCase):
    """Tests for various helper methods without using mocks."""

    def testUserDateTime(self):
        """Test with a raw time value."""
        expected = "Mon, 16 Jun 1980 05:03:20 -0700 (PDT)"
        with cros_test_lib.SetTimeZone("US/Pacific"):
            timeval = 330005000
            self.assertEqual(
                cros_build_lib.UserDateTimeFormat(timeval=timeval), expected
            )

    def testUserDateTimeDateTime(self):
        """Test with a datetime object."""
        expected = "Mon, 16 Jun 1980 00:00:00 -0700 (PDT)"
        with cros_test_lib.SetTimeZone("US/Pacific"):
            timeval = datetime.datetime(1980, 6, 16)
            self.assertEqual(
                cros_build_lib.UserDateTimeFormat(timeval=timeval), expected
            )

    def testUserDateTimeDateTimeInWinter(self):
        """Test that we correctly switch from PDT to PST."""
        expected = "Wed, 16 Jan 1980 00:00:00 -0800 (PST)"
        with cros_test_lib.SetTimeZone("US/Pacific"):
            timeval = datetime.datetime(1980, 1, 16)
            self.assertEqual(
                cros_build_lib.UserDateTimeFormat(timeval=timeval), expected
            )

    def testUserDateTimeDateTimeInEST(self):
        """Test that we correctly switch from PDT to EST."""
        expected = "Wed, 16 Jan 1980 00:00:00 -0500 (EST)"
        with cros_test_lib.SetTimeZone("US/Eastern"):
            timeval = datetime.datetime(1980, 1, 16)
            self.assertEqual(
                cros_build_lib.UserDateTimeFormat(timeval=timeval), expected
            )

    def testUserDateTimeCurrentTime(self):
        """Test that we can get the current time."""
        cros_build_lib.UserDateTimeFormat()

    def testParseUserDateTimeFormat(self):
        stringtime = cros_build_lib.UserDateTimeFormat(100000.0)
        self.assertEqual(
            cros_build_lib.ParseUserDateTimeFormat(stringtime), 100000.0
        )

    def testGetRandomString(self):
        """Verify it looks valid."""
        data = cros_build_lib.GetRandomString()
        self.assertRegex(data, r"^[a-z0-9]+$")
        self.assertEqual(32, len(data))

    def testMachineDetails(self):
        """Verify we don't crash."""
        contents = cros_build_lib.MachineDetails()
        self.assertNotEqual(contents, "")
        self.assertEqual(contents[-1], "\n")


class TestInput(cros_test_lib.MockOutputTestCase):
    """Tests of input gathering functionality."""

    def testBooleanPrompt(self):
        """Verify BooleanPrompt() full behavior."""
        m = self.PatchObject(builtins, "input")

        m.return_value = ""
        self.assertTrue(cros_build_lib.BooleanPrompt())
        self.assertFalse(cros_build_lib.BooleanPrompt(default=False))

        m.return_value = "yes"
        self.assertTrue(cros_build_lib.BooleanPrompt())
        m.return_value = "ye"
        self.assertTrue(cros_build_lib.BooleanPrompt())
        m.return_value = "y"
        self.assertTrue(cros_build_lib.BooleanPrompt())

        m.return_value = "no"
        self.assertFalse(cros_build_lib.BooleanPrompt())
        m.return_value = "n"
        self.assertFalse(cros_build_lib.BooleanPrompt())

    def testBooleanShellValue(self):
        """Verify BooleanShellValue() inputs work as expected"""
        for v in (None,):
            self.assertTrue(cros_build_lib.BooleanShellValue(v, True))
            self.assertFalse(cros_build_lib.BooleanShellValue(v, False))

        for v in (1234, "", "akldjsf", '"'):
            self.assertRaises(
                ValueError, cros_build_lib.BooleanShellValue, v, True
            )
            self.assertTrue(cros_build_lib.BooleanShellValue(v, True, msg=""))
            self.assertFalse(cros_build_lib.BooleanShellValue(v, False, msg=""))

        for v in (
            "yes",
            "YES",
            "YeS",
            "y",
            "Y",
            "1",
            "true",
            "True",
            "TRUE",
        ):
            self.assertTrue(cros_build_lib.BooleanShellValue(v, True))
            self.assertTrue(cros_build_lib.BooleanShellValue(v, False))

        for v in (
            "no",
            "NO",
            "nO",
            "n",
            "N",
            "0",
            "false",
            "False",
            "FALSE",
        ):
            self.assertFalse(cros_build_lib.BooleanShellValue(v, True))
            self.assertFalse(cros_build_lib.BooleanShellValue(v, False))

    def testGetChoiceLists(self):
        """Verify GetChoice behavior w/lists."""
        m = self.PatchObject(builtins, "input")

        m.return_value = "1"
        ret = cros_build_lib.GetChoice("title", ["a", "b", "c"])
        self.assertEqual(ret, 1)

    def testGetChoiceGenerator(self):
        """Verify GetChoice behavior w/generators."""
        m = self.PatchObject(builtins, "input")

        m.return_value = "2"
        ret = cros_build_lib.GetChoice("title", list(range(3)))
        self.assertEqual(ret, 2)

    def testGetChoiceWindow(self):
        """Verify GetChoice behavior w/group_size set."""
        m = self.PatchObject(builtins, "input")

        cnt = [0]

        def _Gen():
            while True:
                cnt[0] += 1
                yield "a"

        m.side_effect = ["\n", "2"]
        ret = cros_build_lib.GetChoice("title", _Gen(), group_size=2)
        self.assertEqual(ret, 2)

        # Verify we showed the correct number of times.
        self.assertEqual(cnt[0], 5)


class Test_iflatten_instance(cros_test_lib.TestCase):
    """Test iflatten_instance function."""

    def test_it(self):
        f = lambda x, **kwargs: list(
            cros_build_lib.iflatten_instance(x, **kwargs)
        )
        self.assertEqual([1, 2], f([1, 2]))
        self.assertEqual([1, "2a"], f([1, "2a"]))
        self.assertEqual([1, 2, "b"], f([1, [2, "b"]]))
        self.assertEqual(
            [1, 2, "f", "d", "a", "s"],
            f([1, 2, ("fdas",)], terminate_on_kls=int),
        )
        self.assertEqual([""], f(""))
        self.assertEqual([b""], f(b""))
        self.assertEqual([b"1234"], f(b"1234"))
        self.assertEqual([b"12", b"34"], f([b"12", b"34"]))


class TestAssertRootUserCheck(cros_test_lib.MockTestCase):
    """Tests root/Non-root user functionality for a root user."""

    def setUp(self):
        self.geteuid_mock = self.PatchObject(os, "geteuid", return_value=0)

    def testAssertNonRootUserForRoot(self):
        """Verify AssertNonRootUser raises an exception"""
        self.assertRaises(
            cros_build_lib.DieSystemExit, cros_build_lib.AssertNonRootUser
        )

    def testAssertRootUserForRoot(self):
        """Verify AssertRootUser doesn't raise an exception"""
        cros_build_lib.AssertRootUser()


class TestAssertNonRootUserCheck(cros_test_lib.MockTestCase):
    """Tests root/Non-root user functionality for a non-root user."""

    def setUp(self):
        self.geteuid_mock = self.PatchObject(os, "geteuid", return_value=20)

    def testAssertNonRootUserforNonRoot(self):
        """Verify AssertNonRootUser doesn't raise an exception"""
        cros_build_lib.AssertNonRootUser()

    def testAssertRootUserforNonRoot(self):
        """Verify AssertRootUser raises an exception"""
        self.assertRaises(
            cros_build_lib.DieSystemExit, cros_build_lib.AssertRootUser
        )


class TarballTests(cros_test_lib.TempDirTestCase):
    """Test tarball handling functions."""

    def setUp(self):
        """Create files/dirs needed for tar test."""
        self.tarball_path = os.path.join(self.tempdir, "test.tar.xz")
        self.inputDir = os.path.join(self.tempdir, "inputs")
        self.inputs = [
            "inputA",
            "inputB",
            "sub/subfile",
            "sub2/subfile",
        ]

        self.inputsWithDirs = [
            "inputA",
            "inputB",
            "sub",
            "sub2",
        ]

        # Create the input files.
        for i in self.inputs:
            osutils.WriteFile(os.path.join(self.inputDir, i), i, makedirs=True)

    def testCreateSuccess(self):
        """Create a tarfile."""
        cros_build_lib.CreateTarball(
            self.tarball_path, self.inputDir, inputs=self.inputs
        )

    def testCreateSuccessWithDirs(self):
        """Create a tarfile."""
        cros_build_lib.CreateTarball(
            self.tarball_path, self.inputDir, inputs=self.inputsWithDirs
        )

    def testCreateSuccessWithTooManyFiles(self):
        """Test a tarfile creation with -T /dev/stdin."""
        # pylint: disable=protected-access
        num_inputs = cros_build_lib._THRESHOLD_TO_USE_T_FOR_TAR + 1
        inputs = ["input%s" % x for x in range(num_inputs)]
        largeInputDir = os.path.join(self.tempdir, "largeinputs")
        for i in inputs:
            osutils.WriteFile(os.path.join(largeInputDir, i), i, makedirs=True)
        cros_build_lib.CreateTarball(
            self.tarball_path, largeInputDir, inputs=inputs
        )

    def testCreateExtractSuccessWithNoCompressionProgram(self):
        """Create a tarfile without any compression, then extract it."""
        path = os.path.join(self.tempdir, "test.tar")
        cros_build_lib.CreateTarball(path, self.inputDir, inputs=self.inputs)
        cros_build_lib.ExtractTarball(path, self.tempdir)

        # Again, but using Path instead of str paths.
        path = Path(path)
        cros_build_lib.CreateTarball(
            path, Path(self.inputDir), inputs=self.inputs
        )
        cros_build_lib.ExtractTarball(path, self.tempdir)

    def testCreateExtractSuccessWithCompressionProgram(self):
        """Create a tarfile with compression, then extract it."""
        tar_files = [
            "test.tar.gz",
            "test.tar.bz2",
            "test.tar.xz",
            "test.tar.zst",
        ]
        dir_path = self.tempdir / "dir"
        dir_path.mkdir()
        D = cros_test_lib.Directory
        dir_structure = [
            D(".", []),
            D("test", ["file1.txt"]),
            D("foo", ["file1.txt"]),
            D("bar", ["file1.txt", "file2.c"]),
        ]
        cros_test_lib.CreateOnDiskHierarchy(dir_path, dir_structure)

        for tar_file in tar_files:
            tar_file_path = self.tempdir / tar_file
            comp = cros_build_lib.CompressionExtToType(tar_file)
            cros_build_lib.CreateTarball(
                tar_file_path, dir_path, compression=comp
            )
            cros_test_lib.VerifyTarball(tar_file_path, dir_structure)

    def testExtractFailureWithMissingFile(self):
        """Verify that stderr from tar is printed if in encounters an error."""
        tarball = "a-tarball-which-does-not-exist.tar.gz"

        try:
            cros_build_lib.ExtractTarball(tarball, self.tempdir)
        except cros_build_lib.TarballError as e:
            # Check to see that tar's error message is printed in the exception.
            self.assertIn("No such file or directory", e.args[0])

    def test_IsTarball(self):
        """Test IsTarball helper function."""
        self.assertTrue(cros_build_lib.IsTarball("file.tar"))
        self.assertTrue(cros_build_lib.IsTarball("file.tar.bz2"))
        self.assertTrue(cros_build_lib.IsTarball("file.tar.gz"))
        self.assertTrue(cros_build_lib.IsTarball("file.tar.xz"))
        self.assertTrue(cros_build_lib.IsTarball("file.tar.zst"))
        self.assertTrue(cros_build_lib.IsTarball("file.tbz"))
        self.assertTrue(cros_build_lib.IsTarball("file.txz"))
        self.assertFalse(cros_build_lib.IsTarball("file.txt"))
        self.assertFalse(cros_build_lib.IsTarball("file.tart"))
        self.assertFalse(cros_build_lib.IsTarball("file.bz2"))


# Tests for tar exceptions.
class FailedCreateTarballExceptionTests(
    cros_test_lib.TempDirTestCase, cros_test_lib.LoggingTestCase
):
    """Tests exception handling for CreateTarball."""

    def setUp(self):
        self.inputDir = os.path.join(self.tempdir, "BadInputDirectory")

    def testSuccess(self):
        """Verify tarball creation when cwd and target dir exist."""
        target_dir = os.path.join(self.tempdir, "target_dir")
        target_file = os.path.join(target_dir, "stuff.tar")
        osutils.SafeMakedirs(target_dir)
        working_dir = os.path.join(self.tempdir, "working_dir")
        osutils.SafeMakedirs(working_dir)
        osutils.WriteFile(os.path.join(working_dir, "file1.txt"), "file1")
        osutils.WriteFile(os.path.join(working_dir, "file2.txt"), "file2")
        cros_build_lib.CreateTarball(target_file, working_dir)
        target_contents = os.listdir(target_dir)
        self.assertEqual(target_contents, ["stuff.tar"])

    def testFailureBadTarget(self):
        """Verify expected error when target does not exist."""
        target_dir = os.path.join(self.tempdir, "target_dir")
        target_file = os.path.join(target_dir, "stuff.tar")
        working_dir = os.path.join(self.tempdir, "working_dir")
        osutils.SafeMakedirs(working_dir)
        with cros_test_lib.LoggingCapturer() as logs:
            with self.assertRaises(cros_build_lib.TarballError):
                cros_build_lib.CreateTarball(target_file, working_dir)
            self.AssertLogsContain(logs, "CreateTarball failed creating")

    def testFailureBadWorkingDir(self):
        """Verify expected error when cwd does not exist."""
        target_dir = os.path.join(self.tempdir, "target_dir")
        osutils.SafeMakedirs(target_dir)
        target_file = os.path.join(target_dir, "stuff.tar")
        working_dir = os.path.join(self.tempdir, "working_dir")
        with cros_test_lib.LoggingCapturer() as logs:
            with self.assertRaises(cros_build_lib.RunCommandError):
                cros_build_lib.CreateTarball(target_file, working_dir)
            self.AssertLogsContain(logs, "CreateTarball unable to run tar for")


# Tests for tar failure retry logic.
class FailedCreateTarballTests(cros_test_lib.RunCommandTestCase):
    """Tests special case error handling for CreateTarball."""

    def setUp(self):
        """Mock run mock."""
        # Each test can change this value as needed.  Each element is the return
        # code in the CompletedProcess for subsequent calls to run().
        self.tarResults = []

        def Result(*_args, **_kwargs):
            """Creates CompletedProcess objects for each tarResults value."""
            return cros_build_lib.CompletedProcess(
                stdout="", stderr="", returncode=self.tarResults.pop(0)
            )

        self.rc.SetDefaultCmdResult(side_effect=Result)

    def testSuccess(self):
        """CreateTarball works the first time."""
        self.tarResults = [0]
        cros_build_lib.CreateTarball("foo", "bar", inputs=["a", "b"])

        self.assertEqual(self.rc.call_count, 1)

    def testFailedOnceSoft(self):
        """Force a single retry for CreateTarball."""
        self.tarResults = [1, 0]
        cros_build_lib.CreateTarball("foo", "bar", inputs=["a", "b"], timeout=0)

        self.assertEqual(self.rc.call_count, 2)

    def testFailedOnceHard(self):
        """Test unrecoverable error."""
        self.tarResults = [2]
        with self.assertRaises(cros_build_lib.RunCommandError) as cm:
            cros_build_lib.CreateTarball("foo", "bar", inputs=["a", "b"])

        self.assertEqual(self.rc.call_count, 1)
        self.assertEqual(cm.exception.args[1].returncode, 2)

    def testFailedThriceSoft(self):
        """Exhaust retries for recoverable errors."""
        self.tarResults = [1, 1, 1]
        with self.assertRaises(cros_build_lib.RunCommandError) as cm:
            cros_build_lib.CreateTarball(
                "foo", "bar", inputs=["a", "b"], timeout=0
            )

        self.assertEqual(self.rc.call_count, 3)
        self.assertEqual(cm.exception.args[1].returncode, 1)


class ClearShadowLocksTests(
    cros_test_lib.TempDirTestCase, cros_test_lib.LoggingTestCase
):
    """Tests shadowlock files are removed from the given sysroot."""

    def setUp(self):
        D = cros_test_lib.Directory
        file_layout = (
            D(
                "etc",
                (
                    "test.lock",
                    "testfile.txt",
                    "passwd.lock",
                    "group.lock",
                    "shadow.lock",
                    "shadow.lockfile",
                    "gshadow.lock",
                ),
            ),
        )
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, file_layout)

    def testClearShadowLocksSuccess(self):
        cros_build_lib.ClearShadowLocks(self.tempdir)

        self.assertTrue(os.path.exists(f"{self.tempdir}/etc/test.lock"))
        self.assertTrue(os.path.exists(f"{self.tempdir}/etc/testfile.txt"))
        self.assertFalse(os.path.exists(f"{self.tempdir}/etc/passwd.lock"))
        self.assertFalse(os.path.exists(f"{self.tempdir}/etc/group.lock"))
        self.assertFalse(os.path.exists(f"{self.tempdir}/etc/shadow.lock"))
        self.assertFalse(os.path.exists(f"{self.tempdir}/etc/shadow.lockfile"))
        self.assertFalse(os.path.exists(f"{self.tempdir}/etc/gshadow.lock"))

    def testClearShadowLocksPathDoesNotExist(self):
        with cros_test_lib.LoggingCapturer() as logs:
            cros_build_lib.ClearShadowLocks(Path("fake/path/does/not/exist"))

            self.AssertLogsContain(
                logs,
                "Unable to clear shadow-utils lockfiles, path does not exist",
            )
