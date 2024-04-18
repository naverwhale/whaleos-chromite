#!/usr/bin/env vpython3
# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# NB: Do not add a ton of wheels here as it's shared among many programs.
# Only list significant ones widely used by chromite.lib modules.
#
# For info on this syntax, see:
# https://chromium.googlesource.com/infra/infra/+/HEAD/doc/users/vpython.md#available-wheels

# [VPYTHON:BEGIN]
# python_version: "3.8"
#
# wheel: <
#   name: "infra/python/wheels/psutil/${vpython_platform}"
#   version: "version:5.7.2"
# >
# wheel: <
#   name: "infra/python/wheels/pyasn1-py2_py3"
#   version: "version:0.2.3"
# >
# wheel: <
#   name: "infra/python/wheels/pyasn1_modules-py2_py3"
#   version: "version:0.0.8"
# >
# wheel: <
#   name: "infra/python/wheels/pyyaml-py3"
#   version: "version:5.3.1"
# >
# wheel: <
#   name: "infra/python/wheels/rsa-py2_py3"
#   version: "version:3.4.2"
# >
# wheel: <
#   name: "infra/python/wheels/six-py2_py3"
#   version: "version:1.15.0"
# >
# [VPYTHON:END]

"""Wrapper around chromite executable scripts that use vpython."""

import wrapper3


def main():
    wrapper3.DoMain()


if __name__ == "__main__":
    main()
