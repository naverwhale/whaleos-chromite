# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Octopus configs."""

from chromite.lib.firmware import servo_lib

BUILD_WORKON_PACKAGES = (
    'chromeos-ec',
    'coreboot',
    'depthcharge',
    'libpayload',
    'vboot_reference',
)

BUILD_PACKAGES = BUILD_WORKON_PACKAGES + ('chromeos-bootimage',)


def is_fast_required(use_futility: bool, servo: servo_lib.Servo) -> bool:
  """Returns true if --fast is necessary to flash successfully.

  The configurations in this function consistently fail on the verify step,
  adding --fast removes verification of the flash and allows these configs to
  flash properly. Meant to be a temporary hack until b/143240576 is fixed.

  Args:
    use_futility: True if futility is to be used, False if flashrom.
    servo: The servo connected to the target DUT.

  Returns:
    bool: True if fast is necessary, False otherwise.
  """
  return use_futility and servo.version == servo_lib.SERVO_V4_CCD


def get_config(servo: servo_lib.Servo) -> servo_lib.FirmwareConfig:
  """Get specific flash config for octopus.

  Each board needs specific config including the voltage for Vref, to turn
  on and turn off the SPI flash. get_config() returns servo_lib.FirmwareConfig
  with settings to flash a servo for a particular build target.
  The voltage for this board needs to be set to 1.8 V.

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
        'spi2_vref:pp1800', 'spi2_buf_en:on', 'spi2_buf_on_flex_en:on',
        'spi_hold:off'
    ])
    dut_control_off.append([
        'spi2_vref:off', 'spi2_buf_en:off', 'spi2_buf_on_flex_en:off',
        'spi_hold:off'
    ])
    programmer = 'ft2232_spi:type=google-servo-v2,serial=%s' % servo.serial
  elif servo.is_micro:
    dut_control_on.append(
        ['spi2_vref:pp1800', 'spi2_buf_en:on', 'spi_hold:off'])
    dut_control_off.append(['spi2_vref:off', 'spi2_buf_en:off', 'spi_hold:off'])
    programmer = 'raiden_debug_spi:serial=%s' % servo.serial
  elif servo.is_ccd:
    programmer = 'raiden_debug_spi:target=AP,serial=%s' % servo.serial
  else:
    raise servo_lib.UnsupportedServoVersionError('%s not supported' %
                                                 servo.version)

  return servo_lib.FirmwareConfig(dut_control_on, dut_control_off, programmer)
