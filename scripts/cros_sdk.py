# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Manage SDK chroots.

This script is used for manipulating local chroot environments; creating,
deleting, downloading, etc.  If given --enter (or no args), it defaults
to an interactive bash shell within the chroot.

If given args those are passed to the chroot environment, and executed.
"""

import argparse
import glob
import logging
import os
from pathlib import Path
import pwd
import re
import shlex
import sys
from typing import List, Tuple
import urllib.parse

from chromite.cbuildbot import cbuildbot_alerts
from chromite.lib import chromite_config
from chromite.lib import chroot_lib
from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_sdk_lib
from chromite.lib import goma_lib
from chromite.lib import locking
from chromite.lib import namespaces
from chromite.lib import osutils
from chromite.lib import process_util
from chromite.lib import remoteexec_util
from chromite.lib import retry_util
from chromite.lib import timeout_util
from chromite.lib import toolchain
from chromite.utils import key_value_store


# Which compression algos the SDK tarball uses.  We've used xz since 2012.
COMPRESSION_PREFERENCE = ("xz",)

# Proxy simulator configuration.
PROXY_HOST_IP = "192.168.240.1"
PROXY_PORT = 8080
PROXY_GUEST_IP = "192.168.240.2"
PROXY_NETMASK = 30
PROXY_VETH_PREFIX = "veth"
PROXY_CONNECT_PORTS = (80, 443, 9418)
PROXY_APACHE_FALLBACK_USERS = ("www-data", "apache", "nobody")
PROXY_APACHE_MPMS = ("event", "worker", "prefork")
PROXY_APACHE_FALLBACK_PATH = ":".join(
    "/usr/lib/apache2/mpm-%s" % mpm for mpm in PROXY_APACHE_MPMS
)
PROXY_APACHE_MODULE_GLOBS = ("/usr/lib*/apache2/modules", "/usr/lib*/apache2")

# We need these tools to run. Very common tools (tar,..) are omitted.
NEEDED_TOOLS = ("curl", "xz")

# Tools needed for --proxy-sim only.
PROXY_NEEDED_TOOLS = ("ip",)


def GetArchStageTarballs(version):
    """Returns the URL for a given arch/version"""
    extension = {"xz": "tar.xz"}
    return [
        toolchain.GetSdkURL(
            suburl="cros-sdk-%s.%s" % (version, extension[compressor])
        )
        for compressor in COMPRESSION_PREFERENCE
    ]


def FetchRemoteTarballs(storage_dir, urls):
    """Fetches a tarball given by url, and place it in |storage_dir|.

    Args:
        storage_dir: Path where to save the tarball.
        urls: List of URLs to try to download. Download will stop on first
            success.

    Returns:
        Full path to the downloaded file.

    Raises:
        ValueError: None of the URLs worked.
    """
    # Note we track content length ourselves since certain versions of curl
    # fail if asked to resume a complete file.
    # https://sourceforge.net/tracker/?func=detail&atid=100976&aid=3482927&group_id=976
    status_re = re.compile(rb"^HTTP/[0-9]+(\.[0-9]+)? 200")
    # pylint: disable=undefined-loop-variable
    for url in urls:
        logging.notice("Downloading tarball %s ...", urls[0].rsplit("/", 1)[-1])
        parsed = urllib.parse.urlparse(url)
        tarball_name = os.path.basename(parsed.path)
        if parsed.scheme in ("", "file"):
            if os.path.exists(parsed.path):
                return parsed.path
            continue
        content_length = 0
        logging.debug("Attempting download from %s", url)
        result = retry_util.RunCurl(
            ["-I", url],
            print_cmd=False,
            debug_level=logging.NOTICE,
            capture_output=True,
        )
        successful = False
        for header in result.stdout.splitlines():
            # We must walk the output to find the 200 code for use cases where
            # a proxy is involved and may have pushed down the actual header.
            if status_re.match(header):
                successful = True
            elif header.lower().startswith(b"content-length:"):
                content_length = int(header.split(b":", 1)[-1].strip())
                if successful:
                    break
        if successful:
            break
    else:
        raise ValueError("No valid URLs found!")

    tarball_dest = os.path.join(storage_dir, tarball_name)
    current_size = 0
    if os.path.exists(tarball_dest):
        current_size = os.path.getsize(tarball_dest)
        if current_size > content_length:
            osutils.SafeUnlink(tarball_dest)
            current_size = 0

    if current_size < content_length:
        retry_util.RunCurl(
            [
                "--fail",
                "-L",
                "-y",
                "30",
                "-C",
                "-",
                "--output",
                tarball_dest,
                url,
            ],
            print_cmd=False,
            debug_level=logging.NOTICE,
        )

    # Cleanup old tarballs now since we've successfull fetched; only cleanup
    # the tarballs for our prefix, or unknown ones. This gets a bit tricky
    # because we might have partial overlap between known prefixes.
    for p in Path(storage_dir).glob("cros-sdk-*"):
        if p.name == tarball_name:
            continue
        logging.info("Cleaning up old tarball: %s", p)
        osutils.SafeUnlink(p)

    return tarball_dest


def _SudoCommand():
    """Get the 'sudo' command, along with all needed environment variables."""

    # Pass in the ENVIRONMENT_ALLOWLIST and ENV_PASSTHRU variables so that
    # scripts in the chroot know what variables to pass through.
    cmd = ["sudo"]
    for key in constants.CHROOT_ENVIRONMENT_ALLOWLIST + constants.ENV_PASSTHRU:
        value = os.environ.get(key)
        if value is not None:
            cmd += ["%s=%s" % (key, value)]

    # We keep PATH not for the chroot but for the re-exec & for programs we
    # might run before we chroot into the SDK.  The process that enters the SDK
    # itself will take care of initializing PATH to the right value then.  But
    # we can't override the system's default PATH for root as that will hide
    # /sbin.
    cmd += ["CHROMEOS_SUDO_PATH=%s" % os.environ.get("PATH", "")]

    # Pass along current rlimit settings so we can restore them.
    cmd += [f"CHROMEOS_SUDO_RLIMITS={cros_sdk_lib.ChrootEnteror.get_rlimits()}"]

    return cmd


def _ReportMissing(missing):
    """Report missing utilities, then exit.

    Args:
        missing: List of missing utilities, as returned by
            osutils.FindMissingBinaries.  If non-empty, will not return.
    """

    if missing:
        raise SystemExit(
            "The tool(s) %s were not found.\n"
            "Please install the appropriate package in your host.\n"
            "Example(ubuntu):\n"
            "  sudo apt-get install <packagename>" % ", ".join(missing)
        )


def _ProxySimSetup(options):
    """Set up proxy simulator, and return only in the child environment.

    TODO: Ideally, this should support multiple concurrent invocations of
    cros_sdk --proxy-sim; currently, such invocations will conflict with each
    other due to the veth device names and IP addresses.  Either this code would
    need to generate fresh, unused names for all of these before forking, or it
    would need to support multiple concurrent cros_sdk invocations sharing one
    proxy and allowing it to exit when unused (without counting on any local
    service-management infrastructure on the host).
    """

    may_need_mpm = False
    apache_bin = osutils.Which("apache2")
    if apache_bin is None:
        apache_bin = osutils.Which("apache2", PROXY_APACHE_FALLBACK_PATH)
        if apache_bin is None:
            _ReportMissing(("apache2",))
    else:
        may_need_mpm = True

    # Module names and .so names included for ease of grepping.
    apache_modules = [
        ("proxy_module", "mod_proxy.so"),
        ("proxy_connect_module", "mod_proxy_connect.so"),
        ("proxy_http_module", "mod_proxy_http.so"),
        ("proxy_ftp_module", "mod_proxy_ftp.so"),
    ]

    # Find the apache module directory and make sure it has the modules we need.
    module_dirs = {}
    for g in PROXY_APACHE_MODULE_GLOBS:
        for _, so in apache_modules:
            for f in glob.glob(os.path.join(g, so)):
                module_dirs.setdefault(os.path.dirname(f), []).append(so)
    for apache_module_path, modules_found in module_dirs.items():
        if len(modules_found) == len(apache_modules):
            break
    else:
        # Appease cros lint, which doesn't understand that this else block will
        # not fall through to the subsequent code which relies on
        # apache_module_path.
        apache_module_path = None
        raise SystemExit(
            "Could not find apache module path containing all required "
            "modules: %s" % ", ".join(so for mod, so in apache_modules)
        )

    def check_add_module(name):
        so = "mod_%s.so" % name
        if os.access(os.path.join(apache_module_path, so), os.F_OK):
            mod = "%s_module" % name
            apache_modules.append((mod, so))
            return True
        return False

    check_add_module("authz_core")
    if may_need_mpm:
        for mpm in PROXY_APACHE_MPMS:
            if check_add_module("mpm_%s" % mpm):
                break

    veth_host = "%s-host" % PROXY_VETH_PREFIX
    veth_guest = "%s-guest" % PROXY_VETH_PREFIX

    # Set up locks to sync the net namespace setup.  We need the child to create
    # the net ns first, and then have the parent assign the guest end of the
    # veth interface to the child's new network namespace & bring up the proxy.
    # Only then can the child move forward and rely on the network being up.
    ns_create_lock = locking.PipeLock()
    ns_setup_lock = locking.PipeLock()

    pid = os.fork()
    if not pid:
        # Create our new isolated net namespace.
        namespaces.Unshare(namespaces.CLONE_NEWNET)

        # Signal the parent the ns is ready to be configured.
        ns_create_lock.Post()
        del ns_create_lock

        # Wait for the parent to finish setting up the ns/proxy.
        ns_setup_lock.Wait()
        del ns_setup_lock

        # Set up child side of the network.
        commands = (
            ("ip", "link", "set", "up", "lo"),
            (
                "ip",
                "address",
                "add",
                "%s/%u" % (PROXY_GUEST_IP, PROXY_NETMASK),
                "dev",
                veth_guest,
            ),
            ("ip", "link", "set", veth_guest, "up"),
        )
        try:
            for cmd in commands:
                cros_build_lib.dbg_run(cmd)
        except cros_build_lib.RunCommandError as e:
            cros_build_lib.Die("Proxy setup failed!\n%s", e)

        proxy_url = "http://%s:%u" % (PROXY_HOST_IP, PROXY_PORT)
        for proto in ("http", "https", "ftp"):
            os.environ[proto + "_proxy"] = proxy_url
        for v in ("all_proxy", "RSYNC_PROXY", "no_proxy"):
            os.environ.pop(v, None)
        return

    # Set up parent side of the network.
    uid = int(os.environ.get("SUDO_UID", "0"))
    gid = int(os.environ.get("SUDO_GID", "0"))
    if uid == 0 or gid == 0:
        for username in PROXY_APACHE_FALLBACK_USERS:
            try:
                pwnam = pwd.getpwnam(username)
                uid, gid = pwnam.pw_uid, pwnam.pw_gid
                break
            except KeyError:
                continue
        if uid == 0 or gid == 0:
            raise SystemExit("Could not find a non-root user to run Apache as")

    chroot_parent, chroot_base = os.path.split(options.chroot)
    pid_file = os.path.join(chroot_parent, ".%s-apache-proxy.pid" % chroot_base)
    log_file = os.path.join(chroot_parent, ".%s-apache-proxy.log" % chroot_base)

    # Wait for the child to create the net ns.
    ns_create_lock.Wait()
    del ns_create_lock

    apache_directives = [
        "User #%u" % uid,
        "Group #%u" % gid,
        "PidFile %s" % pid_file,
        "ErrorLog %s" % log_file,
        "Listen %s:%u" % (PROXY_HOST_IP, PROXY_PORT),
        "ServerName %s" % PROXY_HOST_IP,
        "ProxyRequests On",
        "AllowCONNECT %s" % " ".join(str(x) for x in PROXY_CONNECT_PORTS),
    ] + [
        "LoadModule %s %s" % (mod, os.path.join(apache_module_path, so))
        for (mod, so) in apache_modules
    ]
    commands = (
        (
            "ip",
            "link",
            "add",
            "name",
            veth_host,
            "type",
            "veth",
            "peer",
            "name",
            veth_guest,
        ),
        (
            "ip",
            "address",
            "add",
            "%s/%u" % (PROXY_HOST_IP, PROXY_NETMASK),
            "dev",
            veth_host,
        ),
        ("ip", "link", "set", veth_host, "up"),
        (
            [apache_bin, "-f", "/dev/null"]
            + [arg for d in apache_directives for arg in ("-C", d)]
        ),
        ("ip", "link", "set", veth_guest, "netns", str(pid)),
    )
    cmd = None  # Make cros lint happy.
    try:
        for cmd in commands:
            cros_build_lib.dbg_run(cmd)
    except cros_build_lib.RunCommandError as e:
        # Clean up existing interfaces, if any.
        cmd_cleanup = ("ip", "link", "del", veth_host)
        try:
            cros_build_lib.run(cmd_cleanup, print_cmd=False)
        except cros_build_lib.RunCommandError:
            logging.error("running %r failed", cmd_cleanup)
        cros_build_lib.Die("Proxy network setup failed!\n%s", e)

    # Signal the child that the net ns/proxy is fully configured now.
    ns_setup_lock.Post()
    del ns_setup_lock

    process_util.ExitAsStatus(os.waitpid(pid, 0)[1])


def _BuildReExecCommand(argv, opts) -> List[str]:
    """Generate new command for self-reexec."""
    # Make sure to preserve the active Python executable in case the version
    # we're running as is not the default one found via the (new) $PATH.
    cmd = _SudoCommand() + ["--"]
    if opts.strace:
        cmd += ["strace"] + shlex.split(opts.strace_arguments) + ["--"]
    return cmd + [sys.executable] + argv


def _ReExecuteIfNeeded(argv, opts):
    """Re-execute cros_sdk as root.

    Also unshare the mount namespace so as to ensure that processes outside
    the chroot can't mess with our mounts.
    """
    if osutils.IsNonRootUser():
        cmd = _BuildReExecCommand(argv, opts)
        logging.debug(
            "Reexecing self via sudo:\n%s", cros_build_lib.CmdToStr(cmd)
        )
        os.execvp(cmd[0], cmd)


def _CreateParser(
    sdk_latest_version: str, bootstrap_latest_version: str
) -> Tuple[argparse.ArgumentParser, argparse._ArgumentGroup]:
    """Generate and return the parser with all the options."""
    usage = (
        "usage: %(prog)s [options] "
        "[VAR1=val1 ... VAR2=val2] [--] [command [args]]"
    )
    parser = commandline.ArgumentParser(
        usage=usage, description=__doc__, caching=True
    )

    # Global options.
    parser.add_argument(
        "--chroot",
        dest="chroot",
        default=constants.DEFAULT_CHROOT_PATH,
        type="path",
        help=("SDK chroot dir name [%s]" % constants.DEFAULT_CHROOT_DIR),
    )
    parser.add_argument(
        "--out-dir",
        metavar="DIR",
        default=constants.DEFAULT_OUT_PATH,
        type=Path,
        help="Use DIR for build state and output files",
    )
    parser.add_argument(
        "--nouse-image",
        dest="use_image",
        action="store_false",
        default=False,
        deprecated="--[no]use-image is no longer supported (b/266878468).",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--use-image",
        dest="use_image",
        action="store_true",
        default=False,
        deprecated="--[no]use-image is no longer supported (b/266878468).",
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--chrome-root",
        "--chrome_root",
        type="path",
        help="Mount this chrome root into the SDK chroot",
    )
    parser.add_argument(
        "--chrome_root_mount",
        type="path",
        help="Mount chrome into this path inside SDK chroot",
    )
    parser.add_argument(
        "--nousepkg",
        action="store_true",
        default=False,
        help="Do not use binary packages when creating a chroot.",
    )
    parser.add_argument(
        "-u",
        "--url",
        dest="sdk_url",
        help="Use sdk tarball located at this url. Use file:// "
        "for local files.",
    )
    parser.add_argument(
        "--sdk-version",
        help=(
            "Use this sdk version.  For prebuilt, current is %r"
            ", for bootstrapping it is %r."
            % (sdk_latest_version, bootstrap_latest_version)
        ),
    )
    parser.add_argument(
        "--goma-dir",
        "--goma_dir",
        type="dir_exists",
        help="Goma installed directory to mount into the chroot.",
    )
    parser.add_argument(
        "--reclient-dir",
        type="dir_exists",
        help="Reclient installed directory to mount into the chroot.",
    )
    parser.add_argument(
        "--reproxy-cfg-file",
        type="file_exists",
        help="Config file for re-client's reproxy used for remoteexec.",
    )
    parser.add_argument(
        "--skip-chroot-upgrade",
        dest="chroot_upgrade",
        action="store_false",
        default=True,
        help="Skip automatic SDK and toolchain upgrade when entering the "
        "chroot. Never guaranteed to work, especially as ToT moves forward.",
    )
    parser.add_bool_argument(
        "--delete-out-dir",
        default=True,
        enabled_desc="Delete the SDK build state along with the chroot. "
        "Applies to --delete or --replace.",
        disabled_desc="Don't delete the SDK build state along with the chroot. "
        "Applies to --delete or --replace.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force delete of the current SDK chroot even if "
        "obtaining the write lock fails. Applies only to --delete or "
        "--replace.",
    )
    parser.add_bool_argument(
        "--read-only",
        default=None,
        enabled_desc="Mount the SDK read-only.",
        disabled_desc="Do not mount the SDK read-only. "
        "This is default, but see also --read-only-sticky.",
    )
    parser.add_bool_argument(
        "--read-only-sticky",
        default=False,
        enabled_desc="Remember the --[no-]read-only setting for future runs.",
        disabled_desc="Leave --[no-]read-only stickiness alone.",
    )

    # Use type=str instead of type='path' to prevent the given path from being
    # transferred to absolute path automatically.
    parser.add_argument(
        "--working-dir",
        type=Path,
        help="Run the command in specific working directory in "
        "chroot.  If the given directory is a relative "
        "path, this program will transfer the path to "
        "the corresponding one inside chroot.",
    )

    parser.add_argument("commands", nargs=argparse.REMAINDER)

    # Commands.
    group = parser.add_argument_group("Commands")
    group.add_argument(
        "--enter",
        action="store_true",
        default=False,
        help="Enter the SDK chroot.  Implies --create.",
    )
    group.add_argument(
        "--create",
        action="store_true",
        default=False,
        help="Create the chroot only if it does not already exist. Downloads "
        "the SDK only if needed, even if --download explicitly passed.",
    )
    group.add_argument(
        "--bootstrap",
        action="store_true",
        default=False,
        help="Build everything from scratch, including the sdk.  "
        "Use this only if you need to validate a change "
        "that affects SDK creation itself (toolchain and "
        "build are typically the only folk who need this).  "
        "Note this will quite heavily slow down the build.  "
        "This option implies --create --nousepkg.",
    )
    group.add_argument(
        "-r",
        "--replace",
        action="store_true",
        default=False,
        help="Replace an existing SDK chroot.  Basically an alias "
        "for --delete --create.",
    )
    group.add_argument(
        "--delete",
        action="store_true",
        default=False,
        help="Delete the current SDK chroot and build state if they exist.",
    )
    group.add_argument(
        "--unmount",
        action="store_true",
        default=False,
        deprecated="loopback-image (--use-image) is no longer supported "
        "(b/266878468). If needed, consider `cros unmount /path/to/chroot`.",
        help=argparse.SUPPRESS,
    )
    group.add_argument(
        "--download",
        action="store_true",
        default=False,
        help="Download the sdk.",
    )
    commands = group

    # Namespace options.
    group = parser.add_argument_group("Namespaces")
    group.add_argument(
        "--proxy-sim",
        action="store_true",
        default=False,
        help="Simulate a restrictive network requiring an outbound" " proxy.",
    )
    for ns, default in (("pid", True), ("net", None)):
        group.add_argument(
            f"--ns-{ns}",
            default=default,
            action="store_true",
            help=f"Create a new {ns} namespace.",
        )
        group.add_argument(
            f"--no-ns-{ns}",
            dest=f"ns_{ns}",
            action="store_false",
            help=f"Do not create a new {ns} namespace.",
        )

    # Debug options.
    group = parser.debug_group
    group.add_argument(
        "--strace",
        action="store_true",
        help="Run cros_sdk through strace after re-exec via sudo",
    )
    group.add_argument(
        "--strace-arguments",
        default="",
        help="Extra strace options (shell quoting permitted)",
    )

    # Internal options.
    group = parser.add_argument_group(
        "Internal Chromium OS Build Team Options",
        "Caution: these are for meant for the Chromium OS build team only",
    )
    group.add_argument(
        "--buildbot-log-version",
        default=False,
        action="store_true",
        help="Log SDK version for buildbot consumption",
    )

    return parser, commands


def _FinalizeOptions(
    parser: argparse.ArgumentParser,
    options: argparse.Namespace,
    commands: argparse._ArgumentGroup,
) -> None:
    """Perform any options tweaking, and prevent further modification."""

    # Expand out the aliases...
    if options.replace:
        options.delete = options.create = True

    if options.bootstrap:
        options.create = True

    # If a command is not given, default to enter.
    # pylint: disable=protected-access
    # This _group_actions access sucks, but upstream decided to not include an
    # alternative to optparse's option_list, and this is what they recommend.
    options.enter |= not any(
        getattr(options, x.dest) for x in commands._group_actions
    )
    # pylint: enable=protected-access
    options.enter |= bool(options.commands)

    if options.delete and not options.create and options.enter:
        parser.error(
            "Trying to enter the chroot when --delete "
            "was specified makes no sense."
        )

    if options.force and not options.delete:
        parser.error("Specifying --force without --delete does not make sense.")

    chroot_exists = cros_sdk_lib.IsChrootReady(options.chroot)
    # Finally, flip create if necessary.
    if options.enter:
        options.create |= not chroot_exists

    # Make sure we will download if we plan to create.
    options.download |= options.create

    if options.read_only is None and options.read_only_sticky:
        parser.error(
            "Specifying --read-only-sticky without --read-only or "
            "--no-read-only does not make sense."
        )

    chromite_config.initialize()
    ro_cfg = chromite_config.SDK_READONLY_STICKY_CONFIG
    if options.read_only is None:
        # Defer to sticky configuration file only if --read-only/--no-read-only
        # were not provided.
        options.read_only = ro_cfg.exists()

    options.Freeze()

    if options.reclient_dir and not options.reproxy_cfg_file:
        parser.error("--reclient-dir requires --reproxy-cfg-file")
    if not options.reclient_dir and options.reproxy_cfg_file:
        parser.error("--reproxy-cfg-file only makes sense with --reclient-dir")

    if options.read_only_sticky:
        # Notify the user when toggling stickiness.
        if options.read_only:
            if not ro_cfg.exists():
                logging.warning("Making cros_sdk --read-only sticky")
            ro_cfg.touch()
        else:
            if ro_cfg.exists():
                logging.warning("Making cros_sdk --no-read-only sticky")
                ro_cfg.unlink()


def main(argv):
    # Turn on strict sudo checks.
    cros_build_lib.STRICT_SUDO = True
    conf = key_value_store.LoadFile(
        constants.SDK_VERSION_FILE_FULL_PATH,
        ignore_missing=True,
    )
    sdk_latest_version = conf.get("SDK_LATEST_VERSION", "<unknown>")
    bootstrap_frozen_version = conf.get("BOOTSTRAP_FROZEN_VERSION", "<unknown>")

    # Use latest SDK for bootstrapping if requested. Use a frozen version of SDK
    # for bootstrapping if BOOTSTRAP_FROZEN_VERSION is set.
    bootstrap_latest_version = (
        sdk_latest_version
        if bootstrap_frozen_version == "<unknown>"
        else bootstrap_frozen_version
    )
    parser, commands = _CreateParser(
        sdk_latest_version, bootstrap_latest_version
    )
    options = parser.parse_args(argv)
    options.out_dir = options.out_dir.resolve()

    # Some basic checks first, before we ask for sudo credentials.
    cros_build_lib.AssertOutsideChroot()

    host = os.uname()[4]
    if host != "x86_64":
        cros_build_lib.Die(
            "cros_sdk is currently only supported on x86_64; you're running"
            " %s.  Please find a x86_64 machine." % (host,)
        )

    # Merge the outside PATH setting if we re-execed ourselves.
    if "CHROMEOS_SUDO_PATH" in os.environ:
        os.environ["PATH"] = "%s:%s" % (
            os.environ.pop("CHROMEOS_SUDO_PATH"),
            os.environ["PATH"],
        )

    _ReportMissing(osutils.FindMissingBinaries(NEEDED_TOOLS))
    if options.proxy_sim:
        _ReportMissing(osutils.FindMissingBinaries(PROXY_NEEDED_TOOLS))

    if (
        sdk_latest_version == "<unknown>"
        or bootstrap_latest_version == "<unknown>"
    ):
        cros_build_lib.Die(
            "No SDK version was found. "
            "Are you in a Chromium source tree instead of Chromium OS?\n\n"
            "Please change to a directory inside your Chromium OS source tree\n"
            "and retry.  If you need to setup a Chromium OS source tree, see\n"
            "  https://dev.chromium.org/chromium-os/developer-guide"
        )

    _ReExecuteIfNeeded([sys.argv[0]] + argv, options)

    # |options| cannot be modified after this.
    _FinalizeOptions(parser, options, commands)

    remoteexec = (
        remoteexec_util.Remoteexec(
            options.reclient_dir, options.reproxy_cfg_file
        )
        if (options.reclient_dir and options.reproxy_cfg_file)
        else None
    )

    goma = (
        goma_lib.Goma(
            options.goma_dir, chroot_dir=options.chroot, out_dir=options.out_dir
        )
        if options.goma_dir
        else None
    )

    chroot = chroot_lib.Chroot(
        path=options.chroot,
        out_path=options.out_dir,
        cache_dir=options.cache_dir,
        chrome_root=options.chrome_root,
        goma=goma,
        remoteexec=remoteexec,
    )

    lock_path = os.path.dirname(options.chroot)
    lock_path = os.path.join(
        lock_path, ".%s_lock" % os.path.basename(options.chroot).lstrip(".")
    )

    # Anything that needs to manipulate the main chroot mount or communicate
    # with LVM needs to be done here before we enter the new namespaces.

    if options.delete:
        # Set a timeout of 300 seconds when getting the lock.
        with locking.FileLock(
            lock_path, "chroot lock", blocking_timeout=300
        ) as lock:
            try:
                lock.write_lock()
            except timeout_util.TimeoutError as e:
                logging.error(
                    "Acquiring write_lock on %s failed: %s", lock_path, e
                )
                if not options.force:
                    cros_build_lib.Die(
                        "Exiting; use --force to continue w/o lock."
                    )
                else:
                    logging.warning(
                        "cros_sdk was invoked with force option, continuing."
                    )
            logging.notice("Deleting chroot: %s", chroot.path)
            logging.notice(
                "%s output dir: %s",
                "Deleting" if options.delete_out_dir else "Keeping",
                chroot.out_path,
            )
            cros_sdk_lib.CleanupChrootMount(
                chroot, delete=True, delete_out=options.delete_out_dir
            )

    # Enter a new set of namespaces.  Everything after here cannot directly
    # affect the hosts's mounts or alter LVM volumes.
    namespaces.SimpleUnshare(net=options.ns_net, pid=options.ns_pid)

    if not options.sdk_version:
        sdk_version = (
            bootstrap_latest_version
            if options.bootstrap
            else sdk_latest_version
        )
    else:
        sdk_version = options.sdk_version
    if options.buildbot_log_version:
        cbuildbot_alerts.PrintBuildbotStepText(sdk_version)

    # Based on selections, determine the tarball to fetch.
    urls = []
    if options.download:
        if options.sdk_url:
            urls = [options.sdk_url]
        else:
            urls = GetArchStageTarballs(sdk_version)

    with locking.FileLock(lock_path, "chroot lock") as lock:
        if options.proxy_sim:
            _ProxySimSetup(options)

        sdk_cache = os.path.join(chroot.cache_dir, "sdks")
        distfiles_cache = os.path.join(chroot.cache_dir, "distfiles")
        osutils.SafeMakedirsNonRoot(chroot.cache_dir)
        osutils.SafeMakedirsNonRoot(options.out_dir)
        # Create here (in addition to cros_sdk_lib.MountChrootPaths()) because
        # some usages want to create tmp files here even before we've fully
        # mounted the SDK.
        osutils.SafeMakedirsNonRoot(options.out_dir / "tmp", mode=0o1777)

        for target in (sdk_cache, distfiles_cache):
            src = os.path.join(constants.SOURCE_ROOT, os.path.basename(target))
            if not os.path.exists(src):
                osutils.SafeMakedirsNonRoot(target)
                continue
            lock.write_lock(
                "Upgrade to %r needed but chroot is locked; please exit "
                "all instances so this upgrade can finish." % src
            )
            if not os.path.exists(src):
                # Note that while waiting for the write lock, src may've
                # vanished; it's a rare race during the upgrade process that's a
                # byproduct of us avoiding taking a write lock to do the src
                # check.  If we took a write lock for that check, it would
                # effectively limit all cros_sdk for a chroot to a single
                # instance.
                osutils.SafeMakedirsNonRoot(target)
            elif not os.path.exists(target):
                # Upgrade occurred, but a reversion, or something whacky
                # occurred writing to the old location.  Wipe and continue.
                os.rename(src, target)
            else:
                # Upgrade occurred once already, but either a reversion or
                # some before/after separate cros_sdk usage is at play.
                # Wipe and continue.
                osutils.RmDir(src)

        cros_sdk_lib.MigrateStatePaths(chroot, lock)

        mounted = False
        if options.create:
            lock.write_lock()
            # Recheck if the chroot is set up here before creating to make sure
            # we account for whatever the various delete/cleanup steps above
            # have done.
            if cros_sdk_lib.IsChrootReady(chroot.path):
                logging.debug("Chroot already exists.  Skipping creation.")
            else:
                sdk_tarball = FetchRemoteTarballs(sdk_cache, urls)
                cros_sdk_lib.CreateChroot(
                    chroot,
                    Path(sdk_tarball),
                    usepkg=not options.bootstrap and not options.nousepkg,
                    chroot_upgrade=options.chroot_upgrade,
                )
                mounted = True
        elif options.download:
            # Allow downloading only.
            lock.write_lock()
            FetchRemoteTarballs(sdk_cache, urls)

        if options.enter:
            lock.read_lock()
            if not mounted:
                cros_sdk_lib.MountChrootPaths(chroot)
            ret = cros_sdk_lib.EnterChroot(
                chroot,
                chrome_root_mount=options.chrome_root_mount,
                cwd=options.working_dir,
                cmd=options.commands,
                read_only=options.read_only,
            )
            sys.exit(ret.returncode)
