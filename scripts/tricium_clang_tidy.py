# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs clang-tidy across the given files, dumping diagnostics to a JSON file.

This script is intended specifically for use with Tricium (go/tricium).
"""

# From an implementation perspective, it's good to note that this script
# cooperates with the toolchain's compiler wrapper. In particular,
# ${cros}/src/third_party/toolchain-utils/compiler_wrapper/clang_tidy_flag.go.
#
# When |WITH_TIDY=tricium| is set and the wrapper (which is already $CC/$CXX)
# is invoked, $CC will invoke clang-tidy _as well_ as the regular compiler.
# This clang-tidy invocation will result in a few files being dumped to
# |LINT_BASE| (below):
#   - "${LINT_BASE}/some-prefix.yaml" -- a YAML file that represents
#     clang-tidy's diagnostics for the file the compiler was asked to build
#   - "${LINT_BASE}/some-prefix.json" -- metadata about how the above YAML file
#     was generated, including clang-tidy's exit code, stdout, etc. See
#     |InvocationMetadata| below.
#
# As one might expect, the compiler wrapper writes the JSON file only after
# clang-tidy is done executing.
#
# This directory might contain other files, as well; these are ignored by this
# script.

import bisect
import json
import logging
import multiprocessing
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Set, Tuple, Union

import yaml  # pylint: disable=import-error

from chromite.lib import build_target_lib
from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import portage_util
from chromite.lib import workon_helper


# The directory under which the compiler wrapper stores clang-tidy reports.
LINT_BASE = Path('/tmp/linting_output/clang-tidy')


class TidyReplacement(NamedTuple):
  """Represents a replacement emitted by clang-tidy.

  File path is omitted, since these are intended to be associated with
  TidyDiagnostics with identical paths.
  """
  new_text: str
  start_line: int
  end_line: int
  start_char: int
  end_char: int


class TidyExpandedFrom(NamedTuple):
  """Represents a macro expansion.

  When a diagnostic is inside of a macro expansion, clang-tidy emits
  information about where said macro was expanded from. |TidyDiagnostic|s will
  have one |TidyExpandedFrom| for each level of this expansion.
  """
  file_path: Path
  line_number: int

  def to_dict(self) -> Dict[str, Any]:
    """Converts this |TidyExpandedFrom| to a dict serializeable as JSON."""
    return {
        'file_path': self.file_path.as_posix(),
        'line_number': self.line_number,
    }


class Error(Exception):
  """Base error class for tricium-clang-tidy."""


class ClangTidyParseError(Error):
  """Raised when clang-tidy parsing jobs fail."""

  def __init__(self, failed_jobs: int, total_jobs: int):
    super().__init__(f'{failed_jobs}/{total_jobs} parse jobs failed')
    self.failed_jobs = failed_jobs
    self.total_jobs = total_jobs


class TidyDiagnostic(NamedTuple):
  """A diagnostic emitted by clang-tidy.

  Note that we shove these in a set for cheap deduplication, and we sort based
  on the natural element order here. Sorting is mostly just for
  deterministic/pretty output.
  """
  file_path: Path
  line_number: int
  diag_name: str
  message: str
  replacements: Tuple[TidyReplacement]
  expansion_locs: Tuple[TidyExpandedFrom]

  def normalize_paths_to(self, where: str) -> 'TidyDiagnostic':
    """Creates a new TidyDiagnostic with all paths relative to |where|."""
    return self._replace(
        # Use relpath because Path.relative_to requires that `self` is rooted
        # at `where`.
        file_path=Path(os.path.relpath(self.file_path, where)),
        expansion_locs=tuple(
            x._replace(file_path=Path(os.path.relpath(x.file_path, where)))
            for x in self.expansion_locs))

  def to_dict(self) -> Dict[str, Any]:
    """Converts this |TidyDiagnostic| to a dict serializeable as JSON."""
    return {
        'file_path': self.file_path.as_posix(),
        'line_number': self.line_number,
        'diag_name': self.diag_name,
        'message': self.message,
        'replacements': [x._asdict() for x in self.replacements],
        'expansion_locs': [x.to_dict() for x in self.expansion_locs],
    }


class ClangTidySchemaError(Error):
  """Raised when we encounter malformed YAML."""

  def __init__(self, err_msg: str):
    super().__init__(err_msg)
    self.err_msg = err_msg


class LineOffsetMap:
  """Convenient API to turn offsets in a file into line numbers."""

  def __init__(self, newline_locations: Iterable[int]):
    line_starts = [x + 1 for x in newline_locations]
    # The |bisect| logic in |get_line_number|/|get_line_offset| gets a bit
    # complicated around the first and last lines of a file. Adding boundaries
    # here removes some complexity from those implementations.
    line_starts.append(0)
    line_starts.append(sys.maxsize)
    line_starts.sort()

    assert line_starts[0] == 0, line_starts[0]
    assert line_starts[1] != 0, line_starts[1]
    assert line_starts[-2] < sys.maxsize, line_starts[-2]
    assert line_starts[-1] == sys.maxsize, line_starts[-1]

    self._line_starts = line_starts

  def get_line_number(self, char_number: int) -> int:
    """Given a char offset into a file, returns its line number."""
    assert 0 <= char_number < sys.maxsize, char_number
    return bisect.bisect_right(self._line_starts, char_number)

  def get_line_offset(self, char_number: int) -> int:
    """Given a char offset into a file, returns its column number."""
    assert 0 <= char_number < sys.maxsize, char_number
    line_start_index = bisect.bisect_right(self._line_starts, char_number) - 1
    return char_number - self._line_starts[line_start_index]

  @staticmethod
  def for_text(data: str) -> 'LineOffsetMap':
    """Creates a LineOffsetMap for the given string."""
    return LineOffsetMap(m.start() for m in re.finditer(r'\n', data))


def parse_tidy_fixes_file(tidy_invocation_dir: Path,
                          yaml_data: Any) -> Iterable[TidyDiagnostic]:
  """Parses a clang-tidy YAML file.

  Args:
    yaml_data: The parsed YAML data from clang-tidy's fixits file.
    tidy_invocation_dir: The directory clang-tidy was run in.

  Returns:
    A generator of |TidyDiagnostic|s.
  """
  assert tidy_invocation_dir.is_absolute(), tidy_invocation_dir

  if yaml_data is None:
    return

  # A cache of file_path => LineOffsetMap so we only need to load offsets once
  # per file per |parse_tidy_fixes_file| invocation.
  cached_line_offsets = {}

  def get_line_offsets(file_path: Optional[Path]) -> LineOffsetMap:
    """Gets a LineOffsetMap for the given |file_path|."""
    assert not file_path or file_path.is_absolute(), file_path

    if file_path in cached_line_offsets:
      return cached_line_offsets[file_path]

    # Sometimes tidy will give us empty file names; they don't map to any file,
    # and are generally issues it has with CFLAGS, etc. File offsets don't
    # matter in those, so use an empty map.
    if file_path:
      offsets = LineOffsetMap.for_text(file_path.read_text(encoding='utf-8'))
    else:
      offsets = LineOffsetMap(())
    cached_line_offsets[file_path] = offsets
    return offsets

  # Rarely (e.g., in the case of missing |#include|s, clang will emit relative
  # file paths for diagnostics. This fixes those.
  def makeabs(file_path: str) -> Path:
    """Resolves a |file_path| emitted by clang-tidy to an absolute path."""
    if not file_path:
      return None
    path = Path(file_path)
    if not path.is_absolute():
      path = tidy_invocation_dir / path
    return path.resolve()

  try:
    for diag in yaml_data['Diagnostics']:
      message = diag['DiagnosticMessage']
      file_path = message['FilePath']

      absolute_file_path = makeabs(file_path)
      line_offsets = get_line_offsets(absolute_file_path)

      replacements = []
      for replacement in message.get('Replacements', ()):
        replacement_file_path = makeabs(replacement['FilePath'])

        # FIXME(gbiv): This happens in practice with things like
        # hicpp-member-init. Supporting it should be simple, but I'd like to
        # get the basics running first.
        if replacement_file_path != absolute_file_path:
          logging.warning(
              "Replacement %r wasn't in original file %r (diag: %r)",
              replacement_file_path, file_path, diag)
          continue

        start_offset = replacement['Offset']
        end_offset = start_offset + replacement['Length']
        replacements.append(
            TidyReplacement(
                new_text=replacement['ReplacementText'],
                start_line=line_offsets.get_line_number(start_offset),
                end_line=line_offsets.get_line_number(end_offset),
                start_char=line_offsets.get_line_offset(start_offset),
                end_char=line_offsets.get_line_offset(end_offset),
            ))

      expansion_locs = []
      for note in diag.get('Notes', ()):
        if not note['Message'].startswith('expanded from macro '):
          continue

        absolute_note_path = makeabs(note['FilePath'])
        note_offsets = get_line_offsets(absolute_note_path)
        expansion_locs.append(
            TidyExpandedFrom(
                file_path=absolute_note_path,
                line_number=note_offsets.get_line_number(note['FileOffset']),
            ))

      yield TidyDiagnostic(
          diag_name=diag['DiagnosticName'],
          message=message['Message'],
          file_path=absolute_file_path,
          line_number=line_offsets.get_line_number(message['FileOffset']),
          replacements=tuple(replacements),
          expansion_locs=tuple(expansion_locs),
      )
  except KeyError as k:
    key_name = k.args[0]
    raise ClangTidySchemaError(f'Broken yaml: missing key {key_name!r}')


# Represents metadata about a clang-tidy invocation.
class InvocationMetadata(NamedTuple):
  """Metadata describing a singular invocation of clang-tidy."""
  exit_code: int
  invocation: List[str]
  lint_target: str
  stdstreams: str
  wd: str


class ExceptionData:
  """Info about an exception that can be sent across processes."""

  def __init__(self):
    """Builds an instance; only intended to be called from `except` blocks."""
    self._str = traceback.format_exc()

  def __str__(self):
    return self._str


def parse_tidy_invocation(
    json_file: Path,
) -> Union[ExceptionData, Tuple[InvocationMetadata, List[TidyDiagnostic]]]:
  """Parses a clang-tidy invocation result based on a JSON file.

  This is intended to be run in a separate process, which Exceptions and
  locking and such work notoriously poorly over, so it's never intended to
  |raise| (except under a KeyboardInterrupt or similar).

  Args:
    json_file: The JSON invocation metadata file to parse.

  Returns:
    An |ExceptionData| instance on failure. On success, it returns a
    (InvocationMetadata, [TidyLint]).
  """
  try:
    assert json_file.suffix == '.json', json_file

    with json_file.open(encoding='utf-8') as f:
      raw_meta = json.load(f)

    meta = InvocationMetadata(
        exit_code=raw_meta['exit_code'],
        invocation=[raw_meta['executable']] + raw_meta['args'],
        lint_target=raw_meta['lint_target'],
        stdstreams=raw_meta['stdstreams'],
        wd=raw_meta['wd'],
    )

    raw_crash_output = raw_meta.get('crash_output')
    if raw_crash_output:
      crash_reproducer_path = raw_crash_output['crash_reproducer_path']
      output = raw_crash_output['stdstreams']
      raise RuntimeError(f"""\
Clang-tidy apparently crashed; dumping lots of invocation info:
## Tidy JSON file target: {json_file}
## Invocation: {meta.invocation}
## Target: {meta.lint_target}
## Crash reproducer is at: {crash_reproducer_path}
## Output producing reproducer:
{output}
## Output from the crashing invocation:
{meta.stdstreams}
""")

    yaml_file = json_file.with_suffix('.yaml')
    # If this happened, clang-tidy was probably killed. Dump output as part of
    # the exception so it's easier to reason about what happened.
    if not yaml_file.exists():
      raise RuntimeError("clang-tidy didn't produce an output file for "
                         f'{json_file}. Output:\n{meta.stdstreams}')

    with yaml_file.open('rb') as f:
      yaml_data = yaml.safe_load(f)
    return meta, list(parse_tidy_fixes_file(Path(meta.wd), yaml_data))
  except Exception:
    return ExceptionData()


def generate_lints(board: str, ebuild_path: str) -> Path:
  """Collects the lints for a given package on a given board.

  Args:
    board: the board to collect lints for.
    ebuild_path: the path to the ebuild to collect lints for.

  Returns:
    The path to a tmpdir that all of the lint YAML files (if any) will be in.
    This will also be populated by JSON files containing InvocationMetadata.
    The generation of this is handled by our compiler wrapper.
  """
  logging.info('Running lints for %r on board %r', ebuild_path, board)

  osutils.RmDir(LINT_BASE, ignore_missing=True, sudo=True)
  osutils.SafeMakedirs(LINT_BASE, 0o777, sudo=True)

  # FIXME(gbiv): |test| might be better here?
  result = cros_build_lib.run(
      [f'ebuild-{board}', ebuild_path, 'clean', 'compile'],
      check=False,
      print_cmd=True,
      extra_env={'WITH_TIDY': 'tricium'},
      capture_output=True,
      encoding='utf-8',
      errors='replace',
  )

  if result.returncode:
    status = f'failed with code {result.returncode}; output:\n{result.stdout}'
    log_fn = logging.warning
  else:
    status = 'succeeded'
    log_fn = logging.info

  log_fn('Running |ebuild| on %s %s', ebuild_path, status)
  lint_tmpdir = tempfile.mkdtemp(prefix='tricium_tidy')
  osutils.CopyDirContents(LINT_BASE, lint_tmpdir)
  return Path(lint_tmpdir)


def collect_lints(lint_tmpdir: Path,
                  yaml_pool: multiprocessing.Pool) -> Set[TidyDiagnostic]:
  """Collects the lints for a given directory filled with linting artifacts."""
  json_files = list(lint_tmpdir.glob('*.json'))
  pending_parses = yaml_pool.imap(parse_tidy_invocation, json_files)

  parses_failed = 0
  all_complaints = set()
  for path, parse in zip(json_files, pending_parses):
    if isinstance(parse, ExceptionData):
      parses_failed += 1
      logging.error('Parsing %r failed with an exception\n%s', path, parse)
      continue

    meta, complaints = parse
    if meta.exit_code:
      logging.warning(
          'Invoking clang-tidy on %r with flags %r exited with code %d; '
          'output:\n%s',
          meta.lint_target,
          meta.invocation,
          meta.exit_code,
          meta.stdstreams,
      )

    all_complaints.update(complaints)

  if parses_failed:
    raise ClangTidyParseError(parses_failed, len(json_files))

  return all_complaints


def setup_tidy(board: str, ebuild_list: List[portage_util.EBuild]):
  """Sets up to run clang-tidy on the given ebuilds for the given board."""
  packages = [x.package for x in ebuild_list]
  logging.info('Setting up to lint %r', packages)

  workon = workon_helper.WorkonHelper(
      build_target_lib.get_default_sysroot_path(board))
  workon.StopWorkingOnPackages(packages=[], use_all=True)
  workon.StartWorkingOnPackages(packages)

  # We're going to be hacking with |ebuild| later on, so having all
  # dependencies in place is necessary so one |ebuild| won't stomp on another.
  cmd = [
      f'emerge-{board}',
      '--onlydeps',
      # Since each `emerge` may eat up to `ncpu` cores, limit the maximum
      # concurrency we can get here to (arbitrarily) 8 jobs. Having
      # `configure`s and such run in parallel is nice.
      f'-j{min(8, multiprocessing.cpu_count())}',
  ]
  cmd += packages
  result = cros_build_lib.run(cmd, print_cmd=True, check=False)
  if result.returncode:
    logging.error('Setup failed with exit code %d; some lints may fail.',
                  result.returncode)


def run_tidy(board: str, ebuild_list: List[portage_util.EBuild],
             keep_dirs: bool,
             parse_errors_are_nonfatal: bool) -> Set[TidyDiagnostic]:
  """Runs clang-tidy on the given ebuilds for the given board.

  Returns the set of |TidyDiagnostic|s produced by doing so.
  """
  # Since we rely on build actions _actually_ running, we can't live with a
  # cache.
  osutils.RmDir(
      Path(build_target_lib.get_default_sysroot_path(
          board)) / 'var' / 'cache' / 'portage',
      ignore_missing=True,
      sudo=True,
  )

  results = set()
  # If clang-tidy dumps a lot of diags, it can take 1-10secs of CPU while
  # holding the GIL to |yaml.safe_load| on my otherwise-idle dev box.
  # |yaml_pool| lets us do this in parallel.
  with multiprocessing.pool.Pool() as yaml_pool:
    for ebuild in ebuild_list:
      lint_tmpdir = generate_lints(board, ebuild.ebuild_path)
      try:
        results |= collect_lints(lint_tmpdir, yaml_pool)
      except ClangTidyParseError:
        if not parse_errors_are_nonfatal:
          raise
        logging.exception('Working on %r', ebuild)
      finally:
        if keep_dirs:
          logging.info('Lints for %r are in %r', ebuild.ebuild_path,
                       lint_tmpdir)
        else:
          osutils.RmDir(lint_tmpdir, ignore_missing=True, sudo=True)
  return results


def resolve_package_ebuilds(board: str,
                            package_names: Iterable[str]) -> List[str]:
  """Figures out ebuild paths for the given package names."""

  def resolve_package(package_name_or_ebuild):
    """Resolves a single package name an ebuild path."""
    if package_name_or_ebuild.endswith('.ebuild'):
      return package_name_or_ebuild
    return cros_build_lib.run([f'equery-{board}', 'w', package_name_or_ebuild],
                              check=True,
                              stdout=subprocess.PIPE,
                              encoding='utf-8').stdout.strip()

  # Resolving ebuilds takes time. If we get more than one (like when I'm tesing
  # on 50 of them), parallelism speeds things up quite a bit.
  with multiprocessing.pool.ThreadPool() as pool:
    return pool.map(resolve_package, package_names)


def filter_tidy_lints(only_files: Optional[Set[Path]],
                      git_repo_base: Optional[Path],
                      diags: Iterable[TidyDiagnostic]) -> List[TidyDiagnostic]:
  """Transforms and filters the given TidyDiagnostics.

  Args:
    only_files: a set of file paths, or None; if this is not None, only
      |TidyDiagnostic|s in these files will be kept.
    git_repo_base: if not None, only files in the given directory will be kept.
      All paths of the returned diagnostics will be made relative to
      |git_repo_base|.
    diags: diagnostics to transform/filter.

  Returns:
    A sorted list of |TidyDiagnostic|s.
  """
  result_diags = []
  total_diags = 0

  for diag in diags:
    total_diags += 1

    if not diag.file_path:
      # Things like |-DFOO=1 -DFOO=2| can trigger diagnostics ("oh no you're
      # redefining |FOO| with a different value") in 'virtual' files; these
      # receive no name in clang.
      logging.info('Dropping diagnostic %r, since it has no associated file',
                   diag)
      continue

    file_path = Path(diag.file_path)
    if only_files and file_path not in only_files:
      continue

    if git_repo_base:
      if git_repo_base not in file_path.parents:
        continue
      diag = diag.normalize_paths_to(git_repo_base)

    result_diags.append(diag)

  logging.info('Dropped %d/%d diags', total_diags - len(result_diags),
               total_diags)

  result_diags.sort()
  return result_diags


def get_parser() -> commandline.ArgumentParser:
  """Creates an argument parser for this script."""
  parser = commandline.ArgumentParser(description=__doc__)
  parser.add_argument(
      '--output', required=True, type='path', help='File to write results to.')
  parser.add_argument(
      '--git-repo-base',
      type='path',
      help="Base directory of the git repo we're looking at. If specified, "
      'only diagnostics in files in this directory will be emitted. All '
      'diagnostic file paths will be made relative to this directory.')
  parser.add_argument('--board', required=True, help='Board to run under.')
  parser.add_argument(
      '--package',
      action='append',
      required=True,
      help='Package(s) to build and lint. Required.')
  parser.add_argument(
      '--keep-lint-dirs',
      action='store_true',
      help='Keep directories with tidy lints around; meant primarily for '
      'debugging.')
  parser.add_argument(
      '--nonfatal-parse-errors',
      action='store_true',
      help="Keep going even if clang-tidy's output is impossible to parse.")
  parser.add_argument(
      'file',
      nargs='*',
      type='path',
      help='File(s) to output lints for. If none are specified, this tool '
      'outputs all lints that clang-tidy emits after applying filtering '
      'from |--git-repo-base|, if applicable.')
  return parser


def main(argv: List[str]) -> None:
  cros_build_lib.AssertInsideChroot()
  parser = get_parser()
  opts = parser.parse_args(argv)
  opts.Freeze()

  only_files = {Path(f).resolve() for f in opts.file}

  git_repo_base = opts.git_repo_base
  if git_repo_base:
    git_repo_base = Path(opts.git_repo_base)
    if not (git_repo_base / '.git').exists():
      # This script doesn't strictly care if there's a .git dir there; more of
      # a smoke check.
      parser.error(f'Given git repo base ({git_repo_base}) has no .git dir')

  package_ebuilds = [
      portage_util.EBuild(x)
      for x in resolve_package_ebuilds(opts.board, opts.package)
  ]

  setup_tidy(opts.board, package_ebuilds)
  lints = filter_tidy_lints(
      only_files,
      git_repo_base,
      diags=run_tidy(opts.board, package_ebuilds, opts.keep_lint_dirs,
                     opts.nonfatal_parse_errors))

  osutils.WriteFile(
      opts.output,
      json.dumps({'tidy_diagnostics': [x.to_dict() for x in lints]}),
      atomic=True)
