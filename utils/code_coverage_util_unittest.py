# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for the code_coverage_util.py module."""

import json
import os
from chromite.lib import osutils
from chromite.lib import cros_test_lib
from chromite.utils import code_coverage_util

class GetLlvmJsonCoverageDataIfValidTest(cros_test_lib.TempDirTestCase):
  """Unit tests for GetLlvmJsonCoverageDataIfValid"""

  def testIgnoresIfFileIsNotCoverageJsonFileName(self):
    """Verify that files not named coverage.json are ignored."""
    file = os.path.join(self.tempdir, 'file.json')
    osutils.WriteFile(file, 'Test')
    result = code_coverage_util.GetLlvmJsonCoverageDataIfValid(file)
    self.assertIsNone(result)

  def testIgnoresIfNotAFile(self):
    """Verify non-files are ignored."""
    result = code_coverage_util.GetLlvmJsonCoverageDataIfValid('coverage.json')
    self.assertIsNone(result)

  def testIgnoresIfFileIsNotValidJson(self):
    """Verify files with invalid JSON are ignored."""
    file = os.path.join(self.tempdir, 'coverage.json')
    osutils.WriteFile(file, 'Test')
    result = code_coverage_util.GetLlvmJsonCoverageDataIfValid(file)
    self.assertIsNone(result)

  def testReturnsDataWhenInProperFormat(self):
    """Verify files in the right structure have their contents returned."""
    file = os.path.join(self.tempdir, 'coverage.json')
    content = json.dumps({
        'data': [
            {
                'files': [
                    {
                        'filename': 'abc'
                    }
                ]
            }
        ],
        'version': '1',
        'type': 'llvm.coverage.json.export'
    })
    osutils.WriteFile(file, content)
    result = code_coverage_util.GetLlvmJsonCoverageDataIfValid(file)
    self.assertIsNotNone(result)
