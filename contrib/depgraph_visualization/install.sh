#!/bin/bash
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

WD=$(pwd)
cd "$(dirname "$(realpath "${0}")")" || exit

python3 -m venv my_visualizations
source my_visualizations/bin/activate
pip install -r requirements.txt
pip install .

cd "${WD}" || exit


