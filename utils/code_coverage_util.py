# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for working with code coverage files."""

import json
import logging
import os

from chromite.lib import osutils


def GetLlvmJsonCoverageDataIfValid(path_to_file: str):
  """Gets the content of a file if it matches the llvm coverage json format.

  Args:
    path_to_file: The path of the file to read.

  Returns:
    The file contents if they match the llvm json structure, otherwise None.
  """
  try:
    # Only coverage.json files matter for llvm json coverage.
    if os.path.basename(path_to_file) != 'coverage.json':
      return None

    # Make sure the file exists.
    if not os.path.isfile(path_to_file):
      return None

    # Attempt to parse as json. It's fine for this to fail,
    # it means we can't manipulate it rather than an actual error.
    data = json.loads(osutils.ReadFile(path_to_file))

    # Validate the file structure is:
    # { data: [...], type: "..", version: "..." }.
    if 'data' not in data or 'type' not in data or 'version' not in data:
      return None

    if data['type'] != 'llvm.coverage.json.export':
      return None

    return data
  except Exception as e:
    logging.warning('GetLlvmJsonCoverageDataIfValid failed %s', e)
    return None
