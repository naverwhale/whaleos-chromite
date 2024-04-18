# `cros query`

[TOC]

`cros query` is a tool to query information about the build system. Right now,
it supports querying information about the boards, overlays, profiles, and
ebuilds.

Unlike Portage tools (such as `portageq`, `equery`, and `q`), `cros query` is
designed to work without a sysroot setup for the board, and operates across all
boards instead of a single board.  Additionally, `cros query` does not require a
ChromiumOS SDK to be setup, and only requires a source checkout.

## Command Syntax

The syntax of a query is like so:

``` shellsession
cros query <type> [options...]
```

`type` is one of `boards`, `overlays`, `profiles`, or `ebuilds`.  If you don't
add any options to filter the results, it'll print each result.  For example,
`cros query boards` will print all boards available in your checkout.

You can add filters to your command with the `-f` flag, which takes a Python
expression.  This argument can be passed multiple times.  If all provided
filters evaluate `True`, then the result is printed.

For example, `cros query boards -f '"bootimage" in use_flags'` will print all
boards which have the `bootimage` `USE` flag set.  The available attributes
(e.g., `use_flags` in the previous example) for each type is documented
[here](cros-query-types.md).

Finally, you may wish to change the output format for each result.  You can do
this with the `-o` flag, which takes a Python `format` string.  For example, to
print all boards and their corresponding `USE` flags, run:

``` shellsession
cros query boards -o "{name} {use_flags}"
```

Run `cros query --help` for a list of all flags and options.

## More Examples

For each board, show the path to its top level overlay:

``` shellsession
cros query boards -o '{name} {top_level_overlay}'
```

Show the computed global USE flags for the "volteer" board:

``` shellsession
cros query boards -f 'name == "volteer"' -o '{use_flags}'
```

Show which profiles modify (set or unset) the "bootimage" USE flag:

``` shellsession
cros query profiles -f '"bootimage" in use_flags_set | use_flags_unset'
```

Show which ebuilds IUSE the "bootimage" flag:

``` shellsession
cros query ebuilds -f '"bootimage" in iuse'
```

Show all ebuilds which inherit python-r1 and have EAPI <= 6:

``` shellsession
cros query ebuilds -f '"python-r1" in eclasses' -f 'eapi <= 6'
```

## Python API

For sufficiently complex queries, you might benefit from writing the
query as a Python script instead of as a command.  Import the
`chromite.lib.build_query` module and use the `Query` iterator to
write queries.  For example, to list all boards:

``` shellsession
from chromite.lib import build_query

all_boards = build_query.Query(build_query.Board).all()
```

The `Query` iterator can be directly iterated over (e.g., in a loop),
or you can use the following methods to filter and consume the query:

* `.filter(func)`: Add a filter function.  This will prevent the query
  iterator from returning results for which `func(result)` returns
  `False`.
* `.all()`: Get all results in a `list`.
* `.one()`: Assert there is exactly one result and return it.
* `.one_or_none()`: Assert there is zero or one results.  If zero, return
  `None`.  If one, return it.
