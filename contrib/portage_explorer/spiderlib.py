# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common dataclasses used between spiders.

The dataclasses should be similar to those from portage_explorer.proto. Use
the actual objects to represent the relationships (except for profile
inheritance where ids should be used) instead of ids for ease of access and
organization.
"""

import dataclasses
import enum
from pathlib import Path
from typing import List, Optional

from chromite.lib.parser import package_info


@dataclasses.dataclass
class Eclass:
    """Eclass."""

    path: Path
    name: str


class UseState(enum.Enum):
    """Disabled or enabled state for use flags."""

    DISABLED = False
    ENABLED = True


@dataclasses.dataclass
class EbuildUse:
    """USE flags used for Ebuilds."""

    name: str
    default_enabled: UseState


@dataclasses.dataclass
class TestEbuild:
    """Contain only data that is found by sourcing the ebuild for testing."""

    eapi: int = 0
    description: str = ""
    homepage: str = ""
    license_: str = ""
    slot: str = ""
    src_uri: str = ""
    restrict: str = ""
    depend: str = ""
    rdepend: str = ""
    bdepend: str = ""
    pdepend: str = ""
    iuse: str = ""
    inherit: str = ""


@dataclasses.dataclass
class Ebuild:
    """An Ebuild."""

    path: Path
    package: package_info.PackageInfo
    eapi: int = 0
    description: str = ""
    homepage: str = ""
    license_: str = ""
    slot: str = ""
    src_uri: str = ""
    restrict: str = ""
    depend: str = ""
    rdepend: str = ""
    bdepend: str = ""
    pdepend: str = ""
    use_flags: List[EbuildUse] = dataclasses.field(default_factory=list)
    eclass_inherits: List[str] = dataclasses.field(default_factory=list)

    def add_use_flag(self, flag):
        """Parse the use flag for its UseState and add to use_flags."""
        default_enabled = UseState(flag.startswith("+"))
        # Check Gentoo docs, '-' is "pretty much useless"
        # https://devmanual.gentoo.org/general-concepts/use-flags/index.html#iuse-defaults
        flag = flag.strip("+-")
        self.use_flags.append(EbuildUse(flag, default_enabled))


@dataclasses.dataclass
class ProfileUse:
    """USE flags used for profiles."""

    name: str
    enabled: UseState


@dataclasses.dataclass
class Profile:
    """A profile."""

    id_: str
    path: Path
    name: str
    parent_profiles: List[str] = dataclasses.field(default_factory=list)
    use_flags: List[ProfileUse] = dataclasses.field(default_factory=list)

    def set_enabled(self, flag: str, enabled: bool = True):
        """Set the enabled state for a specified use flag in this profile."""
        for use_flag in self.use_flags:
            if use_flag.name == flag:
                use_flag.enabled = UseState(enabled)


@dataclasses.dataclass
class BuildTarget:
    """A build target."""

    name: str
    profile: Optional[Profile] = None


@dataclasses.dataclass
class Overlay:
    """An overlay."""

    path: Path
    name: str
    profiles: List[Profile] = dataclasses.field(default_factory=list)
    ebuilds: List[Ebuild] = dataclasses.field(default_factory=list)
    eclasses: List[Eclass] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class SpiderOutput:
    """Output from all the spiders.

    The output from all the spiders will be used to fill in the output proto of
    the RunSpiders endpoint for the PortageExplorerService.

    Attributes:
        build_targets: List of build targets. Default value is an empty list.
        overlays: List of overlays. Default value is an empty list.
    """

    build_targets: List[BuildTarget] = dataclasses.field(default_factory=list)
    overlays: List[Overlay] = dataclasses.field(default_factory=list)
