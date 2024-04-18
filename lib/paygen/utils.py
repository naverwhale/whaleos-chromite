# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common python commands used by various internal build scripts."""

from collections import namedtuple
import multiprocessing
import os
import time
from typing import Callable, Optional, Tuple

from chromite.utils import key_value_store


AcquireResult = namedtuple("AcquireResult", ["result", "reason"])

MINOR_VERSION = "PAYLOAD_MINOR_VERSION"


def ListdirFullpath(directory):
    """Return all files in a directory with full path names.

    Args:
        directory: directory to find files for.

    Returns:
        Full paths to every file in that directory.
    """
    return [os.path.join(directory, f) for f in os.listdir(directory)]


class RestrictedAttrDict(dict):
    """Define a dictionary which is also a struct.

    The keys will belong to a restricted list of values.
    """

    _slots = ()

    def __init__(self, *args, **kwargs):
        """Ensure that only the expected keys are added."""
        dict.__init__(self, *args, **kwargs)

        # Ensure all slots are at least populated with None.
        for key in self._slots:
            self.setdefault(key)

        for key in self.keys():
            assert key in self._slots, "Unexpected key %s in %s" % (
                key,
                self._slots,
            )

    def __hash__(self):
        """Hash of the class to make hashable."""

        def _hash(obj):
            """Helper to create a deep hash recursively."""
            t = type(obj)
            pre = None
            if isinstance(obj, dict):
                pre = (t, *((k, _hash(v)) for k, v in sorted(obj.items())))
            elif isinstance(obj, (list, set, tuple)):
                pre = (t, *(_hash(v) for v in obj))
            else:
                pre = (t, obj)
            return hash(pre)

        return _hash(self)

    def __eq__(self, other):
        """Equality of the class with respect to hashing logic."""
        return type(self) is type(other) and super().__eq__(other)

    def __ne__(self, other):
        """Inequality of the class."""
        return not self.__eq__(other)

    def __setattr__(self, name, val):
        """Setting an attribute, actually sets a dictionary value."""
        if name not in self._slots:
            raise AttributeError(
                "'%s' may not have attribute '%s'"
                % (self.__class__.__name__, name)
            )
        self[name] = val

    def __getattr__(self, name):
        """Fetching an attribute, actually fetches a dictionary value."""
        if name not in self:
            raise AttributeError(
                "'%s' has no attribute '%s'" % (self.__class__.__name__, name)
            )
        return self[name]

    def __setitem__(self, name, val):
        """Restrict which keys can be stored in this dictionary."""
        if name not in self._slots:
            raise KeyError(name)
        dict.__setitem__(self, name, val)

    def __str__(self):
        """Default stringification behavior."""
        name = self._name if hasattr(self, "_name") else self.__class__.__name__
        return "%s (%s)" % (name, self._GetAttrString())

    def _GetAttrString(self, delim=", ", equal="="):
        """Return string showing all non-None values of self._slots.

        The ordering of attributes in self._slots is honored in string.

        Args:
            delim: String for separating key/value elements in result.
            equal: String to put between key and associated value in result.

        Returns:
            A string like "a='foo', b=12".
        """
        slots = [s for s in self._slots if self[s] is not None]
        elems = ["%s%s%r" % (s, equal, self[s]) for s in slots]
        return delim.join(elems)

    def _clear_if_default(self, key, default):
        """Helper for constructors.

        If they key value is set to the default value, set it to None.

        Args:
            key: Key value to check and possibly clear.
            default: Default value to compare the key value against.
        """
        if self[key] == default:
            self[key] = None


def ReadLsbRelease(sysroot):
    """Reads the /etc/lsb-release file out of the given sysroot.

    Args:
        sysroot: The path to sysroot of an image to read
            sysroot/etc/lsb-release.

    Returns:
        The lsb-release file content in a dictionary of key/values.
    """
    lsb_release_file = os.path.join(sysroot, "etc", "lsb-release")
    lsb_release = {}
    with open(lsb_release_file, "r", encoding="utf-8") as f:
        for line in f:
            tokens = line.strip().split("=")
            lsb_release[tokens[0]] = tokens[1]

    return lsb_release


def ReadMinorVersion(sysroot: str):
    """Reads the /etc/update_engine.conf file out of the given sysroot.

    Args:
        sysroot: The path to sysroot of an image to read
        sysroot/etc/update_engine.conf

    Returns:
        The minor version.
    """
    update_engine_conf = os.path.join(sysroot, "etc", "update_engine.conf")
    versions = key_value_store.LoadFile(update_engine_conf)
    if MINOR_VERSION in versions:
        return versions.get(MINOR_VERSION)
    return None


class MemoryConsumptionSemaphore:
    """Semaphore that tries to acquire only if there is enough memory available.

    Watch the free memory of the host in order to not oversubscribe. Also,
    rate limit so that memory consumption of previously launched
    fledgling process can swell to peak(ish) level. Also assumes this semaphore
    controls the vast majority of the memory utilization on the host when
    active.

    It will also measure the available total memory when there are no
    acquires (and when it was initialized) and use that to baseline a guess
    based on the configured max memory per acquire to limit the total of
    acquires.
    """

    SYSTEM_POLLING_INTERVAL_SECONDS = 0.5

    def __init__(
        self,
        system_available_buffer_bytes: Optional[int] = None,
        single_proc_max_bytes: Optional[int] = None,
        quiescence_time_seconds: Optional[float] = None,
        unchecked_acquires: int = 0,
        total_max: int = 10,
        clock: Callable = time.time,
    ):
        """Create a new MemoryConsumptionSemaphore.

        Args:
            system_available_buffer_bytes: The number of bytes to reserve on the
                system as a buffer against moving into swap (or OOM).
            single_proc_max_bytes: The number of bytes we expect a process to
                consume on the system.
            quiescence_time_seconds: The number of seconds to wait at a minimum
                between acquires. The purpose is to ensure the subprocess begins
                to consume a stable amount of memory.
            unchecked_acquires: The number acquires to allow without checking
                available memory. This is to allow users to supply a mandatory
                minimum even if the semaphore would otherwise not allow it
                (because of the current available memory being to low).
            total_max: The upper bound of maximum concurrent runs (default 10).
            clock: Function that gets float time.
        """
        self.quiescence_time_seconds = quiescence_time_seconds
        self.unchecked_acquires = unchecked_acquires
        self._lock = (
            multiprocessing.RLock()
        )  # single proc may acquire lock twice.
        self._total_max = multiprocessing.RawValue("I", total_max)
        self._n_within = multiprocessing.RawValue("I", 0)
        self._timer_future = multiprocessing.RawValue("d", 0)
        self._clock = clock  # injected, primarily useful for testing.
        self._system_available_buffer_bytes = system_available_buffer_bytes
        self._single_proc_max_bytes = single_proc_max_bytes
        self._base_available = self._get_system_available()

    def _get_system_available(self):
        """Get the system's available memory (memory free before swapping)."""
        with open("/proc/meminfo", encoding="utf-8") as fp:
            for line in fp:
                fields = line.split()
                if fields[0] == "MemAvailable:":
                    size = int(fields[1])
                    if len(fields) > 2:
                        assert fields[2] == "kB", line
                        size *= 1024
                    return size
        return 0

    def _timer_blocked(self):
        """Check the timer, if we're past it return true, otherwise false."""
        if self._clock() >= self._timer_future.value:
            return False
        else:
            return True

    def _inc_within(self):
        """Inc the lock."""
        with self._lock:
            self._n_within.value += 1

    def _dec_within(self):
        """Dec the lock."""
        with self._lock:
            self._n_within.value -= 1

    def _set_timer(self):
        """Set a time in the future to unblock after."""
        with self._lock:
            self._timer_future.value = max(
                self._clock() + self.quiescence_time_seconds,
                self._timer_future.value,
            )

    def _allow_consumption(self):
        """Calculate max utilization to determine if another should be allowed.

        Returns:
            Boolean if you're allowed to consume (acquire).
        """
        with self._lock:
            one_more_total = (
                self._n_within.value + 1
            ) * self._single_proc_max_bytes

        total_avail = self._base_available - self._system_available_buffer_bytes
        # If the guessed max plus yourself is above what's available including
        # the buffer then refuse to admit.
        if total_avail < one_more_total:
            return False
        else:
            return True

    def acquire(self, timeout: float) -> Tuple[bool, str]:
        """Block until enough available memory, or timeout.

        Polls the system every SYSTEM_POLLING_INTERVAL_SECONDS and determines
        if there is enough available memory to proceed, or potentially timeout.

        Args:
            timeout: Time to block for available memory before return.

        Returns:
            True if you should go, and a text representation of the reason for
            the acquire result.
        """

        # Remeasure the base.
        if self._n_within.value == 0:
            self._base_available = self._get_system_available()

        # If you're under the unchecked_acquires go for it, but lock
        # so that we can't race for it.
        with self._lock:
            if self._n_within.value < self.unchecked_acquires:
                self._set_timer()
                self._inc_within()
                return AcquireResult(True, "Succeeded as unchecked")
        init_time = self._clock()

        # If not enough memory or timer is running then block.
        while init_time + timeout > self._clock():
            with self._lock:
                if not self._timer_blocked():
                    # Extrapolate system state and perhaps allow.
                    if (
                        self._allow_consumption()
                        and self._n_within.value < self._total_max.value
                    ):
                        self._set_timer()
                        self._inc_within()
                        return AcquireResult(
                            True, "Allowed due to available memory"
                        )
            time.sleep(
                MemoryConsumptionSemaphore.SYSTEM_POLLING_INTERVAL_SECONDS
            )

        # There was no moment before timeout where we could have run the task.
        return AcquireResult(
            False,
            "Timed out (due to quiescence, " "total max, or avail memory)",
        )

    def release(self):
        """Releases a single acquire."""
        self._dec_within()
