# Copyright 2013 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for paygen_build_lib."""

from chromite.lib import cros_test_lib
from chromite.lib.paygen import gspaths
from chromite.lib.paygen import paygen_build_lib


class BasePaygenBuildLibTestWithBuilds(cros_test_lib.MockTempDirTestCase):
    """Test PaygenBuildLib class."""

    def setUp(self):
        self.dlc_id = "sample-dlc"
        self.dlc_id2 = "sample-dlc2"
        self.dlc_package = "sample-package"
        self.dlc_package2 = "sample-package2"

        self.prev_build = gspaths.Build(
            bucket="crt",
            channel="foo-channel",
            board="foo-board",
            version="1.0.0",
        )

        self.prev_image = gspaths.Image(build=self.prev_build, key="mp")
        self.prev_premp_image = gspaths.Image(
            build=self.prev_build, key="premp"
        )
        self.prev_test_image = gspaths.UnsignedImageArchive(
            build=self.prev_build, image_type="test"
        )
        self.prev_dlc_package_image = gspaths.DLCImage(
            build=self.prev_build,
            key=None,
            dlc_id=self.dlc_id,
            dlc_package=self.dlc_package,
            dlc_image=gspaths.ChromeosReleases.DLCImageName(),
        )
        self.prev_dlc_package2_image = gspaths.DLCImage(
            build=self.prev_build,
            key=None,
            dlc_id=self.dlc_id,
            dlc_package=self.dlc_package2,
            dlc_image=gspaths.ChromeosReleases.DLCImageName(),
        )
        self.prev_dlc2_image = gspaths.DLCImage(
            build=self.prev_build,
            key=None,
            dlc_id=self.dlc_id2,
            dlc_package=self.dlc_package,
            dlc_image=gspaths.ChromeosReleases.DLCImageName(),
        )

        self.target_build = gspaths.Build(
            bucket="crt",
            channel="foo-channel",
            board="foo-board",
            version="1.2.3",
        )

        # Create an additional 'special' image like NPO that isn't NPO,
        # and keyed with a weird key. It should match none of the filters.
        self.special_image = gspaths.Image(
            build=self.target_build,
            key="foo-key",
            image_channel="special-channel",
        )

        self.basic_image = gspaths.Image(build=self.target_build, key="mp-v2")
        self.premp_image = gspaths.Image(build=self.target_build, key="premp")
        self.test_image = gspaths.UnsignedImageArchive(
            build=self.target_build, image_type="test"
        )
        self.dlc_image = gspaths.DLCImage(
            build=self.target_build,
            key=None,
            dlc_id=self.dlc_id,
            dlc_package=self.dlc_package,
            dlc_image=gspaths.ChromeosReleases.DLCImageName(),
        )

        self.mp_full_payload = gspaths.Payload(tgt_image=self.basic_image)
        self.test_full_payload = gspaths.Payload(tgt_image=self.test_image)
        self.mp_delta_payload = gspaths.Payload(
            tgt_image=self.basic_image, src_image=self.prev_image
        )
        self.test_delta_payload = gspaths.Payload(
            tgt_image=self.test_image, src_image=self.prev_test_image
        )
        self.minios_full_payload = gspaths.Payload(
            tgt_image=self.basic_image, minios=True
        )

    def testDefaultPayloadUri(self):
        """Test paygen_payload_lib.DefaultPayloadUri."""

        # Test a Full Payload
        result = paygen_build_lib.DefaultPayloadUri(
            self.mp_full_payload, random_str="abc123"
        )
        self.assertEqual(
            result,
            "gs://crt/foo-channel/foo-board/1.2.3/payloads/"
            "chromeos_1.2.3_foo-board_foo-channel_full_mp-v2.bin-abc123.signed",
        )

        # Test a Delta Payload
        result = paygen_build_lib.DefaultPayloadUri(
            self.mp_delta_payload, random_str="abc123"
        )
        self.assertEqual(
            result,
            "gs://crt/foo-channel/foo-board/1.2.3/payloads/chromeos_1.0.0-1"
            ".2.3_foo-board_foo-channel_delta_mp-v2.bin-abc123.signed",
        )

        # Test changing channel, board, and keys
        src_image = gspaths.Image(
            build=gspaths.Build(
                channel="dev-channel",
                board="x86-alex",
                version="3588.0.0",
                bucket="crt",
            ),
            key="premp",
        )
        tgt_image = gspaths.Image(
            build=gspaths.Build(
                channel="stable-channel",
                board="x86-alex-he",
                version="3590.0.0",
                bucket="crt",
            ),
            key="mp-v3",
        )
        payload = gspaths.Payload(src_image=src_image, tgt_image=tgt_image)

        result = paygen_build_lib.DefaultPayloadUri(
            payload, random_str="abc123"
        )
        self.assertEqual(
            result,
            "gs://crt/stable-channel/x86-alex-he/3590.0.0/payloads/"
            "chromeos_3588.0.0-3590.0.0_x86-alex-he_stable-channel_delta_mp-v3"
            ".bin-abc123.signed",
        )
