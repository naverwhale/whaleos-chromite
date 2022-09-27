# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Volteer configs."""

import logging

from chromite.lib.firmware import servo_lib


BUILD_WORKON_PACKAGES = None

BUILD_PACKAGES = ('chromeos-bootimage',)

# TODO: Remove this line once VBoot is working on Volteer.
DEPLOY_SERVO_FORCE_FLASHROM = True


def get_config(servo: servo_lib.Servo) -> servo_lib.FirmwareConfig:
  """Get specific flash config for the Volteer.

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
  dut_control_on = [['cpu_fw_spi:on']]
  dut_control_off = [['cpu_fw_spi:off']]
  if servo.is_v2:
    programmer = 'ft2232_spi:type=google-servo-v2,serial=%s' % servo.serial
  elif servo.is_micro:
    # TODO (jacobraz): remove warning once http://b/147679336 is resolved
    logging.warning('servo_micro has not been functioning properly consider '
                    'using a different servo if this fails')
    programmer = 'raiden_debug_spi:serial=%s' % servo.serial
  elif servo.is_ccd:
    # Note nothing listed for flashing with ccd_cr50 on go/volteer-care.
    # These commands were based off the commands for other boards.
    dut_control_on = []
    dut_control_off = []
    programmer = 'raiden_debug_spi:target=AP,serial=%s' % servo.serial
  else:
    raise servo_lib.UnsupportedServoVersionError('%s not supported' %
                                                 servo.version)

  return servo_lib.FirmwareConfig(dut_control_on, dut_control_off, programmer)
