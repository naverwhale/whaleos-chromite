# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for goma_lib.py"""

import datetime
import getpass
import gzip
import json
import os
from pathlib import Path
import time

from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import goma_lib
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.utils import hostname_util


class GomaTest(cros_test_lib.TempDirTestCase, cros_test_lib.RunCommandTestCase):
    """Tests for the Goma object."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        self.goma_dir = self.tempdir / "goma"
        self.chroot_dir = self.tempdir / "chroot"
        self.out_dir = self.tempdir / "out"
        self.chroot_tmp = Path(
            path_util.FromChrootPath(
                "/tmp",
                chroot_path=Path(self.chroot_dir),
                out_path=Path(self.out_dir),
            )
        )
        self.log_dir = self.chroot_tmp / "log_dir"

        osutils.SafeMakedirs(self.goma_dir)
        osutils.SafeMakedirs(self.chroot_tmp)

    def testExtraEnvCustomChroot(self):
        """Test the chroot env building with a custom chroot location."""
        stats_filename = "stats_filename"
        counterz_filename = "counterz_filename"

        goma = goma_lib.Goma(
            self.goma_dir,
            chroot_dir=self.chroot_dir,
            out_dir=self.out_dir,
            log_dir=self.log_dir,
            stats_filename=stats_filename,
            counterz_filename=counterz_filename,
        )

        env = goma.GetExtraEnv()
        chroot_env = goma.GetChrootExtraEnv()

        # Make sure the chroot paths got translated.
        self.assertStartsWith(chroot_env["GOMA_TMP_DIR"], "/tmp")
        self.assertStartsWith(chroot_env["GLOG_log_dir"], "/tmp/log_dir")
        # Make sure the non-chroot paths didn't get translated.
        self.assertStartsWith(env["GOMA_TMP_DIR"], str(self.chroot_tmp))
        self.assertStartsWith(env["GLOG_log_dir"], str(self.log_dir))
        # Make sure they're based on the same path.
        self.assertEndsWith(env["GOMA_TMP_DIR"], chroot_env["GOMA_TMP_DIR"])
        self.assertEndsWith(env["GLOG_log_dir"], chroot_env["GLOG_log_dir"])
        # Make sure the stats file gets set correctly.
        self.assertStartsWith(env["GOMA_DUMP_STATS_FILE"], str(self.log_dir))
        self.assertEndsWith(env["GOMA_DUMP_STATS_FILE"], stats_filename)
        self.assertStartsWith(
            chroot_env["GOMA_DUMP_STATS_FILE"], "/tmp/log_dir"
        )
        self.assertEndsWith(chroot_env["GOMA_DUMP_STATS_FILE"], stats_filename)
        self.assertEndsWith(
            env["GOMA_DUMP_STATS_FILE"], chroot_env["GOMA_DUMP_STATS_FILE"]
        )
        # Make sure the counterz file gets set correctly.
        self.assertStartsWith(env["GOMA_DUMP_COUNTERZ_FILE"], str(self.log_dir))
        self.assertEndsWith(env["GOMA_DUMP_COUNTERZ_FILE"], counterz_filename)
        self.assertStartsWith(
            chroot_env["GOMA_DUMP_COUNTERZ_FILE"], "/tmp/log_dir"
        )
        self.assertEndsWith(
            chroot_env["GOMA_DUMP_COUNTERZ_FILE"], counterz_filename
        )
        self.assertEndsWith(
            env["GOMA_DUMP_COUNTERZ_FILE"],
            chroot_env["GOMA_DUMP_COUNTERZ_FILE"],
        )

    def testExtraEnvGomaApproach(self):
        """Test the chroot env building with a goma approach."""
        goma_approach = goma_lib.GomaApproach("foo", "bar", True)
        goma = goma_lib.Goma(
            self.goma_dir,
            chroot_dir=self.chroot_dir,
            out_dir=self.out_dir,
            goma_approach=goma_approach,
        )
        env = goma.GetExtraEnv()

        # Make sure the extra environment specified by goma_approach is present.
        self.assertEqual(env["GOMA_RPC_EXTRA_PARAMS"], "foo")
        self.assertEqual(env["GOMA_SERVER_HOST"], "bar")
        self.assertEqual(env["GOMA_ARBITRARY_TOOLCHAIN_SUPPORT"], "true")

    def testInvalidArg(self):
        """Test invalid Goma input arguments."""
        with self.assertRaises(ValueError):
            goma_lib.Goma(Path("some/path"))
        with self.assertRaises(ValueError):
            goma_lib.Goma(self.goma_dir, Path("some/path/goma_client.json"))

    def testCommand(self):
        """Test Goma instance command interface."""
        goma_ctl = self.goma_dir / "goma_ctl.py"

        goma = goma_lib.Goma(
            self.goma_dir,
            goma_tmp_dir=None,
            chroot_dir=self.chroot_dir,
            out_dir=self.out_dir,
        )
        goma.Start()
        self.assertCommandContains([goma_ctl, "start"])
        goma.Restart()
        self.assertCommandContains([goma_ctl, "restart"])
        goma.Stop()
        self.assertCommandContains([goma_ctl, "stop"])


class TestLogsArchiver(cros_test_lib.MockTempDirTestCase):
    """Tests for goma_lib.LogsArchiver."""

    def setUp(self):
        self.goma_log_dir = os.path.join(self.tempdir, "goma_log_dir")
        osutils.SafeMakedirs(self.goma_log_dir)
        self.dest_dir = os.path.join(self.tempdir, "destination_dir")
        osutils.SafeMakedirs(self.dest_dir)

    def _CreateFile(self, name: str):
        """Creates a basic file, such as a stats or counterz file.

        Args:
            name: Filename
        """
        osutils.WriteFile(
            os.path.join(self.goma_log_dir, name), "File: " + name
        )

    def _CreateLogFile(self, name: str, timestamp: datetime.datetime):
        """Creates a log file for testing.

        Args:
            name: Log file name.
            timestamp: timestamp that is written to the file.
        """
        path = os.path.join(
            self.goma_log_dir,
            "%s.host.log.INFO.%s"
            % (name, timestamp.strftime("%Y%m%d-%H%M%S.%f")),
        )
        osutils.WriteFile(
            path, timestamp.strftime("Log file created at: %Y/%m/%d %H:%M:%S")
        )

    def testArchive(self):
        """Test successful archive of goma logs without stats/counterz."""
        self._CreateLogFile(
            "compiler_proxy", datetime.datetime(2017, 4, 26, 12, 0, 0)
        )
        self._CreateLogFile(
            "compiler_proxy-subproc", datetime.datetime(2017, 4, 26, 12, 0, 0)
        )
        self._CreateLogFile("gomacc", datetime.datetime(2017, 4, 26, 12, 1, 0))
        self._CreateLogFile("gomacc", datetime.datetime(2017, 4, 26, 12, 2, 0))

        archiver = goma_lib.LogsArchiver(
            self.goma_log_dir, dest_dir=self.dest_dir
        )
        archiver_tuple = archiver.Archive()

        # Verify that no stats/counterz was returned in the tuple.
        self.assertFalse(archiver_tuple.counterz_file)
        self.assertFalse(archiver_tuple.stats_file)

        archived_files = os.listdir(self.dest_dir)

        # Verify that the list of files returned matched what we find in the
        # dest_dir.
        self.assertCountEqual(archiver_tuple.log_files, archived_files)

        self.assertCountEqual(
            archived_files,
            [
                "compiler_proxy.host.log.INFO.20170426-120000.000000.gz",
                "gomacc.host.log.INFO.20170426-120100.000000.tar.gz",
                "compiler_proxy-subproc.host.log.INFO."
                "20170426-120000.000000.gz",
            ],
        )

    def testArchiveWithStatsAndCounterz(self):
        """Test successful archive of goma logs with stats and counterz."""
        self._CreateLogFile(
            "compiler_proxy", datetime.datetime(2017, 4, 26, 12, 0, 0)
        )
        self._CreateLogFile(
            "compiler_proxy-subproc", datetime.datetime(2017, 4, 26, 12, 0, 0)
        )
        self._CreateLogFile("gomacc", datetime.datetime(2017, 4, 26, 12, 1, 0))
        self._CreateLogFile("gomacc", datetime.datetime(2017, 4, 26, 12, 2, 0))
        self._CreateFile("stats.binaryproto")
        self._CreateFile("counterz.binaryproto")

        archiver = goma_lib.LogsArchiver(
            self.goma_log_dir,
            dest_dir=self.dest_dir,
            stats_file="stats.binaryproto",
            counterz_file="counterz.binaryproto",
        )
        archiver_tuple = archiver.Archive()

        self.assertCountEqual(
            archiver_tuple.log_files,
            [
                "compiler_proxy.host.log.INFO.20170426-120000.000000.gz",
                "gomacc.host.log.INFO.20170426-120100.000000.tar.gz",
                "compiler_proxy-subproc.host.log.INFO."
                "20170426-120000.000000.gz",
            ],
        )
        self.assertEqual(archiver_tuple.stats_file, "stats.binaryproto")
        self.assertEqual(archiver_tuple.counterz_file, "counterz.binaryproto")

    def testArchiveWithStatsAndMissingCounterz(self):
        """Test successful archive of goma logs with stats and counterz."""
        self._CreateLogFile(
            "compiler_proxy", datetime.datetime(2017, 4, 26, 12, 0, 0)
        )
        self._CreateLogFile(
            "compiler_proxy-subproc", datetime.datetime(2017, 4, 26, 12, 0, 0)
        )
        self._CreateLogFile("gomacc", datetime.datetime(2017, 4, 26, 12, 1, 0))
        self._CreateLogFile("gomacc", datetime.datetime(2017, 4, 26, 12, 2, 0))
        self._CreateFile("stats.binaryproto")

        archiver = goma_lib.LogsArchiver(
            self.goma_log_dir,
            dest_dir=self.dest_dir,
            stats_file="stats.binaryproto",
            counterz_file="counterz.binaryproto",
        )
        # Because counterz.binaryproto does not exist, verify it is not returned
        # as one of the files archived.
        archiver_tuple = archiver.Archive()
        self.assertFalse(archiver_tuple.counterz_file)
        self.assertEqual(archiver_tuple.stats_file, "stats.binaryproto")
        self.assertCountEqual(
            archiver_tuple.log_files,
            [
                "compiler_proxy.host.log.INFO.20170426-120000.000000.gz",
                "gomacc.host.log.INFO.20170426-120100.000000.tar.gz",
                "compiler_proxy-subproc.host.log.INFO."
                "20170426-120000.000000.gz",
            ],
        )

    def testNinjaLogArchive(self):
        """Test successful archive of ninja logs."""
        self._CreateLogFile(
            "compiler_proxy", datetime.datetime(2017, 8, 21, 12, 0, 0)
        )
        self._CreateLogFile(
            "compiler_proxy-subproc", datetime.datetime(2017, 8, 21, 12, 0, 0)
        )

        ninja_log_path = os.path.join(self.goma_log_dir, "ninja_log")
        osutils.WriteFile(ninja_log_path, "Ninja Log Content\n")
        timestamp = datetime.datetime(2017, 8, 21, 12, 0, 0)
        mtime = time.mktime(timestamp.timetuple())
        os.utime(ninja_log_path, ((time.time(), mtime)))

        osutils.WriteFile(
            os.path.join(self.goma_log_dir, "ninja_command"), "ninja_command"
        )
        osutils.WriteFile(
            os.path.join(self.goma_log_dir, "ninja_cwd"), "ninja_cwd"
        )
        osutils.WriteFile(
            os.path.join(self.goma_log_dir, "ninja_env"),
            "key1=value1\0key2=value2\0",
        )
        osutils.WriteFile(os.path.join(self.goma_log_dir, "ninja_exit"), "0")

        archiver = goma_lib.LogsArchiver(
            self.goma_log_dir, dest_dir=self.dest_dir
        )
        archived_tuple = archiver.Archive()

        username = getpass.getuser()
        pid = os.getpid()
        hostname = hostname_util.get_host_name()
        ninjalog_filename = "ninja_log.%s.%s.20170821-120000.%d.gz" % (
            username,
            hostname,
            pid,
        )
        # Verify the archived files in the dest_dir
        archived_files = os.listdir(self.dest_dir)
        self.assertCountEqual(
            archived_files,
            [
                ninjalog_filename,
                "compiler_proxy-subproc.host.log.INFO."
                "20170821-120000.000000.gz",
                "compiler_proxy.host.log.INFO.20170821-120000.000000.gz",
            ],
        )
        # Verify the archived_tuple result.
        self.assertFalse(archived_tuple.counterz_file)
        self.assertFalse(archived_tuple.stats_file)
        self.assertCountEqual(
            archived_tuple.log_files,
            [
                "compiler_proxy.host.log.INFO.20170821-120000.000000.gz",
                "compiler_proxy-subproc.host.log.INFO."
                "20170821-120000.000000.gz",
                ninjalog_filename,
            ],
        )

        # Verify content of ninja_log file.
        ninjalog_path = os.path.join(self.dest_dir, ninjalog_filename)

        with gzip.open(ninjalog_path, "rt", encoding="utf-8") as gzip_file:
            ninja_log_content = gzip_file.read()

        content, eof, metadata_json = ninja_log_content.split("\n", 3)
        self.assertEqual("Ninja Log Content", content)
        self.assertEqual("# end of ninja log", eof)
        metadata = json.loads(metadata_json)
        self.assertEqual(
            metadata,
            {
                "platform": "chromeos",
                "cmdline": ["ninja_command"],
                "cwd": "ninja_cwd",
                "exit": 0,
                "env": {"key1": "value1", "key2": "value2"},
                "compiler_proxy_info": (
                    "compiler_proxy.host.log.INFO.20170821-120000.000000"
                ),
            },
        )
