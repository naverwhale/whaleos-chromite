# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test signer_payloads_client library."""

import base64
import os
import shutil
import tempfile
from unittest import mock

from chromite.api.gen.chromiumos import common_pb2
from chromite.api.gen.chromiumos import signing_pb2
from chromite.lib import chroot_lib
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import gs
from chromite.lib import gs_unittest
from chromite.lib import osutils
from chromite.lib import remote_access
from chromite.lib.paygen import gslock
from chromite.lib.paygen import gspaths
from chromite.lib.paygen import signer_payloads_client
from chromite.service import image


pytestmark = cros_test_lib.pytestmark_inside_only

# pylint: disable=protected-access


class SignerPayloadsClientGoogleStorageTest(
    gs_unittest.AbstractGSContextTest, cros_test_lib.TempDirTestCase
):
    """Test suite for the class SignerPayloadsClientGoogleStorage."""

    orig_timeout = (
        signer_payloads_client.DELAY_CHECKING_FOR_SIGNER_RESULTS_SECONDS
    )

    def setUp(self):
        """Setup for tests, and store off some standard expected values."""
        self.hash_names = ["1.payload.hash", "2.payload.hash", "3.payload.hash"]

        self.build_uri = (
            "gs://foo-bucket/foo-channel/foo-board/foo-version/"
            "payloads/signing/foo-unique"
        )

        # Some tests depend on this timeout. Make it smaller, then restore.
        signer_payloads_client.DELAY_CHECKING_FOR_SIGNER_RESULTS_SECONDS = 0.01

    def tearDown(self):
        """Teardown after tests, and restore values test might adjust."""
        # Some tests modify this timeout. Restore the original value.
        signer_payloads_client.DELAY_CHECKING_FOR_SIGNER_RESULTS_SECONDS = (
            self.orig_timeout
        )

    def createStandardClient(self):
        """Test helper method to create a client with standard arguments."""

        client = signer_payloads_client.SignerPayloadsClientGoogleStorage(
            chroot=chroot_lib.Chroot(),
            build=gspaths.Build(
                channel="foo-channel",
                board="foo-board",
                version="foo-version",
                bucket="foo-bucket",
            ),
            work_dir=self.tempdir,
            unique="foo-unique",
            ctx=self.ctx,
        )
        return client

    def testUris(self):
        """Test that the URIs on the client are correct."""

        client = self.createStandardClient()

        expected_build_uri = self.build_uri

        self.assertEqual(client.signing_base_dir, expected_build_uri)

        self.assertEqual(
            client.archive_uri, expected_build_uri + "/payload.hash.tar.bz2"
        )

    def testWorkDir(self):
        """Test that the work_dir is generated/passed correctly."""
        client = self.createStandardClient()
        self.assertIsNotNone(client._work_dir)

        client = signer_payloads_client.SignerPayloadsClientGoogleStorage(
            chroot=chroot_lib.Chroot(),
            build=gspaths.Build(),
            work_dir="/foo-dir",
        )
        self.assertEqual(client._work_dir, "/foo-dir")

    def testCleanSignerFilesByKeyset(self):
        """Test the keyset specific cleanup works as expected."""

        hashes = ("hash-1", "hash-2")
        keyset = "foo-keys"

        lock_uri = (
            "gs://foo-bucket/tobesigned/45,foo-channel,foo-board,"
            "foo-version,payloads,signing,foo-unique,"
            "foo-keys.payload.signer.instructions.lock"
        )

        signing_dir = (
            "gs://foo-bucket/foo-channel/foo-board/foo-version/"
            "payloads/signing/foo-unique"
        )

        expected_removals = (
            # Signing Request
            "gs://foo-bucket/tobesigned/45,foo-channel,foo-board,foo-version,"
            "payloads,signing,foo-unique,"
            "foo-keys.payload.signer.instructions",
            # Signing Instructions
            signing_dir + "/foo-keys.payload.signer.instructions",
            # Signed Results`
            signing_dir + "/1.payload.hash.foo-keys.signed.bin",
            signing_dir + "/1.payload.hash.foo-keys.signed.bin.md5",
            signing_dir + "/2.payload.hash.foo-keys.signed.bin",
            signing_dir + "/2.payload.hash.foo-keys.signed.bin.md5",
        )

        client = self.createStandardClient()

        # Fake lock failed then acquired.
        lock = self.PatchObject(gslock, "Lock", autospec=True)
        lock.Acquire.side_effect = [gslock.LockNotAcquired(), mock.MagicMock()]

        # Do the work.
        client._CleanSignerFilesByKeyset(hashes, keyset)

        # Assert locks created with expected lock_uri.
        lock.assert_called_with(lock_uri)

        # Verify all expected files were removed.
        for uri in expected_removals:
            self.gs_mock.assertCommandContains(["rm", uri])

    def testCleanSignerFiles(self):
        """Test that GS cleanup works as expected."""

        hashes = ("hash-1", "hash-2")
        keysets = ("foo-keys-1", "foo-keys-2")

        lock_uri1 = (
            "gs://foo-bucket/tobesigned/45,foo-channel,foo-board,"
            "foo-version,payloads,signing,foo-unique,"
            "foo-keys-1.payload.signer.instructions.lock"
        )

        lock_uri2 = (
            "gs://foo-bucket/tobesigned/45,foo-channel,foo-board,"
            "foo-version,payloads,signing,foo-unique,"
            "foo-keys-2.payload.signer.instructions.lock"
        )

        signing_dir = (
            "gs://foo-bucket/foo-channel/foo-board/foo-version/"
            "payloads/signing/foo-unique"
        )

        expected_removals = (
            # Signing Request
            "gs://foo-bucket/tobesigned/45,foo-channel,foo-board,foo-version,"
            "payloads,signing,foo-unique,"
            "foo-keys-1.payload.signer.instructions",
            "gs://foo-bucket/tobesigned/45,foo-channel,foo-board,foo-version,"
            "payloads,signing,foo-unique,"
            "foo-keys-2.payload.signer.instructions",
            # Signing Instructions
            signing_dir + "/foo-keys-1.payload.signer.instructions",
            signing_dir + "/foo-keys-2.payload.signer.instructions",
            # Signed Results
            signing_dir + "/1.payload.hash.foo-keys-1.signed.bin",
            signing_dir + "/1.payload.hash.foo-keys-1.signed.bin.md5",
            signing_dir + "/2.payload.hash.foo-keys-1.signed.bin",
            signing_dir + "/2.payload.hash.foo-keys-1.signed.bin.md5",
            signing_dir + "/1.payload.hash.foo-keys-2.signed.bin",
            signing_dir + "/1.payload.hash.foo-keys-2.signed.bin.md5",
            signing_dir + "/2.payload.hash.foo-keys-2.signed.bin",
            signing_dir + "/2.payload.hash.foo-keys-2.signed.bin.md5",
        )

        client = self.createStandardClient()

        # Fake lock failed then acquired.
        lock = self.PatchObject(gslock, "Lock", autospec=True)

        # Do the work.
        client._CleanSignerFiles(hashes, keysets)

        # Check created with lock_uri1, lock_uri2.
        self.assertEqual(
            lock.call_args_list, [mock.call(lock_uri1), mock.call(lock_uri2)]
        )

        # Verify expected removals.
        for uri in expected_removals:
            self.gs_mock.assertCommandContains(["rm", uri])

        self.gs_mock.assertCommandContains(["rm", signing_dir])

    def testCreateInstructionsUri(self):
        """Test that the expected instructions URI is correct."""

        client = self.createStandardClient()

        signature_uri = client._CreateInstructionsURI("keyset_foo")

        expected_signature_uri = (
            self.build_uri + "/keyset_foo.payload.signer.instructions"
        )

        self.assertEqual(signature_uri, expected_signature_uri)

    def testCreateHashNames(self):
        """Test that the expected hash names are generated."""

        client = self.createStandardClient()

        hash_names = client._CreateHashNames(3)

        expected_hash_names = self.hash_names

        self.assertEqual(hash_names, expected_hash_names)

    def testCreateSignatureURIs(self):
        """Test that the expected signature URIs are generated."""

        client = self.createStandardClient()

        signature_uris = client._CreateSignatureURIs(
            self.hash_names, "keyset_foo"
        )

        expected_signature_uris = [
            self.build_uri + "/1.payload.hash.keyset_foo.signed.bin",
            self.build_uri + "/2.payload.hash.keyset_foo.signed.bin",
            self.build_uri + "/3.payload.hash.keyset_foo.signed.bin",
        ]

        self.assertEqual(signature_uris, expected_signature_uris)

    def testCreateArchive(self):
        """Test that we can correctly archive up hash values for the signer."""

        client = self.createStandardClient()

        tmp_dir = None
        hashes = [b"Hash 1", b"Hash 2", b"Hash 3"]

        try:
            with tempfile.NamedTemporaryFile() as archive_file:
                client._CreateArchive(
                    archive_file.name, hashes, self.hash_names
                )

                # Make sure the archive file created exists
                self.assertExists(archive_file.name)

                tmp_dir = tempfile.mkdtemp()

                cmd = ["tar", "-xjf", archive_file.name]
                cros_build_lib.run(cmd, stdout=True, stderr=True, cwd=tmp_dir)

                # Check that the expected (and only the expected) contents are
                # present.
                extracted_file_names = os.listdir(tmp_dir)
                self.assertEqual(
                    len(extracted_file_names), len(self.hash_names)
                )
                for name in self.hash_names:
                    self.assertTrue(name in extracted_file_names)

                # Make sure each file has the expected contents
                for h, hash_name in zip(hashes, self.hash_names):
                    with open(os.path.join(tmp_dir, hash_name), "rb") as f:
                        self.assertEqual([h], f.readlines())

        finally:
            # Clean up at the end of the test
            if tmp_dir:
                shutil.rmtree(tmp_dir)

    def testCreateInstructions(self):
        """Test that we can correctly create signer instructions."""

        client = self.createStandardClient()

        instructions = client._CreateInstructions(self.hash_names, "keyset_foo")

        expected_instructions = """
# Auto-generated instruction file for signing payload hashes.

[insns]
generate_metadata = false
keyset = keyset_foo
channel = foo

input_files = %s
output_names = @BASENAME@.@KEYSET@.signed

[general]
type = update_payload
board = foo-board

archive = payload.hash.tar.bz2

# We reuse version for version rev because we may not know the
# correct versionrev "R24-1.2.3"
version = foo-version
versionrev = foo-version
""" % " ".join(
            ["1.payload.hash", "2.payload.hash", "3.payload.hash"]
        )

        self.assertEqual(instructions, expected_instructions)

    def testSignerRequestUri(self):
        """Test that we can create signer request URI."""

        client = self.createStandardClient()

        instructions_uri = client._CreateInstructionsURI("foo_keyset")
        signer_request_uri = client._SignerRequestUri(instructions_uri)

        expected = (
            "gs://foo-bucket/tobesigned/45,foo-channel,foo-board,"
            "foo-version,payloads,signing,foo-unique,"
            "foo_keyset.payload.signer.instructions"
        )

        self.assertEqual(signer_request_uri, expected)

    def testWaitForSignaturesInstant(self):
        """Test that we can correctly wait for a list of URIs to be created."""
        uris = ["foo", "bar", "is"]

        # All Urls exist.
        exists = self.PatchObject(self.ctx, "Exists", return_value=True)

        client = self.createStandardClient()

        self.assertTrue(client._WaitForSignatures(uris, timeout=0.02))

        # Make sure it really looked for every URL listed.
        self.assertEqual(exists.call_args_list, [mock.call(u) for u in uris])

    def testWaitForSignaturesNever(self):
        """Test that we can correctly timeout waiting for a list of URIs."""
        uris = ["foo", "bar", "is"]

        # Default mock GSContext behavior is nothing Exists.
        client = self.createStandardClient()
        self.assertFalse(client._WaitForSignatures(uris, timeout=0.02))

        # We don't care which URLs it checked, since it doesn't have to check
        # them all in this case.


class SignerPayloadsClientIntegrationTest(cros_test_lib.MockTempDirTestCase):
    """Test suite integration with live signer servers."""

    def setUp(self):
        # This is in the real production chromeos-releases, but the listed
        # build has never, and will never exist.
        self.client = signer_payloads_client.SignerPayloadsClientGoogleStorage(
            chroot=chroot_lib.Chroot(),
            build=gspaths.Build(
                channel="test-channel",
                board="crostools-client",
                version="Rxx-Ryy",
                bucket="chromeos-releases",
            ),
            work_dir=self.tempdir,
        )

    def testDownloadSignatures(self):
        """Test that we can correctly download a list of URIs."""

        def fake_copy(uri, sig):
            """Just write the uri address to the content of the file."""
            osutils.WriteFile(sig, uri, mode="wb")

        self.PatchObject(self.client._ctx, "Copy", side_effect=fake_copy)

        uris = [
            b"gs://chromeos-releases-test/sigining-test/foo",
            b"gs://chromeos-releases-test/sigining-test/bar",
        ]
        downloads = self.client._DownloadSignatures(uris)
        self.assertEqual(downloads, uris)

    @cros_test_lib.pytestmark_network_test
    def testGetHashSignatures(self):
        """Integration test that talks to the real signer with test hashes."""
        ctx = gs.GSContext()

        clean_uri = (
            "gs://chromeos-releases/test-channel/%s/crostools-client/**"
            % (cros_build_lib.GetRandomString(),)
        )

        # Cleanup before we start.
        ctx.Remove(clean_uri, ignore_missing=True)

        try:
            hashes = [
                b"0" * 32,
                b"1" * 32,
                (
                    b"29834370e415b3124a926c903906f18b"
                    b"3d52e955147f9e6accd67e9512185a63"
                ),
            ]

            keysets = ["update_signer"]

            expected_sigs_hex = (
                (
                    "ba4c7a86b786c609bf6e4c5fb9c47525608678caa532bea8acc457aa6"
                    "dd32b435f094b331182f2e167682916990c40ff7b6b0128de3fa45ad0"
                    "fd98041ec36d6f63b867bcf219804200616590a41a727c2685b48340e"
                    "fb4b480f1ef448fc7bc3fb1c4b53209e950ecc721b07a52a41d9c025f"
                    "d25602340c93d5295211308caa29a03ed18516cf61411c508097d5b47"
                    "620d643ed357b05213b2b9fa3a3f938d6c4f52b85c3f9774edc376902"
                    "458344d1c1cd72bc932f033c076c76fee2400716fe652306871ba9230"
                    "21ce245e0c778ad9e0e50e87a169b2aea338c4dc8b5c0c716aabfb613"
                    "3482e8438b084a09503db27ca546e910f8938f7805a8a76a3b0d0241",
                ),
                (
                    "2d909ca5b33a7fb6f2323ca0bf9de2e4f2266c73da4b6948a517dffa9"
                    "6783e08ca36411d380f6e8a20011f599d8d73576b2a141a57c0873d08"
                    "9726e24f62c7e0346ba5fbde68414b0f874b627fb1557a6e9658c8fac"
                    "96c54f458161ea770982bfa9fe514120635e5ccb32e8219b9069cb0bf"
                    "8063fba48d60d649c5af203cccefca5dbc2191f81f0215edbdee4ec8c"
                    "1553e69b83036aca3e840227d317ff6cf8b968c973f698db1ce59f687"
                    "1303dcdbe839400c5df4d2e6e505d68890010a44596ca9fee77f4db6e"
                    "a3448d98018437c319fc8c5f4603ef94b04e3a4eafa206b7391a2640d"
                    "43128310285bc0f1c7e5060d37c433d663b1c6f01110b9a43f2a74f4",
                ),
                (
                    "23791c99ab937f1ae5d4988afc9ceca39c290ac90e3da9f243f9a0b1c"
                    "86c3c32ab7241d43dfc233da412bab989cf02f15a01fe9ea4b2dc7dc9"
                    "182117547836d69310af3aa005ee3a6deb9602bc676dcc103bf3f7831"
                    "d64ab844b4785c5c8b4b14467e6b5ab6bf34c12f7534e0d5140151c8f"
                    "28e8276e703dd6332c2bab9e7f4a495215998ff56e476b81bd6b8d765"
                    "e1f87da50c22cd52c9afa8c43a6528ab8986d7a273d9136d5aff5c4d9"
                    "5985d16eeec7380539ef963e0784a0de42b42890dfc83702179f69f5c"
                    "6eca4630807fbc4ab6241017e0942b15feada0b240e9729bf33bf456b"
                    "d419da63302477e147963550a45c6cf60925ff48ad7b309fa158dcb2",
                ),
            )

            expected_sigs = [
                [base64.b16decode(x[0], True)] for x in expected_sigs_hex
            ]

            all_signatures = self.client.GetHashSignatures(hashes, keysets)

            self.assertEqual(all_signatures, expected_sigs)
            self.assertRaises(gs.GSNoSuchKey, ctx.List, clean_uri)

        finally:
            # Cleanup when we are over.
            ctx.Remove(clean_uri, ignore_missing=True)

    @cros_test_lib.pytestmark_network_test
    def testGetHashSignaturesDuplicates(self):
        """Integration test with real signer with duplicate test hashes."""
        ctx = gs.GSContext()

        clean_uri = (
            "gs://chromeos-releases/test-channel/%s/crostools-client/**"
            % (cros_build_lib.GetRandomString(),)
        )

        # Cleanup before we start.
        ctx.Remove(clean_uri, ignore_missing=True)

        try:
            hashes = [b"0" * 32, b"0" * 32]

            keysets = ["update_signer"]

            expected_sigs_hex = (
                (
                    "ba4c7a86b786c609bf6e4c5fb9c47525608678caa532bea8acc457aa6"
                    "dd32b435f094b331182f2e167682916990c40ff7b6b0128de3fa45ad0"
                    "fd98041ec36d6f63b867bcf219804200616590a41a727c2685b48340e"
                    "fb4b480f1ef448fc7bc3fb1c4b53209e950ecc721b07a52a41d9c025f"
                    "d25602340c93d5295211308caa29a03ed18516cf61411c508097d5b47"
                    "620d643ed357b05213b2b9fa3a3f938d6c4f52b85c3f9774edc376902"
                    "458344d1c1cd72bc932f033c076c76fee2400716fe652306871ba9230"
                    "21ce245e0c778ad9e0e50e87a169b2aea338c4dc8b5c0c716aabfb613"
                    "3482e8438b084a09503db27ca546e910f8938f7805a8a76a3b0d0241",
                ),
                (
                    "ba4c7a86b786c609bf6e4c5fb9c47525608678caa532bea8acc457aa6"
                    "dd32b435f094b331182f2e167682916990c40ff7b6b0128de3fa45ad0"
                    "fd98041ec36d6f63b867bcf219804200616590a41a727c2685b48340e"
                    "fb4b480f1ef448fc7bc3fb1c4b53209e950ecc721b07a52a41d9c025f"
                    "d25602340c93d5295211308caa29a03ed18516cf61411c508097d5b47"
                    "620d643ed357b05213b2b9fa3a3f938d6c4f52b85c3f9774edc376902"
                    "458344d1c1cd72bc932f033c076c76fee2400716fe652306871ba9230"
                    "21ce245e0c778ad9e0e50e87a169b2aea338c4dc8b5c0c716aabfb613"
                    "3482e8438b084a09503db27ca546e910f8938f7805a8a76a3b0d0241",
                ),
            )

            expected_sigs = [
                [base64.b16decode(x[0], True)] for x in expected_sigs_hex
            ]

            all_signatures = self.client.GetHashSignatures(hashes, keysets)

            self.assertEqual(all_signatures, expected_sigs)
            self.assertRaises(gs.GSNoSuchKey, ctx.List, clean_uri)

        finally:
            # Cleanup when we are over.
            ctx.Remove(clean_uri, ignore_missing=True)


class UnofficialPayloadSignerTest(cros_test_lib.TempDirTestCase):
    """Test suit for testing unofficial local payload signer."""

    def setUp(self):
        # UnofficialSignerPayloadsClient need a temporary directory inside
        # chroot so cros_test_lib.TempDirTestCase will not work if we run this
        # unittest outside the chroot.
        chroot = chroot_lib.Chroot()
        with chroot.tempdir(delete=False) as dir_in_chroot:
            self._temp_dir = dir_in_chroot

        self._client = signer_payloads_client.UnofficialSignerPayloadsClient(
            chroot=chroot,
            private_key=remote_access.TEST_PRIVATE_KEY,
            work_dir=self._temp_dir,
        )

    def cleanUp(self):
        shutil.rmtree(self._temp_dir)

    def testExtractPublicKey(self):
        """Tests the correct command is run to extract the public key."""
        with tempfile.NamedTemporaryFile() as public_key:
            self._client.ExtractPublicKey(public_key.name)
            self.assertIn(b"BEGIN PUBLIC KEY", public_key.read())

    def testGetHashSignatures(self):
        """Tests we correctly sign given hashes."""
        hashes = (b"0" * 32, b"1" * 32)
        keyset = "foo-keys"
        expected_sigs_hex = (
            "4732bf3c12b5795d5f4dd015cf8a65d8294186710f71e1530aa3b10d364ed15dc"
            "71cef3bed312fd3f805d1b4ee79c1b868f7b8e175199d1c145838044fa3d037d6"
            "7b142140a7187cb18cd8fb6897cc88481cb258e9ba87e6508a3eb2670b1354210"
            "7dfea51417abb3ee30c8ea81242d1b69c92b8c531e7b3799a28285c26ce5e9834"
            "648cf9601bdaf04257ffe97111b7497e14e4530ef9d4e9b6cdbf473304fee948a"
            "f68fb6c992340e20bcf78f0c6c28d7ea7d8f35322bc61d5d1456b3b868c16bfca"
            "9747887750e2734544b2dc0d22f68866e6456243ad53fc847d957b7fc1e87d0b4"
            "eafbb98b61810a86bf5b587b7241d0f92ba4323da3fc57ccd883fdc4d",
            "63cefceefb45688c5af557949fd0ec408245f5867e1453d2037c2125511a0ef5d"
            "7ead88cfebe04f6cda176a91707a6002a3a618fbb0ae8c956c0e7b56e1f29fb50"
            "c3ec3d47e786131c07b14d15cf768bbaceefd8d900526d79f08a985df910f31d3"
            "3c97ec9f159902e8478f4d0a1766bb21ea81677c67d11b2b17b0f4cf41599dcad"
            "b76549ee0b69badca94ba5fae3b54cea75468a7a670991ba595f622d21ccb1f47"
            "edf0366503200e4ee7fec686908f9099e4fc53f4a963769b42b856d2a8c94a153"
            "18d0620b7ed0b425989c599ffd363390a82c175f4ebab80f46d2f07585f5924fe"
            "1014233ba76ca6a2b047baee023141ab38a027f56c963dd70550204ad",
        )

        expected_sigs = [[base64.b16decode(x, True)] for x in expected_sigs_hex]

        signatures = self._client.GetHashSignatures(hashes, keyset)

        self.assertEqual(signatures, expected_sigs)


class LocalSignerPayloadsClientTest(cros_test_lib.TempDirTestCase):
    """Test suite for the class LocalSignerPayloadsClient."""

    def setUp(self):
        """Setup for tests, and store off some standard expected values."""
        self._docker_image = (
            "us-docker.pkg.dev/chromeos-bot/signing/signing:16963491"
        )

    def createStandardClient(self):
        """Test helper method to create a client with standard arguments."""

        client = signer_payloads_client.LocalSignerPayloadsClient(
            docker_image=self._docker_image,
            build=gspaths.Build(
                channel="dev-channel",
                board="foo-board",
                version="foo-version",
                bucket="foo-bucket",
            ),
            work_dir=self.tempdir,
        )
        return client

    def testWorkDir(self):
        """Test that the work_dir is generated/passed correctly."""
        client = self.createStandardClient()
        self.assertIsNotNone(client._work_dir)

    def testCreateArchive(self):
        """Test that we can correctly archive up hash values for the signer."""

        client = self.createStandardClient()

        tmp_dir = None
        hashes = [b"Hash 1", b"Hash 2", b"Hash 3"]

        try:
            with tempfile.NamedTemporaryFile() as archive_file:
                hash_filenames = client._CreateArchive(
                    archive_file.name, hashes
                )

                # Make sure the archive file created exists
                self.assertExists(archive_file.name)

                tmp_dir = tempfile.mkdtemp()

                cmd = ["tar", "-xjf", archive_file.name]
                cros_build_lib.run(cmd, stdout=True, stderr=True, cwd=tmp_dir)

                # Check that the expected (and only the expected) contents are
                # present.
                extracted_file_names = os.listdir(tmp_dir)
                self.assertEqual(len(extracted_file_names), len(hash_filenames))
                for name in hash_filenames:
                    self.assertTrue(name in extracted_file_names)

                # Make sure each file has the expected contents
                for h, hash_name in zip(hashes, hash_filenames):
                    with open(os.path.join(tmp_dir, hash_name), "rb") as f:
                        self.assertEqual([h], f.readlines())

        finally:
            # Clean up at the end of the test
            if tmp_dir:
                shutil.rmtree(tmp_dir)

    def testReadSignatures(self):
        client = self.createStandardClient()

        keysets = ["keyseta", "keysetb"]
        for keyset in keysets:
            for i in range(3):
                signature_file = f"{i}.payload.hash.{keyset}.signed.bin"
                with open(
                    os.path.join(self.tempdir, signature_file), mode="wb+"
                ) as f:
                    f.write(bytes(f"{i}-{keyset}", "utf-8"))

        artifact_name = lambda n: f"{n}.payload.hash.{keyset}.signed.bin"
        archive_artifacts = []
        for keyset in keysets:
            archive_artifacts.append(
                signing_pb2.ArchiveArtifacts(
                    keyset=keyset,
                    signed_artifacts=[
                        signing_pb2.SignedArtifact(
                            status=signing_pb2.STATUS_SUCCESS,
                            signed_artifact_name=artifact_name(i),
                        )
                        for i in range(3)
                    ],
                )
            )
        signing_response = signing_pb2.BuildTargetSignedArtifacts(
            archive_artifacts=archive_artifacts
        )

        signatures = client._ReadSignatures(
            self.tempdir, keysets, signing_response
        )
        b = lambda s: bytes(s, "utf-8")
        self.assertEqual(
            signatures,
            [
                [b("0-keyseta"), b("0-keysetb")],
                [b("1-keyseta"), b("1-keysetb")],
                [b("2-keyseta"), b("2-keysetb")],
            ],
        )

    @mock.patch.object(image, "SignImage")
    def testGetHashSignaturesMockSignImage(
        self, mock_sign_image: mock.MagicMock
    ):
        client = self.createStandardClient()

        expected_signature_files = [
            f"{i}.payload.hash.update_signer.signed.bin" for i in range(3)
        ]
        os.mkdir(os.path.join(self.tempdir, "result_dir"))
        for i, signature_file in enumerate(expected_signature_files):
            with open(
                os.path.join(self.tempdir, "result_dir", signature_file),
                mode="wb+",
            ) as f:
                f.write(bytes("abcd" * (i + 1), "utf-8"))

        artifact_name = lambda n: f"{n}.payload.hash.update_signer.signed.bin"
        mock_sign_image.return_value = signing_pb2.BuildTargetSignedArtifacts(
            archive_artifacts=[
                signing_pb2.ArchiveArtifacts(
                    keyset="update_signer",
                    signed_artifacts=[
                        signing_pb2.SignedArtifact(
                            status=signing_pb2.STATUS_SUCCESS,
                            signed_artifact_name=artifact_name(i),
                        )
                        for i in range(3)
                    ],
                )
            ]
        )

        hashes = [b"Hash 1", b"Hash 2", b"Hash 3"]
        signatures = client.GetHashSignatures(hashes)
        self.assertEqual(
            signatures,
            [
                [bytes("abcd", "utf-8")],
                [bytes("abcdabcd", "utf-8")],
                [bytes("abcdabcdabcd", "utf-8")],
            ],
        )

        expected_signing_config = signing_pb2.BuildTargetSigningConfigs(
            build_target_signing_configs=[
                signing_pb2.BuildTargetSigningConfig(
                    build_target="foo-board",
                    signing_configs=[
                        signing_pb2.SigningConfig(
                            keyset="update_signer",
                            channel=common_pb2.CHANNEL_DEV,
                            version="foo-version",
                            input_files=[
                                "0.payload.hash",
                                "1.payload.hash",
                                "2.payload.hash",
                            ],
                            output_names=["@BASENAME@.@KEYSET@.signed"],
                            archive_path=os.path.join(
                                client._work_dir, "hashes"
                            ),
                        )
                    ],
                )
            ]
        )
        mock_sign_image.assert_called_with(
            expected_signing_config,
            client._work_dir,
            os.path.join(client._work_dir, "result_dir"),
            self._docker_image,
        )
