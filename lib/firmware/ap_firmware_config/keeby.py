# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Keeby configs."""

from chromite.lib.firmware import servo_lib

_COMMON_PACKAGES = (
    'chromeos-ec',
    'coreboot',
    'depthcharge',
    'libpayload',
    'vboot_reference',
)

BUILD_PACKAGES = _COMMON_PACKAGES + (
    'chromeos-bootimage',
    'coreboot-private-files',
    'intel-jslfsp',
)


def get_config(servo: servo_lib.Servo) -> servo_lib.FirmwareConfig:
  """Get specific flash config for Keeby.

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

  # We need to get the SoC into a state where the AP won't boot, but enough
  # rails are up to prevent leakage.
  # Shutdown AP so that it enters G3 state.
  dut_control_on.append(['ec_uart_cmd:apshutdown'])
  # Sleep to ensure the SoC rails get chance to discharge enough.
  dut_control_on.append(['sleep:5'])
  # Turn on the S5 rails & initiate partial power up.
  dut_control_on.append(['ec_uart_cmd:gpioset en_pp3300_a 1'])
  # Sleep to ensure the required delay for device power sequencing.
  # Require 130 ms between EN_PP3300_A assertion and EC_AP_RSMRST_L assertion.
  dut_control_on.append(['sleep:0.2'])
  # Halt the power sequencing by de-asserting EC_AP_RSMRST_L.
  dut_control_on.append(['ec_uart_cmd:gpioset ec_ap_rsmrst_l 0'])
  # De-assert again to be on the safe side.
  dut_control_on.append(['ec_uart_cmd:gpioset ec_ap_rsmrst_l 0'])

  if servo.is_micro or servo.is_v2:
    dut_control_on.append(['cpu_fw_spi:on'])
    dut_control_off = [['cpu_fw_spi:off']]
    if servo.is_v2:
      programmer = 'ft2232_spi:type=google-servo-v2,serial=%s' % servo.serial
    else:
      # Servo micro
      programmer = 'raiden_debug_spi:serial=%s' % servo.serial
  else:
    raise servo_lib.UnsupportedServoVersionError('%s not supported' %
                                                 servo.version)

  return servo_lib.FirmwareConfig(dut_control_on, dut_control_off, programmer)
