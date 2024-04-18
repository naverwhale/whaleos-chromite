#!/usr/bin/env python3
# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Converts compilation database to work outside chroot.

Gets a compilation database generated inside chroot from stdin and outputs the
one that works outside chroot to stdout. This script is used from
platform.eclass.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from typing import Callable, List

import detect_indent


MNT_HOST_SOURCE_RE = r"(?:\.\.(?:/\.\.)*)?/mnt/host/source/(.*)"


def is_mount(directory: str) -> bool:
    try:
        subprocess.check_output(["mountpoint", directory])
        return True
    except subprocess.CalledProcessError:
        return False


class Converter:
    """Converts compilation database to work outside chroot"""

    def __init__(self, external_trunk_path: str, which: Callable[[str], str]):
        self.external_trunk_path = external_trunk_path
        self.external_chroot_path = os.path.join(external_trunk_path, "chroot")
        self.external_out_path = os.path.join(external_trunk_path, "out")

        self.build_is_mount = is_mount("/build")

        self.which = which

    def external_filepath(self, filepath: str) -> str:
        if filepath.startswith("/"):
            if filepath.startswith("/build/") and self.build_is_mount:
                return os.path.join(self.external_out_path, filepath[1:])
            return os.path.join(self.external_chroot_path, filepath[1:])
        return filepath

    def convert_filepath(self, filepath: str) -> str:
        # If out-of-tree build is enabled, source files under /mnt/host/source
        # are used. This directory is inaccessible outside chroot, so we convert
        # it.
        m = re.fullmatch(MNT_HOST_SOURCE_RE, filepath)
        if m:
            return os.path.join(self.external_trunk_path, m[1])

        # If out-of-tree build is disabled, source files are copied in a
        # temporary directory, and the filepath may point to the copied file. We
        # convert this so that code navigation doesn't jump to the file in
        # chroot.
        # We use a heuristic (using /platform2/ as a marker) here to support
        # platform2 packages.
        # TODO(oka): Revisit this logic to support packages outside platform2.
        m = re.fullmatch(r".*/platform2(/.*)?", filepath)
        if m:
            platform2 = os.path.join(self.external_trunk_path, "src/platform2")
            if m[1]:
                return os.path.join(platform2, m[1][1:])
            return platform2

        return self.external_filepath(filepath)

    def convert_include_option(self, option: str) -> List[str]:
        """Converts include option to work outside chroot.

        Examples:
            platform2 directory is converted, and the original one that is
            invisible outside chroot is omitted.
            .../mnt/host/source/src/platform2
            -> /path/to/chromiumos/src/platform2

            platform2 directory is converted, and the original one that is
            visible outside chroot is also kept.
            .../tmp/whatever/platform2
            -> /path/to/chromiumos/src/platform2  .../tmp/whatever/platform2

            Paths having no corresponding sources outside chroot are not
            converted.
            gen/include
            -> gen/include
        """

        filepath = option[2:]
        converted_include = "-I" + self.convert_filepath(filepath)

        # The filepath is not visible outside chroot.
        if re.fullmatch(MNT_HOST_SOURCE_RE, filepath):
            return [converted_include]

        chroot_include = "-I" + self.external_filepath(filepath)

        # chroot_include always points to the file inside chroot and might be
        # different from converted_include.
        if converted_include == chroot_include:
            return [converted_include]
        return [converted_include, chroot_include]

    def convert_clang_option_value(self, value: str) -> str:
        if "/" in value:
            return self.convert_filepath(value)
        return value

    def convert_clang_option(self, option: str) -> List[str]:
        if not option.startswith("-"):
            return [self.convert_clang_option_value(option)]

        # Convert flag value
        if option.startswith("-I"):
            return self.convert_include_option(option)

        # Remove a few compiler options that might not be available in the
        # potentially older clang version outside the chroot.
        if option in [
            "-fdebug-info-for-profiling",
            "-mretpoline",
            "-mretpoline-external-thunk",
            "-mfentry",
            "-mno-sched-prolog",
            "-fconserve-stack",
        ]:
            return []

        if "=" in option:
            flag, value = option.split("=", 2)
            return [flag + "=" + self.convert_clang_option_value(value)]

        if "/" in option:
            raise Exception(f"Unknown flag that suffixes a filepath: {option}")
        return [option]

    def convert_exe(self, exe: str) -> str:
        if exe == "cc":
            return exe

        # We should call clang directly instead of using CrOS wrappers.
        if re.match(r"^(aarch64|arm)", exe):
            return os.path.join(self.external_chroot_path, self.which(exe))

        for x in ["clang", "clang++"]:
            if exe.endswith(x):
                return x

        raise Exception(f"Unexpected executable name: {exe}")

    def convert_command_list(self, command: List[str]) -> List[str]:
        exe, *options = command

        converted_exe = self.convert_exe(exe)

        converted_options = []
        for option in options:
            converted_options += self.convert_clang_option(option)

        # Add "-stdlib=libc++" so that the clang outside the chroot can
        # find built-in headers like <string> and <memory>
        if "clang" in converted_exe:
            converted_options.append("-stdlib=libc++")

        return [converted_exe, *converted_options]

    def convert_command(self, command: str) -> str:
        return " ".join(self.convert_command_list(command.split(" ")))


DIRECTORY = "directory"
COMMAND = "command"
FILE = "file"
OUTPUT = "output"
ARGUMENTS = "arguments"


def generate(
    data, external_trunk_path, which: Callable[[str], str] = shutil.which
):
    """Generates non-chroot version of the compilation database"""

    converter = Converter(external_trunk_path, which)

    converted = []
    for item in data:
        converted_item = {}

        if ARGUMENTS in item:
            converted_item[ARGUMENTS] = converter.convert_command_list(
                item[ARGUMENTS]
            )

        converted_item[DIRECTORY] = converter.convert_filepath(item[DIRECTORY])

        if COMMAND in item:
            converted_item[COMMAND] = converter.convert_command(item[COMMAND])

        converted_item[FILE] = converter.convert_filepath(item[FILE])

        if OUTPUT in item:
            converted_item[OUTPUT] = converter.convert_filepath(item[OUTPUT])

        converted.append(converted_item)

    return converted


def main():
    text = sys.stdin.read()
    data = json.loads(text)
    external_trunk_path = sys.argv[1]
    if not os.path.exists(external_trunk_path):
        # The external_trunk_path points to the chromiumos trunk path *outside*
        # chroot, and it may not exist inside chroot, where the script is run
        # (b:259342928). We still show a warning here for debuggability because
        # the path usually exists.
        print(
            f"{external_trunk_path} does not exist inside chroot",
            file=sys.stderr,
        )
    indent = detect_indent.detect_indentation(text)
    json.dump(generate(data, external_trunk_path), sys.stdout, indent=indent)


if __name__ == "__main__":
    main()
