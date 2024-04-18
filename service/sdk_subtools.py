# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Logic common to scripts/build_sdk_subtools and its build API endpoints."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from chromite.lib import build_target_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_sdk_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import subtool_lib
from chromite.lib import sysroot_lib
from chromite.service import sysroot


# Version file that identifies a chroot setup as a subtools chroot.
SUBTOOLS_CHROOT_VERSION_FILE = Path("/etc/cros_subtools_chroot_version")

# Packages that the subtools builder should never rebuild. This is a superset of
# sysroot._CRITICAL_SDK_PACKAGES. Packages here should only update when a new
# SDK becomes available.
EXCLUDE_PACKAGES = (
    "dev-embedded/hps-sdk",
    "dev-lang/rust",
    "dev-lang/go",
    "sys-libs/glibc",
    "sys-devel/gcc",
    "sys-devel/binutils",
    "sys-kernel/linux-headers",
    "sys-devel/llvm",
)

# Path in subtools chroot that holds export package manifests.
SUBTOOLS_EXPORTS_CONFIG_DIR = Path("/etc/cros/sdk-packages.d")

# Path where subtools will be bundled.
SUBTOOLS_BUNDLE_WORK_DIR = Path("/var/tmp/cros-subtools")


def is_inside_subtools_chroot() -> bool:
    """Returns True if we are inside subtools chroot."""
    return SUBTOOLS_CHROOT_VERSION_FILE.exists()


def assert_inside_subtools_chroot() -> None:
    """Die if not _is_inside_subtools_chroot()."""
    if not is_inside_subtools_chroot():
        cros_build_lib.Die("Not in subtools SDK")


def setup_base_sdk(
    build_target: build_target_lib.BuildTarget,
    setup_chroot: bool,
    sudo: Optional[bool] = False,
) -> None:
    """SetupBoard workalike that converts a regular SDK into a subtools chroot.

    Runs inside the /build/amd64-subtools-host subtools SDK chroot.
    """
    cros_build_lib.AssertInsideChroot()

    # "Convert" the SDK into a subtools SDK.
    if not is_inside_subtools_chroot():
        # Copy the sentinel file that chromite uses to indicate the chroot's
        # duality. The file is copied (not moved) so that other chromite tooling
        # continues to work.
        content = Path(cros_sdk_lib.CHROOT_VERSION_FILE).read_text(
            encoding="utf-8"
        )
        osutils.WriteFile(SUBTOOLS_CHROOT_VERSION_FILE, content, sudo=sudo)

    if setup_chroot:
        logging.info("Setting up subtools SDK in %s.", build_target.root)
        osutils.SafeMakedirs(SUBTOOLS_EXPORTS_CONFIG_DIR, sudo=sudo)


def _run_system_emerge(
    emerge_cmd: List[Union[str, Path]],
    extra_env: Dict[str, str],
    use_goma: bool,
    use_remoteexec: bool,
    reason: str,
) -> None:
    """Runs an emerge command, updating the live system."""
    extra_env = extra_env.copy()
    with osutils.TempDir() as tempdir:
        extra_env[constants.CROS_METRICS_DIR_ENVVAR] = tempdir
        with sysroot.RemoteExecution(use_goma, use_remoteexec):
            logging.info("Merging %s now.", reason)
            try:
                # TODO(b/277992359): Bazel.
                cros_build_lib.sudo_run(
                    emerge_cmd,
                    preserve_env=True,
                    extra_env=extra_env,
                )
                logging.info("Merging %s complete.", reason)
            except cros_build_lib.RunCommandError as e:
                failed_pkgs = portage_util.ParseDieHookStatusFile(tempdir)
                logging.error("Merging %s failed on %s", reason, failed_pkgs)
                raise sysroot_lib.PackageInstallError(
                    f"Merging {reason} failed",
                    e.result,
                    exception=e,
                    packages=failed_pkgs,
                ) from e


def update_packages(packages: List[str], jobs: Optional[int] = None) -> None:
    """The BuildPackages workalike for installing into the subtools SDK."""
    assert_inside_subtools_chroot()
    cros_build_lib.AssertNonRootUser()

    # sysroot.BuildPackages can't (yet?) be used here, because it _only_
    # supports cross-compilation. SDK package management is currently all
    # handled by src/scripts/sdk_lib/make_chroot.sh (b/191307774).

    config = sysroot.BuildPackagesRunConfig(
        packages=packages,
        jobs=jobs,
        usepkg=False,
        clean_build=False,
        eclean=False,
    )

    emerge = [constants.CHROMITE_BIN_DIR / "parallel_emerge"]
    extra_env = config.GetExtraEnv()
    emerge_flags = config.GetEmergeFlags()
    exclude_pkgs = " ".join(EXCLUDE_PACKAGES)
    emerge_flags.extend(
        [
            f"--useoldpkg-atoms={exclude_pkgs}",
            f"--rebuild-exclude={exclude_pkgs}",
        ]
    )
    cmd = emerge + emerge_flags + config.GetPackages()
    _run_system_emerge(
        cmd,
        extra_env,
        config.use_goma,
        config.use_remoteexec,
        reason="subtools builder SDK packages",
    )


def bundle_and_prepare_upload(
    upload_filter: Optional[List[str]] = None,
) -> Tuple[List[Path], subtool_lib.InstalledSubtools]:
    """Searches for configured subtools, bundles, and prepares upload metadata.

    Args:
        upload_filter: If provided, uploads only subtools whose `name` proto
            field value is in the list. If None, uploads everything.

    Returns:
        A tuple: the list of upload metadata paths, and the InstalledSubtools
            that created them.
    """
    assert_inside_subtools_chroot()

    subtools = subtool_lib.InstalledSubtools(
        config_dir=SUBTOOLS_EXPORTS_CONFIG_DIR,
        work_root=SUBTOOLS_BUNDLE_WORK_DIR,
    )
    subtools.bundle_all()
    return (subtools.prepare_uploads(upload_filter), subtools)


def upload_prepared_bundles(use_production: bool, bundles: List[Path]) -> None:
    """Uploads the pre-bundled subtools at each of the provided paths.

    Args:
        use_production: Whether to upload to production environments.
        bundles: The list of bundled metadata paths to upload.
    """
    subtools = subtool_lib.BundledSubtools(bundles)
    subtools.upload(use_production)


def bundle_and_upload(
    use_production: bool = False, upload_filter: Optional[List[str]] = None
) -> subtool_lib.InstalledSubtools:
    """Helper to bundle and upload from within the chroot."""
    (bundles, subtools) = bundle_and_prepare_upload(upload_filter)
    upload_prepared_bundles(use_production, bundles)
    return subtools
