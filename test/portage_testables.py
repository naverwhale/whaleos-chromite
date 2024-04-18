# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for setting up Portage objects for testing."""

from __future__ import division

import itertools
import os
from pathlib import Path
from typing import Dict, Iterable, Tuple, Union

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib.parser import package_info


__all__ = ["Overlay", "Package", "Profile", "Sysroot"]

_EXCLUDED_OVERLAYS = ("chromiumos", "portage-stable")
_MD5CACHE_VARS = (
    "BDEPEND",
    "DEPEND",
    "DESCRIPTION",
    "EAPI",
    "IUSE",
    "KEYWORDS",
    "LICENSE",
    "RDEPEND",
    "SLOT",
)

# We don't know the md5sum for eclasses we don't have, so use a garbage value.
_FAKE_MD5 = "deadbeef" * 4


def _dict_to_conf(dictionary):
    """Helper to format a dictionary into a layout.conf file."""
    output = []
    for key in sorted(dictionary.keys()):
        output.append("%s = %s" % (key, dictionary[key]))

    output.append("\n")
    return "\n".join(output)


def _dict_to_ebuild(dictionary):
    """Helper to format a dictionary into an ebuild file."""
    output = []
    for key in dictionary.keys():
        output.append(f'{key}="{dictionary[key]}"')

    output.append("\n")
    return "\n".join(output)


def _dict_to_md5cache(dictionary):
    """Helper to format a dictionary into a md5-cache file."""
    return "".join(f"{key}={value}\n" for key, value in dictionary.items())


class Overlay:
    """Portage overlay object, responsible for all writes to its directory."""

    HIERARCHY_NAMES = (
        "stable",
        "project",
        "chipset",
        "baseboard",
        "board",
        "board-private",
    )

    def __init__(self, root_path, name, parent_overlays=None, make_conf=None):
        self.path = Path(root_path)
        self.name = str(name)
        self.parent_overlays = (
            tuple(parent_overlays) if parent_overlays else None
        )
        self.packages = []
        self.profiles = {}
        self.categories = set()
        self.make_conf = make_conf or {}

        self._write_layout_conf()
        self._write_make_conf()

    def __contains__(
        self, item: Union[package_info.CPV, package_info.PackageInfo]
    ):
        if not isinstance(item, (package_info.CPV, package_info.PackageInfo)):
            raise TypeError(f"Expected a CPV but received a {type(item)}")

        if isinstance(item, package_info.CPV):
            ebuild_path = (
                self.path / item.category / item.package / f"{item.pv}.ebuild"
            )
        else:
            ebuild_path = self.path / item.relative_path

        return ebuild_path.is_file()

    def _write_layout_conf(self):
        """Write the layout.conf as part of this Overlay's initialization."""
        layout_conf_path = self.path / "metadata" / "layout.conf"
        parent_names = " ".join(m.name for m in self.parent_overlays or [])
        conf = {
            "masters": "portage-stable chromiumos eclass-overlay "
            + parent_names,
            "profile-formats": "portage-2 profile-default-eapi",
            "profile_eapi_when_unspecified": "5-progress",
            "repo-name": str(self.name),
            "thin-manifests": "true",
            "use-manifests": "strict",
        }

        osutils.WriteFile(layout_conf_path, _dict_to_conf(conf), makedirs=True)

    def _write_make_conf(self):
        """Write the make.conf as a part of this Overlay's initialization."""
        make_conf_path = self.path / "make.conf"
        osutils.WriteFile(make_conf_path, _dict_to_ebuild(self.make_conf))

    def add_package(self, pkg):
        """Add a package to this overlay.

        Adds the package to the Overlay object's internal storage and writes the
        package metadata to the Overlay's directory.
        """
        self.packages.append(pkg)
        self._write_ebuild(pkg)
        if pkg.category not in self.categories:
            self.categories.add(pkg.category)
            osutils.WriteFile(
                self.path / "profiles" / "categories",
                pkg.category + "\n",
                mode="a",
                makedirs=True,
            )

    def _write_ebuild(self, pkg: "Package"):
        """Write a Package object out to an ebuild file in this Overlay."""
        ebuild_path = (
            self.path
            / pkg.category
            / pkg.package
            / (pkg.package + "-" + pkg.version + ".ebuild")
        )

        # EAPI must be the first thing defined in an ebuild, so write this
        # config before anything else.
        base_conf = {
            "EAPI": pkg.eapi,
            "KEYWORDS": pkg.keywords,
            "SLOT": pkg.slot,
        }
        base_conf.update(pkg.variables)

        osutils.WriteFile(
            ebuild_path, _dict_to_ebuild(base_conf), makedirs=True
        )

        # Write an eclass inheritance line, if needed.
        if pkg.format_eclass_line():
            osutils.WriteFile(ebuild_path, pkg.format_eclass_line(), mode="a")

        extra_conf = {
            "DEPEND": pkg.depend,
            "RDEPEND": pkg.rdepend,
        }

        osutils.WriteFile(ebuild_path, _dict_to_ebuild(extra_conf), mode="a")

        md5cache_path = (
            self.path / "metadata" / "md5-cache" / pkg.package_info.cpvr
        )
        md5cache_vars = {}
        for var in _MD5CACHE_VARS:
            if var in base_conf:
                md5cache_vars[var] = base_conf[var]
            elif var in extra_conf:
                md5cache_vars[var] = extra_conf[var]

        md5cache_vars["_md5_"] = osutils.MD5HashFile(ebuild_path)
        md5cache_vars["_eclasses_"] = "\t".join(
            f"{x}\t{_FAKE_MD5}" for x in pkg.inherit
        )

        osutils.WriteFile(
            md5cache_path, _dict_to_md5cache(md5cache_vars), makedirs=True
        )

    def create_profile(
        self,
        path=None,
        profile_parents=None,
        make_defaults=None,
        use_mask=(),
        use_force=(),
    ):
        """Create a profile in this overlay.

        Creates a profile with the given settings and writes the profile with
        those settings to the Overlay's directory.
        """
        path = Path(path) if path else Path("base")
        if path in self.profiles:
            raise KeyError("A profile with that path already exists!")

        prof = Profile(
            self,
            path,
            parents=profile_parents,
            make_defaults=make_defaults,
            use_mask=use_mask,
            use_force=use_force,
        )

        self._write_profile(prof)
        self.profiles[path] = prof

        return prof

    def _write_profile(self, profile):
        """Write a Profile object out to this Overlay's directory."""
        osutils.WriteFile(
            self.path / "profiles" / profile.path / "make.defaults",
            _dict_to_ebuild(profile.make_defaults),
            makedirs=True,
        )
        if profile.parents:
            formatted_parents = []
            for parent in profile.parents:
                formatted_parents.append(
                    str(parent.overlay) + ":" + str(parent.path)
                )
            osutils.WriteFile(
                self.path / "profiles" / profile.path / "parent",
                "\n".join(formatted_parents) + "\n",
            )
        if profile.use_mask:
            osutils.WriteFile(
                self.path / "profiles" / profile.path / "use.mask",
                "\n".join(profile.use_mask) + "\n",
            )
        if profile.use_force:
            osutils.WriteFile(
                self.path / "profiles" / profile.path / "use.force",
                "\n".join(profile.use_force) + "\n",
            )


class Sysroot:
    """Sysroot object representing a functional Portage directory."""

    # These PORTDIR_OVERLAY entries are necessary for any Portage operations to
    # function as the chroot's profile is parsed first, even if that profile is
    # not used by the sysroot at all.
    # This tuple should effectively be:
    # /mnt/host/source/src/third_party/portage-stable
    # /mnt/host/source/src/third_party/chromiumos-overlay
    # /mnt/host/source/src/third_party/eclass-overlay
    _BOOTSTRAP_PORTDIR_OVERLAYS = (
        os.path.join(
            constants.CHROOT_SOURCE_ROOT, constants.PORTAGE_STABLE_OVERLAY_DIR
        ),
        os.path.join(
            constants.CHROOT_SOURCE_ROOT, constants.CHROMIUMOS_OVERLAY_DIR
        ),
        os.path.join(
            constants.CHROOT_SOURCE_ROOT, constants.ECLASS_OVERLAY_DIR
        ),
    )

    def __init__(self, path, profile, overlays):
        self.path = path

        osutils.SafeMakedirs(path / "etc" / "portage" / "profile")
        osutils.SafeMakedirs(path / "etc" / "portage" / "hooks")

        osutils.SafeSymlink(
            profile.full_path, path / "etc" / "portage" / "make.profile"
        )

        sysroot_conf = {
            "ACCEPT_KEYWORDS": "amd64",
            "ROOT": str(self.path),
            "SYSROOT": str(self.path),
            "ARCH": "amd64",
            "PORTAGE_CONFIGROOT": str(self.path),
            "PORTDIR": str(overlays[0].path),
            "PORTDIR_OVERLAY": "\n".join(
                itertools.chain(
                    (str(o.path) for o in overlays),
                    Sysroot._BOOTSTRAP_PORTDIR_OVERLAYS,
                )
            ),
            "PORTAGE_BINHOST": "",
            "USE": "",
            "PKGDIR": str(self.path / "packages"),
            "PORTAGE_TMPDIR": str(self.path / "tmp"),
            "DISTDIR": str(self.path / "var" / "lib" / "portage" / "distfiles"),
        }

        osutils.WriteFile(
            self.path / "etc" / "portage" / "make.conf",
            _dict_to_ebuild(sysroot_conf),
        )

        osutils.WriteFile(
            self.path / "etc" / "portage" / "package.mask",
            "".join(f"*/*::{o}\n" for o in _EXCLUDED_OVERLAYS),
        )

    @property
    def _env(self):
        """Return a dict of the environment variables for this sysroot."""
        return {
            "PORTAGE_CONFIGROOT": str(self.path),
            "ROOT": str(self.path),
            "SYSROOT": str(self.path),
            "BROOT": str(self.path),
        }

    def run(self, cmd, **kwargs):
        """Run a command against this sysroot.

        This method sets up the equivalent calling environment to the `emerge`
        wrappers we generate but targeted at this specific sysroot, which has
        an arbitrary path in the test environment. This means that Portage
        commands such as `equery list '*'` will correctly run against this
        sysroot.
        """
        extra_env = self._env
        extra_env.update(kwargs.pop("extra_env", {}))
        kwargs.setdefault("encoding", "utf-8")

        return cros_build_lib.run(cmd, extra_env=extra_env, **kwargs)


class Profile:
    """Portage profile, lives in an overlay."""

    def __init__(
        self,
        overlay,
        path,
        parents=None,
        make_defaults=None,
        use_mask=(),
        use_force=(),
    ):
        self.overlay = overlay.name
        self.path = path
        self.full_path = overlay.path / "profiles" / path
        self.parents = tuple(parents) if parents else None
        self.make_defaults = make_defaults if make_defaults else {"USE": ""}
        self.use_mask = tuple(use_mask)
        self.use_force = tuple(use_force)


class Package:
    """Portage package, lives in an overlay."""

    inherit: Tuple[str]
    variables: Dict[str, str]

    def __init__(
        self,
        category,
        package,
        version="1",
        eapi="7",
        keywords="*",
        slot="0",
        depend="",
        rdepend="",
        inherit: Union[Iterable[str], str] = tuple(),
        **kwargs,
    ):
        self.category = category
        self.package = package
        self.version = version
        self.eapi = eapi
        self.keywords = keywords
        self.slot = slot
        self.depend = depend
        self.rdepend = rdepend
        self.inherit = (
            (inherit,) if isinstance(inherit, str) else tuple(inherit)
        )
        self.variables = kwargs

    @classmethod
    def from_cpv(cls, pkg_str: str):
        """Creates a Package from a CPV string."""
        cpv = package_info.parse(pkg_str)
        return cls(category=cpv.category, package=cpv.package, version=cpv.vr)

    @property
    def cpv(self) -> package_info.CPV:
        """Returns a CPV object constructed from this package's metadata.

        Deprecated, use package_info instead.
        """
        return package_info.SplitCPV(
            self.category + "/" + self.package + "-" + self.version
        )

    @property
    def package_info(self) -> package_info.PackageInfo:
        """Get a PackageInfo object constructed from this package's metadata."""
        return package_info.parse(
            f"{self.category}/{self.package}-{self.version}"
        )

    def format_eclass_line(self) -> str:
        """Get a string containing this package's eclass inheritance line."""
        if self.inherit and isinstance(self.inherit, str):
            return f"inherit {self.inherit}\n"
        elif self.inherit:
            return f'inherit {" ".join(self.inherit)}\n'
        else:
            return ""
