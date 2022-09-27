#!/usr/bin/env python3
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Generate tree for working with refs/meta/config.

# To checkout refs/meta/config for all projects in the chromium GoB:
$ ./gob-meta-config-checkout.py -o ~/src/gob/chromium chromium

Rerunning the command on an existing output will refresh & update new projects.
"""

import argparse
import configparser
import contextlib
import functools
import io
import multiprocessing
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable, Iterable, List, Tuple
import urllib.request


assert sys.version_info >= (3, 7), 'Python 3.7+ required'


# This uses PEP8 4-space indent.
# pylint: disable=bad-indentation


CSI_ERASE_LINE = '\x1b[2K'


class GitConfig:
    """Access to .git/config settings."""

    def __init__(self, path: Path):
        self.path = path / '.git' / 'config'
        self.config = configparser.ConfigParser()
        self.read()

    def read(self):
        if self.path.exists():
            self.config.read(self.path)

    @staticmethod
    def key_to_section_option(key: str) -> Tuple[str, str]:
        section, option = key.split('.', 1)
        if section in {'remote', 'branch'}:
            qual, option = option.split('.', 1)
            section = f'{section} "{qual}"'
        return (section, option)

    def get(self, key: str):
        return self.config.get(*self.key_to_section_option(key))

    def set(self, key: str, value: str):
        run(['git', 'config', key, value], cwd=self.path.parent)
        self.read()

    def exists(self, key: str) -> bool:
        return self.config.has_option(*self.key_to_section_option(key))

    def setdefault(self, key: str, value: str):
        if not self.exists(key):
            self.set(key, value)


def run(cmd: List[str], auto_output=True, **kwargs):
    """Hook around subprocess.run for logging."""
    cwd = kwargs.get('cwd')
    assert cwd is not None, f'{cmd} missing cwd='
    # print(cmd, f'cwd={cwd}', flush=True)
    kwargs.setdefault('check', True)
    if 'capture_output' not in kwargs:
        kwargs.setdefault('stdout', subprocess.PIPE)
        kwargs.setdefault('stderr', subprocess.STDOUT)
    kwargs.setdefault('encoding', 'utf-8')
    ret = subprocess.run(cmd, **kwargs)  # pylint: disable=subprocess-run-check
    if auto_output and not kwargs.get('capture_output'):
        output = ret.stdout.strip()
        if output and 'using GSLB fallback backend' not in output:
            print(output)
    return ret


def get_hook_commit_msg(opts: argparse.Namespace) -> Path:
    """Get a cache of the commit-msg hook."""
    commit_msg = opts.output / '.commit-msg'
    if not commit_msg.exists():
        opts.output.mkdir(0o755, exist_ok=True)
        response = urllib.request.urlopen(
            'https://gerrit-review.googlesource.com/tools/hooks/commit-msg')
        commit_msg.write_bytes(response.read())
        commit_msg.chmod(0o755)
    return commit_msg


def create_repo(opts: argparse.Namespace, repo: Path):
    """Initialize |repo|."""
    path = opts.output / repo
    gitdir = path / '.git'
    hooks = gitdir / 'hooks'
    commit_msg = hooks / 'commit-msg'
    head = gitdir / 'HEAD'

    # Only run the init steps once.
    if commit_msg.exists():
        run(['git', 'pull', '-q'], cwd=path, auto_output=False)
        return

    path.mkdir(parents=True, exist_ok=True)
    if not gitdir.exists():
        run(['git', 'init', '-q', path], cwd=path)
    for hook in hooks.glob('*.sample'):
        hook.unlink()
    config = GitConfig(path)
    uri = f'rpc://{opts.gob}/{repo}'
    if not config.exists('remote.origin.url'):
        run(['git', 'remote', 'add', 'origin', uri], cwd=path)
    config.set('remote.origin.fetch',
               '+refs/meta/config:refs/remotes/origin/meta-config')
    if head.read_text().strip() != 'ref: refs/heads/meta-config':
        result = run(['git', 'fetch', '-q', 'origin'], cwd=path, check=False,
                     auto_output=False)
        if result.returncode:
            # 128 means refs/heads/meta-config doesn't exist which is OK?
            if result.returncode != 128:
                result.check_returncode()
            return
    run(['git', 'checkout', '-q', '-b', 'meta-config',
         'remotes/origin/meta-config'], cwd=path)
    if not config.exists('remote.review.url'):
        config.set('remote.review.url', uri)
    if not config.exists('remote.review.push'):
        config.set('remote.review.push', 'HEAD:refs/for/refs/meta/config')

    # Do this last as a marker that we finished initializing.
    if not commit_msg.exists():
        commit_msg.symlink_to(get_hook_commit_msg(opts))


def capture_output(func: Callable, repo: Path):
    output = io.StringIO()
    with contextlib.redirect_stderr(sys.stdout):
        with contextlib.redirect_stdout(output):
            try:
                func(repo)
            except subprocess.CalledProcessError as e:
                output.write(f'\n{repo}: {e.cmd}={e.returncode}: {e.stdout}')
            except Exception as e:
                output.write(f'\n{repo}: Exception: {e}')
    return (repo, output.getvalue())


def get_repos(gob: str) -> Iterable[Path]:
    """Get all the repos on this host."""
    result = run(['gob-ctl', 'list', gob], cwd='/', encoding='utf-8',
                 capture_output=True)
    # Pull out lines like:
    #  repo: "chromium/chromiumos/platform2"
    REPO_RE = re.compile('^ *repo: *"(.*)"')
    for line in result.stdout.splitlines():
        m = REPO_RE.match(line)
        if m:
            repo = m.group(1)
            assert repo.startswith(f'{gob}/')
            yield Path(repo[len(gob) + 1:])


def get_parser() -> argparse.ArgumentParser:
    """Get CLI parser."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '-j', '--jobs', type=int, default=min(8, multiprocessing.cpu_count()),
        help='Number of jobs to run in parallel (default: %(default)s)')
    parser.add_argument(
        '--output', type=Path,
        help='The root directory to write to')
    parser.add_argument('gob', help='The GoB hostname')
    return parser


def main(argv):
    """The main entry point for scripts."""
    parser = get_parser()
    opts = parser.parse_args(argv)
    if not opts.output:
        opts.output = Path.cwd() / opts.gob

    # Cache the hook once.
    get_hook_commit_msg(opts)

    func = functools.partial(create_repo, opts)
    repos = sorted(get_repos(opts.gob))
    capture = functools.partial(capture_output, func)
    pool = multiprocessing.Pool(opts.jobs)

    finished = 0
    num_repos = len(repos)
    for (repo, output) in pool.imap_unordered(capture, repos):
        finished += 1
        print(CSI_ERASE_LINE + '\r', end='')
        print(f'[{finished}/{num_repos}] {repo}', output,
              end='\n' if output else '', flush=not output)
    print()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
