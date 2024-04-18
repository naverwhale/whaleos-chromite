# Copyright 2013 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Support for Linux namespaces"""

import contextlib
import ctypes
import ctypes.util
import errno
import logging
import os
import signal

# Note: We avoid cros_build_lib here as that's a "large" module and we want
# to keep this "light" and standalone.  The subprocess usage in here is also
# simple by design -- if it gets more complicated, we should look at using
# the cros_build_lib.run helper.
import subprocess
import sys
from typing import List, Optional

from chromite.lib import commandline
from chromite.lib import locking
from chromite.lib import osutils
from chromite.lib import process_util
from chromite.utils import os_util
from chromite.utils import proctitle_util


CLONE_FILES = 0x00000400
CLONE_FS = 0x00000200
CLONE_NEWCGROUP = 0x02000000
CLONE_NEWIPC = 0x08000000
CLONE_NEWNET = 0x40000000
CLONE_NEWNS = 0x00020000
CLONE_NEWPID = 0x20000000
CLONE_NEWUSER = 0x10000000
CLONE_NEWUTS = 0x04000000


def SetNS(fd, nstype):
    """Binding to the Linux setns system call. See setns(2) for details.

    Args:
        fd: An open file descriptor or path to one.
        nstype: Namespace to enter; one of CLONE_*.

    Raises:
        OSError: if setns failed.
    """
    try:
        fp = None
        if isinstance(fd, str):
            fp = open(fd, "wb")  # pylint: disable=consider-using-with
            fd = fp.fileno()

        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        if libc.setns(ctypes.c_int(fd), ctypes.c_int(nstype)) != 0:
            e = ctypes.get_errno()
            raise OSError(e, os.strerror(e))
    finally:
        if fp is not None:
            fp.close()


def Unshare(flags):
    """Binding to the Linux unshare system call. See unshare(2) for details.

    Args:
        flags: Namespaces to unshare; bitwise OR of CLONE_* flags.

    Raises:
        OSError: if unshare failed.
    """
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    if libc.unshare(ctypes.c_int(flags)) != 0:
        e = ctypes.get_errno()
        raise OSError(e, os.strerror(e))


def _ReapChildren(pid: int, uid: Optional[int], gid: Optional[int]) -> None:
    """Reap all children that get reparented to us until we see |pid| exit.

    Args:
        pid: The main child to watch for.
        uid: The user to switch to first.
        gid: The group to switch to first.
    """
    if gid is not None:
        os.setgid(gid)
    if uid is not None:
        os.setuid(uid)

    while True:
        try:
            (wpid, status) = os.wait()
            if pid == wpid:
                process_util.ExitAsStatus(status)
        except OSError as e:
            if e.errno == errno.ECHILD:
                raise ValueError(
                    "All children of the current processes have been reaped, "
                    "but %u was not one of them. This means that %u is not a "
                    "child of the current processes." % (pid)
                )
            elif e.errno != errno.EINTR:
                raise


def _SafeTcSetPgrp(fd, pgrp):
    """Set |pgrp| as the controller of the tty |fd|."""
    try:
        curr_pgrp = os.tcgetpgrp(fd)
    except OSError as e:
        # This can come up when the fd is not connected to a terminal.
        if e.errno == errno.ENOTTY:
            return
        raise

    # We can change the owner only if currently own it.  Otherwise we'll get
    # stopped by the kernel with SIGTTOU and that'll hit the whole group.
    if curr_pgrp == os.getpgrp():
        os.tcsetpgrp(fd, pgrp)


def _ForwardToChildPid(pid, signal_to_forward):
    """Setup a signal handler that forwards the given signal to |pid|."""

    def _ForwardingHandler(signum, _frame):
        try:
            os.kill(pid, signum)
        except ProcessLookupError:
            # The target PID might have already exited, and thus we get a
            # ProcessLookupError when trying to send it a signal.
            logging.debug(
                "Can't forward signal %u to pid %u as it doesn't exist",
                signum,
                pid,
            )

    signal.signal(signal_to_forward, _ForwardingHandler)


def CreatePidNs(uid: Optional[int] = None, gid: Optional[int] = None) -> None:
    """Start a new pid namespace.

    This will launch all the right manager processes.  The child that returns
    will be isolated in a new pid namespace.

    If functionality is not available, then it will return w/out doing anything.

    A note about the processes generated as a result of calling this function:
    You call CreatePidNs() in pid X
    - X launches Pid Y,
      - Pid X will now do nothing but wait for Pid Y to finish and then
        sys.exit() with that return code
      - Y launches Pid Z
        - Pid Y will now do nothing but wait for Pid Z to finish and then
          sys.exit() with that return code
        - **Pid Z returns from CreatePidNs**. So, the caller of this function
          continues in a different process than the one that made the call.
            - All SIGTERM/SIGINT signals are forwarded down from pid X to pid Z
              to handle.
            - SIGKILL will only kill pid X, and leak Pid Y and Z.

    Args:
        uid: The user to run the init processes as.
        gid: The group to run the init processes as.

    Returns:
        The last pid outside of the namespace. (i.e., pid X)
    """
    first_pid = os.getpid()

    try:
        # First create the namespace.
        Unshare(CLONE_NEWPID)
    except OSError as e:
        if e.errno == errno.EINVAL:
            # For older kernels, or the functionality is disabled in the config,
            # return silently.  We don't want to hard require this stuff.
            return first_pid
        else:
            # For all other errors, abort.  They shouldn't happen.
            raise

    # Used to make sure process groups are in the right state before we try to
    # forward the controlling terminal.
    lock = locking.PipeLock()

    # Now that we're in the new pid namespace, fork.  The parent is the master
    # of it in the original namespace, so it only monitors the child inside it.
    # It is only allowed to fork once too.
    pid = os.fork()
    if pid:
        proctitle_util.settitle("pid ns", "external init")

        # We forward termination signals to the child and trust the child to
        # respond sanely. Later, ExitAsStatus propagates the exit status back
        # up.
        _ForwardToChildPid(pid, signal.SIGINT)
        _ForwardToChildPid(pid, signal.SIGTERM)

        # Forward the control of the terminal to the child so it can manage
        # input.
        _SafeTcSetPgrp(sys.stdin.fileno(), pid)

        # Signal our child it can move forward.
        lock.Post()
        del lock

        # Reap the children as the parent of the new namespace.
        _ReapChildren(pid, uid=uid, gid=gid)
    else:
        # Make sure to unshare the existing mount point if needed.  Some distros
        # create shared mount points everywhere by default.
        try:
            osutils.Mount(
                "none", "/proc", 0, osutils.MS_PRIVATE | osutils.MS_REC
            )
        except OSError as e:
            if e.errno != errno.EINVAL:
                raise

        # The child needs its own proc mount as it'll be different.
        osutils.Mount(
            "proc",
            "/proc",
            "proc",
            osutils.MS_NOSUID
            | osutils.MS_NODEV
            | osutils.MS_NOEXEC
            | osutils.MS_RELATIME,
        )

        # Wait for our parent to finish initialization.
        lock.Wait()
        del lock

        # Resetup the locks for the next phase.
        lock = locking.PipeLock()

        pid = os.fork()
        if pid:
            proctitle_util.settitle("pid ns", "init")

            # We forward termination signals to the child and trust the child to
            # respond sanely. Later, ExitAsStatus propagates the exit status
            # back up.
            _ForwardToChildPid(pid, signal.SIGINT)
            _ForwardToChildPid(pid, signal.SIGTERM)

            # Now that we're in a new pid namespace, start a new process group
            # so that children have something valid to use.  Otherwise
            # getpgrp/etc... will get back 0 which tends to confuse -- you can't
            # setpgrp(0) for example.
            os.setpgrp()

            # Forward the control of the terminal to the child so it can manage
            # input.
            _SafeTcSetPgrp(sys.stdin.fileno(), pid)

            # Signal our child it can move forward.
            lock.Post()
            del lock

            # Watch all the children.  We need to act as the master inside the
            # namespace and reap old processes.
            _ReapChildren(pid, uid=uid, gid=gid)

    # Wait for our parent to finish initialization.
    lock.Wait()
    del lock

    # Create a process group for the grandchild so it can manage things
    # independent of the init process.
    os.setpgrp()

    # The grandchild will return and take over the rest of the sdk steps.
    return first_pid


def CreateNetNs():
    """Start a new net namespace

    We will bring up the loopback interface, but that is all.

    If functionality is not available, then it will return w/out doing anything.
    """
    # The net namespace was added in 2.6.24 and may be disabled in the kernel.
    try:
        Unshare(CLONE_NEWNET)
    except OSError as e:
        if e.errno == errno.EINVAL:
            return
        else:
            # For all other errors, abort.  They shouldn't happen.
            raise

    # Since we've unshared the net namespace, we need to bring up loopback.
    # The kernel automatically adds the various ip addresses, so skip that.
    try:
        subprocess.call(["ip", "link", "set", "up", "lo"])
    except OSError as e:
        if e.errno == errno.ENOENT:
            print(
                "warning: could not bring up loopback for network; "
                "install the iproute2 package",
                file=sys.stderr,
            )
        else:
            raise


def CreateUserNs(new_uid: int = 0, new_gid: int = 0) -> None:
    """Start a user namespace

    This will create a new user namespace and move the current process into it.
    It will fail if the current process is multi-threaded.

    In the new user namespace, the current process will:
    - have specified new UID/GID
    - have all capabilities (with the namespace)

    This function is useful when you want to enter other namespaces (e.g. mount
    namespace) without root privileges.

    Args:
        new_uid: UID that will be mapped to the UID in the original namespace.
        new_gid: GID that will be mapped to the GID in the original namespace.
    """
    orig_uid = os.getuid()
    orig_gid = os.getgid()

    Unshare(CLONE_NEWUSER)

    # Set up a UID/GID mapping that maps the original UID/GID to the requested
    # UID and GID in the new user namespace. The order of writing these files
    # matters.
    # See `man 1 user_namespaces` for details.
    with open("/proc/self/setgroups", "w", encoding="utf-8") as f:
        f.write("deny")
    with open("/proc/self/uid_map", "w", encoding="utf-8") as f:
        f.write(f"{new_uid} {orig_uid} 1\n")
    with open("/proc/self/gid_map", "w", encoding="utf-8") as f:
        f.write(f"{new_gid} {orig_gid} 1\n")


def SimpleUnshare(
    mount: bool = True,
    uts: bool = True,
    ipc: bool = True,
    net: bool = False,
    pid: bool = False,
    cgroup: bool = False,
    pid_uid: Optional[int] = None,
    pid_gid: Optional[int] = None,
) -> None:
    """Simpler helper for setting up namespaces quickly.

    If support for any namespace type is not available, we'll silently skip it.

    Args:
        mount: Create a mount namespace.
        uts: Create a UTS namespace.
        ipc: Create an IPC namespace.
        net: Create a net namespace.
        pid: Create a pid namespace.
        cgroup: Create a cgroup namespace.
        pid_uid: The UID to switch the init to when creating a pid namespace.
        pid_gid: The GID to switch the init to when creating a pid namespace.
    """
    # The mount namespace is the only one really guaranteed to exist --
    # it's been supported forever and it cannot be turned off.
    if mount:
        Unshare(CLONE_NEWNS)

    # The UTS namespace was added 2.6.19 and may be disabled in the kernel.
    if uts:
        try:
            Unshare(CLONE_NEWUTS)
        except OSError as e:
            if e.errno != errno.EINVAL:
                pass

    # The IPC namespace was added 2.6.19 and may be disabled in the kernel.
    if ipc:
        try:
            Unshare(CLONE_NEWIPC)
        except OSError as e:
            if e.errno != errno.EINVAL:
                pass

    if net:
        CreateNetNs()

    if pid:
        CreatePidNs(uid=pid_uid, gid=pid_gid)

    # The cgroup namespace was added in 4.6 and may be disabled in the kernel.
    if cgroup:
        try:
            Unshare(CLONE_NEWCGROUP)
        except OSError as e:
            if e.errno != errno.EINVAL:
                pass

    # We considered unsharing the time namespace as well.  Unfortunately,
    # the usefulness of time namespaces is limited:
    # - they only isolate the CLOCK_BOOTTIME and CLOCK_MONOTONIC clocks
    # - there's no way to set these clocks apart from updating the offset in the
    #   /proc/self/timens_offset file, which cannot be edited after a process
    #   has been created in the new time namespace
    # - CLOCK_REALTIME is not isolated
    # Hence we've left them out.


def ReExecuteWithNamespace(
    argv: List[str],
    preserve_env: bool = False,
    network: bool = False,
    clear_saved_id: bool = False,
) -> None:
    """Re-execute as root so we can unshare resources.

    Args:
        argv: Command line arguments to run as root user.
        preserve_env: If True, preserve existing environment variables when
            running as root user.
        network: If False, disable access to the network.
        clear_saved_id: Whether to clear the saved-uid & saved-gid.  See
            os_util.switch_to_sudo_user.
    """
    # Re-run the command as a root user in order to create the namespaces.
    # Ideally, we can rework this logic to swap to the root user in a way that
    # doesn't involve re-executing the command.
    commandline.RunAsRootUser(argv, preserve_env=preserve_env)

    SimpleUnshare(net=not network, pid=True)
    # We got our namespaces, so switch back to the non-root user.
    os_util.switch_to_sudo_user(clear_saved_id=clear_saved_id)


@contextlib.contextmanager
def use_network_sandbox():
    """Context manager to manage switching between network namespaces.

    The default behavior here is to disallow network connectivity during core
    client execution, and restore network connectivity on client completion to
    perform tasks which require the previous network state.
    """

    network_fd = None
    with contextlib.ExitStack() as stack:
        try:
            # Get an open handle to a working network namespace so we can switch
            # back to it for network-dependent operations (e.g. telemetry
            # uploads).
            # pylint: disable=consider-using-with
            network_fd = stack.enter_context(open("/proc/self/ns/net", "rb"))
            logging.debug(
                "open %s %s",
                network_fd.fileno(),
                os.readlink("/proc/self/ns/net"),
            )
        except OSError as e:
            logging.debug(
                "failed to open file descriptor to current network namespace: "
                "%s",
                repr(e),
            )

        try:
            # Make sure we run with network disabled to prevent leakage.
            SimpleUnshare(net=True, pid=True)
            # We got our namespaces, so switch back to the non-root user.
            os_util.switch_to_sudo_user()
        except OSError as e:
            logging.warning("an unshare(2) operation failed: %s", repr(e))

        try:
            yield
        finally:
            # Don't attempt SetNS if we don't have a useful file descriptor for
            # the network namespace.
            if network_fd:
                try:
                    # Turn network back on to allow containing telemetry trace
                    # to be sent to clearcut.
                    os.setresuid(0, 0, -1)
                    os.setresgid(0, 0, -1)
                    SetNS(network_fd.fileno(), CLONE_NEWNET)
                except OSError as e:
                    logging.warning(
                        "Trying to re-enter original network namespace failed: "
                        "%s",
                        repr(e),
                    )
