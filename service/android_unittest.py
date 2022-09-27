# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Android service unittests."""

import logging
import os

from chromite.lib import constants
from chromite.lib import cros_test_lib
from chromite.lib import gs
from chromite.lib import gs_unittest
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.service import android


class ArtifactsConfigTest(cros_test_lib.TestCase):
  """Tests to ensure artifacts configs are properly written."""

  def testAllTargetsAreConfigured(self):
    """Ensure artifact patterns are configured for all branches and targets."""
    self.assertSetEqual(set(android.ARTIFACTS_TO_COPY),
                        set(constants.ANDROID_BRANCH_TO_BUILD_TARGETS),
                        "Branches configured in ARTIFACTS_TO_COPY doesn't "
                        'match list of all Android branches')
    for branch, ebuild_target in (
        constants.ANDROID_BRANCH_TO_BUILD_TARGETS.items()):
      self.assertSetEqual(set(android.ARTIFACTS_TO_COPY[branch]),
                          set(ebuild_target.values()),
                          f'For branch {branch}, targets configured in '
                          "ARTIFACTS_TO_COPY doesn't match list of all "
                          'supported targets')


class GetAndroidBranchForPackageTest(cros_test_lib.TestCase):
  """Tests for GetAndroidBranchForPackage."""

  def testAllPackagesAreMapped(self):
    """Ensure all possible Android packages are mapped to valid branches."""
    for package in constants.ANDROID_ALL_PACKAGES:
      branch = android.GetAndroidBranchForPackage(package)
      self.assertIn(branch, android.ARTIFACTS_TO_COPY)

  def testRaisesOnUnknownPackage(self):
    """Ensure passing an unknown package raises an exception."""
    with self.assertRaises(ValueError):
      android.GetAndroidBranchForPackage('not-an-android-package')


class MockAndroidBuildArtifactsTest(cros_test_lib.MockTempDirTestCase):
  """Tests using a mocked GS bucket containing Android build artifacts."""

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
    self.android_package = constants.ANDROID_PI_PACKAGE

    self.tmp_overlay = os.path.join(self.tempdir, 'chromiumos-overlay')
    self.mock_android_dir = os.path.join(
        self.tmp_overlay,
        portage_util.GetFullAndroidPortagePackageName(self.android_package))

    self.old_version = '25'
    self.old2_version = '50'
    self.new_version = '100'
    self.partial_new_version = '150'
    self.not_new_version = '200'

    self.arm_acl_data = '-g google.com:READ'
    self.x86_acl_data = '-g google.com:WRITE'
    self.public_acl_data = '-u AllUsers:READ'
    self.arm_acl = os.path.join(self.mock_android_dir,
                                android.ARC_BUCKET_ACL_ARM)
    self.x86_acl = os.path.join(self.mock_android_dir,
                                android.ARC_BUCKET_ACL_X86)
    self.public_acl = os.path.join(self.mock_android_dir,
                                   android.ARC_BUCKET_ACL_PUBLIC)

    osutils.WriteFile(self.arm_acl, self.arm_acl_data, makedirs=True)
    osutils.WriteFile(self.x86_acl, self.x86_acl_data, makedirs=True)
    osutils.WriteFile(self.public_acl, self.public_acl_data, makedirs=True)

    self.bucket_url = 'gs://u'
    self.build_branch = constants.ANDROID_PI_BUILD_BRANCH
    self.gs_mock = self.StartPatcher(gs_unittest.GSContextMock())
    self.arc_bucket_url = 'gs://a'
    self.targets = android.ARTIFACTS_TO_COPY[self.build_branch]

    targets = {
        'apps': [
            self.old_version, self.old2_version, self.new_version,
        ],
        'cheets_arm-user': [
            self.old_version, self.old2_version, self.new_version,
            self.partial_new_version
        ],
        'cheets_arm64-user': [
            self.old_version, self.old2_version, self.new_version,
        ],
        'cheets_x86-user': [
            self.old_version, self.old2_version, self.new_version,
        ],
        'cheets_x86_64-user': [
            self.old_version, self.old2_version, self.new_version,
        ],
        'cheets_arm-userdebug': [
            self.old_version, self.old2_version, self.new_version,
        ],
        'cheets_arm64-userdebug': [
            self.old_version, self.old2_version, self.new_version,
        ],
        'cheets_x86-userdebug': [
            self.old_version, self.old2_version, self.new_version
        ],
        'cheets_x86_64-userdebug': [
            self.old_version, self.old2_version, self.new_version
        ],
        'sdk_cheets_x86-userdebug': [
            self.old_version, self.old2_version, self.new_version
        ],
        'sdk_cheets_x86_64-userdebug': [
            self.old_version, self.old2_version, self.new_version
        ],
    }
    for target, versions in targets.items():
      url = self.makeSrcTargetUrl(target)
      versions = '\n'.join(os.path.join(url, version) for version in versions)
      self.gs_mock.AddCmdResult(['ls', '--', url], output=versions)

    for version in [self.old_version, self.old2_version, self.new_version]:
      for target in self.targets:
        self.setupMockBuild(target, version)
    self.new_subpaths = {
        'apps': 'apps100',
        'cheets_arm-user': 'cheets_arm-user100',
        'cheets_arm64-user': 'cheets_arm64-user100',
        'cheets_x86-user': 'cheets_x86-user100',
        'cheets_x86_64-user': 'cheets_x86_64-user100',
        'cheets_arm-userdebug': 'cheets_arm-userdebug100',
        'cheets_arm64-userdebug': 'cheets_arm64-userdebug100',
        'cheets_x86-userdebug': 'cheets_x86-userdebug100',
        'cheets_x86_64-userdebug': 'cheets_x86_64-userdebug100',
        'sdk_cheets_x86-userdebug': 'sdk_cheets_x86-userdebug100',
        'sdk_cheets_x86_64-userdebug': 'sdk_cheets_x86_64-userdebug100',
    }

    self.setupMockBuild('apps', self.partial_new_version, valid=False)
    self.setupMockBuild('cheets_arm-user', self.partial_new_version)
    self.setupMockBuild('cheets_arm64-user', self.partial_new_version,
                        valid=False)
    self.setupMockBuild('cheets_x86-user', self.partial_new_version,
                        valid=False)
    self.setupMockBuild('cheets_x86_64-user', self.partial_new_version,
                        valid=False)
    self.setupMockBuild('cheets_arm-userdebug', self.partial_new_version,
                        valid=False)
    self.setupMockBuild('cheets_arm64-userdebug', self.partial_new_version,
                        valid=False)
    self.setupMockBuild('cheets_x86-userdebug', self.partial_new_version,
                        valid=False)
    self.setupMockBuild('cheets_x86_64-userdebug', self.partial_new_version,
                        valid=False)
    self.setupMockBuild('sdk_cheets_x86-userdebug', self.partial_new_version,
                        valid=False)
    self.setupMockBuild('sdk_cheets_x86_64-userdebug', self.partial_new_version,
                        valid=False)

    for key in self.targets.keys():
      self.setupMockBuild(key, self.not_new_version, False)

  def setupMockBuild(self, target, version, valid=True):
    """Helper to mock a build."""
    def _RaiseGSNoSuchKey(*_args, **_kwargs):
      raise gs.GSNoSuchKey('file does not exist')

    src_url = self.makeSrcUrl(target, version)
    if valid:
      # Show source subpath directory.
      src_subdir = os.path.join(src_url, self.makeSubpath(target, version))
      self.gs_mock.AddCmdResult(['ls', '--', src_url], output=src_subdir)

      # Show files.
      mock_file_template_list = {
          'apps': ['org.chromium.arc.cachebuilder.jar'],
          'cheets_arm-user': ['file-%(version)s.zip', 'adb', 'sepolicy.zip'],
          'cheets_arm64-user': ['cheets_arm64-file-%(version)s.zip',
                                'sepolicy.zip'],
          'cheets_x86-user': ['file-%(version)s.zip'],
          'cheets_x86_64-user': ['file-%(version)s.zip'],
          'cheets_arm-userdebug': ['cheets_arm-file-%(version)s.zip', 'adb',
                                   'sepolicy.zip'],
          'cheets_arm64-userdebug': ['cheets_arm64-file-%(version)s.zip', 'adb',
                                     'sepolicy.zip'],
          'cheets_x86-userdebug': ['cheets_x86-file-%(version)s.zip',
                                   'sepolicy.zip'],
          'cheets_x86_64-userdebug': ['cheets_x86_64-file-%(version)s.zip'],
          'sdk_cheets_x86-userdebug': ['sdk_cheets_x86-file-%(version)s.zip'],
          'sdk_cheets_x86_64-userdebug': [
              'sdk_cheets_x86_64-file-%(version)s.zip'],
      }
      filelist = [template % {'version': version}
                  for template in mock_file_template_list[target]]
      src_filelist = [os.path.join(src_subdir, filename)
                      for filename in filelist]
      self.gs_mock.AddCmdResult(['ls', '--', src_subdir],
                                output='\n'.join(src_filelist))
      for src_file in src_filelist:
        self.gs_mock.AddCmdResult(['stat', '--', src_file],
                                  output=(self.STAT_OUTPUT) % src_url)

      # Show nothing in destination.
      dst_url = self.makeDstUrl(target, version)
      filelist = [template % {'version': version}
                  for template in mock_file_template_list[target]]
      dst_filelist = [os.path.join(dst_url, filename)
                      for filename in filelist]
      for dst_file in dst_filelist:
        self.gs_mock.AddCmdResult(['stat', '--', dst_file],
                                  side_effect=_RaiseGSNoSuchKey)
      logging.warning('mocking no %s', dst_url)

      # Allow copying of source to dest.
      for src_file, dst_file in zip(src_filelist, dst_filelist):
        self.gs_mock.AddCmdResult(['cp', '-v', '--', src_file, dst_file])

      # Allow setting ACL on dest files.
      acls = {
          'apps': self.public_acl_data,
          'cheets_arm-user': self.arm_acl_data,
          'cheets_arm64-user': self.arm_acl_data,
          'cheets_x86-user': self.x86_acl_data,
          'cheets_x86_64-user': self.x86_acl_data,
          'cheets_arm-userdebug': self.arm_acl_data,
          'cheets_arm64-userdebug': self.arm_acl_data,
          'cheets_x86-userdebug': self.x86_acl_data,
          'cheets_x86_64-userdebug': self.x86_acl_data,
          'sdk_cheets_x86-userdebug': self.x86_acl_data,
          'sdk_cheets_x86_64-userdebug': self.x86_acl_data,
      }
      for dst_file in dst_filelist:
        self.gs_mock.AddCmdResult(
            ['acl', 'ch'] + acls[target].split() + [dst_file])
    else:
      self.gs_mock.AddCmdResult(['ls', '--', src_url],
                                side_effect=_RaiseGSNoSuchKey)

  def makeSrcTargetUrl(self, target):
    """Helper to return the url for a target."""
    return os.path.join(self.bucket_url,
                        f'{self.build_branch}-linux-{target}')

  def makeSrcUrl(self, target, version):
    """Helper to return the url for a build."""
    return os.path.join(self.makeSrcTargetUrl(target), version)

  def makeDstTargetUrl(self, target):
    """Helper to return the url for a target."""
    return os.path.join(self.arc_bucket_url,
                        f'{self.build_branch}-linux-{target}')

  def makeDstUrl(self, target, version):
    """Helper to return the url for a build."""
    return os.path.join(self.makeDstTargetUrl(target), version)

  def makeSubpath(self, target, version):
    """Helper to return the subpath for a build."""
    return '%s%s' % (target, version)

  def testIsBuildIdValid(self):
    """Test if checking if build valid."""
    subpaths = android.IsBuildIdValid(self.build_branch, self.old_version,
                                      self.bucket_url)
    self.assertTrue(subpaths)
    self.assertEqual(len(subpaths), 11)
    self.assertEqual(subpaths['apps'], 'apps25')
    self.assertEqual(subpaths['cheets_arm-user'], 'cheets_arm-user25')
    self.assertEqual(subpaths['cheets_arm64-user'], 'cheets_arm64-user25')
    self.assertEqual(subpaths['cheets_x86-user'], 'cheets_x86-user25')
    self.assertEqual(subpaths['cheets_x86_64-user'], 'cheets_x86_64-user25')
    self.assertEqual(subpaths['cheets_arm-userdebug'], 'cheets_arm-userdebug25')
    self.assertEqual(subpaths['cheets_arm64-userdebug'],
                     'cheets_arm64-userdebug25')
    self.assertEqual(subpaths['cheets_x86-userdebug'], 'cheets_x86-userdebug25')
    self.assertEqual(subpaths['cheets_x86_64-userdebug'],
                     'cheets_x86_64-userdebug25')
    self.assertEqual(subpaths['sdk_cheets_x86-userdebug'],
                     'sdk_cheets_x86-userdebug25')
    self.assertEqual(subpaths['sdk_cheets_x86_64-userdebug'],
                     'sdk_cheets_x86_64-userdebug25')

    subpaths = android.IsBuildIdValid(self.build_branch, self.new_version,
                                      self.bucket_url)
    self.assertEqual(subpaths, self.new_subpaths)

    subpaths = android.IsBuildIdValid(self.build_branch,
                                      self.partial_new_version, self.bucket_url)
    self.assertEqual(subpaths, None)

    subpaths = android.IsBuildIdValid(self.build_branch, self.not_new_version,
                                      self.bucket_url)
    self.assertEqual(subpaths, None)

  def testGetLatestBuild(self):
    """Test determination of latest build from gs bucket."""
    version, subpaths = android.GetLatestBuild(self.build_branch,
                                               self.bucket_url)
    self.assertEqual(version, self.new_version)
    self.assertTrue(subpaths)
    self.assertEqual(len(subpaths), 11)
    self.assertEqual(subpaths['apps'], 'apps100')
    self.assertEqual(subpaths['cheets_arm-user'], 'cheets_arm-user100')
    self.assertEqual(subpaths['cheets_arm64-user'], 'cheets_arm64-user100')
    self.assertEqual(subpaths['cheets_x86-user'], 'cheets_x86-user100')
    self.assertEqual(subpaths['cheets_x86_64-user'], 'cheets_x86_64-user100')
    self.assertEqual(subpaths['cheets_arm-userdebug'],
                    'cheets_arm-userdebug100')
    self.assertEqual(subpaths['cheets_arm64-userdebug'],
                     'cheets_arm64-userdebug100')
    self.assertEqual(subpaths['cheets_x86-userdebug'],
                     'cheets_x86-userdebug100')
    self.assertEqual(subpaths['cheets_x86_64-userdebug'],
                     'cheets_x86_64-userdebug100')
    self.assertEqual(subpaths['sdk_cheets_x86-userdebug'],
                     'sdk_cheets_x86-userdebug100')
    self.assertEqual(subpaths['sdk_cheets_x86_64-userdebug'],
                     'sdk_cheets_x86_64-userdebug100')

  def testCopyToArcBucket(self):
    """Test copying of images to ARC bucket."""
    android.CopyToArcBucket(self.bucket_url, self.build_branch,
                            self.new_version, self.new_subpaths,
                            self.arc_bucket_url, self.mock_android_dir)
