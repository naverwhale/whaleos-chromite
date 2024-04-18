# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for testing spiders in portage_explorer."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import chromite as cr
from chromite.contrib.portage_explorer import spiderlib
from chromite.lib.parser import package_info


def create_overlays(
    tmp_path: Path, name: str
) -> Tuple[cr.test.Overlay, spiderlib.Overlay]:
    """Create test overlays for unit testing spiders.

    Create the cr.test.Overlay and spiderlib.Overlay versions of the overlays to
    replicate in the temporary path.

    Args:
        tmp_path: Temporary path to put mock data in
        name: Name of overlay

    Returns:
        A tuple containing the cr.test.Overlay and spiderlib.Overlay version of
        the overlay
    """
    overlay_path = tmp_path / f"src/overlay-{name}"
    test_overlay = cr.test.Overlay(overlay_path, name)
    spider_overlay = spiderlib.Overlay(overlay_path.relative_to(tmp_path), name)
    return (test_overlay, spider_overlay)


def create_profiles(
    tmp_path: Path,
    test_overlay: cr.test.Overlay,
    profile_names: List[str],
    parent_profiles: Optional[Dict[str, cr.test.Profile]] = None,
    make_defaults: Optional[Dict[str, Dict[str, str]]] = None,
) -> Tuple[
    Dict[str, cr.test.Profile],
    Dict[str, spiderlib.Profile],
    Dict[str, spiderlib.Profile],
]:
    """Create test profiles for unit testing spiders.

    Create the unpopulated and populated versions of the profiles for the
    overlay to represent the before and after of running the spider against the
    mock data.

    Args:
        tmp_path: Temporary path to put mock data in.
        test_overlay: cr.test.Overlay instance to create a profile within.
        profile_names: List of strings representing profile names for this
            overlay.
        parent_profiles: Dict of profile names matched to corresponding
            portage_testables profile.
        make_defaults: Dict of profile names matched to corresponding
            make_defaults from portage_testables when creating profiles, which
            is a dict of the variable and its value.

    Returns:
        A tuple containing the cr.test.Profiles, the profiles to run through the
        spider, and the profiles to compare the output against
    """
    test_profiles = {}
    unpopulated_profiles = {}
    populated_profiles = {}
    if not parent_profiles:
        parent_profiles = {}
    if not make_defaults:
        make_defaults = {}
    for profile_name in profile_names:
        test_profile = test_overlay.create_profile(
            Path(profile_name),
            profile_parents=parent_profiles.get(profile_name, []),
            make_defaults=make_defaults.get(profile_name, {}),
        )
        test_profiles[profile_name] = test_profile
        unpopulated_spider_profile = spiderlib.Profile(
            f"{test_profile.overlay}:{profile_name}",
            test_profile.full_path.relative_to(tmp_path),
            profile_name,
        )
        unpopulated_profiles[profile_name] = unpopulated_spider_profile
        populated_spider_profile = spiderlib.Profile(
            f"{test_profile.overlay}:{profile_name}",
            test_profile.full_path.relative_to(tmp_path),
            profile_name,
        )
        for parent in parent_profiles.get(profile_name, []):
            populated_spider_profile.parent_profiles.append(
                f"{parent.overlay}:{parent.path}"
            )
        spider_flags = []
        for flag in make_defaults.get(profile_name, {}).get("USE", "").split():
            flag_name = flag.strip("-")
            spider_use = spiderlib.ProfileUse(
                flag_name, spiderlib.UseState(not flag.startswith("-"))
            )
            spider_flags.append(spider_use)
        populated_spider_profile.use_flags = sorted(
            spider_flags, key=lambda use_flag: use_flag.name
        )
        populated_profiles[profile_name] = populated_spider_profile
    return (test_profiles, unpopulated_profiles, populated_profiles)


def create_ebuilds(
    tmp_path: Path,
    test_overlay: cr.test.Overlay,
    packages: Dict[str, spiderlib.TestEbuild],
):
    """Create test ebuilds for unit testing spiders.

    Create the unpopulated and populated versions of ebuilds for the overlay to
    represent the before and after of running the spider against mock data.
    Unpopulated ebuilds only contain information gathered from ebuild directory.
    Populated ebuilds contain information after sourcing the ebuild.

    Args:
        tmp_path: Temporary path to put mock data in
        test_overlay: cr.test.Overlay instance to create ebuilds in
        packages: Dict of cpv to the metadata associated with the ebuild in that
            cpv.

    Returns:
        A tuple containing the cr.test.Packages, the unpopulated ebuilds, and
        populated ebuilds.
    """
    test_packages = []
    unpopulated_ebuilds = []
    populated_ebuilds = []
    for cpv in packages:
        metadata = packages[cpv]
        package = package_info.parse(cpv)
        test_package = cr.test.Package(
            package.category, package.package, package.vr
        )
        test_packages.append(test_package)
        test_overlay.add_package(test_package)
        md5_path = (
            test_overlay.path / "metadata" / "md5-cache" / package.category
        )
        md5_path.mkdir(parents=True, exist_ok=True)
        pdepend_text = (
            f"PDEPEND={metadata.pdepend}\n" if metadata.pdepend else ""
        )
        (md5_path / package.pvr).write_text(
            f"EAPI={metadata.eapi}\n"
            f"DESCRIPTION={metadata.description}\n"
            f"HOMEPAGE={metadata.homepage}\n"
            f"LICENSE={metadata.license_}\n"
            f"SLOT={metadata.slot}\n"
            f"SRC_URI={metadata.src_uri}\n"
            f"RESTRICT={metadata.restrict}\n"
            f"DEPEND={metadata.depend}\n"
            f"RDEPEND={metadata.rdepend}\n"
            f"BDEPEND={metadata.bdepend}\n"
            f"{pdepend_text}"
            f"IUSE={metadata.iuse}\n"
            f"_eclasses_={metadata.inherit}",
            encoding="utf-8",
        )
        ebuild_path = (
            test_overlay.path.relative_to(tmp_path) / package.relative_path
        )
        spider_ebuild = spiderlib.Ebuild(ebuild_path, package)
        unpopulated_ebuilds.append(spider_ebuild)
        eclasses_inherited = metadata.inherit.split()
        hold_eclasses = sorted(eclasses_inherited[::2])
        spider_ebuild_metadata = spiderlib.Ebuild(
            ebuild_path,
            package,
            metadata.eapi,
            metadata.description,
            metadata.homepage,
            metadata.license_,
            metadata.slot,
            metadata.src_uri,
            metadata.restrict,
            metadata.depend,
            metadata.rdepend,
            metadata.bdepend,
            metadata.pdepend,
            [],
            hold_eclasses,
        )
        for flag in metadata.iuse.split():
            spider_ebuild_metadata.add_use_flag(flag)
        spider_ebuild_metadata.use_flags.sort(key=lambda flag: flag.name)
        populated_ebuilds.append(spider_ebuild_metadata)
    unpopulated_ebuilds.sort(key=lambda ebuild: ebuild.package.cpf)
    return (test_package, unpopulated_ebuilds, populated_ebuilds)


def create_eclasses(
    tmp_path: Path, test_overlay: cr.test.Overlay, eclasses: List[str]
):
    """Create test eclasses in tmp dir for unit testing spiders.

    Args:
        tmp_path: Temporary path to put mock data in.
        test_overlay: The test overlay to create these eclasses for.
        eclasses: List of eclass names.

    Returns:
        A tuple of a list of unpopulated spiderlib.Eclass instances (just
        src_path and name filled in) and a list of populated spiderlib.Eclass
        instances for inheritance.
    """
    eclass_folder = test_overlay.path / "eclass"
    eclass_folder.mkdir(parents=True, exist_ok=True)
    unpopulated_eclasses = []
    populated_eclasses = []
    for eclass in eclasses:
        eclass_path = eclass_folder / f"{eclass}.eclass"
        eclass_path.write_text("", encoding="utf-8")
        unpopulated_eclasses.append(
            spiderlib.Eclass(eclass_path.relative_to(tmp_path), eclass)
        )
    unpopulated_eclasses.sort(key=lambda eclass: eclass.name)
    return (unpopulated_eclasses, populated_eclasses)
