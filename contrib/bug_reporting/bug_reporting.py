# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import logging
from typing import List, Optional

from chromite.lib import cros_build_lib


BUG_TEMPLATE = (
    "https://b.corp.google.com/issues/new?component=1037860&template=1600056"
)


def parse_args():
    parser = argparse.ArgumentParser(
        prog="bug reporting",
        description=" ",
    )

    parser.add_argument("filename")
    args = vars(parser.parse_args())
    file = args["filename"]
    return file


def gcert_check():
    result = cros_build_lib.run(
        ["gcertstatus", "-format=loas2", "--quiet"], debug_level=0
    )
    return result.returncode == 0


def gpaste(file):
    result = cros_build_lib.run(
        ["/google/src/head/depot/eng/tools/pastebin", file],
        capture_output=True,
        encoding="utf-8",
        debug_level=0,
    )
    link = result.stdout
    logging.info("gpaste: %s", link)
    return link


def _add_to_bug_link(section, data):
    data = data.split(" ")
    data = "&" + section + "=" + "%20".join(data)
    return data


def get_bug_link(title: str = None, description: str = None):
    link = BUG_TEMPLATE

    if title:
        link += _add_to_bug_link("title", title)

    if description:
        link += _add_to_bug_link("description", description)

    return link


def main(argv: Optional[List[str]] = None) -> Optional[int]:
    file = parse_args()
    if not gcert_check():
        logging.error("Invalid gcert!!")
        exit(1)

    gpaste_link = gpaste(file)
    bug_link = get_bug_link(description=gpaste_link)
    logging.info("buganizer: %s", bug_link)
