# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Run lint checks on the specified files."""

import collections
import functools
import importlib.machinery
import importlib.util
import itertools
import json
import logging
import os
from pathlib import Path
import stat
from typing import Callable, Dict, List, Optional, Union

from chromite.cli import analyzers
from chromite.cli import command
from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import git
from chromite.lib import json_lib
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib import path_util
from chromite.lint import linters
from chromite.utils import path_filter
from chromite.utils import timer
from chromite.utils.parser import shebang


def _GetProjectPath(path: Path) -> Path:
    """Find the absolute path of the git checkout that contains |path|."""
    ret = git.FindGitTopLevel(path)
    if ret:
        return Path(ret)
    else:
        # Maybe they're running on a file outside of a checkout.
        # e.g. cros lint ~/foo.py /tmp/test.py
        return path.parent


def _get_file_data(path: Union[str, os.PathLike], commit: Optional[str]) -> str:
    """Read the file data for |path| either from disk or git |commit|."""
    if commit:
        return git.GetObjectAtRev(None, f"./{path}", commit)
    else:
        return Path(path).read_text(encoding="utf-8")


def _GetPylintrc(path: Path) -> Path:
    """Locate pylintrc or .pylintrc file that applies to |path|.

    If not found - use the default.
    """

    def _test_func(pylintrc):
        dotpylintrc = pylintrc.with_name(".pylintrc")
        # Only allow one of these to exist to avoid confusing which one is used.
        if pylintrc.exists() and dotpylintrc.exists():
            cros_build_lib.Die(
                '%s: Only one of "pylintrc" or ".pylintrc" is allowed',
                pylintrc.parent,
            )
        return pylintrc.exists() or dotpylintrc.exists()

    end_path = _GetProjectPath(path.parent).parent
    ret = osutils.FindInPathParents(
        "pylintrc", path.parent, test_func=_test_func, end_path=end_path
    )
    if ret:
        return ret if ret.exists() else ret.with_name(".pylintrc")
    return constants.CHROMITE_DIR / "pylintrc"


def _GetPythonPath():
    """Return the set of Python library paths to use."""
    # Carry through custom PYTHONPATH that the host env has set.
    return os.environ.get("PYTHONPATH", "").split(os.pathsep) + [
        # Ideally we'd modify meta_path in pylint to handle our virtual chromite
        # module, but that's not possible currently.  We'll have to deal with
        # that at some point if we want `cros lint` to work when the dir is not
        # named 'chromite'.
        str(constants.SOURCE_ROOT),
    ]


# The mapping between the "cros lint" --output-format flag and cpplint.py
# --output flag.
CPPLINT_OUTPUT_FORMAT_MAP = {
    "colorized": "emacs",
    "msvs": "vs7",
    "parseable": "emacs",
}

# Default category filters to pass to cpplint.py when invoked via `cros lint`.
#
# `-foo/bar` means "don't show any lints from category foo/bar".
# See `cpplint.py --help` for more explanation of category filters.
CPPLINT_DEFAULT_FILTERS = ("-runtime/references",)


# The mapping between the "cros lint" --output-format flag and shellcheck
# flags.
# Note that the msvs mapping here isn't quite VS format, but it's closer than
# the default output.
SHLINT_OUTPUT_FORMAT_MAP = {
    "colorized": ["--color=always"],
    "msvs": ["--format=gcc"],
    "parseable": ["--format=gcc"],
}


def _ToolRunCommand(cmd, debug, **kwargs):
    """Run the linter with common run args set as higher levels expect."""
    return cros_build_lib.run(
        cmd, check=False, print_cmd=debug, debug_level=logging.NOTICE, **kwargs
    )


def _ConfLintFile(path, output_format, debug, relaxed: bool, commit: str):
    """Determine applicable .conf syntax and call the appropriate handler."""
    ret = cros_build_lib.CompletedProcess(f'cros lint "{path}"', returncode=0)
    if not os.path.isfile(path):
        return ret

    # Check for the description and author lines present in upstart configs.
    with open(path, "rb") as file:
        tokens_to_find = {b"author", b"description"}
        for line in file:
            try:
                token = line.split()[0]
            except IndexError:
                continue

            try:
                tokens_to_find.remove(token)
            except KeyError:
                continue

            if not tokens_to_find:
                logging.warning(
                    "Found upstart .conf in a directory other than init or "
                    "upstart."
                )
                return _UpstartLintFile(
                    path, output_format, debug, relaxed, commit
                )
    return ret


@functools.lru_cache(maxsize=None)
def _cpplint_module():
    """Load the cpplint.py module.

    We can't import the module directly because it lives in a non-standard path
    (depot_tools), and we don't want to add that to sys.path because it has a
    lot of unrelated Python module we don't want polluting our normal search.
    """
    modname = "cpplint"
    cpplint = str(constants.DEPOT_TOOLS_DIR / "cpplint.py")
    loader = importlib.machinery.SourceFileLoader(modname, cpplint)
    spec = importlib.util.spec_from_loader(modname, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _CpplintFile(path, output_format, _debug, _relaxed: bool, commit: str):
    """Returns result of running cpplint on |path|."""
    result = cros_build_lib.CompletedProcess(f'cpplint "{path}"', returncode=0)

    # pylint: disable=protected-access
    # The cpplint API doesn't expose state that we need.  We're pinned to a
    # specific version, so we don't exactly have to worry about it changing.
    cpplint = _cpplint_module()
    cpplint._SetFilters(",".join(CPPLINT_DEFAULT_FILTERS))
    cpplint._SetOutputFormat(
        "emacs"
        if output_format == "default"
        else CPPLINT_OUTPUT_FORMAT_MAP[output_format]
    )
    if cpplint.ProcessConfigOverrides(str(path)):
        data = _get_file_data(path, commit)
        lines = data.split("\n")
        ext = path.suffix[1:] or str(path)
        cpplint.ProcessFileData(str(path), ext, lines, cpplint.Error)
        result.returncode = 1 if cpplint._cpplint_state.error_count else 0

    return result


def _PylintFile(path, output_format, debug, _relaxed: bool, _commit: str):
    """Returns result of running pylint on |path|."""
    pylint = constants.CHROMITE_SCRIPTS_DIR / "pylint"
    pylintrc = _GetPylintrc(path)
    cmd = [pylint, "--rcfile=%s" % pylintrc]
    if output_format != "default":
        cmd.append("--output-format=%s" % output_format)
    cmd.append(path)
    extra_env = {
        "PYTHONPATH": ":".join(_GetPythonPath()),
    }
    return _ToolRunCommand(cmd, debug, extra_env=extra_env)


def _GnlintFile(path, _, _debug, _relaxed: bool, commit: str):
    """Returns result of running gnlint on |path|."""
    result = cros_build_lib.CompletedProcess(f'gnlint "{path}"', returncode=0)

    data = _get_file_data(path, commit)
    if linters.gnlint.Data(data, path):
        result.returncode = 1

    return result


def _GolintFile(path, _, debug, _relaxed: bool, _commit: str):
    """Returns result of running golint on |path|."""
    # Try using golint if it exists.
    try:
        cmd = ["golint", "-set_exit_status", path]
        return _ToolRunCommand(cmd, debug)
    except cros_build_lib.RunCommandError:
        logging.notice("Install golint for additional go linting.")
        return cros_build_lib.CompletedProcess(f'gofmt "{path}"', returncode=0)


def _JsonLintFile(path, _output_format, _debug, _relaxed: bool, commit: str):
    """Returns result of running json lint checks on |path|."""
    result = cros_build_lib.CompletedProcess(
        f'python -mjson.tool "{path}"', returncode=0
    )

    data = _get_file_data(path, commit)

    # See if it validates.
    try:
        json_lib.loads(data)
    except ValueError as e:
        result.returncode = 1
        logging.notice("%s: %s", path, e)

    return result


def _MarkdownLintFile(
    path, _output_format, _debug, _relaxed: bool, commit: str
):
    """Returns result of running lint checks on |path|."""
    result = cros_build_lib.CompletedProcess(
        f'mdlint(internal) "{path}"', returncode=0
    )

    data = _get_file_data(path, commit)

    # Check whitespace.
    if not linters.whitespace.Data(data, Path(path)):
        result.returncode = 1

    return result


def _ShellLintFile(
    path,
    output_format,
    debug,
    _relaxed: bool,
    _commit: str,
    gentoo_format=False,
):
    """Returns result of running lint checks on |path|.

    Args:
        path: The path to the script on which to run the linter.
        output_format: The format of the output that the linter should emit. See
            |SHLINT_OUTPUT_FORMAT_MAP|.
        debug: Whether to print out the linter command.
        gentoo_format: Whether to treat this file as an ebuild style script.

    Returns:
        A CompletedProcess object.
    """
    # Instruct shellcheck to run itself from the shell script's dir. Note that
    # 'SCRIPTDIR' is a special string that shellcheck rewrites to the dirname of
    # the given path.
    extra_checks = [
        "avoid-nullary-conditions",  # SC2244
        "check-unassigned-uppercase",  # Include uppercase in SC2154
        "require-variable-braces",  # SC2250
    ]
    if not gentoo_format:
        extra_checks.append("quote-safe-variables")  # SC2248

    cmd = [
        # pylint: disable=protected-access
        linters.shell._find_shellcheck(),
        "--source-path=SCRIPTDIR",
        "--enable=%s" % ",".join(extra_checks),
    ]
    if output_format != "default":
        cmd.extend(SHLINT_OUTPUT_FORMAT_MAP[output_format])
    cmd.append("-x")
    # No warning for using local with /bin/sh.
    cmd.append("--exclude=SC3043")
    if gentoo_format:
        # ebuilds don't explicitly export variables or contain a shebang.
        cmd.append("--exclude=SC2148")
        # ebuilds always use bash.
        cmd.append("--shell=bash")
    cmd.append(path)

    lint_result = _ToolRunCommand(cmd, debug)

    # Check whitespace.
    if not linters.whitespace.Data(osutils.ReadFile(path), Path(path)):
        lint_result.returncode = 1

    return lint_result


def _GentooShellLintFile(
    path, output_format, debug, relaxed: bool, commit: str
):
    """Run shell checks with Gentoo rules."""
    return _ShellLintFile(
        path, output_format, debug, relaxed, commit, gentoo_format=True
    )


def _SeccompPolicyLintFile(
    path, _output_format, debug, _relaxed: bool, commit: str
):
    """Run the seccomp policy linter."""
    if commit:
        stdin = _get_file_data(path, commit)
    else:
        stdin = ""
    return _ToolRunCommand(
        [
            os.path.join(
                constants.SOURCE_ROOT,
                "src",
                "platform",
                "minijail",
                "tools",
                "seccomp_policy_lint.py",
            ),
            "--assume-filename",
            path,
            "/dev/stdin" if commit else path,
        ],
        debug,
        input=stdin,
    )


def _UpstartLintFile(path, _output_format, _debug, relaxed: bool, commit: str):
    """Run lints on upstart configs."""
    # Skip .conf files that aren't in an init parent directory.
    ret = cros_build_lib.CompletedProcess(f'cros lint "{path}"', returncode=0)
    data = _get_file_data(path, commit)
    if not linters.upstart.Data(data, Path(path), relaxed):
        ret.returncode = 1
    return ret


def _DirMdLintFile(path, _output_format, debug, _relaxed: bool, commit: str):
    """Run the dirmd linter."""
    data = _get_file_data(path, commit)
    ret = _ToolRunCommand(
        [constants.DEPOT_TOOLS_DIR / "dirmd", "parse"],
        debug,
        input=data,
        stdout=True,
    )
    if ret.returncode:
        results = json.loads(ret.stdout)
        print(path, results["stdin"]["error"])
    return ret


def _OwnersLintFile(path, _output_format, _debug, _relaxed: bool, commit: str):
    """Run lints on OWNERS files."""
    ret = cros_build_lib.CompletedProcess(f'cros lint "{path}"', returncode=0)
    data = _get_file_data(path, commit)
    if not linters.owners.lint_data(Path(path), data):
        ret.returncode = 1
    return ret


def _TextprotoLintFile(
    path, _output_format, _debug, _relaxed: bool, _commit: str
) -> cros_build_lib.CompletedProcess:
    """Run lints on OWNERS files."""
    ret = cros_build_lib.CompletedProcess(f'cros lint "{path}"', returncode=0)
    # go/textformat-spec#text-format-files says to use .textproto.
    if os.path.splitext(path)[1] != ".textproto":
        logging.error(
            "%s: use '.textproto' extension for text proto messages", path
        )
        ret.returncode = 1
    # TODO(build): Assert file header has `proto-file:` and `proto-message:`
    # keywords in it.  Also allow `proto-import:`, but ban all other `proto-`
    # directives (in case of typos).  go/textformat-schema
    return ret


def _WhitespaceLintFile(
    path, _output_format, _debug, _relaxed: bool, commit: str
):
    """Returns result of running basic whitespace checks on |path|."""
    result = cros_build_lib.CompletedProcess(
        f'whitespace(internal) "{path}"', returncode=0
    )

    data = _get_file_data(path, commit)

    # Check whitespace.
    if not linters.whitespace.Data(data, Path(path)):
        result.returncode = 1

    return result


def _NonExecLintFile(path, _output_format, _debug, _relaxed: bool, commit: str):
    """Check file permissions on |path| are -x."""
    result = cros_build_lib.CompletedProcess(
        f'stat(internal) "{path}"', returncode=0
    )

    if commit:
        entries = git.LsTree(
            os.path.dirname(path) or None, commit, [os.path.basename(path)]
        )
        if entries and entries[0].is_exec:
            result.returncode = 1
            logging.notice(
                "%s: file should not be executable; chmod -x to fix", path
            )
    else:
        # Ignore symlinks.
        st = os.lstat(path)
        if stat.S_ISREG(st.st_mode):
            mode = stat.S_IMODE(st.st_mode)
            if mode & 0o111:
                result.returncode = 1
                logging.notice(
                    "%s: file should not be executable; chmod -x to fix", path
                )

    return result


def _MakeDefaultsLintFile(
    path, _output_format, _debug, _relaxed: bool, commit: str
):
    """Lint make.defaults files."""
    result = cros_build_lib.CompletedProcess(
        f'cros lint "{path}"', returncode=0
    )

    data = _get_file_data(path, commit)
    issues = linters.make_defaults.Data(data)
    for issue in issues:
        logging.error("%s: %s", path, issue)
    if issues:
        result.returncode = 1

    return result


def _PortageLayoutConfLintFile(
    path, _output_format, _debug, _relaxed: bool, commit: str
):
    """Lint metadata/layout.conf files."""
    result = cros_build_lib.CompletedProcess(
        f'cros lint "{path}"', returncode=0
    )

    data = _get_file_data(path, commit)
    issues = linters.portage_layout_conf.Data(data, path)
    for issue in issues:
        logging.error("%s: %s", path, issue)
    if issues:
        result.returncode = 1

    return result


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


# These are used in _BreakoutDataByTool, so add a constant to keep in sync.
_PYTHON_EXT = frozenset({"*.py"})
_SHELL_EXT = frozenset({"*.sh"})

# Map file names to a tool function.
# NB: Order matters as earlier entries override later ones.
_TOOL_MAP = collections.OrderedDict(
    (
        (frozenset({"DIR_METADATA"}), (_DirMdLintFile, _NonExecLintFile)),
        (frozenset({"OWNERS*"}), (_OwnersLintFile, _NonExecLintFile)),
        # NB: Must come before *.conf rules below.
        (
            frozenset({"init/*.conf", "upstart/*.conf"}),
            (
                _UpstartLintFile,
                _NonExecLintFile,
            ),
        ),
        (
            frozenset({"metadata/layout.conf"}),
            (_PortageLayoutConfLintFile, _NonExecLintFile),
        ),
        # Note these are defined to keep in line with cpplint.py. Technically,
        # we could include additional ones, but cpplint.py would just filter
        # them out.
        (frozenset({"*.c"}), (_WhitespaceLintFile, _NonExecLintFile)),
        # Remember to change cros_format to align supported extensions.
        # LINT.IfChange(cpp_extensions)
        (
            frozenset({"*.cc", "*.cpp", "*.cxx", "*.h", "*.hh"}),
            (
                _CpplintFile,
                _NonExecLintFile,
            ),
        ),
        # LINT.ThenChange(cros_format.py:cpp_extensions)
        (frozenset({"*.conf", "*.conf.in"}), (_ConfLintFile, _NonExecLintFile)),
        (frozenset({"*.gn", "*.gni"}), (_GnlintFile, _NonExecLintFile)),
        (
            frozenset({"*.json", "*.jsonproto"}),
            (_JsonLintFile, _NonExecLintFile),
        ),
        (_PYTHON_EXT, (_PylintFile,)),
        (frozenset({"*.go"}), (_GolintFile, _NonExecLintFile)),
        (_SHELL_EXT, (_ShellLintFile,)),
        (
            frozenset({"*.ebuild", "*.eclass", "*.bashrc"}),
            (
                _GentooShellLintFile,
                _NonExecLintFile,
            ),
        ),
        (
            frozenset({"make.defaults"}),
            (_WhitespaceLintFile, _NonExecLintFile, _MakeDefaultsLintFile),
        ),
        (frozenset({"*.md"}), (_MarkdownLintFile, _NonExecLintFile)),
        # Yes, there's a lot of variations here.  We catch these specifically to
        # throw errors and force people to use the single correct name.
        (
            frozenset(
                {
                    "*.pb",
                    "*.pb.txt",
                    "*.pb.text",
                    "*.pbtxt",
                    "*.pbtext",
                    "*.protoascii",
                    "*.prototxt",
                    "*.prototext",
                    "*.textpb",
                    "*.txtpb",
                    "*.textproto",
                    "*.txtproto",
                }
            ),
            (
                _TextprotoLintFile,
                _NonExecLintFile,
            ),
        ),
        (
            frozenset({"*.policy"}),
            (
                _SeccompPolicyLintFile,
                _WhitespaceLintFile,
                _NonExecLintFile,
            ),
        ),
        (frozenset({"*.te"}), (_WhitespaceLintFile, _NonExecLintFile)),
        (
            frozenset(
                {
                    "Dockerfile",
                    "Makefile",
                    "*.bzl",
                    "*.cfg",
                    "*.config",
                    "*.css",
                    "*.grd",
                    "*.gyp",
                    "*.gypi",
                    "*.htm",
                    "*.html",
                    "*.ini",
                    "*.jpeg",
                    "*.jpg",
                    "*.js",
                    "*.l",
                    "*.mk",
                    "*.patch",
                    "*.png",
                    "*.proto",
                    "*.rules",
                    "*.service",
                    "*.star",
                    "*.svg",
                    "*.toml",
                    "*.txt",
                    "*.vpython",
                    "*.vpython3",
                    "*.xml",
                    "*.xtb",
                    "*.y",
                    "*.yaml",
                    "*.yml",
                }
            ),
            (_NonExecLintFile,),
        ),
    )
)


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


def _Dispatcher(
    output_format, debug, relaxed: bool, commit: str, tool, path: Path
) -> int:
    """Call |tool| on |path| and take care of coalescing exit codes/output."""
    try:
        result = tool(path, output_format, debug, relaxed, commit)
    except UnicodeDecodeError:
        logging.error("%s: file is not UTF-8 compatible", path)
        return 1
    return 1 if result.returncode else 0


@command.command_decorator("lint")
class LintCommand(analyzers.AnalyzerCommand):
    """Run lint checks on the specified files."""

    EPILOG = """
For some file formats, see the CrOS style guide:
https://chromium.googlesource.com/chromiumos/docs/+/HEAD/styleguide/

Supported files: %s

NB: Not all linters work with `--commit` yet.
""" % (
        " ".join(sorted(itertools.chain(*_TOOL_MAP))),
    )

    # The output formats supported by cros lint.
    OUTPUT_FORMATS = ("default", "colorized", "msvs", "parseable")

    @classmethod
    def AddParser(cls, parser: commandline.ArgumentParser):
        super().AddParser(parser)
        parser.add_argument(
            "--output",
            default="default",
            choices=LintCommand.OUTPUT_FORMATS,
            help="Output format to pass to the linters. Supported "
            "formats are: default (no option is passed to the "
            "linter), colorized, msvs (Visual Studio) and "
            "parseable.",
        )
        parser.add_argument(
            "--relaxed",
            default=False,
            action="store_true",
            help="Disable some strict checks. This is used for "
            "cases like builds where a more permissive "
            "behavior is desired.",
        )

    def _Run(self):
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
        )

        files = self.options.filter.filter(files)
        if not files:
            logging.warning("All files are excluded.  Doing nothing.")
            return 0

        tool_map = _BreakoutFilesByTool(files)
        dispatcher = functools.partial(
            _Dispatcher,
            self.options.output,
            self.options.debug,
            self.options.relaxed,
            commit,
        )

        # If we filtered out all files, do nothing.
        # Special case one file (or fewer) as it's common -- faster to avoid the
        # parallel startup penalty.
        tasks = []
        for tool, files in tool_map.items():
            tasks.extend([tool, x] for x in files)
        if not tasks:
            return 0
        elif len(tasks) == 1:
            tool, files = next(iter(tool_map.items()))
            return dispatcher(tool, files[0])
        else:
            # Run the tool in parallel on the files.
            return sum(
                parallel.RunTasksInProcessPool(
                    dispatcher, tasks, processes=self.options.jobs
                )
            )

    def Run(self):
        with timer.Timer() as t:
            ret = self._Run()
        if ret:
            logging.error("Found lint errors in %i files in %s.", ret, t)

        return 1 if ret else 0
