# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test Utils library."""

import multiprocessing
import os
import threading
import time

from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib.paygen import utils


# We access a lot of protected members during testing.
# pylint: disable=protected-access

# Tests involving the memory semaphore should block this long.
ACQUIRE_TIMEOUT = 120
ACQUIRE_SHOULD_BLOCK_TIMEOUT = 20


class TestUtils(cros_test_lib.TempDirTestCase):
    """Test utils methods."""

    @classmethod
    def setUpClass(cls):
        """Class setup to run system polling quickly in semaphore tests."""
        utils.MemoryConsumptionSemaphore.SYSTEM_POLLING_INTERVAL_SECONDS = 0

    class MockClock:
        """Mock clock that is manually incremented."""

        def __call__(self):
            """Return the current mock time."""
            return self._now

        def __init__(self):
            """Init the clock."""
            self._now = 0.0

        def add_time(self, n):
            """Add some amount of time."""
            self._now += n

    def mock_get_system_available(self, how_much):
        """Mock the system's available memory, used to override /proc."""
        return lambda: how_much

    def testRestrictedAttrDictHashing(self):
        """Tests that RestrictedAttrDict hashing works in various cases."""
        # Temporary variables for sanity.
        self.assertEqual(
            hash(utils.RestrictedAttrDict()), hash(utils.RestrictedAttrDict())
        )
        self.assertEqual(utils.RestrictedAttrDict(), utils.RestrictedAttrDict())

        # Local variables with differing addresses.
        a = utils.RestrictedAttrDict()
        b = utils.RestrictedAttrDict()
        self.assertEqual(hash(a), hash(b))
        self.assertEqual(a, b)

    def testRestrictedAttrDictHashingDerivedClasses(self):
        """Tests that RestrictedAttrDict hashing works in derived classes."""

        class A(utils.RestrictedAttrDict):
            """Derived class A."""

            _slots = ("foo",)

        a = A()

        class B(utils.RestrictedAttrDict):
            """Derived class B."""

            _slots = ("foo",)

        b = B()
        self.assertNotEqual(hash(a), hash(b))
        self.assertNotEqual(a, b)

    def testRestrictedAttrDictHashingDerivedClassesUnorderedSlots(self):
        """Tests that RestrictedAttrDict hashing works

        ... in derived classes with unordered slots.
        """

        class A(utils.RestrictedAttrDict):
            """Derived class A."""

            _slots = ("foo", "bar")

        a = A()

        class B(utils.RestrictedAttrDict):
            """Derived class B."""

            _slots = ("bar", "foo")

        b = B()
        self.assertNotEqual(hash(a), hash(b))
        self.assertNotEqual(a, b)

    def testRestrictedAttrDictHashingDerivedClassesUnorderedInitialization(
        self,
    ):
        """Tests that RestrictedAttrDict hashing works

        ... in derived class with unordered slots initialization.
        """

        class A(utils.RestrictedAttrDict):
            """Derived class A."""

            _slots = ("foo", "bar")

        a1 = A(foo=1, bar=2)
        a2 = A(bar=2, foo=1)
        self.assertEqual(hash(a1), hash(a2))
        self.assertEqual(a1, a2)

    def testRestrictedAttrDictHashingDerivedClassesDataStructures(self):
        """Tests that RestrictedAttrDict hashing works

        ... in derived class with data structures.
        """

        class A(utils.RestrictedAttrDict):
            """Derived class A."""

            _slots = ("foo", "bar", "car", "far")

        a1 = A(foo={}, bar=set(), car=[], far=tuple())
        a2 = A(car=[], bar=set(), foo={}, far=tuple())
        self.assertEqual(hash(a1), hash(a2))
        self.assertEqual(a1, a2)

        a3 = A(foo={}, bar=set(), car=[], far=tuple())
        a4 = A(car=1, bar=set(), foo={}, far=tuple())
        self.assertNotEqual(hash(a3), hash(a4))
        self.assertNotEqual(a3, a4)

    def testListdirFullpath(self):
        file_a = os.path.join(self.tempdir, "a")
        file_b = os.path.join(self.tempdir, "b")

        osutils.Touch(file_a)
        osutils.Touch(file_b)

        self.assertEqual(
            sorted(utils.ListdirFullpath(self.tempdir)), [file_a, file_b]
        )

    def testReadLsbRelease(self):
        """Tests that we correctly read the lsb release file."""
        path = os.path.join(self.tempdir, "etc", "lsb-release")
        osutils.WriteFile(path, "key=value\nfoo=bar\n", makedirs=True)

        self.assertEqual(
            utils.ReadLsbRelease(self.tempdir), {"key": "value", "foo": "bar"}
        )

    def testReadMinorVersion(self):
        """Tests that we correctly read the update_engine.conf file."""
        path = os.path.join(self.tempdir, "etc", "update_engine.conf")
        osutils.WriteFile(
            path, "PAYLOAD_VERSION=2\nPAYLOAD_MINOR_VERSION=6\n", makedirs=True
        )

        self.assertEqual(utils.ReadMinorVersion(self.tempdir), "6")

    def testMassiveMemoryConsumptionSemaphore(self):
        """Tests that we block on not having enough memory."""
        # You should never get 2**64 bytes.
        _semaphore = utils.MemoryConsumptionSemaphore(
            system_available_buffer_bytes=2**64,
            single_proc_max_bytes=2**64,
            quiescence_time_seconds=0.0,
        )

        # You can't get that much.
        self.assertEqual(
            _semaphore.acquire(ACQUIRE_SHOULD_BLOCK_TIMEOUT).result, False
        )

    def testNoMemoryConsumptionSemaphore(self):
        """Tests that you can acquire a very little amount of memory."""
        # You should always get one byte.
        _semaphore = utils.MemoryConsumptionSemaphore(
            system_available_buffer_bytes=1,
            single_proc_max_bytes=1,
            quiescence_time_seconds=0.0,
        )

        # Sure you can have two bytes.
        self.assertEqual(_semaphore.acquire(ACQUIRE_TIMEOUT).result, True)
        _semaphore.release()

    def testTotalMaxMemoryConsumptionSemaphore(self):
        """Tests that the total_max is respected."""
        _semaphore = utils.MemoryConsumptionSemaphore(
            system_available_buffer_bytes=0,
            single_proc_max_bytes=1,
            quiescence_time_seconds=0.0,
            total_max=3,
        )
        # Look at all this memory.
        _semaphore._get_system_available = self.mock_get_system_available(
            2**64
        )
        # Sure you can have three.
        self.assertEqual(_semaphore.acquire(ACQUIRE_TIMEOUT).result, True)
        self.assertEqual(_semaphore.acquire(ACQUIRE_TIMEOUT).result, True)
        self.assertEqual(_semaphore.acquire(ACQUIRE_TIMEOUT).result, True)
        # Nope, you're now over max.
        self.assertEqual(_semaphore.acquire(1).result, False)

    def testQuiesceMemoryConsumptionSemaphore(self):
        """Tests that you wait for memory utilization to settle (quiesce)."""
        # All you want is two bytes.
        _semaphore = utils.MemoryConsumptionSemaphore(
            system_available_buffer_bytes=1,
            single_proc_max_bytes=1,
            quiescence_time_seconds=2.0,
        )

        # Should want two bytes, have a whole lot.
        _semaphore._get_system_available = self.mock_get_system_available(
            2**64
        )
        self.assertEqual(_semaphore.acquire(ACQUIRE_TIMEOUT).result, True)
        _semaphore.release()

        # Should want two bytes, have a whole lot (but you'll block for 2
        # seconds).
        _semaphore._get_system_available = self.mock_get_system_available(
            2**64 - 2
        )
        self.assertEqual(_semaphore.acquire(ACQUIRE_TIMEOUT).result, True)
        _semaphore.release()

    def testUncheckedMemoryConsumptionSemaphore(self):
        """Tests that some acquires work unchecked."""
        # You should never get 2**64 bytes (i wish...).
        _semaphore = utils.MemoryConsumptionSemaphore(
            system_available_buffer_bytes=2**64,
            single_proc_max_bytes=2**64,
            quiescence_time_seconds=2.0,
            unchecked_acquires=2,
        )

        # Nothing available, but we expect unchecked_acquires to allow it.
        _semaphore._get_system_available = self.mock_get_system_available(0)
        self.assertEqual(_semaphore.acquire(ACQUIRE_TIMEOUT).result, True)
        _semaphore.release()
        self.assertEqual(_semaphore.acquire(ACQUIRE_TIMEOUT).result, True)
        _semaphore.release()

    def testQuiescenceUnblocksMemoryConsumptionSemaphore(self):
        """Test that after a period of time you unblock (due to quiescence)."""
        _semaphore = utils.MemoryConsumptionSemaphore(
            system_available_buffer_bytes=1,
            single_proc_max_bytes=1,
            quiescence_time_seconds=2.0,
            unchecked_acquires=0,
        )

        # Make large amount of memory available, but we expect quiescence
        # to block the second task.
        _semaphore._get_system_available = self.mock_get_system_available(
            2**64
        )
        start_time = time.time()
        self.assertEqual(_semaphore.acquire(ACQUIRE_TIMEOUT).result, True)
        _semaphore.release()

        # Get the lock or die trying. We spin fast here instead of
        # ACQUIRE_TIMEOUT.
        while not _semaphore.acquire(1).result:
            continue
        _semaphore.release()

        # Check that the lock was acquired after quiescence_time_seconds.
        end_time = time.time()
        # Why 1.8? Because the clock isn't monotonic and we don't want to flake.
        self.assertGreaterEqual(end_time - start_time, 1.8)

    def testThreadedMemoryConsumptionSemaphore(self):
        """Test many threads simultaneously using the Semaphore."""
        initial_memory = 6
        # These are lists so we can write nonlocal.
        mem_avail = [initial_memory]
        good_thread_exits = [0]
        mock_clock = TestUtils.MockClock()
        lock, exit_lock = threading.Lock(), threading.Lock()
        test_threads = 8

        # Currently executes in 1.6 seconds a 2 x Xeon Gold 6154 CPUs
        get_and_releases = 50

        def sub_mem():
            with lock:
                mem_avail[0] = mem_avail[0] - 1
                self.assertGreaterEqual(mem_avail[0], 0)

        def add_mem():
            with lock:
                mem_avail[0] = mem_avail[0] + 1
                self.assertGreaterEqual(mem_avail[0], 0)

        def get_mem():
            with lock:
                return mem_avail[0]

        # Ask for two bytes available each time.
        _semaphore = utils.MemoryConsumptionSemaphore(
            system_available_buffer_bytes=1,
            single_proc_max_bytes=1,
            quiescence_time_seconds=0.1,
            unchecked_acquires=1,
            clock=mock_clock,
        )
        _semaphore._get_system_available = get_mem

        def hammer_semaphore():
            for _ in range(get_and_releases):
                while not _semaphore.acquire(0.1).result:
                    continue
                # Simulate 'using the memory'.
                sub_mem()
                time.sleep(0.1)
                add_mem()
                _semaphore.release()
            with exit_lock:
                good_thread_exits[0] = good_thread_exits[0] + 1

        threads = [
            threading.Thread(target=hammer_semaphore)
            for _ in range(test_threads)
        ]
        for x in threads:
            x.daemon = True
            x.start()

        # ~Maximum 600 seconds realtime, keeps clock ticking for overall
        # timeout.
        for _ in range(60000):
            time.sleep(0.01)
            mock_clock.add_time(0.1)

            # Maybe we can break early? (and waste some time for other threads).
            threads_dead = [not x.is_alive() for x in threads]
            if all(threads_dead):
                break

        # If we didn't get here a thread did not exit. This is fatal and may
        # indicate a deadlock has been introduced.
        self.assertEqual(initial_memory, get_mem())
        self.assertEqual(good_thread_exits[0], test_threads)

    def testMultiProcessedMemoryConsumptionSemaphore(self):
        """Test many processes simultaneously using the Semaphore."""
        initial_memory = 6

        mem_avail = multiprocessing.Value("I", initial_memory, lock=True)
        good_process_exits = multiprocessing.Value("I", 0, lock=True)
        n_processes = 4

        # Currently executes in 10 seconds a 2 x Xeon Gold 6154 CPUs.
        get_and_releases = 25

        def sub_mem():
            with mem_avail.get_lock():
                mem_avail.value -= 1
                self.assertGreaterEqual(mem_avail.value, 0)

        def add_mem():
            with mem_avail.get_lock():
                mem_avail.value += 1
                self.assertLessEqual(mem_avail.value, 6)

        def get_mem():
            with mem_avail.get_lock():
                return mem_avail.value

        # Ask for two bytes available each time.
        _semaphore = utils.MemoryConsumptionSemaphore(
            system_available_buffer_bytes=1,
            single_proc_max_bytes=1,
            quiescence_time_seconds=0.1,
            unchecked_acquires=1,
        )

        _semaphore._get_system_available = get_mem

        def hammer_semaphore():
            for _ in range(get_and_releases):
                while not _semaphore.acquire(0.1).result:
                    continue
                # Simulate 'using the memory'.
                sub_mem()
                time.sleep(0.1)
                add_mem()
                _semaphore.release()
            with good_process_exits.get_lock():
                good_process_exits.value = good_process_exits.value + 1

        processes = [
            multiprocessing.Process(target=hammer_semaphore)
            for _ in range(n_processes)
        ]

        for p in processes:
            p.daemon = True
            p.start()

        for p in processes:
            p.join()

        # If we didn't get here a proc did not exit. This is fatal and may
        # indicate a deadlock has been introduced.
        self.assertEqual(initial_memory, get_mem())
        with good_process_exits.get_lock():
            self.assertEqual(good_process_exits.value, n_processes)
