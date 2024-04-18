# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Configuration options for various cbuildbot builders."""

import copy
import logging

from chromite.config import chromeos_config_boards as chromeos_boards
from chromite.lib import config_lib
from chromite.lib import constants
from chromite.utils import memoize


def _frozen_ge_set(ge_build_config, values, extras=None):
    """Return a frozenset of things in GE."""
    separate_board_names = set(
        config_lib.GeBuildConfigAllBoards(ge_build_config)
    )
    unified_builds = config_lib.GetUnifiedBuildConfigAllBuilds(ge_build_config)
    unified_board_names = {
        b[config_lib.CONFIG_TEMPLATE_REFERENCE_BOARD_NAME]
        for b in unified_builds
    }
    board_names = separate_board_names | unified_board_names
    return frozenset(x for x in values if x in board_names).union(
        extras or frozenset()
    )


def add_images(required_images):
    """Add required images when applying changes to a BuildConfig.

    Used similarly to append_useflags.

    Args:
        required_images: A list of image names that need to be present in the
            final build config.

    Returns:
        A callable suitable for use with BuildConfig.apply.
    """
    required_images = set(required_images)

    def handler(old_images):
        if not old_images:
            old_images = []

        new_images = old_images
        for image_name in required_images:
            if set(required_images).issubset(new_images):
                break
            new_images.append(image_name)
        return new_images

    return handler


def remove_images(unsupported_images):
    """Remove unsupported images when applying changes to a BuildConfig.

    Used similarly to append_useflags.

    Args:
        unsupported_images: A list of image names that should not be present in
            the final build config.

    Returns:
        A callable suitable for use with BuildConfig.apply.
    """
    unsupported = set(unsupported_images)

    def handler(old_images):
        if not old_images:
            old_images = []
        return [i for i in old_images if i not in unsupported]

    return handler


def GetBoardTypeToBoardsDict(ge_build_config):
    """Get board type to board names dict.

    Args:
        ge_build_config: Dictionary containing the decoded GE configuration
            file.

    Returns:
        A dict mapping board types to board name collections.
        The dict contains board types including distinct_board_sets,
        all_release_boards, all_boards, and internal_boards.
    """
    ge_arch_board_dict = config_lib.GetArchBoardDict(ge_build_config)

    boards_dict = {}

    arm_internal_release_boards = (
        chromeos_boards.arm_internal_release_boards
        | ge_arch_board_dict.get(config_lib.CONFIG_ARM_INTERNAL, set())
    )
    arm_external_boards = (
        chromeos_boards.arm_external_boards
        | ge_arch_board_dict.get(config_lib.CONFIG_ARM_EXTERNAL, set())
    )

    x86_internal_release_boards = (
        chromeos_boards.x86_internal_release_boards
        | ge_arch_board_dict.get(config_lib.CONFIG_X86_INTERNAL, set())
    )
    x86_external_boards = (
        chromeos_boards.x86_external_boards
        | ge_arch_board_dict.get(config_lib.CONFIG_X86_EXTERNAL, set())
    )

    # Every board should be in only 1 of the above sets.
    boards_dict["distinct_board_sets"] = [
        arm_internal_release_boards,
        arm_external_boards,
        x86_internal_release_boards,
        x86_external_boards,
    ]

    arm_full_boards = arm_internal_release_boards | arm_external_boards
    x86_full_boards = x86_internal_release_boards | x86_external_boards

    arm_boards = arm_full_boards
    x86_boards = x86_full_boards

    boards_dict["all_release_boards"] = (
        arm_internal_release_boards | x86_internal_release_boards
    )
    all_boards = x86_boards | arm_boards
    boards_dict["all_boards"] = all_boards

    boards_dict["internal_boards"] = boards_dict["all_release_boards"]

    boards_dict["generic_kernel_boards"] = frozenset(
        ["amd64-generic"],
    )

    all_ge_boards = set()
    for val in ge_arch_board_dict.values():
        all_ge_boards |= val
    boards_dict["unknown_boards"] = frozenset(all_ge_boards - all_boards)

    return boards_dict


def DefaultSettings():
    """Create the default build config values for this site.

    Returns:
        dict: of default config_lib.BuildConfig values to use for this site.
    """
    # Site specific adjustments for default BuildConfig values.
    defaults = config_lib.DefaultSettings()

    # Git repository URL for our manifests.
    #  https://chromium.googlesource.com/chromiumos/manifest
    #  https://chrome-internal.googlesource.com/chromeos/manifest-internal
    defaults["manifest_repo_url"] = config_lib.GetSiteParams().MANIFEST_URL

    return defaults


def GeneralTemplates(site_config):
    """Defines templates that are shared between categories of builders.

    Args:
        site_config: A SiteConfig object to add the templates too.
        ge_build_config: Dictionary containing the decoded GE configuration
            file.
    """
    # Builder type templates.

    site_config.AddTemplate(
        "full",
        # Full builds are test builds to show that we can build from scratch,
        # so use settings to build from scratch, and archive the results.
        usepkg_build_packages=False,
        build_timeout=12 * 60 * 60,
        display_label=config_lib.DISPLAY_LABEL_FULL,
        build_type=constants.FULL_TYPE,
        luci_builder=config_lib.LUCI_BUILDER_FULL,
        archive_build_debug=True,
        images=["base", "recovery", "test", "factory_install"],
        git_sync=True,
        description="Full Builds",
        doc=(
            "https://dev.chromium.org/chromium-os/build/builder-overview#"
            "TOC-Continuous"
        ),
    )

    site_config.AddTemplate(
        "external",
        internal=False,
        overlays=constants.PUBLIC_OVERLAYS,
        manifest_repo_url=config_lib.GetSiteParams().MANIFEST_URL,
        manifest=constants.DEFAULT_MANIFEST,
    )

    # This builds with more source available.
    site_config.AddTemplate(
        "internal",
        internal=True,
        overlays=constants.BOTH_OVERLAYS,
        manifest_repo_url=config_lib.GetSiteParams().MANIFEST_INT_URL,
    )

    site_config.AddTemplate(
        "infra_builder",
        luci_builder=config_lib.LUCI_BUILDER_INFRA,
    )

    # This adds Chrome branding.
    site_config.AddTemplate(
        "official_chrome",
        useflags=config_lib.append_useflags([constants.USE_CHROME_INTERNAL]),
    )

    # This sets chromeos_official.
    site_config.AddTemplate(
        "official",
        site_config.templates.official_chrome,
        chromeos_official=True,
    )

    site_config.AddTemplate(
        "release_common",
        site_config.templates.full,
        site_config.templates.official,
        site_config.templates.internal,
        display_label=config_lib.DISPLAY_LABEL_RELEASE,
        build_type=constants.CANARY_TYPE,
        luci_builder=config_lib.LUCI_BUILDER_LEGACY_RELEASE,
        suite_scheduling=True,
        # Because release builders never use prebuilts, they need the
        # longer timeout.  See crbug.com/938958.
        build_timeout=18 * 60 * 60,
        useflags=config_lib.append_useflags(["-cros-debug", "thinlto"]),
        manifest=constants.OFFICIAL_MANIFEST,
        manifest_version=True,
        images=["base", "recovery", "test", "factory_install"],
        sign_types=["recovery", "accessory_rwsig"],
        push_image=True,
        upload_symbols=True,
        run_build_configs_export=True,
        binhost_bucket="gs://chromeos-dev-installer",
        binhost_key="RELEASE_BINHOST",
        binhost_base_url=(
            "https://commondatastorage.googleapis.com/chromeos-dev-installer"
        ),
        git_sync=False,
        description="Release Builds (canary) (internal)",
        doc=(
            "https://dev.chromium.org/chromium-os/build/builder-overview#"
            "TOC-Canaries"
        ),
    )

    site_config.AddTemplate(
        "release",
        site_config.templates.release_common,
        luci_builder=config_lib.LUCI_BUILDER_LEGACY_RELEASE,
    )

    # Factory releases much inherit from these classes.
    # Modifications for these release builders should go here.

    # Naming conventions also must be followed. Factory branches must end
    # in "-factory".

    site_config.AddTemplate(
        "factory",
        site_config.templates.release_common,
        display_label=config_lib.DISPLAY_LABEL_FACTORY,
        description="Factory Builds",
        factory_toolkit=True,
        images=["test", "factory_install"],
        luci_builder=config_lib.LUCI_BUILDER_FACTORY,
        sign_types=["factory"],
        upload_hw_test_artifacts=True,
        upload_symbols=False,
    )

    # This should be used by any "workspace_builders."
    site_config.AddTemplate(
        "workspace",
        postsync_patch=False,
    )

    site_config.AddTemplate(
        "build_external_chrome",
        useflags=config_lib.append_useflags(
            ["-%s" % constants.USE_CHROME_INTERNAL]
        ),
    )

    site_config.AddTemplate(
        "buildspec",
        site_config.templates.workspace,
        site_config.templates.internal,
        luci_builder=config_lib.LUCI_BUILDER_FACTORY,
        master=True,
        boards=[],
        build_type=constants.GENERIC_TYPE,
        uprev=True,
        overlays=constants.BOTH_OVERLAYS,
        push_overlays=constants.BOTH_OVERLAYS,
        builder_class_name="workspace_builders.BuildSpecBuilder",
        build_timeout=4 * 60 * 60,
        description="Buildspec creator.",
    )


def CreateBoardConfigs(boards_dict, ge_build_config):
    """Create mixin templates for each board."""
    # Extract the full list of board names from GE data.
    separate_board_names = set(
        config_lib.GeBuildConfigAllBoards(ge_build_config)
    )
    unified_builds = config_lib.GetUnifiedBuildConfigAllBuilds(ge_build_config)
    unified_board_names = {
        b[config_lib.CONFIG_TEMPLATE_REFERENCE_BOARD_NAME]
        for b in unified_builds
    }
    board_names = separate_board_names | unified_board_names

    # TODO(crbug.com/648473): Remove these after GE adds them to their data set.
    board_names = board_names.union(boards_dict["all_boards"])

    result = {}
    for board in board_names:
        board_config = config_lib.BuildConfig(boards=[board])

        if board in chromeos_boards.nofactory_boards:
            board_config.apply(
                factory=False,
                factory_toolkit=False,
                factory_install_netboot=False,
                images=remove_images(["factory_install"]),
            )
        if board in chromeos_boards.builder_incompatible_binaries_boards:
            board_config.apply(unittests=False)

        result[board] = board_config

    return result


def CreateInternalBoardConfigs(site_config, boards_dict, ge_build_config):
    """Create mixin templates for each board."""
    result = CreateBoardConfigs(boards_dict, ge_build_config)

    for board in boards_dict["internal_boards"]:
        if board in result:
            result[board].apply(
                site_config.templates.internal,
                site_config.templates.official_chrome,
                manifest=constants.OFFICIAL_MANIFEST,
            )

    return result


def UpdateBoardConfigs(board_configs, boards, *args, **kwargs):
    """Update "board_configs" for selected chromeos_boards.

    Args:
        board_configs: Dict in CreateBoardConfigs format to filter from.
        boards: Iterable of boards to update in the dict.
        *args: List of templates to apply.
        **kwargs: Individual keys to update.

    Returns:
        Copy of board_configs dict with boards boards update with templates
        and values applied.
    """
    result = board_configs.copy()
    for b in boards:
        result[b] = result[b].derive(*args, **kwargs)

    return result


def FullBuilders(site_config, boards_dict, ge_build_config):
    """Create all full builders.

    Args:
        site_config: config_lib.SiteConfig to be modified by adding templates
            and configs.
        boards_dict: A dict mapping board types to board name collections.
        ge_build_config: Dictionary containing the decoded GE configuration
            file.
    """
    active_builders = _frozen_ge_set(
        ge_build_config,
        [],
        ("amd64-generic",),
    )

    # Move the following builders to active_builders once they are consistently
    # green.
    unstable_builders = _frozen_ge_set(ge_build_config, [])

    external_board_configs = CreateBoardConfigs(boards_dict, ge_build_config)

    site_config.AddForBoards(
        config_lib.CONFIG_TYPE_FULL,
        ["amd64-generic"],
        external_board_configs,
        site_config.templates.full,
        site_config.templates.build_external_chrome,
        internal=False,
        manifest_repo_url=config_lib.GetSiteParams().MANIFEST_URL,
        overlays=constants.PUBLIC_OVERLAYS,
        prebuilts=constants.PUBLIC,
    )

    master_config = site_config.Add(
        "master-full",
        site_config.templates.full,
        site_config.templates.internal,
        site_config.templates.build_external_chrome,
        boards=[],
        master=True,
        manifest_version=True,
        overlays=constants.PUBLIC_OVERLAYS,
        slave_configs=[],
        schedule=None,
    )

    master_config.AddSlaves(
        site_config.ApplyForBoards(
            config_lib.CONFIG_TYPE_FULL,
            active_builders,
            manifest_version=True,
        )
    )

    master_config.AddSlaves(
        site_config.ApplyForBoards(
            config_lib.CONFIG_TYPE_FULL,
            unstable_builders,
            manifest_version=True,
            important=False,
        )
    )


def FactoryBuilders(site_config, _boards_dict, _ge_build_config):
    """Create all factory build configs.

    Args:
        site_config: config_lib.SiteConfig to be modified by adding templates
            and configs.
        boards_dict: A dict mapping board types to board name collections.
        ge_build_config: Dictionary containing the decoded GE configuration
            file.
    """
    # pylint: disable=unused-variable
    # Intervals:
    # None: Do not schedule automatically.
    DAILY = "with 24h interval"  # 1 day interval
    WEEKLY = "with 168h interval"  # 1 week interval
    MONTHLY = "with 720h interval"  # 30 day interval
    TRIGGERED = "triggered"  # Only when triggered
    branch_builders = [
        (MONTHLY, "factory-oak-8182.B", ["elm", "hana"]),
        (MONTHLY, "factory-gru-8652.B", ["kevin"]),
        (MONTHLY, "factory-gale-8743.19.B", ["gale"]),
        (MONTHLY, "factory-reef-8811.B", ["reef", "pyro", "sand", "snappy"]),
        (MONTHLY, "factory-gru-9017.B", ["gru", "bob"]),
        (MONTHLY, "factory-eve-9667.B", ["eve"]),
        (MONTHLY, "factory-coral-10122.B", ["coral"]),
        (MONTHLY, "factory-fizz-10167.B", ["fizz"]),
        (MONTHLY, "factory-scarlet-10211.B", ["scarlet"]),
        (MONTHLY, "factory-soraka-10323.39.B", ["soraka"]),
        (MONTHLY, "factory-poppy-10504.B", ["nautilus"]),
        (MONTHLY, "factory-nami-10715.B", ["nami", "kalista"]),
        (MONTHLY, "factory-nocturne-11066.B", ["nocturne"]),
        (MONTHLY, "factory-grunt-11164.B", ["grunt"]),
        (MONTHLY, "factory-grunt-11164.135.B", ["grunt"]),
        (MONTHLY, "factory-rammus-11289.B", ["rammus"]),
        (WEEKLY, "factory-octopus-11512.B", ["octopus"]),
        (WEEKLY, "factory-atlas-11907.B", ["atlas"]),
        (WEEKLY, "factory-sarien-12033.B", ["sarien"]),
        (WEEKLY, "factory-mistral-12361.B", ["mistral"]),
        (WEEKLY, "factory-kukui-12587.B", ["kukui", "jacuzzi"]),
        (WEEKLY, "factory-hatch-12692.B", ["hatch"]),
        (WEEKLY, "factory-excelsior-12812.B", ["excelsior"]),
        (WEEKLY, "factory-drallion-13080.B", ["drallion"]),
        (MONTHLY, "factory-endeavour-13295.B", ["endeavour"]),
        (WEEKLY, "factory-puff-13329.B", ["puff", "puff-moblab"]),
        (WEEKLY, "factory-zork-13427.B", ["zork"]),
        (WEEKLY, "factory-trogdor-13443.B", ["trogdor", "strongbad"]),
        (DAILY, "factory-trogdor-15210.B", ["trogdor", "strongbad"]),
        (DAILY, "factory-strongbad-13963.B", ["trogdor", "strongbad"]),
        (WEEKLY, "factory-volteer-13600.B", ["volteer"]),
        (WEEKLY, "factory-dedede-13683.B", ["dedede"]),
        (TRIGGERED, "factory-keeby-14162.B", ["keeby"]),
        (WEEKLY, "factory-zork-13700.B", ["zork"]),
        (WEEKLY, "factory-puff-13813.B", ["puff"]),
        (WEEKLY, "factory-asurada-13929.B", ["asurada"]),
        (WEEKLY, "factory-ambassador-14265.B", ["ambassador"]),
        (DAILY, "factory-kukui-14374.B", ["kukui", "jacuzzi"]),
        (WEEKLY, "factory-cherry-14455.B", ["cherry"]),
        (WEEKLY, "factory-brya-14517.B", ["brya", "brask"]),
        (WEEKLY, "factory-guybrush-14908.B", ["guybrush"]),
        (TRIGGERED, "factory-brya-14909.124.B", ["brya"]),
        (WEEKLY, "factory-corsola-15196.B", ["corsola", "staryu"]),
        (DAILY, "factory-nissa-15199.B", ["nissa"]),
        (DAILY, "factory-brya-15231.B", ["brya", "brask", "constitution"]),
        (DAILY, "factory-skyrim-15384.B", ["skyrim"]),
        # This is intended to create master branch tryjobs, NOT for production
        # builds. Update the associated list of boards as needed.
        (
            None,
            "master",
            [
                "atlas",
                "octopus",
                "rammus",
                "coral",
                "eve",
                "sarien",
                "mistral",
                "drallion",
            ],
        ),
    ]

    _FACTORYBRANCH_TIMEOUT = 12 * 60 * 60

    # Requires that you set boards, and workspace_branch.
    site_config.AddTemplate(
        "factorybranch",
        site_config.templates.factory,
        site_config.templates.workspace,
        sign_types=["factory"],
        build_type=constants.GENERIC_TYPE,
        uprev=True,
        overlays=constants.BOTH_OVERLAYS,
        push_overlays=constants.BOTH_OVERLAYS,
        useflags=config_lib.append_useflags(
            ["-cros-debug", "thinlto", "chrome_internal"]
        ),
        builder_class_name="workspace_builders.FactoryBranchBuilder",
        build_timeout=_FACTORYBRANCH_TIMEOUT,
        description="TOT builder to build a factory branch.",
        doc="https://goto.google.com/tot-for-firmware-branches",
    )

    for active, branch, boards in branch_builders:
        schedule = {}
        if active:
            schedule = {
                "schedule": active,
            }

        # Define the buildspec builder for the branch.
        branch_master = site_config.Add(
            "%s-buildspec" % branch,
            site_config.templates.buildspec,
            display_label=config_lib.DISPLAY_LABEL_FACTORY,
            workspace_branch=branch,
            build_timeout=_FACTORYBRANCH_TIMEOUT,
            **schedule,
        )

        # Define the per-board builders for the branch.
        for board in boards:
            child = site_config.Add(
                "%s-%s-factorybranch" % (board, branch),
                site_config.templates.factorybranch,
                boards=[board],
                workspace_branch=branch,
            )
            branch_master.AddSlave(child)


def ReleaseBuilders(site_config, boards_dict, ge_build_config):
    """Create all release builders.

    Args:
        site_config: config_lib.SiteConfig to be modified by adding templates
            and configs.
        boards_dict: A dict mapping board types to board name collections.
        ge_build_config: Dictionary containing the decoded GE configuration
            file.
    """
    board_configs = CreateInternalBoardConfigs(
        site_config, boards_dict, ge_build_config
    )

    def _CreateMasterConfig(
        name, template=site_config.templates.release, schedule="  0 12 * * *"
    ):
        return site_config.Add(
            name,
            template,
            boards=[],
            master=True,
            slave_configs=[],
            # Because PST is 8 hours from UTC, these times are the same in both.
            # But daylight savings time is NOT adjusted for
            schedule=schedule,
        )

    ### Master release configs.
    master_config = _CreateMasterConfig("master-release")

    def _AssignToMaster(config):
        """Add |config| as a slave config to the appropriate master config."""
        # Default to chromeos master release builder.
        master_config.AddSlave(config)

    ### Release configs.

    # Used for future bvt migration.
    _release_experimental_boards = _frozen_ge_set(
        ge_build_config,
        [
            "elm-kernelnext",
            "grunt-kernelnext",
            "hana-kernelnext",
            "hatch-kernelnext",
            "volteer-kernelnext",
            "zork-kernelnext",
        ],
    )

    _release_enable_skylab_hwtest = _frozen_ge_set(
        ge_build_config,
        [
            "asuka",
            "coral",
            "nyan_blaze",
            "reef",
        ],
    )

    _release_enable_skylab_partial_boards = {
        "coral": ["astronaut", "nasher", "lava"],
    }

    _release_enable_skylab_cts_hwtest = _frozen_ge_set(
        ge_build_config,
        [
            "terra",
        ],
    )

    _no_unittest_configs = [
        "grunt-kernelnext-release",
        "guybrush-kernelnext-release",
        "zork-connectivitynext-release",
        "zork-minios-release",
    ]

    def _get_skylab_settings(board_name):
        """Get skylab settings for release builder.

        Args:
            board_name: A string board name.

        Returns:
            A dict mapping suite types to booleans indicating whether this suite
            on this board is to be run on Skylab. Current suite types:
                - cts: all suites using pool:cts,
                - default: the rest of the suites.
        """
        return {
            "cts": board_name in _release_enable_skylab_cts_hwtest,
            "default": board_name in _release_enable_skylab_hwtest,
        }

    builder_to_boards_dict = config_lib.GroupBoardsByBuilder(
        ge_build_config[config_lib.CONFIG_TEMPLATE_BOARDS]
    )

    _all_release_builder_boards = builder_to_boards_dict[
        config_lib.CONFIG_TEMPLATE_RELEASE
    ]

    for unibuild in config_lib.GetUnifiedBuildConfigAllBuilds(ge_build_config):
        reference_board_name = unibuild[
            config_lib.CONFIG_TEMPLATE_REFERENCE_BOARD_NAME
        ]
        if reference_board_name != "eve":
            continue

        config_name = "%s-release" % reference_board_name

        # Move unibuild to skylab.
        important = not unibuild[config_lib.CONFIG_TEMPLATE_EXPERIMENTAL]
        if reference_board_name in _release_experimental_boards:
            important = False

        props = {
            "important": important,
        }
        if config_name in _no_unittest_configs:
            props["unittests"] = False
        site_config.AddForBoards(
            config_lib.CONFIG_TYPE_RELEASE,
            [reference_board_name],
            board_configs,
            site_config.templates.release,
            **props,
        )
        _AssignToMaster(site_config[config_name])

    def GetReleaseConfigName(board):
        """Convert a board name into a release config name."""
        return "%s-release" % board

    def GetConfigName(builder, board):
        """Convert a board name into a config name."""
        if builder == config_lib.CONFIG_TEMPLATE_RELEASE:
            return GetReleaseConfigName(board)
        else:
            # Currently just support RELEASE builders
            raise Exception("Do not support other builders.")

    def _GetConfigValues(board):
        """Get and return config values from template and user definitions."""
        important = not board[config_lib.CONFIG_TEMPLATE_EXPERIMENTAL]
        if board["name"] in _release_experimental_boards:
            important = False

        # Move non-unibuild to skylab.
        config_values = {
            "important": important,
        }

        return config_values

    def _AdjustUngroupedReleaseConfigs(builder_ungrouped_dict):
        """Adjust for ungrouped release boards"""
        for builder in builder_ungrouped_dict:
            for board in builder_ungrouped_dict[builder]:
                config_name = GetConfigName(
                    builder, board[config_lib.CONFIG_TEMPLATE_NAME]
                )
                site_config[config_name].apply(
                    _GetConfigValues(board),
                )
                _AssignToMaster(site_config[config_name])

    def _AdjustGroupedReleaseConfigs(builder_group_dict):
        """Adjust leader and follower configs for grouped boards"""
        for builder in builder_group_dict:
            for group in builder_group_dict[builder]:
                board_group = builder_group_dict[builder][group]

                # Leaders are built on baremetal builders and run all tests
                # needed by the related boards.
                for board in board_group.leader_boards:
                    config_name = GetConfigName(
                        builder, board[config_lib.CONFIG_TEMPLATE_NAME]
                    )
                    site_config[config_name].apply(
                        _GetConfigValues(board),
                    )
                    _AssignToMaster(site_config[config_name])

                # Followers are built on GCE instances, and turn off testing
                # that breaks on GCE. The missing tests run on the leader board.
                for board in board_group.follower_boards:
                    config_name = GetConfigName(
                        builder, board[config_lib.CONFIG_TEMPLATE_NAME]
                    )
                    site_config[config_name].apply(
                        _GetConfigValues(board),
                    )
                    _AssignToMaster(site_config[config_name])


def SpecialtyBuilders(site_config):
    """Add a variety of specialized builders or tryjobs.

    Args:
        site_config: config_lib.SiteConfig to be modified by adding templates
            and configs.
    """
    site_config.AddWithoutTemplate(
        "success-build",
        site_config.templates.external,
        boards=[],
        display_label=config_lib.DISPLAY_LABEL_TRYJOB,
        luci_builder=config_lib.LUCI_BUILDER_TRY,
        builder_class_name="test_builders.SucessBuilder",
        description="Builder always passes as quickly as possible.",
    )

    # Used by cbuildbot/stages/sync_stages_unittest
    site_config.AddWithoutTemplate(
        "sync-test-cbuildbot",
        boards=[],
        display_label=config_lib.DISPLAY_LABEL_TRYJOB,
        luci_builder=config_lib.LUCI_BUILDER_INFRA,
        builder_class_name="test_builders.SucessBuilder",
        description="Used by sync_stages_unittest.",
    )

    site_config.AddWithoutTemplate(
        "fail-build",
        site_config.templates.external,
        boards=[],
        display_label=config_lib.DISPLAY_LABEL_TRYJOB,
        luci_builder=config_lib.LUCI_BUILDER_TRY,
        builder_class_name="test_builders.FailBuilder",
        description="Builder always fails as quickly as possible.",
    )

    site_config.AddWithoutTemplate(
        "config-updater",
        site_config.templates.internal,
        site_config.templates.infra_builder,
        display_label=config_lib.DISPLAY_LABEL_UTILITY,
        description=(
            "Build Config Updater reads updated GE config files from"
            " GS, and commits them to chromite after running tests."
        ),
        build_type=constants.GENERIC_TYPE,
        build_timeout=2 * 60 * 60,
        boards=[],
        builder_class_name="config_builders.UpdateConfigBuilder",
        schedule="@hourly",
    )

    site_config.AddWithoutTemplate(
        "luci-scheduler-updater",
        site_config.templates.internal,
        site_config.templates.infra_builder,
        display_label=config_lib.DISPLAY_LABEL_UTILITY,
        description="Deploy changes to luci_scheduler.cfg.",
        build_type=constants.GENERIC_TYPE,
        boards=[],
        builder_class_name="config_builders.LuciSchedulerBuilder",
        schedule="triggered",
        triggered_gitiles=[
            [
                "https://chromium.googlesource.com/chromiumos/chromite",
                ["refs/heads/main"],
                ["config/luci-scheduler.cfg"],
            ],
            [
                (
                    "https://chrome-internal.googlesource.com/chromeos/infra/"
                    "config"
                ),
                ["refs/heads/main"],
                ["generated/luci-scheduler.cfg"],
            ],
        ],
    )


def TryjobMirrors(site_config):
    """Create tryjob specialized variants of every build config.

    This creates a new 'tryjob' config for every existing config, unless the
    existing config is already a tryjob config.

    Args:
        site_config: config_lib.SiteConfig to be modified by adding templates
            and configs.
    """
    tryjob_configs = {}

    for build_name, config in site_config.items():
        # Don't mirror builds that are already tryjob safe.
        if config_lib.isTryjobConfig(config):
            continue

        tryjob_name = build_name + "-tryjob"

        # Don't overwrite mirrored versions that were explicitly created
        # earlier.
        if tryjob_name in site_config:
            continue

        tryjob_config = copy.deepcopy(config)
        tryjob_config.apply(
            name=tryjob_name,
            display_label=config_lib.DISPLAY_LABEL_TRYJOB,
            luci_builder=config_lib.LUCI_BUILDER_TRY,
            # Generally make tryjobs safer.
            chroot_replace=True,
            debug=True,
            push_image=False,
            # Force uprev. This is so patched in changes are always built.
            uprev=True,
            gs_path=config_lib.GS_PATH_DEFAULT,
            schedule=None,
            suite_scheduling=False,
            triggered_gitiles=None,
            important=True,
        )

        # Force uprev. This is so patched in changes are always built.
        if tryjob_config.internal:
            tryjob_config.apply(overlays=constants.BOTH_OVERLAYS)

        if tryjob_config.master:
            tryjob_config.apply(debug_cidb=True)

        if tryjob_config.slave_configs:
            new_children = []
            for c in tryjob_config.slave_configs:
                if not config_lib.isTryjobConfig(site_config[c]):
                    c = "%s-tryjob" % c
                new_children.append(c)

            tryjob_config.apply(slave_configs=new_children)

        # Save off the new config so we can insert into site_config.
        tryjob_configs[tryjob_name] = tryjob_config

    for tryjob_name, tryjob_config in tryjob_configs.items():
        site_config[tryjob_name] = tryjob_config


@memoize.Memoize
def GetConfig():
    """Create the Site configuration for all ChromeOS builds.

    Returns:
        A config_lib.SiteConfig.
    """
    defaults = DefaultSettings()

    ge_build_config = config_lib.LoadGEBuildConfigFromFile()
    boards_dict = GetBoardTypeToBoardsDict(ge_build_config)

    # If there are unknown boards in the GE config, issue a warning and ignore
    # them.
    unknown = boards_dict["unknown_boards"]
    if unknown:
        logging.warning(
            "dropping unknown boards from GE config: %s",
            " ".join(x for x in unknown),
        )
        ge_build_config["boards"] = [
            x for x in ge_build_config["boards"] if x["name"] not in unknown
        ]
        boards_dict = GetBoardTypeToBoardsDict(ge_build_config)

    # site_config with no templates or build configurations.
    site_config = config_lib.SiteConfig(defaults=defaults)

    GeneralTemplates(site_config)

    ReleaseBuilders(site_config, boards_dict, ge_build_config)

    SpecialtyBuilders(site_config)

    FactoryBuilders(site_config, boards_dict, ge_build_config)

    FullBuilders(site_config, boards_dict, ge_build_config)

    TryjobMirrors(site_config)

    return site_config
