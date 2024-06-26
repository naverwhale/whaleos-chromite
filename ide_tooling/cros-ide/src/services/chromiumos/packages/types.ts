// Copyright 2022 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {ParsedPackageName} from '../../../common/chromiumos/portage/ebuild';

/**
 * Directory containing source code relative to chromiumos/
 */
export type SourceDir = string;

export interface PackageInfo {
  sourceDir: SourceDir;
  pkg: ParsedPackageName;
}
