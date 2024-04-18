# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The Binhost API interacts with Portage binhosts and Packages files."""

import functools
import logging
import os
from pathlib import Path
import tempfile
from typing import List, NamedTuple, Optional, TYPE_CHECKING, Union

from chromite.lib import binpkg
from chromite.lib import config_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import git
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib import portage_util
from chromite.lib import repo_util
from chromite.utils import gs_urls_util
from chromite.utils import key_value_store


if TYPE_CHECKING:
    from chromite.lib import build_target_lib
    from chromite.lib import chroot_lib
    from chromite.lib import sysroot_lib

# The name of the ACL argument file.
_GOOGLESTORAGE_GSUTIL_FILE = "googlestorage_acl.txt"

# The name of the package file (relative to sysroot) where the list of packages
# for dev-install is stored.
_DEV_INSTALL_PACKAGES_FILE = "build/dev-install/package.installable"

# The maximum number of binhosts to return from the lookup service.
_MAX_BINHOSTS = 10


class Error(Exception):
    """Base error class for the module."""


class EmptyPrebuiltsRoot(Error):
    """When a prebuilts root is unexpectedly empty."""


class NoAclFileFound(Error):
    """No ACL file could be found."""


class InvalidMaxUris(Error):
    """When maximum number of uris to store is less than or equal to 0."""


def _ValidateBinhostConf(path: Path, key: str) -> None:
    """Validates the binhost conf file defines only one environment variable.

    This function checks to ensure unexpected configuration is not clobbered by
    conf overwrites.

    Args:
        path: Path to the file to validate.
        key: Expected binhost key.

    Raises:
        ValueError: If file defines != 1 environment variable.
    """
    if not path.exists():
        # If the conf file does not exist, e.g. with new targets, then whatever.
        return

    kvs = key_value_store.LoadFile(path)

    if not kvs:
        raise ValueError(
            "Found empty .conf file %s when a non-empty one was expected."
            % path
        )
    elif len(kvs) > 1:
        raise ValueError(
            "Conf file %s must define exactly 1 variable. "
            "Instead found: %r" % (path, kvs)
        )
    elif key not in kvs:
        raise KeyError("Did not find key %s in %s" % (key, path))


def _ValidatePrebuiltsFiles(
    prebuilts_root: str, prebuilts_paths: List[str]
) -> None:
    """Validate all prebuilt files exist.

    Args:
        prebuilts_root: Absolute path to root directory containing prebuilts.
        prebuilts_paths: List of file paths relative to root, to be verified.

    Raises:
        LookupError: If any prebuilt archive does not exist.
    """
    for prebuilt_path in prebuilts_paths:
        full_path = os.path.join(prebuilts_root, prebuilt_path)
        if not os.path.exists(full_path):
            raise LookupError("Prebuilt archive %s does not exist" % full_path)


def _ValidatePrebuiltsRoot(
    target: "build_target_lib.BuildTarget", prebuilts_root: str
) -> None:
    """Validate the given prebuilts root exists.

    If the root does not exist, it probably means the build target did not build
    successfully, so warn callers appropriately.

    Args:
        target: The build target in question.
        prebuilts_root: The expected root directory for the target's prebuilts.

    Raises:
        EmptyPrebuiltsRoot: If prebuilts root does not exist.
    """
    if not os.path.exists(prebuilts_root):
        raise EmptyPrebuiltsRoot(
            "Expected to find prebuilts for build target %s at %s. "
            "Did %s build successfully?" % (target, prebuilts_root, target)
        )


def _ValidateBinhostMaxURIs(max_uris: int) -> None:
    """Validates that the max_uris is greater or equal to 1.

    Args:
        max_uris: Maximum number of uris that we need to store in Binhost conf
            file.

    Raises:
        InvalidMaxUris: If max_uris is None or less than or equal to zero.
    """
    if max_uris is None or max_uris <= 0:
        raise InvalidMaxUris(
            f"Binhost file cannot have {max_uris} number of URIs."
        )


def GetPrebuiltsRoot(
    chroot: "chroot_lib.Chroot",
    sysroot: "sysroot_lib.Sysroot",
    build_target: "build_target_lib.BuildTarget",
) -> str:
    """Find the root directory with binary prebuilts for the given sysroot.

    Args:
        chroot: The chroot where the sysroot lives.
        sysroot: The sysroot.
        build_target: The build target.

    Returns:
        Absolute path to the root directory with the target's prebuilt archives.
    """
    root = chroot.full_path(sysroot.JoinPath("packages"))
    _ValidatePrebuiltsRoot(build_target, root)
    return root


def GetPrebuiltsFiles(
    prebuilts_root: str,
    package_index_paths: Optional[List[str]] = None,
    sudo=False,
) -> List[str]:
    """Find paths to prebuilts at the given root directory.

    Assumes the root contains a Portage package index named Packages.

    Args:
        prebuilts_root: Absolute path to root directory containing a package
            index.
        package_index_paths: A list of paths to previous package index files
            used to de-duplicate prebuilts.
        sudo: Whether to write the file as the root user.

    Returns:
        List of paths to all prebuilt archives, relative to the root.
    """
    indexes = []
    for package_index_path in package_index_paths or []:
        index = binpkg.PackageIndex()
        index.ReadFilePath(package_index_path)
        indexes.append(index)

    package_index = binpkg.GrabLocalPackageIndex(prebuilts_root)
    packages = package_index.ResolveDuplicateUploads(indexes)
    # Save the PATH changes from the deduplication.
    package_index.WriteFile(Path(prebuilts_root) / "Packages", sudo=sudo)

    prebuilt_paths = []
    for package in packages:
        prebuilt_paths.append(package["CPV"] + ".tbz2")

        include_debug_symbols = package.get("DEBUG_SYMBOLS")
        if cros_build_lib.BooleanShellValue(
            include_debug_symbols, default=False
        ):
            prebuilt_paths.append(package["CPV"] + ".debug.tbz2")

    _ValidatePrebuiltsFiles(prebuilts_root, prebuilt_paths)
    return prebuilt_paths


def UpdatePackageIndex(
    prebuilts_root: str, upload_uri: str, upload_path: str, sudo: bool = False
) -> str:
    """Update package index with information about where it will be uploaded.

    This causes the existing Packages file to be overwritten.

    Args:
        prebuilts_root: Absolute path to root directory containing binary
            prebuilts.
        upload_uri: The URI (typically GS bucket) where prebuilts will be
            uploaded.
        upload_path: The path at the URI for the prebuilts.
        sudo: Whether to write the file as the root user.

    Returns:
        Path to the new Package index.
    """
    assert not upload_path.startswith("/")
    package_index = binpkg.GrabLocalPackageIndex(prebuilts_root)
    package_index.SetUploadLocation(upload_uri, upload_path)
    package_index.header["TTL"] = 60 * 60 * 24 * 365
    package_index_path = os.path.join(prebuilts_root, "Packages")
    package_index.WriteFile(package_index_path, sudo=sudo)
    return package_index_path


def _get_current_uris(
    conf_file_path: Union[str, "Path"], key: str
) -> List[str]:
    """Returns the uri values of the key from the conf file.

    If the file does not exist, then it returns an empty list.

    Args:
        conf_file_path: Path to the conf file.
        key: Expected binhost key.

    Returns:
        List of the current values for the key.
    """
    kvs = key_value_store.LoadFile(str(conf_file_path), ignore_missing=True)
    value = kvs.get(key)
    return value.split(" ") if value is not None else []


def SetBinhost(
    target: str, key: str, uri: str, private: bool = True, max_uris=1
) -> str:
    """Set binhost configuration for the given build target.

    A binhost is effectively a key (Portage env variable) pointing to a set of
    URLs that contains binaries. The configuration is set in .conf files at
    static directories on a build target by build target (and host by host)
    basis.

    This function updates the .conf file by updating the url list.
    The list is updated in the FIFO order.

    Args:
        target: The build target to set configuration for.
        key: The binhost key to set, e.g. POSTSUBMIT_BINHOST.
        uri: The new value for the binhost key,
            e.g. gs://chromeos-prebuilt/foo/bar.
        private: Whether the build target is private.
        max_uris: Maximum number of uris to keep in the conf.

    Returns:
        Path to the updated .conf file.
    """
    _ValidateBinhostMaxURIs(max_uris)
    conf_path = GetBinhostConfPath(target, key, private)
    uris = _get_current_uris(conf_path, key) + [uri]
    osutils.WriteFile(conf_path, '%s="%s"' % (key, " ".join(uris[-max_uris:])))
    return str(conf_path)


def GetBinhostConfPath(target: str, key: str, private: bool = True) -> Path:
    """Returns binhost conf file path.

    Args:
        target: The build target to get configuration file path for.
        key: The binhost key to get, e.g. POSTSUBMIT_BINHOST.
        private: Whether the build target is private.

    Returns:
        Path to the .conf file.
    """
    conf_dir_name = (
        constants.PRIVATE_BINHOST_CONF_DIR
        if private
        else constants.PUBLIC_BINHOST_CONF_DIR
    )
    conf_path = (
        constants.SOURCE_ROOT
        / conf_dir_name
        / "target"
        / f"{target}-{key}.conf"
    )
    _ValidateBinhostConf(conf_path, key)
    return conf_path


def RegenBuildCache(
    chroot: "chroot_lib.Chroot",
    overlay_type: str,
    buildroot: Union[str, Path] = constants.SOURCE_ROOT,
) -> List[str]:
    """Regenerate the Build Cache for the given target.

    Args:
        chroot: The chroot where the regen command will be run.
        overlay_type: one of "private", "public", or "both".
        buildroot: Source root to find overlays.

    Returns:
        The overlays with updated caches.
    """
    overlays = portage_util.FindOverlays(overlay_type, buildroot=buildroot)

    repos_config = portage_util.generate_repositories_configuration(chroot)

    with tempfile.NamedTemporaryFile(
        prefix="repos.conf.", dir=chroot.tmp
    ) as repos_conf:
        repos_conf.write(repos_config.encode("utf-8"))
        repos_conf.flush()
        logging.debug(
            "Using custom repos.conf settings at %s:\n%s",
            repos_conf.name,
            repos_config,
        )

        task = functools.partial(
            portage_util.RegenCache,
            commit_changes=False,
            chroot=chroot,
            repos_conf=repos_conf.name,
        )
        task_inputs = [[o] for o in overlays if os.path.isdir(o)]
        results = parallel.RunTasksInProcessPool(task, task_inputs)

    # Filter out all the unchanged-overlay results.
    return [overlay_dir for overlay_dir in results if overlay_dir]


def GetPrebuiltAclArgs(
    build_target: "build_target_lib.BuildTarget",
) -> List[List[str]]:
    """Read and parse the GS ACL file from the private overlays.

    Args:
        build_target: The build target.

    Returns:
        A list containing all of the [arg, value] pairs. E.g.
        [['-g', 'group_id:READ'], ['-u', 'user:FULL_CONTROL']]
    """
    acl_file = portage_util.FindOverlayFile(
        _GOOGLESTORAGE_GSUTIL_FILE, board=build_target.name
    )

    if not acl_file:
        raise NoAclFileFound("No ACL file found for %s." % build_target.name)

    lines = osutils.ReadFile(acl_file).splitlines()  # type: List[str]
    # Remove comments.
    lines = [line.split("#", 1)[0].strip() for line in lines]
    # Remove empty lines.
    lines = [line for line in lines if line]

    return [line.split() for line in lines]


def GetBinhosts(build_target: "build_target_lib.BuildTarget") -> List[str]:
    """Get the binhosts for the build target.

    Args:
        build_target: The build target.

    Returns:
        The build target's binhosts.
    """
    binhosts = portage_util.PortageqEnvvar(
        "PORTAGE_BINHOST",
        board=build_target.name,
        allow_undefined=True,
    )
    return binhosts.split() if binhosts else []


def ReadDevInstallPackageFile(filename: str) -> List[str]:
    """Parse the dev-install package file.

    Args:
        filename: The full path to the dev-install package list.

    Returns:
        The packages in the package list file.
    """
    with open(filename, encoding="utf-8") as f:
        return [line.strip() for line in f]


def ReadDevInstallFilesToCreatePackageIndex(
    chroot: "chroot_lib.Chroot",
    sysroot: "sysroot_lib.Sysroot",
    package_index_path: str,
    upload_uri: str,
    upload_path: str,
) -> List[str]:
    """Create dev-install Package index specified by package_index_path

    The current Packages file is read and a new Packages file is created based
    on the subset of packages in the _DEV_INSTALL_PACKAGES_FILE.

    Args:
        chroot: The chroot where the sysroot lives.
        sysroot: The sysroot.
        package_index_path: Path to the Packages file to be created.
        upload_uri: The URI (typically GS bucket) where prebuilts will be
            uploaded.
        upload_path: The path at the URI for the prebuilts.

    Returns:
        The list of packages contained in package_index_path, where each package
            string is a category/file.
    """
    # Read the dev-install binhost package file
    devinstall_binhost_filename = chroot.full_path(
        sysroot.path, _DEV_INSTALL_PACKAGES_FILE
    )
    devinstall_package_list = ReadDevInstallPackageFile(
        devinstall_binhost_filename
    )

    # Read the Packages file, remove packages not in package_list
    package_path = chroot.full_path(sysroot.path, "packages")
    CreateFilteredPackageIndex(
        package_path,
        devinstall_package_list,
        package_index_path,
        ConvertGsUploadUri(upload_uri),
        upload_path,
    )

    # We have the list of packages, create full path and verify each one.
    upload_targets_list = GetPrebuiltsForPackages(
        package_path, devinstall_package_list
    )

    return upload_targets_list


def CreateChromePackageIndex(
    chroot: "chroot_lib.Chroot",
    sysroot: "sysroot_lib.Sysroot",
    package_index_path: str,
    gs_bucket: str,
    upload_path: str,
) -> List[str]:
    """Create Chrome package index specified by package_index_path.

    The current Packages file is read and a new Packages file is created based
    on the subset of Chrome packages.

    Args:
        chroot: The chroot where the sysroot lives.
        sysroot: The sysroot.
        package_index_path: Path to the Packages file to be created.
        gs_bucket: The GS bucket where prebuilts will be uploaded.
        upload_path: The path from the GS bucket for the prebuilts.

    Returns:
        The list of packages contained in package_index_path, where each package
            string is a category/file.
    """
    # Get the list of Chrome packages to filter by.
    installed_packages = portage_util.PortageDB(
        chroot.full_path(sysroot.path)
    ).InstalledPackages()
    chrome_packages = []
    for pkg in installed_packages:
        if pkg.category == constants.CHROME_CN and any(
            pn in pkg.pf
            for pn in (constants.CHROME_PN, constants.LACROS_PN, "chrome-icu")
        ):
            chrome_packages.append(pkg.package_info.cpvr)

    # Read the Packages file, remove packages not in the packages list.
    packages_path = chroot.full_path(sysroot.path, "packages")
    CreateFilteredPackageIndex(
        packages_path,
        chrome_packages,
        package_index_path,
        gs_bucket,
        upload_path,
        sudo=True,
    )

    # We have the list of packages, create the full path and verify each one.
    upload_targets_list = GetPrebuiltsForPackages(
        packages_path, chrome_packages
    )

    return upload_targets_list


def ConvertGsUploadUri(upload_uri: str) -> str:
    """Convert a GS URI to the equivalent https:// URI.

    Args:
        upload_uri: The base URI provided (could be GS, https, or really any
            format).

    Returns:
        A new https URL if a gs URI was provided and original URI otherwise.
    """
    if not gs_urls_util.PathIsGs(upload_uri):
        return upload_uri
    return gs_urls_util.GsUrlToHttp(upload_uri)


def CreateFilteredPackageIndex(
    package_path: str,
    package_list: List[str],
    package_index_path: str,
    upload_uri: str,
    upload_path: str,
    sudo: bool = False,
) -> None:
    """Create Package file with filtered packages.

    The created package file (package_index_path) contains only the
    specified packages. The new package file will use the provided values
    for upload_uri and upload_path.

    Args:
        package_path: Absolute path to the standard Packages file.
        package_list: Packages to filter.
        package_index_path: Absolute path for new Packages file.
        upload_uri: The URI where prebuilts will be uploaded.
        upload_path: The path at the URI for the prebuilts.
        sudo: Whether to write the file as the root user.
    """

    def ShouldFilterPackage(package: dict) -> bool:
        """Local func to filter packages not in the package_list.

        Args:
            package: Dictionary with key 'CPV' and package name as value.

        Returns:
            True (filter) if not in the package_list, else False
                (don't filter) if in the package_list.
        """
        value = package["CPV"]
        if value in package_list:
            return False
        else:
            return True

    package_index = binpkg.GrabLocalPackageIndex(package_path)
    package_index.RemoveFilteredPackages(ShouldFilterPackage)
    package_index.SetUploadLocation(upload_uri, upload_path)
    package_index.header["TTL"] = 60 * 60 * 24 * 365
    package_index.WriteFile(package_index_path, sudo=sudo)


def GetPrebuiltsForPackages(
    package_root: str, package_list: List[str]
) -> List[str]:
    """Create list of file paths for the package list and validate they exist.

    Args:
        package_root: Path to 'packages' directory.
        package_list: List of packages.

    Returns:
        List of validated targets.
    """
    upload_targets_list = []
    for pkg in package_list:
        zip_target = pkg + ".tbz2"
        upload_targets_list.append(zip_target)
        full_pkg_path = os.path.join(package_root, pkg) + ".tbz2"
        if not os.path.exists(full_pkg_path):
            raise LookupError("Archive %s does not exist" % full_pkg_path)
    return upload_targets_list


class SnapshotShas(NamedTuple):
    """External and internal snapshot SHAs for the lookup service."""

    external: List[Optional[str]]
    internal: List[Optional[str]]


def lookup_binhosts() -> List[Optional[str]]:
    """Call Cloud Functions to lookup BINHOSTs."""
    # TODO(b/270985155): Implement the lookup logic.
    site_params = config_lib.GetSiteParams()
    snapshot_shas = SnapshotShas([], [])

    # Get the repo.
    try:
        repo = repo_util.Repository.MustFind(constants.SOURCE_ROOT)
    except repo_util.NotInRepoError as e:
        logging.error("Unable to determine a repo directory: %s", e)
        return snapshot_shas

    # Determine the checkout types.
    manifest = repo.Manifest()
    external = manifest.HasRemote(site_params.EXTERNAL_REMOTE)
    internal = manifest.HasRemote(site_params.INTERNAL_REMOTE)

    # Get the snapshot SHAs for each checkout type.
    snapshot_shas.external.extend(_get_snapshot_shas(site_params, not external))
    snapshot_shas.internal.extend(_get_snapshot_shas(site_params, internal))

    return snapshot_shas


def _get_snapshot_shas(
    site_params: "config_lib.AttrDict", internal: bool
) -> List[Optional[str]]:
    """Get the last n=_MAX_BINHOSTS snapshot SHAs using git log.

    We're intentionally swallowing errors related to determining the snapshot
    SHAs since the lookup service will contain logic for these error cases.
    """
    manifest_type = "manifest-internal" if internal else "manifest"
    manifest_dir = os.path.join(constants.SOURCE_ROOT, manifest_type)
    remote_name = (
        site_params.INTERNAL_REMOTE if internal else site_params.EXTERNAL_REMOTE
    )
    try:
        return git.Log(
            manifest_dir,
            format="format:%H",
            max_count=_MAX_BINHOSTS,
            rev=f"{remote_name}/snapshot",
        ).splitlines()
    except cros_build_lib.RunCommandError as e:
        logging.warning(e)
        return []
