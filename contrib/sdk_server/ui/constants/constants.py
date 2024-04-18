# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""String constants for testing SDK Server UI."""

from os import getlogin
import pathlib
from socket import gethostname


# Define a dictionary to feed to Jinja template engine for dynamic data.
# These constants will be replaced with actual results from gRPC endpoints.
def get_index_data():
    index_data = {}
    index_data["user"] = getlogin()
    index_data["hostname"] = gethostname()
    index_data["date_created"] = "May 29, 2023"
    index_data["date_updated"] = "June 6, 2023"
    index_data["path"] = "/usr/local/google/home/josepp/chromiumos/chroot"
    index_data["version"] = "1.0.0"

    index_data["boards"] = ["amd64-generic", "betty"]

    p1 = {"name": "media-libs/libsync", "plus": "116", "minus": "40"}
    p2 = {"name": "media-libs/mesa-iris", "plus": "27", "minus": "0"}
    p3 = {"name": "media-sound/cros-alsa", "plus": "52", "minus": "10"}

    p4 = {"name": "chromeos-base/hammerd", "plus": "652", "minus": "0"}

    index_data["packages"] = {}
    index_data["packages"][index_data["boards"][0]] = [p1, p2, p3]
    index_data["packages"][index_data["boards"][1]] = [p4]

    workon_file = pathlib.Path(__file__).parent / "workon_packages.txt"
    with open(workon_file, mode="r", encoding="utf-8") as f:
        index_data["all_packages"] = f.readlines()

    log = """04:14:25.412: DEBUG: Services registered successfully.
	04:14:25.418: WARNING: No content found in /mnt/host/source/chromite/contrib/sdk_server_poc/empty_proto to deserialize.
	04:14:25.427: INFO: run: /mnt/host/source/src/scripts/update_chroot
	04:14:25.670 INFO    : Updating chroot
	04:14:25.686 INFO    : Clearing shadow utils lockfiles under /
	04:14:25.695 INFO    : Updating cross-compilers
	04:14:25.699 INFO    : Running: sudo -E /mnt/host/source/chromite/bin/cros_setup_toolchains
	04:14:32.259: INFO: Determining required toolchain updates...
	04:14:32.516: INFO: Updating packages:
	04:14:32.516: INFO: ['cross-x86_64-cros-linux-gnu/go', 'cross-x86_64-cros-linux-gnu/binutils', 'cross-x86_64-cros-linux-gnu/gcc', 'cross-x86_64-cros-linux-gnu/linux-headers', 'sys-devel/llvm', 'dev-lang/rust', 'dev-lang/rust-host', 'cross-arm-none-eabi/compiler-rt', 'cross-arm-none-eabi/binutils', 'cross-arm-none-eabi/gcc', 'cross-i686-cros-linux-gnu/binutils', 'cross-i686-cros-linux-gnu/gcc', 'cross-i686-cros-linux-gnu/linux-headers', 'cross-armv7a-cros-linux-gnueabihf/compiler-rt', 'cross-armv7a-cros-linux-gnueabihf/go', 'cross-armv7a-cros-linux-gnueabihf/binutils', 'cross-armv7a-cros-linux-gnueabihf/gcc', 'cross-armv7a-cros-linux-gnueabihf/linux-headers', 'cross-aarch64-cros-linux-gnu/compiler-rt', 'cross-aarch64-cros-linux-gnu/go', 'cross-aarch64-cros-linux-gnu/binutils', 'cross-aarch64-cros-linux-gnu/gcc', 'cross-aarch64-cros-linux-gnu/linux-headers', 'cross-armv7m-cros-eabi/compiler-rt', 'cross-armv7m-cros-eabi/binutils', 'cross-armv7m-cros-eabi/gcc', 'dev-lang/go', 'dev-lang/rust-bootstrap', 'sys-devel/binutils', 'sys-devel/gcc', 'sys-kernel/linux-headers']
	04:14:32.517: INFO: run: /mnt/host/source/chromite/bin/parallel_emerge --oneshot --update --getbinpkg --usepkgonly cross-x86_64-cros-linux-gnu/go cross-x86_64-cros-linux-gnu/binutils cross-x86_64-cros-linux-gnu/gcc cross-x86_64-cros-linux-gnu/linux-headers sys-devel/llvm dev-lang/rust dev-lang/rust-host cross-arm-none-eabi/compiler-rt cross-arm-none-eabi/binutils cross-arm-none-eabi/gcc cross-i686-cros-linux-gnu/binutils cross-i686-cros-linux-gnu/gcc cross-i686-cros-linux-gnu/linux-headers cross-armv7a-cros-linux-gnueabihf/compiler-rt cross-armv7a-cros-linux-gnueabihf/go cross-armv7a-cros-linux-gnueabihf/binutils cross-armv7a-cros-linux-gnueabihf/gcc cross-armv7a-cros-linux-gnueabihf/linux-headers cross-aarch64-cros-linux-gnu/compiler-rt cross-aarch64-cros-linux-gnu/go cross-aarch64-cros-linux-gnu/binutils cross-aarch64-cros-linux-gnu/gcc cross-aarch64-cros-linux-gnu/linux-headers cross-armv7m-cros-eabi/compiler-rt cross-armv7m-cros-eabi/binutils cross-armv7m-cros-eabi/gcc dev-lang/go dev-lang/rust-bootstrap sys-devel/binutils sys-devel/gcc sys-kernel/linux-headers
	04:14:32.648: INFO: Running: emerge --oneshot --update --getbinpkg --usepkgonly cross-x86_64-cros-linux-gnu/go cross-x86_64-cros-linux-gnu/binutils cross-x86_64-cros-linux-gnu/gcc cross-x86_64-cros-linux-gnu/linux-headers sys-devel/llvm dev-lang/rust dev-lang/rust-host cross-arm-none-eabi/compiler-rt cross-arm-none-eabi/binutils cross-arm-none-eabi/gcc cross-i686-cros-linux-gnu/binutils cross-i686-cros-linux-gnu/gcc cross-i686-cros-linux-gnu/linux-headers cross-armv7a-cros-linux-gnueabihf/compiler-rt cross-armv7a-cros-linux-gnueabihf/go cross-armv7a-cros-linux-gnueabihf/binutils cross-armv7a-cros-linux-gnueabihf/gcc cross-armv7a-cros-linux-gnueabihf/linux-headers cross-aarch64-cros-linux-gnu/compiler-rt cross-aarch64-cros-linux-gnu/go cross-aarch64-cros-linux-gnu/binutils cross-aarch64-cros-linux-gnu/gcc cross-aarch64-cros-linux-gnu/linux-headers cross-armv7m-cros-eabi/compiler-rt cross-armv7m-cros-eabi/binutils cross-armv7m-cros-eabi/gcc dev-lang/go dev-lang/rust-bootstrap sys-devel/binutils sys-devel/gcc sys-kernel/linux-headers --root-deps '--jobs=96' '--rebuild-exclude=chromeos-base/chromeos-chrome chromeos-base/chromium-source chromeos-base/chrome-icu'
	"""

    cmd1 = (
        "cros_workon --board=amd64-generic --package=media-libs/mesa-iris start"
    )
    cmd2 = "cros_workon --board=amd64-generic --package=chromeos-base/ml stop"

    d1 = "June 15 2:54pm"
    d2 = "June 14 4:41pm"

    index_data["logs"] = [
        {"log": log, "cmd": cmd1, "date": d1},
        {"log": "", "cmd": cmd2, "date": d2},
    ]

    return index_data
