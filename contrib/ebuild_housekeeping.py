# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Various ebuild house keeping tasks."""

import enum
import functools
import logging
from pathlib import Path
import re
from typing import Iterable, List, Optional

from chromite.lib import commandline
from chromite.lib import git
from chromite.lib.parser import package_info


def logging_dryrun(*args, **kwargs):
    """Helper method for logging dryrun statements in a consistent format."""
    logging.info("(dryrun) " + args[0], *args[1:], **kwargs)


def get_var(lines: List[str], var: str) -> Optional[str]:
    """Lookup the value of |var| and return it.

    This only supports one-liners, and no arrays.  It's extremely basic.
    """
    found_lines = [x for x in lines if x.startswith(f"{var}=")]
    if not found_lines:
        return None
    assert len(found_lines) == 1, found_lines
    line = found_lines[0]
    return line.split("=")[1].strip('"')


class Ebuild:
    """Container representing a single ebuild."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.cpv = package_info.parse(path)

    @functools.cached_property
    def name(self) -> str:
        return self.path.name

    @functools.cached_property
    def is_symlink(self) -> bool:
        return self.path.is_symlink()

    @functools.cached_property
    def is_workon(self) -> bool:
        return self.name.endswith("-9999.ebuild")

    @functools.cached_property
    def content(self) -> str:
        return self.path.read_text(encoding="utf-8")

    @functools.cached_property
    def lines(self) -> List[str]:
        return self.content.strip().splitlines()

    def write_lines(self, lines: List[str], dryrun: bool = False) -> None:
        if dryrun:
            logging_dryrun("%s: rewrote %s", self.cpv, self.path.name)
        else:
            self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @functools.cached_property
    def eapi(self) -> str:
        return get_var(self.lines, "EAPI")

    @functools.cached_property
    def rev0_path(self) -> Path:
        return self.path.with_name(self.cpv.with_rev0().ebuild)

    @functools.cached_property
    def rev_next_path(self) -> Path:
        return self.path.with_name(self.cpv.revision_bump().ebuild)


class Package:
    """Container representing a package in an overlay.

    Can operate on multiple ebuilds for a single package.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    @functools.cached_property
    def category(self) -> str:
        return self.path.parent.name

    @functools.cached_property
    def pn(self) -> str:
        return self.path.name

    @functools.cached_property
    def cp(self) -> str:
        return f"{self.category}/{self.pn}"

    def iterebuilds(self, symlinks: bool = False):
        yield from (
            Ebuild(x)
            for x in self.path.glob("*.ebuild")
            if symlinks or not x.is_symlink()
        )

    @functools.cached_property
    def is_metapackage(self) -> bool:
        return self.path.parent.name == "virtual"

    @functools.cached_property
    def is_workon(self) -> bool:
        return any(x.is_workon for x in self.iterebuilds())

    @functools.cached_property
    def workon_ebuild(self) -> Ebuild:
        return Ebuild(self.path / f"{self.pn}-9999.ebuild")


def git_mv(cwd: Path, src: Path, dst: Path, dryrun: bool = False) -> None:
    git.RunGit(cwd, ["mv", src, dst], dryrun=dryrun)


def git_add(pkg: Package, dryrun: bool = False) -> None:
    if not dryrun:
        git.AddPath(pkg.path)


def ebuild_bump(
    pkg: Package,
    ebuilds: List[Ebuild],
    dryrun: bool = False,
    force: bool = False,  # pylint: disable=unused-argument
) -> None:
    """Revbump the package."""
    if len(ebuilds) == 1:
        ebuild = ebuilds[0]
        rev_path = ebuild.rev_next_path
        if dryrun:
            logging_dryrun(
                "%s: Symlinking %s -> %s",
                pkg.cp,
                rev_path.name,
                ebuild.name,
            )
        else:
            rev_path.symlink_to(ebuild.name)
    else:
        ebuild = ebuilds[1]
        git_mv(pkg.path, ebuild.name, ebuild.rev_next_path.name, dryrun=dryrun)


def normalize(
    pkg: Package,
    dryrun: bool = False,
    force: bool = False,  # pylint: disable=unused-argument
) -> bool:
    """Normalize how the revbump is handled.

    We want the base ebuild to never have a -r# component, and then use a
    symlink to it to force the revbumping.
    """
    if pkg.is_workon:
        return False

    files = list(pkg.iterebuilds(symlinks=True))
    if len(files) not in (1, 2):
        logging.error(
            "%s: too many ebuilds found: %s", pkg.cp, [x.cpv for x in files]
        )
        return False
    if files[0].is_symlink:
        files = [files[1], files[0]]
    src_ebuild = files[0]

    cpv = src_ebuild.cpv
    if cpv.revision:
        logging.notice("%s: normalize -r ebuilds", cpv)
        if len(files) != 1:
            logging.error(
                "%s: too many ebuilds found: %s", cpv, [x.cpv for x in files]
            )
            return False
        rev0_path = src_ebuild.rev0_path
        if dryrun:
            logging_dryrun(
                "%s: Renaming %s -> %s", cpv, src_ebuild.name, rev0_path.name
            )
            logging_dryrun(
                "%s: Symlinking %s -> %s", cpv, src_ebuild.name, rev0_path.name
            )
        else:
            git_mv(pkg.path, src_ebuild.name, rev0_path)
            src_ebuild.path.symlink_to(rev0_path.name)
            git_add(pkg)
        return True

    return False


def eapi_7_safe(pkg: Package, ebuild: Ebuild, force: bool = False) -> bool:
    """Try and guess whether it's safe to upgrade to EAPI=7."""
    log_prefix = "EAPI=7 checks"
    # If it's already upgraded, then there's no need to upgrade again.
    if ebuild.eapi == "7":
        return False

    lines = ebuild.lines
    issues = []

    BAD_CONTENT = (
        ("STRIP_MASK=", "7; use `dostrip -x`"),
        (
            "prune_libtool_files",
            "use `find \"${ED}\" -name '*.la' -delete || die`",
        ),
        ("ltprune", "use `find \"${ED}\" -name '*.la' -delete || die`"),
        ("epatch", "use `eapply` or `PATCHES=(...)`"),
        ("epatch_user", "use `eapply_user`"),
        ("versionator", "use `ver_xxx` helpers"),
        ("eapi7-ver", "don't need this eclass at all"),
        ("dohtml", "use `dodoc`"),
        ("einstall", 'use `emake DESTDIR="${ED}" install`'),
    )
    for entry, replacement in BAD_CONTENT:
        if any(entry in x for x in lines):
            issues += [f"{entry} banned in EAPI=7; {replacement}"]

    if any(
        x.startswith("src_")
        and not x.startswith("src_install()")
        and not x.startswith("src_unpack()")
        for x in lines
    ):
        if ebuild.eapi == "6":
            logging.warning(
                "%s: %s: assuming EAPI=6 -> EAPI=7 is easy; please review!",
                pkg.cp,
                log_prefix,
            )
        else:
            issues += ["src_xxx funcs require manual review"]

    for issue in issues:
        if not force:
            logging.error("%s: %s: skipping: %s", pkg.cp, log_prefix, issue)
        else:
            logging.warning(
                "%s: %s: %s; please review!", pkg.cp, log_prefix, issue
            )

    ret = force or not bool(issues)
    if not ret:
        logging.error(
            "%s: %s: use --force to upgrade anyways", pkg.cp, log_prefix
        )
    return ret


def general_bump_eapi(
    pkg: Package, dryrun: bool = False, force: bool = False
) -> bool:
    """Update EAPI for normal (non-virtual & non-cros-workon) packages."""
    log_prefix = "general EAPI update"

    if pkg.is_workon or pkg.category == "virtual":
        return False

    files = list(pkg.iterebuilds(symlinks=True))
    if len(files) not in (1, 2):
        logging.error(
            "%s: %s: too many ebuilds found: %s",
            pkg.cp,
            log_prefix,
            [x.cpv for x in files],
        )
        return False
    if files[0].is_symlink:
        files = [files[1], files[0]]
    ebuild = files[0]

    if not eapi_7_safe(pkg, ebuild, force=force):
        return False

    logging.notice("%s: %s", pkg.cp, log_prefix)
    lines = ['EAPI="7"' if x.startswith("EAPI=") else x for x in ebuild.lines]
    ebuild.write_lines(lines, dryrun=dryrun)

    ebuild_bump(pkg, files, dryrun=dryrun)
    git_add(pkg, dryrun=dryrun)

    return True


def cros_workon_bump_eapi(
    pkg: Package, dryrun: bool = False, force: bool = False
) -> bool:
    """Update EAPI for cros-workon packages."""
    log_prefix = "cros-workon EAPI update"

    if not pkg.is_workon:
        return False
    ebuild = pkg.workon_ebuild

    if not eapi_7_safe(pkg, ebuild, force=force):
        return False

    logging.notice("%s: %s", pkg.cp, log_prefix)
    lines = ['EAPI="7"' if x.startswith("EAPI=") else x for x in ebuild.lines]
    ebuild.write_lines(lines, dryrun=dryrun)

    git_add(pkg, dryrun=dryrun)

    return True


def virtual_bump_eapi(
    pkg: Package,
    dryrun: bool = False,
    force: bool = False,  # pylint: disable=unused-argument
) -> bool:
    """Update EAPI for virtual packages."""
    if pkg.category != "virtual":
        return False

    files = list(pkg.iterebuilds(symlinks=True))
    if len(files) not in (1, 2):
        logging.error(
            "%s: too many ebuilds found: %s", pkg.cp, [x.cpv for x in files]
        )
        return False
    if files[0].is_symlink:
        files = [files[1], files[0]]
    src_ebuild = files[0]
    if src_ebuild.eapi == "7":
        return False

    cpv = src_ebuild.cpv
    logging.notice("%s: virtual EAPI update", cpv)

    lines = src_ebuild.lines
    lines = ['EAPI="7"' if x.startswith("EAPI=") else x for x in lines]
    src_ebuild.write_lines(lines, dryrun=dryrun)

    ebuild_bump(pkg, files, dryrun=dryrun)
    git_add(pkg, dryrun=dryrun)

    return True


def set_license(
    pkg: Package,
    dryrun: bool = False,
    force: bool = False,  # pylint: disable=unused-argument
) -> bool:
    """Set the LICENSE to the right value.

    This handles metapackages only atm.
    """
    # If the package isn't a metapackage (e.g. virtual), nothing to do!
    if not pkg.is_metapackage:
        return False

    files = list(pkg.iterebuilds(symlinks=True))
    if len(files) not in (1, 2):
        logging.error(
            "%s: too many ebuilds found: %s", pkg.cp, [x.cpv for x in files]
        )
        return False
    if files[0].is_symlink:
        files = [files[1], files[0]]
    src_ebuild = files[0]
    lines = src_ebuild.lines

    lic = get_var(lines, "LICENSE")
    if lic == "metapackage":
        # If the package is already using metapackage, nothing to do!
        return False

    cpv = src_ebuild.cpv
    logging.notice(
        '%s: changing LICENSE="%s" to LICENSE="metapackage"', cpv, lic or ""
    )

    # If the LICENSE= line already exists, replace it.
    # If it doesn't, try to insert it just before the SLOT= line.=
    lines = [
        'LICENSE="metapackage"' if x.startswith("LICENSE=") else x
        for x in lines
    ]
    try:
        i = lines.index('LICENSE="metapackage"')
    except ValueError:
        for i, line in enumerate(lines):
            if line.startswith("SLOT="):
                break
        else:
            logging.error("%s: can't find place to insert LICENSE=", cpv)
            return False
        lines.insert(i, 'LICENSE="metapackage"')
    src_ebuild.write_lines(lines, dryrun=dryrun)

    ebuild_bump(pkg, files, dryrun=dryrun)
    git_add(pkg, dryrun=dryrun)

    return True


@enum.unique
class RunMode(enum.Enum):
    """Which cleanup task to run."""

    NORMALIZE = enum.auto()
    VIRTUAL_EAPI = enum.auto()
    CROS_WORKON_EAPI = enum.auto()
    GENERAL_EAPI = enum.auto()
    META_LICENSE = enum.auto()


ACTION_MAP = {
    RunMode.NORMALIZE: (normalize, "normalize ebuild symlinks"),
    RunMode.VIRTUAL_EAPI: (virtual_bump_eapi, "update to EAPI=7"),
    RunMode.META_LICENSE: (set_license, "set LICENSE=metapackage"),
    RunMode.CROS_WORKON_EAPI: (cros_workon_bump_eapi, "update to EAPI=7"),
    RunMode.GENERAL_EAPI: (general_bump_eapi, "update to EAPI=7"),
}


def enumerate_packages(overlay: Path) -> Iterable[Package]:
    """Return all the unique packages in this overlay."""
    yield from (
        Package(x)
        for x in sorted({x.parent for x in overlay.glob("*/*/*.ebuild")})
    )


def process_overlay(opts, mode: RunMode, overlay: Path) -> None:
    """Process |overlay|."""
    logging.debug("%s: checking", overlay.name)

    for pkg in enumerate_packages(overlay):
        logging.debug("%s: checking", pkg.cp)

        if opts.grep and not any(
            opts.grep.search(x.content) for x in pkg.iterebuilds()
        ):
            logging.debug("%s: ignoring due to --grep not matching", pkg.cp)
            continue

        func, msg = ACTION_MAP[mode]
        if func(pkg, dryrun=opts.dryrun, force=opts.force):
            if not opts.dryrun:
                git.Commit(
                    overlay,
                    (
                        f"{pkg.pn}: {msg}\n\n"
                        f"BUG={opts.bug_tag}\nTEST={opts.test_tag}"
                    ),
                )


def get_parser():
    """Get CLI parser."""
    actions = [
        f"{str(x.name).lower()}: {ACTION_MAP[x][0].__doc__.strip()}"
        for x in RunMode
    ]
    parser = commandline.ArgumentParser(
        description=__doc__, epilog="\n\n".join(actions), dryrun=True
    )
    parser.add_argument(
        "--force", action="store_true", help="Ignore safety checks"
    )
    parser.add_argument(
        "--grep", help="Only process ebuilds matching a regular expression"
    )
    parser.add_argument("--bug-tag", default="None", help="Which bug to use")
    parser.add_argument(
        "--test-tag", default="CQ passes", help="What testing is used"
    )
    parser.add_argument(
        "mode",
        action="enum",
        enum=RunMode,
        help="Which housekeeping task to run",
    )
    parser.add_argument("overlays", nargs="+", help="Which overlays to cleanup")
    return parser


def main(argv):
    """The main entry point for scripts."""
    parser = get_parser()
    opts = parser.parse_args(argv)
    opts.overlays = [Path(x).resolve() for x in opts.overlays]
    if opts.grep:
        opts.grep = re.compile(opts.grep)
    opts.Freeze()

    for overlay in opts.overlays:
        process_overlay(opts, opts.mode, overlay)
