# AP Firmware tooling usage guide:

This guide covers how to use `cros ap` tooling.
If you're interested in changing/fixing config for your board, please refer to
[ap_firmware_config/README.md](ap_firmware_config/README.md).

All `cros ap` commands should be run within the chroot. All examples below
assume that you have already
[entered the chroot](http://go/chromeos-building#enter-the-chroot). You can
enter the chroot by calling:
```
  (outside) cros_sdk
```

## Building
To build the AP Firmware for board `foo`:
```
  cros ap build -b foo
```

To build the AP Firmware only for `foo-variant`:
```
  cros ap build -b foo --fw-name foo-variant
```

## Flashing
Flashing via servo requires servod process to be running.

To flash a DUT with an IP of 1.1.1.1 via SSH:
```
  cros ap flash -b $BOARD -i /path/to/image.bin -d ssh://1.1.1.1
```

To flash a DUT via SERVO on the default port (9999):
```
  cros ap flash -d servo:port -b $BOARD -i /path/to/image.bin
```

To flash a DUT via SERVO on port 1234:
```
  cros ap flash -d servo:port:1234 -b $BOARD -i /path/to/image.bin
```

To pass additional options to futility or flashrom, provide them after `--`,
e.g.:
```
  cros ap flash -b $BOARD -i /path/to/image.bin -d ssh://1.1.1.1 -- --force
```

## Reading
To read firmware image of a DUT with an IP of 1.1.1.1 via SSH:
```
  cros ap read -b $BOARD -o /tmp/read-image.bin -d ssh://1.1.1.1
```

If you don't have ssh access from within the chroot, you may set up ssh tunnel:
```
  ssh -L 2222:localhost:22 1.1.1.1
  cros ap read -b $BOARD -o /tmp/read-image.bin -d ssh://localhost:2222
```

To read image from DUT via SERVO on port 1234:
```
  cros ap read -b $BOARD -o /tmp/read-image.bin -d servo:port:1234
```

To read a specific region from DUT via SERVO on default port(9999):
```
  cros ap read -b $BOARD -r region -o /tmp/read-image.bin -d servo:port
```

## Cleaning
To unmerge firmware-related packages and clear `/build/$BOARD/firmware` directory:
```
cros ap clean -b $BOARD
```
