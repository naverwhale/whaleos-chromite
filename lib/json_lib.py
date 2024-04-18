# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Helpful functions when parsing JSON blobs."""

import json
import re
from typing import Optional, Union

from chromite.lib import osutils


def AssertIsInstance(instance, expected_type, description):
    """Raise an error if |instance| is not of |expected_type|.

    Args:
        instance: instance of a Python object.
        expected_type: expected type of |instance|.
        description: short string describing |instance| used in error reporting.
    """
    if not isinstance(instance, expected_type):
        raise ValueError(
            "Expected %s to be a %s, but found %s"
            % (description, expected_type.__name__, instance.__class__.__name__)
        )


def GetValueOfType(a_dict, key, value_type, value_description):
    """Raise exception if we cannot get |key| from |a_dict| with |value_type|.

    Args:
        a_dict: a dictionary.
        key: string key that should be in the dictionary.
        value_type: expected type of the value at a_dict[key].
        value_description: string describing the value used in error reporting.
    """
    try:
        value = a_dict[key]
    except KeyError:
        raise ValueError(
            'Missing %s in JSON dictionary (key "%s")'
            % (value_description, key)
        )
    AssertIsInstance(value, value_type, value_description)
    return value


def PopValueOfType(a_dict, key, value_type, value_description):
    """Raise exception if we cannot pop |key| from |a_dict| with |value_type|.

    Args:
        a_dict: a dictionary.
        key: string key that should be in the dictionary.
        value_type: expected type of the value at a_dict[key].
        value_description: string describing the value used in error reporting.
    """
    ret = GetValueOfType(a_dict, key, value_type, value_description)
    # We were able to get that value, so the key must exist.
    a_dict.pop(key)
    return ret


# Remove # comments.
STRIP_HASH_COMMENTS = re.compile(r"^\s*#.*", flags=re.M)


def loads(
    data: Union[bytes, str],
    strip_utf8_bom: Optional[bool] = True,
    strip_hash_comments: Optional[bool] = True,
    **kwargs,
):
    """Parse JSON data with optional comment support.

    Args:
        data: JSON data.
        strip_utf8_bom: Remove leading UTF-8 BOM.
        strip_hash_comments: Strip # comments.
        **kwargs: Passed to json.loads().

    Returns:
        The parsed JSON data.
    """
    if isinstance(data, bytes):
        data = data.decode("utf-8")

    # Strip off leading UTF-8 BOM if it exists.
    if strip_utf8_bom and data.startswith("\ufeff"):
        data = data[1:]

    # Strip out comments for JSON parsing.
    if strip_hash_comments:
        # Replace with blank lines so Python error messages maintain the right
        # line numbers.
        data = STRIP_HASH_COMMENTS.sub("", data)

    return json.loads(data, **kwargs)


def load(fp, **kwargs):
    """Parse a JSON file with optional comment support.

    Args:
        fp: A file handle that can be .read().
        **kwargs: Passed to loads().
    """
    return loads(fp.read(), **kwargs)


def ParseJsonFileWithComments(path):
    """Parse a JSON file with bash style comments.

    Strips out comments from JSON blobs.

    Args:
        path: path to JSON file.

    Returns:
        Python representation of contents of JSON file.
    """
    return loads(osutils.ReadFile(path))


def GetNestedDictValue(a_dict, nested_key):
    """Obtains nested dict's value given hierarchical key sequence.

    For example, given d['a']['b']['c'] = 'z':
    GetNestedDictValue(d, ['a', 'b', 'c']) returns 'z'

    Args:
        a_dict: nested dict.
        nested_key: hierarchical key sequence.

    Returns:
        Value if found. None if any of keys doesn't exist.
    """
    obj = a_dict
    for k in nested_key:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
        if obj is None:
            return None
    return obj
