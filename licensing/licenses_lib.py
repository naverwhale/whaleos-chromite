# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Library for validating ebuild license information, and generating credits.

Documentation on this script is also available here:
  https://dev.chromium.org/chromium-os/licensing
"""

import codecs
import fnmatch
import html
import json
import logging
import os
from pathlib import Path
import re
from typing import List, Optional

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import sysroot_lib
from chromite.lib.parser import ebuild_license
from chromite.lib.parser import package_info
from chromite.utils import gs_urls_util


# See https://crbug.com/207004 for discussion.
PER_PKG_LICENSE_DIR = portage_util.VDB_PATH

STOCK_LICENSE_DIRS = [
    "src/third_party/portage-stable/licenses",
]

# The SDK does not have generated overlay info in it, so hardcode these
# fallbacks for them.
SDK_OVERLAY_DIRS = [
    "src/third_party/chromiumos-overlay",
    "src/private-overlays/chromeos-overlay",
]

COPYRIGHT_ATTRIBUTION_DIR = os.path.join(
    constants.SOURCE_ROOT,
    "src/third_party/chromiumos-overlay/licenses/copyright-attribution",
)

# Virtual packages don't need to have a license and often don't, so we skip them
# chromeos-base contains google platform packages that are covered by the
# general license at top of tree, so we skip those too.
SKIPPED_CATEGORIES = [
    "virtual",
]

# If you have an early package for which license terms have yet to be decided,
# use this. It will cause licensing for the package to be mostly ignored.
# Tainted builds will fail signing with official keys.
TAINTED = "TAINTED"

# HTML outputs will include this tag if tainted.
TAINTED_COMMENT_TAG = "<!-- tainted -->"

SKIPPED_LICENSES = [
    # Some of our packages contain binary blobs for which we have special
    # negotiated licenses, and no need to display anything publicly. Strongly
    # consider using Google-TOS instead, if possible.
    "Proprietary-Binary",
]

LICENSE_BASENAMES_REGEX = [
    r"^copyright$",
    r"^copyright[.]txt$",
    r"^copyright[.]regex$",  # llvm
    r"^copying.*$",
    r"^licen[cs]e.*$",
    r"^licensing.*$",  # libatomic_ops
    r"^ipa_font_license_agreement_v1[.]0[.]txt$",  # ja-ipafonts
    r"^MIT-LICENSE$",  # rake
    r"^PKG-INFO$",  # copyright assignment for
    # some python packages
    # (netifaces, unittest2)
]

# Patterns to never classify as a license file. Unlike LICENSE_BASENAMES_REGEX,
# the patterns here are applied to the full path relative to the work dir root.
# Exclusions found this way are logged. We also skip `.git`, but don't log it.
LICENSE_PATHS_EXCLUDE_REGEX = (
    # We never want a GPL license when looking for copyright attribution, so we
    # skip things like license.gpl. Only check the basename.
    r"[^/]*GPL[^/]*$",
    # Skip files that are likely source code or object files generated from
    # source code. E.g., license.py, license.o, etc.
    r"\.py$",
    r"\.o$",
    # Haskell source and object files.
    r"\.hs$",
    r"\.hi$",
    r"\.dyn_hi$",
    r"\.dyn_o$",
    # This folder contains json files listing every license known to Cabal.
    r"Cabal/license-list-data",
)

# Any license listed here found in the ebuild will make the code look for
# license files inside the package source code in order to get copyright
# attribution from them.
COPYRIGHT_ATTRIBUTION_LICENSES = {
    "BSD",  # requires distribution of copyright notice
    "BSD-2",  # so does BSD-2 https://opensource.org/licenses/BSD-2-Clause
    "BSD-2-with-patent",
    "BSD-3",  # and BSD-3? https://opensource.org/licenses/BSD-3-Clause
    "BSD-4",  # and 4?
    "BSD-with-attribution",
    "BSD-with-disclosure",
    "ISC",  # so does ISC https://opensource.org/licenses/ISC
    "MIT",
    "MIT-with-advertising",
    "Old-MIT",
}

# The following licenses are not invalid or to show as a less helpful stock
# license, but it's better to look in the source code for a more specific
# license if there is one, but not an error if no better one is found.
# Note that you don't want to set just anything here since any license here
# will be included once in stock form and a second time in custom form if
# found (there is no good way to know that a license we found on disk is the
# better version of the stock version, so we show both).
LOOK_IN_SOURCE_LICENSES = [
    "PSF-2",  # The custom license in python is more complete than the template.
    # As far as I know, we have no requirement to do copyright attribution for
    # these licenses, but the license included in the code has slightly better
    # information than the stock Gentoo one (including copyright attribution).
    "BZIP2",  # Single use license, do copyright attribution.
    "OFL",  # Almost single use license, do copyright attribution.
    "OFL-1.1",  # Almost single use license, do copyright attribution.
    "UoI-NCSA",  # Only used by NSCA, might as well show their custom copyright.
]

# These are licenses we don't want to allow anyone to use.  Globs allowed.
#
# Gentoo normally uses a naming convention of <name> or <name>-<ver>.  We don't
# block AGPL* in the pathological case that an unrelated license comes up with
# the same first few letters.  Not likely, but not impossible.  But we do block
# AGPL-* as it's much more likely we'll get a newer version using the same base
# name which we want to be future proof against.
BAD_LICENSE_PATTERNS = {
    # Google policy to avoid these licenses (and all versions of them).
    # https://opensource.org/licenses/AGPL-3.0
    "AGPL",
    "AGPL-*",
    # Catch all versions & variants of CC-BY-NC, CC-BY-NC-ND, and CC-BY-NC-SA.
    # https://creativecommons.org/licenses/by-nc/3.0/
    "CC-BY-NC*",
    # https://opensource.org/licenses/CPAL-1.0
    "CPAL",
    "CPAL-*",
    # https://opensource.org/licenses/EUPL-1.2
    "EUPL",
    "EUPL-*",
    # https://en.wikipedia.org/wiki/WTFPL  nocheck
    "WTFPL*",  # nocheck
    # These aren't actual licenses :).
    "as-is",
}

# List of overlays that must use 'metapackage' license for virtual packages.
# Throw error for those, print a warning for others.
OVERLAYS_METAPACKAGES_MUST_USE_VIRTUAL = [
    "chromiumos-overlay",
    "chromeos-overlay",
    "chromeos-partner-overlay",
]

# The full names of packages which we want to generate license information for
# even though they have an empty installation size.
SIZE_EXEMPT_PACKAGES = [
    "net-print/fuji-xerox-printing-license",
    "net-print/fujifilm-printing-license",
    "net-print/konica-minolta-printing-license",
    "net-print/nec-printing-license",
    "net-print/xerox-printing-license",
]

# Find the directory of this script.
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

# The template files we depend on for generating HTML.
TMPL = os.path.join(SCRIPT_DIR, "about_credits.tmpl")
ENTRY_TMPL = os.path.join(SCRIPT_DIR, "about_credits_entry.tmpl")
SHARED_LICENSE_TMPL = os.path.join(
    SCRIPT_DIR, "about_credits_shared_license_entry.tmpl"
)

# dir_set constants for _GetLicenseDirectories.
_CUSTOM_DIRS = "custom"
_STOCK_DIRS = "stock"
_BOTH_DIRS = "both"

# Banner shown when generating a placeholder credits.
_PLACEHOLDER_BANNER = """
<div style="border: dashed; margin: 1em; padding: 1em;">
<p style="font-weight: bold;">Placeholder Credits Page</p>
<p>
See <a href="https://dev.chromium.org/chromium-os/licensing/licensing-for-chromiumos-developers">Licensing for ChromiumOS Developers</a> and
<a href="https://dev.chromium.org/chromium-os/licensing/licensing-for-chromiumos-package-owners">Licensing for ChromiumOS Package Owners</a>
for more details on the credits system.
</p>
<p>
If you need to change styles, fonts, layout, etc of the
<a href="chrome://os-credits">chrome://os-credits</a> page, edit
<a href="https://chromium.googlesource.com/chromiumos/chromite/+/HEAD/licensing/about_credits.tmpl">chromite/licensing/about_credits.tmpl</a>.
The template is used to generate a device-dependent about_os_credits.html
when a CrOS image is built.
</p>
</div>
"""


def _convert_yaml_to_json(yaml_file: str, json_file: str) -> None:
    """Migrate old YAML format to JSON.

    We have a lot of existing binpkgs that used yaml, so keep this for a while.
    TODO(build): Make this fatal in Jan 2024.

    Args:
        yaml_file: Path to the old existing yaml file.
        json_file: Path to the json file to write.
    """
    # The yaml files are legacy, so we don't normally load the module, and
    # because it's not a common 3rd party install.
    import yaml  # pylint: disable=import-error

    class SaferLoader(yaml.SafeLoader):
        """Augment the yaml.SafeLoader with unicode and tuple types."""

        def construct_tuple(self, node):
            return tuple(self.construct_sequence(node))

        def construct_unicode(self, node):
            return node.value

    SaferLoader.add_constructor(
        "tag:yaml.org,2002:python/tuple", SaferLoader.construct_tuple
    )
    SaferLoader.add_constructor(
        "tag:yaml.org,2002:python/unicode", SaferLoader.construct_unicode
    )

    logging.debug("Migrating YAML (%s) to JSON (%s)", yaml_file, json_file)

    old_data = yaml.load(osutils.ReadFile(yaml_file), Loader=SaferLoader)
    data = {}
    for key, value in old_data:
        if isinstance(value, set):
            value = sorted(value)
        data[key] = value
    osutils.WriteFile(json_file, json.dumps(data), sudo=True)


# This is called directly by src/repohooks/pre-upload.py
def GetLicenseTypesFromEbuild(
    ebuild_contents, overlay_path, buildroot=constants.SOURCE_ROOT
):
    """Returns a list of license types from an ebuild.

    This function does not always return the correct list, but it is
    faster than using portageq for not having to access chroot. It is
    intended to be used for tasks such as presubmission checks.

    Args:
        ebuild_contents: contents of ebuild.
        overlay_path: path of the overlay containing the ebuild
        buildroot: base directory, usually constants.SOURCE_ROOT, useful for
            tests

    Returns:
        list of licenses read from ebuild.

    Raises:
        ValueError: ebuild errors.
    """
    ebuild_env_tmpl = """
has() { [[ " ${*:2} " == *" $1 "* ]]; }
inherit() {
  local overlay_list="%(overlay_list)s"
  local eclass overlay f
  for eclass; do
    has ${eclass} ${_INHERITED_} && continue
    _INHERITED_+=" ${eclass}"
    for overlay in %(overlay_list)s; do
      f="${overlay}/eclass/${eclass}.eclass"
      if [[ -e ${f} ]]; then
        source "${f}"
        break
      fi
     done
  done
}
%(ebuild)s"""

    repo_name = portage_util.GetOverlayName(overlay_path)
    overlays = portage_util.FindOverlays(
        constants.BOTH_OVERLAYS, repo_name, buildroot=buildroot
    )
    tmpl_env = {
        "ebuild": ebuild_contents,
        "overlay_list": " ".join(overlays),
    }

    with cros_build_lib.UnbufferedNamedTemporaryFile() as f:
        osutils.WriteFile(f.name, ebuild_env_tmpl % tmpl_env)
        env = osutils.SourceEnvironment(
            f.name, allowlist=["LICENSE"], ifs=" ", multiline=True
        )

    if not env.get("LICENSE"):
        raise ValueError("No LICENSE found in the ebuild.")
    if re.search(r"[,;]", env["LICENSE"]):
        raise ValueError(
            "LICENSE field in the ebuild should be whitespace-limited."
        )

    return env["LICENSE"].split()


class PackageLicenseError(Exception):
    """Thrown for failures while getting license information for a package.

    This will cause the processing to error in the end.
    """


class PackageCorrectnessError(Exception):
    """Thrown if a package has build info incompatible with the license.

    For example, thrown when a package with LICENSE=metapackage installs files.
    This will cause the processing to error in the end.
    """


class PackageInfo:
    """Package specific information, mostly about licenses."""

    def __init__(self, sysroot, fullnamerev):
        """Package info initializer.

        Args:
            sysroot: The board this package was built for.
            fullnamerev: package name of the form 'x11-base/X.Org-1.9.3-r23'

        Raises:
            ValueError if |fullnamerev| is not a valid package string.
        """

        self.sysroot = sysroot

        package = package_info.parse(fullnamerev)
        self.category = package.category
        self.name = package.package
        self.version = package.version
        self.revision = package.revision
        self.fullname = package.cp
        self.fullnamerev = package.cpvr

        if fullnamerev != self.fullnamerev:
            # Parsed package doesn't match original, invalid package passed.
            raise ValueError(
                "portage couldn't find %s, missing version number?"
                % fullnamerev
            )

        #
        # These fields hold license information used to generate the credits
        # page.
        #

        # This contains licenses names for this package.
        self.license_names = set()

        # Full Text of discovered license information.
        self.license_text_scanned = []

        self.homepages = []

        #
        # These fields show the results of processing.
        #

        # After reading basic package information, we can mark the package as
        # one to skip in licensing.
        self.skip = False

        # Intelligently populate initial skip information.
        self.LookForSkip()

        # Set to something by GetLicenses().
        self.tainted = None

        self.ebuild_path = None

    @property
    def license_dump_path(self):
        """e.g. /build/x86-alex/var/db/pkg/sys-apps/dtc-1.4.0/license.json.

        Only valid for packages that have already been emerged.
        """
        return os.path.join(
            self.sysroot, PER_PKG_LICENSE_DIR, self.fullnamerev, "license.json"
        )

    def _RunEbuildPhases(self, ebuild_path, phases):
        """Run a list of ebuild phases on an ebuild.

        Args:
            ebuild_path: exact path of the ebuild file.
            phases: list of phases like ['clean', 'fetch'] or ['unpack'].

        Returns:
            ebuild command output
        """
        ebuild_cmd = cros_build_lib.GetSysrootToolPath(self.sysroot, "ebuild")
        return cros_build_lib.run(
            [ebuild_cmd, ebuild_path] + phases, stdout=True, encoding="utf-8"
        )

    def _GetOverrideLicense(self):
        """Check COPYRIGHT_ATTRIBUTION_DIR for license w/ copyright attribution.

        For dev-util/bsdiff-4.3-r5, the code will look for
        dev-util/bsdiff-4.3-r5
        dev-util/bsdiff-4.3
        dev-util/bsdiff

        It is ok to have more than one bsdiff license file, and an empty file
        acts as a rubout (i.e. an empty dev-util/bsdiff-4.4 will shadow
        dev-util/bsdiff and tell the licensing code to look in the package
        source for a license instead of using dev-util/bsdiff as an override).

        Returns:
            False (no license found) or a multiline license string.
        """
        license_read = None
        # dev-util/bsdiff-4.3-r5 -> bsdiff-4.3-r5
        filename = os.path.basename(self.fullnamerev)
        license_path = os.path.join(
            COPYRIGHT_ATTRIBUTION_DIR, os.path.dirname(self.fullnamerev)
        )
        pv = package_info.parse(filename)
        for filename in (pv.pvr, pv.pv, pv.package):
            file_path = os.path.join(license_path, filename)
            logging.debug(
                "Looking for override copyright attribution license in %s",
                file_path,
            )
            if os.path.exists(file_path):
                # Turn
                # SRC_ROOT/CHROMIUMOS_OVERLAY_DIR/../dev-util/bsdiff
                # into
                # chromiumos-overlay/../dev-util/bsdiff
                short_dir_path = os.path.join(
                    *file_path.rsplit(os.path.sep, 5)[1:]
                )
                license_read = (
                    "Copyright Attribution License %s:\n\n" % short_dir_path
                )
                license_read += ReadUnknownEncodedFile(
                    file_path, "read copyright attribution license"
                )
                break

        return license_read

    def _ExtractLicenses(self, src_dir, need_copyright_attribution):
        """Scrounge for text licenses in the source of package we'll unpack.

        This is only called if we couldn't get usable licenses from the ebuild,
        or one of them is BSD/MIT like which forces us to look for a file with
        copyright attribution in the source code itself.

        First, we have a shortcut where we scan COPYRIGHT_ATTRIBUTION_DIR to see
        if we find a license for this package. If so, we use that.
        Typically, it'll be used if the unpacked source does not have the
        license that we're required to display for copyright attribution (in
        some cases it's plain absent, in other cases, it could be in a filename
        we don't look for).

        Otherwise, we scan the unpacked source code for what looks like license
        files as defined in LICENSE_BASENAMES_REGEX.

        Raises:
            AssertionError: on runtime errors
            PackageLicenseError: couldn't find copyright attribution file.
        """
        license_override = self._GetOverrideLicense()
        if license_override:
            self.license_text_scanned = [license_override]
            return

        if not src_dir:
            self.ebuild_path = self._FindEbuildPath()
            self._RunEbuildPhases(self.ebuild_path, ["clean", "fetch"])
            raw_output = self._RunEbuildPhases(self.ebuild_path, ["unpack"])
            output = raw_output.stdout.splitlines()
            # pylint: disable=line-too-long
            #
            # Output is spammy, it looks like this:
            #  * gc-7.2d.tar.gz RMD160 SHA1 SHA256 size ;-) ...                 [ ok ]
            #  * checking gc-7.2d.tar.gz ;-) ...                                [ ok ]
            #  * Running stacked hooks for pre_pkg_setup
            #  *    sysroot_build_bin_dir ...
            #  [ ok ]
            #  * Running stacked hooks for pre_src_unpack
            #  *    python_multilib_setup ...
            #  [ ok ]
            # >>> Unpacking source...
            # >>> Unpacking gc-7.2d.tar.gz to /build/x86-alex/tmp/po/[...]ps-7.2d/work
            # >>> Source unpacked in /build/x86-alex/tmp/portage/[...]ops-7.2d/work
            # So we only keep the last 2 lines, the others we don't care about.
            #
            # pylint: enable=line-too-long
            output = [
                line
                for line in output
                if line[0:3] == ">>>" and line != ">>> Unpacking source..."
            ]
            for line in output:
                logging.info(line)

            tmpdir = portage_util.PortageqEnvvar(
                "PORTAGE_TMPDIR", sysroot=self.sysroot
            )
            # tmpdir gets something like /build/daisy/tmp/
            src_dir = os.path.join(tmpdir, "portage", self.fullnamerev, "work")

            if not os.path.exists(src_dir):
                raise AssertionError(
                    "Unpack of %s didn't create %s. Version mismatch"
                    % (self.fullnamerev, src_dir)
                )

        # pylint: disable=line-too-long
        #
        # You may wonder how deep should we go?
        # In case of packages with sub-packages, it could be deep.
        # Let's just be safe and get everything we can find.
        # In the case of libatomic_ops, it's actually required to look deep
        # to find the MIT license:
        # dev-libs/libatomic_ops-7.2d/work/gc-7.2/libatomic_ops/doc/LICENSING.txt
        #
        # pylint: enable=line-too-long
        # Use "%P" to truncate results to look like this: swig-2.0.4/COPYRIGHT
        args = ["find", src_dir, "-type", "f", "-printf", "%P\\n"]
        result = cros_build_lib.run(args, stdout=True, encoding="utf-8")
        license_files = FilterLicenseFileCandidates(result.stdout)

        if not license_files:
            if need_copyright_attribution:
                google_bsd_msg = ""
                if need_copyright_attribution == {"BSD"}:
                    google_bsd_msg = """
If this source code was entirely authored by Google employees, you can instead
just change the ebuild settings like so:
  -LICENSE="BSD"
  +LICENSE="BSD-Google"\
"""
                logging.error(
                    """\
%s: unable to find usable license.
The ebuild says it uses at least %s which requires copyright attribution,
but there was no license file that this script could find in the package's
source distribution:
  %s

You will need to investigate that source directory to figure out which license
to assign.  Once you've found it, copy the entire license file to:
  %s
%s""",
                    self.fullnamerev,
                    need_copyright_attribution,
                    src_dir,
                    COPYRIGHT_ATTRIBUTION_DIR,
                    google_bsd_msg,
                )
                raise PackageLicenseError(
                    "Missing copyright attribution for "
                    f"{need_copyright_attribution}"
                )
            else:
                # We can get called for a license like as-is where it's
                # preferable to find a better one in the source, but not fatal
                # if we didn't.
                logging.info(
                    "Was not able to find a better license for %s "
                    "in %s to replace the more generic one from ebuild",
                    self.fullnamerev,
                    src_dir,
                )

        # Examples of multiple license matches:
        # dev-lang/swig-2.0.4-r1: swig-2.0.4/COPYRIGHT swig-2.0.4/LICENSE
        # dev-libs/glib-2.32.4-r1: glib-2.32.4/COPYING pkg-config-0.26/COPYING
        # dev-libs/libnl-3.2.14: libnl-doc-3.2.14/COPYING libnl-3.2.14/COPYING
        # dev-libs/libpcre-8.30-r2: pcre-8.30/LICENCE pcre-8.30/COPYING
        # dev-libs/libusb-0.1.12-r6: libusb-0.1.12/COPYING libusb-0.1.12/LICENSE
        # dev-libs/pyzy-0.1.0-r1: db/COPYING pyzy-0.1.0/COPYING
        # net-misc/strongswan-5.0.2-r4: strongswan-5.0.2/COPYING
        #                               strongswan-5.0.2/LICENSE
        # sys-process/procps-3.2.8_p11: debian/copyright procps-3.2.8/COPYING
        logging.info(
            "License(s) for %s: %s", self.fullnamerev, " ".join(license_files)
        )
        for license_file in sorted(license_files):
            # Joy and pink ponies. Some license_files are encoded as latin1
            # while others are utf-8 and of course you can't know but only
            # guess.
            license_path = os.path.join(src_dir, license_file)
            license_txt = ReadUnknownEncodedFile(license_path, "Adding License")

            self.license_text_scanned += [
                "Scanned Source License %s:\n\n%s" % (license_file, license_txt)
            ]

        # We used to clean up here, but there have been many instances where
        # looking at unpacked source to see where the licenses were, was useful
        # so let's disable this for now
        # self._RunEbuildPhases(['clean'])

    def LookForSkip(self):
        """Look for a reason to skip over this package.

        Sets self.skip to True if a reason was found.

        Returns:
            True if a reason was found.
        """
        if self.category in SKIPPED_CATEGORIES:
            logging.info(
                "%s in SKIPPED_CATEGORIES, skip package", self.fullname
            )
            self.skip = True

        # TODO(dgarrett): There are additional reasons that should be handled
        #   here.

        return self.skip

    def _FindEbuildPath(self):
        """Discover the path to a package's associated ebuild.

        This method is not valid during the emerge hook process.

        Returns:
            full path file name of the ebuild file for this package.

        Raises:
            AssertionError if it can't be discovered for some reason.
        """
        equery_cmd = cros_build_lib.GetSysrootToolPath(self.sysroot, "equery")
        args = [equery_cmd, "-q", "-C", "which", self.fullnamerev]
        try:
            path = cros_build_lib.run(
                args, print_cmd=True, encoding="utf-8", stdout=True
            ).stdout.strip()
        except cros_build_lib.RunCommandError:
            path = None

        # Path can be false because of an exception, or a command result.
        if not path:
            raise AssertionError(
                "_FindEbuildPath for %s failed.\n"
                "Is your tree clean? Try a rebuild?" % self.fullnamerev
            )

        logging.debug("%s -> %s", " ".join(args), path)

        if not os.access(path, os.F_OK):
            raise AssertionError("Can't access %s" % (path,))

        return path

    def GetLicenses(self, build_info_dir, src_dir):
        """Populate the license related fields.

        Fields populated:
            license_names, license_text_scanned, homepages, skip, tainted

        Some packages have static license mappings applied to them that get
        retrieved from the ebuild.

        For others, we figure out whether the package source should be scanned
        to add licenses found there.

        Args:
            build_info_dir: Path to the build_info for the ebuild. This can be
                from the working directory during the emerge hook, or in the
                portage pkg db.
            src_dir: Directory to the expanded source code for this package.
                If None, the source will be expanded, if needed (slow).

        Raises:
            AssertionError: on runtime errors
            PackageLicenseError: couldn't find license in ebuild and source.
        """
        # If the total size installed is zero, we installed no content to
        # license.
        if _BuildInfo(build_info_dir, "SIZE").strip() == "0":
            # Allow for license generation for the exempt empty packages.
            if self.fullname not in SIZE_EXEMPT_PACKAGES:
                logging.debug("Build directory is empty")
                self.skip = True
                return

        self.homepages = _BuildInfo(build_info_dir, "HOMEPAGE").split()
        licenses = ebuild_license.parse(_BuildInfo(build_info_dir, "LICENSE"))

        # The ebuild license field can look like:
        # LICENSE="GPL-3 LGPL-3 Apache-2.0" (this means AND, as in all 3)
        # for third_party/portage-stable/app-admin/rsyslog/rsyslog-5.8.11.ebuild
        # LICENSE="|| ( LGPL-2.1 MPL-1.1 )"
        # for third_party/portage-stable/x11-libs/cairo/cairo-1.8.8.ebuild
        #
        # In order to save time needlessly unpacking packages and looking or a
        # cleartext license (which is really a crapshoot), if we have a license
        # like BSD that requires looking for copyright attribution, but we can
        # chose another license like GPL, we do that.
        def license_picker(choices):
            for choice in choices:
                if choice not in COPYRIGHT_ATTRIBUTION_LICENSES:
                    logging.info(
                        "Picking license '%s' from %s", choice, choices
                    )
                    return choice
            return choices[0]

        ebuild_license_names = licenses.reduce(anyof_reduce=license_picker)

        # Is this tainted?
        self.tainted = TAINTED in ebuild_license_names
        if self.tainted:
            logging.warning("Package %s is tainted", self.fullnamerev)

        # If this ebuild only uses skipped licenses, skip it.
        if ebuild_license_names and all(
            l in SKIPPED_LICENSES for l in ebuild_license_names
        ):
            self.skip = True

        if self.skip:
            return

        logging.info(
            "Read licenses for %s: %s",
            self.fullnamerev,
            ",".join(ebuild_license_names),
        )

        if not self.skip and not ebuild_license_names:
            logging.error(
                "%s: no license found in ebuild. FIXME!", self.fullnamerev
            )
            # In a bind, you could comment this out. I'm making the output fail
            # to get your attention since this error really should be fixed, but
            # if you comment out the next line, the script will try to find a
            # license inside the source.
            raise PackageLicenseError()

        need_copyright_attribution = set()
        scan_source_for_licenses = False

        for license_name in ebuild_license_names:
            # Licenses like BSD or MIT can't be used as is because they do not
            # contain copyright self. They have to be replaced by copyright file
            # given in the source code.
            if license_name in COPYRIGHT_ATTRIBUTION_LICENSES:
                logging.info(
                    "%s: can't use %s, will scan source code for copyright",
                    self.fullnamerev,
                    license_name,
                )
                need_copyright_attribution.add(license_name)
                scan_source_for_licenses = True
            else:
                self.license_names.add(license_name)
                # We can't display just 2+ because it only contains text that
                # says to read v2 or v3.
                if license_name == "GPL-2+":
                    self.license_names.add("GPL-2")
                if license_name == "LGPL-2+":
                    self.license_names.add("LGPL-2")

            if license_name in LOOK_IN_SOURCE_LICENSES:
                logging.info(
                    "%s: Got %s, will try to find better license in source...",
                    self.fullnamerev,
                    license_name,
                )
                scan_source_for_licenses = True

        if self.license_names:
            logging.info(
                "%s: using stock|cust license(s) %s",
                self.fullnamerev,
                ",".join(self.license_names),
            )

        # If the license(s) could not be found, or one requires copyright
        # attribution, dig in the source code for license files:
        # For instance:
        # Read licenses from ebuild for net-dialup/ppp-2.4.5-r3: BSD,GPL-2
        # We need get the substitution file for BSD and add it to GPL.
        if scan_source_for_licenses:
            self._ExtractLicenses(src_dir, need_copyright_attribution)

        # This shouldn't run, but leaving as basic smoke check.
        if not self.license_names and not self.license_text_scanned:
            raise AssertionError(
                "Didn't find usable licenses for %s" % self.fullnamerev
            )

    def SaveLicenseDump(self, save_file):
        """Save PackageInfo contents for loading later.

        This is used to cache license results between the emerge hook phase and
        credits page generation.

        Args:
            save_file: File to save the state into.
        """
        logging.debug("Saving license to %s", save_file)
        dump = {}
        for key, value in list(self.__dict__.items()):
            if isinstance(value, set):
                value = sorted(value)
            dump[key] = value
        osutils.WriteFile(save_file, json.dumps(dump), makedirs=True)

    def AssertCorrectness(self, build_info_dir, ebuild_path):
        """AssertCorrectness runs various correctness checks on the package.

        Args:
            build_info_dir: Path to the build_info for the ebuild. This can be
                from the working directory during the emerge hook, or in the
                portage pkg db.
            ebuild_path: Path to the ebuild. Unknown and therefore None during
                the emerge hook.

        Raises:
            PackageCorrectnessError: if one of the checks fails.
        """
        self._AssertMetapackageNoContent(build_info_dir)
        if ebuild_path is not None:
            self._AssertVirtualIsMetapackage(build_info_dir, ebuild_path)

    def _AssertMetapackageNoContent(self, build_info_dir):
        """Ensures metapackages do not install files.

        Args:
            build_info_dir: Path to the build_info for the ebuild. This can be
                from the working directory during the emerge hook, or in the
                portage pkg db.

        Raises:
            PackageCorrectnessError: if metapackage installs files.
        """
        if _BuildInfo(build_info_dir, "LICENSE") == "metapackage":
            content = _BuildInfo(build_info_dir, "CONTENTS")
            if content:
                content_list = ", ".join(
                    x.split()[1] for x in content.splitlines()
                )
                raise PackageCorrectnessError(
                    "Metapackage %s installs files: %s."
                    % (self.fullnamerev, content_list)
                )

    def _AssertVirtualIsMetapackage(self, build_info_dir, ebuild_path):
        """Ensures that virtual pkgs are metapackages.

        Args:
            ebuild_path: Path to the ebuild.
            build_info_dir: Path to the build_info for the ebuild. This can be
                from the working directory during the emerge hook, or in the
                portage pkg db.

        Raises:
            PackageCorrectnessError: if virtual pkg does not use metapackage
                license.
        """
        category = ebuild_path.split("/")[-3]
        overlay = ebuild_path.split("/")[-4]
        license_name = _BuildInfo(build_info_dir, "LICENSE")
        if category == "virtual" and license_name != "metapackage":
            err_msg = (
                f"Virtual package {ebuild_path} must use LICENSE="
                f'"metapackage". Got: {self.license_names}.'
            )
            if overlay in OVERLAYS_METAPACKAGES_MUST_USE_VIRTUAL:
                raise PackageCorrectnessError(err_msg)
            else:
                logging.warning(err_msg)


def _GetLicenseDirectories(
    board: Optional[str] = None,
    sysroot: Optional[str] = None,
    dir_set: str = _BOTH_DIRS,
    buildroot: Path = constants.SOURCE_ROOT,
) -> List[str]:
    """Get the "licenses" directories for all matching overlays.

    With a |board| argument, allows searching without a compiled sysroot.

    Args:
        board: Which board to use to search a hierarchy. Does not require the
            board be setup or compiled yet.
        sysroot: A setup board sysroot to query.
        dir_set: Whether to fetch stock, custom, or both sets of directories.
            See the _(STOCK|CUSTOM|BOTH)_DIRS constants.
        buildroot: The root chromiumos path.

    Returns:
        list - all matching "licenses" directories
    """
    stock = [os.path.join(buildroot, d) for d in STOCK_LICENSE_DIRS]
    if board is not None:
        custom_paths = portage_util.FindOverlays(
            constants.BOTH_OVERLAYS, board, buildroot
        )
    elif sysroot is not None and sysroot != "/":
        portdir_overlay = (
            sysroot_lib.Sysroot(sysroot).GetStandardField(
                sysroot_lib.STANDARD_FIELD_PORTDIR_OVERLAY
            )
            or ""
        )
        custom_paths = portdir_overlay.split() if portdir_overlay else []
    else:
        custom_paths = [
            os.path.join(constants.SOURCE_ROOT, x) for x in SDK_OVERLAY_DIRS
        ]
    custom = [os.path.join(d, "licenses") for d in custom_paths]

    if dir_set == _STOCK_DIRS:
        return stock
    elif dir_set == _CUSTOM_DIRS:
        return custom
    else:
        return stock + custom


def _CheckForKnownBadLicenses(cpf, licenses):
    """Make sure all the |licenses| are ones we allow.

    We have a bunch of licenses we don't want people to use, but some packages
    were using them by the time we noticed.  Still allow those existing ones,
    but prevent new users from showing up.
    """
    bad_licenses = set()
    for pattern in BAD_LICENSE_PATTERNS:
        bad_licenses |= {x for x in licenses if fnmatch.fnmatch(x, pattern)}

    # We allow ghostscript for public builds to use AGPL but nothing else.
    if cpf.startswith("app-text/ghostscript-gpl"):
        bad_licenses -= {"AGPL-3"}

    if bad_licenses:
        raise PackageLicenseError(f"Licenses {bad_licenses} are not allowed")

    # TODO(crbug.com/401332): Remove this entirely.
    # We allow a few packages for now so new packages will stop showing up.
    if "Proprietary-Binary" in licenses:
        # Note: DO NOT ADD ANY MORE PACKAGES HERE.
        LEGACY_PKGS = (
            "chromeos-base/infineon-firmware",
            "sys-boot/coreboot-private-files-",
            "sys-boot/nhlt-blobs",
            "sys-boot/mma-blobs",
        )
        if not any(cpf.startswith(x) for x in LEGACY_PKGS):
            raise PackageLicenseError(
                f"{cpf}: Proprietary-Binary is not a valid license."
            )

    # TODO(b/187789754): Remove this entirely.
    # We allow a few packages for now so new packages will stop showing up.
    if "Google-TOS" in licenses:
        # Note: DO NOT ADD ANY MORE PACKAGES HERE.
        LEGACY_PKGS = {
            "chromeos-base/chromeos-board-default-apps-atlas",
            "chromeos-base/chromeos-board-default-apps-cave",
            "chromeos-base/chromeos-board-default-apps-chell",
            "chromeos-base/chromeos-board-default-apps-nocturne",
            "chromeos-base/chromeos-board-default-apps-setzer",
            "chromeos-base/chromeos-board-default-apps-snappy",
            "chromeos-base/chromeos-board-default-apps-soraka",
            "chromeos-base/chromeos-board-default-apps-terra",
            "chromeos-base/chromeos-bsp-trogdor-private",
            "chromeos-base/chromeos-chrome",
            "chromeos-base/chromeos-default-apps",
            "chromeos-base/chromeos-firmware-anx7688",
            "chromeos-base/fibocom-firmware",
            "chromeos-base/google-sans-fonts",
            "chromeos-base/houdini",
            "chromeos-base/houdini-pi",
            "chromeos-base/houdini-qt",
            "chromeos-base/intel-hdcp",
            "chromeos-base/monotype-fonts",
            "chromeos-base/qc7180-modem-firmware",
            "chromeos-base/sc7280-modem-firmware",
            "chromeos-base/modem-logger-sc",
            "chromeos-base/modem-fw-dlc",
            "dev-embedded/meta-embedded-toolkit",
            "media-libs/a630-fw",
            "media-libs/apl-hotword-support",
            "media-libs/arc-img-ddk",
            "media-libs/arc-mali-drivers",
            "media-libs/arc-mali-drivers-bifrost",
            "media-libs/cros-camera-hal-qti",
            "media-libs/cros-camera-hal-qti-bin",
            "media-libs/glk-hotword-support",
            "media-libs/go2001-fw",
            "media-libs/img-ddk",
            "media-libs/img-ddk-bin",
            "media-libs/kbl-hotword-support",
            "media-libs/kbl-rt5514-hotword-support",
            "media-libs/mali-drivers",
            "media-libs/mali-drivers-bifrost",
            "media-libs/mali-drivers-bifrost-bin",
            "media-libs/mali-drivers-bin",
            "media-libs/qti-7c-camera-bins",
            "media-libs/rk3399-hotword-support",
            "media-libs/skl-hotword-support",
            "net-print/brother_mlaser",
            "sys-apps/loonix-hydrogen",
            "sys-boot/chromeos-firmware-ps8751",
            "sys-boot/chromeos-vendor-strings-wilco",
            "sys-boot/coreboot-private-files-chipset-picasso",
            "sys-boot/coreboot-private-files-chipset-stnyridge",
            "sys-boot/coreboot-private-files-drallion",
            "sys-boot/coreboot-private-files-grunt",
            "sys-boot/coreboot-private-files-hatch",
            "sys-boot/amd-picasso-fsp",
            "sys-boot/intel-cflfsp",
            "sys-boot/intel-glkfsp",
            "sys-boot/intel-iclfsp",
            "sys-boot/mma-blobs",
            "sys-boot/nhlt-blobs",
            "sys-boot/rk3399-hdcp-fw",
            "sys-boot/qclib",
            "sys-boot/qtiseclib",
            "sys-firmware/analogix-anx3429-firmware",
            "sys-firmware/displaylink-firmware",
            "sys-firmware/falcon-firmware",
            "sys-firmware/huddly-firmware",
            "sys-firmware/iq-firmware",
            "sys-firmware/sis-firmware",
        }
        if not any(cpf.startswith(x) for x in LEGACY_PKGS):
            raise PackageLicenseError(
                f"{cpf}: Google-TOS is not a valid license."
            )


class Licensing:
    """Do the actual work of extracting licensing info and outputting html."""

    def __init__(
        self,
        sysroot,
        package_fullnames,
        gen_licenses,
        placeholder: bool = False,
    ):
        self.sysroot = sysroot
        # List of stock and custom licenses referenced in ebuilds. Used to
        # print a report. Dict value says which packages use that license.
        self.licenses = {}

        # Licenses are supposed to be generated at package build time and be
        # ready for us, but in case they're not, they can be generated.
        self.gen_licenses = gen_licenses

        # Generate placeholder values instead of inspecting real data.
        self.placeholder = placeholder

        self.entry_template = None

        # We need to have a dict for the list of packages objects, index by
        # package fullnamerev, so that when we scan our licenses at the end, and
        # find out some shared licenses are only used by one package, we can
        # access that package object by name, and add the license directly in
        # that object.
        self.packages = {}
        self._package_fullnames = package_fullnames

        # Set by ProcessPackageLicenses().
        self.tainted_pkgs = []

    @property
    def sorted_licenses(self):
        return sorted(self.licenses, key=lambda x: x.lower())

    def _LoadLicenseDump(self, pkg):
        save_file = pkg.license_dump_path
        logging.debug("Getting license from %s for %s", save_file, pkg.name)
        with open(save_file, "rb") as fp:
            dump = json.load(fp)
        for key, value in dump.items():
            if isinstance(pkg.__dict__[key], set):
                value = set(value)
            pkg.__dict__[key] = value

    def LicensedPackages(self, license_name):
        """Return list of packages using a given license."""
        return self.licenses[license_name]

    def LoadPackageInfo(self):
        """Populate basic package info for all packages from their ebuild."""
        for package_name in self._package_fullnames:
            pkg = PackageInfo(self.sysroot, package_name)
            self.packages[package_name] = pkg

    def ProcessPackageLicenses(self):
        """Iterate through all packages provided and gather their licenses.

        GetLicenses will scrape licenses from the code and/or gather stock
        license names. We gather the list of stock and custom ones for later
        processing.

        Do not call this after adding virtual packages with AddExtraPkg.
        """
        # TODO(b/236161656): Fix.
        # pylint: disable-next=consider-using-dict-items
        for package_name in self.packages:
            pkg = self.packages[package_name]

            if pkg.skip:
                logging.debug("Package %s is in skip list", package_name)
                continue

            if self.placeholder:
                pkg.license_names = ["Placeholder-License"]
                pkg.license_text_scanned = ["Custom placeholder license text"]
                pkg.homepages = ["https://dev.chromium.org/"]
                continue

            # Do inplace/ondemand migration.
            if not os.path.exists(pkg.license_dump_path):
                yaml_file = pkg.license_dump_path[0:-4] + "yaml"
                if os.path.exists(yaml_file):
                    _convert_yaml_to_json(yaml_file, pkg.license_dump_path)

            # Other skipped packages get dumped with incomplete info and the
            # skip flag
            if not os.path.exists(pkg.license_dump_path):
                if not self.gen_licenses:
                    logging.error(
                        "Run licenses.py with --generate-licenses to try to "
                        "generate the missing licenses."
                    )
                    raise PackageLicenseError(
                        f"{pkg.fullnamerev}: license is missing"
                    )

                logging.warning(
                    ">>> License for %s is missing, creating now <<<",
                    package_name,
                )
                build_info_path = os.path.join(
                    self.sysroot, PER_PKG_LICENSE_DIR, pkg.fullnamerev
                )
                pkg.GetLicenses(build_info_path, None)
                pkg.AssertCorrectness(build_info_path, self.ebuild_path)

                # We dump packages where licensing failed too.
                pkg.SaveLicenseDump(pkg.license_dump_path)

            # Load the pre-cached version, if the in-memory version is
            # incomplete.
            if not pkg.license_names:
                logging.debug("loading dump for %s", pkg.fullnamerev)
                self._LoadLicenseDump(pkg)

            # Store all tainted packages to print at the top of generated
            # license. If any package is tainted, the whole thing is tainted.
            if pkg.tainted:
                self.tainted_pkgs.append(package_name)

            _CheckForKnownBadLicenses(pkg.fullnamerev, pkg.license_names)

    def AddExtraPkg(self, fullnamerev, homepages, license_names, license_texts):
        """Allow adding pre-created virtual packages.

        GetLicenses will not work on them, so add them after having run
        ProcessPackages.

        Args:
            fullnamerev: package name of the form x11-base/X.Org-1.9.3-r23
            homepages: list of url strings.
            license_names: list of license name strings.
            license_texts: custom license text to use, mostly for attribution.
        """
        pkg = PackageInfo(self.sysroot, fullnamerev)
        pkg.homepages = homepages
        pkg.license_names = license_names
        pkg.license_text_scanned = license_texts
        self.packages[fullnamerev] = pkg

        _CheckForKnownBadLicenses(fullnamerev, pkg.license_names)

    # Called directly by src/repohooks/pre-upload.py
    @staticmethod
    def FindLicenseType(
        license_name,
        board=None,
        sysroot=None,
        overlay_path=None,
        buildroot=constants.SOURCE_ROOT,
        placeholder: bool = False,
    ):
        """Says if a license is stock Gentoo, custom, tainted, or doesn't exist.

        Will check the old, static locations by default, but supplying either
        the overlay directory or sysroot allows searching in the overlay
        hierarchy. Ignores the overlay_path if sysroot is provided.

        Args:
            license_name: The license name
            board: Which board to use to search a hierarchy. Does not require
                the board be setup or compiled yet.
            sysroot: A setup board sysroot to query.
            overlay_path: Which overlay directory to use as the search base
            buildroot: source root
            placeholder: Whether to generate a stub placeholder page.

        Returns:
            str - license type

        Raises:
            AssertionError when the license couldn't be found
        """
        if license_name == TAINTED:
            return TAINTED

        if placeholder:
            return "Placeholder Stock"

        # Check the stock licenses first since those may appear in the generated
        # list of overlay directories for a board
        stock = _GetLicenseDirectories(dir_set=_STOCK_DIRS, buildroot=buildroot)
        for directory in stock:
            path = os.path.join(directory, license_name)
            if os.path.exists(path):
                return "Gentoo Package Stock"

        # Not stock, find and check relevant custom directories
        if board is None and overlay_path is not None:
            board = portage_util.GetOverlayName(overlay_path)

        # Check the custom licenses
        custom = _GetLicenseDirectories(
            board=board,
            sysroot=sysroot,
            dir_set=_CUSTOM_DIRS,
            buildroot=buildroot,
        )
        for directory in custom:
            path = os.path.join(directory, license_name)
            if os.path.exists(path):
                return "Custom"

        if license_name in SKIPPED_LICENSES:
            return "Custom"

        raise AssertionError(
            """
license %s could not be found in %s
If the license in the ebuild is correct,
a) a stock license should be added to portage-stable/licenses :
running `cros_portage_upgrade` inside of the chroot should clone this repo
to /tmp/portage/:
https://chromium.googlesource.com/chromiumos/overlays/portage/+/gentoo
find the new licenses under licenses, and add them to portage-stable/licenses

b) if it's a non gentoo package with a custom license, you can copy that license
to third_party/chromiumos-overlay/licenses/

Try re-running the script with -p cat/package-ver --generate
after fixing the license."""
            % (license_name, "\n".join(set(stock + custom)))
        )

    @staticmethod
    def ReadSharedLicense(
        license_name,
        board=None,
        sysroot=None,
        buildroot=constants.SOURCE_ROOT,
        placeholder: bool = False,
    ):
        """Read and return stock or cust license file specified in an ebuild."""
        if placeholder:
            return "Placeholder license text"

        directories = _GetLicenseDirectories(
            board=board,
            sysroot=sysroot,
            dir_set=_BOTH_DIRS,
            buildroot=buildroot,
        )
        license_path = None
        for directory in directories:
            path = os.path.join(directory, license_name)
            if os.path.exists(path):
                license_path = path
                break

        if license_path:
            return ReadUnknownEncodedFile(license_path, "read license")
        else:
            raise AssertionError(
                "license %s could not be found in %s"
                % (license_name, "\n".join(directories))
            )

    @staticmethod
    def EvaluateTemplate(template, env):
        """Expand |template| with vars like {{foo}} using |env| expansions."""
        # TODO switch to stock python templates.
        for key, val in env.items():
            template = template.replace("{{%s}}" % key, val)
        return template

    def _GeneratePackageLicenseHTML(self, pkg, license_text):
        """Concatenate all licenses related to a pkg in HTML format.

        This means a combination of ebuild shared licenses and licenses read
        from the pkg source tree, if any.

        Args:
            pkg: PackageInfo object
            license_text: the license in plain text.

        Returns:
            The license for a file->package in HTML format.

        Raises:
            AssertionError: on runtime errors
        """
        license_pointers = []
        # sln: shared license name.
        for sln in pkg.license_names:
            # Says whether it's a stock gentoo or custom license.
            try:
                license_type = self.FindLicenseType(
                    sln, sysroot=self.sysroot, placeholder=self.placeholder
                )
            except Exception as e:
                logging.error(
                    "Failed to find the type of %s license, used by %s "
                    "package. If this license is not used anymore, it may be "
                    "still cached as a binpkg—run emerge on the package to "
                    "rebuild. See more info at "
                    "https://dev.chromium.org/chromium-os/licensing",
                    sln,
                    pkg.fullnamerev,
                )
                cros_build_lib.Die(e)
            license_pointers.append(
                "<li><a href='#%s'>%s License %s</a></li>"
                % (sln, license_type, sln)
            )

        # This should get caught earlier, but one extra check.
        if not license_text + license_pointers:
            raise AssertionError(
                "Ended up with no license_text for %s" % pkg.fullnamerev
            )

        env = {
            "comments": TAINTED_COMMENT_TAG if pkg.tainted else "",
            "name": pkg.name,
            "namerev": "%s-%s" % (pkg.name, pkg.version),
            "url": html.escape(pkg.homepages[0]) if pkg.homepages else "",
            "licenses_txt": html.escape("\n".join(license_text)) or "",
            "licenses_ptr": "\n".join(license_pointers) or "",
        }
        return self.EvaluateTemplate(self.entry_template, env)

    def _GeneratePackageLicenseText(self, pkg):
        """Concatenate all licenses related to a pkg.

        This means a combination of ebuild shared licenses and licenses read
        from the pkg source tree, if any.

        Args:
            pkg: PackageInfo object
        """
        license_text = []
        for license_text_scanned in pkg.license_text_scanned:
            license_text.append(license_text_scanned)
            license_text.append("%s\n" % ("-=" * 40))

        return license_text

    def GenerateLicenseText(self):
        """Generate the license text for all packages."""
        license_txts = {}
        # Keep track of which licenses are used by which packages.
        for pkg in self.packages.values():
            if pkg.tainted:
                license_txts[pkg] = TAINTED
                continue
            if pkg.skip:
                continue
            for sln in pkg.license_names:
                self.licenses.setdefault(sln, []).append(pkg.fullnamerev)

        # Find licenses only used once, and roll them in the package that uses
        # them. We use list() because licenses is modified in the loop, so we
        # can't use an iterator.
        for sln in list(self.licenses):
            if len(self.licenses[sln]) == 1:
                pkg_fullnamerev = self.licenses[sln][0]
                logging.info(
                    "Collapsing shared license %s into single use license "
                    "(only used by %s)",
                    sln,
                    pkg_fullnamerev,
                )
                license_type = self.FindLicenseType(
                    sln, sysroot=self.sysroot, placeholder=self.placeholder
                )
                license_txt = self.ReadSharedLicense(
                    sln, sysroot=self.sysroot, placeholder=self.placeholder
                )
                single_license = "%s License %s:\n\n%s" % (
                    license_type,
                    sln,
                    license_txt,
                )
                pkg = self.packages[pkg_fullnamerev]
                pkg.license_text_scanned.append(single_license)
                pkg.license_names.remove(sln)
                del self.licenses[sln]

        for pkg in self.packages.values():
            if pkg.skip:
                logging.debug("Skipping empty package %s", pkg.fullnamerev)
                continue
            license_txts[pkg] = self._GeneratePackageLicenseText(pkg)

        return license_txts

    def GenerateHTMLLicenseOutput(
        self,
        output_file,
        output_template=TMPL,
        entry_template=ENTRY_TMPL,
        license_template=SHARED_LICENSE_TMPL,
        os_version: Optional[str] = None,
        milestone_version: Optional[str] = None,
        compress_output=False,
    ):
        """Generate the combined html license file.

        Args:
            output_file: resulting HTML license output.
            output_template: template for the entire HTML file.
            entry_template: template for per package entries.
            license_template: template for shared license entries.
            os_version: OS version.
            milestone_version: Milestone version.
            compress_output: whether to compress based on suffix of output_file.
        """
        self.entry_template = ReadUnknownEncodedFile(entry_template)
        license_txts = self.GenerateLicenseText()
        sorted_license_txt = []
        for pkg in sorted(
            license_txts.keys(),
            key=lambda x: (x.name.lower(), x.version, x.revision),
        ):
            sorted_license_txt += [
                self._GeneratePackageLicenseHTML(pkg, license_txts[pkg])
            ]

        # W/A add crashpad license
        env = {
            "comments": "",
            "name": 'crashpad',
            "namerev": 'crashpad',
            "url": 'https://chromium.googlesource.com/crashpad/crashpad',
            "licenses_txt": html.escape(
                self.ReadSharedLicense('Apache-2.0', sysroot=self.sysroot)),
            "licenses_ptr": "",
        }
        sorted_license_txt += [self.EvaluateTemplate(self.entry_template, env)]

        # Now generate the bottom of the page that will contain all the shared
        # licenses and a list of who is pointing to them.
        license_template = ReadUnknownEncodedFile(license_template)

        licenses_txt = []
        for license_name in self.sorted_licenses:
            env = {
                "license_name": license_name,
                "license": html.escape(
                    self.ReadSharedLicense(
                        license_name,
                        sysroot=self.sysroot,
                        placeholder=self.placeholder,
                    )
                ),
                "license_type": self.FindLicenseType(
                    license_name,
                    sysroot=self.sysroot,
                    placeholder=self.placeholder,
                ),
                "license_packages": " ".join(
                    self.LicensedPackages(license_name)
                ),
            }
            licenses_txt += [self.EvaluateTemplate(license_template, env)]

        if self.placeholder:
            if not os_version:
                os_version = "1000.10.0"
            if not milestone_version:
                milestone_version = "100"
        reciprocal_txt = ""
        if os_version and milestone_version:
            env = {
                "chromeos-manifest-link": gs_urls_util.GsUrlToHttp(
                    "gs://chromeos-manifest-versions/buildspecs/"
                    f"{milestone_version}/{os_version}.xml"
                ),
                "chromiumos-manifest-link": gs_urls_util.GsUrlToHttp(
                    "gs://chromiumos-manifest-versions/buildspecs/"
                    f"{milestone_version}/{os_version}.xml"
                ),
                "os-version": os_version,
                "milestone-version": milestone_version,
            }
            reciprocal_txt = self.EvaluateTemplate(
                osutils.ReadFile(
                    os.path.join(SCRIPT_DIR, "about_credits_reciprocal.tmpl")
                ),
                env,
            )

        file_template = ReadUnknownEncodedFile(output_template)
        tainted_warning = ""
        if self.tainted_pkgs:
            tained_pkg_lis = "\n".join(
                f"  <li>{x}</li>" for x in self.tainted_pkgs
            )
            tainted_warning = (
                TAINTED_COMMENT_TAG
                + "\n"
                + "<h1>Image is TAINTED due to the following "
                + 'packages:</h1>\n<ul style="font-size:large">\n'
                + tained_pkg_lis
                + "\n</ul>\n"
            )
            for tainted_pkg in self.tainted_pkgs:
                logging.warning("Package %s is tainted", tainted_pkg)
            logging.warning(
                "Image is tainted. See licensing docs to fix this: "
                "https://dev.chromium.org/chromium-os/licensing"
            )
        env = {
            "tainted_warning_if_any": tainted_warning,
            "entries": "\n".join(sorted_license_txt),
            "licenses": "\n".join(licenses_txt),
            "placeholder": _PLACEHOLDER_BANNER if self.placeholder else "",
            "reciprocal-license-statement": reciprocal_txt,
        }
        contents = self.EvaluateTemplate(file_template, env).encode("utf-8")
        if not compress_output:
            # Just write it.
            osutils.WriteFile(output_file, contents, mode="wb")
        else:
            # Write to a temp file, then compress it to the final destination,
            # using the file extension specified to determine compression type.
            with cros_build_lib.UnbufferedNamedTemporaryFile() as f:
                osutils.WriteFile(f.name, contents, mode="wb")
                cros_build_lib.CompressFile(f.name, output_file)


def ListInstalledPackages(sysroot, all_packages=False):
    """Return a list of all packages installed for a particular board."""

    # If all_packages is set to True, all packages visible in the build
    # chroot are used to generate the licensing file. This is not what you want
    # for a release license file, but it's a way to run licensing checks against
    # all packages.
    # If it's set to False, it will only generate a licensing file that contains
    # packages used for a release build (as determined by the dependencies for
    # virtual/target-os).

    if all_packages:
        # The following returns all packages that were part of the build tree
        # (many get built or used during the build, but do not get shipped).
        # Note that it also contains packages that are in the build as
        # defined by cros build-packages but not part of the image we ship.
        equery_cmd = cros_build_lib.GetSysrootToolPath(sysroot, "equery")
        args = [equery_cmd, "list", "*"]
        packages = cros_build_lib.run(
            args, encoding="utf-8", stdout=True
        ).stdout.splitlines()
    else:
        # The following returns all packages that were part of the build tree
        # (many get built or used during the build, but do not get shipped).
        # Note that it also contains packages that are in the build as
        # defined by cros build-packages but not part of the image we ship.
        emerge_cmd = cros_build_lib.GetSysrootToolPath(sysroot, "emerge")
        args = [
            emerge_cmd,
            "--with-bdeps=y",
            "--usepkgonly",
            "--emptytree",
            "--pretend",
            "--color=n",
            "virtual/target-os",
        ]
        emerge = cros_build_lib.run(
            args, encoding="utf-8", stdout=True
        ).stdout.splitlines()
        # Another option which we've decided not to use, is bdeps=n.  This
        # outputs just the packages we ship, but not packages that were used to
        # build them, including a package like flex which generates a .a that is
        # included and shipped in ChromeOS.
        # We've decided to credit build packages, even if we're not legally
        # required to (it's always nice to do), and that way we get corner case
        # packages like flex. This is why we use bdep=y and not bdep=n.

        packages = []
        bad_packages = []
        # [binary   R    ] x11-libs/libva-1.1.1 to /build/x86-alex/
        pkg_rgx = re.compile(r"\[[^]]+R[^]]+\] (.+) to /build/.*")
        # pylint: disable=line-too-long
        # If we match something else without the 'R' like
        # [binary     U  ] chromeos-base/some-package-13.0.0.133-r1 [12.0.0.77-r1]
        # this is bad, and we should die on this.
        # pylint: enable=line-too-long
        pkg_rgx2 = re.compile(r"(\[[^]]+\] .+) to /build/.*")
        for line in emerge:
            match = pkg_rgx.search(line)
            match2 = pkg_rgx2.search(line)
            if match:
                packages.append(match.group(1))
            elif match2:
                bad_packages.append(match2.group(1))

        if bad_packages:
            raise AssertionError(
                "Package incorrectly installed, try reinstalling",
                "\n%s" % "\n".join(bad_packages),
            )

    return packages


def FilterLicenseFileCandidates(stdout: str) -> List[str]:
    """Returns the subset of files in `stdout` that look like licenses."""
    license_files: List[str] = []
    basename_include_pattern = re.compile(
        "|".join(f"({x})" for x in LICENSE_BASENAMES_REGEX), re.IGNORECASE
    )
    path_exclude_pattern = re.compile(
        "|".join(f"({x})" for x in LICENSE_PATHS_EXCLUDE_REGEX), re.IGNORECASE
    )
    for path in stdout.splitlines():
        # When we scan a source tree managed by git, this can contain license
        # files that are not part of the source. Exclude those.
        # (e.g. .git/refs/heads/licensing)
        if ".git/" in path:
            continue
        basename = os.path.basename(path)
        if basename_include_pattern.search(basename):
            if path_exclude_pattern.search(path):
                logging.info("Ignoring %s (matches exclude regex).", path)
            else:
                license_files.append(path)
    return license_files


def ReadUnknownEncodedFile(file_path, logging_text=None):
    """Read a file of unknown encoding (UTF-8 or latin) by trying in sequence.

    Args:
        file_path: what to read.
        logging_text: what to display for logging depending on file read.

    Returns:
        File content, possibly converted from latin1 to UTF-8.
    """
    try:
        with codecs.open(file_path, encoding="utf-8") as c:
            file_txt = c.read()
            if logging_text:
                logging.info("%s %s (UTF-8)", logging_text, file_path)
    except UnicodeDecodeError:
        with codecs.open(file_path, encoding="latin1") as c:
            file_txt = c.read()
            if logging_text:
                logging.info("%s %s (latin1)", logging_text, file_path)

    # Remove characters that are not XML 1.0 legal.
    # XML 1.0 acceptable character range:
    # Char ::= #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | \
    #          [#x10000-#x10FFFF]

    # Strip out common/OK values silently.
    silent_chars_re = re.compile("[\x0c]")
    file_txt = silent_chars_re.sub("", file_txt)

    illegal_chars_re = re.compile(
        "[\x00-\x08\x0b\x0c\x0e-\x1F\uD800-\uDFFF\uFFFE\uFFFF]"
    )

    if illegal_chars_re.findall(file_txt):
        logging.warning("Found illegal XML characters, stripping them out.")
        file_txt = illegal_chars_re.sub("", file_txt)

    return file_txt


def _BuildInfo(build_info_path, filename):
    """Fetch contents of a file from portage build_info directory.

    Portage maintains a build_info directory that exists both during the process
    of emerging an ebuild, and (in a different location) after the ebuild has
    been emerged.

    Various useful data files exist there like:
        'CATEGORY', 'PF', 'SIZE', 'HOMEPAGE', 'LICENSE'

    Args:
        build_info_path: Path to the build_info directory to read from.
        filename: Name of the file to read.

    Returns:
        Contents of the file as a string, or "".
    """
    filename = os.path.join(build_info_path, filename)

    # Buildinfo properties we read are in US-ASCII, not Unicode.
    try:
        bi = osutils.ReadFile(filename).rstrip()
    # Some properties like HOMEPAGE may be absent.
    except IOError:
        bi = ""
    return bi


def HookPackageProcess(pkg_build_path: str, sysroot: Optional[str] = "/"):
    """Different entry point to populate a packageinfo.

    This is called instead of LoadPackageInfo when called by a package build.

    Args:
        pkg_build_path: unpacked being built by emerge.
        sysroot: The sysroot we're building for.
    """
    build_info_dir = os.path.join(pkg_build_path, "build-info")
    if not os.path.isdir(build_info_dir):
        raise ValueError(
            '%s is not a valid build path (missing "build-info/")'
            % (pkg_build_path,)
        )

    fullnamerev = "%s/%s" % (
        _BuildInfo(build_info_dir, "CATEGORY"),
        _BuildInfo(build_info_dir, "PF"),
    )
    logging.debug(
        "Computed package name %s from %s", fullnamerev, pkg_build_path
    )

    pkg = PackageInfo(None, fullnamerev)

    src_dir = os.path.join(pkg_build_path, "work")
    pkg.GetLicenses(build_info_dir, src_dir)

    pkg.AssertCorrectness(build_info_dir, None)
    # Make sure the licenses are valid at build time even if we don't load them.
    _CheckForKnownBadLicenses(fullnamerev, pkg.license_names)
    for license_name in pkg.license_names:
        Licensing.FindLicenseType(license_name, sysroot=sysroot)

    pkg.SaveLicenseDump(os.path.join(build_info_dir, "license.json"))
