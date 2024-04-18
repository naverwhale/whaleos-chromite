# Copyright 2013 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""crosfw - Chrome OS Firmware build/flash script.

Builds a firmware image for any board and writes it to the board. The image
can be pure upstream or include Chrome OS components (-V). Some device
tree parameters can be provided, including silent console (-C) and secure
boot (-S). Use -i for a faster incremental build. The image is written to
the board by default using USB/em100 (or sdcard with -x). Use -b to specify
the board to build. Options can be added to ~/.crosfwrc - see the script for
details.

It can also flash SPI by writing a 'magic flasher' U-Boot with a payload
to the board.

The script is normally run from within the U-Boot directory which is
.../src/third_party/u-boot/files

Example 1: Build upstream image for coreboot and write to a 'link':

 crosfw link

Example 2: Build verified boot image (V) for daisy/snow.

 crosfw daisy -V

You can force a reconfigure with -f and a full distclean with -F.

To increase verbosity use the -v and --debug options.

This script does not use an ebuild. It does a similar thing to the
chromeos-u-boot ebuild, and runs cros_bundle_firmware to produce various
types of image, a little like the chromeos-bootimage ebuild.

The purpose of this script is to make it easier and faster to perform
common firmware build tasks without changing boards, manually updating
device tree files or lots of USE flags and complexity in the ebuilds.

This script has been tested with snow, link and peach_pit. It builds for
peach_pit by default. Note that it will also build any upstream ARM
board - e.g. "snapper9260" will build an image for that board.

Mostly you can use the script inside and outside the chroot. The main
limitation is that dut-control doesn't really work outside the chroot,
so writing the image to the board over USB is not possible, nor can the
board be automatically reset on x86 platforms.

For an incremental build (faster), run with -i

To get faster clean builds, install ccache, and create ~/.crosfwrc with
this line:

 USE_CCACHE = True

(make sure ~/.ccache is not on NFS, or set CCACHE_DIR)

Other options are the default board to build, and verbosity (0-4), e.g.:

 DEFAULT_BOARD = 'daisy'
 VERBOSE = 1

It is possible to use multiple servo boards, each on its own port. Add
these lines to your ~/.crosfwrc to set the servo port to use for each
board:

 SERVO_PORT['link'] = 8888
 SERVO_PORT['daisy'] = 9999
 SERVO_PORT['peach_pit'] = 7777

All builds appear in the <outdir>/<board> subdirectory and images are written
to <outdir>/<uboard>/out, where <uboard> is the U-Boot name for the board (in
the U-Boot boards.cfg file)

The value for <outdir> defaults to /tmp/crosfw but can be configured in your
~/.crosfwrc file, e.g.:"

 OUT_DIR = '/tmp/u-boot'

For the -a option here are some useful options:

--add-blob cros-splash /dev/null
--gbb-flags -force-dev-switch-on
--add-node-enable /spi@131b0000/cros-ecp@0 1
--verify --full-erase
--bootcmd "cros_test sha"
--gbb-flags -force-dev-switch-on
--bmpblk ~/chromiumos/src/third_party/u-boot/bmp.bin

For example: -a "--gbb-flags -force-dev-switch-on"

Note the standard bmpblk is at:
  ~/chromiumos/src/third_party/chromiumos-overlay/sys-boot/
      chromeos-bootimage/files/bmpblk.bin
"""

import glob
import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List

from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import parallel


arch = None
board = None
compiler = None
default_board = None
in_chroot = True
outdir = ""

# If you have multiple boards connected on different servo ports, put lines
# like 'SERVO_PORT{"peach_pit"} = 7777' in your ~/.crosfwrc
SERVO_PORT = {}

src_root = os.path.join(constants.SOURCE_ROOT, "src")
in_chroot = cros_build_lib.IsInsideChroot()

uboard = ""

default_board = "peach_pit"
use_ccache = False

# Special cases for the U-Boot board config, the SOCs and default device tree
# since the naming is not always consistent.
# x86 has a lot of boards, but to U-Boot they are all the same
UBOARDS = {
    "daisy": "smdk5250",
    "peach": "smdk5420",
}
for b in [
    "alex",
    "butterfly",
    "emeraldlake2",
    "link",
    "lumpy",
    "parrot",
    "stout",
    "stumpy",
]:
    UBOARDS[b] = "coreboot-x86"
    UBOARDS["chromeos_%s" % b] = "chromeos_coreboot"

OUT_DIR = "/tmp/crosfw"

rc_file = os.path.expanduser("~/.crosfwrc")
if os.path.exists(rc_file):
    with open(rc_file, "rb") as fp:
        # pylint: disable=exec-used
        exec(compile(fp.read(), rc_file, "exec"))


def run(cmd: List[str], **kwargs: Dict[Any, Any]):
    """Run a command with the common settings.

    Args:
        cmd: Command + arguments to run.
        **kwargs: keyword arguments to pass on to cros_build_lib.run().

    Returns:
        A CompletedProcess object.
    """
    kwargs.setdefault("print_cmd", False)
    kwargs.setdefault("check", False)
    kwargs.setdefault("encoding", "utf-8")
    return cros_build_lib.run(cmd, **kwargs)


def Dumper(flag, infile, outfile):
    """Run objdump on an input file.

    Args:
        flag: Flag to pass objdump (e.g. '-d').
        infile: Input file to process.
        outfile: Output file to write to.
    """
    result = run([CompilerTool("objdump"), flag, infile], stdout=outfile)
    if result.returncode:
        sys.exit()


def CompilerTool(tool):
    """Returns the cross-compiler tool filename.

    Args:
        tool: Tool name to return, e.g. 'size'.

    Returns:
        Filename of requested tool.
    """
    return "%s%s" % (compiler, tool)


def ParseCmdline(argv):
    """Parse all command line options.

    Args:
        argv: Arguments to parse.

    Returns:
        The parsed options object
    """
    parser = commandline.ArgumentParser(
        description=__doc__, default_log_level="notice"
    )
    parser.add_argument(
        "-B",
        "--build",
        action="store_false",
        default=True,
        help="Don't build U-Boot, just configure device tree",
    )
    parser.add_argument(
        "--dt",
        help="Select name of device tree file to use",
    )
    parser.add_argument(
        "--dtb",
        type="file_exists",
        help="Select a binary .dtb, passed to the U-Boot build using EXT_DTB",
    )
    parser.add_argument(
        "-f",
        "--force-reconfig",
        action="store_true",
        default=False,
        help="Reconfigure before building",
    )
    parser.add_argument(
        "-F",
        "--force-distclean",
        action="store_true",
        default=False,
        help="Run distclean and reconfigure before building",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=os.cpu_count(),
        help="Select the number of CPUs to use (defaults to all)",
    )
    parser.add_argument(
        "-I",
        "--in-tree",
        action="store_true",
        default=False,
        help="Build in-tree",
    )
    parser.add_argument(
        "-L",
        "--no-lto",
        dest="lto",
        action="store_false",
        default=True,
        help="Disable Link-time Optimisation (LTO) when building",
    )
    parser.add_argument(
        "-O",
        "--objdump",
        action="store_true",
        default=False,
        help="Write disassembly output",
    )
    parser.add_argument(
        "-t",
        "--trace",
        action="store_true",
        default=False,
        help="Enable trace support",
    )
    parser.add_argument(
        "-T",
        "--target",
        nargs="?",
        default="all",
        help="Select target to build",
    )
    parser.add_argument(
        "-V",
        "--verified",
        action="store_true",
        default=False,
        help="Include Chrome OS verified boot components",
    )
    parser.add_argument(
        "-z",
        "--size",
        action="store_true",
        default=False,
        help="Display U-Boot image size",
    )
    parser.add_argument(
        "board",
        type=str,
        default=default_board,
        help="Select board to build (daisy/peach_pit/link)",
    )
    return parser.parse_args(argv)


def SetupBuild(options):
    """Set up parameters needed for the build.

    This checks the current environment and options and sets up various things
    needed for the build, including 'base' which holds the base flags for
    passing to the U-Boot Makefile.

    Args:
        options: Command line options

    Returns:
        Base flags to use for U-Boot, as a list.
    """
    # pylint: disable=global-statement
    global arch, board, compiler, outdir, uboard

    logging.info("Building for %s", options.board)

    # Separate out board_variant string: "peach_pit" becomes "peach", "pit".
    # But don't mess up upstream boards which use _ in their name.
    parts = options.board.split("_")
    if parts[0] in ["daisy", "peach"]:
        board = parts[0]
    else:
        board = options.board

    # To allow this to be run from 'cros_sdk'
    if in_chroot:
        os.chdir(os.path.join(src_root, "third_party", "u-boot", "files"))

    base_board = board

    if options.verified:
        base_board = "chromeos_%s" % base_board

    uboard = UBOARDS.get(base_board, base_board)
    logging.info("U-Boot board is %s", uboard)

    # Pull out some information from the U-Boot boards config file
    (PRE_KBUILD, PRE_KCONFIG, KCONFIG) = range(3)
    if os.path.exists("MAINTAINERS"):
        board_format = PRE_KBUILD
    else:
        board_format = PRE_KCONFIG

    # Create the boards.cfg file if missing.
    if not os.path.exists("boards.cfg"):
        run(["buildman", "-R", "boards.cfg"])

    with open("boards.cfg", encoding="utf-8") as f:
        for line in f:
            if "genboardscfg" in line:
                board_format = KCONFIG
            if uboard in line:
                if line[0] == "#":
                    continue
                fields = line.split()
                if not fields:
                    continue
                target = fields[6]
                # Make sure this is the right target.
                if target != uboard:
                    continue
                arch = fields[1]
                fields += [None, None, None]
                if board_format in (PRE_KCONFIG, KCONFIG):
                    target = fields[0]
    if not arch:
        cros_build_lib.Die(
            "Selected board '%s' not found in boards.cfg." % board
        )

    vboot = os.path.join("build", board, "usr")
    if arch == "sandbox":
        compiler = ""
    elif in_chroot:
        if arch == "x86":
            compiler = "i686-cros-linux-gnu-"
        elif arch == "arm":
            compiler = "armv7a-cros-linux-gnueabihf-"
        elif arch == "aarch64":
            compiler = "aarch64-cros-linux-gnu-"
    else:
        result = run(
            ["buildman", "-A", "--boards", options.board],
            capture_output=True,
        )
        compiler = result.stdout.strip()
        if not compiler:
            cros_build_lib.Die("Selected arch '%s' not supported.", arch)

    base = [
        "make",
        "-j%d" % options.jobs,
        "CROSS_COMPILE=%s" % compiler,
        "--no-print-directory",
        "HOSTSTRIP=true",
        "QEMU_ARCH=",
        "KCONFIG_NOSILENTUPDATE=1",
    ]
    if options.dt:
        base.append(f"DEVICE_TREE={options.dt}")
    if not options.in_tree:
        outdir = os.path.join(OUT_DIR, uboard)
        base.append(f"O={outdir}")
    if not options.lto:
        base.append("NO_LTO=1")
    if options.dtb:
        base.append(f"EXT_DTB={options.dtb}")

    # Enable quiet output at INFO level, everything at DEBUG level
    if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
        base.append("V=1")
    elif logging.getLogger().getEffectiveLevel() >= logging.NOTICE:
        base.append("-s")

    if options.verified:
        base += [
            "VBOOT=%s" % vboot,
            "MAKEFLAGS_VBOOT=DEBUG=1",
            "QUIET=1",
            "CFLAGS_EXTRA_VBOOT=-DUNROLL_LOOPS",
            "VBOOT_SOURCE=%s/platform/vboot_reference" % src_root,
        ]
        base.append("VBOOT_DEBUG=1")

    base.append("BUILD_ROM=1")
    if options.trace:
        base.append("FTRACE=1")

    if not options.force_reconfig:
        config_mk = "%s/include/autoconf.mk" % outdir
        if not os.path.exists(config_mk):
            logging.warning("No build found for %s - adding -f", board)
            options.force_reconfig = True

    config_mk = "include/autoconf.mk"
    if os.path.exists(config_mk):
        logging.warning("Warning: '%s' exists, try 'make mrproper'", config_mk)

    return base


def CheckConfigChange() -> bool:
    """See if we need to reconfigure due to config files changing

    Checks if any defconfig or Kconfig file has changed in the source tree
    since the last time U-Boot was configured for this build. For simplicity,
    any defconfig change will trigger this, not just one for the board being
    built, since the cost of a reconfigure is fairly small.

    Returns:
        True if any config file has changed since U-Boot was last configured
    """
    fname = os.path.join(outdir, ".config")
    ref_time = os.path.getctime(fname)
    for p in Path.cwd().glob("configs/*"):
        if p.stat().st_ctime > ref_time:
            logging.warning("config/ dir has changed - adding -f")
            return True

    for p in Path.cwd().glob("**/Kconfig*"):
        if p.stat().st_ctime > ref_time:
            logging.warning("Kconfig file(s) changed - adding -f")
            return True

    return False


def RunBuild(options, base, target, queue):
    """Run the U-Boot build.

    Args:
        options: Command line options.
        base: Base U-Boot flags.
        target: Target to build.
        queue: A parallel queue to add jobs to.
    """
    logging.info("U-Boot build flags: %s", " ".join(base))

    if options.force_distclean:
        options.force_reconfig = True
        # Ignore any error from this, some older U-Boots fail on this.
        run(base + ["distclean"], capture_output=True)

    if not options.force_reconfig:
        options.force_reconfig = CheckConfigChange()

    # Reconfigure U-Boot.
    if options.force_reconfig:
        if os.path.exists("tools/genboardscfg.py"):
            mtarget = "defconfig"
        else:
            mtarget = "config"
        cmd = base + ["%s_%s" % (uboard, mtarget)]
        result = run(cmd, stdout=True, stderr=subprocess.STDOUT)
        if (
            result.returncode
            or logging.getLogger().getEffectiveLevel() <= logging.DEBUG
        ):
            print(f"cmd: {result.cmdstr}")
            print(result.stdout, file=sys.stderr)
            if result.returncode:
                sys.exit(result.returncode)

    # Do the actual build.
    if options.build:
        result = run(base + [target], input="", capture_output=True)
        if (
            result.returncode
            or logging.getLogger().getEffectiveLevel() <= logging.INFO
            or result.stderr
        ):
            # The build failed, so output the results to stderr.
            print(f"cmd: {result.cmdstr}", file=sys.stderr)
            print(result.stderr, file=sys.stderr)

            # Note that stdout and stderr are separated here, so warnings
            # associated with a file will appear separately from any output
            # from the build system
            if logging.getLogger().getEffectiveLevel() <= logging.INFO:
                print(result.stdout)
            if result.returncode:
                sys.exit(result.returncode)

    files = ["%s/u-boot" % outdir]
    spl = glob.glob("%s/spl/u-boot-spl" % outdir)
    if spl:
        files += spl
    if options.size:
        result = run([CompilerTool("size")] + files)
        if result.returncode:
            sys.exit()

    # Create disassembly files .dis and .Dis (full dump)
    for f in files:
        base = os.path.splitext(f)[0]
        if options.objdump:
            queue.put(("-d", f, base + ".dis"))
            queue.put(("-D", f, base + ".Dis"))
        else:
            # Remove old files which otherwise might be confusing
            osutils.SafeUnlink(base + ".dis")
            osutils.SafeUnlink(base + ".Dis")

    logging.info("Output directory %s", outdir)


def main(argv):
    """Main function for script to build firmware.

    Args:
        argv: Program arguments.
    """
    options = ParseCmdline(argv)
    base = SetupBuild(options)

    with parallel.BackgroundTaskRunner(Dumper) as queue:
        RunBuild(options, base, options.target, queue)

        if options.objdump:
            logging.info("Writing diasssembly files")
