# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Methods for reading and building manifests exported by the subtools builder.

Loads and interprets subtools export manifests defined by the proto at
https://crsrc.org/o/src/config/proto/chromiumos/build/api/subtools.proto
"""

import dataclasses
import hashlib
import json
import logging
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Literal, Optional, Set

from chromite.third_party import lddtree
from chromite.third_party.google import protobuf
from chromite.third_party.google.protobuf import text_format

import chromite
from chromite.api.gen.chromiumos.build.api import subtools_pb2
from chromite.lib import cipd
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.licensing import licenses_lib


try:
    # The filetype module imports `magic` which is available in the SDK, glinux
    # and vpython environments, but not on bots outside the SDK.
    from chromite.lib import filetype
except ImportError:
    cros_build_lib.AssertOutsideChroot()

logger = chromite.ChromiteLogger.getLogger(__name__)


class Error(Exception):
    """Module base error class."""

    def __init__(self, message: str, subtool: object):
        # TODO(build): Use self.add_note when Python 3.11 is available.
        super().__init__(f"{message}\nSubtool:\n{subtool}")


class ManifestInvalidError(Error):
    """The contents of the subtool package manifest proto are invalid."""


class ManifestBundlingError(Error):
    """The subtool could not be bundled."""


# Default glob to find export package manifests under the config_dir.
SUBTOOLS_EXPORTS_GLOB = "**/*.textproto"

# Path (relative to the bundle root) of the license file generated from the
# licenses of input files. Note the suffix determines the compressor. If GZIP
# is used, the `--no-name` argument must also be passed. Otherwise gzip will
# include the random name of the temporary file and a timestamp in its header,
# which defeats idempotence. This is important to ensure CIPD can de-dupe
# identical uploads.
LICENSE_FILE = Path("license.html.zst")

# Standard set of arguments passed to all `lddtree` invocations.
LDDTREE_ARGS = ["--libdir", "/lib", "--bindir", "/bin", "--generate-wrappers"]

# Path (relative to the metadata work dir) of serialized upload metadata.
UPLOAD_METADATA_FILE = Path("subtool_upload.json")

# Valid names. A stricter version of `packageNameRe` in
# https://crsrc.org/i/go/src/go.chromium.org/luci/cipd/common/common.go
# Diallows slashes and starting with a ".".
_PACKAGE_NAME_RE = re.compile(r"^[a-z0-9_\-]+[a-z0-9_\-\.]*$")

# Default destination path in the bundle when not specified on a PathMapping.
_DEFAULT_DEST = "bin"

# Default regex to apply to input paths when bundling.
_DEFAULT_STRIP_PREFIX_REGEX = "^.*/"

# Default CIPD prefix when unspecified.
_DEFAULT_CIPD_PREFIX = "chromiumos/infra/tools"

# Digest from hashlib to use for hashing files and accumulating hashes.
_DIGEST = "sha1"


@dataclasses.dataclass
class CipdMetadata:
    """Structure of a `cipd_package` in serialized metadata.

    This is reconstructed from JSON, so should not reference other classes.
    Optional members can be added, but should never be removed or added in a way
    that assumes their presence, because they may be serialized by old branches.

    IMPORTANT: Always include type annotations, or you'll get a class variable
    per PEP0526, and it will be omitted from serialization.

    Attributes:
        package: The CIPD package prefix.
        tags: Tags to associate with the package upload.
        refs: Refs to associate with the package upload.
    """

    package: str = ""
    tags: Dict[str, str] = dataclasses.field(default_factory=dict)
    refs: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class UploadMetadata:
    """Structure of the serialized upload metadata.

    This is reconstructed as a Dict. Essentially it maps keys to a metadata
    subtype. Members should not be removed and the reader must be able to handle
    any prior structure.

    IMPORTANT: Always include type annotations.

    Attributes:
        upload_metadata_version: Version of the upload metadata file structure.
            Increment this when making changes that require the ToT uploader to
            change logic for files produced on old branches.
        cipd_package: Metadata for uploading a CIPD package.
    """

    upload_metadata_version: int = 1
    cipd_package: CipdMetadata = dataclasses.field(default_factory=CipdMetadata)

    @staticmethod
    def from_dict(d: Dict[str, Dict[str, Any]]) -> "UploadMetadata":
        metadata = UploadMetadata()
        # Fields are never removed, and all have default values, so just unpack.
        metadata.cipd_package = CipdMetadata(**d.get("cipd_package", {}))
        return metadata


def _extract_build_id(file: Path) -> Optional[str]:
    """Runs `readelf -n` to extract a Build ID as a hex string."""
    BUILD_ID_PATTERN = re.compile("^    Build ID: *([0-9a-f]+)", re.MULTILINE)
    result = cros_build_lib.run(
        ["readelf", "-n", file], capture_output=True, encoding="utf-8"
    ).stdout
    match = BUILD_ID_PATTERN.search(result)
    return match.group(1) if match else None


def extract_hash(file: Path, file_type: str) -> str:
    """Extract build-id from an ELF binary, falling back to a file hash.

    Args:
        file: The file to hash.
        file_type: The result of filetype.FileTypeDecoder.GetType for `file`.

    Returns:
        A hexadecimal string: either the Build ID or file hash.
    """
    if file_type.startswith("binary/elf"):
        build_id = _extract_build_id(file)
        # Only accept BuildID that are at least 64-bit. 160-bit is also common.
        if build_id and len(build_id) >= 8:
            return build_id
        logger.warning(
            "%s is binary/elf but BuildID is bad. Falling back to %s hash",
            file,
            _DIGEST,
        )
    else:
        logger.debug("Hashing %s with %s", file, _DIGEST)

    # TODO(build): Use hashlib.file_digest in Python 3.11.
    BUFSIZE = 256 * 1024
    hasher = hashlib.new(_DIGEST)
    with open(file, "rb") as fp:
        buf = fp.read(BUFSIZE)
        while buf:
            hasher.update(buf)
            buf = fp.read(BUFSIZE)
    return hasher.hexdigest()


def get_installed_package(
    query: str, error_context: "Subtool"
) -> portage_util.InstalledPackage:
    """Returns an InstalledPackage for an installed ebuild."""
    packages = portage_util.FindPackageNameMatches(query)
    if len(packages) != 1:
        raise ManifestBundlingError(
            f"Package '{query}' must match exactly one package."
            f" Matched {len(packages)} -> {packages}.",
            error_context,
        )
    logger.debug("%s matched %s", query, packages[0])
    installed_package = portage_util.PortageDB().GetInstalledPackage(
        packages[0].category, packages[0].pvr
    )
    if not installed_package:
        atom = packages[0].atom
        raise ManifestBundlingError(
            f"Failed to map {query}=>{atom} to an *installed* package.",
            error_context,
        )
    return installed_package


class Subtool:
    """A subtool, backed by a .textproto manifest.

    Attributes:
        manifest_path: The source .textproto, used for debug output.
        package: The parsed protobuf message.
        work_root: Root path in which to build bundles for upload.
        is_valid: Set after validation to indicate an upload may be attempted.
        parse_error: Protobuf parse error held until validation.
    """

    # Allow the FileTypeDecoder to keep its cache, for files rooted at "/".
    _FILETYPE_DECODER: Optional["filetype.FileTypeDecoder"] = None

    @classmethod
    def get_file_type(cls, path: Path) -> str:
        """Gets the type of `path` using FileTypeDecoder, following symlinks."""
        if not cls._FILETYPE_DECODER:
            cls._FILETYPE_DECODER = filetype.FileTypeDecoder()
        # Resolve symlinks (to avoid type=inode/symlink).
        return cls._FILETYPE_DECODER.GetType(str(path.resolve()))

    def __init__(self, message: str, path: Path, work_root: Path):
        """Loads from a .textpoto file contents.

        Args:
            message: The contents of the .textproto file.
            path: The source file (for logging).
            work_root: Location on disk where packages are built.
        """
        self.manifest_path = path
        self.package = subtools_pb2.SubtoolPackage()
        self.work_root = work_root
        self.is_valid: Optional[bool] = None
        self.parse_error: Optional[text_format.ParseError] = None

        # Set of c/p-v-r strings that provided the bundle contents.
        self._source_ebuilds: Set[str] = set()
        # Paths bundled, but not yet attributed to a source ebuild.
        self._unmatched_paths: List[str] = []

        # Running digest of accumulated hashes from file contents, maps the
        # destination file to its hash. Not all destination files may be hashed:
        # only the ones whose hashes we care about. Hash is either a 16- or 40-
        # character hex string.
        self._content_hashes: Dict[str, str] = {}

        try:
            text_format.Parse(message, self.package)
        except text_format.ParseError as e:
            self.parse_error = e

    @classmethod
    def from_file(cls, path: Path, work_root: Path) -> "Subtool":
        """Helper to construct a Subtool from a path on disk."""
        return cls(path.read_text(encoding="utf-8"), path, work_root)

    def __str__(self) -> str:
        """Debug output; emits the parsed textproto and source filename."""
        textproto = text_format.MessageToString(self.package)
        return (
            f"{'=' * 10} {self.manifest_path} {'=' * 10}\n"
            + textproto
            + "=" * (len(self.manifest_path.as_posix()) + 22)
        )

    def _work_dir(self) -> Path:
        """Returns the path under work_root for creating files for upload."""
        return self.work_root / self.package.name

    @property
    def metadata_dir(self) -> Path:
        """Path holding all work relating specifically to this package."""
        return self._work_dir()

    @property
    def bundle_dir(self) -> Path:
        """Path (under metadata) holding files to form the exported bundle."""
        return self._work_dir() / "bundle"

    @property
    def cipd_package(self) -> str:
        """Full path to the CIPD package name."""
        prefix = (
            self.package.cipd_prefix
            if self.package.HasField("cipd_prefix")
            else _DEFAULT_CIPD_PREFIX
        )
        return f"{prefix.rstrip('/')}/{self.package.name}"

    @property
    def summary(self) -> str:
        """A one-line summary describing this package."""
        return f"{self.package.name} (http://go/cipd/p/{self.cipd_package})"

    @property
    def source_packages(self) -> List[str]:
        """The list of packages that contributed files during bundling."""
        return sorted(self._source_ebuilds)

    def stamp(self, kind: Literal["bundled", "uploaded"]) -> Path:
        """Returns the path to a "stamp" file that tracks export progress."""
        return self.metadata_dir / f".{kind}"

    def clean(self) -> None:
        """Resets export progress and removes the temporary bundle tree."""
        self.stamp("bundled").unlink(missing_ok=True)
        (self.metadata_dir / UPLOAD_METADATA_FILE).unlink(missing_ok=True)
        self.stamp("uploaded").unlink(missing_ok=True)
        osutils.RmDir(self.bundle_dir, ignore_missing=True)

    def bundle(self) -> None:
        """Collect and bundle files described in `package` in the work dir."""
        self._validate()
        self._collect_files()
        self._match_ebuilds()
        self._collect_licenses()
        # TODO(b/277992359): hashing.
        self.stamp("bundled").touch()

    def prepare_upload(self) -> None:
        """Prepares metadata required to upload the bundle, e.g., to cipd."""
        self._validate()
        if not self.stamp("bundled").exists():
            raise ManifestBundlingError("Bundling incomplete.", self)

        metadata = UploadMetadata()
        metadata.cipd_package.package = self.cipd_package
        metadata.cipd_package.refs = ["latest"]
        metadata.cipd_package.tags = {
            "builder_source": "sdk_subtools",
            "ebuild_source": ",".join(self.source_packages),
            "subtools_hash": self._calculate_digest(),
        }
        metadata_path = self.metadata_dir / UPLOAD_METADATA_FILE
        with metadata_path.open("w", encoding="utf-8") as fp:
            json.dump(dataclasses.asdict(metadata), fp)

        logger.notice("%s: Wrote %s.", self.package.name, metadata_path)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Contents: `%s`", metadata_path.read_text())

    def _calculate_digest(self) -> str:
        """Calculates the digest of the bundled contents."""
        hasher = hashlib.new(_DIGEST)
        # Sort by path before hashing.
        for _, hash_string in sorted(self._content_hashes.items()):
            hasher.update(bytes.fromhex(hash_string))
        return hasher.hexdigest()

    def _validate(self) -> None:
        """Validate fields in the proto."""
        if self.is_valid:
            # Note this does not worry about validity invalidation, e.g., due to
            # changed disk state since validation.
            return

        if self.parse_error:
            error = ManifestInvalidError(
                f"ParseError in .textproto: {self.parse_error}", self
            )
            error.__cause__ = self.parse_error
            raise error

        if not _PACKAGE_NAME_RE.match(self.package.name):
            raise ManifestInvalidError(
                f"Subtool name must match '{_PACKAGE_NAME_RE.pattern}'", self
            )
        if not self.package.paths:
            raise ManifestInvalidError("At least one path is required", self)

        # TODO(b/277992359): Validate more proto fields.

        self.is_valid = True

    def _copy_into_bundle(
        self, src: Path, destdir: Path, strip: re.Pattern
    ) -> int:
        """Copies a file on disk into the bundling folder.

        Copies only files (follows symlinks). Ensures files are not clobbered.
        Returns the number of files copied.
        """
        if not src.is_file():
            return 0

        # Apply the regex, and ensure the result is not an absolute path.
        dest = destdir / strip.sub("", src.as_posix()).lstrip("/")
        if dest.exists():
            raise ManifestBundlingError(
                f"{dest} exists: refusing to copy {src}.", self
            )
        osutils.SafeMakedirs(dest.parent)
        file_type = self.get_file_type(src)
        hash_string = extract_hash(src, file_type)
        self._content_hashes[str(dest)] = hash_string
        logger.debug("subtools_hash(%s) = '%s'", src, hash_string)

        if file_type == "binary/elf/dynamic-bin":
            return self._lddtree_into_bundle(src, dest.parent)

        logger.debug(
            "Copy file %s -> %s (type=%s, hash=%s).",
            src,
            dest,
            file_type,
            hash_string,
        )
        shutil.copy2(src, dest)
        return 1

    def _lddtree_into_bundle(self, elf: Path, destdir: Path) -> int:
        """Copies a dynamic elf into the bundle."""
        # Output of the main script is always `bin`, so avoid `bin/bin`.
        if destdir.name == "bin":
            destdir = destdir.parent
        lddtree.main(LDDTREE_ARGS + ["--copy-to-tree", str(destdir), str(elf)])
        # The globbing is done already, so there's no big concern about
        # accidentally bundling the entire filesystem. Count as "1 file".
        return 1

    def _check_counts(self, file_count: int) -> None:
        """Raise an error if files violate the manifest spec."""
        if file_count > self.package.max_files:
            raise ManifestBundlingError(
                f"Max file count ({self.package.max_files}) exceeded.", self
            )

    def _bundle_mapping(
        self, mapping: subtools_pb2.SubtoolPackage.PathMapping
    ) -> int:
        """Bundle files for the provided `mapping`.

        Returns the number of files matched.
        """
        subdir = mapping.dest if mapping.HasField("dest") else _DEFAULT_DEST
        destdir = self.bundle_dir / subdir.lstrip("/")
        strip_prefix_regex = (
            mapping.strip_prefix_regex
            if mapping.HasField("strip_prefix_regex")
            else _DEFAULT_STRIP_PREFIX_REGEX
        )
        strip = re.compile(strip_prefix_regex)

        # Any leading '/' must be stripped from the glob (pathlib only supports
        # relative patterns when matching). Steps below effectively restore it.
        glob = mapping.input.lstrip("/")

        file_count = 0

        if mapping.ebuild_filter:
            package = get_installed_package(mapping.ebuild_filter, self)
            for _file_type, relative_path in package.ListContents():
                path = Path(f"/{relative_path}")
                if not path.match(glob):
                    continue
                file_count += self._copy_into_bundle(path, destdir, strip)
                self._check_counts(file_count)
            if file_count:
                self._source_ebuilds.add(package.package_info.cpvr)
        else:
            for path in Path("/").glob(glob):
                added_files = self._copy_into_bundle(path, destdir, strip)
                if not added_files:
                    continue
                file_count += added_files
                self._check_counts(file_count)
                self._unmatched_paths.append(str(path))

        if file_count == 0:
            raise ManifestBundlingError(
                f"Input field {mapping.input} matched no files.", self
            )
        logger.info("Glob '%s' matched %d files.", mapping.input, file_count)
        return file_count

    def _collect_files(self) -> None:
        """Collect files described by the package manifest in the work dir."""
        self.clean()
        self.metadata_dir.mkdir(exist_ok=True)
        self.bundle_dir.mkdir()
        logger.notice(
            "%s: Subtool bundling under %s.", self.package.name, self.bundle_dir
        )
        # Emit the full .textproto to debug logs.
        logger.debug(self)
        file_count = 0
        self._source_ebuilds = set()
        self._unmatched_paths = []
        for path in self.package.paths:
            file_count += self._bundle_mapping(path)
        logger.notice("%s: Copied %d files.", self.package.name, file_count)

    def _match_ebuilds(self) -> None:
        """Match up unmatched paths to the package names that provided them."""
        if self._unmatched_paths:
            ebuilds = portage_util.FindPackageNamesForFiles(
                *self._unmatched_paths
            )
            # Assume all files were matched, and that it is not an error for any
            # file to not be matched to a package.
            self._unmatched_paths = []
            self._source_ebuilds.update(e.cpvr for e in ebuilds)
        if not self._source_ebuilds:
            raise ManifestBundlingError(
                "Bundle cannot be attributed to at least one package.", self
            )
        logger.notice("Contents provided by %s", self.source_packages)

    def _collect_licenses(self) -> None:
        """Generates a license file from `source_packages`."""
        packages = self.source_packages
        if not packages:
            # Avoid putting a useless file into the bundle in this case. But it
            # is only hit when _match_ebuilds is skipped (in tests).
            return

        logger.notice("%s: Collecting licenses.", self.package.name)
        # TODO(b/297978537): Use portage_util.GetFlattenedDepsForPackage to get
        # a full depgraph.
        licensing = licenses_lib.Licensing(
            sysroot="/", package_fullnames=packages, gen_licenses=True
        )
        licensing.LoadPackageInfo()
        licensing.ProcessPackageLicenses()
        # NOTE(b/297978537): Location of license files in the bundle is not
        # yet configurable. Dump it in the package root.
        licensing.GenerateHTMLLicenseOutput(
            self.bundle_dir / LICENSE_FILE, compress_output=True
        )


class InstalledSubtools:
    """Wraps the set of subtool manifests installed on the system.

    Attributes:
        subtools: Collection of parsed subtool manifests.
        work_root: Root folder where all packages are bundled.
    """

    def __init__(
        self,
        config_dir: Path,
        work_root: Path,
        glob: str = SUBTOOLS_EXPORTS_GLOB,
    ):
        logger.notice(
            "Loading subtools from %s/%s with Protobuf library v%s",
            config_dir,
            glob,
            protobuf.__version__,
        )
        self.work_root = work_root
        self.subtools = [
            Subtool.from_file(f, work_root) for f in config_dir.glob(glob)
        ]

    def bundle_all(self) -> None:
        """Read .textprotos and bundle blobs into `work_root`."""
        self.work_root.mkdir(exist_ok=True)
        for subtool in self.subtools:
            subtool.bundle()

    def prepare_uploads(
        self, upload_filter: Optional[List[str]] = None
    ) -> List[Path]:
        """Read .textprotos and prepares valid bundles in `work_root`.

        Args:
            upload_filter: If provided, only upload subtools with these names.
        """
        prepared_bundles: List[Path] = []
        for subtool in self.subtools:
            if upload_filter is None or subtool.package.name in upload_filter:
                subtool.prepare_upload()
                prepared_bundles.append(subtool.metadata_dir)
        return prepared_bundles


class BundledSubtools:
    """Wraps a list of paths with pre-bundled subtools."""

    def __init__(self, bundles: List[Path]):
        """Creates and initializes a BundledSubtools wrapper."""
        self.bundles = bundles
        self.cipd_path = cipd.GetCIPDFromCache()

    def upload(self, use_production: bool) -> None:
        """Uploads each valid, bundled subtool.

        Args:
            use_production: Whether to upload to production environments.
        """
        for bundle in self.bundles:
            self._upload_bundle(bundle, use_production)

    def _upload_bundle(self, path: Path, use_production: bool) -> None:
        """Uploads a single bundle."""
        with (path / UPLOAD_METADATA_FILE).open("rb") as fp:
            cipd_package = UploadMetadata.from_dict(json.load(fp)).cipd_package

        if not cipd_package.package:
            logger.warning(
                "%s: No valid cipd_package in bundle metadata. Skipping.", path
            )
            return

        service_url = None if use_production else cipd.STAGING_SERVICE_URL
        instances = cipd.search_instances(
            self.cipd_path,
            cipd_package.package,
            cipd_package.tags,
            service_url=service_url,
        )
        if instances:
            logger.notice(
                "%s: ebuild and hash match instance %s. Not uploading.",
                cipd_package.package,
                instances,
            )
            return

        # NOTE: This will not create a new instance in CIPD if the hash of the
        # bundle contents matches an existing instance. In that case, CIPD will
        # still add the provided tags to the existing instance.
        cipd.CreatePackage(
            self.cipd_path,
            cipd_package.package,
            path / "bundle",
            cipd_package.tags,
            cipd_package.refs,
            service_url=service_url,
        )
        (path / ".uploaded").touch()
