# AP Firmware sample usage guide:

## Building
To build the AP Firmware for foo:
  setup_board -b foo # if not set up yet
  cros ap build -b foo

To build the AP Firmware only for foo-variant:
  cros ap build -b foo --fw-name foo-variant

## Flashing
Requires servod process to be running if flashing via servo

To flash your zork DUT with an IP of 1.1.1.1 via SSH:
  cros ap flash -b zork -i /path/to/image.bin -d ssh://1.1.1.1

To flash your volteer DUT via SERVO on the default port (9999):
  cros ap flash -d servo:port -b volteer -i /path/to/image.bin

To flash your volteer DUT via SERVO on port 1234:
  cros ap flash -d servo:port:1234 -b volteer -i /path/to/image.bin

To pass additional options to futility or flashrom, provide them after `--`,
e.g.:
  cros ap flash -b zork -i /path/to/image.bin -d ssh://1.1.1.1 -- --force

## Reading
To read image of device.cros via SSH:
  cros ap read -b volteer -o /tmp/volteer-image.bin -d ssh://device.cros

If you don't have ssh access from within the chroot, you may set up ssh tunnel:
  ssh -L 2222:localhost:22 device.cros
  cros ap read -b volteer -o /tmp/volteer-image.bin -d ssh://localhost:2222

To read image from DUT via SERVO on port 1234:
  cros ap read -b volteer -o /tmp/volteer-image.bin -d servo:port:1234

To read a specific region from DUT via SERVO on default port(9999):
  cros ap read -b volteer -r region -o /tmp/volteer-image.bin -d servo:port

## Dumping config
To dump AP config of all boards into /tmp/cros-read-ap-config.json
  cros ap dump-config -o /tmp/cros-read-ap-config.json

To dump AP config of drallion and dedede boards:
  cros ap dump-config -o /tmp/cros-read-ap-config.json -b "drallion dedede"

## Add support for new board
Create ${BOARD}.py in chromite/lib/firmware/ap_firmware_config.
The __template.py file can be copied into place, it contains a skeleton config.

 Define the following variables:

    BUILD_WORKON_PACKAGES as a list of all packages that should be cros_workon'd
      before building.

    BUILD_PACKAGES as a list of all packages that should be emerged during the
      build process.

  Define the following functions:

    is_fast_required:
      Only required if it needs to return True for any cases!
      Returns true if --fast is necessary to flash successfully.

      Args:
        use_futility (bool): True if futility is to be used, False if
          flashrom.
        servo (str): The type name of the servo device being used.
      Returns:
        bool: True if fast is necessary, False otherwise.

    get_config:
      Get specific flash config for this board.
      Each board needs specific commands including the voltage for Vref, to turn
      on and turn off the SPI flash. These commands can be found in the care and
      feeding doc for your board, any command that needs to be run before
      flashing should be included in dut_control_on and anything run after
      flashing should be in dut_control_off.

      Args:
        servo (servo_lib.Servo): The servo connected to the target DUT.

      Returns:
        servo_lib.FirmwareConfig:
          dut_control_on: 2d array formatted like [["cmd1", "arg1", "arg2"],
                                                   ["cmd2", "arg3", "arg4"]]
                          with commands that need to be ran before flashing,
                          where cmd1 will be run before cmd2.
          dut_control_off: 2d array formatted like [["cmd1", "arg1", "arg2"],
                                                    ["cmd2", "arg3", "arg4"]]
                          with commands that need to be ran after flashing,
                          where cmd1 will be run before cmd2.
          programmer: programmer argument (-p) for flashrom and futility.

See dedede.py for examples of each function/variable.
