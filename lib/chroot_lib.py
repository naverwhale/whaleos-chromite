# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Chroot class.

This is currently a very sparse class, but there's a significant amount of
functionality that can eventually be centralized here.
"""

import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, TYPE_CHECKING, Union

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import path_util


if TYPE_CHECKING:
    from chromite.lib import goma_lib
    from chromite.lib import remoteexec_util


class Error(Exception):
    """Base chroot_lib error class."""


class ChrootError(Error):
    """An exception raised when something went wrong with a chroot object."""


class Chroot:
    """Chroot class."""

    def __init__(
        self,
        path: Optional[Union[str, os.PathLike]] = None,
        out_path: Optional[Path] = None,
        cache_dir: Optional[str] = None,
        chrome_root: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        goma: Optional["goma_lib.Goma"] = None,
        remoteexec: Optional["remoteexec_util.Remoteexec"] = None,
    ):
        """Initialize.

        Args:
            path: Path to the chroot.
            out_path: Path to the out directory.
            cache_dir: Path to a directory that will be used for caching files.
            chrome_root: Root of the Chrome browser source checkout.
            env: Extra environment settings to use.
            goma: Interface for utilizing goma.
            remoteexec: Interface for utilizing remoteexec client.
        """
        # Strip trailing / if present for consistency.
        # TODO(vapier): Switch this to Path instead of str.
        self._path = (
            str(path) if path else constants.DEFAULT_CHROOT_PATH
        ).rstrip("/")
        self._out_path = out_path if out_path else constants.DEFAULT_OUT_PATH
        self._is_default_path = not bool(path)
        self._is_default_out_path = not out_path
        self._env = env
        self.goma = goma
        self.remoteexec = remoteexec
        # String in proto are '' when not set, but testing and comparing is much
        # easier when the "unset" value is consistent, so do an explicit "or
        # None".
        self.cache_dir = cache_dir or None
        self.chrome_root = chrome_root or None

    def __eq__(self, other):
        if self.__class__ is other.__class__:
            return (
                self.path == other.path
                and self.out_path == other.out_path
                and self.cache_dir == other.cache_dir
                and self.chrome_root == other.chrome_root
                and self.env == other.env
            )

        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.path)

    @property
    def path(self) -> str:
        return self._path

    @property
    def out_path(self) -> Path:
        return self._out_path

    def exists(self) -> bool:
        """Checks if the chroot exists."""
        return os.path.exists(self.path) and self.out_path.exists()

    @property
    def tmp(self) -> str:
        """Get the chroot's tmp dir."""
        return self.full_path("/tmp")

    def tempdir(self, delete=True) -> osutils.TempDir:
        """Get a TempDir in the chroot's tmp dir."""
        return osutils.TempDir(base_dir=self.tmp, delete=delete)

    def chroot_path(self, path: Union[str, os.PathLike]) -> str:
        """Turn an absolute path into a chroot relative path."""
        return path_util.ToChrootPath(
            path=path, chroot_path=self._path, out_path=self._out_path
        )

    def full_path(self, *args: Union[str, os.PathLike]) -> str:
        """Turn a fully expanded chrootpath into an host-absolute path."""
        path = os.path.join(os.path.sep, *args)
        return path_util.FromChrootPath(
            path=path, chroot_path=self._path, out_path=self._out_path
        )

    def has_path(self, *args: str) -> bool:
        """Check if a chroot-relative path exists inside the chroot."""
        return os.path.exists(self.full_path(*args))

    def get_enter_args(self, for_shell: bool = False) -> List[str]:
        """Build the arguments to enter this chroot.

        Args:
            for_shell: Whether the return value will be used when using the old
                src/scripts/ shell code or with newer `cros_sdk` interface.

        Returns:
            The command line arguments to pass to the enter chroot program.
        """
        args = []

        # The old src/scripts/sdk_lib/enter_chroot.sh uses shflags which only
        # accepts _ in option names.  Our Python code uses - instead.
        # TODO(build): Delete this once sdk_lib/enter_chroot.sh is gone.
        sep = "_" if for_shell else "-"

        # This check isn't strictly necessary, always passing the --chroot
        # argument is valid, but it's nice for cleaning up commands in logs.
        if not self._is_default_path:
            args.extend(["--chroot", self.path])
        if not self._is_default_out_path:
            args.extend([f"--out{sep}dir", str(self.out_path)])
        if self.cache_dir:
            args.extend([f"--cache{sep}dir", self.cache_dir])
        if self.chrome_root:
            args.extend([f"--chrome{sep}root", self.chrome_root])
        if self.goma:
            args.extend(
                [
                    f"--goma{sep}dir",
                    str(self.goma.linux_goma_dir),
                ]
            )
        if self.remoteexec:
            args.extend(
                [
                    f"--reclient{sep}dir",
                    str(self.remoteexec.reclient_dir),
                    f"--reproxy{sep}cfg{sep}file",
                    str(self.remoteexec.reproxy_cfg_file),
                ]
            )

        return args

    @property
    def env(self) -> Dict[str, str]:
        env = self._env.copy() if self._env else {}
        if self.goma:
            env.update(self.goma.GetChrootExtraEnv())
        if self.remoteexec:
            env.update(self.remoteexec.GetChrootExtraEnv())

        return env

    def _runner(
        self,
        func: Callable[..., cros_build_lib.CompletedProcess],
        cmd: Union[List[str], str],
        **kwargs,
    ) -> cros_build_lib.CompletedProcess:
        # Merge provided |extra_env| with self.env.
        extra_env = {**self.env, **(kwargs.pop("extra_env", None) or {})}
        chroot_args = self.get_enter_args() + kwargs.pop("chroot_args", [])
        return func(
            cmd,
            enter_chroot=True,
            chroot_args=chroot_args,
            extra_env=extra_env,
            **kwargs,
        )

    def run(
        self, cmd: Union[List[str], str], **kwargs
    ) -> cros_build_lib.CompletedProcess:
        """Run a command inside this chroot.

        A convenience wrapper around cros_build_lib.run().
        """
        return self._runner(cros_build_lib.run, cmd, **kwargs)

    def sudo_run(
        self, cmd: Union[List[str], str], **kwargs
    ) -> cros_build_lib.CompletedProcess:
        """Run a sudo command inside this chroot.

        A convenience wrapper around cros_build_lib.sudo_run().
        """
        return self._runner(cros_build_lib.sudo_run, cmd, **kwargs)
