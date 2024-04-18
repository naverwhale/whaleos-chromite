# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The cros chrome-sdk command for the simple chrome workflow."""

import argparse
import collections
import contextlib
import datetime
import glob
import json
import logging
import os
from pathlib import Path
import re
import stat
import textwrap

from chromite.third_party.gn_helpers import gn_helpers

from chromite.cli import command
from chromite.lib import cache
from chromite.lib import chrome_lkgm
from chromite.lib import chromite_config
from chromite.lib import cipd
from chromite.lib import config_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import gclient
from chromite.lib import gs
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib import path_util
from chromite.lib import portage_util
from chromite.utils import gs_urls_util
from chromite.utils import memoize
from chromite.utils import pformat


COMMAND_NAME = "chrome-sdk"
CUSTOM_VERSION = "custom"


def Log(*args, **kwargs):
    """Conditional logging.

    Args:
        silent: If set to True, then logs with level DEBUG. logs with level INFO
            otherwise. Defaults to False.
    """
    silent = kwargs.pop("silent", False)
    level = logging.DEBUG if silent else logging.INFO
    logging.log(level, *args, **kwargs)


class MissingSDK(Exception):
    """Error thrown when we cannot find an SDK."""

    def _ConstructDashboardURL(self, config, board):
        """Returns link to the given board's dashboard."""
        if config.endswith(f"-{config_lib.CONFIG_TYPE_RELEASE}"):
            return "http://go/rubik-release-?f=build_target:in:%s" % board
        elif config.endswith(f"-{config_lib.CONFIG_TYPE_PUBLIC}"):
            return (
                "http://go/cros-ci-builds-/public/?f=build_target:in:%s" % board
            )
        else:
            return ""

    def __init__(self, config, board, version=None):
        msg = "Cannot find SDK for %s" % config
        if version is not None:
            msg += " with version %s" % version
        msg += " from its builder"

        dashboard_url = self._ConstructDashboardURL(config, board)
        if dashboard_url != "":
            msg += f": {dashboard_url}"

        Exception.__init__(self, msg)


class SDKFetcher:
    """Functionality for fetching an SDK environment.

    For the version of ChromeOS specified, the class downloads and caches
    SDK components.
    """

    SDK_BOARD_ENV = "%SDK_BOARD"
    SDK_PATH_ENV = "%SDK_PATH"
    SDK_VERSION_ENV = "%SDK_VERSION"

    SDKContext = collections.namedtuple(
        "SDKContext", ["version", "target_tc", "key_map"]
    )

    CIPD_CACHE = "cipd"
    TARBALL_CACHE = "tarballs"
    MISC_CACHE = "misc"
    SYMLINK_CACHE = "symlinks"

    ARM32_TUPLE = "armv7a-cros-linux-gnueabihf"
    ARM64_TUPLE = "aarch64-cros-linux-gnu"
    TARGET_TOOLCHAIN_KEY = "target_toolchain"
    NACL_ARM32_TOOLCHAIN_KEY = "arm32_toolchain_for_nacl_helper"
    QEMU_BIN_PATH = "app-emulation/qemu"
    SEABIOS_BIN_PATH = "sys-firmware/seabios"
    SQUASHFS_CIPD_PATH = "infra/3pp/tools/squashfs/linux-amd64"
    SQUASHFS_CIPD_VER = "97pLXFMaDo0YFKrWyL_wfrZHyTNXM9iO6T_uRHkMkrQC"
    ZSTD_CIPD_PATH = "infra/3pp/static_libs/libzstd/linux-amd64"
    ZSTD_CIPD_VER = "znTYHKuCvEQXnJ16VeZl1-TvGRwrCUBoFDuKLIB_5IIC"

    CANARIES_PER_DAY = 3
    DAYS_TO_CONSIDER = 14
    VERSIONS_TO_CONSIDER = DAYS_TO_CONSIDER * CANARIES_PER_DAY

    def __init__(
        self,
        cache_dir,
        board,
        clear_cache=False,
        chrome_src=None,
        sdk_path=None,
        toolchain_path=None,
        silent=False,
        use_external_config=None,
        fallback_versions=VERSIONS_TO_CONSIDER,
        is_lacros=False,
    ):
        """Initialize the class.

        Args:
            cache_dir: The toplevel cache dir to use.
            board: The board to manage the SDK for.
            clear_cache: Clears the sdk cache during __init__.
            chrome_src: The location of the chrome checkout. If unspecified, the
                cwd is presumed to be within a chrome checkout.
            sdk_path: The path (whether a local directory or a gs:// path) to
                fetch SDK components from.
            toolchain_path: The path (whether a local directory or a gs:// path)
                to fetch toolchain components from.
            silent: If set, the fetcher prints less output.
            use_external_config: When identifying the configuration for a board,
                force usage of the external configuration if both external and
                internal are available.
            fallback_versions: The number of versions to consider.
            is_lacros: whether it's Lacros-Chrome build or not.
        """
        self.cache_base = os.path.join(cache_dir, COMMAND_NAME)
        if clear_cache:
            logging.warning("Clearing the SDK cache.")
            osutils.RmDir(self.cache_base, ignore_missing=True)
        self.tarball_cache = cache.TarballCache(
            os.path.join(self.cache_base, self.TARBALL_CACHE)
        )
        self.misc_cache = cache.DiskCache(
            os.path.join(self.cache_base, self.MISC_CACHE)
        )
        self.symlink_cache = cache.DiskCache(
            os.path.join(self.cache_base, self.SYMLINK_CACHE)
        )
        self.cipd_cache = cache.DiskCache(
            os.path.join(self.cache_base, self.CIPD_CACHE)
        )
        self.board = board
        self.clear_cache = clear_cache
        self.chrome_src = chrome_src
        self.sdk_path = sdk_path
        self.toolchain_path = toolchain_path
        self.fallback_versions = fallback_versions
        self.silent = silent
        self.is_lacros = is_lacros

        self.gs_ctx = gs.GSContext(cache_dir=cache_dir, init_boto=False)

        if self.sdk_path is None:
            self.sdk_path = os.environ.get(self.SDK_PATH_ENV)

        if self.toolchain_path is None:
            self.toolchain_path = "gs://%s" % constants.SDK_GS_BUCKET

        if use_external_config or not self._HasInternalConfig():
            self.config_name = f"{board}-{config_lib.CONFIG_TYPE_PUBLIC}"
            self.gs_base = f"gs://chromiumos-image-archive/{self.config_name}"
        else:
            self.config_name = f"{board}-{config_lib.CONFIG_TYPE_RELEASE}"
            self.gs_base = f"gs://chromeos-image-archive/{self.config_name}"

        self.version_finder = chrome_lkgm.ChromeOSVersionFinder(
            cache_dir,
            self.board,
            self.fallback_versions,
            self.chrome_src,
            use_external_config,
        )

    def _HasInternalConfig(self):
        """Determines if the SDK we need is provided by an internal builder.

        A given board can have a public and/or an internal builder that
        publishes its Simple Chrome SDK. e.g. "amd64-generic" only has a public
        builder, "scarlet" only has an internal builder, "octopus" has both. So
        if we haven't explicitly passed "--use-external-config", we need to
        figure out if we want to use a public or internal builder.

        The configs inside gs://chromeos-build-release-console are the proper
        source of truth for what boards have public or internal builders.
        However, the ACLs on that bucket make it difficult for some folk to
        inspect it. So we instead simply assume that everything but the
        "*-generic" boards have internal configs.

        TODO(b/241964080): Inspect gs://chromeos-build-release-console here
            instead if/when ACLs on that bucket are opened up.

        Returns:
            True if there's an internal builder available that publishes SDKs
            for the board.
        """
        if "generic" in self.board:
            return False
        return True

    def _InstallZstdFromCipd(self):
        """Install zstd from cipd if the system doesn't have it."""
        if osutils.Which("zstd"):
            return

        key = (self.ZSTD_CIPD_PATH.replace("/", "-"), self.ZSTD_CIPD_VER)
        with self.cipd_cache.Lookup(key) as ref:
            if not ref.Exists(lock=True):
                Log("SDK: Getting zstd")
                path = cipd.InstallPackage(
                    cipd.GetCIPDFromCache(),
                    self.ZSTD_CIPD_PATH,
                    self.ZSTD_CIPD_VER,
                    self.cipd_cache.staging_dir,
                )
                ref.SetDefault(os.path.join(path, "bin"))

        os.environ["PATH"] += f":{ref.path}"

    def _InstallSquashfsFromCipd(self):
        """Install mksquahsfs from cipd if the system doesn't have it."""
        if osutils.Which("mksquashfs"):
            return

        key = (
            self.SQUASHFS_CIPD_PATH.replace("/", "-"),
            self.SQUASHFS_CIPD_VER,
        )
        with self.cipd_cache.Lookup(key) as ref:
            if not ref.Exists(lock=True):
                Log("SDK: Getting squashfs")
                path = cipd.InstallPackage(
                    cipd.GetCIPDFromCache(),
                    self.SQUASHFS_CIPD_PATH,
                    self.SQUASHFS_CIPD_VER,
                    self.cipd_cache.staging_dir,
                )
                ref.SetDefault(os.path.join(path, "squashfs-tools"))

        os.environ["PATH"] += f":{ref.path}"

    def _UpdateTarball(self, key, url, ref):
        """Worker function to fetch a tarball.

        Args:
            key: Key for the tarball's entry in the cache.
            url: GS URL to fetch the tarball from.
            ref: cache.CacheReference of the tarball's entry in the cache.
        """
        with osutils.TempDir(
            base_dir=self.tarball_cache.staging_dir
        ) as tempdir:
            local_path = os.path.join(tempdir, os.path.basename(url))
            Log("SDK: Fetching %s", url, silent=self.silent)
            try:
                self.gs_ctx.Copy(url, tempdir, debug_level=logging.DEBUG)
                ref.SetDefault(local_path, lock=True)
            except gs.GSNoSuchKey:
                if key == constants.TEST_IMAGE_TAR:
                    logging.warning(
                        "No VM available for board %s. Please try a different "
                        "board, e.g. amd64-generic.",
                        self.board,
                    )
                else:
                    raise

    def _UpdateCacheSymlink(self, ref, source_path):
        """Adds a symlink to the cache pointing at the given source.

        Args:
            ref: cache.CacheReference of the link to be created.
            source_path: Absolute path that the symlink will point to.
        """
        with osutils.TempDir(
            base_dir=self.symlink_cache.staging_dir
        ) as tempdir:
            # Make the symlink relative so the cache can be moved to different
            # locations/machines without breaking the link.
            rel_source_path = os.path.relpath(
                source_path, start=os.path.dirname(ref.path)
            )
            link_name_path = os.path.join(tempdir, "tmp-link")
            osutils.SafeSymlink(rel_source_path, link_name_path)
            ref.SetDefault(link_name_path, lock=True)

    def _GetBuildReport(self, version):
        """Return build_report.json (as a dict) for a given version."""
        raw_json = None
        version_base = self._GetVersionGSBase(version)
        report_path = os.path.join(version_base, constants.BUILD_REPORT_JSON)
        with self.misc_cache.Lookup(
            self._GetTarballCacheKey(constants.BUILD_REPORT_JSON, report_path)
        ) as ref:
            if ref.Exists(lock=True):
                raw_json = osutils.ReadFile(ref.path)
            else:
                try:
                    raw_json = self.gs_ctx.Cat(
                        report_path,
                        retries=0,
                        debug_level=logging.DEBUG,
                        encoding="utf-8",
                    )
                except (gs.GSNoSuchKey, gs.GSCommandError):
                    # Make this fatal once we stop using metadata.json from old
                    # cbuildbot builders. (GSCommandError gets thrown instead of
                    # GSNoSuchKey for anonymous users, e.g. Chrome's public
                    # bots.)
                    return
                ref.AssignText(raw_json)

        return json.loads(raw_json)

    def _GetMetadata(self, version):
        """Return metadata (in the form of a dict) for a given version."""
        raw_json = None
        version_base = self._GetVersionGSBase(version)
        metadata_path = os.path.join(version_base, constants.METADATA_JSON)
        partial_metadata_path = os.path.join(
            version_base, constants.PARTIAL_METADATA_JSON
        )
        with self.misc_cache.Lookup(
            self._GetTarballCacheKey(
                constants.PARTIAL_METADATA_JSON, partial_metadata_path
            )
        ) as ref:
            if ref.Exists(lock=True):
                raw_json = osutils.ReadFile(ref.path)
            else:
                try:
                    raw_json = self.gs_ctx.Cat(
                        metadata_path,
                        debug_level=logging.DEBUG,
                        encoding="utf-8",
                    )
                except gs.GSNoSuchKey:
                    logging.info(
                        "Could not read %s, falling back to %s",
                        metadata_path,
                        partial_metadata_path,
                    )
                    raw_json = self.gs_ctx.Cat(
                        partial_metadata_path,
                        debug_level=logging.DEBUG,
                        encoding="utf-8",
                    )

                ref.AssignText(raw_json)

        return json.loads(raw_json)

    @classmethod
    def _LookupMiscCache(cls, cache_dir, key):
        """Looks up an item in the misc cache.

        This should be used when inspecting an SDK that's already been
        initialized elsewhere.

        Args:
            cache_dir: The toplevel cache dir to search in.
            key: Key of item in the cache.

        Returns:
            Value of the item, or None if the item is missing.
        """
        misc_cache_path = os.path.join(cache_dir, COMMAND_NAME, cls.MISC_CACHE)
        misc_cache = cache.DiskCache(misc_cache_path)
        with misc_cache.Lookup(key) as ref:
            if ref.Exists(lock=True):
                return osutils.ReadFile(ref.path).strip()
        return None

    @classmethod
    def GetSDKVersion(cls, cache_dir, board):
        """Looks up the SDK version.

        Look at the environment variable, and then the misc cache.

        Args:
            cache_dir: The toplevel cache dir to search in.
            board: The board to search for.

        Returns:
            SDK version string, if found.
        """
        sdk_version = os.environ.get(cls.SDK_VERSION_ENV)
        if sdk_version:
            return sdk_version

        assert board
        return cls._LookupMiscCache(cache_dir, (board, "latest"))

    @classmethod
    def GetCachedFullVersion(cls, cache_dir, board):
        """Get full version from the misc cache.

        Args:
            cache_dir: The toplevel cache dir to search in.
            board: The board to search for.

        Returns:
            Full version from the misc cache, if found.
        """
        assert board
        sdk_version = cls.GetSDKVersion(cache_dir, board)
        if not sdk_version:
            return None

        return cls._LookupMiscCache(
            cache_dir, ("full-version", board, sdk_version)
        )

    @classmethod
    def GetCachePath(cls, key, cache_dir, board):
        """Gets the path to an item in the cache.

        This should be used when inspecting an SDK that's already been
        initialized elsewhere.

        Args:
            key: Key of item in the cache.
            cache_dir: The toplevel cache dir to search in.
            board: The board to search for.

        Returns:
            Path to the item, or None if the item is missing.
        """
        # The board is always known in the simple chrome SDK shell.
        if board is None:
            return None

        sdk_version = cls.GetSDKVersion(cache_dir, board)
        if not sdk_version:
            return None

        # Look up the cache entry in the symlink cache.
        symlink_cache_path = os.path.join(
            cache_dir, COMMAND_NAME, cls.SYMLINK_CACHE
        )
        symlink_cache = cache.DiskCache(symlink_cache_path)
        cache_key = (board, sdk_version, key)
        with symlink_cache.Lookup(cache_key) as ref:
            if ref.Exists():
                return ref.path
        return None

    @classmethod
    def FixCachePermissions(cls, cache_dir):
        """Fixes directories in the cache that are read-only.

        crrev.com/c/3905759 added read-only directories into the sysroot that
        Simple Chrome downloads. This leads to errors when the cache gets
        automatically cleaned up. So we forcibly make every dir in the cache
        writable here to avoid that.

        Args:
            cache_dir: Location of the cache to be cleaned up.
        """
        for root, dirs, _ in os.walk(cache_dir):
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                if not os.access(dir_path, os.W_OK):
                    os.chmod(dir_path, os.stat(dir_path).st_mode | stat.S_IWUSR)

    @classmethod
    def ClearOldItems(cls, cache_dir, max_age_days=14):
        """Removes old items from the tarball cache older than max_age_days.

        Inspects the entire cache, not just a single board's items.

        Args:
            cache_dir: Location of the cache to be cleaned up.
            max_age_days: Any item in the cache not created/modified within this
                amount of time will be removed.
        """
        tarball_cache_path = os.path.join(
            cache_dir, COMMAND_NAME, cls.TARBALL_CACHE
        )
        tarball_cache = cache.TarballCache(tarball_cache_path)
        tarball_cache.DeleteStale(datetime.timedelta(days=max_age_days))

        # Now clean up any links in the symlink cache that are dangling due to
        # the removal of items above.
        symlink_cache_path = os.path.join(
            cache_dir, COMMAND_NAME, cls.SYMLINK_CACHE
        )
        symlink_cache = cache.DiskCache(symlink_cache_path)
        removed_keys = set()
        for key in symlink_cache.ListKeys():
            link_path = symlink_cache.GetKeyPath(key)
            if not os.path.exists(os.path.realpath(link_path)):
                symlink_cache.Lookup(key).Remove()
                removed_keys.add((key[0], key[1]))
        for board, version in removed_keys:
            logging.debug(
                "Evicted SDK for %s-%s from the cache.", board, version
            )

    @memoize.Memoize
    def _GetSDKVersion(self, version):
        """Get SDK version from metadata.

        Args:
            version: LKGM version, e.g. 12345.0.0

        Returns:
            sdk_version, e.g. 2018.06.04.200410
        """
        metadata = self._GetMetadata(version)
        build_report = self._GetBuildReport(version)
        return metadata.get("sdk-version") or build_report.get("sdkVersion")

    def _GetManifest(self, version):
        """Get the build manifest from the cache, downloading it if necessary.

        Args:
            version: LKGM version, e.g. 12345.0.0

        Returns:
            build manifest as a python dictionary. The build manifest contains
            build versions for packages built by the SDK builder.
        """
        with self.misc_cache.Lookup(("manifest", self.board, version)) as ref:
            if ref.Exists(lock=True):
                manifest = osutils.ReadFile(ref.path)
            else:
                manifest_path = gs_urls_util.GetGsURL(
                    bucket=constants.SDK_GS_BUCKET,
                    suburl="cros-sdk-%s.tar.xz.Manifest"
                    % self._GetSDKVersion(version),
                    for_gsutil=True,
                )
                manifest = self.gs_ctx.Cat(manifest_path, encoding="utf-8")
                ref.AssignText(manifest)
            return json.loads(manifest)

    def _GetBinPackageGSPath(self, version, key):
        """Get google storage path of prebuilt binary package.

        Args:
            version: LKGM version, e.g. 12345.0.0
            key: key in build manifest, for e.g. 'app-emulation/qemu'

        Returns:
            GS path, for e.g. gs://chromeos-prebuilt/board/amd64-host/
            chroot-2018.10.23.171742/packages/app-emulation/qemu-3.0.0.tbz2
        """
        if not version or not key:
            # A version and key is needed to locate the package in Google
            # Storage.
            return None
        package_version = self._GetManifest(version)["packages"][key][0][0]
        return gs_urls_util.GetGsURL(
            bucket="chromeos-prebuilt",
            suburl="board/amd64-host/chroot-%s/packages/%s-%s.tbz2"
            % (self._GetSDKVersion(version), key, package_version),
            for_gsutil=True,
        )

    def _GetTarballCachePath(self, component, url):
        """Get a path in the tarball cache.

        Args:
            component: component name, for e.g. 'app-emulation/qemu'
            url: Google Storage url, e.g.
                'gs://chromiumos-sdk/2019/some-tarball.tar'
        """
        cache_key = self._GetTarballCacheKey(component, url)
        with self.tarball_cache.Lookup(cache_key) as ref:
            if ref.Exists(lock=True):
                return ref.path
        return None

    def _FinalizePackages(self, version):
        """Finalize downloaded packages.

        Fix broken seabios symlinks in the qemu package.

        Args:
            version: LKGM version, e.g. 12345.0.0
        """
        self._CreateSeabiosFWSymlinks(version)

    def _CreateSeabiosFWSymlinks(self, version):
        """Create Seabios firmware symlinks.

        tarballs/<board>+<version>+app-emulation/qemu/usr/share/qemu/ has a
        number of broken symlinks, for example: bios.bin -> ../seabios/bios.bin
        bios.bin is in the seabios package at <cache>/seabios/usr/share/seabios/
        To resolve these symlinks, we create symlinks from
        <cache>+sys-firmware/seabios/usr/share/* to
        <cache>+app-emulation/qemu/usr/share/

        Args:
            version: LKGM version, e.g. 12345.0.0
        """
        qemu_bin_path = self._GetTarballCachePath(
            self.QEMU_BIN_PATH,
            self._GetBinPackageGSPath(version, self.QEMU_BIN_PATH),
        )
        seabios_bin_path = self._GetTarballCachePath(
            self.SEABIOS_BIN_PATH,
            self._GetBinPackageGSPath(version, self.SEABIOS_BIN_PATH),
        )
        if not qemu_bin_path or not seabios_bin_path:
            return

        # Symlink the directories in seabios/usr/share/* to qemu/usr/share/.
        share_dir = "usr/share"
        seabios_share_dir = os.path.join(seabios_bin_path, share_dir)
        qemu_share_dir = os.path.join(qemu_bin_path, share_dir)
        for seabios_dir in os.listdir(seabios_share_dir):
            src_dir = os.path.relpath(
                os.path.join(seabios_share_dir, seabios_dir), qemu_share_dir
            )
            target_dir = os.path.join(qemu_share_dir, seabios_dir)
            if not os.path.exists(target_dir):
                os.symlink(src_dir, target_dir)

    def GetDefaultVersion(self):
        """Get the default SDK version to use.

        If we are in an existing SDK shell, the default version will just be
        the current version. Otherwise, we will try to calculate the
        appropriate version to use based on the checkout.
        """
        if os.environ.get(self.SDK_BOARD_ENV) == self.board:
            sdk_version = os.environ.get(self.SDK_VERSION_ENV)
            if sdk_version is not None:
                return sdk_version

        with self.misc_cache.Lookup((self.board, "latest")) as ref:
            if ref.Exists(lock=True):
                version = osutils.ReadFile(ref.path).strip()
                # Deal with the old version format.
                if version.startswith("R"):
                    version = version.split("-")[1]
                return version
            else:
                return None

    def _SetDefaultVersion(self, version):
        """Set the new default version."""
        with self.misc_cache.Lookup((self.board, "latest")) as ref:
            ref.AssignText(version)

    def UpdateDefaultVersion(self):
        """Update the version that we default to using.

        Returns:
            A tuple of the form (version, updated), where |version| is the
            version number in the format '3929.0.0', and |updated| indicates
            whether the version was indeed updated.
        """
        checkout_dir = self.chrome_src if self.chrome_src else os.getcwd()
        checkout = path_util.DetermineCheckout(checkout_dir)
        current = self.GetDefaultVersion() or "0"

        if not checkout.chrome_src_dir:
            raise chrome_lkgm.NoChromiumSrcDir(checkout_dir)

        target = chrome_lkgm.GetChromeLkgm(checkout.chrome_src_dir)
        if target is None:
            raise chrome_lkgm.MissingLkgmFile(checkout.chrome_src_dir)

        self._SetDefaultVersion(target)
        return target, target != current

    def GetFullVersion(self, version):
        """Get the full ChromeOS version.

        Add the release branch and build number to a ChromeOS platform version.
        This will specify where you can get the latest build for the given
        version for the current board.

        Args:
            version: A ChromeOS platform number of the form XXXX.XX.XX, i.e.,
                3918.0.0. If a full version is provided, it will be returned
                unmodified.

        Returns:
            The version with release branch and build number added, as needed.
            E.g. R28-3918.0.0-b1234.
        """
        if version.startswith("R"):
            return version

        with self.misc_cache.Lookup(
            ("full-version", self.board, version)
        ) as ref:
            if ref.Exists(lock=True):
                return osutils.ReadFile(ref.path).strip()

            full_version = self.version_finder.GetFullVersionFromLatest(version)

            if full_version is None:
                raise MissingSDK(self.config_name, self.board, version)

            ref.AssignText(full_version)
            return full_version

    def _GetVersionGSBase(self, version):
        """The base path of the SDK for a particular version."""
        if self.sdk_path is not None:
            return self.sdk_path

        full_version = self.GetFullVersion(version)
        return os.path.join(self.gs_base, full_version)

    def _GetTarballCacheKey(self, component, url):
        """Builds the cache key tuple for an SDK component.

        Returns a key based of the component name + the URL of its location in
        GS.
        """
        key = self.sdk_path if self.sdk_path else url.strip("gs://")
        key = key.replace("/", "-")
        return (os.path.join(component, key),)

    def _GetLinkNameForComponent(self, version, component):
        """Builds the human-readable symlink name for an SDK component."""
        version_section = version
        if self.sdk_path is not None:
            version_section = self.sdk_path.replace("/", "__").replace(
                ":", "__"
            )
        return (self.board, version_section, component)

    @contextlib.contextmanager
    def Prepare(
        self, components, version=None, target_tc=None, toolchain_url=None
    ):
        """Ensures the components of an SDK exist and are read-locked.

        For a given SDK version, pulls down missing components, and provides a
        context where the components are read-locked, which prevents the cache
        from deleting them during its purge operations.

        If both target_tc and toolchain_url arguments are provided, then this
        does not download metadata.json for the given version. Otherwise, this
        function requires metadata.json for the given version to exist.

        Args:
            gs_ctx: GSContext object.
            components: A list of specific components(tarballs) to prepare.
            version: The version to prepare. If not set, uses the version
                returned by GetDefaultVersion(). If there is no default version
                set (this is the first time we are being executed), then we
                update the default version.
            target_tc: Target toolchain name to use, e.g. x86_64-cros-linux-gnu
            toolchain_url: Format pattern for path to fetch toolchain from,
                e.g. 2014/04/%(target)s-2014.04.23.220740.tar.xz

        Yields:
            An SDKFetcher.SDKContext namedtuple object. The attributes of the
            object are:
                version: The version that was prepared.
                target_tc: Target toolchain name.
                key_map: Dictionary that contains CacheReference objects for the
                    SDK artifacts, indexed by cache key.
        """
        if version is None and self.sdk_path is None:
            version = self.GetDefaultVersion()
            if version is None:
                version, _ = self.UpdateDefaultVersion()
        components = list(components)

        key_map = {}
        fetch_urls = {}

        self._InstallSquashfsFromCipd()
        self._InstallZstdFromCipd()

        if not target_tc or not toolchain_url:
            # Look-up the toolchain data in both metadata.json and
            # build_report.json. We can stop using metadata.json once no one
            # needs to build Simple Chrome using artifacts released from a
            # cbuildbot build. Likely ~2023.
            metadata = self._GetMetadata(version)
            build_report = self._GetBuildReport(version)
            if not target_tc:
                if "toolchain-tuple" in metadata:
                    target_tc = metadata["toolchain-tuple"][0]
                elif build_report and "toolchains" in build_report:
                    target_tc = build_report["toolchains"][0]
                else:
                    cros_build_lib.Die(
                        "Toolchains not found in metadata or build report.\n"
                        f"Metadata: {json.dumps(metadata)}\n"
                        f"Build report: {json.dumps(build_report)}"
                    )

            if not toolchain_url:
                if "toolchain-url" in metadata:
                    toolchain_url = metadata["toolchain-url"]
                elif build_report and "toolchainUrl" in build_report:
                    toolchain_url = build_report["toolchainUrl"]
                else:
                    cros_build_lib.Die(
                        "Toolchain URL not found in metadata or build report.\n"
                        f"Metadata: {json.dumps(metadata)}\n"
                        f"Build report: {json.dumps(build_report)}"
                    )

        # Fetch Arm32 toolchain for NaCl in Arm64 builds.
        if target_tc == self.ARM64_TUPLE:
            fetch_urls[self.NACL_ARM32_TOOLCHAIN_KEY] = os.path.join(
                self.toolchain_path,
                toolchain_url % {"target": self.ARM32_TUPLE},
            )

        # Fetch toolchains from separate location.
        if self.TARGET_TOOLCHAIN_KEY in components:
            fetch_urls[self.TARGET_TOOLCHAIN_KEY] = os.path.join(
                self.toolchain_path, toolchain_url % {"target": target_tc}
            )
            components.remove(self.TARGET_TOOLCHAIN_KEY)

        # Also fetch QEMU binary if VM download is requested.
        if constants.TEST_IMAGE_TAR in components:
            qemu_bin_path = self._GetBinPackageGSPath(
                version, self.QEMU_BIN_PATH
            )
            seabios_bin_path = self._GetBinPackageGSPath(
                version, self.SEABIOS_BIN_PATH
            )
            if qemu_bin_path and seabios_bin_path:
                fetch_urls[self.QEMU_BIN_PATH] = qemu_bin_path
                fetch_urls[self.SEABIOS_BIN_PATH] = seabios_bin_path
            else:
                logging.warning(
                    "Failed to find QEMU/Seabios binaries to download."
                )

        version_base = self._GetVersionGSBase(version)
        fetch_urls.update(
            (t, os.path.join(version_base, t)) for t in components
        )
        inputs_list = []
        try:
            for key, url in fetch_urls.items():
                tarball_cache_key = self._GetTarballCacheKey(key, url)
                tarball_ref = self.tarball_cache.Lookup(tarball_cache_key)
                key_map[tarball_cache_key] = tarball_ref
                tarball_ref.Acquire()
                # Starting with the larger components first when fetching the
                # SDK helps ensure we don't save them for a single thread at the
                # very end while the remaining threads sit idle. Put the VM
                # image first (if we're downloading it), then the sysroot, then
                # everything else.
                if not tarball_ref.Exists(lock=True):
                    input_arg = (key, url, tarball_ref)
                    if key == constants.TEST_IMAGE_TAR:
                        inputs_list.insert(0, input_arg)
                    elif key == constants.CHROME_SYSROOT_TAR:
                        if (
                            inputs_list
                            and inputs_list[0][0] == constants.TEST_IMAGE_TAR
                        ):
                            inputs_list.insert(1, input_arg)
                        else:
                            inputs_list.insert(0, input_arg)
                    else:
                        inputs_list.append(input_arg)

                # Create a symlink in a separate cache dir that points to the
                # tarball component. Since the tarball cache is keyed based off
                # of GS URLs, these symlinks can be used to identify tarball
                # components without knowing the GS URL. This can safely be done
                # before actually fetching the SDK components.
                link_name = self._GetLinkNameForComponent(version, key)
                link_ref = self.symlink_cache.Lookup(link_name)
                key_map[key] = link_ref
                link_ref.Acquire()
                # If the link exists but points to the wrong tarball, we might
                # be overriding a component via --toolchain-url or --target-tc.
                # In that case, just clobber the symlink and recreate it.
                if (
                    link_ref.Exists()
                    and osutils.ExpandPath(link_ref.path) != tarball_ref.path
                ):
                    link_ref.Remove()
                if not link_ref.Exists(lock=True):
                    self._UpdateCacheSymlink(link_ref, tarball_ref.path)

            parallel.RunTasksInProcessPool(
                self._UpdateTarball, inputs_list, processes=2
            )

            self._FinalizePackages(version)
            ctx_version = version
            if self.sdk_path is not None:
                ctx_version = CUSTOM_VERSION
            yield self.SDKContext(ctx_version, target_tc, key_map)
        finally:
            # TODO(rcui): Move to using contextlib.ExitStack().
            memoize.SafeRun(ref.Release for ref in key_map.values())


class GomaError(Exception):
    """Indicates error with setting up Goma."""


@command.command_decorator(COMMAND_NAME)
class ChromeSDKCommand(command.CliCommand):
    """Set up an environment for building Chrome on Chrome OS.

    Pulls down SDK components for building and testing Chrome for Chrome OS,
    sets up the environment for building Chrome, and runs a command in the
    environment, starting a bash session if no command is specified.

    The bash session environment is set up by a user-configurable rc file.
    """

    _CHROME_CLANG_DIR = "third_party/llvm-build/Release+Asserts/bin"
    _BUILD_ARGS_DIR = "build/args/chromeos/"

    EBUILD_ENV_PATHS = (
        # Compiler tools.
        "CXX",
        "CC",
        "AR",
        "AS",
        "LD",
        "NM",
        "RANLIB",
        "READELF",
    )

    EBUILD_ENV = EBUILD_ENV_PATHS + (
        # Compiler flags.
        "CFLAGS",
        "CXXFLAGS",
        "CPPFLAGS",
        "LDFLAGS",
        # Misc settings.
        "GN_ARGS",
        "GOLD_SET",
        "USE",
    )

    SDK_GOMA_PORT_ENV = "SDK_GOMA_PORT"
    SDK_GOMA_DIR_ENV = "SDK_GOMA_DIR"

    GOMACC_PORT_CMD = ["./gomacc", "port"]

    # Override base class property to use cache related commandline options.
    use_caching_options = True

    @staticmethod
    def ValidateVersion(version):
        """Ensures that the version arg is potentially valid.

        See the argument description for supported version formats.
        """

        if not re.match(r"^[0-9]+\.0\.0$", version) and not re.match(
            r"^R[0-9]+-[0-9]+\.[0-9]+\.[0-9]+", version
        ):
            raise argparse.ArgumentTypeError(
                "--version should be in the format 1234.0.0 or R56-1234.0.0"
            )
        return version

    @classmethod
    def AddParser(cls, parser):
        super(ChromeSDKCommand, cls).AddParser(parser)
        parser.add_argument(
            "--board", required=False, help="The board SDK to use."
        )
        parser.add_argument(
            "--boards",
            required=False,
            help="Colon-separated list of boards to fetch SDKs for. Implies "
            "--no-shell since a shell is tied to a single board. Used to "
            "quickly setup cache and build dirs for multiple boards at once.",
        )
        parser.add_argument(
            "--build-label",
            default="Release",
            help="The label for this build. Used as a subdirectory name under "
            "out_${BOARD}/",
        )
        parser.add_argument(
            "--bashrc",
            type="path",
            default=chromite_config.CHROME_SDK_BASHRC,
            help="A bashrc file used to set up the SDK shell environment. "
            "(default: %(default)s",
        )
        parser.add_argument(
            "--chroot",
            type="path",
            help="Path to a ChromeOS chroot to use. If set, "
            "<chroot>/build/<board> will be used as the sysroot that Chrome "
            "is built against. If chromeos-chrome was built, the build "
            "environment from the chroot will also be used. The version shown "
            "in the SDK shell prompt will have an asterisk prepended to it.",
        )
        parser.add_argument(
            "--chrome-src",
            type="path",
            help="Specifies the location of a Chrome src/ directory.  Required "
            "if not running from a Chrome checkout.",
        )
        parser.add_argument(
            "--cwd",
            type="path",
            help="Specifies a directory to switch to after setting up the SDK "
            "shell.  Defaults to the current directory.",
        )
        parser.add_argument(
            "--internal",
            action="store_true",
            default=False,
            help="Enables --chrome-branding and --official.",
        )
        parser.add_argument(
            "--chrome-branding",
            action="store_true",
            default=False,
            help="Sets up SDK for building internal Chrome using src-internal, "
            "rather than Chromium.",
        )
        parser.add_argument(
            "--official",
            action="store_true",
            default=False,
            help="Enables the official build level of optimization. This "
            "removes development conveniences like runtime stack traces, and "
            "should be used for performance testing rather than debugging.",
        )
        parser.add_argument(
            "--use-external-config",
            action="store_true",
            default=False,
            help="Use the external configuration for the specified board, even "
            "if an internal configuration is avalable.",
        )
        parser.add_argument(
            "--sdk-path",
            type="local_or_gs_path",
            help="Provides a path, whether a local directory or a gs:// path, "
            "to pull SDK components from.",
        )
        parser.add_argument(
            "--toolchain-path",
            type="local_or_gs_path",
            help="Provides a path, whether a local directory or a gs:// path, "
            "to pull toolchain components from.",
        )
        parser.add_argument(
            "--no-shell",
            action="store_false",
            default=True,
            dest="use_shell",
            help="Skips the interactive shell. When this arg is passed, the "
            "needed toolchain will still be downloaded. However, no //out* "
            "dir will automatically be created. The args.gn file will "
            "instead be downloaded at a shareable location in //%s, and the "
            "SDK will simply exit after that." % cls._BUILD_ARGS_DIR,
        )
        parser.add_argument(
            "--gn-extra-args",
            help='Provides extra args to "gn gen". Uses the same format as '
            'gn gen, e.g. "foo = true bar = 1".',
        )
        parser.add_argument(
            "--gn-gen",
            action="store_true",
            default=True,
            dest="gn_gen",
            help='Run "gn gen" if args.gn is stale.',
        )
        parser.add_argument(
            "--nogn-gen",
            action="store_false",
            dest="gn_gen",
            help='Do not run "gn gen", warns if args.gn is stale.',
        )
        parser.add_argument(
            "--nogoma",
            action="store_false",
            default=True,
            dest="goma",
            help="Disables Goma in the shell by removing it from the PATH and "
            "set use_goma=false to GN_ARGS.",
        )
        parser.add_argument(
            "--nostart-goma",
            action="store_false",
            default=True,
            dest="start_goma",
            help="Skip starting goma and hope somebody else starts goma later.",
        )
        parser.add_argument(
            "--gomadir",
            type="path",
            help="Use the goma installation at the specified PATH.",
        )
        parser.add_argument(
            "--use-remoteexec",
            action="store_true",
            default=False,
            help="Enable RBE client for the build. "
            "This automatically disables Goma.",
        )
        parser.add_argument(
            "--version",
            default=None,
            type=cls.ValidateVersion,
            help="Specify the SDK version to use. This can be a platform "
            "version ending in .0.0, e.g. 1234.0.0, in which case the full "
            "version will be extracted from the corresponding LATEST file "
            "for the specified board. If no LATEST file exists, an older "
            "version will be used if available. Alternatively, a full "
            "version may be specified, e.g. R56-1234.0.0, in which case that "
            "exact version will be used. Defaults to using the version "
            "specified in the CHROMEOS_LKGM file in the chromium checkout.",
        )
        parser.add_argument(
            "--fallback-versions",
            type=int,
            default=SDKFetcher.VERSIONS_TO_CONSIDER,
            help="The number of recent LATEST files to consider in the case "
            "that the specified version is missing.",
        )
        parser.add_argument(
            "cmd",
            nargs="*",
            default=None,
            help="The command to execute in the SDK environment.  Defaults to "
            "starting a bash shell.",
        )
        parser.add_argument(
            "--download-vm",
            action="store_true",
            default=False,
            help="Additionally downloads a VM image from cloud storage.",
        )
        parser.add_argument(
            "--thinlto",
            action="store_true",
            default=False,
            help="Enable ThinLTO in build.",
        )
        parser.add_argument(
            "--cfi",
            action="store_true",
            default=False,
            help="Enable CFI in build.",
        )
        parser.add_argument(
            "--is-lacros",
            action="store_true",
            default=False,
            help="Whether it is Lacros-Chrome build or not. This is "
            "temporarily added to work around a Lacros CrOS toolchain bug "
            "due to version skew, and should be removed once Lacros is "
            "swiched to use Chromium toolchain: crbug.com/1275386.",
        )
        parser.caching_group.add_argument(
            "--clear-sdk-cache",
            action="store_true",
            default=False,
            help="Removes everything in the SDK cache before starting.",
        )

        group = parser.add_argument_group(
            "Metadata Overrides (Advanced)",
            description="Provide all of these overrides in order to remove "
            "dependencies on metadata.json existence.",
        )
        group.add_argument(
            "--target-tc",
            action="store",
            default=None,
            help="Override target toolchain name, e.g. x86_64-cros-linux-gnu",
        )
        group.add_argument(
            "--toolchain-url",
            action="store",
            default=None,
            help="Override toolchain url format pattern, e.g. "
            "2014/04/%%(target)s-2014.04.23.220740.tar.xz",
        )

    @classmethod
    def ProcessOptions(cls, parser, options):
        """Post process options."""
        if bool(options.board) == bool(options.boards):
            parser.error("Must specify either one of --board or --boards.")

        if options.boards and options.use_shell:
            parser.error(
                "Must specify --no-shell when preparing multiple boards."
            )

        if options.is_lacros and not options.version:
            parser.error(
                "Must specify --version for --is-lacros because Lacros-Chrome "
                "build does not use the CHROMEOS_LKGM version for compilation"
            )

        src_path = options.chrome_src or os.getcwd()
        checkout = path_util.DetermineCheckout(src_path)
        if not checkout.chrome_src_dir:
            parser.error(f"Chrome checkout not found at {src_path}")
        options.chrome_src = checkout.chrome_src_dir

        if options.boards:
            options.boards = options.boards.split(":")

    def __init__(self, options):
        super().__init__(options)
        self.board = options.board
        # Lazy initialized.
        self.sdk = None
        # Initialized later based on options passed in.
        self.silent = True

    @staticmethod
    def _PS1Prefix(board, version, chroot=None):
        """Returns a string describing the sdk environment for use in PS1."""
        chroot_star = "*" if chroot else ""
        return "(sdk %s %s%s)" % (board, chroot_star, version)

    @staticmethod
    def _CreatePS1(board, version, chroot=None):
        """Returns PS1 string that sets commandline and xterm window caption.

        If a chroot path is set, then indicate we are using the sysroot from
        there instead of the stock sysroot by prepending an asterisk to the
        version.

        Args:
            board: The SDK board.
            version: The SDK version.
            chroot: The path to the chroot, if set.
        """
        current_ps1 = cros_build_lib.run(
            ["bash", "-l", "-c", 'echo "$PS1"'],
            print_cmd=False,
            encoding="utf-8",
            capture_output=True,
        ).stdout.splitlines()
        if current_ps1:
            current_ps1 = current_ps1[-1]
        if not current_ps1:
            # Something went wrong, so use a fallback value.
            current_ps1 = r"\u@\h \w $ "
        ps1_prefix = ChromeSDKCommand._PS1Prefix(board, version, chroot)
        return "%s %s" % (ps1_prefix, current_ps1)

    def _SaveSharedGnArgs(self, gn_args, board):
        """Saves the new gn args data to the shared location."""
        shared_dir = os.path.join(self.options.chrome_src, self._BUILD_ARGS_DIR)
        if not self.options.is_lacros:
            file_path = os.path.join(shared_dir, board + ".gni")
            osutils.WriteFile(file_path, gn_helpers.ToGNString(gn_args))
            return

        # If the board is a generic family, generate -crostoolchain.gni files,
        # too, which is used by Lacros build.
        if board.endswith("-generic"):
            # pylint: disable=line-too-long
            toolchain_key_pattern = re.compile(
                r"^(%s)$"
                % "|".join(
                    [
                        "cros_board",
                        "cros_sdk_version",
                        "is_clang",
                        "target_cpu",
                        "cros_host_(cc|cxx|ld|extra_(c|cpp|cxx|ld)flags)",
                        "cros_target_(ar|cc|cxx|ld|nm|readelf|extra_(c|cpp|cxx|ld)flags)",
                        "cros_v8_snapshot_(cc|cxx|ld|extra_(c|cpp|cxx|ld)flags)",
                        "cros_nacl_helper_arm32_(ar|cc|cxx|ld|readelf|sysroot)",
                        "(custom|host|v8_snapshot)_toolchain",
                        "rbe_cros_cc_wrapper",
                        "system_libdir",
                        "target_sysroot",
                        "arm_(float_abi|use_neon)",
                    ]
                )
            )
            # pylint: enable=line-too-long
            toolchain_gn_args = {
                k: v
                for k, v in gn_args.items()
                if toolchain_key_pattern.match(k)
            }
            file_path = os.path.join(shared_dir, board + "-crostoolchain.gni")
            osutils.WriteFile(
                file_path, gn_helpers.ToGNString(toolchain_gn_args)
            )

    def _UpdateGnArgsIfStale(self, out_dir, build_label, gn_args, board):
        """Runs 'gn gen' if gn args are stale or logs a warning."""
        build_dir = os.path.join(out_dir, build_label)
        gn_args_file_path = os.path.join(
            self.options.chrome_src, build_dir, "args.gn"
        )

        if not self.options.use_shell:
            import_line = 'import("//%s%s.gni")' % (self._BUILD_ARGS_DIR, board)
            if os.path.exists(
                gn_args_file_path
            ) and not import_line in osutils.ReadFile(gn_args_file_path):
                logging.warning(
                    "Stale or malformed args.gn file at %s. Regenerating.",
                    gn_args_file_path,
                )
                osutils.SafeUnlink(gn_args_file_path)
            if not os.path.exists(gn_args_file_path):
                osutils.WriteFile(
                    gn_args_file_path,
                    textwrap.dedent(
                        """\
          %s
          # Place any additional args or overrides below:

          """
                        % import_line
                    ),
                    makedirs=True,
                )
            return

        if not self._StaleGnArgs(gn_args, gn_args_file_path):
            return

        if not self.options.gn_gen:
            logging.warning("To update gn args run:")
            logging.warning('gn gen %s --args="$GN_ARGS"', build_dir)
            return

        logging.warning("Running gn gen")
        cros_build_lib.run(
            [
                "gn",
                "gen",
                build_dir,
                "--args=%s" % gn_helpers.ToGNString(gn_args),
            ],
            print_cmd=logging.getLogger().isEnabledFor(logging.DEBUG),
            cwd=self.options.chrome_src,
        )

    def _StaleGnArgs(self, new_gn_args, gn_args_file_path):
        """Returns True if args.gn needs to be updated."""
        if not os.path.exists(gn_args_file_path):
            logging.warning("No args.gn file: %s", gn_args_file_path)
            return True

        parser = gn_helpers.GNValueParser(
            osutils.ReadFile(gn_args_file_path),
            checkout_root=self.options.chrome_src,
        )
        old_gn_args = parser.ParseArgs()
        if new_gn_args == old_gn_args:
            return False

        logging.warning("Stale args.gn file: %s", gn_args_file_path)
        self._LogArgsDiff(old_gn_args, new_gn_args)
        return True

    def _LogArgsDiff(self, cur_args, new_args):
        """Logs the differences between |cur_args| and |new_args|."""
        cur_keys = set(cur_args.keys())
        new_keys = set(new_args.keys())

        for k in new_keys - cur_keys:
            logging.info("MISSING ARG: %s = %s", k, new_args[k])

        for k in cur_keys - new_keys:
            logging.info("EXTRA ARG: %s = %s", k, cur_args[k])

        for k in new_keys & cur_keys:
            v_cur = cur_args[k]
            v_new = new_args[k]
            if v_cur != v_new:
                logging.info("MISMATCHED ARG: %s: %s != %s", k, v_cur, v_new)

    def _SetupTCEnvironment(self, options, env):
        """Sets up toolchain-related environment variables."""
        chrome_clang_path = os.path.join(
            options.chrome_src, self._CHROME_CLANG_DIR
        )

        # For host compiler, we use the compiler that comes with Chrome
        # instead of the target compiler.
        env["CC_host"] = os.path.join(chrome_clang_path, "clang")
        env["CXX_host"] = os.path.join(chrome_clang_path, "clang++")
        env["LD_host"] = env["CXX_host"]

    def _AbsolutizeBinaryPath(self, binary, tc_path):
        """Modify toolchain path for goma build.

        This function absolutizes the path to the given toolchain binary, which
        will then be relativized in build/toolchain/cros/BUILD.gn. This ensures
        the paths are the same across different machines & checkouts, which
        improves cache hit rate in distributed build systems (i.e. goma).

        Args:
            binary: Name of toolchain binary.
            tc_path: Path to toolchain directory.

        Returns:
            Absolute path to the binary in the toolchain dir.
        """
        # If binary doesn't contain a '/', assume it's located in the toolchain
        # dir.
        if os.path.basename(binary) == binary:
            return os.path.join(tc_path, "bin", binary)
        return binary

    def _GenerateReclientWrapper(self, board):
        """Generate a wrapper for reclient.

        This function generates a wrapper script for the rewrapper to make it
        passed with --gomacc-path (rewrapper_<board>).
        The wrapper adds a flag to preserve symlinks which are used by CrOS
        clang.

        Args:
            board: Target board name to be used as a config and wrapper name.

        Returns:
            Absolute path to the wrapper script to be used as --gomacc-path.
        """
        shared_dir = os.path.join(self.options.chrome_src, self._BUILD_ARGS_DIR)

        # TODO(b:190741226): remove the wrapper if the compiler wrapper supports
        #                    flags for reclient.
        wrapper_path = os.path.join(shared_dir, "rewrapper_%s" % board)
        wrapper_content = [
            "#!/bin/sh\n",
            "%(rewrapper_dir)s/rewrapper -preserve_symlink=true "
            '-exec_root="%(chrome_src)s" "$@"\n'
            % {
                "rewrapper_dir": os.path.join(
                    self.options.chrome_src, "buildtools", "reclient"
                ),
                "chrome_src": self.options.chrome_src,
            },
        ]
        osutils.WriteFile(wrapper_path, wrapper_content, chmod=0o755)
        Log("generated rewrapper wrapper %s", wrapper_path, silent=self.silent)
        return wrapper_path

    def _SetupEnvironment(
        self, board, sdk_ctx, options, goma_dir=None, goma_port=None
    ):
        """Sets environment variables to export to the SDK shell."""
        if options.chroot:
            sysroot = os.path.join(options.chroot, "build", board)
            if not os.path.isdir(sysroot) and not options.cmd:
                logging.warning(
                    "Because --chroot is set, expected a sysroot to be at "
                    "%s, but couldn't find one.",
                    sysroot,
                )
        else:
            sysroot = sdk_ctx.key_map[constants.CHROME_SYSROOT_TAR].path

        environment = os.path.join(
            sdk_ctx.key_map[constants.CHROME_ENV_TAR].path, "environment"
        )
        if options.chroot:
            # Override with the environment from the chroot if available (i.e.
            # build_packages or emerge chromeos-chrome has been run for
            # |board|).
            env_path = os.path.join(
                sysroot,
                portage_util.VDB_PATH,
                "chromeos-base",
                "chromeos-chrome-*",
            )
            env_glob = glob.glob(env_path)
            if len(env_glob) != 1:
                logging.warning(
                    "Multiple Chrome versions in %s. This can be resolved"
                    ' by running "eclean-$BOARD -d packages". Using'
                    " environment from: %s",
                    env_path,
                    environment,
                )
            elif not os.path.isdir(env_glob[0]):
                logging.warning(
                    "Environment path not found: %s. Using enviroment from:"
                    " %s.",
                    env_path,
                    environment,
                )
            else:
                chroot_env_file = os.path.join(env_glob[0], "environment.bz2")
                if os.path.isfile(chroot_env_file):
                    # Log a warning here since this is new behavior that is not
                    # obvious.
                    logging.notice(
                        "Environment fetched from: %s", chroot_env_file
                    )
                    # Uncompress enviornment.bz2 to pass to
                    # osutils.SourceEnvironment.
                    chroot_cache = os.path.join(
                        options.cache_dir, COMMAND_NAME, "chroot"
                    )
                    osutils.SafeMakedirs(chroot_cache)
                    environment = os.path.join(
                        chroot_cache, "environment_%s" % board
                    )
                    cros_build_lib.UncompressFile(chroot_env_file, environment)

        env = osutils.SourceEnvironment(environment, self.EBUILD_ENV)
        gn_args = gn_helpers.FromGNArgs(env["GN_ARGS"])
        self._SetupTCEnvironment(options, env)

        # Add managed components to the PATH.
        path = os.environ["PATH"].split(os.pathsep)
        path.insert(0, str(constants.CHROMITE_BIN_DIR))
        env["PATH"] = os.pathsep.join(path)

        # Export internally referenced variables.
        os.environ[self.sdk.SDK_BOARD_ENV] = board
        if options.sdk_path:
            os.environ[self.sdk.SDK_PATH_ENV] = options.sdk_path
        os.environ[self.sdk.SDK_VERSION_ENV] = sdk_ctx.version

        # Add board and sdk version as gn args so that tests can bind them in
        # test wrappers generated at compile time.
        gn_args["cros_board"] = board

        if options.is_lacros:
            # The 'cros_sdk_version' is used by the chromium BUILD files to
            # decide the runtime dependencies to isolate for swarming based
            # testing, and given that Lacros uses CHROMEOS_LKGM for testing
            # regardless of the version used for compilation, so always set the
            # value as CHROME_LKGM.
            gn_args["cros_sdk_version"] = chrome_lkgm.GetChromeLkgm(
                options.chrome_src
            )
        else:
            gn_args["cros_sdk_version"] = sdk_ctx.version

        # Export the board/version info in a more accessible way, so developers
        # can reference them in their chrome_sdk.bashrc files, as well as within
        # the chrome-sdk shell.
        for var in [self.sdk.SDK_VERSION_ENV, self.sdk.SDK_BOARD_ENV]:
            env[var.lstrip("%")] = os.environ[var]

        # Export Goma information.
        if goma_dir:
            env[self.SDK_GOMA_DIR_ENV] = goma_dir
        if goma_port:
            env[self.SDK_GOMA_PORT_ENV] = goma_port

        # SYSROOT is necessary for Goma and the sysroot wrapper.
        env["SYSROOT"] = sysroot

        gn_args["target_sysroot"] = sysroot

        # Use Chrome's host sysroot settings and pkg_config for building outside
        # the chroot.
        gn_args.pop("use_sysroot", None)
        gn_args.pop("pkg_config", None)
        gn_args.pop("host_pkg_config", None)

        # --internal == --chrome-branding + --official
        if options.chrome_branding or options.internal:
            gn_args["is_chrome_branded"] = True
        else:
            gn_args.pop("is_chrome_branded", None)
            gn_args.pop("internal_gles2_conform_tests", None)

        if options.official or options.internal:
            gn_args["is_official_build"] = True
        else:
            gn_args.pop("is_official_build", None)

        if not options.internal:
            gn_args.pop("enable_hevc_parser_and_hw_decoder", None)

        target_tc_path = sdk_ctx.key_map[self.sdk.TARGET_TOOLCHAIN_KEY].path
        for env_path in self.EBUILD_ENV_PATHS:
            env[env_path] = self._AbsolutizeBinaryPath(
                env[env_path], target_tc_path
            )

        # Add Arm32 toolchain GN flags for building nacl_helper on Arm64.
        if self.sdk.NACL_ARM32_TOOLCHAIN_KEY in sdk_ctx.key_map:
            nacl_helper_tc_path = sdk_ctx.key_map[
                self.sdk.NACL_ARM32_TOOLCHAIN_KEY
            ].path
            gn_args["cros_nacl_helper_arm32_ar"] = self._AbsolutizeBinaryPath(
                "llvm-ar", nacl_helper_tc_path
            )
            gn_args["cros_nacl_helper_arm32_cc"] = self._AbsolutizeBinaryPath(
                self.sdk.ARM32_TUPLE + "-clang", nacl_helper_tc_path
            )
            gn_args["cros_nacl_helper_arm32_cxx"] = self._AbsolutizeBinaryPath(
                self.sdk.ARM32_TUPLE + "-clang++", nacl_helper_tc_path
            )
            gn_args["cros_nacl_helper_arm32_ld"] = self._AbsolutizeBinaryPath(
                self.sdk.ARM32_TUPLE + "-clang++", nacl_helper_tc_path
            )
            gn_args[
                "cros_nacl_helper_arm32_readelf"
            ] = self._AbsolutizeBinaryPath("llvm-readelf", nacl_helper_tc_path)
            gn_args["cros_nacl_helper_arm32_sysroot"] = os.path.join(
                nacl_helper_tc_path, "usr", self.sdk.ARM32_TUPLE
            )

        gn_args["cros_target_cc"] = env["CC"]
        gn_args["cros_target_cxx"] = env["CXX"]
        gn_args["cros_target_ld"] = env["LD"]
        gn_args["cros_target_nm"] = env["NM"]
        gn_args["cros_target_ar"] = env["AR"]
        gn_args["cros_target_readelf"] = env["READELF"]
        gn_args["cros_target_extra_cflags"] = env.get("CFLAGS", "")
        gn_args["cros_target_extra_cxxflags"] = env.get("CXXFLAGS", "")
        gn_args["cros_host_cc"] = env["CC_host"]
        gn_args["cros_host_cxx"] = env["CXX_host"]
        gn_args["cros_host_ld"] = env["LD_host"]
        gn_args["cros_v8_snapshot_cc"] = env["CC_host"]
        gn_args["cros_v8_snapshot_cxx"] = env["CXX_host"]
        gn_args["cros_v8_snapshot_ld"] = env["LD_host"]
        # Let Chromium's build files pick defaults for the following.
        gn_args.pop("cros_host_nm", None)
        gn_args.pop("cros_host_ar", None)
        gn_args.pop("cros_host_readelf", None)
        gn_args.pop("cros_v8_snapshot_nm", None)
        gn_args.pop("cros_v8_snapshot_ar", None)
        gn_args.pop("cros_v8_snapshot_readelf", None)
        # No need to adjust CFLAGS and CXXFLAGS for GN since the only
        # adjustment made in _SetupTCEnvironment is for split debug which
        # is done with 'use_debug_fission'.

        if options.use_remoteexec:
            gn_args["use_remoteexec"] = True

        # Enable goma if requested.
        if not options.goma or options.use_remoteexec:
            # If --nogoma option is explicitly set, disable goma, even if it is
            # used in the original GN_ARGS.
            gn_args["use_goma"] = False
            gn_args.pop("goma_dir", None)
        elif goma_dir:
            gn_args["use_goma"] = True
            gn_args["goma_dir"] = goma_dir

        gn_args.pop("internal_khronos_glcts_tests", None)  # crbug.com/588080

        # The ebuild sets dcheck_always_on to false to avoid a default value of
        # true for bots. But we'd like developers using DCHECKs when possible,
        # so we let dcheck_always_on use the default value for Simple Chrome.
        gn_args.pop("dcheck_always_on", None)

        # Always allow LOG()s to be enabled via command line flag.
        gn_args["use_runtime_vlog"] = True

        # Disable ThinLTO and CFI for simplechrome. Tryjob machines do not have
        # enough file descriptors to use. crbug.com/789607
        if not options.thinlto:
            gn_args["use_thin_lto"] = False
        if not options.cfi:
            gn_args["is_cfi"] = False
        # When using Goma and ThinLTO, distribute ThinLTO code generation on
        # Goma.
        gn_args["use_goma_thin_lto"] = gn_args.get(
            "use_goma", False
        ) and gn_args.get("use_thin_lto", False)
        # We need to remove the flag -Wl,-plugin-opt,-import-instr-limit=$num
        # from cros_target_extra_ldflags if options.thinlto is not set.
        # The format of ld flags is something like
        # '-Wl,-O1 -Wl,-O2 -Wl,--as-needed -stdlib=libc++'
        if not options.thinlto:
            extra_ldflags = gn_args.get("cros_target_extra_ldflags", "")

            ld_flags_list = extra_ldflags.split()
            ld_flags_list = [
                f
                for f in ld_flags_list
                if not f.startswith("-Wl,-plugin-opt,-import-instr-limit")
            ]
            if extra_ldflags:
                gn_args["cros_target_extra_ldflags"] = " ".join(ld_flags_list)

        # We removed blink symbols on release builds on arm, see
        # https://crbug.com/792999. However, we want to keep the symbols
        # for simplechrome builds.
        gn_args["blink_symbol_level"] = -1

        # Remove symbol_level specified in the ebuild to use the default.
        # Currently that is 1 when is_debug=false, instead of 2 specified by the
        # ebuild. This results in faster builds in Simple Chrome.
        if "symbol_level" in gn_args:
            symbol_level = gn_args.pop("symbol_level")
            logging.info(
                "Removing symbol_level = %d from gn args, use "
                "--gn-extra-args to specify a non default value.",
                symbol_level,
            )

        gn_args["rbe_cros_cc_wrapper"] = self._GenerateReclientWrapper(board)

        if options.gn_extra_args:
            gn_args.update(gn_helpers.FromGNArgs(options.gn_extra_args))

        gn_args_env = gn_helpers.ToGNString(gn_args)
        env["GN_ARGS"] = gn_args_env

        # PS1 sets the command line prompt and xterm window caption.
        full_version = sdk_ctx.version
        if full_version != CUSTOM_VERSION:
            full_version = self.sdk.GetFullVersion(sdk_ctx.version)
        env["PS1"] = self._CreatePS1(board, full_version, chroot=options.chroot)

        # Set the useful part of PS1 for users with a custom PROMPT_COMMAND.
        env["CROS_PS1_PREFIX"] = self._PS1Prefix(
            board, full_version, chroot=options.chroot
        )

        out_dir = "out_%s" % board
        env["builddir_name"] = out_dir

        # This is used by landmines.py to prevent collisions when building both
        # chromeos and android from shared source.
        # For context, see crbug.com/407417
        env["CHROMIUM_OUT_DIR"] = os.path.join(options.chrome_src, out_dir)

        if not self.options.use_shell:
            self._SaveSharedGnArgs(gn_args, board)
        self._UpdateGnArgsIfStale(out_dir, options.build_label, gn_args, board)

        return env

    @staticmethod
    def _VerifyGoma(user_rc):
        """Verify that the user has no goma installations set up in user_rc.

        If the user does have a goma installation set up, verify that it's for
        ChromeOS.

        Args:
            user_rc: User-supplied rc file.
        """
        user_env = osutils.SourceEnvironment(user_rc, ["PATH"])
        goma_ctl = osutils.Which("goma_ctl.py", user_env.get("PATH"))
        if goma_ctl is not None:
            logging.warning(
                "%s is adding Goma to the PATH. Using that Goma instead of the "
                "managed Goma install.",
                user_rc,
            )

    @staticmethod
    def _VerifyChromiteBin(user_rc):
        """Verify that the user has not set a chromite bin/ dir in user_rc.

        Args:
            user_rc: User-supplied rc file.
        """
        user_env = osutils.SourceEnvironment(user_rc, ["PATH"])
        chromite_bin = osutils.Which("parallel_emerge", user_env.get("PATH"))
        if chromite_bin is not None:
            logging.warning(
                "%s is adding chromite/bin to the PATH.  Remove it from the "
                "PATH to use the the default Chromite.",
                user_rc,
            )

    @contextlib.contextmanager
    def _GetRCFile(self, env, user_rc):
        """Returns path to dynamically created bashrc file.

        The bashrc file sets the environment variables contained in |env|, as
        well as sources the user-editable chrome_sdk.bashrc file in the user's
        home directory.  That rc file is created if it doesn't already exist.

        Args:
            env: A dictionary of environment variables that will be set by the
                rc file.
            user_rc: User-supplied rc file.
        """
        if not os.path.exists(user_rc):
            osutils.Touch(user_rc, makedirs=True)

        self._VerifyGoma(user_rc)
        self._VerifyChromiteBin(user_rc)

        # We need a temporary rc file to 'wrap' the user configuration file,
        # because running with '--rcfile' causes bash to ignore bash special
        # variables passed through subprocess.Popen, such as PS1.  So we set
        # them here.
        #
        # Having a wrapper rc file will also allow us to inject bash functions
        # into the environment, not just variables.
        with osutils.TempDir() as tempdir:
            # Only source the user's ~/.bashrc if running in interactive mode.
            contents = [
                "[[ -e ~/.bashrc && $- == *i* ]] && . ~/.bashrc\n",
            ]

            for key, value in env.items():
                contents.append("export %s='%s'\n" % (key, value))
            contents.append('. "%s"\n' % user_rc)

            rc_file = os.path.join(tempdir, "rcfile")
            osutils.WriteFile(rc_file, contents)
            yield rc_file

    def _GomaPort(self, goma_dir):
        """Returns current active Goma port."""
        port = cros_build_lib.run(
            self.GOMACC_PORT_CMD,
            cwd=goma_dir,
            debug_level=logging.DEBUG,
            check=False,
            encoding="utf-8",
            capture_output=True,
        ).stdout.strip()
        return port

    def _GomaDir(self, goma_dir):
        """Returns current active Goma directory."""
        if not goma_dir:
            goma_dir_cmd = ["goma_ctl", "goma_dir"]
            goma_dir = cros_build_lib.run(
                goma_dir_cmd, check=False, capture_output=True, encoding="utf-8"
            ).stdout.strip()
        if goma_dir and os.path.exists(os.path.join(goma_dir, "gomacc")):
            return goma_dir

    def _SetupGoma(self):
        """Find installed Goma and start Goma.

        Returns:
            A tuple (dir, port) containing the path to the cached goma/ dir and
            the Goma port.
        """
        goma_dir = self._GomaDir(self.options.gomadir)
        if not goma_dir:
            raise GomaError(
                "Failed to find the Goma client."
                " Please confirm depot_tools is in PATH,"
                " and you do not set GOMA_DIR."
            )

        port = None
        if self.options.start_goma:
            Log("Starting Goma.", silent=self.silent)
            cros_build_lib.dbg_run(
                [os.path.join(goma_dir, "goma_ctl.py"), "ensure_start"],
                extra_env={"GOMA_ARBITRARY_TOOLCHAIN_SUPPORT": "true"},
            )
            port = self._GomaPort(goma_dir)
            Log("Goma is started on port %s", port, silent=self.silent)
            if not port:
                raise GomaError("No Goma port detected")

        return goma_dir, port

    def Run(self):
        """Perform the command."""
        if os.environ.get(SDKFetcher.SDK_VERSION_ENV) is not None:
            cros_build_lib.Die("Already in an SDK shell.")

        # Migrate config file from old to new path.
        old_config = Path("~/.chromite/chrome_sdk.bashrc").expanduser()
        if (
            old_config.exists()
            and not chromite_config.CHROME_SDK_BASHRC.exists()
        ):
            chromite_config.initialize()
            old_config.rename(chromite_config.CHROME_SDK_BASHRC)
            try:
                old_config.parent.rmdir()
            except OSError:
                pass

        if self.options.chrome_branding or self.options.internal:
            gclient_path = gclient.FindGclientFile(self.options.chrome_src)
            if not gclient_path:
                cros_build_lib.Die(
                    "Found a Chrome checkout at %s with no .gclient file.",
                    self.options.chrome_src,
                )
            gclient_solutions = gclient.LoadGclientFile(gclient_path)
            for solution in gclient_solutions:
                if not solution.get("url", "").startswith(
                    gclient.CHROME_COMMITTER_URL
                ):
                    continue
                if solution.get("custom_vars", {}).get("checkout_src_internal"):
                    break
                cros_build_lib.Die(
                    "You've passed in '--chrome-branding' or '--internal' to "
                    "Simple Chrome, but your .gclient file at %s lacks "
                    "'checkout_src_internal'. Set that var to True in the "
                    "'custom_vars' section of your .gclient file and re-sync.",
                    gclient_path,
                )

        if self.options.version and self.options.sdk_path:
            cros_build_lib.Die("Cannot specify both --version and --sdk-path.")

        if self.options.cfi and not self.options.thinlto:
            cros_build_lib.Die("CFI requires ThinLTO.")

        # Fix read-only dirs in the cache.
        SDKFetcher.FixCachePermissions(self.options.cache_dir)

        # Remove old SDKs from the cache to avoid wasting disk space.
        SDKFetcher.ClearOldItems(self.options.cache_dir)

        if self.options.board:
            return self._RunOnceForBoard(self.options.board)
        else:
            for board in self.options.boards:
                start = datetime.datetime.now()
                self._RunOnceForBoard(board)
                duration = datetime.datetime.now() - start
                if duration > datetime.timedelta(minutes=1):
                    logging.warning(
                        "It took %s to fetch the SDK for %s. Consider removing "
                        "it from your .gclient file if you no longer need to "
                        "build for it.",
                        pformat.timedelta(duration),
                        board,
                    )

    def _RunOnceForBoard(self, board):
        """Internal implementation of Run() above for a single board."""
        self.silent = bool(self.options.cmd)
        # Lazy initialize because SDKFetcher creates a GSContext() object in its
        # constructor, which may block on user input.
        self.sdk = SDKFetcher(
            self.options.cache_dir,
            board,
            clear_cache=self.options.clear_sdk_cache,
            chrome_src=self.options.chrome_src,
            sdk_path=self.options.sdk_path,
            toolchain_path=self.options.toolchain_path,
            silent=self.silent,
            use_external_config=self.options.use_external_config,
            fallback_versions=self.options.fallback_versions,
            is_lacros=self.options.is_lacros,
        )

        prepare_version = self.options.version
        if not prepare_version and not self.options.sdk_path:
            prepare_version, _ = self.sdk.UpdateDefaultVersion()

        components = [self.sdk.TARGET_TOOLCHAIN_KEY, constants.CHROME_ENV_TAR]
        if not self.options.chroot:
            components.append(constants.CHROME_SYSROOT_TAR)
        components.append("autotest_server_package.tar.bz2")
        if self.options.download_vm:
            components.append(constants.TEST_IMAGE_TAR)

        goma_dir = None
        goma_port = None
        if self.options.goma and not self.options.use_remoteexec:
            try:
                goma_dir, goma_port = self._SetupGoma()
            except GomaError as e:
                logging.error("Goma: %s.  Bypass by running with --nogoma.", e)

        with self.sdk.Prepare(
            components,
            version=prepare_version,
            target_tc=self.options.target_tc,
            toolchain_url=self.options.toolchain_url,
        ) as ctx:
            env = self._SetupEnvironment(
                board, ctx, self.options, goma_dir=goma_dir, goma_port=goma_port
            )
            if not self.options.use_shell:
                return 0
            with self._GetRCFile(env, self.options.bashrc) as rcfile:
                bash_cmd = ["/bin/bash"]

                extra_env = None
                if not self.options.cmd:
                    bash_cmd.extend(["--rcfile", rcfile, "-i"])
                else:
                    # The '"$@"' expands out to the properly quoted positional
                    # args coming after the '--'.
                    bash_cmd.extend(["-c", '"$@"', "--"])
                    bash_cmd.extend(self.options.cmd)
                    # When run in noninteractive mode, bash sources the rc file
                    # set in BASH_ENV, and ignores the --rcfile flag.
                    extra_env = {"BASH_ENV": rcfile}

                # Bash behaves differently when it detects that it's being
                # launched by sshd - it ignores the BASH_ENV variable.  So
                # prevent ssh-related environment variables from being passed
                # through.
                os.environ.pop("SSH_CLIENT", None)
                os.environ.pop("SSH_CONNECTION", None)
                os.environ.pop("SSH_TTY", None)

                cmd_result = cros_build_lib.run(
                    bash_cmd,
                    print_cmd=False,
                    debug_level=logging.CRITICAL,
                    check=False,
                    extra_env=extra_env,
                    cwd=self.options.cwd,
                )
                if self.options.cmd:
                    return cmd_result.returncode
