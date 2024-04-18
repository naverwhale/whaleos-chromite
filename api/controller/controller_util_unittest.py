# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""controller_util unittests."""

from pathlib import Path

from chromite.api.controller import controller_util
from chromite.api.gen.chromite.api import build_api_test_pb2
from chromite.api.gen.chromite.api import sysroot_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import binpkg
from chromite.lib import build_target_lib
from chromite.lib import chroot_lib
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import sysroot_lib
from chromite.lib.parser import package_info


class ParseChrootTest(cros_test_lib.MockTestCase):
    """ParseChroot tests."""

    def testSuccess(self):
        """Test successful handling case."""
        path = "/chroot/path"
        cache_dir = "/cache/dir"
        chrome_root = "/chrome/root"
        use_flags = [{"flag": "useflag1"}, {"flag": "useflag2"}]
        features = [{"feature": "feature1"}, {"feature": "feature2"}]
        expected_env = {
            "USE": "useflag1 useflag2",
            "FEATURES": "feature1 feature2",
            "CHROME_ORIGIN": "LOCAL_SOURCE",
        }

        chroot_message = common_pb2.Chroot(
            path=path,
            cache_dir=cache_dir,
            chrome_dir=chrome_root,
            env={"use_flags": use_flags, "features": features},
        )

        expected = chroot_lib.Chroot(
            path=path,
            cache_dir=cache_dir,
            chrome_root=chrome_root,
            env=expected_env,
        )
        result = controller_util.ParseChroot(chroot_message)

        self.assertEqual(expected, result)

    def testWrongMessage(self):
        """Test invalid message type given."""
        with self.assertRaises(AssertionError):
            controller_util.ParseChroot(common_pb2.BuildTarget())


class ParseSysrootTest(cros_test_lib.MockTestCase):
    """ParseSysroot tests."""

    def testSuccess(self):
        """test successful handling case."""
        path = "/build/rare_pokemon"
        sysroot_message = sysroot_pb2.Sysroot(path=path)
        expected = sysroot_lib.Sysroot(path=path)
        result = controller_util.ParseSysroot(sysroot_message)
        self.assertEqual(expected, result)

    def testWrongMessage(self):
        with self.assertRaises(AssertionError):
            controller_util.ParseSysroot(common_pb2.BuildTarget())


class ParseBuildTargetTest(cros_test_lib.TestCase):
    """ParseBuildTarget tests."""

    def testSuccess(self):
        """Test successful handling case."""
        name = "board"
        build_target_message = common_pb2.BuildTarget(name=name)
        expected = build_target_lib.BuildTarget(name)
        result = controller_util.ParseBuildTarget(build_target_message)

        self.assertEqual(expected, result)

    def testParseProfile(self):
        """Test the parsing of a profile."""
        name = "build-target-name"
        profile = "profile"
        build_target_msg = common_pb2.BuildTarget(name=name)
        profile_msg = sysroot_pb2.Profile(name=profile)

        expected = build_target_lib.BuildTarget(name, profile=profile)
        result = controller_util.ParseBuildTarget(
            build_target_msg, profile_message=profile_msg
        )

        self.assertEqual(expected, result)

    def testWrongMessage(self):
        """Test invalid message type given."""
        with self.assertRaises(AssertionError):
            controller_util.ParseBuildTarget(
                build_api_test_pb2.TestRequestMessage()
            )


class ParseBuildTargetsTest(cros_test_lib.TestCase):
    """ParseBuildTargets tests."""

    def testSuccess(self):
        """Test successful handling case."""
        names = ["foo", "bar", "baz"]
        message = build_api_test_pb2.TestRequestMessage()
        for name in names:
            message.build_targets.add().name = name

        result = controller_util.ParseBuildTargets(message.build_targets)

        expected = [build_target_lib.BuildTarget(name) for name in names]
        self.assertCountEqual(expected, result)

    def testWrongMessage(self):
        """Wrong message type handling."""
        message = common_pb2.Chroot()
        message.env.use_flags.add().flag = "foo"
        message.env.use_flags.add().flag = "bar"

        with self.assertRaises(AssertionError):
            controller_util.ParseBuildTargets(message.env.use_flags)


class PackageInfoToStringTest(cros_test_lib.TestCase):
    """PackageInfoToString tests."""

    def testAllFields(self):
        """Test all fields present."""
        pi = common_pb2.PackageInfo()
        pi.package_name = "pkg"
        pi.category = "cat"
        pi.version = "2.0.0"

        cpv_str = controller_util.PackageInfoToString(pi)

        self.assertEqual("cat/pkg-2.0.0", cpv_str)

    def testNoVersion(self):
        """Test no version provided."""
        pi = common_pb2.PackageInfo()
        pi.package_name = "pkg"
        pi.category = "cat"

        cpv_str = controller_util.PackageInfoToString(pi)

        self.assertEqual("cat/pkg", cpv_str)

    def testPackageOnly(self):
        """Test no version provided."""
        pi = common_pb2.PackageInfo()
        pi.package_name = "pkg"

        cpv_str = controller_util.PackageInfoToString(pi)

        self.assertEqual("pkg", cpv_str)

    def testNoPackageName(self):
        """Test no package name given."""
        pi = common_pb2.PackageInfo()

        with self.assertRaises(ValueError):
            controller_util.PackageInfoToString(pi)


def test_serialize_package_info():
    pkg_info = package_info.parse("foo/bar-1.2.3-r4")
    pkg_info_msg = common_pb2.PackageInfo()
    controller_util.serialize_package_info(pkg_info, pkg_info_msg)
    assert pkg_info_msg.category == "foo"
    assert pkg_info_msg.package_name == "bar"
    assert pkg_info_msg.version == "1.2.3-r4"


def test_deserialize_package_info():
    pkg_info_msg = common_pb2.PackageInfo()
    pkg_info_msg.category = "foo"
    pkg_info_msg.package_name = "bar"
    pkg_info_msg.version = "1.2.3-r4"
    pkg_info = controller_util.deserialize_package_info(pkg_info_msg)
    assert pkg_info.cpvr == "foo/bar-1.2.3-r4"


def test_retrieve_package_log_paths():
    packages = [
        package_info.parse("foo/bar%d-1.0-r1" % num) for num in range(1, 4)
    ]
    output_proto = sysroot_pb2.InstallPackagesResponse()
    target_sysroot = sysroot_lib.Sysroot(path="/path/to/sysroot")
    controller_util.retrieve_package_log_paths(
        packages, output_proto, target_sysroot
    )
    assert len(output_proto.failed_package_data) == 3


def test_package_index_info():
    """Quick check converting to/from protobuf works."""
    sha = "SHA"
    number = 5
    build_target_name = "build_target"
    profile_name = "profile"
    location = "location"

    msg = common_pb2.PackageIndexInfo()
    msg.snapshot_sha = sha
    msg.snapshot_number = number
    msg.build_target.name = build_target_name
    msg.profile.name = profile_name
    msg.location = location

    obj = binpkg.PackageIndexInfo(
        snapshot_sha=sha,
        snapshot_number=number,
        build_target=build_target_lib.BuildTarget(name=build_target_name),
        profile=sysroot_lib.Profile(name=profile_name),
        location=location,
    )

    assert obj == controller_util.deserialize_package_index_info(msg)


class Pb2PathToPathlibPathTest(cros_test_lib.MockTestCase):
    """Verify functionality for pb2_path_to_pathlib_path()."""

    chroot = common_pb2.Chroot(path="/path/to/chroot", out_path="/path/to/out")

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)

    @staticmethod
    def create_pb2_path(path: str, inside: bool) -> common_pb2.Path:
        """Helper function to create a common_pb2.Path."""
        location = (
            common_pb2.Path.Location.INSIDE
            if inside
            else common_pb2.Path.Location.OUTSIDE
        )
        return common_pb2.Path(path=path, location=location)

    def test_relative_inside(self):
        """Verify that passing in a relative path inside the chroot fails"""
        pb2_path = self.create_pb2_path(path="usr/bin", inside=True)
        with self.assertRaises(ValueError):
            controller_util.pb2_path_to_pathlib_path(
                pb2_path, chroot=self.chroot
            )

    def test_relative_outside(self):
        """Verify that passing in a relative path outside the chroot fails"""
        pb2_path = self.create_pb2_path(path="usr/bin", inside=False)
        with self.assertRaises(ValueError):
            controller_util.pb2_path_to_pathlib_path(
                pb2_path, chroot=self.chroot
            )

    def test_inside_with_chroot(self):
        """Verify that we can convert an inside path with a chroot."""
        pb2_path = self.create_pb2_path(path="/usr/bin", inside=True)
        pathlib_path = controller_util.pb2_path_to_pathlib_path(
            pb2_path, chroot=self.chroot
        )
        self.assertEqual(pathlib_path, Path("/path/to/chroot/usr/bin"))

    def test_outside_with_chroot(self):
        """Verify that we can convert an outside path with a chroot."""
        pb2_path = self.create_pb2_path(path="/usr/bin", inside=False)
        pathlib_path = controller_util.pb2_path_to_pathlib_path(
            pb2_path, chroot=self.chroot
        )
        self.assertEqual(pathlib_path, Path("/usr/bin"))

    def test_inside_without_chroot(self):
        """Verify that we cannot convert an inside path without a chroot."""
        pb2_path = self.create_pb2_path(path="/usr/bin", inside=True)
        with self.assertRaises(ValueError):
            controller_util.pb2_path_to_pathlib_path(pb2_path)

    def test_outside_without_chroot(self):
        """Verify that we can convert an outside path without a chroot."""
        pb2_path = self.create_pb2_path(path="/usr/bin", inside=False)
        pathlib_path = controller_util.pb2_path_to_pathlib_path(pb2_path)
        self.assertEqual(pathlib_path, Path("/usr/bin"))
