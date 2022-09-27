# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wilco configs."""

import logging

from chromite.lib.firmware import servo_lib


# TODO(b/143241417): Use futility anytime flashing over ssh to avoid failures.
DEPLOY_SSH_FORCE_FUTILITY = True


def is_fast_required(_use_futility: bool, servo: servo_lib.Servo) -> bool:
  """Returns true if --fast is necessary to flash successfully.

  The configurations in this function consistently fail on the verify step,
  adding --fast removes verification of the flash and allows these configs to
  flash properly. Meant to be a temporary hack until b/143240576 is fixed.

  Args:
    _use_futility: True if futility is to be used, False if
      flashrom.
    servo: The servo connected to the target DUT.

  Returns:
    bool: True if fast is necessary, False otherwise.
  """
  # servo_v4_with_servo_micro or servo_micro
  return servo.is_micro


def get_config(servo: servo_lib.Servo) -> servo_lib.FirmwareConfig:
  """Get specific flash config for wilco.

  Each board needs specific config including the voltage for Vref, to turn
  on and turn off the SPI flash. get_config() returns servo_lib.FirmwareConfig
  with settings to flash a servo for a particular build target.
  The voltage for this board needs to be set to 3.3 V.

  wilco care and feeding doc only lists commands for servo v2 and servo micro
  TODO: support 4 byte addressing?
  From wilco care and feeding doc:
  4 Byte Addressing

  As of 20-Aug-2019 flashrom at ToT cannot flash the 32 MB flashes that
  drallion uses. If you see an error about “4 byte addressing” run the
  following commands to get a useable flashrom

  cd ~/trunk/src/third_party/flashrom/
  git co ff7778ab25d0b343e781cffc0e45f329ee69a5a8~1
  cros_workon --host start flashrom
  sudo emerge flashrom

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
  if servo.is_v2:
    dut_control_on.append([
        'spi2_vref:pp3300', 'spi2_buf_en:on', 'spi2_buf_on_flex_en:on',
        'cold_reset:on'
    ])
    dut_control_off.append([
        'spi2_vref:off', 'spi2_buf_en:off', 'spi2_buf_on_flex_en:off',
        'cold_reset:off'
    ])
    programmer = 'ft2232_spi:type=google-servo-v2,serial=%s' % servo.serial
  elif servo.is_micro:
    dut_control_on.append(
        ['spi2_vref:pp3300', 'spi2_buf_en:on', 'cold_reset:on'])
    dut_control_off.append(
        ['spi2_vref:off', 'spi2_buf_en:off', 'cold_reset:off'])
    programmer = 'raiden_debug_spi:serial=%s' % servo.serial
  elif servo.is_ccd:
    # According to wilco care and feeding doc there is
    # NO support for CCD on wilco so this will not work.
    logging.error('wilco devices do not support ccd, cannot flash')
    logging.info('Please use a different servo with wilco devices')
    raise servo_lib.UnsupportedServoVersionError('%s not accepted' %
                                                 servo.version)
  else:
    raise servo_lib.UnsupportedServoVersionError('%s not supported' %
                                                 servo.version)

  return servo_lib.FirmwareConfig(dut_control_on, dut_control_off, programmer)
