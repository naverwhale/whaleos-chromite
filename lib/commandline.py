# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Purpose of this module is to hold common script/commandline functionality.

This ranges from optparse, to a basic script wrapper setup (much like
what is used for chromite.bin.*).
"""

import argparse
import collections
import datetime
import functools
import logging
import optparse  # pylint: disable=deprecated-module
import os
from pathlib import Path
import re
import signal
import sys
from typing import List, NamedTuple, Optional
import urllib.parse

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.lib import terminal
from chromite.utils import attrs_freezer
from chromite.utils import gs_urls_util
from chromite.utils import path_filter


# TODO(build): Convert this to enum module.
DEVICE_SCHEME_FILE = "file"
DEVICE_SCHEME_SERVO = "servo"
DEVICE_SCHEME_SSH = "ssh"
DEVICE_SCHEME_USB = "usb"


class ChrootRequiredError(Exception):
    """Raised when a command must be run in the chroot

    This exception is intended to be caught by code which will restart execution
    in the chroot. Throwing this exception allows contexts to be exited and
    general cleanup to happen before we exec an external binary.

    The command to run inside the chroot, and (optionally) special cros_sdk
    arguments are attached to the exception. Any adjustments to the arguments
    should be done before raising the exception.
    """

    def __init__(self, cmd, chroot_args=None, extra_env=None):
        """Constructor for ChrootRequiredError.

        Args:
            cmd: Command line to run inside the chroot as a list of strings.
            chroot_args: Arguments to pass directly to cros_sdk.
            extra_env: Environmental variables to set in the chroot.
        """
        super().__init__()
        self.cmd = cmd
        self.chroot_args = chroot_args
        self.extra_env = extra_env


class ExecRequiredError(Exception):
    """Raised when a command needs to exec, after cleanup.

    This exception is intended to be caught by code which will exec another
    command. Throwing this exception allows contexts to be exited and general
    cleanup to happen before we exec an external binary.

    The command to run is attached to the exception. Any adjustments to the
    arguments should be done before raising the exception.
    """

    def __init__(self, cmd):
        """Constructor for ExecRequiredError.

        Args:
            cmd: Command line to run inside the chroot as a list of strings.
        """
        super().__init__()
        self.cmd = cmd


def NormalizeGSPath(value):
    """Normalize GS paths."""
    url = gs_urls_util.CanonicalizeURL(value, strict=True)
    return "%s%s" % (
        gs_urls_util.BASE_GS_URL,
        os.path.normpath(url[len(gs_urls_util.BASE_GS_URL) :]),
    )


def NormalizeLocalOrGSPath(value):
    """Normalize a local or GS path."""
    ptype = "gs_path" if gs_urls_util.PathIsGs(value) else "path"
    return VALID_TYPES[ptype](value)


def NormalizeAbUrl(value):
    """Normalize an androidbuild URL."""
    if not value.startswith("ab://"):
        # Give a helpful error message about the format expected.  Putting this
        # message in the exception is useless because argparse ignores the
        # exception message and just says the value is invalid.
        msg = "Invalid ab:// URL format: [%s]." % value
        logging.error(msg)
        raise ValueError(msg)

    # If no errors, just return the unmodified value.
    return value


def ValidateCipdURL(value):
    """Return plain string."""
    if not value.startswith("cipd://"):
        msg = "Invalid cipd:// URL format: %s" % value
        logging.error(msg)
        raise ValueError(msg)
    return value


def ParseBool(value):
    """Parse bool argument into a bool value.

    For the existing type=bool functionality, the parser uses the built-in
    bool(x) function to determine the value.  This function will only return
    false if x is False or omitted.  Even with this type specified, however,
    arguments that are generated from a command line initially get parsed as a
    string, and for any string value passed in to bool(x), it will always return
    True.

    Args:
        value: String representing a boolean value.

    Returns:
        True or False.
    """
    return cros_build_lib.BooleanShellValue(value, False)


def ParseDate(value):
    """Parse date argument into a datetime.date object.

    Args:
        value: String representing a single date in "YYYY-MM-DD" format.

    Returns:
        A datetime.date object.
    """
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        # Give a helpful error message about the format expected.  Putting this
        # message in the exception is useless because argparse ignores the
        # exception message and just says the value is invalid.
        logging.error("Date is expected to be in format YYYY-MM-DD.")
        raise


def ParseEmail(value: str) -> str:
    """Validate an e-mail address.

    Args:
        value: E-mail address.

    Returns:
        The input value.
    """
    if not re.fullmatch(constants.EMAIL_REGEX, value):
        raise ValueError(f"invalid e-mail address: {value}")

    return value


def ParseTimedelta(value: str):
    """Parse timedelta argument into datetime.timedelta object.

    Args:
        value: String in seconds.

    Returns:
        A datetime.timedelta object.
    """
    try:
        seconds = int(value)
        if seconds < 0:
            raise ValueError("Timedelta is expected to be a positive integer.")
        return datetime.timedelta(seconds=seconds)
    except ValueError:
        logging.error("Timedelta is expected to be a positive integer.")
        raise


def NormalizeUri(value):
    """Normalize a local path or URI."""
    o = urllib.parse.urlparse(value)
    if o.scheme == "file":
        # Trim off the file:// prefix.
        return VALID_TYPES["path"](value[7:])
    elif o.scheme not in ("", "gs"):
        o = list(o)
        o[2] = os.path.normpath(o[2])
        return urllib.parse.urlunparse(o)
    else:
        return NormalizeLocalOrGSPath(value)


class Device(NamedTuple):
    """A Device object holds information parsed from the command line input.

    For now this is a superset of all information for USB, SSH, or file devices.
    If functionality diverges based on type, it may be useful to split this into
    separate device classes instead.
    """

    # DEVICE_SCHEME_SSH, DEVICE_SCHEME_USB, DEVICE_SCHEME_SERVO, or
    # DEVICE_SCHEME_FILE.
    scheme: str

    # SSH username.
    username: Optional[str] = None

    # SSH hostname.
    hostname: Optional[str] = None

    # SSH or Servo port.
    port: Optional[int] = None

    # USB/file path.
    path: Optional[str] = None

    # Raw input from the command line.
    raw: Optional[str] = None

    # Servo serial number.
    serial_number: Optional[str] = None


class DeviceParser:
    """Parses devices as an argparse argument type.

    In addition to parsing user input, this class will also ensure that only
    supported device schemes are accepted by the parser. For example,
    `cros deploy` only makes sense with an SSH device, but `cros flash` can use
    SSH, USB, or file device schemes.

    If the device input is malformed or the scheme is wrong, an error message
    will be printed and the program will exit.

    Valid device inputs are:
        - [ssh://][username@]hostname[:port].
        - usb://[path].
        - file://path or /absolute_path.
        - servo:port[:port] to use a port via dut-control, e.g. servo:port:1234.
        - servo:serial:serial-number to use the servo's serial number,
            e.g. servo:serial:641220-00057 servo:serial:C1230024192.
        - [ssh://]:vm:.

    The last item above is an alias for ssh'ing into a virtual machine on a
    localhost.  It gets translated into 'localhost:9222'.

    Examples:
        parser = argparse.ArgumentParser()

        parser.add_argument(
            'ssh_device',
            type=commandline.DeviceParser(commandline.DEVICE_SCHEME_SSH)
        )

        parser.add_argument(
            "usb_or_file_device",
            type=commandline.DeviceParser(
                [commandline.DEVICE_SCHEME_USB, commandline.DEVICE_SCHEME_FILE]
            ),
        )
    """

    def __init__(self, schemes):
        """Initializes the parser.

        See the class comments for usage examples.

        Args:
            schemes: A scheme or list of schemes to accept.
        """
        self.schemes = [schemes] if isinstance(schemes, str) else schemes
        # Provide __name__ for argparse to print on failure, or else it will use
        # repr() which creates a confusing error message.
        self.__name__ = type(self).__name__

    def __call__(self, value):
        """Parses a device input and enforces constraints.

        DeviceParser is an object so that a set of valid schemes can be
        specified, but argparse expects a parsing function, so we overload
        __call__() for argparse to use.

        Args:
            value: String representing a device target. See class comments for
            valid device input formats.

        Returns:
            A Device object.

        Raises:
            ValueError: |value| is not a valid device specifier or doesn't
            match the supported list of schemes.
        """
        try:
            device = self._ParseDevice(value)
            self._EnforceConstraints(device, value)
            return device
        except ValueError as e:
            # argparse ignores exception messages, so print the message
            # manually.
            logging.error(e)
            raise
        except Exception as e:
            logging.error("Internal error while parsing device input: %s", e)
            raise

    def _EnforceConstraints(self, device, value):
        """Verifies that user-specified constraints are upheld.

        Checks that the parsed device has a scheme that matches what the user
        expects. Additional constraints can be added if needed.

        Args:
            device: Device object.
            value: String representing a device target.

        Raises:
            ValueError: |device| has the wrong scheme.
        """
        if device.scheme not in self.schemes:
            raise ValueError(
                'Unsupported scheme "%s" for device "%s"'
                % (device.scheme, value)
            )

    def _ParseDevice(self, value):
        """Parse a device argument.

        Args:
            value: String representing a device target.

        Returns:
            A Device object.

        Raises:
            ValueError: |value| is not a valid device specifier.
        """
        # ':vm:' is an alias for ssh'ing into a virtual machihne on localhost;
        # translate it appropriately.
        if value.strip().lower() == ":vm:":
            value = "localhost:9222"
        elif value.strip().lower() == "ssh://:vm:":
            value = "ssh://localhost:9222"
        parsed = urllib.parse.urlparse(value)

        # crbug.com/1069325: Starting in python 3.7 urllib has different parsing
        # results. 127.0.0.1:9999 parses as scheme='127.0.0.1' path='9999'
        # instead of scheme='' path='127.0.0.1:9999'. We want that parsed as
        # ssh. Check for '.' or 'localhost' in the scheme to catch the most
        # common cases for this result.
        if (
            not parsed.scheme
            or "." in parsed.scheme
            or parsed.scheme == "localhost"
        ):
            # Default to a file scheme for absolute paths, SSH scheme otherwise.
            if value and value[0] == "/":
                scheme = DEVICE_SCHEME_FILE
            else:
                # urlparse won't provide hostname/username/port unless a scheme
                # is specified, so we need to reparse.
                parsed = urllib.parse.urlparse(
                    "%s://%s" % (DEVICE_SCHEME_SSH, value)
                )
                scheme = DEVICE_SCHEME_SSH
        else:
            scheme = parsed.scheme.lower()

        if scheme == DEVICE_SCHEME_SSH:
            hostname = parsed.hostname
            if not hostname and parsed.netloc.count(":") >= 2:
                # Likely an IPv6 address that is missing brackets.  Remind the
                # user to add those brackets.
                raise ValueError(
                    "To write an IPv6 address, you must include brackets to "
                    "distinguish between host and port.  For example, write "
                    "[::1]:2222 instead of ::1:2222."
                )
            port = parsed.port
            if hostname == "localhost" and not port:
                # Use of localhost as the actual machine is uncommon enough
                # relative to the use of KVM that we require users to specify
                # localhost:22 if they actually want to connect to the
                # localhost.  Otherwise, the expectation is that they intend to
                # access the VM but forget or didn't know to use port 9222.
                raise ValueError(
                    "To connect to localhost, use ssh://localhost:22 "
                    "explicitly, or use ssh://localhost:9222 for the local"
                    " VM."
                )
            if not hostname:
                raise ValueError('Hostname is required for device "%s"' % value)
            return Device(
                scheme=scheme,
                username=parsed.username,
                hostname=hostname,
                port=port,
                raw=value,
            )
        elif scheme == DEVICE_SCHEME_USB:
            path = parsed.netloc + parsed.path
            # Change path '' to None for consistency.
            return Device(scheme=scheme, path=path if path else None, raw=value)
        elif scheme == DEVICE_SCHEME_FILE:
            path = parsed.netloc + parsed.path
            if not path:
                raise ValueError('Path is required for "%s"' % value)
            return Device(scheme=scheme, path=path, raw=value)
        elif scheme == DEVICE_SCHEME_SERVO:
            # Parse the identifier type and value.
            servo_type, _, servo_id = parsed.path.partition(":")
            # Don't want to do the netloc before the split in case of serial
            # number.
            servo_type = servo_type.lower()

            return self._parse_servo(servo_type, servo_id)
        else:
            raise ValueError(
                'Unknown device scheme "%s" in "%s"' % (scheme, value)
            )

    @staticmethod
    def _parse_servo(servo_type, servo_id):
        """Parse a servo device from the parsed servo uri info.

        Args:
            servo_type: The servo identifier type, either port or serial.
            servo_id: The servo identifier, either the port number it is
                communicating through or its serial number.
        """
        servo_port = None
        serial_number = None
        if servo_type == "serial":
            if servo_id:
                serial_number = servo_id
            else:
                raise ValueError("No serial number given.")
        elif servo_type == "port":
            if servo_id:
                # Parse and validate when given.
                try:
                    servo_port = int(servo_id)
                except ValueError:
                    raise ValueError("Invalid servo port value: %s" % servo_id)
                if servo_port <= 0 or servo_port > 65535:
                    raise ValueError(
                        "Invalid port, must be 1-65535: %d given." % servo_port
                    )
        else:
            raise ValueError("Invalid servo type given: %s" % servo_type)

        return Device(
            scheme=DEVICE_SCHEME_SERVO,
            port=servo_port,
            serial_number=serial_number,
        )


class _AppendOption(argparse.Action):
    """Append the command line option (with no arguments) to dest.

    parser.add_argument('-b', '--barg', dest='out', action='append_option')
    options = parser.parse_args(['-b', '--barg'])
    options.out == ['-b', '--barg']
    """

    def __init__(self, option_strings, dest, **kwargs):
        if "nargs" in kwargs:
            raise ValueError("nargs is not supported for append_option action")
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is None:
            setattr(namespace, self.dest, [])
        getattr(namespace, self.dest).append(option_string)


class _AppendOptionValue(argparse.Action):
    """Append the command line option to dest. Useful for pass along arguments.

    parser.add_argument(
        "-b",
        "--barg",
        dest="out",
        action="append_option_value",
    )
    options = parser.parse_args(["--barg", "foo", "-b", "bar"])
    options.out == ["-barg", "foo", "-b", "bar"]
    """

    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is None:
            setattr(namespace, self.dest, [])
        getattr(namespace, self.dest).extend([option_string, str(values)])


class _EnumAction(argparse.Action):
    """Allows adding enums as an argument with minimal syntax.

    For example:
        class Size(enum.Enum):
             SMALL = 0
             MEDIUM = 1
             LARGE = 2
        ...
        parser.add_argument(
            "--size",
            action="enum",
            enum=Size,
            help="The size to use (either small, medium, or large)",
        )
    """

    def __init__(self, *args, **kwargs):
        """Init override to extract the "enum" argument."""
        self.enum = kwargs.pop("enum", None)
        if self.enum:
            kwargs.setdefault("choices", self.enum.__members__.values())

            valid_inputs = [x.lower() for x in self.enum.__members__]
            kwargs.setdefault("metavar", "{%s}" % ",".join(valid_inputs))

            def _parse_arg(arg):
                if arg not in valid_inputs:
                    raise argparse.ArgumentTypeError(
                        f"{arg!r} is not recognized.  Choose from "
                        f"{valid_inputs!r}"
                    )
                return self.enum[arg.upper()]

            kwargs.setdefault("type", _parse_arg)

        super().__init__(*args, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)


class _SplitExtendAction(argparse.Action):
    """Callback to split the argument and extend existing value.

    We normalize whitespace before splitting.  This is to support the forms:
        cbuildbot -p 'proj:branch ' ...
        cbuildbot -p ' proj:branch' ...
        cbuildbot -p 'proj:branch  proj2:branch' ...
        cbuildbot -p "$(some_command_that_returns_nothing)" ...
    """

    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is None:
            setattr(namespace, self.dest, [])
        getattr(namespace, self.dest).extend(values.split())


def ExistingPath(value: str) -> Path:
    """Expands ~/ paths and standardizes to the real path.

    Checks that the path exists.
    """
    ret = osutils.ExpandPath(value)
    path = Path(ret)
    if not path.exists():
        msg = f"Path does not exist: {value}"
        logging.error(msg)
        raise ValueError(msg)
    return path


def ExistingDirectory(value: str) -> Path:
    """Expands ~/ paths and standardizes to the real path.

    Checks that the path exists and is a file.
    """
    path = ExistingPath(value)
    if not path.is_dir():
        msg = f"Path is not a directory: {value}"
        logging.error(msg)
        raise ValueError(msg)
    return path


def ExistingFile(value: str) -> Path:
    """Expands ~/ paths and standardizes to the real path.

    Checks that the path exists and is a directory.
    """
    path = ExistingPath(value)
    if not path.is_file():
        msg = f"Path is not a file: {value}"
        logging.error(msg)
        raise ValueError(msg)
    return path


VALID_TYPES = {
    "ab_url": NormalizeAbUrl,
    "bool": ParseBool,
    "cipd": ValidateCipdURL,
    "date": ParseDate,
    "email": ParseEmail,
    "path": osutils.ExpandPath,
    "path_exists": ExistingPath,
    "dir_exists": ExistingDirectory,
    "file_exists": ExistingFile,
    "gs_path": NormalizeGSPath,
    "local_or_gs_path": NormalizeLocalOrGSPath,
    "path_or_uri": NormalizeUri,
    "timedelta": ParseTimedelta,
}

VALID_ACTIONS = {
    "append_option": _AppendOption,
    "append_option_value": _AppendOptionValue,
    "enum": _EnumAction,
    "split_extend": _SplitExtendAction,
}

_DEPRECATE_ACTIONS = [
    None,
    "store",
    "store_const",
    "store_true",
    "store_false",
    "append",
    "append_const",
    "count",
] + list(VALID_ACTIONS)


class _DeprecatedAction:
    """Base functionality to allow adding warnings for deprecated arguments.

    To add a deprecated warning, simply include a deprecated=message argument
    to the add_argument call for the deprecated argument. Beside logging the
    deprecation warning, the argument will behave as normal.
    """

    def __init__(self, *args, **kwargs):
        """Init override to extract the deprecated argument when it exists."""
        self.deprecated_message = kwargs.pop("deprecated", None)
        super().__init__(*args, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        """Log the message then defer to the parent action."""
        if self.deprecated_message:
            logging.warning(
                "Argument %s is deprecated: %s",
                option_string,
                self.deprecated_message,
            )
        return super().__call__(
            parser, namespace, values, option_string=option_string
        )


def OptparseWrapCheck(desc, check_f, _option, opt, value):
    """Optparse adapter for type checking functionality."""
    try:
        return check_f(value)
    except ValueError:
        raise optparse.OptionValueError(
            "Invalid %s given: --%s=%s" % (desc, opt, value)
        )


class Option(optparse.Option):
    """Subclass to implement path evaluation & other useful types."""

    _EXTRA_TYPES = ("path", "gs_path")
    TYPES = optparse.Option.TYPES + _EXTRA_TYPES
    TYPE_CHECKER = optparse.Option.TYPE_CHECKER.copy()
    for t in _EXTRA_TYPES:
        TYPE_CHECKER[t] = functools.partial(
            OptparseWrapCheck, t, VALID_TYPES[t]
        )


class FilteringOption(Option):
    """Subclass that supports Option filtering for FilteringOptionParser"""

    _EXTRA_ACTIONS = ("split_extend",)
    ACTIONS = Option.ACTIONS + _EXTRA_ACTIONS
    STORE_ACTIONS = Option.STORE_ACTIONS + _EXTRA_ACTIONS
    TYPED_ACTIONS = Option.TYPED_ACTIONS + _EXTRA_ACTIONS
    ALWAYS_TYPED_ACTIONS = Option.ALWAYS_TYPED_ACTIONS + _EXTRA_ACTIONS

    def take_action(self, action, dest, opt, value, values, parser):
        if action == "split_extend":
            lvalue = value.split()
            values.ensure_value(dest, []).extend(lvalue)
        else:
            Option.take_action(self, action, dest, opt, value, values, parser)

        if value is None:
            value = []
        elif not self.nargs or self.nargs <= 1:
            value = [value]

        parser.AddParsedArg(self, opt, [str(v) for v in value])


class _PathFilterAction(argparse.Action):
    """Setup a path filter."""

    def __init__(self, option_strings, dest, **kwargs):
        if "nargs" in kwargs:
            raise ValueError("nargs is not supported for filter action")
        super().__init__(option_strings, dest, nargs=1, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is None:
            setattr(namespace, self.dest, path_filter.PathFilter([]))
        getattr(namespace, self.dest).rules.extend(values)


class ColoredFormatter(logging.Formatter):
    """A logging formatter that can color the messages."""

    _COLOR_MAPPING = {
        "WARNING": terminal.Color.YELLOW,
        "ERROR": terminal.Color.RED,
    }

    def __init__(self, *args, **kwargs):
        """Initializes the formatter.

        Args:
            *args: See logging.Formatter for specifics.
            **kwargs: See logging.Formatter for specifics.
            enable_color: Whether to enable colored logging. Defaults
                to None, where terminal.Color will set to a reasonable default.
        """
        self.color = terminal.Color(enabled=kwargs.pop("enable_color", None))
        super().__init__(*args, **kwargs)

    def format(self, record):
        """Formats |record| with color."""
        msg = super().format(record)
        color = self._COLOR_MAPPING.get(record.levelname)
        return msg if not color else self.color.Color(color, msg)


class ChromiteStreamHandler(logging.StreamHandler):
    """A stream handler for logging."""


class BaseParser:
    """Base parser class that includes the logic to add logging controls."""

    DEFAULT_LOG_LEVELS = (
        "fatal",
        "critical",
        "error",
        "warning",
        "notice",
        "info",
        "debug",
    )

    DEFAULT_LOG_LEVEL = "info"
    ALLOW_LOGGING = True

    def __init__(self, **kwargs):
        """Initialize this parser instance.

        kwargs:
            logging: Defaults to ALLOW_LOGGING from the class; if given,
                add --log-level.
            default_log_level: If logging is enabled, override the default
                logging level. Defaults to the class's DEFAULT_LOG_LEVEL value.
            log_levels: If logging is enabled, this overrides the enumeration of
                allowed logging levels. If not given, defaults to the classes
                DEFAULT_LOG_LEVELS value.
            manual_debug: If logging is enabled and this is True, suppress
                addition of a --debug alias. This option defaults to True unless
                'debug' has been exempted from the allowed logging level
                targets.
            caching: If given, must be either a callable that discerns the cache
                location if it wasn't specified (the prototype must be akin to
                lambda parser, values:calculated_cache_dir_path; it may return
                None to indicate that it handles setting the value on its own
                later in the parsing including setting the env), or True; if
                True, the machinery defaults to invoking the class's
                FindCacheDir method (which can be overridden). FindCacheDir
                $CROS_CACHEDIR, falling back to $REPO/.cache, finally falling
                back to $TMP. Note that the cache_dir is not created, just
                discerned where it should live.
                If False, or caching is not given, then no --cache-dir option
                will be added.
            dryrun: Whether to make --dry-run available.
            filter: If given, set up a filter for --include and --exclude paths.
                The resulting filter is in opts.filter.
        """
        self.debug_enabled = False
        self.caching_group = None
        self.debug_group = None
        self.default_log_level = None
        self.log_levels = None
        self.logging_enabled = kwargs.get("logging", self.ALLOW_LOGGING)
        self.default_log_level = kwargs.get(
            "default_log_level", self.DEFAULT_LOG_LEVEL
        )
        self.log_levels = tuple(
            x.lower() for x in kwargs.get("log_levels", self.DEFAULT_LOG_LEVELS)
        )
        self.debug_enabled = (
            not kwargs.get("manual_debug", False) and "debug" in self.log_levels
        )
        self.caching = kwargs.get("caching", False)
        self.dryrun_enabled = kwargs.get("dryrun", False)
        self.filter_enabled = kwargs.get("filter", False)
        self._cros_defaults = {}

    @staticmethod
    def PopUsedArgs(kwarg_dict):
        """Removes keys used by the base parser from the kwarg namespace."""
        parser_keys = [
            "logging",
            "default_log_level",
            "log_levels",
            "manual_debug",
            "caching",
            "dryrun",
            "filter",
        ]
        for key in parser_keys:
            kwarg_dict.pop(key, None)

    def SetupOptions(self):
        """Sets up standard chromite options."""
        # NB: All options here must go through add_common_argument_to_group.
        # You cannot use add_argument or such helpers directly.  This is to
        # support default values with subparsers.
        #
        # You should also explicitly add default=None here when you want the
        # default to be set up in the parsed option namespace.
        if self.logging_enabled:
            self.debug_group = self.add_argument_group("Debug options")
            self.add_common_argument_to_group(
                self.debug_group,
                "--log-level",
                choices=self.log_levels,
                default=self.default_log_level,
                help="Set logging level to report at.",
            )
            self.add_common_argument_to_group(
                self.debug_group,
                "--log-format",
                action="store",
                default=constants.LOGGER_FMT,
                help="Set logging format to use.",
            )
            # Backwards compat name.  We should delete this at some point.
            self.add_common_argument_to_group(
                self.debug_group,
                "--log_format",
                action="store",
                default=constants.LOGGER_FMT,
                help=argparse.SUPPRESS,
            )
            self.add_common_argument_to_group(
                self.debug_group,
                "-v",
                "--verbose",
                action="store_const",
                const="info",
                dest="log_level",
                help="Alias for `--log-level=info`.",
            )
            if self.debug_enabled:
                self.add_common_argument_to_group(
                    self.debug_group,
                    "--debug",
                    action="store_const",
                    const="debug",
                    dest="log_level",
                    help="Alias for `--log-level=debug`. "
                    "Useful for debugging bugs/failures.",
                )
            self.add_common_argument_to_group(
                self.debug_group,
                "--color",
                action="store_true",
                default=None,
                help="Colorize output (default: auto-detect).",
            )
            self.add_common_argument_to_group(
                self.debug_group,
                "--no-color",
                "--nocolor",
                action="store_false",
                dest="color",
                help="Do not colorize output (or `export NOCOLOR=true`).",
            )
            self.add_common_argument_to_group(
                self.debug_group,
                "--log-telemetry",
                action="store_false",
                help="Log telemetry spans.",
            )

        if self.caching:
            self.caching_group = self.add_argument_group("Caching Options")
            self.add_common_argument_to_group(
                self.caching_group,
                "--cache-dir",
                default=None,
                type="path",
                help="Override the calculated chromeos cache directory; "
                "typically defaults to '$REPO/.cache' .",
            )

        if self.dryrun_enabled:
            self.add_argument(
                "-n",
                "--dry-run",
                dest="dryrun",
                action="store_true",
                help="Show what would be done, but don't do it.",
            )
            self.add_argument(
                "--dryrun",
                dest="dryrun",
                action="store_true",
                help=argparse.SUPPRESS,
            )
        if self.filter_enabled:
            filter_group = self.add_argument_group(
                "Path filter options",
                "Filter file paths based on PATTERN (see man 3 fnmatch). "
                "If multiple --exclude and --include rules are specified, "
                "the first that matches takes effect. "
                "If no rules are matched, the path is included by default. "
                "PATTERNS apply to the full path of the file. "
                "For example --exclude='*.py' matches a/foo.py and bar.py; "
                "--exclude=BUILD matches BUILD but not a/BUILD.",
            )
            filter_group.add_argument(
                "--exclude",
                metavar="PATTERN",
                action=_PathFilterAction,
                dest="filter",
                type=path_filter.exclude,
                default=path_filter.PathFilter([]),
                help="Exclude files matching PATTERN.",
            )
            filter_group.add_argument(
                "--include",
                metavar="PATTERN",
                action=_PathFilterAction,
                dest="filter",
                type=path_filter.include,
                help="Include files matching PATTERN.",
            )

    def SetupLogging(self, opts):
        """Sets up logging based on |opts|."""
        value = opts.log_level.upper()
        logger = logging.getLogger()
        log_level = getattr(logging, value)
        logger.setLevel(log_level)
        # If verbose levels, include millisecond output.
        log_format = opts.log_format
        if log_level < logging.NOTICE:
            log_format = log_format.replace(
                "%(asctime)s:", "%(asctime)s.%(msecs)03d:"
            )
        formatter = ColoredFormatter(
            fmt=log_format,
            datefmt=constants.LOGGER_TIME_FMT,
            enable_color=opts.color,
        )

        # Only set colored formatter for ChromiteStreamHandler instances,
        # which could have been added by ScriptWrapperMain() below.
        chromite_handlers = [
            x for x in logger.handlers if isinstance(x, ChromiteStreamHandler)
        ]
        for handler in chromite_handlers:
            handler.setFormatter(formatter)

        logging.captureWarnings(True)

        return value

    def DoPostParseSetup(self, opts, args):
        """Method called to handle post opts/args setup.

        This can be anything from logging setup to positional arg count
        validation.

        Args:
            opts: optparse.Values or argparse.Namespace instance
            args: position arguments unconsumed from parsing.

        Returns:
            (opts, args), w/ whatever modification done.
        """
        for dest, default in self._cros_defaults.items():
            if not hasattr(opts, dest):
                setattr(opts, dest, default)

        if self.logging_enabled:
            value = self.SetupLogging(opts)
            if self.debug_enabled:
                opts.debug = value == "DEBUG"
            opts.verbose = value in ("INFO", "DEBUG")

        if self.caching:
            path = os.environ.get(constants.SHARED_CACHE_ENVVAR)
            if path is not None and opts.cache_dir is None:
                opts.cache_dir = os.path.abspath(path)

            opts.cache_dir_specified = opts.cache_dir is not None
            if not opts.cache_dir_specified:
                func = (
                    self.FindCacheDir
                    if not callable(self.caching)
                    else self.caching
                )
                opts.cache_dir = func(self, opts)
            if opts.cache_dir is not None:
                self.ConfigureCacheDir(opts.cache_dir)

        return opts, args

    @staticmethod
    def ConfigureCacheDir(cache_dir):
        if cache_dir is None:
            os.environ.pop(constants.SHARED_CACHE_ENVVAR, None)
            logging.debug("Removed cache_dir setting")
        else:
            os.environ[constants.SHARED_CACHE_ENVVAR] = cache_dir
            logging.debug("Configured cache_dir to %r", cache_dir)

    @classmethod
    def FindCacheDir(cls, _parser, _opts):
        logging.debug("Cache dir lookup.")
        return path_util.FindCacheDir()


class ArgumentNamespace(argparse.Namespace, metaclass=attrs_freezer.Class):
    """Class to mimic argparse.Namespace with value freezing support."""

    _FROZEN_ERR_MSG = "Option values are frozen, cannot alter %s."


# Note that because optparse.Values is not a new-style class this class
# must use the mixin rather than the metaclass.
class OptionValues(attrs_freezer.Mixin, optparse.Values):
    """Class to mimic optparse.Values with value freezing support."""

    _FROZEN_ERR_MSG = "Option values are frozen, cannot alter %s."

    def __init__(self, defaults, *args, **kwargs):
        attrs_freezer.Mixin.__init__(self)
        optparse.Values.__init__(self, defaults, *args, **kwargs)

        # Used by FilteringParser.
        self.parsed_args = None


PassedOption = collections.namedtuple(
    "PassedOption", ["opt_inst", "opt_str", "value_str"]
)


class FilteringParser(optparse.OptionParser, BaseParser):
    """Custom option parser for filtering options.

    Aside from adding a couple of types (path for absolute paths,
    gs_path for google storage urls, and log_level for logging level control),
    this additionally exposes logging control by default; if undesired,
    either derive from this class setting ALLOW_LOGGING to False, or
    pass in logging=False to the constructor.
    """

    DEFAULT_OPTION_CLASS = FilteringOption

    def __init__(self, usage=None, **kwargs):
        BaseParser.__init__(self, **kwargs)
        self.PopUsedArgs(kwargs)
        kwargs.setdefault("option_class", self.DEFAULT_OPTION_CLASS)
        optparse.OptionParser.__init__(self, usage=usage, **kwargs)
        self.SetupOptions()

    def add_common_argument_to_group(self, group, *args, **kwargs):
        """Adds the given option defined by args and kwargs to group."""
        return group.add_option(*args, **kwargs)

    def add_argument_group(self, *args, **kwargs):
        """Return an option group rather than an argument group."""
        return self.add_option_group(*args, **kwargs)

    def parse_args(self, args=None, values=None):
        # If no Values object is specified then use our custom OptionValues.
        if values is None:
            values = OptionValues(defaults=self.defaults)

        values.parsed_args = []

        opts, remaining = optparse.OptionParser.parse_args(
            self, args=args, values=values
        )
        return self.DoPostParseSetup(opts, remaining)

    def AddParsedArg(self, opt_inst, opt_str, value_str):
        """Add a parsed argument with attributes.

        Args:
            opt_inst: An instance of a raw optparse.Option object that
                represents the option.
            opt_str: The option string.
            value_str: A list of string-ified values dentified by OptParse.
        """
        self.values.parsed_args.append(
            PassedOption(opt_inst, opt_str, value_str)
        )

    @staticmethod
    def FilterArgs(parsed_args, filter_fn):
        """Filter the argument by passing it through a function.

        Args:
            parsed_args: The list of parsed argument namedtuples to filter.
                Tuples are of the form (opt_inst, opt_str, value_str).
            filter_fn: A function with signature f(PassedOption), and returns
                True if the argument is to be passed through. False if not.

        Returns:
            A tuple containing two lists - one of accepted arguments and one of
            removed arguments.
        """
        removed = []
        accepted = []
        for arg in parsed_args:
            target = accepted if filter_fn(arg) else removed
            target.append(arg.opt_str)
            target.extend(arg.value_str)

        return accepted, removed


class ArgumentParser(BaseParser, argparse.ArgumentParser):
    """Custom argument parser for use by chromite.

    This class additionally exposes logging control by default; if undesired,
    either derive from this class setting ALLOW_LOGGING to False, or
    pass in logging=False to the constructor.
    """

    def __init__(self, usage=None, **kwargs):
        kwargs.setdefault(
            "formatter_class", argparse.RawDescriptionHelpFormatter
        )
        BaseParser.__init__(self, **kwargs)
        self.PopUsedArgs(kwargs)
        argparse.ArgumentParser.__init__(self, usage=usage, **kwargs)
        self._SetupTypes()
        self.SetupOptions()
        self._RegisterActions()

    def _SetupTypes(self):
        """Register types with ArgumentParser."""
        for t, check_f in VALID_TYPES.items():
            self.register("type", t, check_f)
        for a, class_a in VALID_ACTIONS.items():
            self.register("action", a, class_a)

    def _RegisterActions(self):
        """Update the container's actions.

        This method builds out a new action class to register for each action
        type. The new action class allows handling the deprecated argument
        without any other changes to the argument parser logic. See
        _DeprecatedAction.
        """
        for action in _DEPRECATE_ACTIONS:
            current_class = self._registry_get("action", action, object)
            # Base classes for the new class. The _DeprecatedAction must be
            # first to ensure its method overrides are called first.
            bases = (_DeprecatedAction, current_class)
            try:
                self.register(
                    "action", action, type("deprecated-wrapper", bases, {})
                )
            except TypeError:
                # Method resolution order error. This occurs when the
                # _DeprecatedAction class is inherited multiple times, so we've
                # already registered the replacement class. The underlying
                # _ActionsContainer gets passed around, so this may get
                # triggered in non-obvious ways.
                continue

    def add_argument(self, *args, **kwargs) -> argparse.Action:
        """Override of argparse.ArgumentParser.add_argument for chromite."""
        # Ban (unquoted) `type=bool` which only accepts the empty string for a
        # `False` parameter value. The argparse documentation also recommends
        # against it. The quoted, `type="bool"`, chromite extension is fine, but
        # add_bool_argument is preferred.
        if "type" in kwargs and kwargs["type"] == bool:
            raise ValueError(
                "Unquoted `add_argument(...type=bool)` is not recommended."
                ' Use `add_bool_argument()` (preferred), or use `type="bool"`.'
            )
        return super().add_argument(*args, **kwargs)

    def add_common_argument_to_group(self, group, *args, **kwargs):
        """Adds the given argument to the group.

        This argument is expected to show up across the base parser and
        subparsers that might be added later on.  The default argparse module
        does not handle this scenario well -- it processes the base parser first
        (defaults and the user arguments), then it processes the subparser
        (defaults and arguments). That means defaults in the subparser will
        clobber user arguments passed in to the base parser!
        """
        default = kwargs.pop("default", None)
        kwargs["default"] = argparse.SUPPRESS
        action = group.add_argument(*args, **kwargs)
        self._cros_defaults.setdefault(action.dest, default)
        return action

    def add_bool_argument(
        self,
        flag: str,
        default: Optional[bool],
        enabled_desc: str,
        disabled_desc: str,
    ) -> None:
        """Adds a boolean argument conforming to chromite recommendations.

        This will add both --flag and --no-flag, storing into dest="flag", and
        with corresponding help strings. Tristate options are also supported
        (default=None), to differentiate presence of flags (either --flag or
        --no-flag) from absence. For boolean (non-tristate) flags, " (DEFAULT)"
        is appended to the help string of the one that is default when no flag
        is provided. For tristate flags, callers should make sure to explain
        the default behavior in their enabled_desc and/or disabled_desc.

        See
        https://chromium.googlesource.com/chromiumos/chromite/+/HEAD/docs/cli-guidelines.md#Boolean-Options

        Args:
            flag: The name of the flag in kebab case (e.g. "--my-bool").
            default: The default value when no flag is provided. If None, this
                is treated as tristate.
            enabled_desc: The help text to use for "--my-bool".
            disabled_desc: The help text to use for "--no-my-bool".
        """
        if not flag.startswith("--"):
            raise ValueError(f"Bool flag `{flag}` must start with `--`")
        if "_" in flag:
            raise ValueError(f"Bool flag `{flag}` must be kebab-case")
        enabled_desc += " (DEFAULT)" if default is True else ""
        disabled_desc += " (DEFAULT)" if default is False else ""
        flag = flag.lstrip("-")
        dest = flag.replace("-", "_")
        self.add_argument(
            f"--{flag}", action="store_true", default=default, help=enabled_desc
        )
        self.add_argument(
            f"--no-{flag}", action="store_false", dest=dest, help=disabled_desc
        )

    def parse_args(self, args=None, namespace=None):
        """Translates OptionParser call to equivalent ArgumentParser call."""
        # If no Namespace object is specified then use our custom
        # ArgumentNamespace.
        if namespace is None:
            namespace = ArgumentNamespace()

        # Unlike OptionParser, ArgParser works only with a single namespace and
        # no args. Re-use BaseParser DoPostParseSetup but only take the
        # namespace.
        namespace = argparse.ArgumentParser.parse_args(
            self, args=args, namespace=namespace
        )
        return self.DoPostParseSetup(namespace, None)[0]


class _ShutDownException(SystemExit):
    """Exception raised when user hits CTRL+C."""

    def __init__(self, sig_num, message):
        self.signal = sig_num
        # Setup a usage message primarily for any code that may intercept it
        # while this exception is crashing back up the stack to us.
        SystemExit.__init__(self, 128 + sig_num)
        self.args = (sig_num, message)

    def __str__(self):
        """Stringify this exception."""
        return self.args[1]


def _DefaultHandler(signum, _frame):
    # Don't double process sigterms; just trigger shutdown from the first
    # exception.
    signal.signal(signum, signal.SIG_IGN)
    raise _ShutDownException(
        signum, "Received signal %i; shutting down" % (signum,)
    )


def _RestartInChroot(cmd, chroot_args, extra_env):
    """Rerun inside the chroot.

    Args:
        cmd: Command line to run inside the chroot as a list of strings.
        chroot_args: Arguments to pass directly to cros_sdk (or None).
        extra_env: Dictionary of environmental variables to set inside the
            chroot (or None).
    """
    return cros_build_lib.run(
        cmd,
        check=False,
        enter_chroot=True,
        chroot_args=chroot_args,
        extra_env=extra_env,
        cwd=constants.SOURCE_ROOT,
    ).returncode


def RunInsideChroot(command=None, chroot_args=None):
    """Restart the current command inside the chroot.

    This method is only valid for any code that is run via ScriptWrapperMain.
    It allows proper cleanup of the local context by raising an exception
    handled in ScriptWrapperMain.

    Args:
        command: An instance of CliCommand to be restarted inside the chroot.
            |command| can be None if you do not wish to modify the log_level.
        chroot_args: List of command-line arguments to pass to cros_sdk, if
            invoked.
    """
    if cros_build_lib.IsInsideChroot():
        return

    # Produce the command line to execute inside the chroot.
    argv = command.TranslateToChrootArgv() if command else sys.argv[:]
    argv[0] = path_util.ToChrootPath(argv[0])

    # Set log-level of cros_sdk to be same as log-level of command entering the
    # chroot.
    if chroot_args is None:
        chroot_args = []
    if command is not None:
        chroot_args += ["--log-level", command.options.log_level]

    raise ChrootRequiredError(argv, chroot_args)


def RunAsRootUser(argv: List[str], preserve_env: bool = False):
    """Run the given command as the root user.

    Args:
        argv: Command line arguments to run as the root user.
        preserve_env: If True, preserve existing environment variables when
            re-executing.

    Raises:
        ValueError: If a command is not provided.
    """
    if not argv:
        raise ValueError("Command not provided to run as the root user.")

    if osutils.IsRootUser():
        return

    cmd = ["sudo"]

    if preserve_env:
        cmd.append("--preserve-env")

    cmd.extend(
        [f'HOME={os.environ["HOME"]}', f'PATH={os.environ["PATH"]}', "--"]
    )
    cmd.extend(argv)

    os.execvp(cmd[0], cmd)


def ReExec():
    """Restart the current command.

    This method is only valid for any code that is run via ScriptWrapperMain.
    It allows proper cleanup of the local context by raising an exception
    handled in ScriptWrapperMain.
    """
    # The command to exec.
    raise ExecRequiredError(sys.argv[:])


def ScriptWrapperMain(
    find_target_func,
    argv=None,
    log_level=logging.DEBUG,
    log_format=constants.LOGGER_FMT,
):
    """Function usable for chromite.script.* style wrapping.

    Note that this function invokes sys.exit on the way out by default.

    Args:
        find_target_func: a function, which, when given the absolute
            pathway the script was invoked via (for example,
            /home/ferringb/chromiumos/chromite/bin/cros_sdk; note that any
            trailing .py from the path name will be removed),
            will return the main function to invoke (that functor will take
            a single arg- a list of arguments, and shall return either None
            or an integer, to indicate the exit code).
        argv: sys.argv, or an equivalent tuple for testing. If nothing is
            given, sys.argv is defaulted to.
        log_level: Default logging level to start at.
        log_format: Default logging format to use.
    """
    if argv is None:
        argv = sys.argv[:]
    target = os.path.abspath(argv[0])
    name = os.path.basename(target)
    if target.endswith(".py"):
        target = os.path.splitext(target)[0]
    target = find_target_func(target)
    if target is None:
        print(
            "Internal error detected- no main functor found in module %r."
            % (name,),
            file=sys.stderr,
        )
        sys.exit(100)

    # If verbose levels, include millisecond output.
    if log_level < logging.NOTICE:
        log_format = log_format.replace(
            "%(asctime)s:", "%(asctime)s.%(msecs)03d:"
        )

    # Set up basic logging information for all modules that use logging.
    # Note a script target may setup default logging in its module namespace
    # which will take precedence over this.
    logger = logging.getLogger()
    logger.setLevel(log_level)
    logger_handler = ChromiteStreamHandler()
    logger_handler.setFormatter(
        logging.Formatter(fmt=log_format, datefmt=constants.LOGGER_TIME_FMT)
    )
    logger.addHandler(logger_handler)
    logging.captureWarnings(True)

    signal.signal(signal.SIGTERM, _DefaultHandler)

    ret = 1
    try:
        ret = target(argv[1:])
    except _ShutDownException as e:
        sys.stdout.flush()
        print(
            "%s: Signaled to shutdown: caught %i signal." % (name, e.signal),
            file=sys.stderr,
        )
        sys.stderr.flush()
    except SystemExit:
        # Right now, let this crash through - longer term, we'll update the
        # scripts in question to not use sys.exit, and make this into a flagged
        # error.
        raise
    except ChrootRequiredError as e:
        ret = _RestartInChroot(e.cmd, e.chroot_args, e.extra_env)
    except ExecRequiredError as e:
        logging.shutdown()
        # This does not return.
        os.execv(e.cmd[0], e.cmd)
    except Exception as e:
        sys.stdout.flush()
        print("%s: Unhandled exception:" % (name,), file=sys.stderr)
        sys.stderr.flush()
        raise
    finally:
        logging.shutdown()

    if ret is None:
        ret = 0
    sys.exit(ret)
