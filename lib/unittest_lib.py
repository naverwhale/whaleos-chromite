# Copyright 2014 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest-only utility functions library."""

import os
from typing import List, Optional

from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import sysroot_lib


class BuildELFError(Exception):
    """Generic error building an ELF file."""


def BuildELF(
    filename: str,
    defined_symbols: Optional[List[str]] = None,
    undefined_symbols: Optional[List[str]] = None,
    used_libs: Optional[List[str]] = None,
    executable: bool = False,
    static: bool = False,
    build_id: Optional[str] = None,
) -> None:
    """Builds a dynamic ELF with the provided import and exports.

    Compiles and links a dynamic program that exports some functions, as
    libraries do, and requires some symbols from other libraries. Dependencies
    should live in the same directory as the result. This function

    Args:
        filename: The output filename where the ELF is created.
        defined_symbols: The list of symbols this ELF exports.
        undefined_symbols: The list of symbols this ELF requires from other
            ELFs.
        used_libs: The list of libraries this ELF loads dynamically, including
            only the name of the library. For example, 'bz2' rather than
            'libbz2.so.1.0'.
        executable: Whether the file has a main() function.
        static: Whether the file is statically linked (implies executable=True).
        build_id: If provided, argument for the --build-id linker arg. E.g. the
            string "0xabcd1234" will set an explicit Build ID.
    """
    if defined_symbols is None:
        defined_symbols = []
    if undefined_symbols is None:
        undefined_symbols = []
    if used_libs is None:
        used_libs = []
    if static and not executable:
        raise ValueError("static requires executable to be True.")

    source = "".join("void %s();\n" % sym for sym in undefined_symbols)
    source += """
void __defined_symbols(const char*) __attribute__ ((visibility ("hidden")));
void __defined_symbols(const char* sym) {
  %s
}
""" % (
        "\n  ".join("%s();" % sym for sym in undefined_symbols)
    )

    source += "".join(
        """
void %s() __attribute__ ((visibility ("default")));
void %s() { __defined_symbols("%s"); }
"""
        % (sym, sym, sym)
        for sym in defined_symbols
    )

    if executable:
        source += """
int main() {
  __defined_symbols("main");
  return 42;
}
"""
    source_fn = filename + "_tmp.c"
    osutils.WriteFile(source_fn, source)

    outdir = os.path.dirname(filename)
    cmd = ["gcc", "-o", filename, source_fn]
    if not executable:
        cmd += ["-shared", "-fPIC"]
    if static:
        cmd += ["-static"]
    if build_id is not None:
        cmd += [f"-Wl,--build-id={build_id}"]
    cmd += ["-L.", "-Wl,-rpath=./"]
    cmd += ["-l%s" % lib for lib in used_libs]
    try:
        cros_build_lib.run(
            cmd, cwd=outdir, stdout=True, stderr=True, print_cmd=False
        )
    except cros_build_lib.RunCommandError as e:
        raise BuildELFError(f"{e}\n{e.stderr}")
    finally:
        os.unlink(source_fn)


def create_stub_make_conf(sysroot: os.PathLike):
    """Create a stub sysroot_lib._MAKE_CONF for tests to correctly read configs.

    sysroot_lib expects sysroot_lib._MAKE_CONF (etc/make.conf) to exist and to
    source sysroot_lib._MAKE_CONF_BOARD_SETUP (etc/make.conf.board_setup) to
    read the config.  For tests to read their expected config, a stub _MAKE_CONF
    needs to be created if they are using sysroot_lib.WriteConfig().

    Args:
        sysroot: The path to the sysroot
    """
    # pylint: disable=protected-access
    osutils.WriteFile(
        os.path.join(sysroot, sysroot_lib._MAKE_CONF),
        "source make.conf.board_setup",
        makedirs=True,
    )
