# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for tricium_clang_tidy.py."""

import io
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import tempfile
from typing import NamedTuple
from unittest import mock

from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.scripts import tricium_clang_tidy


class Replacement(NamedTuple):
  """A YAML `tricium_clang_tidy.TidyReplacement`.

  The data contained in YAML is slightly different than what `TidyReplacement`s
  carry.
  """
  file_path: str
  text: str
  offset: int
  length: int


class Note(NamedTuple):
  """A clang-tidy `note` from the YAML file."""
  message: str
  file_path: str
  file_offset: int


def default_tidy_diagnostic(file_path='/tidy/file.c',
                            line_number=1,
                            diag_name='${diag_name}',
                            message='${message}',
                            replacements=(),
                            expansion_locs=()):
  """Creates a TidyDiagnostic with reasonable defaults.

  Defaults here and yaml_diagnostic are generally intended to match where
  possible.
  """
  return tricium_clang_tidy.TidyDiagnostic(
      file_path=file_path,
      line_number=line_number,
      diag_name=diag_name,
      message=message,
      replacements=replacements,
      expansion_locs=expansion_locs)


def yaml_diagnostic(name='${diag_name}',
                    message='${message}',
                    file_path='/tidy/file.c',
                    file_offset=1,
                    replacements=(),
                    notes=()):
  """Creates a diagnostic serializable as YAML with reasonable defaults."""
  result = {
      'DiagnosticName': name,
      'DiagnosticMessage': {
          'Message': message,
          'FilePath': file_path,
          'FileOffset': file_offset,
      },
  }

  if replacements:
    result['DiagnosticMessage']['Replacements'] = [{
        'FilePath': x.file_path,
        'Offset': x.offset,
        'Length': x.length,
        'ReplacementText': x.text,
    } for x in replacements]

  if notes:
    result['Notes'] = [{
        'Message': x.message,
        'FilePath': x.file_path,
        'FileOffset': x.file_offset,
    } for x in notes]

  return result


def mocked_nop_realpath(f):
  """Mocks os.path.realpath to just return its argument."""

  @mock.patch.object(os.path, 'realpath')
  @mock.patch.object(Path, 'resolve')
  def inner(self, replace_mock, realpath_mock, *args, **kwargs):
    """Mocker for realpath."""
    identity = lambda x: x
    realpath_mock.side_effect = identity
    replace_mock.side_effect = identity
    return f(self, *args, **kwargs)

  return inner


def mocked_readonly_open(contents=None, default=None):
  """Mocks out open() so it always returns things from |contents|.

  Writing to open'ed files is not supported.

  Args:
    contents: a |dict| mapping |file_path| => file_contents.
    default: a default string to return if the given |file_path| doesn't
      exist in |contents|.

  Returns:
    |contents[file_path]| if it exists; otherwise, |default|.

  Raises:
    If |default| is None and |contents[file_path]| does not exist, this will
    raise a |ValueError|.
  """

  if contents is None:
    contents = {}

  def inner(f):
    """mocked_open impl."""

    @mock.mock_open()
    def inner_inner(self, open_mock, *args, **kwargs):
      """the impl of mocked_readonly_open's impl!"""

      def get_data(file_path, mode='r', encoding=None):
        """the impl of the impl of mocked_readonly_open's impl!!"""
        data = contents.get(file_path, default)
        if data is None:
          raise ValueError('No %r file was found; options were %r' %
                           (file_path, sorted(contents.keys())))

        assert mode == 'r', f"File mode {mode} isn't supported."
        if encoding is None:
          return io.BytesIO(data)
        return io.StringIO(data)

      open_mock.side_effect = get_data

      def get_data_stream(file_path):
        return io.StringIO(get_data(file_path))

      open_mock.side_effect = get_data_stream
      return f(self, *args, **kwargs)

    return inner_inner

  return inner


class TriciumClangTidyTests(cros_test_lib.MockTestCase):
  """Various tests for tricium support."""

  def test_tidy_diagnostic_path_normalization(self):
    expanded_from = tricium_clang_tidy.TidyExpandedFrom(
        file_path=Path('/old2/foo'),
        line_number=2,
    )
    diag = default_tidy_diagnostic(
        file_path=Path('/old/foo'),
        expansion_locs=(expanded_from,),
    )

    normalized = diag.normalize_paths_to('/new')
    self.assertEqual(
        normalized,
        diag._replace(
            file_path=Path('../old/foo'),
            expansion_locs=(expanded_from._replace(
                file_path=Path('../old2/foo')),),
        ),
    )

  def test_line_offest_map_works(self):
    # (input_char, line_number_of_char, line_offset_of_char)
    line_offset_pairs = [
        ('a', 1, 0),
        ('b', 1, 1),
        ('\n', 1, 2),
        ('c', 2, 0),
        ('\n', 2, 1),
        ('\n', 3, 0),
        ('d', 4, 0),
        ('', 4, 1),
        ('', 4, 2),
    ]
    text = tricium_clang_tidy.LineOffsetMap.for_text(''.join(
        x for x, _, _ in line_offset_pairs))
    for offset, (_, line_number, line_offset) in enumerate(line_offset_pairs):
      self.assertEqual(text.get_line_number(offset), line_number)
      self.assertEqual(text.get_line_offset(offset), line_offset)

  def test_package_ebuild_resolution(self):
    run_mock = self.StartPatcher(cros_test_lib.RunCommandMock())
    run_mock.SetDefaultCmdResult(stdout='${package1_ebuild}\n')
    ebuilds = tricium_clang_tidy.resolve_package_ebuilds(
        '${board}',
        [
            'package1',
            'package2.ebuild',
        ],
    )

    run_mock.assertCommandContains(['equery-${board}', 'w', 'package1'],
                                   check=True,
                                   stdout=subprocess.PIPE,
                                   encoding='utf-8')
    self.assertEqual(ebuilds, ['${package1_ebuild}', 'package2.ebuild'])

  @mocked_readonly_open(default='')
  def test_parse_tidy_invocation_returns_exception_on_error(
      self, read_file_mock):
    oh_no = ValueError('${oh_no}!')
    read_file_mock.side_effect = oh_no
    result = tricium_clang_tidy.parse_tidy_invocation(
        Path('/some/file/that/doesnt/exist.json'))
    self.assertIn(str(oh_no), str(result))

  @mocked_readonly_open({
      '/file/path.json':
          json.dumps({
              'exit_code': 1,
              'executable': '${clang_tidy}',
              'args': ['foo', 'bar'],
              'lint_target': '${target}',
              'stdstreams': 'brrrrrrr',
              'wd': '/path/to/wd',
          }),
      # |yaml.dumps| doesn't exist, but json parses cleanly as yaml, so...
      '/file/path.yaml':
          json.dumps({
              'Diagnostics': [
                  yaml_diagnostic(
                      name='some-diag',
                      message='${message}',
                      file_path='',
                  ),
              ]
          }),
  })
  def test_parse_tidy_invocation_functions_on_success(self):
    result = tricium_clang_tidy.parse_tidy_invocation('/file/path.json')
    # If we got an |Exception|, print it out.
    self.assertNotIsInstance(result, tricium_clang_tidy.Error)
    meta, info = result
    self.assertEqual(
        meta,
        tricium_clang_tidy.InvocationMetadata(
            exit_code=1,
            invocation=['${clang_tidy}', 'foo', 'bar'],
            lint_target='${target}',
            stdstreams='brrrrrrr',
            wd='/path/to/wd',
        ),
    )

    self.assertEqual(
        info,
        [
            default_tidy_diagnostic(
                diag_name='some-diag',
                message='${message}',
                file_path='',
            ),
        ],
    )

  @mocked_nop_realpath
  @mocked_readonly_open(default='')
  def test_parse_fixes_file_absolutizes_paths(self):
    results = tricium_clang_tidy.parse_tidy_fixes_file(
        '/tidy', {
            'Diagnostics': [
                yaml_diagnostic(file_path='foo.c'),
                yaml_diagnostic(file_path='/tidy/bar.c'),
                yaml_diagnostic(file_path=''),
            ],
        })
    file_paths = [x.file_path for x in results]
    self.assertEqual(file_paths, ['/tidy/foo.c', '/tidy/bar.c', ''])

  @mocked_nop_realpath
  @mocked_readonly_open({
      '/tidy/foo.c': '',
      '/tidy/foo.h': 'a\n\n',
  })
  def test_parse_fixes_file_interprets_offsets_correctly(self):
    results = tricium_clang_tidy.parse_tidy_fixes_file(
        '/tidy', {
            'Diagnostics': [
                yaml_diagnostic(file_path='/tidy/foo.c', file_offset=1),
                yaml_diagnostic(file_path='/tidy/foo.c', file_offset=2),
                yaml_diagnostic(file_path='/tidy/foo.h', file_offset=1),
                yaml_diagnostic(file_path='/tidy/foo.h', file_offset=2),
                yaml_diagnostic(file_path='/tidy/foo.h', file_offset=3),
            ],
        })
    file_locations = [(x.file_path, x.line_number) for x in results]
    self.assertEqual(file_locations, [
        ('/tidy/foo.c', 1),
        ('/tidy/foo.c', 1),
        ('/tidy/foo.h', 1),
        ('/tidy/foo.h', 2),
        ('/tidy/foo.h', 3),
    ])

  @mocked_nop_realpath
  @mocked_readonly_open({'/tidy/foo.c': 'a \n\n'})
  def test_parse_fixes_file_handles_replacements(self):
    results = list(
        tricium_clang_tidy.parse_tidy_fixes_file(
            '/tidy', {
                'Diagnostics': [
                    yaml_diagnostic(
                        file_path='/tidy/foo.c',
                        file_offset=1,
                        replacements=[
                            Replacement(
                                file_path='foo.c',
                                text='whee',
                                offset=2,
                                length=2,
                            ),
                        ],
                    ),
                ],
            }))
    self.assertEqual(len(results), 1, results)
    self.assertEqual(
        results[0].replacements,
        (tricium_clang_tidy.TidyReplacement(
            new_text='whee',
            start_line=1,
            end_line=3,
            start_char=2,
            end_char=0,
        ),),
    )

  @mocked_nop_realpath
  @mocked_readonly_open({'/whee.c': '', '/whee.h': '\n\n'})
  def test_parse_fixes_file_handles_macro_expansions(self):
    results = list(
        tricium_clang_tidy.parse_tidy_fixes_file(
            '/tidy', {
                'Diagnostics': [
                    yaml_diagnostic(
                        file_path='/whee.c',
                        file_offset=1,
                        notes=[
                            Note(
                                message='not relevant',
                                file_path='/whee.c',
                                file_offset=1,
                            ),
                            Note(
                                message='expanded from macro "Foo"',
                                file_path='/whee.h',
                                file_offset=9,
                            ),
                        ],
                    ),
                ],
            }))
    self.assertEqual(len(results), 1, results)
    self.assertEqual(
        results[0].expansion_locs,
        (tricium_clang_tidy.TidyExpandedFrom(
            file_path='/whee.h',
            line_number=3,
        ),),
    )

  @mock.patch.object(Path, 'glob')
  @mock.patch.object(tricium_clang_tidy, 'parse_tidy_invocation')
  def test_collect_lints_functions(self, parse_invocation_mock, glob_mock):
    glob_mock.return_value = ('/lint/foo.json', '/lint/bar.json')

    diag_1 = default_tidy_diagnostic()
    diag_2 = diag_1._replace(line_number=diag_1.line_number + 1)
    diag_3 = diag_2._replace(line_number=diag_2.line_number + 1)

    # Because we want to test unique'ing, ensure these aren't equal.
    all_diags = [diag_1, diag_2, diag_3]
    self.assertEqual(sorted(all_diags), sorted(set(all_diags)))

    per_file_lints = {
        '/lint/foo.json': {diag_1, diag_2},
        '/lint/bar.json': {diag_2, diag_3},
    }

    def parse_invocation_side_effect(json_file):
      self.assertIn(json_file, per_file_lints)
      meta = mock.Mock()
      meta.exit_code = 0
      return meta, per_file_lints[json_file]

    parse_invocation_mock.side_effect = parse_invocation_side_effect

    with multiprocessing.pool.ThreadPool(1) as yaml_pool:
      lints = tricium_clang_tidy.collect_lints(Path('/lint'), yaml_pool)

    self.assertEqual(set(all_diags), lints)

  def test_filter_tidy_lints_filters_nothing_by_default(self):
    basis = default_tidy_diagnostic()
    diag2 = default_tidy_diagnostic(line_number=basis.line_number + 1)
    diags = [basis, diag2]
    diags.sort()

    self.assertEqual(
        diags,
        tricium_clang_tidy.filter_tidy_lints(
            only_files=None,
            git_repo_base=None,
            diags=diags,
        ),
    )

  def test_filter_tidy_lints_filters_paths_outside_of_only_files(self):
    in_only_files = default_tidy_diagnostic(file_path='foo.c')
    out_of_only_files = default_tidy_diagnostic(file_path='bar.c')
    self.assertEqual(
        [in_only_files],
        tricium_clang_tidy.filter_tidy_lints(
            only_files={Path('foo.c')},
            git_repo_base=None,
            diags=[in_only_files, out_of_only_files],
        ),
    )

  def test_filter_tidy_lints_normalizes_to_git_repo_baes(self):
    git = default_tidy_diagnostic(file_path='/git/foo.c')
    nogit = default_tidy_diagnostic(file_path='/nogit/bar.c')
    self.assertEqual(
        [git.normalize_paths_to('/git')],
        tricium_clang_tidy.filter_tidy_lints(
            only_files=None,
            git_repo_base=Path('/git'),
            diags=[git, nogit],
        ),
    )

  def test_filter_tidy_lints_normalizes_and_restricts_properly(self):
    git_and_only = default_tidy_diagnostic(file_path='/git/foo.c')
    git_and_noonly = default_tidy_diagnostic(file_path='/git/bar.c')
    self.assertEqual(
        [git_and_only.normalize_paths_to('/git')],
        tricium_clang_tidy.filter_tidy_lints(
            only_files={Path('/git/foo.c')},
            git_repo_base=Path('/git'),
            diags=[git_and_only, git_and_noonly],
        ),
    )

  @mock.patch.object(osutils, 'CopyDirContents')
  @mock.patch.object(osutils, 'SafeMakedirs')
  def test_lint_generation_functions(self, safe_makedirs_mock,
                                     copy_dir_contents_mock):
    run_mock = self.StartPatcher(cros_test_lib.PopenMock())
    run_mock.SetDefaultCmdResult()

    # Mock mkdtemp last, since PopenMock() makes a tempdir.
    mkdtemp_mock = self.PatchObject(tempfile, 'mkdtemp')
    mkdtemp_path = '/path/to/temp/dir'
    mkdtemp_mock.return_value = mkdtemp_path
    with mock.patch.object(osutils, 'RmDir') as rmdir_mock:
      dir_name = str(
          tricium_clang_tidy.generate_lints('${board}', '/path/to/the.ebuild'))
    self.assertEqual(mkdtemp_path, dir_name)

    rmdir_mock.assert_called_with(
        tricium_clang_tidy.LINT_BASE, ignore_missing=True, sudo=True)
    safe_makedirs_mock.assert_called_with(
        tricium_clang_tidy.LINT_BASE, 0o777, sudo=True)

    desired_env = dict(os.environ)
    desired_env['WITH_TIDY'] = 'tricium'
    run_mock.assertCommandContains(
        ['ebuild-${board}', '/path/to/the.ebuild', 'clean', 'compile'],
        env=desired_env)

    copy_dir_contents_mock.assert_called_with(tricium_clang_tidy.LINT_BASE,
                                              dir_name)
