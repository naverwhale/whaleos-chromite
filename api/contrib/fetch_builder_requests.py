# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility script to fetch the requests from a builder."""

import csv
import logging
from pathlib import Path
import re

from chromite.third_party.google.protobuf import text_format

from chromite.api import message_util
from chromite.api import router
from chromite.api.gen.analysis_service import analysis_service_pb2
from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import osutils


_COLUMNS = [
    "step_name",
    "install_packages_request",
    "bundle_request",
    "bundle_vm_files_request",
    "binhost_get_request",
    "acl_args_request",
    "prepare_binhost_uploads_request",
    "set_binhost_request",
]


def _camel_to_snake(string):
    # Transform FooBARBaz into FooBAR_Baz. Avoids making Foo_B_A_R_Baz.
    sub1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", string)
    # Transform FooBAR_Baz into Foo_BAR_Baz.
    sub2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", sub1)
    # Lower case to get foo_bar_baz.
    return sub2.lower()


def _get_query(fields, build_id):
    return f"""
SELECT {','.join(fields)}
FROM
chromeos_ci_eng.analysis_event_log.all
WHERE build_id = {build_id};
"""


def GetParser():
    """Build the argument parser."""
    parser = commandline.ArgumentParser(description=__doc__)

    parser.add_argument("build_id", type=int, help="The Build Bucket Build ID.")
    parser.add_argument(
        "--raw",
        default=False,
        action="store_true",
        help="Do not do any processing of field values before writing the "
        "input.",
    )

    return parser


def _ParseArguments(argv):
    """Parse and validate arguments."""
    parser = GetParser()
    opts = parser.parse_args(argv)

    opts.Freeze()
    return opts


def main(argv):
    opts = _ParseArguments(argv)

    analysis_service = analysis_service_pb2.AnalysisServiceEvent()
    request_one_of = analysis_service.DESCRIPTOR.oneofs_by_name["request"]

    fields = ["step_name"] + [x.name for x in request_one_of.fields]
    fields.remove("test_all_firmware_request")
    result = None
    unknown_field_re = re.compile(r"Unrecognized name: (?P<unknown_field>\w+)")
    while not result:
        query = _get_query(fields, opts.build_id)
        try:
            result = cros_build_lib.run(
                ["dremel", "--min_completion_ratio", "1", "--output", "csv"],
                input=query,
                capture_output=True,
                encoding="utf-8",
            )
        except cros_build_lib.RunCommandError as e:
            m = unknown_field_re.search(str(e))
            if m and m.group("unknown_field"):
                fields.remove(m.group("unknown_field"))
            else:
                raise

    router_obj = router.Router()
    router.RegisterServices(router_obj)
    serializer = message_util.JsonSerializer()

    endpoint_re = re.compile(r"(chromite\.api\.\w+/\w+)")
    reader = csv.DictReader(result.stdout.split("\r\n"))
    for row in reader:
        # Each row will have a step_name, and all the requests, but only one
        # request will actually be populated.
        m = endpoint_re.search(row["step_name"])
        if not m:
            logging.warning("No endpoint identified in %s", row["step_name"])
            continue

        endpoint = m.groups()[0]
        request = router_obj.get_input_message_instance(*endpoint.split("/"))
        for k, v in row.items():
            if k == "step_name" or not v or v == "NULL":
                # Wrong column, or empty request.
                continue

            # Strip {} from around the message to account for extra layer of
            # nesting when the analysis service serializes it.
            text_format.Parse(v[1:-1], request)

            # Figure out which input.json needs to be written.
            method = _camel_to_snake(endpoint.split("/")[1])
            service = _camel_to_snake(
                endpoint.split("/")[0].split(".")[2].replace("Service", "")
            )
            file_name = f"{service}__{method}_input.json"

            if not opts.raw:
                # Dump chroot's directory fields since they're definitely going
                # to be builder paths that aren't usable.
                if request.HasField("chroot"):
                    request.chroot.path = ""
                    request.chroot.chrome_dir = ""
                    request.chroot.cache_dir = ""

            contrib = Path(__file__).absolute().parent
            file_location = contrib / "call_scripts" / file_name
            osutils.WriteFile(file_location, serializer.serialize(request))
            logging.notice(f"Wrote {file_name}")
            break
