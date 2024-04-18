# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to use goma and archive goma logs."""

import datetime
import getpass
import glob
import json
import logging
import os
from pathlib import Path
import shlex
import shutil
import tempfile
from typing import List, NamedTuple, Optional, Union

from chromite.cbuildbot import goma_util
from chromite.lib import chroot_lib
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.utils import hostname_util


class GomaApproach(NamedTuple):
    """GomaApproach server and rpc details."""

    rpc_extra_params: str
    server_host: str
    arbitrary_toolchain_support: bool


class ArchivedFiles(NamedTuple):
    """Goma files to be archived."""

    stats_file: Optional[str]
    counterz_file: Optional[str]
    log_files: List[str]


class SpecifiedFileMissingError(Exception):
    """Error occurred when running LogsArchiver."""


# TODO(crbug.com/1035114) Refactor.
class Goma:
    """Interface to use goma on bots."""

    # Default environment variables to use goma.
    _DEFAULT_ENV_VARS = {
        # Set MAX_COMPILER_DISABLED_TASKS to let goma enter Burst mode, if
        # there are too many local fallback failures. In the Burst mode, goma
        # tries to use CPU cores as many as possible. Note that, by default,
        # goma runs only a few local fallback tasks in parallel at once.
        # The value is the threshold of the number of local fallback failures
        # to enter the mode.
        # Note that 30 is just heuristically chosen by discussion with goma
        # team.
        #
        # Specifically, this is short-term workaround of the case that all
        # compile processes get local fallback. Otherwise, because goma uses
        # only several processes for local fallback by default, it causes
        # significant slow down of the build.
        # Practically, this happens when toolchain is updated in repository,
        # but prebuilt package is not yet ready. (cf. crbug.com/728971)
        "GOMA_MAX_COMPILER_DISABLED_TASKS": "30",
        # Disable goma soft stickiness.
        # Goma was historically using `soft stickiness cookie` so that uploaded
        # file cache is available as much as possible. However, such sticky
        # requests are causing unbalanced server load, and the disadvantage of
        # the unbalance cannot be negligible now. According to chrome's
        # experiment, the disadvantage of disabling soft stickiness is
        # negligible, and achieving balanced server load will have more
        # advantage for entire build. (cf. crbug.com/730962)
        # TODO(shinyak): This will be removed after crbug.com/730962 is
        #   resolved.
        "GOMA_BACKEND_SOFT_STICKINESS": "false",
        # Enable DepsCache. DepsCache is a cache that holds a file list that
        # compiler_proxy sends to goma server for each compile. This can
        # reduces a lot of I/O and calculation.
        # This is the base file name under GOMA_CACHE_DIR.
        "GOMA_DEPS_CACHE_FILE": "goma.deps",
        # Only run one command in parallel per core.
        #
        # TODO(crbug.com/998076): Increase if Goma fork issue is fixed.
        "NINJA_CORE_MULTIPLIER": "1",
    }

    def __init__(
        self,
        goma_dir: Union[str, os.PathLike],
        goma_tmp_dir: Optional[Union[str, os.PathLike]] = None,
        stage_name: Optional[str] = None,
        chromeos_goma_dir: Optional[Union[str, os.PathLike]] = None,
        chroot_dir: Optional[Union[str, os.PathLike]] = None,
        out_dir: Optional[os.PathLike] = None,
        goma_approach: Optional[GomaApproach] = None,
        log_dir: Optional[Union[str, os.PathLike]] = None,
        stats_filename: Optional[Union[str, os.PathLike]] = None,
        counterz_filename: Optional[Union[str, os.PathLike]] = None,
    ):
        """Initializes Goma instance.

        This ensures that |self.goma_log_dir| directory exists (if missing,
        creates it).

        Args:
            goma_dir: Path to the Goma client used for simplechrome (outside the
                chroot).
            goma_tmp_dir: Path to the GOMA_TMP_DIR to be passed to goma
                programs. If given, it is used. If not given, creates a
                directory under /tmp in the chroot, expecting that the directory
                is removed in the next run's clean up phase on bots.
            stage_name: optional name of the currently running stage. E.g.
                "build_packages" or "test_simple_chrome_workflow". If this is
                set deps cache is enabled.
            chromeos_goma_dir: Path to the Goma client used for build package.
                path should be represented as outside the chroot. If None,
                goma_dir will be used instead.
            chroot_dir: The base chroot path to use when the chroot path is not
                at the default location.
            out_dir: The base out path to use when the out path is not at the
                default location.
            goma_approach: Indicates some extra environment variables to set
                when testing alternative goma approaches.
            log_dir: Allows explicitly setting the log directory. Used for the
                Build API for extracting the logs afterwords. Should be the log
                directory inside the chroot, based on the chroot path when
                outside the chroot.
            stats_filename: The name of the file to use for the
                GOMA_DUMP_STATS_FILE setting. The file will be created in the
                log directory.
            counterz_filename: The name of the file to use for the
                GOMA_DUMP_COUNTERZ_FILE setting. The file will be created in the
                log directory.

        Raises:
            ValueError if 1) |goma_dir| does not point to a directory, or 2)
            if |goma_tmp_dir| is given, but it does not point to a directory.
        """
        # Sanity checks of given paths.
        goma_dir = Path(goma_dir)

        if goma_tmp_dir:
            goma_tmp_dir = Path(goma_tmp_dir)

        if chromeos_goma_dir:
            chromeos_goma_dir = Path(chromeos_goma_dir)

        if chroot_dir:
            chroot_dir = Path(chroot_dir)

        if log_dir:
            log_dir = Path(log_dir)

        if stats_filename:
            stats_filename = Path(stats_filename)

        if counterz_filename:
            counterz_filename = Path(counterz_filename)

        if not goma_dir.is_dir():
            raise ValueError(f"goma_dir does not point a directory: {goma_dir}")

        # If goma_tmp_dir is provided, it must be an existing directory.
        if goma_tmp_dir and not goma_tmp_dir.is_dir():
            raise ValueError(
                f"GOMA_TMP_DIR does not point a directory: {goma_tmp_dir}"
            )

        chroot = chroot_lib.Chroot(path=chroot_dir, out_path=out_dir)
        self.linux_goma_dir = goma_dir
        self.chromeos_goma_dir = chromeos_goma_dir
        self.goma_approach = goma_approach
        # If Goma dir for ChromeOS SDK does not set, fallback to use goma_dir.
        if self.chromeos_goma_dir is None:
            self.chromeos_goma_dir = goma_dir
        # Sanity checks of given paths.
        if not self.chromeos_goma_dir.is_dir():
            raise ValueError(
                "chromeos_goma_dir does not point a directory: "
                f"{self.chromeos_goma_dir}"
            )

        if stage_name:
            self.goma_cache = goma_dir / "goma_cache" / stage_name
            osutils.SafeMakedirs(self.goma_cache)
        else:
            self.goma_cache = None

        if goma_tmp_dir is None:
            chroot_tmp = chroot.full_path("/tmp")

            # If |goma_tmp_dir| is not given, create GOMA_TMP_DIR (goma
            # compiler_proxy's working directory), and its log directory.
            # Create unique directory by mkdtemp under chroot's /tmp.
            # Expect this directory is removed in next run's clean up phase.
            goma_tmp_dir = Path(
                tempfile.mkdtemp(prefix="goma_tmp_dir.", dir=chroot_tmp)
            )
        self.goma_tmp_dir = goma_tmp_dir

        self.chroot_goma_tmp_dir = chroot.chroot_path(self.goma_tmp_dir)

        self._log_dir = log_dir
        # Create log directory if not exist.
        if not self.goma_log_dir.is_dir():
            osutils.SafeMakedirs(self.goma_log_dir)

        self._stats_file = None
        self._chroot_stats_file = None
        self._counterz_file = None
        self._chroot_counterz_file = None
        if stats_filename:
            self._stats_file = self.goma_log_dir / stats_filename
        if counterz_filename:
            self._counterz_file = self.goma_log_dir / counterz_filename

        self.chroot_goma_log_dir = chroot.chroot_path(self.goma_log_dir)
        if self._stats_file:
            self._chroot_stats_file = chroot.chroot_path(self._stats_file)
        if self._counterz_file:
            self._chroot_counterz_file = chroot.chroot_path(self._counterz_file)

    @property
    def goma_log_dir(self):
        """Path to goma's log directory."""
        return self._log_dir or self.goma_tmp_dir / "log_dir"

    def GetExtraEnv(self):
        """Extra env vars set to use goma."""
        result = dict(
            Goma._DEFAULT_ENV_VARS,
            GOMA_DIR=str(self.linux_goma_dir),
            GOMA_TMP_DIR=str(self.goma_tmp_dir),
            GLOG_log_dir=str(self.goma_log_dir),
        )

        self._AddCommonExtraEnv(result)

        if hostname_util.host_is_ci_builder():
            result["GOMA_GCE_SERVICE_ACCOUNT"] = "default"
            result["GCE_METADATA_HOST"] = os.environ.get(
                "GCE_METADATA_HOST", ""
            )

        if self.goma_cache:
            result["GOMA_CACHE_DIR"] = str(self.goma_cache)

        if self._stats_file:
            result["GOMA_DUMP_STATS_FILE"] = str(self._stats_file)
        if self._counterz_file:
            result["GOMA_DUMP_COUNTERZ_FILE"] = str(self._counterz_file)
            result["GOMA_ENABLE_COUNTERZ"] = "true"

        return result

    def GetChrootExtraEnv(self):
        """Extra env vars set to use goma inside chroot."""
        # Note: GOMA_DIR in chroot is hardcoded.
        # Please see also enter_chroot.sh.
        goma_dir = Path.home() / "goma"
        result = dict(
            Goma._DEFAULT_ENV_VARS,
            GOMA_DIR=str(goma_dir),
            GOMA_TMP_DIR=str(self.chroot_goma_tmp_dir),
            GLOG_log_dir=str(self.chroot_goma_log_dir),
        )

        self._AddCommonExtraEnv(result)

        if hostname_util.host_is_ci_builder():
            result["GOMA_GCE_SERVICE_ACCOUNT"] = "default"

        if self.goma_cache:
            result["GOMA_CACHE_DIR"] = str(
                goma_dir / self.goma_cache.relative_to(self.chromeos_goma_dir)
            )

        if self._chroot_stats_file:
            result["GOMA_DUMP_STATS_FILE"] = str(self._chroot_stats_file)
        if self._chroot_counterz_file:
            result["GOMA_DUMP_COUNTERZ_FILE"] = str(self._chroot_counterz_file)
            result["GOMA_ENABLE_COUNTERZ"] = "true"

        return result

    def _AddCommonExtraEnv(self, result):
        """Sets extra env vars to use goma common to in / out chroot."""
        if self.goma_approach:
            result[
                "GOMA_RPC_EXTRA_PARAMS"
            ] = self.goma_approach.rpc_extra_params
            result["GOMA_SERVER_HOST"] = self.goma_approach.server_host
            result["GOMA_ARBITRARY_TOOLCHAIN_SUPPORT"] = (
                "true"
                if self.goma_approach.arbitrary_toolchain_support
                else "false"
            )

    def _RunGomaCtl(self, command):
        goma_ctl = self.linux_goma_dir / "goma_ctl.py"
        cros_build_lib.run(
            ["python3", goma_ctl, command], extra_env=self.GetExtraEnv()
        )

    def Start(self):
        """Starts goma compiler proxy."""
        self._RunGomaCtl("start")

    def Restart(self):
        """Restarts goma compiler proxy."""
        self._RunGomaCtl("restart")

    def Stop(self):
        """Stops goma compiler proxy."""
        self._RunGomaCtl("stop")

    def UploadLogs(self, cbb_config_name):
        """Uploads INFO files related to goma.

        Args:
            cbb_config_name: name of cbb_config.

        Returns:
            URL to the compiler_proxy log visualizer. None if unavailable.
        """
        # TODO(rchandrasekar): The only client that uses UploadLogs is
        #   cbuildbot. Once it is removed, assess if we need to use LogsArchiver
        #   instead or remove this interface.
        uploader = goma_util.GomaLogUploader(
            self.goma_log_dir, cbb_config_name=cbb_config_name
        )
        return uploader.Upload()


class LogsArchiver:
    """Manages archiving goma log files.

    The LogsArchiver was migrated from GomaLogUploader in
    cbuildbot/goma_util.py. Unlike the GomaLogUploader, it does not interact
    with GoogleStorage at all. Instead, it copies Goma files to a
    client-specified archive directory.
    """

    def __init__(self, log_dir, dest_dir, stats_file=None, counterz_file=None):
        """Initializes the archiver.

        Args:
            log_dir: path to the directory containing goma's INFO log files.
            dest_dir: path to the target directory to which logs are written.
            stats_file: name of stats file in the log_dir.
            counterz_file: name of the counterz file in the log dir.
        """
        self._log_dir = log_dir
        self._stats_file = stats_file
        self._counterz_file = counterz_file
        self._dest_dir = dest_dir
        # Ensure destination dir exists.
        osutils.SafeMakedirs(self._dest_dir)

    def Archive(self):
        """Archives goma log files, stats file, and counterz file to dest_dir.

        Returns:
            ArchivedFiles named tuple, which includes stats_file, counterz_file,
            and list of log files. All files in the tuple were copied to
            dest_dir.
        """
        archived_log_files = []
        archived_stats_file = None
        archived_counterz_file = None
        # Find log file names containing compiler_proxy-subproc.INFO.
        # _ArchiveInfoFiles returns a list of tuples of (info_file_path,
        # archived_file_name). We expect only 1 to be found, and add the
        # filename for that tuple to archived_log_files.
        compiler_proxy_subproc_paths = self._ArchiveInfoFiles(
            "compiler_proxy-subproc"
        )
        if len(compiler_proxy_subproc_paths) != 1:
            logging.warning(
                "Unexpected compiler_proxy-subproc INFO files: %r",
                compiler_proxy_subproc_paths,
            )
        else:
            archived_log_files.append(compiler_proxy_subproc_paths[0][1])

        # Find log file names containing compiler_proxy.INFO.
        # _ArchiveInfoFiles returns a list of tuples of (info_file_path,
        # archived_file_name). We expect only 1 to be found, and then need
        # to use the first tuple value of the list of 1 for the full path, and
        # the filename of the tuple is added to archived_log_files.
        compiler_proxy_path = None
        compiler_proxy_paths = self._ArchiveInfoFiles("compiler_proxy")
        if len(compiler_proxy_paths) != 1:
            logging.warning(
                "Unexpected compiler_proxy INFO files: %r", compiler_proxy_paths
            )
        else:
            compiler_proxy_path = compiler_proxy_paths[0][0]
            archived_log_files.append(compiler_proxy_paths[0][1])

        gomacc_info_file = self._ArchiveGomaccInfoFiles()
        if gomacc_info_file:
            archived_log_files.append(gomacc_info_file)

        archived_ninja_log_filename = self._ArchiveNinjaLog(compiler_proxy_path)
        if archived_ninja_log_filename:
            archived_log_files.append(archived_ninja_log_filename)

        # Copy stats file and counterz file if they are specified.
        if self._counterz_file:
            archived_counterz_file = self._CopyExpectedGomaFile(
                self._counterz_file
            )
        if self._stats_file:
            archived_stats_file = self._CopyExpectedGomaFile(self._stats_file)
        return ArchivedFiles(
            archived_stats_file, archived_counterz_file, archived_log_files
        )

    def _CopyExpectedGomaFile(self, filename: str) -> Optional[str]:
        """Copies expected goma files (stats, counterz).

        Args:
            filename: File to copy.

        Returns:
            The filename on success, None on error.
        """
        file_path = os.path.join(self._log_dir, filename)
        if not os.path.isfile(file_path):
            logging.warning(
                "Goma expected file specified, not found %s", file_path
            )
            return None
        else:
            dest_path = os.path.join(self._dest_dir, filename)
            logging.info(
                "Copying Goma file from %s to %s", file_path, dest_path
            )
            shutil.copyfile(file_path, dest_path)
            return filename

    def _ArchiveInfoFiles(self, pattern):
        """Archives INFO files matched with pattern, with gzip'ing.

        Args:
            pattern: matching path pattern.

        Returns:
            A list of tuples of (info_file_path, archived_file_name).
        """
        # Find files matched with the pattern in |log_dir|. Sort for
        # stabilization.
        paths = sorted(
            glob.glob(os.path.join(self._log_dir, "%s.*.INFO.*" % pattern))
        )
        if not paths:
            logging.warning("No glog files matched with: %s", pattern)

        result = []
        for path in paths:
            logging.info("Compressing %s", path)
            archived_filename = os.path.basename(path) + ".gz"
            dest_filepath = os.path.join(self._dest_dir, archived_filename)
            cros_build_lib.CompressFile(path, dest_filepath)
            result.append((path, archived_filename))
        return result

    def _ArchiveGomaccInfoFiles(self):
        """Archives gomacc INFO files, with gzip'ing.

        Returns:
            Archived file path. If failed, None.
        """

        # Since the number of gomacc logs can be large, we'd like to compress
        # them. Otherwise, archive will take long (> 10 mins). Each gomacc logs
        # file size must be small (around 4KB).

        # Find files matched with the pattern in |log_dir|.
        # The paths were themselves used as the inputs for the create
        # tarball, but there can be too many of them. As long as we have
        # files we'll just tar up the entire directory.
        gomacc_paths = glob.glob(os.path.join(self._log_dir, "gomacc.*.INFO.*"))
        if not gomacc_paths:
            # gomacc logs won't be made every time.
            # Only when goma compiler_proxy has
            # crashed. So it's usual gomacc logs are not found.
            logging.info("No gomacc logs found")
            return None

        tarball_name = os.path.basename(min(gomacc_paths)) + ".tar.gz"
        tarball_path = os.path.join(self._dest_dir, tarball_name)
        cros_build_lib.CreateTarball(
            tarball_path,
            cwd=self._log_dir,
            compression=cros_build_lib.CompressionType.GZIP,
        )
        return tarball_name

    def _ArchiveNinjaLog(self, compiler_proxy_path):
        """Archives .ninja_log file and its related metadata.

        This archives the .ninja_log file generated by ninja to build Chrome.
        Also, it appends some related metadata at the end of the file following
        '# end of ninja log' marker.

        Args:
            compiler_proxy_path: Path to the compiler proxy, which will be
                contained in the metadata.

        Returns:
            The name of the archived file.
        """
        ninja_log_path = os.path.join(self._log_dir, "ninja_log")
        if not os.path.exists(ninja_log_path):
            logging.warning("ninja_log is not found: %s", ninja_log_path)
            return None
        ninja_log_content = osutils.ReadFile(ninja_log_path)

        try:
            st = os.stat(ninja_log_path)
            ninja_log_mtime = datetime.datetime.fromtimestamp(st.st_mtime)
        except OSError:
            logging.exception("Failed to get timestamp: %s", ninja_log_path)
            return None

        ninja_log_info = self._BuildNinjaInfo(compiler_proxy_path)

        # Append metadata at the end of the log content.
        ninja_log_content += "# end of ninja log\n" + json.dumps(ninja_log_info)

        # Aligned with goma_utils in chromium bot.
        pid = os.getpid()

        archive_ninja_log_path = os.path.join(
            self._log_dir,
            "ninja_log.%s.%s.%s.%d"
            % (
                getpass.getuser(),
                hostname_util.get_host_name(),
                ninja_log_mtime.strftime("%Y%m%d-%H%M%S"),
                pid,
            ),
        )
        osutils.WriteFile(archive_ninja_log_path, ninja_log_content)
        archived_filename = os.path.basename(archive_ninja_log_path) + ".gz"

        archived_path = os.path.join(self._dest_dir, archived_filename)
        cros_build_lib.CompressFile(archive_ninja_log_path, archived_path)

        return archived_filename

    def _BuildNinjaInfo(self, compiler_proxy_path):
        """Reads metadata for the ninja run.

        Each metadata should be written into a dedicated file in the log
        directory. Read the info, and build the dict containing metadata.

        Args:
            compiler_proxy_path: Path to the compiler_proxy log file.

        Returns:
            A dict of the metadata.
        """

        info = {"platform": "chromeos"}

        command_path = os.path.join(self._log_dir, "ninja_command")
        if os.path.exists(command_path):
            info["cmdline"] = shlex.split(
                osutils.ReadFile(command_path).strip()
            )

        cwd_path = os.path.join(self._log_dir, "ninja_cwd")
        if os.path.exists(cwd_path):
            info["cwd"] = osutils.ReadFile(cwd_path).strip()

        exit_path = os.path.join(self._log_dir, "ninja_exit")
        if os.path.exists(exit_path):
            info["exit"] = int(osutils.ReadFile(exit_path).strip())

        env_path = os.path.join(self._log_dir, "ninja_env")
        if os.path.exists(env_path):
            # env is null-byte separated, and has a trailing null byte.
            content = osutils.ReadFile(env_path).rstrip("\0")
            info["env"] = dict(
                line.split("=", 1) for line in content.split("\0")
            )

        if compiler_proxy_path:
            info["compiler_proxy_info"] = os.path.basename(compiler_proxy_path)

        return info
