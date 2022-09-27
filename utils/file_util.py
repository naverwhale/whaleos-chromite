# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""File interaction utilities."""

import contextlib
from pathlib import Path
from typing import TextIO, TYPE_CHECKING, Union

if TYPE_CHECKING:
  import os


@contextlib.contextmanager
def Open(obj: Union[str, 'os.PathLike', TextIO], mode: str = 'r', **kwargs):
  """Convenience ctx that accepts a file path or an already open file object."""
  if isinstance(obj, str):
    with open(obj, mode=mode, **kwargs) as f:
      yield f
  elif isinstance(obj, Path):
    yield obj.open(mode=mode, **kwargs)
  else:
    yield obj
