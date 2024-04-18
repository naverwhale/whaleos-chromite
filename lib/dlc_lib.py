# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Library to generate a DLC (Downloadable Content) artifact."""

from __future__ import division

import hashlib
import json
import logging
import math
import os
import re
import shutil
from typing import Optional, Set
import zlib

from chromite.lib import build_target_lib
from chromite.lib import cros_build_lib
from chromite.lib import dlc_allowlist
from chromite.lib import gs
from chromite.lib import osutils
from chromite.lib import verity
from chromite.licensing import licenses_lib
from chromite.scripts import cros_set_lsb_release
from chromite.utils import pformat


# ChromiumOS Google Storage Buckets.
GS_LOCALMIRROR_BUCKET = "gs://chromeos-localmirror"

# ChromiumOS Google Storage Bucket related paths.
GS_DLC_IMAGES_DIR = "dlc-images"

# ChromiumOS Google Storage Bucket related values.
GS_PUBLIC_READ_ACL = "public-read"

DLC_BUILD_DIR = "build/rootfs/dlc"
DLC_BUILD_DIR_SCALED = "build/rootfs/dlc-scaled"
DLC_BUILD_DIR_ARTIFACTS_META = "build/rootfs/dlc-meta"
DLC_FACTORY_INSTALL_DIR = "unencrypted/dlc-factory-images"
DLC_DEPLOY_DIR = "unencrypted/dlc-deployed-images/"
DLC_DIR = "dlc"
DLC_DIR_SCALED = "dlc-scaled"
DLC_GID = 20118
DLC_IMAGE = "dlc.img"
DLC_LOADPIN_FILE_HEADER = "# LOADPIN_TRUSTED_VERITY_ROOT_DIGESTS"
DLC_LOADPIN_TRUSTED_VERITY_DIGESTS = "_trusted_verity_digests"
DLC_METADATA_UTIL = "dlc_metadata_util"
DLC_META_DIR = "opt/google/dlc"
DLC_META_FILE_PREFIX = "_metadata_"
DLC_META_FILE_SIZE_LIMIT = 4096
DLC_META_JSON_BEGIN = b"{"
DLC_META_JSON_END = b"}"
DLC_META_POWERWASH_SAFE_FILE = "_powerwash_safe_"
DLC_PACKAGE = "package"
DLC_TMP_META_DIR = "meta"
DLC_UID = 20118
DLC_VERITY_TABLE = "table"
EBUILD_PARAMETERS = "ebuild_parameters.json"
IMAGELOADER_JSON = "imageloader.json"
LICENSE = "LICENSE"
LSB_RELEASE = "etc/lsb-release"
POWERWASH_SAFE_KEY = "powerwash-safe"
URI_PREFIX = "uri-prefix"

IMAGELOADER_IMAGE_SHA256_HASH_KEY = "image-sha256-hash"

DLC_ID_RE = r"[a-zA-Z0-9][a-zA-Z0-9-]*"

# This is a special board that allows for out of band DLC build for builds that
# aren't associated with a specific board.
MAGIC_BOARD = "none"

# This file has major and minor version numbers that the update_engine client
# supports. These values are needed for generating a delta/full payload.
UPDATE_ENGINE_CONF = "etc/update_engine.conf"

_EXTRA_RESOURCES = (UPDATE_ENGINE_CONF,)
# The following boards don't have AppIds, but we allow DLCs to be generated for
# those boards for testing purposes.
_TEST_BOARDS_ALLOWLIST = (
    "amd64-generic",
    "amd64-generic-koosh",
    "arm64-generic",
    "arm-generic",
    "galaxy",
)

DLC_ID_KEY = "DLC_ID"
DLC_PACKAGE_KEY = "DLC_PACKAGE"
DLC_NAME_KEY = "DLC_NAME"
DLC_APPID_KEY = "DLC_RELEASE_APPID"

SQUASHFS_TYPE = "squashfs"
EXT4_TYPE = "ext4"

_MAX_ID_NAME = 80

_IMAGE_SIZE_NEARING_RATIO = 1.05
_IMAGE_SIZE_GROWTH_RATIO = 1.2


class Error(Exception):
    """Base class for dlc_lib errors."""


def CheckAndRaise(value: bool, err_msg: str) -> None:
    """Check and raises and exception with `err_msg` if `value` is False

    Raises:
        Error: on false `value`.
    """
    if not value:
        raise Error(err_msg)


def UniquePowerwashSafeDlcsInRootfs(rootfs: str) -> Set[str]:
    """Generates the DLC IDs that are powerwash safe.

    Args:
        rootfs: Path to the platform rootfs.

    Returns:
        A set of DLC IDs that are powerwash safe.

    Raises:
        Error: if rootfs DLC meta paths are malformed.
    """
    unique_powerwash_safe_dlc_ids = set()

    rootfs_meta_path = os.path.join(rootfs, DLC_META_DIR)
    CheckAndRaise(
        os.path.exists(rootfs_meta_path),
        f"Missing metadata path: {rootfs_meta_path}",
    )
    for dlc_id in os.listdir(rootfs_meta_path):
        rootfs_meta_json_path = os.path.join(
            rootfs_meta_path, dlc_id, DLC_PACKAGE, IMAGELOADER_JSON
        )
        if not os.path.exists(rootfs_meta_json_path):
            continue
        ValidateDlcIdentifier(dlc_id)
        if GetValueInJsonFile(
            json_path=rootfs_meta_json_path,
            key=POWERWASH_SAFE_KEY,
            default_value=False,
        ):
            unique_powerwash_safe_dlc_ids.add(dlc_id)

    return unique_powerwash_safe_dlc_ids


def CreatePowerwashSafeFileInRootfs(rootfs: str) -> None:
    """Creates the powerwash safe file in given rootfs.

    Args:
        rootfs: Path to the platform rootfs.

    Raises:
        Error: if rootfs DLC meta paths are malformed.
    """
    unique_powerwash_safe_dlc_ids = UniquePowerwashSafeDlcsInRootfs(rootfs)
    # Print list as powerwash-safe DLC list should not grow indefinitely.
    logging.info(
        "Creating powerwash safe metadata file containing %d DLCs: %s",
        len(unique_powerwash_safe_dlc_ids),
        unique_powerwash_safe_dlc_ids,
    )
    rootfs_meta_ps_file_path = os.path.join(
        rootfs, DLC_META_DIR, DLC_META_POWERWASH_SAFE_FILE
    )
    # Create even if empty.
    osutils.WriteFile(
        rootfs_meta_ps_file_path,
        "\n".join(unique_powerwash_safe_dlc_ids),
        makedirs=True,
        sudo=True,
    )


class DlcArtifacts:
    """Holds information about generated DLC artifacts.

    Attributes:
        image: The path to the DLC image.
        image_name: The DLC image name.
        image_hash: The hash of the DLC image.
        meta: The path to the DLC meta.
        uri_path: The URI path (dir) where artifacts should be uploaded.
    """

    def __init__(
        self,
        *,
        image: str,
        meta: str,
        uri_path: str = None,
    ):
        self.image = image
        self.image_name = os.path.basename(self.image)
        if self.image_name != DLC_IMAGE:
            err_msg = f"DLC image names should only be named {DLC_IMAGE}"
            logging.error(err_msg)
            raise Error(err_msg)
        if self.image:
            self.image_hash = HashFile(self.image)
        self.meta = meta
        self.uri_path = uri_path

    def StringJSON(self):
        """String format of this objects fields."""
        return pformat.json(self.__dict__)

    def Upload(self, dry_run: bool):
        """Uploads based on fields.

        Args:
            dry_run: Dry run without actual uploading.
        """
        gs_ctx = gs.GSContext(dry_run=dry_run)
        if self.uri_path:
            if self.image:
                gs_ctx.CopyInto(
                    self.image, self.uri_path, acl=GS_PUBLIC_READ_ACL
                )
            if self.meta:
                gs_ctx.CopyInto(
                    self.meta, self.uri_path, acl=GS_PUBLIC_READ_ACL
                )


def HashFile(file_path: str) -> str:
    """Calculate the sha256 hash of a file.

    Args:
        file_path: Path to the file.

    Returns:
        The sha256 hash of the file.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for b in iter(lambda: f.read(2048), b""):
            sha256.update(b)
    return sha256.hexdigest()


def GetValueInJsonFile(json_path: str, key: str, default_value=None):
    """Reads file containing JSON and returns value or default_value for key.

    Args:
        json_path: File containing JSON.
        key: The desired key to lookup.
        default_value: The default value returned in case of missing key.
    """
    with open(json_path, "rb") as fd:
        return json.load(fd).get(key, default_value)


class EbuildParams:
    """Object to store and retrieve DLC ebuild parameters.

    Attributes:
        dlc_id: (str) DLC ID.
        dlc_package: (str) DLC package.
        fs_type: (str) file system type.
        pre_allocated_blocks: (int) number of blocks pre-allocated on device.
        version: (str) DLC version.
        name: (str) DLC name.
        description: (str) DLC description.
        preload: (bool) allow for preloading DLC.
        factory_install: (bool) allow factory installing the DLC.
        mount_file_required: (bool) allow for mount file generation for DLC.
        reserved: (bool) always reserve space for DLC on disk.
        critical_update: (bool) DLC always updates with the OS.
        fullnamerev: (str) The full package & version name.
        loadpin_verity_digest: (bool) DLC digest is part of LoadPin trusted
            dm-verity digest.
        scaled: (bool) DLC will be fed through scaling design.
        powerwash_safe: (bool) DLC will be powerwash safe.
        use_logical_volume: (bool) DLC will use logical volumes on LVM stateful
            partition migrated devices.
    """

    def __init__(
        self,
        dlc_id,
        dlc_package,
        fs_type,
        pre_allocated_blocks,
        version,
        name,
        description,
        preload,
        mount_file_required,
        fullnamerev,
        reserved=False,
        critical_update=False,
        factory_install=False,
        loadpin_verity_digest=False,
        scaled=False,
        powerwash_safe=False,
        use_logical_volume=False,
        *args,  # pylint: disable=unused-argument
        **kwargs,  # pylint: disable=unused-argument
    ):
        """Initializes the object.

        When adding a new variable in here, always set a default value. The
        reason is that this class is sometimes used to load a pre-existing
        ebuild params JSON file (through bin packages) and that file may not
        contain the new argument. So the build will fail.
        """
        self.dlc_id = dlc_id
        self.dlc_package = dlc_package
        self.fs_type = fs_type
        self.pre_allocated_blocks = pre_allocated_blocks
        self.version = version
        self.name = name
        self.description = description
        self.preload = preload
        self.factory_install = factory_install
        self.mount_file_required = mount_file_required
        self.fullnamerev = fullnamerev
        self.reserved = reserved
        self.critical_update = critical_update
        self.loadpin_verity_digest = loadpin_verity_digest
        self.scaled = scaled
        self.powerwash_safe = powerwash_safe
        self.use_logical_volume = use_logical_volume

    def GetUriPath(self) -> str:
        """Retrieves the DLC image URI path based on field values"""
        CheckAndRaise(self.dlc_id, "Missing DLC ID")
        CheckAndRaise(self.dlc_package, "Missing DLC package")
        CheckAndRaise(self.version, "Missing DLC version")
        return "/".join(
            (
                GS_LOCALMIRROR_BUCKET,
                GS_DLC_IMAGES_DIR,
                self.dlc_id,
                self.dlc_package,
                self.version,
            )
        )

    def VerifyDlcParameters(self):
        """Verifies certain DLC parameters are valid and allowed.

        Raises:
            Error: if non-allowlisted in various DLC options.
        """
        if self.factory_install:
            if not dlc_allowlist.IsFactoryInstallAllowlisted(self.dlc_id):
                err_msg = (
                    f"DLC={self.dlc_id} is not allowed to be factory installed."
                )
                logging.error(err_msg)
                raise Error(err_msg)
        if self.powerwash_safe:
            if not dlc_allowlist.IsPowerwashSafeAllowlisted(self.dlc_id):
                err_msg = (
                    f"DLC={self.dlc_id} is not allowed to be powerwash safe."
                )
                logging.error(err_msg)
                raise Error(err_msg)

    def StoreDlcParameters(self, install_root_dir: str, sudo: bool):
        """Store DLC parameters defined in the ebuild.

        Store DLC parameters defined in the ebuild in a temporary file so they
        can be retrieved in the `cros build-image` phase.

        Args:
            install_root_dir: The path to the root installation directory.
            sudo: Use sudo to write the file.
        """
        ebuild_params_path = EbuildParams.GetParamsPath(
            install_root_dir,
            self.dlc_id,
            self.dlc_package,
            self.scaled,
        )
        osutils.WriteFile(
            ebuild_params_path,
            json.dumps(self.__dict__),
            makedirs=True,
            sudo=sudo,
        )

    @staticmethod
    def GetParamsPath(
        install_root_dir: str, dlc_id: str, dlc_package: str, scaled: bool
    ) -> str:
        """Get the path to the file storing the ebuild parameters.

        Args:
            install_root_dir: The path to the root installation directory.
            dlc_id: DLC ID.
            dlc_package: DLC package.
            scaled: Scaled DLC option.

        Returns:
            [str]: Path to |EBUILD_PARAMETERS|.
        """
        return os.path.join(
            install_root_dir,
            DLC_BUILD_DIR_SCALED if scaled else DLC_BUILD_DIR,
            dlc_id,
            dlc_package,
            EBUILD_PARAMETERS,
        )

    @classmethod
    def LoadEbuildParams(
        cls, sysroot: str, dlc_id: str, dlc_package: str, scaled: bool
    ) -> bool:
        """Read the stored ebuild parameters file and return a class instance.

        Args:
            dlc_id: DLC ID.
            dlc_package: DLC package.
            sysroot: The path to the build root directory.
            scaled: Scaled DLC option.

        Returns:
            True if |ebuild_params_path| exists, False otherwise.
        """
        path = cls.GetParamsPath(sysroot, dlc_id, dlc_package, scaled)
        if not os.path.exists(path):
            return None

        with open(path, "rb") as fp:
            return cls(**json.load(fp))

    def __str__(self):
        return str(self.__dict__)


# TODO(yuanpengni): Create a utility to use the metadata library from dlcservice
# so that the implementation of DLC metadata creation and on-device modification
# is in sync.
class DlcMetadata:
    """The class to create and read DLC metadata.

    The DLC metadata consists of metadata files. The metadata file contains
    compressed DLC metadata in json dict entries:
    <id>:{<package>:{"manifest":<manifest>,"table":<table>}},
    Multiple DLC metadata are grouped and compressed together as a file. The
    metadata files are named with the first of ascending DLC IDs it contains.
    """

    def __init__(
        self,
        metadata_path: str,
        max_file_size: int = DLC_META_FILE_SIZE_LIMIT,
        sudo: bool = False,
    ):
        """Object initializer.

        Args:
            metadata_path: The path to the metadata directory.
            max_file_size: The max size of each metadata file, align with
                           file system block size to get better efficiency.
            sudo: Write files as root.
        """
        self._metadata_path = metadata_path
        self._max_file_size = max_file_size
        self._sudo = sudo

        self._compressobj = zlib.compressobj(
            level=zlib.Z_BEST_COMPRESSION, wbits=-zlib.MAX_WBITS
        )
        # The buffer for creating compressed metadata files.
        self._compressed = bytearray()

        osutils.SafeMakedirs(path=metadata_path, sudo=sudo)

    def __enter__(self):
        """Enter the context and clear the existing metadata.

        Makes it ready for creating new metadata.
        """
        self.Clear()
        return self

    def __exit__(self, *args):
        """Exit the context"""

    def _CompressionSize(self, compressobj, metadata: bytes) -> int:
        """Estimate the compressed size of given metadata

        Compress and flush with a copy of compression object and get the size.

        Args:
            compressobj: The zlib compression object. This method will not
                         change the internal state of the object.
            metadata: The metadata for calculating the size after compression.

        Returns:
            The expected size after compress and full flush.
        """
        compressobj_copy = compressobj.copy()
        compress_size = len(compressobj_copy.compress(metadata))
        flushed_size = len(compressobj_copy.flush(zlib.Z_FULL_FLUSH))
        return compress_size + flushed_size

    def Clear(self):
        """Clear existing metadata files"""
        for f in self.ListFiles():
            osutils.SafeUnlink(
                os.path.join(self._metadata_path, f"{DLC_META_FILE_PREFIX}{f}"),
                self._sudo,
            )

    def Create(self, dlc_list: list):
        """Create DLC metadata from the source manifest and table files.

        Args:
            dlc_list: A list of tuples (dlc_id, build_dir)

        Raises:
            Error: if metadata is missing/compresses badly.
        """
        # The first of ascending DLC IDs added to current metadata file, it will
        # be used to name the metadata file.
        min_id = None
        for d_id, dlc_build_dir in sorted(dlc_list):
            metadata = self.LoadSrcMetadata(os.path.join(dlc_build_dir, d_id))
            if not metadata:
                raise Error(f"Unable to load metadata for DLC '{d_id}'.")

            metadata_str = json.dumps(metadata, separators=(",", ":"))
            metadata_enc = f'"{d_id}":{metadata_str},'.encode("utf-8")

            if (
                len(self._compressed)
                + self._CompressionSize(self._compressobj, metadata_enc)
                > self._max_file_size
            ):
                self.FlushCompressed(min_id)
                min_id = None

                if (
                    self._CompressionSize(self._compressobj, metadata_enc)
                    > self._max_file_size
                ):
                    raise Error(
                        f"Unable to add metadata for DLC '{d_id}' as it "
                        "exceeds the file size limit."
                    )

            self._compressed.extend(self._compressobj.compress(metadata_enc))
            if min_id is None:
                min_id = d_id

        self.FlushCompressed(min_id)
        logging.info("Created metadata for %d DLCs", len(dlc_list))

    def FlushCompressed(self, file_id: str):
        """Write the compressed metadata buffer to a file and reset the state.

        The metadata file name is the first of ascending DLC IDs added to the
        buffer.

        Args:
            file_id: The metadata file will be named `file_prefix``file_id`.
        """
        self._compressed.extend(self._compressobj.flush(zlib.Z_FULL_FLUSH))
        if file_id:
            assert len(self._compressed) > 0
            osutils.WriteFile(
                os.path.join(
                    self._metadata_path, f"{DLC_META_FILE_PREFIX}{file_id}"
                ),
                bytes(self._compressed),
                mode="wb",
                sudo=self._sudo,
            )
        self._compressed.clear()

    @staticmethod
    def LoadSrcMetadata(src_dir: str) -> dict:
        """Read manifest and table from the source directory and make metadata.

        Args:
            src_dir: The source dlc metadata directory.

        Returns:
            The metadata as a dict.
        """
        if not os.path.isdir(src_dir):
            return None

        for pkg in os.listdir(src_dir):
            for pkg_path in (
                os.path.join(src_dir, pkg, DLC_TMP_META_DIR),
                os.path.join(src_dir, pkg),
            ):
                if not os.path.isdir(pkg_path):
                    continue
                try:
                    with open(
                        os.path.join(pkg_path, IMAGELOADER_JSON),
                        encoding="utf-8",
                    ) as f:
                        manifest = json.load(f)
                    table = osutils.ReadFile(
                        os.path.join(pkg_path, DLC_VERITY_TABLE),
                        mode="rb",
                    ).strip()
                except Exception as e:
                    logging.error("Failed to read the source metadata: %s.", e)
                    continue

                if pkg != DLC_PACKAGE:
                    logging.warning(
                        "The package name should be '%s', but getting '%s' "
                        "from the source metadata directory %s",
                        DLC_PACKAGE,
                        pkg,
                        src_dir,
                    )
                return {
                    "manifest": manifest,
                    "table": table.decode("utf-8"),
                }

    def LoadDestMetadata(self, file_id: str) -> dict:
        """Load a metadata file from the destination directory and parse it.

        Args:
            file_id: The suffix name of the file to be loaded. It equals to
                     the first of ascending DLC IDs in the file.

        Returns:
            The metadata as a dict.

        Raises:
            Error: if parsed metadata is badly formatted.
        """
        # Read the file content and decompress.
        contents = osutils.ReadFile(
            os.path.join(
                self._metadata_path, f"{DLC_META_FILE_PREFIX}{file_id}"
            ),
            mode="rb",
        )
        decompressobj = zlib.decompressobj(wbits=-zlib.MAX_WBITS)
        decompressed = bytearray(decompressobj.decompress(contents))
        decompressed.extend(decompressobj.flush())

        # Parse json.
        parsed = json.loads(
            DLC_META_JSON_BEGIN + decompressed.rstrip(b",") + DLC_META_JSON_END
        )
        if not isinstance(parsed, dict):
            raise Error("The metadata file is corrupted.")

        return parsed

    def ListFiles(self) -> list:
        """List metadata files in the `self._metadata_path`.

        Returns:
            The metadata file list.
        """
        return [
            f[len(DLC_META_FILE_PREFIX) :]
            for f in os.listdir(self._metadata_path)
            if f.startswith(DLC_META_FILE_PREFIX) and f != DLC_META_FILE_PREFIX
        ]


class DlcGenerator:
    """Object to generate DLC artifacts."""

    # Block size for the DLC image.
    # We use 4K for various reasons:
    # 1. it's what imageloader (linux kernel) supports.
    # 2. it's what verity supports.
    _BLOCK_SIZE = 4096
    # Blocks in the initial sparse image.
    _BLOCKS = 500000
    # Version of manifest file.
    _MANIFEST_VERSION = 1

    # The DLC root path inside the DLC module.
    _DLC_ROOT_DIR = "root"

    def __init__(
        self,
        ebuild_params: EbuildParams,
        sysroot: str,
        board: str,
        src_dir: str = None,
        reproducible: bool = False,
        license_file: os.PathLike = None,
    ):
        """Object initializer.

        Args:
            sysroot: The path to the build root directory.
            ebuild_params: Ebuild variables.
            board: The target board we are building for.
            src_dir: Optional path to the DLC source root directory. When
                None, the default directory in |DLC_BUILD_DIR| is used.
            reproducible: Generates a completely reproducible squash image that
                produces identical bits each gen. (Only applicable to squashfs)
            license_file: Optional license file, but required for prebuilt DLCs.
        """
        # Use a temporary directory to avoid having to use sudo every time we
        # write into the build directory.
        self.temp_root = osutils.TempDir(prefix="dlc", sudo_rm=True)
        self.src_dir = src_dir
        self.sysroot = sysroot
        self.board = board
        self.ebuild_params = ebuild_params
        self.reproducible = reproducible
        self.license_file = license_file

        build_dir = (
            DLC_BUILD_DIR_SCALED if ebuild_params.scaled else DLC_BUILD_DIR
        )
        # If the client is not overriding the src_dir, use the default one.
        if not self.src_dir:
            self.src_dir = os.path.join(
                self.sysroot,
                build_dir,
                self.ebuild_params.dlc_id,
                self.ebuild_params.dlc_package,
                self._DLC_ROOT_DIR,
            )

        self.image_dir = os.path.join(
            self.temp_root.tempdir,
            build_dir,
            self.ebuild_params.dlc_id,
            self.ebuild_params.dlc_package,
        )

        self.meta_dir = os.path.join(self.image_dir, DLC_TMP_META_DIR)
        osutils.SafeMakedirs(self.meta_dir)

        # Create path for all final artifacts.
        self.dest_image = os.path.join(self.image_dir, DLC_IMAGE)
        self.dest_table = os.path.join(self.meta_dir, "table")
        self.dest_imageloader_json = os.path.join(
            self.meta_dir, IMAGELOADER_JSON
        )

        # Log out the member variable values initially set.
        logging.debug(
            "Initial internal values of DlcGenerator: %s",
            repr({k: str(i) for k, i in self.__dict__.items()}),
        )

    def CopyTempContentsToBuildDir(self):
        """Copy the temp files to the build directory using sudo."""
        src = self.temp_root.tempdir.rstrip("/") + "/."
        dst = self.sysroot
        logging.debug(
            "Copy files from temporary directory (%s) to build directory (%s).",
            src,
            dst,
        )
        cros_build_lib.sudo_run(["cp", "-dR", src, dst])

    def CopyArtifactsToOutput(self, output: str):
        """Copy the artifacts to the output directory."""
        files = (self.dest_image, self.meta_dir)
        logging.debug("Copying %s to %s", files, output)
        cros_build_lib.sudo_run(["cp", "-r", *files, output])

    def SquashOwnerships(self, path: str):
        """Squash the ownerships & permissions for files.

        Args:
            path: The path that contains all files to be processed.
        """
        cros_build_lib.sudo_run(["chown", "-R", "0:0", path])
        cros_build_lib.sudo_run(
            [
                "find",
                path,
                "-exec",
                "touch",
                "-h",
                "-t",
                "197001010000.00",
                "{}",
                "+",
            ]
        )

    def CreateExt4Image(self):
        """Create an ext4 image."""
        with osutils.TempDir(prefix="dlc_") as temp_dir:
            mount_point = os.path.join(temp_dir, "mount_point")
            # Create a raw image file.
            osutils.AllocateFile(
                self.dest_image, self._BLOCKS * self._BLOCK_SIZE, makedirs=True
            )
            # Create an ext4 file system on the raw image.
            cros_build_lib.run(
                [
                    "/sbin/mkfs.ext4",
                    "-b",
                    str(self._BLOCK_SIZE),
                    "-O",
                    "^has_journal",
                    self.dest_image,
                ],
                capture_output=True,
            )
            # Create the mount_point directory.
            osutils.SafeMakedirs(mount_point)
            # Mount the ext4 image.
            osutils.MountDir(
                self.dest_image, mount_point, mount_opts=("loop", "rw")
            )

            try:
                self.SetupDlcImageFiles(mount_point)
            finally:
                # Unmount the ext4 image.
                osutils.UmountDir(mount_point)
            # Shrink to minimum size.
            cros_build_lib.run(
                ["/sbin/e2fsck", "-y", "-f", self.dest_image],
                capture_output=True,
            )
            cros_build_lib.run(
                ["/sbin/resize2fs", "-M", self.dest_image], capture_output=True
            )

    def CreateSquashfsImage(self):
        """Create a squashfs image."""
        with osutils.TempDir(prefix="dlc_") as temp_dir:
            squashfs_root = os.path.join(temp_dir, "squashfs-root")
            self.SetupDlcImageFiles(squashfs_root)

            mksquashfs = [
                "mksquashfs",
                squashfs_root,
                self.dest_image,
                "-4k-align",
                "-noappend",
            ]
            if self.reproducible:
                mksquashfs.extend(
                    [
                        "-mkfs-time",
                        "0",
                        "-all-time",
                        "0",
                    ]
                )

            ret = cros_build_lib.run(
                mksquashfs,
                capture_output=True,
            )
            logging.debug(ret.stdout)

            # Verity cannot create hashes for device images which are less than
            # two pages in size. So fix this squashfs image if it's too small.
            # Check out b/187725419 for details.
            if os.path.getsize(self.dest_image) < self._BLOCK_SIZE * 2:
                logging.warning(
                    "Increasing DLC image size to at least two pages."
                )
                os.truncate(self.dest_image, self._BLOCK_SIZE * 2)

            # Verify that the generated squashfs is valid and compressed
            # correctly without any corruption.
            # Refer to b/303628900 for details.
            squashfs_out = os.path.join(temp_dir, "squashfs-out")
            ret = cros_build_lib.run(
                [
                    "unsquashfs",
                    "-d",
                    squashfs_out,
                    self.dest_image,
                ],
                capture_output=True,
            )
            logging.debug(ret.stdout)

            # We changed the ownership and permissions of the squashfs_root
            # directory. Now we need to remove it manually.
            osutils.RmDir(squashfs_root, sudo=True)
            osutils.RmDir(squashfs_out, sudo=True)

    def SetupDlcImageFiles(self, dlc_dir: str):
        """Prepares the directory dlc_dir with all the files a DLC needs.

        Args:
            dlc_dir: The path to where to setup files inside the DLC.
        """
        dlc_root_dir = os.path.join(dlc_dir, self._DLC_ROOT_DIR)
        osutils.SafeMakedirs(dlc_root_dir)
        osutils.CopyDirContents(self.src_dir, dlc_root_dir, symlinks=True)
        self.PrepareLsbRelease(dlc_dir)
        self.AddLicensingFile(dlc_dir)
        self.CollectExtraResources(dlc_dir)
        self.SquashOwnerships(dlc_dir)

    def PrepareLsbRelease(self, dlc_dir: str):
        """Prepare the file /etc/lsb-release in the DLC module.

        This file is used dropping some identification parameters for the DLC.

        Args:
            dlc_dir: The path to the mounted point during image creation.

        Raises:
            Error: if key from lsb-release is missing.
        """
        if self.board == MAGIC_BOARD:
            logging.info("Skipping lsb prep since magic board.")
            return

        app_id = None
        platform_lsb_rel_path = os.path.join(self.sysroot, LSB_RELEASE)
        if os.path.isfile(platform_lsb_rel_path):
            # Reading the platform APPID and creating the DLC APPID.
            platform_lsb_release = osutils.ReadFile(platform_lsb_rel_path)
            for line in platform_lsb_release.split("\n"):
                if line.startswith(cros_set_lsb_release.LSB_KEY_APPID_RELEASE):
                    app_id = line.split("=")[1]

        if app_id is None and self.board not in _TEST_BOARDS_ALLOWLIST:
            raise Error(
                "%s does not have a valid key %s"
                % (
                    platform_lsb_rel_path,
                    cros_set_lsb_release.LSB_KEY_APPID_RELEASE,
                )
            )

        fields = (
            (DLC_ID_KEY, self.ebuild_params.dlc_id),
            (DLC_PACKAGE_KEY, self.ebuild_params.dlc_package),
            (DLC_NAME_KEY, self.ebuild_params.name),
            # The DLC appid is generated by concatenating the platform appid
            # with the DLC ID using an underscore. This pattern should never be
            # changed once set otherwise it can break a lot of things!
            (
                DLC_APPID_KEY,
                "%s_%s" % (app_id if app_id else "", self.ebuild_params.dlc_id),
            ),
        )

        lsb_release = os.path.join(dlc_dir, LSB_RELEASE)
        osutils.SafeMakedirs(os.path.dirname(lsb_release))
        content = "".join("%s=%s\n" % (k, v) for k, v in fields)
        osutils.WriteFile(lsb_release, content)

    def AddLicensingFile(self, dlc_dir: str):
        """Add the licensing file for this DLC.

        Args:
            dlc_dir: The path to the mounted point during image creation.

        Raises:
            Error: if license file is missing.
        """
        license_path = os.path.join(dlc_dir, LICENSE)
        if self.board == MAGIC_BOARD:
            if not self.license_file or not os.path.exists(self.license_file):
                raise Error("License file missing")
            shutil.copyfile(self.license_file, license_path)
            return

        if not self.ebuild_params.fullnamerev:
            return

        sysroot = build_target_lib.get_default_sysroot_path(self.board)
        licensing = licenses_lib.Licensing(
            sysroot, [self.ebuild_params.fullnamerev], True
        )
        licensing.LoadPackageInfo()
        licensing.ProcessPackageLicenses()
        licenses = licensing.GenerateLicenseText()
        # The first (and only) item contains the values for |self.fullnamerev|.
        if licenses:
            _, license_txt = next(iter(licenses.items()))
            osutils.WriteFile(license_path, license_txt)
        else:
            logging.info(
                "LICENSE text is empty. Skipping LICENSE file creation."
            )

    def CollectExtraResources(self, dlc_dir: str):
        """Collect the extra resources needed by the DLC module.

        Look at the documentation around _EXTRA_RESOURCES.

        Args:
            dlc_dir: The path to the mounted point during image creation.
        """
        if self.board == MAGIC_BOARD:
            logging.info("Skipping extra collection since magic board.")
            return

        for r in _EXTRA_RESOURCES:
            source_path = os.path.join(self.sysroot, r)
            target_path = os.path.join(dlc_dir, r)
            osutils.SafeMakedirs(os.path.dirname(target_path))
            shutil.copyfile(source_path, target_path)

    def CreateImage(self):
        """Create the image and copy the DLC files to it."""
        logging.debug("Creating the DLC image.")
        if self.ebuild_params.fs_type == EXT4_TYPE:
            self.CreateExt4Image()
        elif self.ebuild_params.fs_type == SQUASHFS_TYPE:
            self.CreateSquashfsImage()
        else:
            raise ValueError(
                "Wrong fs type: %s used:" % self.ebuild_params.fs_type
            )

    def VerifyImageSize(self):
        """Verify the image can fit to the reserved file."""
        logging.debug("Verifying the DLC image size.")
        image_bytes = os.path.getsize(self.dest_image)
        preallocated_bytes = (
            self.ebuild_params.pre_allocated_blocks * self._BLOCK_SIZE
        )
        # Verifies the actual size of the DLC image is NOT larger than the
        # preallocated space.
        if preallocated_bytes < image_bytes:
            raise ValueError(
                "The DLC_PREALLOC_BLOCKS (%s) value set in DLC ebuild resulted "
                "in a max size of DLC_PREALLOC_BLOCKS * 4K (%s) bytes the DLC "
                "image is allowed to occupy. The value is smaller than the "
                "actual image size (%s) required. Increase DLC_PREALLOC_BLOCKS "
                "in your ebuild to at least %d."
                % (
                    self.ebuild_params.pre_allocated_blocks,
                    preallocated_bytes,
                    image_bytes,
                    self.GetOptimalImageBlockSize(image_bytes),
                )
            )

        image_size_ratio = preallocated_bytes / image_bytes

        # Warn if the DLC image size is nearing the preallocated size.
        if image_size_ratio <= _IMAGE_SIZE_NEARING_RATIO:
            logging.warning(
                "The %s DLC image size (%s) is nearing the preallocated size "
                "(%s).",
                self.ebuild_params.dlc_id,
                image_bytes,
                preallocated_bytes,
            )

        # Warn if the DLC preallocated size is too much.
        if image_size_ratio >= _IMAGE_SIZE_GROWTH_RATIO:
            logging.warning(
                "The %s DLC image size (%s) is significantly less than the "
                "preallocated size (%s). Reduce the DLC_PREALLOC_BLOCKS in "
                "your ebuild",
                self.ebuild_params.dlc_id,
                image_bytes,
                preallocated_bytes,
            )

    def GetOptimalImageBlockSize(self, image_bytes):
        """Given the image bytes, get the least amount of blocks required."""
        return int(math.ceil(image_bytes / self._BLOCK_SIZE))

    def GetImageloaderJsonContent(
        self, image_hash: str, table_hash: str, blocks: int
    ) -> str:
        """Return the content of imageloader.json file.

        Args:
            image_hash: The sha256 hash of the DLC image.
            table_hash: The sha256 hash of the DLC table file.
            blocks: The number of blocks in the DLC image.

        Returns:
            The content of imageloader.json file.
        """
        return {
            "fs-type": self.ebuild_params.fs_type,
            "id": self.ebuild_params.dlc_id,
            "package": self.ebuild_params.dlc_package,
            "image-sha256-hash": image_hash,
            "image-type": "dlc",
            "is-removable": True,
            "manifest-version": self._MANIFEST_VERSION,
            "name": self.ebuild_params.name,
            "description": self.ebuild_params.description,
            "pre-allocated-size": str(
                self.ebuild_params.pre_allocated_blocks * self._BLOCK_SIZE
            ),
            "size": str(blocks * self._BLOCK_SIZE),
            "table-sha256-hash": table_hash,
            "version": self.ebuild_params.version,
            "preload-allowed": self.ebuild_params.preload,
            "factory-install": self.ebuild_params.factory_install,
            "mount-file-required": self.ebuild_params.mount_file_required,
            "reserved": self.ebuild_params.reserved,
            "critical-update": self.ebuild_params.critical_update,
            "loadpin-verity-digest": self.ebuild_params.loadpin_verity_digest,
            "scaled": self.ebuild_params.scaled,
            # All scaled enabled DLCs will by default use logical volume, even
            # when usage of logical volumes are force disabled.
            # Legacy DLCs are allowed to use logical volumes as well.
            "use-logical-volume": (
                self.ebuild_params.scaled
                or self.ebuild_params.use_logical_volume
            ),
            "powerwash-safe": self.ebuild_params.powerwash_safe,
        }

    def GenerateVerity(self, salt: Optional[str] = None):
        """Generate verity parameters and hashes for the image.

        Args:
            salt: An optional hex string to salt verity gen. Please refer
                to details of verity userspace tool to determine max length.
        """
        logging.debug("Generating DLC image verity.")
        with osutils.TempDir(prefix="dlc_") as temp_dir:
            hash_tree = os.path.join(temp_dir, "hash_tree")
            # Get blocks in the image.
            blocks = math.ceil(
                os.path.getsize(self.dest_image) / self._BLOCK_SIZE
            )
            result = cros_build_lib.run(
                [
                    "verity",
                    "--mode=create",
                    "--alg=sha256",
                    f"--payload={self.dest_image}",
                    f"--payload_blocks={blocks}",
                    f"--hashtree={hash_tree}",
                    f"--salt={salt if salt else 'random'}",
                ],
                capture_output=True,
            )
            table = result.stdout

            # Append the merkle tree to the image.
            osutils.WriteFile(
                self.dest_image,
                osutils.ReadFile(hash_tree, mode="rb"),
                mode="a+b",
            )

            # Write verity parameter to table file.
            osutils.WriteFile(self.dest_table, table, mode="wb")

            # Compute image hash.
            image_hash = HashFile(self.dest_image)
            table_hash = HashFile(self.dest_table)
            # Write image hash to imageloader.json file.
            blocks = math.ceil(
                os.path.getsize(self.dest_image) / self._BLOCK_SIZE
            )
            imageloader_json_content = self.GetImageloaderJsonContent(
                image_hash, table_hash, int(blocks)
            )
            pformat.json(
                imageloader_json_content, fp=self.dest_imageloader_json
            )

    def GenerateDLC(self):
        """Generate a DLC artifact."""
        # Create directories.
        osutils.SafeMakedirs(self.image_dir)
        osutils.SafeMakedirs(self.meta_dir)

        # Create the image into |self.temp_root| and copy the DLC files to it.
        self.CreateImage()
        # Verify the image created is within pre-allocated size.
        self.VerifyImageSize()
        # Generate hash tree and other metadata and save them under
        # |self.temp_root|.
        self.GenerateVerity()
        # Copy the files from |self.temp_root| into the build directory.
        self.CopyTempContentsToBuildDir()

        # Now that the image was successfully generated, delete
        # |ebuild_params_path| to indicate that the image in the build directory
        # is in sync with the files installed during the build_package phase.
        ebuild_params_path = EbuildParams.GetParamsPath(
            self.sysroot,
            self.ebuild_params.dlc_id,
            self.ebuild_params.dlc_package,
            self.ebuild_params.scaled,
        )
        osutils.SafeUnlink(ebuild_params_path, sudo=True)

    def ExternalGenerateDLC(
        self, output: str, salt: Optional[str] = None
    ) -> DlcArtifacts:
        """Generate the DLC artifacts from external / non-SDK builds

        Args:
            output: Path in which generated contents are emitted.
            salt: An optional salt for randomness.

        Returns:
            The `DlcArtifacts` class.
        """
        self.CreateImage()
        self.VerifyImageSize()
        self.GenerateVerity(salt=salt)
        self.CopyArtifactsToOutput(output)
        return DlcArtifacts(
            image=os.path.join(output, DLC_IMAGE),
            meta=os.path.join(output, DLC_TMP_META_DIR),
        )


def IsFieldAllowed(dlc_id: str, dlc_build_dir: str, field: str):
    """Checks if a field is allowed.

    Args:
        dlc_id: TheDLC ID.
        dlc_build_dir: The root path where DLC build files reside.
        field: The field name in the metadata json.
    """
    dlc_id_dir = os.path.join(dlc_build_dir, dlc_id)
    if not os.path.exists(dlc_id_dir):
        return False

    for package in os.listdir(dlc_id_dir):
        image_loader_json = os.path.join(
            dlc_id_dir, package, DLC_TMP_META_DIR, IMAGELOADER_JSON
        )
        if not os.path.exists(image_loader_json):
            return False
        if not GetValueInJsonFile(
            json_path=image_loader_json, key=field, default_value=False
        ):
            return False

    return True


def IsDlcPreloadingAllowed(dlc_id: str, dlc_build_dir: str):
    """Validates that DLC is built with DLC_PRELOAD=true.

    Args:
        dlc_id: The DLC ID.
        dlc_build_dir: The root path where DLC build files reside.
    """
    return IsFieldAllowed(dlc_id, dlc_build_dir, "preload-allowed")


def IsFactoryInstallAllowed(dlc_id: str, dlc_build_dir: str) -> bool:
    """Validates that DLC is built with DLC_FACTORY_INSTALL=true.

    Args:
        dlc_id: The DLC ID.
        dlc_build_dir: The root path where DLC build files reside.

    Returns:
        Whether the factory installation for the DLC is allowed.

    Raises:
        Error: if factory install is not allowed.
    """
    if not IsFieldAllowed(dlc_id, dlc_build_dir, "factory-install"):
        return False

    if not dlc_allowlist.IsFactoryInstallAllowlisted(dlc_id):
        err_msg = f"DLC={dlc_id} is not allowed to be factory installed."
        logging.error(err_msg)
        raise Error(err_msg)

    return True


def IsPowerwashSafeAllowed(dlc_id: str, dlc_build_dir: str) -> bool:
    """Validates that DLC is built with DLC_POWERWASH_SAFE=true.

    Args:
        dlc_id: The DLC ID.
        dlc_build_dir: The root path where DLC build files reside.

    Returns:
        Whether powerwash safety for the DLC is allowed.

    Raises:
        Error: if powerwash safety is not allowed.
    """
    if not IsFieldAllowed(dlc_id, dlc_build_dir, "powerwash-safe"):
        return False

    if not dlc_allowlist.IsPowerwashSafeAllowlisted(dlc_id):
        err_msg = f"DLC={dlc_id} is not allowed to be powerwash safe."
        logging.error(err_msg)
        raise Error(err_msg)

    return True


def IsLoadPinVerityDigestAllowed(dlc_id: str, dlc_build_dir: str) -> bool:
    """Checks that DLC is built with DLC_LOADPIN_VERITY_DIGEST set to true.

    Args:
        dlc_id: The DLC ID.
        dlc_build_dir: The root path where DLC build files reside.

    Returns:
        Boolean based on field being true or false.
    """
    return IsFieldAllowed(dlc_id, dlc_build_dir, "loadpin-verity-digest")


def InstallArtifactsMeta(sysroot: str, rootfs: str) -> None:
    """Installs the artifacts DLC meta(data) into rootfs

    Args:
        sysroot: Path to directory containing DLC images, e.g /build/<board>.
        rootfs: Path to the platform rootfs.
    """
    artifacts_meta_dir = os.path.join(sysroot, DLC_BUILD_DIR_ARTIFACTS_META)
    if not os.path.exists(artifacts_meta_dir):
        logging.info("Artifacts meta directory missing, ignoring.")
        return

    artifacts_meta_dlc_ids = sorted(os.listdir(artifacts_meta_dir))
    if not artifacts_meta_dlc_ids:
        logging.info("There are no artifacts meta DLC(s), ignoring.")
        return

    logging.info(
        "Detected artifacts meta for %d DLCs.", len(artifacts_meta_dlc_ids)
    )

    # TODO(b/290961240): Remove copying individual imageloader.json
    # and table files after fully migrated to used the compressed
    # metadata (replace this code with a `pass` for future usage).
    for artifacts_meta_dlc_id in artifacts_meta_dlc_ids:
        # Only support single package for artifacts meta DLC(s).
        if rootfs:
            src_path = os.path.join(
                artifacts_meta_dir, artifacts_meta_dlc_id, DLC_PACKAGE
            )
            dst_path = os.path.join(
                rootfs, DLC_META_DIR, artifacts_meta_dlc_id, DLC_PACKAGE
            )
            osutils.SafeMakedirs(dst_path, sudo=True)
            # Copy the metadata files to rootfs.
            logging.debug(
                "Copying DLC(%s) metadata from %s to %s: ",
                artifacts_meta_dlc_id,
                src_path,
                dst_path,
            )
            # Use sudo_run since osutils.CopyDirContents doesn't support
            # sudo.
            cros_build_lib.sudo_run(
                [
                    "cp",
                    "-dR",
                    src_path.rstrip("/") + "/.",
                    dst_path,
                ],
                debug_level=logging.DEBUG,
                stderr=True,
            )


def InstallDlcImages(
    sysroot: str,
    board: str,
    dlc_id: str = None,
    install_root_dir: str = None,
    preload: bool = False,
    factory_install: bool = False,
    rootfs: str = None,
    stateful: str = None,
    src_dir: str = None,
):
    """Copies all DLC image files into the images directory.

    Copies the DLC image files in the given build directory into the given DLC
    image directory. If the DLC build directory does not exist, or there is no
    DLC for that board, this function does nothing.

    Args:
        sysroot: Path to directory containing DLC images, e.g /build/<board>.
        board: The target board we are building for.
        dlc_id: The DLC ID. If None, all the DLCs will be installed.
        install_root_dir: Path to DLC output directory, e.g.
            src/build/images/<board>/<version>. If None, the image will be
            generated but will not be copied to a destination.
        preload: When true, only copies DLC(s) if built with DLC_PRELOAD=true.
        factory_install: When true, copies DLC(s) built with
            DLC_FACTORY_INSTALL=true.
        rootfs: Path to the platform rootfs.
        stateful: Path to the platform stateful.
        src_dir: Path to the DLC source root directory.

    Raises:
        Error: in case anything goes wrong, check error message.
    """
    # Handle the artifacts meta DLC(s).
    InstallArtifactsMeta(sysroot, rootfs)
    build_dir = os.path.join(sysroot, DLC_BUILD_DIR)
    build_dir_scaled = os.path.join(sysroot, DLC_BUILD_DIR_SCALED)
    build_dir_artifacts_meta = os.path.join(
        sysroot, DLC_BUILD_DIR_ARTIFACTS_META
    )

    build_dir_exists = os.path.exists(build_dir)
    build_dir_scaled_exists = os.path.exists(build_dir_scaled)
    build_dir_artifacts_meta_exists = os.path.exists(build_dir_artifacts_meta)
    if (
        not build_dir_exists
        and not build_dir_scaled_exists
        and not build_dir_artifacts_meta_exists
    ):
        logging.debug(
            "DLC build directories (%s) (%s) (%s) do not exist, ignoring.",
            build_dir,
            build_dir_scaled,
            build_dir_artifacts_meta,
        )
        return

    # Check to make sure that each DLC ID is unique from various install paths.
    # In case it is not enforced during DLC ebuild installations.
    legacy_dlc_ids = os.listdir(build_dir) if build_dir_exists else []
    scaled_dlc_ids = (
        os.listdir(build_dir_scaled) if build_dir_scaled_exists else []
    )
    artifacts_meta_dlc_ids = (
        os.listdir(build_dir_artifacts_meta)
        if build_dir_artifacts_meta_exists
        else []
    )

    unique_dlc_set = set()
    dupe_dlc_set = set(
        x
        for x in legacy_dlc_ids + scaled_dlc_ids + artifacts_meta_dlc_ids
        if x in unique_dlc_set or unique_dlc_set.add(x)
    )

    if dupe_dlc_set:
        err_msg = f"There are duplicate DLC IDs: {dupe_dlc_set}"
        # TODO: Convert this to an error.
        logging.warning(err_msg)

    for scaled in (False, True):
        dlc_build_dir = build_dir_scaled if scaled else build_dir

        if not os.path.exists(dlc_build_dir):
            logging.debug("Skipping build directory %s.", dlc_build_dir)
            continue

        if dlc_id is not None:
            if not os.path.exists(os.path.join(dlc_build_dir, dlc_id)):
                logging.warning(
                    "DLC '%s' does not exist in the build directory %s.",
                    dlc_id,
                    dlc_build_dir,
                )
                continue
            dlc_ids = [dlc_id]
        else:
            # Process all DLCs.
            # Sort to ease testing.
            dlc_ids = sorted(os.listdir(dlc_build_dir))
            if not dlc_ids:
                logging.info("There are no DLC(s) to copy to output, ignoring.")
                return

            logging.info(
                "Detected the following DLCs (scaled=%s): %s",
                scaled,
                ", ".join(dlc_ids),
            )

        for d_id in dlc_ids:
            dlc_id_path = os.path.join(dlc_build_dir, d_id)
            dlc_packages = [
                direct
                for direct in os.listdir(dlc_id_path)
                if os.path.isdir(os.path.join(dlc_id_path, direct))
            ]
            for d_package in dlc_packages:
                logging.debug("Building image: DLC %s", d_id)
                params = EbuildParams.LoadEbuildParams(
                    sysroot=sysroot,
                    dlc_id=d_id,
                    dlc_package=d_package,
                    scaled=scaled,
                )
                # Because portage sandboxes every ebuild package during
                # `cros build-packages` phase, we cannot delete the old image
                # during that phase, but we can use the existence of the file
                # |EBUILD_PARAMETERS| to know if the image has to be generated
                # or not.
                if not params:
                    logging.debug(
                        "The ebuild parameters file (%s) for DLC (%s) does not "
                        "exist. This means that the image was already "
                        "generated and there is no need to create it again.",
                        EbuildParams.GetParamsPath(
                            sysroot, d_id, d_package, scaled=scaled
                        ),
                        d_id,
                    )
                else:
                    # Install time validity check.
                    params.VerifyDlcParameters()

                    dlc_generator = DlcGenerator(
                        src_dir=src_dir,
                        sysroot=sysroot,
                        board=board,
                        ebuild_params=params,
                    )
                    dlc_generator.GenerateDLC()

                # Copy the dlc images to install_root_dir.
                if install_root_dir:
                    if preload and not IsDlcPreloadingAllowed(
                        d_id, dlc_build_dir
                    ):
                        logging.debug(
                            "Skipping installation of DLC %s because the "
                            "preload flag is set and the DLC does not "
                            "support preloading.",
                            d_id,
                        )
                    else:
                        osutils.SafeMakedirsNonRoot(install_root_dir)
                        install_dlc_dir = os.path.join(
                            install_root_dir, d_id, d_package
                        )
                        osutils.SafeMakedirsNonRoot(install_dlc_dir)
                        source_dlc_dir = os.path.join(
                            dlc_build_dir, d_id, d_package
                        )
                        for filepath in (
                            os.path.join(source_dlc_dir, fname)
                            for fname in os.listdir(source_dlc_dir)
                            if fname.endswith(".img")
                        ):
                            logging.debug(
                                "Copying DLC(%s) image from %s to %s: ",
                                d_id,
                                filepath,
                                install_dlc_dir,
                            )
                            shutil.copy(filepath, install_dlc_dir)
                            logging.debug(
                                "Done copying DLC to %s.", install_dlc_dir
                            )
                else:
                    logging.debug(
                        "install_root_dir value was not provided. Copying dlc"
                        " image skipped."
                    )

                # Factory install DLCs.
                if (
                    stateful
                    and factory_install
                    and IsFactoryInstallAllowed(d_id, dlc_build_dir)
                ):
                    install_stateful_root = os.path.join(
                        stateful, DLC_FACTORY_INSTALL_DIR
                    )
                    install_stateful_dir = os.path.join(
                        install_stateful_root, d_id, d_package
                    )
                    osutils.SafeMakedirs(
                        install_stateful_dir, mode=0o755, sudo=True
                    )
                    source_dlc_dir = os.path.join(
                        dlc_build_dir, d_id, d_package
                    )
                    for filepath in (
                        os.path.join(source_dlc_dir, fname)
                        for fname in os.listdir(source_dlc_dir)
                        if fname.endswith(".img")
                    ):
                        logging.debug(
                            "Factory installing DLC(%s) image from %s to %s: ",
                            d_id,
                            filepath,
                            install_stateful_dir,
                        )
                        cros_build_lib.sudo_run(
                            ["cp", filepath, install_stateful_dir],
                            print_cmd=False,
                            stderr=True,
                        )

                    # Change the owner + group of factory install directory.
                    # Refer to
                    # http://cs/chromeos_public/src/third_party/eclass-overlay
                    # or DLC/dlcservice related uid + gid.
                    cros_build_lib.sudo_run(
                        [
                            "chown",
                            "-R",
                            "%d:%d" % (DLC_UID, DLC_GID),
                            install_stateful_root,
                        ]
                    )

                # Create metadata directory in rootfs.
                # TODO(b/290961240): Remove copying individual imageloader.json
                # and table files after fully migrated to used the compressed
                # metadata.
                if rootfs:
                    meta_rootfs = os.path.join(
                        rootfs, DLC_META_DIR, d_id, d_package
                    )
                    osutils.SafeMakedirs(meta_rootfs, sudo=True)
                    # Copy the metadata files to rootfs.
                    meta_dir_src = os.path.join(
                        dlc_build_dir, d_id, d_package, DLC_TMP_META_DIR
                    )
                    logging.debug(
                        "Copying DLC(%s) metadata from %s to %s: ",
                        d_id,
                        meta_dir_src,
                        meta_rootfs,
                    )
                    # Use sudo_run since osutils.CopyDirContents doesn't support
                    # sudo.
                    cros_build_lib.sudo_run(
                        [
                            "cp",
                            "-dR",
                            meta_dir_src.rstrip("/") + "/.",
                            meta_rootfs,
                        ],
                        print_cmd=False,
                        stderr=True,
                    )

                    # Only allow if explicitly set when emerge'ing the DLC
                    # ebuild.
                    if IsLoadPinVerityDigestAllowed(d_id, dlc_build_dir):
                        # Append the DLC root dm-verity digest.
                        root_hexdigest = verity.ExtractRootHexdigest(
                            os.path.join(meta_rootfs, DLC_VERITY_TABLE)
                        )
                        if not root_hexdigest:
                            raise Error(
                                f"Could not find root dm-verity digest of "
                                f"{d_id} in dm-verity table"
                            )
                        trusted_verity_digests = os.path.join(
                            rootfs,
                            DLC_META_DIR,
                            DLC_LOADPIN_TRUSTED_VERITY_DIGESTS,
                        )

                        # Create the initial digests file with correct LoadPin
                        # header.
                        if not os.path.exists(trusted_verity_digests):
                            osutils.WriteFile(
                                trusted_verity_digests,
                                DLC_LOADPIN_FILE_HEADER + "\n",
                                mode="w",
                                sudo=True,
                            )

                        # Handle duplicates.
                        if (
                            root_hexdigest
                            not in osutils.ReadFile(
                                trusted_verity_digests
                            ).split()
                        ):
                            osutils.WriteFile(
                                trusted_verity_digests,
                                root_hexdigest + "\n",
                                mode="a",
                                sudo=True,
                            )
                    else:
                        logging.debug(
                            "Skipping addition of LoadPin dm-verity digest of "
                            "%s.",
                            d_id,
                        )

                else:
                    logging.debug(
                        "rootfs value was not provided. Copying metadata "
                        "skipped."
                    )

    # This read from rootfs directly, which should now hold all the installed
    # metadata. For cleanup, redirect metadata installations into a secondary
    # temporary rootfs path.
    if rootfs and not dlc_id:
        CreatePowerwashSafeFileInRootfs(rootfs)

    # Skip creating compressed metadata when installing a single DLC (e.g. for
    # `cros deploy`).
    if rootfs and not dlc_id:
        logging.info("Creating compressed DLC metadata.")
        dlc_all = []

        artifacts_meta_dir = os.path.join(sysroot, DLC_BUILD_DIR_ARTIFACTS_META)
        if os.path.exists(artifacts_meta_dir):
            dlc_all.extend(
                (x, artifacts_meta_dir) for x in os.listdir(artifacts_meta_dir)
            )

        for scaled in (False, True):
            dlc_build_dir = build_dir_scaled if scaled else build_dir

            if not os.path.isdir(dlc_build_dir):
                logging.debug("Skipping build directory %s.", dlc_build_dir)
                continue

            dlc_all.extend(
                (x, dlc_build_dir) for x in os.listdir(dlc_build_dir)
            )

        with DlcMetadata(
            metadata_path=os.path.join(rootfs, DLC_META_DIR),
            sudo=True,
        ) as metadata:
            metadata.Create(dlc_all)

    logging.debug("Done installing DLCs.")


def ValidateDlcIdentifier(name):
    """Validates the DLC identifiers like ID and package names.

    The name specifications are:
      - No underscore.
      - First character should be only alphanumeric.
      - Other characters can be alphanumeric and '-' (dash).
      - Maximum length (_MAX_ID_NAME) characters.

    For more info see:
    https://chromium.googlesource.com/chromiumos/platform2/+/HEAD/dlcservice/docs/developer.md#create-a-dlc-module

    Args:
        name: The value of the string to be validated.

    Raises:
        Error: if name is not a valid DLC identifier.
    """
    errors = []
    if not name:
        errors.append("Must not be empty.")
    if not name[0].isalnum():
        errors.append("Must start with alphanumeric character.")
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9-]*$", name):
        errors.append("Must only use alphanumeric and - (dash).")
    if len(name) > _MAX_ID_NAME:
        errors.append("Must be within %d characters." % _MAX_ID_NAME)

    if errors:
        msg = "%s is invalid:\n%s" % (name, "\n".join(errors))
        raise Error(msg)
