# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for toolchain_util."""

import base64
import collections
import datetime
import fnmatch
import glob
import json
import os
from pathlib import Path
import shutil
import time
from unittest import mock

from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import gob_util
from chromite.lib import gs
from chromite.lib import osutils
from chromite.lib import partial_mock
from chromite.lib import toolchain_util
from chromite.lib.parser import package_info


# pylint: disable=protected-access

_input_artifact = collections.namedtuple(
    "_input_artifact", ["name", "gs_locations"]
)


class ProfilesNameHelperTest(cros_test_lib.MockTempDirTestCase):
    """Test the helper functions related to naming."""

    # pylint: disable=protected-access
    def testParseBenchmarkProfileName(self):
        """Test top-level function _ParseBenchmarkProfileName."""
        # Test parse failure
        profile_name_to_fail = "this_is_an_invalid_name"
        with self.assertRaises(
            toolchain_util.ProfilesNameHelperError
        ) as context:
            toolchain_util._ParseBenchmarkProfileName(profile_name_to_fail)
        self.assertIn(
            "Unparseable benchmark profile name:", str(context.exception)
        )

        # Test parse success
        profile_name = "chromeos-chrome-amd64-77.0.3849.0_rc-r1.afdo"
        result = toolchain_util._ParseBenchmarkProfileName(profile_name)
        self.assertEqual(
            result,
            toolchain_util.BenchmarkProfileVersion(
                major=77,
                minor=0,
                build=3849,
                patch=0,
                revision=1,
                is_merged=False,
            ),
        )

        # Test Arm parsing.
        profile_name = "chromeos-chrome-arm-77.0.3849.0_rc-r1.afdo"
        result = toolchain_util._ParseBenchmarkProfileName(profile_name)
        self.assertEqual(
            result,
            toolchain_util.BenchmarkProfileVersion(
                major=77,
                minor=0,
                build=3849,
                patch=0,
                revision=1,
                is_merged=False,
            ),
        )

    def testParseCWPProfileName(self):
        """Test top-level function _ParseCWPProfileName."""
        # Test parse failure
        profile_name_to_fail = "this_is_an_invalid_name"
        with self.assertRaises(
            toolchain_util.ProfilesNameHelperError
        ) as context:
            toolchain_util._ParseCWPProfileName(profile_name_to_fail)
        self.assertIn("Unparseable CWP profile name:", str(context.exception))

        # Test parse success
        profile_name = "R77-3809.38-1562580965.afdo.xz"
        result = toolchain_util._ParseCWPProfileName(profile_name)
        self.assertEqual(
            result,
            toolchain_util.CWPProfileVersion(
                major=77, build=3809, patch=38, clock=1562580965
            ),
        )

    def testParseMergedProfileName(self):
        """Test top-level function _ParseMergedProfileName."""
        # Test parse failure
        profile_name_to_fail = "this_is_an_invalid_name"
        with self.assertRaises(
            toolchain_util.ProfilesNameHelperError
        ) as context:
            toolchain_util._ParseMergedProfileName(profile_name_to_fail)
        self.assertIn("Unparseable merged AFDO name:", str(context.exception))

        # Test parse release AFDO success
        afdo_name = (
            "chromeos-chrome-amd64-atom-77-3809.38-1562580965"
            "-benchmark-77.0.3849.0-r1-redacted.afdo.xz"
        )
        result = toolchain_util._ParseMergedProfileName(afdo_name)
        self.assertEqual(
            result,
            (
                toolchain_util.BenchmarkProfileVersion(
                    major=77,
                    minor=0,
                    build=3849,
                    patch=0,
                    revision=1,
                    is_merged=False,
                ),
                toolchain_util.CWPProfileVersion(
                    major=77, build=3809, patch=38, clock=1562580965
                ),
            ),
        )
        # Test parse release Arm AFDO success
        afdo_name = (
            "chromeos-chrome-arm-none-77-3809.38-1562580965"
            "-benchmark-77.0.3849.0-r1-redacted.afdo.xz"
        )
        result = toolchain_util._ParseMergedProfileName(afdo_name)
        self.assertEqual(
            result,
            (
                toolchain_util.BenchmarkProfileVersion(
                    major=77,
                    minor=0,
                    build=3849,
                    patch=0,
                    revision=1,
                    is_merged=False,
                ),
                toolchain_util.CWPProfileVersion(
                    major=77, build=3809, patch=38, clock=1562580965
                ),
            ),
        )

    def testCompressAFDOFiles(self):
        """Test _CompressAFDOFiles()."""
        input_dir = "/path/to/inputs"
        output_dir = "/another/path/to/outputs"
        targets = ["input1", "/path/to/inputs/input2"]
        suffix = ".xz"
        self.PatchObject(cros_build_lib, "CompressFile")
        # Should raise exception because the input doesn't exist
        with self.assertRaises(RuntimeError) as context:
            toolchain_util._CompressAFDOFiles(
                targets, input_dir, output_dir, suffix
            )
        self.assertEqual(
            str(context.exception),
            "file %s to compress does not exist"
            % os.path.join(input_dir, targets[0]),
        )
        # Should pass
        self.PatchObject(os.path, "exists", return_value=True)
        # Return ~1MB profile size.
        self.PatchObject(os.path, "getsize", return_value=100000)
        toolchain_util._CompressAFDOFiles(
            targets, input_dir, output_dir, suffix
        )
        compressed_names = [os.path.basename(x) for x in targets]
        inputs = [os.path.join(input_dir, n) for n in compressed_names]
        outputs = [
            os.path.join(output_dir, n + suffix) for n in compressed_names
        ]
        calls = [mock.call(n, o) for n, o in zip(inputs, outputs)]
        cros_build_lib.CompressFile.assert_has_calls(calls)

    def testGetProfileAge(self):
        """Test top-level function _GetProfileAge()."""
        # Test unsupported artifact_type
        current_day_profile = "R0-0.0-%d" % int(time.time())
        with self.assertRaises(ValueError) as context:
            toolchain_util._GetProfileAge(
                current_day_profile, "unsupported_type"
            )
        self.assertEqual(
            "'unsupported_type' is currently not supported to check profile "
            "age.",
            str(context.exception),
        )

        # Test using profile of the current day.
        ret = toolchain_util._GetProfileAge(current_day_profile, "kernel_afdo")
        self.assertEqual(0, ret)

        # Test using profile from the last day.
        last_day_profile = "R0-0.0-%d" % int(time.time() - 86400)
        ret = toolchain_util._GetProfileAge(last_day_profile, "kernel_afdo")
        self.assertEqual(1, ret)


class PrepareBundleTest(cros_test_lib.RunCommandTempDirTestCase):
    """Setup code common to Prepare/Bundle class methods."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

        self.board = "chell"
        self.chroot = chroot_lib.Chroot(
            path=self.tempdir / "chroot",
            out_path=self.tempdir / "out",
        )
        osutils.SafeMakedirs(self.chroot.path)
        osutils.SafeMakedirs(self.chroot.tmp)
        self.sysroot = f"/build/{self.board}"
        self.sysroot_full_path = self.chroot.full_path("build", self.board)
        self.chrome_package = "chromeos-chrome"
        self.kernel_package = "chromeos-kernel-3_18"
        self.profile_info = {"arch": "amd64"}
        self.chrome_PV = "chromeos-base/chromeos-chrome-78.0.3893.0_rc-r1"
        self.chrome_ebuild = os.path.join(
            self.tempdir,
            "src",
            "third_party",
            "chromiumos-overlay",
            os.path.dirname(self.chrome_PV),
            "chromeos-chrome",
            f"{os.path.basename(self.chrome_PV)}.ebuild",
        )
        self.chrome_pkg = package_info.parse(self.chrome_PV)
        self.glob = self.PatchObject(
            glob, "glob", return_value=[self.chrome_ebuild]
        )
        self.rc.AddCmdResult(partial_mock.In("rm"), returncode=0)
        self.obj = toolchain_util._CommonPrepareBundle(
            "None",
            chroot=self.chroot,
            sysroot_path=self.sysroot,
            profile_info=self.profile_info,
        )
        self.gs_context = self.PatchObject(self.obj, "_gs_context")
        self.gsc_list = self.PatchObject(
            self.gs_context, "List", return_value=[]
        )
        self.data = (
            b"chromeos-chrome-amd64-atom-77-3809.38-1562580965"
            b"-benchmark-77.0.3849.0-r1-redacted.afdo.xz"
        )
        self.arch = "atom"
        self.fetch = self.PatchObject(
            gob_util, "FetchUrl", return_value=base64.encodebytes(self.data)
        )


class CommonPrepareBundleTest(PrepareBundleTest):
    """Test common Prepare/Bundle class methods."""

    def testGetEbuildInfo(self):
        """Verify that EbuildInfo is correctly returned."""
        self.glob.return_value = ["chromeos-chrome-96.0.4657.0_rc-r2.ebuild"]
        ret = self.obj._GetEbuildInfo("chromeos-chrome")
        self.assertEqual(ret.CPV.vr, "96.0.4657.0_rc-r2")
        self.assertEqual(ret.CPV.version, "96.0.4657.0_rc")
        self.assertEqual(ret.CPV.revision, 2)
        self.assertTrue(ret.CPV.with_version("96.0.4657.0_rc"))
        self.assertEqual(ret.CPV.category, "chromeos-base")
        self.assertEqual(ret.CPV.package, "chromeos-chrome")
        self.glob.assert_called_once()

    def testGetEbuildInfoWithoutRevision(self):
        """Verify that EbuildInfo is correctly returned."""
        self.glob.return_value = ["chromeos-chrome-96.0.4657.0_rc.ebuild"]
        ret = self.obj._GetEbuildInfo("chromeos-chrome")
        self.assertEqual(ret.CPV.vr, "96.0.4657.0_rc")
        self.assertEqual(ret.CPV.version, "96.0.4657.0_rc")
        self.assertEqual(ret.CPV.revision, 0)

    def testGetEbuildInfoWithMultipleChromes(self):
        self.glob.return_value = [
            "chromeos-chrome-78.0.3893.0.ebuild",
            "chromeos-chrome-78.0.3893.0_rc-r1.ebuild",
            "chromeos-chrome-78.0.3893.100_rc-r1.ebuild",
            "chromeos-chrome-78.0.3893.10_rc-r1.ebuild",
        ]
        ret = self.obj._GetEbuildInfo("chromeos-chrome")
        self.assertEqual(ret.CPV.vr, "78.0.3893.100_rc-r1")
        self.assertEqual(ret.CPV.version, "78.0.3893.100_rc")
        self.assertEqual(ret.CPV.revision, 1)

    def test_GetArtifactVersionInGob(self):
        """Test that we look in the right place in GoB."""
        self.assertRaises(
            ValueError, self.obj._GetArtifactVersionInGob, "badarch"
        )

        self.assertEqual(
            self.data.decode("utf-8"),
            self.obj._GetArtifactVersionInGob(self.arch),
        )
        self.fetch.assert_called_once_with(
            constants.EXTERNAL_GOB_HOST,
            "chromium/src/+/refs/tags/%s/chromeos/profiles/%s.afdo.newest.txt"
            "?format=text" % (self.chrome_pkg.version.split("_")[0], self.arch),
        )

        self.fetch.reset_mock()
        self.fetch.return_value = ""
        self.assertRaises(
            RuntimeError, self.obj._GetArtifactVersionInGob, self.arch
        )
        self.fetch.assert_called_once()


class PrepBundLatestAFDOArtifactTest(PrepareBundleTest):
    """Test related function to compare freshness of AFDO artifacts."""

    def setUp(self):
        self.board = "board"
        self.gs_url = "gs://path/to/any_gs_url"
        self.current_branch = "78"
        self.current_arch = "atom"
        self.MockListResult = collections.namedtuple(
            "MockListResult", ("url", "creation_time")
        )
        files_in_gs_bucket = [
            # Benchmark profiles
            ("chromeos-chrome-arm-78.0.3892.0_rc-r1.afdo.bz2", 1.0),
            ("chromeos-chrome-amd64-78.0.3893.0_rc-r1.afdo.bz2", 2.0),
            ("chromeos-chrome-amd64-78.0.3896.0_rc-r1.afdo.bz2", 1.0),  # Latest
            ("chromeos-chrome-amd64-78.0.3897.0_rc-r1-merged.afdo.bz2", 3.0),
            # CWP profiles
            ("R78-3869.38-1562580965.afdo.xz", 2.1),
            ("R78-3866.0-1570000000.afdo.xz", 1.1),  # Latest
            ("R77-3811.0-1580000000.afdo.xz", 3.1),
            # Kernel profiles
            ("R76-3869.38-1562580965.gcov.xz", 1.3),
            ("R76-3866.0-1570000000.gcov.xz", 2.3),  # Latest
        ]

        self.gs_list = [
            self.MockListResult(
                url=os.path.join(self.gs_url, x), creation_time=y
            )
            for x, y in files_in_gs_bucket
        ]
        self.gsc_list.return_value = self.gs_list

    def testValidBenchmarkProfileVersion(self):
        """Test that it returns None for unparsable profile name."""
        prof = "unparsable-file.data"
        ver_none = self.obj._ValidBenchmarkProfileVersion(prof)
        self.assertIsNone(ver_none)

    def testFindLatestAFDOArtifactPassWithBenchmarkAfdo(self):
        """Test _FindLatestAFDOArtifact returns latest benchmark AFDO."""
        latest_afdo = self.obj._FindLatestAFDOArtifact(
            [self.gs_url], self.obj._ValidBenchmarkProfileVersion
        )
        self.assertEqual(
            latest_afdo,
            os.path.join(
                self.gs_url, "chromeos-chrome-amd64-78.0.3896.0_rc-r1.afdo.bz2"
            ),
        )

    def testFindLatestAFDOArtifactPassWithBenchmarkAfdoArm(self):
        """Test _FindLatestAFDOArtifact returns latest benchmark Arm AFDO."""
        self.obj.arch = "arm"
        latest_afdo = self.obj._FindLatestAFDOArtifact(
            [self.gs_url], self.obj._ValidBenchmarkProfileVersion
        )
        self.assertEqual(
            latest_afdo,
            os.path.join(
                self.gs_url, "chromeos-chrome-arm-78.0.3892.0_rc-r1.afdo.bz2"
            ),
        )

    def testFindLatestAfdoArtifactOnPriorBranch(self):
        """Test that we find a file from prior branch when we have none."""
        self.obj._ebuild_info["chromeos-chrome"] = toolchain_util._EbuildInfo(
            path="path",
            CPV=package_info.parse(
                "chromeos-base/chromeos-chrome-79.0.3900.0_rc-r1"
            ),
        )
        latest_afdo = self.obj._FindLatestAFDOArtifact(
            [self.gs_url], self.obj._ValidBenchmarkProfileVersion
        )
        self.assertEqual(
            latest_afdo,
            os.path.join(
                self.gs_url,
                "chromeos-chrome-amd64-78.0.3896.0_rc-r1.afdo.bz2",
            ),
        )

    def testFindLatestAFDOArtifactFailToFindAnyFiles(self):
        """Test function fails when no files on current branch."""
        self.obj._ebuild_info["chromeos-chrome"] = toolchain_util._EbuildInfo(
            path="path",
            CPV=package_info.parse(
                "chromeos-base/chromeos-chrome-80.0.3950.0_rc-r1"
            ),
        )
        self.gsc_list.side_effect = gs.GSNoSuchKey("No files")
        with self.assertRaises(
            toolchain_util.NoProfilesInGsBucketError
        ) as context:
            self.obj._FindLatestAFDOArtifact(
                [self.gs_url], self.obj._ValidBenchmarkProfileVersion
            )
        self.assertEqual(
            "No files for branch 80 found in %s" % self.gs_url,
            str(context.exception),
        )

    def testFindLatestAFDOArtifactsFindMaxFromInvalidFiles(self):
        """Test function fails when finds only invalid files."""
        mock_gs_list = [
            self.MockListResult(
                # Invalid chrome version (not full).
                url=os.path.join(
                    self.gs_url, "chromeos-chrome-amd64-78.afdo.bz2"
                ),
                creation_time=1.0,
            )
        ]
        self.gsc_list.return_value = mock_gs_list
        with self.assertRaises(RuntimeError) as context:
            self.obj._FindLatestAFDOArtifact(
                [self.gs_url], self.obj._ValidBenchmarkProfileVersion
            )
        self.assertIn(
            "No valid latest artifact was found", str(context.exception)
        )


class PrepareForBuildHandlerTest(PrepareBundleTest):
    """Test PrepareForBuildHandler specific methods."""

    def setUp(self):
        self.artifact_type = "Unspecified"
        self.input_artifacts = {}
        self.kernel_version = "5_4"
        self.profile_info = {
            "arch": "amd64",
            "kernel_version": self.kernel_version.replace("_", "."),
        }
        self.gsc_exists = None
        self.gsc_ls = None
        self.patch_ebuild = mock.MagicMock()
        # Save datetime for use in mocks.
        self.dt = datetime.datetime
        self.now = datetime.datetime.fromtimestamp(
            1658747184,
            tz=datetime.timezone.utc,
        )
        self.day_old_ts = int(
            datetime.datetime.timestamp(self.now - datetime.timedelta(days=1))
        )
        self.week_old_ts = int(
            datetime.datetime.timestamp(self.now - datetime.timedelta(weeks=1))
        )
        self.month_old_ts = int(
            datetime.datetime.timestamp(self.now - datetime.timedelta(days=30))
        )
        self.verified_afdo_name = (
            f"chromeos-chrome-amd64-atom-78-3876.0-{self.week_old_ts}-"
            "benchmark-78.0.3839.0-r1-redacted.afdo"
        )
        self.cwp_gs_location = "gs://path/to/gs_bucket/cwp"
        self.benchmark_gs_location = "gs://path/to/gs_bucket/benchmark"
        self.PatchObject(
            toolchain_util, "CWP_AFDO_GS_URL", new=self.cwp_gs_location
        )
        self.PatchObject(
            toolchain_util,
            "BENCHMARK_AFDO_GS_URL",
            new=self.benchmark_gs_location,
        )

        class mock_datetime:
            """Class for mocking datetime.datetime."""

            @staticmethod
            def fromtimestamp(ts, tz=None):
                return self.dt.fromtimestamp(ts, tz)

            @staticmethod
            def now(tz=None):
                del tz
                return self.now

        self.PatchObject(toolchain_util.datetime, "datetime", new=mock_datetime)

    def SetUpPrepare(
        self,
        artifact_type,
        input_artifacts,
        mock_patch=True,
        profile_info_extra=None,
    ):
        """Set up to test _Prepare${artifactType}."""
        self.artifact_type = artifact_type
        self.input_artifacts = input_artifacts
        if profile_info_extra:
            self.profile_info.update(profile_info_extra)
        self.obj = toolchain_util.PrepareForBuildHandler(
            self.artifact_type,
            self.chroot,
            self.sysroot,
            self.board,
            self.input_artifacts,
            self.profile_info,
        )
        self.obj._gs_context = self.gs_context
        self.gsc_exists = self.PatchObject(
            self.gs_context, "Exists", return_value=True
        )
        self.gsc_ls = self.PatchObject(
            self.gs_context, "LS", return_value=["gs://path"]
        )
        if mock_patch:
            self.patch_ebuild = self.PatchObject(
                toolchain_util._CommonPrepareBundle, "_PatchEbuild"
            )

    def setupUnverifiedChromeBenchmarkAfdoFileInputProperties(
        self, profile_info_extra=None
    ):
        self.SetUpPrepare(
            "UnverifiedChromeBenchmarkAfdoFile",
            {
                "UnverifiedChromeBenchmarkPerfFile": ["gs://path/to/perfdata"],
                "UnverifiedChromeBenchmarkAfdoFile": ["gs://path/to/unvetted"],
                "ChromeDebugBinary": ["gs://image-archive/path"],
            },
            profile_info_extra=profile_info_extra,
        )

    def testPrepareUnverifiedChromeBenchmarkAfdoFileExists(self):
        """Normal flow, build is needed, all artifacts are present."""
        self.setupUnverifiedChromeBenchmarkAfdoFileInputProperties()
        # Published artifact is missing, debug binary is present, perf.data is
        # present.
        self.gsc_exists.return_value = False
        self.gsc_ls.side_effect = (
            ["gs://image-archive/path/to/debug"],
            ["gs://image-archive/path/to/perf"],
        )
        self.assertEqual(
            toolchain_util.PrepareForBuildReturn.NEEDED, self.obj.Prepare()
        )
        expected_exists = [
            mock.call(
                "gs://path/to/unvetted/"
                "chromeos-chrome-amd64-78.0.3893.0_rc-r1.afdo.bz2"
            ),
        ]
        expected_ls = [
            mock.call(
                "gs://image-archive/path/chromeos-chrome-amd64-*.debug.bz2"
            ),
            mock.call(
                "gs://path/to/perfdata/"
                "chromeos-chrome-amd64-78.0.3893.0.perf.data.bz2"
            ),
        ]
        self.assertEqual(expected_exists, self.gs_context.Exists.call_args_list)
        self.assertEqual(expected_ls, self.gs_context.LS.call_args_list)
        # There is no need to patch the ebuild.
        self.patch_ebuild.assert_not_called()

    def testPrepareUnverifiedChromeBenchmarkArmAfdoFile(self):
        """Normal flow with Arm, build is needed, all artifacts are present."""
        profile_info_extra = {"chrome_cwp_profile": "arm", "arch": "arm"}
        self.setupUnverifiedChromeBenchmarkAfdoFileInputProperties(
            profile_info_extra
        )
        # Published artifact is missing, debug binary is present, perf.data is
        # present.
        self.gsc_exists.return_value = False
        self.gsc_ls.side_effect = (
            ["gs://image-archive/path/to/debug"],
            ["gs://image-archive/path/to/perf"],
        )
        self.assertEqual(
            toolchain_util.PrepareForBuildReturn.NEEDED, self.obj.Prepare()
        )
        # Expect arm profiles.
        expected_exists = [
            mock.call(
                "gs://path/to/unvetted/"
                "chromeos-chrome-arm-78.0.3893.0_rc-r1.afdo.bz2"
            ),
        ]
        expected_ls = [
            mock.call(
                "gs://image-archive/path/chromeos-chrome-arm-*.debug.bz2"
            ),
            mock.call(
                "gs://path/to/perfdata/"
                "chromeos-chrome-arm-78.0.3893.0.perf.data.bz2"
            ),
        ]
        self.assertEqual(expected_exists, self.gs_context.Exists.call_args_list)
        self.assertEqual(expected_ls, self.gs_context.LS.call_args_list)
        # There is no need to patch the ebuild.
        self.patch_ebuild.assert_not_called()

    def testPrepareUnverifiedChromeBenchmarkAfdoFileMissingDebug(self):
        """Test raised exception when chrome.debug file is missing."""
        self.setupUnverifiedChromeBenchmarkAfdoFileInputProperties()
        # Published artifact is missing, debug binary is missing.
        self.gsc_exists.return_value = False
        self.gsc_ls.return_value = []
        with self.assertRaisesRegex(
            toolchain_util.PrepareForBuildHandlerError,
            r"Could not find an artifact matching the pattern "
            r'"chromeos-chrome-amd64-\*.debug.bz2" in '
            r"\['gs://image-archive/path'\].",
        ):
            self.obj.Prepare()

    def testPrepareUnverifiedChromeBenchmarkAfdoFileMissingPerf(self):
        """Test raised exception when perf.data file is missing."""
        self.setupUnverifiedChromeBenchmarkAfdoFileInputProperties()
        # Published artifact is missing, debug binary is present,
        # perf.data is missing.
        self.gsc_exists.return_value = False
        self.gsc_ls.side_effect = (["gs://image-archive/path/to/debug"], [])
        with self.assertRaisesRegex(
            toolchain_util.PrepareForBuildHandlerError,
            r'Could not find "chromeos-chrome-amd64-78.0.3893.0.perf.data.bz2" '
            r"in \['gs://path/to/perfdata'\].",
        ):
            self.obj.Prepare()

    def testPrepareUnverifiedChromeBenchmarkAfdoFileMultArtifacts(self):
        """Test raised exception on multiple artifacts of one type."""
        self.setupUnverifiedChromeBenchmarkAfdoFileInputProperties()
        # Published artifact is missing, multiple debug binary artifacts.
        self.gsc_exists.return_value = False
        self.gsc_ls.return_value = [
            "gs://image-archive/path/to/debug1",
            "gs://image-archive/path/to/debug2",
        ]
        with self.assertRaisesRegex(
            toolchain_util.PrepareForBuildHandlerError,
            r"Found \['gs://image-archive/path/to/debug1', "
            r"'gs://image-archive/path/to/debug2'\] artifacts at "
            r"gs://image-archive/path. Expected ONE file.",
        ):
            self.obj.Prepare()

    def testCleanupArtifactDirectory(self):
        mock_rmdir = self.PatchObject(osutils, "RmDir")
        mock_isdir = self.PatchObject(os.path, "exists")
        for test_dir in [
            "/tmp/fatal_clang_warnings",
            "/tmp/clang_crash_diagnostics",
        ]:
            mock_rmdir.reset_mock()
            # When the dirs don't exist, we shouldn't try to remove them
            mock_isdir.return_value = False
            self.obj._CleanupArtifactDirectory(test_dir)
            mock_rmdir.assert_not_called()

            # When the dirs exist, we should remove all of them
            mock_isdir.return_value = True
            self.obj._CleanupArtifactDirectory(test_dir)
            mock_rmdir.assert_has_calls(
                [
                    mock.call(self.chroot.full_path(test_dir), sudo=True),
                    mock.call(
                        self.chroot.full_path(
                            os.path.join(self.sysroot, test_dir[1:])
                        ),
                        sudo=True,
                    ),
                ]
            )

        # A non-absolute path will trigger assertion
        with self.assertRaises(Exception) as context:
            self.obj._CleanupArtifactDirectory("non/absolute/path")
        self.assertIn("needs to be an absolute path", str(context.exception))

    def callPrepareVerifiedKernelCwpAfdoFile(
        self,
        ebuild_list_of_str,
        cwp_old_loc=None,
        cwp_new_loc=None,
        cwp_old_ver=None,
        cwp_new_ver=None,
    ):
        """Helper function to set up and verify Prepare() call.

        Args:
            ebuild_list_of_str: list[str] of ebuild contents.
                Must contain {changing_cwp_loc} which resolves to
                "cwp_old_loc" before Prepare() and "cwp_new_loc" after.
                Must contain {changing_cwp_ver} which resolves to
                "cwp_old_ver" before Prepare() and "cwp_new_ver" after.
            cwp_old_loc: AFDO_LOCATION value before Prepare().
            cwp_new_loc: AFDO_LOCATION value after Prepare().
            cwp_old_ver: AFDO version before Prepare().
            cwp_new_ver: AFDO version after Prepare().
        """
        if not cwp_old_loc:
            cwp_old_loc = ""
        if not cwp_new_loc:
            cwp_new_loc = "gs://path/to/cwp/kernel/5.4"
        if not cwp_old_ver:
            cwp_old_ver = "R99-14469.8-1644229953"
        if not cwp_new_ver:
            cwp_new_ver = "R100-14496.0-1644834841"

        self.SetUpPrepare(
            "VerifiedKernelCwpAfdoFile",
            {
                "UnverifiedKernelCwpAfdoFile": [cwp_new_loc],
                "VerifiedKernelCwpAfdoFile": [cwp_new_loc],
            },
            mock_patch=False,
        )
        kernel_package = "sys-kernel/chromeos-kernel-5_15-5.15.12-r1234"
        ebuild_spec = "{c}/{p}-{v}-r{r}.ebuild"
        kernel_cpv = package_info.parse(kernel_package)
        ebuild_info_path = os.path.join(
            self.sysroot_full_path, format(kernel_cpv, ebuild_spec)
        )
        ebuild_info = toolchain_util._EbuildInfo(
            path=ebuild_info_path, CPV=kernel_cpv
        )
        self.PatchObject(toolchain_util, "_GetProfileAge", return_value=0)
        self.PatchObject(self.obj, "_GetEbuildInfo", return_value=ebuild_info)
        kernel_cwp = os.path.join(cwp_new_loc, cwp_new_ver)
        self.PatchObject(
            self.obj, "_FindLatestAFDOArtifact", return_value=kernel_cwp
        )
        # The artifact is missing, build is needed.
        self.gsc_exists.return_value = False
        ebuild_old_str = "".join(ebuild_list_of_str).format(
            changing_cwp_loc=cwp_old_loc,
            changing_cwp_ver=cwp_old_ver,
        )
        self.WriteTempFile(
            ebuild_info_path,
            ebuild_old_str,
            makedirs=True,
        )

        self.obj.Prepare()

        # Check contents in the uprevved package.
        uprev_path = os.path.join(
            self.sysroot_full_path,
            format(kernel_cpv.revision_bump(), ebuild_spec),
        )
        new_contents = self.ReadTempFile(uprev_path)
        self.assertEqual(
            "".join(ebuild_list_of_str).format(
                changing_cwp_loc=cwp_new_loc,
                changing_cwp_ver=cwp_new_ver,
            ),
            new_contents,
        )

    def testPrepareVerifiedKernelCwpAfdoFileOldEbuild(self):
        """Test PrepareVerifiedKernelCwpAfdoFile and patch old ebuild."""
        ebuild_data = (
            "# some comment\n",
            'AFDO_LOCATION="{changing_cwp_loc}"\n',
            'AFDO_PROFILE_VERSION="{changing_cwp_ver}"',
        )
        self.callPrepareVerifiedKernelCwpAfdoFile(ebuild_data)

    def testPrepareVerifiedKernelCwpAfdoFileNewEbuild(self):
        """Test PrepareVerifiedKernelCwpAfdoFile and patch new ebuild."""
        ebuild_data = (
            "# some comment\n",
            'export AFDO_LOCATION="{changing_cwp_loc}"\n',
            'export AFDO_PROFILE_VERSION="{changing_cwp_ver}"',
        )
        self.callPrepareVerifiedKernelCwpAfdoFile(ebuild_data)

    def testPrepareVerifiedKernelCwpAfdoFileArm(self):
        """Test PrepareVerifiedKernelCwpAfdoFile with the Arm profile."""
        cwp_old_ver = "R99-14469.8-1644229953"
        cwp_new_ver = "R100-14496.0-1644834841"
        # changing_cwp_ver is going to be resolved to cwp_old_ver
        # before Prepare() and cwp_new_ver after.
        fixed_version = cwp_old_ver
        ebuild_data = (
            "# some comment\n",
            'AFDO_LOCATION="{changing_cwp_loc}"\n',
            f'AFDO_PROFILE_VERSION="{fixed_version}"\n',
            'ARM_AFDO_PROFILE_VERSION="{changing_cwp_ver}"',
        )
        # Overwrite profile_info with arm profile info.
        self.profile_info = {
            "kernel_version": "5.14",
            "arch": "arm",
        }
        self.callPrepareVerifiedKernelCwpAfdoFile(
            ebuild_data, cwp_old_ver=cwp_old_ver, cwp_new_ver=cwp_new_ver
        )

    def testPrepareVerifiedKernelCwpAfdoFileArmAndAmd64(self):
        """Test PrepareVerifiedKernelCwpAfdoFile with the Amd64 profile."""
        cwp_old_ver = "R99-14469.8-1644229953"
        cwp_new_ver = "R100-14496.0-1644834841"
        # changing_cwp_ver is going to be resolved to cwp_old_ver
        # before Prepare() and cwp_new_ver after.
        fixed_version = cwp_old_ver
        # Ebuild contains both Arm and Amd64 version but we change only Amd64.
        ebuild_data = (
            "# some comment\n",
            'AFDO_LOCATION="{changing_cwp_loc}"\n',
            'AFDO_PROFILE_VERSION="{changing_cwp_ver}"\n',
            f'ARM_AFDO_PROFILE_VERSION="{fixed_version}"',
        )
        self.callPrepareVerifiedKernelCwpAfdoFile(
            ebuild_data, cwp_old_ver=cwp_old_ver, cwp_new_ver=cwp_new_ver
        )

    def mockFindLatestAFDOArtifact(self, gs_urls, _, arch=None):
        """Return artifacts from bench and cwp gs buckets."""
        if not arch:
            arch = "amd64"
        atom_cwp_location = os.path.join(self.cwp_gs_location, "atom")
        arm_cwp_location = os.path.join(self.cwp_gs_location, "arm")
        if toolchain_util.BENCHMARK_AFDO_GS_URL in gs_urls:
            if arch == "amd64":
                return os.path.join(
                    toolchain_util.BENCHMARK_AFDO_GS_URL,
                    "chromeos-chrome-amd64-78.0.3839.0_rc-r1.afdo.bz2",
                )
            if arch == "arm":
                return os.path.join(
                    toolchain_util.BENCHMARK_AFDO_GS_URL,
                    "chromeos-chrome-arm-78.0.3840.0_rc-r1.afdo.bz2",
                )
            raise toolchain_util.NoProfilesInGsBucketError("no profiles")
        if atom_cwp_location in gs_urls:
            # Profile is 1-week old compared to self.now.
            return os.path.join(
                atom_cwp_location,
                f"R78-3876.0-{self.week_old_ts}.afdo.xz",
            )
        if arm_cwp_location in gs_urls:
            # Profile is 1-week old compared to self.now.
            return os.path.join(
                arm_cwp_location,
                f"R78-3879.0-{self.day_old_ts}.afdo.xz",
            )
        raise toolchain_util.NoProfilesInGsBucketError("no profiles")

    def setupPrepareVerifiedReleaseAfdoFileMocks(self):
        self.PatchObject(
            self.obj,
            "_FindLatestAFDOArtifact",
            side_effect=self.mockFindLatestAFDOArtifact,
        )
        self.PatchObject(self.obj.chroot, "tempdir", return_value=self.tempdir)
        self.PatchObject(self.obj, "_MergeAFDOProfiles")
        self.PatchObject(self.obj, "_ProcessAFDOProfile")
        self.PatchObject(os, "rename")

    def testPrepareVerifiedReleaseAfdoFileExists(self):
        """Test that _PrepareVerifiedReleaseAfdoFile works when POINTLESS."""
        profile_info_extra = {"chrome_cwp_profile": "atom"}
        self.SetUpPrepare(
            "VerifiedReleaseAfdoFile",
            {
                "UnverifiedChromeBenchmarkAfdoFile": [
                    self.benchmark_gs_location
                ],
                "UnverifiedChromeCwpAfdoFile": [
                    os.path.join(self.cwp_gs_location, "atom")
                ],
                "VerifiedReleaseAfdoFile": ["gs://path/to/vetted"],
            },
            profile_info_extra=profile_info_extra,
        )
        self.setupPrepareVerifiedReleaseAfdoFileMocks()
        self.assertEqual(
            toolchain_util.PrepareForBuildReturn.POINTLESS, self.obj.Prepare()
        )
        self.gs_context.Exists.assert_called_once_with(
            f"gs://path/to/vetted/{self.verified_afdo_name}.xz"
        )
        # The ebuild is still updated.
        self.patch_ebuild.assert_called_once()

    def setupPrepareVerifiedReleaseAfdoFileInputProperties(
        self,
        profile_info_extra,
        input_artifacts=None,
    ):
        profile = (
            profile_info_extra["chrome_cwp_profile"]
            if profile_info_extra
            else "atom"
        )
        if not input_artifacts:
            input_artifacts = {
                "UnverifiedChromeBenchmarkAfdoFile": [
                    toolchain_util.BENCHMARK_AFDO_GS_URL
                ],
                "UnverifiedChromeCwpAfdoFile": [
                    os.path.join(toolchain_util.CWP_AFDO_GS_URL, profile)
                ],
            }

        self.SetUpPrepare(
            "VerifiedReleaseAfdoFile",
            input_artifacts,
            profile_info_extra=profile_info_extra,
        )

    def testPrepareVerifiedReleaseAfdoFile(self):
        """Normal flow, build is needed, all artifacts are present."""
        pi_extra = {"chrome_cwp_profile": "atom"}
        self.setupPrepareVerifiedReleaseAfdoFileInputProperties(
            profile_info_extra=pi_extra,
        )
        self.setupPrepareVerifiedReleaseAfdoFileMocks()
        # Published artifact is missing, debug binary is present, perf.data is
        # present.
        self.gsc_exists.return_value = False
        self.assertEqual(
            toolchain_util.PrepareForBuildReturn.NEEDED, self.obj.Prepare()
        )
        expected_exists = [
            mock.call(
                os.path.join(
                    toolchain_util.RELEASE_PROFILE_VETTED_URL,
                    (
                        "chromeos-chrome-amd64-atom-78-3876.0-"
                        f"{self.week_old_ts}-benchmark-78.0.3839.0-r1"
                        "-redacted.afdo.xz"
                    ),
                )
            ),
        ]
        self.assertEqual(expected_exists, self.gs_context.Exists.call_args_list)
        self.patch_ebuild.assert_called_once_with(
            self.obj._GetEbuildInfo(toolchain_util.constants.CHROME_PN),
            {
                "UNVETTED_AFDO_FILE": os.path.join(
                    os.path.sep,
                    "tmp",
                    (
                        "chromeos-chrome-amd64-atom-78-3876.0-"
                        f"{self.week_old_ts}-benchmark-78.0.3839.0-r1"
                        "-redacted.afdo"
                    ),
                )
            },
            uprev=True,
        )

    def testPrepareVerifiedReleaseAfdoFileArmProfile(self):
        """Test fresh arm profiles."""
        pi_extra = {"chrome_cwp_profile": "arm", "arch": "arm"}
        self.setupPrepareVerifiedReleaseAfdoFileInputProperties(
            profile_info_extra=pi_extra,
        )
        self.setupPrepareVerifiedReleaseAfdoFileMocks()
        self.gsc_exists.return_value = False
        self.assertEqual(
            toolchain_util.PrepareForBuildReturn.NEEDED, self.obj.Prepare()
        )
        # The merged -arm- profile uses the arm's version 78-3877.0-.
        self.patch_ebuild.assert_called_once_with(
            self.obj._GetEbuildInfo(toolchain_util.constants.CHROME_PN),
            {
                "UNVETTED_AFDO_FILE": os.path.join(
                    os.path.sep,
                    "tmp",
                    (
                        f"chromeos-chrome-arm-none-78-3879.0-{self.day_old_ts}-"
                        "benchmark-78.0.3840.0-r1-redacted.afdo"
                    ),
                )
            },
            uprev=True,
        )

    def testPrepareVerifiedReleaseAfdoFileMissingInput(self):
        """Test that _PrepareVerifiedReleaseAfdoFile raises assert."""
        self.setupPrepareVerifiedReleaseAfdoFileInputProperties(
            profile_info_extra=None
        )
        self.setupPrepareVerifiedReleaseAfdoFileMocks()
        with self.assertRaisesRegex(
            toolchain_util.PrepareForBuildHandlerError,
            (
                r"Profile name is not set. "
                r"Is 'chrome_cwp_profile' missing in profile_info?"
            ),
        ):
            self.obj.Prepare()

    def testPrepareVerifiedReleaseAfdoFileArm32Profile(self):
        """Test fresh arm profiles for arm32."""
        pi_extra = {"chrome_cwp_profile": "arm32", "arch": "arm"}
        self.setupPrepareVerifiedReleaseAfdoFileInputProperties(
            profile_info_extra=pi_extra,
            input_artifacts={
                "UnverifiedChromeBenchmarkAfdoFile": [
                    toolchain_util.BENCHMARK_AFDO_GS_URL
                ],
                "UnverifiedChromeCwpAfdoFile": [
                    os.path.join(toolchain_util.CWP_AFDO_GS_URL, "arm")
                ],
            },
        )
        self.setupPrepareVerifiedReleaseAfdoFileMocks()
        self.gsc_exists.return_value = False
        self.assertEqual(
            toolchain_util.PrepareForBuildReturn.NEEDED, self.obj.Prepare()
        )
        # The merged profile must have -arm-arm32-.
        self.patch_ebuild.assert_called_once_with(
            self.obj._GetEbuildInfo(toolchain_util.constants.CHROME_PN),
            {
                "UNVETTED_AFDO_FILE": os.path.join(
                    os.path.sep,
                    "tmp",
                    (
                        "chromeos-chrome-arm-arm32-78-3879.0-"
                        f"{self.day_old_ts}-benchmark-78.0.3840.0-r1-redacted"
                        ".afdo"
                    ),
                )
            },
            uprev=True,
        )

    def testPrepareVerifiedReleaseAfdoFileExpProfileFromArm(self):
        """Test experimental profiles on arm."""
        pi_extra = {"chrome_cwp_profile": "exp", "arch": "arm"}
        # cwp location is atom.
        self.setupPrepareVerifiedReleaseAfdoFileInputProperties(
            profile_info_extra=pi_extra,
            input_artifacts={
                "UnverifiedChromeBenchmarkAfdoFile": [
                    toolchain_util.BENCHMARK_AFDO_GS_URL
                ],
                "UnverifiedChromeCwpAfdoFile": [
                    os.path.join(toolchain_util.CWP_AFDO_GS_URL, "atom")
                ],
            },
        )
        self.setupPrepareVerifiedReleaseAfdoFileMocks()
        self.gsc_exists.return_value = False
        self.assertEqual(
            toolchain_util.PrepareForBuildReturn.NEEDED, self.obj.Prepare()
        )
        # The merged profile must have -arm-exp- and cwp version from atom
        # which is 78-3876.
        self.patch_ebuild.assert_called_once_with(
            self.obj._GetEbuildInfo(toolchain_util.constants.CHROME_PN),
            {
                "UNVETTED_AFDO_FILE": os.path.join(
                    os.path.sep,
                    "tmp",
                    (
                        "chromeos-chrome-arm-exp-78-3876.0-"
                        f"{self.week_old_ts}-benchmark-78.0.3840.0-r1-redacted"
                        ".afdo"
                    ),
                )
            },
            uprev=True,
        )

    def testPrepareVerifiedReleaseAfdoFileExpProfileFromAmd(self):
        """Test experimental profiles on arm."""
        pi_extra = {"chrome_cwp_profile": "exp-amd64", "arch": "arm"}
        # cwp location is atom.
        self.setupPrepareVerifiedReleaseAfdoFileInputProperties(
            profile_info_extra=pi_extra,
            input_artifacts={
                "UnverifiedChromeBenchmarkAfdoFile": [
                    toolchain_util.BENCHMARK_AFDO_GS_URL
                ],
                "UnverifiedChromeCwpAfdoFile": [
                    os.path.join(toolchain_util.CWP_AFDO_GS_URL, "atom")
                ],
            },
        )
        self.setupPrepareVerifiedReleaseAfdoFileMocks()
        self.gsc_exists.return_value = False
        self.assertEqual(
            toolchain_util.PrepareForBuildReturn.NEEDED, self.obj.Prepare()
        )
        # The merged profile has arm arch but uses bench version
        # from amd.
        self.patch_ebuild.assert_called_once_with(
            self.obj._GetEbuildInfo(toolchain_util.constants.CHROME_PN),
            {
                "UNVETTED_AFDO_FILE": os.path.join(
                    os.path.sep,
                    "tmp",
                    (
                        "chromeos-chrome-arm-exp-78-3876.0-"
                        f"{self.week_old_ts}-benchmark-78.0.3839.0-r1-redacted"
                        ".afdo"
                    ),
                )
            },
            uprev=True,
        )

    def testPrepareVerifiedReleaseAfdoFileExpInvalidProfile(self):
        """Test experimental profiles on arm."""
        pi_extra = {"chrome_cwp_profile": "exp-invalid", "arch": "arm"}
        # cwp location is atom.
        self.setupPrepareVerifiedReleaseAfdoFileInputProperties(
            profile_info_extra=pi_extra,
            input_artifacts={
                "UnverifiedChromeBenchmarkAfdoFile": [
                    toolchain_util.BENCHMARK_AFDO_GS_URL
                ],
                "UnverifiedChromeCwpAfdoFile": [
                    os.path.join(toolchain_util.CWP_AFDO_GS_URL, "atom")
                ],
            },
        )
        self.setupPrepareVerifiedReleaseAfdoFileMocks()
        self.gsc_exists.return_value = False
        with self.assertRaises(toolchain_util.NoProfilesInGsBucketError):
            self.obj.Prepare()


class BundleArtifactHandlerTest(PrepareBundleTest):
    """Test BundleArtifactHandler specific methods."""

    def setUp(self):
        def _Bundle(_self):
            osutils.WriteFile(
                os.path.join(_self.output_dir, "artifact"), "data\n"
            )

        self.artifact_type = "Unspecified"
        self.outdir = None
        self.afdo_tmp_path = None
        self.kernel_version = "4_4"
        self.profile_info = {
            "arch": "amd64",
            "kernel_version": self.kernel_version.replace("_", "."),
        }
        cwp_version = "78-3877.0-1567418235"
        benchmark_version = "78.0.3893.0"
        self.afdo_name = f"chromeos-chrome-amd64-{benchmark_version}_rc-r1.afdo"
        self.perf_name = f"chromeos-chrome-amd64-{benchmark_version}.perf.data"
        self.release_afdo_name = (
            f"chromeos-chrome-amd64-atom-{cwp_version}-"
            f"benchmark-{benchmark_version}-r1-redacted.afdo.xz"
        )
        self.debug_binary_name = (
            f"chromeos-chrome-amd64-{benchmark_version}_rc-r1.debug"
        )
        self.merged_android_afdo_name = (
            f"chromeos-chrome-amd64-{benchmark_version}_rc-r1-merged.afdo"
        )
        self.kernel_name = "R89-13638.0-1607337135"

        self.copy2 = self.PatchObject(shutil, "copy2")
        self.fetch = self.PatchObject(
            gob_util,
            "FetchUrl",
            return_value=base64.encodebytes(self.release_afdo_name.encode()),
        )

        class mock_datetime:
            """Class for mocking datetime.datetime."""

            @staticmethod
            def strftime(_when, _fmt):
                return "DATE"

            @staticmethod
            def now():
                return -1

        self.PatchObject(datetime, "datetime", new=mock_datetime)

    def SetUpBundle(self, artifact_type):
        """Set up to test _Bundle${artifactType}."""
        self.artifact_type = artifact_type
        self.outdir = os.path.join(self.tempdir, "tmp", "output_dir")
        osutils.SafeMakedirs(self.outdir)
        self.afdo_tmp_path = "/tmp/benchmark-afdo-generate"
        osutils.SafeMakedirs(self.chroot.full_path(self.afdo_tmp_path))
        self.obj = toolchain_util.BundleArtifactHandler(
            self.artifact_type,
            self.chroot,
            self.sysroot,
            self.board,
            self.outdir,
            self.profile_info,
        )
        self.obj._gs_context = self.gs_context

    def testBundleArtifactHandlerWithoutArchRaises(self):
        """Test that BundleArtifactHandler w/o arch in profile_info raises."""
        self.profile_info = {
            "chrome_cwp_profile": "atom",
            # "arch" is missing.
        }
        with self.assertRaisesRegex(
            ValueError,
            "No 'arch' specified in ArtifactProfileInfo",
        ):
            self.SetUpBundle("UnverifiedChromeBenchmarkPerfFile")

    def mockChrome(self) -> Path:
        """Generate names and mock the files in fs."""
        self.PatchObject(
            toolchain_util, "CHROME_BINARY_PATH", new="path/out_{board}/chrome"
        )
        chrome_binary = Path(
            toolchain_util.CHROME_BINARY_PATH.format(board=self.board)
        )
        self.WriteTempFile(
            self.chroot.full_path(self.sysroot, chrome_binary),
            "",
            makedirs=True,
        )
        return chrome_binary

    def testCheckArgumentsFail(self):
        """Test arguments checking fails without files existing."""
        self.SetUpBundle("UnverifiedChromeBenchmarkAfdoFile")
        chrome_binary = self.mockChrome()
        invalid_dir = "/does/not/exist/"

        invalid_chrome = Path(invalid_dir, "chrome")
        with self.assertRaisesRegex(
            toolchain_util.BundleArtifactsHandlerError,
            f"'{self.chroot.full_path(invalid_chrome)}' chrome binary does not "
            "exist",
        ):
            self.obj._CheckArguments(invalid_chrome)

        self.obj.output_dir = invalid_dir
        with self.assertRaisesRegex(
            toolchain_util.BundleArtifactsHandlerError,
            f"Non-existent directory '{invalid_dir}' specified for --out-dir",
        ):
            self.obj._CheckArguments(chrome_binary)

    def testBundleChromeClangWarningsFile(self):
        """Test that BundleChromeClangWarningsFile works."""
        self.SetUpBundle("ChromeClangWarningsFile")
        artifact = os.path.join(
            self.outdir, "%s.DATE.clang_tidy_warnings.tar.xz" % self.board
        )
        self.assertEqual([artifact], self.obj.Bundle())
        self.copy2.assert_called_once_with(mock.ANY, artifact)

    def testBundleUnverifiedChromeBenchmarkPerfFile(self):
        self.SetUpBundle("UnverifiedChromeBenchmarkPerfFile")
        self.assertEqual([], self.obj.Bundle())

    def testBundleChromeDebugBinary(self):
        self.SetUpBundle("ChromeDebugBinary")
        bin_path = toolchain_util._CHROME_DEBUG_BIN % {
            "root": self.chroot.path,
            "sysroot": self.sysroot,
        }
        osutils.WriteFile(bin_path, "", makedirs=True)
        output = os.path.join(
            self.outdir,
            self.debug_binary_name + toolchain_util.BZ2_COMPRESSION_SUFFIX,
        )
        self.assertEqual([output], self.obj.Bundle())

    def testBundleUnverifiedChromeBenchmarkAfdoFile(self):
        self.SetUpBundle("UnverifiedChromeBenchmarkAfdoFile")
        self.PatchObject(
            self.obj,
            "_GetEbuildInfo",
            return_value=toolchain_util._EbuildInfo(
                path=self.chrome_ebuild, CPV=self.chrome_pkg
            ),
        )
        sym_link_command = self.PatchObject(osutils, "SafeSymlink")
        # Return ~1MB profile size.
        self.PatchObject(os.path, "getsize", return_value=100000)

        chrome_debug_file = os.path.join(
            self.afdo_tmp_path, self.debug_binary_name
        )
        osutils.WriteFile(
            self.chroot.full_path(chrome_debug_file), "", makedirs=True
        )
        ret = self.obj.Bundle()
        afdo_path = os.path.join(
            self.outdir, self.afdo_name + toolchain_util.BZ2_COMPRESSION_SUFFIX
        )
        self.assertEqual([afdo_path], ret)
        # Make sure the sym link to debug Chrome is created
        sym_link_command.assert_called_with(
            self.debug_binary_name,
            self.chroot.full_path(
                os.path.join(self.afdo_tmp_path, "chrome.unstripped")
            ),
        )
        afdo_path_inside = os.path.join(self.afdo_tmp_path, self.afdo_name)
        # Make sure commands are executed correctly
        self.rc.assertCommandContains(
            [
                toolchain_util._AFDO_GENERATE_LLVM_PROF,
                "--binary="
                + os.path.join(self.afdo_tmp_path, "chrome.unstripped"),
                "--profile=" + os.path.join(self.afdo_tmp_path, self.perf_name),
                "--out=" + afdo_path_inside,
                "--sample_threshold_frac=0",
            ]
        )
        self.rc.assertCommandContains(["bzip2", "-c", afdo_path_inside])

    def testBundleUnverifiedChromeBenchmarkAfdoFileLinksMismatchedChrome(self):
        """Checks that Bundle() is OK with mismatched debuginfo files.

        Regression test for b/292382163. It's correct, though rare, for us to
        download an older version of chrome.debug symbols.
        """
        self.SetUpBundle("UnverifiedChromeBenchmarkAfdoFile")
        self.PatchObject(
            self.obj,
            "_GetEbuildInfo",
            return_value=toolchain_util._EbuildInfo(
                path=self.chrome_ebuild, CPV=self.chrome_pkg
            ),
        )
        sym_link_command = self.PatchObject(osutils, "SafeSymlink")
        # Return ~1MB profile size.
        self.PatchObject(os.path, "getsize", return_value=100000)
        mismatched_debug_binary = self.debug_binary_name.replace("-r1", "-r0")
        # Use a regular assert here since this firing == a bug in the test.
        assert mismatched_debug_binary != self.debug_binary_name

        chrome_debug_file = os.path.join(
            self.afdo_tmp_path, mismatched_debug_binary
        )
        osutils.WriteFile(
            self.chroot.full_path(chrome_debug_file), "", makedirs=True
        )
        self.obj.Bundle()
        sym_link_command.assert_called_with(
            mismatched_debug_binary,
            self.chroot.full_path(
                os.path.join(self.afdo_tmp_path, "chrome.unstripped")
            ),
        )

    def testBundleUnverifiedChromeBenchmarkAfdoFileRaisesError(self):
        self.SetUpBundle("UnverifiedChromeBenchmarkAfdoFile")
        self.PatchObject(
            self.obj,
            "_GetEbuildInfo",
            return_value=toolchain_util._EbuildInfo(
                path=self.chrome_ebuild, CPV=self.chrome_pkg
            ),
        )
        self.PatchObject(osutils, "SafeSymlink")
        # Return invalid size of the profile.
        self.PatchObject(os.path, "getsize", return_value=100)

        with self.assertRaises(toolchain_util.BundleArtifactsHandlerError):
            self.obj.Bundle()

    def testBundleChromeAFDOProfileForAndroidLinuxFailWhenNoBenchmark(self):
        self.SetUpBundle("ChromeAFDOProfileForAndroidLinux")
        merge_function = self.PatchObject(
            self.obj, "_CreateAndUploadMergedAFDOProfile"
        )
        with self.assertRaises(AssertionError) as context:
            self.obj.Bundle()
        self.assertIn("No new AFDO profile created", str(context.exception))
        merge_function.assert_not_called()

    def testBundleChromeAFDOProfileForAndroidLinuxPass(self):
        self.SetUpBundle("ChromeAFDOProfileForAndroidLinux")
        self.PatchObject(os.path, "exists", return_value=True)
        merge_function = self.PatchObject(
            self.obj,
            "_CreateAndUploadMergedAFDOProfile",
            return_value=self.merged_android_afdo_name,
        )

        ret = self.obj.Bundle()
        merged_path = os.path.join(
            self.outdir,
            self.merged_android_afdo_name
            + toolchain_util.BZ2_COMPRESSION_SUFFIX,
        )
        self.assertEqual([merged_path], ret)
        # Make sure merged function is called
        afdo_path_inside = os.path.join(self.afdo_tmp_path, self.afdo_name)
        merged_path_inside = os.path.join(
            self.afdo_tmp_path, self.merged_android_afdo_name
        )
        merge_function.assert_called_with(
            self.chroot.full_path(afdo_path_inside),
            self.chroot.full_path(os.path.join(self.afdo_tmp_path)),
        )
        self.rc.assertCommandContains(["bzip2", "-c", merged_path_inside])

    def callBundleVerifiedKernelCwpAfdoFile(self, ebuild_data_list):
        self.SetUpBundle("VerifiedKernelCwpAfdoFile")
        ebuild_info_path = self.chroot.full_path(
            "path", "to", "kernel-9999.ebuild"
        )
        ebuild_info = toolchain_util._EbuildInfo(
            path=ebuild_info_path, CPV=mock.MagicMock()
        )
        self.PatchObject(self.obj, "_GetEbuildInfo", return_value=ebuild_info)
        ebuild_old_str = "".join(ebuild_data_list)
        # We are going to check how the mock_object was called.
        self.WriteTempFile(
            ebuild_info_path,
            ebuild_old_str,
            makedirs=True,
        )

        ret = self.obj.Bundle()

        profile_name = self.kernel_name + (
            toolchain_util.KERNEL_AFDO_COMPRESSION_SUFFIX
        )
        verified_profile = os.path.join(self.outdir, profile_name)
        self.assertEqual([verified_profile], ret)
        profile_path = self.chroot.full_path(
            self.sysroot,
            "usr",
            "lib",
            "debug",
            "boot",
            f"chromeos-kernel-{self.kernel_version}-{profile_name}",
        )
        self.copy2.assert_called_once_with(profile_path, verified_profile)

    def testBundleVerifiedKernelCwpAfdoFileOld(self):
        """Test BundleVerifiedKernelCwpAfdoFile with the old ebuild."""
        ebuild_data_list = (
            "# some comment\n",
            'AFDO_LOCATION=""\n',
            f'AFDO_PROFILE_VERSION="{self.kernel_name}"',
        )
        self.callBundleVerifiedKernelCwpAfdoFile(ebuild_data_list)

    def testBundleVerifiedKernelCwpAfdoFileNew(self):
        """Test BundleVerifiedKernelCwpAfdoFile with the new ebuild."""
        ebuild_data_list = (
            "# some comment\n",
            'export AFDO_LOCATION=""\n',
            f'export AFDO_PROFILE_VERSION="{self.kernel_name}"',
        )
        self.callBundleVerifiedKernelCwpAfdoFile(ebuild_data_list)

    def testBundleVerifiedKernelCwpAfdoFileArm(self):
        """Test BundleVerifiedKernelCwpAfdoFile with the old ebuild."""
        unchanged_profile = "R100-14496.0-1644834841"
        ebuild_data_list = (
            "# some comment\n",
            'AFDO_LOCATION=""\n',
            f'AFDO_PROFILE_VERSION="{unchanged_profile}"',
            f'ARM_AFDO_PROFILE_VERSION="{self.kernel_name}"',
        )
        # Overwrite profile_info with arm profile info.
        self.profile_info = {
            "kernel_version": "5.15",
            "arch": "arm",
        }
        # Expected kernel ebuild version.
        self.kernel_version = "5_15"
        self.callBundleVerifiedKernelCwpAfdoFile(ebuild_data_list)

    def testBundleVerifiedKernelCwpAfdoFileRaises(self):
        """Test that BundleVerifiedKernelCwpAfdoFile raises exception."""
        # AFDO_PROFILE_VERSION is missing in the ebuild.
        ebuild_data_list = ("# some comment\n", 'AFDO_LOCATION=""')
        with self.assertRaisesRegex(
            toolchain_util.BundleArtifactsHandlerError,
            "Could not find AFDO_PROFILE_VERSION in "
            f"chromeos-kernel-{self.kernel_version}",
        ):
            self.callBundleVerifiedKernelCwpAfdoFile(ebuild_data_list)

    def runToolchainBundleTest(
        self, artifact_path, tarball_name, input_files, expected_output_files
    ):
        """Asserts that the given artifact_path is tarred up properly.

        If no output files are expected, we assert that no tarballs are created.

        Args:
            artifact_path: the path to touch |input_files| in.
            tarball_name: the expected name of the tarball we will produce.
            input_files: a list of files to |touch| relative to |artifact_path|.
            expected_output_files: a list of files that should be present in the
                tarball.

        Returns:
            Nothing.
        """
        with mock.patch.object(
            cros_build_lib, "CreateTarball"
        ) as create_tarball_mock:
            in_chroot_dirs = [
                artifact_path,
                f"/build/{self.board}{artifact_path}",
            ]
            for d in (self.chroot.full_path(x) for x in in_chroot_dirs):
                for l in input_files:
                    self.WriteTempFile(os.path.join(d, l), "", makedirs=True)

            tarball = self.obj.Bundle()

            if len(expected_output_files) > 0:
                tarball_path = os.path.join(self.outdir, tarball_name)
                self.assertEqual(tarball, [tarball_path])

                create_tarball_mock.assert_called_once()
                output, _tempdir = create_tarball_mock.call_args[0]
                self.assertEqual(output, tarball_path)
                inputs = create_tarball_mock.call_args[1]["inputs"]
                self.assertCountEqual(expected_output_files, inputs)
            else:
                # Bundlers do not create tarballs when no artifacts are found.
                self.assertEqual(tarball, [])

    def testBundleToolchainWarningLogs(self):
        self.SetUpBundle("ToolchainWarningLogs")
        artifact_path = "/tmp/fatal_clang_warnings"
        tarball_name = "%s.DATE.fatal_clang_warnings.tar.xz" % self.board

        # Test behaviour when no artifacts are found.
        self.runToolchainBundleTest(artifact_path, tarball_name, [], [])

        # Test behaviour when artifacts are found.
        self.runToolchainBundleTest(
            artifact_path,
            tarball_name,
            input_files=("log1.json", "log2.json", "log3.notjson", "log4"),
            expected_output_files=(
                "log1.json",
                "log10.json",
                "log2.json",
                "log20.json",
            ),
        )

    def testBundleClangCrashDiagnoses(self):
        self.SetUpBundle("ClangCrashDiagnoses")
        artifact_path = "/tmp/clang_crash_diagnostics"
        tarball_name = "%s.DATE.clang_crash_diagnoses.tar.xz" % self.board

        # Test behaviour when no artifacts are found.
        self.runToolchainBundleTest(artifact_path, tarball_name, [], [])

        # Test behaviour when artifacts are found.
        self.runToolchainBundleTest(
            artifact_path,
            tarball_name,
            input_files=("1.cpp", "1.sh", "2.cc", "2.sh", "foo/bar.sh"),
            expected_output_files=(
                "1.cpp",
                "1.sh",
                "10.cpp",
                "10.sh",
                "2.cc",
                "2.sh",
                "20.cc",
                "20.sh",
                "foo/bar.sh",
                "foo/bar0.sh",
            ),
        )

    def testBundleCompilerRusageLogs(self):
        self.SetUpBundle("CompilerRusageLogs")
        artifact_path = "/tmp/compiler_rusage"
        tarball_name = "%s.DATE.compiler_rusage_logs.tar.xz" % self.board

        # Test behaviour when no artifacts are found.
        self.runToolchainBundleTest(artifact_path, tarball_name, [], [])

        # Test behaviour when artifacts are found.
        self.runToolchainBundleTest(
            artifact_path,
            tarball_name,
            input_files=(
                "good1.json",
                "good2.json",
                "good3.json",
                "bad1.notjson",
                "bad2",
                "json",
            ),
            expected_output_files=(
                "good1.json",
                "good2.json",
                "good3.json",
                "good10.json",
                "good20.json",
                "good30.json",
            ),
        )


class ReleaseChromeAFDOProfileTest(PrepareBundleTest):
    """Test functions related to create a release CrOS profile.

    Since these functions are similar to _UploadReleaseChromeAFDO() and
    related functions. These tests are also similar to
    UploadReleaseChromeAFDOTest, except the setup are within recipe
    environment.
    """

    def setUp(self):
        self.cwp_name = "R77-3809.38-1562580965.afdo"
        self.cwp_full = self.cwp_name + toolchain_util.XZ_COMPRESSION_SUFFIX
        self.arch = "atom"
        self.benchmark_name = "chromeos-chrome-amd64-77.0.3849.0_rc-r1.afdo"
        self.benchmark_full = (
            self.benchmark_name + toolchain_util.BZ2_COMPRESSION_SUFFIX
        )
        cwp_string = "%s-77-3809.38-1562580965" % self.arch
        benchmark_string = "benchmark-77.0.3849.0-r1"
        self.merged_name = "chromeos-chrome-amd64-%s-%s" % (
            cwp_string,
            benchmark_string,
        )
        self.redacted_name = self.merged_name + "-redacted.afdo"
        self.cwp_url = os.path.join(
            toolchain_util.CWP_AFDO_GS_URL, self.arch, self.cwp_full
        )
        self.benchmark_url = os.path.join(
            toolchain_util.BENCHMARK_AFDO_GS_URL, self.benchmark_full
        )
        self.merge_inputs = [
            (
                os.path.join(self.chroot.tmp, self.cwp_name),
                toolchain_util.RELEASE_CWP_MERGE_WEIGHT,
            ),
            (
                os.path.join(self.chroot.tmp, self.benchmark_name),
                toolchain_util.RELEASE_BENCHMARK_MERGE_WEIGHT,
            ),
        ]
        self.merge_output = os.path.join(self.chroot.tmp, self.merged_name)

        self.gs_copy = self.PatchObject(self.gs_context, "Copy")
        self.decompress = self.PatchObject(cros_build_lib, "UncompressFile")

    def testMergeAFDOProfiles(self):
        self.obj._MergeAFDOProfiles(self.merge_inputs, self.merge_output)
        merge_command = [
            "llvm-profdata",
            "merge",
            "-sample",
            "-output=" + self.chroot.chroot_path(self.merge_output),
        ] + [
            "-weighted-input=%d,%s" % (weight, self.chroot.chroot_path(name))
            for name, weight in self.merge_inputs
        ]
        self.rc.assertCommandContains(merge_command)

    def runProcessAFDOProfileOnce(
        self,
        expected_commands,
        input_path=None,
        output_path=None,
        *args,
        **kwargs,
    ):
        if not input_path:
            input_path = self.chroot.full_path("input.afdo")
        if not output_path:
            output_path = self.chroot.full_path("output.afdo")
        # Return ~1MB profile size.
        self.PatchObject(os.path, "getsize", return_value=100000)
        self.obj._ProcessAFDOProfile(input_path, output_path, *args, **kwargs)

        for expected_command in expected_commands:
            self.rc.assertCommandContains(expected_command)

    def testProcessAFDOProfileForAndroidLinuxProfile(self):
        """Test call on _processAFDOProfile() for Android/Linux profiles."""
        input_path = self.chroot.full_path("android.prof.afdo")
        input_path_inchroot = self.chroot.chroot_path(input_path)
        input_to_text = input_path_inchroot + ".text.temp"
        removed_temp = input_path_inchroot + ".removed.temp"
        reduced_temp = input_path_inchroot + ".reduced.tmp"
        reduce_functions = 70000
        output_path = self.chroot.full_path("android.prof.output.afdo")
        expected_commands = [
            [
                "llvm-profdata",
                "merge",
                "-sample",
                "-text",
                input_path_inchroot,
                "-output",
                input_to_text,
            ],
            [
                "remove_indirect_calls",
                "--input=" + input_to_text,
                "--output=" + removed_temp,
            ],
            [
                "remove_cold_functions",
                "--input=" + removed_temp,
                "--output=" + reduced_temp,
                "--number=" + str(reduce_functions),
            ],
            [
                "llvm-profdata",
                "merge",
                "-sample",
                reduced_temp,
                "-output",
                self.chroot.chroot_path(output_path),
            ],
        ]

        self.runProcessAFDOProfileOnce(
            expected_commands,
            input_path=input_path,
            output_path=output_path,
            remove=True,
            reduce_functions=reduce_functions,
        )

    def testProcessAFDOProfileRaisesError(self):
        input_path = self.chroot.full_path("input.afdo")
        output_path = self.chroot.full_path("output.afdo")
        # Return invalid size of the profile.
        self.PatchObject(os.path, "getsize", return_value=100)
        with self.assertRaises(toolchain_util.BundleArtifactsHandlerError):
            self.obj._ProcessAFDOProfile(input_path, output_path)

    def testProcessAFDOProfileForChromeOSReleaseProfile(self):
        """Test call on _processAFDOProfile() for CrOS release profiles."""
        input_path = self.chroot.full_path(self.merged_name)
        input_path_inchroot = self.chroot.chroot_path(input_path)
        input_to_text = input_path_inchroot + ".text.temp"
        redacted_temp = input_path_inchroot + ".redacted.temp"
        removed_temp = input_path_inchroot + ".removed.temp"
        reduced_temp = input_path_inchroot + ".reduced.tmp"
        reduce_functions = 70000
        output_path = self.chroot.full_path(self.redacted_name)
        osutils.WriteFile(
            self.chroot.full_path(input_to_text), "", makedirs=True
        )

        expected_commands = [
            [
                "llvm-profdata",
                "merge",
                "-sample",
                "-text",
                input_path_inchroot,
                "-output",
                input_to_text,
            ],
            ["redact_textual_afdo_profile"],
            [
                "remove_indirect_calls",
                "--input=" + redacted_temp,
                "--output=" + removed_temp,
            ],
            [
                "remove_cold_functions",
                "--input=" + removed_temp,
                "--output=" + reduced_temp,
                "--number=" + str(reduce_functions),
            ],
            [
                "llvm-profdata",
                "merge",
                "-sample",
                reduced_temp,
                "-output",
                self.chroot.chroot_path(output_path),
                "--extbinary",
            ],
        ]
        self.runProcessAFDOProfileOnce(
            expected_commands,
            input_path=input_path,
            output_path=output_path,
            redact=True,
            remove=True,
            reduce_functions=reduce_functions,
            extbinary=True,
        )

    def testCreateReleaseChromeAFDO(self):
        merged_call = self.PatchObject(self.obj, "_MergeAFDOProfiles")
        process_call = self.PatchObject(self.obj, "_ProcessAFDOProfile")
        ret = self.obj._CreateReleaseChromeAFDO(
            self.cwp_url, self.benchmark_url, self.chroot.tmp, self.merged_name
        )

        self.assertEqual(ret, os.path.join(self.chroot.tmp, self.redacted_name))
        self.gs_copy.assert_has_calls(
            [
                mock.call(
                    self.cwp_url, os.path.join(self.chroot.tmp, self.cwp_full)
                ),
                mock.call(
                    self.benchmark_url,
                    os.path.join(self.chroot.tmp, self.benchmark_full),
                ),
            ]
        )

        # Check decompress files.
        decompress_calls = [
            mock.call(
                os.path.join(self.chroot.tmp, self.cwp_full),
                os.path.join(self.chroot.tmp, self.cwp_name),
            ),
            mock.call(
                os.path.join(self.chroot.tmp, self.benchmark_full),
                os.path.join(self.chroot.tmp, self.benchmark_name),
            ),
        ]
        self.decompress.assert_has_calls(decompress_calls)

        # Check call to merge.
        merged_call.assert_called_once_with(
            self.merge_inputs,
            os.path.join(self.chroot.tmp, self.merged_name),
        )

        # Check calls to redact.
        process_call.assert_called_once_with(
            self.merge_output,
            os.path.join(self.chroot.tmp, self.redacted_name),
            redact=True,
            remove=True,
            reduce_functions=20000,
            extbinary=True,
        )


class CreateAndUploadMergedAFDOProfileTest(PrepBundLatestAFDOArtifactTest):
    """Test CreateAndUploadMergedAFDOProfile and related functions.

    These tests are mostly coming from cbuildbot/afdo_unittest.py, and are
    written to adapt to recipe functions. When legacy builders are removed,
    those tests can be safely preserved by this one.
    """

    @staticmethod
    def _benchmark_afdo_profile_name(
        major=0,
        minor=0,
        build=0,
        patch=0,
        rev=1,
        merged_suffix=False,
        compression_suffix=True,
        arch="amd64",
    ):
        suffix = "-merged" if merged_suffix else ""
        result = (
            f"chromeos-chrome-{arch}-{major}.{minor}.{build}.{patch}"
            f"_rc-r{rev}{suffix}"
        )
        result += toolchain_util.AFDO_SUFFIX
        if compression_suffix:
            result += toolchain_util.BZ2_COMPRESSION_SUFFIX
        return result

    def setUp(self):
        self.benchmark_url = "gs://path/to/unvetted"
        self.obj.input_artifacts = {
            "UnverifiedChromeBenchmarkAfdoFile": [self.benchmark_url],
        }
        self.obj.chroot = self.chroot
        self.output_dir = os.path.join(self.chroot.path, "tmp", "output_dir")
        osutils.SafeMakedirs(self.output_dir)
        self.output_dir_inchroot = self.chroot.chroot_path(self.output_dir)
        self.now = datetime.datetime.now()

    def runCreateAndUploadMergedAFDOProfileOnce(self, arch=None, **kwargs):
        if "unmerged_name" not in kwargs:
            # Match everything.
            kwargs["unmerged_name"] = self._benchmark_afdo_profile_name(
                major=9999, compression_suffix=False
            )

        if "output_dir" not in kwargs:
            kwargs["output_dir"] = self.output_dir

        Mocks = collections.namedtuple(
            "Mocks",
            [
                "gs_context",
                "find_artifact",
                "uncompress_file",
                "compress_file",
                "process_afdo_profile",
            ],
        )

        def MockList(*_args, **_kwargs):
            files = [
                self._benchmark_afdo_profile_name(major=10, build=9),
                self._benchmark_afdo_profile_name(major=10, build=10),
                self._benchmark_afdo_profile_name(
                    major=10, build=10, merged_suffix=True
                ),
                self._benchmark_afdo_profile_name(major=10, build=11),
                self._benchmark_afdo_profile_name(major=10, build=12),
                self._benchmark_afdo_profile_name(major=10, build=13),
                # Profiles with 'arm' have to be filtered out unless Bundle uses
                # other than 'amd64' arch.
                self._benchmark_afdo_profile_name(
                    major=10, build=13, arch="arm"
                ),
                self._benchmark_afdo_profile_name(
                    major=10, build=13, merged_suffix=True
                ),
                self._benchmark_afdo_profile_name(
                    major=10, build=13, patch=1, arch="arm"
                ),
                self._benchmark_afdo_profile_name(major=10, build=13, patch=1),
                self._benchmark_afdo_profile_name(major=10, build=13, patch=2),
                self._benchmark_afdo_profile_name(
                    major=10, build=13, patch=2, merged_suffix=True
                ),
                self._benchmark_afdo_profile_name(major=11, build=14),
                self._benchmark_afdo_profile_name(
                    major=11, build=14, arch="arm"
                ),
                self._benchmark_afdo_profile_name(
                    major=11, build=14, merged_suffix=True
                ),
                self._benchmark_afdo_profile_name(major=11, build=15),
                self._benchmark_afdo_profile_name(
                    major=11, build=15, arch="arm"
                ),
            ]

            results = []
            for i, name in enumerate(files):
                url = os.path.join(self.benchmark_url, name)
                now = self.now - datetime.timedelta(days=len(files) - i)
                results.append(self.MockListResult(url=url, creation_time=now))
            # Add a random file with the newest timestamp.
            # The file has to be ignored by the pattern matcher.
            results.append(
                self.MockListResult(
                    url="file-to-be-ignored", creation_time=self.now
                )
            )
            # Make MockList() a little bit smarter.
            # Give the list of files glob matching "path" from
            # gs_context.List(path). fnmatch() is what glob() is eventually
            # calling.
            return [
                res for res in results if fnmatch.fnmatch(res.url, _args[0])
            ]

        self.gs_context.List = MockList
        uncompress_file = self.PatchObject(cros_build_lib, "UncompressFile")
        compress_file = self.PatchObject(cros_build_lib, "CompressFile")
        process_afdo_profile = self.PatchObject(self.obj, "_ProcessAFDOProfile")
        unmerged_profile = os.path.join(
            self.output_dir, kwargs.pop("unmerged_name")
        )
        osutils.Touch(unmerged_profile)
        kwargs["unmerged_profile"] = unmerged_profile

        # Change arch based on the test argument.
        if arch:
            self.obj.arch = arch
        merged_name = self.obj._CreateAndUploadMergedAFDOProfile(**kwargs)
        return merged_name, Mocks(
            gs_context=self.gs_context,
            find_artifact=MockList,
            uncompress_file=uncompress_file,
            compress_file=compress_file,
            process_afdo_profile=process_afdo_profile,
        )

    def testCreateAndUploadMergedAFDOProfileErrorWhenProfileInBucket(self):
        unmerged_name = self._benchmark_afdo_profile_name(major=10, build=13)
        merged_name = None
        with self.assertRaises(AssertionError):
            merged_name, _ = self.runCreateAndUploadMergedAFDOProfileOnce(
                unmerged_name=unmerged_name
            )
        self.assertIsNone(merged_name)

    def testCreateAndUploadMergedAFDOProfileMergesBranchProfiles(self):
        unmerged_name = self._benchmark_afdo_profile_name(
            major=10, build=13, patch=99, compression_suffix=False
        )

        merged_name, mocks = self.runCreateAndUploadMergedAFDOProfileOnce(
            unmerged_name=unmerged_name
        )
        self.assertIsNotNone(merged_name)

        def _afdo_name(major, build, patch=0, merged_suffix=False):
            return self._benchmark_afdo_profile_name(
                major=major,
                build=build,
                patch=patch,
                merged_suffix=merged_suffix,
                compression_suffix=False,
            )

        expected_unordered_args = [
            "-output="
            + os.path.join(
                self.output_dir_inchroot,
                "raw-"
                + _afdo_name(major=10, build=13, patch=99, merged_suffix=True),
            )
        ] + [
            "-weighted-input=1," + os.path.join(self.output_dir_inchroot, s)
            for s in [
                _afdo_name(major=10, build=12),
                _afdo_name(major=10, build=13),
                _afdo_name(major=10, build=13, patch=1),
                _afdo_name(major=10, build=13, patch=2),
                _afdo_name(major=10, build=13, patch=99),
            ]
        ]

        # Note that these should all be in-chroot names.
        expected_ordered_args = ["llvm-profdata", "merge", "-sample"]

        args = cros_build_lib.run.call_args[0][0]
        ordered_args = args[: len(expected_ordered_args)]
        self.assertEqual(ordered_args, expected_ordered_args)

        unordered_args = args[len(expected_ordered_args) :]

        self.assertCountEqual(unordered_args, expected_unordered_args)
        self.assertEqual(mocks.gs_context.Copy.call_count, 4)

    def testCreateAndUploadMergedAFDOProfileRemovesIndirectCallTargets(self):
        unmerged_name = self._benchmark_afdo_profile_name(
            major=10, build=13, patch=99, compression_suffix=False
        )

        merged_name, mocks = self.runCreateAndUploadMergedAFDOProfileOnce(
            recent_to_merge=2, unmerged_name=unmerged_name
        )
        self.assertIsNotNone(merged_name)

        def _afdo_name(major, build, patch=0, merged_suffix=False):
            return self._benchmark_afdo_profile_name(
                major=major,
                build=build,
                patch=patch,
                merged_suffix=merged_suffix,
                compression_suffix=False,
            )

        merge_output_name = "raw-" + _afdo_name(
            major=10, build=13, patch=99, merged_suffix=True
        )
        self.assertNotEqual(merged_name, merge_output_name)

        expected_unordered_args = [
            "-output="
            + os.path.join(self.output_dir_inchroot, merge_output_name),
            "-weighted-input=1,"
            + os.path.join(
                self.output_dir_inchroot,
                _afdo_name(major=10, build=13, patch=2),
            ),
            "-weighted-input=1,"
            + os.path.join(
                self.output_dir_inchroot,
                _afdo_name(major=10, build=13, patch=99),
            ),
        ]

        # Note that these should all be in-chroot names.
        expected_ordered_args = ["llvm-profdata", "merge", "-sample"]
        args = cros_build_lib.run.call_args[0][0]
        ordered_args = args[: len(expected_ordered_args)]
        self.assertEqual(ordered_args, expected_ordered_args)

        unordered_args = args[len(expected_ordered_args) :]
        self.assertCountEqual(unordered_args, expected_unordered_args)

        mocks.process_afdo_profile.assert_called_once_with(
            os.path.join(self.output_dir, merge_output_name),
            os.path.join(self.output_dir, merged_name),
            redact=False,
            remove=True,
            reduce_functions=70000,
            extbinary=False,
        )

    def testCreateAndUploadMergedAFDOProfileRedactsProfileOnArm(self):
        prof = self._benchmark_afdo_profile_name(
            major=9999, compression_suffix=False, arch="arm"
        )
        merged_name, mocks = self.runCreateAndUploadMergedAFDOProfileOnce(
            unmerged_name=prof, arch="arm"
        )
        self.assertIsNotNone(merged_name)
        mocks.process_afdo_profile.assert_called_once_with(
            os.path.join(self.output_dir, "raw-" + merged_name),
            os.path.join(self.output_dir, merged_name),
            redact=True,
            remove=True,
            reduce_functions=70000,
            extbinary=False,
        )

    def testCreateAndUploadMergedAFDOProfileWorksInTheHappyCase(self):
        merged_name, mocks = self.runCreateAndUploadMergedAFDOProfileOnce()
        self.assertIsNotNone(merged_name)

        # Note that we always return the *basename*
        self.assertEqual(
            merged_name,
            self._benchmark_afdo_profile_name(
                major=9999, merged_suffix=True, compression_suffix=False
            ),
        )

        cros_build_lib.run.assert_called_once()

        # Note that these should all be in-chroot names.
        expected_ordered_args = ["llvm-profdata", "merge", "-sample"]

        def _afdo_name(major, build=0, patch=0, merged_suffix=False):
            return self._benchmark_afdo_profile_name(
                major=major,
                build=build,
                patch=patch,
                merged_suffix=merged_suffix,
                compression_suffix=False,
            )

        input_afdo_names = [
            _afdo_name(major=10, build=13, patch=1),
            _afdo_name(major=10, build=13, patch=2),
            _afdo_name(major=11, build=14),
            _afdo_name(major=11, build=15),
            _afdo_name(major=9999),
        ]

        output_afdo_name = _afdo_name(major=9999, merged_suffix=True)
        expected_unordered_args = [
            "-output="
            + os.path.join(self.output_dir_inchroot, "raw-" + output_afdo_name)
        ] + [
            "-weighted-input=1," + os.path.join(self.output_dir_inchroot, n)
            for n in input_afdo_names
        ]

        args = cros_build_lib.run.call_args[0][0]
        ordered_args = args[: len(expected_ordered_args)]
        self.assertEqual(ordered_args, expected_ordered_args)

        unordered_args = args[len(expected_ordered_args) :]
        self.assertCountEqual(unordered_args, expected_unordered_args)
        self.assertEqual(mocks.gs_context.Copy.call_count, 4)
        self.assertEqual(mocks.uncompress_file.call_count, 4)

        def call_for(name):
            basis = os.path.join(self.output_dir, name)
            return mock.call(
                basis + toolchain_util.BZ2_COMPRESSION_SUFFIX, basis
            )

        # The last profile is not compressed, so no need to uncompress it
        mocks.uncompress_file.assert_has_calls(
            any_order=True, calls=[call_for(n) for n in input_afdo_names[:-1]]
        )

    def testCreateAndUploadMergedAFDOProfileWorksForArm(self):
        prof = self._benchmark_afdo_profile_name(
            major=9999, compression_suffix=False, arch="arm"
        )
        merged_name, mocks = self.runCreateAndUploadMergedAFDOProfileOnce(
            unmerged_name=prof, arch="arm"
        )
        self.assertIsNotNone(merged_name)

        # Note that we always return the *basename*
        self.assertEqual(
            merged_name,
            self._benchmark_afdo_profile_name(
                major=9999,
                merged_suffix=True,
                compression_suffix=False,
                arch="arm",
            ),
        )

        cros_build_lib.run.assert_called_once()

        # Note that these should all be in-chroot names.
        expected_ordered_args = ["llvm-profdata", "merge", "-sample"]

        def _afdo_name(major, build=0, patch=0, merged_suffix=False):
            return self._benchmark_afdo_profile_name(
                major=major,
                build=build,
                patch=patch,
                merged_suffix=merged_suffix,
                compression_suffix=False,
                arch="arm",
            )

        input_afdo_names = [
            _afdo_name(major=10, build=13),
            _afdo_name(major=10, build=13, patch=1),
            _afdo_name(major=11, build=14),
            _afdo_name(major=11, build=15),
            _afdo_name(major=9999),
        ]

        output_afdo_name = _afdo_name(major=9999, merged_suffix=True)
        expected_unordered_args = [
            "-output="
            + os.path.join(self.output_dir_inchroot, "raw-" + output_afdo_name)
        ] + [
            "-weighted-input=1," + os.path.join(self.output_dir_inchroot, n)
            for n in input_afdo_names
        ]

        args = cros_build_lib.run.call_args[0][0]
        ordered_args = args[: len(expected_ordered_args)]
        self.assertEqual(ordered_args, expected_ordered_args)

        unordered_args = args[len(expected_ordered_args) :]
        self.assertCountEqual(unordered_args, expected_unordered_args)
        self.assertEqual(mocks.gs_context.Copy.call_count, 4)
        self.assertEqual(mocks.uncompress_file.call_count, 4)

        def call_for(name):
            basis = os.path.join(self.output_dir, name)
            return mock.call(
                basis + toolchain_util.BZ2_COMPRESSION_SUFFIX, basis
            )

        # The last profile is not compressed, so no need to uncompress it
        mocks.uncompress_file.assert_has_calls(
            any_order=True, calls=[call_for(n) for n in input_afdo_names[:-1]]
        )

    def testMergeIsOKIfWeFindFewerProfilesThanWeWant(self):
        merged_name, mocks = self.runCreateAndUploadMergedAFDOProfileOnce(
            recent_to_merge=1000, max_age_days=1000
        )
        self.assertIsNotNone(merged_name)
        self.assertEqual(mocks.gs_context.Copy.call_count, 9)

    def testNoFilesAfterUnmergedNameAreIncluded(self):
        max_name = self._benchmark_afdo_profile_name(
            major=10, build=11, patch=2, compression_suffix=False
        )
        # Profiles in this test can be older than 14 days.
        merged_name, mocks = self.runCreateAndUploadMergedAFDOProfileOnce(
            unmerged_name=max_name, max_age_days=21
        )
        self.assertIsNotNone(merged_name)

        self.assertEqual(
            self._benchmark_afdo_profile_name(
                major=10,
                build=11,
                patch=2,
                merged_suffix=True,
                compression_suffix=False,
            ),
            merged_name,
        )

        def _afdo_name(major, build, patch=0, merged_suffix=False):
            return self._benchmark_afdo_profile_name(
                major=major,
                build=build,
                patch=patch,
                merged_suffix=merged_suffix,
                compression_suffix=False,
            )

        # Note that these should all be in-chroot names.
        expected_ordered_args = ["llvm-profdata", "merge", "-sample"]
        expected_unordered_args = [
            "-output="
            + os.path.join(
                self.output_dir_inchroot,
                "raw-"
                + _afdo_name(major=10, build=11, patch=2, merged_suffix=True),
            ),
        ] + [
            "-weighted-input=1," + os.path.join(self.output_dir_inchroot, s)
            for s in [
                _afdo_name(major=10, build=9),
                _afdo_name(major=10, build=10),
                _afdo_name(major=10, build=11),
                _afdo_name(major=10, build=11, patch=2),
            ]
        ]

        args = cros_build_lib.run.call_args[0][0]
        ordered_args = args[: len(expected_ordered_args)]
        self.assertEqual(ordered_args, expected_ordered_args)

        unordered_args = args[len(expected_ordered_args) :]
        self.assertCountEqual(unordered_args, expected_unordered_args)

        self.assertEqual(mocks.gs_context.Copy.call_count, 3)
        self.assertEqual(mocks.uncompress_file.call_count, 3)

    def testMergeDoesntHappenIfNoProfilesAreMerged(self):
        runs = [
            self.runCreateAndUploadMergedAFDOProfileOnce(recent_to_merge=1),
            self.runCreateAndUploadMergedAFDOProfileOnce(max_age_days=0),
        ]

        for merged_name, mocks in runs:
            self.assertIsNone(merged_name)
            self.gs_context.Copy.assert_not_called()
            cros_build_lib.run.assert_not_called()
            mocks.uncompress_file.assert_not_called()
            mocks.compress_file.assert_not_called()

    def testCreateAndUploadMergedAFDOProfileNoProfiles(self):
        unmerged_name = self._benchmark_afdo_profile_name(major=10, build=13)
        merged_name = None
        self.gs_context.List = mock.MagicMock()
        self.gs_context.List.side_effect = gs.GSNoSuchKey("No objects")

        merged_name = self.obj._CreateAndUploadMergedAFDOProfile(
            unmerged_name, self.output_dir
        )

        self.assertIsNone(merged_name)


class GetUpdatedFilesTest(cros_test_lib.MockTempDirTestCase):
    """Test functions in class GetUpdatedFilesForCommit."""

    def setUp(self):
        # Prepare a JSON file containing metadata
        toolchain_util.TOOLCHAIN_UTILS_PATH = self.tempdir
        osutils.SafeMakedirs(os.path.join(self.tempdir, "afdo_metadata"))
        self.json_file = os.path.join(
            self.tempdir, "afdo_metadata/kernel_afdo_4_14.json"
        )
        self.kernel = "4.14"
        self.kernel_name = self.kernel.replace(".", "_")
        self.kernel_key_name = f"chromeos-kernel-{self.kernel_name}"
        self.afdo_sorted_by_freshness = [
            "R78-3865.0-1560000000.afdo",
            "R78-3869.38-1562580965.afdo",
            "R78-3866.0-1570000000.afdo",
        ]
        self.afdo_versions = {
            self.kernel_key_name: {
                "name": self.afdo_sorted_by_freshness[1],
            },
        }

        with open(self.json_file, "w", encoding="utf-8") as f:
            json.dump(self.afdo_versions, f)
        self.artifact_path = os.path.join(
            "/any/path/to/",
            self.afdo_sorted_by_freshness[2]
            + toolchain_util.KERNEL_AFDO_COMPRESSION_SUFFIX,
        )
        self.profile_info = {
            "kernel_version": self.kernel,
            "arch": "amd64",
        }

    def testUpdateKernelMetadataFailureWithInvalidKernel(self):
        with self.assertRaises(AssertionError) as context:
            toolchain_util.GetUpdatedFilesHandler._UpdateKernelMetadata(
                "3.8", None
            )
        self.assertIn("does not exist", str(context.exception))

    def testUpdateKernelMetadataFailureWithOlderProfile(self):
        with self.assertRaises(AssertionError) as context:
            toolchain_util.GetUpdatedFilesHandler._UpdateKernelMetadata(
                self.kernel, self.afdo_sorted_by_freshness[0]
            )
        self.assertIn("is not newer than", str(context.exception))

    def testUpdateKernelMetadataPass(self):
        toolchain_util.GetUpdatedFilesHandler._UpdateKernelMetadata(
            self.kernel, self.afdo_sorted_by_freshness[2]
        )
        # Check changes in JSON file
        new_afdo_versions = json.loads(osutils.ReadFile(self.json_file))
        self.assertEqual(len(self.afdo_versions), len(new_afdo_versions))
        self.assertEqual(
            new_afdo_versions[self.kernel_key_name]["name"],
            self.afdo_sorted_by_freshness[2],
        )
        # TODO(b/236161656): Fix.
        # pylint: disable-next=consider-using-dict-items
        for k in self.afdo_versions:
            # Make sure other fields are not changed
            if k != self.kernel_key_name:
                self.assertEqual(self.afdo_versions[k], new_afdo_versions[k])

    def testUpdateKernelProfileMetadata(self):
        ret_files, ret_commit = toolchain_util.GetUpdatedFiles(
            "VerifiedKernelCwpAfdoFile", self.artifact_path, self.profile_info
        )
        file_to_update = os.path.join(
            self.tempdir,
            "afdo_metadata",
            f"kernel_afdo_{self.kernel_name}.json",
        )
        self.assertEqual(ret_files, [file_to_update])
        self.assertIn("Publish new kernel profiles", ret_commit)
        self.assertIn(
            f"Update 4.14 to {self.afdo_sorted_by_freshness[2]}", ret_commit
        )

    def testUpdateFailWithOtherTypes(self):
        with self.assertRaises(
            toolchain_util.GetUpdatedFilesForCommitError
        ) as context:
            toolchain_util.GetUpdatedFiles("OtherType", "", "")
        self.assertIn(
            "has no handler in GetUpdatedFiles", str(context.exception)
        )
