# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for setting up and cleaning up the chroot environment."""

import ast
import collections
import functools
import grp
import logging
import os
from pathlib import Path
import pwd
import resource
import shutil
import sys
from typing import List, Optional, Set, Union

from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import locking
from chromite.lib import metrics_lib
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.lib import timeout_util


# Version file location inside chroot.
CHROOT_VERSION_FILE = "/etc/cros_chroot_version"
# Version hooks directory.
_CHROOT_VERSION_HOOKS_DIR = constants.CROSUTILS_DIR / "chroot_version_hooks.d"

# Bash completion directory.
_BASH_COMPLETION_DIR = (
    f"{constants.CHROOT_SOURCE_ROOT}/chromite/sdk/etc/bash_completion.d"
)

# Pairs of "old chroot location" and "new chroot location." Older SDKs mixed
# chroot state throughout the chroot tree; we'll migrate contents from the old
# path (prefixed at the "chroot" base) to the new path (prefixed at the "output
# directory" base).
_CHROOT_STATE_MIGRATIONS = (
    ("tmp", "tmp"),
    ("home", "home"),
    ("build", "build"),
    ("usr/local/bin", "sdk/bin"),
    ("var/cache", "sdk/cache"),
    ("var/log", "sdk/logs"),
    ("var/tmp", "sdk/tmp"),
)


class Error(Exception):
    """Base cros sdk error class."""


class ChrootDeprecatedError(Error):
    """Raised when the chroot is too old to update."""

    def __init__(self, version):
        # Message defined here because it's long and gives specific
        # instructions.
        super().__init__(
            f"Upgrade hook missing for your chroot version {version}.\n"
            "Your chroot is so old that some updates have been deprecated and "
            "it will need to be recreated. A fresh chroot can be built "
            "with:\n"
            "    cros_sdk --replace"
        )


class ChrootUpdateError(Error):
    """Error encountered when updating the chroot."""


class InvalidChrootVersionError(Error):
    """Chroot version is not a valid version."""


class UninitializedChrootError(Error):
    """Chroot has not been initialized."""


class VersionHasMultipleHooksError(Error):
    """When it is found that a single version has multiple hooks."""


def is_inside_chroot() -> bool:
    """Returns True if we are inside chroot."""
    return os.path.exists(CHROOT_VERSION_FILE)


def is_outside_chroot() -> bool:
    """Returns True if we are outside chroot."""
    return not is_inside_chroot()


def assert_inside_chroot(name: Optional[str] = None):
    """Die if we are outside the chroot"""
    name = name or Path(sys.argv[0]).name
    assert is_inside_chroot(), f"{name}: please run inside the chroot"


def assert_outside_chroot(name: Optional[str] = None):
    """Die if we are inside the chroot"""
    name = name or Path(sys.argv[0]).name
    assert is_outside_chroot(), f"{name}: please run outside the chroot"


def require_inside_chroot(_reason: str = ""):
    """Decorator to assert a function must be called when inside the SDK."""

    def outer(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            assert_inside_chroot(func.__name__)
            return func(*args, **kwargs)

        return wrapper

    return outer


def require_outside_chroot(_reason: str = ""):
    """Decorator to assert a function must be called when outside the SDK."""

    def outer(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            assert_outside_chroot(func.__name__)
            return func(*args, **kwargs)

        return wrapper

    return outer


def require_chroot(_reason: str = ""):
    """Decorator to note the function requires the SDK.

    The function can be called from inside or outside the SDK and the function
    handles entering as needed, but a chroot must have been instantiated.
    This is currently only for documentation purposes.
    """

    def outer(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return outer


def chroot_not_required(func):
    """Decorator to note the SDK has no effect on the function.

    The function does not use SDK specific functionality, and behaves
    identically inside and outside the SDK. This is currently only for
    documentation purposes.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def GetChrootVersion(chroot):
    """Extract the version of the chroot.

    Args:
        chroot: Full path to the chroot to examine.

    Returns:
        The version of the chroot dir, or None if the version is
        missing/invalid.
    """
    if chroot:
        ver_path = os.path.join(chroot, CHROOT_VERSION_FILE.lstrip(os.sep))
    else:
        ver_path = CHROOT_VERSION_FILE

    updater = ChrootUpdater(version_file=ver_path)
    try:
        return updater.GetVersion()
    except (IOError, Error) as e:
        logging.debug(e)

    return None


def IsChrootVersionValid(chroot_path, hooks_dir=None):
    """Check if the chroot version exists and is a valid version."""
    version = GetChrootVersion(chroot_path)
    return version and version <= LatestChrootVersion(hooks_dir)


def LatestChrootVersion(hooks_dir=None):
    """Get the most recent update hook version."""
    hook_files = os.listdir(hooks_dir or _CHROOT_VERSION_HOOKS_DIR)

    # Hook file names must follow the "version_short_description" convention.
    # Pull out just the version number and find the max.
    return max(int(hook.split("_", 1)[0]) for hook in hook_files)


def EarliestChrootVersion(hooks_dir=None):
    """Get the oldest update hook version."""
    hook_files = os.listdir(hooks_dir or _CHROOT_VERSION_HOOKS_DIR)

    # Hook file names must follow the "version_short_description" convention.
    # Pull out just the version number and find the max.
    return min(int(hook.split("_", 1)[0]) for hook in hook_files)


def IsChrootDirValid(chroot_path):
    """Check the permissions and owner on a chroot directory.

    Args:
        chroot_path: The path to a chroot.

    Returns:
        bool - False iff there are incorrect values on an existing directory.
    """
    if not os.path.exists(chroot_path):
        # No directory == no incorrect values.
        return True

    return IsChrootOwnerValid(chroot_path) and IsChrootPermissionsValid(
        chroot_path
    )


def IsChrootOwnerValid(chroot_path):
    """Check if the chroot owner is root."""
    chroot_stat = os.stat(chroot_path)
    return not chroot_stat.st_uid and not chroot_stat.st_gid


def IsChrootPermissionsValid(chroot_path):
    """Check if the permissions on the directory are correct."""
    chroot_stat = os.stat(chroot_path)
    return chroot_stat.st_mode & 0o7777 == 0o755


def IsChrootReady(chroot):
    """Checks if the chroot is mounted and set up.

    /etc/cros_chroot_version is set to the current version of the chroot at the
    end of the setup process.  If this file exists and contains a non-zero
    value, the chroot is ready for use.

    Args:
        chroot: Full path to the chroot to examine.

    Returns:
        True iff the chroot contains a valid version.
    """
    version = GetChrootVersion(chroot)
    return version is not None and version > 0


def MountChrootPaths(chroot: chroot_lib.Chroot):
    """Setup all the mounts for the |chroot|.

    NB: This assumes running in a unique mount namespace.  If it is running in
    the root mount namespace, then it will probably change settings for the
    worse.
    """
    KNOWN_FILESYSTEMS = set(
        x.split()[-1]
        for x in osutils.ReadFile("/proc/filesystems").splitlines()
    )

    path = Path(chroot.path).resolve()
    out_dir = chroot.out_path

    logging.debug("Mounting chroot paths at %s", path)

    # Mark all existing mounts as slave mounts: that means changes made to
    # mounts in the parent mount namespace will propagate down (like unmounts).
    osutils.Mount(None, "/", None, osutils.MS_REC | osutils.MS_SLAVE)

    # If the mount path is already mounted, make it private so we can make
    # changes without it propagating back out.
    for info in osutils.IterateMountPoints():
        if info.destination == str(path):
            osutils.Mount(None, path, None, osutils.MS_REC | osutils.MS_PRIVATE)
            break

    # The source checkout must be mounted first.  We'll be mounting paths into
    # the chroot, and that chroot may live inside SOURCE_ROOT, so if we did
    # the recursive bind at the end, we'd double bind things.
    osutils.Mount(
        constants.SOURCE_ROOT,
        path / constants.CHROOT_SOURCE_ROOT.relative_to("/"),
        "~/chromiumos",
        osutils.MS_BIND | osutils.MS_REC,
    )

    # Prepare for pivot_root(2). `man 2 pivot_root` says new_root must be a
    # mount point.
    osutils.Mount(
        path,
        path,
        None,
        osutils.MS_BIND | osutils.MS_REC,
    )

    osutils.SafeMakedirsNonRoot(out_dir)
    osutils.SafeMakedirs(path / constants.CHROOT_OUT_ROOT.relative_to("/"))
    osutils.Mount(
        out_dir,
        path / constants.CHROOT_OUT_ROOT.relative_to("/"),
        None,
        osutils.MS_BIND | osutils.MS_REC,
    )

    for source_dir, dest_dir, mode in (
        ("tmp", "tmp", 0o1777),
        ("home", "home", None),
        ("build", "build", None),
        ("sdk/bin", "usr/local/bin", None),
        ("sdk/cache", "var/cache", None),
        ("sdk/run", "run", None),
        ("sdk/logs", "var/log", None),
        ("sdk/tmp", "var/tmp", 0o1777),
    ):
        kwargs = {}
        if mode is not None:
            kwargs["mode"] = mode

        osutils.SafeMakedirsNonRoot(out_dir / source_dir, **kwargs)
        osutils.SafeMakedirs(path / dest_dir)
        osutils.Mount(
            out_dir / source_dir,
            path / dest_dir,
            None,
            osutils.MS_BIND | osutils.MS_REC,
        )

    # Bind mount a few /etc files, so sysroots can add their own users/groups.
    for src, dst in (
        ("sdk/passwd", "etc/passwd"),
        ("sdk/group", "etc/group"),
        ("sdk/shadow", "etc/shadow"),
    ):
        if not (out_dir / src).exists():
            # Grab a unique lock here, as we only need fine-grained coverage
            # over these passwd/group/shadow files, in the infrequent
            # (first-time initialization) case that they haven't been copied
            # over before.
            with locking.FileLock(
                out_dir / ".passwd_lock",
                "passwd lock",
                blocking_timeout=30,
            ) as lock:
                lock.write_lock()
                # Check again now that we have the lock. If it exists now, we
                # lost the race, but that's OK.
                if (out_dir / src).exists():
                    break
                osutils.SafeMakedirsNonRoot((out_dir / src).parent)
                shutil.copy2(path / dst, out_dir / src)
        osutils.Mount(out_dir / src, path / dst, None, osutils.MS_BIND)

    defflags = (
        osutils.MS_NOSUID
        | osutils.MS_NODEV
        | osutils.MS_NOEXEC
        | osutils.MS_RELATIME
    )
    osutils.Mount("proc", path / "proc", "proc", defflags)
    osutils.Mount("sysfs", path / "sys", "sysfs", defflags)

    if "binfmt_misc" in KNOWN_FILESYSTEMS:
        try:
            osutils.Mount(
                "binfmt_misc",
                path / "proc/sys/fs/binfmt_misc",
                "binfmt_misc",
                defflags,
            )
        except PermissionError:
            # We're in an environment where we can't mount binfmt_misc (e.g. a
            # container), so ignore it for now.  We need it for unittests via
            # qemu, but nothing else currently.
            pass

    if "configfs" in KNOWN_FILESYSTEMS:
        osutils.Mount(
            "configfs", path / "sys/kernel/config", "configfs", defflags
        )

    # We expose /dev so we can access loopback & USB drives for flashing.
    osutils.Mount("/dev", path / "dev", None, osutils.MS_BIND | osutils.MS_REC)


FileSystemDebugInfo = collections.namedtuple(
    "FileSystemDebugInfo", ("fuser", "lsof", "ps")
)


def GetFileSystemDebug(path: str, run_ps: bool = True) -> FileSystemDebugInfo:
    """Collect filesystem debugging information.

    Dump some information to help find processes that may still be sing
    files. Running ps auxf can also be done to see what processes are
    still running.

    Args:
        path: Full path for directory we want information on.
        run_ps: When true, show processes running.

    Returns:
        FileSystemDebugInfo with debug info.
    """
    cmd_kwargs = {
        "check": False,
        "capture_output": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    fuser = cros_build_lib.sudo_run(["fuser", path], **cmd_kwargs)
    lsof = cros_build_lib.sudo_run(["lsof", path], **cmd_kwargs)
    if run_ps:
        ps = cros_build_lib.run(["ps", "auxf"], **cmd_kwargs)
        ps_stdout = ps.stdout
    else:
        ps_stdout = None
    return FileSystemDebugInfo(fuser.stdout, lsof.stdout, ps_stdout)


@timeout_util.TimeoutDecorator(600)

@timeout_util.TimeoutDecorator(1200)
def CleanupChrootMount(
    chroot: Optional[chroot_lib.Chroot] = None,
    buildroot: Optional[Union[Path, str]] = None,
    delete: bool = False,
    delete_out: bool = True,
):
    """Unmounts a chroot and cleans up attached devices.

    This function attempts to perform all the cleanup steps even if the chroot
    directory isn't present.  This ensures that a partially destroyed chroot
    can still be cleaned up.  This function does not remove the actual chroot
    directory or its content.

    Args:
        chroot: Full path to the chroot to examine, or None to find it relative
            to |buildroot|.
        buildroot: Ignored if |chroot| is set.  If |chroot| is None, find the
            chroot relative to |buildroot|.
        delete: Delete chroot contents after cleaning up.  If |delete| is False,
            the chroot contents will still be present and can be immediately
            re-mounted without recreating a fresh chroot.
        delete_out: Whether to also delete the chroot output directory. Only
            applies if |delete| is True.
    """
    if chroot is None and buildroot is None:
        raise ValueError("need either |chroot| or |buildroot| to search")
    if chroot is None:
        chroot = chroot_lib.Chroot(
            path=os.path.join(buildroot, constants.DEFAULT_CHROOT_DIR),
            out_path=buildroot / constants.DEFAULT_OUT_DIR,
        )

    try:
        with metrics_lib.timer("cros_sdk_lib.CleanupChrootMount.UmountTree"):
            osutils.UmountTree(chroot.path)
    except cros_build_lib.RunCommandError as e:
        # TODO(lamontjones): Dump some information to help find the process
        #   still inside the chroot, causing crbug.com/923432.  In the end, this
        #   is likely to become fuser -k.
        fs_debug = GetFileSystemDebug(chroot.path, run_ps=True)
        raise Error(
            "Umount failed: %s.\nfuser output=%s\nlsof output=%s\nps "
            "output=%s\n"
            % (e.stderr, fs_debug.fuser, fs_debug.lsof, fs_debug.ps)
        )

    if delete:
        with metrics_lib.timer("cros_sdk_lib.CleanupChrootMount.RmDir.Chroot"):
            osutils.RmDir(chroot.path, ignore_missing=True, sudo=True)
        if delete_out:
            with metrics_lib.timer("cros_sdk_lib.CleanupChrootMount.RmDir.out"):
                osutils.RmDir(chroot.out_path, ignore_missing=True, sudo=True)


def MigrateStatePaths(chroot: chroot_lib.Chroot, lock: locking.FileLock):
    """Migrate chroot state paths.

    Moves directory contents from old stateful-chroot locations to new "output
    directory" structure, where stateful directories are all collected in
    out_path.
    """

    def _move_path(src: Path, dst: Path):
        # Move (and merge) contents from |src| to |dst|, similar to
        # osutils.MoveDirContents(). We don't use osutils, because it doesn't
        # reliably handle ownership metadata, due to behaviors within shutil as
        # it falls back to copying. Rather than work around such
        # inconsistencies (and implement root-only tests for it), we fall back
        # to rsync.

        # If destination exists, we might be resuming an operation. Just fall
        # back to rsync.
        if not (dst.exists() or dst.is_symlink()):
            try:
                src.rename(dst)
                return
            except OSError:
                # Fall back to rsync.
                pass

        try:
            cros_build_lib.sudo_run(
                [
                    "rsync",
                    "-aHX",
                    "--remove-source-files",
                    src,
                    f"{dst.parent}/",
                ],
            )
        except cros_build_lib.RunCommandError as e:
            if isinstance(e.exception, FileNotFoundError):
                cros_build_lib.Die(
                    "Could not find `rsync` command; you may need to run"
                    " `sudo apt install rsync` or similar."
                )
            else:
                raise e
        # ignore_missing: "--remove-source-files" will only remove files, so
        # we sometimes need to clean up leftover directories.
        osutils.RmDir(src_entry, ignore_missing=True, sudo=True)

    for src_suffix, dst_suffix in _CHROOT_STATE_MIGRATIONS:
        # If the |src| directory is non-empty (aside from a README), migrate
        # its contents to |dst|.
        src = Path(chroot.path) / src_suffix
        dst = chroot.out_path / dst_suffix

        try:
            src_list = list(src.iterdir())
        except FileNotFoundError:
            continue
        except NotADirectoryError:
            continue
        if not src_list:
            continue
        if src_list == [src / "README"]:
            continue

        logging.info(
            "Migrating state path %s to %s; this may take a few moments",
            src,
            dst,
        )
        lock.write_lock(
            "upgrade to %s needed but chroot is locked; please "
            "exit all instances so this upgrade can finish." % src
        )

        osutils.SafeMakedirsNonRoot(dst)
        for src_entry in src.iterdir():
            dst_entry = dst / src_entry.name
            _move_path(src_entry, dst_entry)
        osutils.WriteFile(
            src / "README",
            """\
This is not the directory you're looking for. The CrOS SDK has been
refactored, and this directory's contents can now be found within the SDK
state/output directory at %s.

Do not remove this directory.
"""
            % dst,
        )


def RunChrootVersionHooks(version_file=None, hooks_dir=None):
    """Run the chroot version hooks to bring the chroot up to date."""
    if not cros_build_lib.IsInsideChroot():
        command = ["run_chroot_version_hooks"]
        cros_build_lib.run(command, enter_chroot=True)
    else:
        chroot = ChrootUpdater(version_file=version_file, hooks_dir=hooks_dir)
        chroot.ApplyUpdates()


def InitLatestVersion(version_file=None, hooks_dir=None):
    """Initialize the chroot version to the latest version."""
    if not cros_build_lib.IsInsideChroot():
        # Run the command in the chroot.
        command = ["run_chroot_version_hooks", "--init-latest"]
        cros_build_lib.run(command, enter_chroot=True)
    else:
        # Initialize the version.
        chroot = ChrootUpdater(version_file=version_file, hooks_dir=hooks_dir)
        if chroot.IsInitialized():
            logging.info(
                "Chroot is already initialized to %s.", chroot.GetVersion()
            )
        else:
            logging.info(
                "Initializing chroot to version %s.", chroot.latest_version
            )
            chroot.SetVersion(chroot.latest_version)


class ChrootUpdater:
    """Chroot version and update related functionality."""

    def __init__(self, version_file=None, hooks_dir=None):
        if version_file:
            # We have one. Just here to skip the logic below since we don't need
            # it.
            default_version_file = None
        elif cros_build_lib.IsInsideChroot():
            # Use the absolute path since we're inside the chroot.
            default_version_file = CHROOT_VERSION_FILE
        else:
            # Otherwise convert to the path outside the chroot.
            default_version_file = path_util.FromChrootPath(CHROOT_VERSION_FILE)

        self._version_file = version_file or default_version_file
        self._hooks_dir = hooks_dir or _CHROOT_VERSION_HOOKS_DIR

        self._version = None
        self._latest_version = None
        self._hook_files = None

    @property
    def latest_version(self):
        """Get the highest available version for the chroot."""
        if self._latest_version is None:
            self._latest_version = LatestChrootVersion(self._hooks_dir)
        return self._latest_version

    def GetVersion(self):
        """Get the chroot version.

        Returns:
            int

        Raises:
            InvalidChrootVersionError: when the file contents are not a valid
                version.
            IOError: when the file cannot be read.
            UninitializedChrootError: when the version file does not exist.
        """
        if self._version is None:
            # Check for existence so IOErrors from osutils.ReadFile are limited
            # to permissions problems.
            if not os.path.exists(self._version_file):
                raise UninitializedChrootError(
                    "Version file does not exist: %s" % self._version_file
                )

            version = osutils.ReadFile(self._version_file)

            try:
                self._version = int(version)
            except ValueError:
                raise InvalidChrootVersionError(
                    "Invalid chroot version in %s: %s"
                    % (self._version_file, version)
                )
            else:
                logging.debug("Found chroot version %s", self._version)

        return self._version

    def SetVersion(self, version):
        """Set and store the chroot version."""
        self._version = version
        osutils.WriteFile(self._version_file, str(version), sudo=True)

        # TODO(2023-11-01): Owner by default should be root, but older chroots
        # used to set this to the user.  Force this to be root to keep all
        # chroots in a consistent state.  We can drop this after we stop caring
        # about chroots that are too old.
        osutils.Chown(self._version_file, user="root")

    def IsInitialized(self):
        """Initialized Check."""
        try:
            return self.GetVersion() > 0
        except (Error, IOError):
            return False

    def ApplyUpdates(self):
        """Apply all necessary updates to the chroot."""
        if self.GetVersion() > self.latest_version:
            raise InvalidChrootVersionError(
                "Missing upgrade hook for version %s.\n"
                "Chroot is too new. Consider running:\n"
                "    cros_sdk --replace\n"
                "If the chroot is brand new, retrieve latest hooks with:\n"
                "    repo sync" % self.GetVersion()
            )

        for hook, version in self.GetChrootUpdates():
            result = cros_build_lib.run(
                ["bash", hook], enter_chroot=True, check=False
            )
            if not result.returncode:
                self.SetVersion(version)
            else:
                raise ChrootUpdateError(
                    "Error running chroot version hook: %s" % hook
                )

    def GetChrootUpdates(self):
        """Get all (update file, version) pairs that have not been run.

        Returns:
            list of (/path/to/hook/file, version) pairs in order.

        Raises:
            ChrootDeprecatedError when one or more required update files have
            been deprecated.
        """
        hooks = self._GetHookFilesByVersion()

        # Create the relevant ChrootUpdates.
        updates = []
        # Current version has already been run and we need to run the latest, so
        # +1 for each end of the version range.
        for version in range(self.GetVersion() + 1, self.latest_version + 1):
            # Deprecation check: Deprecation is done by removing old scripts.
            # Updates must form a continuous sequence. If the sequence is broken
            # between the chroot's current version and the most recent, then the
            # chroot must be recreated.
            if version not in hooks:
                raise ChrootDeprecatedError(self.GetVersion())

            updates.append((hooks[version], version))

        return updates

    def _GetHookFilesByVersion(self):
        """Find and store the hooks by their version number.

        Returns:
            dict - {version: /path/to/hook/file} mapping.

        Raises:
            VersionHasMultipleHooksError when multiple hooks exist for a
            version.
        """
        if self._hook_files:
            return self._hook_files

        hook_files = {}
        for hook in os.listdir(self._hooks_dir):
            version = int(hook.split("_", 1)[0])

            # Sanity check: Each version may only have a single script. Multiple
            # CLs landed at the same time and no one noticed the version
            # overlap.
            if version in hook_files:
                raise VersionHasMultipleHooksError(
                    "Version %s has multiple hooks." % version
                )

            hook_files[version] = os.path.join(self._hooks_dir, hook)

        self._hook_files = hook_files
        return self._hook_files


class ChrootCreator:
    """Creates a new chroot from a given SDK.

    Note: For the lifetime of this class, no paths are mounted in the chroot.
    Thus, some standard path conversion functions like path_util.FromChrootPath
    and chroot.full_path might return paths that don't exist. Instead, use
    self._from_chroot_path().
    """

    MAKE_CHROOT = os.path.join(
        constants.SOURCE_ROOT, "src/scripts/sdk_lib/make_chroot.sh"
    )

    # If the host timezone isn't set, we'll use this inside the SDK.
    DEFAULT_TZ = "usr/share/zoneinfo/PST8PDT"

    # Groups to add the user to inside the chroot.
    # This group list is a bit dated and probably contains a number of items
    # that no longer make sense.
    # TODO(crbug.com/762445): Remove "adm".
    # TODO(build): Remove cdrom & floppy.
    # TODO(build): See if audio is still needed.  Host distros might use diff
    #   "audio" group, so we wouldn't get access to /dev/snd/ nodes directly.
    # TODO(build): See if video is still needed.  Host distros might use diff
    #   "video" group, so we wouldn't get access to /dev/dri/ nodes directly.
    DEFGROUPS = {"adm", "cdrom", "floppy", "audio", "video", "portage"}

    def __init__(
        self,
        chroot: chroot_lib.Chroot,
        sdk_tarball: Path,
        usepkg: bool = True,
        chroot_upgrade: bool = True,
    ):
        """Initialize.

        Args:
            chroot: Chroot object representing the parameters for the chroot to
                create.
            sdk_tarball: Path to a downloaded Chromium OS SDK tarball.
            usepkg: If False, pass --nousepkg to cros_setup_toolchains inside
                the chroot.
            chroot_upgrade: If True, upgrade toolchain/SDK when entering the
                chroot.
        """
        self.chroot = chroot
        self.sdk_tarball = sdk_tarball
        self.usepkg = usepkg
        self.chroot_upgrade = chroot_upgrade

    @metrics_lib.timed("cros_sdk_lib.ChrootCreator._make_chroot")
    def _make_chroot(self):
        """Create the chroot."""
        cmd = [
            self.MAKE_CHROOT,
            "--chroot",
            str(self.chroot.path),
            "--cache_dir",
            str(self.chroot.cache_dir),
        ]

        if not self.usepkg:
            cmd.append("--nousepkg")

        if not self.chroot_upgrade:
            logging.warning(
                "Skipping SDK and toolchain update. "
                "Chroot is not guaranteed to work."
            )
            cmd.append("--skip_chroot_upgrade")

        try:
            cros_build_lib.dbg_run(cmd)
        except cros_build_lib.RunCommandError as e:
            cros_build_lib.Die("Creating chroot failed!\n%s", e)

    def init_timezone(self):
        """Setup the timezone info inside the chroot."""
        tz_path = Path("etc/localtime")
        host_tz = "/" / tz_path
        chroot_tz = Path(self.chroot.full_path(host_tz))
        # Nuke it in case it's a broken symlink.
        osutils.SafeUnlink(chroot_tz)
        if host_tz.exists():
            logging.debug("%s: copying from %s", chroot_tz, host_tz)
            chroot_tz.write_bytes(host_tz.read_bytes())
        else:
            logging.debug("%s: symlinking to %s", chroot_tz, self.DEFAULT_TZ)
            chroot_tz.symlink_to(self.DEFAULT_TZ)

    def init_user(
        self,
        user: Optional[str] = None,
        uid: Optional[int] = None,
        gid: Optional[int] = None,
    ):
        """Setup the current user inside the chroot.

        The user account name & id are synced with the active account outside of
        the SDK.  This helps facilitate copying of files in & out of the SDK
        without the need of sudo.

        The user account must not already exist inside the SDK (as a
        pre-existing reserved name) otherwise we can't create it with the right
        uid.

        Args:
            user: The username to create.
            uid: The new account's userid.
            gid: The new account's groupid.
        """
        if not user:
            user = os.getenv("SUDO_USER")
            assert user is not None
        if uid is None:
            uid_str = os.getenv("SUDO_UID")
            assert uid_str is not None
            uid = int(uid_str)
        if gid is None:
            gid = pwd.getpwnam(user).pw_gid

        path = Path(self.chroot.full_path("/etc/passwd"))
        lines = path.read_text(encoding="utf-8").splitlines()

        # Make sure the user isn't one the existing reserved ones.
        for line in lines:
            existing_user = line.split(":", 1)[0]
            if existing_user == user:
                cros_build_lib.Die(
                    f"{user}: this account cannot be used to build CrOS"
                )

        # Create the account.
        home = f"/home/{user}"
        line = f"{user}:x:{uid}:{gid}:ChromeOS Developer:{home}:/bin/bash"
        logging.debug("%s: adding user: %s", path, line)
        lines.insert(0, line)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        home_path = Path(self.chroot.full_path(home))
        # If |home_path| exists, a chroot has already been established for this
        # tree. Skip reestablishing.
        if not home_path.exists():
            self.init_user_home(home_path, uid, gid)

    def init_group(
        self,
        user: Optional[str] = None,
        groups: Optional[Set[str]] = None,
        group: Optional[str] = None,
        gid: Optional[int] = None,
    ):
        """Setup the current user's groups inside the chroot.

        This will create the user's primary group and add them to a bunch of
        supplemental groups.  The primary group is synced with the active
        account outside the SDK to help facilitate accessing of files &
        resources (e.g. any /dev nodes).

        The primary group must not already exist inside the SDK (as a
        pre-existing reserved name) otherwise we can't create it with the right
        gid.

        Args:
            user: The username to add to groups.
            groups: The account's supplemental groups.
            group: The account's primary group (to be created).
            gid: The primary group's gid.
        """
        if not user:
            user = os.getenv("SUDO_USER")
            assert user is not None
        if groups is None:
            groups = self.DEFGROUPS
        if gid is None:
            gid = pwd.getpwnam(user).pw_gid
        if group is None:
            group = grp.getgrgid(gid).gr_name

        path = Path(self.chroot.full_path("/etc/group"))
        lines = path.read_text(encoding="utf-8").splitlines()

        # Make sure the group isn't one the existing reserved ones.
        # Add the user to all the existing ones too.
        for i, line in enumerate(lines):
            entry = line.split(":")
            if entry[0] == group:
                # If the group exists with the same gid, no need to add a new
                # one. This often comes up with e.g. the "users" group.
                if entry[2] == str(gid):
                    return
                cros_build_lib.Die(
                    f"{group}: this group cannot be used to build CrOS"
                )
            if entry[0] in groups:
                if entry[-1]:
                    entry[-1] += ","
                entry[-1] += user
                lines[i] = ":".join(entry)

        line = f"{group}:x:{gid}:{user}"
        logging.debug("%s: adding group: %s", path, line)
        lines.insert(0, line)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def init_user_home(self, home: Path, uid: int, gid: int):
        """Initialize the user's /home dir."""
        shutil.copytree(self.chroot.full_path("/etc/skel"), home)

        (home / "chromiumos").symlink_to(constants.CHROOT_SOURCE_ROOT)

        bash_profile = home / ".bash_profile"
        osutils.Touch(bash_profile)
        data = bash_profile.read_text(encoding="utf-8").rstrip()
        if data:
            data += "\n\n"
        # Automatically change to scripts directory.
        data += 'cd "${CHROOT_CWD:-${HOME}/chromiumos/src/scripts}"\n\n'
        bash_profile.write_text(data, encoding="utf-8")

        osutils.Chown(home, user=uid, group=gid, recursive=True)

    def init_filesystem_basic(self):
        """Setup various dirs & simple config files."""
        # Create mount point directories. NB: we don't want to translate them
        # via chroot.full_path(), because that would map to, e.g., the source
        # directory (/path/to/chromiumos/src) instead of the mount-point we
        # want to create (/path/to/chromiumos/chroot/mnt/host/source).
        for path in (
            constants.CHROOT_SOURCE_ROOT,
            constants.CHROOT_OUT_ROOT,
        ):
            (Path(self.chroot.path) / path.relative_to("/")).mkdir(
                mode=0o755, parents=True, exist_ok=True
            )

    def init_etc(self, user: Optional[str] = None):
        """Setup the /etc paths."""
        if user is None:
            user = os.getenv("SUDO_USER")

        etc_dir = Path(self.chroot.full_path("/etc"))

        # Setup some symlinks.
        mtab = etc_dir / "mtab"
        if not mtab.is_symlink():
            osutils.SafeUnlink(mtab)
            mtab.symlink_to("/proc/mounts")

        # Copy config from outside chroot into chroot.
        for path in ("hosts", "resolv.conf"):
            host_path = Path("/etc") / path
            chroot_path = etc_dir / path
            if host_path.exists():
                chroot_path.write_bytes(host_path.read_bytes())
                chroot_path.chmod(0o644)

        # Add chromite/sdk/bin and chromite/bin into the path globally. We rely
        # on 'env-update' getting called later (make_chroot.sh).
        env_d = etc_dir / "env.d" / "99chromiumos"
        chroot_chromite_bin = (
            constants.CHROOT_SOURCE_ROOT / constants.CHROMITE_BIN_SUBDIR
        )
        env_d.write_text(
            f"""\
PATH="{constants.CHROOT_SOURCE_ROOT}/chromite/sdk/bin:{chroot_chromite_bin}"
CROS_WORKON_SRCROOT="{constants.CHROOT_SOURCE_ROOT}"
PORTAGE_USERNAME="{user}"
""",
            encoding="utf-8",
        )

        profile_d = etc_dir / "profile.d"
        profile_d.mkdir(mode=0o755, parents=True, exist_ok=True)
        (profile_d / "50-chromiumos-niceties.sh").symlink_to(
            f"{constants.CHROOT_SOURCE_ROOT}/chromite/sdk/etc/profile.d/"
            "50-chromiumos-niceties.sh"
        )

        # Enable bash completion.
        bash_completion_d = etc_dir / "bash_completion.d"
        bash_completion_d.mkdir(mode=0o755, parents=True, exist_ok=True)
        (bash_completion_d / "cros").symlink_to(f"{_BASH_COMPLETION_DIR}/cros")

    def init_var(self):
        """Handle /var contents from SDK tarball."""
        for chroot_path, out_path in (
            ("var/cache", "sdk/cache"),
            ("var/log", "sdk/logs"),
        ):
            src_dir = Path(self.chroot.path) / chroot_path
            dst_dir = self.chroot.out_path / out_path
            # out/ destination exists already? Then we're not doing a clean
            # unpack, and we assume the destination is already set up.
            if dst_dir.exists():
                continue
            # chroot source didn't have this path? Then skip it.
            if not src_dir.exists():
                continue

            osutils.SafeMakedirsNonRoot(dst_dir)
            osutils.MoveDirContents(src_dir, dst_dir)

        # Create edb cache stub directories.
        edb_cache_dep = self.chroot.full_path(
            constants.CHROOT_EDB_CACHE_ROOT / "dep"
        )
        osutils.SafeMakedirs(edb_cache_dep, mode=0o2775)
        # Set users/groups.
        osutils.Chown(
            edb_cache_dep,
            constants.PORTAGE_UID,
            group=constants.PORTAGE_GID,
            recursive=True,
        )

    def print_success_summary(self):
        """Show a summary of the chroot to the user."""
        chroot_opt = ""
        if Path(constants.DEFAULT_CHROOT_PATH) != Path(self.chroot.path):
            chroot_opt = (
                f" --chroot={cros_build_lib.ShellQuote(self.chroot.path)} "
                f"--out-dir={cros_build_lib.ShellQuote(self.chroot.out_path)}"
            )
        logging.info(
            """
All set up.  To enter the chroot, run:
$ cros_sdk --enter%s

CAUTION: Do *NOT* rm -rf the chroot directory; if there are stale bind mounts
you may end up deleting your source tree too.  To unmount & delete cleanly, use:
$ cros_sdk --delete%s
""",
            chroot_opt,
            chroot_opt,
        )

    @metrics_lib.timed("cros_sdk_lib.ChrootCreator.run")
    def run(
        self,
        user: Optional[str] = None,
        uid: Optional[int] = None,
        group: Optional[str] = None,
        gid: Optional[int] = None,
    ):
        """Create the chroot.

        Args:
            user: The user account to use (e.g. for testing).
            uid: The user id to use (e.g. for testing).
            group: The group account to use (e.g. for testing).
            gid: The group id to use (e.g. for testing).
        """
        logging.notice("Creating chroot. This may take a few minutes...")

        metrics_prefix = "cros_sdk_lib.ChrootCreator.run"
        with metrics_lib.timer(f"{metrics_prefix}.ExtractSdkTarball"):
            # Unpack the chroot.
            Path(self.chroot.path).mkdir(
                mode=0o755, parents=True, exist_ok=True
            )
            cros_build_lib.ExtractTarball(self.sdk_tarball, self.chroot.path)

        with metrics_lib.timer(f"{metrics_prefix}.init"):
            self.init_timezone()
            self.init_user(user=user, uid=uid, gid=gid)
            self.init_group(user=user, group=group, gid=gid)
            self.init_filesystem_basic()
            self.init_etc(user=user)
            self.init_var()

        MountChrootPaths(self.chroot)

        self._make_chroot()

        self.print_success_summary()


@metrics_lib.timed("cros_sdk_lib.CreateChroot")
def CreateChroot(*args, **kwargs):
    """Convenience method."""
    ChrootCreator(*args, **kwargs).run()


class ChrootEnteror:
    """Enters an existing chroot (and syncs state we care about)."""

    ENTER_CHROOT = os.path.join(
        constants.SOURCE_ROOT, "src/scripts/sdk_lib/enter_chroot.sh"
    )

    # The rlimits we will lookup & pass down, in order.
    RLIMITS_TO_PASS = (
        resource.RLIMIT_AS,
        resource.RLIMIT_CORE,
        resource.RLIMIT_CPU,
        resource.RLIMIT_FSIZE,
        resource.RLIMIT_MEMLOCK,
        resource.RLIMIT_NICE,
        resource.RLIMIT_NOFILE,
        resource.RLIMIT_NPROC,
        resource.RLIMIT_RSS,
        resource.RLIMIT_STACK,
    )

    # We want a proc limit at least this small.
    _RLIMIT_NPROC_MIN = 4096

    # We want a file limit at least this small.
    _RLIMIT_NOFILE_MIN = 262144

    # Path to sysctl knob.  Class-level constant for easy test overrides.
    _SYSCTL_VM_MAX_MAP_COUNT = Path("/sys/vm/max_map_count")

    def __init__(
        self,
        chroot: "chroot_lib.Chroot",
        chrome_root_mount: Optional[Path] = None,
        cmd: Optional[List[str]] = None,
        cwd: Optional[Path] = None,
        read_only: bool = False,
    ):
        """Initialize.

        Args:
            chroot: Where the new chroot will be created.
            chrome_root_mount: Where to mount |chrome_root| inside the chroot.
            cmd: Program to run inside the chroot.
            cwd: Directory to change to before running |additional_args|.
            read_only: Whether to mount the chroot read-only.
        """
        self.chroot = chroot
        self.chrome_root_mount = chrome_root_mount
        self.cmd = cmd
        self.read_only = read_only

        if cwd and not cwd.is_absolute():
            cwd = Path(chroot.chroot_path(cwd))
        self.cwd = cwd

    def _check_chroot(self) -> None:
        """Verify the chroot is usable."""
        st = os.statvfs(
            Path(self.chroot.full_path(Path("/") / "usr" / "bin" / "sudo"))
        )
        if st.f_flag & os.ST_NOSUID:
            cros_build_lib.Die("chroot cannot be in a nosuid mount")

    def _enter_chroot(
        self, cmd: Optional[List[str]] = None, cwd: Optional[Path] = None
    ) -> cros_build_lib.CompletedProcess:
        """Enter the chroot."""
        self._check_chroot()

        if cmd is None:
            cmd = self.cmd
        if cwd is None:
            cwd = self.cwd

        wrapper = [self.ENTER_CHROOT] + self.chroot.get_enter_args(
            for_shell=True
        )
        if self.chrome_root_mount:
            wrapper += ["--chrome_root_mount", str(self.chrome_root_mount)]
        if cwd:
            wrapper += ["--working_dir", str(cwd)]

        if cmd:
            wrapper += ["--"] + cmd

        return cros_build_lib.dbg_run(wrapper, check=False)

    @classmethod
    def get_rlimits(cls) -> str:
        """Serialize current rlimits."""
        return str(tuple(resource.getrlimit(x) for x in cls.RLIMITS_TO_PASS))

    @classmethod
    def set_rlimits(cls, limits: str) -> None:
        """Deserialize rlimits."""
        for rlim, limit in zip(cls.RLIMITS_TO_PASS, ast.literal_eval(limits)):
            cur_limit = resource.getrlimit(rlim)
            if cur_limit != limit:
                # Turn the number into a symbolic name for logging.
                name = "RLIMIT_???"
                for name, num in resource.__dict__.items():
                    if name.startswith("RLIMIT_") and num == rlim:
                        break
                logging.debug(
                    "Restoring user rlimit %s from %r to %r",
                    name,
                    cur_limit,
                    limit,
                )

                resource.setrlimit(rlim, limit)

    def _setup_rlimit_nproc(self) -> None:
        """Update process rlimits."""
        # Some systems set the soft limit too low.  Bump it to the hard limit.
        # We don't override the hard limit because it's something the admins put
        # in place and we want to respect such configs.  http://b/234353695
        soft, hard = resource.getrlimit(resource.RLIMIT_NPROC)
        if soft != resource.RLIM_INFINITY and soft < self._RLIMIT_NPROC_MIN:
            if soft < hard or hard == resource.RLIM_INFINITY:
                resource.setrlimit(resource.RLIMIT_NPROC, (hard, hard))

    def _setup_vm_max_map_count(self) -> None:
        """Update OS limits as ThinLTO opens lots of files at the same time."""
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(
            resource.RLIMIT_NOFILE,
            (
                max(soft, self._RLIMIT_NOFILE_MIN),
                max(hard, self._RLIMIT_NOFILE_MIN),
            ),
        )
        try:
            max_map_count = int(
                self._SYSCTL_VM_MAX_MAP_COUNT.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            return
        if max_map_count < self._RLIMIT_NOFILE_MIN:
            logging.notice(
                "Raising vm.max_map_count from %s to %s",
                max_map_count,
                self._RLIMIT_NOFILE_MIN,
            )
            self._SYSCTL_VM_MAX_MAP_COUNT.write_text(
                str(self._RLIMIT_NOFILE_MIN), encoding="utf-8"
            )

    def run(
        self, cmd: Optional[List[str]] = None, cwd: Optional[Path] = None
    ) -> cros_build_lib.CompletedProcess:
        """Enter the chroot."""
        if "CHROMEOS_SUDO_RLIMITS" in os.environ:
            self.set_rlimits(os.environ.pop("CHROMEOS_SUDO_RLIMITS"))
        self._setup_rlimit_nproc()
        self._setup_vm_max_map_count()
        if self.read_only:
            with ChrootReadOnly(path=self.chroot.path):
                return self._enter_chroot(cmd=cmd, cwd=cwd)
        else:
            return self._enter_chroot(cmd=cmd, cwd=cwd)


def EnterChroot(*args, **kwargs) -> cros_build_lib.CompletedProcess:
    """Convenience method."""
    return ChrootEnteror(*args, **kwargs).run()


class _ChrootWritable:
    """A context manager for ensuring the Chroot mount writability."""

    def __init__(self, writable: bool, path: Union[str, os.PathLike] = "/"):
        self._want_read_only = not writable
        self._chroot_path = path
        self._needs_remount = False

    def __enter__(self):
        # This context manager doesn't make sense outside the chroot.
        assert IsChrootReady(self._chroot_path)

        assert osutils.IsMounted(self._chroot_path)
        self._needs_remount = (
            osutils.IsMountedReadOnly(self._chroot_path) != self._want_read_only
        )

        if self._needs_remount:
            self._remount(read_only=self._want_read_only)

    def __exit__(self, _type, _value, _traceback):
        if self._needs_remount:
            # Path mounts may change (e.g., pivot_root on chroot entry), which
            # means the path mount looks different by the time we exit. Just
            # ignore it.
            if not osutils.IsMounted(self._chroot_path):
                return

            self._remount(read_only=not self._want_read_only)

    def _remount(self, read_only: bool) -> None:
        """Perform the remount operation.

        Args:
            read_only: if True, remount read-only; otherwise, remount
                read/write.
        """
        try:
            ro = osutils.MS_RDONLY if read_only else 0
            osutils.Mount(
                None,
                self._chroot_path,
                None,
                osutils.MS_REMOUNT | osutils.MS_BIND | ro,
            )
        except PermissionError:
            # Try via sudo instead.
            ro = "ro" if read_only else "rw"
            cros_build_lib.sudo_run(
                [
                    "mount",
                    "-o",
                    ",".join(("remount", "bind", ro)),
                    self._chroot_path,
                ]
            )


class ChrootReadWrite(_ChrootWritable):
    """Context manager for ensuring the Chroot mount is read/write.

    Operations that need to update the main chroot mount (i.e., the contents of
    |Chroot.path|, not |Chroot.out_path|) may require the chroot be mounted in a
    writable state. Such operations should be performed within this
    ChrootReadWrite context manager.

    If the chroot is already mounted read/write, then this context manager is a
    no-op.

    Note: carefully consider whether you really want to mount the chroot
    read/write. Most writable state should go into |Chroot.out_path|, such that
    we can avoid writing to |Chroot.path| most of the time.

    Examples:

        # Perform some chroot updates. The chroot may already be writable, but
        # we document it anyway.
        with ChrootReadWrite():
            PerformChrootUpdates()

        # Perform some chroot updates on chroot entry. The chroot is mounted
        # read-only, and we want it read/write only for the Update operations.
        with ChrootReadOnly():
            ...
            with ChrootReadWrite():
                # Do a few maintenance steps read/write:
                PerformChrootUpdates()
            # Back to regular SDK shell, read-only.
    """

    def __init__(self, path: Union[str, os.PathLike] = "/"):
        """Initialize a ChrootReadWrite context manager.

        Args:
            path: The chroot mount point.
        """
        super().__init__(writable=True, path=path)


class ChrootReadOnly(_ChrootWritable):
    """Context manager for ensuring the Chroot mount is read-only.

    Most code should assume that the chroot may be mounted read-only on chroot
    entry, and so should be using a ChrootReadWrite manager for operations
    where we need a writable chroot. See ChrootReadWrite for more info.
    """

    def __init__(self, path: Union[str, os.PathLike] = "/"):
        """Initialize a ChrootReadOnly context manager.

        Args:
            path: The chroot mount point.
        """
        super().__init__(writable=False, path=path)
