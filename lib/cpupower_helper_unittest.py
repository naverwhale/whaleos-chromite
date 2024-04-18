# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the cpupower_helper module."""

from pathlib import Path

from chromite.lib import chromite_config
from chromite.lib import cpupower_helper
from chromite.lib import cros_test_lib
from chromite.lib import partial_mock


class TestCpuGovernorSwitch(
    cros_test_lib.MockTempDirTestCase,
    cros_test_lib.RunCommandTestCase,
    cros_test_lib.LoggingTestCase,
):
    """Tests the CPU Governor switch context"""

    def setUp(self):
        D = cros_test_lib.Directory
        config_dir_name = chromite_config.DIR.name
        cpu_policy_files = (
            D(config_dir_name, ()),
            D(
                "cpu",
                (
                    D(
                        "cpufreq",
                        (
                            D("policy0", ("scaling_governor",)),
                            D("policy1", ("scaling_governor",)),
                        ),
                    ),
                    D(
                        "cpu0",
                        (D("cpufreq", ("scaling_available_governors",)),),
                    ),
                ),
            ),
        )
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, cpu_policy_files)

        cfg_dir = self.tempdir / config_dir_name
        self.config_file = cfg_dir / chromite_config.AUTO_SET_GOV_CONFIG.name
        self.PatchObject(chromite_config, "DIR", new=cfg_dir)
        for cfg_name, cfg_file in chromite_config.ALL_CONFIGS.items():
            self.PatchObject(chromite_config, cfg_name, cfg_dir / cfg_file)

        self.PatchObject(cpupower_helper, "_CPU_PATH", new=self.tempdir / "cpu")

        self.cpu0_available_gov = Path(
            "cpu/cpu0/cpufreq/scaling_available_governors"
        )
        self.cpu0_scaling_gov = Path("cpu/cpufreq/policy0/scaling_governor")
        self.cpu1_scaling_gov = Path("cpu/cpufreq/policy1/scaling_governor")
        self.WriteTempFile(
            self.cpu0_available_gov, "powersave performance ondemand"
        )
        self.WriteTempFile(self.cpu0_scaling_gov, "powersave")
        self.WriteTempFile(self.cpu1_scaling_gov, "powersave")

        # pylint: disable=protected-access
        self.perf_cmd = cpupower_helper._CPUPOWER_CMD + ["performance"]
        self.power_cmd = cpupower_helper._CPUPOWER_CMD + ["powersave"]
        self.ondemand_cmd = cpupower_helper._CPUPOWER_CMD + ["ondemand"]

    def testCpuPerfSwitchSticky(self):
        """This tests ondemand governor as default with sticky."""
        self.WriteTempFile(self.cpu0_scaling_gov, "ondemand")
        self.WriteTempFile(self.cpu1_scaling_gov, "ondemand")
        with cpupower_helper.ModifyCpuGovernor(perf_governor=True, sticky=True):
            self.assertCommandContains(self.perf_cmd)
        self.assertCommandContains(self.ondemand_cmd)
        # pylint: disable=protected-access
        self.assertTempFileContents(
            self.config_file, cpupower_helper._AUTO_SET_GOV_CONTENT
        )

    def testCpuPerfSwitchOndemand(self):
        """This tests ondemand governor as default and no sticky."""
        self.WriteTempFile(self.cpu0_scaling_gov, "ondemand")
        self.WriteTempFile(self.cpu1_scaling_gov, "ondemand")
        with cpupower_helper.ModifyCpuGovernor(
            perf_governor=True, sticky=False
        ):
            self.assertCommandContains(self.perf_cmd)
        self.assertCommandContains(self.ondemand_cmd)
        self.assertNotExists(self.config_file)

    def testCpuPerfSwitchPowersave(self):
        """This tests powersave governor as default and no sticky."""
        with cpupower_helper.ModifyCpuGovernor(
            perf_governor=True, sticky=False
        ):
            self.assertCommandContains(self.perf_cmd)
        self.assertCommandContains(self.power_cmd)
        self.assertNotExists(self.config_file)

    def testCpuPerfNoSwitchPerformance(self):
        """This tests performance governor as default."""
        self.WriteTempFile(self.cpu0_scaling_gov, "performance")
        self.WriteTempFile(self.cpu1_scaling_gov, "performance")
        with cpupower_helper.ModifyCpuGovernor(
            perf_governor=True, sticky=False
        ):
            pass
        self.assertNotExists(self.config_file)
        self.assertFalse(self.rc.called)

    def testCpuPerfNoSwitch(self):
        """This tests powersave governor as default and no config file."""
        with cros_test_lib.LoggingCapturer() as logs:
            with cpupower_helper.ModifyCpuGovernor(
                perf_governor=False, sticky=False
            ):
                for logSnippet in (
                    "Current CPU governor.*slow down",
                    "Use --autosetgov",
                ):
                    self.AssertLogsMatch(logs, logSnippet)
            self.assertNotExists(self.config_file)
            self.assertFalse(self.rc.called)

    def testCpuPerfSwitchWithConfig(self):
        """This tests powersave governor as default and with config file."""
        # pylint: disable=protected-access
        self.WriteTempFile(
            self.config_file, cpupower_helper._AUTO_SET_GOV_CONTENT
        )
        with cpupower_helper.ModifyCpuGovernor(
            perf_governor=False, sticky=False
        ):
            self.assertCommandContains(self.perf_cmd)
        self.assertCommandContains(self.power_cmd)
        self.assertTempFileContents(
            self.config_file, cpupower_helper._AUTO_SET_GOV_CONTENT
        )

    def testCpuPerfMultipleGovernor(self):
        """This tests multiple governors as default."""
        self.WriteTempFile(self.cpu0_scaling_gov, "powersave")
        self.WriteTempFile(self.cpu1_scaling_gov, "ondemand")
        with cpupower_helper.ModifyCpuGovernor(perf_governor=True, sticky=True):
            pass
        self.assertFalse(self.rc.called)
        # pylint: disable=protected-access
        self.assertTempFileContents(
            self.config_file, cpupower_helper._AUTO_SET_GOV_CONTENT
        )

    def testCpuPerfRemove(self):
        """This tests Perf governor sticky remove."""
        # pylint: disable=protected-access
        self.WriteTempFile(
            self.config_file, cpupower_helper._AUTO_SET_GOV_CONTENT
        )
        with cpupower_helper.ModifyCpuGovernor(
            perf_governor=False, sticky=True
        ):
            pass
        self.assertNotExists(self.config_file)
        self.assertFalse(self.rc.called)

    def testCpuPerfNotSupported(self):
        """This tests Perf governor is not supported case."""
        self.WriteTempFile(self.cpu0_available_gov, "powersave ondemand")
        with cpupower_helper.ModifyCpuGovernor(perf_governor=True, sticky=True):
            pass
        self.assertFalse(self.rc.called)
        # pylint: disable=protected-access
        self.assertTempFileContents(
            self.config_file, cpupower_helper._AUTO_SET_GOV_CONTENT
        )

    def testCpuPerfRunException(self):
        """This tests Perf governor switch with run command Exception."""
        self.rc.AddCmdResult(partial_mock.In("cpupower"), returncode=1)
        with cros_test_lib.LoggingCapturer() as logs:
            with cpupower_helper.ModifyCpuGovernor(
                perf_governor=True, sticky=True
            ):
                self.AssertLogsMatch(logs, "Error.*CPU governors.*")
                self.assertCommandContains(self.perf_cmd)
            self.assertCommandContains(self.power_cmd)
            self.AssertLogsMatch(logs, "Error.*CPU governors.*")
        # pylint: disable=protected-access
        self.assertTempFileContents(
            self.config_file, cpupower_helper._AUTO_SET_GOV_CONTENT
        )


class TestNoCpuGovernors(
    cros_test_lib.MockTempDirTestCase,
    cros_test_lib.RunCommandTestCase,
    cros_test_lib.LoggingTestCase,
):
    """Tests when there are no CPU governors."""

    def setUp(self):
        D = cros_test_lib.Directory
        config_dir_name = chromite_config.DIR.name
        cpu_policy_files = (D(config_dir_name, ()),)
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, cpu_policy_files)

        cfg_dir = self.tempdir / config_dir_name
        self.config_file = cfg_dir / chromite_config.AUTO_SET_GOV_CONFIG.name
        self.PatchObject(chromite_config, "DIR", new=cfg_dir)
        for cfg_name, cfg_file in chromite_config.ALL_CONFIGS.items():
            self.PatchObject(chromite_config, cfg_name, cfg_dir / cfg_file)
        self.PatchObject(cpupower_helper, "_CPU_PATH", new=self.tempdir / "cpu")

    def testNoCpuGovernorFile(self):
        """Test when the scaling governor path file does not exist."""
        with cros_test_lib.LoggingCapturer() as logs:
            with cpupower_helper.ModifyCpuGovernor(
                perf_governor=True, sticky=True
            ):
                self.AssertLogsContain(
                    logs, "Error reading CPU scaling governor file"
                )
        self.assertFalse(self.rc.called)
