# Copyright 2014 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the license_lib module."""

import json
import os
from unittest import mock

from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.licensing import licenses_lib


# pylint: disable=protected-access


class LicenseLibTest(cros_test_lib.TempDirTestCase):
    """Limited tests for license_lib."""

    LICENSE_PUBLIC = "Gentoo Package Stock"
    LICENSE_CUSTOM = "Custom"

    def setUp(self):
        """Sets up the filesystem for the tests."""

        # Licenses for testing:
        #   key - Name of the license.
        #     contents - The contents of the license file itself.
        #     dir - Location of the file containing the license text on the FS.
        #     board - The board argument to use when testing the license.
        #     type - The license type (gentoo stock or custom).
        #     [skip_test] - Skip the tests for that license.

        self.licenses = {
            "TPL": {
                "contents": "Third Party License",
                "dir": "src/third_party/portage-stable/licenses/TPL",
                "board": "foo",
                "type": self.LICENSE_PUBLIC,
            },
            "PUB": {
                "contents": "Public License",
                "dir": "src/third_party/chromiumos-overlay/licenses/PUB",
                "board": "foo",
                "type": self.LICENSE_CUSTOM,
            },
            "CCL": {
                "contents": "ChromeOS Custom License",
                "dir": "src/private-overlays/chromeos-overlay/licenses/CCL",
                "board": "chromeos",
                "type": self.LICENSE_CUSTOM,
            },
            "CPL": {
                "contents": "ChromeOS Partner License",
                "dir": (
                    "src/private-overlays/chromeos-partner-overlay/licenses/CPL"
                ),
                "board": "chromeos-partner",
                "type": self.LICENSE_CUSTOM,
            },
            "FTL": {
                "contents": "Fake Test License",
                "dir": "src/overlays/overlay-foo/licenses/FTL",
                "board": "foo",
                "type": self.LICENSE_CUSTOM,
            },
            "OOR": {
                "contents": "Out Of Reach",
                "dir": "src/overlays/overlay-bar/licenses/OOR",
                "skip_test": True,
            },
            licenses_lib.TAINTED: {
                "contents": licenses_lib.TAINTED,
                "dir": "src/overlays/overlay-foo/licenses/TAINTED",
                "board": "foo",
                "type": licenses_lib.TAINTED,
            },
        }

        # Overlays for testing.
        #   dir: Overlay base directory.
        #   repo-name: The repo-name setting for the overlay.
        #   masters: The masters list for the overlay.

        overlays = [
            {
                "dir": "src/overlays/overlay-foo",
                "repo-name": "foo",
                "masters": ["chromiumos", "portage-stable"],
            },
            {
                "dir": "src/overlays/overlay-bar",
                "repo-name": "bar",
                "masters": [],
            },
            {
                "dir": "src/private-overlays/overlay-foo-private",
                "repo-name": "foo-private",
                "masters": ["foo", "chromeos-partner"],
            },
            {
                "dir": "src/private-overlays/chromeos-overlay",
                "repo-name": "chromeos",
                "masters": ["chromiumos", "portage-stable"],
            },
            {
                "dir": "src/private-overlays/chromeos-partner-overlay",
                "repo-name": "chromeos-partner",
                "masters": ["chromeos"],
            },
            {
                "dir": "src/third_party/chromiumos-overlay",
                "repo-name": "chromiumos",
                "masters": ["portage-stable"],
            },
            {
                "dir": "src/third_party/portage-stable",
                "repo-name": "portage-stable",
                "masters": [],
            },
        ]

        # Template for overlay/metadata/layout.conf.
        layout_template = """
repo-name = %(repo_name)s
masters = %(masters)s
"""

        # Convenience variables for ebuild dictionary building.
        foo_eb_dir = os.path.join(
            self.tempdir, "src/overlays/overlay-foo/category"
        )
        foo_ec_dir = os.path.join(
            self.tempdir, "src/overlays/overlay-foo/eclass"
        )
        _priv_rel_path = "src/private-overlays/overlay-foo-private/category"
        foopriv_eb_dir = os.path.join(self.tempdir, _priv_rel_path)

        # Ebuilds for testing.
        #   key: Package name of the ebuild.
        #     dir: .ebuild file location.
        #     board: Overlay that contains the ebuild.
        #     license: The license the ebuild uses.

        self.ebuilds = {
            "ftl-pkg": {
                "dir": os.path.join(foo_eb_dir, "ftl-pkg/ftl-pkg-1.ebuild"),
                "board": "foo",
                "license": "FTL",
            },
            "ttl-pkg": {
                "dir": os.path.join(foo_eb_dir, "ttl-pkg/ttl-pkg-1.ebuild"),
                "board": "foo",
                "license": licenses_lib.TAINTED,
            },
            "pub-pkg": {
                "dir": os.path.join(foo_eb_dir, "pub-pkg/pub-pkg-1.ebuild"),
                "board": "foo",
                "license": "PUB",
            },
            "pub-cls": {
                "dir": os.path.join(foo_ec_dir, "pub-cls.eclass"),
                "board": "foo",
                "license": "PUB",
            },
            "tpl-pkg": {
                "dir": os.path.join(foo_eb_dir, "tpl-pkg/tpl-pkg-1.ebuild"),
                "board": "foo",
                "license": "TPL",
            },
            "ccl-pkg": {
                "dir": os.path.join(foopriv_eb_dir, "ccl-pkg/ccl-pkg-1.ebuild"),
                "board": "foo-private",
                "license": "CCL",
            },
        }

        self.build_infos = {
            "metapackage-with-files": {
                "files": {
                    "CATEGORY": "virtual",
                    "CONTENTS": """dir /foo
sym /sym -> / 1611355469
obj /file bd1b4ffa168f50b0d45571dae51eefc7 1611355468""",
                    "LICENSE": "metapackage",
                    "PF": "metapackage-with-files-1",
                },
                "expected_exception": licenses_lib.PackageCorrectnessError,
            },
            "metapackage-valid": {
                "files": {
                    "CATEGORY": "virtual",
                    "CONTENTS": "",
                    "LICENSE": "metapackage",
                    "PF": "metapackage-valid-1",
                },
                "expected_exception": None,
            },
        }

        # .ebuild content template.
        ebuild_template = 'LICENSE="%(license)s"'

        D = cros_test_lib.Directory
        # Much of the file layout has to be an exact match due to hard coding of
        # a few repos. Prepare for lisp mode.
        file_layout = (
            D(
                "src",
                (
                    D(
                        "overlays",
                        (
                            D(
                                "overlay-foo",
                                (
                                    D(
                                        "category",
                                        (
                                            D("ftl-pkg", ("ftl-pkg-1.ebuild",)),
                                            D("pub-pkg", ("pub-pkg-1.ebuild",)),
                                            D("tpl-pkg", ("tpl-pkg-1.ebuild",)),
                                            D("ttl-pkg", ("ttl-pkg-1.ebuild",)),
                                        ),
                                    ),
                                    D("eclass", ("pub-cls.eclass",)),
                                    D("licenses", ("FTL",)),
                                    D("metadata", ("layout.conf",)),
                                ),
                            ),
                            D(
                                "overlay-bar",
                                (
                                    D("licenses", ("OOR",)),
                                    D("metadata", ("layout.conf",)),
                                ),
                            ),
                        ),
                    ),
                    D(
                        "private-overlays",
                        (
                            D(
                                "overlay-foo-private",
                                (
                                    D(
                                        "category",
                                        (D("ccl-pkg", ("ccl-pkg-1.ebuild",)),),
                                    ),
                                    D("metadata", ("layout.conf",)),
                                ),
                            ),
                            D(
                                "chromeos-overlay",
                                (
                                    D("licenses", ("CCL",)),
                                    D("metadata", ("layout.conf",)),
                                ),
                            ),
                            D(
                                "chromeos-partner-overlay",
                                (
                                    D("licenses", ("CPL",)),
                                    D("metadata", ("layout.conf",)),
                                ),
                            ),
                        ),
                    ),
                    D(
                        "third_party",
                        (
                            D(
                                "chromiumos-overlay",
                                (
                                    D("licenses", ("PUB",)),
                                    D("metadata", ("layout.conf",)),
                                ),
                            ),
                            D(
                                "portage-stable",
                                (
                                    D("licenses", ("TPL",)),
                                    D("metadata", ("layout.conf",)),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            D(
                "build_infos",
                (
                    D(
                        "metapackage-with-files",
                        (
                            D(
                                "build-info",
                                ("CATEGORY", "CONTENTS", "LICENSE", "PF"),
                            ),
                        ),
                    ),
                    D(
                        "metapackage-valid",
                        (
                            D(
                                "build-info",
                                ("CATEGORY", "CONTENTS", "LICENSE", "PF"),
                            ),
                        ),
                    ),
                ),
            ),
        )
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, file_layout)

        # Write out the files declared above.
        for lic in self.licenses.values():
            osutils.WriteFile(
                os.path.join(self.tempdir, lic["dir"]), lic["contents"]
            )

        for overlay in overlays:
            content = layout_template % {
                "masters": " ".join(overlay["masters"]),
                "repo_name": overlay["repo-name"],
            }
            file_loc = os.path.join(
                self.tempdir, overlay["dir"], "metadata", "layout.conf"
            )
            osutils.WriteFile(file_loc, content)

        for _, ebuild in self.ebuilds.items():
            content = ebuild_template % {"license": ebuild["license"]}
            ebuild["content"] = content
            osutils.WriteFile(
                os.path.join(self.tempdir, ebuild["dir"]), content
            )

        for pkg, build_info in self.build_infos.items():
            for filename, content in build_info["files"].items():
                osutils.WriteFile(
                    os.path.join(
                        self.tempdir, "build_infos", pkg, "build-info", filename
                    ),
                    content,
                )

    def testGetLicenseTypesFromEbuild(self):
        """Tests the fetched license from ebuilds are correct."""
        ebuild_content = self.ebuilds["ftl-pkg"]["content"]
        overlay_path = os.sep.join(
            self.ebuilds["ftl-pkg"]["dir"].split(os.sep)[:-3]
        )

        result = licenses_lib.GetLicenseTypesFromEbuild(
            ebuild_content, overlay_path, self.tempdir
        )
        expected = ["FTL"]
        self.assertEqual(expected, sorted(result))

    def testGetLicenseTypeFromEbuildTainted(self):
        """Tests the fetched tainted license from ebuilds is correct."""
        ebuild_content = self.ebuilds["ttl-pkg"]["content"]
        overlay_path = os.sep.join(
            self.ebuilds["ttl-pkg"]["dir"].split(os.sep)[:-3]
        )

        result = licenses_lib.GetLicenseTypesFromEbuild(
            ebuild_content, overlay_path, self.tempdir
        )
        expected = [licenses_lib.TAINTED]
        self.assertEqual(expected, sorted(result))

    def testFindLicenseType(self):
        """Tests the type for licenses are correctly identified.

        e.g. gentoo vs custom.
        """
        # Doesn't exist anywhere.
        self.assertRaises(
            AssertionError,
            licenses_lib.Licensing.FindLicenseType,
            "DoesNotExist",
            buildroot=self.tempdir,
        )
        # Not in overlay hierarchy.
        self.assertRaises(
            AssertionError,
            licenses_lib.Licensing.FindLicenseType,
            "OOR",
            board="foo",
            buildroot=self.tempdir,
        )
        # Not included in the default search paths.
        self.assertRaises(
            AssertionError,
            licenses_lib.Licensing.FindLicenseType,
            "FTL",
            buildroot=self.tempdir,
        )

        # Checking each license type is the expected.
        for name, lic in self.licenses.items():
            if lic.get("skip_test", False):
                continue

            result = licenses_lib.Licensing.FindLicenseType(
                name, board=lic["board"], buildroot=self.tempdir
            )
            self.assertEqual(lic["type"], result)

    def testReadSharedLicense(self):
        """Tests the license text is correctly fetched."""
        # Doesn't exist.
        self.assertRaises(
            AssertionError,
            licenses_lib.Licensing.ReadSharedLicense,
            "DoesNotExist",
            buildroot=self.tempdir,
        )
        # Not in overlay hierarchy.
        self.assertRaises(
            AssertionError,
            licenses_lib.Licensing.ReadSharedLicense,
            "OOR",
            board="foo",
            buildroot=self.tempdir,
        )
        # Not included in the default search paths.
        self.assertRaises(
            AssertionError,
            licenses_lib.Licensing.ReadSharedLicense,
            "FTL",
            buildroot=self.tempdir,
        )

        for name, lic in self.licenses.items():
            if lic.get("skip_test", False):
                continue

            result = licenses_lib.Licensing.ReadSharedLicense(
                name, board=lic["board"], buildroot=self.tempdir
            )
            self.assertEqual(lic["contents"], result)

    def testFilterLicenseFileCandidates(self) -> None:
        """Ensure license patterns are applied properly to `find` output."""
        EXPECTED_LICENSES = """\
path/to/copyright
a/copyright.txt
llvm/copyright.regex
copying_rules
license.txt
licence.md
license.rst
licenses-3.6.json
LICENSE
LICENSE.gz
LICENSES_FILE
LICENSE-LLVM.TXT
libatomic_ops/licensing.rtf
ja-ipafonts/ipa_font_license_agreement_v1.0.txt
rake/MIT-LICENSE
PKG-INFO
a/GPL_DIR/license.txt"""
        SAMPLE_FIND_OUTPUT = f"""\
{EXPECTED_LICENSES}
ExclusionsStartHere
.git/refs/heads/licensing
license.gpl
License.o
license.py
License.dyn_hi
License.dyn_o
LicenseExceptionId.hi
LicenseExceptionId.hs
Licenses.hs
libraries/Cabal/license-list-data/licenses-3.6.json
"""

        self.assertEqual(
            licenses_lib.FilterLicenseFileCandidates(SAMPLE_FIND_OUTPUT),
            EXPECTED_LICENSES.splitlines(),
        )

    def testReadUnknownEncodedFile(self):
        """Validate the fix for crbug.com/654894."""
        bad_license = os.path.join(self.tempdir, "license.rtf")
        osutils.WriteFile(bad_license, "Foo\x00Bar")
        result = licenses_lib.ReadUnknownEncodedFile(bad_license)
        self.assertEqual(result, "FooBar")

    def testDeprecatedLicenses(self):
        """Verify deprecated license checks."""
        # These are known bad packages.
        licenses_lib._CheckForKnownBadLicenses(
            "chromeos-base/google-sans-fonts-1-r13", {"Google-TOS"}
        )

        # These packages should not be allowed.
        with self.assertRaises(licenses_lib.PackageLicenseError):
            licenses_lib._CheckForKnownBadLicenses(
                "sys-apps/portage-123", {"Proprietary-Binary"}
            )
        with self.assertRaises(licenses_lib.PackageLicenseError):
            licenses_lib._CheckForKnownBadLicenses(
                "sys-apps/portage-123", {"GPL-2", "Google-TOS"}
            )

    def testHookPackageProcess(self):
        build_infos_path = os.path.join(self.tempdir, "build_infos")
        for pkg, build_info in self.build_infos.items():
            if build_info["expected_exception"]:
                with self.assertRaises(licenses_lib.PackageCorrectnessError):
                    licenses_lib.HookPackageProcess(
                        os.path.join(build_infos_path, pkg)
                    )
            else:
                licenses_lib.HookPackageProcess(
                    os.path.join(build_infos_path, pkg)
                )

    @mock.patch("chromite.lib.cros_build_lib.run")
    def testListInstalledPackages(self, run_mock):
        result = "[ U ] test to /build/test_dir\n[ U ] test2 to /build/test_dir"
        run_mock.return_value = cros_build_lib.CompletedProcess(
            args=[], returncode=0, stdout=result
        )
        self.assertRaisesRegex(
            AssertionError,
            r"^.*\[ U \] test.*\[ U \] test2.*$",
            licenses_lib.ListInstalledPackages,
            "",
        )

        result = "[ R ] test to /build/test_dir\n[ R ] test2 to /build/test_dir"
        run_mock.return_value = cros_build_lib.CompletedProcess(
            args=[], returncode=0, stdout=result
        )
        self.assertEqual(
            licenses_lib.ListInstalledPackages(""), ["test", "test2"]
        )

    def testBannedLicenses(self):
        """Verify banned license checks."""
        # These are somewhat redundant, but we want to be overly cautious.
        # All of these have been used in Gentoo at some point.
        BAD_LICENSES = {
            "AGPL",
            "AGPL-1",
            "AGPL-2",
            "AGPL-2+",
            "AGPL-3",
            "AGPL-3+",
            "as-is",
            "CC-BY-NC-4.0",
            "CC-BY-NC-ND-2.0",
            "CC-BY-NC-ND-2.5",
            "CC-BY-NC-ND-3.0",
            "CC-BY-NC-SA-2.5",
            "CC-BY-NC-SA-3.0",
            "CC-BY-NC-SA-4.0",
            "CPAL",
            "CPAL-1.0",
            "EUPL",
            "EUPL-1.1",
            "WTFPL",
            "WTFPL-2",  # nocheck
        }
        for lic in BAD_LICENSES:
            with self.assertRaises(licenses_lib.PackageLicenseError):
                licenses_lib._CheckForKnownBadLicenses("sys-libs/db-18", {lic})
            with self.assertRaises(licenses_lib.PackageLicenseError):
                licenses_lib._CheckForKnownBadLicenses(
                    "sys-libs/db-18", {"GPL-2", lic}
                )

    def testYamlToJson(self):
        """Verify the migration logic."""
        yaml_file = self.tempdir / "foo.yaml"
        yaml_file.write_text(
            """
- !!python/tuple [sysroot, null]
- !!python/tuple [category, dev-python]
- !!python/tuple [name, pycryptodome]
- !!python/tuple [version, 3.7.3]
- !!python/tuple [revision, 0]
- !!python/tuple [fullname, dev-python/pycryptodome]
- !!python/tuple [fullnamerev, dev-python/pycryptodome-3.7.3]
- !!python/tuple
  - license_names
  - !!set {Unlicense: null}
- !!python/tuple
  - license_text_scanned
  - ["Scanned Source License \
pycryptodome-3.7.3-python3_6/pycryptodome.egg-info/PKG-INFO:\\n\\
      Requires-Python: >=2.6, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*\\n"]
- !!python/tuple
  - homepages
  - ['https://www.pycryptodome.org',
    'https://github.com/Legrandin/pycryptodome',
    'https://pypi.org/project/pycryptodome/']
- !!python/tuple [skip, false]
- !!python/tuple [tainted, false]
- !!python/tuple [ebuild_path, null]
""",
            encoding="utf-8",
        )

        json_file = self.tempdir / "foo.json"
        licenses_lib._convert_yaml_to_json(yaml_file, json_file)

        data = json.loads(json_file.read_bytes())
        self.assertEqual(
            data,
            {
                "category": "dev-python",
                "ebuild_path": None,
                "fullname": "dev-python/pycryptodome",
                "fullnamerev": "dev-python/pycryptodome-3.7.3",
                "homepages": [
                    "https://www.pycryptodome.org",
                    "https://github.com/Legrandin/pycryptodome",
                    "https://pypi.org/project/pycryptodome/",
                ],
                "license_names": ["Unlicense"],
                "license_text_scanned": [
                    "Scanned Source License "
                    "pycryptodome-3.7.3-python3_6/pycryptodome.egg-info/"
                    "PKG-INFO:\n"
                    "Requires-Python: >=2.6, !=3.0.*, !=3.1.*, !=3.2.*, "
                    "!=3.3.*\n"
                ],
                "name": "pycryptodome",
                "revision": 0,
                "skip": False,
                "sysroot": None,
                "tainted": False,
                "version": "3.7.3",
            },
        )
