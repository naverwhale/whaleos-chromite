# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the key_value_store module."""

import os
from pathlib import Path
import tempfile

from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.utils import key_value_store


class TestKeyValueFiles(cros_test_lib.TempDirTestCase):
    """Tests handling of key/value files."""

    def setUp(self):
        self.contents = """# A comment !@
A = 1
AA= 2
AAA =3
AAAA\t=\t4
AAAAA\t   \t=\t   5
AAAAAA = 6     \t\t# Another comment
\t
\t# Aerith lives!
C = 'D'
CC= 'D'
CCC ='D'
\x20
 \t# monsters go boom #
E \t= "Fxxxxx" # Blargl
EE= "Faaa\taaaa"\x20
EEE ="Fk  \t  kkkk"\t
Q = "'q"
\tQQ ="q'"\x20
 QQQ='"q"'\t
R = "r
"
RR = "rr
rrr"
RRR = 'rrr
 RRRR
 rrr
'
SSS=" ss
'ssss'
ss"
T="
ttt"
"""
        self.expected = {
            "A": "1",
            "AA": "2",
            "AAA": "3",
            "AAAA": "4",
            "AAAAA": "5",
            "AAAAAA": "6",
            "C": "D",
            "CC": "D",
            "CCC": "D",
            "E": "Fxxxxx",
            "EE": "Faaa\taaaa",
            "EEE": "Fk  \t  kkkk",
            "Q": "'q",
            "QQ": "q'",
            "QQQ": '"q"',
            "R": "r\n",
            "RR": "rr\nrrr",
            "RRR": "rrr\n RRRR\n rrr\n",
            "SSS": " ss\n'ssss'\nss",
            "T": "\nttt",
        }

        self.conf_file = os.path.join(self.tempdir, "file.conf")
        self.conf_path = Path(self.conf_file)
        osutils.WriteFile(self.conf_file, self.contents)

    def _RunAndCompare(self, test_input, multiline):
        result = key_value_store.LoadFile(test_input, multiline=multiline)
        self.assertEqual(self.expected, result)

    def testLoadFilePath(self):
        """Verify reading a simple file works."""
        self._RunAndCompare(self.conf_file, True)

    def testLoadPath(self):
        """Verify reading a simple file Path works."""
        self._RunAndCompare(self.conf_path, True)

    def testLoadData(self):
        """Verify passing in a string works."""
        result = key_value_store.LoadData(self.contents, multiline=True)
        self.assertEqual(self.expected, result)

    def testLoadFileObject(self):
        """Verify passing in open file object works."""
        with open(self.conf_file, encoding="utf-8") as f:
            self._RunAndCompare(f, True)

    def testNoMultlineValues(self):
        """Verify exception is thrown when multiline is disabled."""
        self.assertRaises(
            ValueError, self._RunAndCompare, self.conf_file, False
        )


class TestUpdateFile(cros_test_lib.TempDirTestCase):
    """Tests for UpdateKeyInLocalFile and UpdateKeysInLocalFile."""

    def setUp(self) -> None:
        """Set up vars that will be used in unit tests."""
        self.contents_str = "\n".join(
            [
                "# comment that should be skipped",
                'PKGDIR="/var/lib/portage/pkgs"',
                'PORTAGE_BINHOST="http://no.thanks.com"',
                'COMPILE_FLAGS="some_value=some_other"',
                '  \tKEY_WITH_WHITESPACE \t = "my_value"     ',
            ]
        )
        self.version_file = os.path.join(self.tempdir, "version")

    def _initialize_file(self) -> None:
        """Set up the file with some basic contents.

        Because the file persists across test methods, this should be called at
        the start of each test. Otherwise the tests would not be hermetic.
        """
        osutils.WriteFile(self.version_file, self.contents_str)

    def _read_file(self, filepath: str = None) -> str:
        """Read the contents of filepath and return as a string."""
        with open(filepath, encoding="utf-8") as f:
            return f.read()

    def _check_key_value(self, key: str, expected_value: str) -> None:
        """Check that the key is defined once with the right value."""
        file_contents = self._read_file(self.version_file)

        # Ensure that the key is only defined once.
        key_found = False
        for line in file_contents.split("\n"):
            if "=" not in line:
                continue
            file_key = line.split("=", maxsplit=1)[0].strip()
            if file_key == key:
                if key_found:
                    self.fail(
                        f"Key {file_key} appears more than once. "
                        f"File contents:\n{file_contents}"
                    )
                key_found = True
        if not key_found:
            self.fail(
                f"Key {key} not defined in key-value store; "
                f"expected value {expected_value}. "
                f"File contents:\n{file_contents}"
            )

        # Ensure that the key is defined with the right value.
        # Use LoadData() so we don't need to duplicate parsing logic.
        contents_dict = key_value_store.LoadData(file_contents)
        if contents_dict[key] != expected_value:
            self.fail(
                f"Key {key} had unexpected value {contents_dict[key]}; "
                f"expected {expected_value}. "
                f"File contents:\n{file_contents}"
            )

    def testAddVariableThatDoesNotExist(self):
        """Add in a new variable that was no present in the file."""
        self._initialize_file()
        key = "NEW_KEY"
        value = "1234567"
        key_value_store.UpdateKeyInLocalFile(self.version_file, key, value)
        print(self.version_file)
        self._check_key_value(key, value)
        print(self.version_file)

    def testUpdateExistingVariable(self):
        """Test updating a variable that already exists."""
        self._initialize_file()
        binhost_key = "PORTAGE_BINHOST"
        pkgdir_key = "PKGDIR"

        # Check that the existing keys are already in the file before we start.
        existing_keyvals_dict = key_value_store.LoadData(self.contents_str)
        for existing_key in (binhost_key, pkgdir_key):
            if existing_key not in existing_keyvals_dict:
                self.fail(
                    f"Key {existing_key} not found in initial key-value store."
                )
        pkgdir_value = existing_keyvals_dict[pkgdir_key]

        # Update binhost_key and check the new value.
        # _check_key_value will also ensure that the key is only defined once.
        new_value = "http://no.thanks.com"
        key_value_store.UpdateKeyInLocalFile(
            self.version_file, binhost_key, new_value
        )
        self._check_key_value(binhost_key, new_value)

        # Confirm that unrelated variable does not change.
        self._check_key_value(pkgdir_key, pkgdir_value)

    def testUpdateNonExistentFile(self):
        """Test that we can write key/values in files that don't exist yet."""
        self._initialize_file()
        key = "PORTAGE_BINHOST"
        value = "1234567"
        non_existent_file = tempfile.mktemp()
        try:
            key_value_store.UpdateKeyInLocalFile(non_existent_file, key, value)
            file_contents = self._read_file(non_existent_file)
            self.assertEqual(file_contents, f'{key}="{value}"\n')
        finally:
            if os.path.exists(non_existent_file):
                os.remove(non_existent_file)

    def testExistingKeyValWithWhitespace(self):
        """Test that we can identify a keyval wrapped in whitespace."""
        self._initialize_file()
        key = "KEY_WITH_WHITESPACE"
        new_value = "new_value"
        key_value_store.UpdateKeyInLocalFile(self.version_file, key, new_value)
        self._check_key_value(key, new_value)

    def testUpdateKeysEmptyDict(self):
        """Test UpdateKeys with an empty input dict."""
        self._initialize_file()
        result = key_value_store.UpdateKeysInLocalFile(self.version_file, {})
        self.assertFalse(result)

    def testUpdateTwoKeysButOnlyOneChange(self):
        """Test UpdateKeys with multiple key-value pairs but only one change."""
        self._initialize_file()
        d = {
            "PKGDIR": "/var/lib/portage/pkgs",
            "PORTAGE_BINHOST": "different_value",
        }
        result = key_value_store.UpdateKeysInLocalFile(self.version_file, d)
        self.assertTrue(result)

    def testUpdateTwoKeysButNoChange(self):
        """Test UpdateKeys with multiple key-value pairs but no change."""
        self._initialize_file()
        d = {
            "PKGDIR": "/var/lib/portage/pkgs",
            "PORTAGE_BINHOST": "http://no.thanks.com",
        }
        result = key_value_store.UpdateKeysInLocalFile(self.version_file, d)
        self.assertFalse(result)
