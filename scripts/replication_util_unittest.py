# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for replication_util."""

import json
import os

from chromite.third_party.google.protobuf import json_format

from chromite.api.gen.config import replication_config_pb2
from chromite.lib import constants
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.scripts import replication_util


D = cros_test_lib.Directory
FILE_TYPE_OTHER = replication_config_pb2.FILE_TYPE_OTHER
FileReplicationRule = replication_config_pb2.FileReplicationRule
REPLICATION_TYPE_COPY = replication_config_pb2.REPLICATION_TYPE_COPY
ReplicationConfig = replication_config_pb2.ReplicationConfig


class RunTest(cros_test_lib.MockTempDirTestCase):
    """Tests of the run command.

    Note that detailed tests of replication behavior should be done in
    replication_lib_unittest.
    """

    def setUp(self):
        file_layout = (D("src", ["audio_file"]),)
        cros_test_lib.CreateOnDiskHierarchy(self.tempdir, file_layout)

        self.audio_path = os.path.join("src", "audio_file")
        self.WriteTempFile(self.audio_path, "[Speaker A Settings]")

        self.PatchObject(constants, "SOURCE_ROOT", new=self.tempdir)

    def testRun(self):
        """Basic test of the 'run' command."""
        audio_dst_path = os.path.join("dst", "audio_file")

        replication_config = ReplicationConfig(
            file_replication_rules=[
                FileReplicationRule(
                    source_path=self.audio_path,
                    destination_path=audio_dst_path,
                    file_type=FILE_TYPE_OTHER,
                    replication_type=REPLICATION_TYPE_COPY,
                ),
            ]
        )

        replication_config_path = os.path.join(
            self.tempdir, "replication_config.jsonpb"
        )
        osutils.WriteFile(
            replication_config_path,
            json_format.MessageToJson(replication_config),
        )

        replication_util.main(["run", replication_config_path])

        expected_file_layout = (
            D("src", ["audio_file"]),
            D("dst", ["audio_file"]),
            "replication_config.jsonpb",
        )

        cros_test_lib.VerifyOnDiskHierarchy(self.tempdir, expected_file_layout)

        self.assertTempFileContents(audio_dst_path, "[Speaker A Settings]")

    def testUnknownFieldInConfig(self):
        """Test that unknown fields in the ReplicationConfig cause an error."""
        audio_dst_path = os.path.join("dst", "audio_file")

        replication_config = ReplicationConfig(
            file_replication_rules=[
                FileReplicationRule(
                    source_path=self.audio_path,
                    destination_path=audio_dst_path,
                    file_type=FILE_TYPE_OTHER,
                    replication_type=REPLICATION_TYPE_COPY,
                ),
            ]
        )

        replication_config_path = os.path.join(
            self.tempdir, "replication_config.jsonpb"
        )
        replication_config_dict = json_format.MessageToDict(replication_config)
        replication_config_dict["new_field"] = 1
        osutils.WriteFile(
            replication_config_path, json.dumps(replication_config_dict)
        )

        with self.assertRaises(json_format.ParseError):
            replication_util.main(["run", replication_config_path])
