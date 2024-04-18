# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""An implementation of the RemoteexecConfig proto interface."""

import logging
from pathlib import Path
from typing import List

from chromite.lib import cros_build_lib
from chromite.lib import osutils


# Synced with "log_dir" and "proxy_log_dir" in ./sdk/reclient_cfgs/reproxy.cfg
_REMOTEEXEC_LOG_BASE_DIR = Path("/tmp")
_REMOTEEXEC_LOG_DIRNAME_PATTERN = "reclient-*"

_REMOTEEXEC_LOG_FILE_PATTERN = (
    "*.INFO.*",
    "reproxy_*.INFO",
    "*.rrpl",
)


class LogsArchiver:
    """Manages archiving remoteexec log files."""

    def __init__(self, dest_dir: Path):
        """Initializes the archiver.

        Args:
            dest_dir: path to the target directory to which logs are written.
        """
        self.src_dir_for_testing = None
        self._dest_base_dir = dest_dir
        osutils.SafeMakedirs(self._dest_base_dir)

    def archive(self) -> List[str]:
        """Archives remoteexec log files.

        Returns:
            A list of compressed log file paths.
        """

        log_dir_pattern = self.src_dir_for_testing or _REMOTEEXEC_LOG_BASE_DIR
        log_dirs = sorted(log_dir_pattern.glob(_REMOTEEXEC_LOG_DIRNAME_PATTERN))

        archived_log_files = []
        for log_dir in log_dirs:
            logging.info("Processing log dir: %s", log_dir)

            for pattern in _REMOTEEXEC_LOG_FILE_PATTERN:
                archived_log_files += self._archive_files(log_dir, pattern)

        return archived_log_files

    def _archive_files(self, directory: Path, pattern: str) -> List[Path]:
        """Archives files matched with pattern, with gzip'ing.

        Args:
            directory: directory of the files.
            pattern: matching path pattern (eg. "*.INFO").

        Returns:
            A list of compressed log file paths.
        """
        # Find files matched with the |pattern| in |directory|. Sort for
        # stabilization.
        paths = sorted(directory.glob(pattern))
        if not paths:
            logging.warning("No glob files matched with %s", pattern)

        result = []
        for path in paths:
            archived_filename = f"{path.name}.gz"
            log_label = f"{directory.name}/{archived_filename}"
            logging.info("Compressing %s", log_label)

            dest_filepath = (
                self._dest_base_dir / directory.name / archived_filename
            )
            osutils.SafeMakedirs(dest_filepath.parent)
            cros_build_lib.CompressFile(path, dest_filepath)

            result.append(log_label)

        return result
