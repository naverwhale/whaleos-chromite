# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for remoteexec_lib.py"""

from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import remoteexec_lib


class TestLogArchiver(cros_test_lib.RunCommandTempDirTestCase):
    """Tests for remoteexec_lib."""

    def setUp(self):
        self.src_dir = self.tempdir / "src_dir"
        self.dest_dir = self.tempdir / "dest_dir"

        osutils.SafeMakedirs(self.src_dir)
        osutils.SafeMakedirs(self.dest_dir)

        self.archiver = remoteexec_lib.LogsArchiver(self.dest_dir)
        self.archiver.src_dir_for_testing = self.src_dir

    def _create_file(self, package_name: str, filename: str):
        osutils.WriteFile(
            self.src_dir / f"reclient-{package_name}" / filename,
            f"Package: {package_name}\nFile: {filename}",
            makedirs=True,
        )

    def testArchiveFiles(self):
        """Test LogArchiver.Archive() method."""
        self._create_file("chromeos-chrome", "test.INFO.log")
        self._create_file("chromeos-chrome", "test.INFO")
        self._create_file("chromeos-chrome", "reproxy_test.INFO")
        self._create_file("chromeos-chrome", "reproxy_test.rrpl")

        log_files = self.archiver.archive()

        self.assertEqual(
            log_files,
            [
                "reclient-chromeos-chrome/test.INFO.log.gz",
                "reclient-chromeos-chrome/reproxy_test.INFO.gz",
                "reclient-chromeos-chrome/reproxy_test.rrpl.gz",
            ],
        )
