# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Creates a remote_toolchain_inputs file for Reclient.

Reclient(go/rbe/dev/x/reclient) is used for remote execution of build
actions in build systems e.g. Chrome. It needs a toolchain inputs file
next to clang compiler binary which has all the input dependencies
needed to run the clang binary remotely.

Running the script:
$ generate_reclient_inputs [--output file_name] [--clang /path/to/clang]
will create the file /path/to/file_name.

By default, the script will write to /usr/bin/remote_toolchain_inputs.

Contact: Chrome OS toolchain team.
"""

import argparse
import os
from pathlib import Path
from typing import List, Optional, Set

from chromite.third_party import lddtree

from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import osutils


def _GetSymLinkPath(base_dir: Path, link_path: str) -> Path:
    """Return the actual symlink path relative to base directory."""
    if not link_path:
        return None
    # Handle absolute symlink paths.
    if link_path[0] == "/":
        return link_path
    # handle relative symlinks.
    return base_dir / link_path


def _CollectElfDeps(elfpath: Path) -> Set[Path]:
    """Returns the set of dependent files for the elf file."""
    libs = set()
    to_process = [elfpath]
    elf = lddtree.ParseELF(elfpath, ldpaths=lddtree.LoadLdpaths())
    for _, lib_data in elf["libs"].items():
        if lib_data["path"]:
            to_process.append(Path(lib_data["path"]))

    while to_process:
        path = to_process.pop()
        if not path or path in libs:
            continue
        libs.add(path)
        if path.is_symlink():
            # TODO: Replace os.readlink() by path.readlink().
            to_process.append(_GetSymLinkPath(path.parent, os.readlink(path)))

    return libs


def _GenerateRemoteInputsFile(out_file: str, clang_path: Path) -> None:
    """Generate Remote Inputs for Clang for executing on reclient/RBE."""
    clang_dir = clang_path.parent
    # Start with collecting shared library dependencies.
    paths = _CollectElfDeps(clang_path)

    # Clang is typically a symlink, collect actual files.
    paths.add(clang_path)

    # Add clang resources, gcc config and glibc loader files.
    cmd = [str(clang_path), "--print-resource-dir"]
    resource_dir = cros_build_lib.run(
        cmd, capture_output=True, encoding="utf-8", print_cmd=False
    ).stdout.splitlines()[0]
    paths.add(Path(resource_dir) / "share")
    paths.update(
        Path(x)
        for x in (
            "/etc/env.d/gcc",
            "/etc/ld.so.cache",
            "/etc/ld.so.conf",
            "/etc/ld.so.conf.d",
        )
    )

    # Write the files relative to clang binary location.
    osutils.WriteFile(
        clang_dir / out_file,
        [os.path.relpath(x, clang_dir) + "\n" for x in sorted(paths)],
        sudo=True,
    )


def ParseArgs(argv: Optional[List[str]]) -> argparse.Namespace:
    """Parses program arguments."""
    parser = commandline.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--output",
        default="remote_toolchain_inputs",
        help="Name of remote toolchain file relative to clang binary "
        "directory.",
    )
    parser.add_argument(
        "--clang",
        type=Path,
        default="/usr/bin/clang",
        help="Clang binary path.",
    )

    opts = parser.parse_args(argv)
    opts.Freeze()
    return opts


def main(argv: Optional[List[str]] = None) -> Optional[int]:
    cros_build_lib.AssertInsideChroot()
    opts = ParseArgs(argv)
    _GenerateRemoteInputsFile(opts.output, opts.clang)
