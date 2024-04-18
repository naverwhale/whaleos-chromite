# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Basic lazy module loader."""

import functools
import importlib
import sys
from typing import Any, Callable, Tuple


class ForFunctions:
    """Load modules only when they're needed.

    This helps speed things up when only some of the modules are used.

    This only works for modules that export functions.  Other types (e.g.
    classes, properties, etc...) are not supported.
    """

    def __init__(self, name: str):
        """Initialize.

        Args:
            name: The module name to import.
        """
        self._mod = None
        self._modname = name

    def _get_mod(self):
        """Load the module and return it."""
        if self._mod is None:
            self._mod = importlib.import_module(self._modname)
        return self._mod

    def _wrapped_func(self, name: str, *args, **kwargs) -> Any:
        """Load the module and then call |name|."""
        mod = self._get_mod()
        return getattr(mod, name)(*args, **kwargs)

    def __getattr__(self, name: str) -> Callable:
        """Return a callable to the module function."""
        return functools.partial(self._wrapped_func, name)

    def __str__(self) -> str:
        return f"lazy_loader.ForFunctions({self._modname})"

    def __eq__(self, other: Any) -> bool:
        """Determine if objects are equal."""
        return (
            isinstance(other, ForFunctions) and self._modname == other._modname
        )

    def __ne__(self, other: Any) -> bool:
        """Determine if objects are not equal."""
        return not self == other

    def __getstate__(self) -> Tuple[Any]:
        """Return pickleable state for this Manifest."""
        return (self._modname,)

    def __setstate__(self, state: Tuple[Any]) -> None:
        """Set the state from pickle for this Manifest."""
        # We don't need to pickle the module directly as it'll be cached in
        # sys.modules.  Try to pull it back out to avoid importlib call.
        (self._modname,) = state
        self._mod = sys.modules.get(self._modname)
