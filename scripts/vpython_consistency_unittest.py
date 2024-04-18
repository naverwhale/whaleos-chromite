# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test to ensure consistency between vpython environments."""

from pathlib import Path
from typing import Dict, List, Set, Tuple

from chromite.third_party.google.protobuf import text_format
from packaging import version

from chromite.api.gen_test.go.chromium.org.luci.vpython.api.vpython import (
    spec_pb2,
)
from chromite.lib import constants


# The list of vpython environments to check for consistency. Paths are relative
# to CHROMITE_DIR.
_INPUTS = [
    "scripts/black",
    "scripts/isort",
    "scripts/mypy",
    "scripts/pylint",
    "scripts/run_tests.vpython3",
    "scripts/vpython_wrapper.py",
]

# The list of exceptions in the format emitted by assertions in this test. I.e.,
# <wheel>: <path> wants <old-version> but <path> has <latest-version>
_EXCEPTIONS = {
    "infra/python/wheels/mypy-extensions-py3: scripts/black"
    " wants 0.4.3 but scripts/mypy has 1.0.0",
    "infra/python/wheels/typing-extensions-py3: scripts/mypy"
    " wants 3.10.0.2 but scripts/run_tests.vpython3 has 4.0.1",
    "infra/python/wheels/tomli-py3: scripts/mypy"
    " wants 1.1.0 but scripts/run_tests.vpython3 has 2.0.1",
    "infra/python/wheels/tomli-py3: scripts/black"
    " wants 1.1.0 but scripts/run_tests.vpython3 has 2.0.1",
}

_BEGIN_GUARD = "[VPYTHON:BEGIN]"
_END_GUARD = "[VPYTHON:END]"


def _parse(path: Path) -> Tuple[Path, spec_pb2.Spec]:
    resolved_path = constants.CHROMITE_DIR / path
    assert resolved_path.is_file(), f"{path}: Input file must exist."
    assert (
        not resolved_path.is_symlink()
    ), f"{path}: Check only real files, not symlinks."

    lines = resolved_path.read_text().splitlines()

    # Extract the textproto from embedded specs. See
    # https://crsrc.org/i/go/src/go.chromium.org/luci/vpython/spec/load.go
    start_marker = next(
        (i for i, v in enumerate(lines) if v.endswith(_BEGIN_GUARD)), -1
    )
    if start_marker >= 0:
        end = next(i for i, v in enumerate(lines) if v.endswith(_END_GUARD))
        prefix_len = lines[start_marker].find(_BEGIN_GUARD)
        lines = [line[prefix_len:] for line in lines[start_marker + 1 : end]]

    spec = spec_pb2.Spec()
    text_format.Parse("\n".join(lines), spec)
    return (path, spec)


def test_vpython_consistency() -> None:
    specs = [_parse(Path(f)) for f in _INPUTS]

    # Map of package names, and the list of versions for it used by each file.
    wheels: Dict[str, List[Tuple[version.Version, Path]]] = {}
    for path, spec in specs:
        for wheel in spec.wheel:
            ver = version.parse(wheel.version.replace("version:", ""))
            wheels.setdefault(wheel.name, []).append((ver, path))

    # Sort so that the latest version is always at index[0].
    for versions in wheels.values():
        versions.sort(reverse=True)

    violations: Set[str] = set()
    for wheel, v in wheels.items():
        best = None
        for ver, path in v:
            if best and ver != best:
                violations.add(
                    f"{wheel}: {path} wants {ver} but {v[0][1]} has {best}"
                )
            else:
                best = ver

    expired = "\n".join(_EXCEPTIONS - violations)
    new = "\n".join(violations - _EXCEPTIONS)

    # Fail if an entry in _EXCEPTIONS is no longer detected and should be
    # removed.
    assert not expired, f"Exception no longer needed:\n{expired}"

    # Fail if there are new inconsistencies. To resolve a failure here:
    #     1. If a new version has been introduced ("foo has <new-version>"):
    #         - try to uprev other environments that want it to <new-version>.
    #     2. If an old version has been introduced ("foo wants <old-version>"):
    #         - try to use the newest version for foo.
    #     3. If stuff breaks, add to _EXCEPTIONS.
    assert not new, f"New vpython version inconsistencies:\n{new}"
