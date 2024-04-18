# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Android service unittests."""

import os
import re
from typing import Dict

from chromite.lib import cros_test_lib
from chromite.lib import gs
from chromite.lib import gs_unittest
from chromite.lib import osutils
from chromite.service import android


_STAT_OUTPUT = """%s:
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


def _RaiseGSNoSuchKey(*_args, **_kwargs):
    raise gs.GSNoSuchKey("file does not exist")


class ArtifactsConfigTest(cros_test_lib.TestCase):
    """Tests to ensure artifacts configs are properly written."""

    def testAllTargetsAreConfigured(self):
        """Ensure artifact patterns are configured for all pkgs and targets."""
        self.assertSetEqual(
            set(android.ARTIFACTS_TO_COPY),
            set(android.ANDROID_PACKAGE_TO_BUILD_TARGETS),
            "Branches configured in ARTIFACTS_TO_COPY doesn't "
            "match list of all Android branches",
        )
        for (
            package,
            ebuild_target,
        ) in android.ANDROID_PACKAGE_TO_BUILD_TARGETS.items():
            self.assertSetEqual(
                set(android.ARTIFACTS_TO_COPY[package]),
                set(ebuild_target.values()),
                f"For package {package}, targets configured in "
                "ARTIFACTS_TO_COPY doesn't match list of all "
                "supported targets",
            )


class GetAndroidBranchForPackageTest(cros_test_lib.TestCase):
    """Tests for GetAndroidBranchForPackage."""

    def testAllPackagesAreMapped(self):
        """Ensure all possible Android packages are mapped to valid branches."""
        for package in android.GetAllAndroidPackages():
            android.GetAndroidBranchForPackage(package)

    def testRaisesOnUnknownPackage(self):
        """Ensure passing an unknown package raises an exception."""
        with self.assertRaises(ValueError):
            android.GetAndroidBranchForPackage("not-an-android-package")


class GetAndroidEbuildTargetsForPackageTest(cros_test_lib.TestCase):
    """Tests for GetAndroidEbuildTargetsForPackage."""

    def testAllPackagesAreMapped(self):
        """Ensure all possible Android packages are mapped."""
        for package in android.GetAllAndroidPackages():
            android.GetAndroidEbuildTargetsForPackage(package)

    def testRaisesOnUnknownPackage(self):
        """Ensure passing an unknown package raises an exception."""
        with self.assertRaises(ValueError):
            android.GetAndroidEbuildTargetsForPackage("not-an-android-package")


class MockAndroidBuildArtifactsTest(cros_test_lib.MockTempDirTestCase):
    """Tests using a mocked GS bucket containing Android build artifacts."""

    def setUp(self):
        """Setup vars and create mock dir."""
        self.android_package = "android-package"
        self.mock_android_dir = os.path.join(self.tempdir, "android-package")

        self.arm_acl_data = "-g google.com:READ"
        self.x86_acl_data = "-g google.com:WRITE"
        self.public_acl_data = "-u AllUsers:READ"
        self.arm_acl = os.path.join(
            self.mock_android_dir, android.ARC_BUCKET_ACL_ARM
        )
        self.x86_acl = os.path.join(
            self.mock_android_dir, android.ARC_BUCKET_ACL_X86
        )
        self.public_acl = os.path.join(
            self.mock_android_dir, android.ARC_BUCKET_ACL_PUBLIC
        )

        osutils.WriteFile(self.arm_acl, self.arm_acl_data, makedirs=True)
        osutils.WriteFile(self.x86_acl, self.x86_acl_data, makedirs=True)
        osutils.WriteFile(self.public_acl, self.public_acl_data, makedirs=True)

        self.bucket_url = "gs://u"
        self.gs_mock = self.StartPatcher(gs_unittest.GSContextMock())
        self.arc_bucket_url = "gs://a"
        self.targets = {
            "apps": "^(foo|bar)$",
            "target_arm": r"\.zip$",
            "target_x86": r"\.zip$",
        }

        self.PatchDict(
            android.ARTIFACTS_TO_COPY, {self.android_package: self.targets}
        )

    def setupMockTarget(
        self, branch: str, target: str, versions: Dict[str, bool]
    ):
        """Mocks GS responses for one build target.

        Mocks GS responses for the following paths:
        {src_bucket}/{branch}-linux-{target}
        {src_bucket}/{branch}-linux-{target}/{version}
        {src_bucket}/{branch}-linux-{target}/{version}/{subpath}
        {src_bucket}/{branch}-linux-{target}/{version}/{subpath}/*
        {dst_bucket}/{branch}-linux-{target}
        {dst_bucket}/{branch}-linux-{target}/{version}
        {dst_bucket}/{branch}-linux-{target}/{version}/*

        Each version can be either valid (artifacts exist) or invalid (returns
        file not found error), specified via the `versions` dict.

        Args:
            branch: The branch.
            target: The build target.
            versions: A mapping between versions to mock for this target and
                whether each version is valid.
        """
        # `gsutil ls gs://<bucket>/<target>` shows all available versions.
        url = f"{self.bucket_url}/{branch}-linux-{target}"
        stdout = "\n".join(f"{url}/{version}" for version in versions)
        self.gs_mock.AddCmdResult(["ls", "--", url], stdout=stdout)

        for version, valid in versions.items():
            self.mockOneTargetVersion(branch, target, version, valid)

    def mockOneTargetVersion(self, branch, target, version, valid):
        """Mock GS responses for one (target, version). See setupMockTarget."""

        src_url = f"{self.bucket_url}/{branch}-linux-{target}/{version}"
        if not valid:
            self.gs_mock.AddCmdResult(
                ["ls", "--", src_url], side_effect=_RaiseGSNoSuchKey
            )
            return

        # Show source subpath directory.
        src_subdir = f"{src_url}/{target}{version}"
        self.gs_mock.AddCmdResult(["ls", "--", src_url], stdout=src_subdir)

        # Show files.
        mock_file_template_list = {
            "apps": ["foo", "bar", "baz"],
            "target_arm": [
                "foo-%(version)s.zip",
                "bar.zip",
                "baz",
            ],
            "target_x86": [
                "foo-%(version)s.zip",
                "bar.zip",
                "baz",
            ],
        }
        filelist = [
            template % {"version": version}
            for template in mock_file_template_list[target]
        ]
        src_filelist = [
            os.path.join(src_subdir, filename) for filename in filelist
        ]
        self.gs_mock.AddCmdResult(
            ["ls", "--", src_subdir], stdout="\n".join(src_filelist)
        )
        for src_file in src_filelist:
            self.gs_mock.AddCmdResult(
                ["stat", "--", src_file],
                stdout=_STAT_OUTPUT % src_url,
            )

        # Show nothing in destination.
        dst_url = f"{self.arc_bucket_url}/{branch}-linux-{target}/{version}"
        filelist = [
            template % {"version": version}
            for template in mock_file_template_list[target]
        ]
        dst_filelist = [
            os.path.join(dst_url, filename) for filename in filelist
        ]
        for dst_file in dst_filelist:
            self.gs_mock.AddCmdResult(
                ["stat", "--", dst_file], side_effect=_RaiseGSNoSuchKey
            )

        for src_file, dst_file in zip(src_filelist, dst_filelist):
            # Only allow copying if file name matches target pattern. Otherwise
            # raise an error to fail the test.
            side_effect = (
                None
                if re.search(self.targets[target], src_file)
                else Exception(
                    f"file gets copied while it shouldn't: {src_file}"
                )
            )
            self.gs_mock.AddCmdResult(
                ["cp", "-v", "--", src_file, dst_file], side_effect=side_effect
            )

        # Allow setting ACL on dest files.
        acls = {
            "apps": self.public_acl_data,
            "target_arm": self.arm_acl_data,
            "target_x86": self.x86_acl_data,
        }
        for dst_file in dst_filelist:
            self.gs_mock.AddCmdResult(
                ["acl", "ch"] + acls[target].split() + [dst_file]
            )

    def testIsBuildIdValid_success(self):
        """Test IsBuildIdValid with a valid build."""
        self.setupMockTarget("android-branch", "apps", {"1000": True})
        self.setupMockTarget("android-branch", "target_arm", {"1000": True})
        self.setupMockTarget("android-branch", "target_x86", {"1000": True})

        subpaths = android.IsBuildIdValid(
            self.android_package, "android-branch", "1000", self.bucket_url
        )
        self.assertDictEqual(
            subpaths,
            {
                "apps": "apps1000",
                "target_arm": "target_arm1000",
                "target_x86": "target_x861000",
            },
        )

    def testIsBuildIdValid_partialExist(self):
        """Test IsBuildIdValid with a partially populated build."""
        self.setupMockTarget("android-branch", "apps", {"1000": False})
        self.setupMockTarget("android-branch", "target_arm", {"1000": True})
        self.setupMockTarget("android-branch", "target_x86", {"1000": True})

        subpaths = android.IsBuildIdValid(
            self.android_package,
            "android-branch",
            "1000",
            self.bucket_url,
        )
        self.assertIsNone(subpaths)

    def testIsBuildIdValid_notExist(self):
        """Test IsBuildIdValid with a nonexistent build."""
        self.setupMockTarget("android-branch", "apps", {"1000": False})
        self.setupMockTarget("android-branch", "target_arm", {"1000": False})
        self.setupMockTarget("android-branch", "target_x86", {"1000": False})

        subpaths = android.IsBuildIdValid(
            self.android_package,
            "android-branch",
            "1000",
            self.bucket_url,
        )
        self.assertIsNone(subpaths)

    def testGetLatestBuild_basic(self):
        """Test determination of latest build from gs bucket."""
        # - build 900 is valid (all targets are populated)
        # - build 1000 is valid
        # - build 1100 is invalid (partially populated)
        self.setupMockTarget(
            "android-branch", "apps", {"900": True, "1000": True, "1100": False}
        )
        self.setupMockTarget(
            "android-branch",
            "target_arm",
            {"900": True, "1000": True, "1100": True},
        )
        self.setupMockTarget(
            "android-branch",
            "target_x86",
            {"900": True, "1000": True, "1100": True},
        )

        version, subpaths = android.GetLatestBuild(
            self.android_package,
            build_branch="android-branch",
            bucket_url=self.bucket_url,
        )
        self.assertEqual(version, "1000")
        self.assertDictEqual(
            subpaths,
            {
                "apps": "apps1000",
                "target_arm": "target_arm1000",
                "target_x86": "target_x861000",
            },
        )

    def testGetLatestBuild_defaultBranch(self):
        """Test if default branch is used when no branch is specified."""
        self.setupMockTarget("default-branch", "apps", {"1000": True})
        self.setupMockTarget("default-branch", "target_arm", {"1000": True})
        self.setupMockTarget("default-branch", "target_x86", {"1000": True})
        self.PatchObject(
            android,
            "GetAndroidBranchForPackage",
            return_value="default-branch",
        )

        version, subpaths = android.GetLatestBuild(
            self.android_package,
            bucket_url=self.bucket_url,
        )
        self.assertEqual(version, "1000")
        self.assertDictEqual(
            subpaths,
            {
                "apps": "apps1000",
                "target_arm": "target_arm1000",
                "target_x86": "target_x861000",
            },
        )

    def testCopyToArcBucket(self):
        """Test copying of images to ARC bucket."""
        self.setupMockTarget("android-branch", "apps", {"1000": True})
        self.setupMockTarget("android-branch", "target_arm", {"1000": True})
        self.setupMockTarget("android-branch", "target_x86", {"1000": True})

        android.CopyToArcBucket(
            self.bucket_url,
            self.android_package,
            "android-branch",
            "1000",
            {
                "apps": "apps1000",
                "target_arm": "target_arm1000",
                "target_x86": "target_x861000",
            },
            self.arc_bucket_url,
            self.mock_android_dir,
        )


class LKGBTest(cros_test_lib.TempDirTestCase):
    """Tests ReadLKGB/WriteLKGB."""

    def testWriteReadLGKB(self):
        android_package_dir = self.tempdir
        build_id = "build-id"

        lkgb = android.LKGB(build_id=build_id)
        android.WriteLKGB(android_package_dir, lkgb)
        self.assertEqual(
            android.ReadLKGB(android_package_dir)["build_id"], build_id
        )

    def testReadLKGBMissing(self):
        android_package_dir = self.tempdir

        with self.assertRaises(android.MissingLKGBError):
            android.ReadLKGB(android_package_dir)

    def testReadLKGBNotJSON(self):
        android_package_dir = self.tempdir
        (android_package_dir / "LKGB.json").write_text(
            "not-a-json-file", encoding="utf-8"
        )

        with self.assertRaises(android.InvalidLKGBError):
            android.ReadLKGB(android_package_dir)

    def testReadLKGBMissingBuildID(self):
        android_package_dir = self.tempdir
        (android_package_dir / "LKGB.json").write_text(
            '{"not_build_id": "foo"}', encoding="utf-8"
        )

        with self.assertRaises(android.InvalidLKGBError):
            android.ReadLKGB(android_package_dir)

    def testReadLKGBDiscardUnusedFields(self):
        android_package_dir = self.tempdir
        (android_package_dir / "LKGB.json").write_text(
            """{
    "build_id": "build-id",
    "branch": "branch",
    "runtime_artifacts_pin": "runtime-artifacts-pin",
    "unused": "foo"
}""",
            encoding="utf-8",
        )

        lkgb = android.ReadLKGB(android_package_dir)
        self.assertEqual(
            lkgb,
            dict(
                build_id="build-id",
                branch="branch",
                runtime_artifacts_pin="runtime-artifacts-pin",
            ),
        )


class RuntimeArtifactsTest(cros_test_lib.MockTestCase):
    """Tests runtime artifacts functions."""

    def setUp(self):
        self.android_package = "android-package"
        self.android_branch = "android-branch"
        self.runtime_artifacts_bucket_url = "gs://r"
        self.milestone = "99"

        self.gs_mock = self.StartPatcher(gs_unittest.GSContextMock())

    def setupMockRuntimeDataBuild(self, android_version):
        """Helper to mock a build for runtime data."""

        _ARCHS = ("arm", "arm64", "arm64only", "x86", "x86_64", "x64only")
        _BUILD_TYPES = ("user", "userdebug")
        _RUNTIME_DATAS = (
            "packages_reference",
            "gms_core_cache",
            "tts_cache",
            "dex_opt_cache",
        )

        for arch in _ARCHS:
            for build_type in _BUILD_TYPES:
                for runtime_data in _RUNTIME_DATAS:
                    path = (
                        f"{self.runtime_artifacts_bucket_url}/"
                        f"{self.android_package}/"
                        f"{runtime_data}_{arch}_"
                        f"{build_type}_{android_version}.tar"
                    )
                    self.gs_mock.AddCmdResult(
                        ["stat", "--", path], side_effect=_RaiseGSNoSuchKey
                    )

        _UREADAHEAD_DATA = "ureadahead_pack_host"
        _BINARY_TRANSLATION_TYPES = ("houdini", "ndk", "native")
        for arch in _ARCHS:
            for build_type in _BUILD_TYPES:
                for binary_translation_type in _BINARY_TRANSLATION_TYPES:
                    if (
                        "x86" in arch and binary_translation_type == "native"
                    ) or (
                        "arm" in arch and binary_translation_type != "native"
                    ):
                        continue

                    path = (
                        f"{self.runtime_artifacts_bucket_url}/"
                        f"{self.android_package}/"
                        f"{_UREADAHEAD_DATA}_{arch}_{binary_translation_type}_"
                        f"{build_type}_{android_version}.tar"
                    )
                    self.gs_mock.AddCmdResult(
                        ["stat", "--", path], side_effect=_RaiseGSNoSuchKey
                    )

    def setupMockRuntimeArtifactsPin(self, pin_version):
        """Helper to mock a runtime artifacts pin on GS."""
        pin_paths = [
            (
                f"{self.runtime_artifacts_bucket_url}/"
                f"{self.android_package}/M{self.milestone}_pin_version"
            ),
            (
                f"{self.runtime_artifacts_bucket_url}/"
                f"{self.android_branch}_pin_version"
            ),
        ]
        for _, pin_path in enumerate(pin_paths):
            if pin_version:
                self.gs_mock.AddCmdResult(
                    ["stat", "--", pin_path], stdout=_STAT_OUTPUT % pin_path
                )
                self.gs_mock.AddCmdResult(["cat", pin_path], stdout=pin_version)
            else:
                self.gs_mock.AddCmdResult(
                    ["stat", "--", pin_path], side_effect=_RaiseGSNoSuchKey
                )

    def testFindDataCollectorArtifacts(self):
        android_version = "100"
        # Mock by default runtime artifacts are not found.
        self.setupMockRuntimeDataBuild(android_version)

        # Override few as existing.
        path0 = (
            "gs://r/android-package/"
            "ureadahead_pack_host_x86_64_houdini_user_100.tar"
        )
        path1 = (
            "gs://r/android-package/"
            "ureadahead_pack_host_x86_64_ndk_user_100.tar"
        )
        path2 = (
            "gs://r/android-package/"
            "ureadahead_pack_host_arm64_native_user_100.tar"
        )
        path3 = (
            "gs://r/android-package/"
            "ureadahead_pack_host_x86_64_houdini_userdebug_100.tar"
        )
        path4 = (
            "gs://r/android-package/packages_reference_arm_userdebug_100.tar"
        )
        path5 = "gs://r/android-package/gms_core_cache_arm_userdebug_100.tar"
        path6 = "gs://r/android-package/tts_cache_arm64_user_100.tar"
        path7 = "gs://r/android-package/dex_opt_cache_x86_user_100.tar"
        path8 = (
            "gs://r/android-package/"
            "packages_reference_x64only_userdebug_100.tar"
        )
        path9 = "gs://r/android-package/gms_core_cache_arm64only_user_100.tar"

        self.gs_mock.AddCmdResult(
            ["stat", "--", path0], stdout=_STAT_OUTPUT % path0
        )
        self.gs_mock.AddCmdResult(
            ["stat", "--", path1], stdout=_STAT_OUTPUT % path1
        )
        self.gs_mock.AddCmdResult(
            ["stat", "--", path2], stdout=_STAT_OUTPUT % path2
        )
        self.gs_mock.AddCmdResult(
            ["stat", "--", path3], stdout=_STAT_OUTPUT % path3
        )
        self.gs_mock.AddCmdResult(
            ["stat", "--", path4], stdout=_STAT_OUTPUT % path4
        )
        self.gs_mock.AddCmdResult(
            ["stat", "--", path5], stdout=_STAT_OUTPUT % path5
        )
        self.gs_mock.AddCmdResult(
            ["stat", "--", path6], stdout=_STAT_OUTPUT % path6
        )
        self.gs_mock.AddCmdResult(
            ["stat", "--", path7], stdout=_STAT_OUTPUT % path7
        )
        self.gs_mock.AddCmdResult(
            ["stat", "--", path8], stdout=_STAT_OUTPUT % path8
        )
        self.gs_mock.AddCmdResult(
            ["stat", "--", path9], stdout=_STAT_OUTPUT % path9
        )

        variables = android.FindDataCollectorArtifacts(
            self.android_package,
            android_version,
            "${PV}",
            self.runtime_artifacts_bucket_url,
        )

        expectation0 = (
            "gs://r/android-package/"
            "ureadahead_pack_host_x86_64_houdini_user_${PV}.tar"
        )
        expectation1 = (
            "gs://r/android-package/"
            "ureadahead_pack_host_x86_64_ndk_user_${PV}.tar"
        )
        expectation2 = (
            "gs://r/android-package/"
            "ureadahead_pack_host_arm64_native_user_${PV}.tar"
        )
        expectation3 = (
            "gs://r/android-package/"
            "ureadahead_pack_host_x86_64_houdini_userdebug_${PV}.tar"
        )
        expectation4 = (
            "gs://r/android-package/packages_reference_arm_userdebug_${PV}.tar"
        )
        expectation5 = (
            "gs://r/android-package/gms_core_cache_arm_userdebug_${PV}.tar"
        )
        expectation6 = "gs://r/android-package/tts_cache_arm64_user_${PV}.tar"
        expectation7 = "gs://r/android-package/dex_opt_cache_x86_user_${PV}.tar"
        expectation8 = (
            "gs://r/android-package/"
            "packages_reference_x64only_userdebug_${PV}.tar"
        )
        expectation9 = (
            "gs://r/android-package/gms_core_cache_arm64only_user_${PV}.tar"
        )

        self.assertDictEqual(
            variables,
            {
                "X86_64_HOUDINI_USER_UREADAHEAD_PACK_HOST": expectation0,
                "X86_64_NDK_USER_UREADAHEAD_PACK_HOST": expectation1,
                "ARM64_NATIVE_USER_UREADAHEAD_PACK_HOST": expectation2,
                "X86_64_HOUDINI_USERDEBUG_UREADAHEAD_PACK_HOST": expectation3,
                "ARM_USERDEBUG_PACKAGES_REFERENCE": expectation4,
                "ARM_USERDEBUG_GMS_CORE_CACHE": expectation5,
                "ARM64_USER_TTS_CACHE": expectation6,
                "X86_USER_DEX_OPT_CACHE": expectation7,
                "X64ONLY_USERDEBUG_PACKAGES_REFERENCE": expectation8,
                "ARM64ONLY_USER_GMS_CORE_CACHE": expectation9,
            },
        )

    def testFindDataCollectorArtifactsNotExist(self):
        android_version = "100"
        # Mock by default runtime artifacts are not found.
        self.setupMockRuntimeDataBuild(android_version)

        # Invalid paths that should be ignored.
        invalid_path1 = (
            "gs://r/android-package/"
            "ureadahead_pack_host_arm64_houdini_user_100.tar"
        )
        invalid_path2 = (
            "gs://r/android-package/"
            "ureadahead_pack_host_x86_64_native_user_100.tar"
        )
        invalid_path3 = (
            "gs://r/android-package/ureadahead_pack_host_arm64_ndk_user_100.tar"
        )
        invalid_path4 = (
            "gs://r/android-package/ureadahead_pack_host_x86_64_user_100.tar"
        )
        self.gs_mock.AddCmdResult(
            ["stat", "--", invalid_path1], stdout=_STAT_OUTPUT % invalid_path1
        )
        self.gs_mock.AddCmdResult(
            ["stat", "--", invalid_path2], stdout=_STAT_OUTPUT % invalid_path2
        )
        self.gs_mock.AddCmdResult(
            ["stat", "--", invalid_path3], stdout=_STAT_OUTPUT % invalid_path3
        )
        self.gs_mock.AddCmdResult(
            ["stat", "--", invalid_path4], stdout=_STAT_OUTPUT % invalid_path4
        )

        variables = android.FindDataCollectorArtifacts(
            self.android_package,
            android_version,
            "${PV}",
            self.runtime_artifacts_bucket_url,
        )

        self.assertDictEqual(variables, {})

    def testFindRuntimeArtifactsPin(self):
        self.setupMockRuntimeArtifactsPin("pin-version")

        pin_version = android.FindRuntimeArtifactsPin(
            self.android_package,
            self.milestone,
            self.runtime_artifacts_bucket_url,
        )
        self.assertEqual(pin_version, "pin-version")

    def testFindRuntimeArtifactsPinNotExist(self):
        self.setupMockRuntimeArtifactsPin(None)

        pin_version = android.FindRuntimeArtifactsPin(
            self.android_package,
            self.milestone,
            self.runtime_artifacts_bucket_url,
        )
        self.assertIsNone(pin_version)
