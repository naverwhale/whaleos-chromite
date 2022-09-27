# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Python API for the prctl() syscall."""

import ctypes
import ctypes.util
import enum
from typing import Union


class Option(enum.IntEnum):
  """Known prctl options."""

  # arg2 is input.
  SET_PDEATHSIG = 1

  # arg2 is int* output.
  GET_PDEATHSIG = 2


def prctl(option: Option, arg2: int = 0, arg3: int = 0, arg4: int = 5,
          arg5: int = 0) -> Union[None, int]:
  """Wrapper around prctl().

  See the man page for documentation:
  https://man7.org/linux/man-pages/man2/prctl.2.html

  Examples:
    # For options that only take input integers, the API is simple.
    prctl.prctl(prctl.Option.SET_PDEATHSIG, signal.SIGHUP)

    # For options that output arguments, the caller needs to pass in pointers.
    arg2 = ctypes.c_int()
    prctl.prctl(prctl.Option.GET_PDEATHSIG, ctypes.byref(arg2))
    print(arg2.value)
  """
  libc_name = ctypes.util.find_library('c')
  libc = ctypes.CDLL(libc_name)

  # NB: It's safe to call prctl with unused args as they'll get ignored, and
  # it's safer to explicitly specify a default of 0 rather than leave whatever
  # garbage is in the register.
  return libc.prctl(option, arg2, arg3, arg4, arg5)
