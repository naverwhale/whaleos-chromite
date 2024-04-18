# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrap the clang-format binary from gs://chromium-clang-format"""

import contextlib
import os
from typing import ContextManager, Sequence

from chromite.lib import cache
from chromite.lib import cros_build_lib
from chromite.lib import path_util
from chromite.utils import gs_urls_util


CLANG_FORMAT_BUCKET = "gs://chromium-clang-format"

# The SHA-1 checksum of the clang-format binary.
# Refer to clang-format.sha1 to see what chromium uses:
# https://chromium.googlesource.com/chromium/src/+/HEAD/buildtools/linux64/clang-format.sha1
CLANG_FORMAT_SHA1 = "6ef2183a178a53e47e4448dbe192b1d8d5290222"


class ClangFormatCache(cache.RemoteCache):
    """Supports caching the clang-format executable."""

    def _Fetch(
        self, url: str, local_path: str
    ):  # pylint: disable=arguments-differ
        expected_sha1 = url.rsplit("/", 1)[-1]
        super()._Fetch(url, local_path, hash_sha1=expected_sha1, mode=0o755)


def GetClangFormatCache() -> ClangFormatCache:
    """Returns the cache instance for the clang-format binary."""
    cache_dir = os.path.join(path_util.FindCacheDir(), "chromium-clang-format")
    return ClangFormatCache(cache_dir)


@contextlib.contextmanager
def ClangFormat() -> ContextManager[str]:
    """Context manager returning the clang-format binary."""
    key = (CLANG_FORMAT_SHA1,)
    url = gs_urls_util.GsUrlToHttp(f"{CLANG_FORMAT_BUCKET}/{CLANG_FORMAT_SHA1}")
    with GetClangFormatCache().Lookup(key) as ref:
        if not ref.Exists(lock=True):
            ref.SetDefault(url, lock=True)
        yield ref.path


def main(argv: Sequence[str] = ()) -> int:
    with ClangFormat() as clang_format:
        return cros_build_lib.run(
            ["clang-format", *argv],
            executable=clang_format,
            print_cmd=False,
            check=False,
        ).returncode
