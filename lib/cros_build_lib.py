# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common python commands used by various build scripts."""

import base64
import datetime
import email.utils
import enum
import errno
import functools
import getpass
import inspect
import logging
import operator
import os
import pathlib
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
from typing import List, NoReturn, Optional, Union

from chromite.cbuildbot import cbuildbot_alerts
from chromite.lib import constants
from chromite.lib import osutils
from chromite.lib import signals
from chromite.utils import hostname_util
from chromite.utils import os_util
from chromite.utils.telemetry import trace


STRICT_SUDO = False

# For use by ShellQuote.  Match all characters that the shell might treat
# specially.  This means a number of things:
#  - Reserved characters.
#  - Characters used in expansions (brace, variable, path, globs, etc...).
#  - Characters that an interactive shell might use (like !).
#  - Whitespace so that one arg turns into multiple.
# See the bash man page as well as the POSIX shell documentation for more info:
#   http://www.gnu.org/software/bash/manual/bashref.html
#   http://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html
_SHELL_QUOTABLE_CHARS = frozenset("[|&;()<> \t\n!{}[]=*?~$\"'\\#^")
# The chars that, when used inside of double quotes, need escaping.
# Order here matters as we need to escape backslashes first.
_SHELL_ESCAPE_CHARS = r"\"`$"

# The number of files is larger than this, we will use -T option
# and files to be added may not show up to the command line.
_THRESHOLD_TO_USE_T_FOR_TAR = 50


tracer = trace.get_tracer(__name__)


def ShellQuote(s):
    """Quote |s| in a way that is safe for use in a shell.

    We aim to be safe, but also to produce "nice" output.  That means we don't
    use quotes when we don't need to, and we prefer to use less quotes (like
    putting it all in single quotes) than more (using double quotes and escaping
    a bunch of stuff, or mixing the quotes).

    While python does provide a number of alternatives like:
     - pipes.quote
     - shlex.quote
    They suffer from various problems like:
     - Not widely available in different python versions.
     - Do not produce pretty output in many cases.
     - Are in modules that rarely otherwise get used.

    Note: We don't handle reserved shell words like "for" or "case".  This is
    because those only matter when they're the first element in a command, and
    there is no use case for that.  When we want to run commands, we tend to
    run real programs and not shell ones.

    Args:
        s: The string to quote.

    Returns:
        A safely (possibly quoted) string.
    """
    # If callers pass down bad types, don't blow up.
    if isinstance(s, bytes):
        s = s.decode("utf-8", "backslashreplace")
    elif isinstance(s, pathlib.PurePath):
        return str(s)
    elif not isinstance(s, str):
        return repr(s)

    # See if no quoting is needed so we can return the string as-is.
    for c in s:
        if c in _SHELL_QUOTABLE_CHARS:
            break
    else:
        if not s:
            return "''"
        else:
            return s

    # See if we can use single quotes first.  Output is nicer.
    if "'" not in s:
        return "'%s'" % s

    # Have to use double quotes.  Escape the few chars that still expand when
    # used inside double quotes.
    for c in _SHELL_ESCAPE_CHARS:
        if c in s:
            s = s.replace(c, r"\%s" % c)
    return '"%s"' % s


def ShellUnquote(s):
    """Do the opposite of ShellQuote.

    This function assumes that the input is a valid, escaped string. The
    behaviour is undefined on malformed strings.

    Args:
        s: An escaped string.

    Returns:
        The unescaped version of the string.
    """
    if not s:
        return ""

    if s[0] == "'":
        return s[1:-1]

    if s[0] != '"':
        return s

    s = s[1:-1]
    output = ""
    i = 0
    while i < len(s) - 1:
        # Skip the backslash when it makes sense.
        if s[i] == "\\" and s[i + 1] in _SHELL_ESCAPE_CHARS:
            i += 1
        output += s[i]
        i += 1
    return output + s[i] if i < len(s) else output


def CmdToStr(cmd):
    """Translate a command list into a space-separated string.

    The resulting string should be suitable for logging messages and for
    pasting into a terminal to run.  Command arguments are surrounded by
    quotes to keep them grouped, even if an argument has spaces in it.

    Examples:
        ['a', 'b'] ==> "'a' 'b'"
        ['a b', 'c'] ==> "'a b' 'c'"
        ['a', 'b\'c'] ==> '\'a\' "b\'c"'
        [u'a', "/'$b"] ==> '\'a\' "/\'$b"'
        [] ==> ''
        See unittest for additional (tested) examples.

    Args:
        cmd: List of command arguments.

    Returns:
        String representing full command.
    """
    # If callers pass down bad types, triage it a bit.
    if isinstance(cmd, (list, tuple)):
        return " ".join(ShellQuote(arg) for arg in cmd)
    else:
        raise ValueError(
            "cmd must be list or tuple, not %s: %r" % (type(cmd), repr(cmd))
        )


class CompletedProcess(subprocess.CompletedProcess):
    """An object to store various attributes of a child process.

    This is the same as subprocess.CompletedProcess except we allow None
    defaults for |args| and |returncode|.
    """

    def __init__(self, args=None, returncode=None, **kwargs):
        super().__init__(args=args, returncode=returncode, **kwargs)

    @property
    def cmd(self):
        """Alias to self.args to better match other subprocess APIs."""
        return self.args

    @property
    def cmdstr(self):
        """Return self.cmd as a well shell-quoted string.

        Especially useful for log messages.
        """
        if self.args is None:
            return ""
        else:
            return CmdToStr(self.args)

    def check_returncode(self):
        """Raise CalledProcessError if the exit code is non-zero."""
        if self.returncode:
            raise CalledProcessError(
                returncode=self.returncode,
                cmd=self.args,
                stdout=self.stdout,
                stderr=self.stderr,
                msg="check_returncode failed",
            )


class CalledProcessError(subprocess.CalledProcessError):
    """Error caught in run() function.

    This is akin to subprocess.CalledProcessError.  We do not support |output|,
    only |stdout|.

    Attributes:
        returncode: The exit code of the process.
        cmd: The command that triggered this exception.
        msg: Short explanation of the error.
        exception: The underlying Exception if available.
    """

    def __init__(
        self,
        returncode,
        cmd,
        stdout=None,
        stderr=None,
        msg=None,
        exception=None,
    ):
        if exception is not None and not isinstance(exception, Exception):
            raise TypeError(
                "exception must be an exception instance; got %r" % (exception,)
            )

        super().__init__(returncode, cmd, stdout, stderr=stderr)

        # The parent class will set |output|, so delete it. If Python ever drops
        # this output/stdout compat logic, we can drop this to match.
        del self.output
        self._stdout = stdout

        self.msg = msg
        self.exception = exception

    @property
    def stdout(self):
        """Override parent's usage of .output"""
        return self._stdout

    @stdout.setter
    def stdout(self, value):
        """Override parent's usage of .output"""
        self._stdout = value

    @property
    def cmdstr(self):
        """Return self.cmd as a well shell-quoted string.

        Especially useful for log messages.
        """
        if self.cmd is None:
            return ""
        else:
            return CmdToStr(self.cmd)

    def Stringify(self, stdout=True, stderr=True):
        """Custom method for controlling what is included in stringifying this.

        Args:
            stdout: Whether to include captured stdout in the return value.
            stderr: Whether to include captured stderr in the return value.

        Returns:
            A summary string for this result.
        """
        if self.returncode and self.returncode < 0:
            try:
                msg = f"died with {signal.Signals(-self.returncode)!r}"
            except ValueError:
                msg = f"died with unknown signal {-self.returncode}"
        else:
            msg = f"return code: {self.returncode}"
        items = [f"{msg}; command: {self.cmdstr}"]

        if stderr and self.stderr:
            stderr = self.stderr
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", "replace")
            items.append(stderr)
        if stdout and self.stdout:
            stdout = self.stdout
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", "replace")
            items.append(stdout)
        if self.msg:
            msg = self.msg
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8", "replace")
            items.append(msg)
        return "\n".join(items)

    def __str__(self):
        return self.Stringify()

    def __eq__(self, other):
        return (
            isinstance(other, type(self))
            and self.returncode == other.returncode
            and self.cmd == other.cmd
            and self.stdout == other.stdout
            and self.stderr == other.stderr
            and self.msg == other.msg
            and self.exception == other.exception
        )

    def __ne__(self, other):
        return not self.__eq__(other)


# TODO(crbug.com/1006587): Migrate users to CompletedProcess and drop this.
class RunCommandError(CalledProcessError):
    """Error caught in run() method.

    Attributes:
        args: Tuple of the attributes below.
        msg: Short explanation of the error.
        result: The CompletedProcess that triggered this error, if available.
        exception: The underlying Exception if available.
    """

    def __init__(self, msg, result=None, exception=None):
        # This makes mocking tests easier.
        if result is None:
            result = CompletedProcess()
        elif not isinstance(result, CompletedProcess):
            raise TypeError(
                "result must be a CompletedProcess instance; got %r" % (result,)
            )

        self.result = result
        super().__init__(
            returncode=result.returncode,
            cmd=result.args,
            stdout=result.stdout,
            stderr=result.stderr,
            msg=msg,
            exception=exception,
        )


class _TerminateRunCommandError(RunCommandError):
    """We were signaled to shutdown while running a command.

    Client code shouldn't generally know, nor care about this class.  It's
    used internally to suppress retry attempts when we're signaled to die.
    """


def sudo_run(
    cmd, user="root", preserve_env: bool = False, **kwargs
) -> CompletedProcess:
    """Run a command via sudo.

    Client code must use this rather than coming up with their own run
    invocation that jams sudo in- this function is used to enforce certain
    rules in our code about sudo usage, and as a potential auditing point.

    Args:
        cmd: The command to run.  See run for rules of this argument: sudo_run
            purely prefixes it with sudo.
        user: The user to run the command as.
        preserve_env: Whether to preserve the environment.
        **kwargs: See run() options, it's a direct pass thru to it.
            Note that this supports a 'strict' keyword that defaults to True.
            If set to False, it'll suppress strict sudo behavior.

    Returns:
        See run documentation.

    Raises:
        This function may immediately raise RunCommandError if we're operating
        in a strict sudo context and the API is being misused.
        Barring that, see run's documentation: it can raise the same things run
        does.
    """
    sudo_cmd = ["sudo"]

    strict = kwargs.pop("strict", True)

    if user == "root" and os_util.is_root_user():
        return run(cmd, **kwargs)

    if strict and STRICT_SUDO:
        if "CROS_SUDO_KEEP_ALIVE" not in os.environ:
            raise RunCommandError(
                "We were invoked in a strict sudo non - interactive context, "
                "but no sudo keep alive daemon is running. This is a bug in "
                "the code.",
                CompletedProcess(args=cmd, returncode=126),
            )
        sudo_cmd += ["-n"]

    if user != "root":
        sudo_cmd += ["-u", user]

    if preserve_env:
        sudo_cmd += ["--preserve-env"]

    # Pass these values down into the sudo environment, since sudo will
    # just strip them normally.
    extra_env = kwargs.pop("extra_env", None)
    extra_env = {} if extra_env is None else extra_env.copy()

    for var in constants.ENV_PASSTHRU:
        if var not in extra_env and var in os.environ:
            extra_env[var] = os.environ[var]

    sudo_cmd.extend("%s=%s" % (k, v) for k, v in extra_env.items())

    # Finally, block people from passing options to sudo.
    sudo_cmd.append("--")

    if isinstance(cmd, str):
        # We need to handle shell ourselves so the order is correct:
        #  $ sudo [sudo args] -- bash -c '[shell command]'
        # If we let run take care of it, we'd end up with:
        #  $ bash -c 'sudo [sudo args] -- [shell command]'
        shell = kwargs.pop("shell", False)
        if not shell:
            raise Exception("Cannot run a string command without a shell")
        sudo_cmd.extend(["/bin/bash", "-c", cmd])
    else:
        sudo_cmd.extend(cmd)

    return run(sudo_cmd, **kwargs)


def _KillChildProcess(
    proc, int_timeout, kill_timeout, cmd, original_handler, signum, frame
):
    """Used as a signal handler by run.

    This is internal to run.  No other code should use this.
    """
    if signum:
        # If we've been invoked because of a signal, ignore delivery of that
        # signal from this point forward.  The invoking context of
        # _KillChildProcess restores signal delivery to what it was prior; we
        # suppress future delivery till then since this code handles
        # SIGINT/SIGTERM fully including delivering the signal to the original
        # handler on the way out.
        signal.signal(signum, signal.SIG_IGN)

    # Do not trust Popen's returncode alone; we can be invoked from contexts
    # where the Popen instance was created, but no process was generated.
    if proc.returncode is None and proc.pid is not None:
        try:
            while proc.poll_lock_breaker() is None and int_timeout >= 0:
                time.sleep(0.1)
                int_timeout -= 0.1

            proc.terminate()
            while proc.poll_lock_breaker() is None and kill_timeout >= 0:
                time.sleep(0.1)
                kill_timeout -= 0.1

            if proc.poll_lock_breaker() is None:
                # Still doesn't want to die.  Too bad, so sad, time to die.
                proc.kill()
        except EnvironmentError as e:
            logging.warning(
                "Ignoring unhandled exception in _KillChildProcess: %s", e
            )

        # Ensure our child process has been reaped, but don't wait forever.
        proc.wait_lock_breaker(timeout=60)

    if not signals.RelaySignal(original_handler, signum, frame):
        # Mock up our own, matching exit code for signaling.
        cmd_result = CompletedProcess(args=cmd, returncode=signum << 8)
        raise _TerminateRunCommandError(f"Received signal {signum}", cmd_result)


class _Popen(subprocess.Popen):
    """subprocess.Popen derivative customized for our usage.

    Specifically, we fix terminate/send_signal/kill to work if the child process
    was a setuid binary; on vanilla kernels, the parent can wax the child
    regardless, on goobuntu this apparently isn't allowed, thus we fall back
    to the sudo machinery we have.

    While we're overriding send_signal, we also suppress ESRCH being raised
    if the process has exited, and suppress signaling all together if the
    process has knowingly been waitpid'd already.
    """

    # Pylint seems to be buggy with the send_signal signature detection.
    # pylint: disable=arguments-renamed
    def send_signal(self, sig):
        if self.returncode is not None:
            # The original implementation in Popen would allow signaling
            # whatever process now occupies this pid, even if the Popen object
            # had waitpid'd. Since we can escalate to sudo kill, we do not want
            # to allow that. Fixing this addresses that angle, and makes the API
            # less sucky in the process.
            return

        try:
            os.kill(self.pid, sig)
        except EnvironmentError as e:
            if e.errno == errno.EPERM:
                # Kill returns either 0 (signal delivered), or 1 (signal wasn't
                # delivered).  This isn't particularly informative, but we still
                # need that info to decide what to do, thus the check=False.
                ret = sudo_run(
                    ["kill", "-%i" % sig, str(self.pid)],
                    print_cmd=False,
                    stdout=True,
                    stderr=True,
                    check=False,
                )
                if ret.returncode == 1:
                    # The kill binary doesn't distinguish between permission
                    # denied, and the pid is missing.  Denied can only occur
                    # under weird grsec/selinux policies.  We ignore that
                    # potential and just assume the pid was already dead and try
                    # to reap it.
                    self.poll()
            elif e.errno == errno.ESRCH:
                # Since we know the process is dead, reap it now. Normally Popen
                # would throw this error - we suppress it since frankly that's a
                # misfeature, and we're already overriding this method.
                self.poll()
            else:
                raise

    def _lock_breaker(self, func, *args, **kwargs):
        """Helper to manage the waitpid lock.

        Workaround https://bugs.python.org/issue25960.
        """
        # If the lock doesn't exist, or is not locked, call the func directly.
        lock = getattr(self, "_waitpid_lock", None)
        if lock is not None and lock.locked():
            try:
                lock.release()
                return func(*args, **kwargs)
            finally:
                if not lock.locked():
                    lock.acquire()
        else:
            return func(*args, **kwargs)

    def poll_lock_breaker(self, *args, **kwargs):
        """Wrapper around poll() to break locks if needed."""
        return self._lock_breaker(self.poll, *args, **kwargs)

    def wait_lock_breaker(self, *args, **kwargs):
        """Wrapper around wait() to break locks if needed."""
        return self._lock_breaker(self.wait, *args, **kwargs)


@tracer.start_as_current_span("lib.cros_build_lib.run")
# pylint: disable=redefined-builtin
def run(
    cmd,
    print_cmd=True,
    stdout=None,
    stderr=None,
    cwd=None,
    input=None,
    enter_chroot=False,
    executable: Optional[Union[str, os.PathLike]] = None,
    shell=False,
    env=None,
    extra_env=None,
    ignore_sigint=False,
    chroot_args=None,
    debug_level=logging.INFO,
    check=True,
    int_timeout=1,
    kill_timeout=1,
    log_output=False,
    capture_output=False,
    encoding=None,
    errors=None,
    dryrun=False,
    **kwargs,
) -> CompletedProcess:
    """Runs a command.

    Args:
        cmd: cmd to run.  Should be input to subprocess.Popen. If a string,
            shell must be true. Otherwise, the command must be an array of
            arguments, and shell must be false.
        print_cmd: prints the command before running it.
        stdout: Where to send stdout.  This may be many things to control
            redirection:
                * None is the default; the existing stdout is used.
                * An existing file object. Must be opened with mode 'w' or 'wb'.
                * A string to a file (will be truncated & opened automatically).
                * subprocess.PIPE to capture & return the output.
                * A boolean to indicate whether to capture the output. True will
                    capture the output via a tempfile (good for large output).
                * An open file descriptor (as a positive integer).
        stderr: Where to send stderr.  See |stdout| for possible values. This
            also may be subprocess.STDOUT to indicate stderr & stdout should be
            combined.
        cwd: the working directory to run this cmd.
        input: The data to pipe into this command through stdin.  If a file
            object or file descriptor, stdin will be connected directly to that.
        enter_chroot: this command should be run from within the chroot. If set,
            cwd must point to the scripts directory. If we are already inside
            the chroot, this command will be run as if |enter_chroot| is False.
        executable: Program to run instead of relying on cmd[0].  Useful to set
            a different value for argv[0].
        shell: Controls whether we add a shell as a command interpreter. See cmd
            since it has to agree as to the type.
        env: If non-None, this is the environment for the new process.  If
            enter_chroot is true then this is the environment of the
            enter_chroot, most of which gets removed from the cmd run.
        extra_env: If set, this is added to the environment for the new process.
            In enter_chroot=True case, these are specified on the post-entry
            side, and so are often more useful.  This dictionary is not used to
            clear any entries though.
        ignore_sigint: If True, we'll ignore signal.SIGINT before calling the
            child. This is the desired behavior if we know our child will handle
            Ctrl-C.  If we don't do this, I think we and the child will both get
            Ctrl-C at the same time, which means we'll forcefully kill the
            child.
        chroot_args: An array of arguments for the chroot environment wrapper.
        debug_level: The debug level of run's output.
        check: Whether to raise an exception when command returns a non-zero
            exit code, or return the CompletedProcess object containing the exit
            code.
            Note: will still raise an exception if the cmd file does not exist.
        int_timeout: If we're interrupted, how long (in seconds) should we give
            the invoked process to clean up before we send a SIGTERM.
        kill_timeout: If we're interrupted, how long (in seconds) should we give
            the invoked process to shutdown from a SIGTERM before we SIGKILL it.
        log_output: Log the command and its output automatically.
        capture_output: Set |stdout| and |stderr| to True.
        encoding: Encoding for stdin/stdout/stderr, otherwise bytes are used.
            Most users want 'utf-8' here for string data.
        errors: How to handle errors when |encoding| is used.  Defaults to
            'strict', but 'ignore' and 'replace' are common settings.
        dryrun: Only log the command,and return a stub result.

    Returns:
        A CompletedProcess object.

    Raises:
        RunCommandError: Raised on error.
    """
    # Hide this function in pytest tracebacks when a RunCommandError is raised,
    # as seeing the contents of this function when a command fails is not
    # helpful.
    # https://docs.pytest.org/en/latest/example/simple.html#writing-well-integrated-assertion-helpers
    __tracebackhide__ = operator.methodcaller("errisinstance", RunCommandError)

    # Handle backwards compatible settings.
    stdout_file_mode = "w+b"
    if "append_to_file" in kwargs:
        # TODO(vapier): Enable this warning once chromite & users migrate.
        # logging.warning('run: append_to_file is now part of stdout')
        if kwargs.pop("append_to_file"):
            stdout_file_mode = "a+b"
    assert not kwargs, "Unknown arguments to run: %s" % (list(kwargs),)

    if capture_output:
        if stdout is not None or stderr is not None:
            raise ValueError(
                "capture_output may not be used with stdout & stderr"
            )
        if stdout is None:
            stdout = True
        if stderr is None:
            stderr = True

    if encoding is not None and errors is None:
        errors = "strict"

    # Set default for variables.
    popen_stdout = None
    popen_stderr = None
    stdin = None
    cmd_result = CompletedProcess()
    span = trace.get_current_span()

    # Force the timeout to float; in the process, if it's not convertible,
    # a self-explanatory exception will be thrown.
    kill_timeout = float(kill_timeout)

    def _get_tempfile():
        try:
            return UnbufferedTemporaryFile()
        except EnvironmentError as e:
            if e.errno != errno.ENOENT:
                raise
            # This can occur if we were pointed at a specific location for our
            # TMP, but that location has since been deleted.  Suppress that
            # issue in this particular case since our usage guarantees deletion,
            # and since this is primarily triggered during hard cgroups
            # shutdown.
            return UnbufferedTemporaryFile(dir="/tmp")

    # Modify defaults based on parameters.
    # Note that tempfiles must be unbuffered else attempts to read
    # what a separate process did to that file can result in a bad
    # view of the file.
    log_stdout_to_file = False
    if isinstance(stdout, (str, os.PathLike)):
        # We explicitly close this handle below before returning.
        # pylint: disable=consider-using-with
        popen_stdout = open(stdout, stdout_file_mode)
        log_stdout_to_file = True
    elif hasattr(stdout, "fileno"):
        popen_stdout = stdout
        log_stdout_to_file = True
    elif isinstance(stdout, bool):
        # This check must come before isinstance(int) because bool subclasses
        # int.
        if stdout:
            popen_stdout = _get_tempfile()
    elif isinstance(stdout, int):
        popen_stdout = stdout
    elif log_output:
        popen_stdout = _get_tempfile()

    log_stderr_to_file = False
    if isinstance(stderr, (str, os.PathLike)):
        # We explicitly close this handle below before returning.
        # pylint: disable=consider-using-with
        popen_stderr = open(stderr, "w+b")
        log_stderr_to_file = True
    elif hasattr(stderr, "fileno"):
        popen_stderr = stderr
        log_stderr_to_file = True
    elif isinstance(stderr, bool):
        # This check must come before isinstance(int) because bool subclasses
        # int.
        if stderr:
            popen_stderr = _get_tempfile()
    elif isinstance(stderr, int):
        popen_stderr = stderr
    elif log_output:
        popen_stderr = _get_tempfile()

    # If subprocesses have direct access to stdout or stderr, they can bypass
    # our buffers, so we need to flush to ensure that output is not interleaved.
    if popen_stdout is None or popen_stderr is None:
        sys.stdout.flush()
        sys.stderr.flush()

    # If input is a string, we'll create a pipe and send it through that.
    # Otherwise we assume it's a file object that can be read from directly.
    if isinstance(input, (str, bytes)):
        stdin = subprocess.PIPE
        # Allow people to always pass in bytes or strings regardless of
        # encoding. Our Popen usage takes care of converting everything to bytes
        # first.
        #
        # Linter can't see that we're using |input| as a var, not a builtin.
        if encoding and isinstance(input, str):
            input = input.encode(encoding, errors)
        elif not encoding and isinstance(input, str):
            input = input.encode("utf-8")
    elif input is not None:
        stdin = input
        input = None

    # Sanity check the command.  This helps when RunCommand is deep in the call
    # chain, but the command itself was constructed along the way.
    if isinstance(cmd, (str, bytes)):
        if not shell:
            raise ValueError("Cannot run a string command without a shell")
        cmd = ["/bin/bash", "-c", cmd]
        shell = False
    elif shell:
        raise ValueError("Cannot run an array command with a shell")
    elif not cmd:
        raise ValueError("Missing command to run")
    elif not isinstance(cmd, (list, tuple)):
        raise TypeError(
            "cmd must be list or tuple, not %s: %r" % (type(cmd), repr(cmd))
        )
    elif not all(isinstance(x, (bytes, str, os.PathLike)) for x in cmd):
        raise TypeError(
            f"All command elements must be bytes/strings/Path: {cmd!r}"
        )

    # If we are using enter_chroot we need to use enterchroot pass env through
    # to the final command.
    env = env.copy() if env is not None else os.environ.copy()
    # Looking at localized error messages may be unexpectedly dangerous, so we
    # set LC_MESSAGES=C to make sure the output of commands is safe to inspect.
    env["LC_MESSAGES"] = "C"
    env.update(extra_env if extra_env else {})

    if enter_chroot and not IsInsideChroot():
        wrapper = ["cros_sdk"]
        if cwd:
            # If the current working directory is set, try to find cros_sdk
            # relative to cwd. Generally cwd will be the buildroot therefore we
            # want to use {cwd}/chromite/bin/cros_sdk. For more info PTAL at
            # crbug.com/432620
            path = cwd / constants.CHROMITE_BIN_SUBDIR / "cros_sdk"
            if os.path.exists(path):
                wrapper = [path]

        if chroot_args:
            wrapper += chroot_args

        if extra_env:
            wrapper.extend("%s=%s" % (k, v) for k, v in extra_env.items())

        cmd = wrapper + ["--"] + cmd

    for var in constants.ENV_PASSTHRU:
        if var not in env and var in os.environ:
            env[var] = os.environ[var]

    # Print out the command before running.
    if dryrun or print_cmd or log_output:
        log = ""
        if dryrun:
            log += "(dryrun) "
        log += "run: %s" % (CmdToStr(cmd),)
        if cwd:
            log += " in %s" % (cwd,)
        logging.log(debug_level, "%s", log)

    if span.is_recording():
        span.set_attributes(
            {
                "cmd": CmdToStr(cmd),
                "dryrun": dryrun,
                "cwd": str(cwd),
                "executable": str(executable),
            }
        )

        tracecontext = trace.extract_tracecontext()
        env.update(tracecontext)

    cmd_result.args = cmd

    # We want to still something in dryrun mode so we process all the options
    # and return appropriate values (e.g. output with correct encoding).
    popen_cmd = ["true"] if dryrun else cmd

    proc = None
    try:
        proc = _Popen(
            popen_cmd,
            executable=executable,
            cwd=cwd,
            stdin=stdin,
            stdout=popen_stdout,
            stderr=popen_stderr,
            shell=False,
            env=env,
            close_fds=True,
        )

        old_sigint = signal.getsignal(signal.SIGINT)
        if ignore_sigint:
            new_sigint = signal.SIG_IGN
        else:
            new_sigint = functools.partial(
                _KillChildProcess,
                proc,
                int_timeout,
                kill_timeout,
                cmd,
                old_sigint,
            )
        # We have to ignore ValueError in case we're run from a thread.
        try:
            signal.signal(signal.SIGINT, new_sigint)
        except ValueError:
            old_sigint = None

        old_sigterm = signal.getsignal(signal.SIGTERM)
        new_sigterm = functools.partial(
            _KillChildProcess, proc, int_timeout, kill_timeout, cmd, old_sigterm
        )
        try:
            signal.signal(signal.SIGTERM, new_sigterm)
        except ValueError:
            old_sigterm = None

        try:
            try:
                (cmd_result.stdout, cmd_result.stderr) = proc.communicate(input)
            finally:
                if old_sigint is not None:
                    signal.signal(signal.SIGINT, old_sigint)
                if old_sigterm is not None:
                    signal.signal(signal.SIGTERM, old_sigterm)

                if (
                    popen_stdout
                    and not isinstance(popen_stdout, int)
                    and not log_stdout_to_file
                ):
                    popen_stdout.seek(0)
                    cmd_result.stdout = popen_stdout.read()
                    popen_stdout.close()
                elif log_stdout_to_file:
                    popen_stdout.close()

                if (
                    popen_stderr
                    and not isinstance(popen_stderr, int)
                    and not log_stderr_to_file
                ):
                    popen_stderr.seek(0)
                    cmd_result.stderr = popen_stderr.read()
                    popen_stderr.close()
                elif log_stderr_to_file:
                    popen_stderr.close()
        except _TerminateRunCommandError as e:
            # If we were killed by a signal (like SIGTERM in case of a timeout),
            # don't swallow the output completely as it can be a huge help for
            # figuring out why the command failed.
            e.stdout = e.result.stdout = cmd_result.stdout
            e.stderr = e.result.stderr = cmd_result.stderr
            raise

        cmd_result.returncode = proc.returncode

        # The try/finally block is a bit hairy.  We normally want the logged
        # output to be what gets passed back up.  But if there's a decode error,
        # we don't want it to break logging entirely.  If the output had a lot
        # of newlines, always logging it as bytes wouldn't be human readable.
        try:
            if encoding:
                if cmd_result.stdout is not None:
                    cmd_result.stdout = cmd_result.stdout.decode(
                        encoding, errors
                    )
                if cmd_result.stderr is not None:
                    cmd_result.stderr = cmd_result.stderr.decode(
                        encoding, errors
                    )
        finally:
            if log_output:
                if cmd_result.stdout:
                    logging.log(debug_level, "(stdout):\n%s", cmd_result.stdout)
                if cmd_result.stderr:
                    logging.log(debug_level, "(stderr):\n%s", cmd_result.stderr)

        if check and proc.returncode:
            msg = "cmd=%s" % cmd
            if cwd:
                msg += ", cwd=%s" % cwd
            if extra_env:
                msg += ", extra env=%s" % extra_env
            raise RunCommandError(msg, cmd_result)
    except OSError as e:
        estr = str(e)
        if e.errno == errno.EACCES:
            estr += "; does the program need `chmod a+x`?"
        raise RunCommandError(
            estr, CompletedProcess(args=cmd), exception=e
        ) from e
    finally:
        if proc is not None:
            # Ensure the process is dead.
            _KillChildProcess(
                proc, int_timeout, kill_timeout, cmd, None, None, None
            )

    # We might capture stdout/stderr for internal reasons (like logging), but we
    # don't want to let it leak back out to the callers. They only get output if
    # they explicitly requested it.
    if stdout is None:
        cmd_result.stdout = None
    if stderr is None:
        cmd_result.stderr = None

    return cmd_result


# pylint: enable=redefined-builtin


# Convenience run methods.
#
# We don't use functools.partial because it binds the methods at import time,
# which doesn't work well with unit tests, since it bypasses the mock that may
# be set up for run.


def dbg_run(*args, **kwargs):
    kwargs.setdefault("debug_level", logging.DEBUG)
    return run(*args, **kwargs)


class DieSystemExit(SystemExit):
    """Custom Exception used so we can intercept this if necessary."""


def Die(message, *args, **kwargs) -> NoReturn:
    """Emits an error message with a stack trace and halts execution.

    Args:
        message: The message to be emitted before exiting.
    """
    logging.error(message, *args, **kwargs)
    raise DieSystemExit(1)


def GetSysrootToolPath(sysroot, tool_name):
    """Returns the path to the sysroot specific version of a tool.

    Does not check that the tool actually exists.

    Args:
        sysroot: build root of the system in question.
        tool_name: string name of tool desired (e.g. 'equery').

    Returns:
        string path to tool inside the sysroot.
    """
    if sysroot == "/":
        return os.path.join(sysroot, "usr", "bin", tool_name)

    return os.path.join(sysroot, "build", "bin", tool_name)


def IsInsideChroot():
    """Returns True if we are inside chroot."""
    return os.path.exists("/etc/cros_chroot_version")


def IsOutsideChroot():
    """Returns True if we are outside chroot."""
    return not IsInsideChroot()


def AssertInsideChroot():
    """Die if we are outside the chroot"""
    if not IsInsideChroot():
        Die("%s: please run inside the chroot", os.path.basename(sys.argv[0]))


def AssertOutsideChroot():
    """Die if we are inside the chroot"""
    if IsInsideChroot():
        Die("%s: please run outside the chroot", os.path.basename(sys.argv[0]))


def AssertRootUser() -> None:
    """Die if non-root user."""
    try:
        os_util.assert_root_user()
    except AssertionError as e:
        Die(e)


def AssertNonRootUser() -> None:
    """Die if root user."""
    try:
        os_util.assert_non_root_user()
    except AssertionError as e:
        Die(e)


class CompressionType(enum.IntEnum):
    """Type of compression."""

    NONE = 0
    GZIP = 1
    BZIP2 = 2
    XZ = 3
    ZSTD = 4


def FindCompressor(
    compression, chroot: Optional[Union[Path, str]] = None
) -> str:
    """Locate a compressor utility program (possibly in a chroot).

    Since we compress/decompress a lot, make it easy to locate a
    suitable utility program in a variety of locations.  We favor
    the one in the chroot over /, and the parallel implementation
    over the single threaded one.

    Args:
        compression: The type of compression desired.
        chroot: Optional path to a chroot to search.

    Returns:
        Path to a compressor.

    Raises:
        ValueError: If compression is unknown.
    """
    if compression == CompressionType.XZ:
        return str(constants.CHROMITE_SCRIPTS_DIR / "xz_auto")
    elif compression == CompressionType.GZIP:
        possible_progs = ["pigz", "gzip"]
    elif compression == CompressionType.BZIP2:
        possible_progs = ["lbzip2", "pbzip2", "bzip2"]
    elif compression == CompressionType.ZSTD:
        possible_progs = ["zstdmt", "zstd"]
    elif compression == CompressionType.NONE:
        return "cat"
    else:
        raise ValueError("unknown compression")

    roots = []
    if chroot:
        roots.append(chroot)
    roots.append("/")

    for prog in possible_progs:
        for root in roots:
            for subdir in ["", "usr"]:
                path = os.path.join(root, subdir, "bin", prog)
                if os.path.exists(path):
                    return path

    return possible_progs[-1]


def CompressionDetectType(path: Union[str, os.PathLike]) -> CompressionType:
    """Detect the type of compression used by |path| by sniffing its data.

    Args:
        path: The file to sniff.

    Returns:
        The compression type if we could detect it.
    """
    if not isinstance(path, Path):
        path = Path(path)

    with path.open("rb") as f:
        data = f.read(6)

    MAGIC_TO_TYPE = (
        (b"BZh", CompressionType.BZIP2),
        (b"\x1f\x8b", CompressionType.GZIP),
        (b"\xfd\x37\x7a\x58\x5a\x00", CompressionType.XZ),
        (b"\x28\xb5\x2f\xfd", CompressionType.ZSTD),
    )
    for magic, ctype in MAGIC_TO_TYPE:
        if data.startswith(magic):
            return ctype
    return CompressionType.NONE


def CompressionStrToType(s: str) -> Optional[CompressionType]:
    """Convert a compression string type to a constant.

    Args:
        s: string to check

    Returns:
        A constant, or None if the compression type is unknown.
    """
    _COMP_STR = {
        "gz": CompressionType.GZIP,
        "bz2": CompressionType.BZIP2,
        "xz": CompressionType.XZ,
        "zst": CompressionType.ZSTD,
    }
    if s:
        return _COMP_STR.get(s)
    else:
        return CompressionType.NONE


def CompressionExtToType(file_name: Union[Path, str]) -> CompressionType:
    """Retrieve a compression type constant from a compression file's name.

    Args:
        file_name: Name of a compression file.

    Returns:
        A constant, return CompressionType.NONE if the extension is unknown.
    """
    ext = os.path.splitext(file_name)[-1]
    _COMP_EXT = {
        ".tgz": CompressionType.GZIP,
        ".gz": CompressionType.GZIP,
        ".tbz2": CompressionType.BZIP2,
        ".bz2": CompressionType.BZIP2,
        ".txz": CompressionType.XZ,
        ".xz": CompressionType.XZ,
        ".zst": CompressionType.ZSTD,
    }
    return _COMP_EXT.get(ext, CompressionType.NONE)


def CompressFile(infile, outfile) -> CompletedProcess:
    """Compress a file using compressor specified by |outfile| suffix.

    Args:
        infile: File to compress.
        outfile: Name of output file. Compression used is based on the
            type of suffix of the name specified (e.g.: .bz2).
    """
    comp_type = CompressionExtToType(outfile)
    assert comp_type and comp_type != CompressionType.NONE
    comp = FindCompressor(comp_type)
    return run([comp, "-c", infile], stdout=outfile)


def UncompressFile(infile, outfile) -> CompletedProcess:
    """Uncompress a file using compressor specified by |infile| suffix.

    Args:
        infile: File to uncompress. Compression used is based on the
            type of suffix of the name specified (e.g.: .bz2).
        outfile: Name of output file.
    """
    comp_type = CompressionExtToType(infile)
    assert comp_type and comp_type != CompressionType.NONE
    comp = FindCompressor(comp_type)
    return run([comp, "-dc", infile], stdout=outfile)


class TarballError(RunCommandError):
    """Error while running tar.

    We may run tar multiple times because of "soft" errors.  The result is from
    the last run instance.
    """


def CreateTarball(
    tarball_path: Union[Path, int, str],
    cwd: Union[Path, str],
    sudo: Optional[bool] = False,
    compression: CompressionType = CompressionType.XZ,
    chroot: Optional[Union[Path, str]] = None,
    inputs: Optional[List[str]] = None,
    timeout: int = 300,
    extra_args: Optional[List[str]] = None,
    **kwargs,
):
    """Create a tarball.  Executes 'tar' on the commandline.

    Args:
        tarball_path: The path of the tar file to generate. Can be file
            descriptor.
        cwd: The directory to run the tar command.
        sudo: Whether to run with "sudo".
        compression: The type of compression desired.  See the FindCompressor
            function for details.
        chroot: See FindCompressor().
        inputs: A list of files or directories to add to the tarball.  If unset,
            defaults to ".".
        timeout: The number of seconds to wait on soft failure.
        extra_args: A list of extra args to pass to "tar".
        **kwargs: Any run options/overrides to use.

    Returns:
        The cmd_result object returned by the run invocation.

    Raises:
        TarballError: if the tar command failed, possibly after retry.
    """
    if inputs is None:
        inputs = ["."]

    if extra_args is None:
        extra_args = []
    kwargs.setdefault("debug_level", logging.INFO)

    # Use a separate compression program - this enables parallel compression
    # in some cases.
    # Using 'raw' hole detection instead of 'seek' isn't that much slower, but
    # will provide much better results when archiving large disk images that are
    # not fully sparse.
    comp = FindCompressor(compression, chroot=chroot)
    cmd = (
        ["tar"]
        + extra_args
        + [
            "--sparse",
            "--hole-detection=raw",
            "--use-compress-program",
            comp,
            "-c",
        ]
    )

    rc_stdout = None
    if isinstance(tarball_path, int):
        cmd += ["--to-stdout"]
        rc_stdout = tarball_path
    else:
        cmd += ["-f", str(tarball_path)]

    if len(inputs) > _THRESHOLD_TO_USE_T_FOR_TAR:
        cmd += ["--null", "-T", "/dev/stdin"]
        rc_input = b"\0".join(x.encode("utf-8") for x in inputs)
    else:
        cmd += list(inputs)
        rc_input = None

    if sudo:
        rc_func = functools.partial(sudo_run, preserve_env=True)
    else:
        rc_func = run

    # If tar fails with status 1, retry twice. Once after timeout seconds and
    # again 2*timeout seconds after that.
    for try_count in range(3):
        try:
            result = rc_func(
                cmd,
                cwd=cwd,
                **dict(kwargs, check=False, input=rc_input, stdout=rc_stdout),
            )
        except RunCommandError as rce:
            # There are cases where run never executes the command (cannot find
            # tar, cannot execute tar, such as when cwd does not exist).
            # Although the run command will show low-level problems, we also
            # want to log the context of what CreateTarball was trying to do.
            logging.error(
                "CreateTarball unable to run tar for %s in %s. cmd={%s}",
                tarball_path,
                cwd,
                cmd,
            )
            raise rce
        if result.returncode == 0:
            return result
        if result.returncode != 1 or try_count > 1:
            # Since the build is abandoned at this point, we will take 5 entire
            # minutes to track down the competing process. Error will have the
            # low-level tar command error, so log the context of the tar command
            # (tarball_path file, current working dir).
            logging.error(
                "CreateTarball failed creating %s in %s. cmd={%s}",
                tarball_path,
                cwd,
                cmd,
            )
            raise TarballError("CreateTarball", result)

        assert result.returncode == 1
        time.sleep(timeout * (try_count + 1))
        logging.warning(
            "CreateTarball: tar: source modification time changed "
            "(see crbug.com/547055), retrying"
        )
        cbuildbot_alerts.PrintBuildbotStepWarnings()


def ExtractTarball(
    tarball_path: Union[Path, str],
    install_path: Union[Path, str],
    files_to_extract: Optional[List[str]] = None,
    excluded_files: Optional[List[str]] = None,
    return_extracted_files: bool = False,
) -> List[str]:
    """Extracts a tarball using tar.

    Detects whether the tarball is compressed or not based on the file
    extension and extracts the tarball into the install_path.

    Args:
        tarball_path: Path to the tarball to extract.
        install_path: Path to extract the tarball to.
        files_to_extract: String of specific files in the tarball to extract.
        excluded_files: String of files to not extract.
        return_extracted_files: whether the caller expects the list of files
            extracted; if False, returns an empty list.

    Returns:
        List of absolute paths of the files extracted (possibly empty).

    Raises:
        TarballError: if the tar command failed
    """
    # Use a separate decompression program - this enables parallel decompression
    # in some cases.
    cmd = [
        "tar",
        "--sparse",
        "-xf",
        str(tarball_path),
        "--directory",
        str(install_path),
    ]

    try:
        comp_type = CompressionDetectType(tarball_path)
    except FileNotFoundError as e:
        raise TarballError(str(e))
    if comp_type != CompressionType.NONE:
        cmd += ["--use-compress-program", FindCompressor(comp_type)]

    # If caller requires the list of extracted files, get verbose.
    if return_extracted_files:
        cmd += ["--verbose"]

    if excluded_files:
        for exclude in excluded_files:
            cmd.extend(["--exclude", exclude])

    if files_to_extract:
        cmd.extend(files_to_extract)

    try:
        result = run(cmd, capture_output=True, encoding="utf-8")
    except RunCommandError as e:
        raise TarballError(
            "An error occurred when attempting to untar %s:\n%s"
            % (tarball_path, e)
        )

    if result.returncode != 0:
        logging.error(
            "ExtractTarball failed extracting %s. cmd={%s}", tarball_path, cmd
        )
        raise TarballError("ExtractTarball", result)

    if return_extracted_files:
        return [
            os.path.join(install_path, filename)
            for filename in result.stdout.splitlines()
            if not filename.endswith("/")
        ]
    return []


def IsTarball(path: str) -> bool:
    """Guess if this is a tarball based on the filename."""
    parts = path.split(".")
    if len(parts) <= 1:
        return False

    if parts[-1] == "tar":
        return True

    if parts[-2] == "tar":
        return parts[-1] in ("bz2", "gz", "xz", "zst")

    return parts[-1] in ("tbz2", "tbz", "tgz", "txz")


def GetChoice(title, options, group_size=0):
    """Ask user to choose an option from the list.

    When |group_size| is 0, then all items in |options| will be extracted and
    shown at the same time.  Otherwise, the items will be extracted |group_size|
    at a time, and then shown to the user.  This makes it easier to support
    generators that are slow, extremely large, or people usually want to pick
    from the first few choices.

    Args:
        title: The text to display before listing options.
        options: Iterable which provides options to display.
        group_size: How many options to show before asking the user to choose.

    Returns:
        An integer of the index in |options| the user picked.
    """

    def PromptForChoice(max_choice, more):
        prompt = "Please choose an option [0-%d]" % max_choice
        if more:
            prompt += " (Enter for more options)"
        prompt += ": "

        while True:
            choice = input(prompt)
            if more and not choice.strip():
                return None
            try:
                choice = int(choice)
            except ValueError:
                print("Input is not an integer")
                continue
            if choice < 0 or choice > max_choice:
                print("Choice %d out of range (0-%d)" % (choice, max_choice))
                continue
            return choice

    print(title)
    max_choice = 0
    for i, opt in enumerate(options):
        if i and group_size and not i % group_size:
            choice = PromptForChoice(i - 1, True)
            if choice is not None:
                return choice
        print("  [%d]: %s" % (i, opt))
        max_choice = i

    return PromptForChoice(max_choice, False)


def BooleanPrompt(
    prompt="Do you want to continue?",
    default=True,
    true_value="yes",
    false_value="no",
    prolog=None,
):
    """Helper function for processing boolean choice prompts.

    Args:
        prompt: The question to present to the user.
        default: Boolean to return if the user just presses enter.
        true_value: The text to display that represents a True returned.
        false_value: The text to display that represents a False returned.
        prolog: The text to display before prompt.

    Returns:
        True or False.
    """
    true_value, false_value = true_value.lower(), false_value.lower()
    true_text, false_text = true_value, false_value
    if true_value == false_value:
        raise ValueError(
            "true_value and false_value must differ: got %r" % true_value
        )

    if default:
        true_text = true_text[0].upper() + true_text[1:]
    else:
        false_text = false_text[0].upper() + false_text[1:]

    prompt = "\n%s (%s/%s)? " % (prompt, true_text, false_text)

    if prolog:
        prompt = "\n%s\n%s" % (prolog, prompt)

    while True:
        try:
            response = input(prompt).lower()
        except EOFError:
            # If the user hits CTRL+D, or stdin is disabled, use the default.
            print()
            response = None
        except KeyboardInterrupt:
            # If the user hits CTRL+C, just exit the process.
            print()
            Die("CTRL+C detected; exiting")

        if not response:
            return default
        if true_value.startswith(response):
            if not false_value.startswith(response):
                return True
            # common prefix between the two...
        elif false_value.startswith(response):
            return False


def BooleanShellValue(sval, default, msg=None):
    """See if the string value is a value users typically consider as boolean

    Often times people set shell variables to different values to mean "true"
    or "false".  For example, they can do:
        export FOO=yes
        export BLAH=1
        export MOO=true
    Handle all that user ugliness here.

    If the user picks an invalid value, you can use |msg| to display a non-fatal
    warning rather than raising an exception.

    Args:
        sval: The string value we got from the user.
        default: If we can't figure out if the value is true or false, use this.
        msg: If |sval| is an unknown value, use |msg| to warn the user that we
           could not decode the input.  Otherwise, raise ValueError().

    Returns:
        The interpreted boolean value of |sval|.

    Raises:
        ValueError() if |sval| is an unknown value and |msg| is not set.
    """
    if sval is None:
        return default

    if isinstance(sval, str):
        s = sval.lower()
        if s in ("yes", "y", "1", "true"):
            return True
        elif s in ("no", "n", "0", "false"):
            return False

    if msg is not None:
        logging.warning("%s: %r", msg, sval)
        return default
    else:
        raise ValueError("Could not decode as a boolean value: %r" % sval)


# Suppress whacked complaints about abstract class being unused.
class PrimaryPidContextManager:
    """Allow context managers to restrict their exit to within the same PID."""

    # In certain cases we actually want this ran outside
    # of the main pid- specifically in backup processes
    # doing cleanup.
    ALTERNATE_PRIMARY_PID = None

    def __init__(self):
        self._invoking_pid = None

    def __enter__(self):
        self._invoking_pid = os.getpid()
        return self._enter()

    def __exit__(self, exc_type, exc, exc_tb):
        curpid = os.getpid()
        if curpid == self.ALTERNATE_PRIMARY_PID:
            self._invoking_pid = curpid
        if curpid == self._invoking_pid:
            return self._exit(exc_type, exc, exc_tb)

    def _enter(self):
        raise NotImplementedError(self, "_enter")

    def _exit(self, exc_type, exc, exc_tb):
        raise NotImplementedError(self, "_exit")


def iflatten_instance(iterable, terminate_on_kls=(str, bytes)):
    """Derivative of snakeoil.lists.iflatten_instance; flatten an object.

    Given an object, flatten it into a single depth iterable,
    stopping descent on objects that either aren't iterable, or match
    isinstance(obj, terminate_on_kls).

    Examples:
        >>> print list(iflatten_instance([1, 2, "as", ["4", 5]))
        [1, 2, "as", "4", 5]
    """

    def descend_into(item):
        if isinstance(item, terminate_on_kls):
            return False
        try:
            iter(item)
        except TypeError:
            return False
        # Note strings can be infinitely descended through - thus this
        # recursion limiter.
        return not isinstance(item, str) or len(item) > 1

    if not descend_into(iterable):
        yield iterable
        return
    for item in iterable:
        if not descend_into(item):
            yield item
        else:
            for subitem in iflatten_instance(item, terminate_on_kls):
                yield subitem


def UserDateTimeFormat(timeval=None):
    """Format a date meant to be viewed by a user

    The focus here is to have a format that is easily readable by humans,
    but still easy (and unambiguous) for a machine to parse.  Hence, we
    use the RFC 2822 date format (with timezone name appended).

    Args:
        timeval: Either a datetime object or a floating point time value as
            accepted by gmtime()/localtime(). If None, the current time is used.

    Returns:
        A string format such as 'Wed, 20 Feb 2013 15:25:15 -0500 (EST)'
    """
    if isinstance(timeval, datetime.datetime):
        timeval = time.mktime(timeval.timetuple())
    return "%s (%s)" % (
        email.utils.formatdate(timeval=timeval, localtime=True),
        time.strftime("%Z", time.localtime(timeval)),
    )


def ParseUserDateTimeFormat(time_string):
    """Parse a time string into a floating point time value.

    This function is essentially the inverse of UserDateTimeFormat.

    Args:
        time_string: A string datetime representation in RFC 2822 format, such
            as 'Wed, 20 Feb 2013 15:25:15 -0500 (EST)'.

    Returns:
        Floating point Unix timestamp (seconds since epoch).
    """
    return email.utils.mktime_tz(email.utils.parsedate_tz(time_string))


def GetDefaultBoard():
    """Gets the default board.

    Returns:
        The default board (as a string), or None if either the default board
        file was missing or malformed.
    """
    default_board_file_name = os.path.join(
        constants.SOURCE_ROOT, "src", "scripts", ".default_board"
    )
    try:
        default_board = osutils.ReadFile(default_board_file_name).strip()
    except IOError:
        return None

    # Check for user typos like whitespace
    if not re.match("[a-zA-Z0-9-_]*$", default_board):
        logging.warning(
            "Noticed invalid default board: |%s|. Ignoring this default.",
            default_board,
        )
        default_board = None

    return default_board


def SetDefaultBoard(board: str):
    """Set the default board.

    Args:
        board: The name of the board to save as the default.

    Returns:
        bool - True if successfully wrote default, False otherwise.
    """
    config_path = constants.CROSUTILS_DIR / ".default_board"
    try:
        osutils.WriteFile(config_path, board)
    except IOError as e:
        logging.error("Unable to write default board: %s", e)
        return False

    return True


def GetBoard(device_board, override_board=None, force=False, strict=False):
    """Gets the board name to use.

    Ask user to confirm when |override_board| and |device_board| are
    both None.

    Args:
        device_board: The board detected on the device.
        override_board: Overrides the board.
        force: Force using the default board if |device_board| is None.
        strict: If True, abort if no valid board can be found.

    Returns:
        Returns the first non-None board in the following order:
        |override_board|, |device_board|, and GetDefaultBoard().

    Raises:
        DieSystemExit: If board is not set or user enters no.
    """
    if override_board:
        return override_board

    board = device_board or GetDefaultBoard()
    if not device_board:
        if not board and strict:
            Die("No board specified and no default board found.")
        msg = "Cannot detect board name; using default board %s." % board
        if not force and not BooleanPrompt(default=False, prolog=msg):
            Die("Exiting...")

        logging.warning(msg)

    return board


def GetRandomString():
    """Returns a random string.

    It will be 32 characters long, although callers shouldn't rely on this.
    Only lowercase & numbers are used to avoid case-insensitive collisions.
    """
    # Start with current time.  This "scopes" the following random data.
    stamp = b"%x" % int(time.time())
    # Add in some entropy.  This reads more bytes than strictly necessary, but
    # it guarantees that we always have enough bytes below.
    data = os.urandom(16)
    # Then convert it to a lowercase base32 string of 32 characters.
    return base64.b32encode(stamp + data).decode("utf-8")[0:32].lower()


def MachineDetails():
    """Returns a string to help identify the source of a job.

    This is not meant for machines to parse; instead, we want content that is
    easy for humans to read when trying to figure out where "something" is
    coming from. For example, when a service has grabbed a lock in Google
    Storage, and we want to see what process actually triggered that (in case it
    is a test gone rogue), the content in here should help triage.

    Note: none of the details included may be secret, so they can be freely
        pasted into bug reports/chats/logs/etc...

    Note: this content should not be large

    Returns:
        A string with content that helps identify this system/process/etc...
    """
    return (
        "\n".join(
            (
                "PROG=%s" % inspect.stack()[-1][1],
                "USER=%s" % getpass.getuser(),
                "HOSTNAME=%s"
                % hostname_util.get_host_name(fully_qualified=True),
                "PID=%s" % os.getpid(),
                "TIMESTAMP=%s" % UserDateTimeFormat(),
                "RANDOM_JUNK=%s" % GetRandomString(),
            )
        )
        + "\n"
    )


def UnbufferedTemporaryFile(**kwargs):
    """Handle buffering changes in tempfile.TemporaryFile."""
    # File handles are closed in tempfile's close() overload or on garbage
    # collection.
    # pylint: disable=consider-using-with
    return tempfile.TemporaryFile(buffering=0, **kwargs)


def UnbufferedNamedTemporaryFile(**kwargs):
    """Handle buffering changes in tempfile.NamedTemporaryFile."""
    # File handles are closed in tempfile's close() overload or on garbage
    # collection.
    # pylint: disable=consider-using-with
    return tempfile.NamedTemporaryFile(buffering=0, **kwargs)


def ClearShadowLocks(sysroot: Union[str, os.PathLike] = "/") -> None:
    """Clears out stale shadow-utils locks in the given sysroot."""
    sysroot = Path(sysroot)
    logging.info("Clearing shadow-utils lockfiles under %s", sysroot)
    filenames = ("passwd.lock", "group.lock", "shadow.lock", "gshadow.lock")
    etc_path = sysroot / "etc"
    if not etc_path.exists():
        logging.warning(
            "Unable to clear shadow-utils lockfiles, path does not exist: %s",
            etc_path,
        )
        return
    for f in (x for x in os.listdir(etc_path) if x.startswith(filenames)):
        osutils.RmDir(etc_path / f, ignore_missing=True, sudo=True)
