# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Servo-related functionality.

This module keeps a list of all valid servos, and provides utility functions
to simplify checking whether a given servo name has a property, such as being a
CCD/servo v4/servo micro.
"""

from typing import List, NamedTuple


SERVO_C2D2 = "c2d2"
SERVO_CCD_CR50 = "ccd_cr50"
SERVO_CCD_TI50 = "ccd_ti50"
SERVO_CCD_GSC = "ccd_gsc"
SERVO_MICRO = "servo_micro"
SERVO_V2 = "servo_v2"
SERVO_V4_C2D2 = "servo_v4_with_c2d2"
SERVO_V4_CCD = "servo_v4_with_ccd"
SERVO_V4_CCD_CR50 = "servo_v4_with_ccd_cr50"
SERVO_V4_CCD_TI50 = "servo_v4_with_ccd_ti50"
SERVO_V4_CCD_GSC = "servo_v4_with_ccd_gsc"
SERVO_V4_MICRO = "servo_v4_with_servo_micro"
SERVO_V4P1_C2D2 = "servo_v4p1_with_c2d2"
SERVO_V4P1_CCD = "servo_v4p1_with_ccd"
SERVO_V4P1_CCD_CR50 = "servo_v4p1_with_ccd_cr50"
SERVO_V4P1_CCD_TI50 = "servo_v4p1_with_ccd_ti50"
SERVO_V4P1_CCD_GSC = "servo_v4p1_with_ccd_gsc"
SERVO_V4P1_MICRO = "servo_v4p1_with_servo_micro"

VALID_SERVOS = (
    SERVO_C2D2,
    SERVO_CCD_CR50,
    SERVO_CCD_TI50,
    SERVO_CCD_GSC,
    SERVO_MICRO,
    SERVO_V2,
    SERVO_V4_C2D2,
    SERVO_V4_CCD,
    SERVO_V4_CCD_CR50,
    SERVO_V4_CCD_TI50,
    SERVO_V4_CCD_GSC,
    SERVO_V4_MICRO,
    SERVO_V4P1_C2D2,
    SERVO_V4P1_CCD,
    SERVO_V4P1_CCD_CR50,
    SERVO_V4P1_CCD_TI50,
    SERVO_V4P1_CCD_GSC,
    SERVO_V4P1_MICRO,
)

CCD_SERVOS = (
    SERVO_CCD_CR50,
    SERVO_CCD_TI50,
    SERVO_CCD_GSC,
    SERVO_V4_CCD,
    SERVO_V4_CCD_CR50,
    SERVO_V4_CCD_TI50,
    SERVO_V4_CCD_GSC,
    SERVO_V4P1_CCD,
    SERVO_V4P1_CCD_CR50,
    SERVO_V4P1_CCD_TI50,
    SERVO_V4P1_CCD_GSC,
)
MICRO_SERVOS = (SERVO_MICRO, SERVO_V4_MICRO, SERVO_V4P1_MICRO)
V2_SERVOS = (SERVO_V2,)
V4_SERVOS = (
    SERVO_V4_C2D2,
    SERVO_V4_CCD,
    SERVO_V4_CCD_CR50,
    SERVO_V4_MICRO,
    SERVO_V4_CCD_TI50,
    SERVO_V4P1_C2D2,
    SERVO_V4P1_CCD,
    SERVO_V4P1_CCD_CR50,
    SERVO_V4P1_CCD_TI50,
    SERVO_V4P1_MICRO,
    SERVO_V4_CCD_GSC,
    SERVO_V4P1_CCD_GSC,
)
C2D2_SERVOS = (SERVO_C2D2, SERVO_V4_C2D2, SERVO_V4P1_C2D2)

_SERIAL_NUMBER_OPTION = "serialname"
_SERIAL_NUMBER_OPTION_OVERRIDE = {
    SERVO_V4_CCD: "ccd_serialname",
    SERVO_V4_CCD_CR50: "ccd_serialname",
    SERVO_V4_CCD_TI50: "ccd_serialname",
    SERVO_V4_CCD_GSC: "ccd_serialname",
    SERVO_V4_MICRO: "servo_micro_serialname",
    SERVO_V4P1_CCD: "ccd_serialname",
    SERVO_V4P1_CCD_CR50: "ccd_serialname",
    SERVO_V4P1_CCD_TI50: "ccd_serialname",
    SERVO_V4P1_CCD_GSC: "ccd_serialname",
    SERVO_V4P1_MICRO: "servo_micro_serialname",
}


def get_serial_option(servo_type: str) -> str:
    """Return the variable to be used with a given servo to get DUT's serial."""
    return _SERIAL_NUMBER_OPTION_OVERRIDE.get(servo_type, _SERIAL_NUMBER_OPTION)


class Error(Exception):
    """Base error class for the module."""


class UnsupportedServoVersionError(Error):
    """Unsupported servo version error (e.g. some servos do not support CCD)."""


class Servo:
    """Data class for servos."""

    def __init__(self, servo_type, serial):
        assert servo_type in VALID_SERVOS
        self.version = servo_type
        self.serial = serial

    @property
    def is_ccd(self):
        return self.version in CCD_SERVOS

    @property
    def is_c2d2(self):
        return self.version in C2D2_SERVOS

    @property
    def is_micro(self):
        return self.version in MICRO_SERVOS

    @property
    def is_v2(self):
        return self.version in V2_SERVOS

    @property
    def is_v4(self):
        return self.version in V4_SERVOS


class ServoConfig(NamedTuple):
    """Stores dut controls for specific servos.

    Attributes:
        dut_control_on: 2d array formatted like
            [["cmd1", "arg1", "arg2"], ["cmd2", "arg3", "arg4"]]
            with commands that need to be run before flashing,
            where cmd1 will be run before cmd2.
        dut_control_off: 2d array formatted like
            [["cmd1", "arg1", "arg2"], ["cmd2", "arg3", "arg4"]]
            with commands that need to be run after flashing,
            where cmd1 will be run before cmd2.
        programmer: programmer argument (-p) for flashrom and futility.
    """

    dut_control_on: List[List[str]]
    dut_control_off: List[List[str]]
    programmer: str
