# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module tests the cros dump-ap-config command."""

import json
from pathlib import Path

from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib.firmware import servo_lib


pytestmark = cros_test_lib.pytestmark_inside_only


class CrosAPDumpConfigTest(cros_test_lib.TempDirTestCase):
  """Test calling `cros ap dump-config` and doing some simple validity checking.

  Confirm that json output file is readable, contains expected structure and
  non-empty fields.
  """

  def testCrosConfigDump(self):
    """Run cros dump-ap-config, read the output, and check validity."""
    output_file = Path(self.tempdir) / 'tmp.json'
    cmd = ['cros', 'ap', 'dump-config', '-o', str(output_file)]
    cros_build_lib.run(cmd)
    with output_file.open(encoding='utf-8') as fp:
      result = json.load(fp)

    # dut_control_on, seen_dut_control_off and programmer are sometimes empty,
    # but we can expect that at least one board:servo pair will have them
    # non-empty. Assert that.
    seen_dut_control_on = False
    seen_dut_control_off = False
    seen_programmer = False

    for board, board_config in result.items():
      assert board
      for servo, configs in board_config.items():
        assert servo in servo_lib.VALID_SERVOS
        assert 'dut_control_on' in configs
        if configs['dut_control_on']:
          seen_dut_control_on = True
        assert 'dut_control_off' in configs
        if configs['dut_control_off']:
          seen_dut_control_off = True
        assert 'programmer' in configs
        if configs['programmer']:
          seen_programmer = True

    assert seen_dut_control_on
    assert seen_dut_control_off
    assert seen_programmer
