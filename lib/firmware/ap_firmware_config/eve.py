# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Eve configs."""

from chromite.lib.firmware import servo_lib

BUILD_WORKON_PACKAGES = (
  'chromeos-mrc',
  'coreboot',
)

BUILD_PACKAGES = BUILD_WORKON_PACKAGES + (
  'coreboot-private-files-eve',
  'depthcharge',
  'chromeos-bootimage',
)

def get_config(servo: servo_lib.Servo) -> servo_lib.FirmwareConfig:
  """Get specific flash config for eve.

  Each board needs specific config including the voltage for Vref, to turn
  on and turn off the SPI flash. get_config() returns servo_lib.FirmwareConfig
  with settings to flash a servo for a particular build target.
  The voltage for this board needs to be set to 3.3 V.

  Args:
    servo: The servo connected to the target DUT.

  Returns:
    servo_lib.FirmwareConfig:
      dut_control_{on, off}=2d arrays formatted like [["cmd1", "arg1", "arg2"],
                                                      ["cmd2", "arg3", "arg4"]]
                            where cmd1 will be run before cmd2.
      programmer=programmer argument (-p) for flashrom and futility.
  """
  dut_control_on = []
  dut_control_off = []
  if servo.is_ccd:
    programmer = 'raiden_debug_spi:target=AP,serial=%s' % servo.serial
  else:
    raise servo_lib.UnsupportedServoVersionError('%s not supported' %
                                                 servo.version)

  return servo_lib.FirmwareConfig(dut_control_on, dut_control_off, programmer)
