# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""DLC service tests."""

from chromite.api import api_config
from chromite.api.controller import dlc as dlc_controller
from chromite.api.gen.chromite.api import dlc_pb2
from chromite.api.gen.chromite.api import sysroot_pb2
from chromite.lib import cros_test_lib
from chromite.service import image


class GenerateDlcArtifactsListTest(
    cros_test_lib.MockTempDirTestCase, api_config.ApiConfigMixin
):
    """Tests for GenerateDLcArtifactsList."""

    def setUp(self):
        self.response = dlc_pb2.GenerateDlcArtifactsListResponse()
        self.sysroot_path = "/build/target"

    def _InputProto(self):
        in_proto = dlc_pb2.GenerateDlcArtifactsListRequest(
            sysroot=sysroot_pb2.Sysroot(path=self.sysroot_path),
        )
        in_proto.chroot.path = "path"
        return in_proto

    def testNoDlcArtifacts(self):
        """Test for no artifacts being returned."""
        self.PatchObject(
            image, "generate_dlc_artifacts_metadata_list", return_value=[]
        )
        in_proto = self._InputProto()
        dlc_controller.GenerateDlcArtifactsList(
            in_proto, self.response, self.api_config
        )

        self.assertEqual(len(self.response.dlc_artifacts), 0)

    def testDlcArtifactsSuccess(self):
        """Test for successfully returning artifacts."""
        self.PatchObject(
            image,
            "generate_dlc_artifacts_metadata_list",
            return_value=[
                image.DlcArtifactsMetadata(
                    image_hash="deadbeef",
                    image_name="dlc.img",
                    uri_path="gs://some/uri/prefix/for/dlc-1",
                    identifier="dlc-1",
                )
            ],
        )
        in_proto = self._InputProto()
        dlc_controller.GenerateDlcArtifactsList(
            in_proto, self.response, self.api_config
        )

        self.assertEqual(
            self.response.dlc_artifacts[0],
            dlc_pb2.GenerateDlcArtifactsListResponse.DlcArtifact(
                image_hash="deadbeef",
                image_name="dlc.img",
                gs_uri_path="gs://some/uri/prefix/for/dlc-1",
                id="dlc-1",
            ),
        )
