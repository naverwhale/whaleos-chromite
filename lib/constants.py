# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module contains constants used by cbuildbot and related code."""

import itertools
import os

def _FindSourceRoot():
  """Try and find the root check out of the chromiumos tree"""
  source_root = path = os.path.realpath(os.path.join(
      os.path.abspath(__file__), '..', '..', '..'))
  while True:
    if os.path.isdir(os.path.join(path, '.repo')):
      return path
    elif path == '/':
      break
    path = os.path.dirname(path)
  return source_root


SOURCE_ROOT = _FindSourceRoot()
CHROOT_SOURCE_ROOT = '/mnt/host/source'
CHROOT_CACHE_ROOT = '/var/cache/chromeos-cache'
DEPOT_TOOLS_SUBPATH = 'src/chromium/depot_tools'

CROSUTILS_DIR = os.path.join(SOURCE_ROOT, 'src/scripts')
CHROMITE_DIR = os.path.realpath(os.path.join(
    os.path.abspath(__file__), '..', '..'))
BOOTSTRAP_DIR = os.path.join(CHROMITE_DIR, 'bootstrap')
DEPOT_TOOLS_DIR = os.path.join(SOURCE_ROOT, DEPOT_TOOLS_SUBPATH)
CHROMITE_BIN_SUBDIR = 'chromite/bin'
CHROMITE_BIN_DIR = os.path.join(CHROMITE_DIR, 'bin')
CHROMITE_SCRIPTS_DIR = os.path.join(CHROMITE_DIR, 'scripts')
PATH_TO_CBUILDBOT = os.path.join(CHROMITE_BIN_SUBDIR, 'cbuildbot')
DEFAULT_CHROOT_DIR = 'chroot'
DEFAULT_CHROOT_PATH = os.path.join(SOURCE_ROOT, DEFAULT_CHROOT_DIR)
TERMINA_TOOLS_DIR = os.path.join(
    CHROOT_SOURCE_ROOT, 'src/platform/container-guest-tools/termina')

STATEFUL_DIR = '/mnt/stateful_partition'

# These constants are defined and used in the die_hook that logs failed
# packages: 'cros_log_failed_packages' in profiles/base/profile.bashrc in
# chromiumos-overlay. The status file is generated in CROS_METRICS_DIR, and
# only if that environment variable is defined.
CROS_METRICS_DIR_ENVVAR = 'CROS_METRICS_DIR'
DIE_HOOK_STATUS_FILE_NAME = 'FAILED_PACKAGES'

CHROMEOS_CONFIG_FILE = os.path.join(CHROMITE_DIR, 'config', 'config_dump.json')
WATERFALL_CONFIG_FILE = os.path.join(
    CHROMITE_DIR, 'config', 'waterfall_layout_dump.txt')
LUCI_SCHEDULER_CONFIG_FILE = os.path.join(
    CHROMITE_DIR, 'config', 'luci-scheduler.cfg')

GE_BUILD_CONFIG_FILE = os.path.join(
    CHROMITE_DIR, 'config', 'ge_build_config.json')

# The following define the location for storing toolchain packages and
# SDK overlay tarballs created during SDK builder runs. The paths are relative
# to the build root's chroot, which guarantees that they are reachable from it
# and get cleaned up when it is removed.
SDK_TOOLCHAINS_OUTPUT = 'tmp/toolchain-pkgs'
SDK_OVERLAYS_OUTPUT = 'tmp/sdk-overlays'

AUTOTEST_BUILD_PATH = 'usr/local/build/autotest'
UNITTEST_PKG_PATH = 'test-packages'

# Path to the lsb-release file on the device.
LSB_RELEASE_PATH = '/etc/lsb-release'

HOME_DIRECTORY = os.path.expanduser('~')

# If cbuiltbot is running on a bot, then the cidb access credentials will be
# available here. This directory will not exist otherwise.
CIDB_PROD_BOT_CREDS = os.path.join(HOME_DIRECTORY, '.cidb_creds',
                                   'prod_cidb_bot')
CIDB_DEBUG_BOT_CREDS = os.path.join(HOME_DIRECTORY, '.cidb_creds',
                                    'debug_cidb_bot')

# Crash Server upload API key.
CRASH_API_KEY = os.path.join('/', 'creds', 'api_keys',
                             'api_key-chromeos-crash-uploader')

# Buildbucket build status
BUILDBUCKET_BUILDER_STATUS_CANCELED = 'CANCELED'
BUILDBUCKET_BUILDER_STATUS_FAILURE = 'FAILURE'
BUILDBUCKET_BUILDER_STATUS_INFRA_FAILURE = 'INFRA_FAILURE'
BUILDBUCKET_BUILDER_STATUS_SCHEDULED = 'SCHEDULED'
BUILDBUCKET_BUILDER_STATUS_STARTED = 'STARTED'
BUILDBUCKET_BUILDER_STATUS_SUCCESS = 'SUCCESS'

BUILDBUCKET_BUILDER_STATUSES = (BUILDBUCKET_BUILDER_STATUS_FAILURE,
                                BUILDBUCKET_BUILDER_STATUS_INFRA_FAILURE,
                                BUILDBUCKET_BUILDER_STATUS_SCHEDULED,
                                BUILDBUCKET_BUILDER_STATUS_STARTED,
                                BUILDBUCKET_BUILDER_STATUS_SUCCESS)

# Builder status strings
BUILDER_STATUS_FAILED = 'fail'
BUILDER_STATUS_PASSED = 'pass'
BUILDER_STATUS_INFLIGHT = 'inflight'
BUILDER_STATUS_MISSING = 'missing'
BUILDER_STATUS_ABORTED = 'aborted'
# The following statuses are currently only used for build stages.
BUILDER_STATUS_PLANNED = 'planned'
BUILDER_STATUS_WAITING = 'waiting'
BUILDER_STATUS_SKIPPED = 'skipped'
BUILDER_STATUS_FORGIVEN = 'forgiven'
BUILDER_COMPLETED_STATUSES = (BUILDER_STATUS_PASSED,
                              BUILDER_STATUS_FAILED,
                              BUILDER_STATUS_ABORTED,
                              BUILDER_STATUS_SKIPPED,
                              BUILDER_STATUS_FORGIVEN)
BUILDER_ALL_STATUSES = (BUILDER_STATUS_FAILED,
                        BUILDER_STATUS_PASSED,
                        BUILDER_STATUS_INFLIGHT,
                        BUILDER_STATUS_MISSING,
                        BUILDER_STATUS_ABORTED,
                        BUILDER_STATUS_WAITING,
                        BUILDER_STATUS_PLANNED,
                        BUILDER_STATUS_SKIPPED,
                        BUILDER_STATUS_FORGIVEN)
BUILDER_NON_FAILURE_STATUSES = (BUILDER_STATUS_PLANNED,
                                BUILDER_STATUS_PASSED,
                                BUILDER_STATUS_SKIPPED,
                                # Quick fix for Buildbucket race problems.
                                BUILDER_STATUS_INFLIGHT,
                                BUILDER_STATUS_FORGIVEN)

# Signer status strings
SIGNER_STATUS_PASSED = 'passed'
SIGNER_STATUS_FAILED = 'failed'

# Change sources
CHANGE_SOURCE_INTERNAL = 'internal'
CHANGE_SOURCE_EXTERNAL = 'external'

# Exception categories, as recorded in cidb
EXCEPTION_CATEGORY_UNKNOWN = 'unknown'
EXCEPTION_CATEGORY_BUILD = 'build'
EXCEPTION_CATEGORY_TEST = 'test'
EXCEPTION_CATEGORY_INFRA = 'infra'
EXCEPTION_CATEGORY_LAB = 'lab'

EXCEPTION_CATEGORY_ALL_CATEGORIES = (
    EXCEPTION_CATEGORY_UNKNOWN,
    EXCEPTION_CATEGORY_BUILD,
    EXCEPTION_CATEGORY_TEST,
    EXCEPTION_CATEGORY_INFRA,
    EXCEPTION_CATEGORY_LAB,
)

# Monarch metric names
MON_LAST_SLAVE = 'chromeos/cbuildbot/last_completed_slave'
MON_BUILD_COMP_COUNT = 'chromeos/cbuildbot/build/completed_count'
MON_BUILD_DURATION = 'chromeos/cbuildbot/build/durations'
MON_STAGE_COMP_COUNT = 'chromeos/cbuildbot/stage/completed_count'
MON_STAGE_DURATION = 'chromeos/cbuildbot/stage/durations'
MON_STAGE_INSTANCE_DURATION = 'chromeos/cbuildbot/stage/instance_durations'
MON_STAGE_FAILURE_COUNT = 'chromeos/cbuildbot/stage/failure_count'
MON_FAILED_STAGE = 'chromeos/chromite/cbuildbot_launch/failed_stage'
MON_CHROOT_USED = 'chromeos/cbuildbot/chroot_at_version'
MON_REPO_SYNC_COUNT = 'chromeos/cbuildbot/repo/sync_count'
MON_REPO_SYNC_RETRY_COUNT = 'chromeos/cbuildbot/repo/sync_retry_count'
MON_REPO_SELFUPDATE_FAILURE_COUNT = ('chromeos/cbuildbot/repo/'
                                     'selfupdate_failure_count')
MON_REPO_INIT_RETRY_COUNT = 'chromeos/cbuildbot/repo/init_retry_count'
MON_REPO_MANIFEST_FAILURE_COUNT = ('chromeos/cbuildbot/repo/'
                                   'manifest_failure_count')
MON_BB_RETRY_BUILD_COUNT = ('chromeos/cbuildbot/buildbucket/'
                            'retry_build_count')
MON_BB_CANCEL_BATCH_BUILDS_COUNT = ('chromeos/cbuildbot/buildbucket/'
                                    'cancel_batch_builds_count')
MON_EXPORT_TO_GCLOUD = 'chromeos/cbuildbot/export_to_gcloud'

# Stage Categorization for failed stages metric.
UNCATEGORIZED_STAGE = 'Uncategorized'
CI_INFRA_STAGE = 'CI-Infra'
TEST_INFRA_STAGE = 'Test-Infra'
PRODUCT_OS_STAGE = 'Product-OS'
PRODUCT_ANDROID_STAGE = 'Product-Android'
PRODUCT_CHROME_STAGE = 'Product-Chrome'
PRODUCT_TOOLCHAIN_STAGE = 'Product-Toolchain'


# Re-execution API constants.
# Used by --resume and --bootstrap to decipher which options they
# can pass to the target cbuildbot (since it may not have that
# option).
# Format is Major.Minor.  Minor is used for tracking new options added
# that aren't critical to the older version if it's not ran.
# Major is used for tracking heavy API breakage- for example, no longer
# supporting the --resume option.
REEXEC_API_MAJOR = 0
REEXEC_API_MINOR = 12
REEXEC_API_VERSION = '%i.%i' % (REEXEC_API_MAJOR, REEXEC_API_MINOR)

# Support --master-build-id
REEXEC_API_MASTER_BUILD_ID = 3
# Support --git-cache-dir
REEXEC_API_GIT_CACHE_DIR = 4
# Support --goma_dir and --goma_client_json
REEXEC_API_GOMA = 5
# Support --ts-mon-task-num
REEXEC_API_TSMON_TASK_NUM = 6
# Support --sanity-check-build
REEXEC_API_SANITY_CHECK_BUILD = 7
# Support --previous-build-state
REEXEC_API_PREVIOUS_BUILD_STATE = 8
# Support --workspace
REEXEC_API_WORKSPACE = 9
# Support --master-buildbucket-id
REEXEC_API_MASTER_BUILDBUCKET_ID = 10
# Support --chromeos_goma_dir
REEXEC_API_CHROMEOS_GOMA_DIR = 11
# Support --chrome-preload-dir
REEXEC_API_CHROME_PRELOAD_DIR = 12

# We rely on the (waterfall, builder name, build number) to uniquely identify
# a build. However, future migrations or state wipes of the buildbot master may
# cause it to reset its build number counter. When that happens, this value
# should be incremented, ensuring that (waterfall, builder name, build number,
# buildbot generation) is a unique identifier of builds.
BUILDBOT_GENERATION = 1

GOOGLE_EMAIL = '@google.com'
CHROMIUM_EMAIL = '@chromium.org'

CORP_DOMAIN = 'corp.google.com'
GOLO_DOMAIN = 'golo.chromium.org'
CHROME_DOMAIN = 'chrome.' + CORP_DOMAIN
CHROMEOS_BOT_INTERNAL = 'chromeos-bot.internal'

GOB_HOST = '%s.googlesource.com'

EXTERNAL_GOB_INSTANCE = 'chromium'
EXTERNAL_GERRIT_INSTANCE = 'chromium-review'
EXTERNAL_GOB_HOST = GOB_HOST % EXTERNAL_GOB_INSTANCE
EXTERNAL_GERRIT_HOST = GOB_HOST % EXTERNAL_GERRIT_INSTANCE
EXTERNAL_GOB_URL = 'https://%s' % EXTERNAL_GOB_HOST
EXTERNAL_GERRIT_URL = 'https://%s' % EXTERNAL_GERRIT_HOST

INTERNAL_GOB_INSTANCE = 'chrome-internal'
INTERNAL_GERRIT_INSTANCE = 'chrome-internal-review'
INTERNAL_GOB_HOST = GOB_HOST % INTERNAL_GOB_INSTANCE
INTERNAL_GERRIT_HOST = GOB_HOST % INTERNAL_GERRIT_INSTANCE
INTERNAL_GOB_URL = 'https://%s' % INTERNAL_GOB_HOST
INTERNAL_GERRIT_URL = 'https://%s' % INTERNAL_GERRIT_HOST

# Tests without 'cheets_CTS_', 'cheets_GTS.' prefix will not considered
# as CTS/GTS test in chromite.lib.cts_helper
DEFAULT_CTS_TEST_XML_MAP = {
    'cheets_CTS_': 'test_result.xml',
    'cheets_GTS.': 'test_result.xml',
    'cheets_GTS_': 'test_result.xml',
}
# Google Storage bucket URI to store results in.
DEFAULT_CTS_RESULTS_GSURI = 'gs://chromeos-cts-results/'
DEFAULT_CTS_APFE_GSURI = 'gs://chromeos-cts-apfe/'

# List of Android Portage packages.
ANDROID_PI_PACKAGE = 'android-container-pi'
ANDROID_VMRVC_PACKAGE = 'android-vm-rvc'
ANDROID_VMSC_PACKAGE = 'android-vm-sc'
# T uses master until the T branch is cut.
ANDROID_VMT_PACKAGE = 'android-vm-master'

ANDROID_ALL_PACKAGES = frozenset([ANDROID_PI_PACKAGE,
                                  ANDROID_VMRVC_PACKAGE,
                                  ANDROID_VMSC_PACKAGE,
                                  ANDROID_VMT_PACKAGE])

# List of supported Android branches. When adding/removing branches make sure
# the ANDROID_BRANCH_TO_BUILD_TARGETS map is also updated.
ANDROID_PI_BUILD_BRANCH = 'git_pi-arc-m96'
ANDROID_VMRVC_BUILD_BRANCH = 'git_rvc-arc-m96'
ANDROID_VMSC_BUILD_BRANCH = 'git_sc-arc-dev'
ANDROID_VMT_BUILD_BRANCH = 'git_master-arc-dev'

# Supported Android build targets for each branch. Maps from *_TARGET variables
# in Android ebuilds to Android build targets. Used during Android uprev to fill
# in corresponding variables.
# TODO(crbug/1192431): Move this next to uprev code once
# ANDROID_ALL_BUILD_TARGETS is removed.
ANDROID_BRANCH_TO_BUILD_TARGETS = {
    ANDROID_PI_BUILD_BRANCH: {
        'APPS_TARGET': 'apps',
        'ARM_TARGET': 'cheets_arm-user',
        'ARM64_TARGET': 'cheets_arm64-user',
        'X86_TARGET': 'cheets_x86-user',
        'X86_64_TARGET': 'cheets_x86_64-user',
        'ARM_USERDEBUG_TARGET': 'cheets_arm-userdebug',
        'ARM64_USERDEBUG_TARGET': 'cheets_arm64-userdebug',
        'X86_USERDEBUG_TARGET': 'cheets_x86-userdebug',
        'X86_64_USERDEBUG_TARGET': 'cheets_x86_64-userdebug',
        'SDK_GOOGLE_X86_USERDEBUG_TARGET': 'sdk_cheets_x86-userdebug',
        'SDK_GOOGLE_X86_64_USERDEBUG_TARGET': 'sdk_cheets_x86_64-userdebug',
    },
    ANDROID_VMRVC_BUILD_BRANCH: {
        'APPS_TARGET': 'apps',
        'ARM64_TARGET': 'bertha_arm64-user',
        'X86_64_TARGET': 'bertha_x86_64-user',
        'ARM64_USERDEBUG_TARGET': 'bertha_arm64-userdebug',
        'X86_64_USERDEBUG_TARGET': 'bertha_x86_64-userdebug',
    },
    ANDROID_VMSC_BUILD_BRANCH: {
        'ARM64_USERDEBUG_TARGET': 'bertha_arm64-userdebug',
        'X86_64_USERDEBUG_TARGET': 'bertha_x86_64-userdebug',
    },
    ANDROID_VMT_BUILD_BRANCH: {
        'X86_64_USERDEBUG_TARGET': 'bertha_x86_64-userdebug',
    },
}

# All possible *_TARGET variables in Android ebuild files, used when parsing
# ebuilds to determine the corresponding Android branch.
# TODO(crbug/1193413): Remove this.
ANDROID_ALL_BUILD_TARGETS = frozenset(itertools.chain.from_iterable(
    ANDROID_BRANCH_TO_BUILD_TARGETS.values()
))

# The bucket where we save Android artifacts indefinitely, to ensure any old
# Android versions in the commit history can be built.
# TODO(crbug/1192431): Move to service.android.
ARC_BUCKET_URL = 'gs://chromeos-arc-images/builds'

# URL template to Android symbols, used by release builders.
ANDROID_SYMBOLS_URL_TEMPLATE = (
    ARC_BUCKET_URL +
    '/%(branch)s-linux-%(target)s_%(arch)s-%(variant)s/%(version)s'
    '/%(target)s_%(arch)s-symbols-%(version)s.zip')
ANDROID_SYMBOLS_FILE = 'android-symbols.zip'

GOB_COOKIE_PATH = os.path.expanduser('~/.git-credential-cache/cookie')
GITCOOKIES_PATH = os.path.expanduser('~/.gitcookies')

# Timestamps in the JSON from GoB's web interface is of the form 'Tue
# Dec 02 17:48:06 2014' and is assumed to be in UTC.
GOB_COMMIT_TIME_FORMAT = '%a %b %d %H:%M:%S %Y'

CHROMITE_PROJECT = 'chromiumos/chromite'
CHROMITE_URL = '%s/%s' % (EXTERNAL_GOB_URL, CHROMITE_PROJECT)
CHROMIUM_SRC_PROJECT = 'chromium/src'
CHROMIUM_GOB_URL = '%s/%s.git' % (EXTERNAL_GOB_URL, CHROMIUM_SRC_PROJECT)
CHROME_INTERNAL_PROJECT = 'chrome/src-internal'
CHROME_INTERNAL_GOB_URL = '%s/%s.git' % (
    INTERNAL_GOB_URL, CHROME_INTERNAL_PROJECT)

DEFAULT_MANIFEST = 'default.xml'
OFFICIAL_MANIFEST = 'official.xml'
LKGM_MANIFEST = 'LKGM/lkgm.xml'

SHARED_CACHE_ENVVAR = 'CROS_CACHEDIR'
PARALLEL_EMERGE_STATUS_FILE_ENVVAR = 'PARALLEL_EMERGE_STATUS_FILE'

# These projects can be responsible for infra failures.
INFRA_PROJECTS = (CHROMITE_PROJECT,)


STREAK_COUNTERS = 'streak_counters'

PATCH_BRANCH = 'patch_branch'
STABLE_EBUILD_BRANCH = 'stabilizing_branch'
MERGE_BRANCH = 'merge_branch'

# These branches are deleted at the beginning of every buildbot run.
CREATED_BRANCHES = [
    PATCH_BRANCH,
    STABLE_EBUILD_BRANCH,
    MERGE_BRANCH
]

# SDK target.
TARGET_SDK = 'virtual/target-sdk'
# Default OS target packages.
TARGET_OS_PKG = 'virtual/target-os'
TARGET_OS_DEV_PKG = 'virtual/target-os-dev'
TARGET_OS_TEST_PKG = 'virtual/target-os-test'
TARGET_OS_FACTORY_PKG = 'virtual/target-os-factory'
TARGET_OS_FACTORY_SHIM_PKG = 'virtual/target-os-factory-shim'
# The virtuals composing a "full" build, e.g. what's built in the cq.
# Local (developer) builds only use target-os by default.
ALL_TARGET_PACKAGES = (
    TARGET_OS_PKG,
    TARGET_OS_DEV_PKG,
    TARGET_OS_TEST_PKG,
    TARGET_OS_FACTORY_PKG,
    TARGET_OS_FACTORY_SHIM_PKG,
)

# Constants for uprevving Chrome

CHROMEOS_BASE = 'chromeos-base'

# Portage category and package name for Chrome.
CHROME_CN = CHROMEOS_BASE
CHROME_PN = 'chromeos-chrome'
CHROME_CP = '%s/%s' % (CHROME_CN, CHROME_PN)

# Other packages to uprev while uprevving Chrome.
OTHER_CHROME_PACKAGES = ['chromeos-base/chromium-source',
                         'chromeos-base/chrome-icu']

# Chrome use flags
USE_CHROME_INTERNAL = 'chrome_internal'
USE_AFDO_USE = 'afdo_use'


# Builds and validates _alpha ebuilds.  These builds sync to the latest
# revsion of the Chromium src tree and build with that checkout.
CHROME_REV_TOT = 'tot'

# Builds and validates chrome at a given revision through cbuildbot
# --chrome_version
CHROME_REV_SPEC = 'spec'

# Builds and validates the latest Chromium release as defined by
# ~/trunk/releases in the Chrome src tree.  These ebuilds are suffixed with rc.
CHROME_REV_LATEST = 'latest_release'

# Builds and validates the latest Chromium release for a specific Chromium
# branch that we want to watch.  These ebuilds are suffixed with rc.
CHROME_REV_STICKY = 'stable_release'

# Builds and validates Chromium for a pre-populated directory.
# Also uses _alpha, since portage doesn't have anything lower.
CHROME_REV_LOCAL = 'local'
VALID_CHROME_REVISIONS = [CHROME_REV_TOT, CHROME_REV_LATEST,
                          CHROME_REV_STICKY, CHROME_REV_LOCAL, CHROME_REV_SPEC]


# Constants for uprevving Android.

# Builds and validates the latest Android release.
# TODO(b/187788131): cleanup this
ANDROID_REV_LATEST = 'latest_release'
VALID_ANDROID_REVISIONS = [ANDROID_REV_LATEST]

# Build types supported.

# TODO(sosa): Deprecate PFQ type.
# Incremental builds that are built using binary packages when available.
# These builds have less validation than other build types.
INCREMENTAL_TYPE = 'binary'

# These builds serve as PFQ builders.  This is being deprecated.
PFQ_TYPE = 'pfq'

# Android PFQ type.  Builds and validates new versions of Android.
ANDROID_PFQ_TYPE = 'android'

# Builds from source and non-incremental.  This builds fully wipe their
# chroot before the start of every build and no not use a BINHOST.
FULL_TYPE = 'full'

# Full but with versioned logic.
CANARY_TYPE = 'canary'

# Generate payloads for an already built build/version.
PAYLOADS_TYPE = 'payloads'

# How long we should wait for the signing fleet to sign payloads.
PAYLOAD_SIGNING_TIMEOUT = 10800

# Similar behavior to canary, but used to validate toolchain changes.
TOOLCHAIN_TYPE = 'toolchain'

# Generic type of tryjob only build configs.
TRYJOB_TYPE = 'tryjob'

# Special build type for Chroot builders.  These builds focus on building
# toolchains and validate that they work.
CHROOT_BUILDER_TYPE = 'chroot'
CHROOT_BUILDER_BOARD = 'amd64-host'

# Use for builds that don't requite a type.
GENERIC_TYPE = 'generic'

VALID_BUILD_TYPES = (
    INCREMENTAL_TYPE,
    FULL_TYPE,
    CANARY_TYPE,
    CHROOT_BUILDER_TYPE,
    CHROOT_BUILDER_BOARD,
    ANDROID_PFQ_TYPE,
    PFQ_TYPE,
    PAYLOADS_TYPE,
    TOOLCHAIN_TYPE,
    TRYJOB_TYPE,
    GENERIC_TYPE,
)

HWTEST_TRYBOT_NUM = 3
HWTEST_QUOTA_POOL = 'quota'

HWTEST_QUOTA_ACCOUNT_BVT = 'legacypool-bvt'
HWTEST_QUOTA_ACCOUNT_BVT_SYNC = 'bvt-sync'
HWTEST_QUOTA_ACCOUNT_PFQ = 'pfq'
HWTEST_QUOTA_ACCOUNT_SUITES = 'legacypool-suites'
HWTEST_QUOTA_ACCOUNT_TOOLCHAIN = 'toolchain'

# How many total test retries should be done for a suite.
HWTEST_MAX_RETRIES = 5

# Defines for the various hardware test suites:
#   BVT:  Basic blocking suite to be run against any build that
#       requires a HWTest phase.
#   COMMIT:  Suite of basic tests required for commits to the source
#       tree.  Runs as a blocking suite on the CQ and PFQ; runs as
#       a non-blocking suite on canaries.
#   CANARY:  Non-blocking suite run only against the canaries.
#   AFDO:  Non-blocking suite run only AFDO builders.
#   MOBLAB: Blocking Suite run only on *_moblab builders.
#   INSTALLER: Blocking suite run against all canaries; tests basic installer
#              functionality.
HWTEST_ARC_COMMIT_SUITE = 'bvt-arc'
HWTEST_BVT_SUITE = 'bvt-inline'
HWTEST_COMMIT_SUITE = 'bvt-cq'
HWTEST_CANARY_SUITE = 'bvt-perbuild'
HWTEST_INSTALLER_SUITE = 'bvt-installer'
# Runs all non-informational Tast tests (exercising any of OS, Chrome, and ARC).
HWTEST_TAST_CQ_SUITE = 'bvt-tast-cq'
# Runs non-informational Tast tests exercising either Chrome or ARC.
HWTEST_TAST_CHROME_PFQ_SUITE = 'bvt-tast-chrome-pfq'
# Runs non-informational Tast tests exercising ARC.
HWTEST_TAST_ANDROID_PFQ_SUITE = 'bvt-tast-android-pfq'
# Runs all Tast informational tests.
HWTEST_TAST_INFORMATIONAL_SUITE = 'bvt-tast-informational'
HWTEST_AFDO_SUITE = 'AFDO_record'
HWTEST_JETSTREAM_COMMIT_SUITE = 'jetstream_cq'
HWTEST_MOBLAB_SUITE = 'moblab'
HWTEST_MOBLAB_QUICK_SUITE = 'moblab_quick'
HWTEST_SANITY_SUITE = 'sanity'
HWTEST_TOOLCHAIN_SUITE = 'toolchain-tests'
# Non-blocking informational hardware tests for Chrome, run throughout the
# day on tip-of-trunk Chrome rather than on the daily Chrome branch.
HWTEST_CHROME_INFORMATIONAL = 'chrome-informational'

# Additional timeout to wait for autotest to abort a suite if the test takes
# too long to run. This is meant to be overly conservative as a timeout may
# indicate that autotest is at capacity.
HWTEST_TIMEOUT_EXTENSION = 10 * 60

HWTEST_WEEKLY_PRIORITY = 'Weekly'
HWTEST_CTS_PRIORITY = 'CTS'
HWTEST_GTS_PRIORITY = HWTEST_CTS_PRIORITY
HWTEST_DAILY_PRIORITY = 'Daily'
HWTEST_DEFAULT_PRIORITY = 'DEFAULT'
HWTEST_CQ_PRIORITY = 'CQ'
HWTEST_BUILD_PRIORITY = 'Build'
HWTEST_PFQ_PRIORITY = 'PFQ'
HWTEST_POST_BUILD_PRIORITY = 'PostBuild'

# Ordered by priority (first item being lowest).
HWTEST_VALID_PRIORITIES = [HWTEST_WEEKLY_PRIORITY,
                           HWTEST_CTS_PRIORITY,
                           HWTEST_DAILY_PRIORITY,
                           HWTEST_POST_BUILD_PRIORITY,
                           HWTEST_DEFAULT_PRIORITY,
                           HWTEST_BUILD_PRIORITY,
                           HWTEST_PFQ_PRIORITY,
                           HWTEST_CQ_PRIORITY]

# Creates a mapping of priorities to make easy comparsions.
# Use the same priorities mapping as autotest/client/common_lib/priorities.py
HWTEST_PRIORITIES_MAP = {
    HWTEST_WEEKLY_PRIORITY: 10,
    HWTEST_CTS_PRIORITY: 11,
    HWTEST_DAILY_PRIORITY: 20,
    HWTEST_POST_BUILD_PRIORITY: 30,
    HWTEST_DEFAULT_PRIORITY: 40,
    HWTEST_BUILD_PRIORITY: 50,
    HWTEST_PFQ_PRIORITY: 60,
    HWTEST_CQ_PRIORITY: 70}

# Creates a mapping of priorities for skylab hwtest tasks. In swarming,
# lower number means high priorities. Priority lower than 48 will be special
# tasks. The upper bound of priority is 255.
# Use the same priorities mapping as autotest/venv/skylab_suite/swarming_lib.py
SKYLAB_HWTEST_PRIORITIES_MAP = {
    HWTEST_WEEKLY_PRIORITY: 230,
    HWTEST_CTS_PRIORITY: 215,
    HWTEST_DAILY_PRIORITY: 200,
    HWTEST_POST_BUILD_PRIORITY: 170,
    HWTEST_DEFAULT_PRIORITY: 140,
    HWTEST_BUILD_PRIORITY: 110,
    HWTEST_PFQ_PRIORITY: 80,
    HWTEST_CQ_PRIORITY: 50,
}

# The environment for executing tests.
ENV_SKYLAB = 'skylab'
ENV_AUTOTEST = 'autotest'

# The cipd package for skylab tool
CIPD_SKYLAB_PACKAGE = 'chromiumos/infra/skylab/linux-amd64'
# The skylab tool CIPD package is pinned to a specific tag to avoid uncontrolled
# tool release.
CIPD_SKYLAB_INSTANCE_ID = 'cbuildbot-prod'

# HWTest result statuses
HWTEST_STATUS_PASS = 'pass'
HWTEST_STATUS_FAIL = 'fail'
HWTEST_STATUS_ABORT = 'abort'
HWTEST_STATUS_OTHER = 'other'
HWTEST_STATUES_NOT_PASSED = frozenset([HWTEST_STATUS_FAIL,
                                       HWTEST_STATUS_ABORT,
                                       HWTEST_STATUS_OTHER])

# Build messages
MESSAGE_TYPE_IGNORED_REASON = 'ignored_reason'
MESSAGE_TYPE_ANNOTATIONS_FINALIZED = 'annotations_finalized'
# MESSSGE_TYPE_IGNORED_REASON messages store the affected build as
# the CIDB column message_value.
MESSAGE_SUBTYPE_SELF_DESTRUCTION = 'self_destruction'

# Define HWTEST job_keyvals
JOB_KEYVAL_DATASTORE_PARENT_KEY = 'datastore_parent_key'
JOB_KEYVAL_CIDB_BUILD_ID = 'cidb_build_id'
JOB_KEYVAL_CIDB_BUILD_STAGE_ID = 'cidb_build_stage_id'
JOB_KEYVAL_BUILD_CONFIG = 'build_config'
JOB_KEYVAL_MASTER_BUILD_CONFIG = 'master_build_config'
JOB_KEYVAL_BRANCH = 'branch'


# How many total test retries should be done for a suite.
VM_TEST_MAX_RETRIES = 5
# Defines VM Test types.
SIMPLE_AU_TEST_TYPE = 'pfq_suite'
VM_SUITE_TEST_TYPE = 'vm_suite'
GCE_SUITE_TEST_TYPE = 'gce_suite'
CROS_VM_TEST_TYPE = 'cros_vm_test'
DEV_MODE_TEST_TYPE = 'dev_mode_test'
VALID_VM_TEST_TYPES = [
    SIMPLE_AU_TEST_TYPE,
    VM_SUITE_TEST_TYPE,
    GCE_SUITE_TEST_TYPE,
    CROS_VM_TEST_TYPE,
    DEV_MODE_TEST_TYPE
]
VALID_GCE_TEST_SUITES = ['gce-smoke', 'gce-sanity']
# MoblabVM tests are suites of tests used to validate a moblab image via
# VMTests.
MOBLAB_VM_SMOKE_TEST_TYPE = 'moblab_smoke_test'

CHROMIUMOS_OVERLAY_DIR = 'src/third_party/chromiumos-overlay'
PORTAGE_STABLE_OVERLAY_DIR = 'src/third_party/portage-stable'
ECLASS_OVERLAY_DIR = 'src/third_party/eclass-overlay'
CHROMEOS_PARTNER_OVERLAY_DIR = 'src/private-overlays/chromeos-partner-overlay/'
PUBLIC_BINHOST_CONF_DIR = os.path.join(CHROMIUMOS_OVERLAY_DIR,
                                       'chromeos/binhost')
PRIVATE_BINHOST_CONF_DIR = os.path.join(CHROMEOS_PARTNER_OVERLAY_DIR,
                                        'chromeos/binhost')

VERSION_FILE = os.path.join(CHROMIUMOS_OVERLAY_DIR,
                            'chromeos/config/chromeos_version.sh')
SDK_VERSION_FILE = os.path.join(PUBLIC_BINHOST_CONF_DIR,
                                'host/sdk_version.conf')
SDK_GS_BUCKET = 'chromiumos-sdk'

PUBLIC = 'public'
PRIVATE = 'private'

BOTH_OVERLAYS = 'both'
PUBLIC_OVERLAYS = PUBLIC
PRIVATE_OVERLAYS = PRIVATE
VALID_OVERLAYS = [BOTH_OVERLAYS, PUBLIC_OVERLAYS, PRIVATE_OVERLAYS, None]

# Common default logging settings for use with the logging module.
LOGGER_FMT = '%(asctime)s: %(levelname)s: %(message)s'
LOGGER_DATE_FMT = '%H:%M:%S'

# Used by remote patch serialization/deserialzation.
INTERNAL_PATCH_TAG = 'i'
EXTERNAL_PATCH_TAG = 'e'
PATCH_TAGS = (INTERNAL_PATCH_TAG, EXTERNAL_PATCH_TAG)

GERRIT_ON_BORG_LABELS = {
    'Code-Review': 'CRVW',
    'Commit-Queue': 'COMR',
    'Verified': 'VRIF',
}

# Environment variables that should be exposed to all children processes
# invoked via cros_build_lib.run.
ENV_PASSTHRU = ('CROS_SUDO_KEEP_ALIVE', SHARED_CACHE_ENVVAR,
                PARALLEL_EMERGE_STATUS_FILE_ENVVAR)

# List of variables to proxy into the chroot from the host, and to
# have sudo export if existent. Anytime this list is modified, a new
# chroot_version_hooks.d upgrade script that symlinks to 153_rewrite_sudoers.d
# should be created.
CHROOT_ENVIRONMENT_WHITELIST = (
    'CHROMEOS_OFFICIAL',
    'CHROMEOS_VERSION_AUSERVER',
    'CHROMEOS_VERSION_DEVSERVER',
    'CHROMEOS_VERSION_TRACK',
    'GCC_GITHASH',
    'GIT_AUTHOR_EMAIL',
    'GIT_AUTHOR_NAME',
    'GIT_COMMITTER_EMAIL',
    'GIT_COMMITTER_NAME',
    'GIT_PROXY_COMMAND',
    'GIT_SSH',
    'RSYNC_PROXY',
    'SSH_AGENT_PID',
    'SSH_AUTH_SOCK',
    'TMUX',
    'USE',
    'all_proxy',
    'ftp_proxy',
    'http_proxy',
    'https_proxy',
    'no_proxy',
)

# Paths for Chrome LKGM which are relative to the Chromium base url.
CHROME_LKGM_FILE = 'CHROMEOS_LKGM'
PATH_TO_CHROME_LKGM = 'chromeos/%s' % CHROME_LKGM_FILE
# Path for the Chrome LKGM's closest OWNERS file.
PATH_TO_CHROME_CHROMEOS_OWNERS = 'chromeos/OWNERS'

# Cache constants.
COMMON_CACHE = 'common'

# Artifact constants.
def _SlashToUnderscore(string):
  return string.replace('/', '_')

# GCE tar ball constants.
def ImageBinToGceTar(image_bin):
  assert image_bin.endswith('.bin'), ('Filename %s does not end with ".bin"' %
                                      image_bin)
  return '%s_gce.tar.gz' % os.path.splitext(image_bin)[0]

RELEASE_BUCKET = 'gs://chromeos-releases'
TRASH_BUCKET = 'gs://chromeos-throw-away-bucket'
CHROME_SYSROOT_TAR = 'sysroot_%s.tar.xz' % _SlashToUnderscore(CHROME_CP)
CHROME_ENV_TAR = 'environment_%s.tar.xz' % _SlashToUnderscore(CHROME_CP)
CHROME_ENV_FILE = 'environment'
BASE_IMAGE_NAME = 'chromiumos_base_image'
BASE_IMAGE_TAR = '%s.tar.xz' % BASE_IMAGE_NAME
BASE_IMAGE_BIN = '%s.bin' % BASE_IMAGE_NAME
BASE_IMAGE_GCE_TAR = ImageBinToGceTar(BASE_IMAGE_BIN)
IMAGE_SCRIPTS_NAME = 'image_scripts'
IMAGE_SCRIPTS_TAR = '%s.tar.xz' % IMAGE_SCRIPTS_NAME
TARGET_SYSROOT_TAR = 'sysroot_%s.tar.xz' % _SlashToUnderscore(TARGET_OS_PKG)
VM_IMAGE_NAME = 'chromiumos_qemu_image'
VM_IMAGE_BIN = '%s.bin' % VM_IMAGE_NAME
VM_IMAGE_TAR = '%s.tar.xz' % VM_IMAGE_NAME
VM_DISK_PREFIX = 'chromiumos_qemu_disk.bin'
VM_MEM_PREFIX = 'chromiumos_qemu_mem.bin'
VM_NUM_RETRIES = 0
# Disabling Tast VM retries because of https://crbug.com/1098346.
TAST_VM_NUM_RETRIES = 0
TAST_VM_TEST_RESULTS = 'tast_vm_test_results_%(attempt)s'
BASE_GUEST_VM_DIR = 'guest-vm-base'
TEST_GUEST_VM_DIR = 'guest-vm-test'
BASE_GUEST_VM_TAR = '%s.tar.xz' % BASE_GUEST_VM_DIR
TEST_GUEST_VM_TAR = '%s.tar.xz' % TEST_GUEST_VM_DIR

KERNEL_IMAGE_NAME = 'vmlinuz'
KERNEL_IMAGE_BIN = '%s.bin' % KERNEL_IMAGE_NAME
KERNEL_IMAGE_TAR = '%s.tar.xz' % KERNEL_IMAGE_NAME

TEST_IMAGE_NAME = 'chromiumos_test_image'
TEST_IMAGE_TAR = '%s.tar.xz' % TEST_IMAGE_NAME
TEST_IMAGE_BIN = '%s.bin' % TEST_IMAGE_NAME
TEST_IMAGE_GCE_TAR = ImageBinToGceTar(TEST_IMAGE_BIN)
TEST_KEY_PRIVATE = 'id_rsa'
TEST_KEY_PUBLIC = 'id_rsa.pub'

BREAKPAD_DEBUG_SYMBOLS_NAME = 'debug_breakpad'
BREAKPAD_DEBUG_SYMBOLS_TAR = '%s.tar.xz' % BREAKPAD_DEBUG_SYMBOLS_NAME

CODE_COVERAGE_LLVM_JSON_SYMBOLS_NAME = 'code_coverage'
CODE_COVERAGE_LLVM_JSON_SYMBOLS_TAR = ('%s.tar.xz'
                                       % CODE_COVERAGE_LLVM_JSON_SYMBOLS_NAME)

DEBUG_SYMBOLS_NAME = 'debug'
DEBUG_SYMBOLS_TAR = '%s.tgz' % DEBUG_SYMBOLS_NAME

DEV_IMAGE_NAME = 'chromiumos_image'
DEV_IMAGE_BIN = '%s.bin' % DEV_IMAGE_NAME

RECOVERY_IMAGE_NAME = 'recovery_image'
RECOVERY_IMAGE_BIN = '%s.bin' % RECOVERY_IMAGE_NAME
RECOVERY_IMAGE_TAR = '%s.tar.xz' % RECOVERY_IMAGE_NAME

FACTORY_IMAGE_NAME = 'factory_install_shim'
FACTORY_IMAGE_BIN = f'{FACTORY_IMAGE_NAME}.bin'

# Image type constants.
IMAGE_TYPE_BASE = 'base'
IMAGE_TYPE_DEV = 'dev'
IMAGE_TYPE_TEST = 'test'
IMAGE_TYPE_RECOVERY = 'recovery'
# This is the image type used by legacy CBB configs.
IMAGE_TYPE_FACTORY = 'factory'
# This is the image type mapping to the factory image type in build_image.
IMAGE_TYPE_FACTORY_SHIM = 'factory_install'
IMAGE_TYPE_FIRMWARE = 'firmware'
# USB PD accessory microcontroller firmware (e.g. power brick, display dongle).
IMAGE_TYPE_ACCESSORY_USBPD = 'accessory_usbpd'
# Standalone accessory microcontroller firmware (e.g. wireless keyboard).
IMAGE_TYPE_ACCESSORY_RWSIG = 'accessory_rwsig'
# GSC Firmware.
IMAGE_TYPE_GSC_FIRMWARE = 'gsc_firmware'
# TODO(b/173049030): Deprecate this alias after 2021-06.
IMAGE_TYPE_CR50_FIRMWARE = IMAGE_TYPE_GSC_FIRMWARE

IMAGE_TYPE_TO_NAME = {
    IMAGE_TYPE_BASE: BASE_IMAGE_BIN,
    IMAGE_TYPE_DEV: DEV_IMAGE_BIN,
    IMAGE_TYPE_RECOVERY: RECOVERY_IMAGE_BIN,
    IMAGE_TYPE_TEST: TEST_IMAGE_BIN,
    IMAGE_TYPE_FACTORY_SHIM: FACTORY_IMAGE_BIN,
}
IMAGE_NAME_TO_TYPE = dict((v, k) for k, v in IMAGE_TYPE_TO_NAME.items())

METADATA_JSON = 'metadata.json'
PARTIAL_METADATA_JSON = 'partial-metadata.json'
METADATA_TAGS = 'tags'
DELTA_SYSROOT_TAR = 'delta_sysroot.tar.xz'
DELTA_SYSROOT_BATCH = 'batch'

FIRMWARE_ARCHIVE_NAME = 'firmware_from_source.tar.bz2'
FPMCU_UNITTESTS_ARCHIVE_NAME = 'fpmcu_unittests.tar.bz2'

# Global configuration constants.
SYNC_RETRIES = 4
SLEEP_TIMEOUT = 30

# Lab status url.
LAB_STATUS_URL = 'http://chromiumos-lab.appspot.com/current?format=json'

GOLO_SMTP_SERVER = 'mail.golo.chromium.org'

CHROME_GARDENER = 'chrome'
# Email alias to add as reviewer in Gerrit, which GWSQ will then automatically
# assign to the current gardener.
CHROME_GARDENER_REVIEW_EMAIL = 'chrome-os-gardeners-reviews@google.com'

# Useful config targets.
CANARY_MASTER = 'master-release'
PFQ_MASTER = 'master-chromium-pfq'
PI_ANDROID_PFQ_MASTER = 'master-pi-android-pfq'
VMRVC_ANDROID_PFQ_MASTER = 'master-vmrvc-android-pfq'
VMSC_ANDROID_PFQ_MASTER = 'master-vmsc-android-pfq'
VMT_ANDROID_PFQ_MASTER = 'master-vmt-android-pfq'
TOOLCHAIN_MASTTER = 'master-toolchain'


# Email validation regex. Not quite fully compliant with RFC 2822, but good
# approximation.
EMAIL_REGEX = r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}'

# Blacklist of files not allowed to be uploaded into the Partner Project Google
# Storage Buckets:
# debug.tgz contains debug symbols.
# manifest.xml exposes all of our repo names.
# vm_test_results can contain symbolicated crash dumps.
EXTRA_BUCKETS_FILES_BLACKLIST = [
    'debug.tgz',
    'manifest.xml',
    'vm_test_results_*'
]

# AFDO common constants.
# How long does the AFDO_record autotest have to generate the AFDO perf data.
AFDO_GENERATE_TIMEOUT = 120 * 60

# Gmail Credentials.
GMAIL_TOKEN_CACHE_FILE = os.path.expanduser('~/.gmail_credentials')
GMAIL_TOKEN_JSON_FILE = '/creds/refresh_tokens/chromeos_gmail_alerts'

# Maximum number of boards per release group builder. This should be
# chosen/adjusted based on expected release build times such that successive
# builds don't overlap and create a backlog.
MAX_RELEASE_GROUP_BOARDS = 4

CHROMEOS_SERVICE_ACCOUNT = os.path.join('/', 'creds', 'service_accounts',
                                        'service-account-chromeos.json')

# Buildbucket buckets
CHROMEOS_RELEASE_BUILDBUCKET_BUCKET = 'chromeos_release'
CHROMEOS_BUILDBUCKET_BUCKET = 'chromeos'
INTERNAL_SWARMING_BUILDBUCKET_BUCKET = 'general'

# Milo URL
CHROMEOS_MILO_HOST = 'https://ci.chromium.org/b/'

ACTIVE_BUCKETS = [
    CHROMEOS_RELEASE_BUILDBUCKET_BUCKET,
    CHROMEOS_BUILDBUCKET_BUCKET,
    INTERNAL_SWARMING_BUILDBUCKET_BUCKET,
]

# Build retry limit on buildbucket
#
# 2020-05-13 by engeg@: This is rarely effective, causes confusion,
# higher bot utilization, and if the initial try was past uploading artifacts
# then the retry is destined to fail with a difficult to parse error.
# 2020-05-19 by seanabraham@: Leave this at zero. These retries can break
# Chrome-wide profiling. http://b/156994019
BUILDBUCKET_BUILD_RETRY_LIMIT = 0  # Do not change. Read the above.

# TODO(nxia): consolidate all run.metadata key constants,
# add a unit test to avoid duplicated keys in run_metadata

# Builder_run metadata keys
METADATA_SCHEDULED_IMPORTANT_SLAVES = 'scheduled_important_slaves'
METADATA_SCHEDULED_EXPERIMENTAL_SLAVES = 'scheduled_experimental_slaves'
METADATA_UNSCHEDULED_SLAVES = 'unscheduled_slaves'
# List of builders marked as experimental through the tree status, not all the
# experimental builders for a run.
METADATA_EXPERIMENTAL_BUILDERS = 'experimental_builders'

# Metadata key to indicate whether a build is self-destructed.
SELF_DESTRUCTED_BUILD = 'self_destructed_build'

# Metadata key to indicate whether a build is self-destructed with success.
SELF_DESTRUCTED_WITH_SUCCESS_BUILD = 'self_destructed_with_success_build'

# Chroot snapshot names
CHROOT_SNAPSHOT_CLEAN = 'clean-chroot'

# Partition labels.
PART_STATE = 'STATE'
PART_ROOT_A = 'ROOT-A'
PART_ROOT_B = 'ROOT-B'
PART_KERN_A = 'KERN-A'
PART_KERN_B = 'KERN-B'
PART_MINIOS_A = 'MINIOS-A'

# Crossystem related constants.
MINIOS_PRIORITY = 'minios_priority'

# Quick provision payloads. These file names should never be changed, otherwise
# very bad things can happen :). The reason is we have already uploaded these
# files with these names for all boards. So if the name changes, all scripts
# that have been using this need to handle both cases to be backward compatible.
QUICK_PROVISION_PAYLOAD_KERNEL = 'full_dev_part_KERN.bin.gz'
QUICK_PROVISION_PAYLOAD_ROOTFS = 'full_dev_part_ROOT.bin.gz'
QUICK_PROVISION_PAYLOAD_MINIOS = 'full_dev_part_MINIOS.bin.gz'

# Mock build and stage IDs.
MOCK_STAGE_ID = 313377
MOCK_BUILD_ID = 31337

# Topology dictionary copied from CIDB.
TOPOLOGY_DICT = {
    '/buildbucket/host':
        'cr-buildbucket.appspot.com',
    '/chrome_swarming_proxy/host':
        'chromeos-swarming.appspot.com',
    '/datastore/creds_file': ('/creds/service_accounts/service-account-chromeos'
                              '-datastore-writer-prod.json'),
    '/sheriffomatic/host':
        'sheriff-o-matic.appspot.com',
    '/statsd/es_host':
        '104.154.79.237',
    '/statsd/host':
        '104.154.79.237',
}

# Percentage of child builders that need to complete to update LKGM
LKGM_THRESHOLD = 80

# Dev key related names.
VBOOT_DEVKEYS_DIR = os.path.join('/usr/share/vboot/devkeys')
KERNEL_PUBLIC_SUBKEY = 'kernel_subkey.vbpubk'
KERNEL_DATA_PRIVATE_KEY = 'kernel_data_key.vbprivk'
KERNEL_KEYBLOCK = 'kernel.keyblock'
RECOVERY_PUBLIC_KEY = 'recovery_key.vbpubk'
RECOVERY_DATA_PRIVATE_KEY = 'recovery_kernel_data_key.vbprivk'
RECOVERY_KEYBLOCK = 'recovery_kernel.keyblock'
MINIOS_DATA_PRIVATE_KEY = 'minios_kernel_data_key.vbprivk'
MINIOS_KEYBLOCK = 'minios_kernel.keyblock'
