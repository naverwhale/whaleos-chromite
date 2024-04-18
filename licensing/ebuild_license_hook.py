# Copyright 2014 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Emerge hook to pre-parse and verify license information.

Called from src/scripts/hooks/install/gen-package-licenses.sh as part of a
package emerge.
"""

import os

from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.licensing import licenses_lib


def main(args):
    parser = commandline.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--builddir",
        type="path",
        required=True,
        help="Take $PORTAGE_BUILDDIR as argument.",
    )
    parser.add_argument(
        "--sysroot", type="path", help="Take $SYSROOT as argument."
    )

    opts = parser.parse_args(args)
    opts.Freeze()

    if not os.path.isdir(opts.builddir):
        parser.error(f"--builddir must be a directory: {opts.builddir}")

    sysroot = opts.sysroot
    if not sysroot:
        sysroot = os.environ.get("SYSROOT") or "/"

    try:
        licenses_lib.HookPackageProcess(opts.builddir, sysroot)
    except licenses_lib.PackageLicenseError as e:
        cros_build_lib.Die("Licensing error needs resolving: %s", e)
