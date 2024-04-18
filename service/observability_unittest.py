# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for service/observability.py methods."""

import itertools
import os
from typing import Dict, List

from chromite.lib import constants
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib.parser import package_info
from chromite.service import observability


def test_parse_package_name__full_with_mmpe():
    """Test version parsing for 4-part version number with no suffix."""
    lacros_pkg_info = package_info.parse(
        "chromeos-base/chromeos-lacros-104.0.5083.0-r1"
    )
    lacros_identifier = observability.parse_package_name(lacros_pkg_info)

    assert lacros_identifier.package_version.major == 104
    assert lacros_identifier.package_version.minor == 0
    assert lacros_identifier.package_version.patch == 5083
    assert lacros_identifier.package_version.extended == 0
    assert lacros_identifier.package_version.revision == 1
    assert lacros_identifier.package_version.full_version == lacros_pkg_info.vr
    assert lacros_identifier.package_name.atom == lacros_pkg_info.atom
    assert lacros_identifier.package_name.category == lacros_pkg_info.category
    assert (
        lacros_identifier.package_name.package_name == lacros_pkg_info.package
    )
    assert lacros_identifier.package_version.full_version == "104.0.5083.0-r1"

    assert (
        lacros_identifier.package_name.atom == "chromeos-base/chromeos-lacros"
    )
    assert lacros_identifier.package_name.category == "chromeos-base"
    assert lacros_identifier.package_name.package_name == "chromeos-lacros"


def test_parse_package_name__full_with_mmp():
    """Test version parsing for standard 3-part version number."""
    py_pkg_info = package_info.parse("dev-lang/python-3.6.15-r2")
    py_identifier = observability.parse_package_name(py_pkg_info)

    assert py_identifier.package_version.major == 3
    assert py_identifier.package_version.minor == 6
    assert py_identifier.package_version.patch == 15
    assert py_identifier.package_version.extended == 0
    assert py_identifier.package_version.revision == 2
    assert py_identifier.package_version.full_version == "3.6.15-r2"

    assert py_identifier.package_name.atom == "dev-lang/python"
    assert py_identifier.package_name.category == "dev-lang"
    assert py_identifier.package_name.package_name == "python"


def test_parse_package_name__full_with_suffix():
    """Test version parsing for 2-part version number with suffix included."""
    fake_pkg_info = package_info.parse("cat/test-pkg-1.1b_alpha3")
    fake_identifier = observability.parse_package_name(fake_pkg_info)

    assert fake_identifier.package_version.major == 1
    assert fake_identifier.package_version.minor == 1
    assert fake_identifier.package_version.patch == 0
    assert fake_identifier.package_version.extended == 0
    assert fake_identifier.package_version.revision == 0
    assert fake_identifier.package_version.full_version == "1.1b_alpha3"

    assert fake_identifier.package_name.atom == "cat/test-pkg"
    assert fake_identifier.package_name.category == "cat"
    assert fake_identifier.package_name.package_name == "test-pkg"


_FAKE_DATA = "FAKE DATA"
_FAKE_DATA_SIZE = len(_FAKE_DATA)
_FAKE_FILES = [
    ("dir", "lib64"),
    (
        "obj",
        "lib64/libext2fs.so.2.4",
        "a6723f44cf82f1979e9731043f820d8c",
        "1390848093",
    ),
    ("dir", "dir with spaces"),
    (
        "obj",
        "dir with spaces/file with spaces",
        "cd4865bbf122da11fca97a04dfcac258",
        "1390848093",
    ),
    ("sym", "lib64/libe2p.so.2", "->", "libe2p.so.2.3", "1390850489"),
    "foo",
]
_FAKE_EXPECTED_APPARENT_PACKAGE_SIZE = sum(
    [_FAKE_DATA_SIZE for f in _FAKE_FILES if f[0] == "obj"]
)
_FAKE_EXPECTED_PACKAGE_DISK_USAGE = sum(
    [8 * 512 for f in _FAKE_FILES if f[0] == "obj"]
)


def make_portage_db(
    tmp_path: os.PathLike,
    pkgs: Dict[str, List[str]] = None,
    fake_vdb_subdir: str = portage_util.VDB_PATH,
    fake_install_subdir: str = "",
):
    """Construct an artificial, ephemeral Portage package database on-disk.

    Useful for testing behavior of ISCP methods which require a usable Portage
    DB to provide portage_util.InstalledPackage objects and all the trimmings
    therein.

    Args:
        tmp_path: A temporary path to build a fake image filesystem in. Provided
            by calling methods only; can use tmp_path for pytest or some other
            temporary path.
        pkgs: A dictionary mapping category to PVR values. If not provided, a
            set of default values is used.
        fake_vdb_subdir: A relative path from the mount point's root to the
            Portage database fileset. Since different partitions use different
            defaults for the database fileset, allow custom VDB paths to more
            easily mimic that behavior.
        fake_install_subdir: A relative path from the mount point's root to the
            location of the installed package files on the image. Again,
            different partitions use different defaults, so we want to mimic
            that behavior if needed.
    """
    if pkgs is None:
        pkgs = {
            "category1": ["package-1", "package-2"],
            "category2": ["package-3", "package-4"],
            "with": ["files-1"],
            "dash-category": ["package-5"],
        }

    # create a rough approximation of a Portage DB filesystem with the fake data
    # given above.
    fake_vdb = tmp_path / fake_vdb_subdir

    for cat, pvrs in pkgs.items():
        catpath = fake_vdb / cat
        os.makedirs(catpath)
        for pkg in pvrs:
            pkgpath = catpath / pkg
            os.makedirs(pkgpath)
            osutils.Touch(pkgpath / (pkg + ".ebuild"))
            osutils.WriteFile(
                pkgpath / "CONTENTS",
                "".join(" ".join(entry) + "\n" for entry in _FAKE_FILES),
            )

    # add fake installed files to this new filesystem
    for fake_file_data in _FAKE_FILES:
        if fake_file_data[0] == "obj":
            fake_filename = tmp_path / fake_install_subdir / fake_file_data[1]
            osutils.WriteFile(fake_filename, _FAKE_DATA, makedirs=True)

    db = portage_util.PortageDB(
        root=tmp_path,
        vdb=fake_vdb_subdir,
        package_install_path=fake_install_subdir,
    )
    return db


def convert_pkg_dict_to_package_identifier(pkgs: Dict[str, List[str]]):
    """Generate PackageIdentifier instances from test data in dictionary."""
    pkgs_flattened = []
    for cat, pkg_list in pkgs.items():
        pkgs_flattened += list(zip(itertools.repeat(cat), pkg_list))
    pkgs_flattened = [f"{c}/{p}" for c, p in pkgs_flattened]
    expected_packages = [
        observability.parse_package_name(package_info.parse(pkg))
        for pkg in pkgs_flattened
    ]
    return expected_packages


def test_get_package_details_for_partition__rootfs(tmp_path):
    """Test PortageDB reads & size calculation for standard (rootfs) db."""
    pkgs = {
        "dev-lang": ["python-3.6.15-r2", "rust-1.58.1-r1"],
        "chromeos-base": [
            "chromeos-chrome-104.0.5107.2_rc-r1",
            "autotest-0.0.2-r15979",
        ],
    }
    expected_packages = convert_pkg_dict_to_package_identifier(pkgs)
    db = make_portage_db(tmp_path=tmp_path, pkgs=pkgs)
    packages = [(pkg, pkg.ListContents()) for pkg in db.InstalledPackages()]
    print(packages)
    result = observability.get_package_details_for_partition(
        installation_path=tmp_path, pkgs=packages
    )
    assert len(result) == 4
    for expected in expected_packages:
        assert expected in result
        # verify apparent size
        assert result[expected][0] == _FAKE_EXPECTED_APPARENT_PACKAGE_SIZE
        # verify disk utilization size
        assert result[expected][1] == _FAKE_EXPECTED_PACKAGE_DISK_USAGE


def test_get_package_details_for_partition__stateful(tmp_path):
    """Test PortageDB reads & size calculation for non-standard db."""
    pkgs = {
        "dev-lang": ["python-3.6.15-r2", "rust-1.58.1-r1"],
        "chromeos-base": [
            "chromeos-chrome-104.0.5107.2_rc-r1",
            "autotest-0.0.2-r15979",
        ],
    }
    expected_packages = convert_pkg_dict_to_package_identifier(pkgs)
    db = make_portage_db(
        tmp_path=tmp_path,
        pkgs=pkgs,
        fake_vdb_subdir="var_overlay/db/pkg",
        fake_install_subdir="dev_image",
    )
    packages = [(pkg, pkg.ListContents()) for pkg in db.InstalledPackages()]
    result = observability.get_package_details_for_partition(
        installation_path=(tmp_path / "dev_image"), pkgs=packages
    )
    assert len(result) == 4
    for expected in expected_packages:
        assert expected in result
        assert result[expected][0] == _FAKE_EXPECTED_APPARENT_PACKAGE_SIZE
        # verify disk utilization size
        assert result[expected][1] == _FAKE_EXPECTED_PACKAGE_DISK_USAGE


def test_get_package_details_for_partition__bad_install_path(tmp_path):
    """Test PortageDB read failure mode for an invalid package install path."""
    pkgs = {
        "dev-lang": ["python-3.6.15-r2", "rust-1.58.1-r1"],
        "chromeos-base": [
            "chromeos-chrome-104.0.5107.2_rc-r1",
            "autotest-0.0.2-r15979",
        ],
    }
    expected_packages = convert_pkg_dict_to_package_identifier(pkgs)
    db = make_portage_db(
        tmp_path=tmp_path,
        pkgs=pkgs,
        fake_vdb_subdir="var_overlay/db/pkg",
        fake_install_subdir="foo/bar/baz",
    )
    packages = [(pkg, pkg.ListContents()) for pkg in db.InstalledPackages()]
    # mismatched custom install path - hilariously, the provided path isn't used
    # for anything except exception raising, so all data remains the same.
    result = observability.get_package_details_for_partition(
        installation_path="bad_path", pkgs=packages
    )
    assert len(result) == 4
    for expected in expected_packages:
        assert expected in result
        # Since a bad path was provided, we expect all packages to report back
        # as have 0 bytes on the provided partition.
        # TODO(zland): make this mechanism a little less brittle?
        assert result[expected] == (0, 0)


def test_get_installed_package_data__bad_image_type(tmp_path, caplog):
    """Ensure unsupported image types are not mounted and crawled for pkgs."""
    result = observability.get_installed_package_data(
        constants.IMAGE_TYPE_FACTORY, tmp_path / "chromiumos_factory_image.bin"
    )
    assert "Provided image type is not supported." in caplog.text
    assert not result
