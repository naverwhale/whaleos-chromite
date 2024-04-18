# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Run the right formatter on the specified files.

TODO: Support stdin & diffs.
"""

import collections
import difflib
import functools
import itertools
import logging
import os
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional

from chromite.cli import analyzers
from chromite.cli import command
from chromite.format import formatters
from chromite.lib import cros_build_lib
from chromite.lib import git
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib import path_util
from chromite.utils import path_filter
from chromite.utils.parser import shebang


# These are used in _BreakoutDataByTool, so add a constant to keep in sync.
_PYTHON_EXT = frozenset({"*.py", "*.pyi"})
_SHELL_EXT = frozenset({"*.sh"})

# Map file names to a tool function.
# NB: Order matters as earlier entries override later ones.
_TOOL_MAP = collections.OrderedDict(
    (
        # These are plain text files.
        (
            frozenset(
                {
                    ".clang-format",
                    ".gitignore",
                    ".gitmodules",
                    "COPYING*",
                    "LICENSE*",
                    "make.conf",
                    "make.defaults",
                    "package.accept_keywords",
                    "package.force",
                    "package.keywords",
                    "package.mask",
                    "package.provided",
                    "package.unmask",
                    "package.use",
                    "package.use.force",
                    "package.use.mask",
                    "use.force",
                    "use.mask",
                }
            ),
            (formatters.whitespace.Data,),
        ),
        # NB: Must come before *.conf rules below.
        (
            frozenset({"metadata/layout.conf"}),
            (formatters.portage_layout_conf.Data,),
        ),
        # TODO(build): Add a formatter for this.
        (frozenset({"OWNERS*"}), (formatters.whitespace.Data,)),
        (
            frozenset({"*.bazel", "*.bzl", "*.star", "BUILD", "WORKSPACE"}),
            (formatters.star.Data,),
        ),
        # Remember to change cros_lint to align supported extensions.
        # LINT.IfChange(cpp_extensions)
        (
            frozenset({"*.c", "*.cc", "*.cpp", "*.cxx", "*.h", "*.hh"}),
            (formatters.cpp.Data,),
        ),
        # LINT.ThenChange(cros_lint.py:cpp_extensions)
        (frozenset({"*.gn", "*.gni"}), (formatters.gn.Data,)),
        (frozenset({"*.go"}), (formatters.go.Data,)),
        (frozenset({"*.json", "*.jsonproto"}), (formatters.json.Data,)),
        # TODO(build): Add a formatter for this.
        (frozenset({"*.ebuild", "*.eclass"}), (formatters.whitespace.Data,)),
        # TODO(build): Add a formatter for this.
        (frozenset({"*.md"}), (formatters.whitespace.Data,)),
        # TODO(build): Add a formatter for this (minijail seccomp policies).
        (frozenset({"*.policy"}), (formatters.whitespace.Data,)),
        (frozenset({"*.proto"}), (formatters.proto.Data,)),
        (_PYTHON_EXT, (formatters.python.Data,)),
        (frozenset({"*.rs"}), (formatters.rust.Data,)),
        # TODO(build): Add a formatter for this.
        (_SHELL_EXT, (formatters.whitespace.Data,)),
        # TODO(build): Add a formatter for this (SELinux policies).
        (frozenset({"*.te"}), (formatters.whitespace.Data,)),
        # NB: We don't list all the variations in filenames as .textproto is the
        # only one that should be used, and `cros lint` enforces that.
        (
            frozenset({"*.textproto", "DIR_METADATA", "METADATA"}),
            (formatters.textproto.Data,),
        ),
        (
            frozenset({"*.grd", "*.svg", "*.xml", "*.xtb"}),
            (formatters.xml.Data,),
        ),
        # TODO(build): Switch .toml to rustfmt when available.
        # https://github.com/rust-lang/rustfmt/issues/4091
        (
            frozenset(
                {
                    "*.cfg",
                    "*.conf",
                    "*.ini",
                    "*.rules",
                    "*.toml",
                    "*.txt",
                    "*.vpython",
                    "*.vpython3",
                }
            ),
            (formatters.whitespace.Data,),
        ),
    )
)


def _BreakoutDataByTool(map_to_return, path):
    """Maps a tool method to the content of the |path|."""
    # Detect by content of the file itself.
    try:
        with open(path, "rb") as fp:
            # We read 128 bytes because that's the Linux kernel's current limit.
            # Look for BINPRM_BUF_SIZE in fs/binfmt_script.c.
            data = fp.read(128)

            try:
                result = shebang.parse(data)
            except ValueError:
                # If the file doesn't have a shebang, nothing to do.
                return

            basename = os.path.basename(result.real_command)
            if basename.startswith("python") or basename.startswith("vpython"):
                for tool in _TOOL_MAP[_PYTHON_EXT]:
                    map_to_return.setdefault(tool, []).append(path)
            elif basename in ("sh", "dash", "bash"):
                for tool in _TOOL_MAP[_SHELL_EXT]:
                    map_to_return.setdefault(tool, []).append(path)
    except IOError as e:
        logging.debug("%s: reading initial data failed: %s", path, e)


def _BreakoutFilesByTool(files: List[Path]) -> Dict[Callable, List[Path]]:
    """Maps a tool method to the list of files to process."""
    map_to_return = {}

    for f in files:
        abs_f = f.absolute()
        for patterns, tools in _TOOL_MAP.items():
            if any(abs_f.match(x) for x in patterns):
                for tool in tools:
                    map_to_return.setdefault(tool, []).append(f)
                break
        else:
            if f.is_file():
                _BreakoutDataByTool(map_to_return, f)

    return map_to_return


class DispatcherResult(NamedTuple):
    """Result of running a format command.

    Includes the process exit code and, if the file was and remains
    misformatted, the path of the file (for messaging for the --check mode).
    """

    process_return: int
    misformatted_file: Path  # None if file is now formatted.


def _Dispatcher(
    inplace: bool,
    _debug: bool,
    diff: bool,
    dryrun: bool,
    commit: Optional[str],
    tool: Callable,
    path: Path,
) -> DispatcherResult:
    """Call |tool| on |path| and take care of coalescing exit codes."""
    if commit:
        old_data = git.GetObjectAtRev(None, path, commit)
    else:
        try:
            old_data = osutils.ReadFile(path)
        except FileNotFoundError:
            logging.error("%s: file does not exist", path)
            return DispatcherResult(1, None)
        except UnicodeDecodeError:
            logging.error("%s: file is not UTF-8 compatible", path)
            return DispatcherResult(1, None)
    try:
        new_data = tool(old_data, path=path)
    except formatters.ParseError as e:
        logging.error("%s: parsing error: %s", e.args[0], e.__cause__)
        return DispatcherResult(1, None)
    if new_data == old_data:
        return DispatcherResult(0, None)

    if dryrun:
        logging.warning("%s: needs formatting", path)
        return DispatcherResult(1, path)
    elif diff:
        path = str(path).lstrip("/")
        print(
            "\n".join(
                difflib.unified_diff(
                    old_data.splitlines(),
                    new_data.splitlines(),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                    fromfiledate=f"({commit})" if commit else "(original)",
                    tofiledate="(formatted)",
                    lineterm="",
                )
            )
        )
        return DispatcherResult(1, path)
    elif inplace:
        logging.debug("Updating %s", path)
        osutils.WriteFile(path, new_data)
        return DispatcherResult(0, None)
    else:
        print(new_data, end="")
        return DispatcherResult(1, None)


@command.command_decorator("format")
class FormatCommand(analyzers.AnalyzerCommand):
    """Run the right formatter on the specified files."""

    EPILOG = """
For some file formats, see the CrOS style guide:
https://chromium.googlesource.com/chromiumos/docs/+/HEAD/styleguide/

Supported files: %s
""" % (
        " ".join(sorted(itertools.chain(*_TOOL_MAP))),
    )

    # AnalyzerCommand overrides.
    inplace_option_aliases = ["--fix"]
    can_modify_files = True
    use_dryrun_options = True

    def Run(self):
        # Hack "pre-submit" to "HEAD" when being run by repohooks/pre-upload.py
        # --pre-submit.  We should drop support for this once we merge repohooks
        # into `cros` with proper preupload/presubmit.
        commit = (
            "HEAD"
            if self.options.commit == "pre-submit"
            else self.options.commit
        )

        # Ignore symlinks.
        files = []
        syms = []
        if commit:
            for f in git.LsTree(None, commit, self.options.files):
                if f.is_symlink:
                    syms.append(f.name)
                else:
                    files.append(f.name)
        else:
            for f in path_util.ExpandDirectories(self.options.files):
                if f.is_symlink():
                    syms.append(f)
                else:
                    files.append(f)
        if syms:
            logging.info("Ignoring symlinks: %s", syms)
        if not files:
            # Running with no arguments is allowed to make the repo upload hook
            # simple, but print a warning so that if someone runs this manually
            # they are aware that nothing happened.
            logging.warning("No files found to process.  Doing nothing.")
            return 0

        # Ignore generated files.  Some tools can do this for us, but not all,
        # and it'd be faster if we just never spawned the tools in the first
        # place.  Prepend to exclude them early: a more general filter like
        # `--include "*.py"` earlier in the list would otherwise nerf this.
        # TODO(build): Move to a centralized configuration somewhere.
        self.options.filter.rules[:0] = (
            # Compiled python protobuf bindings.
            path_filter.exclude("*_pb2.py"),
            path_filter.exclude("*_pb2_grpc.py"),
            # Vendored third-party code.
            path_filter.exclude("*third_party/*.py"),
        )

        files = self.options.filter.filter(files)
        if not files:
            logging.warning("All files are excluded.  Doing nothing.")
            return 0

        tool_map = _BreakoutFilesByTool(files)
        dispatcher = functools.partial(
            _Dispatcher,
            self.options.inplace,
            self.options.debug,
            self.options.diff,
            self.options.dryrun,
            commit,
        )

        # If we filtered out all files, do nothing.
        # Special case one file (or fewer) as it's common -- faster to avoid the
        # parallel startup penalty.
        tasks = []
        for tool, files in tool_map.items():
            tasks.extend([tool, x] for x in files)

        misformatted_files = []
        if not tasks:
            logging.warning("No files support formatting.")
            ret = 0
        elif len(tasks) == 1:
            tool, files = next(iter(tool_map.items()))
            ret, misformatted_file = dispatcher(tool, files[0])
            if misformatted_file:
                misformatted_files = [str(misformatted_file)]
        else:
            ret = 0
            # Run the tool in parallel on the files.
            for task_ret, task_file in parallel.RunTasksInProcessPool(
                dispatcher, tasks, processes=self.options.jobs
            ):
                ret += task_ret
                if task_file:
                    misformatted_files.append(str(task_file))

        if misformatted_files:
            logging.notice(
                "You can fix formatting errors by running:\n  cros format %s",
                cros_build_lib.CmdToStr(misformatted_files),
            )

        return 1 if ret else 0
