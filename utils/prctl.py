# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Python API for the prctl() syscall."""

import ctypes
import ctypes.util
import enum
import errno
import os
from typing import List, Optional


class Option(enum.IntEnum):
    """Known prctl options."""

    # arg2 is int* input.
    SET_PDEATHSIG = 1

    # arg2 is int* output.
    GET_PDEATHSIG = 2

    # arg2 is char* input.
    SET_NAME = 15

    # arg2 is char* output.
    GET_NAME = 16

    # arg2 is int input.
    SET_NO_NEW_PRIVS = 38

    # arg2 is int* output.
    GET_NO_NEW_PRIVS = 39


class Error(Exception):
    """Base class for errors in this module."""


class PrctlError(OSError, Error):
    """prctl() call failed."""

    option: Option
    returncode: int
    # NB: Can't call |args| as Error.args already takes that over.
    prargs: List[int]

    # pylint: disable=redefined-outer-name
    def __init__(
        self,
        option: Option,
        returncode: int,
        prargs: List[int] = None,
        errno: int = None,
    ):
        if errno is None:
            errno = ctypes.get_errno()
        # We have to expand the errno string ourselves as Python will not, and
        # will ignore the first argument (errno) if not provided.
        OSError.__init__(self, errno, os.strerror(errno))
        Error.__init__(self, option, returncode, prargs, errno)

        self.option = option
        self.returncode = returncode
        self.prargs = list(prargs) if prargs else []

    @property
    def msg(self) -> str:
        str_args = "".join(", {x}" for x in self.prargs)
        str_errno = ""
        if bool(self.errno):
            str_errno = (
                f" ({errno.errorcode.get(self.errno, 'E???')}[{self.errno}])"
            )
        return (
            f"prctl({self.option.name}{str_args}) failed: "
            f"ret={self.returncode}{str_errno}"
        )

    def __str__(self) -> str:
        str_errno = ""
        if bool(self.errno):
            str_errno = f", {errno.errorcode.get(self.errno, 'E???')}"
        return (
            f"PrctlError({self.option.name}, {self.returncode}, "
            f"{self.prargs}{str_errno})"
        )


def prctl(
    option: Option, arg2: int = 0, arg3: int = 0, arg4: int = 0, arg5: int = 0
) -> Optional[int]:
    """Wrapper around prctl().

    See the man page for documentation:
    https://man7.org/linux/man-pages/man2/prctl.2.html

    Examples:
        # For options that only take input integers, the API is simple.
        prctl.prctl(prctl.Option.SET_PDEATHSIG, signal.SIGHUP)

        # For options that output arguments, the caller must pass in pointers.
        arg2 = ctypes.c_int(0)
        prctl.prctl(prctl.Option.GET_PDEATHSIG, ctypes.byref(arg2))
        print(arg2.value)
    """
    libc_name = ctypes.util.find_library("c")
    libc = ctypes.CDLL(libc_name, use_errno=True)

    # Clear the errno so the caller can determine whether this call failed.
    ctypes.set_errno(0)

    # NB: It's safe to call prctl with unused args as they'll get ignored, and
    # it's safer to explicitly specify a default of 0 rather than leave whatever
    # garbage is in the register.
    ret = libc.prctl(option, arg2, arg3, arg4, arg5)

    c_errno = ctypes.get_errno()
    if c_errno:
        raise PrctlError(option, ret, [arg2, arg3, arg4, arg5], c_errno)

    return ret


def _set_int(option: Option, value: int) -> None:
    """Helper for functions that have a single input integer."""
    ret = prctl(option, value)
    if ret:
        raise PrctlError(option, ret, [value])


def _get_int(option: Option) -> int:
    """Helper for functions that have a single output integer."""
    value = ctypes.c_int(0)
    ret = prctl(option, ctypes.byref(value))
    if ret:
        raise PrctlError(option, ret)
    return value.value


def _set_str(option: Option, value: str) -> None:
    """Helper for functions that have a single input string."""
    c_str = ctypes.create_string_buffer(value.encode("utf-8"))
    ret = prctl(option, ctypes.byref(c_str))
    if ret:
        raise PrctlError(option, ret, [value])


def _get_str(option: Option, length: int) -> str:
    """Helper for functions that have a single output string."""
    c_str = ctypes.create_string_buffer(length)
    ret = prctl(Option.GET_NAME, ctypes.byref(c_str))
    if ret:
        raise PrctlError(option, ret)
    return c_str.value.decode("utf-8")


def set_pdeathsig(value: int) -> None:
    """SET_PDEATHSIG wrapper."""
    _set_int(Option.SET_PDEATHSIG, value)


def get_pdeathsig() -> int:
    """GET_PDEATHSIG wrapper."""
    return _get_int(Option.GET_PDEATHSIG)


def set_name(name: str) -> None:
    """SET_NAME (thread name) wrapper."""
    _set_str(Option.SET_NAME, name)


def get_name() -> str:
    """GET_NAME (thread name) wrapper."""
    # Return is 16 bytes, and it's always NUL terminated.
    return _get_str(Option.GET_NAME, 16)


def set_no_new_privs(value: int = 1) -> None:
    """SET_NO_NEW_PRIVS wrapper."""
    _set_int(Option.SET_NO_NEW_PRIVS, value)


def get_no_new_privs() -> int:
    """GET_NO_NEW_PRIVS wrapper."""
    ret = prctl(Option.GET_NO_NEW_PRIVS)
    if ret not in (0, 1):
        raise PrctlError(Option.GET_NO_NEW_PRIVS, ret)
    return ret
