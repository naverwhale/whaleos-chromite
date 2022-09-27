# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Configuration options for cbuildbot boards."""

#
# Define assorted constants describing various sets of boards.
#

# Base per-board configuration.
# Every board must appear in exactly 1 of the following sets.

#
# Define assorted constants describing various sets of boards.
#

# Base per-board configuration.
# Every board must appear in exactly 1 of the following sets.

arm_internal_release_boards = frozenset([
    'arkham',
    'beaglebone',
    'beaglebone_servo',
    'gale',
    'hana',
    'littlejoe',
    'nyan_big',
    'nyan_blaze',
    'tael',
    'veyron_mighty',
    'veyron_minnie',
    'veyron_rialto',
    'veyron_speedy',
    'viking',
    'viking-poc2',
    'whirlwind',
])

arm_external_boards = frozenset([
    'arm-generic',
    'arm64-generic',
    'arm64-llvmpipe',
])

x86_internal_release_boards = frozenset([
    'deltaur',
    'falco_li',
    'glados',
    'guado_labstation',
    'guybrush',
    'jecht',
    'majolica',
    'mancomb',
    'poppy',
    'sludge',
    'tatl',
    'wristpin',
])

x86_external_boards = frozenset([
    'amd64-generic',
    'moblab-generic-vm',
    'x32-generic',
])

# Board can appear in 1 or more of the following sets.
brillo_boards = frozenset([
    'arkham',
    'gale',
    'mistral',
    'whirlwind',
])

accelerator_boards = frozenset([
    'fizz-accelerator',
])

beaglebone_boards = frozenset([
    'beaglebone',
    'beaglebone_servo',
])

dustbuster_boards = frozenset([
    'wristpin',
])

lassen_boards = frozenset([
    'lassen',
])

loonix_boards = frozenset([])

reven_boards = frozenset([
    'reven',
    'reven-vmtest',
])

wshwos_boards = frozenset([
    'littlejoe',
    'viking',
    'viking-poc2',
])

moblab_boards = frozenset([
    'puff-moblab',
    'fizz-moblab',
    'moblab-generic-vm',
])

scribe_boards = frozenset([
    'guado-macrophage',
    'puff-macrophage',
])

termina_boards = frozenset([
    'sludge',
    'tatl',
    'tael',
])

nofactory_boards = (
    termina_boards | lassen_boards | reven_boards | frozenset([
        'x30evb',
    ])
)

toolchains_from_source = frozenset([
    'x32-generic',
])

noimagetest_boards = (termina_boards | scribe_boards
                      | wshwos_boards | dustbuster_boards)

nohwqual_boards = (lassen_boards | termina_boards
                   | beaglebone_boards | wshwos_boards
                   | dustbuster_boards | reven_boards)

base_layout_boards = termina_boards

builder_incompatible_binaries_boards = frozenset([
    'grunt',
    'grunt-arc64',
    'grunt-arc-r',
    'guybrush',
    'majolica',
    'mancomb',
    'zork',
    'zork-arc-r',
    'zork-borealis',
])
