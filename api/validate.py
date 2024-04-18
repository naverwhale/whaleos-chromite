# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Validation helpers for simple input validation in the API.

Note: Every validator MUST respect config.do_validation. This is an internally
set config option that allows the mock call decorators to be placed before or
after the validation decorators, rather than forcing an ordering that could then
produce incorrect outputs if missed.
"""

import functools
import logging
import os
from typing import Any, Callable, Iterable, List, Optional, Union

from chromite.third_party.google.protobuf import message as protobuf_message

from chromite.lib import cros_build_lib


def _value(
    field: str, message: protobuf_message.Message
) -> Union[bool, int, str, None, List, protobuf_message.Message]:
    """Helper function to fetch the value of the field.

    Args:
        field: The field name. Can be nested via . separation.
        message: The protobuf message it is being fetched from.

    Returns:
        The value of the field.
    """
    if not field:
        return message

    value = message
    for part in field.split("."):
        if not isinstance(value, protobuf_message.Message):
            value = None
            break

        try:
            value = getattr(value, part)
        except AttributeError as e:
            cros_build_lib.Die("Invalid field: %s", e)

    return value


# pylint: disable=docstring-misnamed-args
def exists(*fields: str):
    """Validate that the paths in |fields| exist.

    Args:
        fields (str): The fields being checked. Can be . separated nested
            fields.
    """
    assert fields

    def decorator(func):
        @functools.wraps(func)
        def _exists(input_proto, output_proto, config, *args, **kwargs):
            if config.do_validation:
                for field in fields:
                    logging.debug("Validating %s exists.", field)

                    value = _value(field, input_proto)
                    if not value or not os.path.exists(value):
                        cros_build_lib.Die(
                            "%s path does not exist: %s", field, value
                        )

            return func(input_proto, output_proto, config, *args, **kwargs)

        return _exists

    return decorator


def eq(field: str, expected_value: Any):
    """Validate |field| is set to |expected_value|.

    Args:
        field: The field being checked. May be a `.` separated field.
        expected_value: The value to which the field must be equal.
    """
    assert field

    def decorator(func):
        @functools.wraps(func)
        def _eq(input_proto, output_proto, config, *args, **kwargs):
            if config.do_validation:
                logging.debug(
                    "Validating %s is equal to %r", field, expected_value
                )
                actual_value = _value(field, input_proto)

                if actual_value != expected_value:
                    cros_build_lib.Die(
                        "%s (%r) must be equal to %r",
                        field,
                        actual_value,
                        expected_value,
                    )

            return func(input_proto, output_proto, config, *args, **kwargs)

        return _eq

    return decorator


def is_in(field: str, values: Iterable):
    """Validate |field| is an element of |values|.

    Args:
        field: The field being checked. May be . separated nested fields.
        values: The possible values field may take.
    """
    assert field
    assert values

    def decorator(func):
        @functools.wraps(func)
        def _is_in(input_proto, output_proto, config, *args, **kwargs):
            if config.do_validation:
                logging.debug("Validating %s is in %r", field, values)
                value = _value(field, input_proto)

                if value not in values:
                    cros_build_lib.Die(
                        "%s (%r) must be in %r", field, value, values
                    )

            return func(input_proto, output_proto, config, *args, **kwargs)

        return _is_in

    return decorator


def each_in(
    field: str,
    subfield: Optional[str],
    values: Iterable,
    optional: bool = False,
):
    """Validate each |subfield| of the repeated |field| is in |values|.

    Args:
        field: The field being checked. May be . separated nested fields.
        subfield: The field in the repeated |field| to validate, or None
            when |field| is not a repeated message, e.g. enum, scalars.
        values: The possible values field may take.
        optional: Also allow the field to be empty when True.
    """
    assert field
    assert values

    def decorator(func):
        @functools.wraps(func)
        def _is_in(input_proto, output_proto, config, *args, **kwargs):
            if config.do_validation:
                members = _value(field, input_proto) or []
                if not optional and not members:
                    cros_build_lib.Die("The %s field is empty.", field)
                for member in members:
                    logging.debug(
                        "Validating %s.[each].%s is in %r.",
                        field,
                        subfield,
                        values,
                    )
                    value = _value(subfield, member)
                    if value not in values:
                        cros_build_lib.Die(
                            "%s.[each].%s (%r) must be in %r is required.",
                            field,
                            subfield,
                            value,
                            values,
                        )

            return func(input_proto, output_proto, config, *args, **kwargs)

        return _is_in

    return decorator


def constraint(description):
    """Define a function to be used as a constraint check.

    A constraint is a function that checks the value of a field and either
    does nothing (returns None) or returns a string indicating why the value
    isn't valid.

    We bind a human readable description to the constraint for error reporting
    and logging.

    Args:
        description: Human readable description of the constraint
    """

    def decorator(func):
        @functools.wraps(func)
        def _func(*args, **kwargs):
            func(*args, **kwargs)

        setattr(_func, "__constraint_description__", description)
        return _func

    return decorator


def check_constraint(field: str, checkfunc: Callable):
    """Validate all values of |field| pass a constraint.

    Args:
        field: The field being checked. May be . separated nested fields.
        checkfunc: A constraint function to check on each value
    """
    assert field
    assert constraint

    # Get description for the constraint if it's set
    constraint_description = getattr(
        checkfunc,
        "__constraint_description__",
        checkfunc.__name__,
    )

    def decorator(func):
        @functools.wraps(func)
        def _check_constraint(
            input_proto, output_proto, config, *args, **kwargs
        ):
            if config.do_validation:
                values = _value(field, input_proto) or []

                failed = []
                for val in values:
                    msg = checkfunc(val)
                    if msg is not None:
                        failed.append((val, msg))

                if failed:
                    msg = (
                        f"{field}.[all] one or more values failed check "
                        f'"{constraint_description}"\n'
                    )

                    for value, msg in failed:
                        msg += "  %s: %s\n" % (value, msg)
                    cros_build_lib.Die(msg)

            return func(input_proto, output_proto, config, *args, **kwargs)

        return _check_constraint

    return decorator


# pylint: disable=docstring-misnamed-args
def require(*fields: str):
    """Verify |fields| have all been set to truthy values.

    Args:
        fields: The fields being checked. May be . separated nested fields.
    """
    assert fields

    def decorator(func):
        @functools.wraps(func)
        def _require(input_proto, output_proto, config, *args, **kwargs):
            if config.do_validation:
                for field in fields:
                    logging.debug("Validating %s is set.", field)

                    value = _value(field, input_proto)
                    if not value:
                        cros_build_lib.Die("%s is required.", field)

            return func(input_proto, output_proto, config, *args, **kwargs)

        return _require

    return decorator


# pylint: disable=docstring-misnamed-args
def require_any(*fields: str):
    """Verify at least one of |fields| have been set.

    Args:
        fields: The fields being checked. May be . separated nested fields.
    """
    assert fields

    def decorator(func):
        @functools.wraps(func)
        def _require(input_proto, output_proto, config, *args, **kwargs):
            if config.do_validation:
                for field in fields:
                    logging.debug("Validating %s is set.", field)
                    value = _value(field, input_proto)
                    if value:
                        break
                else:
                    cros_build_lib.Die(
                        "At least one of the following must be set: %s",
                        ", ".join(fields),
                    )

            return func(input_proto, output_proto, config, *args, **kwargs)

        return _require

    return decorator


def require_each(
    field: str, subfields: Iterable[str], allow_empty: bool = True
):
    """Verify |field| each have all of the |subfields| set.

    When |allow_empty| is True, |field| may be empty, and |subfields| are only
    validated when it is not empty. When |allow_empty| is False, |field| must
    also have at least one entry.

    Args:
        field: The repeated field being checked. May be . separated nested
            fields.
        subfields: The fields of the repeated message to validate.
        allow_empty: Also require at least one entry in the repeated field.
    """
    assert field
    assert subfields
    assert not isinstance(subfields, str)

    def decorator(func):
        @functools.wraps(func)
        def _require_each(input_proto, output_proto, config, *args, **kwargs):
            if config.do_validation:
                members = _value(field, input_proto) or []
                if not allow_empty and not members:
                    cros_build_lib.Die("The %s field is empty.", field)
                for member in members:
                    for subfield in subfields:
                        logging.debug(
                            "Validating %s.[each].%s is set.", field, subfield
                        )
                        value = _value(subfield, member)
                        if not value:
                            cros_build_lib.Die("%s is required.", field)

            return func(input_proto, output_proto, config, *args, **kwargs)

        return _require_each

    return decorator


def validation_complete(func: Callable):
    """Automatically skip the endpoint when called after all other validators.

    This decorator MUST be applied after all other validate decorators.
    The config can be checked manually if there is non-decorator validation, but
    this is much cleaner if it is all done in decorators.
    """

    @functools.wraps(func)
    def _validate_only(request, response, configs, *args, **kwargs):
        if configs.validate_only:
            # Avoid calling the endpoint.
            return 0
        else:
            return func(request, response, configs, *args, **kwargs)

    return _validate_only
