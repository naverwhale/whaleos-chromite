# Copyright 2017 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to upload goma logs to Google cloud storage bucket."""

import collections
import datetime
import getpass
import glob
import json
import logging
import os
import shlex

from chromite.lib import cros_build_lib
from chromite.lib import gs
from chromite.lib import osutils
from chromite.utils import hostname_util


_GOMA_COMPILER_PROXY_LOG_URL_TEMPLATE = (
    "https://chromium-build-stats.appspot.com/compiler_proxy_log/%s/%s"
)
_GOMA_NINJA_LOG_URL_TEMPLATE = (
    "https://chromium-build-stats.appspot.com/ninja_log/%s/%s"
)


# Note: Public for testing purpose. In real use, please think about using
# Goma.UploadLogs() instead.
class GomaLogUploader:
    """Manages to upload goma log files."""

    # The Google Cloud Storage bucket to store logs related to goma.
    _BUCKET = "chrome-goma-log"

    def __init__(
        self, goma_log_dir, today=None, dry_run=False, cbb_config_name=""
    ):
        """Initializes the uploader.

        Args:
            goma_log_dir: path to the directory containing goma's INFO log
                files.
            today: datetime.date instance representing today. This is for
                testing purpose, because datetime.date is unpatchable. In real
                use case, this must be None.
            dry_run: If True, no actual upload. This is for testing purpose.
            cbb_config_name: Name of cbb_config.
        """
        self._goma_log_dir = goma_log_dir
        logging.info("Goma log directory is: %s", self._goma_log_dir)

        # Set log upload destination.
        if today is None:
            today = datetime.date.today()
        self.dest_path = "%s/%s" % (
            today.strftime("%Y/%m/%d"),
            hostname_util.get_host_name(),
        )
        self._remote_dir = "gs://%s/%s" % (
            GomaLogUploader._BUCKET,
            self.dest_path,
        )
        logging.info("Goma log upload destination: %s", self._remote_dir)

        # HACK(yyanagisawa): I suppose LUCI do not set BUILDBOT_BUILDERNAME.
        is_luci = not bool(os.environ.get("BUILDBOT_BUILDERNAME"))
        # Build metadata to be annotated to log files.
        # Use OrderedDict for json output stabilization.
        builder_info = collections.OrderedDict(
            [
                ("builder", os.environ.get("BUILDBOT_BUILDERNAME", "")),
                ("master", os.environ.get("BUILDBOT_MASTERNAME", "")),
                ("slave", os.environ.get("BUILDBOT_SLAVENAME", "")),
                ("clobber", bool(os.environ.get("BUILDBOT_CLOBBER"))),
                ("os", "chromeos"),
                ("is_luci", is_luci),
                ("cbb_config_name", cbb_config_name),
            ]
        )
        if is_luci:
            # TODO(yyanagisawa): will adjust to valid value if needed.
            builder_info["builder_id"] = collections.OrderedDict(
                [
                    ("project", "chromeos"),
                    ("builder", "Prod"),
                    ("bucket", "general"),
                ]
            )
        builder_info_json = json.dumps(builder_info)
        logging.info("BuilderInfo: %s", builder_info_json)
        self._headers = ["x-goog-meta-builderinfo:" + builder_info_json]

        self._gs_context = gs.GSContext(dry_run=dry_run)

    def Upload(self):
        """Uploads all necessary log files to Google Storage.

        Returns:
            A list of pairs of label and URL of goma log visualizers to be
            linked from the build status page.
        """
        compiler_proxy_subproc_paths = self._UploadInfoFiles(
            "compiler_proxy-subproc"
        )
        # compiler_proxy-subproc.INFO file should be exact one.
        if len(compiler_proxy_subproc_paths) != 1:
            logging.warning(
                "Unexpected compiler_proxy-subproc INFO files: %r",
                compiler_proxy_subproc_paths,
            )

        compiler_proxy_paths = self._UploadInfoFiles("compiler_proxy")
        # compiler_proxy.INFO file should be exact one.
        if len(compiler_proxy_paths) != 1:
            logging.warning(
                "Unexpected compiler_proxy INFO files: %r", compiler_proxy_paths
            )
        compiler_proxy_path, uploaded_compiler_proxy_filename = (
            compiler_proxy_paths[0] if compiler_proxy_paths else (None, None)
        )

        self._UploadGomaccInfoFiles()

        uploaded_ninja_log_filename = self._UploadNinjaLog(compiler_proxy_path)

        # Build URL to be linked.
        result = []
        if uploaded_compiler_proxy_filename:
            result.append(
                (
                    "Goma compiler_proxy log",
                    _GOMA_COMPILER_PROXY_LOG_URL_TEMPLATE
                    % (self.dest_path, uploaded_compiler_proxy_filename),
                )
            )
        if uploaded_ninja_log_filename:
            result.append(
                (
                    "Goma ninja_log",
                    _GOMA_NINJA_LOG_URL_TEMPLATE
                    % (self.dest_path, uploaded_ninja_log_filename),
                )
            )
        return result

    def _UploadInfoFiles(self, pattern):
        """Uploads INFO files matched with pattern, with gzip'ing.

        Args:
            pattern: matching path pattern.

        Returns:
            A list of uploaded file paths.
        """
        # Find files matched with the pattern in |goma_log_dir|. Sort for
        # stabilization.
        paths = sorted(
            glob.glob(os.path.join(self._goma_log_dir, "%s.*.INFO.*" % pattern))
        )
        if not paths:
            logging.warning("No glog files matched with: %s", pattern)

        result = []
        for path in paths:
            logging.info("Uploading %s", path)
            uploaded_filename = os.path.basename(path) + ".gz"
            self._gs_context.CopyInto(
                path,
                self._remote_dir,
                filename=uploaded_filename,
                auto_compress=True,
                headers=self._headers,
            )
            result.append((path, uploaded_filename))
        return result

    def _UploadGomaccInfoFiles(self):
        """Uploads gomacc INFO files, with gzip'ing.

        Returns:
            Uploaded file path. If failed, None.
        """

        # Since the number of gomacc logs can be large, we'd like to compress
        # them. Otherwise, upload will take long (> 10 mins). Each gomacc logs
        # file size must be small (around 4KB).

        # Find files matched with the pattern in |goma_log_dir|.
        # The paths were themselves used as the inputs for the create
        # tarball, but there can be too many of them. As long as we have
        # files we'll just tar up the entire directory.
        gomacc_paths = glob.glob(
            os.path.join(self._goma_log_dir, "gomacc.*.INFO.*")
        )
        if not gomacc_paths:
            # gomacc logs won't be made every time.
            # Only when goma compiler_proxy has
            # crashed. So it's usual gomacc logs are not found.
            logging.info("No gomacc logs found")
            return None

        # Taking the alphabetically first name as uploaded_filename.
        tarball_name = os.path.basename(min(gomacc_paths)) + ".tar.gz"
        # When using the pigz compressor (what we use for gzip) to create an
        # archive in a folder that is also a source for contents, there is a
        # race condition involving the created archive itself that can cause it
        # to fail creating the archive. To avoid this, make the archive in a
        # tempdir.
        with osutils.TempDir() as tempdir:
            tarball_path = os.path.join(tempdir, tarball_name)
            cros_build_lib.CreateTarball(
                tarball_path,
                cwd=self._goma_log_dir,
                compression=cros_build_lib.CompressionType.GZIP,
            )
            self._gs_context.CopyInto(
                tarball_path,
                self._remote_dir,
                filename=tarball_name,
                headers=self._headers,
            )
        return tarball_name

    def _UploadNinjaLog(self, compiler_proxy_path):
        """Uploads .ninja_log file and its related metadata.

        This uploads the .ninja_log file generated by ninja to build Chrome.
        Also, it appends some related metadata at the end of the file following
        '# end of ninja log' marker.

        Args:
            compiler_proxy_path: Path to the compiler proxy, which will be
                contained in the metadata.

        Returns:
            The name of the uploaded file.
        """
        ninja_log_path = os.path.join(self._goma_log_dir, "ninja_log")
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

        upload_ninja_log_path = os.path.join(
            self._goma_log_dir,
            "ninja_log.%s.%s.%s.%d"
            % (
                getpass.getuser(),
                hostname_util.get_host_name(),
                ninja_log_mtime.strftime("%Y%m%d-%H%M%S"),
                pid,
            ),
        )
        osutils.WriteFile(upload_ninja_log_path, ninja_log_content)
        uploaded_filename = os.path.basename(upload_ninja_log_path) + ".gz"
        self._gs_context.CopyInto(
            upload_ninja_log_path,
            self._remote_dir,
            filename=uploaded_filename,
            auto_compress=True,
            headers=self._headers,
        )
        return uploaded_filename

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

        command_path = os.path.join(self._goma_log_dir, "ninja_command")
        if os.path.exists(command_path):
            info["cmdline"] = shlex.split(
                osutils.ReadFile(command_path).strip()
            )

        cwd_path = os.path.join(self._goma_log_dir, "ninja_cwd")
        if os.path.exists(cwd_path):
            info["cwd"] = osutils.ReadFile(cwd_path).strip()

        exit_path = os.path.join(self._goma_log_dir, "ninja_exit")
        if os.path.exists(exit_path):
            info["exit"] = int(osutils.ReadFile(exit_path).strip())

        env_path = os.path.join(self._goma_log_dir, "ninja_env")
        if os.path.exists(env_path):
            # env is null-byte separated, and has a trailing null byte.
            content = osutils.ReadFile(env_path).rstrip("\0")
            info["env"] = dict(
                line.split("=", 1) for line in content.split("\0")
            )

        if compiler_proxy_path:
            info["compiler_proxy_info"] = os.path.basename(compiler_proxy_path)

        return info
