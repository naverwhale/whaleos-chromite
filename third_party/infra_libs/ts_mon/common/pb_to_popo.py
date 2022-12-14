# Copyright 2015 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import sys

from chromite.third_party.google.protobuf.descriptor import FieldDescriptor as fd
from chromite.third_party import six


def convert(pb):
  """Convert protobuf to plain-old-python-object"""
  obj = {}
  for field, value in pb.ListFields():
    if field.label == fd.LABEL_REPEATED:
      obj[field.name] = list(_get_json_func(field.type)(v) for v in value)
    else:
      obj[field.name] = _get_json_func(field.type)(value)
  return obj


def _get_json_func(field_type):
  if field_type in _FD_TO_JSON:
    return _FD_TO_JSON[field_type]
  else: # pragma: no cover
    logging.warning("pb_to_popo doesn't support converting %s", field_type)
    return six.text_type


if sys.version_info.major < 3:
  _64bit_type = long
else:
  _64bit_type = int

_FD_TO_JSON  = {
  fd.TYPE_BOOL: bool,
  fd.TYPE_DOUBLE: float,
  fd.TYPE_ENUM: int,
  fd.TYPE_FIXED32: float,
  fd.TYPE_FIXED64: float,
  fd.TYPE_FLOAT: float,
  fd.TYPE_INT32: int,
  fd.TYPE_INT64: _64bit_type,
  fd.TYPE_SFIXED32: float,
  fd.TYPE_SFIXED64: float,
  fd.TYPE_SINT32: int,
  fd.TYPE_SINT64: _64bit_type,
  fd.TYPE_STRING: six.text_type,
  fd.TYPE_UINT32: int,
  fd.TYPE_UINT64: _64bit_type,
  fd.TYPE_MESSAGE: convert
}
