# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO: Name the build target.

"""{Build Target} configs."""

from chromite.lib.firmware import servo_lib

# BUILD CONFIGS.
# You probably don't need to fill those in.
# BUILD_WORKON_PACKAGES is the list packages that will be `cros_workon`ed.
# TODO(b/197680341): deprecate in favor of --workon-all.
# BUILD_WORKON_PACKAGES = (
#    '',
# )
# All packages that need to be built.
# BUILD_PACKAGES = BUILD_WORKON_PACKAGES + (
#    '',
# )
# End BUILD CONFIGS.

# FLASH CONFIGS.

# futility will be used by default for flashing.
# TODO: If flashrom is required, set the constant to True with explanation.
# DEPLOY_SSH_FORCE_FLASHROM = False
# DEPLOY_SERVO_FORCE_FLASHROM = False


# pylint: disable=unused-argument
def deploy_extra_flags_futility(servo: servo_lib.Servo) -> str:
  """Returns extra flags for flashing with futility"""
  return ''


def deploy_extra_flags_flashrom(servo: servo_lib.Servo) -> str:
  """Returns extra flags for flashing with flashrom"""
  return ''


def get_config(servo: servo_lib.Servo) -> servo_lib.FirmwareConfig:
  """Get specific flash config for the build target.

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
  # TODO: modify defaults according to the board needs.
  # TODO: raise UnsupportedServoVersionError for servos that are not supported.
  dut_control_on = [['cpu_fw_spi:on']]
  dut_control_off = [['cpu_fw_spi:off']]
  if servo.is_v2:
    programmer = 'ft2232_spi:type=google-servo-v2,serial=%s'
  elif servo.is_micro or servo.is_c2d2:
    programmer = 'raiden_debug_spi:serial=%s'
  elif servo.is_ccd:
    dut_control_on = []
    dut_control_off = []
    programmer = 'raiden_debug_spi:target=AP,serial=%s'
  else:
    raise servo_lib.UnsupportedServoVersionError('%s not supported' %
                                                 servo.version)

  return servo_lib.FirmwareConfig(dut_control_on, dut_control_off, programmer)


# End FLASH CONFIGS.
