# Copyright 2014 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Collection of tests to run on the rootfs of a built image.

This module should only be imported inside the chroot.
"""

from __future__ import division

import collections
import errno
import fnmatch
import glob
import io
import itertools
import logging
import mimetypes
import os
from pathlib import Path
import re
import stat
from typing import NamedTuple
import unittest

from chromite.third_party import lddtree
from chromite.third_party.pyelftools.elftools.common import exceptions
from chromite.third_party.pyelftools.elftools.elf import elffile
import magic  # pylint: disable=import-error

# pylint: disable=ungrouped-imports
from chromite.cros.test import usergroup_baseline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import image_test_lib
from chromite.lib import osutils
from chromite.lib import parseelf
from chromite.lib import portage_util
from chromite.utils.parser import shebang


class LocaltimeTest(image_test_lib.ImageTestCase):
    """Verify that /etc/localtime is a symlink to /var/lib/timezone/localtime.

    This is an example of an image test. The image is already mounted. The
    test can access rootfs via ROOT_A constant.
    """

    def TestLocaltimeIsSymlink(self):
        localtime_path = os.path.join(image_test_lib.ROOT_A, "etc", "localtime")
        self.assertTrue(os.path.islink(localtime_path))

    def TestLocaltimeLinkIsCorrect(self):
        localtime_path = os.path.join(image_test_lib.ROOT_A, "etc", "localtime")
        self.assertEqual(
            "/var/lib/timezone/localtime", os.readlink(localtime_path)
        )


def _GuessMimeType(magic_obj, file_name):
    """Guess a file's mimetype base on its extension and content.

    File extension is favored over file content to reduce noise.

    Args:
        magic_obj: A loaded magic instance.
        file_name: A path to the file.

    Returns:
        A mime type of |file_name|.
    """
    mime_type, _ = mimetypes.guess_type(file_name)
    if not mime_type:
        mime_type = magic_obj.file(file_name)
    return mime_type


class BlockedTest(image_test_lib.ImageTestCase):
    """Verify that rootfs does not contain blocked items."""

    BLOCKED_PACKAGES = (
        "app-text/iso-codes",
        "dev-java/icedtea",
        "dev-java/icedtea6-bin",
        "dev-java/openjdk-bin",
        "dev-lang/perl",
        "dev-lang/python",
        "dev-lang/tcl",
        "media-sound/pulseaudio",
        "sys-apps/mosys",
        "x11-libs/libxklavier",
    )

    BLOCKED_FILES = (
        "/usr/bin/java",
        "/usr/bin/javac",
        "/usr/bin/perl",
        "/usr/bin/python",
        "/usr/bin/tclsh",
        "/usr/share/kdump/boot/kdump-image",
    )

    BLOCKED_DIRS = ("/usr/share/locale",)

    def TestBlockedDirectories(self):
        for path in self.BLOCKED_DIRS:
            full_path = os.path.join(image_test_lib.ROOT_A, path.lstrip(os.sep))
            self.assertFalse(
                os.path.isdir(full_path), "Directory %s is not allowed." % path
            )

    def TestBlockedFileTypes(self):
        """Fail if there are files of prohibited types (e.g. C++ source code).

        The allow list has higher precedence than the block list.
        """
        blocked_patterns = [
            re.compile(x)
            for x in [
                r"^text/x-c\+\+$",
                r"^text/x-c$",
            ]
        ]
        allowed_patterns = [
            re.compile(x)
            for x in [
                r".*/braille/.*",
                r".*/brltty/.*",
                r".*/etc/sudoers$",
                r".*/dump_vpd_log$",
                r".*\.conf$",
                r".*/libnl/classid$",
                r".*/locale/",
                r".*/X11/xkb/",
                r".*/chromeos-assets/",
                r".*/udev/rules.d/",
                r".*/firmware/ar3k/.*pst$",
                r".*/etc/services",
                # Python reads this file at runtime to look up install features.
                r".*/usr/include/python[\d\.]*/pyconfig.h$",
                r".*/usr/lib/node_modules/.*",
                r".*/usr/share/dev-install/portage",
                r".*/opt/pita/qml",
            ]
        ]

        failures = []

        magic_obj = magic.open(magic.MAGIC_MIME_TYPE)
        magic_obj.load()
        for root, _, file_names in os.walk(image_test_lib.ROOT_A):
            for file_name in file_names:
                full_name = os.path.join(root, file_name)
                if os.path.islink(full_name) or not os.path.isfile(full_name):
                    continue

                mime_type = _GuessMimeType(magic_obj, full_name)
                if any(
                    x.match(mime_type) for x in blocked_patterns
                ) and not any(x.match(full_name) for x in allowed_patterns):
                    failures.append(
                        "File %s type %s is not allowed."
                        % (full_name, mime_type)
                    )
        magic_obj.close()

        self.assertFalse(failures, "\n".join(failures))

    def TestBlockedPackages(self):
        """Fail if any blocked packages are installed."""
        for package in self.BLOCKED_PACKAGES:
            self.assertFalse(
                portage_util.PortageqHasVersion(
                    package, sysroot=image_test_lib.ROOT_A
                )
            )

    def TestBlockedFiles(self):
        """Fail if any blocked files exist."""
        for path in self.BLOCKED_FILES:
            full_path = os.path.join(image_test_lib.ROOT_A, path.lstrip(os.sep))
            self.assertFalse(
                os.path.exists(full_path),
                "Path exists but should not: %s" % full_path,
            )

    def TestValidInterpreter(self):
        """Fail if a script's interpreter is not found, or not executable.

        A script interpreter is anything after the #! sign, up to the end of
        line or the first space.
        """
        failures = []

        for root, _, file_names in os.walk(image_test_lib.ROOT_A):
            for file_name in file_names:
                full_name = os.path.join(root, file_name)
                file_stat = os.lstat(full_name)
                if (
                    not stat.S_ISREG(file_stat.st_mode)
                    or (file_stat.st_mode & 0o0111) == 0
                ):
                    continue

                with open(full_name, "rb") as f:
                    if f.read(2) != "#!":
                        continue
                    line = "#!" + f.readline().strip()

                try:
                    # Ignore arguments to the interpreter.
                    interp = shebang.parse(line).command
                except ValueError:
                    failures.append(
                        'File %s has an invalid interpreter path: "%s".'
                        % (full_name, line)
                    )

                # Absolute path to the interpreter.
                interp = os.path.join(image_test_lib.ROOT_A, interp.lstrip("/"))
                # Interpreter could be a symlink. Resolve it.
                interp = osutils.ResolveSymlinkInRoot(
                    interp, image_test_lib.ROOT_A
                )
                if not os.path.isfile(interp):
                    failures.append(
                        "File %s uses non-existing interpreter %s."
                        % (full_name, interp)
                    )
                elif (os.stat(interp).st_mode & 0o111) == 0:
                    failures.append(
                        "Interpreter %s is not executable." % interp
                    )

        self.assertFalse(failures, "\n".join(failures))


class LinkageTest(image_test_lib.ImageTestCase):
    """Verify that all binaries and libraries have proper linkage."""

    def setUp(self):
        osutils.MountDir(
            os.path.join(image_test_lib.STATEFUL, "var_overlay"),
            os.path.join(image_test_lib.ROOT_A, "var"),
            mount_opts=("bind",),
        )

    def tearDown(self):
        osutils.UmountDir(
            os.path.join(image_test_lib.ROOT_A, "var"),
            cleanup=False,
        )

    def _IsPackageMerged(self, package_name):
        has_version = portage_util.PortageqHasVersion(
            package_name, sysroot=os.path.abspath(image_test_lib.ROOT_A)
        )
        if has_version:
            logging.info("Package is available: %s", package_name)
        else:
            logging.info("Package is not available: %s", package_name)
        return has_version

    def TestLinkage(self):
        """Find main executable binaries and check their linkage."""
        binaries = [
            "bin/sed",
        ]

        if self._IsPackageMerged("chromeos-base/chromeos-login"):
            binaries.append("sbin/session_manager")

        if self._IsPackageMerged("x11-base/xorg-server"):
            binaries.append("usr/bin/Xorg")

        # When chrome is built with USE="pgo_generate", rootfs chrome is
        # actually a symlink to a real binary which is in the stateful
        # partition. So we do not check for a valid chrome binary in that case.
        if not self._IsPackageMerged(
            "chromeos-base/chromeos-chrome[pgo_generate]"
        ):
            if self._IsPackageMerged(
                "chromeos-base/chromeos-chrome[app_shell]"
            ):
                binaries.append("opt/google/chrome/app_shell")
            elif self._IsPackageMerged("chromeos-base/chromeos-chrome"):
                binaries.append("opt/google/chrome/chrome")

        if self._IsPackageMerged("net-print/hplip"):
            binaries.append("usr/libexec/cups/filter/hpcups")
            binaries.append("usr/libexec/cups/filter/hpps")

        binaries = [os.path.join(image_test_lib.ROOT_A, x) for x in binaries]

        # Grab all .so files
        libraries = []
        for root, _, files in os.walk(image_test_lib.ROOT_A):
            for name in files:
                filename = os.path.join(root, name)
                if ".so" in filename:
                    libraries.append(filename)

        ldpaths = lddtree.LoadLdpaths(image_test_lib.ROOT_A)
        failures = []
        for to_test in itertools.chain(binaries, libraries):
            # to_test could be a symlink, we need to resolve it relative to
            # ROOT_A.
            while os.path.islink(to_test):
                link = os.readlink(to_test)
                if link.startswith("/"):
                    to_test = os.path.join(image_test_lib.ROOT_A, link[1:])
                else:
                    to_test = os.path.join(os.path.dirname(to_test), link)
            try:
                elf = lddtree.ParseELF(
                    to_test, root=image_test_lib.ROOT_A, ldpaths=ldpaths
                )

                if os.path.basename(to_test) in [
                    # Deps mounted from squashfs at runtime.
                    "libcros_camera.so",
                    # Deps mounted from squashfs at runtime.
                    "intel-ipu6.so",
                    # Deps mounted from squashfs at runtime.
                    "camera.qcom.core.so",
                    # libasound_module_ctl_ipaudio.so dep outside normal search
                    # paths.
                    "libasound_module_pcm_ipaudio.so",
                    # libfwupdutil.so dep outside normal search paths.
                    "libfwupdutil.so",
                    # libfwupdengine.so dep outside normal search paths.
                    "libfwupdengine.so",
                ]:
                    continue

                for lib in elf["needed"]:
                    if not lib in elf["libs"] or not elf["libs"][lib]["path"]:
                        failures.append(
                            "Fail linkage test for /%s: unresolved library %s"
                            % (
                                os.path.relpath(
                                    to_test, start=image_test_lib.ROOT_A
                                ),
                                lib,
                            )
                        )

            except lddtree.exceptions.ELFError:
                continue
            except IOError as e:
                self.fail("Fail linkage test for %s: %s" % (to_test, e))
        if failures:
            self.fail(str(failures))


@unittest.expectedFailure
class FileSystemMetaDataTest(image_test_lib.ImageTestCase):
    """A test class to gather file system stats such as free inodes, blocks."""

    def TestStats(self):
        """Collect inodes and blocks usage."""
        # Find the loopback device that was mounted to ROOT_A.
        loop_device = None
        root_path = os.path.abspath(os.readlink(image_test_lib.ROOT_A))
        for mtab in osutils.IterateMountPoints():
            if mtab.destination == root_path:
                loop_device = mtab.source
                break
        self.assertTrue(loop_device, "Cannot find loopback device for ROOT_A.")

        # Gather file system stats with tune2fs.
        cmd = ["tune2fs", "-l", loop_device]
        # tune2fs produces output like this:
        #
        # tune2fs 1.42 (29-Nov-2011)
        # Filesystem volume name:   ROOT-A
        # Last mounted on:          <not available>
        # Filesystem UUID:          <none>
        # Filesystem magic number:  0xEF53
        # Filesystem revision #:    1 (dynamic)
        # ...
        #
        # So we need to ignore the first line.
        ret = cros_build_lib.sudo_run(
            cmd, capture_output=True, extra_env={"LC_ALL": "C"}
        )
        fs_stat = dict(
            line.split(":", 1)
            for line in ret.stdout.splitlines()
            if ":" in line
        )
        free_inodes = int(fs_stat["Free inodes"])
        free_blocks = int(fs_stat["Free blocks"])
        inode_count = int(fs_stat["Inode count"])
        block_count = int(fs_stat["Block count"])
        block_size = int(fs_stat["Block size"])

        sum_file_size = 0
        for root, _, filenames in os.walk(image_test_lib.ROOT_A):
            for file_name in filenames:
                full_name = os.path.join(root, file_name)
                file_stat = os.lstat(full_name)
                sum_file_size += file_stat.st_size

        metadata_size = (block_count - free_blocks) * block_size - sum_file_size

        self.OutputPerfValue(
            "free_inodes_over_inode_count",
            free_inodes * 100 / inode_count,
            "percent",
            graph="free_over_used_ratio",
        )
        self.OutputPerfValue(
            "free_blocks_over_block_count",
            free_blocks * 100 / block_count,
            "percent",
            graph="free_over_used_ratio",
        )
        self.OutputPerfValue(
            "apparent_size",
            sum_file_size,
            "bytes",
            higher_is_better=False,
            graph="filesystem_stats",
        )
        self.OutputPerfValue(
            "metadata_size",
            metadata_size,
            "bytes",
            higher_is_better=False,
            graph="filesystem_stats",
        )


class SymbolsTest(image_test_lib.ImageTestCase):
    """Tests related to symbols in ELF files."""

    def setUp(self):
        # Mapping of file name --> 2-tuple (import, export).
        self._known_symtabs = {}

    def _GetSymbols(self, file_name):
        """Return a 2-tuple (import, export) of an ELF file |file_name|.

        Import and export in the returned tuple are sets of strings (symbol
        names).
        """
        if file_name in self._known_symtabs:
            return self._known_symtabs[file_name]

        # We use BytesIO here to obviate fseek/fread time in pyelftools.
        stream = io.BytesIO(osutils.ReadFile(file_name, mode="rb"))

        try:
            elf = elffile.ELFFile(stream)
        except exceptions.ELFError:
            raise ValueError("%s is not an ELF file." % file_name)

        imp, exp = parseelf.ParseELFSymbols(elf)
        self._known_symtabs[file_name] = imp, exp
        return imp, exp

    def TestImportedSymbolsAreAvailable(self):
        """Ensure all ELF files' imported symbols are available in ROOT-A.

        In this test, we find all imported symbols and exported symbols from all
        ELF files on the system. This test will fail if the set of imported
        symbols is not a subset of exported symbols.

        This test DOES NOT simulate ELF loading. "TestLinkage" does that with
        `lddtree`.
        """
        # Import tables of files, keyed by file names.
        importeds = collections.defaultdict(set)
        # All exported symbols.
        exported = set()

        # Allow firmware binaries which are mostly provided by various
        # vendors, some in proprietary format. This is OK because the files are
        # not executable on the main CPU, so we treat them as blobs that we load
        # into external hardware/devices. This is ensured by PermissionTest.
        # TestNoExecutableInFirmwareFolder.
        permitted_patterns = (
            os.path.join("dir-ROOT-A", "lib", "firmware", "*"),
            # Jetstream firmware package.
            os.path.join("dir-ROOT-A", "usr", "share", "fastrpc", "*"),
        )

        for root, _, filenames in os.walk(image_test_lib.ROOT_A):
            for filename in filenames:
                full_name = os.path.join(root, filename)
                if os.path.islink(full_name) or not os.path.isfile(full_name):
                    continue

                if any(
                    fnmatch.fnmatch(full_name, x) for x in permitted_patterns
                ):
                    continue

                try:
                    imp, exp = self._GetSymbols(full_name)
                except (ValueError, IOError):
                    continue
                else:
                    importeds[full_name] = imp
                    exported.update(exp)

        # TODO(toolchain): Remove the old libthread_db-1.0.so entry once glibc
        # is upgraded past 2.34
        known_unsatisfieds = {
            "libthread_db-1.0.so": {
                b"ps_pdwrite",
                b"ps_pdread",
                b"ps_lgetfpregs",
                b"ps_lsetregs",
                b"ps_lgetregs",
                b"ps_lsetfpregs",
                b"ps_pglobal_lookup",
                b"ps_getpid",
            },
            "libthread_db.so.1": {
                b"ps_pdwrite",
                b"ps_pdread",
                b"ps_lgetfpregs",
                b"ps_lsetregs",
                b"ps_lgetregs",
                b"ps_lsetfpregs",
                b"ps_pglobal_lookup",
                b"ps_getpid",
            },
        }

        excluded_files = set(
            [
                # These libraries are built against Android NDK's libc and have
                # several imports that will appear to be unsatisfied.
                "libmojo_core_arc32.so",
                "libmojo_core_arc64.so",
                # The camera shared libraries these libraries need are mounted
                # at runtime.
                "libcros_camera.so",
                "camera_hal/intel-ipu6.so",
                "camera.qcom.core.so",
                "camera_hal/usb.so",
                # In glibc 2.35, ldconfig is a static PIE executable with
                # dynamic sections which confuses the image test.
                # Ignore any missing symbols in it (b/244512686).
                "sbin/ldconfig",
            ]
        )

        failures = []
        for full_name, imported in importeds.items():
            parts = full_name.split("/")
            file_name = parts[-1]
            dir_file_name = "/".join(parts[-2:])
            if file_name in excluded_files or dir_file_name in excluded_files:
                continue
            missing = (
                imported - exported - known_unsatisfieds.get(file_name, set())
            )
            if missing:
                failures.append(
                    "File %s contains unsatisfied symbols: %r"
                    % (full_name, missing)
                )
        self.assertFalse(failures, "\n".join(failures))


class UserGroupTest(image_test_lib.ImageTestCase):
    """Tests users and groups in /etc/passwd and /etc/group."""

    @staticmethod
    def _validate_passwd(entry):
        """Check users that are not in the baseline.

        The user ID should match the group ID, and the user's home directory
        and shell should be invalid.
        """
        uid = entry.uid
        gid = entry.gid

        if uid != gid:
            logging.error(
                'New user "%s" has uid %d and different gid %d',
                entry.user,
                uid,
                gid,
            )
            return False

        if entry.home != "/dev/null":
            logging.error(
                'Expected /dev/null for new user "%s" home dir, got "%s"',
                entry.user,
                entry.home,
            )
            return False

        if entry.shell != "/bin/false":
            logging.error(
                'Expected /bin/false for new user "%s" shell, got "%s"',
                entry.user,
                entry.shell,
            )
            return False

        return True

    @staticmethod
    def _validate_group(entry):
        """Check groups that are not in the baseline.

        Allow groups that have no users and groups with only the matching user.
        """
        group_name = entry.group
        users = entry.users

        # Groups with no users and groups with only the matching user are OK.
        if not users or users == {group_name}:
            return True

        logging.error('New group "%s" has users "%s"', group_name, users)
        return False

    @staticmethod
    def _match_passwd(expected, actual):
        """Match password, uid, gid, home, and shell."""
        matched = True

        if expected.encpasswd != actual.encpasswd:
            matched = False
            logging.error(
                'Expected encrypted password "%s" for user "%s", got "%s".',
                expected.encpasswd,
                expected.user,
                actual.encpasswd,
            )

        if expected.uid != actual.uid:
            matched = False
            logging.error(
                'Expected uid %d for user "%s", got %d.',
                expected.uid,
                expected.user,
                actual.uid,
            )

        if expected.gid != actual.gid:
            matched = False
            logging.error(
                'Expected gid %d for user "%s", got %d.',
                expected.gid,
                expected.user,
                actual.gid,
            )

        if isinstance(expected.home, set):
            valid_home = actual.home in expected.home
        else:
            valid_home = actual.home == expected.home
        if not valid_home:
            matched = False
            logging.error(
                'Expected home "%s" for user "%s", got "%s".',
                expected.home,
                expected.user,
                actual.home,
            )

        if isinstance(expected.shell, set):
            valid_shell = actual.shell in expected.shell
        else:
            valid_shell = actual.shell == expected.shell
        if not valid_shell:
            matched = False
            logging.error(
                'Expected shell "%s" for user "%s", got "%s".',
                expected.shell,
                expected.user,
                actual.shell,
            )

        return matched

    @staticmethod
    def _match_group(expected, actual):
        """Match password, gid, and members."""
        matched = True

        if expected.encpasswd != actual.encpasswd:
            matched = False
            logging.error(
                'Expected encrypted password "%s" for group "%s", got "%s".',
                expected.encpasswd,
                expected.group,
                actual.encpasswd,
            )

        if expected.gid != actual.gid:
            matched = False
            logging.error(
                'Expected gid %d for group "%s", got %d.',
                expected.gid,
                expected.group,
                actual.gid,
            )

        if expected.users != actual.users:
            matched = False
            logging.error(
                'Expected members "%s" for group "%s", got "%s".',
                expected.users,
                expected.group,
                actual.users,
            )

        return matched

    def _LoadPath(self, path):
        """Load the given passwd/group file.

        Args:
            path: Path to the file.

        Returns:
            A dict of passwd/group entries indexed by account name.
        """
        d = {}
        for line in osutils.ReadFile(path).splitlines():
            fields = line.split(":")
            if len(fields) == 7:
                # wpa:!:219:219::/dev/null:/bin/false
                entry = usergroup_baseline.UserEntry(
                    user=fields[0],
                    encpasswd=fields[1],
                    uid=int(fields[2]),
                    gid=int(fields[3]),
                    home=fields[5],
                    shell=fields[6],
                )
                d[entry.user] = entry
            elif len(fields) == 4:
                # tty:!:5:power,brltty
                users = set()
                if fields[3]:
                    users = set(fields[3].split(","))
                entry = usergroup_baseline.GroupEntry(
                    group=fields[0],
                    encpasswd=fields[1],
                    gid=int(fields[2]),
                    users=users,
                )
                d[entry.group] = entry
            else:
                raise ValueError('Invalid baseline format "%s"' % line)

        return d

    def _LoadBaseline(self, basename):
        """Loads the passwd or group baseline."""
        d = None
        if "passwd" in basename:
            d = usergroup_baseline.USER_BASELINE.copy()

            # Per-board baseline.
            if (
                self._board
                and self._board in usergroup_baseline.USER_BOARD_BASELINES
            ):
                d.update(usergroup_baseline.USER_BOARD_BASELINES[self._board])
        elif "group" in basename:
            d = usergroup_baseline.GROUP_BASELINE.copy()

            # Per-board baseline.
            if (
                self._board
                and self._board in usergroup_baseline.GROUP_BOARD_BASELINES
            ):
                d.update(usergroup_baseline.GROUP_BOARD_BASELINES[self._board])
        else:
            raise ValueError('Invalid basename "%s"' % basename)

        return d

    def _CheckFile(self, basename):
        """Validates the passwd or group file."""
        match_func = getattr(self, "_match_%s" % basename)
        validate_func = getattr(self, "_validate_%s" % basename)

        expected_entries = self._LoadBaseline(basename)
        actual_entries = self._LoadPath(
            os.path.join(image_test_lib.ROOT_A, "etc", basename)
        )

        success = True
        for entry, details in actual_entries.items():
            if entry not in expected_entries:
                is_valid = validate_func(details)
                if not is_valid:
                    logging.error(
                        'Unexpected %s entry for "%s".', basename, entry
                    )

                success = success and is_valid
                continue

            expected = expected_entries[entry]
            match_res = match_func(expected, details)
            success = success and match_res

        missing = set(expected_entries.keys()) - set(actual_entries.keys())
        for m in missing:
            logging.info('Ignoring missing %s entry for "%s".', basename, m)

        self.assertTrue(success)

    def TestUsers(self):
        """Enforces known user IDs."""
        self._CheckFile("passwd")

    def TestGroups(self):
        """Enforces known group IDs."""
        self._CheckFile("group")


class CroshTest(image_test_lib.ImageTestCase):
    """Check crosh code."""

    # Base directory for crosh code.
    CROSH_DIR = "usr/share/crosh"

    def TestUnknownModules(self):
        """Only permit known crosh modules on the system."""
        # Do *not* add modules to this list until they've been reviewed by
        # security or someone in the crosh/OWNERS list.  Insecure code here can
        # easily cause compromise of CrOS system security in verified mode.  It
        # has happened.
        ALLOWED = {
            "dev.d": {"50-crosh.sh"},
            "extra.d": set(),
            "removable.d": {"50-crosh.sh"},
        }

        base_path = os.path.join(image_test_lib.ROOT_A, self.CROSH_DIR)
        for mod_dir, good_modules in ALLOWED.items():
            mod_path = os.path.join(base_path, mod_dir)
            if not os.path.exists(mod_path):
                continue

            found_modules = set(os.listdir(mod_path))
            unknown_modules = found_modules - good_modules
            self.assertEqual(set(), unknown_modules)


class SymlinkTest(image_test_lib.ImageTestCase):
    """Verify symlinks in the rootfs."""

    # These are an allow list only.  We don't require any of these to actually
    # be symlinks.  But if they are, they have to point to these targets.
    #
    # The key is the symlink and the value is the symlink target.
    # Both accept fnmatch style expressions (i.e. globs).
    _ACCEPTABLE_LINKS = {
        # Allow any /etc path to point to any /run path.
        "/etc/*": {"/run/*"},
        "/etc/localtime": {"/var/lib/timezone/localtime"},
        "/etc/machine-id": {"/var/lib/dbus/machine-id"},
        "/etc/mtab": {"/proc/mounts"},
        # Some boards don't set this up properly.  It's not a big deal.
        "/usr/libexec/editor": {"/usr/bin/*"},
        # These are hacks to make dev images and `dev_install` work.  Normally
        # /usr/local isn't mounted or populated, so it's not too big a deal to
        # let these things always point there.
        "/etc/env.d/*": {"/usr/local/etc/env.d/*"},
        "/usr/bin/python*": {
            "/usr/local/usr/bin/python*",
            "/usr/local/bin/python*",
        },
        "/usr/lib/portage": {
            "/usr/local/usr/lib/portage",
            "/usr/local/lib/portage",
        },
        "/usr/lib/python-exec": {
            "/usr/local/usr/lib/python-exec",
            "/usr/local/lib/python-exec",
        },
        "/usr/lib/python*": {
            "/usr/local/usr/lib/python*",
            "/usr/local/lib/python*",
        },
        "/usr/lib64/python*": {
            "/usr/local/usr/lib64/python*",
            "/usr/local/lib64/python*",
        },
        "/usr/lib/debug": {"/usr/local/usr/lib/debug"},
        # Used by `file` and libmagic.so when the package is in /usr/local.
        "/usr/share/misc/magic.mgc": {"/usr/local/share/misc/magic.mgc"},
        "/usr/share/portage": {"/usr/local/share/portage"},
        # Needed for the ARC++/ARCVM dual build. For test images only.
        "/opt/google/vms/android": {"/usr/local/vms/android"},
        # TODO(b/150806692): Cleanup this library symlink.
        # Allow /opt/pita/lib path to point to any /run path. For PluginVM DLC.
        "/opt/pita/lib": {"/run/*"},
    }

    @classmethod
    def _SymlinkTargetAllowed(cls, source, target):
        """See whether |source| points to an acceptable |target|."""
        # Scan the allow list.
        for allow_source, allow_targets in cls._ACCEPTABLE_LINKS.items():
            if fnmatch.fnmatch(source, allow_source) and any(
                fnmatch.fnmatch(target, x) for x in allow_targets
            ):
                return True

        # Reject everything else.
        return False

    def TestCheckSymlinkTargets(self):
        """Make sure the targets of all symlinks are 'valid'."""
        failures = []
        for root, _, files in os.walk(image_test_lib.ROOT_A):
            for name in files:
                full_path = os.path.join(root, name)
                try:
                    target = os.readlink(full_path)
                except OSError as e:
                    # If it's not a symlink, ignore it.
                    if e.errno == errno.EINVAL:
                        continue
                    raise

                # Ignore symlinks to just basenames.
                if "/" not in target:
                    continue

                # Resolve the link target relative to the rootfs.
                resolved_target = osutils.ResolveSymlinkInRoot(
                    full_path, image_test_lib.ROOT_A
                )
                normed_target = os.path.normpath(resolved_target)

                # If the target exists, it's fine.
                if os.path.exists(normed_target):
                    continue

                # Now check the allow list.
                source = "/" + os.path.relpath(full_path, image_test_lib.ROOT_A)
                if not self._SymlinkTargetAllowed(source, target):
                    failures.append((source, target))

        for source, target in failures:
            logging.error("Insecure symlink: %s -> %s", source, target)
        self.assertEqual(0, len(failures))


class PermissionTest(image_test_lib.ImageTestCase):
    """Verify file permissions."""

    def TestNoExecutableInFirmwareFolder(self):
        """Ensure all files in ROOT-A/lib/firmware are not executable.

        Files under ROOT-A/lib/firmware will be allowed in
        "TestImportedSymbolsAreAvailable".
        """
        firmware_path = os.path.join(image_test_lib.ROOT_A, "lib", "firmware")

        success = True
        for root, _, filenames in os.walk(firmware_path):
            for filename in filenames:
                full_name = os.path.join(root, filename)
                # We check symlinks in SymlinkTest, so no need to recheck here.
                if os.path.islink(full_name) or not os.path.isfile(full_name):
                    continue

                st = os.stat(full_name)
                if st.st_mode & 0o111:
                    success = False
                    logging.error(
                        "Executable file not allowed in /lib/firmware: %s.",
                        filename,
                    )

        self.assertTrue(success)


class IntelWifiTest(image_test_lib.ImageTestCase):
    """Verify installation of iwlwifi driver and firmware.

    Intel WiFi chips need a kernel module and a firmware file. Test that they're
    installed correctly, in particular that there's no version mismatch between
    the two or that the firmware file for a particular chip is missing entirely.
    """

    def _FindKernelVersion(self):
        """Detect the version of the kernel used by the image."""
        module_top = os.path.join(image_test_lib.ROOT_A, "lib", "modules")
        if not os.path.isdir(module_top):
            logging.error('Path "%s" is not a directory.', module_top)
            return None

        kernels = os.listdir(module_top)
        if len(kernels) != 1:
            logging.error(
                "Image has %d kernel versions, expected 1.", len(kernels)
            )
            logging.error("Found kernel versions: %s", ", ".join(kernels))
            return None

        return kernels[0]

    def _FindDriverSupportedFirmware(self, kernel):
        """List all the firmware files supported by the driver.

        The iwlwifi driver has the path of the various firmware versions that it
        supports built in. The list of firmware versions is available through
        the 'modinfo' command.

        Args:
            kernel: A string containing the kernel version.

        Returns:
            A list of strings containing the names of all the firmware files
            that can be loaded by the iwlwifi driver.
        """
        # The iwlwifi module lists the firmware files that it can load.
        # Typical output of the 'modinfo' command:
        # iwlwifi-7265-17.ucode
        # iwlwifi-7265D-29.ucode
        # iwlwifi-8000C-36.ucode
        # iwlwifi-8265-36.ucode
        # iwlwifi-9000-pu-b0-jf-b0-46.ucode
        # iwlwifi-9260-th-b0-jf-b0-46.ucode
        try:
            cmd = [
                "modinfo",
                "-F",
                "firmware",
                "-b",
                image_test_lib.ROOT_A,
                "-k",
                kernel,
                "iwlwifi",
            ]
            modinfo = cros_build_lib.run(
                cmd, print_cmd=False, capture_output=True, encoding="utf-8"
            )
        except cros_build_lib.RunCommandError as e:
            # It's not necessarily an error to have enabled the firmware but not
            # the iwlwifi driver (e.g. bringup) -> log a warning, not an error.
            logging.warning("Could not query iwlwifi driver.")
            logging.warning(
                '"%s" returned code %d.', " ".join(cmd), e.returncode
            )
            logging.warning("stdout: %s", e.stdout)
            logging.warning("stderr: %s", e.stderr)
            return []

        return modinfo.stdout.splitlines()

    def _GetLinuxFirmwareIwlwifiFlags(self):
        """Extract 'iwlwifi-*' flags from LINUX_FIRMWARE."""
        linux_firmware = portage_util.PortageqEnvvar(
            "LINUX_FIRMWARE", board=self._board, allow_undefined=True
        )
        if not linux_firmware:
            logging.info("Board %s doesn't use LINUX_FIRMWARE.", self._board)
            return []

        # Look for flags 'iwlwifi-all', 'iwlwifi-9260', 'iwlwifi-QuZ', etc.
        flags = [x for x in linux_firmware.split() if x.startswith("iwlwifi-")]
        if not flags:
            logging.info("Board %s doesn't support iwlwifi.", self._board)
            return []

        logging.info("Expecting the following WiFi chips: %s", ", ".join(flags))
        return flags

    def _GetIwlwifiFirmwareFiles(self):
        """List all the iwlwifi-* files in /lib/firmware."""
        pathname = os.path.join(
            image_test_lib.ROOT_A, "lib", "firmware", "iwlwifi-*"
        )
        return [os.path.basename(x) for x in glob.glob(pathname)]

    def TestIwlwifiFirmwareAndKernelMatch(self):
        """Ensure that the firmware files are supported by the kernel.

        The iwlwifi firmware files expected by the driver must be present in
        /lib/firmware. This will also ensure that there's no version mismatch
        between the driver and the firmware.
        """
        iwlwifi_flags = self._GetLinuxFirmwareIwlwifiFlags()
        if not iwlwifi_flags:
            self.skipTest("Could not find iwlwifi flags.")
        if "iwlwifi-all" in iwlwifi_flags:
            self.skipTest("All firmware files have been installed.")

        # Find the kernel version of the image, necessary to call 'modinfo'
        # later.
        kernel = self._FindKernelVersion()
        if kernel is None:
            self.skipTest("Failed to detect the kernel version.")

        modinfo_files = self._FindDriverSupportedFirmware(kernel)
        if not modinfo_files:
            self.skipTest("Could not find iwlwifi module.")

        iwlwifi_files = self._GetIwlwifiFirmwareFiles()
        # We have at least one iwlwifi-* flag listed in LINUX_FIRMWARE, ensure
        # that at least one firmware file is present.
        self.assertTrue(iwlwifi_files, "No iwlwifi firmware file installed.")

        # Ensure that for every iwlwifi-* flag listed in LINUX_FIRMWARE, the
        # driver has at least one corresponding firmware file listed, and at
        # least one of the firmware files is present on the rootfs.
        for flag in iwlwifi_flags:
            supported_fw = {x for x in modinfo_files if x.startswith(flag)}
            available_fw = {x for x in iwlwifi_files if x.startswith(flag)}
            logging.info(
                'The driver supports the following "%s" files: %s',
                flag,
                ", ".join(supported_fw),
            )
            logging.info(
                'The rootfs provides the following "%s" files: %s',
                flag,
                ", ".join(available_fw),
            )
            self.assertTrue(
                supported_fw & available_fw,
                "Driver/firmware mismatch for %s" % flag,
            )


class DBusServiceTest(image_test_lib.ImageTestCase):
    """Verify installed D-Bus service file contents."""

    def TestDelegationToUpstart(self):
        """Check D-Bus service files for delegation to Upstart.

        crbug.com/1025914: To prevent D-Bus activated services from running
        indefinitely, each D-Bus activated service file should have an
        associated Upstart job that manages the lifecycle of the service.

        The Exec clause can either start with "Exec=/sbin/start(whitespace)"
        (delegate to upstart) or should be "Exec=/sbin/false" (D-Bus service
        activations disabled).
        """
        DBUS_HEADER_RE = re.compile(r"^\[D-BUS Service]$", re.MULTILINE)
        EXEC_CLAUSE_RE = re.compile(
            r"^Exec=(/sbin/start\s|/bin/false)", re.MULTILINE
        )

        dbus_service_path_spec = (
            "%s/usr/share/dbus-1/*services/*.service" % image_test_lib.ROOT_A
        )
        success = True

        for filename in glob.iglob(dbus_service_path_spec):
            file_contents = osutils.ReadFile(filename)
            if DBUS_HEADER_RE.search(
                file_contents
            ) and not EXEC_CLAUSE_RE.search(file_contents):
                success = False
                logging.error(
                    "%s: Add an Upstart script to manage D-Bus activated "
                    "service lifecycle: see crbug.com/1025914.",
                    filename,
                )

        self.assertTrue(success)


class TmpfilesdEntry(NamedTuple):
    """An entry in a tmpfiles.d file."""

    config: str
    type: str
    path: str
    mode: str
    user: str
    group: str
    age: str
    argument: str


class TmpfilesdTest(image_test_lib.ImageTestCase):
    """Verify tmpfiles.d configuration settings."""

    def _parse(self, conf):
        """Parse a tmpfiles.d file and yield each entry."""
        for line in conf.read_text("utf-8").splitlines():
            line = line.strip().split("#", 1)[0]
            if not line:
                continue

            line = line.split()
            yield TmpfilesdEntry(conf, *(line + (["-"] * 5))[0:7])

    def _iter_tmpfiles_d(self):
        """Yield every tmpfiles.d entry in the rootfs."""
        root = Path(image_test_lib.ROOT_A)
        etc_tmpfiles_d = root / "etc" / "tmpfiles.d"
        usr_tmpfiles_d = root / "usr" / "lib" / "tmpfiles.d"
        for tmpfiles_d in (etc_tmpfiles_d, usr_tmpfiles_d):
            for conf in tmpfiles_d.glob("*.conf"):
                yield from self._parse(conf)

    def TestAccounts(self):
        """Make sure every user & group actually exist.

        If the accounts don't exist at runtime, tmpfiles.d likes to blow up.
        Numeric entries are allowed to support ARC++ shared mounts.
        """
        root = Path(image_test_lib.ROOT_A)
        etc_passwd = root / "etc" / "passwd"
        etc_group = root / "etc" / "group"
        valid_users = set(
            x.split(":", 1)[0]
            for x in etc_passwd.read_text("utf-8").splitlines()
        )
        valid_users.add("-")
        valid_groups = set(
            x.split(":", 1)[0]
            for x in etc_group.read_text("utf-8").splitlines()
        )
        valid_groups.add("-")

        success = True
        for entry in self._iter_tmpfiles_d():
            if not entry.user.isnumeric() and entry.user not in valid_users:
                logging.error("%s: unknown user", entry)
                success = False
            if not entry.group.isnumeric() and entry.group not in valid_groups:
                logging.error("%s: unknown group", entry)
                success = False

        self.assertTrue(success)


class FactoryScriptTest(image_test_lib.ImageTestCase):
    """Verifies the image can be loaded by the factory scripts.

    Some factory scripts parse files in the image. This test aims to detect if
    there's any format change in the image that breaks the factory scripts.

    Please contact
    https://chromium.googlesource.com/chromiumos/platform/factory/+/main/DIR_METADATA
    or
    chromeos-factoy-eng@google.com
    if this test fails in CQ.
    """

    FINALIZE_BUNDLE = os.path.join(
        constants.SOURCE_ROOT, "src/platform/factory/bin/finalize_bundle"
    )

    def TestFinalizeBundle_ExtractFirmwareInfo(self):
        root = Path(image_test_lib.ROOT_A)

        # Skip the test for:
        # 1. The project is too old that doesn't have cros-config
        # 2. The project is too new that its firmware is not ready yet
        if self._board and not portage_util.PortageqHasVersion(
            "chromeos-base/chromeos-config", self._board
        ):
            logging.info(
                "Board %s doesn't have chromeos-config. Skip the test.",
                self._board,
            )
            return

        fw_update = root / "usr/sbin/chromeos-firmwareupdate"
        if not fw_update.exists():
            logging.info(
                "The image doesn't have firmware updater. Skip the test."
            )
            return

        cmd = [
            self.FINALIZE_BUNDLE,
            "fake_manifest.yaml",
            "--extract-firmware-info",
            root,
        ]
        cros_build_lib.run(cmd)
