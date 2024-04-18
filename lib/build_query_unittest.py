# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for query.py."""

from pathlib import Path
from unittest import mock

import pytest

from chromite.lib import build_query
from chromite.test import portage_testables


# Linter seems unaware of pytest fixtures.
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument


@pytest.fixture
def fake_overlays(tmp_path):
    portage_stable = portage_testables.Overlay(
        root_path=tmp_path / "portage-stable", name="portage-stable"
    )
    chromiumos_overlay = portage_testables.Overlay(
        root_path=tmp_path / "chromiumos-overlay", name="chromiumos"
    )
    eclass_overlay = portage_testables.Overlay(
        root_path=tmp_path / "eclass-overlay", name="eclass-overlay"
    )
    baseboard_fake = portage_testables.Overlay(
        root_path=tmp_path / "baseboard-fake",
        name="baseboard-fake",
    )
    baseboard_fake.create_profile(
        make_defaults={
            "ARCH": "amd64",
            "USE": "some another masked not_masked",
            "USE_EXPAND": "SOME_VAR",
            "SOME_VAR": "baseboard_val",
        },
        use_mask=["masked", "not_masked"],
        use_force=["amd64"],
    )

    overlay_fake = portage_testables.Overlay(
        root_path=tmp_path / "overlay-fake",
        name="fake",
        parent_overlays=[baseboard_fake],
    )
    overlay_fake.create_profile(
        make_defaults={
            "USE": "fake -another -baseboard_fake_private",
            "SOME_VAR": "-* board_val",
            "ANOTHER_VAR": "one_val another_val",
            "USE_EXPAND": "ANOTHER_VAR",
        },
        profile_parents=[baseboard_fake.profiles[Path("base")]],
        use_mask=["-not_masked"],
    )
    overlay_fake.add_package(
        portage_testables.Package(
            category="chromeos-base",
            package="chromeos-bsp-fake",
            version="0.0.1-r256",
            IUSE="another internal +static",
            inherit=["cros-workon", "chromeos-bsp"],
            keywords="*",
        )
    )
    overlay_fake.add_package(
        portage_testables.Package(
            category="chromeos-base",
            package="chromeos-bsp-fake",
            version="9999",
            IUSE="another internal +static",
            inherit=["cros-workon", "chromeos-bsp"],
            keywords="~*",
        )
    )

    baseboard_fake_private = portage_testables.Overlay(
        root_path=tmp_path / "baseboard-fake-private",
        name="baseboard-fake-private",
        parent_overlays=[baseboard_fake],
    )
    baseboard_fake_private.create_profile(
        make_defaults={"USE": "baseboard_fake_private"},
        profile_parents=[baseboard_fake.profiles[Path("base")]],
    )

    overlay_fake_private = portage_testables.Overlay(
        root_path=tmp_path / "overlay-fake-private",
        name="fake-private",
        parent_overlays=[overlay_fake],
        make_conf={
            "CHOST": "x86_64-pc-linux-gnu",
            "USE": "internal",
        },
    )
    overlay_fake_private.create_profile(
        make_defaults={"SOME_VAR": "private_val"},
        profile_parents=[
            baseboard_fake_private.profiles[Path("base")],
            overlay_fake.profiles[Path("base")],
        ],
    )
    overlay_fake_private.add_package(
        portage_testables.Package(
            category="chromeos-base",
            package="chromeos-bsp-fake-private",
            version="0.0.1",
            IUSE="another internal +static",
            inherit=["cros-workon", "chromeos-bsp"],
            keywords="-* ~amd64",
        )
    )
    overlay_fake_private.add_package(
        portage_testables.Package(
            category="chromeos-base",
            package="chromeos-bsp-fake-private",
            version="9999",
            IUSE="another internal +static",
            inherit=["cros-workon", "chromeos-bsp"],
            keywords="~* amd64",
        )
    )

    overlay_faux_private = portage_testables.Overlay(
        root_path=tmp_path / "overlay-faux-private",
        name="faux-private",
        parent_overlays=[
            baseboard_fake,
            overlay_fake,
            baseboard_fake_private,
            overlay_fake_private,
        ],
    )
    overlay_faux_private.create_profile(
        profile_parents=[
            overlay_fake_private.profiles[Path("base")],
        ],
    )

    overlays = [
        portage_stable,
        chromiumos_overlay,
        eclass_overlay,
        baseboard_fake,
        overlay_fake,
        baseboard_fake_private,
        overlay_fake_private,
        overlay_faux_private,
    ]
    with mock.patch(
        "chromite.lib.portage_util.FindOverlays",
        return_value=[str(x.path) for x in overlays],
    ):
        # We just changed the overlays with our mock, we need to clear the
        # cache.
        # pylint: disable=protected-access
        build_query._get_all_overlays_by_name.cache_clear()
        yield overlays


def test_query_overlays(fake_overlays):
    """Test listing all overlays."""
    overlays = {x.name: x for x in build_query.Overlay.find_all()}
    assert overlays["baseboard-fake"].board_name is None
    assert overlays["baseboard-fake"].is_private is False
    assert overlays["fake"].board_name == "fake"
    assert overlays["fake"].is_private is False
    assert overlays["baseboard-fake-private"].board_name is None
    assert overlays["baseboard-fake-private"].is_private is True
    assert overlays["fake-private"].board_name == "fake"
    assert overlays["fake-private"].is_private is True


def test_query_profiles(fake_overlays):
    """Test listing all profiles."""
    profiles = list(build_query.Profile.find_all())
    assert profiles[0].overlay.name == "baseboard-fake"
    assert profiles[0].name == "base"
    assert profiles[0].parents == []
    assert profiles[1].overlay.name == "fake"
    assert profiles[1].name == "base"
    assert profiles[1].parents == [profiles[0]]
    assert profiles[2].overlay.name == "baseboard-fake-private"
    assert profiles[2].name == "base"
    assert profiles[2].parents == [profiles[0]]
    assert profiles[3].overlay.name == "fake-private"
    assert profiles[3].name == "base"
    assert profiles[3].parents == [profiles[2], profiles[1]]


def test_query_boards(fake_overlays):
    """Test listing all boards."""
    board = (
        build_query.Query(build_query.Board)
        .filter(lambda x: x.name == "fake")
        .one()
    )
    assert board.arch == "amd64"
    overlay = [x for x in fake_overlays if x.name == "fake-private"][0]
    assert board.top_level_overlay.path == overlay.path
    assert (
        board.top_level_profile.path == overlay.profiles[Path("base")].full_path
    )


def test_query_ebuilds(fake_overlays):
    """Test listing all ebuilds."""
    ebuilds = list(build_query.Ebuild.find_all())
    found_packages = {str(ebuild) for ebuild in ebuilds}
    assert found_packages == {
        "chromeos-base/chromeos-bsp-fake-0.0.1-r256::fake",
        "chromeos-base/chromeos-bsp-fake-9999::fake",
        "chromeos-base/chromeos-bsp-fake-private-0.0.1::fake-private",
        "chromeos-base/chromeos-bsp-fake-private-9999::fake-private",
    }
    assert all(x.eapi == 7 for x in ebuilds)
    assert all(x.eclasses == ["cros-workon", "chromeos-bsp"] for x in ebuilds)
    assert all(x.iuse == {"another", "internal", "static"} for x in ebuilds)
    assert all(x.iuse_default == {"static"} for x in ebuilds)


@pytest.mark.parametrize(
    ["board_name", "is_variant"],
    [
        ("fake", False),
        ("faux", True),
    ],
)
def test_is_variant(fake_overlays, board_name, is_variant):
    """Test the is_variant property of boards."""
    board = (
        build_query.Query(build_query.Board)
        .filter(lambda x: x.name == board_name)
        .one()
    )
    assert board.is_variant == is_variant


@pytest.mark.parametrize(
    ["cpvr", "arch", "expected_stability"],
    [
        (
            "chromeos-base/chromeos-bsp-fake-0.0.1-r256",
            "amd64",
            build_query.Stability.STABLE,
        ),
        (
            "chromeos-base/chromeos-bsp-fake-9999",
            "amd64",
            build_query.Stability.UNSTABLE,
        ),
        (
            "chromeos-base/chromeos-bsp-fake-private-0.0.1",
            "amd64",
            build_query.Stability.UNSTABLE,
        ),
        (
            "chromeos-base/chromeos-bsp-fake-private-0.0.1",
            "arm",
            build_query.Stability.BAD,
        ),
        (
            "chromeos-base/chromeos-bsp-fake-private-9999",
            "arm",
            build_query.Stability.UNSTABLE,
        ),
        (
            "chromeos-base/chromeos-bsp-fake-private-9999",
            "amd64",
            build_query.Stability.STABLE,
        ),
    ],
)
def test_ebuild_stability(fake_overlays, cpvr, arch, expected_stability):
    """Test the ebuild stability evaluator."""
    ebuild = (
        build_query.Query(build_query.Ebuild)
        .filter(lambda ebuild: ebuild.package_info.cpvr == cpvr)
        .one()
    )
    assert ebuild.get_stability(arch) == expected_stability


def test_make_conf_vars(fake_overlays):
    """Test reading make.conf variables from an overlay."""
    overlay = (
        build_query.Query(build_query.Overlay)
        .filter(lambda overlay: overlay.name == "fake-private")
        .one()
    )
    assert overlay.make_conf_vars == {
        "CHOST": "x86_64-pc-linux-gnu",
        "USE": "internal",
    }


def test_overlay_parents(fake_overlays):
    overlays = {x.name: x for x in build_query.Overlay.find_all()}
    assert list(overlays["baseboard-fake-private"].parents) == [
        overlays["portage-stable"],
        overlays["chromiumos"],
        overlays["eclass-overlay"],
        overlays["baseboard-fake"],
    ]


def test_use_flags(fake_overlays):
    """Test getting the USE flags on a board."""
    board = (
        build_query.Query(build_query.Board)
        .filter(lambda x: x.name == "fake")
        .one()
    )
    assert board.use_flags == {
        "amd64",
        "board_use_fake",
        "not_masked",
        "some",
        "fake",
        "internal",
        "some_var_board_val",
        "some_var_private_val",
        "another_var_one_val",
        "another_var_another_val",
    }


def test_use_flags_set(fake_overlays):
    """Test querying the flags set by a profile."""
    overlay = (
        build_query.Query(build_query.Overlay)
        .filter(lambda overlay: overlay.name == "baseboard-fake")
        .one()
    )
    profile = overlay.profiles[0]
    assert profile.use_flags_set == {
        "amd64",
        "some",
        "another",
        "masked",
        "not_masked",
        "some_var_baseboard_val",
    }


def test_use_flags_unset(fake_overlays):
    """Test querying the flags unset by a profile."""
    overlay = (
        build_query.Query(build_query.Overlay)
        .filter(lambda overlay: overlay.name == "fake")
        .one()
    )
    profile = overlay.profiles[0]
    assert profile.use_flags_unset == {
        "another",
        "baseboard_fake_private",
        "some_var_*",
    }


def test_masked_use_flags(fake_overlays):
    """Test getting the masked_use_flags on a profile."""
    board = (
        build_query.Query(build_query.Board)
        .filter(lambda x: x.name == "fake")
        .one()
    )
    assert board.top_level_profile.masked_use_flags == {"masked"}


def test_query_one(fake_overlays):
    """Test .one() on a query which yields one result."""
    board = (
        build_query.Query(build_query.Board)
        .filter(lambda x: x.name == "fake")
        .one()
    )
    assert board.name == "fake"


def test_query_one_fail_zero(fake_overlays):
    """Test .one() on a query which yields zero results fails."""
    with pytest.raises(StopIteration):
        build_query.Query(build_query.Board).filter(
            lambda x: x.name == "notfake"
        ).one()


def test_query_one_fail_multiple(fake_overlays):
    """Test .one() on a query which yields multiple results fails."""
    with pytest.raises(ValueError):
        build_query.Query(build_query.Ebuild).one()


def test_query_one_or_none(fake_overlays):
    """Test .one_or_none() on a query which yields no results returns None."""
    board = (
        build_query.Query(build_query.Board)
        .filter(lambda x: x.name == "notfake")
        .one_or_none()
    )
    assert not board


def test_query_all(fake_overlays):
    """Test .all() on a query."""
    boards = build_query.Query(build_query.Board).all()
    assert boards == [build_query.Board("fake"), build_query.Board("faux")]


def test_resolve_incremental_variable(fake_overlays):
    """Test correctness Profile.resolve_incremental_variable."""
    board = (
        build_query.Query(build_query.Board)
        .filter(lambda x: x.name == "fake")
        .one()
    )
    assert board.top_level_profile.resolve_var_incremental("SOME_VAR") == {
        "board_val",
        "private_val",
    }
