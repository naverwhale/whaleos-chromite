# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module that handles tee-ing output to a file."""

import errno
import fcntl
import multiprocessing
import os
import select
import signal
import sys
import traceback
import warnings

from chromite.cbuildbot import cbuildbot_alerts
from chromite.lib import cros_build_lib


warnings.warn("lib/tee.py is deprecated", DeprecationWarning)

# Max amount of data we're hold in the buffer at a given time.
_BUFSIZE = 1024


# Custom signal handlers so we can catch the exception and handle it.
class ToldToDie(Exception):
    """Exception thrown via signal handlers."""

    def __init__(self, signum):
        Exception.__init__(self, f"We received signal {signum}")


def _TeeProcessSignalHandler(signum, _frame):
    """TeeProcess custom signal handler.

    This is used to decide whether to kill our parent.
    """
    raise ToldToDie(signum)


def _output(line, output_files, complain):
    """Print line to output_files.

    Args:
        line: Line to print.
        output_files: List of files to print to.
        complain: Print a warning if we get EAGAIN errors. Only one error is
            printed per line.
    """
    for f in output_files:
        offset = 0
        while offset < len(line):
            select.select([], [f], [])
            try:
                offset += os.write(f.fileno(), line[offset:])
            except OSError as ex:
                if ex.errno == errno.EINTR:
                    continue
                elif ex.errno != errno.EAGAIN:
                    raise

            if offset < len(line) and complain:
                flags = fcntl.fcntl(f.fileno(), fcntl.F_GETFL, 0)
                if flags & os.O_NONBLOCK:
                    warning = (
                        f"\nWarning: {f.name}/{f.fileno()} is non-blocking.\n"
                    )
                    _output(warning, output_files, False)

                warning = f"\nWarning: Short write for {f.name}/{f.fileno()}.\n"
                _output(warning, output_files, False)


def _tee(input_fd, output_files, complain):
    """Read data from |input_fd| and write to |output_files|."""
    while True:
        # We need to use os.read() directly because it will return to us when
        # the other side has flushed its output (and is shorter than _BUFSIZE).
        # If we use python's file object helpers (like read() and readline()),
        # it will not return until either the full buffer is filled or a newline
        # is hit.
        data = os.read(input_fd, _BUFSIZE)
        if not data:
            return
        _output(data, output_files, complain)


class _TeeProcess(multiprocessing.Process):
    """Replicate output to multiple file handles."""

    def __init__(self, output_filenames, complain, error_fd, master_pid):
        """Write to stdout and supplied filenames.

        Args:
            output_filenames: List of filenames to print to.
            complain: Print a warning if we get EAGAIN errors.
            error_fd: The fd to write exceptions/errors to during shutdown.
            master_pid: Pid to SIGTERM if we shutdown uncleanly.
        """

        self._reader_pipe, self.writer_pipe = os.pipe()
        self._output_filenames = output_filenames
        self._complain = complain
        # Dupe the fd on the off chance it's stdout/stderr,
        # which we screw with.
        # Not passing 3 argument (0) for unbuffered output because this is not
        # supported in Python 3 and there are issues in Python 2 -- see
        # https://bugs.python.org/issue17404.
        self._error_handle = os.fdopen(os.dup(error_fd), "w")
        self.master_pid = master_pid
        multiprocessing.Process.__init__(self)

    def _CloseUnnecessaryFds(self):
        # For python2 we were relying on subprocess.MAXFD but that does not
        # exist in python3. However, the calculation below is how it was being
        # computed.
        try:
            max_fd_value = os.sysconf("SC_OPEN_MAX")
        except ValueError:
            max_fd_value = 256
        preserve = {
            1,
            2,
            self._error_handle.fileno(),
            self._reader_pipe,
            max_fd_value,
        }
        preserve = iter(sorted(preserve))
        fd = 0
        while fd < max_fd_value:
            current_low = next(preserve)
            if fd != current_low:
                os.closerange(fd, current_low)
                fd = current_low
            fd += 1

    def run(self):
        """Main function for tee subprocess."""
        failed = True
        input_fd = None
        try:
            signal.signal(signal.SIGINT, _TeeProcessSignalHandler)
            signal.signal(signal.SIGTERM, _TeeProcessSignalHandler)

            # Cleanup every fd except for what we use.
            self._CloseUnnecessaryFds()

            # Read from the pipe.
            input_fd = self._reader_pipe

            # Create list of files to write to.
            # Not passing 3 argument (0) for unbuffered output because this is
            # not supported in Python 3 and there are issues in Python 2 -- see
            # https://bugs.python.org/issue17404.
            output_files = [os.fdopen(sys.stdout.fileno(), "w")]
            for filename in self._output_filenames:
                # TODO(b/236161656): Fix.
                # pylint: disable-next=consider-using-with
                output_files.append(open(filename, "w", encoding="utf-8"))

            # Send all data from the one input to all the outputs.
            _tee(input_fd, output_files, self._complain)
            failed = False
        except ToldToDie:
            failed = False
        except Exception:
            tb = traceback.format_exc()
            cbuildbot_alerts.PrintBuildbotStepFailure(self._error_handle)
            self._error_handle.write(
                f"Unhandled exception occurred in tee:\n{tb}\n"
            )
            # Try to signal the parent telling them of our
            # imminent demise.

        finally:
            # Close input.
            if input_fd:
                os.close(input_fd)

            if failed:
                try:
                    os.kill(self.master_pid, signal.SIGTERM)
                except Exception as e:
                    self._error_handle.write(f"\nTee failed signaling {e}\n")

            # Finally, kill ourself.
            # Specifically do it in a fashion that ensures no inherited
            # cleanup code from our parent process is ran - leave that to
            # the parent.
            # pylint: disable=protected-access
            os._exit(0)


class Tee(cros_build_lib.PrimaryPidContextManager):
    """Class that handles tee-ing output to a file."""

    def __init__(self, output_file):
        """Initializes object with path to log file."""
        cros_build_lib.PrimaryPidContextManager.__init__(self)
        self._file = output_file
        self._old_stdout = None
        self._old_stderr = None
        self._old_stdout_fd = None
        self._old_stderr_fd = None
        self._tee = None

    def start(self):
        """Start tee-ing all stdout and stderr output to the file."""
        # Flush and save old file descriptors.
        sys.stdout.flush()
        sys.stderr.flush()
        self._old_stdout_fd = os.dup(sys.stdout.fileno())
        self._old_stderr_fd = os.dup(sys.stderr.fileno())
        # Save file objects
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr

        # Replace std[out|err] with unbuffered file objects
        # Not passing 3 argument (0) for unbuffered output because this is not
        # supported in Python 3 and there are issues in Python 2 -- see
        # https://bugs.python.org/issue17404.
        sys.stdout = os.fdopen(sys.stdout.fileno(), "w")
        sys.stderr = os.fdopen(sys.stderr.fileno(), "w")

        # Create a tee subprocess.
        self._tee = _TeeProcess(
            [self._file], True, self._old_stderr_fd, os.getpid()
        )
        self._tee.start()

        # Redirect stdout and stderr to the tee subprocess.
        writer_pipe = self._tee.writer_pipe
        os.dup2(writer_pipe, sys.stdout.fileno())
        os.dup2(writer_pipe, sys.stderr.fileno())
        os.close(writer_pipe)

    def stop(self):
        """Restore old stdout/stderr handles and wait for tee proc to exit."""
        # Close unbuffered std[out|err] file objects, as well as the tee's
        # stdin.
        sys.stdout.close()
        sys.stderr.close()

        # Restore file objects
        sys.stdout = self._old_stdout
        sys.stderr = self._old_stderr

        # Restore old file descriptors.
        os.dup2(self._old_stdout_fd, sys.stdout.fileno())
        os.dup2(self._old_stderr_fd, sys.stderr.fileno())
        os.close(self._old_stdout_fd)
        os.close(self._old_stderr_fd)
        self._tee.join()

    def _enter(self):
        self.start()

    def _exit(self, exc_type, exc, exc_tb):
        try:
            self.stop()
        finally:
            if self._tee is not None:
                self._tee.terminate()
