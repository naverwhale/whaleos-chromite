# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Configuration options for various cbuildbot builders."""

import copy
import itertools
import json
import os

from chromite.lib import constants
from chromite.lib import osutils
from chromite.utils import memoize
from chromite.utils import pformat


GS_PATH_DEFAULT = "default"  # Means gs://chromeos-image-archive/ + bot_id

# Contains the valid build config suffixes.
CONFIG_TYPE_RELEASE = "release"
CONFIG_TYPE_FULL = "full"
CONFIG_TYPE_FACTORY = "factory"
CONFIG_TYPE_PUBLIC = "public"

# DISPLAY labels are used to group related builds together in the GE UI.

DISPLAY_LABEL_TRYJOB = "tryjob"
DISPLAY_LABEL_INCREMENATAL = "incremental"
DISPLAY_LABEL_FULL = "full"
DISPLAY_LABEL_CHROME_INFORMATIONAL = "chrome_informational"
DISPLAY_LABEL_INFORMATIONAL = "informational"
DISPLAY_LABEL_RELEASE = "release"
DISPLAY_LABEL_CHROME_PFQ = "chrome_pfq"
DISPLAY_LABEL_MST_ANDROID_PFQ = "mst_android_pfq"
DISPLAY_LABEL_PI_ANDROID_PFQ = "pi_android_pfq"
DISPLAY_LABEL_QT_ANDROID_PFQ = "qt_android_pfq"
DISPLAY_LABEL_RVC_ANDROID_PFQ = "rvc_android_pfq"
DISPLAY_LABEL_VMRVC_ANDROID_PFQ = "vmrvc_android_pfq"
DISPLAY_LABEL_VMSC_ANDROID_PFQ = "vmsc_android_pfq"
DISPLAY_LABEL_VMT_ANDROID_PFQ = "vmt_android_pfq"
DISPLAY_LABEL_FACTORY = "factory"
DISPLAY_LABEL_TOOLCHAIN = "toolchain"
DISPLAY_LABEL_UTILITY = "utility"
DISPLAY_LABEL_PRODUCTION_TRYJOB = "production_tryjob"

# This list of constants should be kept in sync with GoldenEye code.
ALL_DISPLAY_LABEL = {
    DISPLAY_LABEL_TRYJOB,
    DISPLAY_LABEL_INCREMENATAL,
    DISPLAY_LABEL_FULL,
    DISPLAY_LABEL_CHROME_INFORMATIONAL,
    DISPLAY_LABEL_INFORMATIONAL,
    DISPLAY_LABEL_RELEASE,
    DISPLAY_LABEL_CHROME_PFQ,
    DISPLAY_LABEL_MST_ANDROID_PFQ,
    DISPLAY_LABEL_PI_ANDROID_PFQ,
    DISPLAY_LABEL_QT_ANDROID_PFQ,
    DISPLAY_LABEL_RVC_ANDROID_PFQ,
    DISPLAY_LABEL_VMRVC_ANDROID_PFQ,
    DISPLAY_LABEL_VMSC_ANDROID_PFQ,
    DISPLAY_LABEL_VMT_ANDROID_PFQ,
    DISPLAY_LABEL_FACTORY,
    DISPLAY_LABEL_TOOLCHAIN,
    DISPLAY_LABEL_UTILITY,
    DISPLAY_LABEL_PRODUCTION_TRYJOB,
}

# These values must be kept in sync with the ChromeOS LUCI builders.
#
# https://chrome-internal.googlesource.com/chromeos/infra/config/+/HEAD/luci/cr-buildbucket.cfg
LUCI_BUILDER_FACTORY = "Factory"
LUCI_BUILDER_FULL = "Full"
LUCI_BUILDER_INCREMENTAL = "Incremental"
LUCI_BUILDER_INFORMATIONAL = "Informational"
LUCI_BUILDER_INFRA = "Infra"
LUCI_BUILDER_LEGACY_RELEASE = "LegacyRelease"
LUCI_BUILDER_PFQ = "PFQ"
LUCI_BUILDER_RAPID = "Rapid"
LUCI_BUILDER_RELEASE = "Release"
LUCI_BUILDER_STAGING = "Staging"
LUCI_BUILDER_TRY = "Try"

ALL_LUCI_BUILDER = {
    LUCI_BUILDER_FACTORY,
    LUCI_BUILDER_FULL,
    LUCI_BUILDER_INCREMENTAL,
    LUCI_BUILDER_INFORMATIONAL,
    LUCI_BUILDER_INFRA,
    LUCI_BUILDER_LEGACY_RELEASE,
    LUCI_BUILDER_PFQ,
    LUCI_BUILDER_RAPID,
    LUCI_BUILDER_RELEASE,
    LUCI_BUILDER_STAGING,
    LUCI_BUILDER_TRY,
}

GOLDENEYE_IGNORED_BOARDS = [
    "capri",
    "capri-zfpga",
    "cobblepot",
    "gonzo",
    "lakitu",
    "lasilla-ground",
    "lasilla-sky",
    "macchiato-ground",
    "octavius",
    "romer",
    "wooten",
]


def isTryjobConfig(build_config):
    """Is a given build config a tryjob config, or a production config?

    Args:
        build_config: A fully populated instance of BuildConfig.

    Returns:
        Boolean. True if it's a tryjob config.
    """
    return build_config.luci_builder in [LUCI_BUILDER_RAPID, LUCI_BUILDER_TRY]


# In the Json, this special build config holds the default values for all
# other configs.
DEFAULT_BUILD_CONFIG = "_default"

# Constants for config template file
CONFIG_TEMPLATE_BOARDS = "boards"
CONFIG_TEMPLATE_NAME = "name"
CONFIG_TEMPLATE_EXPERIMENTAL = "experimental"
CONFIG_TEMPLATE_BUILDER = "builder"
CONFIG_TEMPLATE_RELEASE = "RELEASE"
CONFIG_TEMPLATE_CONFIGS = "configs"
CONFIG_TEMPLATE_ARCH = "arch"
CONFIG_TEMPLATE_REFERENCE_BOARD_NAME = "reference_board_name"

CONFIG_X86_INTERNAL = "X86_INTERNAL"
CONFIG_X86_EXTERNAL = "X86_EXTERNAL"
CONFIG_ARM_INTERNAL = "ARM_INTERNAL"
CONFIG_ARM_EXTERNAL = "ARM_EXTERNAL"


def IsCanaryMaster(builder_run):
    """Returns True if this build type is master-release"""
    return (
        builder_run.config.build_type == constants.CANARY_TYPE
        and builder_run.config.master
        and builder_run.manifest_branch in ("main", "master")
    )


def IsPFQType(b_type):
    """Returns True if this build type is a PFQ."""
    return b_type in (constants.PFQ_TYPE,)


def IsCanaryType(b_type):
    """Returns True if this build type is a Canary."""
    return b_type == constants.CANARY_TYPE


class AttrDict(dict):
    """Dictionary with 'attribute' access.

    This is identical to a dictionary, except that string keys can be addressed
    as read-only attributes.
    """

    def __getattr__(self, name):
        """Support attribute-like access to each dict entry."""
        if name in self:
            return self[name]

        # Super class (dict) has no __getattr__ method, so use __getattribute__.
        return super().__getattribute__(name)


class BuildConfig(AttrDict):
    """Dictionary of explicit configuration settings for a cbuildbot config

    Each dictionary entry is in turn a dictionary of config_param->value.

    See DefaultSettings for details on known configurations, and their
    documentation.
    """

    def deepcopy(self):
        """Create a deep copy of this object.

        This is a specialized version of copy.deepcopy() for BuildConfig
        objects. It speeds up deep copies by 10x because we know in advance what
        is stored inside a BuildConfig object and don't have to do as much
        introspection. This function is called a lot during setup of the config
        objects so optimizing it makes a big difference. (It saves seconds off
        the load time of this module!)
        """
        result = BuildConfig(self)

        # Here is where we handle all values that need deepcopy instead of
        # shallow.
        for k, v in result.items():
            if v is not None:
                # type(v) is faster than isinstance.
                if type(v) is list:  # pylint: disable=unidiomatic-typecheck
                    result[k] = v[:]

        return result

    def apply(self, *args, **kwargs):
        """Apply changes to this BuildConfig.

        Note: If an override is callable, it will be called and passed the prior
        value for the given key (or None) to compute the new value.

        Args:
            *args: Dictionaries or templates to update this config with.
            **kwargs: Settings to inject; see DefaultSettings for valid values.

        Returns:
            self after changes are applied.
        """
        inherits = list(args)
        inherits.append(kwargs)

        for update_config in inherits:
            for name, value in update_config.items():
                if callable(value):
                    # If we are applying to a fixed value, we resolve to a fixed
                    # value. Otherwise, we save off a callable to apply later,
                    # perhaps with nested callables (IE: we curry them). This
                    # allows us to use callables in templates, and apply
                    # templates to each other and still get the expected result
                    # when we use them later on.
                    #
                    # Delaying the resolution of callables is safe, because
                    # "Add()" always applies against the default, which has
                    # fixed values for everything.

                    if name in self:
                        # apply it to the current value.
                        if callable(self[name]):
                            # If we have no fixed value to resolve with, stack
                            # the callables.
                            def stack(new_callable, old_callable):
                                """Helper to isolate namespace for closure."""
                                return lambda fixed: new_callable(
                                    old_callable(fixed)
                                )

                            self[name] = stack(value, self[name])
                        else:
                            # If the current value was a fixed value, apply the
                            # callable.
                            self[name] = value(self[name])
                    else:
                        # If we had no value to apply it to, save it for later.
                        self[name] = value

                elif name == "_template":
                    # We never apply _template. You have to set it through Add.
                    pass

                else:
                    # Simple values overwrite whatever we do or don't have.
                    self[name] = value

        return self

    def derive(self, *args, **kwargs):
        """Create a new config derived from this one.

        Note: If an override is callable, it will be called and passed the prior
        value for the given key (or None) to compute the new value.

        Args:
            *args: Mapping instances to mixin.
            **kwargs: Settings to inject; see DefaultSettings for valid values.

        Returns:
            A new _config instance.
        """
        return self.deepcopy().apply(*args, **kwargs)

    def AddSlave(self, slave):
        """Assign slave config(s) to a build master.

        A helper for adding slave configs to a master config.
        """
        assert self.master
        if self["slave_configs"] is None:
            self["slave_configs"] = []
        self.slave_configs.append(slave.name)
        self.slave_configs.sort()

    def AddSlaves(self, slaves):
        """Assign slave config(s) to a build master.

        A helper for adding slave configs to a master config.
        """
        assert self.master
        if self["slave_configs"] is None:
            self["slave_configs"] = []
        self.slave_configs.extend(slave_config.name for slave_config in slaves)
        self.slave_configs.sort()


def DefaultSettings():
    # Enumeration of valid settings; any/all config settings must be in this.
    # All settings must be documented.
    return dict(
        # The name of the template we inherit settings from.
        _template=None,
        # The name of the config.
        name=None,
        # A list of boards to build.
        boards=None,
        # This value defines what part of the Golden Eye UI is responsible for
        # displaying builds of this build config. The value is required, and
        # must be in ALL_DISPLAY_LABEL.
        # TODO: Make the value required after crbug.com/776955 is finished.
        display_label=None,
        # This defines which LUCI Builder to use. It must match an entry in:
        #
        # https://chrome-internal.git.corp.google.com/chromeos/
        #    manifest-internal/+/infra/config/cr-buildbucket.cfg
        #
        luci_builder=LUCI_BUILDER_LEGACY_RELEASE,
        # The profile of the variant to set up and build.
        profile=None,
        # This bot pushes changes to the overlays.
        master=False,
        # If this bot triggers slave builds, this will contain a list of
        # slave config names.
        slave_configs=None,
        # If False, this flag indicates that the CQ should not check whether
        # this bot passed or failed. Set this to False if you are setting up a
        # new bot. Once the bot is on the waterfall and is consistently green,
        # mark the builder as important=True.
        important=True,
        # If True, build config should always be run as if --debug was set
        # on the cbuildbot command line. This is different from 'important'
        # and is usually correlated with tryjob build configs.
        debug=False,
        # If True, use the debug instance of CIDB instead of prod.
        debug_cidb=False,
        # Timeout for the build as a whole (in seconds).
        build_timeout=(5 * 60 + 30) * 60,
        # Whether this is an internal build config.
        internal=False,
        # Whether this is a branched build config. Used for pfq logic.
        branch=False,
        # The name of the manifest to use. E.g., to use the buildtools manifest,
        # specify 'buildtools'.
        manifest=constants.DEFAULT_MANIFEST,
        # emerge use flags to use while setting up the board, building packages,
        # making images, etc.
        useflags=[],
        # Set the variable CHROMEOS_OFFICIAL for the build. Known to affect
        # parallel_emerge, cros_set_lsb_release, and chromeos_version.sh. See
        # bug chromium-os:14649
        chromeos_official=False,
        # Use binary packages for build_packages and setup_board.
        usepkg_build_packages=True,
        # Does this profile need to sync chrome?  If None, we guess based on
        # other factors.  If True/False, we always do that.
        sync_chrome=None,
        # Use the newest ebuilds for all the toolchain packages.
        latest_toolchain=False,
        # Wipe and replace the board inside the chroot.
        board_replace=False,
        # Wipe and replace chroot, but not source.
        chroot_replace=True,
        # Uprevs the local ebuilds to build new changes since last stable.
        # build.  If master then also pushes these changes on success. Note that
        # we uprev on just about every bot config because it gives us a more
        # deterministic build system (the tradeoff being that some bots build
        # from source more frequently than if they never did an uprev). This way
        # the release/factory/etc... builders will pick up changes that devs
        # pushed before it runs, but after the correspoding PFQ bot ran (which
        # is what creates+uploads binpkgs).  The incremental bots are about the
        # only ones that don't uprev because they mimic the flow a developer
        # goes through on their own local systems.
        uprev=True,
        # Select what overlays to look at for revving and prebuilts. This can be
        # any constants.VALID_OVERLAYS.
        overlays=constants.PUBLIC_OVERLAYS,
        # Select what overlays to push at. This should be a subset of overlays
        # for the particular builder.  Must be None if not a master.  There
        # should only be one master bot pushing changes to each overlay per
        # branch.
        push_overlays=None,
        # Uprev Chrome, values of 'tot', 'stable_release', or None.
        chrome_rev=None,
        # Runs unittests for packages.
        unittests=True,
        # If true, uploads artifacts for hw testing. Upload payloads for test
        # image if the image is built. If not, dev image is used and then base
        # image.
        upload_hw_test_artifacts=True,
        # If true, uploads individual image tarballs.
        upload_standalone_images=True,
        # Whether to run BuildConfigsExport stage. This stage generates build
        # configs (see crbug.com/974795 project). Only release builders should
        # run this stage.
        run_build_configs_export=False,
        # List of patterns for portage packages for which stripped binpackages
        # should be uploaded to GS. The patterns are used to search for packages
        # via `equery list`.
        upload_stripped_packages=[
            # Used by SimpleChrome workflow.
            "chromeos-base/chromeos-chrome",
            "sys-kernel/*kernel*",
        ],
        # Google Storage path to offload files to.
        #   None - No upload
        #   GS_PATH_DEFAULT - 'gs://chromeos-image-archive/' + bot_id
        #   value - Upload to explicit path
        gs_path=GS_PATH_DEFAULT,
        # TODO(sosa): Deprecate binary.
        # Type of builder.  Check constants.VALID_BUILD_TYPES.
        build_type=constants.PFQ_TYPE,
        # Whether to schedule test suites by suite_scheduler. Generally only
        # True for "release" builders.
        suite_scheduling=False,
        # The class name used to build this config.  See the modules in
        # cbuildbot / builders/*_builders.py for possible values.  This should
        # be the name in string form -- e.g. "simple_builders.SimpleBuilder" to
        # get the SimpleBuilder class in the simple_builders module.  If not
        # specified, we'll fallback to legacy probing behavior until everyone
        # has been converted (see the scripts/cbuildbot.py file for details).
        builder_class_name=None,
        # List of images we want to build -- see `cros build-image --help`.
        images=["test"],
        # Whether to build a netboot image.
        factory_install_netboot=True,
        # Whether to build the factory toolkit.
        factory_toolkit=True,
        # Whether to build factory packages in BuildPackages.
        factory=True,
        # Flag to control if all packages for the target are built. If disabled
        # and unittests are enabled, the unit tests and their dependencies
        # will still be built during the testing stage.
        build_packages=True,
        # Tuple of specific packages we want to build.  Most configs won't
        # specify anything here and instead let build_packages calculate.
        packages=[],
        # Do we push a final release image to chromeos-images.
        push_image=False,
        # Do we upload debug symbols.
        upload_symbols=False,
        # Run a stage that generates and uploads debug symbols.
        debug_symbols=True,
        # Include *.debug files for debugging core files with gdb in debug.tgz.
        # These are very large. This option only has an effect if debug_symbols
        # and archive are set.
        archive_build_debug=False,
        # Run a stage that archives build and test artifacts for developer
        # consumption.
        archive=True,
        # Git repository URL for our manifests.
        #  https://chromium.googlesource.com/chromiumos/manifest
        #  https://chrome-internal.googlesource.com/chromeos/manifest-internal
        manifest_repo_url=None,
        # Whether we are using the manifest_version repo that stores per-build
        # manifests.
        manifest_version=False,
        # Use a different branch of the project manifest for the build.
        manifest_branch=None,
        # Upload prebuilts for this build. Valid values are PUBLIC, PRIVATE, or
        # False.
        prebuilts=False,
        # Use SDK as opposed to building the chroot from source.
        use_sdk=True,
        # The description string to print out for config when user runs --list.
        description=None,
        # Boolean that enables parameter --git-sync for upload_prebuilts.
        git_sync=False,
        # Whether this config belongs to a config group.
        grouped=False,
        # If enabled, run the PatchChanges stage.  Enabled by default. Can be
        # overridden by the --nopatch flag.
        postsync_patch=True,
        # Reexec into the buildroot after syncing.  Enabled by default.
        postsync_reexec=True,
        # If specified, it is passed on to the PushImage script as
        # '--sign-types' commandline argument.  Must be either None or a list of
        # image types.
        sign_types=None,
        # TODO(sosa): Collapse to one option.
        # ========== Dev installer prebuilts options =======================
        # Upload prebuilts for this build to this bucket. If it equals None the
        # default buckets are used.
        binhost_bucket=None,
        # Parameter --key for upload_prebuilts. If it equals None, the default
        # values are used, which depend on the build type.
        binhost_key=None,
        # Parameter --binhost-base-url for upload_prebuilts. If it equals None,
        # the default value is used.
        binhost_base_url=None,
        # Enable rootfs verification on the image.
        rootfs_verification=True,
        # ==================================================================
        # Workspace related options.
        # Which branch should WorkspaceSyncStage checkout, if run.
        workspace_branch=None,
        # ==================================================================
        # The documentation associated with the config.
        doc=None,
        # This is a LUCI Scheduler schedule string. Setting this will create
        # a LUCI Scheduler for this build on swarming (not buildbot).
        # See: https://goo.gl/VxSzFf
        schedule=None,
        # This is the list of git repos which can trigger this build in
        # swarming. Implies that schedule is set, to "triggered".
        # The format is of the form:
        #   [ (<git repo url>, (<ref1>, <ref2>, …)),
        #    …]
        triggered_gitiles=None,
        # If true, skip package retries in BuildPackages step.
        nobuildretry=False,
    )


def GerritInstanceParameters(name, instance):
    param_names = [
        "_GOB_INSTANCE",
        "_GERRIT_INSTANCE",
        "_GOB_HOST",
        "_GERRIT_HOST",
        "_GOB_URL",
        "_GERRIT_URL",
    ]

    gob_instance = instance
    gerrit_instance = "%s-review" % instance
    gob_host = constants.GOB_HOST % gob_instance
    gerrit_host = constants.GOB_HOST % gerrit_instance
    gob_url = "https://%s" % gob_host
    gerrit_url = "https://%s" % gerrit_host

    params = [
        gob_instance,
        gerrit_instance,
        gob_host,
        gerrit_host,
        gob_url,
        gerrit_url,
    ]

    return {f"{name}{pn}": p for pn, p in zip(param_names, params)}


def DefaultSiteParameters():
    # Enumeration of valid site parameters; any/all site parameters must be
    # here. All site parameters should be documented.
    default_site_params = {}

    manifest_project = "chromiumos/manifest"
    manifest_int_project = "chromeos/manifest-internal"
    external_remote = "cros"
    internal_remote = "cros-internal"
    chromium_remote = "chromium"
    chrome_remote = "chrome"
    aosp_remote = "aosp"
    weave_remote = "weave"

    internal_change_prefix = "chrome-internal:"
    external_change_prefix = "chromium:"

    # Gerrit instance site parameters.
    default_site_params.update(GerritInstanceParameters("EXTERNAL", "chromium"))
    default_site_params.update(
        GerritInstanceParameters("INTERNAL", "chrome-internal")
    )
    default_site_params.update(GerritInstanceParameters("AOSP", "android"))
    default_site_params.update(GerritInstanceParameters("WEAVE", "weave"))

    default_site_params.update(
        # Parameters to define which manifests to use.
        MANIFEST_PROJECT=manifest_project,
        MANIFEST_INT_PROJECT=manifest_int_project,
        MANIFEST_PROJECTS=(manifest_project, manifest_int_project),
        MANIFEST_URL=os.path.join(
            default_site_params["EXTERNAL_GOB_URL"], manifest_project
        ),
        MANIFEST_INT_URL=os.path.join(
            default_site_params["INTERNAL_GERRIT_URL"], manifest_int_project
        ),
        # CrOS remotes specified in the manifests.
        EXTERNAL_REMOTE=external_remote,
        INTERNAL_REMOTE=internal_remote,
        GOB_REMOTES={
            default_site_params["EXTERNAL_GOB_INSTANCE"]: external_remote,
            default_site_params["INTERNAL_GOB_INSTANCE"]: internal_remote,
        },
        CHROMIUM_REMOTE=chromium_remote,
        CHROME_REMOTE=chrome_remote,
        AOSP_REMOTE=aosp_remote,
        WEAVE_REMOTE=weave_remote,
        # Only remotes listed in CROS_REMOTES are considered branchable.
        # CROS_REMOTES and BRANCHABLE_PROJECTS must be kept in sync.
        GERRIT_HOSTS={
            external_remote: default_site_params["EXTERNAL_GERRIT_HOST"],
            internal_remote: default_site_params["INTERNAL_GERRIT_HOST"],
            aosp_remote: default_site_params["AOSP_GERRIT_HOST"],
            weave_remote: default_site_params["WEAVE_GERRIT_HOST"],
        },
        CROS_REMOTES={
            external_remote: default_site_params["EXTERNAL_GOB_URL"],
            internal_remote: default_site_params["INTERNAL_GOB_URL"],
            aosp_remote: default_site_params["AOSP_GOB_URL"],
            weave_remote: default_site_params["WEAVE_GOB_URL"],
        },
        GIT_REMOTES={
            chromium_remote: default_site_params["EXTERNAL_GOB_URL"],
            chrome_remote: default_site_params["INTERNAL_GOB_URL"],
            external_remote: default_site_params["EXTERNAL_GOB_URL"],
            internal_remote: default_site_params["INTERNAL_GOB_URL"],
            aosp_remote: default_site_params["AOSP_GOB_URL"],
            weave_remote: default_site_params["WEAVE_GOB_URL"],
        },
        # Prefix to distinguish internal and external changes. This is used
        # when a user specifies a patch with "-g", when generating a key for
        # a patch to use in our PatchCache, and when displaying a custom
        # string for the patch.
        INTERNAL_CHANGE_PREFIX=internal_change_prefix,
        EXTERNAL_CHANGE_PREFIX=external_change_prefix,
        CHANGE_PREFIX={
            external_remote: external_change_prefix,
            internal_remote: internal_change_prefix,
        },
        # List of remotes that are okay to include in the external manifest.
        EXTERNAL_REMOTES=(
            external_remote,
            chromium_remote,
            aosp_remote,
            weave_remote,
        ),
        # Mapping 'remote name' -> regexp that matches names of repositories on
        # that remote that can be branched when creating CrOS branch. Branching
        # script will actually create a new git ref when branching these
        # projects. It won't attempt to create a git ref for other projects that
        # may be mentioned in a manifest. If a remote is missing from this
        # dictionary, all projects on that remote are considered to not be
        # branchable.
        BRANCHABLE_PROJECTS={
            external_remote: r"(chromiumos|aosp)/(.+)",
            internal_remote: r"chromeos/(.+)",
        },
        # Additional parameters used to filter manifests, create modified
        # manifests, and to branch manifests.
        MANIFEST_VERSIONS_GOB_URL=(
            "%s/chromiumos/manifest-versions"
            % default_site_params["EXTERNAL_GOB_URL"]
        ),
        MANIFEST_VERSIONS_INT_GOB_URL=(
            "%s/chromeos/manifest-versions"
            % default_site_params["INTERNAL_GOB_URL"]
        ),
        MANIFEST_VERSIONS_GS_URL="gs://chromeos-manifest-versions",
        # Standard directories under buildroot for cloning these repos.
        EXTERNAL_MANIFEST_VERSIONS_PATH="manifest-versions",
        INTERNAL_MANIFEST_VERSIONS_PATH="manifest-versions-internal",
        # GS URL in which to archive build artifacts.
        ARCHIVE_URL="gs://chromeos-image-archive",
    )

    return default_site_params


class SiteConfig(dict):
    """This holds a set of named BuildConfig values."""

    def __init__(self, defaults=None, templates=None):
        """Init.

        Args:
            defaults: Dictionary of key value pairs to use as BuildConfig
                values. All BuildConfig values should be defined here. If None,
                the DefaultSettings() is used. Most sites should use
                DefaultSettings(), and then update to add any site specific
                values needed.
            templates: Dictionary of template names to partial BuildConfigs
                other BuildConfigs can be based on. Mostly used to reduce
                verbosity of the config dump file format.
        """
        super().__init__()
        self._defaults = DefaultSettings()
        if defaults:
            self._defaults.update(defaults)
        self._templates = (
            AttrDict() if templates is None else AttrDict(templates)
        )

    def GetDefault(self):
        """Create the canonical default build configuration."""
        # Enumeration of valid settings; any/all config settings must be in
        # this. All settings must be documented.
        return BuildConfig(**self._defaults)

    def GetTemplates(self):
        """Get the templates of the build configs"""
        return self._templates

    @property
    def templates(self):
        return self._templates

    #
    # Methods for searching a SiteConfig's contents.
    #
    def GetBoards(self):
        """Return an iterable of all boards in the SiteConfig."""
        return set(
            itertools.chain.from_iterable(
                x.boards for x in self.values() if x.boards
            )
        )

    def FindFullConfigsForBoard(self, board=None):
        """Returns full builder configs for a board.

        Args:
            board: The board to match. By default, match all boards.

        Returns:
            A tuple containing a list of matching external configs and a list of
            matching internal release configs for a board.
        """
        ext_cfgs = []
        int_cfgs = []

        for name, c in self.items():
            possible_names = []
            if board:
                possible_names = [
                    board + "-" + CONFIG_TYPE_RELEASE,
                    board + "-" + CONFIG_TYPE_FULL,
                ]
            if c["boards"] and (
                board is None or board in c["boards"] or name in possible_names
            ):
                if name.endswith("-%s" % CONFIG_TYPE_RELEASE) and c["internal"]:
                    int_cfgs.append(c.deepcopy())
                elif (
                    name.endswith("-%s" % CONFIG_TYPE_FULL)
                    and not c["internal"]
                ):
                    ext_cfgs.append(c.deepcopy())

        return ext_cfgs, int_cfgs

    def FindCanonicalConfigForBoard(self, board, allow_internal=True):
        """Get the canonical cbuildbot builder config for a board."""
        ext_cfgs, int_cfgs = self.FindFullConfigsForBoard(board)
        # If both external and internal builds exist for this board, prefer the
        # internal one unless instructed otherwise.
        both = (int_cfgs if allow_internal else []) + ext_cfgs

        if not both:
            raise ValueError("Invalid board specified: %s." % board)
        return both[0]

    def GetSlaveConfigMapForMaster(
        self, master_config, options=None, important_only=True
    ):
        """Gets the slave builds triggered by a master config.

        If a master builder also performs a build, it can (incorrectly) return
        itself.

        Args:
            master_config: A build config for a master builder.
            options: The options passed on the commandline. This argument is
                required for normal operation, but we accept None to assist with
                testing.
            important_only: If True, only get the important slaves.

        Returns:
            A slave_name to slave_config map, corresponding to the slaves for
            the master represented by master_config.

        Raises:
            AssertionError if the given config is not a master config or it does
            not have a manifest_version.
        """
        assert master_config.master
        assert master_config.slave_configs is not None

        slave_name_config_map = {}
        if options is not None and options.remote_trybot:
            return {}

        # Look up the build configs for all slaves named by the master.
        slave_name_config_map = {
            name: self[name] for name in master_config.slave_configs
        }

        if important_only:
            # Remove unimportant configs from the result.
            slave_name_config_map = {
                k: v for k, v in slave_name_config_map.items() if v.important
            }

        return slave_name_config_map

    def GetSlavesForMaster(
        self, master_config, options=None, important_only=True
    ):
        """Get a list of qualified build slave configs given the master_config.

        Args:
            master_config: A build config for a master builder.
            options: The options passed on the commandline. This argument is
                optional, and only makes sense when called from cbuildbot.
            important_only: If True, only get the important slaves.
        """
        slave_map = self.GetSlaveConfigMapForMaster(
            master_config, options=options, important_only=important_only
        )
        return list(slave_map.values())

    #
    # Methods used when creating a Config programatically.
    #
    def Add(self, name, template=None, *args, **kwargs):
        """Add a new BuildConfig to the SiteConfig.

        Examples:
            # Creates default build named foo.
            site_config.Add('foo')

            # Creates default build with board 'foo_board'
            site_config.Add('foo', boards=['foo_board'])

            # Creates build based on template_build for 'foo_board'.
            site_config.Add(
                'foo', template_build, boards=['foo_board']
            )

            # Creates build based on template for 'foo_board'. with mixin.
            # Inheritance order is default, template, mixin, arguments.
            site_config.Add(
                'foo', template_build, mixin_build_config, boards=['foo_board']
            )

            # Creates build without a template but with mixin.
            # Inheritance order is default, template, mixin, arguments.
            site_config.Add(
                'foo', None, mixin_build_config, boards=['foo_board']
            )

        Args:
            name: The name to label this configuration; this is what cbuildbot
                would see.
            template: BuildConfig to use as a template for this build.
            *args: BuildConfigs to patch into this config. First one (if
                present) is considered the template. See AddTemplate for help on
                templates.
            **kwargs: BuildConfig values to explicitly set on this config.

        Returns:
            The BuildConfig just added to the SiteConfig.
        """
        assert name not in self, "%s already exists." % name

        inherits, overrides = args, kwargs
        if template:
            inherits = (template,) + inherits

        # Make sure we don't ignore that argument silently.
        if "_template" in overrides:
            raise ValueError("_template cannot be explicitly set.")

        result = self.GetDefault()
        result.apply(*inherits, **overrides)

        # Select the template name based on template argument, or nothing.
        resolved_template = template.get("_template") if template else None
        assert (
            not resolved_template or resolved_template in self.templates
        ), "%s inherits from non-template %s" % (name, resolved_template)

        # Our name is passed as an explicit argument. We use the first build
        # config as our template, or nothing.
        result["name"] = name
        result["_template"] = resolved_template
        self[name] = result
        return result

    def AddWithoutTemplate(self, name, *args, **kwargs):
        """Add config containing only explicitly listed values (no defaults)."""
        self.Add(name, None, *args, **kwargs)

    def AddForBoards(
        self, suffix, boards, per_board=None, template=None, *args, **kwargs
    ):
        """Create configs for all boards in |boards|.

        Args:
            suffix: Config name is <board>-<suffix>.
            boards: A list of board names as strings.
            per_board: A dictionary of board names to BuildConfigs, or None.
            template: The template to use for all configs created.
            *args: Mixin templates to apply.
            **kwargs: Additional keyword arguments to be used in AddConfig.

        Returns:
            List of the configs created.
        """
        result = []

        for board in boards:
            config_name = "%s-%s" % (board, suffix)

            # Insert the per_board value as the last mixin, if it exists.
            mixins = args + (dict(boards=[board]),)
            if per_board and board in per_board:
                mixins = mixins + (per_board[board],)

            # Create the new config for this board.
            result.append(self.Add(config_name, template, *mixins, **kwargs))

        return result

    def ApplyForBoards(self, suffix, boards, *args, **kwargs):
        """Update configs for all boards in |boards|.

        Args:
            suffix: Config name is <board>-<suffix>.
            boards: A list of board names as strings.
            *args: Mixin templates to apply.
            **kwargs: Additional keyword arguments to be used in AddConfig.

        Returns:
            List of the configs updated.
        """
        result = []

        for board in boards:
            config_name = "%s-%s" % (board, suffix)
            assert config_name in self, "%s does not exist." % config_name

            # Update the config for this board.
            result.append(self[config_name].apply(*args, **kwargs))

        return result

    def AddTemplate(self, name, *args, **kwargs):
        """Create a template named |name|.

        Templates are used to define common settings that are shared across
        types of builders. They help reduce duplication in config_dump.json,
        because we only define the template and its settings once.

        Args:
            name: The name of the template.
            *args: See the docstring of BuildConfig.derive.
            **kwargs: See the docstring of BuildConfig.derive.
        """
        assert name not in self._templates, "Template %s already exists." % name

        template = BuildConfig()
        template.apply(*args, **kwargs)
        template["_template"] = name
        self._templates[name] = template

        return template

    def _MarshalBuildConfig(self, name, config):
        """Hide the defaults from a given config entry.

        Args:
            name: Default build name (usually dictionary key).
            config: A config entry.

        Returns:
            The same config entry, but without any defaults.
        """
        defaults = self.GetDefault()
        defaults["name"] = name

        template = config.get("_template")
        if template:
            defaults.apply(self._templates[template])
            defaults["_template"] = None

        result = {}
        for k, v in config.items():
            if defaults.get(k) != v:
                result[k] = v

        return result

    def _MarshalTemplates(self) -> dict:
        """Return a version of self._templates with only used templates.

        Templates have callables/delete keys resolved against GetDefault() to
        ensure they can be safely saved to json.

        Returns:
            Dict copy of self._templates with all unreferenced templates
            removed.
        """
        defaults = self.GetDefault()

        # All templates used. We ignore child configs since they
        # should exist at top level.
        used = set(c.get("_template", None) for c in self.values())
        used.discard(None)

        result = {}

        for name in used:
            # Expand any special values (callables, etc)
            expanded = defaults.derive(self._templates[name])
            # Recover the '_template' value which is filtered out by derive.
            expanded["_template"] = name
            # Hide anything that matches the default.
            save = {k: v for k, v in expanded.items() if defaults.get(k) != v}
            result[name] = save

        return result

    def SaveConfigToString(self):
        """Save this Config object to a Json format string."""
        default = self.GetDefault()

        config_dict = {}
        config_dict["_default"] = default
        config_dict["_templates"] = self._MarshalTemplates()
        for k, v in self.items():
            config_dict[k] = self._MarshalBuildConfig(k, v)

        return PrettyJsonDict(config_dict)

    def SaveConfigToFile(self, config_file):
        """Save this Config to a Json file.

        Args:
            config_file: The file to write too.
        """
        json_string = self.SaveConfigToString()
        osutils.WriteFile(config_file, json_string)

    def DumpExpandedConfigToString(self):
        """Dump the SiteConfig to Json with all configs full expanded.

        This is intended for debugging default/template behavior. The dumped
        JSON can't be reloaded (at least not reliably).
        """
        return PrettyJsonDict(self)

    def DumpConfigCsv(self):
        """Dump the SiteConfig to CSV with all configs fully expanded.

        This supports configuration analysis and debugging.
        """
        raw_config = json.loads(self.DumpExpandedConfigToString())
        header_keys = {"builder_name", "test_type", "device"}
        csv_rows = []
        for builder_name, values in raw_config.items():
            row = {"builder_name": builder_name}
            tests = {}
            raw_devices = []
            for key, value in values.items():
                header_keys.add(key)
                if value:
                    if isinstance(value, list):
                        if "_tests" in key:
                            tests[key] = value
                        elif key == "models":
                            raw_devices = value
                        else:
                            row[key] = " | ".join(
                                str(array_val) for array_val in value
                            )
                    else:
                        row[key] = value

            if tests:
                for test_type, test_entries in tests.items():
                    for test_entry in test_entries:
                        test_row = copy.deepcopy(row)
                        test_row["test_type"] = test_type
                        raw_test = json.loads(test_entry)
                        for test_key, test_value in raw_test.items():
                            if test_value:
                                header_keys.add(test_key)
                                test_row[test_key] = test_value
                        csv_rows.append(test_row)
                        if raw_devices:
                            for raw_device in raw_devices:
                                device = json.loads(raw_device)
                                test_suite = test_row.get("suite", "")
                                test_suites = device.get("test_suites", [])
                                if (
                                    test_suite
                                    and test_suites
                                    and test_suite in test_suites
                                ):
                                    device_row = copy.deepcopy(test_row)
                                    device_row["device"] = device["name"]
                                    csv_rows.append(device_row)
            else:
                csv_rows.append(row)

        csv_result = [",".join(header_keys)]
        for csv_row in csv_rows:
            row_values = []
            for header_key in header_keys:
                row_values.append('"%s"' % str(csv_row.get(header_key, "")))
            csv_result.append(",".join(row_values))

        return "\n".join(csv_result)


#
# Functions related to working with GE Data.
#


def LoadGEBuildConfigFromFile(
    build_settings_file=constants.GE_BUILD_CONFIG_FILE,
):
    """Load template config dict from a Json encoded file."""
    json_string = osutils.ReadFile(build_settings_file)
    ret = json.loads(json_string)

    i = 0
    configs = ret["boards"]
    while i < len(configs):
        if configs[i]["name"] in {
            "betty",
            "betty-arc-r",
            "betty-arc-t",
            "betty-arc-u",
            "betty-kernelnext",
            "betty-pi-arc",
            "guado-macrophage",
            "novato",
            "novato-arc64",
            "reven",
            "reven-vmtest",
        }:
            configs.pop(i)
        else:
            i += 1

    i = 0
    configs = ret["reference_board_unified_builds"]
    while i < len(configs):
        if configs[i]["name"] in {
            "aurora-borealis",
            "fizz-moblab",
            "puff-moblab",
        }:
            configs.pop(i)
        else:
            i += 1

    return ret


def GeBuildConfigAllBoards(ge_build_config):
    """Extract a list of board names from the GE Build Config.

    Args:
        ge_build_config: Dictionary containing the decoded GE configuration
            file.

    Returns:
        A list of board names as strings.
    """
    return [b["name"] for b in ge_build_config["boards"]]


def GetUnifiedBuildConfigAllBuilds(ge_build_config):
    """Extract a list of all unified build configurations.

    This dictionary is based on the JSON defined by the proto generated from
    GoldenEye.  See cs/crosbuilds.proto

    Args:
        ge_build_config: Dictionary containing the decoded GE configuration
            file.

    Returns:
        A list of unified build configurations (json configs)
    """
    return ge_build_config.get("reference_board_unified_builds", [])


def GroupBoardsByBuilder(board_list):
    """Group boards by the 'builder' flag."""
    builder_to_boards_dict = {}

    for b in board_list:
        # Until Lakitu is removed from GE, skip the board
        # http://b/180437658
        if b["name"] in GOLDENEYE_IGNORED_BOARDS:
            continue
        # Invalid build configs being written out with no configs array, thus
        # the default. See https://crbug.com/1005803.
        for config in b.get(CONFIG_TEMPLATE_CONFIGS, []):
            builder = config[CONFIG_TEMPLATE_BUILDER]
            if builder not in builder_to_boards_dict:
                builder_to_boards_dict[builder] = set()
            builder_to_boards_dict[builder].add(b[CONFIG_TEMPLATE_NAME])

    return builder_to_boards_dict


def GetArchBoardDict(ge_build_config):
    """Get a dict mapping arch types to board names.

    Args:
        ge_build_config: Dictionary containing the decoded GE configuration
            file.

    Returns:
        A dict mapping arch types to board names.
    """
    arch_board_dict = {}

    for b in ge_build_config[CONFIG_TEMPLATE_BOARDS]:
        board_name = b[CONFIG_TEMPLATE_NAME]
        # Invalid build configs being written out with no configs array, thus
        # the default. See https://crbug.com/947712.
        for config in b.get(CONFIG_TEMPLATE_CONFIGS, []):
            arch = config[CONFIG_TEMPLATE_ARCH]
            arch_board_dict.setdefault(arch, set()).add(board_name)

    for b in GetUnifiedBuildConfigAllBuilds(ge_build_config):
        board_name = b[CONFIG_TEMPLATE_REFERENCE_BOARD_NAME]
        arch = b[CONFIG_TEMPLATE_ARCH]
        arch_board_dict.setdefault(arch, set()).add(board_name)

    return arch_board_dict


#
# Functions related to loading/saving Json.
#
class ObjectJSONEncoder(json.JSONEncoder):
    """Json Encoder that encodes objects as their dictionaries."""

    # pylint: disable=method-hidden
    def default(self, o):
        return self.encode(o.__dict__)


def PrettyJsonDict(dictionary):
    """Returns a pretty-ified json dump of a dictionary."""
    return pformat.json(dictionary, cls=ObjectJSONEncoder)


def LoadConfigFromFile(config_file=constants.CHROMEOS_CONFIG_FILE):
    """Load a Config a Json encoded file."""
    json_string = osutils.ReadFile(config_file)
    return LoadConfigFromString(json_string)


def LoadConfigFromString(json_string):
    """Load a cbuildbot config from it's Json encoded string."""
    config_dict = json.loads(json_string)

    # Use standard defaults, but allow the config to override.
    defaults = DefaultSettings()
    defaults.update(config_dict.pop(DEFAULT_BUILD_CONFIG))

    templates = config_dict.pop("_templates", {})

    defaultBuildConfig = BuildConfig(**defaults)

    builds = {
        n: _CreateBuildConfig(n, defaultBuildConfig, v, templates)
        for n, v in config_dict.items()
    }

    # config is the struct that holds the complete cbuildbot config.
    result = SiteConfig(defaults=defaults, templates=templates)
    result.update(builds)

    return result


def _CreateBuildConfig(name, default, build_dict, templates):
    """Create a BuildConfig object from it's parsed JSON dictionary encoding."""
    # These build config values need special handling.
    template = build_dict.get("_template")

    # Use the name passed in as the default build name.
    build_dict.setdefault("name", name)

    result = default.deepcopy()
    # Use update to explicitly avoid apply's special handing.
    if template:
        result.update(templates[template])
    result.update(build_dict)

    return result


@memoize.Memoize
def GetConfig():
    """Load the current SiteConfig.

    Returns:
        SiteConfig instance to use for this build.
    """
    return LoadConfigFromFile(constants.CHROMEOS_CONFIG_FILE)


@memoize.Memoize
def GetSiteParams():
    """Get the site parameter configs.

    This is the new, preferred method of accessing the site parameters, instead
    of SiteConfig.params.

    Returns:
        AttrDict of site parameters
    """
    site_params = AttrDict()
    site_params.update(DefaultSiteParameters())
    return site_params


def append_useflags(useflags):
    """Used to append a set of useflags to existing useflags.

    Useflags that shadow prior use flags will cause the prior flag to be
    removed. (e.g. appending '-foo' to 'foo' will cause 'foo' to be removed)

    Examples:
        new_config = base_config.derive(
            useflags=append_useflags(['foo', '-bar'])
        )

    Args:
        useflags: List of string useflags to append.
    """
    assert isinstance(useflags, (list, set))
    shadowed_useflags = {
        "-" + flag for flag in useflags if not flag.startswith("-")
    }
    shadowed_useflags.update(
        {flag[1:] for flag in useflags if flag.startswith("-")}
    )

    def handler(old_useflags):
        new_useflags = set(old_useflags or [])
        new_useflags.update(useflags)
        new_useflags.difference_update(shadowed_useflags)
        return sorted(list(new_useflags))

    return handler
