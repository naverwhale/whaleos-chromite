# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Run fuzzers on ChromeOS Devices for given packages.

Given a remote host and a list of portage packages,
run the associated package fuzzers in a sysroot on the
remote host.

As of 2022-10-24, this script is intended to
only test fuzzers on x86_64 devices.

Example:
    cros_on_device_fuzz setup 'myhost:1234' 'my_package'
    cros_on_device_fuzz fuzz 'myhost:1234' 'my_installed_fuzzer'
"""

import logging
from pathlib import Path
import re
import tempfile
from typing import Iterable, Optional

from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import on_device_fuzz
from chromite.lib import remote_access


_DUT_FUZZER_ROOT = Path("/usr/local/tmp/fuzzer_root")
_IMPLICIT_SYSTEM_PACKAGE = "virtual/implicit-system"
_PACKAGE_SEPARATOR = re.compile(r"[ ,]+")
_FUZZER_BOARD = "amd64-generic"


def main(argv: Iterable[str]):
    """Dispatch to other functions."""
    opts = parse_args(argv)
    opts.func(opts)


def setup_main(opts):
    """Setup up the DUT for fuzzing."""
    cros_build_lib.AssertInsideChroot()
    device = _get_device(opts.device, opts.private_key)
    # Get a nice string representation of the device host for logging
    host = _format_collection(opts.device)
    # We do this version check to ensure we have a CrOS device
    # immediately.
    try:
        version = device.version
        if not version:
            raise RuntimeError("Version is null or empty.")
    except Exception:
        logging.error("Unable to get version of remote %s", host)
        raise

    logging.info("Connected to %s; CrOS version %s", host, version)
    packages = set(re.split(_PACKAGE_SEPARATOR, opts.packages))
    # We require virtual/implicit-system so that we can
    # build the on-device sysroot. Without it, we'll
    # miss critical libs and binaries.
    packages.add(_IMPLICIT_SYSTEM_PACKAGE)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        tarball_name = "sysroot_fuzzer_tarball.tar.xz"
        on_device_fuzz.create_sysroot_tarball(
            packages=packages,
            board=_FUZZER_BOARD,
            output_path=tmpdir / tarball_name,
        )
        on_device_fuzz.create_dut_sysroot(
            device,
            sysroot_tarball=tmpdir / tarball_name,
            sysroot_device_path=_DUT_FUZZER_ROOT,
        )
    logging.info("Fuzzer set up complete for %s", host)


def fuzz_main(opts):
    """Run a given fuzzer on the DUT."""
    cros_build_lib.AssertInsideChroot()
    fuzzer_install_path = Path("/usr/libexec/fuzzers")
    device = _get_device(opts.device, opts.private_key)
    on_device_fuzz.run_fuzzer_executable(
        device,
        sysroot_device_path=_DUT_FUZZER_ROOT,
        sysroot_fuzzer_path=fuzzer_install_path / opts.fuzzer_name,
        libfuzzer_options={},
    )


def _get_device(
    collection: commandline.Device, private_key: Optional[Path]
) -> remote_access.ChromiumOSDevice:
    """Get ChromiumOSDevice host from commandline.Device collection.

    The device will always execute commands as root.

    Args:
        collection: Device collection object to connect to.
        private_key: Path to private key to log into the device for.

    Returns:
        A remote_access.ChromiumOSDevice connection.
    """
    return remote_access.ChromiumOSDevice(
        collection.hostname,
        port=collection.port,
        username="root",
        private_key=private_key,
        base_dir=_DUT_FUZZER_ROOT,
        connect=True,
    )


def _format_collection(collection: commandline.Device) -> str:
    if collection.port is None:
        return collection.hostname
    return f"{collection.hostname}:{collection.port}"


def parse_args(raw_args: Iterable[str]):
    """Parse CLI arguments."""
    parser = commandline.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private-key",
        type=Path,
        default=None,
        help="RSA key for device. (default: lib.remote_access's key path)",
    )

    # Device parsing aids.
    device_parser = commandline.DeviceParser(commandline.DEVICE_SCHEME_SSH)
    device_host_help = "Device host, in the format '[ssh://]hostname[:port]'"

    subparsers = parser.add_subparsers()
    # setup subcommand
    subparser = subparsers.add_parser(
        "setup", help="Installs fuzzers on device sysroot."
    )
    subparser.set_defaults(func=setup_main)
    subparser.add_argument(
        "--device-sysroot-path",
        type=Path,
        help="Absolute location on device for the"
        f" fuzzer sysroot. (default: {_DUT_FUZZER_ROOT})",
        default=_DUT_FUZZER_ROOT,
    )
    subparser.add_argument("device", type=device_parser, help=device_host_help)
    subparser.add_argument(
        "packages",
        help="Portage packages to install fuzzers for."
        " Space or comma separated."
        f" Automatically includes {_IMPLICIT_SYSTEM_PACKAGE}",
    )

    # fuzz subcommand
    subparser = subparsers.add_parser(
        "fuzz", help="Runs a fuzzer in device sysroot."
    )
    subparser.set_defaults(func=fuzz_main)
    subparser.add_argument("device", type=device_parser, help=device_host_help)
    subparser.add_argument(
        "fuzzer_name", help="Name of the fuzzer executable to run."
    )

    return parser.parse_args(raw_args)
