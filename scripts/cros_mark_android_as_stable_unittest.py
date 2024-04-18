# Copyright 2016 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for cros_mark_android_as_stable.py."""

import builtins
import os
from unittest import mock

from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.scripts import cros_mark_android_as_stable
from chromite.service import android
from chromite.service import packages


pytestmark = cros_test_lib.pytestmark_inside_only


class CrosMarkAndroidAsStable(cros_test_lib.MockTempDirTestCase):
    """Tests for cros_mark_android_as_stable."""

    unstable_data = 'KEYWORDS="~x86 ~arm"'
    stable_data = 'KEYWORDS="x86 arm"'

    STAT_OUTPUT = """%s:
        Creation time:    Sat, 23 Aug 2014 06:53:20 GMT
        Content-Language: en
        Content-Length:   74
        Content-Type:   application/octet-stream
        Hash (crc32c):    BBPMPA==
        Hash (md5):   ms+qSYvgI9SjXn8tW/5UpQ==
        ETag:     CNCgocbmqMACEAE=
        Generation:   1408776800850000
        Metageneration:   1
      """

    def setUp(self):
        """Setup vars and create mock dir."""
        self.android_package = "android-package"
        self.android_branch = "android-branch"
        self.PatchObject(
            android,
            "GetAllAndroidPackages",
            return_value=[self.android_package],
        )
        self.PatchObject(
            android,
            "GetAndroidBranchForPackage",
            return_value=self.android_branch,
        )
        self.PatchObject(
            android,
            "GetAndroidEbuildTargetsForPackage",
            return_value={
                "APPS_TARGET": "apps",
                "ARM64_TARGET": "target_arm64",
                "X86_64_TARGET": "target_x86_64",
            },
        )

        self.mock_find_data_collector_artifacts = self.PatchObject(
            android,
            "FindDataCollectorArtifacts",
            return_value={},
        )
        self.mock_find_runtime_artifacts_pin = self.PatchObject(
            android,
            "FindRuntimeArtifactsPin",
            return_value=None,
        )
        self.PatchObject(
            packages,
            "determine_milestone_version",
            return_value="99",
        )

        self.tmp_overlay = os.path.join(
            self.tempdir, "private-overlays", "project-cheets-private"
        )
        self.mock_android_dir = android.GetAndroidPackageDir(
            self.android_package, overlay_dir=self.tmp_overlay
        )

        ebuild = os.path.join(
            self.mock_android_dir, self.android_package + "-%s.ebuild"
        )
        self.unstable = ebuild % "9999"
        self.old_version = "25"
        self.old = ebuild % ("%s-r1" % self.old_version)
        self.old2_version = "50"
        self.old2 = ebuild % ("%s-r1" % self.old2_version)
        self.new_version = "100"
        self.new = ebuild % ("%s-r1" % self.new_version)

        osutils.WriteFile(self.unstable, self.unstable_data, makedirs=True)
        osutils.WriteFile(self.old, self.stable_data, makedirs=True)
        osutils.WriteFile(self.old2, self.stable_data, makedirs=True)

        self.arc_bucket_url = "gs://a"
        self.runtime_artifacts_bucket_url = "gs://r"

    def testFindAndroidCandidates(self):
        """Test creation of stable ebuilds from mock dir."""
        (unstable, stable) = cros_mark_android_as_stable.FindAndroidCandidates(
            self.mock_android_dir
        )

        stable_ebuild_paths = [x.ebuild_path for x in stable]
        self.assertEqual(unstable.ebuild_path, self.unstable)
        self.assertEqual(len(stable), 2)
        self.assertIn(self.old, stable_ebuild_paths)
        self.assertIn(self.old2, stable_ebuild_paths)

    def testMarkAndroidEBuildAsStable(self):
        """Test updating of ebuild."""
        rc_mock = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc_mock.SetDefaultCmdResult()
        self.PatchObject(
            portage_util.EBuild, "GetCrosWorkonVars", return_value=None
        )
        stable_candidate = portage_util.EBuild(self.old2)
        unstable = portage_util.EBuild(self.unstable)
        android_version = self.new_version
        package_dir = self.mock_android_dir

        revved = cros_mark_android_as_stable.MarkAndroidEBuildAsStable(
            stable_candidate,
            unstable,
            self.android_package,
            android_version,
            package_dir,
            self.android_branch,
            self.arc_bucket_url,
            self.runtime_artifacts_bucket_url,
            False,
        )

        self.assertIsNotNone(revved)
        version_atom, files_to_add, files_to_remove = revved
        self.assertEqual(
            version_atom,
            f"chromeos-base/{self.android_package}-{self.new_version}-r1",
        )
        self.assertEqual(
            files_to_add, [self.new, os.path.join(package_dir, "Manifest")]
        )
        self.assertEqual(files_to_remove, [self.old2])
        self.mock_find_data_collector_artifacts.assert_called()

    def testMarkAndroidEBuildAsStableIgnoreDataCollector(self):
        rc_mock = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc_mock.SetDefaultCmdResult()
        self.PatchObject(
            portage_util.EBuild, "GetCrosWorkonVars", return_value=None
        )
        stable_candidate = portage_util.EBuild(self.old2)
        unstable = portage_util.EBuild(self.unstable)
        android_version = self.new_version
        package_dir = self.mock_android_dir

        cros_mark_android_as_stable.MarkAndroidEBuildAsStable(
            stable_candidate,
            unstable,
            self.android_package,
            android_version,
            package_dir,
            self.android_branch,
            self.arc_bucket_url,
            self.runtime_artifacts_bucket_url,
            True,
        )

        self.mock_find_data_collector_artifacts.assert_not_called()

    def testUpdateDataCollectorArtifacts(self):
        android_version = "100"
        self.mock_find_data_collector_artifacts.return_value = {
            "key1": "val1",
            "key2": "val2",
        }

        variables = cros_mark_android_as_stable.UpdateDataCollectorArtifacts(
            android_version,
            self.runtime_artifacts_bucket_url,
            self.android_package,
        )

        self.assertDictEqual(variables, {"key1": "val1", "key2": "val2"})
        self.mock_find_data_collector_artifacts.assert_called_once_with(
            self.android_package,
            android_version,
            "${PV}",
            self.runtime_artifacts_bucket_url,
        )
        self.mock_find_runtime_artifacts_pin.assert_not_called()

    def testUpdateDataCollectorArtifactsPinBranch(self):
        android_version = "100"
        android_pin_version = "50"

        def _ReturnPinnedArtifacts(_, in_version, *_args, **_kwargs):
            """Return valid result only if input version is the pin version."""
            if in_version == android_pin_version:
                return {"key1": "val1", "key2": "val2"}
            return {}

        self.mock_find_data_collector_artifacts.side_effect = (
            _ReturnPinnedArtifacts
        )
        self.mock_find_runtime_artifacts_pin.return_value = android_pin_version

        variables = cros_mark_android_as_stable.UpdateDataCollectorArtifacts(
            android_version,
            self.runtime_artifacts_bucket_url,
            self.android_package,
        )

        self.assertDictEqual(variables, {"key1": "val1", "key2": "val2"})
        self.mock_find_data_collector_artifacts.assert_has_calls(
            [
                # First call: attempt to find artifacts for current version
                mock.call(
                    self.android_package,
                    android_version,
                    "${PV}",
                    self.runtime_artifacts_bucket_url,
                ),
                # Second call: attempt to find artifacts for pinned version
                mock.call(
                    self.android_package,
                    android_pin_version,
                    android_pin_version,
                    self.runtime_artifacts_bucket_url,
                ),
            ]
        )
        self.mock_find_runtime_artifacts_pin.assert_called_once()

    def testMainRevved(self):
        android_version = self.new_version

        rc_mock = self.StartPatcher(cros_test_lib.RunCommandMock())
        rc_mock.SetDefaultCmdResult()
        self.PatchObject(
            portage_util.EBuild, "GetCrosWorkonVars", return_value=None
        )
        mock_mirror_artifacts = self.PatchObject(
            android, "MirrorArtifacts", return_value=android_version
        )
        mock_print = self.PatchObject(builtins, "print")
        android_bucket_url = "gs://ab"

        cros_mark_android_as_stable.main(
            [
                "--android_bucket_url",
                android_bucket_url,
                "--android_build_branch",
                self.android_branch,
                "--android_package",
                self.android_package,
                "--arc_bucket_url",
                self.arc_bucket_url,
                "--force_version",
                android_version,
                "--srcroot",
                str(self.tempdir),
                "--runtime_artifacts_bucket_url",
                self.runtime_artifacts_bucket_url,
                "--skip_commit",
            ]
        )

        mock_mirror_artifacts.assert_called_once_with(
            self.android_package,
            android_bucket_url,
            self.android_branch,
            self.arc_bucket_url,
            self.mock_android_dir,
            android_version,
        )
        # pylint: disable=line-too-long
        mock_print.assert_called_once_with(
            '\n{"android_atom": "chromeos-base/android-package-100-r1", "modified_files": ["chromeos-base/android-package/android-package-100-r1.ebuild", "chromeos-base/android-package/Manifest", "chromeos-base/android-package/android-package-50-r1.ebuild"], "revved": true}'
        )

    def testMainNotRevved(self):
        android_version = self.old2_version

        # Mock to create a stable ebuild identical to the original.
        def MockMarkAsStable(_unstable_path, new_stable_path, _vars, **_kwargs):
            osutils.WriteFile(new_stable_path, self.stable_data)

        self.PatchObject(
            portage_util.EBuild, "GetCrosWorkonVars", return_value=None
        )
        self.PatchObject(
            portage_util.EBuild, "MarkAsStable", side_effect=MockMarkAsStable
        )
        mock_mirror_artifacts = self.PatchObject(
            android, "MirrorArtifacts", return_value=android_version
        )
        mock_print = self.PatchObject(builtins, "print")
        android_bucket_url = "gs://ab"

        cros_mark_android_as_stable.main(
            [
                "--android_bucket_url",
                android_bucket_url,
                "--android_build_branch",
                self.android_branch,
                "--android_package",
                self.android_package,
                "--arc_bucket_url",
                self.arc_bucket_url,
                "--force_version",
                android_version,
                "--srcroot",
                str(self.tempdir),
                "--runtime_artifacts_bucket_url",
                self.runtime_artifacts_bucket_url,
                "--skip_commit",
            ]
        )

        mock_mirror_artifacts.assert_called_once_with(
            self.android_package,
            android_bucket_url,
            self.android_branch,
            self.arc_bucket_url,
            self.mock_android_dir,
            android_version,
        )
        mock_print.assert_called_once_with('\n{"revved": false}')
