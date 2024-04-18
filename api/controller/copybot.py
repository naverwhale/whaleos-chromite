# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Copybot Controller.

Handles the endpoint for running copybot and generating the protobuf.
"""

from pathlib import Path
import tempfile

from chromite.third_party.google.protobuf import json_format

from chromite.api import controller
from chromite.api import faux
from chromite.api import validate
from chromite.api.gen.chromite.api import copybot_pb2
from chromite.lib import constants
from chromite.lib import cros_build_lib


def _MockSuccess(_input_proto, _output_proto, _config_proto):
    """Mock success output for the RunCopybot endpoint."""

    # Successful response is the default protobuf, so no need to fill it out.


@faux.success(_MockSuccess)
@faux.empty_error
@validate.validation_complete
def RunCopybot(input_proto, output_proto, _config_proto):
    """Run copybot. Translate all fields in the input protobuf to CLI args."""

    cmd = [
        constants.SOURCE_ROOT / "src/platform/dev/contrib/copybot/copybot.py"
    ]

    if input_proto.topic:
        cmd.extend(["--topic", input_proto.topic])

    for label in input_proto.labels:
        cmd.extend(["--label", label.label])

    for reviewer in input_proto.reviewers:
        cmd.extend(["--re", reviewer.user])

    for cc in input_proto.ccs:
        cmd.extend(["--cc", cc.user])

    if input_proto.prepend_subject:
        cmd.extend(["--prepend-subject", input_proto.prepend_subject])

    if (
        input_proto.merge_conflict_behavior
        == copybot_pb2.RunCopybotRequest.MERGE_CONFLICT_BEHAVIOR_SKIP
    ):
        cmd.extend(["--merge-conflict-behavior", "SKIP"])

    if (
        input_proto.merge_conflict_behavior
        == copybot_pb2.RunCopybotRequest.MERGE_CONFLICT_BEHAVIOR_FAIL
    ):
        cmd.extend(["--merge-conflict-behavior", "FAIL"])

    for exclude in input_proto.exclude_file_patterns:
        cmd.extend(["--exclude-file-pattern", exclude.pattern])

    for ph in input_proto.keep_pseudoheaders:
        cmd.extend(["--keep-pseudoheader", ph.name])

    if input_proto.add_signed_off_by:
        cmd.append("--add-signed-off-by")

    if input_proto.dry_run:
        cmd.append("--dry-run")

    for po in input_proto.push_options:
        cmd.extend(["--push-option", po.opt])

    cmd.append(f"{input_proto.upstream.url}:{input_proto.upstream.branch}")
    cmd.append(f"{input_proto.downstream.url}:{input_proto.downstream.branch}")

    with tempfile.TemporaryDirectory() as temp_dir:
        json_output_path = Path(temp_dir) / "copybot_output.json"
        cmd.extend(["--json-out", json_output_path])

        try:
            cros_build_lib.run(cmd)
        except cros_build_lib.RunCommandError:
            # In case of failure, load details about the error from CopyBot's
            # JSON output into the output protobuf. (If CopyBot ran
            # successfully, the default values are simply used). CopyBot's
            # output matches the JSON representation of the RunCopybotResponse
            # protobuf.

            if not json_output_path.exists():
                return controller.RETURN_CODE_UNRECOVERABLE

            json_format.Parse(json_output_path.read_text(), output_proto)
            return controller.RETURN_CODE_UNSUCCESSFUL_RESPONSE_AVAILABLE
