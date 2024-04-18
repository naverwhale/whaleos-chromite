# AP Firmware tooling configuration guide

> ## **DO NOT ADD NEW CONFIGURATION HERE**
>
> The use of board-specific AP firmware flashing configuration in Chromite is
> ***deprecated***, do not add new config files here!
>
> AP firmware flashing prep and unprep configuration belongs in the `cpu_fw_spi`
> and `ccd_cpu_fw_spi` servod controls for the board.  They will get used
> automatically by `futility --servo` *and* by `cros ap flash`.  Example CL
> adding those controls for a board: https://crrev.com/c/4129143
>
> The `cros ap flash` and `cros ap read` commands are *not* deprecated, they
> will continue to wrap `futility --servo`.

This guide covers how to write configuration files for `cros ap` tooling.
If you're interested in `cros ap` tooling usage guide, please refer to
[../README.md](../README.md)

Note that it is not necessarily required to write custom config for your board.
If config for your board is missing, [generic config](generic.py) will be used,
and it should work in most cases.

## Add support for a new board

Create `${BOARD}.py` in `chromite/lib/firmware/ap_firmware_config`.
Generic config [`generic.py`](generic.py) file can be copied into place,
and used as a starting point for your config.

### Variables to define

#### Force flashrom for ssh/servo flashing
By default, `cros ap flash` will flash with `futility`.
If `futility` works for your board, there's no need to define any variables.
If there's a reason to use `flashrom` instead for SSH/Servo flashing,
set either of the following variables to true.

```
DEPLOY_SSH_FORCE_FLASHROM = True
DEPLOY_SERVO_FORCE_FLASHROM = True
```

### Functions to define:
#### Extra flags to use when flashing with futility/flashrom
You can use `deploy_extra_flags_futility` and `deploy_extra_flags_flashrom` functions to add extra flags(such as --fast or --force) to
futility and flashrom respectively while flashing.
These functions accept [`servo_lib.Servo` object](https://source.corp.google.com/chromeos_public/chromite/lib/firmware/servo_lib.py) (or `None` for SSH) and return a list of flags.

```
def deploy_extra_flags_futility(servo: Optional[servo_lib.Servo]) -> List[str]
```
```
def deploy_extra_flags_flashrom(servo: Optional[servo_lib.Servo]) -> List[str]
```

#### ServoConfig
`get_config` is the primary function to set config for flashing with Servo.
It accepts [`servo_lib.Servo` object](https://source.corp.google.com/chromeos_public/chromite/lib/firmware/servo_lib.py) and returns a [`servo_lib.ServoConfig` tuple](https://source.corp.google.com/chromeos_public/chromite/lib/firmware/servo_lib.py), which contains dut_control commands to be run before and after flashing, and programmer argument to be used for flashing.
```
def get_config(servo: servo_lib.Servo) -> servo_lib.ServoConfig
```

## Deprecated
You shouldn't use any of those:
 * BUILD_PACKAGES and BUILD_WORKON_PACKAGES are not needed anymore.
 * `is_fast_required()` should be specified as part of `deploy_extra_flags_futility()` or `deploy_extra_flags_flashrom()` (see above)

### Deprecated variables

```
    BUILD_WORKON_PACKAGES as a list of all packages that should be cros_workon'd
      before building.

    BUILD_PACKAGES as a list of all packages that should be emerged during the
      build process.
```
### Deprecated functions
```
    is_fast_required:
      Only required if it needs to return True for any cases!
      Returns true if --fast is necessary to flash successfully.

      Args:
        use_futility (bool): True if futility is to be used, False if flashrom.
        servo (str): The type name of the servo device being used.
      Returns:
        bool: True if fast is necessary, False otherwise.
```
