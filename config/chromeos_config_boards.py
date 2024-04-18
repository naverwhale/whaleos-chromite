# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Configuration options for cbuildbot boards."""

# Base per-board configuration.
# Every board must appear in exactly 1 of the following sets.

arm_internal_release_boards = frozenset(
    [
        "hana",
        "littlejoe",
        "tael",
        "viking",
        "viking-arm64",
        "viking-poc2",
    ]
)

arm_external_boards = frozenset()

x86_internal_release_boards = frozenset(
    [
        "glados",
        "guado_labstation",
        "guybrush",
        "jecht",
        "majolica",
        "mancomb",
        "poppy",
        "sludge",
        "tatl",
        "wristpin",
    ]
)

x86_external_boards = frozenset(
    [
        "amd64-generic",
    ]
)

# Board can appear in 1 or more of the following sets.
brillo_boards = frozenset([])

dustbuster_boards = frozenset(
    [
        "wristpin",
    ]
)

loonix_boards = frozenset([])

reven_boards = frozenset(
    [
        "reven",
        "reven-vmtest",
    ]
)

wshwos_boards = frozenset(
    [
        "littlejoe",
        "viking",
        "viking-arm64",
        "viking-poc2",
    ]
)

moblab_boards = frozenset(
    [
        "puff-moblab",
        "fizz-moblab",
    ]
)

scribe_boards = frozenset(
    [
        "guado-macrophage",
        "puff-macrophage",
    ]
)

termina_boards = frozenset(
    [
        "sludge",
        "tatl",
        "tael",
    ]
)

labstation_boards = frozenset(
    [
        "fizz-labstation",
        "guado_labstation",
    ]
)

nofactory_boards = termina_boards | reven_boards | labstation_boards

builder_incompatible_binaries_boards = frozenset(
    [
        "grunt",
        "grunt-arc64",
        "grunt-arc-r",
        "guybrush",
        "majolica",
        "mancomb",
        "zork",
        "zork-arc-r",
        "skyrim",
        "skyrim-chausie",
        "skyrim-kernelnext",
    ]
)
