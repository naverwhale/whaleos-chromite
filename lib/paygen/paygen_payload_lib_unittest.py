# Copyright 2013 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test paygen_payload_lib library."""

import json
import os
import shutil
import subprocess
import tempfile
from unittest import mock

from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import dlc_lib
from chromite.lib import osutils
from chromite.lib import partial_mock
from chromite.lib.paygen import download_cache
from chromite.lib.paygen import gspaths
from chromite.lib.paygen import partition_lib
from chromite.lib.paygen import paygen_payload_lib
from chromite.lib.paygen import signer_payloads_client
from chromite.lib.paygen import urilib
from chromite.lib.paygen import utils


pytestmark = cros_test_lib.pytestmark_inside_only

# We access a lot of protected members during testing.
# pylint: disable=protected-access


class PaygenLibTest(cros_test_lib.RunCommandTempDirTestCase):
    """PaygenPayloadLib tests base class."""

    def setUp(self):
        self.old_build = gspaths.Build(
            channel="dev-channel",
            board="x86-alex",
            version="1620.0.0",
            bucket="chromeos-releases",
        )

        self.old_image = gspaths.Image(
            build=self.old_build,
            key="mp-v3",
            uri=(
                "gs://chromeos-releases/dev-channel/x86-alex/1620.0.0/"
                "chromeos_1620.0.0_x86-alex_recovery_dev-channel_mp-v3.bin"
            ),
        )

        self.old_base_image = gspaths.Image(
            build=self.old_build,
            key="mp-v3",
            image_type="base",
            uri=(
                "gs://chromeos-releases/dev-channel/x86-alex/1620.0.0/"
                "chromeos_1620.0.0_x86-alex_base_dev-channel_mp-v3.bin"
            ),
        )

        self.new_build = gspaths.Build(
            channel="dev-channel",
            board="x86-alex",
            version="4171.0.0",
            bucket="chromeos-releases",
        )

        self.new_image = gspaths.Image(
            build=self.new_build,
            key="mp-v3",
            uri=(
                "gs://chromeos-releases/dev-channel/x86-alex/4171.0.0/"
                "chromeos_4171.0.0_x86-alex_recovery_dev-channel_mp-v3.bin"
            ),
        )

        self.new_dlc_image = gspaths.DLCImage(
            build=self.new_build,
            key="dlc",
            dlc_id="sample-dlc",
            dlc_package="sample-package",
            uri=(
                "gs://chromeos-releases/dev-channel/x86-alex/4171.0.0/dlc/"
                "sample-dlc/sample-package/dlc.img"
            ),
        )

        self.old_dlc_image = gspaths.DLCImage(
            build=self.old_build,
            key="dlc",
            dlc_id="sample-dlc",
            dlc_package="sample-package",
            uri=(
                "gs://chromeos-releases/dev-channel/x86-alex/1620.0.0/dlc/"
                "sample-dlc/sample-package/dlc.img"
            ),
        )

        self.old_test_image = gspaths.UnsignedImageArchive(
            build=self.old_build,
            uri=(
                "gs://chromeos-releases/dev-channel/x86-alex/1620.0.0/"
                "chromeos_1620.0.0_x86-alex_recovery_dev-channel_test.bin"
            ),
        )

        self.new_test_image = gspaths.Image(
            build=self.new_build,
            uri=(
                "gs://chromeos-releases/dev-channel/x86-alex/4171.0.0/"
                "chromeos_4171.0.0_x86-alex_recovery_dev-channel_test.bin"
            ),
        )

        self.full_payload = gspaths.Payload(
            tgt_image=self.old_base_image,
            src_image=None,
            uri="gs://full_old_foo/boo",
        )

        self.full_dlc_payload = gspaths.Payload(
            tgt_image=self.new_dlc_image,
            src_image=None,
            uri="gs://full_old_foo/boo",
        )

        self.full_minios_payload = gspaths.Payload(
            tgt_image=self.old_base_image,
            src_image=None,
            uri="gs://full_old_foo/boo",
            minios=True,
        )

        self.delta_payload = gspaths.Payload(
            tgt_image=self.new_image,
            src_image=self.old_image,
            uri="gs://delta_new_old/boo",
        )

        self.delta_dlc_payload = gspaths.Payload(
            tgt_image=self.new_dlc_image,
            src_image=self.old_dlc_image,
            uri="gs://full_old_foo/boo",
        )

        self.full_test_payload = gspaths.Payload(
            tgt_image=self.old_test_image,
            src_image=None,
            uri="gs://full_old_foo/boo-test",
        )

        self.delta_test_payload = gspaths.Payload(
            tgt_image=self.new_test_image,
            src_image=self.old_test_image,
            uri="gs://delta_new_old/boo-test",
        )

        self._rand_idx = 0

        def _random():
            self._rand_idx = self._rand_idx + 1
            return f"<random{self._rand_idx}>"

        self.PatchObject(cros_build_lib, "GetRandomString", side_effect=_random)

    @classmethod
    def setUpClass(cls):
        cls.cache_dir = tempfile.mkdtemp(prefix="crostools-unittest-cache")
        cls.cache = download_cache.DownloadCache(cls.cache_dir)

    @classmethod
    def tearDownClass(cls):
        cls.cache = None
        shutil.rmtree(cls.cache_dir)


class PaygenSignerTest(PaygenLibTest):
    """PaygenSigner testing."""

    def testSetupOfficialSigner(self):
        """Tests that official signer is being setup properly."""
        signer = paygen_payload_lib.PaygenSigner(
            chroot=chroot_lib.Chroot(),
            work_dir="/foo",
            private_key="foo-private-key",
            payload_build=self.full_payload.build,
        )

        self.assertIsInstance(
            signer._signer,
            signer_payloads_client.SignerPayloadsClientGoogleStorage,
        )
        self.assertIsNone(signer._private_key)
        self.assertIsNone(signer.public_key)

    def testSetupUnofficialSigner(self):
        """Tests that unofficial signer is being setup properly.

        And private key is set to the default correctly.
        """
        pubkey_extract_mock = self.PatchObject(
            signer_payloads_client.UnofficialSignerPayloadsClient,
            "ExtractPublicKey",
        )

        build = self.new_build
        build.bucket = "foo-bucket"
        signer = paygen_payload_lib.PaygenSigner(
            chroot=chroot_lib.Chroot(),
            work_dir="/foo",
            private_key=None,
            payload_build=None,
        )

        self.assertIsInstance(
            signer._signer,
            signer_payloads_client.UnofficialSignerPayloadsClient,
        )
        self.assertEqual(
            signer._private_key,
            constants.CHROMITE_DIR / "ssh_keys" / "testing_rsa",
        )
        pubkey_extract_mock.assert_called_once_with("/foo/public_key.pem")

    def testSetupUnofficialSignerPassedPrivateKey(self):
        """Tests that setting signers use correct passed private key."""
        build = self.new_build
        build.bucket = "foo-bucket"
        signer = paygen_payload_lib.PaygenSigner(
            chroot=chroot_lib.Chroot(),
            work_dir="/foo",
            private_key="some-foo-private-key",
            payload_build=None,
        )

        self.assertIsInstance(
            signer._signer,
            signer_payloads_client.UnofficialSignerPayloadsClient,
        )
        self.assertEqual(signer._private_key, "some-foo-private-key")

    def testSetupLocalSigner(self):
        """Tests that local signer is being setup properly."""
        signer = paygen_payload_lib.PaygenSigner(
            chroot=chroot_lib.Chroot(),
            work_dir="/foo",
            payload_build=self.full_payload.build,
            local_signing=True,
        )

        self.assertIsInstance(
            signer._signer,
            signer_payloads_client.LocalSignerPayloadsClient,
        )


class PaygenPayloadLibBasicTest(PaygenLibTest):
    """PaygenPayloadLib basic (and quick) testing."""

    def _GetStdGenerator(
        self, work_dir=None, payload=None, sign=True, minios=False, static=True
    ):
        """Helper function to create a standardized PayloadGenerator."""
        if payload is None:
            payload = self.full_payload

        if work_dir is None:
            work_dir = self.tempdir

        payload.minios = payload.minios or minios

        signer_mock = None
        if sign:
            signer_mock = self.PatchObject(paygen_payload_lib, "PaygenSigner")
            signer_mock.public_key = None

        gen = paygen_payload_lib.PaygenPayload(
            chroot=chroot_lib.Chroot(),
            payload=payload,
            work_dir=work_dir,
            signer=signer_mock,
            verify=False,
            static=static,
        )

        gen.partition_names = ("foo-root", "foo-kernel")
        gen.tgt_partitions = ("/work/tgt_root.bin", "/work/tgt_kernel.bin")
        gen.src_partitions = ("/work/src_root.bin", "/work/src_kernel.bin")

        return gen

    def testPaygenPayloadRunOSPayload(self):
        gen = self._GetStdGenerator(work_dir="/foo", minios=False)

        mock_inner_run = self.PatchObject(gen, "_Run", return_value=None)

        gen.Run()

        self.assertEqual(
            mock_inner_run.call_args_list,
            [
                mock.call(),
            ],
        )

    def testPaygenPayloadRunMiniOSPayload(self):
        gen = self._GetStdGenerator(work_dir="/foo", minios=True)

        mock_inner_run = self.PatchObject(gen, "_Run", return_value=None)

        gen.Run()

        self.assertEqual(
            mock_inner_run.call_args_list,
            [
                mock.call(part_a=True),
                mock.call(part_a=False),
            ],
        )

    def testWorkingDirNames(self):
        """Make sure that files we create have the expected names."""
        gen = self._GetStdGenerator(work_dir="/foo")

        self.assertEqual(gen.src_image_file, "/foo/src_image.bin")
        self.assertEqual(gen.tgt_image_file, "/foo/tgt_image.bin")
        self.assertEqual(gen.payload_file, "/foo/delta.bin")
        self.assertEqual(gen.log_file, "/foo/delta.log")

        # Siged image specific values.
        self.assertEqual(gen.signed_payload_file, "/foo/delta.bin.signed")
        self.assertEqual(
            gen.metadata_signature_file,
            "/foo/delta.bin.signed.metadata-signature",
        )

    def testWorkingDirNamesNonStatic(self):
        """Make sure that files we create have the expected names."""
        gen = self._GetStdGenerator(work_dir="/foo", static=False)

        self.assertEqual(gen.src_image_file, "/foo/src_image-<random1>.bin")
        self.assertEqual(gen.tgt_image_file, "/foo/tgt_image-<random1>.bin")
        self.assertEqual(gen.payload_file, "/foo/delta-<random1>.bin")
        self.assertEqual(gen.log_file, "/foo/delta-<random1>.log")

        # Siged image specific values.
        self.assertEqual(
            gen.signed_payload_file, "/foo/delta-<random1>.bin.signed"
        )
        self.assertEqual(
            gen.metadata_signature_file,
            "/foo/delta-<random1>.bin.signed.metadata-signature",
        )

    def testWorkingDirNamesMiniOS(self):
        """Make sure that files we create have the expected names."""
        gen = self._GetStdGenerator(work_dir="/foo", minios=True)

        self.assertEqual(gen.src_image_file, "/foo/src_image-<random1>.bin")
        self.assertEqual(gen.tgt_image_file, "/foo/tgt_image-<random1>.bin")
        self.assertEqual(gen.payload_file, "/foo/delta-<random1>.bin")
        self.assertEqual(gen.log_file, "/foo/delta-<random1>.log")

        # Siged image specific values.
        self.assertEqual(
            gen.signed_payload_file, "/foo/delta-<random1>.bin.signed"
        )
        self.assertEqual(
            gen.metadata_signature_file,
            "/foo/delta-<random1>.bin.signed.metadata-signature",
        )

    def testUriManipulators(self):
        """Validate _MetadataUri."""
        gen = self._GetStdGenerator(work_dir="/foo")

        self.assertEqual(
            gen._MetadataUri("/foo/bar"), "/foo/bar.metadata-signature"
        )
        self.assertEqual(
            gen._MetadataUri("gs://foo/bar"), "gs://foo/bar.metadata-signature"
        )

        self.assertEqual(gen._LogsUri("/foo/bar"), "/foo/bar.log")
        self.assertEqual(gen._LogsUri("gs://foo/bar"), "gs://foo/bar.log")

        self.assertEqual(gen._JsonUri("/foo/bar"), "/foo/bar.json")
        self.assertEqual(gen._JsonUri("gs://foo/bar"), "gs://foo/bar.json")

    def testRunGeneratorCmd(self):
        """Test the specialized command to run programs in chroot."""
        expected_cmd = ["cmd", "bar", "jo nes"]
        expected_stdout = b"foo output"
        self.rc.AddCmdResult(expected_cmd, stdout=expected_stdout)
        gen = self._GetStdGenerator(work_dir=self.tempdir)
        gen._RunGeneratorCmd(expected_cmd)

        self.rc.assertCommandCalled(
            expected_cmd,
            stdout=True,
            enter_chroot=True,
            chroot_args=mock.ANY,
            stderr=subprocess.STDOUT,
            extra_env=mock.ANY,
        )

        self.assertIn(
            expected_stdout,
            osutils.ReadFile(
                os.path.join(self.tempdir, "delta.log"), mode="rb"
            ),
        )

    def testRunGeneratorCmdSquawk(self):
        """Test the specialized command to run programs in chroot w/squawk."""
        expected_cmd = ["cmd", "bar", "jo nes"]
        expected_stdout = b"foo output"
        self.rc.AddCmdResult(expected_cmd, stdout=expected_stdout)
        gen = self._GetStdGenerator(work_dir=self.tempdir)
        gen._RunGeneratorCmd(expected_cmd, squawk_wrap=True)

        self.rc.assertCommandCalled(
            expected_cmd,
            stdout=True,
            enter_chroot=True,
            chroot_args=mock.ANY,
            stderr=subprocess.STDOUT,
            extra_env=mock.ANY,
        )

        self.assertIn(
            expected_stdout,
            osutils.ReadFile(
                os.path.join(self.tempdir, "delta.log"), mode="rb"
            ),
        )

    def testBuildArg(self):
        """Make sure the function semantics is satisfied."""
        gen = self._GetStdGenerator(work_dir="/work")
        test_dict = {"foo": "bar"}

        # Value present.
        self.assertEqual(gen._BuildArg("--foo", test_dict, "foo"), "--foo=bar")

        # Value present, default has no impact.
        self.assertEqual(
            gen._BuildArg("--foo", test_dict, "foo", default="baz"), "--foo=bar"
        )

        # Value missing, default kicking in.
        self.assertEqual(
            gen._BuildArg("--foo2", test_dict, "foo2", default="baz"),
            "--foo2=baz",
        )

    def _DoPrepareImageTest(self, image_type):
        """Test _PrepareImage."""
        download_uri = "gs://bucket/foo/image.bin"
        image_file = "/work/image.bin"
        gen = self._GetStdGenerator(work_dir=self.tempdir)

        if image_type == "Image":
            image_obj = gspaths.Image(
                build=self.new_build, key="mp-v3", uri=download_uri
            )
            test_extract_file = None
        elif image_type == "UnsignedImageArchive":
            image_obj = gspaths.UnsignedImageArchive(
                build=self.new_build, image_type="test", uri=download_uri
            )
            test_extract_file = paygen_payload_lib.PaygenPayload.TEST_IMAGE_NAME
        else:
            raise ValueError("invalid image type descriptor (%s)" % image_type)

        # Stub out and Check the expected function calls.
        copy_mock = self.PatchObject(
            download_cache.DownloadCache, "GetFileCopy"
        )
        if test_extract_file:
            download_file = mock.ANY
        else:
            download_file = image_file

        if test_extract_file:
            move_mock = self.PatchObject(shutil, "move")

        # Run the test.
        gen._PrepareImage(image_obj, image_file)

        copy_mock.assert_called_once_with(download_uri, download_file)

        if test_extract_file:
            self.rc.assertCommandCalled(
                [
                    "tar",
                    "--sparse",
                    "-xf",
                    download_file,
                    "--directory",
                    str(self.tempdir),
                    test_extract_file,
                ],
                capture_output=True,
                encoding="utf-8",
            )
            move_mock.assert_called_once_with(
                os.path.join(self.tempdir, test_extract_file), image_file
            )

    def testPrepareImageNormal(self):
        """Test preparing a normal image."""
        self._DoPrepareImageTest("Image")

    def testPrepareImageTest(self):
        """Test preparing a test image."""
        self._DoPrepareImageTest("UnsignedImageArchive")

    def testGeneratePostinstConfigTrue(self):
        """Tests creating the postinstall config file."""
        gen = self._GetStdGenerator(
            payload=self.full_payload, work_dir=self.tempdir
        )

        gen._GeneratePostinstConfig(True)
        self.assertEqual(
            osutils.ReadFile(gen._postinst_config_file),
            "RUN_POSTINSTALL_root=true\n",
        )

    def testGeneratePostinstConfigFalse(self):
        """Tests creating the postinstall config file."""
        gen = self._GetStdGenerator(
            payload=self.full_payload, work_dir=self.tempdir
        )

        gen._GeneratePostinstConfig(False)
        self.assertEqual(
            osutils.ReadFile(gen._postinst_config_file),
            "RUN_POSTINSTALL_root=false\n",
        )

    def testPreparePartitionsImageType(self):
        """Tests discrepancy in image types for _PreparePartitions function."""
        gen = self._GetStdGenerator(
            payload=self.delta_payload, work_dir=self.tempdir
        )

        def side_effect(image):
            if image == gen.tgt_image_file:
                return partition_lib.CROS_IMAGE
            else:
                return partition_lib.DLC_IMAGE

        self.PatchObject(
            partition_lib, "LookupImageType", side_effect=side_effect
        )

        with self.assertRaisesRegex(
            paygen_payload_lib.Error, "different types"
        ):
            gen._PreparePartitions()

    def testPreparePartitionsGptFull(self):
        """Tests _PreparePartitions function for GPT (platform) images.

        This test is or full payloads only.
        """
        gen = self._GetStdGenerator(
            payload=self.full_payload, work_dir=self.tempdir
        )
        # Mock out needed functions.
        self.PatchObject(
            partition_lib,
            "LookupImageType",
            return_value=partition_lib.CROS_IMAGE,
        )
        platform_params_mock = self.PatchObject(
            gen, "_GetPlatformImageParams", return_value=("foo-appid", None)
        )
        root_ext_mock = self.PatchObject(partition_lib, "ExtractRoot")
        kern_ext_mock = self.PatchObject(partition_lib, "ExtractKernel")
        postinst_mock = self.PatchObject(gen, "_GeneratePostinstConfig")
        tgt_image_file = gen.tgt_image_file

        gen._PreparePartitions()

        # Check the appid was correctly set.
        self.assertEqual(gen._appid, "foo-appid")
        # Check extract partition functions are called correctly.
        root_ext_mock.assert_called_once_with(
            tgt_image_file, gen.tgt_partitions[0]
        )
        kern_ext_mock.assert_called_once_with(
            tgt_image_file, gen.tgt_partitions[1]
        )
        # Checks that postinstall config file was generated.
        postinst_mock.assert_called_once_with(True)
        # Checks we mounted the image and read the lsb-release file correctly.
        platform_params_mock.assert_called_once_with(tgt_image_file)
        # Make sure the tgt_image_file variable is set to None so no one can use
        # it again.
        self.assertIsNone(gen.tgt_image_file)

    def testPreparePartitionsGptDelta(self):
        """Tests _PreparePartitions function for GPT (platform) images.

        This test is or delta payloads only.
        """
        gen = self._GetStdGenerator(
            payload=self.delta_payload, work_dir=self.tempdir
        )

        # Mock out needed functions.
        self.PatchObject(
            partition_lib,
            "LookupImageType",
            return_value=partition_lib.CROS_IMAGE,
        )
        self.PatchObject(
            gen, "_GetPlatformImageParams", return_value=("foo-appid", None)
        )
        root_ext_mock = self.PatchObject(partition_lib, "ExtractRoot")
        kern_ext_mock = self.PatchObject(partition_lib, "ExtractKernel")

        gen._PreparePartitions()

        # Check extract partition functions are called correctly. Two times each
        # partition (kernel, rootfs), once for source partition and once for
        # target partition.
        self.assertEqual(root_ext_mock.call_count, 2)
        self.assertEqual(kern_ext_mock.call_count, 2)

    def testPreparePartitionsDlc(self):
        """Tests _PreparePartitions function for DLC images."""
        gen = self._GetStdGenerator(
            payload=self.full_payload, work_dir=self.tempdir
        )
        self.PatchObject(
            partition_lib,
            "LookupImageType",
            return_value=partition_lib.DLC_IMAGE,
        )
        get_params_mock = self.PatchObject(
            gen,
            "_GetDlcImageParams",
            return_value=("foo-id", "foo-package", "foo-appid"),
        )
        postinst_mock = self.PatchObject(gen, "_GeneratePostinstConfig")

        gen._PreparePartitions()

        self.assertEqual(gen._appid, "foo-appid")
        self.assertEqual(gen.partition_names, ("dlc/foo-id/foo-package",))
        self.assertFalse(postinst_mock.called)
        get_params_mock.assert_called_once()

    def testPreparePartitionsMiniOSFull(self):
        """Tests _PreparePartitions function for only the MiniOS partition.

        This test is for full payloads only.
        """
        gen = self._GetStdGenerator(
            payload=self.full_payload, work_dir=self.tempdir, minios=True
        )
        # Mock out needed functions.
        self.PatchObject(
            partition_lib,
            "LookupImageType",
            return_value=partition_lib.CROS_IMAGE,
        )
        params_mock = self.PatchObject(
            gen,
            "_GetPlatformImageParams",
            return_value=("foo-appid_minios", None),
        )
        minios_ext_mock = self.PatchObject(partition_lib, "ExtractMiniOS")
        tgt_image_file = gen.tgt_image_file
        gen._PreparePartitions()
        # Check the appid was correctly set.
        self.assertEqual(gen._appid, "foo-appid_minios")
        # Check extract partition function is called correctly.
        self.assertEqual(len(gen.tgt_partitions), 1)
        minios_ext_mock.assert_called_once_with(
            tgt_image_file, gen.tgt_partitions[0], part_a=True
        )
        # Checks we mounted the image and read the lsb-release file correctly.
        params_mock.assert_called_once_with(tgt_image_file)
        # Make sure the tgt_image_file variable is set to None so no one can use
        # it again.
        self.assertIsNone(gen.tgt_image_file)

    def testPreparePartitionsMiniOSDelta(self):
        """Tests _PreparePartitions function for only the MiniOS partition.

        This test is for delta payloads only.
        """
        gen = self._GetStdGenerator(
            payload=self.delta_payload, work_dir=self.tempdir, minios=True
        )
        # Mock out needed functions.
        self.PatchObject(
            partition_lib,
            "LookupImageType",
            return_value=partition_lib.CROS_IMAGE,
        )
        self.PatchObject(
            gen, "_GetPlatformImageParams", return_value=("foo-appid", "6")
        )

        minios_ext_mock = self.PatchObject(partition_lib, "ExtractMiniOS")

        gen._PreparePartitions()
        # Check extract partition functions are called correctly. Two times each
        # partition once for source partition and once for target partition.
        self.assertEqual(minios_ext_mock.call_count, 2)

    def _TestGetDlcImageParams(self, tgt_id, tgt_package):
        """Utility function for Testing _GetDlcImageParams."""
        payload = self.full_dlc_payload
        tgt_image = self.new_dlc_image
        tgt_image.dlc_id = tgt_id
        tgt_image.dlc_package = tgt_package

        gen = self._GetStdGenerator(payload=payload, work_dir=self.tempdir)
        self.PatchObject(osutils, "MountDir")
        self.PatchObject(osutils, "UmountDir")
        lsb_read_mock = self.PatchObject(
            utils,
            "ReadLsbRelease",
            return_value={
                dlc_lib.DLC_APPID_KEY: "foo-appid",
                dlc_lib.DLC_ID_KEY: "sample-dlc",
                dlc_lib.DLC_PACKAGE_KEY: "sample-package",
            },
        )

        dlc_id, dlc_package, dlc_appid = gen._GetDlcImageParams(tgt_image)

        self.assertEqual(dlc_id, "sample-dlc")
        self.assertEqual(dlc_package, "sample-package")
        self.assertEqual(dlc_appid, "foo-appid")
        lsb_read_mock.assert_called_once()

    def testGetDlcImageParamsCorrect(self):
        """Tests _GetDlcImageParams function."""
        self._TestGetDlcImageParams("sample-dlc", "sample-package")

    def testGetDlcImageParamsMismatchId(self):
        """Tests _GetDlcImageParams function with mismatched DLC ID."""
        with self.assertRaises(paygen_payload_lib.Error):
            self._TestGetDlcImageParams("sample-dlc2", "sample-package")

    def testGetDlcImageParamsMismatchPackage(self):
        """Tests _GetDlcImageParams function with mismatched DLC package."""
        with self.assertRaises(paygen_payload_lib.Error):
            self._TestGetDlcImageParams("sample-dlc", "sample-package2")

    def testGenerateUnsignedPayloadFull(self):
        """Test _GenerateUnsignedPayload with full payload."""
        gen = self._GetStdGenerator(
            payload=self.full_payload, work_dir=self.tempdir
        )
        osutils.WriteFile(gen._postinst_config_file, "Fake postinst content")

        # Stub out the required functions.
        run_mock = self.PatchObject(gen, "_RunGeneratorCmd")

        # Run the test.
        gen._GenerateUnsignedPayload()

        # Check the expected function calls.
        cmd = [
            "delta_generator",
            "--major_version=2",
            "--out_file=" + gen.payload_file,
            "--partition_names=" + ":".join(gen.partition_names),
            "--new_partitions=" + ":".join(gen.tgt_partitions),
            "--new_postinstall_config_file=" + gen._postinst_config_file,
        ]
        run_mock.assert_called_once_with(cmd, squawk_wrap=True)

    def testGenerateUnsignedPayloadDelta(self):
        """Test _GenerateUnsignedPayload with delta payload."""
        gen = self._GetStdGenerator(
            payload=self.delta_payload, work_dir=self.tempdir
        )

        # Stub out the required functions.
        run_mock = self.PatchObject(gen, "_RunGeneratorCmd")

        # Run the test.
        gen._GenerateUnsignedPayload()

        # Check the expected function calls.
        cmd = [
            "delta_generator",
            "--major_version=2",
            "--out_file=" + gen.payload_file,
            "--partition_names=" + ":".join(gen.partition_names),
            "--new_partitions=" + ":".join(gen.tgt_partitions),
            "--old_partitions=" + ":".join(gen.src_partitions),
        ]
        run_mock.assert_called_once_with(cmd, squawk_wrap=True)

    def testGenerateUnsignedPayloadMiniOSDelta(self):
        """Test _GenerateUnsignedPayload with MiniOS delta payload."""
        gen = self._GetStdGenerator(
            payload=self.delta_payload, work_dir=self.tempdir, minios=True
        )

        # Stub out the required functions.
        run_mock = self.PatchObject(gen, "_RunGeneratorCmd")
        self.PatchObject(
            gen,
            "_GetPlatformImageParams",
            return_value=("foo-appid_minios", "6"),
        )

        # Run the test.
        _, gen._minor_version = gen._GetPlatformImageParams(gen.tgt_image_file)
        gen._GenerateUnsignedPayload()

        # Check the expected function calls.
        cmd = [
            "delta_generator",
            "--major_version=2",
            "--out_file=" + gen.payload_file,
            "--partition_names=" + ":".join(gen.partition_names),
            "--new_partitions=" + ":".join(gen.tgt_partitions),
            "--old_partitions=" + ":".join(gen.src_partitions),
            "--minor_version=" + gen._minor_version,
        ]

        run_mock.assert_called_once_with(cmd, squawk_wrap=True)

    def testGenerateHashes(self):
        """Test _GenerateHashes."""
        gen = self._GetStdGenerator()

        # Stub out the required functions.
        run_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_RunGeneratorCmd"
        )
        osutils.WriteFile(gen.payload_hash_file, "payload")
        osutils.WriteFile(gen.metadata_hash_file, "hash")

        # Run the test.
        self.assertEqual(gen._GenerateHashes(), (b"payload", b"hash"))

        # Check the expected function calls.
        cmd = [
            "delta_generator",
            "--in_file=" + gen.payload_file,
            "--signature_size=256",
            partial_mock.HasString("--out_hash_file="),
            partial_mock.HasString("--out_metadata_hash_file="),
        ]
        run_mock.assert_called_once_with(cmd)

    def testSignHashes(self):
        """Test _SignHashes."""
        hashes = (b"foo", b"bar")
        signatures = ((b"0" * 256,), (b"1" * 256,))

        gen = self._GetStdGenerator(work_dir="/work")

        # Stub out the required functions.
        hash_mock = self.PatchObject(
            paygen_payload_lib.PaygenSigner,
            "GetHashSignatures",
            return_value=signatures,
        )

        # Run the test.
        self.assertEqual(gen._SignHashes(hashes), signatures)

        # Check the expected function calls.
        hash_mock.assert_called_once_with(
            hashes, keysets=gen.PAYLOAD_SIGNATURE_KEYSETS
        )

    def testWriteSignaturesToFile(self):
        """Test writing signatures into files."""
        gen = self._GetStdGenerator(payload=self.delta_payload)
        signatures = (b"0" * 256, b"1" * 256)

        file_paths = gen._WriteSignaturesToFile(signatures)
        self.assertEqual(len(file_paths), len(signatures))
        self.assertExists(file_paths[0])
        self.assertExists(file_paths[1])
        self.assertEqual(
            osutils.ReadFile(file_paths[0], mode="rb"), signatures[0]
        )
        self.assertEqual(
            osutils.ReadFile(file_paths[1], mode="rb"), signatures[1]
        )

    def testInsertSignaturesIntoPayload(self):
        """Test inserting payload and metadata signatures."""
        gen = self._GetStdGenerator(payload=self.delta_payload)
        payload_signatures = (b"0" * 256,)
        metadata_signatures = (b"0" * 256,)

        # Stub out the required functions.
        run_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_RunGeneratorCmd"
        )

        # Run the test.
        gen._InsertSignaturesIntoPayload(
            payload_signatures, metadata_signatures
        )

        # Check the expected function calls.
        cmd = [
            "delta_generator",
            "--in_file=" + gen.payload_file,
            "--signature_size=256",
            partial_mock.HasString("payload_signature_file"),
            partial_mock.HasString("metadata_signature_file"),
            "--out_file=" + gen.signed_payload_file,
        ]
        run_mock.assert_called_once_with(cmd)

    def testStoreMetadataSignatures(self):
        """Test how we store metadata signatures."""
        gen = self._GetStdGenerator(payload=self.delta_payload)
        metadata_signatures = (b"1" * 256,)
        encoded_metadata_signature = (
            "MTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMT"
            "ExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTEx"
            "MTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMT"
            "ExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTEx"
            "MTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMT"
            "ExMTExMTExMQ=="
        )

        gen._StoreMetadataSignatures(metadata_signatures)

        self.assertEqual(
            osutils.ReadFile(gen.metadata_signature_file),
            encoded_metadata_signature,
        )

    def testVerifyPayloadDelta(self):
        """Test _VerifyPayload with delta payload."""
        gen = self._GetStdGenerator(
            payload=self.delta_test_payload, work_dir="/work"
        )

        # Stub out the required functions.
        run_mock = self.PatchObject(gen, "_RunGeneratorCmd")
        gen.metadata_size = 10

        # Run the test.
        gen._VerifyPayload()

        # Check the expected function calls.
        cmd = [
            "check_update_payload",
            gen.signed_payload_file,
            "--check",
            "--type",
            "delta",
            "--disabled_tests",
            "move-same-src-dst-block",
            "--part_names",
            "foo-root",
            "foo-kernel",
            "--dst_part_paths",
            "/work/tgt_root.bin",
            "/work/tgt_kernel.bin",
            "--meta-sig",
            gen.metadata_signature_file,
            "--metadata-size",
            "10",
            "--src_part_paths",
            "/work/src_root.bin",
            "/work/src_kernel.bin",
        ]
        run_mock.assert_called_once_with(cmd)

    def testVerifyPayloadFull(self):
        """Test _VerifyPayload with Full payload."""
        gen = self._GetStdGenerator(
            payload=self.full_test_payload, work_dir="/work"
        )

        # Stub out the required functions.
        run_mock = self.PatchObject(gen, "_RunGeneratorCmd")
        gen.metadata_size = 10

        # Run the test.
        gen._VerifyPayload()

        # Check the expected function calls.
        cmd = [
            "check_update_payload",
            gen.signed_payload_file,
            "--check",
            "--type",
            "full",
            "--disabled_tests",
            "move-same-src-dst-block",
            "--part_names",
            "foo-root",
            "foo-kernel",
            "--dst_part_paths",
            "/work/tgt_root.bin",
            "/work/tgt_kernel.bin",
            "--meta-sig",
            gen.metadata_signature_file,
            "--metadata-size",
            "10",
        ]
        run_mock.assert_called_once_with(cmd)

    def testVerifyPayloadPublicKey(self):
        """Test _VerifyPayload with delta payload."""
        payload = self.full_test_payload
        payload.build.bucket = "gs://chromeos-release-test"
        gen = self._GetStdGenerator(payload=payload, work_dir="/work")

        # Stub out the required functions.
        run_mock = self.PatchObject(gen, "_RunGeneratorCmd")
        gen.metadata_size = 10
        public_key = os.path.join("/work/public_key.pem")
        gen.signer.public_key = public_key

        # Run the test.
        gen._VerifyPayload()

        # Check the expected function calls.
        cmd = [mock.ANY] * 17
        cmd.extend(["--key", public_key])
        run_mock.assert_called_once_with(cmd)

    def testSignPayload(self):
        """Test the overall payload signature process."""
        payload_hash = b"payload_hash"
        metadata_hash = b"metadata_hash"
        payload_sigs = [b"payload_sig"]
        metadata_sigs = [b"metadata_sig"]

        gen = self._GetStdGenerator(
            payload=self.delta_payload, work_dir="/work"
        )

        # Set up stubs.
        gen_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload,
            "_GenerateHashes",
            return_value=(payload_hash, metadata_hash),
        )
        sign_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload,
            "_SignHashes",
            return_value=[payload_sigs, metadata_sigs],
        )

        ins_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_InsertSignaturesIntoPayload"
        )
        store_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_StoreMetadataSignatures"
        )

        # Run the test.
        result_payload_sigs, result_metadata_sigs = gen._SignPayload()

        self.assertEqual(payload_sigs, result_payload_sigs)
        self.assertEqual(metadata_sigs, result_metadata_sigs)

        # Check expected calls.
        gen_mock.assert_called_once_with()
        sign_mock.assert_called_once_with([payload_hash, metadata_hash])
        ins_mock.assert_called_once_with(payload_sigs, metadata_sigs)
        store_mock.assert_called_once_with(metadata_sigs)

    def testCreateSignedDelta(self):
        """Test the overall payload generation process."""
        payload = self.delta_payload
        gen = self._GetStdGenerator(payload=payload, work_dir="/work")

        # Set up stubs.
        prep_image_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_PrepareImage"
        )
        prep_part_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_PreparePartitions"
        )
        gen_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_GenerateUnsignedPayload"
        )
        sign_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload,
            "_SignPayload",
            return_value=(["payload_sigs"], ["metadata_sigs"]),
        )
        store_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_StorePayloadJson"
        )

        # Run the test.
        gen._Create()

        # Check expected calls.
        self.assertEqual(
            prep_image_mock.call_args_list,
            [
                mock.call(payload.tgt_image, gen.tgt_image_file),
                mock.call(payload.src_image, gen.src_image_file),
            ],
        )
        gen_mock.assert_called_once_with()
        sign_mock.assert_called_once_with()
        store_mock.assert_called_once_with(["metadata_sigs"])
        prep_part_mock.assert_called_once()

    def testCreateSignedMiniOSFullWithoutMiniOSPartition(self):
        """Test the overall payload generation process with miniOS."""
        payload = self.full_minios_payload
        gen = self._GetStdGenerator(payload=payload, work_dir="/work")

        # Set up stubs.
        prep_image_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_PrepareImage"
        )
        check_minios_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload,
            "_CheckEitherImageIsMissingMiniOSPayload",
        )
        check_minios_mock.side_effect = (
            paygen_payload_lib.NoMiniOSPartitionException
        )

        # Run the test.
        with self.assertRaises(paygen_payload_lib.NoMiniOSPartitionException):
            gen.Run()

        # Check expected calls.
        self.assertEqual(
            prep_image_mock.call_args_list,
            [
                mock.call(payload.tgt_image, gen.tgt_image_file),
            ],
        )
        check_minios_mock.assert_called_once_with()

    def testCreateSignedMiniOSFullWithMiniOSPartitionMismatch(self):
        """Test the overall payload generation process with miniOS."""
        payload = self.full_minios_payload
        gen = self._GetStdGenerator(payload=payload, work_dir="/work")

        # Set up stubs.
        prep_image_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_PrepareImage"
        )
        check_minios_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload,
            "_CheckEitherImageIsMissingMiniOSPayload",
        )
        check_minios_mock.side_effect = (
            paygen_payload_lib.MiniOSPartitionMismatchException
        )

        # Run the test.
        with self.assertRaises(
            paygen_payload_lib.MiniOSPartitionMismatchException
        ):
            gen.Run()

        # Check expected calls.
        self.assertEqual(
            prep_image_mock.call_args_list,
            [
                mock.call(payload.tgt_image, gen.tgt_image_file),
            ],
        )
        check_minios_mock.assert_called_once_with()

    def testCreateSignedMiniOSFullWithMiniOSPartition(self):
        """Test the overall payload generation process with miniOS."""
        payload = self.full_minios_payload
        gen = self._GetStdGenerator(payload=payload, work_dir="/work")

        # Set up stubs.
        prep_image_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_PrepareImage"
        )
        check_minios_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload,
            "_CheckEitherImageIsMissingMiniOSPayload",
        )
        prep_part_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_PreparePartitions"
        )
        gen_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_GenerateUnsignedPayload"
        )
        sign_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload,
            "_SignPayload",
            return_value=(["payload_sigs"], ["metadata_sigs"]),
        )
        store_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_StorePayloadJson"
        )

        # Run the test.
        gen._Create()

        # Check expected calls.
        self.assertEqual(
            prep_image_mock.call_args_list,
            [
                mock.call(payload.tgt_image, gen.tgt_image_file),
            ],
        )
        check_minios_mock.assert_called_once_with()
        gen_mock.assert_called_once_with()
        sign_mock.assert_called_once_with()
        store_mock.assert_called_once_with(["metadata_sigs"])
        prep_part_mock.assert_called_once()

    def testUploadResults(self):
        """Test the overall payload generation process."""
        gen_sign = self._GetStdGenerator(work_dir="/work", sign=True)
        gen_nosign = self._GetStdGenerator(work_dir="/work", sign=False)

        # Set up stubs.
        copy_mock = self.PatchObject(urilib, "Copy")

        # Run the test.
        gen_sign._UploadResults()
        gen_nosign._UploadResults()

        self.assertEqual(
            copy_mock.call_args_list,
            [
                # Check signed calls.
                mock.call("/work/delta.bin.signed", "gs://full_old_foo/boo"),
                mock.call("/work/delta.log", "gs://full_old_foo/boo.log"),
                mock.call("/work/delta.json", "gs://full_old_foo/boo.json"),
                # Check unsigned calls.
                mock.call("/work/delta.bin", "gs://full_old_foo/boo"),
                mock.call("/work/delta.log", "gs://full_old_foo/boo.log"),
                mock.call("/work/delta.json", "gs://full_old_foo/boo.json"),
            ],
        )

    def testUploadResultsNonStatic(self):
        """Test the overall payload generation process."""
        gen_sign = self._GetStdGenerator(
            work_dir="/work", sign=True, static=False
        )
        gen_nosign = self._GetStdGenerator(
            work_dir="/work", sign=False, static=False
        )

        # Set up stubs.
        copy_mock = self.PatchObject(urilib, "Copy")

        # Run the test.
        gen_sign._UploadResults()
        gen_nosign._UploadResults()

        self.assertEqual(
            copy_mock.call_args_list,
            [
                # Check signed calls.
                mock.call(
                    "/work/delta-<random1>.bin.signed",
                    "gs://full_old_foo/boo-<random3>",
                ),
                mock.call(
                    "/work/delta-<random1>.log",
                    "gs://full_old_foo/boo-<random3>.log",
                ),
                mock.call(
                    "/work/delta-<random1>.json",
                    "gs://full_old_foo/boo-<random3>.json",
                ),
                # Check unsigned calls.
                mock.call(
                    "/work/delta-<random2>.bin",
                    "gs://full_old_foo/boo-<random4>",
                ),
                mock.call(
                    "/work/delta-<random2>.log",
                    "gs://full_old_foo/boo-<random4>.log",
                ),
                mock.call(
                    "/work/delta-<random2>.json",
                    "gs://full_old_foo/boo-<random4>.json",
                ),
            ],
        )

    def testUploadResultsForMiniOS(self):
        """Test the overall payload generation process."""
        gen_sign = self._GetStdGenerator(
            work_dir="/work", sign=True, minios=True
        )
        gen_nosign = self._GetStdGenerator(
            work_dir="/work", sign=False, minios=True
        )

        # Set up stubs.
        copy_mock = self.PatchObject(urilib, "Copy")

        # Run the test.
        gen_sign._UploadResults()
        gen_nosign._UploadResults()

        self.assertEqual(
            copy_mock.call_args_list,
            [
                # Check signed calls.
                mock.call(
                    "/work/delta-<random1>.bin.signed",
                    "gs://full_old_foo/boo-<random3>",
                ),
                mock.call(
                    "/work/delta-<random1>.log",
                    "gs://full_old_foo/boo-<random3>.log",
                ),
                mock.call(
                    "/work/delta-<random1>.json",
                    "gs://full_old_foo/boo-<random3>.json",
                ),
                # Check unsigned calls.
                mock.call(
                    "/work/delta-<random2>.bin",
                    "gs://full_old_foo/boo-<random4>",
                ),
                mock.call(
                    "/work/delta-<random2>.log",
                    "gs://full_old_foo/boo-<random4>.log",
                ),
                mock.call(
                    "/work/delta-<random2>.json",
                    "gs://full_old_foo/boo-<random4>.json",
                ),
            ],
        )

    def testFindCacheDir(self):
        """Test calculating the location of the cache directory."""
        gen = self._GetStdGenerator(work_dir="/foo")

        # The correct result is based on the system cache directory, which
        # changes. Ensure it ends with the right directory name.
        self.assertEqual(os.path.basename(gen._FindCacheDir()), "paygen_cache")

    def testGetPayloadPropertiesMap(self):
        """Tests getting the payload properties as a dict."""
        gen = self._GetStdGenerator(sign=False)
        gen._appid = "foo-appid"
        run_mock = self.PatchObject(gen, "_RunGeneratorCmd")

        props_file = os.path.join(self.tempdir, "properties.json")
        osutils.WriteFile(
            props_file,
            json.dumps({"metadata_signature": "", "metadata_size": 10}),
        )
        payload_path = "/foo"
        props_map = gen.GetPayloadPropertiesMap(payload_path)

        cmd = [
            "delta_generator",
            "--in_file=" + payload_path,
            "--properties_file=" + props_file,
            "--properties_format=json",
        ]
        run_mock.assert_called_once_with(cmd)
        self.assertEqual(
            props_map,
            # This tests that if metadata_signature is empty, the code
            # converts it to None.
            {
                "metadata_signature": None,
                "metadata_size": 10,
                "appid": "foo-appid",
                "target_version": "1620.0.0",
            },
        )

    def testGetDeltaPayloadPropertiesMap(self):
        """Tests getting the delta payload properties as a dict."""
        gen = self._GetStdGenerator(sign=False, payload=self.delta_payload)
        gen._appid = "foo-appid"
        run_mock = self.PatchObject(gen, "_RunGeneratorCmd")

        props_file = os.path.join(self.tempdir, "properties.json")
        osutils.WriteFile(
            props_file,
            json.dumps({"metadata_signature": "", "metadata_size": 10}),
        )
        payload_path = "/foo"
        props_map = gen.GetPayloadPropertiesMap(payload_path)

        cmd = [
            "delta_generator",
            "--in_file=" + payload_path,
            "--properties_file=" + props_file,
            "--properties_format=json",
        ]
        run_mock.assert_called_once_with(cmd)
        self.assertEqual(
            props_map,
            # This tests that if metadata_signature is empty, the code
            # converts it to None.
            {
                "metadata_signature": None,
                "metadata_size": 10,
                "appid": "foo-appid",
                "target_version": "4171.0.0",
                "source_version": "1620.0.0",
            },
        )

    def testGetPayloadPropertiesMapSigned(self):
        """Test getting the payload properties as a dict for signed payloads."""
        gen = self._GetStdGenerator()

        props_file = os.path.join(self.tempdir, "properties.json")
        osutils.WriteFile(
            props_file,
            json.dumps({"metadata_signature": "foo-sig", "metadata_size": 10}),
        )
        gen.signer.public_key = os.path.join(self.tempdir, "public_key.pem")
        osutils.WriteFile(gen.signer.public_key, "foo-pubkey")

        payload_path = "/foo"
        props_map = gen.GetPayloadPropertiesMap(payload_path)
        self.assertEqual(
            props_map,
            {
                "metadata_signature": "foo-sig",
                "metadata_size": 10,
                # This tests that appid key is always added to the
                # properties file even if it is empty.
                "appid": "",
                # This is the base64 encode of 'foo-pubkey'.
                "public_key": "Zm9vLXB1YmtleQ==",
                "target_version": "1620.0.0",
            },
        )


class GenerateUpdatePayloadTest(PaygenLibTest):
    """Tests for GenerateUpdatePayload."""

    def testGenerateUpdatePayload(self):
        self.PatchObject(
            partition_lib,
            "LookupImageType",
            return_value=partition_lib.CROS_IMAGE,
        )
        prep_image_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_PrepareImage"
        )
        prep_part_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_PreparePartitions"
        )
        gen_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_GenerateUnsignedPayload"
        )
        sign_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload,
            "_SignPayload",
            return_value=(["payload_sigs"], ["metadata_sigs"]),
        )
        store_mock = self.PatchObject(
            paygen_payload_lib.PaygenPayload, "_StorePayloadJson"
        )

        result_paths = paygen_payload_lib.GenerateUpdatePayload(
            chroot=chroot_lib.Chroot(),
            tgt_image=str(self.full_minios_payload.uri),
            payload=str(self.full_payload.uri),
            src_image=None,
            work_dir=self.tempdir,
            minios=True,
        )

        # Check expected calls.
        self.assertEqual(
            prep_image_mock.call_args_list,
            [
                mock.call(mock.ANY, mock.ANY),
                mock.call(mock.ANY, mock.ANY),
            ],
        )
        self.assertEqual(
            prep_part_mock.call_args_list,
            [
                mock.call(True),
                mock.call(False),
            ],
        )
        self.assertEqual(gen_mock.call_args_list, mock.call(), mock.call())
        self.assertEqual(sign_mock.call_args_list, mock.call(), mock.call())
        self.assertEqual(
            store_mock.call_args_list,
            [
                mock.call(["metadata_sigs"]),
                mock.call(["metadata_sigs"]),
            ],
        )

        self.assertEqual(
            result_paths,
            [
                str(self.full_payload.uri) + "-<random3>",
                str(self.full_payload.uri) + "-<random5>",
            ],
        )
