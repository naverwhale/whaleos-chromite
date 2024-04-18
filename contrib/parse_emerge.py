# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Parse emerge output.

Note: This is very much a contrib script. There are no guarantees it'll keep up
with emerge output, or that it works on all variations of the output.

Capable of parsing output saved to a file to generate total times per pacakge,
e.g. output from a builder.

    ./parse_emerge --parse /path/to/file

Can also compare two outputs, producing a list of deltas between the files,
where a positive number indicates it took that many seconds longer in the first
file than the second, and a negative number the opposite.

    ./parse_emerge --parse /path/to/file1 --parse /path/to/file2

    cat/pkg-1 100   # 100 seconds slower in file1 than file2
    cat/pkg-2 -100  # 100 seconds slower in file2 than file1

Finally, it can do a live parsing of a build_packages run, displaying a status
summary underneath the output from build_packages of active packages, as well
as producing the package time summary at the end.

    ./parse_emerge --build-packages {build_package arguments}
    ./parse_emerge --build-packages --board eve --cleanbuild --autosetgov
"""

import datetime
import enum
import os
import shutil
import subprocess
import sys

from chromite.lib import commandline
from chromite.lib import osutils


class NextAction(enum.Enum):
    """Enum for the follow-up actions to take based on parsing."""

    CLEAR_LINE = enum.auto()
    RESET = enum.auto()


class BuildPackagesProcessor:
    """Manages the state of the status summary and its output."""

    _EMERGING = (
        "Emerging (",
        "Emerging binary (",
    )
    _INSTALLING = "Installing ("
    _COMPLETED = "Completed ("
    _FAILED = "Failed to emerge"
    _JOBS = "Jobs:"
    _IGNORE = (
        # e.g. ... Recording <pkg> in "world" favorites file
        "Recording ",
    )

    def __init__(self, stream):
        self.stream = stream
        self.terminal_width = None
        self.terminal_height = None

        self.last_status = None
        self.started = None
        self.done = None
        self.failed = None
        self.source = None
        self.prebuilts = None
        self.all_packages = None
        self.emerging = None
        self.installing = None
        self.completed = None
        self.replace_last = None
        self.package_start = {}
        self.package_end = {}
        self.all_package_times = {}
        self.max_hour = 0

        self._reset()

    def _reset(self):
        self.last_status = None
        self.started = False
        self.done = False
        self.failed = False
        self.source = set()
        self.prebuilts = set()
        self.all_packages = set()
        self.emerging = set()
        self.installing = set()
        self.completed = set()
        self.replace_last = False

    def process(self, line):
        size = shutil.get_terminal_size((80, 20))
        self.terminal_width = size.columns
        self.terminal_height = size.lines

        self._clear_last_status()
        self.stream.write(line)
        # self.stream.flush()
        next_action = self._parse(line)
        self._print_status()
        # self.stream.flush()
        if next_action == NextAction.CLEAR_LINE:
            self.replace_last = True
        elif next_action == NextAction.RESET:
            self._reset()

    def _parse(self, line):
        if self.done:
            # Just echoing the rest of the output.
            return

        if not self.started:
            # Not started building yet, look for the lines listing the packages.
            ebuild = line.startswith("[ebuild")
            binary = line.startswith("[binary")
            if ebuild or binary:
                # [ebuild|binary N  ] package::overlay ...
                parts = line.split()
                for part in parts:
                    if "::" in part:
                        pkg = part.split("::")[0]
                        self.all_packages.add(pkg)
                        if ebuild:
                            self.source.add(pkg)
                        else:
                            self.prebuilts.add(pkg)
                        return

        for e in self._EMERGING:
            if e in line:
                self.started = True
                parts = line.split()
                # ... Emerging [binary] (X of N) package::overlay [for /sysroot]
                pkgstr = parts[-1] if "::" in parts[-1] else parts[-3]
                pkg = pkgstr.split("::")[0]
                self.emerging.add(pkg)
                t = parts[1]
                tparts = t.split(":")
                h = int(tparts[0])
                m = int(tparts[1])
                s = int(tparts[2].split(".")[0])
                ms = int(tparts[2].split(".")[1])
                d = 1
                if abs(h - self.max_hour) > 1 and h < self.max_hour:
                    d = 2
                self.max_hour = max(self.max_hour, h)
                start_dt = datetime.datetime(2000, 1, d, h, m, s, ms * 1000)
                self.package_start[pkg] = start_dt
                return

        if self.started:
            # Only bother checking for these after we've started.
            for pattern in self._IGNORE:
                if pattern in line:
                    return

            if self._INSTALLING in line:
                parts = line.split()
                # ... Installing (X of N) package::overlay [for /build/target]
                pkgstr = parts[-1] if "::" in parts[-1] else parts[-3]
                pkg = pkgstr.split("::")[0]
                self.installing.add(pkg)
                self.emerging.remove(pkg)
                return
            elif self._COMPLETED in line:
                parts = line.split()
                # ... Completed (X of N) package::overlay [for /build/target]
                pkgstr = parts[-1] if "::" in parts[-1] else parts[-3]
                pkg = pkgstr.split("::")[0]
                self.completed.add(pkg)
                self.installing.remove(pkg)

                t = parts[1]
                tparts = t.split(":")
                h = int(tparts[0])
                m = int(tparts[1])
                s = int(tparts[2].split(".")[0])
                ms = int(tparts[2].split(".")[1])
                d = 1
                if abs(h - self.max_hour) > 1 and h < self.max_hour:
                    d = 2
                self.max_hour = max(self.max_hour, h)
                end_dt = datetime.datetime(2000, 1, d, h, m, s, ms * 1000)
                self.package_end[pkg] = end_dt
                self.all_package_times[pkg] = (
                    end_dt - self.package_start[pkg]
                ).seconds
                return
            elif self._FAILED in line:
                # ... Failed to emerge package::overlay ...
                pkgstr = line.partition(self._FAILED)[2].split()[0]
                pkg = pkgstr.split("::")[0]
                self.failed = pkg
                self.done = True
                return
            elif self._JOBS in line:
                return NextAction.CLEAR_LINE
            elif not self.emerging and not self.installing:
                # Non-matching line, we're done with this block.
                return NextAction.RESET

    def _clear_last_status(self):
        if not self.last_status:
            return

        line_count = len(self.last_status)
        if self.replace_last:
            # Also replace the last log line.
            line_count += 1

        # Precondition: cursor at end of stream, directly after last status.
        # \033[K = clear current line.
        # \033[F = go to beginning of previous line.
        # Clear each status line, moving cursor to the previous line each time.
        self.stream.write("\033[K\033[F" * (line_count - 1))
        # Finally, clear the last (i.e. first) line.
        self.stream.write("\033[K")
        # Postcondition: Last status message has been erased, and cursor is at
        # the beginning of the line where we will resume the output.

        # Clear the relevant status variables.
        self.last_status = None
        self.replace_last = False

    def _print_status(self):
        if not self.started or self.done:
            # No status before we started emerging or after we're done.
            return

        status = [
            "_" * self.terminal_width,
            f"Emerging: {len(self.emerging)}",
        ]
        colsep = " | "
        longest = max(
            len(p) + len(colsep)
            for p in self.emerging | self.installing or [""]
        )
        available = self.terminal_width - 2
        n = max(available // longest, 1)
        if self.emerging:
            sorted_emerging = sorted(self.emerging)
            for i in range(0, len(sorted_emerging), n):
                chunk = sorted_emerging[i : i + n]
                status.append(
                    "  "
                    + colsep.join(x.ljust(longest - len(colsep)) for x in chunk)
                )

        status.append(f"Installing: {len(self.installing)}")
        if self.installing:
            sorted_installing = sorted(self.installing)
            for i in range(0, len(sorted_installing), n):
                chunk = sorted_installing[i : i + n]
                status.append(
                    "  "
                    + colsep.join(x.ljust(longest - len(colsep)) for x in chunk)
                )

        counts = f"Completed: {len(self.completed)}"
        if self.prebuilts:
            total_prebuilts = len(self.prebuilts)
            prebuilts = len(
                self.prebuilts
                - self.completed
                - self.emerging
                - self.installing
            )
            counts += f"\tPending Prebuilts: {prebuilts}/{total_prebuilts}"

        if self.source:
            total_src = len(self.source)
            src = len(
                self.source - self.completed - self.emerging - self.installing
            )
            counts += f"\tPending Source Builds: {src}/{total_src}"

        status.append(counts + "\r")

        # Progress bar (has a bug).
        # progress = len(self.completed) / len(self.prebuilts | self.source)
        # full_len = int((self.terminal_width - 2) * progress)
        # empty_len = (self.terminal_width - 2) - full_len
        # bar = "[" + "|" * full_len + " " * empty_len + "]"
        # status.append(bar + "\r")

        self.stream.write("\n".join(status))
        self.last_status = status

    def print_package_times(self):
        """Print the package time summary."""
        lines = [f"{k} {v}" for k, v in sorted(self.all_package_times.items())]
        print("\n".join(lines))


def build_packages_live_output(argv):
    """Execute build packages and live parse the output."""
    commandline.RunInsideChroot()

    # Live parse output.
    bpp = BuildPackagesProcessor(stream=sys.stdout)
    cmd = ["build_packages"] + argv

    with subprocess.Popen(cmd, stdout=subprocess.PIPE, encoding="utf-8") as p:
        while p.poll() is None:
            line = p.stdout.readline()
            bpp.process(line)

        bpp.print_package_times()


def replay_file(f, stream=sys.stdout):
    """Analyze an output in a file."""
    contents = osutils.ReadFile(f)
    bpp = BuildPackagesProcessor(stream=stream)

    for line in contents.splitlines():
        bpp.process(line + "\n")

    return bpp


def compare(f1, f2):
    """Differences over 15 seconds in package times between the files."""
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        f1_times = replay_file(f1, stream=devnull).all_package_times
        f2_times = replay_file(f2, stream=devnull).all_package_times

    deltas = {}
    for k, v in f1_times.items():
        if k not in f2_times:
            deltas[k] = v
        elif abs(v - f2_times[k]) > 15:
            deltas[k] = v - f2_times[k]

    for k, v in f2_times.items():
        if k not in f1_times:
            deltas[k] = v

    lines = []
    for k, v in sorted(deltas.items(), key=lambda x: list(reversed(x))):
        lines.append(f"{k} {v}")

    print("\n".join(reversed(lines)))


def get_parser():
    """Build the argument parser."""
    parser = commandline.ArgumentParser(
        caching=False, logging=False, description=__doc__
    )

    modes_group = parser.add_mutually_exclusive_group(required=True)
    modes_group.add_argument(
        "--parse",
        type="path",
        action="append",
        default=[],
        help="File(s) to parse.",
    )
    modes_group.add_argument(
        "--build-packages",
        default=False,
        action="store_true",
        help="Run build_packages and do live analysis of output.",
    )

    return parser


def parse_args(argv):
    """Parse the arguments."""
    parser = get_parser()

    known, unknown = parser.parse_known_args(
        argv, namespace=commandline.ArgumentNamespace()
    )

    known.Freeze()

    if len(known.parse) > 2:
        parser.error("Unable to compare more than two files.")

    return known, unknown


def main(argv):
    known, unknown = parse_args(argv)

    if known.build_packages:
        build_packages_live_output(unknown)
    elif len(known.parse) == 1:
        replay_file(known.parse.pop()).print_package_times()
    elif len(known.parse) == 2:
        compare(*known.parse)
