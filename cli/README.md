# Chromite CLI Framework

This directory contains the core CLI system.

This document covers the common APIs chromite provides when writing tools.
It does not get into CLI best practices as the [CLI Guidelines] document covers
that more generally already.

[TOC]

## Adding a new command

New commands can be added by creating a new file in `cros/` that follows
the `cros_{command_name}.py` format where the command can live.

The command class's implementation _must_:
*   Be a subclass of `cli.command.Command`
*   Have a `@command.command_decorator('command-name')` decorator on the class
*   Define an `EPILOG` class constant
*   Implement the `@classmethod` `AddParser(cls, parser)`
*   Implement `Run(self)`

Rules of thumb:
*   The `Run` method _should not_ be a full implementation of the command.
    *   It _should_ validate the raw arguments.
    *   It _should_ translate arguments to chromite constructs as applicable.
    *   It should then call a reusable implementation (e.g. in `service/`).
    *   Otherwise, it _may_ be a wrapper around a command outside of chromite.

## Argument Parser

Chromite has a subclass of `argparse.ArgumentParser` in the `lib.commandline`
module.
The `ArgumentParser` subclass adds some common functionality, and a set of
standard arguments that all scripts can take advantage of.

### Custom Argument Types

There are a number of custom types defined for the `ArgumentParser`,
which can be used with `type='custom_type_name'`.

*   ab_url: Parse android build urls.
*   bool: Parse standard shell boolean values (y/yes, n/no, 1, 0, true, false).
*   build_target: Does a regex validation of the name and produces a
    BuildTarget instance.
*   date: Parse the argument as a Y-m-d formatted date.
*   path: Expands ~/ paths and then standardizes to the real path.
*   path_exists: Expands ~/ paths and standardizes to the real path,
    then checks that the path exists.
*   file_exists: Expands ~/ paths and standardizes to the real path,
    then checks that the path exists and is a file.
*   dir_exists: Expands ~/ paths and standardizes to the real path,
    then checks that the path exists and is a directory.
*   gs_path: Processes all known GS urls and provides the equivalent gs:// url.
*   local_or_gs_path: Processes the argument as a 'path' or a 'gs_path',
    as needed.
*   path_or_uri: Like local_or_gs_path, but also parse other uri formats.

### Argument Deprecation Functionality

The `ArgumentParser` also provides support for the `deprecated` argument in the
`ArgumentParser.add_argument` method.
This argument allows marking an argument as deprecated by printing a warning
message, but still processes the argument as it normally would.
Using the `--foo` argument below would produce something like the following log
message.

```python
parser.add_argument('--foo', type=int, deprecated='Use --bar instead!')
```

```text
Argument --foo is deprecated: Use --bar instead!
```

### Defined Arguments

`logging=True` (default) enables standard logging options:

*   `--log-level=<level>`: The minimum logging level (default: info).
*   `--log-format=<format>`: Change log line format.
*   `-v`, `--verbose`: Sets the verbose option to true and sets the log-level to
    info.
*   `--debug`: Sets verbose and debug options to true and sets the log-level to
    debug.
*   `--color`, `--no-color`: Control log coloring.

The `caching=` option (disabled by default) enables the common cache dir, and
exposes the options:

*   `--cache-dir=<dir>`: Override the cache directory.

The `dryrun=` option (disabled by default) enables:

*   `-n`, `--dry-run`: Don't run commands, and show what would be done.

The `filter=` option (disabled by default) sets up a generic filter for tools
that process user-specified paths.  This filter can be accessed via `.filter`
in the parsed options object; see `chromite.utils.path_filter.PathFilter` for
more details.  It also enables:

*   `--include=<pattern>`: Paths to include in the filter.
*   `--exclude=<pattern>`: Paths to exclude from the filter.

### Standard Arguments

Generally scripts are welcome to use any arguments they need.
However, in the interest of standardizing the tools, some arguments have been
defined as being reserved for specific usages.
Not all the arguments will always apply, but when they are used, this is the
form they must have.

| Short | Long | Description |
|---|---|---|
| -b | --build-target | [Build Target](#Build-Target) |
| -d | --device | [Device](#Device) |
| | package(s) | [Packages](#Packages) |

#### Build Target

This is the new version of the `--board` option that is in scripts pre-dating
the standards.
The build target option comes with parsing support in the form of the
build_target type.
The build target type will validate the name and construct a
[BuildTarget](/lib/build_target_lib.py)
instance to assign to the variable rather than just storing the string.

```python
parser.add_argument('-b', '--build-target', type='build_target')
```

#### Device

The device argument is a long-standing type that just did not always use the
same argument naming conventions.
The device parser supports USB, File, SSH, and Servo.
A specific device argument can accept any or all of the supported types.
The example below supports USB and File, but not SSH or Servo.

```python
parser.add_argument(
    '-d', '--device',
    type=commandline.DeviceParser([commandline.DEVICE_SCHEME_USB,
                                   commandline.DEVICE_SCHEME_FILE]))
```

#### Packages

The package(s) argument should be a positional argument taking one or more
packages as appropriate.
The requirements for what must be included in the specified package(s) are
dependent on the script itself.

```python
parser.add_argument('packages', nargs='+')
```

[CLI Guidelines]: /docs/cli-guidelines.md
