# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Setup definitions for depgraph_visualization package."""

from setuptools import setup

setup(
    name='depgraph_visualization',
    version='0.0.1',
    packages=['depgraph_visualization'],
    author='The Chromium OS Authors',
    entry_points={
        'console_scripts':
            ['visualize_depgraph = depgraph_visualization.depgraph_viz:main']
    }
)
