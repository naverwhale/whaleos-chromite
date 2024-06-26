# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Helpers for constructing objects with frozen attributes."""

import types


class Error(Exception):
    """Raised when frozen attribute value is modified."""


class Class(type):
    """Metaclass for any class to support freezing attribute values.

    This metaclass can be used by any class to add the ability to
    freeze attribute values with the Freeze method.

    Use by including this line in the class signature:
        class ...(..., metaclass=attrs_freezer.Class)
    """

    _FROZEN_ERR_MSG = "Attribute values are frozen, cannot alter %s."

    def __new__(cls, clsname, bases, scope):
        # Create Freeze method that freezes current attributes.
        if "Freeze" in scope:
            raise TypeError(
                "Class %s has its own Freeze method, cannot use with"
                " the attrs_freezer.Class metaclass." % clsname
            )

        # Make sure cls will have _FROZEN_ERR_MSG set.
        scope.setdefault("_FROZEN_ERR_MSG", cls._FROZEN_ERR_MSG)

        # Create the class.
        # pylint: disable=bad-super-call
        newcls = super(Class, cls).__new__(cls, clsname, bases, scope)

        # Replace cls.__setattr__ with the one that honors freezing.
        orig_setattr = newcls.__setattr__

        def SetAttr(obj, name, value):
            """If the object is frozen then abort."""
            # pylint: disable=protected-access
            if getattr(obj, "_frozen", False):
                raise Error(obj._FROZEN_ERR_MSG % name)
            if isinstance(orig_setattr, types.MethodType):
                orig_setattr(obj, name, value)
            else:
                super(newcls, obj).__setattr__(name, value)

        newcls.__setattr__ = SetAttr

        # Add new newcls.Freeze method.
        def Freeze(obj):
            # pylint: disable=protected-access
            obj._frozen = True

        newcls.Freeze = Freeze

        return newcls


class Mixin(metaclass=Class):
    """Alternate mechanism for freezing attributes in a class.

    If an existing class is not a new-style class then it will be unable to
    use the attrs_freezer.Class metaclass directly.  Simply use this class
    as a mixin instead to accomplish the same thing.
    """
