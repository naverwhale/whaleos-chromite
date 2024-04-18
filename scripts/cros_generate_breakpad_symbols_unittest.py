# Copyright 2013 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test cros_generate_breakpad_symbols."""

import ctypes
import io
import logging
import multiprocessing
import os
import pathlib
from unittest import mock

from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import parallel_unittest
from chromite.lib import partial_mock
from chromite.scripts import cros_generate_breakpad_symbols


class FindDebugDirMock(partial_mock.PartialMock):
    """Mock out the DebugDir helper so we can point it to a tempdir."""

    TARGET = "chromite.scripts.cros_generate_breakpad_symbols"
    ATTRS = ("FindDebugDir",)
    DEFAULT_ATTR = "FindDebugDir"

    def __init__(self, path, *args, **kwargs):
        self.path = path
        super().__init__(*args, **kwargs)

    # pylint: disable=unused-argument
    def FindDebugDir(self, _board, sysroot=None):
        return self.path


class IsSharedLibraryTest(cros_test_lib.TestCase):
    """Test IsSharedLibrary"""

    def testSharedLibaries(self):
        """Verify that shared libraries return truthy"""
        shared_libraries = [
            "lib/libcontainer.so",
            "lib64/libnss_db.so.2",
            "usr/lib/libboost_type_erasure.so.1.81.0",
            "usr/lib/v4l1compat.so",
        ]

        for shared_library in shared_libraries:
            self.assertTrue(
                cros_generate_breakpad_symbols.IsSharedLibrary(shared_library),
                msg=f"expected {shared_library} to be a shared library",
            )

    def testExecutables(self):
        """Verify that executables return None"""
        executables = [
            "sbin/crash_reporter",
            "usr/bin/pqso",  # ends in so but not .so
            "usr/bin/perl5.36.0",  # ends in numbers but not .so
        ]

        for executable in executables:
            self.assertFalse(
                cros_generate_breakpad_symbols.IsSharedLibrary(executable),
                msg=f"expected {executable} to not be a shared library",
            )


# This long decorator triggers a false positive in the docstring test.
# https://github.com/PyCQA/pylint/issues/3077
# pylint: disable=bad-docstring-quotes
@mock.patch(
    "chromite.scripts.cros_generate_breakpad_symbols." "GenerateBreakpadSymbol"
)
class GenerateSymbolsTest(cros_test_lib.MockTempDirTestCase):
    """Test GenerateBreakpadSymbols."""

    def setUp(self):
        self.board = "monkey-board"
        self.board_dir = os.path.join(self.tempdir, "build", self.board)
        self.debug_dir = os.path.join(self.board_dir, "usr", "lib", "debug")
        self.breakpad_dir = os.path.join(self.debug_dir, "breakpad")

        # Generate a tree of files which we'll scan through.
        elf_files = [
            "bin/elf",
            "iii/large-elf",
            # Need some kernel modules (with & without matching .debug).
            "lib/modules/3.10/module.ko",
            "lib/modules/3.10/module-no-debug.ko",
            # Need a file which has an ELF only, but not a .debug.
            "usr/bin/elf-only",
            "usr/sbin/elf",
        ]
        debug_files = [
            "bin/bad-file",
            "bin/elf.debug",
            "iii/large-elf.debug",
            "boot/vmlinux.debug",
            "lib/modules/3.10/module.ko.debug",
            # Need a file which has a .debug only, but not an ELF.
            "sbin/debug-only.debug",
            "usr/sbin/elf.debug",
        ]
        for f in [os.path.join(self.board_dir, x) for x in elf_files] + [
            os.path.join(self.debug_dir, x) for x in debug_files
        ]:
            osutils.Touch(f, makedirs=True)

        # Set up random build dirs and symlinks.
        buildid = os.path.join(self.debug_dir, ".build-id", "00")
        osutils.SafeMakedirs(buildid)
        os.symlink("/asdf", os.path.join(buildid, "foo"))
        os.symlink("/bin/sh", os.path.join(buildid, "foo.debug"))
        os.symlink("/bin/sh", os.path.join(self.debug_dir, "file.debug"))
        osutils.WriteFile(
            os.path.join(self.debug_dir, "iii", "large-elf.debug"),
            "just some content",
        )

        self.StartPatcher(FindDebugDirMock(self.debug_dir))

    def markAllFilesAsProcessed(self, gen_mock):
        """Sets mock to pretend it processed all the expected ELF files.

        This avoids having GenerateBreakpadSymbols return an error because not
        all expected files were processed.
        """
        expected_found = list(cros_generate_breakpad_symbols.ALL_EXPECTED_FILES)

        def _SetFound(*_args, **kwargs):
            kwargs["found_files"].extend(expected_found)
            gen_mock.side_effect = None
            return 1

        gen_mock.side_effect = _SetFound

    def testNormal(self, gen_mock):
        """Verify all the files we expect to get generated do"""
        with parallel_unittest.ParallelMock():
            self.markAllFilesAsProcessed(gen_mock)
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board, sysroot=self.board_dir
            )
            self.assertEqual(ret, 0)
            self.assertEqual(gen_mock.call_count, 5)

            # The largest ELF should be processed first.
            call1 = (
                os.path.join(self.board_dir, "iii/large-elf"),
                os.path.join(self.debug_dir, "iii/large-elf.debug"),
            )
            self.assertEqual(gen_mock.call_args_list[0][0], call1)

            # The other ELFs can be called in any order.
            call2 = (
                os.path.join(self.board_dir, "bin/elf"),
                os.path.join(self.debug_dir, "bin/elf.debug"),
            )
            call3 = (
                os.path.join(self.board_dir, "usr/sbin/elf"),
                os.path.join(self.debug_dir, "usr/sbin/elf.debug"),
            )
            call4 = (
                os.path.join(self.board_dir, "lib/modules/3.10/module.ko"),
                os.path.join(
                    self.debug_dir, "lib/modules/3.10/module.ko.debug"
                ),
            )
            call5 = (
                os.path.join(self.board_dir, "boot/vmlinux"),
                os.path.join(self.debug_dir, "boot/vmlinux.debug"),
            )
            exp_calls = set((call2, call3, call4, call5))
            actual_calls = set(
                (
                    gen_mock.call_args_list[1][0],
                    gen_mock.call_args_list[2][0],
                    gen_mock.call_args_list[3][0],
                    gen_mock.call_args_list[4][0],
                )
            )
            self.assertEqual(exp_calls, actual_calls)

    def testFileList(self, gen_mock):
        """Verify that file_list restricts the symbols generated"""
        with parallel_unittest.ParallelMock():
            # Don't need markAllFilesAsProcessed since using file_list will
            # skip the expected-files-processed check.
            call1 = (
                os.path.join(self.board_dir, "usr/sbin/elf"),
                os.path.join(self.debug_dir, "usr/sbin/elf.debug"),
            )

            # Filter with elf path.
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board,
                sysroot=self.board_dir,
                breakpad_dir=self.breakpad_dir,
                file_list=[os.path.join(self.board_dir, "usr", "sbin", "elf")],
            )
            self.assertEqual(ret, 0)
            self.assertEqual(gen_mock.call_count, 1)
            self.assertEqual(gen_mock.call_args_list[0][0], call1)

            # Filter with debug symbols file path.
            gen_mock.reset_mock()
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board,
                sysroot=self.board_dir,
                breakpad_dir=self.breakpad_dir,
                file_list=[
                    os.path.join(self.debug_dir, "usr", "sbin", "elf.debug")
                ],
            )
            self.assertEqual(ret, 0)
            self.assertEqual(gen_mock.call_count, 1)
            self.assertEqual(gen_mock.call_args_list[0][0], call1)

    def testGenLimit(self, gen_mock):
        """Verify generate_count arg works"""
        with parallel_unittest.ParallelMock():
            # Generate nothing!
            # Don't need markAllFilesAsProcessed since using generate_count will
            # skip the expected-files-processed check.
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board,
                sysroot=self.board_dir,
                breakpad_dir=self.breakpad_dir,
                generate_count=0,
            )
            self.assertEqual(ret, 0)
            self.assertEqual(gen_mock.call_count, 0)

            # Generate just one.
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board,
                sysroot=self.board_dir,
                breakpad_dir=self.breakpad_dir,
                generate_count=1,
            )
            self.assertEqual(ret, 0)
            self.assertEqual(gen_mock.call_count, 1)

            # The largest ELF should be processed first.
            call1 = (
                os.path.join(self.board_dir, "iii/large-elf"),
                os.path.join(self.debug_dir, "iii/large-elf.debug"),
            )
            self.assertEqual(gen_mock.call_args_list[0][0], call1)

    def testGenErrors(self, gen_mock):
        """Verify we handle errors from generation correctly"""

        def _SetError(*_args, **kwargs):
            kwargs["num_errors"].value += 1
            return 1

        gen_mock.side_effect = _SetError
        with parallel_unittest.ParallelMock():
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board, sysroot=self.board_dir
            )
            # Expect 5 errors from calls plus 1 from the
            # expected-files-processed check.
            self.assertEqual(ret, 6)
            self.assertEqual(gen_mock.call_count, 5)

    def testCleaningTrue(self, gen_mock):
        """Verify behavior of clean_breakpad=True"""
        with parallel_unittest.ParallelMock():
            self.markAllFilesAsProcessed(gen_mock)
            # Dir does not exist, and then does.
            self.assertNotExists(self.breakpad_dir)
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board,
                sysroot=self.board_dir,
                generate_count=1,
                clean_breakpad=True,
            )
            self.assertEqual(ret, 0)
            self.assertEqual(gen_mock.call_count, 1)
            self.assertExists(self.breakpad_dir)

            # Dir exists before & after.
            # File exists, but then doesn't.
            stub_file = os.path.join(self.breakpad_dir, "fooooooooo")
            osutils.Touch(stub_file)
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board,
                sysroot=self.board_dir,
                generate_count=1,
                clean_breakpad=True,
            )
            self.assertEqual(ret, 0)
            self.assertEqual(gen_mock.call_count, 2)
            self.assertNotExists(stub_file)

    def testCleaningFalse(self, gen_mock):
        """Verify behavior of clean_breakpad=False"""
        with parallel_unittest.ParallelMock():
            self.markAllFilesAsProcessed(gen_mock)
            # Dir does not exist, and then does.
            self.assertNotExists(self.breakpad_dir)
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board,
                sysroot=self.board_dir,
                generate_count=1,
                clean_breakpad=False,
            )
            self.assertEqual(ret, 0)
            self.assertEqual(gen_mock.call_count, 1)
            self.assertExists(self.breakpad_dir)

            # Dir exists before & after.
            # File exists before & after.
            stub_file = os.path.join(self.breakpad_dir, "fooooooooo")
            osutils.Touch(stub_file)
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board,
                sysroot=self.board_dir,
                generate_count=1,
                clean_breakpad=False,
            )
            self.assertEqual(ret, 0)
            self.assertEqual(gen_mock.call_count, 2)
            self.assertExists(stub_file)

    def testExclusionList(self, gen_mock):
        """Verify files in directories of the exclusion list are excluded"""
        exclude_dirs = ["bin", "usr", "fake/dir/fake"]
        with parallel_unittest.ParallelMock():
            self.markAllFilesAsProcessed(gen_mock)
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board, sysroot=self.board_dir, exclude_dirs=exclude_dirs
            )
            self.assertEqual(ret, 0)
            self.assertEqual(gen_mock.call_count, 3)

    def testExpectedFilesCompleteFailure(self, _):
        """Verify if no files are processed, all expected files give errors"""
        with parallel_unittest.ParallelMock() and self.assertLogs(
            level=logging.WARNING
        ) as cm:
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board, sysroot=self.board_dir
            )
            self.assertEqual(ret, 1)
            self.assertIn(
                "Not all expected files were processed successfully",
                "\n".join(cm.output),
            )
            for output in cm.output:
                if (
                    "Not all expected files were processed successfully"
                    in output
                ):
                    # This is the line that lists all the files we didn't find.
                    for (
                        expected_file
                    ) in cros_generate_breakpad_symbols.ExpectedFiles:
                        self.assertIn(expected_file.name, output)

    def testExpectedFilesPartialFailure(self, gen_mock):
        """If some expected files are processed, the others give errors"""
        expected_found = (
            cros_generate_breakpad_symbols.ExpectedFiles.LIBC,
            cros_generate_breakpad_symbols.ExpectedFiles.CRASH_REPORTER,
        )

        def _SetFound(*_args, **kwargs):
            kwargs["found_files"].extend(expected_found)
            gen_mock.side_effect = None
            return 1

        gen_mock.side_effect = _SetFound
        with parallel_unittest.ParallelMock() and self.assertLogs(
            level=logging.WARNING
        ) as cm:
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board, sysroot=self.board_dir
            )
            self.assertEqual(ret, 1)
            self.assertIn(
                "Not all expected files were processed successfully",
                "\n".join(cm.output),
            )
            for output in cm.output:
                if (
                    "Not all expected files were processed successfully"
                    in output
                ):
                    # This is the line that lists all the files we didn't find.
                    for (
                        expected_file
                    ) in cros_generate_breakpad_symbols.ExpectedFiles:
                        if expected_file in expected_found:
                            self.assertNotIn(expected_file.name, output)
                        else:
                            self.assertIn(expected_file.name, output)

    def testExpectedFilesWithSomeIgnored(self, _):
        """If some expected files are ignored, they don't give errors"""
        ignore_expected_files = [
            cros_generate_breakpad_symbols.ExpectedFiles.ASH_CHROME,
            cros_generate_breakpad_symbols.ExpectedFiles.LIBC,
        ]
        with parallel_unittest.ParallelMock() and self.assertLogs(
            level=logging.WARNING
        ) as cm:
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board,
                sysroot=self.board_dir,
                ignore_expected_files=ignore_expected_files,
            )
            self.assertEqual(ret, 1)
            self.assertIn(
                "Not all expected files were processed successfully",
                "\n".join(cm.output),
            )
            for output in cm.output:
                if (
                    "Not all expected files were processed successfully"
                    in output
                ):
                    # This is the line that lists all the files we didn't find.
                    for (
                        expected_file
                    ) in cros_generate_breakpad_symbols.ExpectedFiles:
                        if expected_file in ignore_expected_files:
                            self.assertNotIn(expected_file.name, output)
                        else:
                            self.assertIn(expected_file.name, output)

    def testExpectedFilesWithAllIgnored(self, _):
        """If all expected files are ignored, there is no error"""
        with parallel_unittest.ParallelMock() and self.assertLogs(
            level=logging.WARNING
        ) as cm:
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board,
                sysroot=self.board_dir,
                ignore_expected_files=list(
                    cros_generate_breakpad_symbols.ExpectedFiles
                ),
            )
            self.assertEqual(ret, 0)
            self.assertNotIn(
                "Not all expected files were processed successfully",
                "\n".join(cm.output),
            )

    def testExpectedFilesWithSomeIgnoredAndSomeFound(self, gen_mock):
        """Some expected files are ignored, others processed => no error"""
        expected_found = (
            cros_generate_breakpad_symbols.ExpectedFiles.LIBC,
            cros_generate_breakpad_symbols.ExpectedFiles.CRASH_REPORTER,
        )

        def _SetFound(*_args, **kwargs):
            kwargs["found_files"].extend(expected_found)
            gen_mock.side_effect = None
            return 1

        gen_mock.side_effect = _SetFound
        with parallel_unittest.ParallelMock() and self.assertLogs(
            level=logging.WARNING
        ) as cm:
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbols(
                self.board,
                sysroot=self.board_dir,
                ignore_expected_files=[
                    cros_generate_breakpad_symbols.ExpectedFiles.ASH_CHROME,
                    cros_generate_breakpad_symbols.ExpectedFiles.LIBMETRICS,
                ],
            )
            self.assertEqual(ret, 0)
            self.assertNotIn(
                "Not all expected files were processed successfully",
                "\n".join(cm.output),
            )


class GenerateSymbolTest(cros_test_lib.RunCommandTempDirTestCase):
    """Test GenerateBreakpadSymbol."""

    _DUMP_SYMS_BASE_CMD = ["dump_syms", "-v", "-d", "-m"]

    def setUp(self):
        self.elf_file = os.path.join(self.tempdir, "elf")
        osutils.Touch(self.elf_file)
        self.debug_dir = os.path.join(self.tempdir, "debug")
        self.debug_file = os.path.join(self.debug_dir, "elf.debug")
        osutils.Touch(self.debug_file, makedirs=True)
        # Not needed as the code itself should create it as needed.
        self.breakpad_dir = os.path.join(self.debug_dir, "breakpad")

        self.FILE_OUT = (
            f"{self.elf_file}: ELF 64-bit LSB pie executable, x86-64, "
            "version 1 (SYSV), dynamically linked, interpreter "
            "/lib64/ld-linux-x86-64.so.2, for GNU/Linux 3.2.0, "
            "BuildID[sha1]=cf9a21fa6b14bfb2dfcb76effd713c4536014d95, stripped"
        )
        # A symbol file which would pass validation.
        MINIMAL_SYMBOL_FILE = (
            "MODULE OS CPU ID NAME\n"
            "PUBLIC f10 0 func\n"
            "STACK CFI INIT f10 22 .cfa: $rsp 8 + .ra: .cfa -8 + ^\n"
        )
        self.rc.SetDefaultCmdResult(stdout=MINIMAL_SYMBOL_FILE)
        self.rc.AddCmdResult(
            ["/usr/bin/file", self.elf_file], stdout=self.FILE_OUT
        )
        self.assertCommandContains = self.rc.assertCommandContains
        self.sym_file = os.path.join(self.breakpad_dir, "NAME/ID/NAME.sym")

        self.StartPatcher(FindDebugDirMock(self.debug_dir))

    def assertCommandArgs(self, i, args):
        """Helper for looking at the args of the |i|th call"""
        self.assertEqual(self.rc.call_args_list[i][0][0], args)

    def testNormal(self):
        """Normal run -- given an ELF and a debug file"""
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            self.elf_file,
            self.debug_file,
            self.breakpad_dir,
        )
        self.assertEqual(ret, self.sym_file)
        self.assertEqual(self.rc.call_count, 2)
        self.assertCommandArgs(
            1, self._DUMP_SYMS_BASE_CMD + [self.elf_file, self.debug_dir]
        )
        self.assertExists(self.sym_file)

    def testNormalNoCfi(self):
        """Normal run w/out CFI"""
        # Make sure the num_errors flag works too.
        num_errors = ctypes.c_int(0)
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            self.elf_file,
            self.debug_file,
            breakpad_dir=self.breakpad_dir,
            strip_cfi=True,
            num_errors=num_errors,
        )
        self.assertEqual(ret, self.sym_file)
        self.assertEqual(num_errors.value, 0)
        self.assertCommandArgs(
            1, self._DUMP_SYMS_BASE_CMD + ["-c", self.elf_file, self.debug_dir]
        )
        self.assertEqual(self.rc.call_count, 2)
        self.assertExists(self.sym_file)

    def testNormalElfOnly(self):
        """Normal run with just an ELF will fail"""
        num_errors = ctypes.c_int(0)
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            self.elf_file,
            breakpad_dir=self.breakpad_dir,
            num_errors=num_errors,
        )
        self.assertEqual(ret, 1)
        self.assertEqual(num_errors.value, 1)
        self.assertNotExists(self.sym_file)

    def testNormalSudo(self):
        """Normal run where ELF is readable only by root"""
        with mock.patch.object(os, "access") as mock_access:
            mock_access.return_value = False
            ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
                self.elf_file, self.debug_file, breakpad_dir=self.breakpad_dir
            )
        self.assertEqual(ret, self.sym_file)
        self.assertCommandArgs(
            1,
            ["sudo", "--"]
            + self._DUMP_SYMS_BASE_CMD
            + [self.elf_file, self.debug_dir],
        )

    def testDumpSymsFail(self):
        """The call to dump_syms failed"""
        self.rc.AddCmdResult(
            self._DUMP_SYMS_BASE_CMD + [self.elf_file, self.debug_dir],
            returncode=1,
        )
        num_errors = ctypes.c_int(0)
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            self.elf_file,
            self.debug_file,
            breakpad_dir=self.breakpad_dir,
            num_errors=num_errors,
        )
        self.assertEqual(ret, 1)
        self.assertEqual(num_errors.value, 1)
        self.assertEqual(self.rc.call_count, 2)
        self.assertCommandArgs(
            1, self._DUMP_SYMS_BASE_CMD + [self.elf_file, self.debug_dir]
        )
        self.assertNotExists(self.sym_file)

    def testValidationFail(self):
        """If symbol file validation fails, return an error"""
        BAD_SYMBOL_FILE = "MODULE OS CPU ID NAME\n"
        self.rc.SetDefaultCmdResult(stdout=BAD_SYMBOL_FILE)
        num_errors = ctypes.c_int(0)
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            self.elf_file,
            self.debug_file,
            breakpad_dir=self.breakpad_dir,
            strip_cfi=True,
            num_errors=num_errors,
        )
        self.assertEqual(ret, 1)
        self.assertEqual(num_errors.value, 1)
        self.assertNotExists(self.sym_file)

    def testValidationRaises(self):
        """If symbol file validation raises an error, return an error."""
        BAD_SYMBOL_FILE = (
            "MODULE Linux x86 D3096ED481217FD4C16B29CD9BC208BA0 elf\n"
            "JUNK LINE IS BAD LINE\n"
        )
        self.rc.SetDefaultCmdResult(stdout=BAD_SYMBOL_FILE)
        num_errors = ctypes.c_int(0)
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            self.elf_file,
            self.debug_file,
            breakpad_dir=self.breakpad_dir,
            strip_cfi=True,
            num_errors=num_errors,
        )
        self.assertEqual(ret, 1)
        self.assertEqual(num_errors.value, 1)
        self.assertNotExists(self.sym_file)

    def testForceBasicFallback(self):
        """Running with force_basic_fallback

        Test force_basic_fallback goes straight to _DumpAllowingBasicFallback().
        """
        self.rc.AddCmdResult(
            self._DUMP_SYMS_BASE_CMD + [self.elf_file, self.debug_dir],
            returncode=1,
        )
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            self.elf_file,
            self.debug_file,
            breakpad_dir=self.breakpad_dir,
            force_basic_fallback=True,
        )
        self.assertEqual(ret, self.sym_file)
        self.assertEqual(self.rc.call_count, 2)
        self.assertCommandArgs(
            0, self._DUMP_SYMS_BASE_CMD + [self.elf_file, self.debug_dir]
        )
        self.assertCommandArgs(
            1,
            self._DUMP_SYMS_BASE_CMD
            + ["-c", "-r", self.elf_file, self.debug_dir],
        )
        self.assertExists(self.sym_file)

    def testForceBasicFallbackElfOnly(self):
        """Running with force_basic_fallback run given just an ELF"""
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            self.elf_file,
            breakpad_dir=self.breakpad_dir,
            force_basic_fallback=True,
        )
        self.assertEqual(ret, self.sym_file)
        self.assertEqual(self.rc.call_count, 1)
        self.assertCommandArgs(0, self._DUMP_SYMS_BASE_CMD + [self.elf_file])
        self.assertExists(self.sym_file)

    def testForceBasicFallbackLargeDebugFail(self):
        """In fallback mode, running w/large .debug failed, but retry worked"""
        self.rc.AddCmdResult(
            self._DUMP_SYMS_BASE_CMD + [self.elf_file, self.debug_dir],
            returncode=1,
        )
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            self.elf_file,
            self.debug_file,
            breakpad_dir=self.breakpad_dir,
            force_basic_fallback=True,
        )
        self.assertEqual(ret, self.sym_file)
        self.assertEqual(self.rc.call_count, 2)
        self.assertCommandArgs(
            0, self._DUMP_SYMS_BASE_CMD + [self.elf_file, self.debug_dir]
        )
        self.assertCommandArgs(
            1,
            self._DUMP_SYMS_BASE_CMD
            + ["-c", "-r", self.elf_file, self.debug_dir],
        )
        self.assertExists(self.sym_file)

    def testForceBasicFallbackDebugFail(self):
        """In fallback mode, running w/.debug always fails, but works without"""
        self.rc.AddCmdResult(
            self._DUMP_SYMS_BASE_CMD + [self.elf_file, self.debug_dir],
            returncode=1,
        )
        self.rc.AddCmdResult(
            self._DUMP_SYMS_BASE_CMD
            + ["-c", "-r", self.elf_file, self.debug_dir],
            returncode=1,
        )
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            self.elf_file,
            self.debug_file,
            breakpad_dir=self.breakpad_dir,
            force_basic_fallback=True,
        )
        self.assertEqual(ret, self.sym_file)
        self.assertEqual(self.rc.call_count, 3)
        self.assertCommandArgs(
            0, self._DUMP_SYMS_BASE_CMD + [self.elf_file, self.debug_dir]
        )
        self.assertCommandArgs(
            1,
            self._DUMP_SYMS_BASE_CMD
            + ["-c", "-r", self.elf_file, self.debug_dir],
        )
        self.assertCommandArgs(2, self._DUMP_SYMS_BASE_CMD + [self.elf_file])
        self.assertExists(self.sym_file)

    def testForceBasicFallbackCompleteFail(self):
        """In fallback mode, if dump_syms always fails, still an error"""
        self.rc.SetDefaultCmdResult(returncode=1)
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            self.elf_file,
            breakpad_dir=self.breakpad_dir,
            force_basic_fallback=True,
        )
        self.assertEqual(ret, 1)
        # Make sure the num_errors flag works too.
        num_errors = ctypes.c_int(0)
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            self.elf_file, breakpad_dir=self.breakpad_dir, num_errors=num_errors
        )
        self.assertEqual(ret, 1)
        self.assertEqual(num_errors.value, 1)

    def testKernelObjects(self):
        """Kernel object files should call _DumpAllowingBasicFallback()"""
        ko_file = os.path.join(self.tempdir, "elf.ko")
        osutils.Touch(ko_file)
        self.rc.AddCmdResult(
            self._DUMP_SYMS_BASE_CMD + [ko_file, self.debug_dir],
            returncode=1,
        )
        self.rc.AddCmdResult(
            self._DUMP_SYMS_BASE_CMD + ["-c", "-r", ko_file, self.debug_dir],
            returncode=1,
        )
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            ko_file, self.debug_file, self.breakpad_dir
        )
        self.assertEqual(ret, self.sym_file)
        self.assertEqual(self.rc.call_count, 3)
        self.assertCommandArgs(
            0, self._DUMP_SYMS_BASE_CMD + [ko_file, self.debug_dir]
        )
        self.assertCommandArgs(
            1,
            self._DUMP_SYMS_BASE_CMD + ["-c", "-r", ko_file, self.debug_dir],
        )
        self.assertCommandArgs(2, self._DUMP_SYMS_BASE_CMD + [ko_file])
        self.assertExists(self.sym_file)

    def testGoBinary(self):
        """Go binaries should call _DumpAllowingBasicFallback()

        Also tests that dump_syms failing with 'file contains no debugging
        information' does not fail the script.
        """
        go_binary = os.path.join(self.tempdir, "goprogram")
        osutils.Touch(go_binary)
        go_debug_file = os.path.join(self.debug_dir, "goprogram.debug")
        osutils.Touch(go_debug_file, makedirs=True)
        FILE_OUT_GO = go_binary + (
            ": ELF 64-bit LSB executable, x86-64, "
            "version 1 (SYSV), statically linked, "
            "Go BuildID=KKXVlL66E8Qmngr4qll9/5kOKGZw9I7TmNhoqKLqq/SiYVJam6w5Fo"
            "39B3BtDo/ba8_ceezZ-3R4qEv6_-K, not stripped"
        )
        self.rc.AddCmdResult(["/usr/bin/file", go_binary], stdout=FILE_OUT_GO)
        self.rc.AddCmdResult(
            self._DUMP_SYMS_BASE_CMD + [go_binary, self.debug_dir],
            returncode=1,
        )
        self.rc.AddCmdResult(
            self._DUMP_SYMS_BASE_CMD + ["-c", "-r", go_binary, self.debug_dir],
            returncode=1,
        )
        self.rc.AddCmdResult(
            self._DUMP_SYMS_BASE_CMD + [go_binary],
            returncode=1,
            stderr=(
                f"{go_binary}: file contains no debugging information "
                '(no ".stab" or ".debug_info" sections)'
            ),
        )
        num_errors = ctypes.c_int(0)
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            go_binary, go_debug_file, self.breakpad_dir
        )
        self.assertEqual(ret, 0)
        self.assertEqual(self.rc.call_count, 4)
        self.assertCommandArgs(0, ["/usr/bin/file", go_binary])
        self.assertCommandArgs(
            1, self._DUMP_SYMS_BASE_CMD + [go_binary, self.debug_dir]
        )
        self.assertCommandArgs(
            2,
            self._DUMP_SYMS_BASE_CMD + ["-c", "-r", go_binary, self.debug_dir],
        )
        self.assertCommandArgs(3, self._DUMP_SYMS_BASE_CMD + [go_binary])
        self.assertNotExists(self.sym_file)
        self.assertEqual(num_errors.value, 0)

    def _testBinaryIsInLocalFallback(self, directory, filename):
        binary = os.path.join(self.tempdir, directory, filename)
        osutils.Touch(binary, makedirs=True)
        debug_dir = os.path.join(self.debug_dir, directory)
        debug_file = os.path.join(debug_dir, f"{filename}.debug")
        osutils.Touch(debug_file, makedirs=True)
        self.rc.AddCmdResult(["/usr/bin/file", binary], stdout=self.FILE_OUT)
        self.rc.AddCmdResult(
            self._DUMP_SYMS_BASE_CMD + [binary, debug_dir], returncode=1
        )
        self.rc.AddCmdResult(
            self._DUMP_SYMS_BASE_CMD + ["-c", "-r", binary, debug_dir],
            returncode=1,
        )
        self.rc.AddCmdResult(
            self._DUMP_SYMS_BASE_CMD + [binary],
            returncode=1,
            stderr=(
                f"{binary}: file contains no debugging information "
                '(no ".stab" or ".debug_info" sections)'
            ),
        )
        num_errors = ctypes.c_int(0)
        ret = cros_generate_breakpad_symbols.GenerateBreakpadSymbol(
            binary, debug_file, self.breakpad_dir, sysroot=self.tempdir
        )
        self.assertEqual(ret, 0)
        self.assertEqual(self.rc.call_count, 4)
        self.assertCommandArgs(0, ["/usr/bin/file", binary])
        self.assertCommandArgs(
            1, self._DUMP_SYMS_BASE_CMD + [binary, debug_dir]
        )
        self.assertCommandArgs(
            2, self._DUMP_SYMS_BASE_CMD + ["-c", "-r", binary, debug_dir]
        )
        self.assertCommandArgs(3, self._DUMP_SYMS_BASE_CMD + [binary])
        self.assertNotExists(self.sym_file)
        self.assertEqual(num_errors.value, 0)

    def testAllowlist(self):
        """Binaries in the allowlist should call _DumpAllowingBasicFallback()"""
        self._testBinaryIsInLocalFallback("usr/bin", "goldctl")

    def testUsrLocalSkip(self):
        """Binaries in /usr/local should call _DumpAllowingBasicFallback()"""
        self._testBinaryIsInLocalFallback("usr/local", "minidump_stackwalk")


class ValidateSymbolFileTest(cros_test_lib.TempDirTestCase):
    """Tests ValidateSymbolFile"""

    def _GetTestdataFile(self, filename: str) -> str:
        """Gets the path to a file in the testdata directory.

        Args:
            filename: The base filename of the file.

        Returns:
            A string with the complete path to the file.
        """
        return os.path.join(os.path.dirname(__file__), "testdata", filename)

    def testValidSymbolFiles(self):
        """Make sure ValidateSymbolFile passes on valid files"""

        # All files are in the testdata/ subdirectory.
        VALID_SYMBOL_FILES = [
            # A "normal" symbol file from an executable.
            "basic.sym",
            # A "normal" symbol file from a shared library.
            "basic_lib.sym",
            # A symbol file with PUBLIC records but no FUNC records.
            "public_only.sym",
            # A symbol file with FUNC records but no PUBLIC records.
            "func_only.sym",
            # A symbol file with at least one of every line type.
            "all_line_types.sym",
        ]

        for file in VALID_SYMBOL_FILES:
            with self.subTest(
                file=file
            ), multiprocessing.Manager() as mp_manager:
                found_files = mp_manager.list()
                self.assertTrue(
                    cros_generate_breakpad_symbols.ValidateSymbolFile(
                        self._GetTestdataFile(file),
                        "/build/board/bin/foo",
                        "/build/board",
                        found_files,
                    )
                )
                self.assertFalse(found_files)

    def testInvalidSymbolFiles(self):
        """Make sure ValidateSymbolFile fails on invalid files.

        This test only covers cases that return false, not cases that raise
        exceptions.
        """

        class InvalidSymbolFile:
            """The name of an invalid symbol file + the expected error msg."""

            def __init__(self, filename, expected_errors):
                self.filename = filename
                self.expected_errors = expected_errors

        INVALID_SYMBOL_FILES = [
            InvalidSymbolFile(
                "bad_no_func_or_public.sym",
                [
                    "WARNING:root:/build/board/bin/foo: "
                    "Symbol file has no FUNC or PUBLIC records"
                ],
            ),
            InvalidSymbolFile(
                "bad_no_stack.sym",
                [
                    "WARNING:root:/build/board/bin/foo: "
                    "Symbol file has no STACK records"
                ],
            ),
            InvalidSymbolFile(
                "bad_no_module.sym",
                [
                    "WARNING:root:/build/board/bin/foo: "
                    "Symbol file has 0 MODULE lines"
                ],
            ),
            InvalidSymbolFile(
                "bad_two_modules.sym",
                [
                    "WARNING:root:/build/board/bin/foo: "
                    "Symbol file has 2 MODULE lines"
                ],
            ),
            InvalidSymbolFile(
                "bad_func_no_line_numbers.sym",
                [
                    "WARNING:root:/build/board/bin/foo: "
                    "Symbol file has FUNC records but no line numbers"
                ],
            ),
            InvalidSymbolFile(
                "bad_line_numbers_no_file.sym",
                [
                    "WARNING:root:/build/board/bin/foo: "
                    "Symbol file has line number records but no FILE records"
                ],
            ),
            InvalidSymbolFile(
                "bad_inline_no_files.sym",
                [
                    "WARNING:root:/build/board/bin/foo: "
                    "Symbol file has INLINE records but no FILE records"
                ],
            ),
            InvalidSymbolFile(
                "bad_inline_no_origins.sym",
                [
                    "WARNING:root:/build/board/bin/foo: "
                    "Symbol file has INLINE records but no INLINE_ORIGIN "
                    "records"
                ],
            ),
            InvalidSymbolFile(
                "blank.sym",
                [
                    "WARNING:root:/build/board/bin/foo: "
                    "Symbol file has no STACK records",
                    "WARNING:root:/build/board/bin/foo: "
                    "Symbol file has 0 MODULE lines",
                    "WARNING:root:/build/board/bin/foo: "
                    "Symbol file has no FUNC or PUBLIC records",
                ],
            ),
        ]

        for file in INVALID_SYMBOL_FILES:
            with self.subTest(
                file=file.filename
            ), multiprocessing.Manager() as mp_manager:
                found_files = mp_manager.list()
                with self.assertLogs(level=logging.WARNING) as cm:
                    self.assertFalse(
                        cros_generate_breakpad_symbols.ValidateSymbolFile(
                            self._GetTestdataFile(file.filename),
                            "/build/board/bin/foo",
                            "/build/board",
                            found_files,
                        )
                    )
                self.assertEqual(file.expected_errors, cm.output)
                self.assertFalse(found_files)

    def testInvalidSymbolFilesWhichRaise(self):
        """Test ValidateSymbolFile raise exceptions on certain files"""

        class InvalidSymbolFile:
            """The invalid symbol file + the expected exception message"""

            def __init__(self, filename, expected_exception_regex):
                self.filename = filename
                self.expected_exception_regex = expected_exception_regex

        INVALID_SYMBOL_FILES = [
            InvalidSymbolFile(
                "bad_unknown_line_type.sym",
                r"symbol file has unknown line type UNKNOWN "
                r"\(line='UNKNOWN line type\n'\)",
            ),
            InvalidSymbolFile(
                "bad_blank_line.sym",
                "symbol file has unexpected blank line",
            ),
            InvalidSymbolFile(
                "bad_short_func.sym",
                r"symbol file has FUNC line with 2 words "
                r"\(expected 5 or more\) \(line='FUNC fb0\n'\)",
            ),
            InvalidSymbolFile(
                "bad_short_line_number.sym",
                r"symbol file has line number line with 3 words "
                r"\(expected 4 - 4\) \(line='fb0 106 0\n'\)",
            ),
            InvalidSymbolFile(
                "bad_long_line_number.sym",
                r"symbol file has line number line with 5 words "
                r"\(expected 4 - 4\) \(line='c184 7 59 4 8\n'\)",
            ),
        ]

        for file in INVALID_SYMBOL_FILES:
            with self.subTest(
                file=file.filename
            ), multiprocessing.Manager() as mp_manager:
                found_files = mp_manager.list()
                self.assertRaisesRegex(
                    ValueError,
                    file.expected_exception_regex,
                    cros_generate_breakpad_symbols.ValidateSymbolFile,
                    self._GetTestdataFile(file.filename),
                    "/build/board/bin/foo",
                    "/build/board",
                    found_files,
                )

    def testAllowlist(self):
        """Test that ELFs on the allowlist are allowed to pass."""
        with multiprocessing.Manager() as mp_manager:
            found_files = mp_manager.list()
            self.assertTrue(
                cros_generate_breakpad_symbols.ValidateSymbolFile(
                    self._GetTestdataFile("bad_no_module.sym"),
                    "/build/board/opt/google/chrome/nacl_helper_bootstrap",
                    "/build/board",
                    found_files,
                )
            )
            self.assertFalse(found_files)

    def testAllowlistRegex(self):
        """Test that ELFs on the regex-based allowlist are allowed to pass."""
        with multiprocessing.Manager() as mp_manager:
            found_files = mp_manager.list()
            self.assertTrue(
                cros_generate_breakpad_symbols.ValidateSymbolFile(
                    self._GetTestdataFile("bad_no_module.sym"),
                    "/build/board/lib64/libnss_dns.so.2",
                    "/build/board",
                    found_files,
                )
            )
            self.assertFalse(found_files)

    def testSharedLibrariesSkipStackTest(self):
        """Test that shared libraries can pass validation with no STACK."""
        with multiprocessing.Manager() as mp_manager:
            found_files = mp_manager.list()
            self.assertTrue(
                cros_generate_breakpad_symbols.ValidateSymbolFile(
                    self._GetTestdataFile("bad_no_stack.sym"),
                    "/build/board/lib64/libiw.so.30",
                    "/build/board",
                    found_files,
                )
            )
            self.assertFalse(found_files)

    def _CreateSymbolFile(
        self,
        sym_file: pathlib.Path,
        func_lines: int = 0,
        public_lines: int = 0,
        stack_lines: int = 0,
        line_number_lines: int = 0,
    ) -> None:
        """Creates a symbol file.

        Creates a symbol file with the given number of lines (and enough other
        lines to pass validation) in the temp directory.

        To pass validation, chrome.sym files must be huge; create them
        programmatically during the test instead of checking in a real 800MB+
        chrome symbol file.
        """
        with sym_file.open(mode="w", encoding="utf-8") as f:
            f.write("MODULE OS CPU ID NAME\n")
            f.write("FILE 0 /path/to/source.cc\n")
            for func in range(0, func_lines):
                f.write(f"FUNC {func} 1 0 function{func}\n")
            for public in range(0, public_lines):
                f.write(f"PUBLIC {public} 0 Public{public}\n")
            for line in range(0, line_number_lines):
                f.write(f"{line} 1 {line} 0\n")
            for stack in range(0, stack_lines):
                f.write(f"STACK CFI {stack} .cfa: $esp {stack} +\n")

    def testValidChromeSymbolFile(self):
        """Test that a chrome symbol file can pass the additional checks"""
        sym_file = self.tempdir / "chrome.sym"
        self._CreateSymbolFile(
            sym_file,
            func_lines=100000,
            public_lines=10,
            stack_lines=1000000,
            line_number_lines=1000000,
        )
        with multiprocessing.Manager() as mp_manager:
            found_files = mp_manager.list()
            self.assertTrue(
                cros_generate_breakpad_symbols.ValidateSymbolFile(
                    str(sym_file),
                    "/build/board/opt/google/chrome/chrome",
                    "/build/board",
                    found_files,
                )
            )
            self.assertEqual(
                list(found_files),
                [cros_generate_breakpad_symbols.ExpectedFiles.ASH_CHROME],
            )

    def testInvalidChromeSymbolFile(self):
        """Test that a chrome symbol file is held to higher standards."""

        class ChromeSymbolFileTest:
            """Defines the subtest for an invalid Chrome symbol file."""

            def __init__(
                self,
                name,
                expected_error,
                func_lines=100000,
                stack_lines=1000000,
                line_number_lines=1000000,
            ):
                self.name = name
                self.expected_error = expected_error
                self.func_lines = func_lines
                self.stack_lines = stack_lines
                self.line_number_lines = line_number_lines

        CHROME_SYMBOL_TESTS = [
            ChromeSymbolFileTest(
                name="Insufficient FUNC records",
                func_lines=10000,
                expected_error="chrome should have at least 100,000 FUNC "
                "records, found 10000",
            ),
            ChromeSymbolFileTest(
                name="Insufficient STACK records",
                stack_lines=100000,
                expected_error="chrome should have at least 1,000,000 STACK "
                "records, found 100000",
            ),
            ChromeSymbolFileTest(
                name="Insufficient line number records",
                line_number_lines=100000,
                expected_error="chrome should have at least 1,000,000 "
                "line number records, found 100000",
            ),
        ]
        for test in CHROME_SYMBOL_TESTS:
            with self.subTest(
                name=test.name
            ), multiprocessing.Manager() as mp_manager:
                sym_file = self.tempdir / "chrome.sym"
                self._CreateSymbolFile(
                    sym_file,
                    func_lines=test.func_lines,
                    public_lines=10,
                    stack_lines=test.stack_lines,
                    line_number_lines=test.line_number_lines,
                )
                found_files = mp_manager.list()
                with self.assertLogs(level=logging.WARNING) as cm:
                    self.assertFalse(
                        cros_generate_breakpad_symbols.ValidateSymbolFile(
                            str(sym_file),
                            "/build/board/opt/google/chrome/chrome",
                            "/build/board",
                            found_files,
                        )
                    )
                self.assertIn(test.expected_error, cm.output[0])
                self.assertEqual(len(cm.output), 1)

    def testValidLibcSymbolFile(self):
        """Test that a libc.so symbol file can pass the additional checks."""
        with multiprocessing.Manager() as mp_manager:
            sym_file = self.tempdir / "libc.so.sym"
            self._CreateSymbolFile(
                sym_file, public_lines=200, stack_lines=20000
            )
            found_files = mp_manager.list()
            self.assertTrue(
                cros_generate_breakpad_symbols.ValidateSymbolFile(
                    str(sym_file),
                    "/build/board/lib64/libc.so.6",
                    "/build/board",
                    found_files,
                )
            )
            self.assertEqual(
                list(found_files),
                [cros_generate_breakpad_symbols.ExpectedFiles.LIBC],
            )

    def testInvalidLibcSymbolFile(self):
        """Test that a libc.so symbol file is held to higher standards."""

        class LibcSymbolFileTest:
            """Defines the subtest for an invalid libc symbol file."""

            def __init__(
                self,
                name,
                expected_error,
                public_lines=200,
                stack_lines=20000,
            ):
                self.name = name
                self.expected_error = expected_error
                self.public_lines = public_lines
                self.stack_lines = stack_lines

        LIBC_SYMBOL_TESTS = [
            LibcSymbolFileTest(
                name="Insufficient PUBLIC records",
                public_lines=50,
                expected_error="/build/board/lib64/libc.so.6 should have at "
                "least 100 PUBLIC records, found 50",
            ),
            LibcSymbolFileTest(
                name="Insufficient STACK records",
                stack_lines=1000,
                expected_error="/build/board/lib64/libc.so.6 should have at "
                "least 10000 STACK records, found 1000",
            ),
        ]
        for test in LIBC_SYMBOL_TESTS:
            with self.subTest(
                name=test.name
            ), multiprocessing.Manager() as mp_manager:
                sym_file = self.tempdir / "libc.so.sym"
                self._CreateSymbolFile(
                    sym_file,
                    public_lines=test.public_lines,
                    stack_lines=test.stack_lines,
                )
                found_files = mp_manager.list()
                with self.assertLogs(level=logging.WARNING) as cm:
                    self.assertFalse(
                        cros_generate_breakpad_symbols.ValidateSymbolFile(
                            str(sym_file),
                            "/build/board/lib64/libc.so.6",
                            "/build/board",
                            found_files,
                        )
                    )
                self.assertIn(test.expected_error, cm.output[0])
                self.assertEqual(len(cm.output), 1)

    def testValidCrashReporterSymbolFile(self):
        """Test a crash_reporter symbol file can pass the additional checks."""
        with multiprocessing.Manager() as mp_manager:
            sym_file = self.tempdir / "crash_reporter.sym"
            self._CreateSymbolFile(
                sym_file,
                func_lines=2000,
                public_lines=10,
                stack_lines=2000,
                line_number_lines=20000,
            )
            found_files = mp_manager.list()
            self.assertTrue(
                cros_generate_breakpad_symbols.ValidateSymbolFile(
                    str(sym_file),
                    "/build/board/sbin/crash_reporter",
                    "/build/board",
                    found_files,
                )
            )
            self.assertEqual(
                list(found_files),
                [cros_generate_breakpad_symbols.ExpectedFiles.CRASH_REPORTER],
            )

    def testInvalidCrashReporterSymbolFile(self):
        """Test that a crash_reporter symbol file is held to higher standards"""

        class CrashReporterSymbolFileTest:
            """Defines the subtest for an invalid crash_reporter symbol file."""

            def __init__(
                self,
                name,
                expected_error,
                func_lines=2000,
                stack_lines=2000,
                line_number_lines=20000,
            ):
                self.name = name
                self.expected_error = expected_error
                self.func_lines = func_lines
                self.stack_lines = stack_lines
                self.line_number_lines = line_number_lines

        CRASH_REPORTER_SYMBOL_TESTS = [
            CrashReporterSymbolFileTest(
                name="Insufficient FUNC records",
                func_lines=500,
                expected_error="crash_reporter should have at least 1000 FUNC "
                "records, found 500",
            ),
            CrashReporterSymbolFileTest(
                name="Insufficient STACK records",
                stack_lines=100,
                expected_error="crash_reporter should have at least 1000 STACK "
                "records, found 100",
            ),
            CrashReporterSymbolFileTest(
                name="Insufficient line number records",
                line_number_lines=2000,
                expected_error="crash_reporter should have at least 10,000 "
                "line number records, found 2000",
            ),
        ]
        for test in CRASH_REPORTER_SYMBOL_TESTS:
            with self.subTest(
                name=test.name
            ), multiprocessing.Manager() as mp_manager:
                sym_file = self.tempdir / "crash_reporter.sym"
                self._CreateSymbolFile(
                    sym_file,
                    func_lines=test.func_lines,
                    stack_lines=test.stack_lines,
                    line_number_lines=test.line_number_lines,
                )
                found_files = mp_manager.list()
                with self.assertLogs(level=logging.WARNING) as cm:
                    self.assertFalse(
                        cros_generate_breakpad_symbols.ValidateSymbolFile(
                            str(sym_file),
                            "/build/board/sbin/crash_reporter",
                            "/build/board",
                            found_files,
                        )
                    )
                self.assertIn(test.expected_error, cm.output[0])
                self.assertEqual(len(cm.output), 1)

    def testValidLibMetricsSymbolFile(self):
        """Test a libmetrics.so symbol file can pass the additional checks."""
        with multiprocessing.Manager() as mp_manager:
            sym_file = self.tempdir / "libmetrics.so.sym"
            self._CreateSymbolFile(
                sym_file,
                func_lines=200,
                public_lines=2,
                stack_lines=2000,
                line_number_lines=10000,
            )
            found_files = mp_manager.list()
            self.assertTrue(
                cros_generate_breakpad_symbols.ValidateSymbolFile(
                    str(sym_file),
                    "/build/board/usr/lib64/libmetrics.so",
                    "/build/board",
                    found_files,
                )
            )
            self.assertEqual(
                list(found_files),
                [cros_generate_breakpad_symbols.ExpectedFiles.LIBMETRICS],
            )

    def testInvalidLibMetricsSymbolFile(self):
        """Test that a libmetrics.so symbol file is held to higher standards."""

        class LibMetricsSymbolFileTest:
            """Defines the subtest for an invalid libmetrics.so symbol file."""

            def __init__(
                self,
                name,
                expected_error,
                func_lines=200,
                public_lines=2,
                stack_lines=2000,
                line_number_lines=10000,
            ):
                self.name = name
                self.expected_error = expected_error
                self.func_lines = func_lines
                self.public_lines = public_lines
                self.stack_lines = stack_lines
                self.line_number_lines = line_number_lines

        LIBMETRICS_SYMBOL_TESTS = [
            LibMetricsSymbolFileTest(
                name="Insufficient FUNC records",
                func_lines=10,
                expected_error="libmetrics should have at least 100 FUNC "
                "records, found 10",
            ),
            LibMetricsSymbolFileTest(
                name="Insufficient PUBLIC records",
                public_lines=0,
                expected_error="libmetrics should have at least 1 PUBLIC "
                "record, found 0",
            ),
            LibMetricsSymbolFileTest(
                name="Insufficient STACK records",
                stack_lines=500,
                expected_error="libmetrics should have at least 1000 STACK "
                "records, found 500",
            ),
            LibMetricsSymbolFileTest(
                name="Insufficient line number records",
                line_number_lines=2000,
                expected_error="libmetrics should have at least 5000 "
                "line number records, found 2000",
            ),
        ]
        for test in LIBMETRICS_SYMBOL_TESTS:
            with self.subTest(
                name=test.name
            ), multiprocessing.Manager() as mp_manager:
                sym_file = self.tempdir / "libmetrics.so.sym"
                self._CreateSymbolFile(
                    sym_file,
                    func_lines=test.func_lines,
                    public_lines=test.public_lines,
                    stack_lines=test.stack_lines,
                    line_number_lines=test.line_number_lines,
                )
                found_files = mp_manager.list()
                with self.assertLogs(level=logging.WARNING) as cm:
                    self.assertFalse(
                        cros_generate_breakpad_symbols.ValidateSymbolFile(
                            str(sym_file),
                            "/build/board/usr/lib64/libmetrics.so",
                            "/build/board",
                            found_files,
                        )
                    )
                self.assertIn(test.expected_error, cm.output[0])
                self.assertEqual(len(cm.output), 1)


class UtilsTestDir(cros_test_lib.TempDirTestCase):
    """Tests ReadSymsHeader."""

    def testReadSymsHeaderGoodFile(self):
        """Make sure ReadSymsHeader can parse sym files"""
        sym_file = os.path.join(self.tempdir, "sym")
        osutils.WriteFile(sym_file, "MODULE Linux x86 s0m31D chrooome")
        result = cros_generate_breakpad_symbols.ReadSymsHeader(
            sym_file, "unused_elfname"
        )
        self.assertEqual(result.cpu, "x86")
        self.assertEqual(result.id, "s0m31D")
        self.assertEqual(result.name, "chrooome")
        self.assertEqual(result.os, "Linux")


class UtilsTest(cros_test_lib.TestCase):
    """Tests ReadSymsHeader."""

    def testReadSymsHeaderGoodBuffer(self):
        """Make sure ReadSymsHeader can parse sym file handles"""
        result = cros_generate_breakpad_symbols.ReadSymsHeader(
            io.BytesIO(b"MODULE Linux arm MY-ID-HERE blkid"), "unused_elfname"
        )
        self.assertEqual(result.cpu, "arm")
        self.assertEqual(result.id, "MY-ID-HERE")
        self.assertEqual(result.name, "blkid")
        self.assertEqual(result.os, "Linux")

    def testReadSymsHeaderBadd(self):
        """Make sure ReadSymsHeader throws on bad sym files"""
        self.assertRaises(
            ValueError,
            cros_generate_breakpad_symbols.ReadSymsHeader,
            io.BytesIO(b"asdf"),
            "unused_elfname",
        )

    def testBreakpadDir(self):
        """Make sure board->breakpad path expansion works"""
        expected = "/build/blah/usr/lib/debug/breakpad"
        result = cros_generate_breakpad_symbols.FindBreakpadDir("blah")
        self.assertEqual(expected, result)

    def testDebugDir(self):
        """Make sure board->debug path expansion works"""
        expected = "/build/blah/usr/lib/debug"
        result = cros_generate_breakpad_symbols.FindDebugDir("blah")
        self.assertEqual(expected, result)
