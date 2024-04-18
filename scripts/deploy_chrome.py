# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Script that deploys a Chrome build to a device.

The script supports deploying Chrome from these sources:

1. A local build output directory, such as chromium/src/out/[Debug|Release].
2. A Chrome tarball uploaded by a trybot/official-builder to GoogleStorage.
3. A Chrome tarball existing locally.

The script copies the necessary contents of the source location (tarball or
build directory) and rsyncs the contents of the staging directory onto your
device's rootfs.
"""

import argparse
import collections
import contextlib
import functools
import glob
import logging
import multiprocessing
import os
import re
import shlex
import shutil
import time

from chromite.third_party.gn_helpers import gn_helpers

from chromite.cli.cros import cros_chrome_sdk
from chromite.lib import chrome_util
from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import failures_lib
from chromite.lib import gs
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib import remote_access as remote
from chromite.lib import retry_util
from chromite.lib import timeout_util


KERNEL_A_PARTITION = 2
KERNEL_B_PARTITION = 4

KILL_PROC_MAX_WAIT = 10
POST_KILL_WAIT = 2
POST_UNLOCK_WAIT = 3

MOUNT_RW_COMMAND = ["mount", "-o", "remount,rw", "/"]
LAST_LOGIN_COMMAND = ["bootstat_get_last", "login-prompt-visible"]
UNLOCK_PASSWORD_COMMAND = "python -m uinput.cros_type_keys $'%s\\n'"

_ANDROID_DIR = "/system/chrome"
_ANDROID_DIR_EXTRACT_PATH = "system/chrome/*"

_CHROME_DIR = "/opt/google/chrome"
_CHROME_DIR_MOUNT = "/usr/local/opt/google/chrome"
_CHROME_DIR_STAGING_TARBALL_ZSTD = "chrome.tar.zst"
_CHROME_TEST_BIN_DIR = "/usr/local/libexec/chrome-binary-tests"

_UMOUNT_DIR_IF_MOUNTPOINT_CMD = (
    "if mountpoint -q %(dir)s; then umount %(dir)s; fi"
)
_FIND_TEST_BIN_CMD = [
    "find",
    _CHROME_TEST_BIN_DIR,
    "-maxdepth",
    "1",
    "-executable",
    "-type",
    "f",
]

# This constants are related to an experiment of running compressed ash chrome
# to save rootfs space. See b/247397013
COMPRESSED_ASH_SERVICE = "mount-ash-chrome"
COMPRESSED_ASH_FILE = "chrome.squashfs"
RAW_ASH_FILE = "chrome"
COMPRESSED_ASH_PATH = os.path.join(_CHROME_DIR, COMPRESSED_ASH_FILE)
RAW_ASH_PATH = os.path.join(_CHROME_DIR, RAW_ASH_FILE)
COMPRESSED_ASH_OVERLAY_SUFFIX = "-compressed-ash"

LACROS_DIR = "/usr/local/lacros-chrome"
_CONF_FILE = "/etc/chrome_dev.conf"
MODIFIED_CONF_FILE = f"modified {_CONF_FILE}"

# This command checks if
# "--enable-features=LacrosOnly,LacrosPrimary,LacrosSupport" is present in
# /etc/chrome_dev.conf. If it is not, then it is added.
# TODO(https://crbug.com/1112493): Automated scripts are currently not allowed
# to modify chrome_dev.conf. Either revisit this policy or find another
# mechanism to pass configuration to ash-chrome.
ENABLE_LACROS_VIA_CONF_COMMAND = f"""
    if ! grep -q "^--enable-features=LacrosOnly,LacrosPrimary,LacrosSupport$" {_CONF_FILE}; then
    echo "--enable-features=LacrosOnly,LacrosPrimary,LacrosSupport" >> {_CONF_FILE};
    echo {MODIFIED_CONF_FILE};
    fi
"""

# This command checks if "--lacros-chrome-path=" is present with the right value
# in /etc/chrome_dev.conf. If it is not, then all previous instances are removed
# and the new one is added.
# TODO(https://crbug.com/1112493): Automated scripts are currently not allowed
# to modify chrome_dev.conf. Either revisit this policy or find another
# mechanism to pass configuration to ash-chrome.
_SET_LACROS_PATH_VIA_CONF_COMMAND = """
    if ! grep -q "^--lacros-chrome-path=%(lacros_path)s$" %(conf_file)s; then
    sed 's/--lacros-chrome-path/#--lacros-chrome-path/' %(conf_file)s;
    echo "--lacros-chrome-path=%(lacros_path)s" >> %(conf_file)s;
    echo %(modified_conf_file)s;
    fi
"""


def _UrlBaseName(url):
    """Return the last component of the URL."""
    return url.rstrip("/").rpartition("/")[-1]


class DeployFailure(failures_lib.StepFailure):
    """Raised whenever the deploy fails."""


DeviceInfo = collections.namedtuple(
    "DeviceInfo", ["target_dir_size", "target_fs_free"]
)


class DeployChrome:
    """Wraps the core deployment functionality."""

    def __init__(self, options, tempdir, staging_dir):
        """Initialize the class.

        Args:
            options: options object.
            tempdir: Scratch space for the class.  Caller has responsibility to
                clean it up.
            staging_dir: Directory to stage the files to.
        """
        self.tempdir = tempdir
        self.options = options
        self.staging_dir = staging_dir
        if not self.options.staging_only:
            hostname = options.device.hostname
            port = options.device.port
            self.device = remote.ChromiumOSDevice(
                hostname,
                port=port,
                ping=options.ping,
                private_key=options.private_key,
                include_dev_paths=False,
            )
            if self._ShouldUseCompressedAsh():
                self.options.compressed_ash = True

        self._root_dir_is_still_readonly = multiprocessing.Event()

        self._deployment_name = "lacros" if options.lacros else "chrome"
        self.copy_paths = chrome_util.GetCopyPaths(self._deployment_name)

        self.chrome_dir = LACROS_DIR if self.options.lacros else _CHROME_DIR

        # Whether UI was stopped during setup.
        self._stopped_ui = False

    def _ShouldUseCompressedAsh(self):
        """Detects if the DUT uses compressed-ash setup."""
        if self.options.lacros:
            return False

        return self.device.IfFileExists(COMPRESSED_ASH_PATH)

    def _GetRemoteMountFree(self, remote_dir):
        result = self.device.run(["df", "-k", remote_dir])
        line = result.stdout.splitlines()[1]
        value = line.split()[3]
        multipliers = {
            "G": 1024 * 1024 * 1024,
            "M": 1024 * 1024,
            "K": 1024,
        }
        return int(value.rstrip("GMK")) * multipliers.get(value[-1], 1)

    def _GetRemoteDirSize(self, remote_dir):
        result = self.device.run(
            "du -ks %s" % remote_dir, capture_output=True, encoding="utf-8"
        )
        return int(result.stdout.split()[0])

    def _GetStagingDirSize(self):
        result = cros_build_lib.dbg_run(
            ["du", "-ks", self.staging_dir],
            capture_output=True,
            encoding="utf-8",
        )
        return int(result.stdout.split()[0])

    def _ChromeFileInUse(self):
        result = self.device.run(
            ["lsof", f"{self.options.target_dir}/chrome"],
            check=False,
            capture_output=True,
        )
        return result.returncode == 0

    def _DisableRootfsVerification(self):
        if not self.options.force:
            logging.error(
                "Detected that the device has rootfs verification enabled."
            )
            logging.info(
                "This script can automatically remove the rootfs "
                "verification, which requires it to reboot the device."
            )
            logging.info("Make sure the device is in developer mode!")
            logging.info("Skip this prompt by specifying --force.")
            if not cros_build_lib.BooleanPrompt(
                "Remove rootfs verification?", False
            ):
                return False

        logging.info(
            "Removing rootfs verification from %s", self.options.device
        )
        # Running in VMs cause make_dev_ssd's firmware confidence checks to
        # fail. Use --force to bypass the checks.
        # TODO(b/269266992): Switch back to a list.
        cmd = (
            "/usr/share/vboot/bin/make_dev_ssd.sh "
            f"--partitions '{KERNEL_A_PARTITION} {KERNEL_B_PARTITION}' "
            "--remove_rootfs_verification "
            "--force"
        )
        self.device.run(cmd, shell=True, check=False)

        self.device.Reboot()

        # Make sure the rootfs is writable now.
        self._MountRootfsAsWritable(run_diagnostics=True)

        # Now that the machine has been rebooted, we need to kill Chrome again.
        self._KillAshChromeIfNeeded()

        return self.device.IsDirWritable("/")

    def _CheckUiJobStarted(self):
        # status output is in the format:
        # <job_name> <status> ['process' <pid>].
        # <status> is in the format <goal>/<state>.
        try:
            result = self.device.run(
                "status ui", capture_output=True, encoding="utf-8"
            )
        except cros_build_lib.RunCommandError as e:
            if "Unknown job" in e.stderr:
                return False
            else:
                raise e

        return result.stdout.split()[1].split("/")[0] == "start"

    def _KillLacrosChrome(self):
        """This method kills lacros-chrome on the device, if it's running."""
        # Mark the lacros chrome binary as not executable, so if keep-alive is
        # enabled ash chrome can't restart lacros chrome. This prevents rsync
        # from failing if the file is still in use (being executed by ash
        # chrome). Note that this will cause ash chrome to continuously attempt
        # to start lacros and fail, although it doesn't seem to cause issues.
        if self.options.skip_restart_ui:
            self.device.run(
                ["chmod", "-x", f"{self.options.target_dir}/chrome"],
                check=False,
            )
        self.device.run(
            ["pkill", "-f", f"{self.options.target_dir}/chrome"],
            check=False,
        )

    def _ResetLacrosChrome(self):
        """Reset Lacros to fresh state by deleting user data dir."""
        self.device.run(["rm", "-rf", "/home/chronos/user/lacros"], check=False)

    def _KillAshChromeIfNeeded(self):
        """This method kills ash-chrome on the device, if it's running.

        This method calls 'stop ui', and then also manually pkills both
        ash-chrome and the session manager.
        """
        if self._CheckUiJobStarted():
            logging.info("Shutting down Chrome...")
            self.device.run(["stop", "ui"])

        # Developers sometimes run session_manager manually, in which case we'll
        # need to help shut the chrome processes down.
        try:
            with timeout_util.Timeout(self.options.process_timeout):
                while self._ChromeFileInUse():
                    logging.warning(
                        "The chrome binary on the device is in use."
                    )
                    logging.warning(
                        "Killing chrome and session_manager processes...\n"
                    )

                    self.device.run(
                        "pkill 'chrome|session_manager'", check=False
                    )
                    # Wait for processes to actually terminate
                    time.sleep(POST_KILL_WAIT)
                    logging.info("Rechecking the chrome binary...")
                if self.options.compressed_ash:
                    result = self.device.run(
                        ["umount", RAW_ASH_PATH],
                        check=False,
                        capture_output=True,
                    )
                    if result.returncode and not (
                        result.returncode == 32
                        and "not mounted" in result.stderr
                    ):
                        raise DeployFailure(
                            "Could not unmount compressed ash. "
                            f"Error Code: {result.returncode}, "
                            f"Error Message: {result.stderr}"
                        )
        except timeout_util.TimeoutError:
            msg = (
                "Could not kill processes after %s seconds.  Please exit any "
                "running chrome processes and try again."
                % self.options.process_timeout
            )
            raise DeployFailure(msg)

    def _MountRootfsAsWritable(self, check=False, run_diagnostics=False):
        """Mounts the rootfs as writable.

        If the command fails and the root dir is not writable then this function
        sets self._root_dir_is_still_readonly.

        Args:
            check: See remote.RemoteAccess.RemoteSh for details.
            run_diagnostics: Run additional diagnostics if mounting fails.
        """
        # TODO: Should migrate to use the remount functions in remote_access.
        result = self.device.run(
            MOUNT_RW_COMMAND,
            capture_output=True,
            check=check,
            encoding="utf-8",
        )

        if not self.device.IsDirWritable("/"):
            if result and result.returncode:
                logging.warning(
                    "Mounting root as writable failed: %s", result.stderr
                )

            if run_diagnostics:
                # Dump debug info to help diagnose b/293204438.
                findmnt_result = self.device.run(
                    ["findmnt"], capture_output=True
                )
                logging.info("findmnt: %s", findmnt_result.stdout)
                dmesg_result = self.device.run(["dmesg"], capture_output=True)
                logging.info("dmesg: %s", dmesg_result.stdout)

            self._root_dir_is_still_readonly.set()
        else:
            self._root_dir_is_still_readonly.clear()

    def _EnsureTargetDir(self):
        """Ensures that the target directory exists on the remote device."""
        target_dir = self.options.target_dir
        # Any valid /opt directory should already exist so avoid the remote
        # call.
        if os.path.commonprefix([target_dir, "/opt"]) == "/opt":
            return
        self.device.mkdir(target_dir, mode=0o775)

    def _GetDeviceInfo(self):
        """Get the disk space used and available for the target directory."""
        steps = [
            functools.partial(self._GetRemoteDirSize, self.options.target_dir),
            functools.partial(
                self._GetRemoteMountFree, self.options.target_dir
            ),
        ]
        return_values = parallel.RunParallelSteps(steps, return_values=True)
        return DeviceInfo(*return_values)

    def _CheckDeviceFreeSpace(self, device_info):
        """See if target device has enough space for Chrome.

        Args:
            device_info: A DeviceInfo named tuple.
        """
        effective_free = (
            device_info.target_dir_size + device_info.target_fs_free
        )
        staging_size = self._GetStagingDirSize()
        if effective_free < staging_size:
            raise DeployFailure(
                "Not enough free space on the device.  Required: %s MiB, "
                "actual: %s MiB."
                % (staging_size // 1024, effective_free // 1024)
            )
        if device_info.target_fs_free < (100 * 1024):
            logging.warning(
                "The device has less than 100MB free.  deploy_chrome may "
                "hang during the transfer."
            )

    def _ShouldUseCompression(self):
        """Checks if compression should be used for rsync."""
        if self.options.compress == "always":
            return True
        elif self.options.compress == "never":
            return False
        elif self.options.compress == "auto":
            return not self.device.HasGigabitEthernet()

    def _Deploy(self):
        logging.info(
            "Copying %s to %s on device...",
            self._deployment_name,
            self.options.target_dir,
        )
        # CopyToDevice will fall back to scp if rsync is corrupted on stateful.
        # This does not work for deploy.
        if not self.device.HasRsync():
            # This assumes that rsync is part of the bootstrap package. In the
            # future, this might change and we'll have to install it separately.
            if not cros_build_lib.BooleanPrompt(
                "Run dev_install on the device to install rsync?", True
            ):
                raise DeployFailure("rsync is not found on the device.")
            self.device.BootstrapDevTools()
            if not self.device.HasRsync():
                raise DeployFailure("Failed to install rsync")

        try:
            staging_dir = os.path.abspath(self.staging_dir)
            staging_chrome = os.path.join(staging_dir, "chrome")

            if (
                self.options.lacros
                and self.options.skip_restart_ui
                and os.path.exists(staging_chrome)
            ):
                # Make the chrome binary not executable before deploying to
                # prevent ash chrome from starting chrome before the rsync has
                # finished.
                os.chmod(staging_chrome, 0o644)

            self.device.CopyToDevice(
                f"{staging_dir}/",
                self.options.target_dir,
                mode="rsync",
                inplace=True,
                compress=self._ShouldUseCompression(),
                debug_level=logging.INFO,
                verbose=self.options.verbose,
            )
        finally:
            if self.options.lacros and self.options.skip_restart_ui:
                self.device.run(
                    ["chmod", "+x", f"{self.options.target_dir}/chrome"],
                    check=False,
                )

        # Set the security context on the default Chrome dir if that's where
        # it's getting deployed, and only on SELinux supported devices.
        if (
            not self.options.lacros
            and self.device.IsSELinuxAvailable()
            and (
                _CHROME_DIR in (self.options.target_dir, self.options.mount_dir)
            )
        ):
            self.device.run(["restorecon", "-R", _CHROME_DIR])

        for p in self.copy_paths:
            if p.mode:
                # Set mode if necessary.
                self.device.run(
                    "chmod %o %s/%s"
                    % (
                        p.mode,
                        self.options.target_dir,
                        p.src if not p.dest else p.dest,
                    )
                )

        if self.options.lacros:
            self.device.run(
                ["chown", "-R", "chronos:chronos", self.options.target_dir]
            )

        if self.options.compressed_ash:
            self.device.run(["start", COMPRESSED_ASH_SERVICE])

        # Send SIGHUP to dbus-daemon to tell it to reload its configs. This
        # won't pick up major changes (bus type, logging, etc.), but all we care
        # about is getting the latest policy from /opt/google/chrome/dbus so
        # that Chrome will be authorized to take ownership of its service names.
        self.device.run(["killall", "-HUP", "dbus-daemon"], check=False)

        if self.options.startui and self._stopped_ui:
            last_login = self._GetLastLogin()
            logging.info("Starting UI...")
            self.device.run(["start", "ui"])

            if self.options.unlock_password:
                logging.info("Unlocking...")

                @retry_util.WithRetry(max_retry=5, sleep=1)
                def WaitForUnlockScreen():
                    if self._GetLastLogin() == last_login:
                        raise DeployFailure("Unlock screen not shown")

                WaitForUnlockScreen()
                time.sleep(POST_UNLOCK_WAIT)
                self.device.run(
                    UNLOCK_PASSWORD_COMMAND % self.options.unlock_password
                )

    def _GetLastLogin(self):
        """Returns last login time"""
        return self.device.run(LAST_LOGIN_COMMAND).stdout.strip()

    def _DeployTestBinaries(self):
        """Deploys any local test binary to _CHROME_TEST_BIN_DIR on the device.

        There could be several binaries located in the local build dir, so
        compare what's already present on the device in _CHROME_TEST_BIN_DIR ,
        and copy over any that we also built ourselves.
        """
        r = self.device.run(_FIND_TEST_BIN_CMD, check=False)
        if r.returncode != 0:
            raise DeployFailure(
                "Unable to ls contents of %s" % _CHROME_TEST_BIN_DIR
            )
        binaries_to_copy = []
        for f in r.stdout.splitlines():
            binaries_to_copy.append(
                chrome_util.Path(os.path.basename(f), exe=True, optional=True)
            )

        staging_dir = os.path.join(
            self.tempdir, os.path.basename(_CHROME_TEST_BIN_DIR)
        )
        _PrepareStagingDir(
            self.options, self.tempdir, staging_dir, copy_paths=binaries_to_copy
        )
        # Deploying can occasionally run into issues with rsync getting a broken
        # pipe, so retry several times. See crbug.com/1141618 for more
        # information.
        retry_util.RetryException(
            None,
            3,
            self.device.CopyToDevice,
            staging_dir,
            os.path.dirname(_CHROME_TEST_BIN_DIR),
            mode="rsync",
        )

    def _CheckBoard(self):
        """Check that the Chrome build is targeted for the device board."""
        if self.options.board == self.device.board:
            return
        logging.warning(
            "Device board is %s whereas target board is %s.",
            self.device.board,
            self.options.board,
        )
        if self.options.force:
            return
        if not cros_build_lib.BooleanPrompt(
            "Continue despite board mismatch?", False
        ):
            raise DeployFailure("Aborted.")

    def _CheckDeployType(self):
        if self.options.build_dir:

            def BinaryExists(filename):
                """Checks if |filename| is present in the build directory."""
                return os.path.exists(
                    os.path.join(self.options.build_dir, filename)
                )

            # In the future, lacros-chrome and ash-chrome will likely be named
            # something other than 'chrome' to avoid confusion.
            # Handle non-Chrome deployments.
            if not BinaryExists("chrome"):
                if BinaryExists("app_shell"):
                    self.copy_paths = chrome_util.GetCopyPaths("app_shell")

    def _PrepareStagingDir(self):
        _PrepareStagingDir(
            self.options,
            self.tempdir,
            self.staging_dir,
            self.copy_paths,
            self.chrome_dir,
        )

    def _MountTarget(self):
        logging.info("Mounting Chrome...")

        # Create directory if does not exist.
        self.device.mkdir(self.options.mount_dir, mode=0o775)
        try:
            # Umount the existing mount on mount_dir if present first.
            self.device.run(
                _UMOUNT_DIR_IF_MOUNTPOINT_CMD % {"dir": self.options.mount_dir}
            )
        except cros_build_lib.RunCommandError as e:
            logging.error("Failed to umount %s", self.options.mount_dir)
            # If there is a failure, check if some process is using the
            # mount_dir.
            result = self.device.run(
                ["lsof", self.options.mount_dir],
                check=False,
                capture_output=True,
                encoding="utf-8",
            )
            logging.error("lsof %s -->", self.options.mount_dir)
            logging.error(result.stdout)
            raise e

        self.device.run(
            [
                "mount",
                "--rbind",
                self.options.target_dir,
                self.options.mount_dir,
            ]
        )

        # Chrome needs partition to have exec and suid flags set
        self.device.run(
            ["mount", "-o", "remount,exec,suid", self.options.mount_dir]
        )

    def Cleanup(self):
        """Clean up RemoteDevice."""
        if not self.options.staging_only:
            self.device.Cleanup()

    def Perform(self):
        self._CheckDeployType()

        # If requested, just do the staging step.
        if self.options.staging_only:
            self._PrepareStagingDir()
            return 0

        # Check that the build matches the device. Lacros-chrome skips this
        # check as it's currently board independent. This means that it's
        # possible to deploy a build of lacros-chrome with a mismatched
        # architecture. We don't try to prevent this developer foot-gun.
        if not self.options.lacros:
            self._CheckBoard()

        # Ensure that the target directory exists before running parallel steps.
        self._EnsureTargetDir()

        logging.info("Preparing device")
        steps = [
            self._GetDeviceInfo,
            self._MountRootfsAsWritable,
            self._PrepareStagingDir,
        ]

        restart_ui = not self.options.skip_restart_ui
        if self.options.lacros:
            steps.append(self._KillLacrosChrome)
            if self.options.reset_lacros:
                steps.append(self._ResetLacrosChrome)
            config_modified = False
            if self.options.modify_config_file:
                config_modified = self._ModifyConfigFileIfNeededForLacros()
            if config_modified and not restart_ui:
                logging.warning(
                    "Config file modified but skipping restart_ui "
                    "due to option --skip-restart-ui. Config file "
                    "update is not reflected."
                )

        if restart_ui:
            steps.append(self._KillAshChromeIfNeeded)
            self._stopped_ui = True

        ret = parallel.RunParallelSteps(
            steps, halt_on_error=True, return_values=True
        )
        self._CheckDeviceFreeSpace(ret[0])

        # If the root dir is not writable, try disabling rootfs verification.
        # (We always do this by default so that developers can write to
        # /etc/chrome_dev.conf and other directories in the rootfs).
        if self._root_dir_is_still_readonly.is_set():
            if self.options.noremove_rootfs_verification:
                logging.warning("Skipping disable rootfs verification.")
            elif not self._DisableRootfsVerification():
                # A writable rootfs might not be needed if
                # 1) Deploy chrome to stateful partition with mount option.
                # 2) Deploy lacros without modifying /etc/chrome_dev.conf.
                if self.options.mount:
                    logging.warning(
                        "Failed to disable rootfs verification. "
                        "Continue as --mount is set."
                    )
                elif (
                    self.options.lacros and not self.options.modify_config_file
                ):
                    logging.warning(
                        "Failed to disable rootfs verification. "
                        "Continue as --lacros is set and "
                        "--skip-modifying-config-file is unset."
                    )
                else:
                    raise DeployFailure(
                        "Failed to disable rootfs verification."
                    )

            # If the target dir is still not writable (i.e. the user opted out
            # or the command failed), abort.
            if not self.device.IsDirWritable(self.options.target_dir):
                if self.options.startui and self._stopped_ui:
                    logging.info("Restarting Chrome...")
                    self.device.run(["start", "ui"])
                raise DeployFailure(
                    "Target location is not writable. Aborting."
                )

        if self.options.mount_dir is not None:
            self._MountTarget()

        # Actually deploy Chrome to the device.
        self._Deploy()
        if self.options.deploy_test_binaries:
            self._DeployTestBinaries()

    def _ModifyConfigFileIfNeededForLacros(self):
        """Modifies the /etc/chrome_dev.conf file for lacros-chrome.

        Returns:
            True if the file is modified, and the return value is usually used
            to determine whether restarting ash-chrome is needed.
        """
        assert (
            self.options.lacros
        ), "Only deploying lacros-chrome needs to modify the config file."
        # Update /etc/chrome_dev.conf to include appropriate flags.
        modified = False
        if self.options.enable_lacros_support:
            result = self.device.run(ENABLE_LACROS_VIA_CONF_COMMAND, shell=True)
            if result.stdout.strip() == MODIFIED_CONF_FILE:
                modified = True
        result = self.device.run(
            _SET_LACROS_PATH_VIA_CONF_COMMAND
            % {
                "conf_file": _CONF_FILE,
                "lacros_path": self.options.target_dir,
                "modified_conf_file": MODIFIED_CONF_FILE,
            },
            shell=True,
        )
        if result.stdout.strip() == MODIFIED_CONF_FILE:
            modified = True

        return modified


def ValidateStagingFlags(value):
    """Convert formatted string to dictionary."""
    return chrome_util.ProcessShellFlags(value)


def ValidateGnArgs(value):
    """Convert GN_ARGS-formatted string to dictionary."""
    return gn_helpers.FromGNArgs(value)


def _CreateParser():
    """Create our custom parser."""
    parser = commandline.ArgumentParser(description=__doc__, caching=True)

    # TODO(rcui): Have this use the UI-V2 format of having source and target
    # device be specified as positional arguments.
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Skip all prompts (such as the prompt for disabling "
        "of rootfs verification).  This may result in the "
        "target machine being rebooted.",
    )
    sdk_board_env = os.environ.get(cros_chrome_sdk.SDKFetcher.SDK_BOARD_ENV)
    parser.add_argument(
        "--board",
        default=sdk_board_env,
        help="The board the Chrome build is targeted for.  When "
        "in a 'cros chrome-sdk' shell, defaults to the SDK "
        "board.",
    )
    parser.add_argument(
        "--build-dir",
        type="path",
        help="The directory with Chrome build artifacts to "
        "deploy from. Typically of format "
        "<chrome_root>/out/Debug. When this option is used, "
        "the GN_ARGS environment variable must be set.",
    )
    parser.add_argument(
        "--target-dir",
        type="path",
        default=None,
        help="Target directory on device to deploy Chrome into.",
    )
    parser.add_argument(
        "-g",
        "--gs-path",
        type="gs_path",
        help="GS path that contains the chrome to deploy.",
    )
    parser.add_argument(
        "--private-key",
        type="path",
        default=None,
        help="An ssh private key to use when deploying to " "a CrOS device.",
    )
    parser.add_argument(
        "--nostartui",
        action="store_false",
        dest="startui",
        default=True,
        help="Don't restart the ui daemon after deployment.",
    )
    parser.add_argument(
        "--unlock-password",
        default=None,
        help="Password to use to unlock after deployment and restart.",
    )
    parser.add_argument(
        "--nostrip",
        action="store_false",
        dest="dostrip",
        default=True,
        help="Don't strip binaries during deployment.  Warning: "
        "the resulting binaries will be very large!",
    )
    parser.add_argument(
        "-d",
        "--device",
        type=commandline.DeviceParser(commandline.DEVICE_SCHEME_SSH),
        help="Device hostname or IP in the format hostname[:port].",
    )
    parser.add_argument(
        "--mount-dir",
        type="path",
        default=None,
        help="Deploy Chrome in target directory and bind it "
        "to the directory specified by this flag. "
        "Any existing mount on this directory will be "
        "umounted first.",
    )
    parser.add_argument(
        "--mount",
        action="store_true",
        default=False,
        help="Deploy Chrome to default target directory and bind "
        "it to the default mount directory. "
        "Any existing mount on this directory will be "
        "umounted first.",
    )
    parser.add_argument(
        "--noremove-rootfs-verification",
        action="store_true",
        default=False,
        help="Never remove rootfs verification.",
    )
    parser.add_argument(
        "--deploy-test-binaries",
        action="store_true",
        default=False,
        help="Also deploy any test binaries to %s. Useful for "
        "running any Tast tests that execute these "
        "binaries." % _CHROME_TEST_BIN_DIR,
    )
    parser.add_argument(
        "--use-external-config",
        action="store_true",
        help="When identifying the configuration for a board, "
        "force usage of the external configuration if both "
        "internal and external are available. This only "
        "has an effect when stripping Chrome, i.e. when "
        "--nostrip is not passed in.",
    )

    group = parser.add_argument_group("Lacros Options")
    group.add_argument(
        "--lacros",
        action="store_true",
        default=False,
        help="Deploys lacros-chrome rather than ash-chrome.",
    )
    group.add_argument(
        "--reset-lacros",
        action="store_true",
        default=False,
        help="Reset Lacros by deleting Lacros user data dir if it exists.",
    )
    group.add_argument(
        "--skip-restart-ui",
        action="store_true",
        default=False,
        help="Skip restarting ash-chrome on deploying lacros-chrome. Note "
        "that this flag may cause ETXTBSY error on rsync, and also won't "
        "reflect the /etc/chrome_dev.conf file updates as it won't restart.",
    )
    group.add_argument(
        "--skip-enabling-lacros-support",
        action="store_false",
        dest="enable_lacros_support",
        help="By default, deploying lacros-chrome modifies the "
        "/etc/chrome_dev.conf file to (1) enable the LacrosSupport feature "
        "and (2) set the Lacros path, which can interfere with automated "
        "testing. With this flag, part (1) will be skipped. See the "
        "--skip-modifying-config-file flag for skipping both parts.",
    )
    group.add_argument(
        "--skip-modifying-config-file",
        action="store_false",
        dest="modify_config_file",
        help="When deploying lacros-chrome, do not modify the "
        "/etc/chrome_dev.conf file. See also the "
        "--skip-enabling-lacros-support flag.",
    )

    group = parser.add_argument_group("Advanced Options")
    group.add_argument(
        "-l",
        "--local-pkg-path",
        type="path",
        help="Path to local chrome prebuilt package to deploy.",
    )
    group.add_argument(
        "--sloppy",
        action="store_true",
        default=False,
        help="Ignore when mandatory artifacts are missing.",
    )
    group.add_argument(
        "--staging-flags",
        default=None,
        type=ValidateStagingFlags,
        help=(
            "Extra flags to control staging.  Valid flags are - "
            "%s" % ", ".join(chrome_util.STAGING_FLAGS)
        ),
    )
    # TODO(stevenjb): Remove --strict entirely once removed from the ebuild.
    group.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help='Deprecated. Default behavior is "strict". Use '
        "--sloppy to omit warnings for missing optional "
        "files.",
    )
    group.add_argument(
        "--strip-flags",
        default=None,
        help="Flags to call the 'strip' binutil tool with.  "
        "Overrides the default arguments.",
    )
    group.add_argument(
        "--ping",
        action="store_true",
        default=False,
        help="Ping the device before connection attempt.",
    )
    group.add_argument(
        "--process-timeout",
        type=int,
        default=KILL_PROC_MAX_WAIT,
        help="Timeout for process shutdown.",
    )

    group = parser.add_argument_group(
        "Metadata Overrides (Advanced)",
        description="Provide all of these overrides in order to remove "
        "dependencies on metadata.json existence.",
    )
    group.add_argument(
        "--target-tc",
        action="store",
        default=None,
        help="Override target toolchain name, e.g. " "x86_64-cros-linux-gnu",
    )
    group.add_argument(
        "--toolchain-url",
        action="store",
        default=None,
        help="Override toolchain url format pattern, e.g. "
        "2014/04/%%(target)s-2014.04.23.220740.tar.xz",
    )

    # DEPRECATED: --gyp-defines is ignored, but retained for backwards
    # compatibility. TODO(stevenjb): Remove once eliminated from the ebuild.
    parser.add_argument(
        "--gyp-defines",
        default=None,
        type=ValidateStagingFlags,
        help=argparse.SUPPRESS,
    )

    # GN_ARGS (args.gn) used to build Chrome. Influences which files are staged
    # when --build-dir is set. Defaults to reading from the GN_ARGS env
    # variable. CURRENTLY IGNORED, ADDED FOR FORWARD COMPATIBILITY.
    parser.add_argument(
        "--gn-args", default=None, type=ValidateGnArgs, help=argparse.SUPPRESS
    )

    # Path of an empty directory to stage chrome artifacts to.  Defaults to a
    # temporary directory that is removed when the script finishes. If the path
    # is specified, then it will not be removed.
    parser.add_argument(
        "--staging-dir", type="path", default=None, help=argparse.SUPPRESS
    )
    # Only prepare the staging directory, and skip deploying to the device.
    parser.add_argument(
        "--staging-only",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS,
    )
    # Uploads the compressed staging directory to the given gs:// path URI.
    parser.add_argument(
        "--staging-upload",
        type="gs_path",
        help="GS path to upload the compressed staging files to.",
    )
    # Used alongside --staging-upload to upload with public-read ACL.
    parser.add_argument(
        "--public-read",
        action="store_true",
        default=False,
        help="GS path to upload the compressed staging files to.",
    )
    # Path to a binutil 'strip' tool to strip binaries with.  The passed-in path
    # is used as-is, and not normalized.  Used by the Chrome ebuild to skip
    # fetching the SDK toolchain.
    parser.add_argument("--strip-bin", default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--compress",
        action="store",
        default="auto",
        choices=("always", "never", "auto"),
        help="Choose the data transfer compression behavior. Default "
        'is set to "auto", that disables compression if '
        "the target device has a gigabit ethernet port.",
    )
    parser.add_argument(
        "--compressed-ash",
        action="store_true",
        default=False,
        help="Use compressed-ash deployment scheme. With the flag, ash-chrome "
        "binary is stored on DUT in squashfs, mounted upon boot.",
    )
    return parser


def _ParseCommandLine(argv):
    """Parse args, and run environment-independent checks."""
    parser = _CreateParser()
    options = parser.parse_args(argv)

    if not any([options.gs_path, options.local_pkg_path, options.build_dir]):
        parser.error(
            "Need to specify either --gs-path, --local-pkg-path, or "
            "--build-dir"
        )
    if options.build_dir and any([options.gs_path, options.local_pkg_path]):
        parser.error(
            "Cannot specify both --build_dir and " "--gs-path/--local-pkg-patch"
        )
    if options.lacros:
        if options.dostrip and not options.board:
            parser.error("Please specify --board.")
        if options.mount_dir or options.mount:
            parser.error("--lacros does not support --mount or --mount-dir")
        if options.deploy_test_binaries:
            parser.error("--lacros does not support --deploy-test-binaries")
        if options.local_pkg_path:
            parser.error("--lacros does not support --local-pkg-path")
        if options.compressed_ash:
            parser.error("--lacros does not support --compressed-ash")
    else:
        if not options.board and options.build_dir:
            match = re.search(r"out_([^/]+)/Release$", options.build_dir)
            if match:
                options.board = match.group(1)
                logging.info("--board is set to %s", options.board)
        if not options.board:
            parser.error("--board is required")
    if options.gs_path and options.local_pkg_path:
        parser.error("Cannot specify both --gs-path and --local-pkg-path")
    if not (options.staging_only or options.device):
        parser.error("Need to specify --device")
    if options.staging_flags and not options.build_dir:
        parser.error("--staging-flags require --build-dir to be set.")

    if options.strict:
        logging.warning("--strict is deprecated.")
    if options.gyp_defines:
        logging.warning("--gyp-defines is deprecated.")

    if options.mount or options.mount_dir:
        if not options.target_dir:
            options.target_dir = _CHROME_DIR_MOUNT
    else:
        if not options.target_dir:
            options.target_dir = LACROS_DIR if options.lacros else _CHROME_DIR

    if options.mount and not options.mount_dir:
        options.mount_dir = _CHROME_DIR

    return options


def _PostParseCheck(options):
    """Perform some usage validation (after we've parsed the arguments).

    Args:
        options: The options object returned by the cli parser.
    """
    if options.local_pkg_path and not os.path.isfile(options.local_pkg_path):
        cros_build_lib.Die("%s is not a file.", options.local_pkg_path)

    if not options.gn_args:
        gn_env = os.getenv("GN_ARGS")
        if gn_env is not None:
            options.gn_args = gn_helpers.FromGNArgs(gn_env)
            logging.debug("GN_ARGS taken from environment: %s", options.gn_args)

    if not options.staging_flags:
        use_env = os.getenv("USE")
        if use_env is not None:
            options.staging_flags = " ".join(
                set(use_env.split()).intersection(chrome_util.STAGING_FLAGS)
            )
            logging.info(
                "Staging flags taken from USE in environment: %s",
                options.staging_flags,
            )


def _FetchChromePackage(cache_dir, tempdir, gs_path):
    """Get the chrome prebuilt tarball from GS.

    Returns:
        Path to the fetched chrome tarball.
    """
    gs_ctx = gs.GSContext(cache_dir=cache_dir, init_boto=True)
    files = gs_ctx.LS(gs_path)
    files = [
        found
        for found in files
        if _UrlBaseName(found).startswith("%s-" % constants.CHROME_PN)
    ]
    if not files:
        raise Exception("No chrome package found at %s" % gs_path)
    elif len(files) > 1:
        # - Users should provide us with a direct link to either a stripped or
        #   unstripped chrome package.
        # - In the case of being provided with an archive directory, where both
        #   stripped and unstripped chrome available, use the stripped chrome
        #   package.
        # - Stripped chrome pkg is chromeos-chrome-<version>.tar.gz
        # - Unstripped chrome pkg is
        #   chromeos-chrome-<version>-unstripped.tar.gz.
        files = [f for f in files if not "unstripped" in f]
        assert len(files) == 1
        logging.warning("Multiple chrome packages found.  Using %s", files[0])

    filename = _UrlBaseName(files[0])
    logging.info("Fetching %s...", filename)
    gs_ctx.Copy(files[0], tempdir, print_cmd=False)
    chrome_path = os.path.join(tempdir, filename)
    assert os.path.exists(chrome_path)
    return chrome_path


@contextlib.contextmanager
def _StripBinContext(options):
    if not options.dostrip:
        yield None
    elif options.strip_bin:
        yield options.strip_bin
    else:
        sdk = cros_chrome_sdk.SDKFetcher(
            options.cache_dir,
            options.board,
            use_external_config=options.use_external_config,
        )
        components = (sdk.TARGET_TOOLCHAIN_KEY, constants.CHROME_ENV_TAR)
        with sdk.Prepare(
            components=components,
            target_tc=options.target_tc,
            toolchain_url=options.toolchain_url,
        ) as ctx:
            env_path = os.path.join(
                ctx.key_map[constants.CHROME_ENV_TAR].path,
                constants.CHROME_ENV_FILE,
            )
            strip_bin = osutils.SourceEnvironment(env_path, ["STRIP"])["STRIP"]
            strip_bin = os.path.join(
                ctx.key_map[sdk.TARGET_TOOLCHAIN_KEY].path,
                "bin",
                os.path.basename(strip_bin),
            )
            yield strip_bin


def _UploadStagingDir(
    options: commandline.ArgumentNamespace, tempdir: str, staging_dir: str
) -> None:
    """Uploads the compressed staging directory.

    Args:
        options: options object.
        tempdir: Scratch space.
        staging_dir: Directory staging chrome files.
    """
    staging_tarball_path = os.path.join(
        tempdir, _CHROME_DIR_STAGING_TARBALL_ZSTD
    )
    logging.info(
        "Compressing staging dir (%s) to (%s)",
        staging_dir,
        staging_tarball_path,
    )
    cros_build_lib.CreateTarball(
        staging_tarball_path,
        staging_dir,
        compression=cros_build_lib.CompressionType.ZSTD,
        extra_env={"ZSTD_CLEVEL": "9"},
    )
    logging.info(
        "Uploading staging tarball (%s) into %s",
        staging_tarball_path,
        options.staging_upload,
    )
    ctx = gs.GSContext()
    ctx.Copy(
        staging_tarball_path,
        options.staging_upload,
        acl="public-read" if options.public_read else "",
    )


def _PrepareStagingDir(
    options, tempdir, staging_dir, copy_paths=None, chrome_dir=None
):
    """Place the necessary files in the staging directory.

    The staging directory is the directory used to rsync the build artifacts
    over to the device.  Only the necessary Chrome build artifacts are put into
    the staging directory.
    """
    if chrome_dir is None:
        chrome_dir = LACROS_DIR if options.lacros else _CHROME_DIR
    osutils.SafeMakedirs(staging_dir)
    os.chmod(staging_dir, 0o755)
    if options.build_dir:
        with _StripBinContext(options) as strip_bin:
            strip_flags = (
                None
                if options.strip_flags is None
                else shlex.split(options.strip_flags)
            )
            chrome_util.StageChromeFromBuildDir(
                staging_dir,
                options.build_dir,
                strip_bin,
                sloppy=options.sloppy,
                gn_args=options.gn_args,
                staging_flags=options.staging_flags,
                strip_flags=strip_flags,
                copy_paths=copy_paths,
            )
    else:
        pkg_path = options.local_pkg_path
        if options.gs_path:
            pkg_path = _FetchChromePackage(
                options.cache_dir, tempdir, options.gs_path
            )

        assert pkg_path
        logging.info("Extracting %s...", pkg_path)
        # Extract only the ./opt/google/chrome contents, directly into the
        # staging dir, collapsing the directory hierarchy.
        if pkg_path[-4:] == ".zip":
            cros_build_lib.dbg_run(
                [
                    "unzip",
                    "-X",
                    pkg_path,
                    _ANDROID_DIR_EXTRACT_PATH,
                    "-d",
                    staging_dir,
                ]
            )
            for filename in glob.glob(
                os.path.join(staging_dir, "system/chrome/*")
            ):
                shutil.move(filename, staging_dir)
            osutils.RmDir(
                os.path.join(staging_dir, "system"), ignore_missing=True
            )
        else:
            compression = cros_build_lib.CompressionDetectType(pkg_path)
            compressor = cros_build_lib.FindCompressor(compression)
            if compression == cros_build_lib.CompressionType.ZSTD:
                compressor += " -f"
            cros_build_lib.dbg_run(
                [
                    "tar",
                    "--strip-components",
                    "4",
                    "--extract",
                    "-I",
                    compressor,
                    "--preserve-permissions",
                    "--file",
                    pkg_path,
                    ".%s" % chrome_dir,
                ],
                cwd=staging_dir,
            )

    if options.compressed_ash:
        # Setup SDK here so mksquashfs is still found in no-shell + nostrip
        # configuration.
        # HACH(b/247397013, dlunev): to not setup release builders for SDK while
        # this is in test, cut the known suffix of experimental overlays.
        sdk_orig_board = options.board
        if sdk_orig_board.endswith(COMPRESSED_ASH_OVERLAY_SUFFIX):
            sdk_orig_board = sdk_orig_board[
                : -len(COMPRESSED_ASH_OVERLAY_SUFFIX)
            ]

        sdk = cros_chrome_sdk.SDKFetcher(
            options.cache_dir,
            sdk_orig_board,
            use_external_config=options.use_external_config,
        )
        with sdk.Prepare(
            components=[],
            target_tc=options.target_tc,
            toolchain_url=options.toolchain_url,
        ):
            cros_build_lib.dbg_run(
                [
                    "mksquashfs",
                    RAW_ASH_FILE,
                    COMPRESSED_ASH_FILE,
                    "-all-root",
                    "-no-progress",
                    "-comp",
                    "zstd",
                ],
                cwd=staging_dir,
            )
        os.truncate(os.path.join(staging_dir, RAW_ASH_FILE), 0)

    if options.staging_upload:
        _UploadStagingDir(options, tempdir, staging_dir)


def main(argv):
    options = _ParseCommandLine(argv)
    _PostParseCheck(options)

    with osutils.TempDir(set_global=True) as tempdir:
        staging_dir = options.staging_dir
        if not staging_dir:
            staging_dir = os.path.join(tempdir, "chrome")

        deploy = DeployChrome(options, tempdir, staging_dir)
        try:
            deploy.Perform()
        except failures_lib.StepFailure as ex:
            raise SystemExit(str(ex).strip())
        deploy.Cleanup()
