# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common file and os related utilities, including tempdir manipulation."""

import collections
import contextlib
import ctypes
import ctypes.util
import errno
import glob
import hashlib
import logging
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Callable, Iterable, Iterator, List, Optional, Union

from chromite.lib import cros_build_lib
from chromite.lib import retry_util
from chromite.utils import key_value_store
from chromite.utils import os_util


# Env vars that tempdir can be gotten from; minimally, this
# needs to match python's tempfile module and match normal
# unix standards.
_TEMPDIR_ENV_VARS = ("TMPDIR", "TEMP", "TMP")


def IsChildProcess(pid, name=None):
    """Return True if pid is a child of the current process.

    Args:
        pid: Child pid to search for in current process's pstree.
        name: Name of the child process.

    Note:
      This function is not foolproof. If the process tree contains wierd names,
      an incorrect match might be possible.
    """
    cmd = ["pstree", "-Ap", str(os.getpid())]
    pstree = cros_build_lib.run(
        cmd, capture_output=True, print_cmd=False, encoding="utf-8"
    ).stdout
    if name is None:
        match = "(%d)" % pid
    else:
        match = "-%s(%d)" % (name, pid)
    return match in pstree


def ExpandPath(path: Union[str, os.PathLike]) -> Union[str, os.PathLike]:
    """Returns path after passing through realpath and expanduser."""
    ret = Path(path).expanduser().resolve()
    return str(ret) if isinstance(path, str) else ret


def IsSubPath(path, other):
    """Returns whether |path| is a sub path of |other|."""
    path = os.path.abspath(path)
    other = os.path.abspath(other)
    return os.path.commonpath((path, other)) == other


def AllocateFile(
    path: Union[str, os.PathLike], size: int, makedirs: bool = False
) -> None:
    """Allocates a file of a certain |size| in |path|.

    This is intended to be used with new files as it will create the path (and
    optionally, the parent dirs) for you.

    If used on an existing file, existing content is automatically zeroed out.

    If you want to truncate an existing file and preserve content, use the
    os.truncate() API instead.

    Args:
        path: Path to allocate the file.
        size: The length, in bytes, of the desired file.
        makedirs: If True, create missing leading directories in the path.
    """
    path = Path(path)
    if makedirs:
        SafeMakedirs(path.parent)

    with path.open("wb") as out:
        out.truncate(size)


# All the modes that we allow people to pass to WriteFile.  This allows us to
# make assumptions about the input so we can update it if needed.
_VALID_WRITE_MODES = {
    # Read & write, but no truncation, and file offset is 0.
    "r+",
    "r+b",
    # Writing (and maybe reading) with truncation.
    "w",
    "wb",
    "w+",
    "w+b",
    # Writing (and maybe reading), but no truncation, and file offset is at end.
    "a",
    "ab",
    "a+",
    "a+b",
}


def WriteFile(
    path: Union[Path, str],
    content: Union[str, Iterable[str]],
    mode="w",
    encoding=None,
    errors=None,
    atomic=False,
    makedirs=False,
    sudo=False,
    chmod: Optional[int] = None,
):
    """Write the given content to disk.

    Args:
        path: Pathway to write the content to.
        content: Content to write.  May be either an iterable, or a string.
        mode: The mode to use when opening the file.  'w' is for text files (see
            the following settings) and 'wb' is for binary files.  If appending,
            pass 'w+', etc...
        encoding: The encoding of the file content.  Text files default to
            'utf-8'.
        errors: How to handle encoding errors.  Text files default to 'strict'.
        atomic: If the updating of the file should be done atomically.  Note
            this option is incompatible w/ append mode.
        makedirs: If True, create missing leading directories in the path.
        sudo: If True, write the file as root.
        chmod: Permissions to make sure the file uses.  By default, permissions
            will be maintained if |path| exists, or default to 0644.
    """
    if mode not in _VALID_WRITE_MODES:
        raise ValueError(
            'mode must be one of {"%s"}, not %r'
            % ('", "'.join(sorted(_VALID_WRITE_MODES)), mode)
        )

    if sudo and atomic and ("a" in mode or "+" in mode):
        raise ValueError("append mode does not work in sudo+atomic mode")

    if "b" in mode:
        if encoding is not None or errors is not None:
            raise ValueError("binary mode does not use encoding/errors")
    else:
        if encoding is None:
            encoding = "utf-8"
        if errors is None:
            errors = "strict"

    if makedirs:
        SafeMakedirs(os.path.dirname(path), sudo=sudo)

    # TODO(vapier): We can merge encoding/errors into the open call once we are
    # Python 3 only.  Until then, we have to handle it ourselves.
    if "b" in mode:
        write_wrapper = lambda x: x
    else:
        mode += "b"

        def write_wrapper(iterable):
            for item in iterable:
                yield item.encode(encoding, errors)

    def get_existing_perms(path):
        """Return permissions for |path| if available."""
        try:
            return os.stat(path).st_mode & 0o7777
        except OSError as e:
            # EPERM: We have access to dir, but not the file.
            # EACCES: We don't have access to the dir.
            if e.errno in (errno.EPERM, errno.EACCES):
                if sudo:
                    result = cros_build_lib.sudo_run(
                        ["stat", "-c%a", "--", str(path)], stdout=True
                    )
                    return int(result.stdout, 8)
                else:
                    raise
            elif e.errno != errno.ENOENT:
                raise
            else:
                return 0o644

    # If the file needs to be written as root and we are not root, write to a
    # temp file, move it and change the permission.
    if sudo and IsNonRootUser():
        if "a" in mode or mode.startswith("r+"):
            # Use dd to run through sudo & append the output, and write the new
            # data to it through stdin.
            cmd = ["dd", "conv=notrunc", "status=none", f"of={path}"]
            if "a" in mode:
                cmd += ["oflag=append"]
            cros_build_lib.sudo_run(cmd, print_cmd=False, input=content)
            if chmod is not None:
                Chmod(path, chmod, sudo=True)

        else:
            with tempfile.NamedTemporaryFile(mode=mode, delete=False) as temp:
                write_path = temp.name
                temp.writelines(
                    write_wrapper(cros_build_lib.iflatten_instance(content))
                )
            os.chmod(
                write_path, get_existing_perms(path) if chmod is None else chmod
            )

            try:
                mv_target = str(path) if not atomic else str(path) + ".tmp"
                cros_build_lib.sudo_run(
                    ["mv", write_path, mv_target], print_cmd=False, stderr=True
                )
                Chown(mv_target, user="root", group="root")
                if atomic:
                    cros_build_lib.sudo_run(
                        ["mv", mv_target, str(path)],
                        print_cmd=False,
                        stderr=True,
                    )

            except cros_build_lib.RunCommandError:
                SafeUnlink(write_path)
                SafeUnlink(mv_target)
                raise

    else:
        # We have the right permissions, simply write the file in python.
        write_path = path
        if atomic:
            # TODO(b/236161656): Fix.
            # pylint: disable-next=consider-using-with
            write_path = tempfile.NamedTemporaryFile(
                prefix=str(path), delete=False
            ).name
        # TODO(b/236161656): Fix.
        # pylint: disable-next=consider-using-with,unspecified-encoding
        with open(write_path, mode) as f:
            f.writelines(
                write_wrapper(cros_build_lib.iflatten_instance(content))
            )
            if atomic or chmod is not None:
                os.fchmod(
                    f.fileno(),
                    get_existing_perms(path) if chmod is None else chmod,
                )

        if not atomic:
            return

        try:
            os.rename(write_path, path)
        except EnvironmentError:
            SafeUnlink(write_path)
            raise


def Touch(
    path: Union[str, os.PathLike], makedirs: bool = False, mode: int = None
) -> None:
    """Simulate unix touch. Create if doesn't exist and update its timestamp.

    Args:
        path: File name of the file to touch (creating if not present).
        makedirs: If True, create missing leading directories in the path.
        mode: The access permissions to set.  In the style of chmod.  Defaults
            to using the umask.
    """
    path = Path(path)
    if makedirs:
        SafeMakedirs(path.parent)

    # Create the file if nonexistent.
    try:
        path.open("ab").close()
    except PermissionError:
        # If the file exists, updating the timestamp below via os.utime often
        # works (even if it's owned by someone else).  But if it doesn't exist,
        # throw the permission error to make it clear to the caller what's wrong
        # since a FileNotFound error is confusing.
        if not path.exists():
            raise
    if mode is not None:
        path.chmod(mode)
    # Update timestamp to right now.
    os.utime(path, None)


def Chmod(path: Union[Path, str], mode: int, sudo: bool = False):
    """Helper for changing file modes even if we have to elevate to root.

    Args:
        path: File/directory to chmod.
        mode: The permissions (e.g. 0o644) to change the file mode to.  String
            permissions (e.g. a+r) are *not* supported.
        sudo: If True, chmod the permissions as root.
    """
    # Try to chmod the file directly ourselves.  If we have access, no need to
    # elevate via sudo.  Faster this way in general.
    try:
        os.chmod(path, mode)
        return
    except OSError as e:
        # EPERM: We have access to dir, but not the file.
        # EACCES: We don't have access to the dir.
        if not sudo or e.errno not in (errno.EPERM, errno.EACCES):
            raise

    # If we're still here, we got permission denied and sudo=True was requested.
    cros_build_lib.sudo_run(["chmod", f"{mode:o}", "--", str(path)])


def Chown(
    path: Union[Path, str],
    user: Union[str, int],
    group: Optional[Union[str, int]] = None,
    recursive: bool = False,
):
    """Simple sudo chown path to a user.

    Args:
        path: File/directory to chown.
        user: User to chown the file to.
        group: Group to assign the file to.
        recursive: Also chown child files/directories recursively.
    """
    group = "" if group is None else str(group)

    cmd = ["chown"]
    if recursive:
        cmd += ["-R"]
    cmd += ["%s:%s" % (user, group), str(path)]
    cros_build_lib.sudo_run(cmd, print_cmd=False, stderr=True, stdout=True)


def ReadText(
    path: Union[Path, str],
    size: Optional[int] = None,
    seek: Optional[int] = None,
    sudo: Optional[bool] = False,
) -> str:
    """Read a given file on disk as text.

    See ReadFile.
    """
    text = ReadFile(path, "r", "utf-8", "strict", size, seek, sudo)
    assert isinstance(text, str)
    return text


def ReadBytes(
    path: Union[Path, str],
    size: Optional[int] = None,
    seek: Optional[int] = None,
    sudo: Optional[bool] = False,
) -> bytes:
    """Read a given file on disk as bytes.

    See ReadFile.
    """
    data = ReadFile(path, "rb", size=size, seek=seek, sudo=sudo)
    assert isinstance(data, bytes)
    return data


def ReadFile(
    path: Union[Path, str],
    mode: str = "r",
    encoding: Optional[str] = None,
    errors: Optional[str] = None,
    size: Optional[int] = None,
    seek: Optional[int] = None,
    sudo: Optional[bool] = False,
) -> Union[bytes, str]:
    """Read a given file on disk.

    Primarily useful for one off small files.

    The defaults are geared towards reading UTF-8 encoded text.

    Args:
        path: The file to read.
        mode: The mode to use when opening the file.  'r' is for text files (see
            the following settings) and 'rb' is for binary files.
        encoding: The encoding of the file content.  Text files default to
            'utf-8'.
        errors: How to handle encoding errors.  Text files default to 'strict'.
        size: How many bytes to return.  Defaults to the entire file.  If this
            is larger than the number of available bytes, an error is not
            thrown, you'll just get back a short read.
        seek: How many bytes to skip from the beginning.  By default, none.  If
            this is larger than the file itself, an error is not thrown, you'll
            just get back a short read.
        sudo: If True, read the file as root.

    Returns:
        The content of the file, either as bytes or a string (with the specified
        encoding).
    """
    if mode not in ("r", "rb"):
        raise ValueError('mode may only be "r" or "rb", not %r' % (mode,))

    if "b" not in mode:
        if encoding is None:
            encoding = "utf-8"
        if errors is None:
            errors = "strict"

    # Try to read w/out permission first.
    try:
        with open(path, mode=mode, encoding=encoding, errors=errors) as f:
            if seek:
                f.seek(seek)
            return f.read(size)
    except PermissionError:
        if not sudo:
            raise

    # If in sudo mode, use dd to extract.  We'll read in chunks of 1MiB for
    # better perf than the default of 512 bytes.
    cmd = [
        "dd",
        "status=none",
        "iflag=count_bytes,skip_bytes",
        f"bs={1024 * 1024}",
        f"if={path}",
    ]
    if seek:
        cmd += [f"skip={seek}"]
    if size:
        cmd += [f"count={size}"]
    result = cros_build_lib.sudo_run(
        cmd,
        capture_output=True,
        encoding=encoding,
        errors=errors,
        debug_level=logging.DEBUG,
    )
    return result.stdout


def MD5HashFile(path: Union[str, os.PathLike]) -> str:
    """Calculate the md5 hash of a given file path.

    Args:
        path: The path of the file to hash.

    Returns:
        The hex digest of the md5 hash of the file.
    """
    contents = Path(path).read_bytes()
    return hashlib.md5(contents).hexdigest()


def SafeSymlink(
    source: Union[Path, str], dest: Union[Path, str], sudo: bool = False
):
    """Create a symlink at |dest| pointing to |source|.

    This is done atomically by creating the symlink at a temporary file in the
    same directory, and renaming that symlink.

    Args:
        source: source path.
        dest: destination path.
        sudo: If True, create the link as root.
    """
    dest = Path(dest)
    if sudo and IsNonRootUser():
        cros_build_lib.sudo_run(
            ["ln", "-sfT", str(source), str(dest)], print_cmd=False, stderr=True
        )
    else:
        while True:
            tmp_dest = dest.with_name(
                f".tmp-{dest.name}-{cros_build_lib.GetRandomString()}"
            )
            try:
                tmp_dest.symlink_to(source)
                break
            except FileExistsError:
                # 1 in 2**96 chance this happens.
                # self.buy_lottery_ticket()
                continue
        try:
            tmp_dest.rename(dest)
        except OSError:
            # If the rename failed, try to clean up our litter.
            tmp_dest.unlink(missing_ok=True)
            raise


def SafeUnlink(path: Union[Path, str], sudo: bool = False):
    """Unlink a file from disk, ignoring if it doesn't exist.

    Returns:
        True if the file existed and was removed, False if it didn't exist.
    """
    try:
        os.unlink(path)
        return True
    except EnvironmentError as e:
        if e.errno == errno.ENOENT:
            return False

        if not sudo:
            raise

    # If we're still here, we're falling back to sudo.
    try:
        cros_build_lib.sudo_run(
            ["rm", "--", str(path)], print_cmd=False, stderr=True
        )
    except cros_build_lib.RunCommandError as e:
        # If the dir is inaccessible to non-root users, we'd end up here.
        if b"No such file or directory" in e.stderr:
            return False

        raise

    return True


def SafeMakedirs(path, mode=0o775, sudo=False, user="root"):
    """Make parent directories if needed. Ignore if existing.

    Args:
        path: The path to create.  Intermediate directories will be created as
            needed. This can be either a |Path| or |str|.
        mode: The access permissions in the style of chmod.
        sudo: If True, create it via sudo, thus root owned.
        user: If |sudo| is True, run sudo as |user|.

    Returns:
        True if the directory had to be created, False if otherwise.

    Raises:
        EnvironmentError: If the makedir failed.
        RunCommandError: If using run and the command failed for any reason.
    """
    if sudo and not (IsRootUser() and user == "root"):
        if os.path.isdir(path):
            return False
        cros_build_lib.sudo_run(
            ["mkdir", "-p", "--mode", "%o" % mode, str(path)],
            user=user,
            print_cmd=False,
            stderr=True,
            stdout=True,
        )
        cros_build_lib.sudo_run(
            ["chmod", "%o" % mode, str(path)],
            print_cmd=False,
            stderr=True,
            stdout=True,
        )
        return True

    try:
        os.makedirs(path, mode)
        # If we made the directory, force the mode.
        os.chmod(path, mode)
        return True
    except EnvironmentError as e:
        if e.errno != errno.EEXIST or not os.path.isdir(path):
            raise

    # If the mode on the directory does not match the request, log it.
    # It is the callers responsibility to coordinate mode values if there is a
    # need for that.
    if stat.S_IMODE(os.stat(path).st_mode) != mode:
        try:
            os.chmod(path, mode)
        except EnvironmentError:
            # Just make sure it's a directory.
            if not os.path.isdir(path):
                raise
    return False


class MakingDirsAsRoot(Exception):
    """Raised when creating directories as root."""


def SafeMakedirsNonRoot(path, mode=0o775, user=None):
    """Create directories and make sure they are not owned by root.

    See SafeMakedirs for the arguments and returns.
    """
    if user is None:
        user = os_util.get_non_root_user()

    if user is None or user == "root":
        raise MakingDirsAsRoot(
            "Refusing to create %s as user %s!" % (path, user)
        )

    created = False
    should_chown = False
    try:
        created = SafeMakedirs(path, mode=mode, user=user)
        if not created:
            # Sometimes, the directory exists, but is owned by root. As a HACK,
            # we will chown it to the requested user.
            stat_info = os.stat(path)
            should_chown = stat_info.st_uid == 0
    except OSError as e:
        if e.errno == errno.EACCES:
            # Sometimes, (a prefix of the) path we're making the directory in
            # may be owned by root, and so we fail. As a HACK, use da power to
            # create directory and then chown it.
            created = should_chown = SafeMakedirs(path, mode=mode, sudo=True)

    if should_chown:
        Chown(path, user=user)

    return created


class BadPathsException(Exception):
    """Raised by various osutils path manipulation functions on bad input."""


def _CopyDirContents(
    from_dir: Union[str, os.PathLike],
    to_dir: Union[str, os.PathLike],
    symlinks: bool = False,
    allow_nonempty: bool = False,
    move: bool = False,
) -> None:
    """Copy contents of from_dir to to_dir.

    Both must exist.

    shutil.copytree allows one to copy a rooted directory tree along with the
    containing directory. OTOH, this function copies the contents of from_dir to
    an existing directory. For example, for the given paths:

    from/
        inside/x.py
        y.py
    to/

    shutil.copytree('from', 'to')
    # Raises because 'to' already exists.

    shutil.copytree('from', 'to/non_existent_dir')
    to/non_existent_dir/
        inside/x.py
        y.py

    CopyDirContents('from', 'to')
    to/
        inside/x.py
        y.py

    Args:
        from_dir: The directory whose contents should be copied. Must exist.
        to_dir: The directory to which contents should be copied. Must exist.
        symlinks: Whether symlinks should be copied or dereferenced. When True,
            all symlinks will be copied as symlinks into the destination. When
            False, the symlinks will be dereferenced and the contents copied
            over.
        allow_nonempty: If True, do not die when to_dir is nonempty.
        move: Move the contents instead of copying them.

    Raises:
        BadPathsException: if the source / target directories don't exist, or if
            target directory is non-empty when allow_nonempty=False.
        OSError: on esoteric permission errors.
    """
    from_dir = Path(from_dir).resolve()
    to_dir = Path(to_dir).resolve()

    if not from_dir.is_dir():
        raise BadPathsException(f"Source directory {from_dir} does not exist.")
    if not to_dir.is_dir():
        raise BadPathsException(
            f"Destination directory {to_dir} does not exist."
        )
    if os.listdir(to_dir) and not allow_nonempty:
        raise BadPathsException(f"Destination directory {to_dir} is not empty.")

    if from_dir == to_dir:
        return

    for from_path in from_dir.iterdir():
        # Copy/Move the contents.
        to_path = to_dir / from_path.name

        if from_path.is_symlink():
            if move:
                if to_path.is_file() or to_path.is_symlink():
                    SafeUnlink(to_path)
                shutil.move(from_path, to_path)
            elif symlinks:
                to_path.symlink_to(os.readlink(from_path))
            else:
                shutil.copy2(from_path, to_path)
        elif from_path.is_dir():
            if move:
                if to_path.is_dir():
                    # if a destination directory already exists, recursively
                    # check for the individual files and directories in from
                    # path to be moved, so that we overwrite or copy the files
                    # to destination directory.
                    _CopyDirContents(
                        from_path,
                        to_path,
                        symlinks=symlinks,
                        allow_nonempty=allow_nonempty,
                        move=move,
                    )
                    RmDir(from_path)
                else:
                    # If it is a file or symbolic link, remove the destination
                    # file and then move the content.
                    if to_path.is_file() or to_path.is_symlink():
                        SafeUnlink(to_path)
                    # TODO(python3.9): In python 3.9, shutil.move() accepts
                    #   Path object. Remove the typecast to string, once python
                    #   version moves to 3.9.
                    shutil.move(
                        str(from_path),
                        str(to_path),
                    )
            else:
                shutil.copytree(from_path, to_path, symlinks=symlinks)
        elif from_path.is_file():
            if move:
                shutil.move(from_path, to_path)
            else:
                shutil.copy2(from_path, to_path)


def CopyDirContents(
    from_dir: Union[str, os.PathLike],
    to_dir: Union[str, os.PathLike],
    symlinks: bool = False,
    allow_nonempty: bool = False,
) -> None:
    """Copy contents of from_dir to to_dir.

    Both should exist.

    Args:
        from_dir: The directory whose contents should be copied. Must exist.
        to_dir: The directory to which contents should be copied. Must exist.
        symlinks: Whether symlinks should be copied or dereferenced. When True,
            all symlinks will be copied as symlinks into the destination. When
            False, the symlinks will be dereferenced and the contents copied
            over.
        allow_nonempty: If True, do not die when to_dir is nonempty.

    Raises:
        BadPathsException: if the source / target directories don't exist, or if
            target directory is non-empty when allow_nonempty=False.
        OSError: on esoteric permission errors.
    """
    _CopyDirContents(
        from_dir, to_dir, symlinks=symlinks, allow_nonempty=allow_nonempty
    )


def MoveDirContents(
    from_dir: Union[str, os.PathLike],
    to_dir: Union[str, os.PathLike],
    remove_from_dir: bool = False,
    allow_nonempty: bool = False,
) -> None:
    """Move contents of from_dir to to_dir.

    Both should exist.

    Args:
        from_dir: The directory whose contents should be moved. Must exist.
        to_dir: The directory to which contents should be moved. Must exist.
        remove_from_dir: Remove |from_dir| after the contents are moved.
        allow_nonempty: If True, do not die when to_dir is nonempty.

    Raises:
        BadPathsException: if the source / target directories don't exist, or if
        target directory is non-empty when allow_nonempty is False.
        OSError: on esoteric permission errors.
    """
    from_dir = Path(from_dir).resolve()
    to_dir = Path(to_dir).resolve()

    _CopyDirContents(from_dir, to_dir, allow_nonempty=allow_nonempty, move=True)
    if remove_from_dir and from_dir != to_dir:
        RmDir(from_dir)


def RmDir(path, ignore_missing=False, sudo=False):
    """Recursively remove a directory.

    Args:
        path: Path of directory to remove. Either a |Path| or |str|.
        ignore_missing: Do not error when path does not exist.
        sudo: Remove directories as root.
    """
    # Using `sudo` is a bit expensive, so try to delete everything natively
    # first.
    try:
        shutil.rmtree(path)
        return
    except EnvironmentError as e:
        if ignore_missing and e.errno == errno.ENOENT:
            return

        if not sudo:
            raise

    # If we're still here, we're falling back to sudo.
    try:
        cros_build_lib.sudo_run(
            ["rm", "-r%s" % ("f" if ignore_missing else "",), "--", str(path)],
            debug_level=logging.DEBUG,
            stdout=True,
            stderr=True,
        )
    except cros_build_lib.RunCommandError:
        if not ignore_missing or os.path.exists(path):
            # If we're not ignoring the rm ENOENT equivalent, throw it;
            # if the pathway still exists, something failed, thus throw it.
            raise


class EmptyDirNonExistentException(BadPathsException):
    """EmptyDir called on a non-existent directory without ignore_missing."""


def EmptyDir(path, ignore_missing=False, sudo=False, exclude=()):
    """Remove all files inside a directory, including subdirs.

    Args:
        path: Path of directory to empty.
        ignore_missing: Do not error when path does not exist.
        sudo: Remove directories as root.
        exclude: Iterable of file names to exclude from the cleanup. They should
            exactly match the file or directory name in path. e.g. ['foo',
            'bar']

    Raises:
        EmptyDirNonExistentException: if ignore_missing false, and dir is
            missing.
        OSError: If the directory is not user writable.
    """
    path = ExpandPath(path)
    exclude = set(exclude)

    if not os.path.exists(path):
        if ignore_missing:
            return
        raise EmptyDirNonExistentException(
            "EmptyDir called non-existent: %s" % path
        )

    # We don't catch OSError if path is not a directory.
    for candidate in os.listdir(path):
        if candidate not in exclude:
            subpath = os.path.join(path, candidate)
            # Both options can throw OSError if there is a permission problem.
            if os.path.isdir(subpath):
                RmDir(subpath, ignore_missing=ignore_missing, sudo=sudo)
            else:
                SafeUnlink(subpath, sudo)


def Which(
    binary: str,
    path: Optional[Union[str, os.PathLike]] = None,
    mode: int = os.X_OK,
    root: Optional[Union[str, os.PathLike]] = None,
) -> Optional[str]:
    """Return the absolute path to the specified binary.

    Args:
        binary: The binary to look for.
        path: Search path. Defaults to os.environ['PATH'].
        mode: File mode to check on the binary.
        root: Path to automatically prefix to every element of |path|.

    Returns:
        The full path to |binary| if found (with the right mode). Otherwise,
        None.
    """
    if path is None:
        path = os.environ.get("PATH", "")
    else:
        path = str(path)

    for p in path.split(os.pathsep):
        if root and p.startswith("/"):
            # Don't prefix relative paths.  We might want to support this at
            # some point, but it's not worth the coding hassle currently.
            p = os.path.join(root, p.lstrip("/"))
        p = os.path.join(p, binary)
        if os.path.isfile(p) and os.access(p, mode):
            return p

    return None


def FindMissingBinaries(needed_tools: List[str]) -> List[str]:
    """Verifies that the required tools are present on the system.

    This is especially important for scripts that are intended to run
    outside the chroot.

    Args:
        needed_tools: an array of string specified binaries to look for.

    Returns:
        If all tools are found, returns the empty list. Otherwise, returns the
        list of missing tools.
    """
    return [binary for binary in needed_tools if Which(binary) is None]


def DirectoryIterator(base_path: Path) -> Iterator[Path]:
    """Iterates through the files and subdirs of a directory."""
    for root, dirs, files in os.walk(base_path):
        root = Path(root)
        for e in dirs + files:
            yield root / e


def IteratePaths(end_path):
    """Generator that iterates down to |end_path| from root /.

    Args:
        end_path: The destination. If this is a relative path, it will be
            resolved to absolute path. In all cases, it will be normalized.

    Yields:
        All the paths gradually constructed from / to |end_path|. For example:
        IteratePaths("/this/path") yields "/", "/this", and "/this/path".
    """
    return reversed(list(IteratePathParents(end_path)))


def IteratePathParents(start_path: Union[str, os.PathLike]) -> Iterator[Path]:
    """Generator that iterates through a directory's parents.

    Args:
        start_path: The path to start from.

    Yields:
        The passed-in path, along with its parents.  i.e.,
        IteratePathParents('/usr/local')
        would yield '/usr/local', '/usr', and '/'.
    """
    path = Path(start_path).resolve()
    yield path
    yield from path.parents


def FindInPathParents(
    path_to_find: str,
    start_path: Union[str, os.PathLike],
    test_func: Optional[Callable[[Union[str, os.PathLike]], bool]] = None,
    end_path: Union[str, os.PathLike] = None,
) -> Optional[Union[str, os.PathLike]]:
    """Look for a relative path, ascending through parent directories.

    Ascend through parent directories of current path looking for a relative
    path.  I.e., given a directory structure like:
    -/
     |
     --usr
       |
       --bin
       |
       --local
         |
         --google

    the call FindInPathParents('bin', '/usr/local') would return '/usr/bin', and
    the call FindInPathParents('google', '/usr/local') would return
    '/usr/local/google'.

    Args:
        path_to_find: The relative path to look for.
        start_path: The path to start the search from.  If |start_path| is a
            directory, it will be included in the directories that are searched.
        test_func: The function to use to verify the relative path.  Defaults to
            os.path.exists.  The function will be passed one argument - the
            target path to test.  A True return value will cause AscendingLookup
            to return the target.
        end_path: The path to stop searching.

    Returns:
        The path, if found, with the same type as |start_path|.  Otherwise,
        None.
    """
    if end_path is not None:
        end_path = Path(end_path).resolve()
    if test_func is None:
        test_func = os.path.exists
    for path in IteratePathParents(Path(start_path)):
        if path == end_path:
            return None
        target = path / path_to_find
        if test_func(target):
            return str(target) if isinstance(start_path, str) else target
    return None


def SetGlobalTempDir(tempdir_value, tempdir_env=None):
    """Set the global temp directory to the specified |tempdir_value|

    Using this API is preferred over setting tempfile.tempdir directly because
    this takes care of setting up environment variables so external programs
    (e.g. subprocess.run & cros_build_lib.run) also access this tempdir.

    Conversely, tempfile.gettempdir() should be used to get the current value
    since SetGlobalTempDir takes care of updating the right value.

    Args:
        tempdir_value: The new location for the global temp directory.
        tempdir_env: Optional. A list of key/value pairs to set in the
            environment. If not provided, set all global tempdir environment
            variables to point at |tempdir_value|.

    Returns:
        Returns (old_tempdir_value, old_tempdir_env).

        old_tempdir_value: The old value of the global temp directory.
        old_tempdir_env: A list of the key/value pairs that control the tempdir
            environment and were set prior to this function. If the environment
            variable was not set, it is recorded as None.
    """
    # pylint: disable=protected-access
    with tempfile._once_lock:
        # Use internal API because tempfile.gettempdir() might grab the lock.
        old_tempdir_value = tempfile._get_default_tempdir()
        old_tempdir_env = tuple(
            (x, os.environ.get(x)) for x in _TEMPDIR_ENV_VARS
        )

        # Now update TMPDIR/TEMP/TMP, and poke the python
        # internals to ensure all subprocess/raw tempfile
        # access goes into this location.
        if tempdir_env is None:
            os.environ.update((x, tempdir_value) for x in _TEMPDIR_ENV_VARS)
        else:
            for key, value in tempdir_env:
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        # Finally, adjust python's cached value (we know it's cached by here
        # since we invoked _get_default_tempdir from above).  Note this
        # is necessary since we want *all* output from that point
        # forward to go to this location.
        tempfile.tempdir = tempdir_value

    return (old_tempdir_value, old_tempdir_env)


def _TempDirSetup(self, prefix="tmp", set_global=False, base_dir=None):
    """Generate a tempdir, modifying the object, and env to use it.

    Specifically, if set_global is True, then from this invocation forward,
    python and all subprocesses will use this location for their tempdir.

    The matching _TempDirTearDown restores the env to what it was.
    """
    # Stash the old tempdir that was used so we can
    # switch it back on the way out.
    self.tempdir = tempfile.mkdtemp(prefix=prefix, dir=base_dir)
    os.chmod(self.tempdir, 0o700)

    if set_global:
        self._orig_tempdir_value, self._orig_tempdir_env = SetGlobalTempDir(
            self.tempdir
        )


def _TempDirTearDown(self, force_sudo, delete=True):
    # Note that _TempDirSetup may have failed, resulting in these attributes
    # not being set; this is why we use getattr here (and must).
    tempdir = getattr(self, "tempdir", None)
    try:
        if tempdir is not None and delete:
            RmDir(tempdir, ignore_missing=True, sudo=force_sudo)
    except EnvironmentError as e:
        # Suppress ENOENT since we may be invoked
        # in a context where parallel wipes of the tempdir
        # may be occuring; primarily during hard shutdowns.
        if e.errno != errno.ENOENT:
            raise

    # Restore environment modification if necessary.
    orig_tempdir_value = getattr(self, "_orig_tempdir_value", None)
    if orig_tempdir_value is not None:
        # pylint: disable=protected-access
        SetGlobalTempDir(orig_tempdir_value, self._orig_tempdir_env)


class TempDir:
    """Object that creates a temporary directory.

    This object can either be used as a context manager or just as a simple
    object. The temporary directory is stored as self.tempdir in the object, and
    is returned as a string by a 'with' statement.
    """

    def __init__(self, **kwargs):
        """Constructor. Creates the temporary directory.

        Args:
            prefix: See tempfile.mkdtemp documentation.
            base_dir: The directory to place the temporary directory.
            set_global: Set this directory as the global temporary directory.
            delete: Whether the temporary dir should be deleted as part of
                cleanup. (default: True)
            sudo_rm: Whether the temporary dir will need root privileges to
                remove. (default: False)
        """
        self.kwargs = kwargs.copy()
        self.delete = kwargs.pop("delete", True)
        self.sudo_rm = kwargs.pop("sudo_rm", False)
        self.tempdir = None
        _TempDirSetup(self, **kwargs)

    def SetSudoRm(self, enable=True):
        """Sets |sudo_rm|, which forces us to delete temporary files as root."""
        self.sudo_rm = enable

    def Cleanup(self):
        """Clean up the temporary directory."""
        if self.tempdir is not None:
            try:
                _TempDirTearDown(self, self.sudo_rm, delete=self.delete)
            finally:
                self.tempdir = None

    def __enter__(self):
        """Return the temporary directory."""
        return self.tempdir

    def __exit__(self, exc_type, exc_value, exc_traceback):
        try:
            self.Cleanup()
        except Exception:
            if exc_type:
                # If an exception from inside the context was already in
                # progress, log our cleanup exception, then allow the original
                # to resume.
                logging.error("While exiting %s:", self, exc_info=True)

                if self.tempdir:
                    # Log all files in tempdir at the time of the failure.
                    try:
                        logging.error("Directory contents were:")
                        for name in os.listdir(self.tempdir):
                            logging.error("  %s", name)
                    except OSError:
                        logging.error("  Directory did not exist.")

                    # Log all mounts at the time of the failure, since that's
                    # the most common cause.
                    mount_results = cros_build_lib.run(
                        ["mount"],
                        stdout=True,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
                    logging.error("Mounts were:")
                    logging.error("  %s", mount_results.stdout)

            else:
                # If there was not an exception from the context, raise ours.
                raise

    def __del__(self):
        self.Cleanup()

    def __str__(self):
        return self.tempdir if self.tempdir else ""


def TempDirDecorator(func):
    """Populates self.tempdir with path to a temporary writeable directory."""

    def f(self, *args, **kwargs):
        with TempDir() as tempdir:
            self.tempdir = tempdir
            return func(self, *args, **kwargs)

    f.__name__ = func.__name__
    f.__doc__ = func.__doc__
    f.__module__ = func.__module__
    return f


def TempFileDecorator(func):
    """Populates self.tempfile with path to a temporary writeable file"""

    def f(self, *args, **kwargs):
        with tempfile.NamedTemporaryFile(dir=self.tempdir, delete=False) as f:
            self.tempfile = f.name
        return func(self, *args, **kwargs)

    f.__name__ = func.__name__
    f.__doc__ = func.__doc__
    f.__module__ = func.__module__
    return TempDirDecorator(f)


# Flags synced from sys/mount.h.  See mount(2) for details.
# COIL(b/187793358): keeping values synced with Linux utility constants.
MS_RDONLY = 1
MS_NOSUID = 2
MS_NODEV = 4
MS_NOEXEC = 8
MS_SYNCHRONOUS = 16
MS_REMOUNT = 32
MS_MANDLOCK = 64
MS_DIRSYNC = 128
MS_NOATIME = 1024
MS_NODIRATIME = 2048
MS_BIND = 4096
MS_MOVE = 8192
MS_REC = 16384
MS_SILENT = 32768
MS_POSIXACL = 1 << 16
MS_UNBINDABLE = 1 << 17
MS_PRIVATE = 1 << 18
MS_SLAVE = 1 << 19
MS_SHARED = 1 << 20
MS_RELATIME = 1 << 21
MS_KERNMOUNT = 1 << 22
MS_I_VERSION = 1 << 23
MS_STRICTATIME = 1 << 24
MS_ACTIVE = 1 << 30
MS_NOUSER = 1 << 31


def Mount(
    source: Union[None, Path, str, bytes, int],
    target: Union[None, Path, str, bytes, int],
    fstype: Union[None, str, bytes, int],
    flags: int,
    data: Union[None, str, bytes, int] = "",
):
    """Call the mount(2) func; see the man page for details.

    Args:
        source: The source mount path (for bind mounts or block devices), or a
            human readable description string (for pseudo filesystems).
        target: The target path to mount over.  It may be a dir or file, but it
            must exist already.
        fstype: The filesystem type (e.g. "ext4" or "tmpfs"), or None if a bind
            mount.
        flags: Various MS_* flags.
        data: Additional mount options parsed by the kernel filesystem driver.
            Not to be confused with the MS_* flags -- NB the `mount` program
            will convert some of these to MS_* flags for you e.g.
            "bind"->MS_BIND, but this function does not.
    """
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

    # These fields might be a Path/string/bytes or None/0 (for NULL).
    # Convert to bytes or 0.
    def _MaybeEncode(
        s: Union[None, Path, str, bytes, int], path_ok: bool = False
    ):
        if isinstance(s, Path):
            if path_ok:
                s = str(s).encode("utf-8")
            else:
                raise TypeError(f'"{s}" cannot be of type Path')
        elif isinstance(s, str):
            s = s.encode("utf-8")
        elif s is None:
            s = 0
        elif isinstance(s, int):
            if s:
                raise ValueError(f"{s}: only NULL (0) ints are allowed")
        elif not isinstance(s, bytes):
            raise TypeError(f'"{s}" is an unsupported type: {type(s)}')
        return s

    if (
        libc.mount(
            _MaybeEncode(source, path_ok=True),
            _MaybeEncode(target, path_ok=True),
            _MaybeEncode(fstype),
            ctypes.c_int(flags),
            _MaybeEncode(data),
        )
        != 0
    ):
        e = ctypes.get_errno()
        raise OSError(
            e,
            'Could not mount "%s" to "%s": %s'
            % (source, target, os.strerror(e)),
        )


def MountDir(
    src_path,
    dst_path,
    fs_type=None,
    sudo=True,
    makedirs=True,
    mount_opts=("nodev", "noexec", "nosuid"),
    skip_mtab=False,
    **kwargs,
):
    """Mount |src_path| at |dst_path|

    Args:
        src_path: Source of the new mount.
        dst_path: Where to mount things.
        fs_type: Specify the filesystem type to use.  Defaults to autodetect.
        sudo: Run through sudo.
        makedirs: Create |dst_path| if it doesn't exist.
        mount_opts: List of options to pass to `mount`.
        skip_mtab: Whether to write new entries to /etc/mtab.
        **kwargs: Pass all other args to run.
    """
    if sudo:
        runcmd = cros_build_lib.sudo_run
    else:
        runcmd = cros_build_lib.run

    if makedirs:
        SafeMakedirs(dst_path, sudo=sudo)

    cmd = ["mount", src_path, dst_path]
    if skip_mtab:
        cmd += ["-n"]
    if fs_type:
        cmd += ["-t", fs_type]
    if mount_opts:
        cmd += ["-o", ",".join(mount_opts)]
    runcmd(cmd, **kwargs)


def MountTmpfsDir(
    path,
    name="osutils.tmpfs",
    size="5G",
    mount_opts=("nodev", "noexec", "nosuid"),
    **kwargs,
):
    """Mount a tmpfs at |path|

    Args:
        path: Directory to mount the tmpfs.
        name: Friendly name to include in mount output.
        size: Size of the temp fs.
        mount_opts: List of options to pass to `mount`.
        **kwargs: Pass all other args to MountDir.
    """
    mount_opts = list(mount_opts) + ["size=%s" % size]
    MountDir(name, path, fs_type="tmpfs", mount_opts=mount_opts, **kwargs)


def UmountDir(path, lazy=True, sudo=True, cleanup=True):
    """Unmount a previously mounted temp fs mount.

    Args:
        path: Directory to unmount.
        lazy: Whether to do a lazy unmount.
        sudo: Run through sudo.
        cleanup: Whether to delete the |path| after unmounting.
        Note: Does not work when |lazy| is set.
    """
    if sudo:
        runcmd = cros_build_lib.sudo_run
    else:
        runcmd = cros_build_lib.run

    # Canonicalize the path first, because `umount` will soon no longer resolve
    # symlinks. See b/226186168.
    path = Path(path).resolve()

    cmd = ["umount", "-d", path]
    if lazy:
        cmd += ["-l"]
    runcmd(cmd, debug_level=logging.DEBUG)

    if cleanup:
        # We will randomly get EBUSY here even when the umount worked.  Suspect
        # this is due to the host distro doing stupid crap on us like
        # autoscanning directories when they get mounted.
        def _retry(e):
            # When we're using `rm` (which is required for sudo), we can't
            # cleanly detect the aforementioned failure.  This is because `rm`
            # will see the errno, handle itself, and then do exit(1).  Which
            # means all we see is that rm failed.  Assume it's this issue as -rf
            # will ignore most things.
            if isinstance(e, cros_build_lib.RunCommandError):
                return True
            elif isinstance(e, OSError):
                # When we aren't using sudo, we do the unlink ourselves, so the
                # exact errno is bubbled up to us and we can detect it
                # specifically without potentially ignoring all other possible
                # failures.
                return e.errno == errno.EBUSY
            else:
                # Something else, we don't know so do not retry.
                return False

        retry_util.GenericRetry(_retry, 60, RmDir, path, sudo=sudo, sleep=1)


def UmountTree(
    path: Union[str, os.PathLike],
    lazy: bool = False,
    cleanup: bool = False,
) -> None:
    """Unmounts |path| and any submounts under it.

    Args:
        path: Directory to unmount.
        lazy: Whether to do a lazy unmount.
        cleanup: Whether to delete the |path| after unmounting. Note: Does not
            work when |lazy| is set.
    """
    # Scrape it from /proc/mounts since it's easily accessible;
    # additionally, unmount in reverse order of what's listed there
    # rather than trying a reverse sorting; it's possible for
    # mount /z /foon
    # mount /foon/blah -o loop /a
    # which reverse sorting cannot handle.
    path = os.path.realpath(path).rstrip("/") + "/"
    mounts = [
        x.destination
        for x in IterateMountPoints()
        if x.destination.startswith(path) or x.destination == path.rstrip("/")
    ]

    for mount_pt in reversed(mounts):
        UmountDir(mount_pt, lazy=lazy, cleanup=cleanup)


def SetEnvironment(env):
    """Restore the environment variables to that of passed in dictionary."""
    os.environ.clear()
    os.environ.update(env)


def SourceEnvironment(script, allowlist, ifs=",", env=None, multiline=False):
    """Returns the environment exported by a shell script.

    Note that the script is actually executed (sourced), so do not use this on
    files that have side effects (such as modify the file system).  Stdout will
    be sent to /dev/null, so just echoing is OK.

    Args:
        script: The shell script to 'source'.
        allowlist: An iterable of environment variables to retrieve values for.
        ifs: When showing arrays, what separator to use.
        env: A dict of the initial env to pass down.  You can also pass it None
            (to clear the env) or True (to preserve the current env).
        multiline: Allow a variable to span multiple lines.

    Returns:
        A dictionary containing the values of the allowlisted environment
        variables that are set.
    """
    dump_script = ['source "%s" >/dev/null' % script, 'IFS="%s"' % ifs]
    for var in allowlist:
        # Note: If we want to get more exact results out of bash, we should
        # switch to using `declare -p "${var}"`.  It would require writing a
        # custom parser here, but it would be more robust.
        dump_script.append(
            '[[ "${%(var)s+set}" == "set" ]] && '
            'echo "%(var)s=\\"${%(var)s[*]}\\""' % {"var": var}
        )
    dump_script.append("exit 0")

    if env is None:
        env = {}
    elif env is True:
        env = None
    output = cros_build_lib.run(
        ["bash"],
        env=env,
        capture_output=True,
        print_cmd=False,
        encoding="utf-8",
        input="\n".join(dump_script),
    ).stdout
    return key_value_store.LoadData(output, multiline=multiline)


def ListBlockDevices(device_path=None, in_bytes=False):
    """Lists all block devices.

    Args:
        device_path: device path (e.g. /dev/sdc).
        in_bytes: whether to display size in bytes.

    Returns:
        A list of BlockDevice items with attributes 'NAME', 'RM', 'TYPE',
        'SIZE', 'HOTPLUG' (RM stands for removable).
    """
    keys = ["NAME", "RM", "TYPE", "SIZE", "HOTPLUG"]
    BlockDevice = collections.namedtuple("BlockDevice", keys)

    cmd = ["lsblk", "--pairs"]
    if in_bytes:
        cmd.append("--bytes")

    if device_path:
        cmd.append(device_path)

    cmd += ["--output", ",".join(keys)]
    result = cros_build_lib.dbg_run(cmd, capture_output=True, encoding="utf-8")
    devices = []
    for line in result.stdout.strip().splitlines():
        d = {}
        for k, v in re.findall(r"(\S+?)=\"(.+?)\"", line):
            d[k] = v

        devices.append(BlockDevice(**d))

    return devices


def GetDeviceInfo(device, keyword="model"):
    """Get information of |device| by searching through device path.

      Looks for the file named |keyword| in the path upwards from
      /sys/block/|device|/device. This path is a symlink and will be fully
      expanded when searching.

    Args:
        device: Device name (e.g. 'sdc').
        keyword: The filename to look for (e.g. product, model).

    Returns:
        The content of the |keyword| file.
    """
    device_path = os.path.join("/sys", "block", device)
    if not os.path.isdir(device_path):
        raise ValueError("%s is not a valid device path." % device_path)

    path_list = ExpandPath(os.path.join(device_path, "device")).split(
        os.path.sep
    )
    while len(path_list) > 2:
        target = os.path.join(os.path.sep.join(path_list), keyword)
        if os.path.isfile(target):
            return ReadFile(target).strip()

        path_list = path_list[:-1]


def GetDeviceSize(device_path, in_bytes=False):
    """Returns the size of |device|.

    Args:
        device_path: Device path (e.g. '/dev/sdc').
        in_bytes: If set True, returns the size in bytes.

    Returns:
        Size of the device in human-readable format unless |in_bytes| is set.
    """
    devices = ListBlockDevices(device_path=device_path, in_bytes=in_bytes)
    for d in devices:
        if d.TYPE == "disk":
            return int(d.SIZE) if in_bytes else d.SIZE

    raise ValueError("No size info of %s is found." % device_path)


@contextlib.contextmanager
def OpenContext(
    path: Union[Path, str], flags: int = os.O_RDONLY, mode: int = 0o777
) -> int:
    """Context manager to open & close |path| and return the OS file descriptor.

    Args:
        path: The path to open.
        flags: The O_* flags to use.
        mode: The permission bits to use (when creating a file).

    Yields:
        The open OS file descriptor.
    """
    fd = None
    try:
        fd = os.open(path, flags, mode)
        yield fd
    finally:
        if fd is not None:
            os.close(fd)


@contextlib.contextmanager
def ChdirContext(target_dir: Union[Path, str]) -> int:
    """A context manager to chdir() into |target_dir| and back out on exit.

    Args:
        target_dir: A target directory to chdir into.

    Yields:
        File descriptor to old working directory.
    """
    with OpenContext(".", flags=os.O_RDONLY | os.O_PATH | os.O_CLOEXEC) as fd:
        try:
            os.chdir(target_dir)
            yield fd
        finally:
            os.fchdir(fd)


@contextlib.contextmanager
def ChrootContext(target_dir: Union[Path, str]) -> int:
    """A context manager to chroot() into |target_dir| and back out on exit.

    The current process must already be running with sufficient privileges
    (e.g. root).

    Args:
        target_dir: A target directory to chdir into.
    """
    # Order here is important, and use of handles & . avoids races.
    # First chdir to the new path and save a handle to the old one.  The open
    # handle stays viable across chroot calls.
    with ChdirContext(target_dir):
        # Get a handle to the current / so we can restore to it later.
        with OpenContext(
            "/", flags=os.O_RDONLY | os.O_PATH | os.O_CLOEXEC
        ) as fd:
            try:
                # Chroot to the target_dir (via the cwd . symlink).
                os.chroot(".")
                # Pause here for the caller as we're now inside the chroot.
                yield
            finally:
                # chdir to the saved / handle (breaking out of the chroot).
                os.fchdir(fd)
                # chroot to the saved / (via the cwd . symlink).
                os.chroot(".")
        # Context manager will chdir back to the original cwd via its saved
        # handle.


def _SameFileSystem(path1, path2):
    """Determine whether two paths are on the same filesystem.

    Be resilient to nonsense paths. Return False instead of blowing up.
    """
    try:
        return os.stat(path1).st_dev == os.stat(path2).st_dev
    except OSError:
        return False


class MountOverlayContext:
    """A context manager for mounting an OverlayFS directory.

    An overlay filesystem will be mounted at |mount_dir|, and will be unmounted
    when the context exits.
    """

    OVERLAY_FS_MOUNT_ERRORS = (32,)

    def __init__(self, lower_dir, upper_dir, mount_dir, cleanup=False):
        """Initialize.

        Args:
            lower_dir: The lower directory (read-only).
            upper_dir: The upper directory (read-write).
            mount_dir: The mount point for the merged overlay.
            cleanup: Whether to remove the mount point after unmounting. This
                uses an internal retry logic for cases where unmount is
                successful but the directory still appears busy, and is
                generally more resilient than removing it independently.
        """
        self._lower_dir = lower_dir
        self._upper_dir = upper_dir
        self._mount_dir = mount_dir
        self._cleanup = cleanup
        self.tempdir = None

    def __enter__(self):
        # Upstream Kernel 3.18 and the ubuntu backport of overlayfs have
        # different APIs. We must support both.
        try_legacy = False
        stashed_e_overlay_str = None

        # We must ensure that upperdir and workdir are on the same filesystem.
        if _SameFileSystem(self._upper_dir, tempfile.gettempdir()):
            _TempDirSetup(self)
        elif _SameFileSystem(self._upper_dir, os.path.dirname(self._upper_dir)):
            _TempDirSetup(self, base_dir=os.path.dirname(self._upper_dir))
        else:
            logging.debug(
                "Could create find a workdir on the same filesystem as %s. "
                "Trying legacy API instead.",
                self._upper_dir,
            )
            try_legacy = True

        if not try_legacy:
            try:
                MountDir(
                    "overlay",
                    self._mount_dir,
                    fs_type="overlay",
                    makedirs=False,
                    mount_opts=(
                        "lowerdir=%s" % self._lower_dir,
                        "upperdir=%s" % self._upper_dir,
                        "workdir=%s" % self.tempdir,
                    ),
                    quiet=True,
                )
            except cros_build_lib.RunCommandError as e_overlay:
                if e_overlay.returncode not in self.OVERLAY_FS_MOUNT_ERRORS:
                    raise
                logging.debug(
                    "Failed to mount overlay filesystem. Trying legacy API."
                )
                stashed_e_overlay_str = str(e_overlay)
                try_legacy = True

        if try_legacy:
            try:
                MountDir(
                    "overlayfs",
                    self._mount_dir,
                    fs_type="overlayfs",
                    makedirs=False,
                    mount_opts=(
                        "lowerdir=%s" % self._lower_dir,
                        "upperdir=%s" % self._upper_dir,
                    ),
                    quiet=True,
                )
            except cros_build_lib.RunCommandError as e_overlayfs:
                logging.error(
                    "All attempts at mounting overlay filesystem failed."
                )
                if stashed_e_overlay_str is not None:
                    logging.error("overlay: %s", stashed_e_overlay_str)
                logging.error("overlayfs: %s", str(e_overlayfs))
                raise

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        UmountDir(self._mount_dir, cleanup=self._cleanup)
        _TempDirTearDown(self, force_sudo=True)


MountInfo = collections.namedtuple(
    "MountInfo", "source destination filesystem options"
)


def IterateMountPoints(proc_file: Union[os.PathLike, str] = "/proc/mounts"):
    """Iterate over all mounts as reported by "/proc/mounts".

    Args:
        proc_file: A path to a file whose content is similar to /proc/mounts.
            Default to "/proc/mounts" itself.

    Returns:
        A generator that yields MountInfo objects.
    """
    with open(proc_file, encoding="utf-8") as f:
        for line in f:
            # Escape any \xxx to a char.
            source, destination, filesystem, options, _, _ = [
                re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), x)
                for x in line.split()
            ]
            mtab = MountInfo(source, destination, filesystem, options)
            yield mtab


def IsMounted(
    path: Union[os.PathLike, str],
    proc_file: Union[os.PathLike, str] = "/proc/mounts",
) -> bool:
    """Determine if |path| is already mounted or not."""
    path = str(Path(path).resolve())
    mounts = [x.destination for x in IterateMountPoints(proc_file=proc_file)]
    if path in mounts:
        return True

    return False


def IsMountedReadOnly(
    path: Union[os.PathLike, str],
    proc_file: Union[os.PathLike, str] = "/proc/mounts",
) -> bool:
    """Determine if |path| is mounted read-only."""
    path = str(Path(path).resolve())
    mounts = [
        x
        for x in IterateMountPoints(proc_file=proc_file)
        if x.destination == path
    ]
    if not mounts:
        return False

    # There can be multiple stacked mounts. Check the last one.
    return "ro" in mounts[-1].options.split(",")


def ResolveSymlinkInRoot(
    file_name: Union[str, os.PathLike],
    root: Optional[Union[str, os.PathLike]] = None,
) -> str:
    """Resolve a symlink |file_name| relative to |root|.

    This can be used to resolve absolute symlinks within an alternative root
    path (i.e. chroot). For example:

      ROOT-A/absolute_symlink --> /an/abs/path
      ROOT-A/relative_symlink --> a/relative/path

      absolute_symlink will be resolved to ROOT-A/an/abs/path
      relative_symlink will be resolved to ROOT-A/a/relative/path

    Args:
        file_name: A path to the file.
        root: A path to the root directory.

    Returns:
        |file_name| if |file_name| is not a symlink. Otherwise, the ultimate
        path that |file_name| points to, with links resolved relative to |root|.
    """
    count = 0
    while os.path.islink(file_name):
        count += 1
        if count > 128:
            raise ValueError("Too many link levels for %s." % file_name)
        link = os.readlink(file_name)
        if link.startswith("/"):
            file_name = os.path.join(root, link[1:]) if root else link
        else:
            file_name = os.path.join(os.path.dirname(file_name), link)
    return file_name


def ResolveSymlink(
    file_name: Union[str, os.PathLike]
) -> Union[str, os.PathLike]:
    """Resolve a symlink |file_name| to an absolute path.

    This is similar to ResolveSymlinkInRoot, but does not resolve absolute
    symlinks to an alternative root, and normalizes the path before returning.

    Args:
        file_name: The symlink.

    Returns:
        str - |file_name| if |file_name| is not a symlink. Otherwise, the
        ultimate path that |file_name| points to.
    """
    ret = os.path.realpath(ResolveSymlinkInRoot(file_name, None))
    return ret if isinstance(file_name, str) else Path(ret)


def IsInsideVm():
    """Return True if we are running inside a virtual machine.

    The detection is based on the model of the hard drive.
    """
    for blk_model in glob.glob("/sys/block/*/device/model"):
        if os.path.isfile(blk_model):
            model = ReadFile(blk_model)
            if model.startswith("VBOX") or model.startswith("VMware"):
                return True

    return False


@contextlib.contextmanager
def UmaskContext(mask: int) -> int:
    """Context manager for changing umask.

    Args:
        mask: The new umask setting to apply.  Should be an octal number.

    Yields:
        The old umask setting in case it's useful.  It will still be restored
        automatically by this context manager.
    """
    try:
        old = os.umask(mask)
        yield old
    finally:
        os.umask(old)


def IsRootUser() -> bool:
    """Returns True if the user has root privileges."""
    return os_util.is_root_user()


def IsNonRootUser() -> bool:
    """Returns True if user doesn't have root privileges."""
    return os_util.is_non_root_user()


def sync_storage(
    path: Optional[Union[str, os.PathLike]] = None,
    data_only: Optional[bool] = False,
    filesystem: Optional[bool] = False,
    sudo: Optional[bool] = False,
) -> bool:
    """Sync file data or storage.

    This is directly related to the `sync` command.

    Args:
        path: Path to use for reference when syncing.
        data_only: Whether to sync file data only and ignore metadata.
        filesystem: If True, sync the filesystem the path lives on, otherwise
            sync the file data itself.
        sudo: Whether to run the command via sudo.

    Returns:
        Whether the sync worked.

    Raises:
        ValueError: Only one of data_only & filesystem may be used.
        ValueError: data_only requires a path.
    """
    if IsRootUser() or not path:
        sudo = False

    if data_only:
        if filesystem:
            raise ValueError("data_only & filesystem are exclusive")
        if not path:
            raise ValueError("data_only=True requires a path")

    # If sudo, have to use sync command for now.
    if sudo:
        cmd = ["sync"]
        if data_only:
            cmd += ["--data"]
        if filesystem:
            cmd += ["--file-system"]
        if path:
            cmd += [path]
        result = cros_build_lib.sudo_run(
            cmd, check=False, debug_level=logging.DEBUG
        )
        return result.returncode == 0

    # If not sudo, run code directly.
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    if path:
        fd = None
        try:
            with OpenContext(path) as fd:
                if data_only:
                    logging.debug("%s: syncing data only (no metadata)", path)
                    ret = libc.fdatasync(fd) == 0
                elif filesystem:
                    logging.debug("%s: syncing underlying filesystem", path)
                    ret = libc.syncfs(fd) == 0
                else:
                    logging.debug("%s: syncing file & its metadata", path)
                    ret = libc.fsync(fd) == 0
        except FileNotFoundError:
            return False
    else:
        # This is expensive, so log at a higher level.
        logging.info("syncing all data & filesystems & hardware in the system")
        ret = libc.sync() == 0
    return ret
