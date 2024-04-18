# Copyright 2018 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Library for running Chrome OS tests."""

import datetime
import logging
import os

from chromite.cbuildbot import commands
from chromite.cli.cros import cros_chrome_sdk
from chromite.lib import chrome_util
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import device
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.lib import retry_util
from chromite.lib import vm
from chromite.lib.xbuddy import xbuddy


# The Lacros sub directory when builds using alternate toolchain.
# Defined in
# https://source.chromium.org/chromium/chromium/src/+/main:build/toolchain/cros/BUILD.gn?q=lacros_clang&ss=chromium
_ADDITIONAL_LACROS_SUBDIR = "lacros_clang"


class CrOSTest:
    """Class for running Chrome OS tests."""

    def __init__(self, opts):
        """Initialize CrOSTest.

        Args:
            opts: command line options.
        """
        self.start_time = datetime.datetime.utcnow()

        self.start_vm = opts.start_vm
        self.cache_dir = opts.cache_dir
        self.dryrun = opts.dryrun

        self.build = opts.build
        self.flash = opts.flash
        self.public_image = opts.public_image
        self.xbuddy = opts.xbuddy
        self.deploy = opts.deploy
        self.deploy_lacros = opts.deploy_lacros
        self.lacros_launcher_script = opts.lacros_launcher_script
        if opts.deploy_lacros and opts.deploy:
            self.additional_lacros_build_dir = os.path.join(
                opts.build_dir, _ADDITIONAL_LACROS_SUBDIR
            )
        self.nostrip = opts.nostrip
        self.build_dir = opts.build_dir
        self.mount = opts.mount

        self.catapult_tests = opts.catapult_tests
        self.guest = opts.guest

        self.autotest = opts.autotest
        self.tast = opts.tast
        self.tast_vars = opts.tast_vars
        self.tast_total_shards = opts.tast_total_shards
        self.tast_shard_index = opts.tast_shard_index
        self.tast_shard_method = opts.tast_shard_method
        self.tast_retries = opts.tast_retries
        self.tast_extra_use_flags = []
        if opts.tast_extra_use_flags:
            self.tast_extra_use_flags = opts.tast_extra_use_flags.split(",")
        self.results_dir = opts.results_dir
        self.test_that_args = opts.test_that_args
        self.test_timeout = opts.test_timeout

        self.remote_cmd = opts.remote_cmd
        self.host_cmd = opts.host_cmd
        self.cwd = opts.cwd
        self.files = opts.files
        self.files_from = opts.files_from
        self.as_chronos = opts.as_chronos
        self.args = opts.args[1:] if opts.args else None

        self.results_src = opts.results_src
        self.results_dest_dir = opts.results_dest_dir
        self.save_snapshot_on_failure = opts.save_snapshot_on_failure

        self.chrome_test = opts.chrome_test
        if self.chrome_test:
            self.chrome_test_target = os.path.basename(opts.args[1])
            self.chrome_test_deploy_target_dir = "/usr/local/chrome_test"
        else:
            self.chrome_test_target = None
            self.chrome_test_deploy_target_dir = None
        self.staging_dir = None

        self.clean = opts.clean

        self._device = device.Device.Create(opts)

    def __del__(self):
        self._StopVM()

        logging.info(
            "Time elapsed: %s", datetime.datetime.utcnow() - self.start_time
        )

    def Run(self):
        """Start a VM, build/deploy, run tests, stop the VM."""
        if self._device.should_start_vm:
            self._StartVM()
        else:
            self._device.WaitForBoot()

        @retry_util.WithRetry(
            max_retry=2,
            sleep=60.0,
            backoff_factor=2,
            exception=cros_build_lib.RunCommandError,
        )
        def _FlashWithRetry():
            self._Flash()

        self._Build()
        _FlashWithRetry()
        self._Deploy()

        returncode = self._RunTests()

        self._StopVM()
        return returncode

    def _StartVM(self):
        """Start a VM if necessary.

        If --start-vm is specified, we launch a new VM, otherwise we use an
        existing VM.
        """
        if not self._device.should_start_vm:
            return

        if not self._device.IsRunning():
            self.start_vm = True

        if self.start_vm:
            self._device.Start()

    def _StopVM(self):
        """Stop the VM if necessary.

        If --start-vm was specified, we launched this VM, so we now stop it.
        """
        if self._device and self.start_vm:
            self._device.Stop()

    def _Build(self):
        """Build chrome."""
        if not self.build:
            return

        build_target = self.chrome_test_target or "chromiumos_preflight"
        cros_build_lib.run(
            ["autoninja", "-C", self.build_dir, build_target],
            dryrun=self.dryrun,
        )

    def _Flash(self):
        """Flash device."""
        if not self.flash:
            return

        version = xbuddy.LATEST
        if self.xbuddy:
            flash_path = self.xbuddy.format(board=self._device.board)
        else:
            flash_path = "xbuddy://remote/%s/%s" % (
                self._device.board,
                xbuddy.LATEST,
            )
            if (
                path_util.DetermineCheckout().type
                != path_util.CheckoutType.REPO
            ):
                # Try flashing to the full version of the board used in the
                # Simple Chrome SDK if it's present in the cache. Otherwise
                # default to using latest.
                cache = self.cache_dir or path_util.GetCacheDir()
                version = (
                    cros_chrome_sdk.SDKFetcher.GetCachedFullVersion(
                        cache, self._device.board
                    )
                    or version
                )
                if self.public_image:
                    flash_path = (
                        "gs://chromiumos-image-archive/%s-public/%s"
                        % (self._device.board, version)
                    )
                else:
                    flash_path = "gs://chromeos-image-archive/%s-release/%s" % (
                        self._device.board,
                        version,
                    )

        # Only considers skipping flashing if it's NOT for lacros-chrome tests
        # because at this time, automated/CI tests can't assume that ash-chrome
        # is left in a clean state and lacros-chrome depends on ash-chrome.
        if not self.deploy_lacros and xbuddy.LATEST not in flash_path:
            # Skip the flash if the device is already running the requested
            # version.
            device_version = self._device.remote.version
            # Split on the first "-" when comparing versions since xbuddy
            # requires the RX- prefix, but the device may not advertise it.
            if version == device_version or (
                "-" in version and version.split("-", 1)[1] == device_version
            ):
                logging.info(
                    "Skipping the flash. Device running %s when %s was "
                    "requested",
                    device_version,
                    flash_path,
                )
                return

        device_name = "ssh://" + self._device.device
        if self._device.ssh_port:
            device_name += ":" + str(self._device.ssh_port)
        flash_cmd = [
            constants.CHROMITE_BIN_DIR / "cros",
            "flash",
            device_name,
            flash_path,
            "--board",
            self._device.board,
            "--disable-rootfs-verification",
            "--clobber-stateful",
            "--clear-tpm-owner",
        ]
        cros_build_lib.run(flash_cmd, dryrun=self.dryrun)

    def _Deploy(self):
        """Deploy binary files to device."""
        if not self.build and not self.deploy and not self.deploy_lacros:
            return

        if self.chrome_test:
            self._DeployChromeTest()
        else:
            if self.deploy and self.deploy_lacros:
                self._DeployChrome(self.build_dir, False)
                self._DeployChrome(self.additional_lacros_build_dir, True)
            else:
                self._DeployChrome(self.build_dir, self.deploy_lacros)

        if self.deploy_lacros:
            self._DeployLacrosLauncherScript()

    def _DeployChrome(self, build_dir, is_lacros):
        """Deploy lacros-chrome or ash-chrome.

        Args:
            build_dir: str the build dir contains chrome binary.
            is_lacros: bool whether it's lacros or ash.
        """
        deploy_cmd = [
            "deploy_chrome",
            "--force",
            "--build-dir",
            build_dir,
            "--process-timeout",
            "180",
        ]
        if self._device.ssh_port:
            deploy_cmd += [
                "--device",
                "%s:%d" % (self._device.device, self._device.ssh_port),
            ]
        else:
            deploy_cmd += ["--device", self._device.device]

        if self.cache_dir:
            deploy_cmd += ["--cache-dir", self.cache_dir]

        if is_lacros:
            # By default, deploying lacros-chrome modifies the
            # /etc/chrome_dev.conf file, which is desired behavior for local
            # development, however, a modified config file interferes with
            # automated testing.
            deploy_cmd += [
                "--lacros",
                "--nostrip",
                "--skip-modifying-config-file",
            ]
        else:
            deploy_cmd.append("--deploy-test-binaries")
            if self._device.board:
                deploy_cmd += ["--board", self._device.board]
            if self.nostrip:
                deploy_cmd += ["--nostrip"]
            if self.mount:
                deploy_cmd += ["--mount"]
            if self.public_image:
                deploy_cmd += ["--use-external-config"]

        cros_build_lib.run(deploy_cmd, dryrun=self.dryrun)
        self._device.WaitForBoot()

    def _DeployChromeTest(self):
        """Deploy chrome test binary and its runtime files to device."""
        src_dir = os.path.dirname(os.path.dirname(self.build_dir))
        self._DeployCopyPaths(
            src_dir,
            self.chrome_test_deploy_target_dir,
            chrome_util.GetChromeTestCopyPaths(
                self.build_dir, self.chrome_test_target
            ),
        )

    def _DeployLacrosLauncherScript(self):
        """Deploy a script that is needed to launch Lacros in Tast tests."""
        self._DeployCopyPaths(
            os.path.dirname(self.lacros_launcher_script),
            "/usr/local/bin",
            [chrome_util.Path(os.path.basename(self.lacros_launcher_script))],
        )

    def _DeployCopyPaths(self, host_src_dir, remote_target_dir, copy_paths):
        """Deploy files in copy_paths to device.

        Args:
            host_src_dir: Source dir on the host that files in |copy_paths| are
                relative to.
            remote_target_dir: Target dir on the remote device that the files in
                |copy_paths| are copied to.
            copy_paths: A list of chrome_utils.Path of files to be copied.
        """

        # The rsync connection can occasionally crash during the transfer, so
        # retry in the hope that it's transient.
        @retry_util.WithRetry(max_retry=3, sleep=1, backoff_factor=2)
        def copy_with_retries():
            if self._device.remote.HasRsync():
                self._device.remote.CopyToDevice(
                    "%s/" % os.path.abspath(self.staging_dir),
                    remote_target_dir,
                    mode="rsync",
                    inplace=True,
                    compress=True,
                    debug_level=logging.INFO,
                )
            else:
                self._device.remote.CopyToDevice(
                    "%s/" % os.path.abspath(self.staging_dir),
                    remote_target_dir,
                    mode="scp",
                    debug_level=logging.INFO,
                )

        with osutils.TempDir(set_global=True) as tempdir:
            self.staging_dir = tempdir
            strip_bin = None
            chrome_util.StageChromeFromBuildDir(
                self.staging_dir, host_src_dir, strip_bin, copy_paths=copy_paths
            )
            copy_with_retries()

    def _RunCatapultTests(self):
        """Run catapult tests matching a pattern using run_tests.

        Returns:
            cros_build_lib.CompletedProcess object.
        """

        browser = "system-guest" if self.guest else "system"
        return self._device.run(
            [
                "python",
                "/usr/local/telemetry/src/third_party/catapult/telemetry/bin/"
                "run_tests",
                "--browser=%s" % browser,
            ]
            + self.catapult_tests,
            stream_output=True,
        )

    def _RunAutotest(self):
        """Run an autotest using test_that.

        Returns:
            cros_build_lib.CompletedProcess object.
        """
        cmd = ["test_that"]
        if self._device.board:
            cmd += ["--board", self._device.board]
        if self.results_dir:
            cmd += ["--results_dir", path_util.ToChrootPath(self.results_dir)]
        if self._device.private_key:
            cmd += [
                "--ssh_private_key",
                path_util.ToChrootPath(self._device.private_key),
            ]
        if self._device.log_level == "debug":
            cmd += ["--debug"]
        if self.test_that_args:
            cmd += self.test_that_args[1:]
        cmd += [
            "--no-quickmerge",
            "--ssh_options",
            "-F /dev/null -i /dev/null",
        ]
        if self._device.ssh_port:
            cmd += ["%s:%d" % (self._device.device, self._device.ssh_port)]
        else:
            cmd += [self._device.device]
        cmd += self.autotest
        return cros_build_lib.run(cmd, dryrun=self.dryrun, enter_chroot=True)

    def _RunTastTests(self):
        """Run Tast tests.

        Returns:
            cros_build_lib.CompletedProcess object.
        """
        # Try using the Tast binaries that the SimpleChrome SDK downloads
        # automatically.
        autotest_pkg_dir = cros_chrome_sdk.SDKFetcher.GetCachePath(
            commands.AUTOTEST_SERVER_PACKAGE,
            self.cache_dir,
            self._device.board,
        )
        if autotest_pkg_dir:
            cmd = [os.path.join(autotest_pkg_dir, "tast", "run_tast.sh")]
            need_chroot = False
        else:
            # Silently fall back to using the chroot if there's no SimpleChrome
            # SDK present.
            cmd = ["tast"]
            if self._device.log_level == "debug":
                cmd += ["-verbose"]
            cmd += ["run"]
            need_chroot = True
        cmd += [
            "-build=false",
            "-waituntilready",
            # Skip tests depending on private runtime variables.
            # 'gs://chromeos-prebuilt/board/amd64-host/.../
            # chromeos-base/tast-vars*'
            # doesn't contain runtime variable files in the tast-tests-private
            # repository.
            r"-maybemissingvars=.+\..+",
        ]
        # If the tests are not informational, then fail on test failure.
        # TODO(dhanyaganesh@): Make this less hack-y crbug.com/1034403.
        if "!informational" in self.tast[0]:
            cmd += ["-failfortests"]
        if not need_chroot:
            private_key = (
                self._device.private_key
                or self._device.remote.agent.private_keys[-1]
            )
            assert private_key, "ssh private key not found."
            cmd += [
                "-ephemeraldevserver=true",
                "-keyfile",
                private_key,
                "-maxtestfailures=10",
            ]
            # Tast may make calls to gsutil during the tests. If we're outside
            # the chroot, we may not have gsutil on PATH. So push chromite's
            # copy of gsutil onto path during the test.
            gsutil_dir = constants.CHROMITE_SCRIPTS_DIR
            extra_env = {
                "PATH": os.environ.get("PATH", "") + ":" + str(gsutil_dir)
            }
        else:
            extra_env = None

        if self.test_timeout > 0:
            cmd += ["-timeout=%d" % self.test_timeout]
        if (
            self._device.should_start_vm
            and "tast_vm" not in self.tast_extra_use_flags
        ):
            # The 'tast_vm' flag is needed when running Tast tests on VMs. Note
            # that this check is only true if we're handling VM
            # start-up/tear-down ourselves for the duration of the test. If the
            # caller has already launched a VM themselves and has pointed the
            # '--device' arg at it, this check will be false.
            self.tast_extra_use_flags.append("tast_vm")
        if self.tast_extra_use_flags:
            cmd += ["-extrauseflags=%s" % ",".join(self.tast_extra_use_flags)]
        if self.results_dir:
            results_dir = self.results_dir
            if need_chroot:
                results_dir = path_util.ToChrootPath(self.results_dir)
            cmd += ["-resultsdir", results_dir]
        if self.tast_vars:
            cmd += ["-var=%s" % v for v in self.tast_vars]
        if self.tast_total_shards:
            cmd += [
                "-totalshards=%d" % self.tast_total_shards,
                "-shardindex=%d" % self.tast_shard_index,
            ]
        if self.tast_retries:
            cmd += ["-retries=%d" % self.tast_retries]
        if self.tast_shard_method:
            cmd += ["-shardmethod=%s" % self.tast_shard_method]
        if self._device.ssh_port:
            cmd += ["%s:%d" % (self._device.device, self._device.ssh_port)]
        else:
            cmd += [self._device.device]
        cmd += self.tast
        return cros_build_lib.run(
            cmd,
            dryrun=self.dryrun,
            extra_env=extra_env,
            # Don't raise an exception if the command fails.
            check=False,
            enter_chroot=need_chroot and not cros_build_lib.IsInsideChroot(),
        )

    def _RunTests(self):
        """Run tests.

        Run user-specified tests, catapult tests, tast tests, autotest, or the
        default, vm_sanity.

        Returns:
            Command execution return code.
        """
        if self.remote_cmd:
            result = self._RunDeviceCmd()
        elif self.host_cmd:
            extra_env = {}
            if self.build_dir:
                extra_env["CHROMIUM_OUTPUT_DIR"] = self.build_dir
            # Don't raise an exception if the command fails.
            result = cros_build_lib.run(
                self.args, check=False, dryrun=self.dryrun, extra_env=extra_env
            )
        elif self.catapult_tests:
            result = self._RunCatapultTests()
        elif self.autotest:
            result = self._RunAutotest()
        elif self.tast:
            result = self._RunTastTests()
        elif self.chrome_test:
            result = self._RunChromeTest()
        else:
            result = self._device.run(
                ["/usr/local/autotest/bin/vm_sanity.py"], stream_output=True
            )

        self._MaybeSaveVMImage(result)
        self._FetchResults()

        name = self.args[0] if self.args else "Test process"
        logging.info("%s exited with status code %d.", name, result.returncode)

        return result.returncode

    def _MaybeSaveVMImage(self, result):
        """Tells the VM to save its image on shutdown if the test failed.

        Args:
            result: A cros_build_lib.CompletedProcess object from a test run.
        """
        if (
            not self._device.should_start_vm
            or not self.save_snapshot_on_failure
        ):
            return
        if not result.returncode:
            return
        osutils.SafeMakedirs(self.results_dest_dir)
        self._device.SaveVMImageOnShutdown(self.results_dest_dir)

    def _FetchResults(self):
        """Fetch results files/directories."""
        if not self.results_src:
            return
        osutils.SafeMakedirs(self.results_dest_dir)
        for src in self.results_src:
            logging.info("Fetching %s to %s", src, self.results_dest_dir)
            # Don't raise an error if the filepath doesn't exist on the device
            # since some log/crash directories are only created under certain
            # conditions. e.g. When a user logs in.
            self._device.remote.CopyFromDevice(
                src=src,
                dest=self.results_dest_dir,
                mode="scp",
                debug_level=logging.INFO,
                ignore_failures=True,
            )

    def _AuthorizeKeys(self):
        """Authorize the test ssh keys with chronos."""
        # With "nosymfollow" mount option present in /home/chronos/user/,
        # "-L" is required and it will copy symbolic links as real files.
        self._device.run(
            ["cp", "-L", "-r", "/root/.ssh/", "/home/chronos/user/"]
        )

    def _RunDeviceCmd(self):
        """Run a command on the device.

        Copy src files to /usr/local/cros_test/, change working directory to
        self.cwd, run the command in self.args, and cleanup.

        Returns:
            cros_build_lib.CompletedProcess object.
        """
        DEST_BASE = "/usr/local/cros_test"
        files = FileList(self.files, self.files_from)
        # Copy files, preserving the directory structure.
        copy_paths = []
        for f in files:
            is_exe = os.path.isfile(f) and os.access(f, os.X_OK)
            has_exe = False
            if os.path.isdir(f):
                if not f.endswith("/"):
                    f += "/"
                for sub_dir, _, sub_files in os.walk(f):
                    for sub_file in sub_files:
                        if os.access(os.path.join(sub_dir, sub_file), os.X_OK):
                            has_exe = True
                            break
                    if has_exe:
                        break
            copy_paths.append(chrome_util.Path(f, exe=is_exe or has_exe))
        if copy_paths:
            self._DeployCopyPaths(os.getcwd(), DEST_BASE, copy_paths)

        # Make cwd an absolute path (if it isn't one) rooted in DEST_BASE.
        cwd = self.cwd
        if files and not (cwd and os.path.isabs(cwd)):
            cwd = os.path.join(DEST_BASE, cwd) if cwd else DEST_BASE
            self._device.mkdir(cwd)

        if self.as_chronos:
            self._AuthorizeKeys()
            if files:
                # The trailing ':' after the user also changes the group to the
                # user's primary group.
                self._device.run(["chown", "-R", "chronos:", DEST_BASE])

        user = "chronos" if self.as_chronos else None
        if cwd:
            # Run the remote command with cwd.
            cmd = "cd %s && %s" % (cwd, " ".join(self.args))
            # Pass shell=True because of && in the cmd.
            result = self._device.run(
                cmd, stream_output=True, shell=True, remote_user=user
            )
        else:
            result = self._device.run(
                self.args, stream_output=True, remote_user=user
            )

        # Cleanup.
        if self.clean and files:
            self._device.run(["rm", "-rf", DEST_BASE])

        return result

    def _RunChromeTest(self):
        # Stop UI in case the test needs to grab GPU.
        self._device.run(["stop", "ui"])

        # Send a user activity ping to powerd to light up the display.
        self._device.run(
            [
                "dbus-send",
                "--system",
                "--type=method_call",
                "--dest=org.chromium.PowerManager",
                "/org/chromium/PowerManager",
                "org.chromium.PowerManager.HandleUserActivity",
                "int32:0",
            ]
        )

        # Authorize ssh keys for user chronos.
        self._AuthorizeKeys()

        # Run test.
        chrome_src_dir = os.path.dirname(os.path.dirname(self.build_dir))
        test_binary = os.path.relpath(
            os.path.join(self.build_dir, self.chrome_test_target),
            chrome_src_dir,
        )
        test_args = self.args[1:]
        command = "cd %s && %s %s" % (
            self.chrome_test_deploy_target_dir,
            test_binary,
            " ".join(test_args),
        )
        result = self._device.run(
            command, stream_output=True, remote_user="chronos"
        )
        return result


def ParseCommandLine(argv):
    """Parse the command line.

    Args:
        argv: Command arguments.

    Returns:
        List of parsed options for CrOSTest.
    """

    parser = vm.VM.GetParser()
    parser.add_argument(
        "--start-vm",
        action="store_true",
        default=False,
        help="Start a new VM before running tests.",
    )
    parser.add_argument(
        "--catapult-tests",
        nargs="+",
        help="Catapult test pattern to run, passed to run_tests.",
    )
    parser.add_argument(
        "--autotest",
        nargs="+",
        help="Autotest test pattern to run, passed to test_that.",
    )
    parser.add_argument(
        "--tast",
        nargs="+",
        help="Tast test pattern to run, passed to tast. "
        "See go/tast-running for patterns.",
    )
    parser.add_argument(
        "--tast-var",
        dest="tast_vars",
        action="append",
        help="Runtime variables for Tast tests, and the format "
        'are expected to be "key=value" pairs.',
    )
    parser.add_argument(
        "--tast-shard-index",
        type=int,
        default=0,
        help="Shard index to use when running Tast tests.",
    )
    parser.add_argument(
        "--tast-total-shards",
        type=int,
        default=0,
        help="Total number of shards when running Tast tests.",
    )
    parser.add_argument(
        "--tast-shard-method",
        help="The sharding algorithm used for Tast tests.",
    )
    parser.add_argument(
        "--tast-retries",
        type=int,
        default=0,
        help="Number of retries for failed Tast tests.",
    )
    parser.add_argument(
        "--tast-extra-use-flags",
        help="Comma-separated list of extra USE flags to pass to "
        "Tast when running tests.",
    )
    parser.add_argument(
        "--chrome-test",
        action="store_true",
        default=False,
        help="Run chrome test on device. The first arg in the "
        "remote command should be the test binary name, such as "
        "interactive_ui_tests. It is used for building and "
        "collecting runtime deps files.",
    )
    parser.add_argument(
        "--guest",
        action="store_true",
        default=False,
        help="Run tests in incognito mode.",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        default=False,
        help="Before running tests, build chrome using ninja, "
        "--build-dir must be specified.",
    )
    parser.add_argument(
        "--build-dir",
        type="path",
        help="Directory for building and deploying chrome.",
    )
    parser.add_argument(
        "--flash",
        action="store_true",
        default=False,
        help="Before running tests, flash the device.",
    )
    parser.add_argument(
        "--public-image",
        action="store_true",
        default=False,
        help="Flash with a public image.",
    )
    parser.add_argument(
        "--xbuddy",
        help="xbuddy link to use for flashing the device. Will "
        "default to the board's version used in the cros "
        'chrome-sdk if available, or "latest" otherwise.',
    )
    parser.add_argument(
        "--deploy-lacros",
        action="store_true",
        default=False,
        help="Before running tests, deploy lacros-chrome, "
        "--build-dir must be specified.",
    )
    parser.add_argument(
        "--lacros-launcher-script",
        type=str,
        help="Absolute path to a python script needed to launch "
        "Lacros in tast tests.",
    )
    parser.add_argument(
        "--deploy",
        action="store_true",
        default=False,
        help="Before running tests, deploy ash-chrome, "
        "--build-dir must be specified.",
    )
    parser.add_argument(
        "--nostrip",
        action="store_true",
        default=False,
        help="Don't strip symbols from binaries if deploying.",
    )
    parser.add_argument(
        "--mount",
        action="store_true",
        default=False,
        help="Deploy ash-chrome to the default target directory "
        "and bind it to the default mount directory. Useful for "
        "large ash-chrome binaries.",
    )
    # type='path' converts a relative path for cwd into an absolute one on the
    # host, which we don't want.
    parser.add_argument(
        "--cwd",
        help="Change working directory. "
        "An absolute path or a path relative to CWD on the host.",
    )
    parser.add_argument(
        "--files",
        default=[],
        action="append",
        help="Files to scp to the device.",
    )
    parser.add_argument(
        "--files-from", type="path", help="File with list of files to copy."
    )
    parser.add_argument(
        "--results-src",
        default=[],
        action="append",
        help="Files/Directories to copy from "
        "the device into CWD after running the test.",
    )
    parser.add_argument(
        "--results-dest-dir",
        type="path",
        help="Destination directory to copy results to.",
    )
    parser.add_argument(
        "--remote-cmd",
        action="store_true",
        default=False,
        help="Run a command on the device.",
    )
    parser.add_argument(
        "--as-chronos",
        action="store_true",
        help="Runs the remote test as the chronos user on "
        "the device. Only supported for --remote-cmd tests. "
        "Runs as root if not set.",
    )
    parser.add_argument(
        "--host-cmd",
        action="store_true",
        default=False,
        help="Run a command on the host.",
    )
    parser.add_argument(
        "--results-dir", type="path", help="Autotest results directory."
    )
    parser.add_argument(
        "--test_that-args",
        action="append_option_value",
        help="Args to pass directly to test_that for autotest.",
    )
    parser.add_argument(
        "--test-timeout",
        type=int,
        default=0,
        help="Timeout for running all tests (for --tast).",
    )
    parser.add_argument(
        "--save-snapshot-on-failure",
        action="store_true",
        default=False,
        help="Save a snapshot of the VM on test failure to "
        "results-dest-dir.",
    )
    parser.add_bool_argument(
        "--clean",
        default=True,
        enabled_desc="Clean up the deployed files after running the test. "
        "Only supported for --remote-cmd tests",
        disabled_desc="Do not clean up the deployed files after running the "
        "test. Only supported for --remote-cmd tests",
    )

    opts = parser.parse_args(argv)

    if opts.device and opts.device.port and opts.ssh_port:
        parser.error(
            "Must not specify SSH port via both --ssh-port and --device."
        )

    if opts.chrome_test:
        if not opts.args:
            parser.error("Must specify a test command with --chrome-test")

        if not opts.build_dir:
            opts.build_dir = os.path.dirname(opts.args[1])

    if opts.build or opts.deploy or opts.deploy_lacros:
        if not opts.build_dir:
            parser.error("Must specify --build-dir with --build or --deploy.")
        if not os.path.isdir(opts.build_dir):
            parser.error("%s is not a directory." % opts.build_dir)

    if opts.tast_vars and not opts.tast:
        parser.error("--tast-var is only applicable to Tast tests.")

    if opts.tast_retries and not opts.tast:
        parser.error("--tast-retries is only applicable to Tast tests.")

    if opts.deploy_lacros and opts.deploy:
        additional_lacros_build_dir = os.path.join(
            opts.build_dir, _ADDITIONAL_LACROS_SUBDIR
        )
        if not os.path.exists(additional_lacros_build_dir):
            parser.error(
                "Script will deploy both Ash and Lacros but can not find "
                f"Lacros at {additional_lacros_build_dir}"
            )

    if bool(opts.deploy_lacros) != bool(opts.lacros_launcher_script):
        parser.error(
            "--lacros-launcher-script is required when running Lacros tests."
        )

    if opts.results_src:
        for src in opts.results_src:
            if not os.path.isabs(src):
                parser.error("results-src must be absolute.")
        if not opts.results_dest_dir:
            parser.error("results-dest-dir must be specified with results-src.")
    if opts.results_dest_dir:
        if not opts.results_src:
            parser.error("results-src must be specified with results-dest-dir.")
        if os.path.isfile(opts.results_dest_dir):
            parser.error(
                "results-dest-dir %s is an existing file."
                % opts.results_dest_dir
            )

    if opts.save_snapshot_on_failure and not opts.results_dest_dir:
        parser.error(
            "Must specify results-dest-dir with save-snapshot-on-failure"
        )

    # Ensure command is provided. For e.g. to copy out to the device and run
    # out/unittest:
    # cros_run_test --files out --cwd out --cmd -- ./unittest
    # Treat --cmd as --remote-cmd.
    opts.remote_cmd = opts.remote_cmd or opts.cmd
    if (opts.remote_cmd or opts.host_cmd) and len(opts.args) < 2:
        parser.error("Must specify test command to run.")
    if opts.as_chronos and not opts.remote_cmd:
        parser.error("as-chronos only supported when running test commands.")
    # Verify additional args.
    if opts.args:
        if not opts.remote_cmd and not opts.host_cmd and not opts.chrome_test:
            parser.error(
                "Additional args may be specified with either "
                "--remote-cmd or --host-cmd or --chrome-test: %s" % opts.args
            )
        if opts.args[0] != "--":
            parser.error("Additional args must start with '--': %s" % opts.args)

    # Verify CWD.
    if opts.cwd:
        if opts.cwd.startswith(".."):
            parser.error("cwd cannot start with ..")
        if (
            not os.path.isabs(opts.cwd)
            and not opts.files
            and not opts.files_from
        ):
            parser.error(
                "cwd must be an absolute path if "
                "--files or --files-from is not specified"
            )

    # Verify files.
    if opts.files_from:
        if opts.files:
            parser.error("--files and --files-from cannot both be specified")
        if not os.path.isfile(opts.files_from):
            parser.error("%s is not a file" % opts.files_from)
    files = FileList(opts.files, opts.files_from)
    for f in files:
        if os.path.isabs(f):
            parser.error("%s should be a relative path" % f)
        # Restrict paths to under CWD on the host. See crbug.com/829612.
        if f.startswith(".."):
            parser.error("%s cannot start with .." % f)
        if not os.path.exists(f):
            parser.error("%s does not exist" % f)

    # Verify Tast.
    if opts.tast_shard_index or opts.tast_total_shards:
        if not opts.tast:
            parser.error(
                "Can only specify --tast-total-shards and "
                "--tast-shard-index with --tast."
            )
        if opts.tast_shard_index >= opts.tast_total_shards:
            parser.error("Shard index must be < total shards.")

    return opts


def FileList(files, files_from):
    """Get list of files from command line args --files and --files-from.

    Args:
        files: files specified directly on the command line.
        files_from: files specified in a file.

    Returns:
        Contents of files_from if it exists, otherwise files.
    """
    if files_from and os.path.isfile(files_from):
        with open(files_from, encoding="utf-8") as f:
            files = [line.rstrip() for line in f]
    return files
