# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for dlc_allowlist."""

import re
from typing import Pattern, Tuple

from chromite.lib import cros_test_lib
from chromite.lib import dlc_allowlist


class DlcAllowlistTest(cros_test_lib.TestCase):
    """Tests DlcAllowlist functions."""

    def testIsAllowlisted(self):
        """Test the IsAllowlisted function."""
        self.assertTrue(dlc_allowlist.IsAllowlisted("", ("",)))
        self.assertTrue(dlc_allowlist.IsAllowlisted("id", ("id",)))
        self.assertTrue(dlc_allowlist.IsAllowlisted("id", ("", "id", "")))

        self.assertFalse(dlc_allowlist.IsAllowlisted("id", ()))
        self.assertFalse(dlc_allowlist.IsAllowlisted("id", ("",)))
        self.assertFalse(dlc_allowlist.IsAllowlisted("id", ("notid",)))
        self.assertFalse(dlc_allowlist.IsAllowlisted("id", ("", "notid")))

    def testIsAllowlistedRe(self):
        """Test the IsAllowlistedRe function."""

        def compile_regexes(regexes: Tuple[str]) -> Tuple[Pattern]:
            """Helper to compile regexes."""
            return tuple(re.compile(regex) for regex in regexes)

        self.assertTrue(
            dlc_allowlist.IsAllowlistedRe("", compile_regexes((r"",)))
        )
        self.assertTrue(
            dlc_allowlist.IsAllowlistedRe("", compile_regexes((r".*",)))
        )
        self.assertTrue(
            dlc_allowlist.IsAllowlistedRe("id", compile_regexes((r"i.*",)))
        )
        self.assertTrue(
            dlc_allowlist.IsAllowlistedRe("id", compile_regexes((r".*d",)))
        )
        self.assertTrue(
            dlc_allowlist.IsAllowlistedRe(
                "id", compile_regexes((r"a.*", r"i.*"))
            )
        )

        self.assertFalse(
            dlc_allowlist.IsAllowlistedRe("id", compile_regexes((r"",)))
        )
        self.assertFalse(
            dlc_allowlist.IsAllowlistedRe("id", compile_regexes((r"a.*",)))
        )
        self.assertFalse(
            dlc_allowlist.IsAllowlistedRe(
                "id", compile_regexes((r"a.*", r"b.*"))
            )
        )

    def testIsPowerwashSafeAllowlisted(self):
        """Test the IsPowerwashSafeAllowlisted function."""
        self.assertTrue(dlc_allowlist.IsPowerwashSafeAllowlisted("sample-dlc"))
        self.assertTrue(
            dlc_allowlist.IsPowerwashSafeAllowlisted("prebuilt-test-dlc")
        )
        self.assertTrue(
            dlc_allowlist.IsPowerwashSafeAllowlisted("modem-fw-dlc-foo")
        )
        self.assertTrue(
            dlc_allowlist.IsPowerwashSafeAllowlisted("modem-fw-dlc-foo123")
        )
        self.assertTrue(
            dlc_allowlist.IsPowerwashSafeAllowlisted("modem-fw-dlc-foo123-FOO")
        )

        self.assertFalse(dlc_allowlist.IsPowerwashSafeAllowlisted(""))
        self.assertFalse(dlc_allowlist.IsPowerwashSafeAllowlisted("scaled-dlc"))

    def testIsFactoryInstallAllowlisted(self):
        """Test the IsFactoryInstallAllowlisted function."""
        self.assertTrue(dlc_allowlist.IsFactoryInstallAllowlisted("sample-dlc"))
        self.assertTrue(
            dlc_allowlist.IsFactoryInstallAllowlisted("modem-fw-dlc-foo")
        )
        self.assertTrue(
            dlc_allowlist.IsFactoryInstallAllowlisted("modem-fw-dlc-foo123")
        )
        self.assertTrue(
            dlc_allowlist.IsFactoryInstallAllowlisted("modem-fw-dlc-foo123-FOO")
        )

        self.assertFalse(dlc_allowlist.IsFactoryInstallAllowlisted(""))
        self.assertFalse(
            dlc_allowlist.IsFactoryInstallAllowlisted("scaled-dlc")
        )
