# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import importlib
import logging
import pkgutil
from types import ModuleType
from typing import Iterator, Tuple


_CONFIG_MODULE_FULL_NAME = "chromite.lib.firmware.ap_firmware_config.%s"
_GENERIC_CONFIG_NAME = "generic"


class Error(Exception):
    """Base error class for the module."""


class BuildTargetNotConfiguredError(Error):
    """Thrown when a config module does not exist for the build target."""


def configs() -> Iterator[Tuple[str, ModuleType]]:
    """Iterate over all config modules.

    Yields:
        (board, module): build target name and associated config module.
    """
    for _, module_name, _ in pkgutil.iter_modules(__path__):
        if module_name.startswith("_"):
            continue
        yield module_name, get(module_name, fallback=False)


def get(build_target_name: str, fallback: bool = True) -> ModuleType:
    """Return configuration module for a given build target.

    Args:
        build_target_name: Name of the build target, e.g. 'dedede'.
        fallback: Allows falling back to generic config if the config for
            build_target_name is not found.

    Returns:
        module: Python configuration module for a given build target.
    """
    name = _CONFIG_MODULE_FULL_NAME % build_target_name
    try:
        return importlib.import_module(name)
    except ImportError:
        name_path = name.replace(".", "/") + ".py"
        if not fallback:
            raise BuildTargetNotConfiguredError(
                f"Could not find a config module for {build_target_name}. "
                f"Fill in the config in {name_path}."
            )

    # Falling back to generic config.
    logging.notice(
        "Did not find a dedicated config module for %s at %s. "
        "Using default config.",
        build_target_name,
        name_path,
    )
    return get(_GENERIC_CONFIG_NAME, fallback=False)
