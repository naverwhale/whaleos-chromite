# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""controller_util unittests."""

from chromite.api.controller import controller_util
from chromite.api.gen.chromite.api import build_api_test_pb2
from chromite.api.gen.chromite.api import sysroot_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import build_target_lib
from chromite.lib import cros_test_lib
from chromite.lib.parser import package_info
from chromite.lib.chroot_lib import Chroot
from chromite.lib.sysroot_lib import Sysroot


class ParseChrootTest(cros_test_lib.MockTestCase):
  """ParseChroot tests."""

  def testSuccess(self):
    """Test successful handling case."""
    path = '/chroot/path'
    cache_dir = '/cache/dir'
    chrome_root = '/chrome/root'
    use_flags = [{'flag': 'useflag1'}, {'flag': 'useflag2'}]
    features = [{'feature': 'feature1'}, {'feature': 'feature2'}]
    expected_env = {'USE': 'useflag1 useflag2',
                    'FEATURES': 'feature1 feature2',
                    'CHROME_ORIGIN': 'LOCAL_SOURCE'}

    chroot_message = common_pb2.Chroot(path=path, cache_dir=cache_dir,
                                       chrome_dir=chrome_root,
                                       env={'use_flags': use_flags,
                                            'features': features})

    expected = Chroot(path=path, cache_dir=cache_dir, chrome_root=chrome_root,
                      env=expected_env)
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
    path = '/build/rare_pokemon'
    sysroot_message = sysroot_pb2.Sysroot(path=path)
    expected = Sysroot(path=path)
    result = controller_util.ParseSysroot(sysroot_message)
    self.assertEqual(expected, result)

  def testWrongMessage(self):
    with self.assertRaises(AssertionError):
      controller_util.ParseSysroot(common_pb2.BuildTarget())

class ParseBuildTargetTest(cros_test_lib.TestCase):
  """ParseBuildTarget tests."""

  def testSuccess(self):
    """Test successful handling case."""
    name = 'board'
    build_target_message = common_pb2.BuildTarget(name=name)
    expected = build_target_lib.BuildTarget(name)
    result = controller_util.ParseBuildTarget(build_target_message)

    self.assertEqual(expected, result)

  def testParseProfile(self):
    """Test the parsing of a profile."""
    name = 'build-target-name'
    profile = 'profile'
    build_target_msg = common_pb2.BuildTarget(name=name)
    profile_msg = sysroot_pb2.Profile(name=profile)

    expected = build_target_lib.BuildTarget(name, profile=profile)
    result = controller_util.ParseBuildTarget(
        build_target_msg, profile_message=profile_msg)

    self.assertEqual(expected, result)


  def testWrongMessage(self):
    """Test invalid message type given."""
    with self.assertRaises(AssertionError):
      controller_util.ParseBuildTarget(build_api_test_pb2.TestRequestMessage())


class ParseBuildTargetsTest(cros_test_lib.TestCase):
  """ParseBuildTargets tests."""

  def testSuccess(self):
    """Test successful handling case."""
    names = ['foo', 'bar', 'baz']
    message = build_api_test_pb2.TestRequestMessage()
    for name in names:
      message.build_targets.add().name = name

    result = controller_util.ParseBuildTargets(message.build_targets)

    expected = [build_target_lib.BuildTarget(name) for name in names]
    self.assertCountEqual(expected, result)

  def testWrongMessage(self):
    """Wrong message type handling."""
    message = common_pb2.Chroot()
    message.env.use_flags.add().flag = 'foo'
    message.env.use_flags.add().flag = 'bar'

    with self.assertRaises(AssertionError):
      controller_util.ParseBuildTargets(message.env.use_flags)


class PackageInfoToCPVTest(cros_test_lib.TestCase):
  """PackageInfoToCPV tests."""

  def testAllFields(self):
    """Quick sanity check it's working properly."""
    pi = common_pb2.PackageInfo()
    pi.package_name = 'pkg'
    pi.category = 'cat'
    pi.version = '2.0.0'

    cpv = controller_util.PackageInfoToCPV(pi)

    self.assertEqual('pkg', cpv.package)
    self.assertEqual('cat', cpv.category)
    self.assertEqual('2.0.0', cpv.version)

  def testNoPackageInfo(self):
    """Test no package info given."""
    self.assertIsNone(controller_util.PackageInfoToCPV(None))

  def testNoPackageName(self):
    """Test no package name given."""
    pi = common_pb2.PackageInfo()
    pi.category = 'cat'
    pi.version = '2.0.0'

    self.assertIsNone(controller_util.PackageInfoToCPV(pi))


class PackageInfoToStringTest(cros_test_lib.TestCase):
  """PackageInfoToString tests."""

  def testAllFields(self):
    """Test all fields present."""
    pi = common_pb2.PackageInfo()
    pi.package_name = 'pkg'
    pi.category = 'cat'
    pi.version = '2.0.0'

    cpv_str = controller_util.PackageInfoToString(pi)

    self.assertEqual('cat/pkg-2.0.0', cpv_str)

  def testNoVersion(self):
    """Test no version provided."""
    pi = common_pb2.PackageInfo()
    pi.package_name = 'pkg'
    pi.category = 'cat'

    cpv_str = controller_util.PackageInfoToString(pi)

    self.assertEqual('cat/pkg', cpv_str)

  def testPackageOnly(self):
    """Test no version provided."""
    pi = common_pb2.PackageInfo()
    pi.package_name = 'pkg'

    cpv_str = controller_util.PackageInfoToString(pi)

    self.assertEqual('pkg', cpv_str)

  def testNoPackageName(self):
    """Test no package name given."""
    pi = common_pb2.PackageInfo()

    with self.assertRaises(ValueError):
      controller_util.PackageInfoToString(pi)


class CPVToStringTest(cros_test_lib.TestCase):
  """CPVToString tests."""

  def testTranslations(self):
    """Test standard translations used."""
    cases = [
        'cat/pkg-2.0.0-r1',
        'cat/pkg-2.0.0',
        'cat/pkg',
        'pkg',
    ]

    for case in cases:
      cpv = package_info.SplitCPV(case, strict=False)
      # We should end up with as much info as is available, so we should see
      # the original value in each case.
      self.assertEqual(case, controller_util.CPVToString(cpv))

  def testInvalidCPV(self):
    """Test invalid CPV object."""
    cpv = package_info.SplitCPV('', strict=False)
    with self.assertRaises(ValueError):
      controller_util.CPVToString(cpv)


def test_serialize_package_info():
  pkg_info = package_info.parse('foo/bar-1.2.3-r4')
  pkg_info_msg = common_pb2.PackageInfo()
  controller_util.serialize_package_info(pkg_info, pkg_info_msg)
  assert pkg_info_msg.category == 'foo'
  assert pkg_info_msg.package_name == 'bar'
  assert pkg_info_msg.version == '1.2.3-r4'


def test_deserialize_package_info():
  pkg_info_msg = common_pb2.PackageInfo()
  pkg_info_msg.category = 'foo'
  pkg_info_msg.package_name = 'bar'
  pkg_info_msg.version = '1.2.3-r4'
  pkg_info = controller_util.deserialize_package_info(pkg_info_msg)
  assert pkg_info.cpvr == 'foo/bar-1.2.3-r4'
