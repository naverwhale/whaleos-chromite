# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test controller.

Handles all testing related functionality, it is not itself a test.
"""

import functools
import os
import string

from chromite.api import controller
from chromite.api import faux
from chromite.api import validate
from chromite.api.metrics import deserialize_metrics_log
from chromite.api.controller import controller_util
from chromite.api.gen.chromite.api import test_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.api.gen.chromiumos.test.api import coverage_rule_pb2
from chromite.api.gen.chromiumos.test.api import dut_attribute_pb2
from chromite.api.gen.chromiumos.test.api import test_suite_pb2
from chromite.cbuildbot import goma_util
from chromite.lib import build_target_lib
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import image_lib
from chromite.lib import osutils
from chromite.lib import sysroot_lib
from chromite.lib.parser import package_info
from chromite.scripts import cros_set_lsb_release
from chromite.service import packages as packages_service
from chromite.service import test
from chromite.third_party.google.protobuf import json_format
from chromite.third_party.google.protobuf import text_format
from chromite.utils import key_value_store
from chromite.utils import metrics


@faux.empty_success
@faux.empty_completed_unsuccessfully_error
def DebugInfoTest(input_proto, _output_proto, config):
  """Run the debug info tests."""
  sysroot_path = input_proto.sysroot.path
  target_name = input_proto.sysroot.build_target.name

  if not sysroot_path:
    if target_name:
      sysroot_path = build_target_lib.get_default_sysroot_path(target_name)
    else:
      cros_build_lib.Die("The sysroot path or the sysroot's build target name "
                         'must be provided.')

  # We could get away with out this, but it's a cheap check.
  sysroot = sysroot_lib.Sysroot(sysroot_path)
  if not sysroot.Exists():
    cros_build_lib.Die('The provided sysroot does not exist.')

  if config.validate_only:
    return controller.RETURN_CODE_VALID_INPUT

  if test.DebugInfoTest(sysroot_path):
    return controller.RETURN_CODE_SUCCESS
  else:
    return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY


def _BuildTargetUnitTestResponse(input_proto, output_proto, _config):
  """Add tarball path to a successful response."""
  output_proto.tarball_path = os.path.join(input_proto.result_path,
                                           'unit_tests.tar')


def _BuildTargetUnitTestFailedResponse(_input_proto, output_proto, _config):
  """Add failed packages to a failed response."""
  packages = ['foo/bar', 'cat/pkg']
  for pkg in packages:
    pkg_info = package_info.parse(pkg)
    pkg_info_msg = output_proto.failed_packages.add()
    controller_util.serialize_package_info(pkg_info, pkg_info_msg)


@faux.success(_BuildTargetUnitTestResponse)
@faux.error(_BuildTargetUnitTestFailedResponse)
@validate.require_each('packages', ['category', 'package_name'])
@validate.validation_complete
@metrics.collect_metrics
def BuildTargetUnitTest(input_proto, output_proto, _config):
  """Run a build target's ebuild unit tests."""
  # Method flags.
  # An empty sysroot means build packages was not run. This is used for
  # certain boards that need to use prebuilts (e.g. grunt's unittest-only).
  was_built = not input_proto.flags.empty_sysroot

  # Packages to be tested.
  packages_package_info = input_proto.packages
  packages = []
  for package_info_msg in packages_package_info:
    cpv = controller_util.PackageInfoToCPV(package_info_msg)
    packages.append(cpv.cp)

  # Skipped tests.
  blocklisted_package_info = input_proto.package_blocklist
  blocklist = []
  for package_info_msg in blocklisted_package_info:
    blocklist.append(controller_util.PackageInfoToString(package_info_msg))

  # Allow call to filter out non-cros_workon packages from the input packages.
  filter_only_cros_workon = input_proto.flags.filter_only_cros_workon

  # Allow call to succeed if no tests were found.
  testable_packages_optional = input_proto.flags.testable_packages_optional

  build_target = controller_util.ParseBuildTarget(input_proto.build_target)
  chroot = controller_util.ParseChroot(input_proto.chroot)

  code_coverage = input_proto.flags.code_coverage

  result = test.BuildTargetUnitTest(
      build_target,
      chroot,
      packages=packages,
      blocklist=blocklist,
      was_built=was_built,
      code_coverage=code_coverage,
      testable_packages_optional=testable_packages_optional,
      filter_only_cros_workon=filter_only_cros_workon)

  if not result.success:
    # Failed to run tests or some tests failed.
    # Record all failed packages.
    for pkg_info in result.failed_pkgs:
      package_info_msg = output_proto.failed_packages.add()
      controller_util.serialize_package_info(pkg_info, package_info_msg)
    if result.failed_pkgs:
      return controller.RETURN_CODE_UNSUCCESSFUL_RESPONSE_AVAILABLE
    else:
      return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY

  deserialize_metrics_log(output_proto.events, prefix=build_target.name)


SRC_DIR = os.path.join(constants.SOURCE_ROOT, 'src')
PLATFORM_DEV_DIR = os.path.join(SRC_DIR, 'platform/dev')
TEST_SERVICE_DIR = os.path.join(PLATFORM_DEV_DIR, 'src/chromiumos/test')
TEST_CONTAINER_BUILD_SCRIPTS = [
    os.path.join(TEST_SERVICE_DIR, 'provision/docker/build-dockerimage.sh'),
    os.path.join(TEST_SERVICE_DIR, 'dut/docker/build-dockerimage.sh'),
    os.path.join(PLATFORM_DEV_DIR, 'test/container/utils/build-dockerimage.sh'),
]


def _BuildTestServiceContainersResponse(input_proto, output_proto, _config):
  """Fake success response"""
  # pylint: disable=unused-argument
  output_proto.results.append(test_pb2.TestServiceContainerBuildResult(
      success=test_pb2.TestServiceContainerBuildResult.Success()
  ))


def _BuildTestServiceContainersFailedResponse(
    _input_proto, output_proto, _config):
  """Fake failure response"""

  # pylint: disable=unused-argument
  output_proto.results.append(test_pb2.TestServiceContainerBuildResult(
      failure=test_pb2.TestServiceContainerBuildResult.Failure(
          error_message='fake error'
      )
  ))


@validate.constraint('valid docker tag')
def _ValidDockerTag(tag):
  """Check that a string meets requirements for Docker tag naming."""
  # Tags can't start with period or dash
  if tag[0] in '.-':
    return "tag can't begin with '.' or '-'"

  # Tags can only consist of [a-zA-Z0-9-_.]
  allowed_chars = set(string.ascii_letters+string.digits+'-_.')
  invalid_chars = set(tag) - allowed_chars
  if invalid_chars:
    return 'saw one or more invalid characters: [{}]'.format(
        ''.join(invalid_chars),
    )

  # Finally, max tag length is 128 characters
  if len(tag) > 128:
    return 'maximum tag length is 128 characters'


@validate.constraint('valid docker label key')
def _ValidDockerLabelKey(key):
  """Check that a string meets requirements for Docker tag naming."""

  # Label keys should start and end with a lowercase letter
  lowercase = set(string.ascii_lowercase)
  if not (key[0] in lowercase and key[-1] in lowercase):
    return "label key doesn't start and end with lowercase letter"

  # Label keys can have lower-case alphanumeric characters, period and dash
  allowed_chars = set(string.ascii_lowercase+string.digits+'-.')
  invalid_chars = set(key) - allowed_chars
  if invalid_chars:
    return 'saw one or more invalid characters: [{}]'.format(
        ''.join(invalid_chars),
    )

  # Repeated . and - aren't allowed
  for char in '.-':
    if char*2 in key:
      return "'{}' can\'t be repeated in label key".format(char)


@faux.success(_BuildTestServiceContainersResponse)
@faux.error(_BuildTestServiceContainersFailedResponse)
@validate.require('build_target.name')
@validate.require('chroot.path')
@validate.check_constraint('tags', _ValidDockerTag)
@validate.check_constraint('labels', _ValidDockerLabelKey)
@validate.validation_complete
def BuildTestServiceContainers(
    input_proto: test_pb2.BuildTestServiceContainersRequest,
    output_proto: test_pb2.BuildTestServiceContainersResponse, _config):
  """Builds docker containers for all test services and pushes them to gcr.io"""
  build_target = controller_util.ParseBuildTarget(input_proto.build_target)
  chroot = controller_util.ParseChroot(input_proto.chroot)
  sysroot = sysroot_lib.Sysroot(build_target.root)

  tags = ','.join(input_proto.tags)
  labels = (
      '{}={}'.format(key, value) for key, value in input_proto.labels.items()
  )

  for build_script in TEST_CONTAINER_BUILD_SCRIPTS:
    cmd = [build_script, chroot.path, sysroot.path]
    cmd += ['--tags', tags]
    cmd += labels

    cmd_result = cros_build_lib.run(cmd, check=False)
    if cmd_result.returncode == 0:
      output_proto.results.append(test_pb2.TestServiceContainerBuildResult(
          success=test_pb2.TestServiceContainerBuildResult.Success()
      ))
    else:
      output_proto.results.append(test_pb2.TestServiceContainerBuildResult(
          failure=test_pb2.TestServiceContainerBuildResult.Failure(
              error_message=cmd_result.stderr
          )
      ))


@faux.empty_success
@faux.empty_completed_unsuccessfully_error
@validate.validation_complete
def ChromiteUnitTest(_input_proto, _output_proto, _config):
  """Run the chromite unit tests."""
  if test.ChromiteUnitTest():
    return controller.RETURN_CODE_SUCCESS
  else:
    return controller.RETURN_CODE_COMPLETED_UNSUCCESSFULLY


@faux.empty_success
@faux.empty_completed_unsuccessfully_error
@validate.validation_complete
def ChromitePytest(_input_proto, _output_proto, _config):
  """Run the chromite unit tests."""
  # TODO(vapier): Delete this stub.
  return controller.RETURN_CODE_SUCCESS


@faux.all_empty
@validate.require('sysroot.path', 'sysroot.build_target.name', 'chrome_root')
@validate.validation_complete
def SimpleChromeWorkflowTest(input_proto, _output_proto, _config):
  """Run SimpleChromeWorkflow tests."""
  if input_proto.goma_config.goma_dir:
    chromeos_goma_dir = input_proto.goma_config.chromeos_goma_dir or None
    goma = goma_util.Goma(
        input_proto.goma_config.goma_dir,
        input_proto.goma_config.goma_client_json,
        stage_name='BuildApiTestSimpleChrome',
        chromeos_goma_dir=chromeos_goma_dir)
  else:
    goma = None
  return test.SimpleChromeWorkflowTest(input_proto.sysroot.path,
                                       input_proto.sysroot.build_target.name,
                                       input_proto.chrome_root,
                                       goma)


@faux.all_empty
@validate.require('build_target.name', 'vm_path.path', 'test_harness',
                  'vm_tests')
@validate.validation_complete
def VmTest(input_proto, _output_proto, _config):
  """Run VM tests."""
  build_target_name = input_proto.build_target.name
  vm_path = input_proto.vm_path.path

  test_harness = input_proto.test_harness

  vm_tests = input_proto.vm_tests

  cmd = ['cros_run_test', '--debug', '--no-display', '--copy-on-write',
         '--board', build_target_name, '--image-path', vm_path,
         '--%s' % test_pb2.VmTestRequest.TestHarness.Name(test_harness).lower()]
  cmd.extend(vm_test.pattern for vm_test in vm_tests)

  if input_proto.ssh_options.port:
    cmd.extend(['--ssh-port', str(input_proto.ssh_options.port)])

  if input_proto.ssh_options.private_key_path:
    cmd.extend(['--private-key', input_proto.ssh_options.private_key_path.path])

  # TODO(evanhernandez): Find a nice way to pass test_that-args through
  # the build API. Or obviate them.
  if test_harness == test_pb2.VmTestRequest.AUTOTEST:
    cmd.append('--test_that-args=--allow-chrome-crashes')

  with osutils.TempDir(prefix='vm-test-results.') as results_dir:
    cmd.extend(['--results-dir', results_dir])
    cros_build_lib.run(cmd, kill_timeout=10 * 60)


@faux.all_empty
@validate.require('image_payload.path.path', 'cache_payloads')
@validate.require_each('cache_payloads', ['path.path'])
@validate.validation_complete
def MoblabVmTest(input_proto, _output_proto, _config):
  """Run Moblab VM tests."""
  chroot = controller_util.ParseChroot(input_proto.chroot)
  image_payload_dir = input_proto.image_payload.path.path
  cache_payload_dirs = [cp.path.path for cp in input_proto.cache_payloads]

  # Autotest and Moblab depend on the builder path, so we must read it from
  # the image.
  image_file = os.path.join(image_payload_dir, constants.TEST_IMAGE_BIN)
  with osutils.TempDir() as mount_dir:
    with image_lib.LoopbackPartitions(image_file, destination=mount_dir) as lp:
      # The file we want is /etc/lsb-release, which lives in the ROOT-A
      # disk partition.
      partition_paths = lp.Mount([constants.PART_ROOT_A])
      assert len(partition_paths) == 1, (
          'expected one partition path, got: %r' % partition_paths)
      partition_path = partition_paths[0]
      lsb_release_file = os.path.join(partition_path,
                                      constants.LSB_RELEASE_PATH.strip('/'))
      lsb_release_kvs = key_value_store.LoadFile(lsb_release_file)
      builder = lsb_release_kvs.get(cros_set_lsb_release.LSB_KEY_BUILDER_PATH)

  if not builder:
    cros_build_lib.Die('Image did not contain key %s in %s',
                       cros_set_lsb_release.LSB_KEY_BUILDER_PATH,
                       constants.LSB_RELEASE_PATH)

  # Now we can run the tests.
  with chroot.tempdir() as workspace_dir, chroot.tempdir() as results_dir:
    # Convert the results directory to an absolute chroot directory.
    chroot_results_dir = '/%s' % os.path.relpath(results_dir, chroot.path)
    vms = test.CreateMoblabVm(workspace_dir, chroot.path, image_payload_dir)
    cache_dir = test.PrepareMoblabVmImageCache(vms, builder, cache_payload_dirs)
    test.RunMoblabVmTest(chroot, vms, builder, cache_dir, chroot_results_dir)
    test.ValidateMoblabVmTest(results_dir)


@faux.all_empty
@validate.validation_complete
def CrosSigningTest(_input_proto, _output_proto, _config):
  """Run the cros-signing unit tests."""
  test_runner = os.path.join(constants.SOURCE_ROOT, 'cros-signing', 'signer',
                             'run_tests.py')
  result = cros_build_lib.run([test_runner], check=False)

  return result.returncode


def GetArtifacts(in_proto: common_pb2.ArtifactsByService.Test,
                 chroot: chroot_lib.Chroot, sysroot_class: sysroot_lib.Sysroot,
                 build_target: build_target_lib.BuildTarget,
                 output_dir: str) -> list:
  """Builds and copies test artifacts to specified output_dir.

  Copies test artifacts to output_dir, returning a list of (output_dir: str)
  paths to the desired files.

  Args:
    in_proto: Proto request defining reqs.
    chroot: The chroot class used for these artifacts.
    sysroot_class: The sysroot class used for these artifacts.
    build_target: The build target used for these artifacts.
    output_dir: The path to write artifacts to.

  Returns:
    A list of dictionary mappings of ArtifactType to list of paths.
  """
  generated = []

  artifact_types = {
      in_proto.ArtifactType.UNIT_TESTS: test.BuildTargetUnitTestTarball,
      in_proto.ArtifactType.CODE_COVERAGE_LLVM_JSON:
          test.BundleCodeCoverageLlvmJson,
      in_proto.ArtifactType.HWQUAL: functools.partial(
          test.BundleHwqualTarball,
          build_target.name, packages_service.determine_full_version()),
  }

  for output_artifact in in_proto.output_artifacts:
    for artifact_type, func in artifact_types.items():
      if artifact_type in output_artifact.artifact_types:
        paths = func(chroot, sysroot_class, output_dir)
        if paths:
          generated.append({
              'paths': [paths] if isinstance(paths, str) else paths,
              'type': artifact_type,
          })

  return generated


def _GetCoverageRulesResponseSuccess(
    _input_proto, output_proto: test_pb2.GetCoverageRulesResponse, _config):
  output_proto.coverage_rules.append(
      coverage_rule_pb2.CoverageRule(
          name='kernel:4.4',
          test_suites=[
              test_suite_pb2.TestSuite(
                  test_case_tag_criteria=test_suite_pb2.TestSuite
                  .TestCaseTagCriteria(tags=['kernel']))
          ],
          dut_criteria=[
              dut_attribute_pb2.DutCriterion(
                  attribute_id=dut_attribute_pb2.DutAttribute.Id(
                      value='system_build_target'),
                  values=['overlayA'],
              )
          ],
      ),)


@faux.success(_GetCoverageRulesResponseSuccess)
@faux.empty_error
@validate.require('source_test_plans')
@validate.exists('dut_attribute_list.path', 'build_metadata_list.path',
                 'flat_config_list.path')
@validate.validation_complete
def GetCoverageRules(input_proto: test_pb2.GetCoverageRulesRequest,
                     output_proto: test_pb2.GetCoverageRulesResponse, _config):
  """Call the testplan tool to generate CoverageRules."""
  source_test_plans = input_proto.source_test_plans
  dut_attribute_list = input_proto.dut_attribute_list
  build_metadata_list = input_proto.build_metadata_list
  flat_config_list = input_proto.flat_config_list

  cmd = [
      'testplan', 'generate', '-dutattributes', dut_attribute_list.path,
      '-buildmetadata', build_metadata_list.path, '-flatconfiglist',
      flat_config_list.path, '-logtostderr', '-v', '2'
  ]

  with osutils.TempDir(prefix='get_coverage_rules_input') as tempdir:
    # Write all input files required by testplan, and read the output file
    # containing CoverageRules.
    for i, plan in enumerate(source_test_plans):
      plan_path = os.path.join(tempdir, 'source_test_plan_%d.textpb' % i)
      osutils.WriteFile(plan_path, text_format.MessageToString(plan))
      cmd.extend(['-plan', plan_path])

    out_path = os.path.join(tempdir, 'out.jsonpb')
    cmd.extend(['-out', out_path])

    cros_build_lib.run(cmd)

    out_text = osutils.ReadFile(out_path)

  # The output file contains CoverageRules as jsonpb, separated by newlines.
  coverage_rules = []
  for out_line in out_text.splitlines():
    coverage_rule = coverage_rule_pb2.CoverageRule()
    json_format.Parse(out_line, coverage_rule)
    coverage_rules.append(coverage_rule)

  output_proto.coverage_rules.extend(coverage_rules)
