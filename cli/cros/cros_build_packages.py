# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""cros build-packages updates the set of binary packages needed by ChromiumOS.

The build-packages process cross compiles all packages that have been
updated into the given sysroot and builds binary packages as a side-effect.
The output packages will be used by `cros build-image` to create a bootable
ChromiumOS image.

If packages are specified in the command line, only build those specific
packages and any dependencies they might need.
"""

import argparse
import logging
import os
from typing import Optional
import urllib.error
import urllib.request

from chromite.third_party.opentelemetry import trace

from chromite.cli import command
from chromite.lib import build_target_lib
from chromite.lib import chromite_config
from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import sysroot_lib
from chromite.service import sysroot
from chromite.utils import telemetry
from chromite.utils import timer


def build_shell_bool_style_args(
    parser: commandline.ArgumentParser,
    name: str,
    default_val: bool,
    help_str: str,
    deprecation_note: str,
    alternate_name: Optional[str] = None,
) -> None:
    """Build the shell boolean input argument equivalent.

    There are two cases which we will need to handle,
    case 1: A shell boolean arg, which doesn't need to be re-worded in python.
    case 2: A shell boolean arg, which needs to be re-worded in python.
    Example below.
    For Case 1, for a given input arg name 'argA', we create three python
    arguments.
    --argA, --noargA, --no-argA. The arguments --argA and --no-argA will be
    retained after deprecating --noargA.
    For Case 2, for a given input arg name 'arg_A' we need to use alternate
    argument name 'arg-A'. we create four python arguments in this case.
    --arg_A, --noarg_A, --arg-A, --no-arg-A. The first two arguments will be
    deprecated later.
    TODO(b/218522717): Remove the creation of --noargA in case 1 and --arg_A and
    --noarg_A in case 2.

    Args:
        parser: The parser to update.
        name: The input argument name. This will be used as 'dest' variable
            name.
        default_val: The default value to assign.
        help_str: The help string for the input argument.
        deprecation_note: A deprecation note to use.
        alternate_name: Alternate argument to be used after deprecation.
    """
    arg = f"--{name}"
    shell_narg = f"--no{name}"
    py_narg = f"--no-{name}"
    alt_arg = f"--{alternate_name}" if alternate_name else None
    alt_py_narg = f"--no-{alternate_name}" if alternate_name else None
    default_val_str = f"{help_str} (Default: %(default)s)."

    if alternate_name:
        parser.add_argument(
            alt_arg,
            action="store_true",
            default=default_val,
            dest=name,
            help=default_val_str,
        )
        parser.add_argument(
            alt_py_narg,
            action="store_false",
            dest=name,
            help="Don't " + help_str.lower(),
        )

    parser.add_argument(
        arg,
        action="store_true",
        default=default_val,
        dest=name,
        deprecated=deprecation_note % alt_arg if alternate_name else None,
        help=default_val_str if not alternate_name else argparse.SUPPRESS,
    )
    parser.add_argument(
        shell_narg,
        action="store_false",
        dest=name,
        deprecated=deprecation_note % alt_py_narg
        if alternate_name
        else py_narg,
        help=argparse.SUPPRESS,
    )

    if not alternate_name:
        parser.add_argument(
            py_narg,
            action="store_false",
            dest=name,
            help="Don't " + help_str.lower(),
        )


tracer = trace.get_tracer(__name__)


@command.command_decorator("build-packages")
class BuildPackagesCommand(command.CliCommand):
    """Update the set of binary packages used by ChromiumOS."""

    @classmethod
    def AddParser(cls, parser: commandline.ArgumentParser):
        """Build the parser.

        Args:
            parser: The argument parser.
        """
        super().AddParser(parser)

        deprecation_note = "Argument will be removed July 2022. Use %s instead."
        parser.add_argument(
            "-b",
            "--board",
            "--build-target",
            dest="board",
            default=cros_build_lib.GetDefaultBoard(),
            help="The board to build packages for.",
        )

        build_shell_bool_style_args(
            parser,
            "usepkg",
            True,
            "Use binary packages to bootstrap when possible.",
            deprecation_note,
        )
        build_shell_bool_style_args(
            parser,
            "usepkgonly",
            False,
            "Use binary packages only to bootstrap; abort if any are missing.",
            deprecation_note,
        )
        build_shell_bool_style_args(
            parser,
            "workon",
            True,
            "Force-build workon packages.",
            deprecation_note,
        )
        build_shell_bool_style_args(
            parser,
            "withrevdeps",
            True,
            "Calculate reverse dependencies on changed ebuilds.",
            deprecation_note,
        )
        build_shell_bool_style_args(
            parser,
            "cleanbuild",
            False,
            "Delete sysroot if it exists before building.",
            deprecation_note,
        )
        build_shell_bool_style_args(
            parser,
            "pretend",
            False,
            "Pretend building packages, just display which packages would have "
            "been installed.",
            deprecation_note,
        )

        # The --sysroot flag specifies the environment variables ROOT and
        # PKGDIR.  This allows fetching and emerging of all packages to
        # specified sysroot.  Note that --sysroot will setup the board normally
        # in /build/$BOARD, if it's not setup yet. It also expects the toolchain
        # to already be installed in the sysroot.
        # --usepkgonly and --norebuild are required, because building is not
        # supported when board_root is set.
        parser.add_argument(
            "--sysroot", type="path", help="Emerge packages to sysroot."
        )
        parser.add_argument(
            "--board_root",
            type="path",
            dest="sysroot",
            deprecated=deprecation_note % "--sysroot",
            help=argparse.SUPPRESS,
        )

        # CPU Governor related options.
        group = parser.add_argument_group("CPU Governor Options")
        build_shell_bool_style_args(
            group,
            "autosetgov",
            False,
            "Automatically set cpu governor to 'performance'.",
            deprecation_note,
        )
        build_shell_bool_style_args(
            group,
            "autosetgov_sticky",
            False,
            "Remember --autosetgov setting for future runs.",
            deprecation_note,
            alternate_name="autosetgov-sticky",
        )

        # Chrome building related options.
        group = parser.add_argument_group("Chrome Options")
        build_shell_bool_style_args(
            group,
            "use_any_chrome",
            True,
            "Use any Chrome prebuilt available, even if the prebuilt doesn't "
            "match exactly.",
            deprecation_note,
            alternate_name="use-any-chrome",
        )
        build_shell_bool_style_args(
            group,
            "internal",
            False,
            "Build the internal version of chrome (set the chrome_internal USE "
            "flag).",
            deprecation_note,
        )
        build_shell_bool_style_args(
            group,
            "chrome",
            False,
            "Ensure chrome instead of chromium. Alias for "
            "--internal --no-use-any-chrome.",
            deprecation_note,
        )

        # Setup board related options.
        group = parser.add_argument_group("Setup Board Config Options")
        build_shell_bool_style_args(
            group,
            "skip_chroot_upgrade",
            False,
            "Skip the automatic chroot upgrade; use with care.",
            deprecation_note,
            alternate_name="skip-chroot-upgrade",
        )
        build_shell_bool_style_args(
            group,
            "skip_toolchain_update",
            False,
            "Skip automatic toolchain update",
            deprecation_note,
            alternate_name="skip-toolchain-update",
        )
        build_shell_bool_style_args(
            group,
            "skip_setup_board",
            False,
            "Skip running setup_board. Implies "
            "--skip-chroot-upgrade --skip-toolchain-update.",
            deprecation_note,
            alternate_name="skip-setup-board",
        )

        # Image Type selection related options.
        group = parser.add_argument_group("Image Type Options")
        build_shell_bool_style_args(
            group,
            "withdev",
            True,
            "Build useful developer friendly utilities.",
            deprecation_note,
        )
        build_shell_bool_style_args(
            group,
            "withdebug",
            True,
            "Build debug versions of Chromium-OS-specific packages.",
            deprecation_note,
        )
        build_shell_bool_style_args(
            group,
            "withfactory",
            True,
            "Build factory installer.",
            deprecation_note,
        )
        build_shell_bool_style_args(
            group,
            "withtest",
            True,
            "Build packages required for testing.",
            deprecation_note,
        )
        build_shell_bool_style_args(
            group,
            "withautotest",
            True,
            "Build autotest client code.",
            deprecation_note,
        )
        build_shell_bool_style_args(
            group,
            "withdebugsymbols",
            False,
            "Install the debug symbols for all packages.",
            deprecation_note,
        )

        # Advanced Options.
        group = parser.add_argument_group("Advanced Options")
        group.add_argument(
            "--accept-licenses", help="Licenses to append to the accept list."
        )
        group.add_argument(
            "--accept_licenses",
            deprecated=deprecation_note % "--accept-licenses",
            help=argparse.SUPPRESS,
        )
        build_shell_bool_style_args(
            group,
            "eclean",
            True,
            "Run eclean to delete old binpkgs.",
            deprecation_note,
        )
        group.add_argument(
            "--jobs",
            type=int,
            default=os.cpu_count(),
            help=(
                "Number of packages to build in parallel. (Default: "
                "%(default)s)"
            ),
        )
        build_shell_bool_style_args(
            group,
            "expandedbinhosts",
            True,
            "Allow expanded binhost inheritance.",
            deprecation_note,
        )
        group.add_argument(
            "--backtrack",
            type=int,
            default=sysroot.BACKTRACK_DEFAULT,
            help="See emerge --backtrack.",
        )

        # The --reuse-pkgs-from-local-boards flag tells Portage to share binary
        # packages between boards that are built locally, so that the total time
        # required to build several boards is reduced. This flag is only useful
        # when you are not able to use remote binary packages, since remote
        # binary packages are usually more up to date than anything you have
        # locally.
        build_shell_bool_style_args(
            group,
            "reuse_pkgs_from_local_boards",
            False,
            "Bootstrap from local packages instead of remote packages.",
            deprecation_note,
            alternate_name="reuse-pkgs-from-local-boards",
        )

        # --run-goma option is designed to be used on bots.
        # If you're trying to build packages with goma in your local dev env,
        # this is *not* the option you're looking for.  Please see comments
        # below.  This option; 1) starts goma, 2) builds packages (expecting
        # that goma is used), then 3) stops goma explicitly.
        # 4) is a request from the goma team, so that stats/logs can be taken.
        # Note: GOMA_DIR is expected to be passed via env var.
        #
        # In local dev env cases, compiler_proxy is expected to keep running.
        # In such a case;
        #   $ python ${GOMA_DIR}/goma_ctl.py ensure_start
        #   $ cros build-image (... and options without --run-goma ...)
        # is an expected commandline sequence. If you set --run-goma flag while
        # compiler_proxy is already running, the existing compiler_proxy will be
        # stopped.
        build_shell_bool_style_args(
            group,
            "run_goma",
            False,
            "When set, (re)starts goma, builds packages, and then stops goma.",
            deprecation_note,
            alternate_name="run-goma",
        )
        # This option is for building chrome remotely.
        # 1) starts reproxy 2) builds chrome with reproxy and 3) stops reproxy
        # so logs/stats can be collected.
        # Note: RECLIENT_DIR and REPROXY_CFG env var will be deprecated July
        # 2022.  Use --reclient-dir and --reproxy-cfg input options instead.
        build_shell_bool_style_args(
            group,
            "run_remoteexec",
            False,
            "If set to true, starts RBE reproxy, builds packages, and then "
            "stops reproxy.",
            deprecation_note,
        )

        build_shell_bool_style_args(
            group,
            "bazel",
            False,
            "Use Bazel to build packages.",
            deprecation_note,
        )

        build_shell_bool_style_args(
            group,
            "bazel_lite",
            False,
            "Perform lite build with a limited set of packages.",
            deprecation_note,
        )

        parser.add_argument("packages", nargs="*", help="Packages to build.")
        return parser

    @classmethod
    def ProcessOptions(
        cls,
        parser: commandline.ArgumentParser,
        options: commandline.ArgumentNamespace,
    ):
        if not options.board:
            # Not supplied and no default set.
            parser.error("--board is required")

        if options.chrome:
            options.internal_chrome = True
            options.use_any_chrome = False

        options.setup_board_run_config = sysroot.SetupBoardRunConfig(
            force=options.cleanbuild,
            usepkg=options.usepkg,
            jobs=options.jobs,
            quiet=True,
            update_toolchain=not options.skip_toolchain_update,
            upgrade_chroot=not options.skip_chroot_upgrade,
            local_build=options.reuse_pkgs_from_local_boards,
            expanded_binhost_inheritance=options.expandedbinhosts,
            use_cq_prebuilts=options.usepkg,
            backtrack=options.backtrack,
        )
        options.build_run_config = sysroot.BuildPackagesRunConfig(
            usepkg=options.usepkg,
            install_debug_symbols=options.withdebugsymbols,
            packages=options.packages,
            use_goma=options.run_goma,
            use_remoteexec=options.run_remoteexec,
            incremental_build=options.withrevdeps,
            dryrun=options.pretend,
            usepkgonly=options.usepkgonly,
            workon=options.workon,
            install_auto_test=options.withautotest,
            autosetgov=options.autosetgov,
            autosetgov_sticky=options.autosetgov_sticky,
            use_any_chrome=options.use_any_chrome,
            internal_chrome=options.internal,
            clean_build=options.cleanbuild,
            eclean=options.eclean,
            jobs=options.jobs,
            local_pkg=options.reuse_pkgs_from_local_boards,
            dev_image=options.withdev,
            factory_image=options.withfactory,
            test_image=options.withtest,
            debug_version=options.withdebug,
            backtrack=options.backtrack,
            bazel=options.bazel,
            bazel_lite=options.bazel_lite,
        )

    @timer.timed("Elapsed time (cros build-packages)")
    def Run(self):
        commandline.RunInsideChroot()

        chromite_config.initialize()
        telemetry.initialize(
            chromite_config.TELEMETRY_CONFIG,
            log_traces=self.options.log_telemetry,
        )
        try:
            build_packages(self.options)
        except sysroot_lib.PackageInstallError as e:
            try:
                with urllib.request.urlopen(
                    "https://chromiumos-status.appspot.com/current?format=raw"
                ) as request:
                    logging.notice("Tree Status: %s", request.read().decode())
            except urllib.error.HTTPError:
                pass
            cros_build_lib.Die(e)


@tracer.start_as_current_span("cli.cros.cros_build_packages.build_packages")
def build_packages(opts: commandline.ArgumentNamespace):
    span = trace.get_current_span()

    build_target = build_target_lib.BuildTarget(
        opts.board, build_root=opts.sysroot
    )
    span.set_attributes(
        {
            "board": build_target.name,
            "packages": opts.packages or [],
            "workon": opts.workon is True,
            "bazel": opts.bazel is True,
        }
    )

    board_root = sysroot_lib.Sysroot(build_target.root)

    # TODO(xcl): Update run_configs to have a common base set of configs for
    # setup_board and cros build-packages.
    if not opts.skip_setup_board:
        sysroot.SetupBoard(
            build_target,
            accept_licenses=opts.accept_licenses,
            run_configs=opts.setup_board_run_config,
        )

    sysroot.BuildPackages(build_target, board_root, opts.build_run_config)
