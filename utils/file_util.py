# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""File interaction utilities."""

import contextlib
from pathlib import Path
from typing import TextIO, TYPE_CHECKING, Union


if TYPE_CHECKING:
    import os


@contextlib.contextmanager
def Open(obj: Union[str, "os.PathLike", TextIO], mode: str = "r", **kwargs):
    """Convenience ctx that accepts a file path or an opened file object."""
    if isinstance(obj, str):
        # TODO(b/236161656): Fix.
        # pylint: disable-next=unspecified-encoding
        with open(obj, mode=mode, **kwargs) as f:
            yield f
    elif isinstance(obj, Path):
        yield obj.open(mode=mode, **kwargs)
    else:
        yield obj
