# Copyright 2014 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Integration VM test for cros commands.

To run this command, first build a test image. e.g.
$ cros build-packages --board=betty
$ cros build-image --board=betty test
$ cd chromite/cli/cros/tests/
$ ./cros_vm_test --board=betty --image_path \
~/chromiumos/src/build/images/betty/latest/chromiumos_test_image.bin
"""

from chromite.cli import command_vm_test
from chromite.lib import commandline


class CrosVMTest(command_vm_test.CommandVMTest):
    """Test class for cros commands."""

    def BuildCommand(self, command, device=None, pos_args=None, opt_args=None):
        """Builds a cros command.

        Args:
            command: The subcommand to build on (e.g. 'flash', 'deploy').
            device: The device's address for the command.
            pos_args: A list of positional arguments for the command.
            opt_args: A list of optional arguments for the command.

        Returns:
            A full cros command as a list.
        """
        cmd = ["cros", command]
        if opt_args:
            cmd.extend(opt_args)
        if device:
            if command == "devices":
                # The device argument is optional for 'cros devices' command.
                cmd.extend(["--device", device])
            else:
                cmd.append(device)
        if pos_args:
            cmd.extend(pos_args)
        return cmd


def _ParseArguments(argv):
    """Parses command-line arguments."""
    parser = commandline.ArgumentParser(description=__doc__, caching=True)
    parser.add_argument(
        "--board", required=True, help="Board for the VM to run tests."
    )
    parser.add_argument(
        "--image_path",
        required=True,
        type="path",
        help="Path to the image for the VM to run tests.",
    )
    return parser.parse_args(argv)


def main(argv):
    """Main function of the script."""
    options = _ParseArguments(argv)
    options.Freeze()
    test = CrosVMTest(options.board, options.image_path)
    test.Run()
