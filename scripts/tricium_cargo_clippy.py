# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs cargo clippy across the given files, dumping diagnostics to a JSON file.

This script is intended specifically for use with Tricium (go/tricium).
"""

import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, NamedTuple, Text

from chromite.lib import commandline
from chromite.lib import cros_build_lib


class Error(Exception):
  """Base error class for tricium-cargo-clippy."""


class CargoClippyPackagePathError(Error):
  """Raised when no Package Path is provided."""

  def __init__(self, source: Text):
    super().__init__(f'{source} does not start with a package path')
    self.source = source

class CargoClippyJSONError(Error):
  """Raised when cargo-clippy parsing jobs are not proper JSON."""

  def __init__(self, source: Text, line_num: int):
    super().__init__(f'{source}:{line_num}: is not valid JSON')
    self.source = source
    self.line_num = line_num


class CargoClippyReasonError(Error):
  """Raised when cargo-clippy parsing jobs don't provide a "reason" field."""

  def __init__(self, source: Text, line_num: int):
    super().__init__(f'{source}:{line_num}: is missing its reason')
    self.source = source
    self.line_num = line_num


class CargoClippyFieldError(Error):
  """Raised when cargo-clippy parsing jobs fail to determine a field."""

  def __init__(self, source: Text, line_num: int, field: Text):
    super().__init__(
        f'{source}:{line_num}: {field} could not be parsed from original json'
    )
    self.source = source
    self.line_num = line_num
    self.field = field


def resolve_path(file_path: Text) -> Text:
  return str(Path(file_path).resolve())


class CodeLocation(NamedTuple):
  """Holds the location a ClippyDiagnostic Finding."""
  file_path: Text
  line_start: int
  line_end: int
  column_start: int
  column_end: int

  def to_dict(self):
    return {
        **self._asdict(),
        'file_path': self.file_path
    }


class ClippyDiagnostic(NamedTuple):
  """Holds information about a compiler message from Clippy."""
  locations: Iterable['CodeLocation']
  level: Text
  message: Text

  def as_json(self):
    return json.dumps({
        **self._asdict(),
        'locations': [loc.to_dict() for loc in self.locations],
    })


def parse_locations(
    orig_json: Dict[Text, Any],
    package_path: Text, git_repo: Text) -> Iterable['CodeLocation']:
  """The code locations associated with this diagnostic as an iter.

  The relevant code location can appear in either the messages[spans] field,
  which will be used if present, or else child messages each have their own
  locations specified.

  Args:
    orig_json: An iterable of clippy entries in original json.
    package_path: A resolved path to the rust package.
    git_repo: Base directory for git repo to strip out in diagnostics.

  Yields:
    A CodeLocation object associated with a relevant span.

  Raises:
    CargoClippyFieldError: Parsing failed to determine any code locations.
  """
  spans = orig_json.get('message', {}).get('spans', [])
  children = orig_json.get('message', {}).get('children', [])
  for child in children:
    spans = spans + child.get('spans', [])
  locations = set()
  for span in spans:
    file_path = os.path.join(package_path, span.get('file_name'))
    if git_repo and file_path.startswith(f'{git_repo}/'):
      file_path = file_path[len(git_repo)+1:]
    else:
      # Remove ebuild work directories from prefix
      # Such as: "**/<package>-9999/work/<package>-9999/"
      #      or: "**/<package>-0.24.52-r9/work/<package>-0.24.52/"
      file_path = re.sub(r'(.*/)?([^/]+)-[^/]+/work/[^/]+/+', '', file_path)
    location = CodeLocation(
        file_path=file_path,
        line_start=span.get('line_start'),
        line_end=span.get('line_end'),
        column_start=span.get('column_start'),
        column_end=span.get('column_end'))
    if location not in locations:
      locations.add(location)
      yield location


def parse_level(src: Text, src_line: int, orig_json: Dict[Text, Any]) -> Text:
  """The level (error or warning) associated with this diagnostic.

  Args:
    src: Name of the file orig_json was found in.
    src_line: Line number where orig_json was found.
    orig_json: An iterable of clippy entries in original json.

  Returns:
    The level of the diagnostic as a string (either error or warning).

  Raises:
    CargoClippyFieldError: Parsing failed to determine the level.
  """
  level = orig_json.get('level')
  if not level:
    level = orig_json.get('message', {}).get('level')
  if not level:
    raise CargoClippyFieldError(src, src_line, 'level')
  return level


def parse_message(
    src: Text, src_line: int, orig_json: Dict[Text, Any]) -> Text:
  """The formatted linter message for this diagnostic.

  Args:
    src: Name of the file orig_json was found in.
    src_line: Line number where orig_json was found.
    orig_json: An iterable of clippy entries in original json.

  Returns:
    The rendered message of the diagnostic.

  Raises:
    CargoClippyFieldError: Parsing failed to determine the message.
  """
  message = orig_json.get('message', {}).get('rendered')
  if message is None:
    raise CargoClippyFieldError(src, src_line, 'message')
  return message


def parse_diagnostics(
    src: Text, orig_jsons: Iterable[Text], git_repo: Text) -> ClippyDiagnostic:
  """Parses original JSON to find the fields of a Clippy Diagnostic.

  Args:
    src: Name of the file orig_json was found in.
    orig_jsons: An iterable of clippy entries in original json.
    git_repo: Base directory for git repo to strip out in diagnostics.

  Yields:
    A ClippyDiagnostic for orig_json.

  Raises:
    CargoClippyJSONError: if a diagnostic is not valid JSON.
    CargoClippyReasonError: if a diagnostic is missing a "reason" field.
    CargoClippyFieldError: if a field cannot be determined while parsing.
  """
  for src_line, orig_json in enumerate(orig_jsons):
    try:
      line_json = json.loads(orig_json)
    except json.decoder.JSONDecodeError:
      json_error = CargoClippyJSONError(src, src_line)
      logging.error(json_error)
      raise json_error

    # We pass the path to the package in a special JSON on the first line
    if src_line == 0:
      package_path = line_json.get('package_path')
      if not package_path:
        raise CargoClippyPackagePathError(src)
      package_path = resolve_path(package_path)
      continue

    # Clippy outputs several types of logs, as distinguished by the "reason"
    # field, but we only want to process "compiler-message" logs.
    reason = line_json.get('reason')
    if reason is None:
      reason_error = CargoClippyReasonError(src, src_line)
      logging.error(reason_error)
      raise reason_error
    if reason != 'compiler-message':
      continue

    locations = parse_locations(line_json, package_path, git_repo)
    level = parse_level(src, src_line, line_json)
    message = parse_message(src, src_line, line_json)

    # TODO(ryanbeltran): Export suggested replacements
    yield ClippyDiagnostic(locations, level, message)


def parse_files(input_dir: Text, git_repo: Text) -> Iterable[ClippyDiagnostic]:
  """Gets all compiler-message lints from all the input files in input_dir.

  Args:
    input_dir: path to directory to scan for files
    git_repo: Base directory for git repo to strip out in diagnostics.

  Yields:
    Clippy Diagnostics objects found in files in the input directory
  """
  for root_path, _, file_names in os.walk(input_dir):
    for file_name in file_names:
      file_path = os.path.join(root_path, file_name)
      with open(file_path, encoding='utf-8') as clippy_file:
        yield from parse_diagnostics(file_path, clippy_file, git_repo)


def filter_diagnostics(
    diags: Iterable[ClippyDiagnostic]) -> Iterable[ClippyDiagnostic]:
  """Filters diagnostics and validates schemas."""
  for diag in diags:
    # ignore redundant messages: "aborting due to previous error..."
    if 'aborting due to previous error' in diag.message:
      continue
    # findings with no location are never useful
    if not diag.locations:
      continue
    yield diag


def get_arg_parser() -> commandline.ArgumentParser:
  """Creates an argument parser for this script."""
  parser = commandline.ArgumentParser(description=__doc__)
  parser.add_argument(
      '--output', required=True, type='path', help='File to write results to.')
  parser.add_argument(
      '--clippy-json-dir',
      type='path',
      help='Directory where clippy outputs were previously written to.')
  parser.add_argument(
      '--git-repo-path',
      type='path',
      default='',
      help='Base directory for git repo to strip out in diagnostics.')
  return parser


def main(argv: List[str]) -> None:
  cros_build_lib.AssertInsideChroot()

  logging.basicConfig()

  parser = get_arg_parser()
  opts = parser.parse_args(argv)
  opts.Freeze()

  input_dir = resolve_path(opts.clippy_json_dir)
  output_path = resolve_path(opts.output)
  git_repo = opts.git_repo_path

  diagnostics = filter_diagnostics(parse_files(input_dir, git_repo))
  with open(output_path, 'w', encoding='utf-8') as output_file:
    output_file.writelines(f'{diag}\n' for diag in diagnostics)
